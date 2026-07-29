import json
import re
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

    def test_bayesian_claims_route_to_one_update_mechanism(self):
        source = artifact("src", "https://example.edu/bayes", "Bayes notes")
        texts = [
            "A fair coin and a trick coin that always lands heads are equally likely, so each starts with prior probability one half.",
            "Seeing two heads has likelihood one quarter for the fair coin and likelihood one for the trick coin.",
            "Bayes theorem multiplies the prior probability by the likelihood of the evidence.",
            "The weights are one eighth and one half; normalizing gives posterior probability one fifth and four fifths.",
            "The evidence reweights the competing hypotheses into a posterior probability.",
        ]
        claims = [
            Claim(
                f"c{index}",
                text,
                text,
                "src",
                source.origin,
                source.label,
                0.9,
                ClaimType.OFFICIAL_FACT,
            )
            for index, text in enumerate(texts)
        ]
        plan = plan_video(
            "Why two heads make the trick coin more likely",
            [source],
            claims,
            hook_style="question",
        )
        self.assertEqual(plan.hook, "Why do two heads make the trick coin more likely?")
        self.assertEqual({beat.primitive for beat in plan.beats}, {"bayes_update"})
        self.assertLessEqual(sum(len(beat.narration.split()) for beat in plan.beats), 110)
        self.assertTrue(all(len(sentence.split()) <= 15 for beat in plan.beats for sentence in beat.narration.replace("?", ".").split(".") if sentence.strip()))
        self.assertIn("Two heads. Same result.", plan.beats[0].narration)
        self.assertIn("one fifth fair, four fifths trick", plan.beats[3].narration)
        self.assertEqual(plan.beats[0].claim_ids, ["c0", "c1"])
        self.assertEqual(plan.beats[-1].claim_ids, ["c0", "c3", "c4"])
        self.assertEqual(
            [beat.headline for beat in plan.beats[1:]],
            [
                "Evidence favors one coin",
                "Prior times likelihood",
                "Normalize the weights",
                "Posterior after two heads",
            ],
        )

    def test_non_coin_bayes_source_never_inherits_coin_mechanism(self):
        source = artifact("src", "https://example.edu/medical-bayes", "Medical Bayes notes")
        texts = [
            "A screening test starts from the prior probability of disease.",
            "The likelihood of the evidence depends on sensitivity and specificity.",
            "Bayes theorem multiplies the prior probability by the likelihood.",
            "Normalizing the weights gives the posterior probability after a positive result.",
            "The posterior probability can guide a follow-up test.",
        ]
        claims = [
            Claim(f"m{index}", text, text, "src", source.origin, source.label, 0.9, ClaimType.OFFICIAL_FACT)
            for index, text in enumerate(texts)
        ]
        plan = plan_video("How a medical test updates risk", [source], claims, hook_style="question")
        self.assertNotIn("bayes_update", {beat.primitive for beat in plan.beats})
        self.assertNotIn("coin", " ".join(beat.headline for beat in plan.beats).lower())

    def test_open_weights_debate_gets_bounded_conversational_narration(self):
        source = artifact("src", "https://example.com/open-weights", "Open-weights primary sources")
        texts = [
            "NVIDIA and Dario Amodei agree more than the headlines suggest: the real argument is not simply open AI versus closed AI.",
            "The NVIDIA-backed open-weights letter says downloadable models improve access, competition, and control.",
            "The letter says released weights cannot be withdrawn, while transparency helps defenders inspect, test, and strengthen models.",
            "Amodei agrees on access, competition, and control, but disputes whether open access helps defenders more than attackers.",
            "Amodei rejects a categorical ban and proposes chip controls, limits on industrial-scale distillation, and safety testing for open and closed models.",
        ]
        claims = [
            Claim(
                f"ow{index}",
                text,
                text,
                "src",
                source.origin,
                source.label,
                0.9,
                ClaimType.OFFICIAL_FACT,
            )
            for index, text in enumerate(texts)
        ]
        plan = plan_video(
            "NVIDIA open weights versus Dario Amodei",
            [source],
            claims,
            hook_style="direct",
        )
        narrations = [beat.narration for beat in plan.beats]
        self.assertLessEqual(sum(len(narration.split()) for narration in narrations), 110)
        self.assertTrue(
            all(
                len(sentence.split()) <= 15
                for narration in narrations
                for sentence in narration.replace("?", ".").split(".")
                if sentence.strip()
            )
        )
        self.assertEqual(
            [beat.headline for beat in plan.beats],
            [
                "The real disagreement",
                "NVIDIA: access and control",
                "The catch: no undo",
                "Who gains more?",
                "No blanket ban",
            ],
        )
        self.assertIn("They aren't.", narrations[0])
        self.assertIn("model weights are released", narrations[2])
        self.assertIn("does not want to ban open weights", narrations[4])
        self.assertEqual(plan.beats[0].claim_ids, ["ow0", "ow3"])
        self.assertEqual(plan.beats[-1].claim_ids, ["ow4"])

    def test_technology_adolescence_gets_one_bounded_source_grounded_argument(self):
        source = artifact(
            "tech",
            "https://www.darioamodei.com/essay/the-adolescence-of-technology",
            "Dario Amodei essay",
        )
        texts = [
            "Humanity is entering a technological rite of passage with enormous power before its institutions have the maturity, or are mature enough, to wield it.",
            "Powerful AI could act like a country of geniuses in a datacenter, with long autonomous tasks and millions of copies operating faster than humans.",
            "The major risks include autonomous systems acting against human intentions, destructive misuse such as biological weapons, political power used to seize or entrench control, and economic disruption.",
            "The response should reject doomerism and complacency, acknowledge uncertainty, seek evidence, build defenses, and keep intervention targeted and surgically limited.",
            "Humanity can survive by steering powerful AI toward broadly beneficial outcomes.",
        ]
        claims = [
            Claim(
                f"ta{index}",
                text,
                text,
                "tech",
                source.origin,
                source.label,
                0.9,
                ClaimType.OFFICIAL_FACT,
            )
            for index, text in enumerate(texts)
        ]
        plan = plan_video(
            "The adolescence of technology",
            [source],
            claims,
        )
        self.assertEqual(plan.hook, "The adolescence of technology")
        self.assertEqual(len(plan.beats), 5)
        self.assertLessEqual(
            sum(len(beat.narration.split()) for beat in plan.beats),
            95,
        )
        narration = " ".join(beat.narration for beat in plan.beats)
        for phrase in (
            "enormous power",
            "country of geniuses in a datacenter",
            "four tests",
            "Acknowledge uncertainty",
            "Build defenses",
            "grow up fast enough",
        ):
            self.assertIn(phrase, narration)

    def test_lecun_world_model_bet_is_short_grounded_and_qualified(self):
        source = artifact(
            "lecun",
            "https://amilabs.xyz/",
            "AMI Labs and funding references",
        )
        texts = [
            "Advanced Machine Intelligence Labs says Yann LeCun is its founding Executive Chairman and announced $1.03 billion in financing to pursue a different path toward advanced machine intelligence.",
            "Large language models generate text by predicting tokens, while LeCun argues that scaling next-token prediction alone is unlikely to produce physical understanding and planning.",
            "AMI Labs says real-world sensor data is noisy, so world models learn abstract representations from video and sensors, then predict the consequences of actions so a system can plan.",
            "AMI says real intelligence starts in the world, but this is not a demonstrated victory and world models still have to prove the thesis.",
        ]
        claims = [
            Claim(
                f"yl{index}",
                text,
                text,
                "lecun",
                source.origin,
                source.label,
                0.9,
                ClaimType.OFFICIAL_FACT,
            )
            for index, text in enumerate(texts)
        ]
        plan = plan_video(
            "Yann LeCun's bet against LLMs",
            [source],
            claims,
        )
        self.assertEqual(len(plan.beats), 4)
        narration = " ".join(beat.narration for beat in plan.beats)
        self.assertLessEqual(len(narration.split()), 60)
        self.assertIn("one point oh three billion dollar bet", narration)
        self.assertIn("predict the next word", narration)
        self.assertIn("video, sensors, and actions", narration)
        self.assertIn("has to prove it", narration)
        self.assertNotIn("technology-adolescence.md", narration)

    def test_incomplete_open_weights_evidence_does_not_inherit_debate_profile(self):
        source = artifact("src", "https://example.com/open-weights", "Open-weights note")
        texts = [
            "NVIDIA released an open-weight model.",
            "Dario Amodei discussed model access.",
            "Open weights can increase competition.",
            "Customers may want deployment control.",
            "Safety remains important.",
        ]
        claims = [
            Claim(f"owx{index}", text, text, "src", source.origin, source.label, 0.8, ClaimType.UNCERTAIN)
            for index, text in enumerate(texts)
        ]
        plan = plan_video("NVIDIA open weights and Dario Amodei", [source], claims)
        self.assertNotIn("They aren't.", " ".join(beat.narration for beat in plan.beats))
        self.assertNotEqual(plan.beats[0].headline, "The real disagreement")

    def test_generic_likelihood_word_does_not_select_bayes_animation(self):
        source = artifact("src", "https://example.com/source", "source")
        claim = Claim(
            "c",
            "The launch likelihood improved after the reliability test.",
            "evidence",
            "src",
            source.origin,
            source.label,
            0.8,
            ClaimType.UNCERTAIN,
        )
        plan = plan_video("launch reliability", [source], [claim])
        self.assertNotEqual(plan.beats[0].primitive, "bayes_update")

    def test_generic_ordered_mechanism_gets_extractively_tight_narration(self):
        source = artifact("dns", "https://www.rfc-editor.org/rfc/rfc1034", "RFC 1034")
        texts = [
            "First, a resolver checks locally available information, including cached records, and returns a usable answer immediately when one is present.",
            "If the resolver has no local answer, it finds the best name servers to ask and sends a DNS query to one of them.",
            "When a response contains a valid referral, the referral points the resolver toward a closer name server, so the resolver updates its server list and repeats the search.",
            "An authoritative answer returns the requested resource data, such as the host address associated with a domain name.",
            "Finally, the resolver returns the answer to the client and stores cacheable response data for future use according to its time to live.",
        ]
        claims = [
            Claim(
                f"dns{index}",
                text,
                text,
                "dns",
                source.origin,
                source.label,
                0.95,
                ClaimType.OFFICIAL_FACT,
            )
            for index, text in enumerate(texts)
        ]
        plan = plan_video(
            "How DNS resolution finds an IP address",
            [source],
            claims,
            hook_style="question",
        )
        narrations = [beat.narration for beat in plan.beats]
        self.assertLessEqual(sum(len(item.split()) for item in narrations), 95)
        self.assertLessEqual(len(narrations[0].split()), 22)
        self.assertEqual(plan.beats[0].claim_ids, ["dns0"])
        self.assertIn("checks locally available information", narrations[0])
        self.assertIn("sends a DNS query", narrations[1])
        self.assertIn("updates its server list", narrations[2])
        self.assertIn("authoritative answer returns", narrations[3])
        self.assertIn("time to live", narrations[4])
        hook_tokens = set(re.findall(r"[a-z0-9]+", plan.hook.lower()))
        for beat, claim in zip(plan.beats, claims):
            narration_tokens = set(re.findall(r"[a-z0-9]+", beat.narration.lower()))
            claim_tokens = set(re.findall(r"[a-z0-9]+", claim.text.lower()))
            self.assertEqual(narration_tokens - claim_tokens - hook_tokens, set())

    def test_extractive_sequence_profile_generalizes_without_attention_hijack(self):
        source = artifact("compiler", "https://example.edu/compiler", "Compiler notes")
        texts = [
            "First, a tokenizer converts source characters into a stream of tokens.",
            "Next, a parser transforms those tokens into a syntax tree that records program structure.",
            "Semantic analysis validates names and types before the compiler continues.",
            "An optimizer rewrites the intermediate tree while preserving the program's meaning.",
            "Finally, a code generator produces machine instructions for the target processor.",
        ]
        claims = [
            Claim(
                f"compiler{index}",
                text,
                text,
                "compiler",
                source.origin,
                source.label,
                0.9,
                ClaimType.OFFICIAL_FACT,
            )
            for index, text in enumerate(texts)
        ]
        plan = plan_video("How a compiler produces machine code", [source], claims, hook_style="question")
        self.assertLessEqual(sum(len(beat.narration.split()) for beat in plan.beats), 95)
        self.assertIn(plan.hook, plan.beats[0].narration)
        self.assertFalse(all(beat.primitive == "attention_flow" for beat in plan.beats))
        self.assertEqual([beat.claim_ids for beat in plan.beats], [[claim.id] for claim in claims])

    def test_extractive_sequence_never_stops_mid_list_or_drops_the_subject(self):
        source = artifact(
            "browser",
            "https://developer.mozilla.org/en-US/docs/Web/Performance/Guides/How_browsers_work",
            "MDN browser navigation",
        )
        texts = [
            "First, navigation begins when a person requests a page, and the browser finds the server's IP address through DNS, reusing a cached result when one is available.",
            "Next, after the browser establishes a TCP connection, TLS verifies the server for HTTPS and establishes a secure connection before content transfer begins.",
            "Once the connection is ready, the browser sends an initial HTTP GET request, and the server replies with response headers and the contents of the HTML document.",
            "As HTML arrives, the browser tokenizes the markup and builds a DOM tree, while linked stylesheets, scripts, images, and other resources can trigger more requests.",
            "Finally, the browser combines the DOM and CSSOM into a render tree, computes layout for visible elements, and paints the resulting pixels to the screen.",
        ]
        claims = [
            Claim(
                f"browser{index}",
                text,
                text,
                "browser",
                source.origin,
                source.label,
                0.95,
                ClaimType.OFFICIAL_FACT,
            )
            for index, text in enumerate(texts)
        ]
        plan = plan_video(
            "How a browser turns a URL into a page",
            [source],
            claims,
            hook_style="question",
        )
        narrations = [beat.narration for beat in plan.beats]
        self.assertLessEqual(sum(len(item.split()) for item in narrations), 95)
        self.assertIn("finds the server's IP address through DNS", narrations[0])
        self.assertIn("tokenizes the markup", narrations[3])
        self.assertIn("builds a DOM tree", narrations[3])
        self.assertNotRegex(narrations[3], r"stylesheets,?\s*$|scripts,?\s*$|images,?\s*$")
        self.assertTrue(narrations[4].startswith("The browser combines"))
        self.assertIn("paints the resulting pixels", narrations[4])
        for narration in narrations:
            self.assertNotRegex(
                narration,
                r"^(?:Reusing|Computes|Paints|Builds|Combines|Sends|Returns)\b",
            )

    def test_long_physical_cycle_groups_every_claim_without_truncating_the_mechanism(self):
        source = artifact(
            "heat-pump",
            "https://www.energy.gov/energysaver/heat-pump-systems",
            "U.S. Department of Energy",
        )
        texts = [
            "A heat pump does not primarily make heat the way electric resistance does.",
            "It uses electricity to transfer heat from a cooler place to a warmer place.",
            "In heating mode, cool low-pressure refrigerant enters the outdoor evaporator.",
            "It absorbs heat from the outside air and boils into a low-pressure vapor.",
            "The compressor squeezes that vapor.",
            "Raising the refrigerant's pressure also raises its temperature, producing a hot high-pressure gas.",
            "Inside the home, the condenser lets that hot refrigerant release heat into the indoor air.",
            "As it gives up heat, the refrigerant condenses back into a high-pressure liquid.",
            "The expansion valve reduces the liquid's pressure and temperature.",
            "The cool low-pressure refrigerant returns to the evaporator, where the same four-part cycle repeats.",
        ]
        claims = [
            Claim(
                f"heat{index}",
                text,
                text,
                "heat-pump",
                source.origin,
                source.label,
                0.95,
                ClaimType.OFFICIAL_FACT,
            )
            for index, text in enumerate(texts)
        ]
        plan = plan_video(
            "How a heat pump moves heat",
            [source],
            claims,
            hook_style="question",
        )
        self.assertEqual(len(plan.beats), 5)
        self.assertEqual(
            [claim_id for beat in plan.beats for claim_id in beat.claim_ids],
            [claim.id for claim in claims],
        )
        narration = " ".join(beat.narration for beat in plan.beats)
        for required in (
            "does not primarily make heat",
            "outdoor evaporator",
            "compressor squeezes",
            "condenser lets",
            "expansion valve reduces",
            "cycle repeats",
        ):
            self.assertIn(required, narration)
        self.assertLessEqual(len(narration.split()), 135)
        self.assertNotIn(".,", narration)

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

        tls_plan = plan_video(
            "How a TLS 1.3 handshake creates a secure channel",
            [source],
            [claim],
            hook_style="question",
        )
        self.assertEqual(tls_plan.hook, "How does a TLS 1.3 handshake create a secure channel?")

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
