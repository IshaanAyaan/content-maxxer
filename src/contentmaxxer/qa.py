"""Hard, evidence-bearing QA gates and deterministic plan revision."""

import copy
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from PIL import Image, ImageStat

from .io import read_json, write_json
from .models import ContentPlan, ManimSceneSpec, QACheck, QAReport, SlideSpec, VideoBeat
from .motion import (
    CONTINUITY_MIN_AVERAGE_RETENTION,
    CONTINUITY_MIN_MEDIAN_RETENTION,
    FEEDBACK_RETURN_MIN_BOTTOM_ACTIVE_FRAMES,
    FEEDBACK_RETURN_MIN_LOOP_SECONDS,
    FEEDBACK_RETURN_MIN_UPPER_LEFT_ACTIVE_FRAMES,
    HEADER_MEDIAN_RETENTION,
    HEADER_MINIMUM_RETENTION,
    ROUTE_RECAP_MIN_BOTTOM_ACTIVE_FRAMES,
    ROUTE_RECAP_MIN_TOP_ACTIVE_FRAMES,
    ROUTE_RECAP_MIN_TRAVERSAL_SECONDS,
)


def _check(name: str, passed: bool, detail: str, *, hard: bool = True) -> QACheck:
    return QACheck(name=name, passed=bool(passed), detail=detail, hard=hard)


def _delivery_cadence_check(words_per_minute: float) -> QACheck:
    """Flag narration outside the tested short-form cadence without blocking slower lessons."""
    return _check(
        "delivery_cadence",
        135 <= words_per_minute <= 185,
        f"words_per_minute={words_per_minute:.1f}; preferred=135-185",
        hard=False,
    )


def _referenced_claims(plan: ContentPlan) -> List[str]:
    ids: List[str] = []
    for item in list(plan.beats) + list(plan.slides):
        ids.extend(item.claim_ids)
    return ids


def _citation_checks(plan: ContentPlan) -> List[QACheck]:
    claim_map = {claim.id: claim for claim in plan.claims}
    referenced = _referenced_claims(plan)
    missing = [claim_id for claim_id in referenced if claim_id not in claim_map]
    uncited_items = [
        item.id
        for item in list(plan.beats) + list(plan.slides)
        if not item.claim_ids or not item.source_label.strip()
    ]
    bad_evidence = [claim.id for claim in plan.claims if not claim.evidence_excerpt.strip() or not claim.source_label.strip()]
    first_item = (plan.beats or plan.slides or [None])[0]
    first_claim = claim_map.get(first_item.claim_ids[0]) if first_item is not None and first_item.claim_ids else None
    hook_bound = not plan.hook_style == "statistic" or bool(first_claim and first_claim.numeric)
    return [
        _check("schema", plan.schema_version == "1.0" and plan.format in {"video", "carousel"}, f"schema={plan.schema_version}; format={plan.format}"),
        _check("grounding", plan.grounded, plan.blocked_reason or "plan is grounded"),
        _check("citation_coverage", not missing and not uncited_items, f"missing_claims={missing}; uncited_items={uncited_items}"),
        _check("claim_evidence", not bad_evidence, f"claims_without_evidence={bad_evidence}"),
        _check("hook_binding", hook_bound, f"hook_style={plan.hook_style}; first_claim={getattr(first_claim, 'id', None)}"),
    ]


def _box_overlap(left: Sequence[int], right: Sequence[int]) -> bool:
    return not (left[2] <= right[0] or right[2] <= left[0] or left[3] <= right[1] or right[3] <= left[1])


def _media_checks(paths: Sequence[Path], expected: Optional[Tuple[int, int]] = None) -> List[QACheck]:
    missing = [str(path) for path in paths if not path.is_file() or path.stat().st_size == 0]
    dimensions: List[Tuple[str, Tuple[int, int]]] = []
    blank: List[str] = []
    digests: Dict[str, List[str]] = {}
    for path in paths:
        if not path.is_file() or path.stat().st_size == 0:
            continue
        with Image.open(path) as image:
            dimensions.append((path.name, image.size))
            extrema = ImageStat.Stat(image.convert("RGB")).extrema
            if all(low == high for low, high in extrema):
                blank.append(path.name)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        digests.setdefault(digest, []).append(path.name)
    duplicates = [names for names in digests.values() if len(names) > 1]
    wrong = [(name, size) for name, size in dimensions if expected and size != expected]
    return [
        _check("missing_files", not missing, f"missing={missing}"),
        _check("exact_dimensions", not wrong, f"expected={expected}; wrong={wrong}"),
        _check("blank_media", not blank, f"blank={blank}"),
        _check("duplicate_media", not duplicates, f"duplicates={duplicates}"),
    ]


