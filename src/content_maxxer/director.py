from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from content_maxxer.backend import (
    ASPECTS,
    BACKGROUND,
    BLUE,
    GREEN,
    MUTED,
    PINK,
    QUALITY_SCALE,
    TEAL,
    TEXT,
    YELLOW,
    Beat,
    contact_sheet,
    draw_centered_text,
    draw_text_box,
    load_fonts,
    render_size,
    slugify,
    write_srt,
)


@dataclass
class DirectorScene:
    scene_id: str
    viewer_question: str
    visual_object: str
    motion: str
    meaning: str
    visible_text: list[str]
    caption: str
    duration: float
    visual_kind: str


@dataclass
class DirectorPlan:
    title: str
    slug: str
    source: str
    format: str
    duration: float
    visual_thesis: str
    central_object: str
    primary_transformation: str
    scenes: list[DirectorScene]


def build_director_plan(
    *,
    title: str,
    idea: str,
    slug: str | None = None,
    source: str = "",
    video_format: str = "vertical",
    duration: float = 30.0,
) -> DirectorPlan:
    slug = slug or slugify(title)
    key = f"{title} {idea}".lower()
    if "nexus" in key:
        return nexus_plan(title, idea, slug, source, video_format, duration)
    if "gradient" in key or "descent" in key:
        return gradient_descent_plan(title, idea, slug, source, video_format, duration)
    return generic_plan(title, idea, slug, source, video_format, duration)


def scene_durations(total: float, count: int) -> list[float]:
    total = max(total, count * 4.0)
    base = total / count
    return [round(base, 2) for _ in range(count)]


def gradient_descent_plan(
    title: str,
    idea: str,
    slug: str,
    source: str,
    video_format: str,
    duration: float,
) -> DirectorPlan:
    durations = scene_durations(duration, 5)
    scenes = [
        DirectorScene(
            "too_big_step",
            "Why can a model fail even when it knows the downhill direction?",
            "one dot on a loss curve",
            "The dot jumps across the bottom when the step is too large.",
            "Direction is not enough; step size controls whether learning behaves.",
            ["too large", "misses"],
            "A downhill step can still miss the bottom.",
            durations[0],
            "gradient",
        ),
        DirectorScene(
            "read_slope",
            "What does the gradient actually tell us?",
            "tangent arrow on the same curve",
            "A tangent appears at the current dot and points downhill.",
            "The gradient is a local measurement, not a map of the whole valley.",
            ["slope", "direction"],
            "The gradient reads the slope right here.",
            durations[1],
            "gradient",
        ),
        DirectorScene(
            "small_step",
            "What makes the movement useful?",
            "the same dot and a shorter arrow",
            "The dot takes one small controlled step.",
            "Learning improves when movement is measured.",
            ["small step"],
            "A small step turns direction into progress.",
            durations[2],
            "gradient",
        ),
        DirectorScene(
            "repeat_settle",
            "Why does repetition matter?",
            "a trail of dots converging to the minimum",
            "Each new dot lands closer to the bottom.",
            "The algorithm works by repeating one local correction.",
            ["repeat", "settle"],
            "Repeat the correction and the dot settles.",
            durations[3],
            "gradient",
        ),
        DirectorScene(
            "gradient_takeaway",
            "What should the viewer remember?",
            "the same curve with a simple loop",
            "Measure, step, and repeat labels orbit the minimum.",
            "Gradient descent is measured movement, not magic.",
            ["measure", "step", "repeat"],
            "Learning is measured movement repeated.",
            durations[4],
            "gradient",
        ),
    ]
    return DirectorPlan(
        title=title,
        slug=slug,
        source=source or "Concept prompt",
        format=video_format,
        duration=sum(scene.duration for scene in scenes),
        visual_thesis="A model learns by repeatedly measuring local slope and taking small controlled downhill steps.",
        central_object="A dot moving on a single loss curve.",
        primary_transformation="Wild oversized movement becomes small repeated movement that settles near the minimum.",
        scenes=scenes,
    )


