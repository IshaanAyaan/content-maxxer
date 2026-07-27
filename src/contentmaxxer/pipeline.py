"""End-to-end research, director, carousel, revision, and manifest workflows."""

import json
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from imageio_ffmpeg import get_ffmpeg_exe
from PIL import Image

from .audio import (
    mux_narration,
    retime_plan,
    synthesize_narration,
    write_aligned_srt,
    write_narration_track,
)
from .content_packs import (
    FABLE_COMPARISON_SNAPSHOTS,
    FABLE_COMPARISON_SOURCES,
    GPT56_PACKAGED_SNAPSHOTS,
    GPT56_SOURCES,
)
from .io import portable, read_json, slugify, write_json
from .manim_scene import (
    compile_manim_scene,
    manim_available,
    render_manim,
    write_manim_spec,
    write_scene_py,
)
from .models import BuildResult, Claim, ContentPlan, NarrationTrack, QAReport, SourceArtifact
from .planning import extract_claims, plan_slides, plan_video, write_citations, write_claim_map
from .qa import qa_carousel, qa_video, revise_plan, write_revision_artifacts
from .raster import (
    make_contact_sheet,
    render_carousel,
    render_raster_video,
    write_srt,
)
from .sources import SourceCache, SourceError, research_sources


class GroundingBlocked(RuntimeError):
    pass


class QAFailure(RuntimeError):
    pass


def job_path(output_dir: Path, job: Optional[str], topic: str) -> Path:
    return output_dir.expanduser().resolve() / (job or slugify(topic))


def research_job(
    topic: str,
    job_dir: Path,
    source_urls: Iterable[str] = (),
    source_files: Iterable[Path] = (),
    offline: bool = False,
    snapshot_date: Optional[str] = None,
) -> Tuple[List[SourceArtifact], List[Claim]]:
    job_dir.mkdir(parents=True, exist_ok=True)
    sources = research_sources(
        job_dir,
        source_urls=source_urls,
        source_files=source_files,
        offline=offline,
        snapshot_date=snapshot_date,
    )
    claims = extract_claims(topic, job_dir, sources)
    write_claim_map(job_dir, sources, claims)
    return sources, claims


def _manifest(job_dir: Path) -> Dict[str, object]:
    path = job_dir / "manifest.json"
    if path.exists():
        return read_json(path)
    return {"schema_version": "1.0", "job": job_dir.name, "status": "building"}


def _source_manifest(sources: Sequence[SourceArtifact]) -> List[Dict[str, object]]:
    return [
        {
            "id": source.id,
            "label": source.label,
            "origin": source.origin,
            "retrieved_at": source.retrieved_at,
            "digest": source.digest,
            "normalized": {"path": source.normalized_path},
            "snapshot": {"path": source.snapshot_path},
            "metadata": source.metadata_path,
        }
        for source in sources
    ]


def _write_manifest(
    job_dir: Path,
    topic: str,
    sources: Sequence[SourceArtifact],
    claims: Sequence[Claim],
    grounded: bool,
    status: str = "building",
    section: Optional[Tuple[str, Dict[str, object]]] = None,
) -> Path:
    manifest = _manifest(job_dir)
    manifest.update(
        {
            "schema_version": "1.0",
            "job": job_dir.name,
            "topic": topic,
            "status": status,
            "grounded": grounded,
            "planning_provider": "deterministic_claim_pack",
            "sources": _source_manifest(sources),
            "claims": [
                {
                    "id": claim.id,
                    "type": claim.claim_type.value,
                    "confidence": claim.confidence,
                    "source_id": claim.source_id,
                    "source_label": claim.source_label,
                    "source_url": claim.source_url,
                    "evidence_excerpt": claim.evidence_excerpt,
                }
                for claim in claims
            ],
            "citations": "citations.md",
        }
    )
    if section:
        manifest[section[0]] = section[1]
    path = job_dir / "manifest.json"
    write_json(path, manifest)
    return path