def _layout_checks(items: Sequence[Dict[str, object]]) -> List[QACheck]:
    truncations: List[str] = []
    tiny: List[str] = []
    overlaps: List[str] = []
    outside: List[str] = []
    dense: List[str] = []
    for item in items:
        item_id = str(item.get("id") or item.get("path"))
        width, height = int(item["width"]), int(item["height"])
        safe = [int(value) for value in item["safe_zone"]]
        boxes = item.get("text_boxes", [])
        for box_meta in boxes:
            box = [int(value) for value in box_meta["box"]]
            if box_meta.get("truncated"):
                truncations.append(item_id)
            if int(box_meta.get("font_size", 0)) < 18:
                tiny.append(item_id)
            if (
                box[0] < safe[0]
                or box[1] < safe[1]
                or box[2] > safe[2]
                or box[3] > safe[3]
                or box[0] < 0
                or box[1] < 0
                or box[2] > width
                or box[3] > height
            ):
                outside.append(item_id)
            text = str(box_meta.get("text", ""))
            area = max(1, (box[2] - box[0]) * (box[3] - box[1]))
            if len(text) / area > 0.0012:
                dense.append(item_id)
        for first in range(len(boxes)):
            for second in range(first + 1, len(boxes)):
                if _box_overlap(boxes[first]["box"], boxes[second]["box"]):
                    overlaps.append(item_id)
    return [
        _check("safe_zones", not outside, f"outside_canvas_or_safe_regions={outside}"),
        _check("text_size", not tiny, f"below_18px={tiny}"),
        _check("truncation", not truncations, f"truncated={truncations}"),
        _check("overlap", not overlaps, f"overlap={overlaps}"),
        _check("density", not dense, f"dense={dense}"),
    ]


def _manifest_check(job_dir: Path, manifest_path: Optional[Path]) -> QACheck:
    if manifest_path is None or not manifest_path.exists():
        return _check("manifest_integrity", False, "manifest is missing")
    manifest = read_json(manifest_path)
    paths: List[str] = []

    def visit(value: object, key: str = "") -> None:
        if isinstance(value, dict):
            for child_key, child in value.items():
                visit(child, child_key)
        elif isinstance(value, list):
            for child in value:
                visit(child, key)
        elif isinstance(value, str) and key in {
            "path",
            "manifest",
            "metadata",
            "mp4",
            "srt",
            "contact_sheet",
            "scene",
            "spec",
            "plan",
            "citations",
            "audio",
            "timings",
            "raw_transcript",
            "motion_contact_sheet",
        }:
            paths.append(value)

    visit(manifest)
    absolute = [value for value in paths if Path(value).is_absolute()]
    missing = [value for value in paths if not Path(value).is_absolute() and not (job_dir / value).exists()]
    valid = manifest.get("schema_version") == "1.0" and not absolute and not missing
    return _check("manifest_integrity", valid, f"absolute={absolute}; missing={missing}")


def _mechanism_motion_checks(
    spec: ManimSceneSpec,
    render_metadata: Dict[str, object],
) -> List[QACheck]:
    story_kind = str(spec.story.get("kind", ""))
    is_mechanism = story_kind.startswith("mechanism_")
    is_argument = story_kind == "open_weights_debate"
    is_causal = story_kind == "causal_explainer"
    is_editorial = story_kind == "technology_adolescence"
    is_guided_route = story_kind == "lecun_world_model_bet"
    is_nested_model = story_kind == "elastic_llm_nesting"
    if (
        not is_mechanism
        and not is_argument
        and not is_causal
        and not is_editorial
        and not is_guided_route
        and not is_nested_model
    ) or render_metadata.get("renderer") != "manim":
        return []
    check_name = (
        "mechanism_motion"
        if is_mechanism
        else "argument_motion"
        if is_argument
        else "editorial_motion"
        if is_editorial
        else "guided_route_motion"
        if is_guided_route
        else "nested_model_motion"
        if is_nested_model
        else "causal_motion"
    )
    motion = render_metadata.get("motion")
    if not isinstance(motion, dict):
        return [_check(check_name, False, "motion metadata is missing")]
    coverage = float(motion.get("motion_coverage_percent", 0.0))
    longest_static = float(motion.get("longest_static_seconds", 999.0))
    minimum_coverage = (
        16.0
        if is_editorial
        else 30.0
        if is_guided_route or is_nested_model
        else 25.0
    )
    maximum_static = (
        5.5
        if is_editorial
        else 4.5
        if is_guided_route or is_nested_model
        else 6.0
    )
    passed = coverage >= minimum_coverage and longest_static <= maximum_static
    return [
        _check(
            check_name,
            passed,
            (
                f"coverage_percent={coverage}; longest_static_seconds={longest_static}; "
                f"required_coverage>={minimum_coverage:g}; "
                f"required_static<={maximum_static:g}"
            ),
        )
    ]


def _motion_witness_checks(
    job_dir: Path,
    plan: ContentPlan,
    spec: ManimSceneSpec,
    render_metadata: Dict[str, object],
) -> List[QACheck]:
    story_kind = str(spec.story.get("kind", ""))
    is_semantic_story = (
        story_kind.startswith("mechanism_")
        or story_kind
        in {
            "elastic_llm_nesting",
            "lecun_world_model_bet",
            "technology_adolescence",
            "open_weights_debate",
            "causal_explainer",
        }
    )
    if not is_semantic_story or render_metadata.get("renderer") != "manim":
        return []
    motion = render_metadata.get("motion")
    witnesses = motion.get("witnesses") if isinstance(motion, dict) else None
    if not isinstance(witnesses, list):
        return [
            _check(
                "motion_witness_evidence",
                False,
                "motion witness metadata is missing",
            )
        ]
    witness_root = job_dir / str(
        render_metadata.get(
            "motion_witness_root",
            "video/manim/motion-witness-frames",
        )
    )
    expected_ids = [beat.id for beat in plan.beats]
    counts = {beat_id: 0 for beat_id in expected_ids}
    missing: List[str] = []
    wrong_dimensions: List[str] = []
    for item in witnesses:
        if not isinstance(item, dict):
            missing.append("<invalid metadata>")
            continue
        segment_id = str(item.get("segment_id", ""))
        if segment_id in counts:
            counts[segment_id] += 1
        path = witness_root / str(item.get("path", ""))
        if not path.is_file():
            missing.append(str(item.get("path", "")))
            continue
        with Image.open(path) as image:
            if image.size != (spec.width, spec.height):
                wrong_dimensions.append(str(item.get("path", "")))
    outputs = render_metadata.get("outputs")
    sheet_path = (
        job_dir / str(outputs.get("motion_contact_sheet", ""))
        if isinstance(outputs, dict)
        else job_dir / ""
    )
    under_sampled = [
        beat_id
        for beat_id, count in counts.items()
        if count < 2
    ]
    passed = (
        not missing
        and not wrong_dimensions
        and not under_sampled
        and sheet_path.is_file()
    )
    return [
        _check(
            "motion_witness_evidence",
            passed,
            (
                f"witnesses={len(witnesses)}; per_beat={counts}; "
                f"under_sampled={under_sampled}; missing={missing}; "
                f"wrong_dimensions={wrong_dimensions}; "
                f"contact_sheet={sheet_path.is_file()}"
            ),
        )
    ]