def nexus_plan(
    title: str,
    idea: str,
    slug: str,
    source: str,
    video_format: str,
    duration: float,
) -> DirectorPlan:
    durations = scene_durations(duration, 5)
    scenes = [
        DirectorScene(
            "same_score_different_basin",
            "How can two models tie on loss and behave differently downstream?",
            "two dots on one contour landscape",
            "Two colored paths descend to equal score lines but different basins.",
            "The score hides where optimization landed.",
            ["same loss", "different basin"],
            "Two models can tie on loss and land in different basins.",
            durations[0],
            "nexus",
        ),
        DirectorScene(
            "downstream_valley",
            "Why does the landing place matter?",
            "the same landscape plus a downstream target valley",
            "One basin sits near the downstream valley while the other is far away.",
            "Downstream tasks care about closeness, not just the pretraining score.",
            ["downstream valley", "closer"],
            "Downstream tasks care which valley you are near.",
            durations[1],
            "nexus",
        ),
        DirectorScene(
            "task_agreement",
            "What is Nexus trying to encourage?",
            "task direction arrows from the same model point",
            "Task arrows rotate from conflict into agreement.",
            "Nexus wants task directions to pull the model toward compatible regions.",
            ["conflict", "agreement"],
            "Nexus asks whether task directions agree.",
            durations[2],
            "nexus",
        ),
        DirectorScene(
            "inner_steps_to_ghat",
            "How does the method estimate that agreement?",
            "a model block, clone, mini-batches, and displacement arrow",
            "The model clones, steps on batches, and turns the displacement into g_hat.",
            "Temporary inner motion becomes the training signal.",
            ["clone", "batch steps", "g_hat"],
            "Clone, step on batches, then measure the displacement.",
            durations[3],
            "nexus",
        ),
        DirectorScene(
            "nexus_takeaway",
            "What should the viewer remember?",
            "the same route through the landscape",
            "The route glows while the scorecard fades back.",
            "The path through training is the object Nexus changes.",
            ["route", "not just score"],
            "Nexus changes the route, not just the score.",
            durations[4],
            "nexus",
        ),
    ]
    return DirectorPlan(
        title=title,
        slug=slug,
        source=source or "https://arxiv.org/pdf/2604.09258",
        format=video_format,
        duration=sum(scene.duration for scene in scenes),
        visual_thesis="Nexus treats pretraining as a path through a landscape, not just a final loss number.",
        central_object="Two optimization paths moving across the same loss landscape.",
        primary_transformation="Equal final score becomes visibly different landing geometry, then task agreement reshapes the route.",
        scenes=scenes,
    )


def generic_plan(
    title: str,
    idea: str,
    slug: str,
    source: str,
    video_format: str,
    duration: float,
) -> DirectorPlan:
    durations = scene_durations(duration, 4)
    scenes = [
        DirectorScene(
            "concrete_tension",
            "What concrete tension makes this worth watching?",
            "one object under pressure",
            "A simple object is pulled in two directions.",
            "The concept becomes concrete when the viewer sees the tension.",
            ["tension", "choice"],
            f"{title} is easier to understand when one object has to choose.",
            durations[0],
            "generic",
        ),
        DirectorScene(
            "mechanism",
            "What changes what?",
            "three connected nodes",
            "Signal moves through the nodes in order.",
            "The important part is the causal chain.",
            ["cause", "effect"],
            "The mechanism is the chain of changes.",
            durations[1],
            "generic",
        ),
        DirectorScene(
            "comparison",
            "What changes after the idea is applied?",
            "before and after states of the same object",
            "One state transforms into a cleaner state.",
            "The idea earns its keep by changing the outcome.",
            ["before", "after"],
            "The same object behaves differently after the idea.",
            durations[2],
            "generic",
        ),
        DirectorScene(
            "takeaway",
            "What should the viewer keep?",
            "the final object with one short label",
            "The object settles into its final form.",
            "The viewer leaves with one visual memory.",
            ["one visual memory"],
            f"Remember {title} as a transformation, not a definition.",
            durations[3],
            "generic",
        ),
    ]
    return DirectorPlan(
        title=title,
        slug=slug,
        source=source or "Concept prompt",
        format=video_format,
        duration=sum(scene.duration for scene in scenes),
        visual_thesis=f"{title} should be explained as one visible transformation, not as a definition.",
        central_object="A single object changing under pressure.",
        primary_transformation="A vague concept becomes a concrete before-and-after motion.",
        scenes=scenes,
    )


