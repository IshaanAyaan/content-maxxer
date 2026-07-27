import json
import tempfile
import unittest
from pathlib import Path

from contentmaxxer.content_packs import (
    FABLE_DOCS,
    FABLE_PAGE,
    GPT56_GUIDE,
    GPT56_LAUNCH,
    GPT56_MODELS,
    GPT56_SYSTEM_CARD,
)
from contentmaxxer.models import Claim, ClaimType, SourceArtifact
from contentmaxxer.planning import PlanningError, extract_claims, plan_slides, plan_video, validate_claims
from contentmaxxer.sources import SourceCache, SourceError, normalize_text, research_sources


def artifact(source_id, origin, label, normalized_path="sources/source.txt"):
    return SourceArtifact(
        id=source_id,
        label=label,
        origin=origin,
        source_type="url",
        retrieved_at="2026-07-09",
        digest="a" * 64,
        normalized_path=normalized_path,
        snapshot_path="sources/source.html",
        metadata_path="sources/source.json",
    )


class SourceTests(unittest.TestCase):
    def test_html_normalization_drops_script(self):
        text = normalize_text("<html><script>bad()</script><h1>Useful title</h1><p>Useful body.</p></html>", "text/html")
        self.assertNotIn("bad", text)
        self.assertIn("Useful title", text)
        self.assertIn("Useful body", text)

    def test_local_source_cache_has_digest_and_portable_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            note = root / "note.md"
            note.write_text("A grounded fact lives here.\n", encoding="utf-8")
            sources = research_sources(root / "job", source_files=[note])
            self.assertEqual(len(sources), 1)
            self.assertFalse(Path(sources[0].normalized_path).is_absolute())
            self.assertEqual(len(sources[0].digest), 64)
            self.assertTrue((root / "job" / sources[0].metadata_path).exists())

    def test_offline_cache_miss_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = SourceCache(Path(tmp))
            with self.assertRaises(SourceError):
                cache.cache_url("https://example.invalid/source", offline=True)

    def test_offline_reuses_local_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            note = root / "note.txt"
            note.write_text("Documented orbital storage improves discharge stability.", encoding="utf-8")
            first = research_sources(root / "job", source_files=[note])
            second = research_sources(root / "job", offline=True)
            self.assertEqual(first[0].digest, second[0].digest)


