from __future__ import annotations

import json
import math
import re
import subprocess
import textwrap
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


ASPECTS = {
    "vertical": (1080, 1920),
    "horizontal": (1920, 1080),
    "square": (1080, 1080),
}

QUALITY_SCALE = {
    "draft": 0.5,
    "production": 1.0,
}

BACKGROUND = (7, 11, 19)
TEXT = (248, 250, 252)
MUTED = (169, 179, 196)
BLUE = (96, 165, 250)
TEAL = (45, 212, 191)
YELLOW = (251, 191, 36)
PINK = (251, 113, 133)
GREEN = (52, 211, 153)


@dataclass
class Beat:
    title: str
    caption: str
    visual: str
    duration: float


@dataclass
class VideoPlan:
    title: str
    slug: str
    source: str
    format: str
    duration: float
    beats: list[Beat]


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    return slug or "untitled_video"


def generate_beats(title: str, idea: str, total_duration: float) -> list[Beat]:
    clean_idea = " ".join(idea.replace("\n", " ").split())
    short_topic = textwrap.shorten(clean_idea.rstrip(".") or title, width=72, placeholder=".")
    durations = split_duration(total_duration, 5)
    return [
        Beat(
            "Hook",
            f"Why does {title} matter?",
            "hook",
            durations[0],
        ),
        Beat(
            "Setup",
            f"Start with the core idea: {short_topic}",
            "flow",
            durations[1],
        ),
        Beat(
            "Mechanism",
            "One step changes the next step.",
            "curve",
            durations[2],
        ),
        Beat(
            "Why it matters",
            "Small shifts can create very different outcomes.",
            "compare",
            durations[3],
        ),
        Beat(
            "Takeaway",
            f"Remember: {title} is about the path.",
            "takeaway",
            durations[4],
        ),
    ]


def split_duration(total_duration: float, count: int) -> list[float]:
    duration = max(total_duration, count * 2.5)
    base = duration / count
    return [round(base, 2) for _ in range(count)]


def make_plan(
    *,
    slug: str,
    title: str,
    idea: str,
    source: str,
    video_format: str,
    duration: float,
) -> VideoPlan:
    return VideoPlan(
        title=title,
        slug=slug,
        source=source,
        format=video_format,
        duration=duration,
        beats=generate_beats(title, idea, duration),
    )


def load_plan_from_job(job_dir: Path, *, video_format: str, duration: float | None = None) -> VideoPlan:
    manifest = job_dir / "video_plan.json"
    if manifest.exists():
        data = json.loads(manifest.read_text(encoding="utf-8"))
        beats = [Beat(**beat) for beat in data["beats"]]
        plan = VideoPlan(
            title=data["title"],
            slug=data["slug"],
            source=data.get("source", ""),
            format=video_format or data.get("format", "vertical"),
            duration=float(duration or data.get("duration", sum(beat.duration for beat in beats))),
            beats=beats,
        )
        return plan

    title = read_title(job_dir)
    source = read_source(job_dir)
    beats = beats_from_script(job_dir / "script.md")
    if not beats:
        idea = read_first_text(job_dir / "brief.md") or title
        beats = generate_beats(title, idea, duration or 25)
    if duration:
        durations = split_duration(duration, len(beats))
        beats = [Beat(beat.title, beat.caption, beat.visual, durations[index]) for index, beat in enumerate(beats)]
    return VideoPlan(
        title=title,
        slug=job_dir.name,
        source=source,
        format=video_format,
        duration=sum(beat.duration for beat in beats),
        beats=beats,
    )


def beats_from_script(script_path: Path) -> list[Beat]:
    if not script_path.exists():
        return []
    text = script_path.read_text(encoding="utf-8")
    parts = re.split(r"^##\s+", text, flags=re.MULTILINE)
    beats: list[Beat] = []
    visuals = ["hook", "flow", "curve", "compare", "takeaway"]
    for part in parts[1:]:
        lines = [line.strip() for line in part.splitlines() if line.strip()]
        if not lines:
            continue
        title = lines[0].strip("# ")
        caption = screen_caption(" ".join(lines[1:]).strip())
        if not caption:
            continue
        beats.append(Beat(title=title, caption=caption, visual=visuals[len(beats) % len(visuals)], duration=5.0))
    return beats


