import json
import tempfile
import unittest
from pathlib import Path

from contentmaxxer.cli import main
from contentmaxxer.pipeline import run_slides


class CLITests(unittest.TestCase):
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