def write_director_files(job_dir: Path, plan: DirectorPlan, idea: str) -> None:
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "visual_thesis.md").write_text(visual_thesis_markdown(plan, idea), encoding="utf-8")
    (job_dir / "scene_graph.json").write_text(plan_json(plan), encoding="utf-8")
    (job_dir / "script.md").write_text(script_markdown(plan), encoding="utf-8")
    (job_dir / "storyboard.md").write_text(storyboard_markdown(plan), encoding="utf-8")


def visual_thesis_markdown(plan: DirectorPlan, idea: str) -> str:
    return "\n".join(
        [
            f"# Visual Thesis: {plan.title}",
            "",
            "## Input",
            "",
            idea.strip(),
            "",
            "## Thesis",
            "",
            plan.visual_thesis,
            "",
            "## Central object",
            "",
            plan.central_object,
            "",
            "## Primary transformation",
            "",
            plan.primary_transformation,
            "",
        ]
    )


def script_markdown(plan: DirectorPlan) -> str:
    lines = [f"# Script: {plan.title}", ""]
    for scene in plan.scenes:
        lines.extend([f"## {scene.scene_id}", "", scene.caption, ""])
    return "\n".join(lines)


def storyboard_markdown(plan: DirectorPlan) -> str:
    lines = [
        f"# Storyboard: {plan.title}",
        "",
        "| Scene | Duration | Visual object | Motion | Meaning | Visible text |",
        "| --- | ---: | --- | --- | --- | --- |",
    ]
    for scene in plan.scenes:
        visible = ", ".join(scene.visible_text).replace("|", "/")
        lines.append(
            f"| {scene.scene_id} | {scene.duration:.1f}s | {scene.visual_object} | {scene.motion} | {scene.meaning} | {visible} |"
        )
    lines.append("")
    return "\n".join(lines)


def plan_json(plan: DirectorPlan) -> str:
    return json.dumps(asdict(plan), indent=2) + "\n"


