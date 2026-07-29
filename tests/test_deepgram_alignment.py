import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from contentmaxxer.alignment import (
    DEEPGRAM_ALIGNMENT_METHOD,
    WordAlignmentError,
    align_track_with_deepgram,
    deepgram_words_to_whisper_payload,
)
from contentmaxxer.audio import (
    NarrationError,
    _maybe_align_narration,
    proportional_word_timings,
)
from contentmaxxer.models import NarrationCue, NarrationTrack


def _deepgram_payload(words, request_id="req-123"):
    return {
        "metadata": {"request_id": request_id},
        "results": {
            "channels": [
                {
                    "alternatives": [
                        {
                            "transcript": " ".join(item["word"] for item in words),
                            "confidence": 0.98,
                            "words": words,
                        }
                    ]
                }
            ]
        },
    }


def _track(text: str, duration: float) -> NarrationTrack:
    cue = NarrationCue(
        "beat",
        text,
        0.0,
        duration,
        proportional_word_timings(text, "beat", 0.0, duration),
    )
    return NarrationTrack(
        provider="deepgram",
        voice="aura-2-thalia-en",
        audio_path="video/narration/voiceover.wav",
        duration_seconds=duration,
        sample_rate=48_000,
        alignment_method="measured_audio_proportional_words",
        cues=[cue],
    )


class DeepgramPayloadConversionTests(unittest.TestCase):
    def test_listen_response_converts_to_mapper_payload(self):
        payload = _deepgram_payload(
            [
                {"word": "elastic", "start": 0.1, "end": 0.5, "confidence": 0.99},
                {"word": "models", "start": 0.55, "end": 0.9, "confidence": 0.97},
            ]
        )
        converted = deepgram_words_to_whisper_payload(payload)
        words = converted["segments"][0]["words"]
        self.assertEqual([w["word"] for w in words], ["elastic", "models"])
        self.assertAlmostEqual(words[0]["start"], 0.1)
        self.assertAlmostEqual(words[1]["end"], 0.9)
        self.assertAlmostEqual(words[0]["probability"], 0.99)

    def test_malformed_entries_are_skipped(self):
        payload = _deepgram_payload(
            [
                {"word": "", "start": 0.0, "end": 0.4},
                {"word": "kept", "start": "bad", "end": 0.6},
                {"word": "kept", "start": 0.5, "end": 0.5},
                {"word": "good", "start": 0.7, "end": 1.0},
            ]
        )
        converted = deepgram_words_to_whisper_payload(payload)
        words = converted["segments"][0]["words"]
        self.assertEqual(len(words), 1)
        self.assertEqual(words[0]["word"], "good")

    def test_empty_response_produces_empty_word_list(self):
        converted = deepgram_words_to_whisper_payload({"results": {}})
        self.assertEqual(converted["segments"][0]["words"], [])


class DeepgramAlignTrackTests(unittest.TestCase):
    def test_aligns_track_and_records_report_and_raw_payload(self):
        text = "elastic models resize themselves at inference time"
        track = _track(text, 3.5)
        script_words = text.split()
        asr_words = []
        cursor = 0.2
        for word in script_words:
            asr_words.append(
                {"word": word, "start": cursor, "end": cursor + 0.3, "confidence": 0.98}
            )
            cursor += 0.45
        payload = _deepgram_payload(asr_words)

        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp)

            def fake_transcribe(audio_path, api_key, model):
                self.assertEqual(api_key, "secret")
                self.assertEqual(model, "nova-3")
                return payload

            aligned = align_track_with_deepgram(
                track,
                job_dir,
                "secret",
                "nova-3",
                transcribe=fake_transcribe,
            )

            self.assertEqual(aligned.alignment_method, DEEPGRAM_ALIGNMENT_METHOD)
            self.assertEqual(
                [word.text for word in aligned.cues[0].words], script_words
            )
            report = aligned.metadata["word_alignment"]
            self.assertEqual(report["status"], "aligned")
            self.assertEqual(report["model"], "nova-3")
            self.assertEqual(report["request_id"], "req-123")
            self.assertEqual(report["timing_coverage_percent"], 100.0)
            raw_path = job_dir / "video" / "narration" / "deepgram-word-alignment.json"
            self.assertTrue(raw_path.is_file())
            saved = json.loads(raw_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["metadata"]["request_id"], "req-123")

    def test_unrelated_transcript_is_rejected_by_acceptance_thresholds(self):
        text = "one two three four five six seven eight nine ten"
        track = _track(text, 4.0)
        asr_words = [
            {"word": f"wrong{index}", "start": index * 0.3, "end": index * 0.3 + 0.2}
            for index in range(10)
        ]
        payload = _deepgram_payload(asr_words)

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(WordAlignmentError):
                align_track_with_deepgram(
                    track,
                    Path(tmp),
                    "secret",
                    transcribe=lambda *args: payload,
                )


class DeepgramAlignerRoutingTests(unittest.TestCase):
    def test_explicit_deepgram_aligner_requires_key(self):
        track = _track("a short line", 1.0)
        with tempfile.TemporaryDirectory() as tmp:
            with patch("contentmaxxer.audio._local_env_value", return_value=""):
                with self.assertRaises(NarrationError):
                    _maybe_align_narration(
                        track,
                        Path(tmp),
                        "deepgram",
                        None,
                        "mlx-community/whisper-large-v3-turbo-asr-fp16",
                        imported_timings=False,
                    )

    def test_explicit_deepgram_aligner_uses_nova_default_and_hard_fails(self):
        track = _track("a short line", 1.0)
        with tempfile.TemporaryDirectory() as tmp:
            with patch("contentmaxxer.audio._local_env_value", return_value="secret"):
                with patch(
                    "contentmaxxer.audio.align_track_with_deepgram",
                    side_effect=WordAlignmentError("rejected"),
                ) as align:
                    with self.assertRaises(NarrationError):
                        _maybe_align_narration(
                            track,
                            Path(tmp),
                            "deepgram",
                            None,
                            "mlx-community/whisper-large-v3-turbo-asr-fp16",
                            imported_timings=False,
                        )
            args, _kwargs = align.call_args
            self.assertEqual(args[2], "secret")
            self.assertEqual(args[3], "nova-3")

    def test_explicit_deepgram_aligner_realigns_imported_timings(self):
        track = _track("a short line", 1.0)
        with tempfile.TemporaryDirectory() as tmp:
            with patch("contentmaxxer.audio._local_env_value", return_value="secret"):
                with patch(
                    "contentmaxxer.audio.align_track_with_deepgram",
                    return_value=track,
                ) as align:
                    result = _maybe_align_narration(
                        track,
                        Path(tmp),
                        "deepgram",
                        None,
                        "mlx-community/whisper-large-v3-turbo-asr-fp16",
                        imported_timings=True,
                    )
            self.assertIs(result, track)
            self.assertEqual(align.call_count, 1)

    def test_auto_behavior_is_unchanged_for_imported_timings(self):
        track = _track("a short line", 1.0)
        with tempfile.TemporaryDirectory() as tmp:
            result = _maybe_align_narration(
                track,
                Path(tmp),
                "auto",
                None,
                "mlx-community/whisper-large-v3-turbo-asr-fp16",
                imported_timings=True,
            )
        self.assertIs(result, track)


if __name__ == "__main__":
    unittest.main()
