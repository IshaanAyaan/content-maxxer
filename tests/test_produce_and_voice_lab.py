import json
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from contentmaxxer.audio import NarrationError, run_voice_lab
from contentmaxxer.cli import _load_produce_config, build_parser


def _write_silence_wav(path: Path, seconds: float = 0.2) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(48_000)
        handle.writeframes(b"\x00\x00" * int(48_000 * seconds))


class ProduceParserTests(unittest.TestCase):
    def test_parser_accepts_voice_lab(self):
        args = build_parser().parse_args(
            [
                "voice-lab",
                "One sample sentence.",
                "--voice",
                "aura-2-thalia-en",
                "--voice",
                "aura-2-orion-en",
                "--voice-rate",
                "180",
            ]
        )
        self.assertEqual(args.command, "voice-lab")
        self.assertEqual(args.voice, ["aura-2-thalia-en", "aura-2-orion-en"])
        self.assertEqual(args.voice_rate, 180)

    def test_parser_accepts_produce(self):
        args = build_parser().parse_args(["produce", "configs/reel.json"])
        self.assertEqual(args.command, "produce")
        self.assertEqual(args.config, Path("configs/reel.json"))

    def test_parser_accepts_burn_captions_flag(self):
        args = build_parser().parse_args(["director", "topic", "--burn-captions"])
        self.assertTrue(args.burn_captions)
        args = build_parser().parse_args(["director", "topic"])
        self.assertFalse(args.burn_captions)


class ProduceConfigTests(unittest.TestCase):
    def _write(self, payload) -> Path:
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False, encoding="utf-8"
        )
        json.dump(payload, handle)
        handle.close()
        self.addCleanup(Path(handle.name).unlink)
        return Path(handle.name)

    def test_valid_config_resolves_defaults(self):
        path = self._write(
            {
                "topic": "Elastic language models",
                "job": "elastic-llms",
                "source_files": ["examples/reel-sources/elastic-llms.md"],
                "voice": "aura-2-thalia-en",
                "word_aligner": "deepgram",
                "burn_captions": True,
            }
        )
        config = _load_produce_config(path, None)
        self.assertEqual(config["topic"], "Elastic language models")
        self.assertEqual(config["job"], "elastic-llms")
        self.assertEqual(config["output_dir"], Path("build"))
        self.assertEqual(config["renderer"], "manim")
        self.assertEqual(config["animation_style"], "director_cut")
        self.assertEqual(config["voice_provider"], "deepgram")
        self.assertEqual(config["word_aligner"], "deepgram")
        self.assertTrue(config["burn_captions"])
        self.assertEqual(
            config["source_files"], [Path("examples/reel-sources/elastic-llms.md")]
        )

    def test_unknown_keys_are_rejected(self):
        path = self._write({"topic": "x", "voice_speed": 2})
        with self.assertRaises(ValueError) as ctx:
            _load_produce_config(path, None)
        self.assertIn("voice_speed", str(ctx.exception))

    def test_missing_topic_is_rejected(self):
        path = self._write({"job": "x"})
        with self.assertRaises(ValueError):
            _load_produce_config(path, None)

    def test_output_dir_override_wins(self):
        path = self._write({"topic": "x", "output_dir": "build"})
        config = _load_produce_config(path, Path("elsewhere"))
        self.assertEqual(config["output_dir"], Path("elsewhere"))


class VoiceLabTests(unittest.TestCase):
    def test_voice_lab_requires_key_and_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("contentmaxxer.audio._local_env_value", return_value=""):
                with self.assertRaises(NarrationError):
                    run_voice_lab("hello", ["aura-2-thalia-en"], Path(tmp))
            with patch("contentmaxxer.audio._local_env_value", return_value="secret"):
                with self.assertRaises(NarrationError):
                    run_voice_lab("", ["aura-2-thalia-en"], Path(tmp))
                with self.assertRaises(NarrationError):
                    run_voice_lab("hello", [], Path(tmp))

    def test_voice_lab_writes_samples_report_and_transcripts(self):
        text = "Elastic models resize themselves."

        def fake_segments(beats, directory, voice, rate_wpm, pronunciations):
            wav = Path(directory) / "01-voice_lab.wav"
            _write_silence_wav(wav)
            return (
                [(beats[0], wav)],
                {
                    "requests": [
                        {
                            "beat_id": "voice_lab",
                            "request_id": f"req-{voice}",
                            "duration_seconds": 0.2,
                        }
                    ]
                },
            )

        def fake_transcribe(audio_path, api_key, model):
            return {
                "metadata": {"request_id": "asr-1"},
                "results": {
                    "channels": [
                        {
                            "alternatives": [
                                {
                                    "words": [
                                        {"word": "elastic", "start": 0.0, "end": 0.1},
                                        {"word": "models", "start": 0.1, "end": 0.2},
                                    ]
                                }
                            ]
                        }
                    ]
                },
            }

        with tempfile.TemporaryDirectory() as tmp:
            lab_dir = Path(tmp) / "voice-lab"
            with patch("contentmaxxer.audio._local_env_value", return_value="secret"):
                with patch(
                    "contentmaxxer.audio._deepgram_segments", side_effect=fake_segments
                ):
                    with patch(
                        "contentmaxxer.alignment.transcribe_with_deepgram",
                        side_effect=fake_transcribe,
                    ):
                        report = run_voice_lab(
                            text,
                            ["aura-2-thalia-en", "aura-2-orion-en"],
                            lab_dir,
                            rate_wpm=180,
                        )

            self.assertEqual(len(report["candidates"]), 2)
            for candidate in report["candidates"]:
                self.assertTrue(Path(candidate["sample"]).is_file())
                self.assertEqual(candidate["asr_transcript"], "elastic models")
                self.assertGreater(candidate["duration_seconds"], 0.0)
            saved = json.loads((lab_dir / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["rate_wpm"], 180)


if __name__ == "__main__":
    unittest.main()
