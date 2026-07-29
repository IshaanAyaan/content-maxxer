import json
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from PIL import Image

from contentmaxxer.content_packs import GPT56_LAUNCH, GPT56_MODELS, GPT56_SYSTEM_CARD
from contentmaxxer.manim_scene import (
    ANIMATION_STYLES,
    _caption_payload,
    compile_manim_scene,
    manim_available,
    semantic_emphasis_summary,
    semantic_text_transition_summary,
    write_scene_py,
)
from contentmaxxer.models import Claim, ClaimType, NarrationCue, NarrationTrack, SourceArtifact, WordTiming
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
        self.assertEqual(first.story["kind"], "generic_explainer")
        self.assertEqual(len(first.story["stages"]), len(plan.beats))
        self.assertTrue(first.story["core_label"])

    def test_math_action_words_begin_a_precisely_timed_caption(self):
        for action in ("Multiply", "multiplying", "Normalize", "normalizing"):
            words = [
                WordTiming("hypothesis", 10.0, 10.5, "beat_03"),
                WordTiming("by", 10.5, 10.7, "beat_03"),
                WordTiming(action, 10.7, 11.4, "beat_03"),
                WordTiming("it", 11.4, 11.6, "beat_03"),
            ]
            cue = NarrationCue("beat_03", f"hypothesis by {action} it", 10.0, 11.6, words)
            captions = _caption_payload(cue, "", 1.6)
            self.assertEqual([item["text"] for item in captions], ["hypothesis by", f"{action} it"])
            self.assertEqual(captions[1]["start_seconds"], 0.7)

    def test_semantic_emphasis_uses_the_trigger_word_not_caption_start(self):
        words = [
            WordTiming("The", 10.0, 10.2, "beat"),
            WordTiming("gradient", 10.2, 10.7, "beat"),
            WordTiming("points", 10.7, 11.0, "beat"),
            WordTiming("uphill.", 11.0, 11.4, "beat"),
        ]
        cue = NarrationCue("beat", "The gradient points uphill.", 10.0, 11.4, words)
        captions = _caption_payload(
            cue,
            "",
            1.4,
            story_kind="mechanism_gradient",
        )
        self.assertEqual(captions[0]["start_seconds"], 0.0)
        self.assertEqual(captions[0]["emphasis_start_seconds"], 0.2)
        self.assertEqual(captions[0]["emphasis_text"], "The gradient points uphill.")

    def test_semantic_emphasis_summary_excludes_stage_entry_and_validates_delays(self):
        plan = plan_video("GPT-5.6 family tiers", self.sources, self.claims)
        mechanism = replace(
            plan,
            beats=[replace(beat, primitive="gradient_descent") for beat in plan.beats],
        )
        cues = []
        for beat_index, beat in enumerate(mechanism.beats):
            text = "The gradient points uphill. Each update lowers loss."
            start = beat_index * 4.0
            words = [
                WordTiming(word, start + index * 0.35, start + index * 0.35 + 0.3, beat.id)
                for index, word in enumerate(text.split())
            ]
            cues.append(NarrationCue(beat.id, text, start, start + 4.0, words))
        track = NarrationTrack(
            "file",
            "test",
            "voice.wav",
            20.0,
            48_000,
            "test",
            cues,
        )
        spec = compile_manim_scene(mechanism, track, animation_style="warm_papyrus")
        summary = semantic_emphasis_summary(spec)
        self.assertEqual(summary["scheduled_event_count"], len(mechanism.beats))
        self.assertEqual(summary["invalid_event_count"], 0)
        self.assertGreater(summary["delayed_event_count"], 0)

    def test_semantic_caption_cadence_uses_longer_phrases_and_persistent_header(self):
        plan = plan_video("GPT-5.6 family tiers", self.sources, self.claims)
        mechanism = replace(
            plan,
            beats=[
                replace(
                    beat,
                    primitive="gradient_descent",
                    duration_seconds=4.0,
                )
                for beat in plan.beats
            ],
        )
        cues = []
        for beat_index, beat in enumerate(mechanism.beats):
            text = (
                "The gradient points uphill while each update "
                "moves toward lower loss."
            )
            start = beat_index * 4.0
            words = [
                WordTiming(
                    word,
                    start + index * 0.32,
                    start + index * 0.32 + 0.28,
                    beat.id,
                )
                for index, word in enumerate(text.split())
            ]
            cues.append(
                NarrationCue(
                    beat.id,
                    text,
                    start,
                    start + 4.0,
                    words,
                )
            )
        track = NarrationTrack(
            "file",
            "test",
            "voice.wav",
            20.0,
            48_000,
            "test",
            cues,
        )
        spec = compile_manim_scene(mechanism, track)
        summary = semantic_text_transition_summary(spec)
        self.assertEqual(
            spec.story["text_transition_mode"],
            "persistent_lesson_header_handwritten_captions",
        )
        self.assertEqual(summary["headline_replacement_count"], 0)
        self.assertEqual(summary["hook_title_mode"], "persistent_complete_hook")
        self.assertFalse(summary["hook_title_contains_ellipsis"])
        self.assertTrue(summary["hook_title_matches_plan_hook"])
        self.assertEqual(summary["recap_mode"], "semantic_payoff_hold")
        self.assertTrue(
            all(
                len(caption["text"].split()) <= 6
                for primitive in spec.primitives
                for caption in primitive.params["captions"]
            )
        )
        self.assertLessEqual(summary["caption_transitions_per_minute"], 32)
        self.assertGreaterEqual(summary["median_caption_dwell_seconds"], 1.7)

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

    def test_style_experiments_are_distinct_and_preserve_hand_drawn_default(self):
        plan = plan_video("GPT-5.6 family tiers", self.sources, self.claims)
        default = compile_manim_scene(plan)
        self.assertEqual(default.animation_style, "hand_drawn")
        self.assertEqual(default.background, "#07111F")
        backgrounds = set()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for style in ANIMATION_STYLES[1:]:
                spec = compile_manim_scene(plan, animation_style=style)
                scene = write_scene_py(root / style, spec).read_text(encoding="utf-8")
                backgrounds.add(spec.background)
                self.assertEqual(spec.animation_style, style)
                self.assertIn(f'"animation_style": "{style}"', scene)
                self.assertIn("semantic_visual_swap(current_visual, visual)", scene)
                self.assertIn("narration_visual_phase(stage, cue[\"text\"])", scene)
                self.assertIn("stage_visual(stage, phase=target_phase)", scene)
                self.assertIn('cue.get("emphasis_text", cue["text"])', scene)
                self.assertIn("emphasis_time = beat_origin + float(emphasis_start)", scene)
                self.assertIn("Succession(Wait(emphasis_delay), emphasis)", scene)
                self.assertIn("def style_native_emphasis(target)", scene)
                self.assertIn(
                    "rotation_angle=(0.022 if tcp_profile else 0.015) * TAU",
                    scene,
                )
                self.assertIn("target.scale", scene)
                self.assertIn("RIGHT * 0.30", scene)
                self.assertIn("1.085,", scene)
                self.assertIn("RIGHT * 0.14", scene)
                self.assertIn("target.shift", scene)
                self.assertIn("style_native_emphasis(target)", scene)
                self.assertIn("def caption_swap(old, new)", scene)
                self.assertIn("Unwrite(old)", scene)
                self.assertIn("Write(new)", scene)
                self.assertIn("caption_swap_duration(cue_duration)", scene)
                self.assertIn("caption_change.set_run_time(caption_swap_run_time)", scene)
                self.assertIn("persistent_header", scene)
                self.assertIn('if STYLE == "future_minimal"', scene)
                self.assertIn("min(0.76, max(0.46, cue_duration * 0.48))", scene)
                self.assertIn("emphasis.set_run_time(emphasis_run_time)", scene)
                self.assertNotIn("FadeOut(current_visual", scene)
        self.assertEqual(len(backgrounds), len(ANIMATION_STYLES) - 1)

    def test_unknown_animation_style_is_rejected(self):
        plan = plan_video("GPT-5.6 family tiers", self.sources, self.claims)
        with self.assertRaisesRegex(ValueError, "unknown animation style"):
            compile_manim_scene(plan, animation_style="box_spam")

    def test_generic_style_story_contains_only_source_derived_labels(self):
        plan = plan_video("GPT-5.6 family tiers", self.sources, self.claims)
        spec = compile_manim_scene(plan, animation_style="whiteboard")
        serialized = json.dumps(spec.story)
        self.assertEqual(spec.story["kind"], "generic_explainer")
        self.assertNotIn("OPEN WEIGHTS", serialized)
        self.assertNotIn("Amodei", serialized)
        self.assertNotIn("NVIDIA", serialized)
        expected_labels = {
            beat.headline.replace("‑", "-").split()[0].strip(".,;:").lower()
            for beat in plan.beats
        }
        actual_labels = {stage["label"].split()[0].strip(".,;:").lower() for stage in spec.story["stages"]}
        self.assertEqual(actual_labels, expected_labels)

    def test_open_weights_special_composition_requires_full_debate_evidence(self):
        plan = plan_video("GPT-5.6 family tiers", self.sources, self.claims)
        debate_claims = [
            Claim(
                f"ow{index}",
                text,
                text,
                "ow",
                "https://example.com/open-weights",
                "Open-weights sources",
                0.9,
                ClaimType.OFFICIAL_FACT,
            )
            for index, text in enumerate(
                [
                    "NVIDIA and Dario Amodei debate open-weight AI.",
                    "The letter says access, competition, and customer control improve.",
                    "Released weights cannot be withdrawn, while defenders may gain transparency.",
                    "Amodei asks whether attackers gain more than defenders.",
                    "He rejects a categorical ban and favors chip controls, distillation limits, and safety testing for open and closed models.",
                ]
            )
        ]
        specialized = replace(
            plan,
            topic="NVIDIA open weights and Dario Amodei",
            claims=debate_claims,
        )
        spec = compile_manim_scene(specialized, animation_style="director_cut")
        self.assertEqual(spec.story["kind"], "open_weights_debate")
        self.assertEqual(spec.story["core_label"], "OPEN WEIGHTS")
        self.assertEqual(spec.story["transition_mode"], "semantic_continuity")
        with tempfile.TemporaryDirectory() as tmp:
            scene = write_scene_py(Path(tmp), spec).read_text(encoding="utf-8")
        for semantic_id in (
            "open_weights_core",
            "shared_benefits",
            "irreversibility",
            "attacker_defender",
            "policy_response",
        ):
            self.assertIn(f'"{semantic_id}"', scene)
        self.assertIn("def play_argument_motion(", scene)
        self.assertIn("play_argument_motion(", scene)
        compile(scene, "<generated-open-weights-scene>", "exec")

    def test_open_weights_names_alone_do_not_trigger_special_composition(self):
        plan = plan_video("GPT-5.6 family tiers", self.sources, self.claims)
        renamed = replace(plan, topic="NVIDIA open weights and Dario Amodei")
        spec = compile_manim_scene(renamed, animation_style="director_cut")
        self.assertEqual(spec.story["kind"], "generic_explainer")

    def test_technology_adolescence_uses_quiet_typed_editorial_composition(self):
        essay = source(
            "tech",
            "https://www.darioamodei.com/essay/the-adolescence-of-technology",
        )
        texts = [
            "Humanity is entering a technological rite of passage with enormous power before its institutions have the maturity, or are mature enough, to wield it.",
            "Powerful AI could act like a country of geniuses in a datacenter, with long autonomous tasks and millions of copies operating faster than humans.",
            "The risks include autonomous systems acting against human intentions, destructive misuse such as biological weapons, political power used to seize control, and economic disruption.",
            "Reject doomerism and complacency: acknowledge uncertainty, seek evidence, build defenses, and keep intervention targeted and surgically limited.",
            "Humanity can survive by steering powerful AI toward broadly beneficial outcomes.",
        ]
        claims = [
            Claim(
                f"ta{index}",
                text,
                text,
                "tech",
                essay.origin,
                essay.label,
                0.9,
                ClaimType.OFFICIAL_FACT,
            )
            for index, text in enumerate(texts)
        ]
        plan = plan_video(
            "The adolescence of technology",
            [essay],
            claims,
        )
        spec = compile_manim_scene(
            plan,
            animation_style="director_cut",
        )
        self.assertEqual(spec.story["kind"], "technology_adolescence")
        self.assertEqual(
            spec.story["motion_language"],
            "one_shot_reveal_only_v1",
        )
        self.assertEqual(spec.story["chrome_mode"], "minimal_title_only")
        self.assertEqual(spec.story["source_badge_mode"], "hidden")
        with tempfile.TemporaryDirectory() as tmp:
            scene = write_scene_py(Path(tmp), spec).read_text(
                encoding="utf-8"
            )
        custom_scene = scene.split(
            "def construct_technology_adolescence",
            1,
        )[1].split("class ContentMaxxerScene", 1)[0]
        self.assertIn("Write(title)", custom_scene)
        self.assertIn(
            "Transform(title, technology_title_header())",
            custom_scene,
        )
        self.assertIn("technology_visual_swap", scene)
        self.assertIn("nersc-server-racks-cc0.jpg", scene)
        self.assertNotIn("Wiggle(", custom_scene)
        self.assertNotIn("source_name(", custom_scene)
        self.assertNotIn("style_names", custom_scene)
        compile(scene, "<generated-technology-adolescence-scene>", "exec")

    def test_lecun_bet_uses_full_canvas_guided_route_composition(self):
        source_artifact = source(
            "lecun",
            "https://amilabs.xyz/",
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
                source_artifact.origin,
                source_artifact.label,
                0.9,
                ClaimType.OFFICIAL_FACT,
            )
            for index, text in enumerate(texts)
        ]
        plan = plan_video(
            "Yann LeCun's bet against LLMs",
            [source_artifact],
            claims,
        )
        spec = compile_manim_scene(
            plan,
            animation_style="director_cut",
        )
        self.assertEqual(spec.story["kind"], "lecun_world_model_bet")
        self.assertEqual(
            spec.story["source_visual_profile"],
            "lecun_world_model_route_v1",
        )
        self.assertEqual(
            spec.story["motion_language"],
            "guided_camera_route_v1",
        )
        self.assertEqual(
            spec.story["chrome_mode"],
            "full_canvas_integrated_labels",
        )
        self.assertEqual(spec.story["source_badge_mode"], "hidden")
        with tempfile.TemporaryDirectory() as tmp:
            scene = write_scene_py(Path(tmp), spec).read_text(
                encoding="utf-8"
            )
        custom_scene = scene.split(
            "def construct_lecun_world_model_bet",
            1,
        )[1].split("def technology_visual_swap", 1)[0]
        self.assertIn("EARTH_IMAGE_PATH", custom_scene)
        self.assertIn("LECUN_PORTRAIT_PATH", scene)
        self.assertIn("MoveAlongPath(marker", custom_scene)
        self.assertIn("NEXT WORD", custom_scene)
        self.assertIn("NEXT STATE", custom_scene)
        self.assertIn("NOW PROVE IT.", custom_scene)
        self.assertNotIn("Wiggle(", custom_scene)
        self.assertNotIn("style_names", custom_scene)
        compile(scene, "<generated-lecun-world-model-scene>", "exec")

    def test_dominant_primitives_route_to_mechanism_stories(self):
        plan = plan_video("GPT-5.6 family tiers", self.sources, self.claims)
        routes = {
            "orbit_trace": "mechanism_orbit",
            "gradient_descent": "mechanism_gradient",
            "attention_flow": "mechanism_attention",
        }
        for primitive, expected in routes.items():
            routed = replace(
                plan,
                beats=[replace(beat, primitive=primitive) for beat in plan.beats],
            )
            spec = compile_manim_scene(routed, animation_style="whiteboard")
            self.assertEqual(spec.story["kind"], expected)
            self.assertEqual(spec.story["dominant_primitive"], primitive)
            self.assertEqual(spec.story["transition_mode"], "semantic_continuity")
            with tempfile.TemporaryDirectory() as tmp:
                scene = write_scene_py(Path(tmp), spec).read_text(encoding="utf-8")
            self.assertIn("def semantic_part", scene)
            self.assertIn("ReplacementTransform(old_part, new_parts[key])", scene)
            self.assertIn("Create(new_part)", scene)

        bayes_claims = [
            Claim(
                f"b{index}",
                text,
                text,
                "bayes",
                "https://example.edu/bayes",
                "Bayes notes",
                0.9,
                ClaimType.OFFICIAL_FACT,
            )
            for index, text in enumerate(
                [
                    "A fair coin and a trick coin that always lands heads are equally likely.",
                    "Seeing two heads has likelihood one quarter for the fair coin.",
                    "Bayes multiplies prior probability by likelihood.",
                    "The posterior is one fifth fair and four fifths trick.",
                    "Two heads reweight the competing hypotheses.",
                ]
            )
        ]
        bayes_plan = replace(
            plan,
            topic="Why two heads favor the trick coin",
            claims=bayes_claims,
            beats=[replace(beat, primitive="bayes_update") for beat in plan.beats],
        )
        bayes_spec = compile_manim_scene(bayes_plan, animation_style="whiteboard")
        self.assertEqual(bayes_spec.story["kind"], "mechanism_bayes")
        self.assertEqual(bayes_spec.story["dominant_primitive"], "bayes_update")
        self.assertEqual(bayes_spec.story["transition_mode"], "semantic_continuity")

    def test_forced_bayes_primitive_without_coin_evidence_falls_back_safely(self):
        plan = plan_video("GPT-5.6 family tiers", self.sources, self.claims)
        forced = replace(
            plan,
            topic="How a medical test updates risk",
            beats=[replace(beat, primitive="bayes_update") for beat in plan.beats],
        )
        spec = compile_manim_scene(forced, animation_style="whiteboard")
        self.assertEqual(spec.story["kind"], "generic_explainer")
        self.assertIsNone(spec.story["dominant_primitive"])

    def test_single_mechanism_keyword_does_not_hijack_generic_story(self):
        plan = plan_video("GPT-5.6 family tiers", self.sources, self.claims)
        mixed = replace(
            plan,
            beats=[
                replace(beat, primitive="orbit_trace") if index == 0 else beat
                for index, beat in enumerate(plan.beats)
            ],
        )
        spec = compile_manim_scene(mixed, animation_style="future_minimal")
        self.assertEqual(spec.story["kind"], "generic_explainer")
        self.assertEqual(spec.story["transition_mode"], "clean_swap")

    def test_complete_tls_evidence_routes_to_handshake_without_attention_leakage(self):
        tls_texts = [
            "In a TLS 1.3 handshake, the client starts with a ClientHello and a key share.",
            "The server answers with a ServerHello and both peers derive the same handshake traffic secrets.",
            "The server then sends encrypted handshake messages and authenticates with a certificate and CertificateVerify signature.",
            "Each peer validates a Finished message that authenticates the transcript and computed keys.",
            "After both sides validate Finished, they can protect application data with traffic keys.",
        ]
        claims = [
            Claim(
                f"tls{index}",
                text,
                text,
                "tls",
                "https://www.rfc-editor.org/rfc/rfc8446",
                "RFC 8446",
                0.95,
                ClaimType.OFFICIAL_FACT,
            )
            for index, text in enumerate(tls_texts)
        ]
        plan = plan_video(
            "TLS 1.3 handshake",
            [source("tls", "https://www.rfc-editor.org/rfc/rfc8446")],
            claims,
            hook_style="curiosity",
        )
        self.assertEqual(plan.beats[0].narration.count(tls_texts[0]), 1)
        self.assertNotIn("attention_flow", {beat.primitive for beat in plan.beats})
        self.assertFalse(
            any(
                phrase in beat.headline.lower()
                for beat in plan.beats
                for phrase in ("queries score", "softmax", "weighted values", "heads learn")
            )
        )
        spec = compile_manim_scene(plan, animation_style="warm_papyrus")
        self.assertEqual(spec.story["kind"], "mechanism_handshake")
        self.assertEqual(spec.story["core_label"], "SECURE CHANNEL")
        self.assertEqual(spec.story["transition_mode"], "semantic_continuity")
        self.assertEqual(
            spec.story["hook_title"]["text"],
            "What happens during a TLS 1.3 handshake?",
        )
        self.assertNotIn("…", spec.story["hook_title"]["text"])
        self.assertEqual(
            [stage["sequence_index"] for stage in spec.story["stages"]],
            list(range(len(plan.beats))),
        )
        labels = [stage["label"].lower() for stage in spec.story["stages"]]
        self.assertIn("client starts", labels[0])
        self.assertIn("server answers", labels[1])
        self.assertIn("protect application data", labels[-1])
        with tempfile.TemporaryDirectory() as tmp:
            scene = write_scene_py(Path(tmp), spec).read_text(encoding="utf-8")
        self.assertIn("def mechanism_handshake_visual(stage)", scene)
        self.assertIn("def causal_explainer_visual(stage)", scene)
        for semantic_id in (
            "client_actor",
            "server_actor",
            "hello_messages",
            "shared_secrets",
            "certificate_auth",
            "finished_checks",
            "application_data",
        ):
            self.assertIn(f'"{semantic_id}"', scene)
        self.assertNotIn('"TARGET QUERY"', json.dumps(spec.story))
        hand_drawn = compile_manim_scene(plan, animation_style="hand_drawn")
        with tempfile.TemporaryDirectory() as tmp:
            hand_scene = write_scene_py(Path(tmp), hand_drawn).read_text(encoding="utf-8")
        self.assertIn('"hand_drawn": "CHALK MECHANISM"', hand_scene)
        self.assertIn("def mechanism_handshake_visual(stage)", hand_scene)
        self.assertIn("def handshake_transit_token(point, label, color, seed)", hand_scene)
        self.assertIn("def play_handshake_transit(scene, stage, cycle_index, run_time)", hand_scene)
        self.assertIn("def wait_with_story_motion(scene, visual, stage, duration)", hand_scene)
        self.assertIn("MoveAlongPath(token, path)", hand_scene)
        for label in ('"HELLO"', '"DERIVE"', '"ENC"', '"FIN"', '"DATA"'):
            self.assertIn(label, hand_scene)
        self.assertIn(
            '([-1.72, 0.82, 0], [1.72, 0.82, 0], "HELLO"',
            hand_scene,
        )
        self.assertIn('handshake_key([-0.15, 0.15, 0]', hand_scene)
        self.assertGreaterEqual(hand_scene.count("wait_with_story_motion("), 4)
        self.assertIn("rotation_angle=0.022 * TAU", hand_scene)
        self.assertNotIn('hand_label(f"SKETCH {stage + 1}/5"', hand_scene)
        incomplete = replace(plan, claims=claims[:-1])
        fallback = compile_manim_scene(incomplete, animation_style="hand_drawn")
        self.assertEqual(fallback.story["kind"], "causal_explainer")
        self.assertNotEqual(fallback.story["core_label"], "SECURE CHANNEL")

    def test_causal_caption_emphasis_uses_first_meaningful_aligned_word(self):
        words = [
            WordTiming("After", 5.0, 5.25, "beat"),
            WordTiming("both", 5.25, 5.45, "beat"),
            WordTiming("peers", 5.45, 5.8, "beat"),
            WordTiming("validate", 5.8, 6.2, "beat"),
        ]
        cue = NarrationCue("beat", "After both peers validate", 5.0, 6.2, words)
        captions = _caption_payload(cue, "", 1.2, story_kind="causal_explainer")
        self.assertEqual(captions[0]["emphasis_start_seconds"], 0.45)

    def test_semantic_caption_cadence_does_not_leave_one_word_orphans(self):
        text = "The refrigerant condenses back into a liquid."
        words = [
            WordTiming(
                word,
                index * 0.3,
                index * 0.3 + 0.26,
                "beat",
            )
            for index, word in enumerate(text.split())
        ]
        cue = NarrationCue("beat", text, 0.0, 2.06, words)
        captions = _caption_payload(
            cue,
            "",
            2.06,
            story_kind="causal_explainer",
        )
        self.assertEqual([caption["text"] for caption in captions], [text])

    def test_unseen_dns_sequence_uses_persistent_process_grammar(self):
        dns_texts = [
            "First, a resolver checks locally available information, including cached records, and returns a usable answer immediately when one is present.",
            "If the resolver has no local answer, it finds the best name servers to ask and sends a DNS query to one of them.",
            "When a response contains a valid referral, the referral points the resolver toward a closer name server, so the resolver updates its server list and repeats the search.",
            "An authoritative answer returns the requested resource data, such as the host address associated with a domain name.",
            "Finally, the resolver returns the answer to the client and stores cacheable response data for future use according to its time to live.",
        ]
        dns_source = source("dns", "https://www.rfc-editor.org/rfc/rfc1034")
        claims = [
            Claim(
                f"dns{index}",
                text,
                text,
                "dns",
                dns_source.origin,
                "RFC 1034",
                0.95,
                ClaimType.OFFICIAL_FACT,
            )
            for index, text in enumerate(dns_texts)
        ]
        plan = plan_video(
            "How DNS resolution finds an IP address",
            [dns_source],
            claims,
            hook_style="question",
        )
        spec = compile_manim_scene(plan, animation_style="hand_drawn")
        self.assertEqual(spec.story["kind"], "causal_explainer")
        self.assertEqual(spec.story["transition_mode"], "semantic_continuity")
        self.assertEqual(spec.story["recap_mode"], "full_route_sweep")
        self.assertEqual(spec.story["topology_mode"], "linear_journey")
        self.assertEqual(
            spec.story["source_visual_profile"],
            "generic_process_v1",
        )
        self.assertEqual(spec.story["core_label"], "LOOKUP → STORE")
        self.assertEqual(
            spec.story["hook_title"]["text"],
            "How does DNS resolution find an IP address?",
        )
        self.assertNotIn("…", spec.story["hook_title"]["text"])
        self.assertEqual(
            [stage["mechanism_role"] for stage in spec.story["stages"]],
            ["LOOKUP", "DISPATCH", "ROUTE", "RESOLVE", "STORE"],
        )
        self.assertEqual(
            [stage["label"] for stage in spec.story["stages"]],
            [
                "check local cache",
                "send DNS query",
                "referral points to closer server",
                "return authoritative address",
                "return answer • store by time to live",
            ],
        )
        self.assertTrue(
            all(
                "…" not in stage["label"]
                and stage["label_source_token_overlap"] >= 2
                for stage in spec.story["stages"]
            )
        )
        self.assertEqual(
            spec.story["stage_label_render_mode"],
            "complete_scaled_two_line",
        )
        serialized = json.dumps(spec.story)
        self.assertNotIn("SOFTMAX", serialized.upper())
        self.assertNotIn("CLIENTHELLO", serialized.upper())
        for style in ANIMATION_STYLES:
            styled = compile_manim_scene(plan, animation_style=style)
            self.assertEqual(styled.story["kind"], "causal_explainer")
            self.assertEqual(
                [stage["mechanism_role"] for stage in styled.story["stages"]],
                ["LOOKUP", "DISPATCH", "ROUTE", "RESOLVE", "STORE"],
            )
        with tempfile.TemporaryDirectory() as tmp:
            scene = write_scene_py(Path(tmp), spec).read_text(encoding="utf-8")
        compile(scene, "<generated-tcp-scene>", "exec")
        for marker in (
            "def process_positions()",
            "def process_label_positions()",
            "def process_curve_points(index, endpoint_buffer=0.0)",
            "def process_backbone_points()",
            "def process_travel_path(index)",
            "def process_role_glyph(point, role, color, seed)",
            "def complete_wrap_text(value, max_width=7.2",
            "def process_carrier(point, color, seed)",
            '"process_backbone"',
            '"process_carrier"',
            '"process_station_{index}"',
            "def play_process_motion(scene, visual, stage, cycle_index, run_time)",
            "def process_recap_animation(visual, run_time)",
            "def play_process_recap(scene, visual, run_time)",
            "MoveAlongPath(process_token, path)",
            "path = process_travel_path(stage)",
            "ShowPassingFlash(",
            "ONE QUESTION • ONE CONTINUOUS JOURNEY",
            "ONE CONTINUOUS PATH",
            'STORY.get("recap_mode") == "full_route_sweep"',
            "is_final_recap_caption = (",
            "complete=True,",
        ):
            self.assertIn(marker, scene)
        self.assertIn("np.array([-2.36, 2.44, 0.0])", scene)
        self.assertIn(
            'STORY.get("hook_title", {}).get("text", item["title"])',
            scene,
        )
        self.assertIn("np.array([2.26, 1.18, 0.0])", scene)
        self.assertNotIn("np.array([-2.72, 1.25, 0.0])", scene)

    def test_browser_navigation_reuses_spatial_journey_without_tls_hijack(self):
        browser_texts = [
            "First, navigation begins when a person requests a page, and the browser finds the server's IP address through DNS, reusing a cached result when one is available.",
            "Next, after the browser establishes a TCP connection, TLS verifies the server for HTTPS and establishes a secure connection before content transfer begins.",
            "Once the connection is ready, the browser sends an initial HTTP GET request, and the server replies with response headers and the contents of the HTML document.",
            "As HTML arrives, the browser tokenizes the markup and builds a DOM tree, while linked stylesheets, scripts, images, and other resources can trigger more requests.",
            "Finally, the browser combines the DOM and CSSOM into a render tree, computes layout for visible elements, and paints the resulting pixels to the screen.",
        ]
        browser_source = source(
            "browser",
            "https://developer.mozilla.org/en-US/docs/Web/Performance/Guides/How_browsers_work",
        )
        claims = [
            Claim(
                f"browser{index}",
                text,
                text,
                "browser",
                browser_source.origin,
                "MDN browser navigation",
                0.95,
                ClaimType.OFFICIAL_FACT,
            )
            for index, text in enumerate(browser_texts)
        ]
        plan = plan_video(
            "How a browser turns a URL into a page",
            [browser_source],
            claims,
            hook_style="question",
        )
        spec = compile_manim_scene(plan, animation_style="hand_drawn")
        self.assertEqual(spec.story["kind"], "causal_explainer")
        self.assertEqual(spec.story["topology_mode"], "linear_journey")
        self.assertEqual(
            spec.story["source_visual_profile"],
            "generic_process_v1",
        )
        self.assertEqual(spec.story["core_label"], "LOOKUP → TRANSFORM")
        self.assertEqual(
            spec.story["hook_title"]["text"],
            "How does a browser turn a URL into a page?",
        )
        self.assertNotEqual(spec.story["kind"], "mechanism_handshake")
        self.assertEqual(
            [stage["mechanism_role"] for stage in spec.story["stages"]],
            ["LOOKUP", "VERIFY", "DISPATCH", "TRANSFORM", "TRANSFORM"],
        )
        self.assertEqual(
            [stage["label"] for stage in spec.story["stages"]],
            [
                "request page • find server IP",
                "verify HTTPS server • establish secure connection",
                "send HTTP GET request",
                "tokenize HTML • build DOM",
                "combine DOM + CSSOM • paint pixels",
            ],
        )
        self.assertTrue(
            all(
                "…" not in stage["label"]
                and stage["label_source_token_overlap"] >= 2
                for stage in spec.story["stages"]
            )
        )
        self.assertEqual(
            spec.story["stage_label_render_mode"],
            "complete_scaled_two_line",
        )
        with tempfile.TemporaryDirectory() as tmp:
            scene = write_scene_py(Path(tmp), spec).read_text(encoding="utf-8")
        self.assertIn("def process_curve_points(index, endpoint_buffer=0.0)", scene)
        self.assertIn('"process_backbone"', scene)
        self.assertNotIn("def browser_navigation_visual", scene)

    def test_unseen_tcp_control_loop_adds_source_backed_feedback_return(self):
        tcp_texts = [
            "First, TCP uses a congestion window to limit in-flight data; slow start probes unknown network capacity instead of releasing a large burst.",
            "Each new acknowledgment, or ACK, increases the window, allowing more data in flight while network feedback remains healthy.",
            "At the slow-start threshold, congestion avoidance grows the window gradually, by no more than one maximum-size sender segment per network round trip.",
            "When a retransmission timeout detects loss, TCP sets the threshold to no more than half the data still in flight and reduces the congestion window.",
            "Finally, after recovery the sender tests capacity again with the adjusted window; new ACKs raise it and later congestion lowers it, repeating the feedback loop.",
        ]
        tcp_source = source(
            "tcp",
            "https://www.rfc-editor.org/rfc/rfc5681",
        )
        claims = [
            Claim(
                f"tcp{index}",
                text,
                text,
                "tcp",
                tcp_source.origin,
                "RFC 5681",
                0.95,
                ClaimType.OFFICIAL_FACT,
            )
            for index, text in enumerate(tcp_texts)
        ]
        plan = plan_video(
            "How TCP congestion control learns the available capacity",
            [tcp_source],
            claims,
            hook_style="question",
        )
        spec = compile_manim_scene(plan, animation_style="hand_drawn")
        self.assertEqual(spec.story["kind"], "causal_explainer")
        self.assertEqual(spec.story["topology_mode"], "feedback_loop")
        self.assertEqual(
            spec.story["source_visual_profile"],
            "tcp_congestion_control_v1",
        )
        self.assertEqual(spec.story["core_label"], "PROBE ↻ ADJUST")
        contract = spec.story["feedback_contract"]
        self.assertTrue(contract["detected"])
        self.assertEqual(contract["mode"], "source_feedback_loop_v1")
        self.assertGreaterEqual(contract["evidence_stage_count"], 3)
        self.assertIn("window", contract["shared_state_tokens"])
        self.assertEqual(contract["return_from_stage_index"], 4)
        self.assertEqual(contract["return_to_stage_index"], 0)
        self.assertEqual(
            [stage["mechanism_role"] for stage in spec.story["stages"]],
            ["PROBE", "EXPAND", "MODERATE", "ADJUST", "FEEDBACK"],
        )
        self.assertEqual(
            [stage["label"] for stage in spec.story["stages"]],
            [
                "limit in-flight data • probe capacity",
                "ACK increases window",
                "cross threshold • grow window gradually",
                "detect loss • reduce window",
                "ACKs raise window • congestion lowers it",
            ],
        )
        self.assertTrue(
            all(
                "…" not in stage["label"]
                and stage["label_source_token_overlap"] >= 2
                for stage in spec.story["stages"]
            )
        )
        with tempfile.TemporaryDirectory() as tmp:
            scene = write_scene_py(Path(tmp), spec).read_text(encoding="utf-8")
        for marker in (
            "def process_feedback_points(endpoint_buffer=0.0)",
            "def process_recap_points()",
            "def tcp_packet_icon(point, color, size=0.18",
            "def tcp_role_glyph(point, role, color, seed)",
            "def tcp_window_state(stage)",
            '"tcp_window_state"',
            '"CONGESTION WINDOW"',
            '"ACKS • REPEAT"',
            '"process_feedback_return"',
            '"FEEDBACK"',
            '"PROBE → ADJUST → PROBE AGAIN"',
            'STORY.get("topology_mode") in {"feedback_loop", "cycle_loop"}',
        ):
            self.assertIn(marker, scene)
        incomplete_plan = plan_video(
            "TCP congestion windows",
            [tcp_source],
            claims[:2],
            hook_style="question",
        )
        incomplete_spec = compile_manim_scene(
            incomplete_plan,
            animation_style="hand_drawn",
        )
        self.assertNotEqual(
            incomplete_spec.story["source_visual_profile"],
            "tcp_congestion_control_v1",
        )

    def test_unseen_heat_pump_adds_evidence_gated_closed_cycle_return(self):
        heat_texts = [
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
        heat_source = source(
            "heat-pump",
            "https://www.energy.gov/energysaver/heat-pump-systems",
        )
        claims = [
            Claim(
                f"heat{index}",
                text,
                text,
                "heat-pump",
                heat_source.origin,
                "U.S. Department of Energy",
                0.95,
                ClaimType.OFFICIAL_FACT,
            )
            for index, text in enumerate(heat_texts)
        ]
        plan = plan_video(
            "How a heat pump moves heat",
            [heat_source],
            claims,
            hook_style="question",
        )
        spec = compile_manim_scene(plan, animation_style="whiteboard")
        self.assertEqual(spec.story["kind"], "causal_explainer")
        self.assertEqual(spec.story["topology_mode"], "cycle_loop")
        self.assertEqual(
            spec.story["source_visual_profile"],
            "heat_pump_cycle_v1",
        )
        self.assertEqual(spec.story["core_label"], "ONE CLOSED CYCLE")
        contract = spec.story["cycle_contract"]
        self.assertTrue(contract["detected"])
        self.assertEqual(contract["mode"], "source_cycle_loop_v1")
        self.assertEqual(contract["return_from_stage_index"], 4)
        self.assertEqual(contract["return_to_stage_index"], 1)
        self.assertGreaterEqual(contract["evidence_stage_count"], 4)
        self.assertIn("refrigerant", contract["shared_state_tokens"])
        self.assertEqual(
            [stage["mechanism_role"] for stage in spec.story["stages"]],
            ["INPUT", "ABSORB", "COMPRESS", "RELEASE", "RETURN"],
        )
        with tempfile.TemporaryDirectory() as tmp:
            scene = write_scene_py(Path(tmp), spec).read_text(encoding="utf-8")
        compile(scene, "generated_heat_pump_scene.py", "exec")
        for marker in (
            '"process_feedback_return"',
            '"CYCLE"',
            '" • CYCLE REPEATS"',
            "def heat_pump_role_glyph(point, role, color, seed)",
            "def heat_pump_refrigerant_token(point, color, seed)",
            '"COLD • LOW PRESSURE"',
            '"HOT • HIGH PRESSURE"',
            'STORY.get("topology_mode") in {"feedback_loop", "cycle_loop"}',
        ):
            self.assertIn(marker, scene)

        nonrecurring_claims = list(claims)
        nonrecurring_claims[-1] = replace(
            nonrecurring_claims[-1],
            text=(
                "Finally, the cool low-pressure refrigerant leaves the "
                "expansion valve and enters the evaporator."
            ),
        )
        nonrecurring_plan = plan_video(
            "How a heat pump moves heat",
            [heat_source],
            nonrecurring_claims,
            hook_style="question",
        )
        nonrecurring_spec = compile_manim_scene(
            nonrecurring_plan,
            animation_style="whiteboard",
        )
        self.assertEqual(
            nonrecurring_spec.story["topology_mode"],
            "linear_journey",
        )

    def test_handshake_caption_emphasis_waits_for_the_named_protocol_object(self):
        words = [
            WordTiming("The", 7.0, 7.2, "beat"),
            WordTiming("server", 7.2, 7.55, "beat"),
            WordTiming("sends", 7.55, 7.85, "beat"),
            WordTiming("encrypted", 7.85, 8.3, "beat"),
        ]
        cue = NarrationCue("beat", "The server sends encrypted", 7.0, 8.3, words)
        captions = _caption_payload(cue, "", 1.3, story_kind="mechanism_handshake")
        self.assertEqual(captions[0]["emphasis_start_seconds"], 0.2)
        self.assertEqual(captions[0]["emphasis_text"], "The server sends encrypted")

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
