"""Deterministic raster fallback and ratio-adapted carousel renderer."""

import hashlib
import math
import shutil
import subprocess
import textwrap
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

from .io import portable, write_json
from .manim_scene import CAPTION_RAIL, SAFE_ZONE
from .models import ContentPlan, ManimSceneSpec


BG = "#07111F"
PANEL = "#122238"
INK = "#F4F7FB"
MUTED = "#A8B3C4"
ACCENT = "#5EEAD4"
WARNING = "#F59E0B"
EDITORIAL_BLACK = "#080706"
EDITORIAL_INK = "#FFF7E6"
EDITORIAL_GOLD = "#FFD34E"
EDITORIAL_ORANGE = "#FF5A36"
EDITORIAL_RED = "#E33127"
EDITORIAL_VIOLET = "#8B5CF6"
PAPER_CREAM = "#F7F0DE"
PAPER_INK = "#111111"
PAPER_LIME = "#B7FF3C"
PAPER_PINK = "#FF4FA3"
PAPER_BLUE = "#3D5AFE"
PAPER_CORAL = "#FF5F45"
PAPER_GRID = "#D8CEB7"
def _first_existing_font(candidates: Sequence[str]) -> Optional[Path]:
    for candidate in candidates:
        path = Path(candidate)
        if path.is_file():
            return path
    return None