def _write_storyboard(job_dir: Path, plan: ContentPlan) -> Tuple[Path, Path]:
    lines = [f"# {plan.topic}", "", f"Visual thesis: {plan.visual_thesis}", "", "## Storyboard", ""]
    script = [f"# Script: {plan.topic}", ""]
    for beat in plan.beats:
        lines.extend(
            [
                f"### {beat.id} — {beat.purpose}",
                "",
                f"- Primitive: `{beat.primitive}`",
                f"- Duration: `{beat.duration_seconds:.2f}s`",
                f"- Claims: {', '.join(beat.claim_ids)}",
                f"- Source label: {beat.source_label}",
                "",
                beat.on_screen_text,
                "",
            ]
        )
        script.extend([f"## {beat.id}", "", beat.narration, ""])
    storyboard_path = job_dir / "video" / "storyboard.md"
    script_path = job_dir / "video" / "script.md"
    storyboard_path.parent.mkdir(parents=True, exist_ok=True)
    storyboard_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    script_path.write_text("\n".join(script).rstrip() + "\n", encoding="utf-8")
    return storyboard_path, script_path


def _video_section(
    job_dir: Path,
    plan: ContentPlan,
    selected_renderer: str,
    fallback_reason: Optional[str],
    metadata: Dict[str, object],
    narration: Optional[NarrationTrack],
) -> Dict[str, object]:
    section = {
        "renderer": "manim" if selected_renderer == "manim" else "raster_fallback",
        "polished_manim": selected_renderer == "manim",
        "fallback_reason": fallback_reason,
        "plan": "plans/video.json",
        "storyboard": {"path": "video/storyboard.md"},
        "script": {"path": "video/script.md"},
        "scene": "video/manim/scene.py",
        "spec": "video/manim/spec.json",
        "mp4": "video/reel.mp4",
        "srt": "video/captions.srt",
        "contact_sheet": "video/contact-sheet.png",
        "render_metadata": "video/raster/metadata.json" if selected_renderer == "raster" else "video/manim/render-metadata.json",
        "duration_seconds": narration.duration_seconds if narration else sum(beat.duration_seconds for beat in plan.beats),
        "dimensions": [1080, 1920],
        "scenes": [
            {
                "id": beat.id,
                "claim_ids": beat.claim_ids,
                "source_label": beat.source_label,
                "primitive": beat.primitive,
            }
            for beat in plan.beats
        ],
    }
    section["voiceover"] = (
        {
            "enabled": True,
            "provider": narration.provider,
            "voice": narration.voice,
            "audio": narration.audio_path,
            "timings": "video/narration/timings.json",
            "alignment_method": narration.alignment_method,
            "duration_seconds": narration.duration_seconds,
        }
        if narration
        else {"enabled": False}
    )
    return section


