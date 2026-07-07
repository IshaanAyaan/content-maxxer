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


if __name__ == "__main__":
    unittest.main()
