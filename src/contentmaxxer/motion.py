"""Repeatable upper-diagram motion measurements for rendered reels."""

import re
import statistics
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from imageio_ffmpeg import get_ffmpeg_exe
from PIL import Image, ImageChops, ImageFilter


MOTION_SAMPLE_FPS = 5
MOTION_SIGNAL_THRESHOLD = 0.3
MOTION_STYLE_THRESHOLDS = {
    "warm_papyrus": 0.18,
}
MOTION_CROP_RATIO = 1350 / 1920
MOTION_WITNESSES_PER_SEGMENT = 3
MOTION_WITNESS_MIN_SEPARATION_SECONDS = 0.8
CONTINUITY_ANALYSIS_WIDTH = 240
CONTINUITY_CROP = (60 / 1080, 380 / 1920, 960 / 1080, 950 / 1920)
CONTINUITY_EDGE_THRESHOLD = 10
CONTINUITY_MIN_EDGE_PIXELS = 60
CONTINUITY_RESET_THRESHOLD = 0.35
CONTINUITY_MIN_AVERAGE_RETENTION = 0.60
CONTINUITY_MIN_MEDIAN_RETENTION = 0.65
HEADER_ANALYSIS_WIDTH = 240
HEADER_CROP = (60 / 1080, 145 / 1920, 960 / 1080, 195 / 1920)
HEADER_MINIMUM_RETENTION = 0.92
HEADER_MEDIAN_RETENTION = 0.95
ROUTE_RECAP_ANALYSIS_WIDTH = 240
ROUTE_RECAP_CROP = (60 / 1080, 380 / 1920, 900 / 1080, 1060 / 1920)
ROUTE_RECAP_SAMPLE_FPS = 10
ROUTE_RECAP_WINDOW_SECONDS = 1.05
ROUTE_RECAP_PIXEL_DELTA_THRESHOLD = 15
ROUTE_RECAP_MIN_CHANGED_PIXELS = 50
ROUTE_RECAP_MIN_TOP_ACTIVE_FRAMES = 2
ROUTE_RECAP_MIN_BOTTOM_ACTIVE_FRAMES = 1
ROUTE_RECAP_MIN_TRAVERSAL_SECONDS = 0.2
FEEDBACK_RETURN_MIN_BOTTOM_ACTIVE_FRAMES = 1
FEEDBACK_RETURN_MIN_UPPER_LEFT_ACTIVE_FRAMES = 2
FEEDBACK_RETURN_MIN_LOOP_SECONDS = 0.2


def motion_threshold_for_style(animation_style: str) -> float:
    return MOTION_STYLE_THRESHOLDS.get(animation_style, MOTION_SIGNAL_THRESHOLD)


