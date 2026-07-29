import io
import json
import tempfile
import unittest
import wave
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from contentmaxxer.audio import (
    _caption_chunks,
    _local_env_value,
    deepgram_speed_for_rate,
    mux_narration,
    proportional_word_timings,
    resolve_provider,
    retime_plan,
    synthesize_narration,
    tts_sentence_chunks,
    write_aligned_srt,
)
from contentmaxxer.alignment import WordAlignmentError, map_whisper_words_to_script
from contentmaxxer.models import ContentPlan, NarrationCue, NarrationTrack, VideoBeat


def _plan() -> ContentPlan:
    return ContentPlan(
        id="video_test",
        topic="Why orbits do not fall straight down",
        format="video",
        hook_style="question",
        hook="Why does an orbit keep missing Earth?",
        visual_thesis="A velocity arrow turns a fall into a continuous miss.",
        source_ids=["source_1"],
        claims=[],
        beats=[
            VideoBeat(
                id="hook",
                purpose="hook",
                headline="An orbit is a fall",
                narration="Gravity pulls the satellite down.",
                on_screen_text="Gravity pulls down",
                claim_ids=["claim_1"],
                source_label="Test source",
                primitive="orbit_trace",
            ),
            VideoBeat(
                id="mechanism",
                purpose="mechanism",
                headline="But it keeps missing",
                narration="Sideways velocity moves Earth away at the same time.",
                on_screen_text="Sideways speed changes the path",
                claim_ids=["claim_1"],
                source_label="Test source",
                primitive="vector_transform",
            ),
        ],
    )


def _write_silence(path: Path, duration: float, rate: int = 48_000) -> None:
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(b"\x00\x00" * int(duration * rate))


