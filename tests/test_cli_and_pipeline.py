import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from contentmaxxer.cli import build_parser, main
from contentmaxxer.pipeline import (
    _displayed_headline,
    _route_recap_window_seconds,
    run_slides,
)


class CLITests(unittest.TestCase):
    def test_preview_metadata_uses_the_complete_persistent_hook(self):
        spec = SimpleNamespace(
            story={
                "text_transition_mode": (
                    "persistent_lesson_header_handwritten_captions"
                ),
                "hook_title": {
                    "text": "How does a browser turn a URL into a page?"
                },
            }
        )
        self.assertEqual(
            _displayed_headline(
                spec,
                "How does a browser turn a URL…",
                "The browser parses HTML",
            ),
            "How does a browser turn a URL into a page?",
        )

    def test_route_recap_window_covers_long_final_caption_tail(self):
        spec = SimpleNamespace(
            story={"recap_mode": "full_route_sweep"},
            primitives=[
                SimpleNamespace(
                    duration_seconds=10.2841,
                    params={
                        "captions": [
                            {
                                "start_seconds": 7.8845,
                                "end_seconds": 10.2841,
                            }
                        ]
                    },
                )
            ],
        )
        self.assertAlmostEqual(
            _route_recap_window_seconds(spec),
            2.4996,
            places=4,
        )

    def test_director_parser_accepts_animation_style(self):
        args = build_parser().parse_args(
            ["director", "orbital storage", "--animation-style", "whiteboard"]
        )
        self.assertEqual(args.animation_style, "whiteboard")

    def test_director_parser_accepts_deepgram_voice_model(self):
        args = build_parser().parse_args(
            [
                "director",
                "orbital storage",
                "--voice-provider",
                "deepgram",
                "--voice",
                "aura-2-thalia-en",
                "--voice-rate",
                "180",
                "--voice-pronunciation",
                "Amodei=ˌɑːmoʊˈdeɪ",
            ]
        )
        self.assertEqual(args.voice_provider, "deepgram")
        self.assertEqual(args.voice, "aura-2-thalia-en")
        self.assertEqual(args.voice_rate, 180)
        self.assertEqual(args.voice_pronunciation, ["Amodei=ˌɑːmoʊˈdeɪ"])
        self.assertEqual(args.word_aligner, "auto")

    def test_director_parser_accepts_explicit_mlx_whisper_alignment(self):
        args = build_parser().parse_args(
            [
                "director",
                "topic",
                "--word-aligner",
                "mlx-whisper",
                "--word-aligner-model",
                "local-whisper",
            ]
        )
        self.assertEqual(args.word_aligner, "mlx-whisper")
        self.assertEqual(args.word_aligner_model, "local-whisper")

    def test_research_command_caches_local_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            note = root / "notes.txt"
            note.write_text("Ceramic orbital storage improves measured discharge stability in the cited test.")
            code = main(["research", "orbital storage", "--output-dir", str(root / "jobs"), "--source-file", str(note)])
            self.assertEqual(code, 0)
            self.assertTrue((root / "jobs" / "orbital_storage" / "claims.json").exists())

    def test_director_without_sources_writes_blocked_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            code = main(["director", "unknown subject", "--output-dir", str(root)])
            self.assertEqual(code, 2)
            plan = json.loads((root / "unknown_subject" / "plans" / "video.json").read_text())
            self.assertFalse(plan["grounded"])
            self.assertEqual(plan["beats"], [])
            self.assertFalse((root / "unknown_subject" / "video" / "reel.mp4").exists())

    def test_slides_pipeline_has_portable_manifest_and_revision_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            note = root / "notes.txt"
            note.write_text(
                "Orbital storage cells use a documented ceramic layer that improves discharge stability. "
                "The cited test reports 25% less variance across repeated discharge cycles."
            )
            result = run_slides(
                "orbital storage",
                root / "jobs",
                source_files=[note],
                count=4,
                targets=("9:16", "4:5"),
            )
            self.assertTrue(result.qa_passed)
            job = Path(result.job_dir)
            manifest = json.loads((job / "manifest.json").read_text())
            self.assertEqual(manifest["carousel"]["count"], 4)
            self.assertFalse(Path(manifest["carousel"]["plan"]).is_absolute())
            self.assertTrue((job / "revision_history" / "carousel" / "plan.initial.json").exists())
            self.assertTrue((job / "revision_history" / "carousel" / "qa.revised.json").exists())
            self.assertTrue((job / "qa" / "carousel.json").exists())


if __name__ == "__main__":
    unittest.main()