def _word_alignment_checks(audio: Dict[str, object]) -> List[QACheck]:
    provider_metadata = audio.get("provider_metadata", {})
    word_alignment = (
        provider_metadata.get("word_alignment")
        if isinstance(provider_metadata, dict)
        else None
    )
    if not isinstance(word_alignment, dict):
        return []
    alignment_status = str(word_alignment.get("status", ""))
    if alignment_status != "aligned":
        return [
            _check(
                "voiceover_word_alignment",
                False,
                (
                    f"status={alignment_status}; fallback={word_alignment.get('fallback')}; "
                    f"reason={word_alignment.get('reason', '')}"
                ),
                hard=False,
            )
        ]
    timing_coverage = float(word_alignment.get("timing_coverage_percent", 0.0))
    alignment_wer = float(word_alignment.get("wer", 1.0))
    return [
        _check(
            "voiceover_word_alignment_coverage",
            timing_coverage >= 95.0,
            f"timing_coverage_percent={timing_coverage}; required>=95",
        ),
        _check(
            "voiceover_word_alignment_fidelity",
            alignment_wer <= 0.15,
            f"wer={alignment_wer}; required<=0.15",
        ),
    ]


def _semantic_emphasis_checks(
    spec: ManimSceneSpec,
    render_metadata: Dict[str, object],
) -> List[QACheck]:
    story_kind = str(spec.story.get("kind", ""))
    is_semantic_story = (
        story_kind.startswith("mechanism_")
        or story_kind
        in {
            "technology_adolescence",
            "open_weights_debate",
            "causal_explainer",
        }
    )
    if (
        not is_semantic_story
        or render_metadata.get("renderer") != "manim"
        or not isinstance(render_metadata.get("audio"), dict)
    ):
        return []
    summary = render_metadata.get("semantic_emphasis")
    if not isinstance(summary, dict):
        return [_check("semantic_emphasis_timing", False, "semantic emphasis metadata is missing")]
    scheduled = int(summary.get("scheduled_event_count", 0))
    invalid = int(summary.get("invalid_event_count", 999))
    required = max(1, len(spec.primitives) - 1)
    return [
        _check(
            "semantic_emphasis_timing",
            scheduled >= required and invalid == 0,
            (
                f"scheduled_events={scheduled}; required>={required}; invalid_events={invalid}; "
                f"delayed_events={summary.get('delayed_event_count')}; "
                f"max_trigger_delay_seconds={summary.get('max_trigger_delay_seconds')}"
            ),
        )
    ]


