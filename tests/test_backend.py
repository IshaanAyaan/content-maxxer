import unittest

from content_maxxer.backend import (
    format_srt_time,
    generate_beats,
    score_format,
    score_pacing,
    score_semantic_motion,
    score_subtitles,
    slugify,
)
from content_maxxer.director import build_director_plan, retime_plan


class BackendTests(unittest.TestCase):
    def test_slugify(self):
        self.assertEqual(slugify("Gradient Descent!"), "gradient_descent")

    def test_generate_beats_uses_short_captions(self):
        beats = generate_beats(
            "Gradient Descent",
            "Gradient descent improves a model by taking small downhill steps.",
            22,
        )
        self.assertEqual(len(beats), 5)
        self.assertTrue(all(len(beat.caption) <= 112 for beat in beats))

    def test_srt_time_format(self):
        self.assertEqual(format_srt_time(65.25), "00:01:05,250")

    def test_scores_basic_postable_shape(self):
        beats = generate_beats("Attention", "Attention picks which tokens matter most.", 20)
        self.assertEqual(score_format(540, 960, "vertical"), 100.0)
        self.assertGreaterEqual(score_subtitles(beats), 80.0)
        self.assertEqual(score_pacing(beats), 100.0)
        self.assertEqual(score_semantic_motion(beats, "caption_template_v0"), 35.0)

    def test_director_plan_has_semantic_scenes(self):
        plan = build_director_plan(
            title="Gradient Descent",
            idea="A dot moves down a loss curve by reading local slope.",
            slug="gradient_descent_test",
        )
        self.assertIn("dot", plan.central_object.lower())
        self.assertTrue(all(scene.motion for scene in plan.scenes))
        self.assertTrue(all("Hook" not in scene.visible_text for scene in plan.scenes))

    def test_director_retimes_for_faster_shortform_pacing(self):
        plan = build_director_plan(
            title="Large Language Models",
            idea="Explain how large language models work.",
            slug="llm_test",
            duration=42,
        )
        faster = retime_plan(plan, 1.75)
        self.assertLess(faster.duration, plan.duration)
        self.assertAlmostEqual(faster.duration, round(plan.duration / 1.75, 1), delta=0.2)
        self.assertTrue(all(scene.visual_kind == "llm" for scene in faster.scenes))


if __name__ == "__main__":
    unittest.main()