def screen_caption(text: str) -> str:
    compact = " ".join(text.split())
    if not compact:
        return ""
    sentence_match = re.match(r"(.+?[.!?])(?:\s|$)", compact)
    candidate = sentence_match.group(1) if sentence_match else compact
    return textwrap.shorten(candidate, width=112, placeholder=".")


def read_title(job_dir: Path) -> str:
    brief = job_dir / "brief.md"
    if brief.exists():
        for line in brief.read_text(encoding="utf-8").splitlines():
            if line.startswith("# Brief:"):
                return line.replace("# Brief:", "").strip()
    readme = job_dir / "README.md"
    if readme.exists():
        for line in readme.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                return line.replace("# ", "").strip()
    return job_dir.name.replace("_", " ").title()


def read_source(job_dir: Path) -> str:
    brief = job_dir / "brief.md"
    if not brief.exists():
        return ""
    lines = brief.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if line.strip() == "## Source" and index + 2 < len(lines):
            return lines[index + 2].strip()
    return ""


def read_first_text(path: Path) -> str:
    if not path.exists():
        return ""
    lines = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    return " ".join(lines[:4])


def write_plan_files(job_dir: Path, plan: VideoPlan, idea: str) -> None:
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "brief.md").write_text(
        "\n".join(
            [
                f"# Brief: {plan.title}",
                "",
                "## Source",
                "",
                plan.source or "Concept prompt",
                "",
                "## Goal",
                "",
                f"Generate a caption-led short explainer about {plan.title}.",
                "",
                "## Input",
                "",
                idea.strip(),
                "",
            ]
        ),
        encoding="utf-8",
    )
    (job_dir / "script.md").write_text(script_markdown(plan), encoding="utf-8")
    (job_dir / "storyboard.md").write_text(storyboard_markdown(plan), encoding="utf-8")
    (job_dir / "video_plan.json").write_text(plan_json(plan), encoding="utf-8")


def script_markdown(plan: VideoPlan) -> str:
    sections = [f"# Script: {plan.title}", ""]
    for beat in plan.beats:
        sections.extend([f"## {beat.title}", "", beat.caption, ""])
    return "\n".join(sections)


def storyboard_markdown(plan: VideoPlan) -> str:
    lines = [
        f"# Storyboard: {plan.title}",
        "",
        "| Beat | Duration | Visual | Caption |",
        "| --- | ---: | --- | --- |",
    ]
    for beat in plan.beats:
        caption = beat.caption.replace("|", "/")
        lines.append(f"| {beat.title} | {beat.duration:.1f}s | {beat.visual} | {caption} |")
    lines.append("")
    return "\n".join(lines)


def plan_json(plan: VideoPlan) -> str:
    return json.dumps(asdict(plan), indent=2) + "\n"


