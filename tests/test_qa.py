import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from contentmaxxer.models import Claim, ClaimType, ContentPlan, SlideSpec, VideoBeat
from contentmaxxer.qa import _layout_checks, _manifest_check, _media_checks, revise_plan


class QAGateTests(unittest.TestCase):
    def test_media_gates_catch_missing_wrong_blank_and_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            blank = root / "blank.png"
            copy = root / "copy.png"
            Image.new("RGB", (100, 100), "white").save(blank)
            copy.write_bytes(blank.read_bytes())
            checks = _media_checks([blank, copy, root / "missing.png"], expected=(200, 200))
            failed = {check.name for check in checks if not check.passed}
            self.assertEqual(failed, {"missing_files", "exact_dimensions", "blank_media", "duplicate_media"})

    def test_layout_gates_catch_text_size_truncation_overlap_density_and_bounds(self):
        item = {
            "id": "bad",
            "width": 100,
            "height": 100,
            "safe_zone": [10, 10, 90, 90],
            "text_boxes": [
                {"box": [-1, 0, 90, 90], "font_size": 12, "truncated": True, "text": "x" * 500},
                {"box": [20, 20, 80, 80], "font_size": 20, "truncated": False, "text": "overlap"},
            ],
        }
        checks = _layout_checks([item])
        failed = {check.name for check in checks if not check.passed}
        self.assertEqual(failed, {"safe_zones", "text_size", "truncation", "overlap", "density"})

    def test_manifest_gate_rejects_absolute_and_missing_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"schema_version": "1.0", "mp4": "/tmp/absolute.mp4", "plan": "missing.json"}))
            check = _manifest_check(root, manifest)
            self.assertFalse(check.passed)
            self.assertIn("absolute", check.detail)
            self.assertIn("missing", check.detail)

    def test_revision_trims_and_sets_readable_caption_timing(self):
        claim = Claim("c", "fact", "evidence", "s", "https://example.com", "source", 1.0, ClaimType.OFFICIAL_FACT)
        plan = ContentPlan(
            id="p",
            topic="topic",
            format="video",
            hook_style="direct",
            hook="hook",
            visual_thesis="thesis",
            source_ids=["s"],
            claims=[claim],
            beats=[VideoBeat("b", "body", "h" * 300, "word " * 60, "word " * 60, ["c"], "source", "claim_callout", 2.0)],
        )
        revised = revise_plan(plan)
        self.assertLessEqual(len(revised.beats[0].headline), 150)
        self.assertGreater(revised.beats[0].duration_seconds, 3.0)
        rate = len(revised.beats[0].narration.split()) / revised.beats[0].duration_seconds * 60
        self.assertAlmostEqual(rate, 180.0, places=1)


if __name__ == "__main__":
    unittest.main()