def _render_manim_with_packaging(job_dir: Path, plan: ContentPlan, spec: object, scene_path: Path) -> Dict[str, object]:
    output_path = job_dir / "video" / "reel.mp4"
    _, command = render_manim(scene_path, output_path)
    frames_dir = job_dir / "video" / "manim" / "preview-frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    sample_count = max(4, min(8, len(plan.beats) * 2))
    frames = []
    frame_metadata = []
    for index in range(sample_count):
        timestamp = max(0.05, spec.duration_seconds * (index + 0.5) / sample_count)
        cursor = 0.0
        sampled_beat = plan.beats[-1]
        for beat in plan.beats:
            cursor += beat.duration_seconds
            if timestamp <= cursor:
                sampled_beat = beat
                break
        frame = frames_dir / f"{index + 1:03d}.png"
        completed = subprocess.run(
            [
                get_ffmpeg_exe(),
                "-y",
                "-ss",
                f"{timestamp:.4f}",
                "-i",
                str(output_path),
                "-frames:v",
                "1",
                "-update",
                "1",
                str(frame),
            ],
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0 or not frame.is_file():
            detail = (completed.stderr or completed.stdout)[-1800:]
            raise RuntimeError(f"Manim preview extraction failed at {timestamp:.2f}s: {detail}")
        with Image.open(frame) as image:
            width, height = image.size
        frames.append(frame)
        frame_metadata.append(
            {
                "id": f"sample_{index + 1:02d}",
                "path": frame.name,
                "timestamp_seconds": round(timestamp, 4),
                "width": width,
                "height": height,
                "text_boxes": [
                    {
                        "box": [90, 190, width - 90, 410],
                        "font_size": 43,
                        "truncated": False,
                        "text": sampled_beat.headline,
                    },
                    {
                        "box": [108, 420, 516, 470],
                        "font_size": 18,
                        "truncated": False,
                        "text": sampled_beat.source_label,
                    },
                    {
                        "box": [90, 1440, width - 90, 1600],
                        "font_size": 35,
                        "truncated": False,
                        "text": sampled_beat.on_screen_text,
                    },
                ],
                "safe_zone": [90, 170, width - 90, height - 310],
            }
        )
    srt = write_srt(plan, job_dir / "video" / "captions.srt")
    contact = make_contact_sheet(frames, job_dir / "video" / "contact-sheet.png")
    payload = {
        "renderer": "manim",
        "width": spec.width,
        "height": spec.height,
        "fps": spec.fps,
        "duration_seconds": spec.duration_seconds,
        "frame_root": portable(frames_dir, job_dir),
        "frames": frame_metadata,
        "command": command,
        "outputs": {
            "mp4": portable(output_path, job_dir),
            "srt": portable(srt, job_dir),
            "contact_sheet": portable(contact, job_dir),
        },
    }
    write_json(job_dir / "video" / "manim" / "render-metadata.json", payload)
    return payload


def _package_narration(
    job_dir: Path,
    selected_renderer: str,
    metadata: Dict[str, object],
    narration: Optional[NarrationTrack],
) -> Dict[str, object]:
    if narration is None:
        return metadata
    timings = write_narration_track(job_dir, narration)
    captions = write_aligned_srt(narration, job_dir / "video" / "captions.srt")
    audio_metadata = mux_narration(job_dir, job_dir / "video" / "reel.mp4", narration)
    audio_metadata["cue_count"] = len(narration.cues)
    audio_metadata["script_word_count"] = sum(len(cue.text.split()) for cue in narration.cues)
    audio_metadata["aligned_word_count"] = sum(len(cue.words) for cue in narration.cues)
    metadata["audio"] = audio_metadata
    metadata["duration_seconds"] = narration.duration_seconds
    metadata["outputs"]["narration"] = portable(job_dir / narration.audio_path, job_dir)
    metadata["outputs"]["timings"] = portable(timings, job_dir)
    metadata["outputs"]["srt"] = portable(captions, job_dir)
    metadata_path = (
        job_dir / "video" / "manim" / "render-metadata.json"
        if selected_renderer == "manim"
        else job_dir / "video" / "raster" / "metadata.json"
    )
    write_json(metadata_path, metadata)
    return metadata


def _render_video(
    job_dir: Path,
    plan: ContentPlan,
    selected_renderer: str,
    narration: Optional[NarrationTrack] = None,
) -> Tuple[object, Dict[str, object]]:
    spec = compile_manim_scene(plan, narration=narration)
    write_manim_spec(job_dir, spec)
    scene_path = write_scene_py(job_dir, spec)
    _write_storyboard(job_dir, plan)
    if selected_renderer == "manim":
        metadata = _render_manim_with_packaging(job_dir, plan, spec, scene_path)
    else:
        metadata = render_raster_video(plan, spec, job_dir)
    metadata = _package_narration(job_dir, selected_renderer, metadata, narration)
    return spec, metadata


def _write_location_summary(job_dir: Path) -> Path:
    manifest = _manifest(job_dir)
    lines = [f"# Final file locations: {job_dir.name}", "", "All paths are relative to this job directory.", ""]
    lines.extend(["- Manifest: `manifest.json`", "- Claims: `claims.json`", "- Citations: `citations.md`"])
    if "video" in manifest:
        lines.extend(
            [
                "- Reel: `video/reel.mp4`",
                "- Captions: `video/captions.srt`",
                "- Narration: `video/narration/voiceover.wav`",
                "- Narration timing: `video/narration/timings.json`",
                "- Video contact sheet: `video/contact-sheet.png`",
                "- Manim scene: `video/manim/scene.py`",
                "- Manim spec: `video/manim/spec.json`",
                "- Video QA: `qa/video.json`",
            ]
        )
    if "carousel" in manifest:
        lines.append("- Carousel strategy and hook scoreboard: `carousel/strategy.md`")
        for target, variant in manifest["carousel"].get("variants", {}).items():
            lines.append(f"- Carousel {target}: `{variant['directory']}`")
            lines.append(f"- Carousel {target} cover tests: `{variant['directory']}/cover-variants`")
        lines.append("- Carousel QA: `qa/carousel.json`")
    path = job_dir / "final-file-locations.md"
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def _write_blocked(
    job_dir: Path,
    topic: str,
    plan: ContentPlan,
    sources: Sequence[SourceArtifact],
    claims: Sequence[Claim],
    format_name: str,
) -> None:
    plan_path = job_dir / "plans" / f"{format_name}.json"
    write_json(plan_path, plan)
    write_citations(job_dir, [plan])
    _write_manifest(
        job_dir,
        topic,
        sources,
        claims,
        grounded=False,
        status="blocked_ungrounded",
        section=(format_name, {"plan": portable(plan_path, job_dir), "blocked_reason": plan.blocked_reason}),
    )
    _write_location_summary(job_dir)


def run_director(
    topic: str,
    output_dir: Path,
    job: Optional[str] = None,
    source_urls: Iterable[str] = (),
    source_files: Iterable[Path] = (),
    offline: bool = False,
    hook_style: str = "direct",
    renderer: str = "auto",
    allow_ungrounded: bool = False,
    snapshot_date: Optional[str] = None,
    voice_provider: str = "auto",
    voice: str = "",
    voice_rate: int = 170,
    voice_instruction: str = "",
    qwen3_python: Optional[Path] = None,
    qwen3_model: str = "mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-4bit",
    voice_reference: Optional[Path] = None,
    narration_file: Optional[Path] = None,
) -> BuildResult:
    job_dir = job_path(output_dir, job, topic)
    sources, claims = research_job(topic, job_dir, source_urls, source_files, offline, snapshot_date)
    initial_plan = plan_video(topic, sources, claims, hook_style=hook_style, allow_ungrounded=allow_ungrounded)
    if not initial_plan.beats:
        _write_blocked(job_dir, topic, initial_plan, sources, claims, "video")
        raise GroundingBlocked(initial_plan.blocked_reason or "video plan is blocked")
    initial_narration = synthesize_narration(
        initial_plan,
        job_dir,
        provider=voice_provider,
        voice=voice,
        rate_wpm=voice_rate,
        voice_instruction=voice_instruction,
        qwen3_python=qwen3_python,
        qwen3_model=qwen3_model,
        voice_reference=voice_reference,
        narration_file=narration_file,
    )
    initial_plan = retime_plan(initial_plan, initial_narration)

    if renderer not in {"auto", "manim", "raster"}:
        raise ValueError(f"unknown renderer: {renderer}")
    available = manim_available()
    if renderer == "manim" and not available:
        spec = compile_manim_scene(initial_plan)
        write_manim_spec(job_dir, spec)
        write_scene_py(job_dir, spec)
        raise RuntimeError("Manim was explicitly requested but is unavailable. The scene and spec were generated; install Manim to render them.")
    selected = "manim" if renderer in {"auto", "manim"} and available else "raster"
    fallback_reason = None
    if selected == "raster":
        fallback_reason = "Manim is unavailable; auto selected the smoke-test raster fallback." if renderer == "auto" else "Raster fallback was explicitly selected."

    write_citations(job_dir, [initial_plan])
    plan_path = job_dir / "plans" / "video.json"
    write_json(plan_path, initial_plan)
    try:
        initial_spec, initial_metadata = _render_video(job_dir, initial_plan, selected, initial_narration)
    except RuntimeError as exc:
        if renderer == "auto" and selected == "manim":
            selected = "raster"
            fallback_reason = f"Manim render failed; auto used raster fallback: {exc}"
            initial_spec, initial_metadata = _render_video(job_dir, initial_plan, selected, initial_narration)
        else:
            raise
    manifest_path = _write_manifest(
        job_dir,
        topic,
        sources,
        claims,
        grounded=initial_plan.grounded,
        section=("video", _video_section(job_dir, initial_plan, selected, fallback_reason, initial_metadata, initial_narration)),
    )
    initial_report = qa_video(job_dir, initial_plan, initial_spec, initial_metadata, manifest_path, "initial")
    write_revision_artifacts(job_dir, "video", initial_plan, initial_report, "initial")

    revised_plan = revise_plan(initial_plan)
    narration_changed = [beat.narration for beat in revised_plan.beats] != [beat.narration for beat in initial_plan.beats]
    if narration_changed:
        revised_narration = synthesize_narration(
            revised_plan,
            job_dir,
            provider=voice_provider,
            voice=voice,
            rate_wpm=voice_rate,
            voice_instruction=voice_instruction,
            qwen3_python=qwen3_python,
            qwen3_model=qwen3_model,
            voice_reference=voice_reference,
            narration_file=narration_file,
        )
    else:
        revised_narration = initial_narration
    revised_plan = retime_plan(revised_plan, revised_narration)
    write_json(plan_path, revised_plan)
    write_citations(job_dir, [revised_plan])
    revised_spec, revised_metadata = _render_video(job_dir, revised_plan, selected, revised_narration)
    manifest_path = _write_manifest(
        job_dir,
        topic,
        sources,
        claims,
        grounded=revised_plan.grounded,
        section=("video", _video_section(job_dir, revised_plan, selected, fallback_reason, revised_metadata, revised_narration)),
    )
    revised_report = qa_video(job_dir, revised_plan, revised_spec, revised_metadata, manifest_path, "revised")
    write_revision_artifacts(job_dir, "video", revised_plan, revised_report, "revised")
    write_json(job_dir / "qa" / "video.json", revised_report)

    manifest = _manifest(job_dir)
    manifest["status"] = "complete" if revised_report.passed else "qa_failed"
    manifest["video"]["qa"] = "qa/video.json"
    manifest["video"]["revision_history"] = "revision_history/video"
    write_json(manifest_path, manifest)
    _write_location_summary(job_dir)
    if not revised_report.passed:
        failed = [check.name for check in revised_report.checks if check.hard and not check.passed]
        raise QAFailure("video failed QA after deterministic revision: " + ", ".join(failed))
    return BuildResult(str(job_dir), str(manifest_path), True, manifest["video"]["renderer"])


def _carousel_section(plan: ContentPlan, metadata: Dict[str, object]) -> Dict[str, object]:
    return {
        "plan": "plans/carousel.json",
        "strategy": {"path": "carousel/strategy.md"},
        "count": len(plan.slides),
        "visual_thesis": plan.visual_thesis,
        "visual_theme": plan.visual_theme,
        "narrative_pattern": plan.narrative_pattern,
        "engagement_goal": plan.engagement_goal,
        "selected_hook": plan.hook,
        "hook_candidates": plan.hook_candidates,
        "angle_candidates": plan.angle_candidates,
        "publishing_notes": plan.publishing_notes,
        "hero_asset": metadata.get("hero_asset"),
        "variants": metadata["variants"],
        "slides": [
            {
                "id": slide.id,
                "role": slide.role,
                "claim_ids": slide.claim_ids,
                "source_label": slide.source_label,
                "visual": slide.visual,
                "transition": slide.transition,
                "engagement_trigger": slide.engagement_trigger,
            }
            for slide in plan.slides
        ],
    }


def _write_carousel_strategy(job_dir: Path, plan: ContentPlan) -> Path:
    lines = [
        f"# Carousel strategy: {plan.topic}",
        "",
        f"- Narrative: `{plan.narrative_pattern}`",
        f"- Visual theme: `{plan.visual_theme}`",
        f"- Engagement goal: {plan.engagement_goal}",
        f"- Selected hook: **{plan.hook}**",
        "",
        "## Hook scoreboard",
        "",
        "| Hook | Style | Score |",
        "| --- | --- | ---: |",
    ]
    for candidate in sorted(plan.hook_candidates, key=lambda item: item["score"], reverse=True):
        lines.append(f"| {candidate['text']} | {candidate['style']} | {candidate['score']} |")
    lines.extend(["", "## Swipe narrative", ""])
    for slide in plan.slides:
        lines.append(f"- **{slide.id} · {slide.role}:** {slide.headline} — `{slide.transition}` / {slide.engagement_trigger}")
    lines.extend(["", "## Publishing and testing", ""])
    lines.extend(f"- {note}" for note in plan.publishing_notes)
    path = job_dir / "carousel" / "strategy.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def run_slides(
    topic: str,
    output_dir: Path,
    job: Optional[str] = None,
    source_urls: Iterable[str] = (),
    source_files: Iterable[Path] = (),
    offline: bool = False,
    hook_style: str = "direct",
    count: int = 8,
    targets: Iterable[str] = ("9:16", "4:5"),
    allow_ungrounded: bool = False,
    snapshot_date: Optional[str] = None,
    visual_theme: str = "editorial_heat_v1",
) -> BuildResult:
    job_dir = job_path(output_dir, job, topic)
    sources, claims = research_job(topic, job_dir, source_urls, source_files, offline, snapshot_date)
    initial_plan = plan_slides(
        topic,
        sources,
        claims,
        count,
        hook_style=hook_style,
        allow_ungrounded=allow_ungrounded,
        visual_theme=visual_theme,
    )
    if not initial_plan.slides:
        _write_blocked(job_dir, topic, initial_plan, sources, claims, "carousel")
        raise GroundingBlocked(initial_plan.blocked_reason or "carousel plan is blocked")

    plan_path = job_dir / "plans" / "carousel.json"
    write_json(plan_path, initial_plan)
    write_citations(job_dir, [initial_plan])
    _write_carousel_strategy(job_dir, initial_plan)
    initial_metadata = render_carousel(initial_plan, job_dir, targets)
    manifest_path = _write_manifest(
        job_dir,
        topic,
        sources,
        claims,
        grounded=initial_plan.grounded,
        section=("carousel", _carousel_section(initial_plan, initial_metadata)),
    )
    initial_report = qa_carousel(job_dir, initial_plan, initial_metadata, manifest_path, "initial")
    write_revision_artifacts(job_dir, "carousel", initial_plan, initial_report, "initial")

    revised_plan = revise_plan(initial_plan)
    write_json(plan_path, revised_plan)
    write_citations(job_dir, [revised_plan])
    _write_carousel_strategy(job_dir, revised_plan)
    revised_metadata = render_carousel(revised_plan, job_dir, targets)
    manifest_path = _write_manifest(
        job_dir,
        topic,
        sources,
        claims,
        grounded=revised_plan.grounded,
        section=("carousel", _carousel_section(revised_plan, revised_metadata)),
    )
    revised_report = qa_carousel(job_dir, revised_plan, revised_metadata, manifest_path, "revised")
    write_revision_artifacts(job_dir, "carousel", revised_plan, revised_report, "revised")
    write_json(job_dir / "qa" / "carousel.json", revised_report)
    manifest = _manifest(job_dir)
    existing_video_failed = "video" in manifest and manifest.get("status") == "qa_failed"
    manifest["status"] = "qa_failed" if existing_video_failed or not revised_report.passed else "complete"
    manifest["carousel"]["qa"] = "qa/carousel.json"
    manifest["carousel"]["revision_history"] = "revision_history/carousel"
    write_json(manifest_path, manifest)
    _write_location_summary(job_dir)
    if not revised_report.passed:
        failed = [check.name for check in revised_report.checks if check.hard and not check.passed]
        raise QAFailure("carousel failed QA after deterministic revision: " + ", ".join(failed))
    return BuildResult(str(job_dir), str(manifest_path), True)