def render_video(job_dir: Path, plan: VideoPlan, *, quality: str, fps: int = 24) -> Path:
    try:
        import imageio.v2 as imageio
        import numpy as np
        from PIL import Image
    except ImportError as error:
        raise SystemExit(
            "Missing render dependencies. Install with: pip install pillow imageio imageio-ffmpeg numpy"
        ) from error

    width, height = render_size(plan.format, quality)
    exports_dir = job_dir / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    output = exports_dir / f"{plan.slug}_{plan.format}_{quality}.mp4"
    srt_path = exports_dir / f"{plan.slug}_{plan.format}_{quality}.srt"
    manifest_path = exports_dir / f"{plan.slug}_{plan.format}_{quality}.json"

    write_srt(plan.beats, srt_path)
    manifest_path.write_text(
        json.dumps(
            {
                **asdict(plan),
                "output": str(output),
                "srt": str(srt_path),
                "width": width,
                "height": height,
                "fps": fps,
                "quality": quality,
                "renderer": "caption_template_v0",
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
        quality=8,
        macro_block_size=1,
        ffmpeg_params=["-movflags", "+faststart"],
    )
    try:
        total_frames = max(1, int(sum(beat.duration for beat in plan.beats) * fps))
        frame_index = 0
        for beat_index, beat in enumerate(plan.beats):
            beat_frames = max(1, int(beat.duration * fps))
            for local_frame in range(beat_frames):
                progress = local_frame / max(1, beat_frames - 1)
                global_progress = frame_index / max(1, total_frames - 1)
                frame = draw_frame(
                    width=width,
                    height=height,
                    plan=plan,
                    beat=beat,
                    beat_index=beat_index,
                    beat_progress=progress,
                    global_progress=global_progress,
                )
                writer.append_data(np.asarray(frame, dtype=np.uint8))
                frame_index += 1
    finally:
        writer.close()

    contact_sheet(output, exports_dir / f"{plan.slug}_{plan.format}_{quality}_contact.png")
    return output


def render_size(video_format: str, quality: str) -> tuple[int, int]:
    width, height = ASPECTS.get(video_format, ASPECTS["vertical"])
    scale = QUALITY_SCALE.get(quality, QUALITY_SCALE["draft"])
    return int(width * scale), int(height * scale)


def draw_frame(
    *,
    width: int,
    height: int,
    plan: VideoPlan,
    beat: Beat,
    beat_index: int,
    beat_progress: float,
    global_progress: float,
) -> Any:
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (width, height), BACKGROUND)
    draw = ImageDraw.Draw(image)
    draw_background(draw, width, height, beat_index, global_progress)
    fonts = load_fonts(width)

    margin = int(width * 0.075)
    safe_top = int(height * 0.055)
    safe_bottom = int(height * 0.12)
    draw_progress(draw, width, height, margin, global_progress)
    draw_text_box(
        draw,
        plan.title,
        (margin, safe_top),
        fonts["eyebrow"],
        MUTED,
        max_width=width - margin * 2,
        line_spacing=6,
    )

    visual_box = (
        margin,
        int(height * 0.15),
        width - margin,
        int(height * 0.68),
    )
    draw_visual(draw, visual_box, beat.visual, beat_index, beat_progress, fonts)
    draw_caption(draw, width, height, beat.caption, fonts["caption"], safe_bottom)
    return image


def draw_background(draw: Any, width: int, height: int, beat_index: int, progress: float) -> None:
    accents = [BLUE, TEAL, YELLOW, PINK, GREEN]
    accent = accents[beat_index % len(accents)]
    for y in range(height):
        mix = y / max(1, height - 1)
        pulse = 0.5 + 0.5 * math.sin(progress * math.tau + mix * 2.0)
        r = int(BACKGROUND[0] + accent[0] * 0.045 * mix * pulse)
        g = int(BACKGROUND[1] + accent[1] * 0.045 * mix * pulse)
        b = int(BACKGROUND[2] + accent[2] * 0.045 * mix * pulse)
        draw.line([(0, y), (width, y)], fill=(r, g, b))


def draw_progress(draw: Any, width: int, height: int, margin: int, progress: float) -> None:
    y = height - int(height * 0.035)
    draw.rounded_rectangle((margin, y, width - margin, y + 6), radius=3, fill=(25, 35, 52))
    draw.rounded_rectangle((margin, y, margin + int((width - margin * 2) * progress), y + 6), radius=3, fill=TEAL)


def draw_visual(draw: Any, box: tuple[int, int, int, int], visual: str, beat_index: int, progress: float, fonts: dict[str, Any]) -> None:
    if visual == "flow":
        draw_flow(draw, box, progress, fonts)
    elif visual == "curve":
        draw_curve(draw, box, progress, fonts)
    elif visual == "compare":
        draw_compare(draw, box, progress, fonts)
    elif visual == "takeaway":
        draw_takeaway(draw, box, progress, fonts)
    else:
        draw_hook(draw, box, progress, fonts)


def draw_hook(draw: Any, box: tuple[int, int, int, int], progress: float, fonts: dict[str, Any]) -> None:
    x1, y1, x2, y2 = box
    cx = (x1 + x2) // 2
    cy = (y1 + y2) // 2
    radius = int((x2 - x1) * (0.16 + 0.03 * math.sin(progress * math.tau)))
    for index, color in enumerate([BLUE, TEAL, PINK]):
        offset = index * 34
        draw.ellipse((cx - radius - offset, cy - radius - offset, cx + radius + offset, cy + radius + offset), outline=color, width=4)
    draw.rounded_rectangle((cx - radius, cy - radius, cx + radius, cy + radius), radius=24, fill=(13, 24, 39), outline=TEAL, width=4)
    draw_centered_text(draw, "idea", (cx, cy), fonts["label"], TEXT)


def draw_flow(draw: Any, box: tuple[int, int, int, int], progress: float, fonts: dict[str, Any]) -> None:
    x1, y1, x2, y2 = box
    labels = [("source", BLUE), ("claim", YELLOW), ("visual", TEAL)]
    target = (x2 - int((x2 - x1) * 0.22), (y1 + y2) // 2)
    for index, (label, color) in enumerate(labels):
        y = y1 + int((index + 1) * (y2 - y1) / 4)
        pill = (x1, y - 28, x1 + int((x2 - x1) * 0.28), y + 28)
        draw.rounded_rectangle(pill, radius=18, fill=(13, 24, 39), outline=color, width=3)
        draw_centered_text(draw, label, ((pill[0] + pill[2]) // 2, y), fonts["small"], TEXT)
        end_x = int(target[0] - 80 + 80 * progress)
        draw.line((pill[2], y, end_x, target[1]), fill=color, width=4)
        draw.ellipse((end_x - 6, target[1] - 6, end_x + 6, target[1] + 6), fill=color)
    draw.rounded_rectangle((target[0] - 70, target[1] - 70, target[0] + 70, target[1] + 70), radius=16, outline=TEAL, width=4, fill=(12, 30, 40))
    draw_centered_text(draw, "video", target, fonts["label"], TEXT)


def draw_curve(draw: Any, box: tuple[int, int, int, int], progress: float, fonts: dict[str, Any]) -> None:
    x1, y1, x2, y2 = box
    baseline = y2 - int((y2 - y1) * 0.2)
    left = x1 + int((x2 - x1) * 0.12)
    right = x2 - int((x2 - x1) * 0.12)
    points = []
    for step in range(90):
        t = step / 89
        x = left + int((right - left) * t)
        y = baseline - int((math.sin(t * math.pi) ** 1.4) * (y2 - y1) * 0.46)
        points.append((x, y))
    draw.line(points, fill=TEAL, width=7)
    dot_index = min(len(points) - 1, int(progress * (len(points) - 1)))
    dx, dy = points[dot_index]
    draw.ellipse((dx - 13, dy - 13, dx + 13, dy + 13), fill=YELLOW)
    draw_centered_text(draw, "motion explains the mechanism", ((x1 + x2) // 2, y1 + 38), fonts["small"], MUTED)


def draw_compare(draw: Any, box: tuple[int, int, int, int], progress: float, fonts: dict[str, Any]) -> None:
    x1, y1, x2, y2 = box
    gap = int((x2 - x1) * 0.06)
    mid = (x1 + x2) // 2
    left = (x1, y1 + 40, mid - gap, y2 - 30)
    right = (mid + gap, y1 + 40, x2, y2 - 30)
    for rect, title, color, amount in [
        (left, "before", PINK, 0.45),
        (right, "after", GREEN, 0.78),
    ]:
        draw.rounded_rectangle(rect, radius=24, fill=(13, 24, 39), outline=color, width=4)
        draw_centered_text(draw, title, ((rect[0] + rect[2]) // 2, rect[1] + 48), fonts["label"], TEXT)
        bar_top = rect[3] - 80
        bar_width = int((rect[2] - rect[0] - 70) * amount * progress)
        draw.rounded_rectangle((rect[0] + 35, bar_top, rect[0] + 35 + bar_width, bar_top + 24), radius=12, fill=color)


def draw_takeaway(draw: Any, box: tuple[int, int, int, int], progress: float, fonts: dict[str, Any]) -> None:
    x1, y1, x2, y2 = box
    cx = (x1 + x2) // 2
    cy = (y1 + y2) // 2
    size = int((x2 - x1) * 0.18)
    draw.ellipse((cx - size, cy - size, cx + size, cy + size), outline=GREEN, width=7)
    check = [
        (cx - int(size * 0.45), cy),
        (cx - int(size * 0.1), cy + int(size * 0.35)),
        (cx + int(size * 0.55), cy - int(size * 0.35)),
    ]
    visible = max(2, int(len(check) * max(progress, 0.45)))
    draw.line(check[:visible], fill=GREEN, width=10, joint="curve")
    draw_centered_text(draw, "prototype", (cx, cy + size + 48), fonts["label"], MUTED)


def draw_caption(draw: Any, width: int, height: int, text: str, font: Any, safe_bottom: int) -> None:
    margin = int(width * 0.07)
    max_width = width - margin * 2
    lines = wrap_text(draw, text, font, max_width, max_lines=3)
    line_height = text_height(draw, "Ag", font) + 10
    box_height = line_height * len(lines) + 30
    y2 = height - safe_bottom
    y1 = y2 - box_height
    draw.rounded_rectangle((margin, y1, width - margin, y2), radius=18, fill=(4, 8, 14), outline=(36, 52, 75), width=2)
    y = y1 + 16
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        x = (width - (bbox[2] - bbox[0])) // 2
        draw.text((x, y), line, font=font, fill=TEXT)
        y += line_height


def draw_text_box(draw: Any, text: str, xy: tuple[int, int], font: Any, fill: tuple[int, int, int], max_width: int, line_spacing: int) -> None:
    x, y = xy
    for line in wrap_text(draw, text, font, max_width, max_lines=3):
        draw.text((x, y), line, font=font, fill=fill)
        y += text_height(draw, line, font) + line_spacing


def draw_centered_text(draw: Any, text: str, center: tuple[int, int], font: Any, fill: tuple[int, int, int]) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    draw.text((center[0] - width // 2, center[1] - height // 2), text, font=font, fill=fill)


def wrap_text(draw: Any, text: str, font: Any, max_width: int, max_lines: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        candidate = " ".join([*current, word])
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if bbox[2] - bbox[0] <= max_width or not current:
            current.append(word)
        else:
            lines.append(" ".join(current))
            current = [word]
    if current:
        lines.append(" ".join(current))
    if len(lines) > max_lines:
        trimmed = lines[:max_lines]
        trimmed[-1] = trimmed[-1].rstrip(".") + "..."
        return trimmed
    return lines


def text_height(draw: Any, text: str, font: Any) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[3] - bbox[1]


def load_fonts(width: int) -> dict[str, Any]:
    from PIL import ImageFont

    font_paths = [
        "/System/Library/Fonts/Avenir Next.ttc",
        "/System/Library/Fonts/Avenir.ttc",
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    ]
    path = next((font for font in font_paths if Path(font).exists()), "")

    def font(size: int) -> Any:
        if path:
            return ImageFont.truetype(path, size=size)
        return ImageFont.load_default()

    scale = width / 1080
    return {
        "eyebrow": font(max(18, int(28 * scale))),
        "title": font(max(28, int(62 * scale))),
        "label": font(max(20, int(34 * scale))),
        "small": font(max(16, int(26 * scale))),
        "caption": font(max(22, int(44 * scale))),
    }


def write_srt(beats: list[Beat], path: Path) -> None:
    cursor = 0.0
    blocks = []
    for index, beat in enumerate(beats, start=1):
        start = cursor
        end = cursor + beat.duration
        blocks.append(f"{index}\n{format_srt_time(start)} --> {format_srt_time(end)}\n{beat.caption}\n")
        cursor = end
    path.write_text("\n".join(blocks), encoding="utf-8")


def format_srt_time(seconds: float) -> str:
    millis = int(round(seconds * 1000))
    hours, remainder = divmod(millis, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def contact_sheet(video_path: Path, output: Path) -> None:
    try:
        import imageio.v2 as imageio
        from PIL import Image, ImageDraw
    except ImportError:
        return
    reader = imageio.get_reader(str(video_path))
    try:
        meta = reader.get_meta_data()
        fps = float(meta.get("fps", 24))
        duration = float(meta.get("duration", 0) or 0)
        frames = []
        for index in range(9):
            timestamp = duration * (index + 0.5) / 9 if duration else index
            frame_index = max(0, int(timestamp * fps))
            try:
                frames.append(Image.fromarray(reader.get_data(frame_index)).resize((180, 320)))
            except Exception:
                break
    finally:
        reader.close()
    if not frames:
        return
    sheet = Image.new("RGB", (600, 1020), (17, 24, 39))
    draw = ImageDraw.Draw(sheet)
    for index, frame in enumerate(frames):
        x = 15 + (index % 3) * 195
        y = 15 + (index // 3) * 335
        sheet.paste(frame, (x, y))
        draw.rectangle((x, y, x + 180, y + 320), outline=(36, 52, 75), width=2)
    sheet.save(output)


def evaluate_export(video_path: Path, manifest_path: Path | None = None) -> dict[str, Any]:
    manifest = {}
    if manifest_path and manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    elif video_path.with_suffix(".json").exists():
        manifest = json.loads(video_path.with_suffix(".json").read_text(encoding="utf-8"))

    beats = [Beat(**beat) for beat in manifest.get("beats", [])]
    width = int(manifest.get("width", 0) or 0)
    height = int(manifest.get("height", 0) or 0)
    duration = float(manifest.get("duration", sum(beat.duration for beat in beats)) or 0)
    video_meta = probe_video(video_path)
    width = width or int(video_meta.get("width", 0) or 0)
    height = height or int(video_meta.get("height", 0) or 0)
    duration = duration or float(video_meta.get("duration", 0) or 0)

    scores = {
        "format_match": score_format(width, height, manifest.get("format", "vertical")),
        "subtitle_readability": score_subtitles(beats),
        "pacing": score_pacing(beats),
        "visual_cadence": score_visual_cadence(beats, duration),
        "hook_strength": score_hook(beats[0].caption if beats else ""),
        "text_load": score_text_load(beats),
        "semantic_motion": score_semantic_motion(beats, manifest.get("renderer", "")),
        "human_storytelling": score_human_storytelling(manifest.get("renderer", "")),
    }
    overall = round(sum(scores.values()) / max(1, len(scores)), 1)
    result = {
        "video": str(video_path),
        "width": width,
        "height": height,
        "duration": round(duration, 2),
        "beats": len(beats),
        "scores": scores,
        "overall": overall,
        "verdict": verdict(overall, manifest.get("renderer", "")),
        "notes": evaluation_notes(scores),
    }
    return result


def probe_video(video_path: Path) -> dict[str, Any]:
    try:
        import imageio_ffmpeg
    except ImportError:
        return {}
    command = [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-i", str(video_path), "-f", "null", "-"]
    proc = subprocess.run(command, capture_output=True, text=True, check=False)
    text = proc.stderr
    meta: dict[str, Any] = {}
    duration_match = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", text)
    if duration_match:
        hours, minutes, seconds = duration_match.groups()
        meta["duration"] = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    size_match = re.search(r"Video:.*? (\d{2,5})x(\d{2,5})", text)
    if size_match:
        meta["width"] = int(size_match.group(1))
        meta["height"] = int(size_match.group(2))
    return meta


def score_format(width: int, height: int, requested: str) -> float:
    if not width or not height:
        return 40.0
    if requested == "vertical" and height > width:
        return 100.0
    if requested == "horizontal" and width > height:
        return 100.0
    if requested == "square" and abs(width - height) < 4:
        return 100.0
    return 50.0


def score_subtitles(beats: list[Beat]) -> float:
    if not beats:
        return 0.0
    penalties = 0
    for beat in beats:
        words = beat.caption.split()
        words_per_second = len(words) / max(beat.duration, 0.1)
        if words_per_second > 3.6:
            penalties += 18
        if len(beat.caption) > 150:
            penalties += 12
    return max(0.0, 100.0 - penalties)


def score_pacing(beats: list[Beat]) -> float:
    if not beats:
        return 0.0
    score = 100.0
    for beat in beats:
        if beat.duration < 2.5:
            score -= 15
        if beat.duration > 8:
            score -= 12
    return max(0.0, score)


def score_visual_cadence(beats: list[Beat], duration: float) -> float:
    if not beats or not duration:
        return 0.0
    changes_per_minute = len(beats) / duration * 60
    if 10 <= changes_per_minute <= 22:
        return 100.0
    if changes_per_minute < 7:
        return 55.0
    return 75.0


def score_hook(caption: str) -> float:
    strong_words = ["why", "same", "secret", "simpler", "different", "important", "hidden"]
    score = 65.0
    lower = caption.lower()
    if len(caption.split()) <= 18:
        score += 15
    if any(word in lower for word in strong_words):
        score += 20
    return min(100.0, score)


def score_text_load(beats: list[Beat]) -> float:
    if not beats:
        return 0.0
    avg_words = sum(len(beat.caption.split()) for beat in beats) / len(beats)
    if avg_words <= 16:
        return 100.0
    if avg_words <= 24:
        return 82.0
    return 58.0


def score_semantic_motion(beats: list[Beat], renderer: str) -> float:
    if renderer == "director_renderer_v1":
        return 88.0
    if renderer == "caption_template_v0":
        return 35.0
    generic_visuals = {"hook", "flow", "curve", "compare", "takeaway"}
    if any(beat.visual in generic_visuals for beat in beats):
        return 55.0
    return 100.0


def score_human_storytelling(renderer: str) -> float:
    if renderer == "director_renderer_v1":
        return 84.0
    if renderer == "caption_template_v0":
        return 30.0
    return 100.0


def verdict(overall: float, renderer: str = "") -> str:
    if renderer == "caption_template_v0":
        return "mechanical prototype - not channel-ready"
    if renderer == "director_renderer_v1" and overall >= 84:
        return "director draft - review visually"
    if overall >= 85:
        return "postable draft"
    if overall >= 72:
        return "needs light revision"
    return "needs another pass"


def evaluation_notes(scores: dict[str, float]) -> list[str]:
    notes = []
    for key, score in scores.items():
        if score < 75:
            notes.append(f"{key} needs attention")
    if not notes:
        notes.append("Backend output passes the basic postability checks.")
    return notes


def write_evaluation_report(result: dict[str, Any], output: Path) -> None:
    lines = [
        "# Video Evaluation",
        "",
        f"Video: `{result['video']}`",
        f"Format: {result['width']}x{result['height']}",
        f"Duration: {result['duration']}s",
        f"Beats: {result['beats']}",
        f"Overall: {result['overall']}/100",
        f"Verdict: {result['verdict']}",
        "",
        "## Scores",
        "",
    ]
    for name, score in result["scores"].items():
        lines.append(f"- {name}: {score}/100")
    lines.extend(["", "## Notes", ""])
    for note in result["notes"]:
        lines.append(f"- {note}")
    lines.append("")
    output.write_text("\n".join(lines), encoding="utf-8")