def _spoken_wav_bytes(duration: float = 1.5, rate: int = 48_000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes((1000).to_bytes(2, "little", signed=True) * int(duration * rate))
    return buffer.getvalue()


class _FakeDeepgramResponse:
    def __init__(self, payload: bytes, headers: dict):
        self.payload = payload
        self.headers = headers

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.payload


class NarrationTests(unittest.TestCase):
    def test_whisper_timestamps_map_to_exact_script_with_name_substitution_and_split_word(self):
        text = (
            "NVIDIA and Amodei compare open weights while defenders inspect "
            "industrial-scale distillation systems."
        )
        script_words = text.split()
        cue = NarrationCue(
            "beat",
            text,
            0.0,
            5.0,
            proportional_word_timings(text, "beat", 0.0, 5.0),
        )
        asr_text = [
            "NVIDIA",
            "and",
            "Omoaday",
            "compare",
            "open",
            "weights",
            "while",
            "defenders",
            "inspect",
            "industrial",
            "-scale",
            "distillation",
            "systems.",
        ]
        cursor = 0.2
        words = []
        for word in asr_text:
            words.append({"word": word, "start": cursor, "end": cursor + 0.25, "probability": 0.95})
            cursor += 0.3
        aligned, report = map_whisper_words_to_script(
            [cue],
            {"segments": [{"words": words}]},
        )
        self.assertEqual([word.text for word in aligned[0].words], script_words)
        self.assertAlmostEqual(aligned[0].words[2].start_seconds, words[2]["start"], places=4)
        self.assertAlmostEqual(aligned[0].words[9].start_seconds, words[9]["start"], places=4)
        self.assertAlmostEqual(aligned[0].words[9].end_seconds, words[10]["end"], places=4)
        self.assertEqual(report["substitutions"], 1)
        self.assertEqual(report["merged_tokens"], 1)
        self.assertEqual(report["timing_coverage_percent"], 100.0)

    def test_whisper_mapping_rejects_lexically_unrelated_audio(self):
        text = "one two three four five six seven eight nine ten"
        cue = NarrationCue(
            "beat",
            text,
            0.0,
            5.0,
            proportional_word_timings(text, "beat", 0.0, 5.0),
        )
        payload = {
            "segments": [
                {
                    "words": [
                        {"word": f"wrong{index}", "start": index * 0.3, "end": index * 0.3 + 0.2}
                        for index in range(10)
                    ]
                }
            ]
        }
        with self.assertRaises(WordAlignmentError):
            map_whisper_words_to_script([cue], payload)

    def test_whisper_mapping_recovers_fused_article_and_technical_term(self):
        text = "A softmax converts scores into normalized weights for each token."
        cue = NarrationCue(
            "beat",
            text,
            0.0,
            4.0,
            proportional_word_timings(text, "beat", 0.0, 4.0),
        )
        transcript = [
            "AssantMax",
            "converts",
            "scores",
            "into",
            "normalized",
            "weights",
            "for",
            "each",
            "token.",
        ]
        payload = {
            "segments": [
                {
                    "words": [
                        {
                            "word": word,
                            "start": index * 0.35,
                            "end": index * 0.35 + 0.3,
                        }
                        for index, word in enumerate(transcript)
                    ]
                }
            ]
        }
        aligned, report = map_whisper_words_to_script([cue], payload)
        self.assertEqual([word.text for word in aligned[0].words], text.split())
        self.assertEqual(report["timing_coverage_percent"], 100.0)
        self.assertEqual(report["fallback_word_count"], 0)
        self.assertEqual(report["deletions"], 0)
        self.assertEqual(report["substitutions"], 1)

    def test_tts_sentence_chunks_preserve_copy_and_bound_generation_units(self):
        text = (
            "Two heads. Same result. Start with a fair coin and a trick coin that always lands heads. "
            "The unnormalized weights are one eighth for fair, one half for trick, and then we normalize."
        )
        chunks = tts_sentence_chunks(text, max_words=12)
        self.assertEqual(" ".join(chunks), text)
        self.assertTrue(all(len(chunk.split()) <= 12 for chunk in chunks))
        self.assertGreaterEqual(len(chunks), 4)

    def test_proportional_word_timings_cover_exact_interval(self):
        words = proportional_word_timings("Build it, then transform it.", "beat", 1.25, 4.75)
        self.assertEqual([word.text for word in words], ["Build", "it,", "then", "transform", "it."])
        self.assertEqual(words[0].start_seconds, 1.25)
        self.assertEqual(words[-1].end_seconds, 4.75)
        self.assertTrue(all(first.end_seconds <= second.start_seconds for first, second in zip(words, words[1:])))

    def test_file_narration_controls_plan_duration_and_writes_word_captions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "voice.wav"
            _write_silence(source, 8.0)
            plan = _plan()
            track = synthesize_narration(
                plan,
                root / "job",
                provider="file",
                narration_file=source,
            )
            self.assertIsNotNone(track)
            revised = retime_plan(plan, track)
            self.assertAlmostEqual(sum(beat.duration_seconds for beat in revised.beats), track.duration_seconds, places=2)
            self.assertAlmostEqual(track.duration_seconds, 8.0, delta=0.05)
            self.assertEqual(
                sum(len(cue.words) for cue in track.cues),
                sum(len(beat.narration.split()) for beat in plan.beats),
            )
            captions = write_aligned_srt(track, root / "job" / "video" / "captions.srt")
            text = captions.read_text()
            self.assertIn("Gravity pulls the satellite", text)
            self.assertIn("down.", text)
            self.assertGreater(text.count("-->"), 1)

    def test_file_narration_can_reuse_exact_master_timings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "voice.wav"
            _write_silence(source, 8.0)
            plan = _plan()
            cues = []
            for beat, start, end in zip(plan.beats, (0.0, 3.25), (3.25, 8.0)):
                cues.append(
                    {
                        "beat_id": beat.id,
                        "text": beat.narration,
                        "start_seconds": start,
                        "end_seconds": end,
                        "words": [
                            word.__dict__
                            for word in proportional_word_timings(
                                beat.narration,
                                beat.id,
                                start,
                                end,
                            )
                        ],
                    }
                )
            timings = root / "timings.json"
            raw_alignment = root / "alignment.json"
            raw_alignment.write_text('{"segments": []}\n', encoding="utf-8")
            timings.write_text(
                json.dumps(
                    {
                        "provider": "qwen3",
                        "voice": "Aiden",
                        "duration_seconds": 8.0,
                        "alignment_method": "measured_audio_proportional_words",
                        "cues": cues,
                        "metadata": {
                            "word_alignment": {
                                "status": "aligned",
                                "raw_transcript": "alignment.json",
                            }
                        },
                    }
                )
            )
            track = synthesize_narration(
                plan,
                root / "job",
                provider="file",
                narration_file=source,
                narration_timings=timings,
            )
            self.assertEqual(track.provider, "qwen3")
            self.assertEqual(track.voice, "Aiden (master import)")
            self.assertEqual([cue.end_seconds for cue in track.cues], [3.25, 8.0])
            self.assertEqual(
                (root / "job" / "video" / "narration" / "voiceover.wav").read_bytes(),
                source.read_bytes(),
            )
            self.assertEqual(
                (root / "job" / "alignment.json").read_bytes(),
                raw_alignment.read_bytes(),
            )

            payload = json.loads(timings.read_text(encoding="utf-8"))
            payload["voice"] = track.voice
            timings.write_text(json.dumps(payload), encoding="utf-8")
            second_track = synthesize_narration(
                plan,
                root / "second-job",
                provider="file",
                narration_file=source,
                narration_timings=timings,
            )
            self.assertEqual(second_track.voice, "Aiden (master import)")

            punctuation_plan = replace(
                plan,
                beats=[
                    replace(
                        plan.beats[0],
                        narration=plan.beats[0].narration.replace(
                            "satellite",
                            "satellite,",
                            1,
                        ),
                    ),
                    plan.beats[1],
                ],
            )
            punctuation_track = synthesize_narration(
                punctuation_plan,
                root / "punctuation-job",
                provider="file",
                narration_file=source,
                narration_timings=timings,
            )
            self.assertIn(",", punctuation_track.cues[0].text)
            self.assertTrue(
                any(
                    word.text.endswith(",")
                    for word in punctuation_track.cues[0].words
                )
            )
            self.assertEqual(
                punctuation_track.metadata["imported_script_match"][
                    "punctuation_normalized_beat_count"
                ],
                1,
            )
            lexical_plan = replace(
                punctuation_plan,
                beats=[
                    replace(
                        punctuation_plan.beats[0],
                        narration=punctuation_plan.beats[0].narration.replace(
                            "Gravity",
                            "Magnetism",
                            1,
                        ),
                    ),
                    punctuation_plan.beats[1],
                ],
            )
            with self.assertRaisesRegex(
                Exception,
                "do not match the current script",
            ):
                synthesize_narration(
                    lexical_plan,
                    root / "lexical-job",
                    provider="file",
                    narration_file=source,
                    narration_timings=timings,
                )

    def test_caption_chunks_are_short_enough_for_vertical_phrase_cards(self):
        words = proportional_word_timings(
            "one two three four five six seven eight nine",
            "beat",
            0.0,
            4.5,
        )
        chunks = _caption_chunks(words)
        self.assertTrue(chunks)
        self.assertTrue(all(len(chunk) <= 4 for chunk in chunks))

    def test_mux_pins_delivery_audio_to_standard_mono_48khz(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "video" / "reel.mp4"
            video.parent.mkdir(parents=True)
            video.write_bytes(b"unmuxed")
            track = NarrationTrack(
                provider="file",
                voice="test",
                audio_path="video/narration/voiceover.wav",
                duration_seconds=1.0,
                sample_rate=48_000,
                alignment_method="measured_audio_proportional_words",
            )

            def fake_run(command, _label):
                Path(command[-1]).write_bytes(b"muxed")

            with patch("contentmaxxer.audio._run", side_effect=fake_run) as run:
                with patch(
                    "contentmaxxer.audio._media_streams",
                    return_value={
                        "has_audio": True,
                        "has_video": True,
                        "duration_seconds": 1.0,
                        "encoded_sample_rate": 48_000,
                        "encoded_channel_layout": "mono",
                    },
                ):
                    with patch("contentmaxxer.audio._audio_quality", return_value={}):
                        metadata = mux_narration(root, video, track)

            command = run.call_args.args[0]
            self.assertEqual(command[command.index("-ar") + 1], "48000")
            self.assertEqual(command[command.index("-ac") + 1], "1")
            self.assertEqual(metadata["encoded_sample_rate"], 48_000)
            self.assertEqual(metadata["encoded_channel_layout"], "mono")

    def test_auto_provider_prefers_qwen3_then_other_local_speech(self):
        with patch.dict("os.environ", {"DEEPGRAM_API_KEY": "configured-but-explicit"}, clear=True):
            with patch("contentmaxxer.audio.qwen3_available", return_value=True):
                self.assertEqual(resolve_provider("auto"), "qwen3")
            with patch("contentmaxxer.audio.qwen3_available", return_value=False):
                with patch("contentmaxxer.audio.importlib.util.find_spec", return_value=object()):
                    with patch("contentmaxxer.audio.shutil.which", return_value="/usr/bin/say"):
                        self.assertEqual(resolve_provider("auto"), "chatterbox")
                with patch("contentmaxxer.audio.importlib.util.find_spec", return_value=None):
                    with patch("contentmaxxer.audio.shutil.which", return_value="/usr/bin/say"):
                        self.assertEqual(resolve_provider("auto"), "say")

    def test_deepgram_rate_maps_to_documented_speed_range(self):
        self.assertEqual(deepgram_speed_for_rate(170), 1.0)
        self.assertEqual(deepgram_speed_for_rate(119), 0.7)
        self.assertEqual(deepgram_speed_for_rate(255), 1.5)

    def test_deepgram_pronunciation_removes_invalid_word_internal_spaces(self):
        from contentmaxxer.audio import _deepgram_pronunciation_map

        self.assertEqual(
            _deepgram_pronunciation_map(
                ["cwnd=ˌsiː ˌdʌbəljuː ˌɛn ˈdiː"]
            ),
            {"cwnd": "ˌsiːˌdʌbəljuːˌɛnˈdiː"},
        )
        self.assertEqual(deepgram_speed_for_rate(80), 0.7)
        self.assertEqual(deepgram_speed_for_rate(400), 1.5)

    def test_local_env_reader_reads_value_without_executing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            marker = root / "must-not-exist"
            (root / ".env.local").write_text(
                "DEEPGRAM_API_KEY='test-value'\n"
                f"UNRELATED=$(touch {marker})\n",
                encoding="utf-8",
            )
            with patch.dict("os.environ", {}, clear=True):
                with patch("contentmaxxer.audio.PROJECT_ROOT", root):
                    self.assertEqual(_local_env_value("DEEPGRAM_API_KEY"), "test-value")
            self.assertFalse(marker.exists())

    def test_deepgram_provider_requests_linear16_wav_and_records_metadata(self):
        calls = []

        def fake_urlopen(request, timeout):
            calls.append((request, timeout))
            return _FakeDeepgramResponse(
                _spoken_wav_bytes(),
                {
                    "dg-request-id": f"request-{len(calls)}",
                    "dg-model-name": "aura-2-thalia-en",
                    "dg-char-count": "42",
                    "dg-speed-used": "1.0",
                },
            )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("contentmaxxer.audio._local_env_value", return_value="test-only-key"):
                with patch("contentmaxxer.audio.urllib.request.urlopen", side_effect=fake_urlopen):
                    track = synthesize_narration(
                        _plan(),
                        root / "job",
                        provider="deepgram",
                        rate_wpm=170,
                        voice_pronunciations=["Gravity=ˈɡrævəti"],
                    )
            self.assertEqual(track.provider, "deepgram")
            self.assertEqual(track.voice, "aura-2-thalia-en")
            self.assertEqual(track.alignment_method, "measured_audio_proportional_words")
            self.assertEqual(track.metadata["character_count"], 84)
            self.assertEqual(track.metadata["request_count"], 2)
            self.assertEqual(track.metadata["requests"][0]["request_id"], "request-1")
            self.assertEqual(track.metadata["pronunciations"], [{"word": "Gravity", "ipa": "ˈɡrævəti"}])
            self.assertTrue((root / "job" / "video" / "narration" / "voiceover.wav").is_file())

        self.assertEqual(len(calls), 2)
        for request, timeout in calls:
            self.assertEqual(timeout, 120)
            self.assertIn("encoding=linear16", request.full_url)
            self.assertIn("container=wav", request.full_url)
            self.assertIn("sample_rate=48000", request.full_url)
            self.assertIn("speed=1.000", request.full_url)
            self.assertEqual(request.get_header("Authorization"), "Token test-only-key")
        payloads = [json.loads(request.data.decode("utf-8"))["text"] for request, _timeout in calls]
        self.assertIn(r'\{"word": "Gravity", "pronounce": "ˈɡrævəti"\}', payloads[0])
        self.assertNotIn("pronounce", payloads[1])


if __name__ == "__main__":
    unittest.main()