def render_director_video(job_dir: Path, plan: DirectorPlan, *, quality: str, fps: int = 24) -> Path:
    try:
        import imageio.v2 as imageio
        import numpy as np
    except ImportError as error:
        raise SystemExit(
            "Missing render dependencies. Install with: pip install pillow imageio imageio-ffmpeg numpy"
        ) from error

    width, height = render_size(plan.format, quality)
    exports_dir = job_dir / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    output = exports_dir / f"{plan.slug}_director_{plan.format}_{quality}.mp4"
    srt_path = exports_dir / f"{plan.slug}_director_{plan.format}_{quality}.srt"
    manifest_path = exports_dir / f"{plan.slug}_director_{plan.format}_{quality}.json"
    beats = [Beat(scene.scene_id, scene.caption, scene.visual_kind, scene.duration) for scene in plan.scenes]
    write_srt(beats, srt_path)
    manifest_path.write_text(
        json.dumps(
            {
                **asdict(plan),
                "renderer": "director_renderer_v1",
                "beats": [asdict(beat) for beat in beats],
                "output": str(output),
                "srt": str(srt_path),
                "width": width,
                "height": height,
                "fps": fps,
                "quality": quality,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    writer = imageio.get_writer(
        str(output),
        fps=fps,
        codec="libx264",
        quality=9,
        macro_block_size=1,
        ffmpeg_params=["-movflags", "+faststart"],
    )
    try:
        total_frames = max(1, int(plan.duration * fps))
        frame_index = 0
        for scene_index, scene in enumerate(plan.scenes):
            scene_frames = max(1, int(scene.duration * fps))
            for local_frame in range(scene_frames):
                progress = ease(local_frame / max(1, scene_frames - 1))
                global_progress = frame_index / max(1, total_frames - 1)
                frame = draw_director_frame(width, height, plan, scene, scene_index, progress, global_progress)
                writer.append_data(np.asarray(frame, dtype=np.uint8))
                frame_index += 1
    finally:
        writer.close()

    contact_sheet(output, exports_dir / f"{plan.slug}_director_{plan.format}_{quality}_contact.png")
    return output


def ease(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def draw_director_frame(
    width: int,
    height: int,
    plan: DirectorPlan,
    scene: DirectorScene,
    scene_index: int,
    progress: float,
    global_progress: float,
) -> Any:
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (width, height), BACKGROUND)
    draw = ImageDraw.Draw(image)
    draw_director_background(draw, width, height, scene_index)
    fonts = load_fonts(width)
    margin = int(width * 0.07)
    draw_progress(draw, width, height, margin, global_progress)
    draw_text_box(draw, plan.title, (margin, int(height * 0.035)), fonts["eyebrow"], MUTED, width - 2 * margin, 4)
    box = (margin, int(height * 0.12), width - margin, int(height * 0.72))
    if scene.visual_kind == "gradient":
        draw_gradient_scene(draw, box, scene, progress, fonts)
    elif scene.visual_kind == "nexus":
        draw_nexus_scene(draw, box, scene, progress, fonts)
    else:
        draw_generic_scene(draw, box, scene, progress, fonts)
    draw_scene_caption(draw, width, height, scene.caption, fonts)
    return image


def draw_director_background(draw: Any, width: int, height: int, scene_index: int) -> None:
    accent = [BLUE, TEAL, YELLOW, GREEN, PINK][scene_index % 5]
    for y in range(height):
        mix = y / max(1, height - 1)
        fill = (
            int(BACKGROUND[0] + accent[0] * 0.035 * mix),
            int(BACKGROUND[1] + accent[1] * 0.035 * mix),
            int(BACKGROUND[2] + accent[2] * 0.035 * mix),
        )
        draw.line((0, y, width, y), fill=fill)
    grid = (20, 29, 44)
    spacing = max(36, width // 12)
    for x in range(0, width, spacing):
        draw.line((x, 0, x, height), fill=grid, width=1)
    for y in range(0, height, spacing):
        draw.line((0, y, width, y), fill=grid, width=1)


def draw_progress(draw: Any, width: int, height: int, margin: int, progress: float) -> None:
    y = height - int(height * 0.032)
    draw.rounded_rectangle((margin, y, width - margin, y + 5), radius=3, fill=(27, 39, 58))
    draw.rounded_rectangle((margin, y, margin + int((width - margin * 2) * progress), y + 5), radius=3, fill=TEAL)


def draw_scene_caption(draw: Any, width: int, height: int, caption: str, fonts: dict[str, Any]) -> None:
    margin = int(width * 0.07)
    y = int(height * 0.77)
    draw.rounded_rectangle((margin, y, width - margin, y + int(height * 0.115)), radius=18, fill=(5, 9, 16), outline=(39, 56, 79), width=2)
    draw_text_box(draw, caption, (margin + 18, y + 18), fonts["caption"], TEXT, width - 2 * margin - 36, 8)


def draw_label(draw: Any, text: str, xy: tuple[int, int], fonts: dict[str, Any], fill: tuple[int, int, int] = TEXT, outline: tuple[int, int, int] = TEAL) -> None:
    x, y = xy
    bbox = draw.textbbox((0, 0), text, font=fonts["small"])
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    pad_x, pad_y = 10, 7
    rect = (x, y, x + w + pad_x * 2, y + h + pad_y * 2)
    draw.rounded_rectangle(rect, radius=10, fill=(9, 16, 27), outline=outline, width=2)
    draw.text((x + pad_x, y + pad_y), text, font=fonts["small"], fill=fill)


def draw_arrow(draw: Any, start: tuple[float, float], end: tuple[float, float], fill: tuple[int, int, int], width: int = 5) -> None:
    draw.line((start[0], start[1], end[0], end[1]), fill=fill, width=width)
    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    head = 16
    left = (end[0] - head * math.cos(angle - 0.55), end[1] - head * math.sin(angle - 0.55))
    right = (end[0] - head * math.cos(angle + 0.55), end[1] - head * math.sin(angle + 0.55))
    draw.polygon([end, left, right], fill=fill)


def gradient_point(box: tuple[int, int, int, int], x: float) -> tuple[int, int]:
    x1, y1, x2, y2 = box
    span = x2 - x1
    graph_top = y1 + int((y2 - y1) * 0.12)
    graph_height = int((y2 - y1) * 0.58)
    px = x1 + int((x + 3) / 6 * span)
    y_value = (x * x) / 9
    py = graph_top + int((1 - y_value) * graph_height)
    return px, py


def draw_gradient_base(draw: Any, box: tuple[int, int, int, int]) -> list[tuple[int, int]]:
    x1, y1, x2, y2 = box
    axis_y = y2 - int((y2 - y1) * 0.18)
    draw.line((x1, axis_y, x2, axis_y), fill=(42, 57, 78), width=2)
    points = [gradient_point(box, -3 + 6 * i / 120) for i in range(121)]
    draw.line(points, fill=TEAL, width=7, joint="curve")
    return points


def draw_gradient_scene(draw: Any, box: tuple[int, int, int, int], scene: DirectorScene, progress: float, fonts: dict[str, Any]) -> None:
    points = draw_gradient_base(draw, box)
    x1, y1, x2, y2 = box
    if scene.scene_id == "too_big_step":
        start = gradient_point(box, -2.0)
        end = gradient_point(box, 1.7)
        dot = lerp_point(start, end, progress)
        draw_arrow(draw, start, end, PINK, width=5)
        draw_dot(draw, dot, YELLOW, 13)
        draw_label(draw, "too large", (x1 + 12, y1 + 20), fonts, outline=PINK)
        draw_label(draw, "misses", (x2 - 120, y1 + 130), fonts, outline=PINK)
    elif scene.scene_id == "read_slope":
        dot = gradient_point(box, -1.9)
        tangent_start = (dot[0] - 55, dot[1] - 42)
        tangent_end = (dot[0] + 70, dot[1] + 52)
        draw.line((tangent_start[0], tangent_start[1], tangent_end[0], tangent_end[1]), fill=YELLOW, width=5)
        draw_arrow(draw, dot, (dot[0] + 88, dot[1] + 64), BLUE, width=5)
        draw_dot(draw, dot, YELLOW, 13)
        draw_label(draw, "slope", (dot[0] - 95, dot[1] - 92), fonts, outline=YELLOW)
        draw_label(draw, "direction", (dot[0] + 62, dot[1] + 58), fonts, outline=BLUE)
    elif scene.scene_id == "small_step":
        start = gradient_point(box, -1.9)
        end = gradient_point(box, -1.15)
        dot = lerp_point(start, end, progress)
        draw_arrow(draw, start, end, GREEN, width=5)
        draw_dot(draw, dot, YELLOW, 13)
        draw_label(draw, "small step", (min(start[0], end[0]) + 28, start[1] + 42), fonts, outline=GREEN)
    elif scene.scene_id == "repeat_settle":
        xs = [-2.15, -1.35, -0.78, -0.38, -0.12, 0.0]
        visible = max(2, min(len(xs), 1 + int(progress * len(xs))))
        path = [gradient_point(box, x) for x in xs[:visible]]
        if len(path) > 1:
            draw.line(path, fill=GREEN, width=5)
        for index, pt in enumerate(path):
            radius = 8 if index < len(path) - 1 else 13
            draw_dot(draw, pt, GREEN if index < len(path) - 1 else YELLOW, radius)
        draw_label(draw, "repeat", (x1 + 18, y1 + 30), fonts, outline=GREEN)
        draw_label(draw, "settle", (gradient_point(box, 0)[0] + 18, gradient_point(box, 0)[1] - 46), fonts, outline=TEAL)
    else:
        center = gradient_point(box, 0)
        draw_dot(draw, center, YELLOW, 13)
        orbit = [(center[0] - 150, center[1] - 90), (center[0], center[1] - 145), (center[0] + 140, center[1] - 84)]
        for text, pt, color in zip(scene.visible_text, orbit, [BLUE, GREEN, YELLOW]):
            draw_label(draw, text, pt, fonts, outline=color)
            draw_arrow(draw, (pt[0] + 45, pt[1] + 28), center, color, width=3)


def draw_nexus_scene(draw: Any, box: tuple[int, int, int, int], scene: DirectorScene, progress: float, fonts: dict[str, Any]) -> None:
    if scene.scene_id == "inner_steps_to_ghat":
        draw_inner_steps(draw, box, progress, fonts)
        return
    if scene.scene_id == "task_agreement":
        draw_task_agreement(draw, box, progress, fonts)
        return

    left_basin = (box[0] + int((box[2] - box[0]) * 0.34), box[1] + int((box[3] - box[1]) * 0.55))
    right_basin = (box[0] + int((box[2] - box[0]) * 0.68), box[1] + int((box[3] - box[1]) * 0.42))
    draw_contours(draw, left_basin, BLUE)
    draw_contours(draw, right_basin, PINK)
    start_a = (box[0] + 48, box[1] + 80)
    end_a = left_basin
    start_b = (box[2] - 36, box[1] + 90)
    end_b = right_basin
    path_a = bezier_path(start_a, (box[0] + 100, box[1] + 270), end_a, progress)
    path_b = bezier_path(start_b, (box[2] - 150, box[1] + 290), end_b, progress)
    draw.line(sample_bezier(start_a, (box[0] + 100, box[1] + 270), end_a, progress), fill=BLUE, width=5)
    draw.line(sample_bezier(start_b, (box[2] - 150, box[1] + 290), end_b, progress), fill=PINK, width=5)
    draw_dot(draw, path_a, BLUE, 12)
    draw_dot(draw, path_b, PINK, 12)

    if scene.scene_id == "same_score_different_basin":
        y = box[1] + int((box[3] - box[1]) * 0.76)
        draw.line((box[0] + 35, y, box[2] - 35, y), fill=YELLOW, width=3)
        draw_label(draw, "same loss", (box[0] + 42, y - 48), fonts, outline=YELLOW)
        draw_label(draw, "different basin", (box[2] - 190, y - 48), fonts, outline=PINK)
    elif scene.scene_id == "downstream_valley":
        target = (left_basin[0] - 42, left_basin[1] + 66)
        draw_contours(draw, target, GREEN, scale=0.55)
        draw_label(draw, "downstream valley", (target[0] - 72, target[1] + 48), fonts, outline=GREEN)
        draw_arrow(draw, right_basin, target, MUTED, width=3)
        draw_arrow(draw, left_basin, target, GREEN, width=4)
        draw_label(draw, "closer", (left_basin[0] - 90, left_basin[1] - 72), fonts, outline=GREEN)
    else:
        route_points = sample_bezier(start_a, (box[0] + 100, box[1] + 270), end_a, 1.0)
        draw.line(route_points, fill=GREEN, width=7)
        draw_label(draw, "route", (box[0] + 54, box[1] + 50), fonts, outline=GREEN)
        draw_label(draw, "not just score", (box[2] - 190, box[1] + 52), fonts, outline=YELLOW)


def draw_inner_steps(draw: Any, box: tuple[int, int, int, int], progress: float, fonts: dict[str, Any]) -> None:
    x1, y1, x2, y2 = box
    model = (x1 + 38, y1 + 130, x1 + 170, y1 + 220)
    clone = (x1 + 38, y1 + 320, x1 + 170, y1 + 410)
    draw.rounded_rectangle(model, radius=16, fill=(12, 28, 40), outline=TEAL, width=4)
    draw_centered_text(draw, "model", ((model[0] + model[2]) // 2, (model[1] + model[3]) // 2), fonts["small"], TEXT)
    if progress > 0.15:
        draw_arrow(draw, ((model[0] + model[2]) // 2, model[3]), ((clone[0] + clone[2]) // 2, clone[1]), BLUE, width=4)
        draw.rounded_rectangle(clone, radius=16, fill=(12, 22, 38), outline=BLUE, width=4)
        draw_centered_text(draw, "clone", ((clone[0] + clone[2]) // 2, (clone[1] + clone[3]) // 2), fonts["small"], TEXT)
    if progress > 0.35:
        batch_x = x1 + 260
        for idx, label in enumerate(["batch A", "batch B", "batch C"]):
            y = y1 + 165 + idx * 70
            draw_label(draw, label, (batch_x, y), fonts, outline=[BLUE, YELLOW, PINK][idx])
            draw_arrow(draw, (batch_x + 92, y + 18), (clone[2] + 70, clone[1] + 45), [BLUE, YELLOW, PINK][idx], width=3)
    if progress > 0.65:
        out = (x2 - 118, (clone[1] + clone[3]) // 2)
        draw_arrow(draw, (clone[2], (clone[1] + clone[3]) // 2), out, GREEN, width=6)
        draw_label(draw, "g_hat", (out[0] + 8, out[1] - 24), fonts, outline=GREEN)


def draw_task_agreement(draw: Any, box: tuple[int, int, int, int], progress: float, fonts: dict[str, Any]) -> None:
    cx = (box[0] + box[2]) // 2
    cy = (box[1] + box[3]) // 2
    draw_dot(draw, (cx, cy), YELLOW, 14)
    conflict_angle = math.radians(145 - 92 * progress)
    agree_angle = math.radians(35)
    arrows = [
        (BLUE, conflict_angle, "task A"),
        (PINK, -conflict_angle, "task B"),
        (GREEN, agree_angle, "shared pull"),
    ]
    for color, angle, label in arrows:
        end = (cx + 165 * math.cos(angle), cy - 165 * math.sin(angle))
        draw_arrow(draw, (cx, cy), end, color, width=5)
        draw_label(draw, label, (int(end[0] - 44), int(end[1] - 50)), fonts, outline=color)
    draw_label(draw, "agreement", (box[0] + 30, box[1] + 38), fonts, outline=GREEN)


def draw_generic_scene(draw: Any, box: tuple[int, int, int, int], scene: DirectorScene, progress: float, fonts: dict[str, Any]) -> None:
    x1, y1, x2, y2 = box
    left = (x1 + 50, (y1 + y2) // 2)
    right = (x2 - 80, (y1 + y2) // 2)
    dot = lerp_point(left, right, progress)
    draw_arrow(draw, left, right, TEAL, width=5)
    draw_dot(draw, dot, YELLOW, 14)
    for index, text in enumerate(scene.visible_text[:2]):
        draw_label(draw, text, (x1 + 40 + index * 180, y1 + 45), fonts, outline=[BLUE, GREEN][index])


def draw_contours(draw: Any, center: tuple[int, int], color: tuple[int, int, int], scale: float = 1.0) -> None:
    for index, radius in enumerate([92, 62, 34]):
        rx = int(radius * scale)
        ry = int(radius * 0.58 * scale)
        opacity_color = tuple(int(c * (0.75 + 0.08 * index)) for c in color)
        draw.ellipse((center[0] - rx, center[1] - ry, center[0] + rx, center[1] + ry), outline=opacity_color, width=3)


def sample_bezier(start: tuple[int, int], control: tuple[int, int], end: tuple[int, int], progress: float, steps: int = 40) -> list[tuple[int, int]]:
    count = max(2, int(steps * progress))
    return [bezier_point(start, control, end, i / max(1, count - 1)) for i in range(count)]


def bezier_path(start: tuple[int, int], control: tuple[int, int], end: tuple[int, int], progress: float) -> tuple[int, int]:
    return bezier_point(start, control, end, progress)


def bezier_point(start: tuple[int, int], control: tuple[int, int], end: tuple[int, int], t: float) -> tuple[int, int]:
    x = (1 - t) ** 2 * start[0] + 2 * (1 - t) * t * control[0] + t * t * end[0]
    y = (1 - t) ** 2 * start[1] + 2 * (1 - t) * t * control[1] + t * t * end[1]
    return int(x), int(y)


def lerp_point(start: tuple[int, int], end: tuple[int, int], t: float) -> tuple[int, int]:
    return int(start[0] + (end[0] - start[0]) * t), int(start[1] + (end[1] - start[1]) * t)


def draw_dot(draw: Any, center: tuple[int, int], color: tuple[int, int, int], radius: int) -> None:
    draw.ellipse((center[0] - radius, center[1] - radius, center[0] + radius, center[1] + radius), fill=color)