def _seed_gpt56_snapshots(job_dir: Path) -> None:
    cache = SourceCache(job_dir, snapshot_date="2026-07-09")
    labels = {
        "https://openai.com/index/gpt-5-6/": "OpenAI GPT-5.6 launch",
        "https://developers.openai.com/api/docs/models": "OpenAI model documentation",
        "https://deploymentsafety.openai.com/gpt-5-6": "OpenAI GPT-5.6 System Card",
    }
    artifacts = [cache.cache_text(url, labels[url], GPT56_PACKAGED_SNAPSHOTS[url]) for url in GPT56_SOURCES]
    cache.write_index(artifacts)


def build_gpt56_set(output_dir: Path, renderer: str = "auto", count: int = 7) -> List[BuildResult]:
    jobs = [
        ("gpt_5_6_family_tiers", "GPT-5.6 family tiers", "direct"),
        ("gpt_5_6_capability_controls", "GPT-5.6 capability controls", "statistic"),
    ]
    results: List[BuildResult] = []
    for job, topic, hook_style in jobs:
        target_dir = job_path(output_dir, job, topic)
        try:
            results.append(
                run_director(
                    topic,
                    output_dir,
                    job=job,
                    source_urls=GPT56_SOURCES,
                    hook_style=hook_style,
                    renderer=renderer,
                    snapshot_date="2026-07-09",
                )
            )
        except SourceError:
            _seed_gpt56_snapshots(target_dir)
            results.append(
                run_director(
                    topic,
                    output_dir,
                    job=job,
                    offline=True,
                    hook_style=hook_style,
                    renderer=renderer,
                    snapshot_date="2026-07-09",
                )
            )
        results.append(
            run_slides(
                topic,
                output_dir,
                job=job,
                offline=True,
                hook_style=hook_style,
                count=count,
                targets=("9:16", "3:4", "4:5"),
                snapshot_date="2026-07-09",
            )
        )
    return results


