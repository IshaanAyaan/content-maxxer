import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from PIL import Image, ImageDraw

from contentmaxxer.models import Claim, ClaimType, ContentPlan, SlideSpec, VideoBeat
from contentmaxxer.motion import (
    measure_feedback_return_frames,
    measure_header_persistence_frames,
    measure_route_recap_frames,
    measure_semantic_continuity_frames,
    motion_threshold_for_style,
    select_motion_witnesses,
    summarize_motion,
)
from contentmaxxer.qa import (
    _delivery_cadence_check,
    _layout_checks,
    _manifest_check,
    _mechanism_motion_checks,
    _media_checks,
    _motion_witness_checks,
    _route_recap_checks,
    _semantic_continuity_checks,
    _semantic_emphasis_checks,
    _semantic_text_transition_checks,
    _word_alignment_checks,
    revise_plan,
)


class QAGateTests(unittest.TestCase):
    def test_motion_summary_counts_coverage_and_longest_static_run(self):
        summary = summarize_motion([0.5, 0.0, 0.0, 0.6, 0.0], sample_fps=5, threshold=0.3)
        self.assertEqual(summary["motion_coverage_percent"], 40.0)
        self.assertEqual(summary["longest_static_seconds"], 0.4)
        self.assertEqual(
            summary["longest_static_span"],
            {
                "start_seconds": 0.2,
                "end_seconds": 0.6,
                "duration_seconds": 0.4,
            },
        )

    def test_encoded_route_recap_requires_ordered_top_to_bottom_motion(self):
        frames = [Image.new("L", (240, 218), 0) for _ in range(12)]
        for index, y in enumerate((30, 42, 58, 78, 102, 130, 158), start=3):
            draw = ImageDraw.Draw(frames[index])
            draw.ellipse((92, y, 108, y + 16), fill=255)
        measured = measure_route_recap_frames(
            frames,
            1.1,
            sample_fps=10,
        )
        self.assertTrue(measured["passed"])
        self.assertGreaterEqual(measured["top_active_frame_count"], 2)
        self.assertGreaterEqual(measured["bottom_active_frame_count"], 1)
        stationary = [Image.new("L", (240, 218), 0) for _ in range(12)]
        for index in range(3, 10):
            draw = ImageDraw.Draw(stationary[index])
            draw.ellipse((92, 150, 108, 166), fill=255)
        failed = measure_route_recap_frames(
            stationary,
            1.1,
            sample_fps=10,
        )
        self.assertFalse(failed["passed"])

        widened = measure_route_recap_frames(
            frames,
            1.1,
            sample_fps=10,
            window_seconds=1.1,
        )
        self.assertEqual(widened["window_start_seconds"], 0.0)
        self.assertTrue(widened["passed"])

        spec = SimpleNamespace(
            story={
                "kind": "causal_explainer",
                "recap_mode": "full_route_sweep",
            }
        )
        passing = _route_recap_checks(
            spec,
            {
                "renderer": "manim",
                "motion": {"route_recap": measured},
            },
        )
        self.assertTrue(passing[0].passed)
        failing = _route_recap_checks(
            spec,
            {
                "renderer": "manim",
                "motion": {"route_recap": failed},
            },
        )
        self.assertFalse(failing[0].passed)

    def test_encoded_feedback_recap_requires_bottom_to_upper_return(self):
        frames = [Image.new("L", (240, 218), 0) for _ in range(18)]
        positions = (
            (120, 28),
            (126, 52),
            (132, 78),
            (128, 106),
            (118, 138),
            (104, 168),
            (88, 194),
            (66, 176),
            (58, 150),
            (52, 120),
            (46, 92),
            (42, 64),
            (44, 38),
            (54, 22),
        )
        for index, (x, y) in enumerate(positions, start=3):
            draw = ImageDraw.Draw(frames[index])
            draw.ellipse((x - 8, y - 8, x + 8, y + 8), fill=255)
        measured = measure_feedback_return_frames(
            frames,
            1.7,
            sample_fps=10,
            window_seconds=1.7,
        )
        self.assertTrue(measured["passed"])
        self.assertGreaterEqual(
            measured["return_upper_left_active_frame_count"],
            2,
        )
        self.assertGreaterEqual(measured["loop_span_seconds"], 0.2)

        linear_frames = [Image.new("L", (240, 218), 0) for _ in range(18)]
        for index, (x, y) in enumerate(positions[:7], start=3):
            draw = ImageDraw.Draw(linear_frames[index])
            draw.ellipse((x - 8, y - 8, x + 8, y + 8), fill=255)
        rejected = measure_feedback_return_frames(
            linear_frames,
            1.7,
            sample_fps=10,
            window_seconds=1.7,
        )
        self.assertFalse(rejected["passed"])

        route = measure_route_recap_frames(
            frames,
            1.7,
            sample_fps=10,
            window_seconds=1.7,
        )
        spec = SimpleNamespace(
            story={
                "kind": "causal_explainer",
                "recap_mode": "full_route_sweep",
                "topology_mode": "feedback_loop",
            }
        )
        passing = _route_recap_checks(
            spec,
            {
                "renderer": "manim",
                "motion": {
                    "route_recap": {
                        **route,
                        "feedback_return": measured,
                    }
                },
            },
        )
        self.assertTrue(passing[0].passed)
        missing_return = _route_recap_checks(
            spec,
            {
                "renderer": "manim",
                "motion": {"route_recap": route},
            },
        )
        self.assertFalse(missing_return[0].passed)

    def test_motion_witnesses_surface_multiple_interior_changes_per_beat(self):
        signals = [0.01] * 30
        for index, value in {
            4: 1.2,
            8: 0.8,
            12: 1.0,
            16: 0.9,
            21: 1.4,
            26: 1.1,
        }.items():
            signals[index] = value
        witnesses = select_motion_witnesses(
            signals,
            [
                ("beat_01", 0.0, 3.0),
                ("beat_02", 3.0, 6.0),
            ],
            sample_fps=5,
            per_segment=3,
        )
        self.assertEqual(len(witnesses), 6)
        self.assertEqual(
            [item["segment_id"] for item in witnesses],
            ["beat_01"] * 3 + ["beat_02"] * 3,
        )
        self.assertEqual(
            [item["selection_reason"] for item in witnesses].count(
                "subtle_motion"
            ),
            2,
        )
        self.assertTrue(
            all(
                item["timestamp_seconds"] == item["peak_timestamp_seconds"]
                if item["selection_reason"] == "subtle_motion"
                else item["timestamp_seconds"] < item["peak_timestamp_seconds"]
                for item in witnesses
            )
        )

    def test_encoded_continuity_measure_separates_growth_from_scene_resets(self):
        def frame_with_lines(lines):
            image = Image.new("L", (240, 238), 16)
            draw = ImageDraw.Draw(image)
            for line in lines:
                draw.line(line, fill=238, width=5)
            return image

        backbone = (20, 120, 220, 120)
        cumulative = [
            frame_with_lines([(15, 25, 225, 25)]),
            frame_with_lines([backbone, (35, 120, 35, 75)]),
            frame_with_lines(
                [backbone, (35, 120, 35, 75), (95, 120, 95, 65)]
            ),
            frame_with_lines(
                [
                    backbone,
                    (35, 120, 35, 75),
                    (95, 120, 95, 65),
                    (155, 120, 155, 55),
                ]
            ),
            frame_with_lines(
                [
                    backbone,
                    (35, 120, 35, 75),
                    (95, 120, 95, 65),
                    (155, 120, 155, 55),
                    (215, 120, 215, 45),
                ]
            ),
        ]
        resets = [
            frame_with_lines([(15, 25, 225, 25)]),
            frame_with_lines([(20, 55, 70, 55)]),
            frame_with_lines([(95, 95, 145, 95)]),
            frame_with_lines([(165, 135, 215, 135)]),
            frame_with_lines([(85, 185, 135, 185)]),
        ]
        segments = [
            (f"beat_{index + 1:02d}", float(index), float(index))
            for index in range(5)
        ]
        growing = measure_semantic_continuity_frames(
            cumulative,
            segments,
            sample_fps=1,
        )
        replacing = measure_semantic_continuity_frames(
            resets,
            segments,
            sample_fps=1,
        )
        self.assertGreaterEqual(
            growing["average_retained_edge_ratio"],
            0.6,
        )
        self.assertLess(
            replacing["average_retained_edge_ratio"],
            0.35,
        )

    def test_encoded_header_measure_separates_hold_from_replacement(self):
        held = []
        replaced = []
        for index in range(5):
            held_frame = Image.new("L", (240, 60), 16)
            held_draw = ImageDraw.Draw(held_frame)
            held_draw.line((20, 20, 220, 20), fill=238, width=5)
            held.append(held_frame)

            replaced_frame = Image.new("L", (240, 60), 16)
            replaced_draw = ImageDraw.Draw(replaced_frame)
            replaced_draw.line(
                (20, 8 + index * 10, 70, 8 + index * 10),
                fill=238,
                width=5,
            )
            replaced.append(replaced_frame)
        segments = [
            (f"beat_{index + 1:02d}", float(index), float(index))
            for index in range(5)
        ]
        stable = measure_header_persistence_frames(
            held,
            segments,
            sample_fps=1,
        )
        swapping = measure_header_persistence_frames(
            replaced,
            segments,
            sample_fps=1,
        )
        self.assertGreaterEqual(
            stable["minimum_retained_edge_ratio"],
            0.95,
        )
        self.assertLess(
            swapping["median_retained_edge_ratio"],
            0.1,
        )

    def test_motion_witness_gate_requires_files_contact_sheet_and_beat_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            witness_root = root / "video" / "manim" / "motion-witness-frames"
            witness_root.mkdir(parents=True)
            witnesses = []
            for beat_index in (1, 2):
                for witness_index in (1, 2):
                    name = f"{beat_index}-{witness_index}.png"
                    Image.new("RGB", (100, 200), "navy").save(witness_root / name)
                    witnesses.append(
                        {
                            "segment_id": f"beat_{beat_index:02d}",
                            "path": name,
                        }
                    )
            sheet = root / "video" / "motion-contact-sheet.png"
            Image.new("RGB", (300, 300), "black").save(sheet)
            plan = SimpleNamespace(
                beats=[
                    SimpleNamespace(id="beat_01"),
                    SimpleNamespace(id="beat_02"),
                ]
            )
            spec = SimpleNamespace(
                story={"kind": "mechanism_handshake"},
                width=100,
                height=200,
            )
            metadata = {
                "renderer": "manim",
                "motion_witness_root": "video/manim/motion-witness-frames",
                "motion": {"witnesses": witnesses},
                "outputs": {
                    "motion_contact_sheet": "video/motion-contact-sheet.png",
                },
            }
            passing = _motion_witness_checks(root, plan, spec, metadata)
            self.assertTrue(passing[0].passed)
            metadata["motion"]["witnesses"] = witnesses[:2]
            failing = _motion_witness_checks(root, plan, spec, metadata)
            self.assertFalse(failing[0].passed)

    def test_papyrus_uses_a_contrast_aware_motion_threshold(self):
        self.assertEqual(motion_threshold_for_style("warm_papyrus"), 0.18)
        self.assertEqual(motion_threshold_for_style("whiteboard"), 0.3)
        self.assertEqual(motion_threshold_for_style("future_minimal"), 0.3)

    def test_delivery_cadence_is_advisory_and_uses_the_tested_short_form_range(self):
        paced = _delivery_cadence_check(155.8)
        self.assertTrue(paced.passed)
        self.assertFalse(paced.hard)
        slow = _delivery_cadence_check(126.0)
        self.assertFalse(slow.passed)
        self.assertFalse(slow.hard)

    def test_word_alignment_is_hard_gated_after_local_aligner_acceptance(self):
        passing = _word_alignment_checks(
            {
                "provider_metadata": {
                    "word_alignment": {
                        "status": "aligned",
                        "timing_coverage_percent": 100.0,
                        "wer": 0.0194,
                    }
                }
            }
        )
        self.assertTrue(all(check.passed and check.hard for check in passing))
        failing = _word_alignment_checks(
            {
                "provider_metadata": {
                    "word_alignment": {
                        "status": "aligned",
                        "timing_coverage_percent": 90.0,
                        "wer": 0.2,
                    }
                }
            }
        )
        self.assertFalse(any(check.passed for check in failing))
        fallback = _word_alignment_checks(
            {
                "provider_metadata": {
                    "word_alignment": {
                        "status": "unavailable",
                        "fallback": "measured_audio_proportional_words",
                    }
                }
            }
        )
        self.assertFalse(fallback[0].passed)
        self.assertFalse(fallback[0].hard)

    def test_semantic_emphasis_gate_requires_scheduled_valid_word_events(self):
        spec = SimpleNamespace(
            story={"kind": "mechanism_gradient"},
            primitives=[object()] * 5,
        )
        passing = _semantic_emphasis_checks(
            spec,
            {
                "renderer": "manim",
                "audio": {},
                "semantic_emphasis": {
                    "scheduled_event_count": 4,
                    "invalid_event_count": 0,
                    "delayed_event_count": 3,
                    "max_trigger_delay_seconds": 1.2,
                },
            },
        )
        self.assertTrue(passing[0].passed)
        failing = _semantic_emphasis_checks(
            spec,
            {
                "renderer": "manim",
                "audio": {},
                "semantic_emphasis": {
                    "scheduled_event_count": 3,
                    "invalid_event_count": 1,
                },
            },
        )
        self.assertFalse(failing[0].passed)

    def test_semantic_continuity_gate_requires_contract_and_encoded_evidence(self):
        plan = SimpleNamespace(
            beats=[SimpleNamespace(id=f"beat_{index:02d}") for index in range(5)]
        )
        spec = SimpleNamespace(
            story={
                "kind": "causal_explainer",
                "transition_mode": "semantic_continuity",
            }
        )
        metadata = {
            "renderer": "manim",
            "motion": {
                "semantic_continuity": {
                    "eligible_transition_count": 3,
                    "valid_transition_count": 3,
                    "insufficient_edge_transition_count": 0,
                    "average_retained_edge_ratio": 0.66,
                    "median_retained_edge_ratio": 0.81,
                    "reset_transition_count": 1,
                }
            },
        }
        passing = _semantic_continuity_checks(plan, spec, metadata)
        self.assertTrue(passing[0].passed)
        metadata["motion"]["semantic_continuity"][
            "average_retained_edge_ratio"
        ] = 0.59
        failing = _semantic_continuity_checks(plan, spec, metadata)
        self.assertFalse(failing[0].passed)
        spec.story["transition_mode"] = "scene_swap"
        metadata["motion"]["semantic_continuity"][
            "average_retained_edge_ratio"
        ] = 0.9
        contract_failure = _semantic_continuity_checks(plan, spec, metadata)
        self.assertFalse(contract_failure[0].passed)

    def test_semantic_text_gate_rejects_rapid_headline_and_caption_swaps(self):
        spec = SimpleNamespace(
            story={"kind": "causal_explainer"},
            primitives=[object()] * 5,
        )
        passing = _semantic_text_transition_checks(
            spec,
            {
                "renderer": "manim",
                "frames": [
                    {
                        "text_boxes": [
                            {
                                "text": "How does the process work?",
                                "truncated": False,
                            }
                        ]
                    }
                ],
                "semantic_text_transitions": {
                    "mode": "persistent_lesson_header_handwritten_captions",
                    "hook_title_mode": "persistent_complete_hook",
                    "hook_title": "How does the process work?",
                    "hook_title_contains_ellipsis": False,
                    "hook_title_matches_plan_hook": True,
                    "stage_label_count": 5,
                    "stage_label_render_mode": "complete_scaled_two_line",
                    "stage_label_ellipsis_count": 0,
                    "maximum_stage_label_words": 7,
                    "minimum_stage_label_source_overlap": 3,
                    "stage_label_method_count": 5,
                    "recap_mode": "full_route_sweep",
                    "headline_replacement_count": 0,
                    "caption_transitions_per_minute": 29.4,
                    "median_caption_dwell_seconds": 1.86,
                    "rapid_caption_ratio": 0.0588,
                    "encoded_header_persistence": {
                        "transition_count": 4,
                        "minimum_retained_edge_ratio": 0.983,
                        "median_retained_edge_ratio": 0.987,
                    },
                },
            },
        )
        self.assertTrue(passing[0].passed)
        failing = _semantic_text_transition_checks(
            spec,
            {
                "renderer": "manim",
                "frames": [
                    {
                        "text_boxes": [
                            {
                                "text": "How does the process…",
                                "truncated": True,
                            }
                        ]
                    }
                ],
                "semantic_text_transitions": {
                    "mode": "beat_headline_swap",
                    "hook_title_mode": "truncated_hook",
                    "hook_title": "How does the process…",
                    "hook_title_contains_ellipsis": True,
                    "hook_title_matches_plan_hook": False,
                    "stage_label_count": 5,
                    "stage_label_render_mode": "truncating_wrap",
                    "stage_label_ellipsis_count": 5,
                    "maximum_stage_label_words": 9,
                    "minimum_stage_label_source_overlap": 1,
                    "stage_label_method_count": 0,
                    "recap_mode": "none",
                    "headline_replacement_count": 4,
                    "caption_transitions_per_minute": 42.2,
                    "median_caption_dwell_seconds": 1.31,
                    "rapid_caption_ratio": 0.125,
                    "encoded_header_persistence": {
                        "transition_count": 4,
                        "minimum_retained_edge_ratio": 0.577,
                        "median_retained_edge_ratio": 0.765,
                    },
                },
            },
        )
        self.assertFalse(failing[0].passed)

    def test_semantic_gates_cover_mechanisms_arguments_and_causal_sequences(self):
        mechanism = SimpleNamespace(story={"kind": "mechanism_orbit"})
        passing = _mechanism_motion_checks(
            mechanism,
            {
                "renderer": "manim",
                "motion": {
                    "motion_coverage_percent": 25.0,
                    "longest_static_seconds": 6.0,
                },
            },
        )
        self.assertTrue(passing[0].passed)
        failing = _mechanism_motion_checks(
            mechanism,
            {
                "renderer": "manim",
                "motion": {
                    "motion_coverage_percent": 24.9,
                    "longest_static_seconds": 6.1,
                },
            },
        )
        self.assertFalse(failing[0].passed)
        argument = SimpleNamespace(story={"kind": "open_weights_debate"})
        argument_check = _mechanism_motion_checks(
            argument,
            {
                "renderer": "manim",
                "motion": {
                    "motion_coverage_percent": 25.0,
                    "longest_static_seconds": 6.0,
                },
            },
        )
        self.assertEqual(argument_check[0].name, "argument_motion")
        self.assertTrue(argument_check[0].passed)
        causal = SimpleNamespace(story={"kind": "causal_explainer"})
        causal_check = _mechanism_motion_checks(
            causal,
            {
                "renderer": "manim",
                "motion": {
                    "motion_coverage_percent": 25.0,
                    "longest_static_seconds": 6.0,
                },
            },
        )
        self.assertEqual(causal_check[0].name, "causal_motion")
        self.assertTrue(causal_check[0].passed)
        editorial = SimpleNamespace(
            story={"kind": "technology_adolescence"}
        )
        editorial_check = _mechanism_motion_checks(
            editorial,
            {
                "renderer": "manim",
                "motion": {
                    "motion_coverage_percent": 16.0,
                    "longest_static_seconds": 5.5,
                },
            },
        )
        self.assertEqual(editorial_check[0].name, "editorial_motion")
        self.assertTrue(editorial_check[0].passed)
        causal_emphasis = _semantic_emphasis_checks(
            SimpleNamespace(
                story={"kind": "causal_explainer"},
                primitives=[object()] * 5,
            ),
            {
                "renderer": "manim",
                "audio": {},
                "semantic_emphasis": {
                    "scheduled_event_count": 4,
                    "invalid_event_count": 0,
                },
            },
        )
        self.assertTrue(causal_emphasis[0].passed)
        generic = SimpleNamespace(story={"kind": "generic_explainer"})
        self.assertEqual(_mechanism_motion_checks(generic, {"renderer": "manim"}), [])

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
