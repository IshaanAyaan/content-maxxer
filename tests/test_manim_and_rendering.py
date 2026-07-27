import json
import os
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from contentmaxxer.content_packs import GPT56_LAUNCH, GPT56_MODELS, GPT56_SYSTEM_CARD
from contentmaxxer.manim_scene import compile_manim_scene, manim_available, write_scene_py
from contentmaxxer.models import SourceArtifact
from contentmaxxer.planning import extract_claims, plan_slides, plan_video
from contentmaxxer.raster import render_carousel


def source(source_id, origin):
    return SourceArtifact(source_id, origin.split("/")[2], origin, "url", "2026-07-09", "a" * 64, "a.txt", "a.html", "a.json")


class ManimTests(unittest.TestCase):
    def setUp(self):
        self.sources = [source("launch", GPT56_LAUNCH), source("models", GPT56_MODELS), source("card", GPT56_SYSTEM_CARD)]
        self.claims = extract_claims("GPT-5.6 family tiers", Path("."), self.sources)

    def test_compiler_is_vertical_safe_zone_aware_and_deterministic(self):
        plan = plan_video("GPT-5.6 family tiers", self.sources, self.claims)
        first = compile_manim_scene(plan)
        second = compile_manim_scene(plan)
        self.assertEqual(first, second)
        self.assertEqual((first.width, first.height), (1080, 1920))
        self.assertGreaterEqual(first.safe_zone["bottom"], 300)
        self.assertEqual(len(first.primitives), len(plan.beats))
        self.assertTrue(all(item.claim_ids for item in first.primitives))

    def test_generated_scene_contains_all_reusable_primitives(self):
        plan = plan_video("GPT-5.6 family tiers", self.sources, self.claims)
        spec = compile_manim_scene(plan)
        with tempfile.TemporaryDirectory() as tmp:
            scene = write_scene_py(Path(tmp), spec).read_text(encoding="utf-8")
        for primitive in ("model_cards", "timeline", "comparison_grid", "tokens_context", "eval_bars", "agent_loop", "claim_callout", "routing_diagram", "before_after"):
            self.assertIn(f"def {primitive}", scene)
        for hand_drawn_marker in (
            "def rough_path",
            "def sticky_note",
            "def chalk_dust",
            "SKETCH {stage + 1}/5",
            "FadeOut(current_visual",
            "LaggedStart(",
        ):
            self.assertIn(hand_drawn_marker, scene)
        self.assertNotIn("FadeTransformPieces(current_visual, visual)", scene)

    @unittest.skipUnless(os.getenv("CONTENTMAXXER_MANIM_INTEGRATION") == "1", "set integration flag to test local Manim")
    def test_manim_integration_available(self):
        self.assertTrue(manim_available())


class CarouselRenderTests(unittest.TestCase):
    def test_paper_meme_style_is_code_native(self):
        sources = [source("launch", GPT56_LAUNCH), source("models", GPT56_MODELS), source("card", GPT56_SYSTEM_CARD)]
        claims = extract_claims("GPT-5.6 family tiers", Path("."), sources)
        plan = plan_slides("GPT-5.6 family tiers", sources, claims, 3, visual_theme="paper_meme_v1")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = render_carousel(plan, root, ("4:5",))
            metadata = json.loads((root / result["variants"]["4:5"]["metadata"]).read_text())
            self.assertEqual(metadata["palette"], "paper_meme_v1")
            self.assertIsNone(metadata["hero_asset"])
            self.assertEqual(metadata["slides"][0]["visual_asset"], "code_native_paper_collage")

    def test_dual_targets_are_adapted_and_exact(self):
        sources = [source("launch", GPT56_LAUNCH), source("models", GPT56_MODELS), source("card", GPT56_SYSTEM_CARD)]
        claims = extract_claims("GPT-5.6 family tiers", Path("."), sources)
        plan = plan_slides("GPT-5.6 family tiers", sources, claims, 3)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = render_carousel(plan, root, ("9:16", "4:5"))
            self.assertEqual(result["count"], 3)
            self.assertEqual(set(result["variants"]), {"9:16", "4:5"})
            vertical = root / result["variants"]["9:16"]["slides"][0]
            feed = root / result["variants"]["4:5"]["slides"][0]
            with Image.open(vertical) as image:
                self.assertEqual(image.size, (1080, 1920))
            with Image.open(feed) as image:
                self.assertEqual(image.size, (1080, 1350))
            vertical_meta = json.loads((root / result["variants"]["9:16"]["metadata"]).read_text())
            feed_meta = json.loads((root / result["variants"]["4:5"]["metadata"]).read_text())
            self.assertNotEqual(vertical_meta["slides"][0]["text_boxes"][0]["box"], feed_meta["slides"][0]["text_boxes"][0]["box"])
            self.assertEqual(vertical_meta["palette"], "editorial_heat_v1")
            self.assertEqual(len(vertical_meta["cover_variants"]), 3)
            self.assertTrue(vertical_meta["slides"][0]["swipe_cue"])
            self.assertEqual(vertical_meta["slides"][0]["template"], "cover_hero")


if __name__ == "__main__":
    unittest.main()