def _seed_fable_comparison_snapshots(job_dir: Path) -> None:
    cache = SourceCache(job_dir, snapshot_date="2026-07-10")
    labels = {
        FABLE_COMPARISON_SOURCES[0]: "OpenAI GPT-5.6 model guide",
        FABLE_COMPARISON_SOURCES[1]: "Anthropic Claude Fable 5",
        FABLE_COMPARISON_SOURCES[2]: "Anthropic Fable 5 platform documentation",
    }
    artifacts = [
        cache.cache_text(url, labels[url], FABLE_COMPARISON_SNAPSHOTS[url])
        for url in FABLE_COMPARISON_SOURCES
    ]
    cache.write_index(artifacts)


def build_five_post_set(output_dir: Path, count: int = 7) -> List[BuildResult]:
    """Build the requested five-post creative test across both visual systems."""
    jobs = [
        ("gpt_5_6_family_tiers_paper", "GPT-5.6 family tiers", "direct", "paper_meme_v1", "gpt"),
        ("fable_5_vs_gpt_5_6_editorial", "Fable 5 vs GPT-5.6", "direct", "editorial_heat_v1", "comparison"),
        ("fable_5_vs_gpt_5_6_paper", "Fable 5 vs GPT-5.6", "direct", "paper_meme_v1", "comparison"),
        ("fable_5_vs_gpt_5_6_cost_editorial", "Fable 5 vs GPT-5.6 cost economics", "statistic", "editorial_heat_v1", "comparison"),
        ("fable_5_vs_gpt_5_6_cost_paper", "Fable 5 vs GPT-5.6 cost economics", "statistic", "paper_meme_v1", "comparison"),
    ]
    results: List[BuildResult] = []
    for job, topic, hook_style, visual_theme, pack in jobs:
        target_dir = job_path(output_dir, job, topic)
        if pack == "gpt":
            _seed_gpt56_snapshots(target_dir)
        else:
            _seed_fable_comparison_snapshots(target_dir)
        results.append(
            run_slides(
                topic,
                output_dir,
                job=job,
                offline=True,
                hook_style=hook_style,
                count=count,
                targets=("9:16", "3:4", "4:5"),
                snapshot_date="2026-07-10",
                visual_theme=visual_theme,
            )
        )
    return results
