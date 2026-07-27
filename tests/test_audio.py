import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from contentmaxxer.audio import (
    _caption_chunks,
    proportional_word_timings,
    resolve_provider,
    retime_plan,
    synthesize_narration,
    write_aligned_srt,
)
from contentmaxxer.models import ContentPlan, VideoBeat


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


class NarrationTests(unittest.TestCase):
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

    def test_auto_provider_prefers_qwen3_then_other_local_speech(self):
        with patch.dict("os.environ", {}, clear=True):
            with patch("contentmaxxer.audio.qwen3_available", return_value=True):
                self.assertEqual(resolve_provider("auto"), "qwen3")
            with patch("contentmaxxer.audio.qwen3_available", return_value=False):
                with patch("contentmaxxer.audio.importlib.util.find_spec", return_value=object()):
                    with patch("contentmaxxer.audio.shutil.which", return_value="/usr/bin/say"):
                        self.assertEqual(resolve_provider("auto"), "chatterbox")
                with patch("contentmaxxer.audio.importlib.util.find_spec", return_value=None):
                    with patch("contentmaxxer.audio.shutil.which", return_value="/usr/bin/say"):
                        self.assertEqual(resolve_provider("auto"), "say")


if __name__ == "__main__":
    unittest.main()
