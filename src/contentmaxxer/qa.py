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


def _check(name: str, passed: bool, detail: str) -> QACheck:
    return QACheck(name=name, passed=bool(passed), detail=detail, hard=True)


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
        }:
            paths.append(value)

    visit(manifest)
    absolute = [value for value in paths if Path(value).is_absolute()]
    missing = [value for value in paths if not Path(value).is_absolute() and not (job_dir / value).exists()]
    valid = manifest.get("schema_version") == "1.0" and not absolute and not missing
    return _check("manifest_integrity", valid, f"absolute={absolute}; missing={missing}")


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
    word_count = sum(len(beat.narration.split()) for beat in plan.beats)
    duration = sum(beat.duration_seconds for beat in plan.beats)
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
    checks.extend(
        [
            _check("duration", 25.0 <= duration <= 60.0, f"duration_seconds={duration:.2f}; target=25-60"),
            _check("caption_rate", 90 <= caption_rate <= 220, f"words_per_minute={caption_rate:.1f}"),
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