def _semantic_continuity_checks(
    plan: ContentPlan,
    spec: ManimSceneSpec,
    render_metadata: Dict[str, object],
) -> List[QACheck]:
    story_kind = str(spec.story.get("kind", ""))
    is_semantic_story = (
        story_kind.startswith("mechanism_")
        or story_kind in {"open_weights_debate", "causal_explainer"}
    )
    if not is_semantic_story or render_metadata.get("renderer") != "manim":
        return []
    transition_mode = str(spec.story.get("transition_mode", ""))
    motion = render_metadata.get("motion")
    continuity = (
        motion.get("semantic_continuity")
        if isinstance(motion, dict)
        else None
    )
    if not isinstance(continuity, dict):
        return [
            _check(
                "semantic_visual_continuity",
                False,
                (
                    f"transition_mode={transition_mode}; "
                    "encoded continuity metadata is missing"
                ),
            )
        ]
    expected = max(0, len(plan.beats) - 2)
    eligible = int(continuity.get("eligible_transition_count", 0))
    valid = int(continuity.get("valid_transition_count", 0))
    insufficient = int(
        continuity.get("insufficient_edge_transition_count", 999)
    )
    average = float(
        continuity.get("average_retained_edge_ratio", 0.0)
    )
    median = float(
        continuity.get("median_retained_edge_ratio", 0.0)
    )
    resets = int(continuity.get("reset_transition_count", 999))
    maximum_resets = 0 if expected == 0 else max(1, expected // 4)
    passed = (
        transition_mode == "semantic_continuity"
        and eligible == expected
        and valid == expected
        and insufficient == 0
        and (
            expected == 0
            or (
                average >= CONTINUITY_MIN_AVERAGE_RETENTION
                and median >= CONTINUITY_MIN_MEDIAN_RETENTION
                and resets <= maximum_resets
            )
        )
    )
    return [
        _check(
            "semantic_visual_continuity",
            passed,
            (
                f"transition_mode={transition_mode}; transitions={valid}/{expected}; "
                f"insufficient_edges={insufficient}; average_retention={average}; "
                f"median_retention={median}; reset_transitions={resets}; "
                f"allowed_resets={maximum_resets}; "
                f"required_average>={CONTINUITY_MIN_AVERAGE_RETENTION}; "
                f"required_median>={CONTINUITY_MIN_MEDIAN_RETENTION}"
            ),
        )
    ]


def _semantic_text_transition_checks(
    spec: ManimSceneSpec,
    render_metadata: Dict[str, object],
) -> List[QACheck]:
    story_kind = str(spec.story.get("kind", ""))
    is_semantic_story = (
        story_kind.startswith("mechanism_")
        or story_kind
        in {
            "technology_adolescence",
            "open_weights_debate",
            "causal_explainer",
        }
    )
    if not is_semantic_story or render_metadata.get("renderer") != "manim":
        return []
    summary = render_metadata.get("semantic_text_transitions")
    if not isinstance(summary, dict):
        return [
            _check(
                "semantic_text_cadence",
                False,
                "semantic text-transition metadata is missing",
            )
        ]
    mode = str(summary.get("mode", ""))
    hook_title_mode = str(summary.get("hook_title_mode", ""))
    hook_title = str(summary.get("hook_title", ""))
    hook_title_contains_ellipsis = bool(
        summary.get("hook_title_contains_ellipsis", True)
    )
    hook_title_matches_plan_hook = bool(
        summary.get("hook_title_matches_plan_hook", False)
    )
    stage_label_count = int(summary.get("stage_label_count", 0))
    stage_label_render_mode = str(
        summary.get("stage_label_render_mode", "")
    )
    stage_label_ellipsis_count = int(
        summary.get("stage_label_ellipsis_count", 999)
    )
    maximum_stage_label_words = int(
        summary.get("maximum_stage_label_words", 999)
    )
    minimum_stage_label_source_overlap = int(
        summary.get("minimum_stage_label_source_overlap", 0)
    )
    stage_label_method_count = int(
        summary.get("stage_label_method_count", 0)
    )
    topology_mode = str(summary.get("topology_mode", ""))
    source_visual_profile = str(
        summary.get("source_visual_profile", "")
    )
    motion_language = str(summary.get("motion_language", ""))
    chrome_mode = str(summary.get("chrome_mode", ""))
    source_badge_mode = str(summary.get("source_badge_mode", ""))
    feedback_contract_mode = str(
        summary.get("feedback_contract_mode", "")
    )
    feedback_evidence_stage_count = int(
        summary.get("feedback_evidence_stage_count", 0)
    )
    feedback_shared_state_token_count = int(
        summary.get("feedback_shared_state_token_count", 0)
    )
    cycle_contract_mode = str(
        summary.get("cycle_contract_mode", "")
    )
    cycle_evidence_stage_count = int(
        summary.get("cycle_evidence_stage_count", 0)
    )
    cycle_shared_state_token_count = int(
        summary.get("cycle_shared_state_token_count", 0)
    )
    expected_topology_mode = str(spec.story.get("topology_mode", ""))
    expected_source_visual_profile = str(
        spec.story.get("source_visual_profile", "")
    )
    topology_contract_passed = (
        not expected_topology_mode
        or topology_mode == expected_topology_mode
    )
    source_visual_profile_passed = (
        not expected_source_visual_profile
        or (
            source_visual_profile == expected_source_visual_profile
            and (
                expected_source_visual_profile
                != "tcp_congestion_control_v1"
                or expected_topology_mode == "feedback_loop"
            )
        )
    )
    feedback_contract = spec.story.get("feedback_contract")
    feedback_contract = (
        feedback_contract if isinstance(feedback_contract, dict) else {}
    )
    feedback_contract_passed = (
        expected_topology_mode != "feedback_loop"
        or (
            bool(feedback_contract.get("detected"))
            and feedback_contract_mode == "source_feedback_loop_v1"
            and feedback_evidence_stage_count >= 3
            and feedback_shared_state_token_count >= 1
            and isinstance(
                feedback_contract.get("return_from_stage_index"),
                int,
            )
            and isinstance(
                feedback_contract.get("return_to_stage_index"),
                int,
            )
            and int(feedback_contract["return_from_stage_index"])
            > int(feedback_contract["return_to_stage_index"])
        )
    )
    cycle_contract = spec.story.get("cycle_contract")
    cycle_contract = (
        cycle_contract if isinstance(cycle_contract, dict) else {}
    )
    cycle_contract_passed = (
        expected_topology_mode != "cycle_loop"
        or (
            bool(cycle_contract.get("detected"))
            and cycle_contract_mode == "source_cycle_loop_v1"
            and cycle_evidence_stage_count >= 4
            and cycle_shared_state_token_count >= 1
            and isinstance(
                cycle_contract.get("return_from_stage_index"),
                int,
            )
            and isinstance(
                cycle_contract.get("return_to_stage_index"),
                int,
            )
            and int(cycle_contract["return_from_stage_index"])
            > int(cycle_contract["return_to_stage_index"])
        )
    )
    requires_concise_stage_labels = story_kind == "causal_explainer"
    stage_label_contract_passed = (
        not requires_concise_stage_labels
        or (
            stage_label_count == len(spec.primitives)
            and stage_label_render_mode == "complete_scaled_two_line"
            and stage_label_ellipsis_count == 0
            and maximum_stage_label_words <= 8
            and minimum_stage_label_source_overlap >= 2
            and stage_label_method_count == len(spec.primitives)
        )
    )
    recap_mode = str(summary.get("recap_mode", ""))
    required_recap_mode = (
        "full_route_sweep"
        if story_kind == "causal_explainer"
        else "semantic_payoff_hold"
    )
    headline_replacements = int(
        summary.get("headline_replacement_count", 999)
    )
    transitions_per_minute = float(
        summary.get("caption_transitions_per_minute", 999.0)
    )
    median_dwell = float(
        summary.get("median_caption_dwell_seconds", 0.0)
    )
    rapid_ratio = float(summary.get("rapid_caption_ratio", 1.0))
    header = summary.get("encoded_header_persistence")
    header_transition_count = (
        int(header.get("transition_count", -1))
        if isinstance(header, dict)
        else -1
    )
    expected_header_transitions = max(0, len(spec.primitives) - 1)
    header_minimum = (
        float(header.get("minimum_retained_edge_ratio", 0.0))
        if isinstance(header, dict)
        else 0.0
    )
    header_median = (
        float(header.get("median_retained_edge_ratio", 0.0))
        if isinstance(header, dict)
        else 0.0
    )
    frames = render_metadata.get("frames")
    frame_items = frames if isinstance(frames, list) else []
    title_samples: List[Tuple[str, bool]] = []
    for frame in frame_items:
        if not isinstance(frame, dict):
            continue
        text_boxes = frame.get("text_boxes")
        if not isinstance(text_boxes, list) or not text_boxes:
            continue
        title_box = text_boxes[0]
        if not isinstance(title_box, dict):
            continue
        title_samples.append(
            (
                str(title_box.get("text", "")),
                bool(title_box.get("truncated", True)),
            )
        )
    matching_title_samples = sum(
        sampled_title == hook_title and not truncated
        for sampled_title, truncated in title_samples
    )
    is_editorial = story_kind == "technology_adolescence"
    editorial_contract_passed = (
        not is_editorial
        or (
            motion_language == "one_shot_reveal_only_v1"
            and chrome_mode == "minimal_title_only"
            and source_badge_mode == "hidden"
        )
    )
    maximum_transitions_per_minute = 42.0 if is_editorial else 32.0
    minimum_median_dwell = 1.05 if is_editorial else 1.7
    maximum_rapid_ratio = 0.15 if is_editorial else 0.1
    passed = (
        mode == "persistent_lesson_header_handwritten_captions"
        and hook_title_mode == "persistent_complete_hook"
        and bool(hook_title)
        and not hook_title_contains_ellipsis
        and hook_title_matches_plan_hook
        and bool(title_samples)
        and matching_title_samples == len(title_samples)
        and stage_label_contract_passed
        and topology_contract_passed
        and source_visual_profile_passed
        and editorial_contract_passed
        and feedback_contract_passed
        and cycle_contract_passed
        and recap_mode == required_recap_mode
        and headline_replacements == 0
        and transitions_per_minute <= maximum_transitions_per_minute
        and median_dwell >= minimum_median_dwell
        and rapid_ratio <= maximum_rapid_ratio
        and header_transition_count == expected_header_transitions
        and header_minimum >= HEADER_MINIMUM_RETENTION
        and header_median >= HEADER_MEDIAN_RETENTION
    )
    return [
        _check(
            "semantic_text_cadence",
            passed,
            (
                f"mode={mode}; headline_replacements={headline_replacements}; "
                f"hook_title_mode={hook_title_mode}; hook_title={hook_title!r}; "
                f"hook_title_contains_ellipsis={hook_title_contains_ellipsis}; "
                f"hook_title_matches_plan_hook={hook_title_matches_plan_hook}; "
                f"encoded_hook_title_samples={matching_title_samples}/"
                f"{len(title_samples)}; "
                f"stage_labels={stage_label_count}/{len(spec.primitives)}; "
                f"stage_label_render_mode={stage_label_render_mode}; "
                f"stage_label_ellipses={stage_label_ellipsis_count}; "
                f"maximum_stage_label_words={maximum_stage_label_words}; "
                f"minimum_stage_label_source_overlap="
                f"{minimum_stage_label_source_overlap}; "
                f"source_compressed_stage_labels={stage_label_method_count}/"
                f"{len(spec.primitives)}; "
                f"topology_mode={topology_mode}; "
                f"expected_topology_mode={expected_topology_mode}; "
                f"source_visual_profile={source_visual_profile}; "
                f"expected_source_visual_profile="
                f"{expected_source_visual_profile}; "
                f"motion_language={motion_language}; "
                f"chrome_mode={chrome_mode}; "
                f"source_badge_mode={source_badge_mode}; "
                f"feedback_contract_mode={feedback_contract_mode}; "
                f"feedback_evidence_stages={feedback_evidence_stage_count}; "
                f"feedback_shared_state_tokens="
                f"{feedback_shared_state_token_count}; "
                f"cycle_contract_mode={cycle_contract_mode}; "
                f"cycle_evidence_stages={cycle_evidence_stage_count}; "
                f"cycle_shared_state_tokens="
                f"{cycle_shared_state_token_count}; "
                f"recap_mode={recap_mode}; required_recap_mode={required_recap_mode}; "
                f"caption_transitions_per_minute={transitions_per_minute}; "
                f"median_caption_dwell_seconds={median_dwell}; "
                f"rapid_caption_ratio={rapid_ratio}; "
                f"encoded_header_transitions={header_transition_count}/"
                f"{expected_header_transitions}; "
                f"header_minimum_retention={header_minimum}; "
                f"header_median_retention={header_median}; "
                "required_replacements=0; required_transitions_per_minute<=32; "
                "required_median_dwell>=1.7; required_rapid_ratio<=0.1; "
                f"required_header_minimum>={HEADER_MINIMUM_RETENTION}; "
                f"required_header_median>={HEADER_MEDIAN_RETENTION}"
            ),
        )
    ]


def _route_recap_checks(
    spec: ManimSceneSpec,
    render_metadata: Dict[str, object],
) -> List[QACheck]:
    if (
        str(spec.story.get("kind", "")) != "causal_explainer"
        or render_metadata.get("renderer") != "manim"
    ):
        return []
    motion = render_metadata.get("motion")
    recap = (
        motion.get("route_recap")
        if isinstance(motion, dict)
        else None
    )
    if not isinstance(recap, dict):
        return [
            _check(
                "encoded_route_recap",
                False,
                "encoded route-recap metadata is missing",
            )
        ]
    recap_mode = str(spec.story.get("recap_mode", ""))
    top_frames = int(recap.get("top_active_frame_count", 0))
    bottom_frames = int(recap.get("bottom_active_frame_count", 0))
    traversal = float(recap.get("traversal_span_seconds", 0.0))
    first_top = recap.get("first_top_motion_seconds")
    last_bottom = recap.get("last_bottom_motion_seconds")
    chronology = (
        isinstance(first_top, (int, float))
        and isinstance(last_bottom, (int, float))
        and float(first_top) <= float(last_bottom)
    )
    passed = (
        recap_mode == "full_route_sweep"
        and bool(recap.get("passed"))
        and top_frames >= ROUTE_RECAP_MIN_TOP_ACTIVE_FRAMES
        and bottom_frames >= ROUTE_RECAP_MIN_BOTTOM_ACTIVE_FRAMES
        and traversal >= ROUTE_RECAP_MIN_TRAVERSAL_SECONDS
        and chronology
    )
    feedback_required = (
        str(spec.story.get("topology_mode", ""))
        in {"feedback_loop", "cycle_loop"}
    )
    feedback = recap.get("feedback_return")
    feedback_passed = not feedback_required
    feedback_bottom_frames = 0
    feedback_return_frames = 0
    feedback_loop_span = 0.0
    if feedback_required and isinstance(feedback, dict):
        feedback_bottom_frames = int(
            feedback.get("bottom_active_frame_count", 0)
        )
        feedback_return_frames = int(
            feedback.get("return_upper_left_active_frame_count", 0)
        )
        feedback_loop_span = float(
            feedback.get("loop_span_seconds", 0.0)
        )
        feedback_passed = (
            bool(feedback.get("passed"))
            and feedback_bottom_frames
            >= FEEDBACK_RETURN_MIN_BOTTOM_ACTIVE_FRAMES
            and feedback_return_frames
            >= FEEDBACK_RETURN_MIN_UPPER_LEFT_ACTIVE_FRAMES
            and feedback_loop_span >= FEEDBACK_RETURN_MIN_LOOP_SECONDS
        )
    passed = passed and feedback_passed
    return [
        _check(
            "encoded_route_recap",
            passed,
            (
                f"recap_mode={recap_mode}; top_active_frames={top_frames}; "
                f"bottom_active_frames={bottom_frames}; "
                f"first_top_motion_seconds={first_top}; "
                f"last_bottom_motion_seconds={last_bottom}; "
                f"traversal_span_seconds={traversal}; "
                f"feedback_required={feedback_required}; "
                f"feedback_bottom_active_frames={feedback_bottom_frames}; "
                f"feedback_return_upper_left_frames={feedback_return_frames}; "
                f"feedback_loop_span_seconds={feedback_loop_span}; "
                f"required_top_frames>={ROUTE_RECAP_MIN_TOP_ACTIVE_FRAMES}; "
                f"required_bottom_frames>={ROUTE_RECAP_MIN_BOTTOM_ACTIVE_FRAMES}; "
                f"required_traversal>={ROUTE_RECAP_MIN_TRAVERSAL_SECONDS}; "
                f"required_feedback_bottom_frames>="
                f"{FEEDBACK_RETURN_MIN_BOTTOM_ACTIVE_FRAMES}; "
                f"required_feedback_return_frames>="
                f"{FEEDBACK_RETURN_MIN_UPPER_LEFT_ACTIVE_FRAMES}; "
                f"required_feedback_loop_span>="
                f"{FEEDBACK_RETURN_MIN_LOOP_SECONDS}"
            ),
        )
    ]


def qa_video(
    job_dir: Path,
    plan: ContentPlan,
    spec: ManimSceneSpec,
    raster_metadata: Dict[str, object],
    manifest_path: Optional[Path],
    revision: str,
) -> QAReport:
    checks = _citation_checks(plan)
    frames_meta = raster_metadata.get("frames", [])
    frame_root = job_dir / str(raster_metadata.get("frame_root", "video/raster/frames"))
    paths = [frame_root / str(item["path"]) for item in frames_meta]
    checks.extend(_media_checks(paths, expected=(spec.width, spec.height)))
    checks.extend(_layout_checks(frames_meta))
    checks.extend(_mechanism_motion_checks(spec, raster_metadata))
    checks.extend(
        _motion_witness_checks(
            job_dir,
            plan,
            spec,
            raster_metadata,
        )
    )
    checks.extend(_semantic_emphasis_checks(spec, raster_metadata))
    checks.extend(
        _semantic_continuity_checks(
            plan,
            spec,
            raster_metadata,
        )
    )
    checks.extend(
        _semantic_text_transition_checks(
            spec,
            raster_metadata,
        )
    )
    checks.extend(_route_recap_checks(spec, raster_metadata))
    word_count = sum(len(beat.narration.split()) for beat in plan.beats)
    duration = sum(beat.duration_seconds for beat in plan.beats)
    is_short_guided_test = (
        str(spec.story.get("kind", "")) == "lecun_world_model_bet"
    )
    duration_minimum = 20.0 if is_short_guided_test else 25.0
    duration_maximum = 25.1 if is_short_guided_test else 60.0
    duration_target = (
        "20-25"
        if is_short_guided_test
        else "25-60"
    )
    caption_rate = word_count / max(duration, 0.1) * 60
    reference_copy = [
        beat.id
        for beat in plan.beats
        if re.search(r"https?://|^(?:primary\s+)?(?:references?|sources?)\s*:", beat.narration.strip(), re.I)
    ]
    long_hooks = [beat.id for beat in plan.beats[:1] if len(beat.headline.split()) > 12]
    long_headlines = [beat.id for beat in plan.beats if len(beat.headline.split()) > 8]
    long_screen_copy = [beat.id for beat in plan.beats if len(beat.on_screen_text.split()) > 8]
    purposes = [beat.purpose for beat in plan.beats]
    story_ok = bool(purposes) and purposes[0] == "hook" and (len(purposes) == 1 or purposes[-1] == "payoff")
    audio = raster_metadata.get("audio")
    if isinstance(audio, dict):
        aligned = int(audio.get("aligned_word_count", 0))
        scripted = int(audio.get("script_word_count", 0))
        checks.extend(
            [
                _check("voiceover_audio_stream", bool(audio.get("has_audio")), f"audio={audio}"),
                _check("voiceover_video_stream", bool(audio.get("has_video")), f"audio={audio}"),
                _check(
                    "voiceover_encoded_sample_rate",
                    int(audio.get("encoded_sample_rate") or 0) == 48_000,
                    f"encoded_sample_rate={audio.get('encoded_sample_rate')}; required=48000",
                ),
                _check(
                    "voiceover_encoded_channels",
                    audio.get("encoded_channel_layout") == "mono",
                    f"encoded_channel_layout={audio.get('encoded_channel_layout')}; required=mono",
                ),
                _check(
                    "voiceover_sync",
                    float(audio.get("sync_delta_seconds", 999.0)) <= 0.25,
                    f"sync_delta_seconds={audio.get('sync_delta_seconds')}",
                ),
                _check(
                    "voiceover_alignment",
                    scripted > 0 and aligned >= int(scripted * 0.95),
                    f"aligned_words={aligned}; script_words={scripted}",
                ),
                _check(
                    "voiceover_file",
                    (job_dir / str(audio.get("path", ""))).is_file(),
                    f"path={audio.get('path')}",
                ),
                _check(
                    "voiceover_loudness",
                    -20.0 <= float(audio.get("integrated_lufs", -999.0)) <= -12.0,
                    f"integrated_lufs={audio.get('integrated_lufs')}",
                ),
                _check(
                    "voiceover_true_peak",
                    float(audio.get("true_peak_dbfs", 999.0)) <= -1.0,
                    f"true_peak_dbfs={audio.get('true_peak_dbfs')}",
                ),
                _check(
                    "voiceover_dead_air",
                    float(audio.get("long_silence_ratio", 1.0)) <= 0.08,
                    f"long_silence_seconds={audio.get('long_silence_seconds')}; ratio={audio.get('long_silence_ratio')}",
                ),
            ]
        )
        checks.extend(_word_alignment_checks(audio))
    checks.extend(
        [
            _check(
                "duration",
                duration_minimum <= duration <= duration_maximum,
                (
                    f"duration_seconds={duration:.2f}; "
                    f"target={duration_target}"
                ),
            ),
            _check("caption_rate", 90 <= caption_rate <= 220, f"words_per_minute={caption_rate:.1f}"),
            _delivery_cadence_check(caption_rate),
            _check("reference_copy_filter", not reference_copy, f"reference_copy_beats={reference_copy}"),
            _check("video_hook_brevity", not long_hooks, f"over_12_words={long_hooks}"),
            _check("video_headline_brevity", not long_headlines, f"over_8_words={long_headlines}"),
            _check("video_screen_copy_brevity", not long_screen_copy, f"over_8_words={long_screen_copy}"),
            _check(
                "explanatory_progression",
                story_ok and len(set(purposes)) >= min(4, len(purposes)),
                f"purposes={purposes}",
            ),
            _check("video_file", (job_dir / "video" / "reel.mp4").stat().st_size > 1024 if (job_dir / "video" / "reel.mp4").exists() else False, "MP4 exists and is nontrivial"),
            _manifest_check(job_dir, manifest_path),
        ]
    )
    return QAReport.from_checks("video", checks, revision)


def qa_carousel(
    job_dir: Path,
    plan: ContentPlan,
    carousel_metadata: Dict[str, object],
    manifest_path: Optional[Path],
    revision: str,
) -> QAReport:
    checks = _citation_checks(plan)
    variants = carousel_metadata.get("variants", {})
    exact_counts: List[str] = []
    variant_metadata: List[Dict[str, object]] = []
    for target, variant in variants.items():
        metadata = read_json(job_dir / variant["metadata"])
        variant_metadata.append(metadata)
        profile = metadata["profile"]
        paths = [job_dir / path for path in variant["slides"]]
        if len(paths) != len(plan.slides):
            exact_counts.append(str(target))
        checks.extend(_media_checks(paths, expected=(int(profile["width"]), int(profile["height"]))))
        checks.extend(_layout_checks(metadata["slides"]))
    headline_overflow = [(slide.id, len(slide.headline.split())) for slide in plan.slides if len(slide.headline.split()) > 14]
    body_overflow = [(slide.id, len(slide.body.split())) for slide in plan.slides if len(slide.body.split()) > 26]
    idea_overflow = [slide.id for slide in plan.slides if len(slide.claim_ids) > 2 or len((slide.headline + " " + slide.body).split()) > 40]
    duplicate_copy = [slide.id for slide in plan.slides if slide.headline.strip().lower() == slide.body.strip().lower()]
    roles = [slide.role for slide in plan.slides]
    templates = {slide.visual for slide in plan.slides}
    progression_ok = bool(roles) and roles[0] == "hook" and (len(roles) == 1 or roles[-1] == "payoff")
    cta_ok = len(plan.slides) == 1 or any(token in plan.slides[-1].engagement_trigger.lower() for token in ("save", "share", "comment"))
    rendered_covers_ok = bool(variant_metadata) and all(len(metadata.get("cover_variants", [])) >= 3 for metadata in variant_metadata)
    swipe_cues_ok = bool(variant_metadata) and all(bool(metadata.get("slides", [{}])[0].get("swipe_cue")) for metadata in variant_metadata)
    palette_ok = bool(variant_metadata) and all(metadata.get("palette") == plan.visual_theme for metadata in variant_metadata)
    checks.extend(
        [
            _check("exact_count", not exact_counts and bool(variants), f"expected={len(plan.slides)}; wrong_variants={exact_counts}"),
            _check("hook_options", len(plan.hook_candidates) >= 12, f"hook_candidates={len(plan.hook_candidates)}"),
            _check("angle_options", len(plan.angle_candidates) >= 3, f"angle_candidates={len(plan.angle_candidates)}"),
            _check("hook_brevity", not headline_overflow, f"over_14_words={headline_overflow}"),
            _check("body_brevity", not body_overflow, f"over_26_words={body_overflow}"),
            _check("one_idea_per_slide", not idea_overflow, f"overloaded={idea_overflow}"),
            _check("non_redundant_copy", not duplicate_copy, f"duplicates={duplicate_copy}"),
            _check("swipe_narrative", progression_ok and len(set(roles)) >= min(3, len(roles)), f"roles={roles}"),
            _check("visual_variety", len(templates) >= min(3, len(plan.slides)), f"templates={sorted(templates)}"),
            _check("engagement_payoff", cta_ok, f"last_trigger={plan.slides[-1].engagement_trigger if plan.slides else None}"),
            _check("cover_tests", rendered_covers_ok, "three rendered cover candidates per target"),
            _check("swipe_cue", swipe_cues_ok, "cover includes a visible swipe cue"),
            _check("visual_theme", palette_ok, f"palette={plan.visual_theme}"),
            _manifest_check(job_dir, manifest_path),
        ]
    )
    return QAReport.from_checks("carousel", checks, revision)


def _trim(value: str, limit: int) -> str:
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    shortened = compact[: max(1, limit - 1)].rsplit(" ", 1)[0].rstrip(".,;:")
    return shortened + "…"


def _trim_words(value: str, limit: int) -> str:
    words = " ".join(value.split()).split()
    if len(words) <= limit:
        return " ".join(words)
    return " ".join(words[:limit]).rstrip(".,;:") + "…"


def revise_plan(plan: ContentPlan) -> ContentPlan:
    revised = copy.deepcopy(plan)
    revised.beats = [
        VideoBeat(
            id=beat.id,
            purpose=beat.purpose,
            headline=_trim(beat.headline, 150),
            narration=_trim(beat.narration, 220),
            on_screen_text=_trim(beat.on_screen_text, 220),
            claim_ids=list(beat.claim_ids),
            source_label=_trim(beat.source_label, 52),
            primitive=beat.primitive,
            duration_seconds=max(3.0, len(_trim(beat.narration, 220).split()) / 3.0),
        )
        for beat in plan.beats
    ]
    revised.slides = [
        SlideSpec(
            id=slide.id,
            role=slide.role,
            headline=_trim_words(slide.headline, 14),
            body=_trim_words(slide.body, 26),
            claim_ids=list(slide.claim_ids),
            source_label=_trim(slide.source_label, 52),
            visual=slide.visual,
            eyebrow=slide.eyebrow,
            accent_terms=list(slide.accent_terms),
            transition=slide.transition,
            engagement_trigger=slide.engagement_trigger,
        )
        for slide in plan.slides
    ]
    if revised.slides:
        revised.hook = revised.slides[0].headline
    return revised


def write_revision_artifacts(job_dir: Path, format_name: str, plan: ContentPlan, report: QAReport, revision: str) -> None:
    root = job_dir / "revision_history" / format_name
    write_json(root / f"plan.{revision}.json", plan)
    write_json(root / f"qa.{revision}.json", report)