class PlanningTests(unittest.TestCase):
    def test_fable_comparison_has_two_styles_and_source_bound_economics(self):
        sources = [
            artifact("guide", GPT56_GUIDE, "OpenAI guide"),
            artifact("fable", FABLE_PAGE, "Anthropic Fable"),
            artifact("docs", FABLE_DOCS, "Anthropic docs"),
        ]
        claims = extract_claims("Fable 5 vs GPT-5.6 cost economics", Path("."), sources)
        plan = plan_slides(
            "Fable 5 vs GPT-5.6 cost economics",
            sources,
            claims,
            7,
            hook_style="statistic",
            visual_theme="paper_meme_v1",
        )
        self.assertEqual(plan.visual_theme, "paper_meme_v1")
        self.assertEqual(len(plan.hook_candidates), 12)
        self.assertTrue(all(slide.claim_ids for slide in plan.slides))
        self.assertIn("clm_fable_price", plan.slides[0].claim_ids)
        self.assertTrue(any(claim.source_label.startswith("CONTENTMAXXER ANALYSIS") for claim in claims))

    def test_known_gpt_pack_is_typed_and_never_claims_auto_routing(self):
        sources = [
            artifact("launch", GPT56_LAUNCH, "launch"),
            artifact("models", GPT56_MODELS, "models"),
            artifact("card", GPT56_SYSTEM_CARD, "card"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            claims = extract_claims("GPT-5.6 family tiers", Path(tmp), sources)
        self.assertEqual(len(claims), 6)
        self.assertIn(ClaimType.INTERPRETATION, {claim.claim_type for claim in claims})
        self.assertNotIn("automatic routing", " ".join(claim.text.lower() for claim in claims))
        self.assertEqual(validate_claims(claims, sources), [])

    def test_safety_pack_has_numeric_source_backed_claim(self):
        sources = [
            artifact("launch", GPT56_LAUNCH, "launch"),
            artifact("models", GPT56_MODELS, "models"),
            artifact("card", GPT56_SYSTEM_CARD, "card"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            claims = extract_claims("GPT-5.6 capability controls", Path(tmp), sources)
        self.assertTrue(any(claim.numeric for claim in claims))
        plan = plan_video("GPT-5.6 capability controls", sources, claims, hook_style="statistic")
        self.assertIn("ten times", plan.hook)
        numeric = next(claim for claim in claims if claim.numeric)
        self.assertEqual(plan.beats[0].claim_ids, [numeric.id])
        deck = plan_slides("GPT-5.6 capability controls", sources, claims, 4, hook_style="statistic")
        self.assertIn(numeric.id, deck.slides[0].claim_ids)

    def test_statistic_hook_rejects_non_numeric_claims(self):
        sources = [artifact("src", GPT56_LAUNCH, "launch"), artifact("models", GPT56_MODELS, "models"), artifact("card", GPT56_SYSTEM_CARD, "card")]
        with tempfile.TemporaryDirectory() as tmp:
            claims = extract_claims("GPT-5.6 family tiers", Path(tmp), sources)
        self.assertFalse(any(claim.numeric for claim in claims))
        with self.assertRaises(PlanningError):
            plan_slides("GPT-5.6 family tiers", sources, claims, 3, hook_style="statistic")

    def test_unknown_grounded_topic_uses_source_claim_not_generic_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            job = root / "job"
            note = root / "note.txt"
            sentence = "Orbital storage cells use a documented ceramic layer that improves discharge stability."
            note.write_text(sentence, encoding="utf-8")
            sources = research_sources(job, source_files=[note])
            claims = extract_claims("orbital storage", job, sources)
            plan = plan_slides("orbital storage", sources, claims, 4)
            rendered_copy = " ".join(slide.headline for slide in plan.slides)
            self.assertIn("ceramic layer", rendered_copy)
            self.assertNotIn("Here are", rendered_copy)

    def test_generic_claims_preserve_explanatory_order_and_drop_reference_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            job = root / "job"
            note = root / "note.md"
            note.write_text(
                "# Why satellites stay in orbit\n\n"
                "Gravity continuously pulls a satellite toward Earth while it travels sideways.\n\n"
                "Its sideways speed makes the curved surface drop away beneath the falling path.\n\n"
                "Together those motions bend the trajectory into a closed orbit around Earth.\n\n"
                "Primary references: NASA orbital mechanics.\n\n"
                "https://www.nasa.gov/example\n",
                encoding="utf-8",
            )
            sources = research_sources(job, source_files=[note])
            claims = extract_claims("satellites orbit Earth", job, sources)
            self.assertEqual(
                [claim.text for claim in claims],
                [
                    "Gravity continuously pulls a satellite toward Earth while it travels sideways.",
                    "Its sideways speed makes the curved surface drop away beneath the falling path.",
                    "Together those motions bend the trajectory into a closed orbit around Earth.",
                ],
            )
            self.assertNotIn("http", " ".join(claim.text for claim in claims).lower())

    def test_orbital_storage_does_not_select_orbit_animation(self):
        source = artifact("src", "https://example.com/source", "source")
        claim = Claim(
            "c",
            "Orbital storage cells use a ceramic layer for stability.",
            "evidence",
            "src",
            source.origin,
            source.label,
            0.8,
            ClaimType.UNCERTAIN,
        )
        plan = plan_video("orbital storage", [source], [claim])
        self.assertNotEqual(plan.beats[0].primitive, "orbit_trace")

    def test_question_hook_adds_auxiliary_for_plain_why_topic(self):
        source = artifact("src", "https://example.com/source", "source")
        claim = Claim(
            "c",
            "A satellite continuously falls toward Earth.",
            "evidence",
            "src",
            source.origin,
            source.label,
            0.8,
            ClaimType.UNCERTAIN,
        )
        plan = plan_video("Why satellites stay in orbit", [source], [claim], hook_style="question")
        self.assertEqual(plan.hook, "Why do satellites stay in orbit?")

        how_plan = plan_video("How gradient descent learns", [source], [claim], hook_style="question")
        self.assertEqual(how_plan.hook, "How does gradient descent learn?")

    def test_ungrounded_plan_blocks_before_render(self):
        plan = plan_video("unknown", [], [], allow_ungrounded=False)
        self.assertFalse(plan.grounded)
        self.assertEqual(plan.beats, [])
        self.assertIn("source", plan.blocked_reason.lower())

    def test_slide_count_is_exact_for_small_and_large_decks(self):
        sources = [artifact("launch", GPT56_LAUNCH, "launch"), artifact("models", GPT56_MODELS, "models"), artifact("card", GPT56_SYSTEM_CARD, "card")]
        with tempfile.TemporaryDirectory() as tmp:
            claims = extract_claims("GPT-5.6 family tiers", Path(tmp), sources)
        for count in (1, 2, 7, 11):
            self.assertEqual(len(plan_slides("GPT-5.6 family tiers", sources, claims, count).slides), count)

    def test_carousel_plan_is_engagement_first_not_an_information_dump(self):
        sources = [artifact("launch", GPT56_LAUNCH, "launch"), artifact("models", GPT56_MODELS, "models"), artifact("card", GPT56_SYSTEM_CARD, "card")]
        with tempfile.TemporaryDirectory() as tmp:
            claims = extract_claims("GPT-5.6 family tiers", Path(tmp), sources)
        plan = plan_slides("GPT-5.6 family tiers", sources, claims, 7)
        self.assertGreaterEqual(len(plan.hook_candidates), 12)
        self.assertGreaterEqual(len(plan.angle_candidates), 3)
        self.assertEqual(plan.slides[0].role, "hook")
        self.assertEqual(plan.slides[-1].role, "payoff")
        self.assertIn("save", plan.slides[-1].engagement_trigger)
        self.assertTrue(all(len(slide.headline.split()) <= 14 for slide in plan.slides))
        self.assertTrue(all(slide.headline.lower() != slide.body.lower() for slide in plan.slides))
        self.assertGreaterEqual(len({slide.visual for slide in plan.slides}), 5)


if __name__ == "__main__":
    unittest.main()
