import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from contentmaxxer.audio import (
    NarrationError,
    _ass_timestamp,
    burn_captions_into_reel,
    proportional_word_timings,
    write_caption_ass,
)
from contentmaxxer.models import NarrationCue, NarrationTrack


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


class AssTimestampTests(unittest.TestCase):
    def test_timestamps_are_centisecond_ass_format(self):
        self.assertEqual(_ass_timestamp(0.0), "0:00:00.00")
        self.assertEqual(_ass_timestamp(1.234), "0:00:01.23")
        self.assertEqual(_ass_timestamp(61.5), "0:01:01.50")
        self.assertEqual(_ass_timestamp(3600.0), "1:00:00.00")


class CaptionAssTests(unittest.TestCase):
    def test_ass_file_has_style_and_short_word_synced_cards(self):
        track = _track(
            "Elastic models resize themselves. One network serves many sizes.",
            5.0,
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "captions.ass"
            write_caption_ass(track, path)
            content = path.read_text(encoding="utf-8")
        self.assertIn("PlayResX: 1080", content)
        self.assertIn("PlayResY: 1920", content)
        self.assertIn("Style: Caption", content)
        dialogues = [line for line in content.splitlines() if line.startswith("Dialogue:")]
        self.assertTrue(dialogues)
        for line in dialogues:
            text = line.split(",", 9)[-1]
            self.assertLessEqual(len(text.split()), 5)

    def test_braces_are_sanitized_so_no_override_tags_leak(self):
        track = _track("weights {scale} cleanly", 2.0)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "captions.ass"
            write_caption_ass(track, path)
            content = path.read_text(encoding="utf-8")
        self.assertNotIn("{scale}", content)
        self.assertIn("(scale)", content)


class BurnCaptionTests(unittest.TestCase):
    def test_burn_writes_sidecar_output_and_reports_cards(self):
        track = _track("Elastic models resize themselves at inference time.", 4.0)
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp)
            video = job_dir / "video" / "reel.mp4"
            video.parent.mkdir(parents=True)
            video.write_bytes(b"reel")

            def fake_run(command, _label):
                Path(command[-1]).write_bytes(b"captioned")

            streams = {
                "has_audio": True,
                "has_video": True,
                "duration_seconds": 4.0,
                "encoded_sample_rate": 48_000,
                "encoded_channel_layout": "mono",
            }
            with patch("contentmaxxer.audio._run", side_effect=fake_run):
                with patch("contentmaxxer.audio._media_streams", return_value=streams):
                    report = burn_captions_into_reel(job_dir, video, track)

        self.assertEqual(report["captioned_mp4"], "video/reel-captioned.mp4")
        self.assertEqual(report["ass"], "video/captions.ass")
        self.assertGreater(report["caption_card_count"], 0)
        self.assertGreater(report["median_caption_dwell_seconds"], 0.0)
        self.assertGreater(report["caption_transitions_per_minute"], 0.0)

    def test_burn_rejects_output_that_lost_a_stream(self):
        track = _track("A short line.", 1.0)
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp)
            video = job_dir / "video" / "reel.mp4"
            video.parent.mkdir(parents=True)
            video.write_bytes(b"reel")

            def fake_run(command, _label):
                Path(command[-1]).write_bytes(b"captioned")

            broken = {
                "has_audio": False,
                "has_video": True,
                "duration_seconds": 1.0,
                "encoded_sample_rate": None,
                "encoded_channel_layout": None,
            }
            with patch("contentmaxxer.audio._run", side_effect=fake_run):
                with patch("contentmaxxer.audio._media_streams", return_value=broken):
                    with self.assertRaises(NarrationError):
                        burn_captions_into_reel(job_dir, video, track)

    def test_burn_rejects_duration_drift(self):
        track = _track("A short line.", 1.0)
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp)
            video = job_dir / "video" / "reel.mp4"
            video.parent.mkdir(parents=True)
            video.write_bytes(b"reel")

            def fake_run(command, _label):
                Path(command[-1]).write_bytes(b"captioned")

            def fake_streams(path):
                return {
                    "has_audio": True,
                    "has_video": True,
                    "duration_seconds": 1.0 if path == video else 2.0,
                    "encoded_sample_rate": 48_000,
                    "encoded_channel_layout": "mono",
                }

            with patch("contentmaxxer.audio._run", side_effect=fake_run):
                with patch("contentmaxxer.audio._media_streams", side_effect=fake_streams):
                    with self.assertRaises(NarrationError):
                        burn_captions_into_reel(job_dir, video, track)


if __name__ == "__main__":
    unittest.main()
