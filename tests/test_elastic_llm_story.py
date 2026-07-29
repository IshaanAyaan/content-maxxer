import tempfile
import unittest
from pathlib import Path

from contentmaxxer.manim_scene import compile_manim_scene, write_scene_py
from contentmaxxer.models import Claim, ClaimType, SourceArtifact
from contentmaxxer.planning import plan_video


ELASTIC_TEXTS = [
    (
        "Google's Gemma 3n is built on the MatFormer (Matryoshka Transformer) "
        "architecture, a nested transformer for elastic inference in which a larger "
        "model contains smaller, fully functional versions of itself, the way "
        "Matryoshka dolls nest inside each other."
    ),
    (
        "During MatFormer training of Gemma 3n's E4B model, a smaller E2B sub-model "
        "is simultaneously optimized inside it, so developers can download either "
        "the main E4B model or the already-extracted standalone E2B sub-model, "
        "which offers up to 2x faster inference."
    ),
    (
        "Between the two endpoints, a method called Mix-n-Match creates a spectrum "
        "of custom-sized models from the one trained E4B model by adjusting the "
        "feed-forward hidden dimension per layer and selectively skipping some "
        "layers, so a developer can slice a size tuned to specific hardware "
        "constraints without any retraining."
    ),
    (
        "NVIDIA's Flextron research transforms an already-trained LLM into an "
        "elastic model with nested elastic MLP and elastic attention layers, "
        "supports latency targets with no additional fine-tuning, and its "
        "sample-efficient training used only 7.63% of the tokens consumed in the "
        "original pretraining, though sliced sub-models still have to prove they "
        "match separately trained models of the same size."
    ),
]


def _source(source_id, origin):
    return SourceArtifact(
        source_id,
        origin.split("/")[2],
        origin,
        "url",
        "2026-07-28",
        "a" * 64,
        "a.txt",
        "a.html",
        "a.json",
    )


def _claims(texts, source_artifact, prefix="el"):
    return [
        Claim(
            f"{prefix}{index}",
            text,
            text,
            source_artifact.id,
            source_artifact.origin,
            source_artifact.label,
            0.9,
            ClaimType.OFFICIAL_FACT,
        )
        for index, text in enumerate(texts)
    ]


class ElasticLlmStoryTests(unittest.TestCase):
    def _plan(self):
        source_artifact = _source(
            "gemma",
            "https://developers.googleblog.com/en/introducing-gemma-3n-developer-guide/",
        )
        return plan_video(
            "Elastic language models",
            [source_artifact],
            _claims(ELASTIC_TEXTS, source_artifact),
        )

    def test_profile_produces_exact_grounded_narration(self):
        plan = self._plan()
        self.assertEqual(plan.hook, "One model, many sizes")
        self.assertEqual(len(plan.beats), 4)
        narrations = " ".join(beat.narration for beat in plan.beats)
        self.assertIn("smaller model hiding inside it", narrations)
        self.assertIn("MatFormer", narrations)
        self.assertIn("Mix and Match", narrations)
        self.assertIn("under eight percent", narrations)
        self.assertIn("prove they match models trained from scratch", narrations)
        self.assertNotIn("7.63", narrations)
        self.assertEqual(plan.beats[0].purpose, "hook")
        self.assertEqual(plan.beats[-1].purpose, "payoff")

    def test_story_uses_full_canvas_nested_composition(self):
        plan = self._plan()
        spec = compile_manim_scene(plan, animation_style="director_cut")
        self.assertEqual(spec.story["kind"], "elastic_llm_nesting")
        self.assertEqual(
            spec.story["source_visual_profile"], "elastic_llm_nesting_v1"
        )
        self.assertEqual(spec.story["motion_language"], "nested_zoom_v1")
        self.assertEqual(
            spec.story["chrome_mode"], "full_canvas_integrated_labels"
        )
        self.assertEqual(spec.story["source_badge_mode"], "hidden")
        self.assertEqual(spec.story["core_label"], "ONE MODEL, MANY SIZES")
        with tempfile.TemporaryDirectory() as tmp:
            scene = write_scene_py(Path(tmp), spec).read_text(encoding="utf-8")
        custom_scene = scene.split("def construct_elastic_llm_nesting", 1)[1].split(
            "def construct_lecun_world_model_bet", 1
        )[0]
        self.assertIn("ONE MODEL,", custom_scene)
        self.assertIn("MATFORMER", custom_scene)
        self.assertIn("MIX-N-MATCH", custom_scene)
        self.assertIn("TRAIN ONCE.", custom_scene)
        self.assertIn("prove parity", custom_scene)
        self.assertNotIn("Wiggle(", custom_scene)
        self.assertNotIn("style_names", custom_scene)
        self.assertNotIn("source_name(", custom_scene)
        compile(scene, "<generated-elastic-llm-scene>", "exec")

    def test_negative_control_generic_llm_lesson_does_not_hijack(self):
        source_artifact = _source("llm", "https://example.com/attention")
        texts = [
            "Large language models turn text into tokens and tokens into vectors.",
            "Attention lets every token weigh every other token in context.",
            "Transformer layers refine token meaning layer by layer.",
            "The model predicts the next token and repeats the loop elastically.",
        ]
        plan = plan_video(
            "How attention works",
            [source_artifact],
            _claims(texts, source_artifact, prefix="at"),
        )
        spec = compile_manim_scene(plan, animation_style="director_cut")
        self.assertNotEqual(spec.story["kind"], "elastic_llm_nesting")
        narrations = " ".join(beat.narration for beat in plan.beats)
        self.assertNotIn("MatFormer", narrations)


if __name__ == "__main__":
    unittest.main()