def summarize_motion(
    signal_values: Sequence[float],
    sample_fps: int = MOTION_SAMPLE_FPS,
    threshold: float = MOTION_SIGNAL_THRESHOLD,
) -> Dict[str, object]:
    if not signal_values:
        raise RuntimeError("motion analysis produced no frame-difference samples")
    moving = [value >= threshold for value in signal_values]
    longest_static = 0
    longest_static_start = 0
    current_static = 0
    current_static_start = 0
    for index, is_moving in enumerate(moving):
        if is_moving:
            current_static = 0
            continue
        if current_static == 0:
            current_static_start = index
        current_static += 1
        if current_static > longest_static:
            longest_static = current_static
            longest_static_start = current_static_start
    ordered = sorted(float(value) for value in signal_values)
    median = ordered[len(ordered) // 2]
    p90 = ordered[round((len(ordered) - 1) * 0.9)]
    longest_static_seconds = longest_static / sample_fps
    return {
        "sample_fps": sample_fps,
        "signal_threshold": threshold,
        "sample_count": len(signal_values),
        "motion_coverage_ratio": round(sum(moving) / len(moving), 4),
        "motion_coverage_percent": round(sum(moving) / len(moving) * 100.0, 1),
        "longest_static_seconds": round(longest_static_seconds, 2),
        "longest_static_span": {
            "start_seconds": round(longest_static_start / sample_fps, 4),
            "end_seconds": round(
                longest_static_start / sample_fps + longest_static_seconds,
                4,
            ),
            "duration_seconds": round(longest_static_seconds, 2),
        },
        "median_signal": round(median, 4),
        "p90_signal": round(p90, 4),
    }


def select_motion_witnesses(
    signal_values: Sequence[float],
    segments: Sequence[Tuple[str, float, float]],
    *,
    sample_fps: int = MOTION_SAMPLE_FPS,
    per_segment: int = MOTION_WITNESSES_PER_SEGMENT,
    min_separation_seconds: float = MOTION_WITNESS_MIN_SEPARATION_SECONDS,
    motion_threshold: float = MOTION_SIGNAL_THRESHOLD,
) -> List[Dict[str, object]]:
    """Choose several interior motion moments per story segment for visual review."""
    if per_segment <= 0:
        return []
    samples = [
        {
            "sample_index": index,
            "peak_timestamp_seconds": (index + 1) / sample_fps,
            "signal": float(value),
        }
        for index, value in enumerate(signal_values)
    ]
    witnesses: List[Dict[str, object]] = []
    lead_seconds = 2.5 / sample_fps
    for segment_id, raw_start, raw_end in segments:
        start = float(raw_start)
        end = float(raw_end)
        duration = max(0.0, end - start)
        margin = min(0.75, max(0.2, duration * 0.08))
        candidates = [
            sample
            for sample in samples
            if start + margin
            <= float(sample["peak_timestamp_seconds"])
            <= end - margin
        ]
        if not candidates:
            candidates = [
                sample
                for sample in samples
                if start <= float(sample["peak_timestamp_seconds"]) <= end
            ]
        ranked = sorted(
            candidates,
            key=lambda item: (
                -float(item["signal"]),
                float(item["peak_timestamp_seconds"]),
            ),
        )
        selected: List[Dict[str, object]] = []
        if ranked:
            selected.append({**ranked[0], "selection_reason": "strongest_motion"})
        witness_floor = max(0.05, motion_threshold * 0.5)
        subthreshold = sorted(
            (
                candidate
                for candidate in candidates
                if witness_floor
                <= float(candidate["signal"])
                < motion_threshold
            ),
            key=lambda item: int(item["sample_index"]),
        )
        subtle_runs: List[List[Dict[str, object]]] = []
        for candidate in subthreshold:
            if (
                not subtle_runs
                or int(candidate["sample_index"])
                != int(subtle_runs[-1][-1]["sample_index"]) + 1
            ):
                subtle_runs.append([candidate])
            else:
                subtle_runs[-1].append(candidate)
        subtle_runs.sort(
            key=lambda run: (
                -len(run),
                -max(float(item["signal"]) for item in run),
                int(run[0]["sample_index"]),
            )
        )
        if len(selected) < per_segment:
            for run in subtle_runs:
                candidate = run[len(run) // 2]
                peak = float(candidate["peak_timestamp_seconds"])
                if all(
                    abs(peak - float(existing["peak_timestamp_seconds"]))
                    >= min_separation_seconds
                    for existing in selected
                ):
                    selected.append(
                        {
                            **candidate,
                            "selection_reason": "subtle_motion",
                        }
                    )
                    break
        if len(selected) < min(2, per_segment):
            subtle_ranked = sorted(
                (
                    candidate
                    for candidate in candidates
                    if float(candidate["signal"]) >= motion_threshold
                ),
                key=lambda item: (
                    float(item["signal"]),
                    float(item["peak_timestamp_seconds"]),
                ),
            )
            for candidate in subtle_ranked:
                peak = float(candidate["peak_timestamp_seconds"])
                if all(
                    abs(peak - float(existing["peak_timestamp_seconds"]))
                    >= min_separation_seconds
                    for existing in selected
                ):
                    selected.append(
                        {
                            **candidate,
                            "selection_reason": "subtle_motion",
                        }
                    )
                    break
        for candidate in ranked:
            if any(
                int(candidate["sample_index"]) == int(existing["sample_index"])
                for existing in selected
            ):
                continue
            peak = float(candidate["peak_timestamp_seconds"])
            if all(
                abs(peak - float(existing["peak_timestamp_seconds"]))
                >= min_separation_seconds
                for existing in selected
            ):
                selected.append(
                    {
                        **candidate,
                        "selection_reason": "distributed_peak",
                    }
                )
            if len(selected) == per_segment:
                break
        if len(selected) < per_segment:
            for candidate in ranked:
                if any(
                    int(candidate["sample_index"])
                    == int(existing["sample_index"])
                    for existing in selected
                ):
                    continue
                selected.append(
                    {
                        **candidate,
                        "selection_reason": "coverage_fill",
                    }
                )
                if len(selected) == per_segment:
                    break
        for index, sample in enumerate(
            sorted(selected, key=lambda item: float(item["peak_timestamp_seconds"])),
            start=1,
        ):
            peak = float(sample["peak_timestamp_seconds"])
            capture_time = (
                peak
                if sample["selection_reason"] == "subtle_motion"
                else peak - lead_seconds
            )
            timestamp = max(start + 0.05, min(end - 0.05, capture_time))
            witnesses.append(
                {
                    "id": f"{segment_id}_motion_{index:02d}",
                    "segment_id": segment_id,
                    "timestamp_seconds": round(timestamp, 4),
                    "peak_timestamp_seconds": round(peak, 4),
                    "signal": round(float(sample["signal"]), 4),
                    "selection_reason": sample["selection_reason"],
                }
            )
    return witnesses


def _edge_mask(
    frame: Image.Image,
    *,
    threshold: int = CONTINUITY_EDGE_THRESHOLD,
) -> Image.Image:
    """Return a binary one-pixel gradient mask without wraparound edges."""
    gray = frame.convert("L")
    width, height = gray.size
    left = Image.new("L", gray.size)
    left.paste(gray.crop((0, 0, width - 1, height)), (1, 0))
    left.paste(gray.crop((0, 0, 1, height)), (0, 0))
    above = Image.new("L", gray.size)
    above.paste(gray.crop((0, 0, width, height - 1)), (0, 1))
    above.paste(gray.crop((0, 0, width, 1)), (0, 0))
    gradient = ImageChops.lighter(
        ImageChops.difference(gray, left),
        ImageChops.difference(gray, above),
    )
    return gradient.point(lambda value: 255 if value > threshold else 0)


def _mask_pixel_count(mask: Image.Image) -> int:
    return sum(mask.histogram()[1:])


def summarize_semantic_continuity(
    transitions: Sequence[Dict[str, object]],
    *,
    reset_threshold: float = CONTINUITY_RESET_THRESHOLD,
) -> Dict[str, object]:
    ratios = [
        float(item["retained_edge_ratio"])
        for item in transitions
        if int(item.get("previous_dynamic_edge_pixels", 0))
        >= CONTINUITY_MIN_EDGE_PIXELS
    ]
    reset_count = sum(value < reset_threshold for value in ratios)
    if ratios:
        average = statistics.fmean(ratios)
        median = statistics.median(ratios)
        minimum = min(ratios)
    else:
        average = median = minimum = 0.0
    return {
        "eligible_transition_count": len(transitions),
        "valid_transition_count": len(ratios),
        "insufficient_edge_transition_count": len(transitions) - len(ratios),
        "average_retained_edge_ratio": round(average, 4),
        "median_retained_edge_ratio": round(median, 4),
        "minimum_retained_edge_ratio": round(minimum, 4),
        "reset_threshold": reset_threshold,
        "reset_transition_count": reset_count,
        "transitions": list(transitions),
    }


def measure_semantic_continuity_frames(
    frames: Sequence[Image.Image],
    segments: Sequence[Tuple[str, float, float]],
    *,
    sample_fps: int = MOTION_SAMPLE_FPS,
) -> Dict[str, object]:
    """Measure retained non-template diagram ink between settled body beats.

    The hook-to-diagram transition is intentionally excluded. Pixels that are
    edges in every sampled beat are treated as template/background structure.
    """
    if not frames:
        raise RuntimeError("semantic continuity analysis produced no frames")
    sampled: List[Tuple[str, float, Image.Image]] = []
    for segment_id, raw_start, raw_end in segments:
        timestamp = (float(raw_start) + float(raw_end)) / 2
        frame_index = min(
            len(frames) - 1,
            max(0, round(timestamp * sample_fps)),
        )
        sampled.append(
            (
                segment_id,
                timestamp,
                _edge_mask(frames[frame_index]),
            )
        )
    if not sampled:
        result = summarize_semantic_continuity([])
        result["sampled_beat_count"] = 0
        return result

    persistent = sampled[0][2]
    for _, _, mask in sampled[1:]:
        persistent = ImageChops.multiply(persistent, mask)
    persistent = persistent.filter(ImageFilter.MaxFilter(3))
    non_persistent = ImageChops.invert(persistent)

    transitions: List[Dict[str, object]] = []
    # Beat 1 is the hook. Compare only the settled diagrams for beats 2 onward.
    for previous, current in zip(sampled[1:-1], sampled[2:]):
        previous_mask = ImageChops.multiply(previous[2], non_persistent)
        current_mask = ImageChops.multiply(current[2], non_persistent)
        previous_pixels = _mask_pixel_count(previous_mask)
        current_pixels = _mask_pixel_count(current_mask)
        retained = ImageChops.multiply(
            previous_mask,
            current_mask.filter(ImageFilter.MaxFilter(5)),
        )
        retained_pixels = _mask_pixel_count(retained)
        ratio = retained_pixels / max(1, previous_pixels)
        transitions.append(
            {
                "from_segment_id": previous[0],
                "to_segment_id": current[0],
                "from_timestamp_seconds": round(previous[1], 4),
                "to_timestamp_seconds": round(current[1], 4),
                "previous_dynamic_edge_pixels": previous_pixels,
                "current_dynamic_edge_pixels": current_pixels,
                "retained_edge_pixels": retained_pixels,
                "retained_edge_ratio": round(ratio, 4),
            }
        )
    result = summarize_semantic_continuity(transitions)
    result["sampled_beat_count"] = len(sampled)
    result["sampling"] = "settled_midpoint_body_beats_excluding_hook_transition"
    result["template_mask"] = "edge_intersection_across_all_sampled_beats_dilated_1px"
    result["edge_match_radius_pixels"] = 2
    result["edge_threshold"] = CONTINUITY_EDGE_THRESHOLD
    result["minimum_dynamic_edge_pixels"] = CONTINUITY_MIN_EDGE_PIXELS
    return result


def analyze_semantic_continuity(
    video_path: Path,
    width: int,
    height: int,
    segments: Sequence[Tuple[str, float, float]],
    *,
    sample_fps: int = MOTION_SAMPLE_FPS,
) -> Dict[str, object]:
    crop_x = max(0, int(width * CONTINUITY_CROP[0]) // 2 * 2)
    crop_y = max(0, int(height * CONTINUITY_CROP[1]) // 2 * 2)
    crop_width = max(2, int(width * CONTINUITY_CROP[2]) // 2 * 2)
    crop_height = max(2, int(height * CONTINUITY_CROP[3]) // 2 * 2)
    crop_width = min(crop_width, width - crop_x)
    crop_height = min(crop_height, height - crop_y)
    analysis_height = max(
        2,
        round(
            crop_height * CONTINUITY_ANALYSIS_WIDTH / crop_width / 2
        )
        * 2,
    )
    video_filter = (
        f"crop={crop_width}:{crop_height}:{crop_x}:{crop_y},"
        f"scale={CONTINUITY_ANALYSIS_WIDTH}:{analysis_height},"
        f"fps={sample_fps},format=gray"
    )
    completed = subprocess.run(
        [
            get_ffmpeg_exe(),
            "-v",
            "error",
            "-i",
            str(video_path),
            "-vf",
            video_filter,
            "-f",
            "rawvideo",
            "-pix_fmt",
            "gray",
            "-",
        ],
        capture_output=True,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout)[-1800:].decode(
            "utf-8",
            errors="replace",
        )
        raise RuntimeError(f"semantic continuity analysis failed: {detail}")
    frame_size = CONTINUITY_ANALYSIS_WIDTH * analysis_height
    if not frame_size or len(completed.stdout) < frame_size:
        raise RuntimeError("semantic continuity analysis produced no raw frames")
    frames = [
        Image.frombytes(
            "L",
            (CONTINUITY_ANALYSIS_WIDTH, analysis_height),
            completed.stdout[offset : offset + frame_size],
        )
        for offset in range(
            0,
            len(completed.stdout) - frame_size + 1,
            frame_size,
        )
    ]
    result = measure_semantic_continuity_frames(
        frames,
        segments,
        sample_fps=sample_fps,
    )
    result["crop"] = [crop_x, crop_y, crop_width, crop_height]
    result["analysis_dimensions"] = [
        CONTINUITY_ANALYSIS_WIDTH,
        analysis_height,
    ]
    result["sample_fps"] = sample_fps
    result["method"] = "encoded_dynamic_edge_retention_v1"
    return result


def measure_header_persistence_frames(
    frames: Sequence[Image.Image],
    segments: Sequence[Tuple[str, float, float]],
    *,
    sample_fps: int = MOTION_SAMPLE_FPS,
) -> Dict[str, object]:
    if not frames:
        raise RuntimeError("header persistence analysis produced no frames")
    sampled: List[Tuple[str, float, Image.Image]] = []
    for segment_id, raw_start, raw_end in segments:
        timestamp = (float(raw_start) + float(raw_end)) / 2
        frame_index = min(
            len(frames) - 1,
            max(0, round(timestamp * sample_fps)),
        )
        sampled.append(
            (
                segment_id,
                timestamp,
                _edge_mask(frames[frame_index]),
            )
        )
    transitions: List[Dict[str, object]] = []
    for previous, current in zip(sampled[:-1], sampled[1:]):
        previous_pixels = _mask_pixel_count(previous[2])
        current_pixels = _mask_pixel_count(current[2])
        retained_previous = _mask_pixel_count(
            ImageChops.multiply(
                previous[2],
                current[2].filter(ImageFilter.MaxFilter(3)),
            )
        ) / max(1, previous_pixels)
        retained_current = _mask_pixel_count(
            ImageChops.multiply(
                current[2],
                previous[2].filter(ImageFilter.MaxFilter(3)),
            )
        ) / max(1, current_pixels)
        ratio = min(retained_previous, retained_current)
        transitions.append(
            {
                "from_segment_id": previous[0],
                "to_segment_id": current[0],
                "from_timestamp_seconds": round(previous[1], 4),
                "to_timestamp_seconds": round(current[1], 4),
                "retained_edge_ratio": round(ratio, 4),
            }
        )
    ratios = [
        float(item["retained_edge_ratio"])
        for item in transitions
    ]
    return {
        "transition_count": len(transitions),
        "average_retained_edge_ratio": round(
            statistics.fmean(ratios) if ratios else 0.0,
            4,
        ),
        "median_retained_edge_ratio": round(
            statistics.median(ratios) if ratios else 0.0,
            4,
        ),
        "minimum_retained_edge_ratio": round(
            min(ratios) if ratios else 0.0,
            4,
        ),
        "edge_match_radius_pixels": 1,
        "edge_threshold": CONTINUITY_EDGE_THRESHOLD,
        "sampling": "settled_midpoint_all_beats",
        "transitions": transitions,
    }


def analyze_header_persistence(
    video_path: Path,
    width: int,
    height: int,
    segments: Sequence[Tuple[str, float, float]],
    *,
    sample_fps: int = MOTION_SAMPLE_FPS,
) -> Dict[str, object]:
    crop_x = max(0, int(width * HEADER_CROP[0]) // 2 * 2)
    crop_y = max(0, int(height * HEADER_CROP[1]) // 2 * 2)
    crop_width = max(2, int(width * HEADER_CROP[2]) // 2 * 2)
    crop_height = max(2, int(height * HEADER_CROP[3]) // 2 * 2)
    crop_width = min(crop_width, width - crop_x)
    crop_height = min(crop_height, height - crop_y)
    analysis_height = max(
        2,
        round(crop_height * HEADER_ANALYSIS_WIDTH / crop_width / 2) * 2,
    )
    video_filter = (
        f"crop={crop_width}:{crop_height}:{crop_x}:{crop_y},"
        f"scale={HEADER_ANALYSIS_WIDTH}:{analysis_height},"
        f"fps={sample_fps},format=gray"
    )
    completed = subprocess.run(
        [
            get_ffmpeg_exe(),
            "-v",
            "error",
            "-i",
            str(video_path),
            "-vf",
            video_filter,
            "-f",
            "rawvideo",
            "-pix_fmt",
            "gray",
            "-",
        ],
        capture_output=True,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout)[-1800:].decode(
            "utf-8",
            errors="replace",
        )
        raise RuntimeError(f"header persistence analysis failed: {detail}")
    frame_size = HEADER_ANALYSIS_WIDTH * analysis_height
    if not frame_size or len(completed.stdout) < frame_size:
        raise RuntimeError("header persistence analysis produced no raw frames")
    frames = [
        Image.frombytes(
            "L",
            (HEADER_ANALYSIS_WIDTH, analysis_height),
            completed.stdout[offset : offset + frame_size],
        )
        for offset in range(
            0,
            len(completed.stdout) - frame_size + 1,
            frame_size,
        )
    ]
    result = measure_header_persistence_frames(
        frames,
        segments,
        sample_fps=sample_fps,
    )
    result["crop"] = [crop_x, crop_y, crop_width, crop_height]
    result["analysis_dimensions"] = [HEADER_ANALYSIS_WIDTH, analysis_height]
    result["sample_fps"] = sample_fps
    result["method"] = "encoded_header_edge_persistence_v1"
    return result


def measure_route_recap_frames(
    frames: Sequence[Image.Image],
    recap_end_seconds: float,
    *,
    sample_fps: int = ROUTE_RECAP_SAMPLE_FPS,
    window_seconds: float = ROUTE_RECAP_WINDOW_SECONDS,
    pixel_delta_threshold: int = ROUTE_RECAP_PIXEL_DELTA_THRESHOLD,
    minimum_changed_pixels: int = ROUTE_RECAP_MIN_CHANGED_PIXELS,
) -> Dict[str, object]:
    if len(frames) < 2:
        raise RuntimeError("route recap analysis produced too few frames")
    start_seconds = max(0.0, float(recap_end_seconds) - window_seconds)
    start_index = min(
        len(frames) - 2,
        max(0, int(start_seconds * sample_fps)),
    )
    end_index = min(
        len(frames) - 1,
        max(start_index + 1, round(float(recap_end_seconds) * sample_fps)),
    )
    samples: List[Dict[str, object]] = []
    for index in range(start_index + 1, end_index + 1):
        previous = frames[index - 1].convert("L")
        current = frames[index].convert("L")
        difference = ImageChops.difference(previous, current).point(
            lambda value: 255 if value >= pixel_delta_threshold else 0
        )
        width, height = difference.size
        midpoint = height // 2
        top_pixels = _mask_pixel_count(
            difference.crop((0, 0, width, midpoint))
        )
        bottom_pixels = _mask_pixel_count(
            difference.crop((0, midpoint, width, height))
        )
        samples.append(
            {
                "timestamp_seconds": round(index / sample_fps, 4),
                "top_changed_pixels": top_pixels,
                "bottom_changed_pixels": bottom_pixels,
            }
        )
    top_active = [
        item
        for item in samples
        if int(item["top_changed_pixels"]) >= minimum_changed_pixels
    ]
    bottom_active = [
        item
        for item in samples
        if int(item["bottom_changed_pixels"]) >= minimum_changed_pixels
    ]
    first_top = (
        float(top_active[0]["timestamp_seconds"])
        if top_active
        else None
    )
    last_bottom = (
        float(bottom_active[-1]["timestamp_seconds"])
        if bottom_active
        else None
    )
    traversal_seconds = (
        max(0.0, last_bottom - first_top)
        if first_top is not None and last_bottom is not None
        else 0.0
    )
    passed = (
        len(top_active) >= ROUTE_RECAP_MIN_TOP_ACTIVE_FRAMES
        and len(bottom_active) >= ROUTE_RECAP_MIN_BOTTOM_ACTIVE_FRAMES
        and first_top is not None
        and last_bottom is not None
        and first_top <= last_bottom
        and traversal_seconds >= ROUTE_RECAP_MIN_TRAVERSAL_SECONDS
    )
    return {
        "passed": passed,
        "window_start_seconds": round(start_seconds, 4),
        "window_end_seconds": round(float(recap_end_seconds), 4),
        "top_active_frame_count": len(top_active),
        "bottom_active_frame_count": len(bottom_active),
        "first_top_motion_seconds": first_top,
        "last_bottom_motion_seconds": last_bottom,
        "traversal_span_seconds": round(traversal_seconds, 4),
        "pixel_delta_threshold": pixel_delta_threshold,
        "minimum_changed_pixels": minimum_changed_pixels,
        "samples": samples,
    }


def measure_feedback_return_frames(
    frames: Sequence[Image.Image],
    recap_end_seconds: float,
    *,
    sample_fps: int = ROUTE_RECAP_SAMPLE_FPS,
    window_seconds: float = ROUTE_RECAP_WINDOW_SECONDS,
    pixel_delta_threshold: int = ROUTE_RECAP_PIXEL_DELTA_THRESHOLD,
    minimum_changed_pixels: int = ROUTE_RECAP_MIN_CHANGED_PIXELS,
) -> Dict[str, object]:
    """Prove that encoded motion returns from the lower payoff to the upper-left probe."""
    if len(frames) < 2:
        raise RuntimeError("feedback return analysis produced too few frames")
    start_seconds = max(0.0, float(recap_end_seconds) - window_seconds)
    start_index = min(
        len(frames) - 2,
        max(0, int(start_seconds * sample_fps)),
    )
    end_index = min(
        len(frames) - 1,
        max(start_index + 1, round(float(recap_end_seconds) * sample_fps)),
    )
    samples: List[Dict[str, object]] = []
    for index in range(start_index + 1, end_index + 1):
        previous = frames[index - 1].convert("L")
        current = frames[index].convert("L")
        difference = ImageChops.difference(previous, current).point(
            lambda value: 255 if value >= pixel_delta_threshold else 0
        )
        width, height = difference.size
        bottom_top = round(height * 0.56)
        upper_left_right = round(width * 0.32)
        upper_left_bottom = round(height * 0.56)
        bottom_pixels = _mask_pixel_count(
            difference.crop((0, bottom_top, width, height))
        )
        upper_left_pixels = _mask_pixel_count(
            difference.crop((0, 0, upper_left_right, upper_left_bottom))
        )
        samples.append(
            {
                "timestamp_seconds": round(index / sample_fps, 4),
                "bottom_changed_pixels": bottom_pixels,
                "upper_left_changed_pixels": upper_left_pixels,
            }
        )
    bottom_active = [
        item
        for item in samples
        if int(item["bottom_changed_pixels"]) >= minimum_changed_pixels
    ]
    first_bottom = (
        float(bottom_active[0]["timestamp_seconds"])
        if bottom_active
        else None
    )
    returning_upper_left = [
        item
        for item in samples
        if first_bottom is not None
        and float(item["timestamp_seconds"]) > first_bottom
        and int(item["upper_left_changed_pixels"]) >= minimum_changed_pixels
    ]
    last_return = (
        float(returning_upper_left[-1]["timestamp_seconds"])
        if returning_upper_left
        else None
    )
    loop_span = (
        max(0.0, last_return - first_bottom)
        if first_bottom is not None and last_return is not None
        else 0.0
    )
    passed = (
        len(bottom_active) >= FEEDBACK_RETURN_MIN_BOTTOM_ACTIVE_FRAMES
        and len(returning_upper_left)
        >= FEEDBACK_RETURN_MIN_UPPER_LEFT_ACTIVE_FRAMES
        and loop_span >= FEEDBACK_RETURN_MIN_LOOP_SECONDS
    )
    return {
        "passed": passed,
        "window_start_seconds": round(start_seconds, 4),
        "window_end_seconds": round(float(recap_end_seconds), 4),
        "bottom_active_frame_count": len(bottom_active),
        "return_upper_left_active_frame_count": len(returning_upper_left),
        "first_bottom_motion_seconds": first_bottom,
        "last_return_motion_seconds": last_return,
        "loop_span_seconds": round(loop_span, 4),
        "pixel_delta_threshold": pixel_delta_threshold,
        "minimum_changed_pixels": minimum_changed_pixels,
        "samples": samples,
    }


def analyze_route_recap(
    video_path: Path,
    width: int,
    height: int,
    recap_end_seconds: float,
    *,
    sample_fps: int = ROUTE_RECAP_SAMPLE_FPS,
    window_seconds: float = ROUTE_RECAP_WINDOW_SECONDS,
    analyze_feedback: bool = False,
) -> Dict[str, object]:
    crop_x = max(0, int(width * ROUTE_RECAP_CROP[0]) // 2 * 2)
    crop_y = max(0, int(height * ROUTE_RECAP_CROP[1]) // 2 * 2)
    crop_width = max(2, int(width * ROUTE_RECAP_CROP[2]) // 2 * 2)
    crop_height = max(2, int(height * ROUTE_RECAP_CROP[3]) // 2 * 2)
    crop_width = min(crop_width, width - crop_x)
    crop_height = min(crop_height, height - crop_y)
    analysis_height = max(
        2,
        round(
            crop_height * ROUTE_RECAP_ANALYSIS_WIDTH / crop_width / 2
        )
        * 2,
    )
    video_filter = (
        f"crop={crop_width}:{crop_height}:{crop_x}:{crop_y},"
        f"scale={ROUTE_RECAP_ANALYSIS_WIDTH}:{analysis_height},"
        f"fps={sample_fps},format=gray"
    )
    completed = subprocess.run(
        [
            get_ffmpeg_exe(),
            "-v",
            "error",
            "-i",
            str(video_path),
            "-vf",
            video_filter,
            "-f",
            "rawvideo",
            "-pix_fmt",
            "gray",
            "-",
        ],
        capture_output=True,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout)[-1800:].decode(
            "utf-8",
            errors="replace",
        )
        raise RuntimeError(f"route recap analysis failed: {detail}")
    frame_size = ROUTE_RECAP_ANALYSIS_WIDTH * analysis_height
    frames = [
        Image.frombytes(
            "L",
            (ROUTE_RECAP_ANALYSIS_WIDTH, analysis_height),
            completed.stdout[offset : offset + frame_size],
        )
        for offset in range(
            0,
            len(completed.stdout) - frame_size + 1,
            frame_size,
        )
    ]
    result = measure_route_recap_frames(
        frames,
        recap_end_seconds,
        sample_fps=sample_fps,
        window_seconds=window_seconds,
    )
    result["crop"] = [crop_x, crop_y, crop_width, crop_height]
    result["analysis_dimensions"] = [
        ROUTE_RECAP_ANALYSIS_WIDTH,
        analysis_height,
    ]
    result["sample_fps"] = sample_fps
    result["method"] = "encoded_top_to_bottom_route_motion_v1"
    if analyze_feedback:
        feedback = measure_feedback_return_frames(
            frames,
            recap_end_seconds,
            sample_fps=sample_fps,
            window_seconds=window_seconds,
        )
        feedback["crop"] = [crop_x, crop_y, crop_width, crop_height]
        feedback["analysis_dimensions"] = [
            ROUTE_RECAP_ANALYSIS_WIDTH,
            analysis_height,
        ]
        feedback["sample_fps"] = sample_fps
        feedback["method"] = "encoded_bottom_to_upper_left_feedback_motion_v1"
        result["feedback_return"] = feedback
    return result


def analyze_visual_motion(
    video_path: Path,
    width: int,
    height: int,
    sample_fps: int = MOTION_SAMPLE_FPS,
    threshold: float = MOTION_SIGNAL_THRESHOLD,
    witness_segments: Optional[Sequence[Tuple[str, float, float]]] = None,
    analyze_continuity: bool = False,
    analyze_recap: bool = False,
    analyze_feedback: bool = False,
    recap_window_seconds: float = ROUTE_RECAP_WINDOW_SECONDS,
) -> Dict[str, object]:
    crop_height = max(2, int(height * MOTION_CROP_RATIO) // 2 * 2)
    analysis_width = 270
    analysis_height = max(2, round(crop_height * analysis_width / width / 2) * 2)
    video_filter = (
        f"crop={width}:{crop_height}:0:0,"
        f"scale={analysis_width}:{analysis_height},"
        f"fps={sample_fps},"
        "tblend=all_mode=difference,"
        "signalstats,"
        "metadata=print:key=lavfi.signalstats.YAVG:file=-"
    )
    completed = subprocess.run(
        [
            get_ffmpeg_exe(),
            "-v",
            "error",
            "-i",
            str(video_path),
            "-vf",
            video_filter,
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout)[-1800:]
        raise RuntimeError(f"motion analysis failed: {detail}")
    signal_values = [
        float(value)
        for value in re.findall(
            r"lavfi\.signalstats\.YAVG=([0-9.]+)",
            completed.stdout + completed.stderr,
        )
    ]
    result = summarize_motion(signal_values, sample_fps=sample_fps, threshold=threshold)
    result["crop"] = [0, 0, width, crop_height]
    result["analysis_dimensions"] = [analysis_width, analysis_height]
    result["method"] = "ffmpeg_tblend_signalstats_v1"
    witnesses = select_motion_witnesses(
        signal_values,
        witness_segments or (),
        sample_fps=sample_fps,
        motion_threshold=threshold,
    )
    static_span = result["longest_static_span"]
    static_timestamp = (
        float(static_span["start_seconds"])
        + float(static_span["end_seconds"])
    ) / 2
    static_index = min(
        len(signal_values) - 1,
        max(0, round(static_timestamp * sample_fps) - 1),
    )
    witnesses.append(
        {
            "id": "longest_static_midpoint",
            "segment_id": "longest_static",
            "timestamp_seconds": round(static_timestamp, 4),
            "peak_timestamp_seconds": round(static_timestamp, 4),
            "signal": round(float(signal_values[static_index]), 4),
            "selection_reason": "longest_static_midpoint",
        }
    )
    result["witnesses"] = witnesses
    result["witness_selection_method"] = (
        "strongest_plus_subtle_interior_motion_per_story_segment_with_static_midpoint_v2"
    )
    if analyze_continuity:
        semantic_continuity = analyze_semantic_continuity(
            video_path,
            width,
            height,
            witness_segments or (),
            sample_fps=sample_fps,
        )
        semantic_continuity["header_persistence"] = (
            analyze_header_persistence(
                video_path,
                width,
                height,
                witness_segments or (),
                sample_fps=sample_fps,
            )
        )
        result["semantic_continuity"] = semantic_continuity
    if analyze_recap and witness_segments:
        result["route_recap"] = analyze_route_recap(
            video_path,
            width,
            height,
            float(witness_segments[-1][2]),
            window_seconds=recap_window_seconds,
            analyze_feedback=analyze_feedback,
        )
    return result