FONT_REGULAR = _first_existing_font(
    [
        "/System/Library/Fonts/SFNS.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
)
FONT_BOLD = _first_existing_font(
    [
        "/System/Library/Fonts/SFNS.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ]
)
FONT_HEADLINE = _first_existing_font(
    [
        "/System/Library/Fonts/Supplemental/DIN Condensed Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSansNarrow-Bold.ttf",
    ]
)
FONT_MARKER = _first_existing_font(
    [
        "/System/Library/Fonts/MarkerFelt.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Italic.ttf",
    ]
)


TARGET_PROFILES: Dict[str, Dict[str, object]] = {
    "9:16": {"width": 1080, "height": 1920, "group": "9x16", "safe": (90, 170, 990, 1610)},
    "3:4": {"width": 1080, "height": 1440, "group": "3x4", "safe": (80, 100, 1000, 1300)},
    "4:5": {"width": 1080, "height": 1350, "group": "4x5", "safe": (80, 100, 1000, 1210)},
    "tiktok": {"width": 1080, "height": 1920, "group": "tiktok", "safe": (90, 170, 900, 1510)},
    "stories": {"width": 1080, "height": 1920, "group": "stories", "safe": (90, 230, 990, 1560)},
    "reels": {"width": 1080, "height": 1920, "group": "reels", "safe": (90, 170, 930, 1510)},
    "instagram": {"width": 1080, "height": 1350, "group": "instagram", "safe": (80, 100, 1000, 1210)},
    "linkedin": {"width": 1080, "height": 1350, "group": "linkedin", "safe": (80, 90, 1000, 1230)},
}


def _default_font(size: int) -> ImageFont.ImageFont:
    try:
        # Pillow >= 10.1 can scale the bundled fallback font.
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = FONT_BOLD if bold else FONT_REGULAR
    if path is None:
        return _default_font(size)
    try:
        return ImageFont.truetype(str(path), size=size)
    except OSError:
        return _default_font(size)


def _headline_font(size: int) -> ImageFont.FreeTypeFont:
    if FONT_HEADLINE is None:
        return _font(size, bold=True)
    try:
        return ImageFont.truetype(str(FONT_HEADLINE), size=size)
    except OSError:
        return _font(size, bold=True)


def _marker_font(size: int) -> ImageFont.FreeTypeFont:
    if FONT_MARKER is None:
        return _font(size, bold=True)
    try:
        return ImageFont.truetype(str(FONT_MARKER), size=size)
    except OSError:
        return _font(size, bold=True)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> List[str]:
    words = text.split()
    if not words:
        return []
    lines: List[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = current + " " + word
        if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    box: Tuple[int, int, int, int],
    max_size: int,
    min_size: int,
    bold: bool = False,
    spacing_ratio: float = 0.25,
) -> Tuple[ImageFont.ImageFont, List[str], int]:
    width = box[2] - box[0]
    height = box[3] - box[1]
    for size in range(max_size, min_size - 1, -2):
        font = _font(size, bold=bold)
        lines = _wrap(draw, text, font, width)
        spacing = max(6, int(size * spacing_ratio))
        line_height = draw.textbbox((0, 0), "Ag", font=font)[3]
        if len(lines) * line_height + max(0, len(lines) - 1) * spacing <= height:
            return font, lines, spacing
    font = _font(min_size, bold=bold)
    return font, _wrap(draw, text, font, width), max(6, int(min_size * spacing_ratio))


def _draw_text_box(
    draw: ImageDraw.ImageDraw,
    text: str,
    box: Tuple[int, int, int, int],
    max_size: int,
    min_size: int,
    color: str = INK,
    bold: bool = False,
    anchor: str = "la",
) -> Dict[str, object]:
    font, lines, spacing = _fit_text(draw, text, box, max_size, min_size, bold=bold)
    line_height = draw.textbbox((0, 0), "Ag", font=font)[3]
    total_height = len(lines) * line_height + max(0, len(lines) - 1) * spacing
    y = box[1] + max(0, (box[3] - box[1] - total_height) // 2)
    for line in lines:
        draw.text((box[0], y), line, font=font, fill=color)
        y += line_height + spacing
    return {
        "box": list(box),
        "font_size": getattr(font, "size", min_size),
        "line_count": len(lines),
        "truncated": y - spacing > box[3] + 2,
        "text": text,
    }


def _draw_visual(draw: ImageDraw.ImageDraw, kind: str, box: Tuple[int, int, int, int], index: int = 0) -> None:
    left, top, right, bottom = box
    width, height = right - left, bottom - top
    if kind in {"model_cards", "comparison_grid"}:
        columns = 3 if kind == "model_cards" else 2
        rows = 1 if columns == 3 else 2
        gap = 20
        card_w = (width - gap * (columns - 1)) // columns
        card_h = (height - gap * (rows - 1)) // rows
        labels = ["SOL", "TERRA", "LUNA", "CONTROL"]
        for item in range(columns * rows):
            x = left + (item % columns) * (card_w + gap)
            y = top + (item // columns) * (card_h + gap)
            draw.rounded_rectangle((x, y, x + card_w, y + card_h), radius=20, fill=PANEL, outline=ACCENT, width=4)
            label = labels[item]
            font = _font(32 if width > 700 else 22, bold=True)
            bbox = draw.textbbox((0, 0), label, font=font)
            draw.text((x + (card_w - bbox[2]) / 2, y + (card_h - bbox[3]) / 2), label, font=font, fill=ACCENT)
    elif kind == "timeline":
        y = top + height // 2
        draw.line((left + 30, y, right - 30, y), fill=ACCENT, width=8)
        for x in (left + 30, left + width // 2, right - 30):
            draw.ellipse((x - 18, y - 18, x + 18, y + 18), fill=ACCENT)
    elif kind == "eval_bars":
        for row, scale in enumerate((0.45, 0.7, 0.95)):
            y = top + row * max(70, height // 4)
            draw.rounded_rectangle((left, y, left + int(width * scale), y + 42), radius=20, fill=ACCENT)
    elif kind == "agent_loop":
        points = [(left + width // 3, top + height // 3), (right - width // 3, top + height // 3), (right - width // 3, bottom - height // 3), (left + width // 3, bottom - height // 3)]
        for start, end in zip(points, points[1:] + points[:1]):
            draw.line((*start, *end), fill=ACCENT, width=6)
        for x, y in points:
            draw.ellipse((x - 30, y - 30, x + 30, y + 30), fill=PANEL, outline=ACCENT, width=6)
    elif kind == "routing_diagram":
        center = (left + width // 3, top + height // 2)
        draw.ellipse((center[0] - 35, center[1] - 35, center[0] + 35, center[1] + 35), fill=ACCENT)
        for row in range(3):
            target = (right - width // 4, top + (row + 1) * height // 4)
            draw.line((*center, *target), fill=ACCENT, width=5)
            draw.rounded_rectangle((target[0] - 80, target[1] - 30, target[0] + 80, target[1] + 30), radius=15, fill=PANEL, outline=ACCENT, width=3)
    elif kind == "before_after":
        mid = left + width // 2
        draw.rounded_rectangle((left, top + 30, mid - 45, bottom - 30), radius=20, fill=PANEL, outline=MUTED, width=4)
        draw.rounded_rectangle((mid + 45, top + 30, right, bottom - 30), radius=20, fill=PANEL, outline=ACCENT, width=4)
        draw.line((mid - 25, top + height // 2, mid + 25, top + height // 2), fill=ACCENT, width=8)
    else:
        draw.rounded_rectangle(box, radius=28, fill=PANEL, outline=ACCENT, width=4)
        inset = 40 + (index % 3) * 12
        draw.rounded_rectangle((left + inset, top + inset, right - inset, bottom - inset), radius=20, outline=MUTED, width=3)


def _source_badge(draw: ImageDraw.ImageDraw, label: str, box: Tuple[int, int, int, int]) -> Dict[str, object]:
    draw.rounded_rectangle(box, radius=16, fill=PANEL)
    text = "SOURCE  " + label
    return _draw_text_box(draw, text, (box[0] + 22, box[1], box[2] - 22, box[3]), 25, 18, color=MUTED, bold=True)


def render_video_frames(plan: ContentPlan, spec: ManimSceneSpec, frames_dir: Path) -> Tuple[List[Path], List[Dict[str, object]]]:
    frames_dir.mkdir(parents=True, exist_ok=True)
    paths: List[Path] = []
    metadata: List[Dict[str, object]] = []
    for index, beat in enumerate(plan.beats):
        image = Image.new("RGB", (spec.width, spec.height), BG)
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((55, 55, 285, 105), radius=22, fill=ACCENT)
        draw.text((78, 68), "CONTENTMAXXER", font=_font(20, bold=True), fill=BG)
        title_box = (SAFE_ZONE["left"], SAFE_ZONE["top"], spec.width - SAFE_ZONE["right"], 650)
        title_meta = _draw_text_box(draw, beat.headline, title_box, 78, 42, bold=True)
        visual_box = (130, 700, 950, 1200)
        _draw_visual(draw, beat.primitive, visual_box, index)
        rail = (CAPTION_RAIL["left"], CAPTION_RAIL["top"], CAPTION_RAIL["right"], CAPTION_RAIL["bottom"])
        draw.rounded_rectangle(rail, radius=28, fill="#0B1829")
        caption_box = (rail[0] + 34, rail[1] + 24, rail[2] - 34, rail[3] - 24)
        caption_meta = _draw_text_box(draw, beat.on_screen_text, caption_box, 42, 30)
        source_box = (90, 1240, 990, 1305)
        source_meta = _source_badge(draw, beat.source_label, source_box)
        path = frames_dir / f"{index + 1:03d}.png"
        image.save(path, optimize=True)
        paths.append(path)
        metadata.append(
            {
                "path": path.name,
                "width": spec.width,
                "height": spec.height,
                "duration_seconds": beat.duration_seconds,
                "text_boxes": [title_meta, caption_meta, source_meta],
                "safe_zone": [SAFE_ZONE["left"], SAFE_ZONE["top"], spec.width - SAFE_ZONE["right"], spec.height - SAFE_ZONE["bottom"]],
            }
        )
    return paths, metadata


def _ffmpeg_executable() -> str:
    try:
        import imageio_ffmpeg
    except ImportError as exc:
        raise RuntimeError("Raster video packaging requires imageio-ffmpeg; run `python -m pip install -e .`.") from exc
    return imageio_ffmpeg.get_ffmpeg_exe()


def package_frames(frames: Sequence[Path], durations: Sequence[float], output_path: Path, fps: int = 30) -> str:
    if not frames:
        raise RuntimeError("no frames to package")
    concat_path = output_path.parent / "frames.concat.txt"
    lines: List[str] = []
    for frame, duration in zip(frames, durations):
        escaped = frame.resolve().as_posix().replace("'", "'\\''")
        lines.extend([f"file '{escaped}'", f"duration {duration:.3f}"])
    escaped_last = frames[-1].resolve().as_posix().replace("'", "'\\''")
    lines.append(f"file '{escaped_last}'")
    concat_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        _ffmpeg_executable(),
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_path),
        "-vf",
        f"fps={fps}",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError("ffmpeg packaging failed: " + (completed.stderr or completed.stdout)[-1800:])
    return " ".join(command)


def write_srt(plan: ContentPlan, path: Path) -> Path:
    def timestamp(seconds: float) -> str:
        millis = int(round(seconds * 1000))
        hours, millis = divmod(millis, 3_600_000)
        minutes, millis = divmod(millis, 60_000)
        secs, millis = divmod(millis, 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    elapsed = 0.0
    blocks: List[str] = []
    for index, beat in enumerate(plan.beats, start=1):
        end = elapsed + beat.duration_seconds
        blocks.append(f"{index}\n{timestamp(elapsed)} --> {timestamp(end)}\n{beat.narration}\n")
        elapsed = end
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(blocks), encoding="utf-8")
    return path


def make_contact_sheet(images: Sequence[Path], output_path: Path, columns: int = 2, thumb_width: int = 360) -> Path:
    if not images:
        raise RuntimeError("cannot make a contact sheet without images")
    opened = [Image.open(path).convert("RGB") for path in images]
    ratio = opened[0].height / opened[0].width
    thumb_height = int(thumb_width * ratio)
    rows = math.ceil(len(opened) / columns)
    gap = 18
    sheet = Image.new("RGB", (columns * thumb_width + (columns + 1) * gap, rows * thumb_height + (rows + 1) * gap), BG)
    for index, image in enumerate(opened):
        thumb = image.resize((thumb_width, thumb_height), Image.Resampling.LANCZOS)
        x = gap + (index % columns) * (thumb_width + gap)
        y = gap + (index // columns) * (thumb_height + gap)
        sheet.paste(thumb, (x, y))
        image.close()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path, optimize=True)
    return output_path


def make_labeled_contact_sheet(
    images: Sequence[Path],
    labels: Sequence[str],
    output_path: Path,
    columns: int = 3,
    thumb_width: int = 300,
) -> Path:
    if not images:
        raise RuntimeError("cannot make a labeled contact sheet without images")
    if len(images) != len(labels):
        raise ValueError("contact-sheet images and labels must have equal lengths")
    opened = [Image.open(path).convert("RGB") for path in images]
    ratio = opened[0].height / opened[0].width
    thumb_height = int(thumb_width * ratio)
    label_height = 34
    rows = math.ceil(len(opened) / columns)
    gap = 14
    cell_height = thumb_height + label_height
    sheet = Image.new(
        "RGB",
        (
            columns * thumb_width + (columns + 1) * gap,
            rows * cell_height + (rows + 1) * gap,
        ),
        BG,
    )
    draw = ImageDraw.Draw(sheet)
    font = _font(14, bold=True)
    for index, (image, label) in enumerate(zip(opened, labels)):
        thumb = image.resize((thumb_width, thumb_height), Image.Resampling.LANCZOS)
        x = gap + (index % columns) * (thumb_width + gap)
        y = gap + (index // columns) * (cell_height + gap)
        sheet.paste(thumb, (x, y))
        draw.rectangle(
            [x, y + thumb_height, x + thumb_width, y + cell_height],
            fill="#0C1A2B",
        )
        draw.text(
            (x + 8, y + thumb_height + 8),
            label,
            font=font,
            fill=INK,
        )
        image.close()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path, optimize=True)
    return output_path


def render_raster_video(plan: ContentPlan, spec: ManimSceneSpec, job_dir: Path) -> Dict[str, object]:
    frames_dir = job_dir / "video" / "raster" / "frames"
    frames, frame_metadata = render_video_frames(plan, spec, frames_dir)
    output_path = job_dir / "video" / "reel.mp4"
    command = package_frames(frames, [beat.duration_seconds for beat in plan.beats], output_path, fps=spec.fps)
    srt = write_srt(plan, job_dir / "video" / "captions.srt")
    contact = make_contact_sheet(frames, job_dir / "video" / "contact-sheet.png")
    metadata_path = job_dir / "video" / "raster" / "metadata.json"
    payload = {
        "renderer": "raster_fallback",
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
    write_json(metadata_path, payload)
    return payload


def _hero_source(plan: ContentPlan) -> Path:
    root = Path(__file__).resolve().parents[2]
    key = plan.topic.lower()
    filename = "gpt-5-6-controls-hero.png" if any(word in key for word in ("capability", "control", "safety", "cyber", "bio")) else "gpt-5-6-family-hero.png"
    return root / "assets" / "editorial" / filename


def _copy_hero(plan: ContentPlan, job_dir: Path) -> Optional[Path]:
    if plan.visual_theme != "editorial_heat_v1":
        return None
    source = _hero_source(plan)
    if not source.exists() or "gpt" not in plan.topic.lower():
        return None
    destination = job_dir / "carousel" / "assets" / source.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination


def _generated_backdrop(size: Tuple[int, int], accent: str) -> Image.Image:
    width, height = size
    image = Image.new("RGB", size, EDITORIAL_BLACK)
    draw = ImageDraw.Draw(image)
    for y in range(height):
        amount = y / max(1, height - 1)
        draw.line((0, y, width, y), fill=(int(18 + 20 * amount), int(10 + 5 * amount), int(12 + 8 * amount)))
    for radius, color in ((300, accent), (190, EDITORIAL_VIOLET), (100, EDITORIAL_GOLD)):
        x, y = width // 2, int(height * 0.35)
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), outline=color, width=max(3, radius // 25))
    return image


def _editorial_background(plan: ContentPlan, size: Tuple[int, int], hero_path: Optional[Path], cover: bool, index: int) -> Image.Image:
    accent = EDITORIAL_RED if "control" in plan.topic.lower() else EDITORIAL_ORANGE
    if hero_path and hero_path.exists():
        with Image.open(hero_path) as source:
            centering = (0.5 + ((index % 3) - 1) * 0.05, 0.42 if cover else 0.38)
            image = ImageOps.fit(source.convert("RGB"), size, method=Image.Resampling.LANCZOS, centering=centering)
    else:
        image = _generated_backdrop(size, accent)
    image = ImageEnhance.Contrast(image).enhance(1.12)
    image = ImageEnhance.Color(image).enhance(1.05 if cover else 0.72)
    if not cover:
        image = image.filter(ImageFilter.GaussianBlur(radius=1.2))
    overlay = Image.new("RGBA", size, (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    width, height = size
    for y in range(height):
        position = y / max(1, height - 1)
        if cover:
            alpha = int(15 + 220 * max(0.0, (position - 0.42) / 0.58) ** 1.25)
        else:
            alpha = int(145 + 65 * position)
        odraw.line((0, y, width, y), fill=(4, 3, 3, min(235, alpha)))
    tint = (115, 18, 10, 35) if "control" in plan.topic.lower() else (83, 35, 8, 24)
    odraw.rectangle((0, 0, width, height), fill=tint)
    return Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")


def _normalize_token(value: str) -> str:
    return "".join(character for character in value.upper() if character.isalnum() or character in {"×", "‑"})


def _draw_editorial_headline(
    draw: ImageDraw.ImageDraw,
    text: str,
    box: Tuple[int, int, int, int],
    max_size: int,
    min_size: int,
    accent_terms: Sequence[str],
    accent: str,
) -> Dict[str, object]:
    value = " ".join(text.upper().replace("‑", "-").split())
    width = box[2] - box[0]
    chosen_font: ImageFont.ImageFont = _headline_font(min_size)
    lines: List[List[str]] = []
    spacing = max(8, min_size // 8)
    for size in range(max_size, min_size - 1, -2):
        font = _headline_font(size)
        candidate_lines: List[List[str]] = []
        current: List[str] = []
        for word in value.split():
            test = " ".join(current + [word])
            if current and draw.textbbox((0, 0), test, font=font)[2] > width:
                candidate_lines.append(current)
                current = [word]
            else:
                current.append(word)
        if current:
            candidate_lines.append(current)
        line_height = draw.textbbox((0, 0), "AG", font=font)[3]
        candidate_spacing = max(8, size // 8)
        total = len(candidate_lines) * line_height + max(0, len(candidate_lines) - 1) * candidate_spacing
        if total <= box[3] - box[1]:
            chosen_font, lines, spacing = font, candidate_lines, candidate_spacing
            break
    if not lines:
        lines = [[word] for word in value.split()]
    accent_tokens = {_normalize_token(word) for term in accent_terms for word in term.split()}
    line_height = draw.textbbox((0, 0), "AG", font=chosen_font)[3]
    total_height = len(lines) * line_height + max(0, len(lines) - 1) * spacing
    y = box[1] + max(0, (box[3] - box[1] - total_height) // 2)
    for line in lines:
        x = box[0]
        for word in line:
            color = accent if _normalize_token(word) in accent_tokens else EDITORIAL_INK
            draw.text((x, y), word, font=chosen_font, fill=color)
            x += int(draw.textlength(word + " ", font=chosen_font))
        y += line_height + spacing
    return {
        "box": list(box),
        "font_size": getattr(chosen_font, "size", min_size),
        "line_count": len(lines),
        "truncated": y - spacing > box[3] + 2,
        "text": value,
    }


def _draw_editorial_header(draw: ImageDraw.ImageDraw, slide: object, index: int, count: int, safe: Tuple[int, int, int, int], accent: str, cover: bool) -> None:
    brand_font = _font(22, bold=True)
    small_font = _font(18, bold=True)
    draw.text((safe[0], safe[1]), "CONTENTMAXXER", font=brand_font, fill=EDITORIAL_INK)
    pill_text = slide.eyebrow or "SOURCE-BACKED BRIEF"
    pill_width = max(150, int(draw.textlength(pill_text, font=small_font)) + 34)
    y = safe[1] + 42
    draw.rounded_rectangle((safe[0], y, safe[0] + pill_width, y + 42), radius=10, fill=accent)
    draw.text((safe[0] + 17, y + 10), pill_text, font=small_font, fill=EDITORIAL_BLACK)
    right = safe[2]
    cue = "SWIPE  →" if cover else f"{index + 1:02d} / {count:02d}"
    cue_width = int(draw.textlength(cue, font=small_font))
    draw.text((right - cue_width, safe[1] + 10), cue, font=small_font, fill=EDITORIAL_INK)


def _draw_editorial_visual(draw: ImageDraw.ImageDraw, slide: object, box: Tuple[int, int, int, int], accent: str) -> None:
    left, top, right, bottom = box
    width, height = right - left, bottom - top
    draw.rounded_rectangle(box, radius=30, fill=(7, 6, 6), outline="#5C5049", width=2)
    visual = slide.visual
    if visual in {"versus_cover", "price_split", "input_split", "control_split"}:
        mid = left + width // 2
        labels = ("FABLE 5", "GPT-5.6")
        colors = (EDITORIAL_VIOLET, accent)
        for item, label in enumerate(labels):
            x1 = left + 35 if item == 0 else mid + 18
            x2 = mid - 18 if item == 0 else right - 35
            draw.rounded_rectangle((x1, top + 45, x2, bottom - 45), radius=26, fill="#17110F", outline=colors[item], width=5)
            _draw_text_box(draw, label, (x1 + 25, top + 75, x2 - 25, top + 185), 48, 28, color=colors[item], bold=True)
            if visual == "price_split":
                value = "$10 / $50" if item == 0 else "$5 / $30"
            elif visual == "input_split":
                value = "$10 IN" if item == 0 else "$5 IN"
            elif visual == "control_split":
                value = "ADAPTIVE" if item == 0 else "EFFORT DIAL"
            else:
                value = "ONE BET" if item == 0 else "3 TIERS"
            _draw_text_box(draw, value, (x1 + 25, top + 205, x2 - 25, bottom - 80), 54, 28, color=EDITORIAL_INK, bold=True)
        draw.ellipse((mid - 42, top + height // 2 - 42, mid + 42, top + height // 2 + 42), fill=accent)
        _draw_text_box(draw, "VS", (mid - 28, top + height // 2 - 25, mid + 28, top + height // 2 + 25), 26, 20, color=EDITORIAL_BLACK, bold=True)
    elif visual == "mental_model":
        mid = left + width // 2
        draw.rounded_rectangle((left + 30, top + 45, mid - 24, bottom - 45), radius=24, fill="#1B1715", outline="#71645B", width=3)
        draw.rounded_rectangle((mid + 24, top + 45, right - 30, bottom - 45), radius=24, fill="#26130D", outline=accent, width=5)
        _draw_text_box(draw, "ONE MODEL", (left + 60, top + 90, mid - 50, bottom - 90), 54, 30, color="#9B8D82", bold=True)
        _draw_text_box(draw, "THREE\nTIERS", (mid + 60, top + 90, right - 60, bottom - 90), 62, 34, color=accent, bold=True)
        draw.line((mid - 10, top + height // 2, mid + 10, top + height // 2), fill=EDITORIAL_GOLD, width=8)
    elif visual in {"tier_sol", "tier_terra", "tier_luna"}:
        label = visual.split("_")[1].upper()
        colors = {"SOL": EDITORIAL_GOLD, "TERRA": EDITORIAL_ORANGE, "LUNA": EDITORIAL_VIOLET}
        color = colors[label]
        center = (left + width // 2, top + height // 2)
        for radius, line_width in ((170, 6), (125, 4), (82, 3)):
            draw.ellipse((center[0] - radius, center[1] - radius, center[0] + radius, center[1] + radius), outline=color, width=line_width)
        font = _headline_font(94)
        bbox = draw.textbbox((0, 0), label, font=font)
        draw.text((center[0] - bbox[2] / 2, center[1] - bbox[3] / 2), label, font=font, fill=EDITORIAL_INK)
    elif visual == "three_tiers":
        labels = ("SOL", "TERRA", "LUNA")
        colors = (EDITORIAL_GOLD, EDITORIAL_ORANGE, EDITORIAL_VIOLET)
        gap = 18
        card_width = (width - 100 - gap * 2) // 3
        for item, (label, color) in enumerate(zip(labels, colors)):
            x = left + 50 + item * (card_width + gap)
            draw.rounded_rectangle((x, top + 70, x + card_width, bottom - 70), radius=24, fill="#17110F", outline=color, width=5)
            _draw_text_box(draw, label, (x + 12, top + 105, x + card_width - 12, bottom - 105), 48, 26, color=color, bold=True)
    elif visual == "risk_signal":
        labels = ("SOL", "TERRA", "LUNA")
        gap = 20
        card_width = (width - 100 - gap * 2) // 3
        for item, label in enumerate(labels):
            x = left + 50 + item * (card_width + gap)
            draw.rounded_rectangle((x, top + 65, x + card_width, bottom - 65), radius=24, fill="#1C100D", outline=accent, width=4)
            _draw_text_box(draw, label, (x + 20, top + 105, x + card_width - 20, top + 205), 44, 28, color=EDITORIAL_INK, bold=True)
            _draw_text_box(draw, "HIGH", (x + 20, top + 230, x + card_width - 20, bottom - 105), 68, 36, color=accent, bold=True)
    elif visual == "threshold_split":
        mid = left + width // 2
        _draw_text_box(draw, "HIGH", (left + 45, top + 55, mid - 20, bottom - 55), 84, 42, color=accent, bold=True)
        draw.line((mid, top + 55, mid, bottom - 55), fill="#6C5E55", width=3)
        _draw_text_box(draw, "BELOW\nCRITICAL", (mid + 35, top + 55, right - 45, bottom - 55), 62, 34, color=EDITORIAL_INK, bold=True)
    elif visual == "system_layers":
        labels = ("MODEL", "CHECKS", "MONITOR", "ACCOUNT")
        for layer, label in enumerate(labels):
            inset = 35 + layer * 45
            color = accent if layer in {0, 3} else EDITORIAL_GOLD
            draw.rounded_rectangle((left + inset, top + inset, right - inset, bottom - inset), radius=30, outline=color, width=max(2, 6 - layer))
            draw.text((left + inset + 18, top + inset + 12), label, font=_font(18, bold=True), fill=color)
    elif visual == "proof_receipt":
        paper = (left + 85, top + 45, right - 55, bottom - 45)
        draw.rounded_rectangle(paper, radius=16, fill="#F3E8D4")
        draw.rounded_rectangle((paper[0] + 35, paper[1] + 30, paper[0] + 235, paper[1] + 75), radius=8, fill=accent)
        draw.text((paper[0] + 52, paper[1] + 40), "OFFICIAL SOURCE", font=_font(18, bold=True), fill=EDITORIAL_BLACK)
        for row in range(5):
            y = paper[1] + 125 + row * 48
            end = paper[2] - (80 if row in {1, 4} else 35)
            draw.rounded_rectangle((paper[0] + 35, y, end, y + 13), radius=6, fill="#B7A995")
        draw.ellipse((paper[2] - 155, paper[3] - 155, paper[2] - 35, paper[3] - 35), outline=accent, width=10)
    elif visual in {"calculator_receipt", "price_fable", "price_gpt", "cost_iceberg"}:
        paper = (left + 95, top + 38, right - 75, bottom - 38)
        draw.rounded_rectangle(paper, radius=18, fill="#F3E8D4")
        label = {"calculator_receipt": "$2,000 GAP", "price_fable": "$50 / MTOK", "price_gpt": "$30 / MTOK", "cost_iceberg": "PRICE ≠ COST"}[visual]
        draw.rounded_rectangle((paper[0] + 35, paper[1] + 30, paper[2] - 35, paper[1] + 105), radius=12, fill=accent)
        _draw_text_box(draw, label, (paper[0] + 55, paper[1] + 40, paper[2] - 55, paper[1] + 95), 42, 25, color=EDITORIAL_BLACK, bold=True)
        for row in range(4):
            y = paper[1] + 150 + row * 48
            draw.rounded_rectangle((paper[0] + 45, y, paper[2] - 45 - row % 2 * 90, y + 12), radius=6, fill="#AA9B88")
        draw.line((paper[0] + 45, paper[3] - 55, paper[2] - 45, paper[3] - 55), fill=accent, width=11)
    elif visual == "context_tie":
        _draw_text_box(draw, "1M", (left + 60, top + 70, left + width // 2 - 30, bottom - 70), 96, 48, color=EDITORIAL_VIOLET, bold=True)
        _draw_text_box(draw, "≈", (left + width // 2 - 55, top + 70, left + width // 2 + 55, bottom - 70), 82, 42, color=EDITORIAL_INK, bold=True)
        _draw_text_box(draw, "1.05M", (left + width // 2 + 35, top + 70, right - 60, bottom - 70), 84, 42, color=accent, bold=True)
    elif visual == "single_frontier":
        center = (left + width // 2, top + height // 2)
        for radius, color in ((185, EDITORIAL_VIOLET), (125, EDITORIAL_ORANGE), (65, EDITORIAL_GOLD)):
            draw.ellipse((center[0] - radius, center[1] - radius, center[0] + radius, center[1] + radius), outline=color, width=12)
        draw.line((center[0] - 265, center[1] + 200, center[0], center[1]), fill=EDITORIAL_INK, width=12)
    elif visual == "tension_scale":
        center_x = left + width // 2
        y = top + height // 2
        draw.line((center_x, top + 75, center_x, bottom - 60), fill=EDITORIAL_INK, width=9)
        draw.line((left + 110, y - 50, right - 110, y + 50), fill=accent, width=10)
        for x, label, dy in ((left + 160, "CONTROL", -70), (right - 160, "FRICTION", 70)):
            draw.ellipse((x - 85, y + dy - 85, x + 85, y + dy + 85), fill="#1B1110", outline=accent, width=5)
            _draw_text_box(draw, label, (x - 65, y + dy - 45, x + 65, y + dy + 45), 30, 20, color=EDITORIAL_INK, bold=True)
    elif visual == "save_card":
        center = (left + width // 2, top + height // 2)
        bookmark = [(center[0] - 90, center[1] - 150), (center[0] + 90, center[1] - 150), (center[0] + 90, center[1] + 150), (center[0], center[1] + 75), (center[0] - 90, center[1] + 150)]
        draw.polygon(bookmark, fill=accent)
        for offset in (-250, 250):
            draw.ellipse((center[0] + offset - 34, center[1] - 34, center[0] + offset + 34, center[1] + 34), fill=EDITORIAL_VIOLET if offset < 0 else EDITORIAL_GOLD)
            draw.line((center[0] + (90 if offset > 0 else -90), center[1], center[0] + offset, center[1]), fill=EDITORIAL_INK, width=5)
    else:
        _draw_visual(draw, "before_after" if visual == "detail_crop" else visual, (left + 35, top + 35, right - 35, bottom - 35))


def _paper_background(size: Tuple[int, int], index: int) -> Image.Image:
    width, height = size
    image = Image.new("RGB", size, PAPER_CREAM)
    draw = ImageDraw.Draw(image)
    grid = 54
    for x in range(-index * 7 % grid, width, grid):
        draw.line((x, 0, x, height), fill=PAPER_GRID, width=1)
    for y in range(-index * 11 % grid, height, grid):
        draw.line((0, y, width, y), fill=PAPER_GRID, width=1)
    for dot in range(65):
        x = (dot * 173 + index * 97) % width
        y = (dot * 281 + index * 61) % height
        draw.ellipse((x, y, x + 2, y + 2), fill="#C9BFA9")
    return image


def _paper_tape(draw: ImageDraw.ImageDraw, x: int, y: int, width: int, color: str) -> None:
    points = [(x, y + 4), (x + width, y), (x + width - 5, y + 42), (x + 4, y + 46)]
    draw.polygon(points, fill=color)
    for offset in range(8, width, 22):
        draw.line((x + offset, y + 5, x + offset - 5, y + 40), fill="#FFFFFF", width=2)


def _draw_paper_headline(
    draw: ImageDraw.ImageDraw,
    text: str,
    box: Tuple[int, int, int, int],
    max_size: int,
    min_size: int,
    accent_terms: Sequence[str],
    accent: str,
) -> Dict[str, object]:
    value = " ".join(text.upper().replace("‑", "-").split())
    width = box[2] - box[0]
    chosen = _marker_font(min_size)
    lines: List[List[str]] = []
    spacing = 8
    for size in range(max_size, min_size - 1, -2):
        font = _marker_font(size)
        candidate: List[List[str]] = []
        current: List[str] = []
        for word in value.split():
            test = " ".join(current + [word])
            if current and draw.textbbox((0, 0), test, font=font)[2] > width:
                candidate.append(current)
                current = [word]
            else:
                current.append(word)
        if current:
            candidate.append(current)
        line_height = draw.textbbox((0, 0), "AG", font=font)[3]
        candidate_spacing = max(5, size // 12)
        if len(candidate) * line_height + max(0, len(candidate) - 1) * candidate_spacing <= box[3] - box[1]:
            chosen, lines, spacing = font, candidate, candidate_spacing
            break
    if not lines:
        lines = [[word] for word in value.split()]
    accents = {_normalize_token(word) for term in accent_terms for word in term.split()}
    line_height = draw.textbbox((0, 0), "AG", font=chosen)[3]
    total = len(lines) * line_height + max(0, len(lines) - 1) * spacing
    y = box[1] + max(0, (box[3] - box[1] - total) // 2)
    for line in lines:
        x = box[0]
        for word in line:
            advance = int(draw.textlength(word + " ", font=chosen))
            if _normalize_token(word) in accents:
                word_width = int(draw.textlength(word, font=chosen))
                draw.polygon([(x - 5, y + line_height // 2), (x + word_width + 7, y + line_height // 2 - 5), (x + word_width + 4, y + line_height + 5), (x - 2, y + line_height + 8)], fill=accent)
            draw.text((x, y), word, font=chosen, fill=PAPER_INK)
            x += advance
        y += line_height + spacing
    return {"box": list(box), "font_size": getattr(chosen, "size", min_size), "line_count": len(lines), "truncated": y - spacing > box[3] + 2, "text": value}


def _stick_person(draw: ImageDraw.ImageDraw, center: Tuple[int, int], scale: int, color: str, mood: str = "neutral") -> None:
    x, y = center
    draw.ellipse((x - scale, y - scale * 2, x + scale, y), fill=PAPER_CREAM, outline=color, width=max(3, scale // 7))
    draw.ellipse((x - scale // 3, y - scale * 4 // 3, x - scale // 5, y - scale * 6 // 5), fill=color)
    draw.ellipse((x + scale // 5, y - scale * 4 // 3, x + scale // 3, y - scale * 6 // 5), fill=color)
    mouth_y = y - scale * 2 // 3
    if mood == "wow":
        draw.ellipse((x - scale // 5, mouth_y - scale // 6, x + scale // 5, mouth_y + scale // 5), outline=color, width=max(2, scale // 10))
    else:
        draw.arc((x - scale // 3, mouth_y - scale // 4, x + scale // 3, mouth_y + scale // 4), 0, 180, fill=color, width=max(2, scale // 10))
    draw.line((x, y, x, y + scale * 2), fill=color, width=max(4, scale // 6))
    draw.line((x, y + scale // 2, x - scale * 2, y + scale), fill=color, width=max(4, scale // 6))
    draw.line((x, y + scale // 2, x + scale * 2, y + scale), fill=color, width=max(4, scale // 6))
    draw.line((x, y + scale * 2, x - scale, y + scale * 3), fill=color, width=max(4, scale // 6))
    draw.line((x, y + scale * 2, x + scale, y + scale * 3), fill=color, width=max(4, scale // 6))


def _paper_label(draw: ImageDraw.ImageDraw, text: str, box: Tuple[int, int, int, int], fill: str, color: str = PAPER_INK) -> None:
    draw.rounded_rectangle(box, radius=14, fill=fill, outline=PAPER_INK, width=4)
    _draw_text_box(draw, text, (box[0] + 14, box[1] + 4, box[2] - 14, box[3] - 4), 30, 20, color=color, bold=True)


def _draw_paper_visual(draw: ImageDraw.ImageDraw, slide: object, box: Tuple[int, int, int, int], index: int) -> None:
    left, top, right, bottom = box
    width, height = right - left, bottom - top
    visual = slide.visual
    draw.polygon([(left + 10, top + 22), (right - 8, top), (right, bottom - 20), (left, bottom)], fill="#FFFDF5", outline=PAPER_INK)
    _paper_tape(draw, left + width // 2 - 90, top - 12, 180, PAPER_LIME if index % 2 else PAPER_PINK)
    if visual == "cover_hero":
        _stick_person(draw, (left + 160, top + height // 2 - 20), 44, PAPER_INK, "wow")
        draw.text((left + 65, bottom - 85), "ONE MODEL?", font=_marker_font(34), fill=PAPER_BLUE)
        card_w = 135
        for item, (label, color) in enumerate(zip(("SOL", "TERRA", "LUNA"), (PAPER_LIME, PAPER_CORAL, PAPER_BLUE))):
            x = right - 3 * card_w - 75 + item * (card_w + 8)
            draw.rounded_rectangle((x, top + 120 + item * 15, x + card_w, bottom - 100 + item * 8), radius=15, fill=color, outline=PAPER_INK, width=4)
            draw.text((x + 18, top + 150 + item * 15), label, font=_marker_font(26), fill=PAPER_INK)
        draw.line((left + 260, top + height // 2, right - 450, top + height // 2), fill=PAPER_INK, width=6)
        draw.polygon([(right - 450, top + height // 2), (right - 480, top + height // 2 - 18), (right - 480, top + height // 2 + 18)], fill=PAPER_INK)
    elif visual in {"versus_cover", "control_split", "price_split", "input_split", "mental_model", "threshold_split", "tension_scale"}:
        mid = left + width // 2
        draw.line((mid, top + 65, mid, bottom - 35), fill=PAPER_INK, width=5)
        left_label, right_label = ("FABLE 5", "GPT-5.6") if "fable" in slide.headline.lower() or visual in {"versus_cover", "price_split", "input_split", "control_split"} else ("OLD TAKE", "NEW TAKE")
        _paper_label(draw, left_label, (left + 30, top + 55, mid - 20, top + 120), PAPER_PINK)
        _paper_label(draw, right_label, (mid + 20, top + 55, right - 30, top + 120), PAPER_LIME)
        _stick_person(draw, (left + width // 4, top + height // 2), 42, PAPER_INK, "wow")
        _stick_person(draw, (left + width * 3 // 4, top + height // 2), 42, PAPER_INK)
        draw.text((mid - 42, bottom - 110), "VS", font=_marker_font(54), fill=PAPER_BLUE)
    elif visual in {"three_tiers", "tier_sol", "tier_terra", "tier_luna", "risk_signal"}:
        labels = ("SOL", "TERRA", "LUNA")
        colors = (PAPER_LIME, PAPER_CORAL, PAPER_BLUE)
        gap = 18
        card_w = (width - 80 - gap * 2) // 3
        for position, (label, color) in enumerate(zip(labels, colors)):
            x = left + 40 + position * (card_w + gap)
            draw.rounded_rectangle((x, top + 85, x + card_w, bottom - 65), radius=18, fill=color, outline=PAPER_INK, width=5)
            _draw_text_box(draw, label, (x + 8, top + 105, x + card_w - 8, top + 205), 40, 24, color=PAPER_INK, bold=True)
            draw.ellipse((x + card_w // 2 - 35, top + 225, x + card_w // 2 + 35, top + 295), fill=PAPER_CREAM, outline=PAPER_INK, width=4)
    elif visual in {"context_tie", "single_frontier"}:
        if visual == "single_frontier":
            center = (left + width // 2, top + height // 2)
            for radius, color in ((180, PAPER_PINK), (125, PAPER_CREAM), (65, PAPER_LIME)):
                draw.ellipse((center[0] - radius, center[1] - radius, center[0] + radius, center[1] + radius), fill=color, outline=PAPER_INK, width=4)
            draw.line((center[0] - 230, center[1] + 180, center[0], center[1]), fill=PAPER_BLUE, width=12)
        else:
            _paper_label(draw, "1M", (left + 70, top + 110, left + width // 2 - 25, bottom - 105), PAPER_PINK)
            _paper_label(draw, "1.05M", (left + width // 2 + 25, top + 110, right - 70, bottom - 105), PAPER_LIME)
            draw.text((left + width // 2 - 38, bottom - 105), "≈", font=_marker_font(64), fill=PAPER_BLUE)
    elif visual in {"calculator_receipt", "price_fable", "price_gpt", "proof_receipt", "cost_iceberg"}:
        receipt = (left + 95, top + 50, right - 75, bottom - 45)
        draw.rectangle(receipt, fill="#FFFDF5", outline=PAPER_INK, width=5)
        label = {"price_fable": "$50 / MTOK", "price_gpt": "$30 / MTOK", "calculator_receipt": "$2,000 GAP", "cost_iceberg": "PRICE ≠ COST"}.get(visual, "OFFICIAL SOURCE")
        _paper_label(draw, label, (receipt[0] + 35, receipt[1] + 35, receipt[2] - 35, receipt[1] + 115), PAPER_LIME if index % 2 else PAPER_PINK)
        for row in range(4):
            y = receipt[1] + 165 + row * 52
            draw.line((receipt[0] + 40, y, receipt[2] - 40 - (row % 2) * 80, y), fill=PAPER_INK, width=7)
        draw.line((receipt[0] + 40, receipt[3] - 65, receipt[2] - 40, receipt[3] - 65), fill=PAPER_CORAL, width=12)
    elif visual in {"control_split", "system_layers"}:
        pass
    elif visual == "save_card":
        draw.rounded_rectangle((left + 100, top + 90, right - 100, bottom - 70), radius=28, fill=PAPER_BLUE, outline=PAPER_INK, width=6)
        draw.polygon([(left + width // 2 - 75, top + 150), (left + width // 2 + 75, top + 150), (left + width // 2 + 75, bottom - 150), (left + width // 2, bottom - 210), (left + width // 2 - 75, bottom - 150)], fill=PAPER_LIME, outline=PAPER_INK)
        draw.text((left + 140, bottom - 145), "SAVE + SEND", font=_marker_font(44), fill=PAPER_CREAM)
    else:
        labels = ("CLAIM", "MECHANISM", "SO WHAT?")
        for row, label in enumerate(labels):
            y = top + 75 + row * max(95, (height - 150) // 3)
            _paper_label(draw, label, (left + 55 + row * 18, y, right - 55 - row * 18, y + 70), (PAPER_LIME, PAPER_PINK, PAPER_BLUE)[row])
            if row < 2:
                draw.line((left + width // 2, y + 72, left + width // 2 + 25, y + 92), fill=PAPER_INK, width=5)


def _render_paper_slide(
    plan: ContentPlan,
    index: int,
    target: str,
    path: Path,
    headline_override: Optional[str] = None,
) -> Dict[str, object]:
    profile = TARGET_PROFILES[target]
    width, height = int(profile["width"]), int(profile["height"])
    safe = tuple(profile["safe"])
    slide = plan.slides[index]
    cover = index == 0
    accent = (PAPER_LIME, PAPER_PINK, PAPER_CORAL, PAPER_BLUE)[index % 4]
    image = _paper_background((width, height), index)
    draw = ImageDraw.Draw(image)
    draw.text((safe[0], safe[1]), "CONTENTMAXXER // FIELD NOTES", font=_font(21, bold=True), fill=PAPER_INK)
    cue = "SWIPE >" if cover else f"{index + 1:02d}/{len(plan.slides):02d}"
    cue_width = int(draw.textlength(cue, font=_marker_font(24)))
    draw.text((safe[2] - cue_width, safe[1]), cue, font=_marker_font(24), fill=PAPER_BLUE)
    eyebrow = slide.eyebrow or "INTERNET BRIEF"
    tag_font = _font(17, bold=True)
    tag_width = min(440, int(draw.textlength(eyebrow, font=tag_font)) + 38)
    tag_box = (safe[0], safe[1] + 48, safe[0] + tag_width, safe[1] + 94)
    draw.rounded_rectangle(tag_box, radius=12, fill=accent, outline=PAPER_INK, width=3)
    draw.text((tag_box[0] + 17, tag_box[1] + 12), eyebrow, font=tag_font, fill=PAPER_INK)
    vertical = height / width > 1.5
    if vertical:
        title_box = (safe[0], 285, safe[2], 700)
        visual_box = (safe[0], 750, safe[2], 1260)
        body_box = (safe[0], 1300, safe[2], 1470)
        source_box = (safe[0], 1530, safe[2], safe[3])
        title_sizes, body_sizes = (88, 46), (36, 24)
    else:
        title_box = (safe[0], 205, safe[2], 500)
        visual_box = (safe[0], 530, safe[2], 900)
        body_box = (safe[0], 925, safe[2], 1080)
        source_box = (safe[0], 1140, safe[2], safe[3])
        title_sizes, body_sizes = (72, 40), (31, 22)
    headline = headline_override or slide.headline
    title_meta = _draw_paper_headline(draw, headline, title_box, title_sizes[0], title_sizes[1], slide.accent_terms, accent)
    _draw_paper_visual(draw, slide, visual_box, index)
    body_meta = _draw_text_box(draw, slide.body, body_box, body_sizes[0], body_sizes[1], color=PAPER_INK, bold=True)
    source_meta = _draw_text_box(draw, "SOURCE // " + slide.source_label, source_box, 20, 18, color="#655D50", bold=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, optimize=True)
    return {
        "id": slide.id, "path": path.name, "width": width, "height": height, "safe_zone": list(safe),
        "text_boxes": [title_meta, body_meta, source_meta], "claim_ids": slide.claim_ids, "role": slide.role,
        "template": slide.visual, "transition": slide.transition, "engagement_trigger": slide.engagement_trigger,
        "headline_words": len(headline.split()), "body_words": len(slide.body.split()), "swipe_cue": cover,
        "visual_asset": "code_native_paper_collage", "palette": "paper_meme_v1",
    }


def _render_slide(
    plan: ContentPlan,
    index: int,
    target: str,
    path: Path,
    hero_path: Optional[Path] = None,
    headline_override: Optional[str] = None,
) -> Dict[str, object]:
    if plan.visual_theme == "paper_meme_v1":
        return _render_paper_slide(plan, index, target, path, headline_override=headline_override)
    profile = TARGET_PROFILES[target]
    width, height = int(profile["width"]), int(profile["height"])
    safe = tuple(profile["safe"])
    slide = plan.slides[index]
    cover = index == 0
    controls = any(word in plan.topic.lower() for word in ("capability", "control", "safety", "cyber", "bio"))
    accent = EDITORIAL_ORANGE if controls else EDITORIAL_GOLD
    image = _editorial_background(plan, (width, height), hero_path, cover, index)
    draw = ImageDraw.Draw(image)
    _draw_editorial_header(draw, slide, index, len(plan.slides), safe, accent, cover)
    vertical = height / width > 1.5
    if cover and vertical:
        title_box = (safe[0], 1000, safe[2], 1385)
        body_box = (safe[0], 1400, safe[2], 1505)
        source_box = (safe[0], 1530, safe[2], safe[3])
        title_sizes, body_sizes = (108, 54), (38, 25)
        visual_box = None
    elif cover:
        title_box = (safe[0], 700, safe[2], 1055)
        body_box = (safe[0], 1060, safe[2], 1140)
        source_box = (safe[0], 1160, safe[2], safe[3])
        title_sizes, body_sizes = (94, 50), (34, 23)
        visual_box = None
    elif vertical:
        title_box = (safe[0], 240, safe[2], 610)
        visual_box = (safe[0], 630, safe[2], 1190)
        body_box = (safe[0], 1210, safe[2], 1455)
        source_box = (safe[0], 1510, safe[2], safe[3])
        title_sizes, body_sizes = (92, 48), (38, 25)
    else:
        title_box = (safe[0], 170, safe[2], 455)
        visual_box = (safe[0], 475, safe[2], 930)
        body_box = (safe[0], 950, safe[2], 1115)
        source_box = (safe[0], 1160, safe[2], safe[3])
        title_sizes, body_sizes = (78, 42), (34, 23)
    headline = headline_override or slide.headline
    title_meta = _draw_editorial_headline(draw, headline, title_box, title_sizes[0], title_sizes[1], slide.accent_terms, accent)
    if visual_box:
        _draw_editorial_visual(draw, slide, visual_box, accent)
    body_meta = _draw_text_box(draw, slide.body.upper(), body_box, body_sizes[0], body_sizes[1], color=EDITORIAL_INK, bold=True)
    source_text = "SOURCE  " + slide.source_label
    source_meta = _draw_text_box(draw, source_text, source_box, 20, 18, color="#B7A995", bold=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, optimize=True)
    return {
        "id": slide.id,
        "path": path.name,
        "width": width,
        "height": height,
        "safe_zone": list(safe),
        "text_boxes": [title_meta, body_meta, source_meta],
        "claim_ids": slide.claim_ids,
        "role": slide.role,
        "template": slide.visual,
        "transition": slide.transition,
        "engagement_trigger": slide.engagement_trigger,
        "headline_words": len(headline.split()),
        "body_words": len(slide.body.split()),
        "swipe_cue": cover,
        "visual_asset": hero_path.name if hero_path else "generated_editorial_backdrop",
        "palette": plan.visual_theme,
    }


def render_carousel(plan: ContentPlan, job_dir: Path, targets: Iterable[str]) -> Dict[str, object]:
    normalized: List[str] = []
    for target in targets:
        if target == "all":
            normalized.extend(["9:16", "4:5"])
        elif target in TARGET_PROFILES:
            normalized.append(target)
        else:
            raise ValueError(f"unknown target profile: {target}")
    normalized = list(dict.fromkeys(normalized or ["9:16", "4:5"]))
    variants: Dict[str, object] = {}
    hero_path = _copy_hero(plan, job_dir)
    for target in normalized:
        profile = TARGET_PROFILES[target]
        group = str(profile["group"])
        output_dir = job_dir / "carousel" / group
        output_dir.mkdir(parents=True, exist_ok=True)
        paths: List[Path] = []
        slide_metadata: List[Dict[str, object]] = []
        for index in range(len(plan.slides)):
            path = output_dir / f"slide-{index + 1:02d}.png"
            slide_metadata.append(_render_slide(plan, index, target, path, hero_path=hero_path))
            paths.append(path)
        selected = next((item for item in plan.hook_candidates if item["text"] == plan.hook), None)
        ordered_hooks = ([selected] if selected else []) + [
            item for item in sorted(plan.hook_candidates, key=lambda candidate: candidate["score"], reverse=True) if not selected or item["text"] != selected["text"]
        ]
        cover_variants: List[Dict[str, object]] = []
        cover_paths: List[Path] = []
        variants_dir = output_dir / "cover-variants"
        for candidate_index, candidate in enumerate(ordered_hooks[:3]):
            variant_path = variants_dir / f"cover-{chr(97 + candidate_index)}.png"
            _render_slide(plan, 0, target, variant_path, hero_path=hero_path, headline_override=str(candidate["text"]))
            cover_paths.append(variant_path)
            cover_variants.append({"path": portable(variant_path, job_dir), "hook": candidate["text"], "score": candidate["score"], "style": candidate["style"]})
        cover_contact = make_contact_sheet(cover_paths, variants_dir / "contact-sheet.png", columns=3, thumb_width=260)
        contact = make_contact_sheet(paths, output_dir / "contact-sheet.png", columns=2, thumb_width=320)
        metadata_path = output_dir / "metadata.json"
        payload = {
            "target": target,
            "profile": profile,
            "count": len(paths),
            "slides": slide_metadata,
            "contact_sheet": contact.name,
            "hero_asset": portable(hero_path, job_dir) if hero_path else None,
            "cover_variants": cover_variants,
            "cover_variants_contact_sheet": portable(cover_contact, job_dir),
            "palette": plan.visual_theme,
        }
        write_json(metadata_path, payload)
        variants[target] = {
            "directory": portable(output_dir, job_dir),
            "metadata": portable(metadata_path, job_dir),
            "contact_sheet": portable(contact, job_dir),
            "slides": [portable(path, job_dir) for path in paths],
            "cover_variants": cover_variants,
            "cover_variants_contact_sheet": portable(cover_contact, job_dir),
        }
    return {"variants": variants, "count": len(plan.slides), "hero_asset": portable(hero_path, job_dir) if hero_path else None}
