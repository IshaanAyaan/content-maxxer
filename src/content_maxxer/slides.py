from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from content_maxxer.backend import (
    BACKGROUND,
    BLUE,
    GREEN,
    MUTED,
    PINK,
    QUALITY_SCALE,
    TEAL,
    TEXT,
    YELLOW,
    draw_centered_text,
    slugify,
    text_height,
    wrap_text,
)


SLIDE_SIZES = {
    "tiktok": (1080, 1920),
    "reels": (1080, 1920),
    "instagram": (1080, 1350),
    "square": (1080, 1080),
}

INK = (12, 18, 30)
PANEL = (16, 25, 42)
LINE = (45, 62, 88)
SOFT = (99, 114, 138)
WHITE = (252, 252, 249)
CREAM = (246, 241, 226)
ORANGE = (251, 146, 60)
VIOLET = (167, 139, 250)


@dataclass
class Slide:
    slide_id: str
    role: str
    eyebrow: str
    headline: str
    body: str
    visual: str
    bullets: list[str]
    footer: str


@dataclass
class SlideDeck:
    title: str
    slug: str
    source: str
    platform: str
    width: int
    height: int
    thesis: str
    audience_action: str
    slides: list[Slide]


def build_slide_deck(
    *,
    title: str,
    idea: str,
    slug: str | None = None,
    source: str = "",
    platform: str = "tiktok",
    slide_count: int = 8,
) -> SlideDeck:
    slug = slug or slugify(title)
    width, height = SLIDE_SIZES.get(platform, SLIDE_SIZES["tiktok"])
    key = f"{title} {idea}".lower()
    if "agent" in key and any(term in key for term in ["reliability", "benchmark", "hype", "employee", "fail"]):
        return agent_reliability_slide_deck(title, slug, source, platform, width, height)
    if "large language model" in key or "llm" in key or "language model" in key:
        return llm_slide_deck(title, slug, source, platform, width, height)
    if "nexus" in key:
        return nexus_slide_deck(title, slug, source, platform, width, height)
    if "gradient" in key or "descent" in key:
        return gradient_slide_deck(title, slug, source, platform, width, height)
    return generic_slide_deck(title, idea, slug, source, platform, width, height, slide_count)


def llm_slide_deck(title: str, slug: str, source: str, platform: str, width: int, height: int) -> SlideDeck:
    slides = [
        Slide(
            "01_hook",
            "hook",
            "LLMs, minus the fog",
            "It is not reading words.",
            "A language model turns text into tiny IDs, then learns what should come next.",
            "token_split",
            ["text", "tokens", "numbers", "next token"],
            "Swipe for the whole loop",
        ),
        Slide(
            "02_map",
            "map",
            "The whole loop",
            "Text goes in. One token comes out.",
            "Everything else is the machinery that makes that next-token guess smarter.",
            "pipeline",
            ["tokenize", "mix context", "predict", "repeat"],
            "Keep one loop in your head",
        ),
        Slide(
            "03_tokens",
            "mechanism",
            "Step 1",
            "Text becomes tokens.",
            "Tokens are chunks the model can count. Some are words. Some are pieces.",
            "token_cards",
            ["Large", "language", "models", "work"],
            "The model sees IDs",
        ),
        Slide(
            "04_vectors",
            "mechanism",
            "Step 2",
            "Tokens become vectors.",
            "Each token becomes a point in a learned space where meaning can be compared.",
            "vector_space",
            ["token", "embedding", "meaning space"],
            "Meaning becomes geometry",
        ),
        Slide(
            "05_attention",
            "mechanism",
            "Step 3",
            "Attention decides what matters.",
            "Every token looks at the other tokens and borrows the context it needs.",
            "attention_arcs",
            ["query", "key", "value", "context"],
            "This is the context engine",
        ),
        Slide(
            "06_layers",
            "mechanism",
            "Step 4",
            "Layers refine the guess.",
            "Transformer blocks keep mixing and reshaping the vectors until the next token is clearer.",
            "layer_stack",
            ["attention", "MLP", "residual", "repeat"],
            "A little clearer each layer",
        ),
        Slide(
            "07_prediction",
            "payoff",
            "Step 5",
            "It picks a next token.",
            "The model scores many possible next tokens, then samples one from the distribution.",
            "probability_bars",
            ["tokens", "words", "pizza"],
            "One choice, many possibilities",
        ),
        Slide(
            "08_takeaway",
            "takeaway",
            "The mental model",
            "LLMs are next-token engines.",
            "The magic is not one giant answer. It is a tiny prediction loop repeated very fast.",
            "loop",
            ["predict", "append", "repeat"],
            "Save this loop",
        ),
    ]
    return SlideDeck(
        title=title,
        slug=slug,
        source=source or "Concept prompt",
        platform=platform,
        width=width,
        height=height,
        thesis="Large language models are a repeated next-token prediction loop built on tokens, vectors, attention, and transformer layers.",
        audience_action="Swipe away understanding the loop, not memorizing jargon.",
        slides=slides,
    )


def nexus_slide_deck(title: str, slug: str, source: str, platform: str, width: int, height: int) -> SlideDeck:
    slides = [
        Slide("01_hook", "hook", "Nexus in one picture", "Same loss. Different model.", "Two models can tie on pretraining loss and still land in different downstream regions.", "basins", ["same score", "different basin"], "The path matters"),
        Slide("02_problem", "problem", "The hidden problem", "Loss is a scoreboard.", "A scoreboard tells you the number. It does not tell you where training landed.", "score_vs_route", ["score", "route"], "Scores hide geometry"),
        Slide("03_valley", "mechanism", "Why it matters", "Downstream tasks live in valleys.", "If a model lands near useful downstream valleys, adaptation gets easier.", "downstream_valley", ["near", "far"], "Location matters"),
        Slide("04_agreement", "mechanism", "The Nexus question", "Do tasks pull together?", "Nexus asks whether task directions agree or fight with each other during training.", "task_arrows", ["conflict", "agreement"], "Agreement is signal"),
        Slide("05_inner_loop", "mechanism", "How it checks", "Clone. Step. Measure.", "Temporary inner steps estimate how training moves the model under task batches.", "inner_loop", ["clone", "batch steps", "g_hat"], "Measure movement"),
        Slide("06_takeaway", "takeaway", "Remember this", "Nexus changes the route.", "The paper is about shaping the training path, not just lowering one final score.", "route_takeaway", ["route", "not just score"], "Save the visual"),
    ]
    return SlideDeck(
        title=title,
        slug=slug,
        source=source or "https://arxiv.org/pdf/2604.09258",
        platform=platform,
        width=width,
        height=height,
        thesis="Nexus explains why the route through optimization matters even when final loss looks the same.",
        audience_action="Swipe away seeing loss as a landscape route, not a single number.",
        slides=slides,
    )


def gradient_slide_deck(title: str, slug: str, source: str, platform: str, width: int, height: int) -> SlideDeck:
    slides = [
        Slide("01_hook", "hook", "Gradient descent", "It is just controlled downhill movement.", "The trick is not knowing the whole map. It is reading the slope right here.", "loss_curve", ["slope", "step", "repeat"], "One loop explains it"),
        Slide("02_slope", "mechanism", "Step 1", "Read the local slope.", "The gradient tells the model which direction increases loss fastest.", "slope_arrow", ["gradient", "direction"], "Move the other way"),
        Slide("03_step", "mechanism", "Step 2", "Take a small step.", "The learning rate controls whether the step is useful or chaotic.", "step_size", ["too big", "small step"], "Size matters"),
        Slide("04_repeat", "mechanism", "Step 3", "Repeat until it settles.", "Many small corrections can turn a rough guess into a useful solution.", "settle_path", ["repeat", "settle"], "Local correction compounds"),
        Slide("05_takeaway", "takeaway", "The mental model", "Measure. Step. Repeat.", "That loop is the simplest way to understand model training.", "loop", ["measure", "step", "repeat"], "Save the loop"),
    ]
    return SlideDeck(
        title=title,
        slug=slug,
        source=source or "Concept prompt",
        platform=platform,
        width=width,
        height=height,
        thesis="Gradient descent is repeated local slope measurement plus controlled movement.",
        audience_action="Swipe away remembering measure, step, repeat.",
        slides=slides,
    )


def agent_reliability_slide_deck(title: str, slug: str, source: str, platform: str, width: int, height: int) -> SlideDeck:
    slides = [
        Slide(
            "01_hook",
            "hook",
            "AI agent hype check",
            "Would you hire a 1-in-3 failure?",
            "Agents are getting scary good. But reliability is still the part everyone tries to skip.",
            "pass_fail_grid",
            ["pass", "pass", "fail"],
            "Swipe before you buy the hype",
        ),
        Slide(
            "02_progress",
            "context",
            "The progress is real",
            "Agents jumped from 12% to 66%.",
            "OSWorld jumped from about 12% to 66.3%. Huge progress. Still about one failure in three.",
            "benchmark_bars",
            ["12%", "66.3%", "human"],
            "Better is not reliable",
        ),
        Slide(
            "03_benchmark_trap",
            "problem",
            "The benchmark trap",
            "The leaderboard is lying by omission.",
            "One score hides cost, consistency, predictability, and how bad failure gets.",
            "scorecard_crack",
            ["score", "cost", "consistency", "severity"],
            "A score is not a product",
        ),
        Slide(
            "04_reliability",
            "mechanism",
            "The missing test",
            "Reliability is not accuracy.",
            "A useful agent should work across reruns, small changes, uncertainty, and bad outcomes.",
            "reliability_quadrants",
            ["consistency", "robustness", "predictability", "safety"],
            "This is the missing test",
        ),
        Slide(
            "05_cost",
            "mechanism",
            "The cost trap",
            "Spends $8 to save $2?",
            "Princeton's point: accuracy and cost belong on the same chart.",
            "cost_accuracy",
            ["accuracy", "cost", "useful"],
            "Expensive magic is still expensive",
        ),
        Slide(
            "06_where_it_works",
            "filter",
            "Where agents actually work",
            "Useful agents are boxed in.",
            "Narrow, checkable, reversible tasks are where agent workflows start to make sense.",
            "guardrails",
            ["narrow", "checkable", "reversible"],
            "Box the task first",
        ),
        Slide(
            "07_build",
            "solution",
            "The useful wrapper",
            "Do not buy autonomy. Build supervision.",
            "Useful agents need logs, verifiers, permissions, tools, and human review.",
            "supervision_loop",
            ["tools", "logs", "verifier", "human"],
            "The wrapper matters",
        ),
        Slide(
            "08_takeaway",
            "takeaway",
            "The better question",
            "Stop asking if agents are smart.",
            "Ask a better question: can this system fail safely when it is wrong?",
            "safe_fail_loop",
            ["try", "check", "limit damage"],
            "Save this before the next demo",
        ),
    ]
    return SlideDeck(
        title=title,
        slug=slug,
        source=source or "Stanford AI Index 2026; Towards a Science of AI Agent Reliability; AI Agents That Matter",
        platform=platform,
        width=width,
        height=height,
        thesis="AI agents are improving fast, but real adoption depends on reliability, cost, and safe failure rather than benchmark hype.",
        audience_action="Swipe away with a sharper test for agent claims: can it fail safely and consistently?",
        slides=slides,
    )


def generic_slide_deck(
    title: str,
    idea: str,
    slug: str,
    source: str,
    platform: str,
    width: int,
    height: int,
    slide_count: int,
) -> SlideDeck:
    count = max(5, min(slide_count, 9))
    clean = " ".join(idea.split()) or title
    slides = [
        Slide("01_hook", "hook", title, "Stop memorizing the definition.", "Learn the one transformation behind the idea instead.", "split_compare", ["before", "after"], "Swipe for the model"),
        Slide("02_map", "map", "The map", "One object changes state.", clean[:132], "pipeline", ["input", "mechanism", "output"], "Watch the object"),
        Slide("03_mechanism", "mechanism", "The mechanism", "This changes that.", "The useful part is the causal chain, not the label.", "node_chain", ["cause", "change", "effect"], "Follow the arrows"),
        Slide("04_example", "example", "Tiny example", "Make it concrete.", "A good explainer starts with one small case before the abstraction.", "split_compare", ["specific", "general"], "Concrete first"),
        Slide("05_takeaway", "takeaway", "Remember this", f"{title} is a transformation.", "If you can picture the transformation, the definition becomes easier.", "loop", ["see it", "name it", "use it"], "Save the visual"),
    ][:count]
    return SlideDeck(
        title=title,
        slug=slug,
        source=source or "Concept prompt",
        platform=platform,
        width=width,
        height=height,
        thesis=f"{title} should be understood as one transformation, not a memorized definition.",
        audience_action="Swipe away with a visual model.",
        slides=slides,
    )


def write_slide_deck_files(job_dir: Path, deck: SlideDeck, idea: str) -> None:
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "slide_brief.md").write_text(slide_brief_markdown(deck, idea), encoding="utf-8")
    (job_dir / "slide_storyboard.md").write_text(slide_storyboard_markdown(deck), encoding="utf-8")
    (job_dir / "slide_plan.json").write_text(json.dumps(asdict(deck), indent=2) + "\n", encoding="utf-8")


def slide_brief_markdown(deck: SlideDeck, idea: str) -> str:
    lines = [
        f"# Slide Brief: {deck.title}",
        "",
        "## Input",
        "",
        idea.strip(),
        "",
        "## Source",
        "",
        deck.source,
        "",
        "## Thesis",
        "",
        deck.thesis,
        "",
        "## Audience action",
        "",
        deck.audience_action,
        "",
    ]
    return "\n".join(lines)


def slide_storyboard_markdown(deck: SlideDeck) -> str:
    lines = [
        f"# Slide Storyboard: {deck.title}",
        "",
        "| # | Role | Headline | Visual | Body |",
        "| ---: | --- | --- | --- | --- |",
    ]
    for index, slide in enumerate(deck.slides, start=1):
        body = slide.body.replace("|", "/")
        lines.append(f"| {index} | {slide.role} | {slide.headline} | {slide.visual} | {body} |")
    lines.append("")
    return "\n".join(lines)


def render_slide_deck(job_dir: Path, deck: SlideDeck, *, quality: str = "production") -> Path:
    try:
        from PIL import Image, ImageDraw
    except ImportError as error:
        raise SystemExit("Missing render dependency. Install with: pip install pillow") from error

    scale = QUALITY_SCALE.get(quality, QUALITY_SCALE["production"])
    width = int(deck.width * scale)
    height = int(deck.height * scale)
    export_dir = job_dir / "exports" / f"slides_{deck.platform}_{quality}"
    export_dir.mkdir(parents=True, exist_ok=True)
    fonts = load_slide_fonts(width)
    slide_paths = []
    for index, slide in enumerate(deck.slides, start=1):
        image = Image.new("RGB", (width, height), INK)
        draw = ImageDraw.Draw(image)
        draw_slide_background(draw, width, height, index)
        draw_slide(draw, width, height, deck, slide, index, fonts)
        output = export_dir / f"{index:02d}_{slide.slide_id}.png"
        image.save(output)
        slide_paths.append(output)

    manifest = {
        **asdict(deck),
        "quality": quality,
        "output_dir": str(export_dir),
        "width": width,
        "height": height,
        "slide_paths": [str(path) for path in slide_paths],
        "renderer": "slide_carousel_v1",
    }
    (export_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    contact_sheet(slide_paths, export_dir / "contact_sheet.png")
    return export_dir


def draw_slide(draw: Any, width: int, height: int, deck: SlideDeck, slide: Slide, index: int, fonts: dict[str, Any]) -> None:
    margin = int(width * 0.078)
    top = int(height * 0.065)
    draw.text((margin, top), slide.eyebrow, font=fonts["eyebrow"], fill=MUTED)
    draw.text((width - margin - 68, top), f"{index:02}", font=fonts["number"], fill=SOFT)

    headline_y = top + int(height * 0.07)
    draw_multiline(draw, slide.headline, (margin, headline_y), fonts["headline"], WHITE, width - margin * 2, max_lines=3, spacing=8)

    visual_box = (
        margin,
        int(height * 0.39),
        width - margin,
        int(height * 0.73),
    )
    draw_slide_visual(draw, visual_box, slide, fonts)

    body_y = int(height * 0.77)
    draw_multiline(draw, slide.body, (margin, body_y), fonts["body"], CREAM, width - margin * 2, max_lines=3, spacing=8)
    footer_y = height - int(height * 0.065)
    draw.text((margin, footer_y), slide.footer, font=fonts["footer"], fill=MUTED)
    draw_progress_dots(draw, width, height, len(deck.slides), index)


def draw_slide_background(draw: Any, width: int, height: int, index: int) -> None:
    accents = [TEAL, BLUE, YELLOW, GREEN, PINK, VIOLET, ORANGE]
    accent = accents[(index - 1) % len(accents)]
    for y in range(height):
        mix = y / max(1, height - 1)
        fill = (
            int(INK[0] + accent[0] * 0.03 * mix),
            int(INK[1] + accent[1] * 0.03 * mix),
            int(INK[2] + accent[2] * 0.03 * mix),
        )
        draw.line((0, y, width, y), fill=fill)
    grid = (23, 33, 52)
    spacing = max(56, width // 9)
    for x in range(0, width, spacing):
        draw.line((x, 0, x, height), fill=grid, width=1)
    for y in range(0, height, spacing):
        draw.line((0, y, width, y), fill=grid, width=1)


def draw_slide_visual(draw: Any, box: tuple[int, int, int, int], slide: Slide, fonts: dict[str, Any]) -> None:
    visual = slide.visual
    if visual in {"token_split", "token_cards"}:
        draw_token_visual(draw, box, slide.bullets, fonts)
    elif visual == "pipeline":
        draw_pipeline_visual(draw, box, slide.bullets, fonts)
    elif visual == "vector_space":
        draw_vector_space(draw, box, fonts)
    elif visual == "attention_arcs":
        draw_attention_visual(draw, box, fonts)
    elif visual == "layer_stack":
        draw_layer_visual(draw, box, fonts)
    elif visual == "probability_bars":
        draw_probability_visual(draw, box, slide.bullets, fonts)
    elif visual == "loop":
        draw_loop_visual(draw, box, slide.bullets, fonts)
    elif visual in {"basins", "score_vs_route", "downstream_valley", "route_takeaway"}:
        draw_basin_visual(draw, box, visual, fonts)
    elif visual == "task_arrows":
        draw_task_arrow_visual(draw, box, fonts)
    elif visual == "inner_loop":
        draw_inner_loop_visual(draw, box, fonts)
    elif visual in {"loss_curve", "slope_arrow", "step_size", "settle_path"}:
        draw_gradient_visual(draw, box, visual, fonts)
    elif visual == "node_chain":
        draw_pipeline_visual(draw, box, slide.bullets, fonts)
    elif visual == "pass_fail_grid":
        draw_pass_fail_grid(draw, box, fonts)
    elif visual == "benchmark_bars":
        draw_benchmark_bars(draw, box, fonts)
    elif visual == "scorecard_crack":
        draw_scorecard_crack(draw, box, fonts)
    elif visual == "reliability_quadrants":
        draw_reliability_quadrants(draw, box, slide.bullets, fonts)
    elif visual == "cost_accuracy":
        draw_cost_accuracy(draw, box, fonts)
    elif visual == "guardrails":
        draw_guardrails(draw, box, slide.bullets, fonts)
    elif visual == "supervision_loop":
        draw_supervision_loop(draw, box, slide.bullets, fonts)
    elif visual == "safe_fail_loop":
        draw_safe_fail_loop(draw, box, slide.bullets, fonts)
    else:
        draw_split_compare(draw, box, slide.bullets, fonts)


def draw_token_visual(draw: Any, box: tuple[int, int, int, int], labels: list[str], fonts: dict[str, Any]) -> None:
    x1, y1, x2, y2 = box
    prompt = (x1, y1 + 18, x2, y1 + 92)
    draw.rounded_rectangle(prompt, radius=20, fill=PANEL, outline=BLUE, width=4)
    draw_centered_text(draw, "Large language models predict tokens", center(prompt), fonts["small"], WHITE)
    tokens = labels if len(labels) >= 3 else ["Large", "language", "models", "tokens"]
    rects = row_rects(draw, tokens, fonts["small"], x1, x2, y1 + int((y2 - y1) * 0.72), gap=12)
    for index, rect in enumerate(rects):
        draw_card(draw, rect, tokens[index], fonts["small"], [TEAL, BLUE, YELLOW, GREEN, PINK][index % 5])
    draw_arrow(draw, center(prompt), ((x1 + x2) // 2, rects[0][1] - 26), TEAL, width=5)


def draw_pipeline_visual(draw: Any, box: tuple[int, int, int, int], labels: list[str], fonts: dict[str, Any]) -> None:
    x1, y1, x2, y2 = box
    labels = labels[:4] or ["input", "mechanism", "output"]
    rects = row_rects(draw, labels, fonts["small"], x1, x2, (y1 + y2) // 2, gap=22)
    for index, rect in enumerate(rects):
        draw_card(draw, rect, labels[index], fonts["small"], [TEAL, BLUE, YELLOW, GREEN][index % 4])
        if index < len(rects) - 1:
            draw_arrow(draw, (rect[2] + 8, center(rect)[1]), (rects[index + 1][0] - 8, center(rect)[1]), MUTED, width=4)


def draw_vector_space(draw: Any, box: tuple[int, int, int, int], fonts: dict[str, Any]) -> None:
    x1, y1, x2, y2 = box
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    draw.line((x1 + 40, cy, x2 - 40, cy), fill=LINE, width=3)
    draw.line((cx, y1 + 20, cx, y2 - 20), fill=LINE, width=3)
    points = [(-150, -70, "king", BLUE), (-88, 68, "queen", TEAL), (92, -42, "code", YELLOW), (146, 78, "token", GREEN)]
    for dx, dy, label, color in points:
        pt = (cx + dx, cy + dy)
        draw.ellipse((pt[0] - 10, pt[1] - 10, pt[0] + 10, pt[1] + 10), fill=color)
        draw.text((pt[0] + 16, pt[1] - 16), label, font=fonts["tiny"], fill=WHITE)
    draw_label(draw, "meaning space", (x1 + 24, y1 + 18), fonts, TEAL)


def draw_attention_visual(draw: Any, box: tuple[int, int, int, int], fonts: dict[str, Any]) -> None:
    labels = ["The", "model", "predicts", "tokens"]
    x1, y1, x2, y2 = box
    rects = row_rects(draw, labels, fonts["tiny"], x1 + 12, x2 - 12, (y1 + y2) // 2, gap=12)
    centers = [center(rect) for rect in rects]
    for index, rect in enumerate(rects):
        draw_card(draw, rect, labels[index], fonts["tiny"], YELLOW if index == 2 else TEAL)
    focus = centers[2]
    for index, source in enumerate([0, 1, 3]):
        arc_y = y1 + 38 + index * 24
        draw.line((centers[source][0], centers[source][1] - 40, centers[source][0], arc_y, focus[0], arc_y), fill=[BLUE, TEAL, GREEN][index], width=4)
        draw_arrow(draw, (focus[0], arc_y), (focus[0], focus[1] - 42), [BLUE, TEAL, GREEN][index], width=4)
    draw_label(draw, "context", (x1 + 18, y2 - 56), fonts, TEAL)


def draw_layer_visual(draw: Any, box: tuple[int, int, int, int], fonts: dict[str, Any]) -> None:
    x1, y1, x2, y2 = box
    blocks = [("attention", TEAL), ("MLP", YELLOW), ("residual", BLUE), ("repeat", GREEN)]
    block_h = int((y2 - y1) * 0.17)
    y = y1 + 20
    for label, color in blocks:
        rect = (x1 + 120, y, x2 - 120, y + block_h)
        draw.rounded_rectangle(rect, radius=22, fill=PANEL, outline=color, width=4)
        draw_centered_text(draw, label, center(rect), fonts["small"], WHITE)
        y += block_h + 22


def draw_probability_visual(draw: Any, box: tuple[int, int, int, int], labels: list[str], fonts: dict[str, Any]) -> None:
    x1, y1, x2, y2 = box
    labels = labels[:3] or ["tokens", "words", "pizza"]
    amounts = [0.82, 0.44, 0.16]
    colors = [GREEN, BLUE, PINK]
    for index, label in enumerate(labels):
        y = y1 + 52 + index * int((y2 - y1) * 0.23)
        draw.text((x1 + 16, y), label, font=fonts["small"], fill=WHITE)
        bar = (x1 + 190, y + 6, x2 - 18, y + 42)
        draw.rounded_rectangle(bar, radius=16, fill=PANEL)
        draw.rounded_rectangle((bar[0], bar[1], bar[0] + int((bar[2] - bar[0]) * amounts[index]), bar[3]), radius=16, fill=colors[index])
    draw_label(draw, "distribution", (x1 + 16, y1 + 4), fonts, YELLOW)


def draw_loop_visual(draw: Any, box: tuple[int, int, int, int], labels: list[str], fonts: dict[str, Any]) -> None:
    x1, y1, x2, y2 = box
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    radius_x = int((x2 - x1) * 0.34)
    radius_y = int((y2 - y1) * 0.28)
    draw.arc((cx - radius_x, cy - radius_y, cx + radius_x, cy + radius_y), start=25, end=340, fill=TEAL, width=7)
    draw_arrow(draw, (cx + radius_x - 34, cy - 14), (cx + radius_x, cy + 18), TEAL, width=6)
    points = [(cx, cy - radius_y), (cx + radius_x, cy), (cx, cy + radius_y)]
    for label, point, color in zip(labels[:3], points, [BLUE, GREEN, YELLOW]):
        draw_label(draw, label, (point[0] - 62, point[1] - 26), fonts, color)


def draw_basin_visual(draw: Any, box: tuple[int, int, int, int], visual: str, fonts: dict[str, Any]) -> None:
    x1, y1, x2, y2 = box
    left = (x1 + int((x2 - x1) * 0.32), y1 + int((y2 - y1) * 0.58))
    right = (x1 + int((x2 - x1) * 0.68), y1 + int((y2 - y1) * 0.45))
    draw_contours(draw, left, BLUE)
    draw_contours(draw, right, PINK)
    draw.line((x1 + 50, y1 + 48, left[0], left[1]), fill=BLUE, width=5)
    draw.line((x2 - 50, y1 + 64, right[0], right[1]), fill=PINK, width=5)
    if visual == "downstream_valley":
        target = (left[0] - 52, left[1] + 56)
        draw_contours(draw, target, GREEN, scale=0.58)
        draw_arrow(draw, right, target, MUTED, width=3)
        draw_arrow(draw, left, target, GREEN, width=5)
        draw_label(draw, "downstream", (target[0] - 68, target[1] + 42), fonts, GREEN)
    elif visual in {"score_vs_route", "route_takeaway"}:
        draw.line((x1 + 42, y2 - 52, x2 - 42, y2 - 52), fill=YELLOW, width=4)
        draw_label(draw, "score", (x1 + 44, y2 - 102), fonts, YELLOW)
        draw_label(draw, "route", (x2 - 140, y1 + 24), fonts, GREEN)
    else:
        draw_label(draw, "same loss", (x1 + 36, y2 - 95), fonts, YELLOW)
        draw_label(draw, "different basin", (x2 - 205, y2 - 95), fonts, PINK)


def draw_task_arrow_visual(draw: Any, box: tuple[int, int, int, int], fonts: dict[str, Any]) -> None:
    cx, cy = center(box)
    draw.ellipse((cx - 14, cy - 14, cx + 14, cy + 14), fill=YELLOW)
    for angle, color, label in [(150, BLUE, "task A"), (30, PINK, "task B"), (80, GREEN, "agreement")]:
        rad = math.radians(angle)
        end = (cx + int(190 * math.cos(rad)), cy - int(190 * math.sin(rad)))
        draw_arrow(draw, (cx, cy), end, color, width=6)
        draw_label(draw, label, (end[0] - 54, end[1] - 46), fonts, color)


def draw_inner_loop_visual(draw: Any, box: tuple[int, int, int, int], fonts: dict[str, Any]) -> None:
    labels = ["model", "clone", "batch", "g_hat"]
    draw_pipeline_visual(draw, box, labels, fonts)


def draw_gradient_visual(draw: Any, box: tuple[int, int, int, int], visual: str, fonts: dict[str, Any]) -> None:
    points = gradient_points(box)
    draw.line(points, fill=TEAL, width=7)
    if visual == "slope_arrow":
        dot = points[28]
        draw.ellipse((dot[0] - 12, dot[1] - 12, dot[0] + 12, dot[1] + 12), fill=YELLOW)
        draw_arrow(draw, (dot[0] - 80, dot[1] - 52), (dot[0] + 80, dot[1] + 52), YELLOW, width=5)
        draw_label(draw, "slope", (dot[0] - 92, dot[1] - 104), fonts, YELLOW)
    elif visual == "step_size":
        a, b, c = points[25], points[51], points[78]
        draw_arrow(draw, a, c, PINK, width=4)
        draw_arrow(draw, a, b, GREEN, width=6)
        draw_label(draw, "too big", (c[0] - 42, c[1] - 70), fonts, PINK)
        draw_label(draw, "small step", (b[0] - 58, b[1] + 32), fonts, GREEN)
    elif visual == "settle_path":
        path = [points[i] for i in [18, 32, 44, 53, 59]]
        draw.line(path, fill=GREEN, width=5)
        for point in path:
            draw.ellipse((point[0] - 9, point[1] - 9, point[0] + 9, point[1] + 9), fill=GREEN)
        draw_label(draw, "settle", (path[-1][0] + 18, path[-1][1] - 32), fonts, GREEN)
    else:
        draw_label(draw, "measure", (box[0] + 30, box[1] + 30), fonts, BLUE)
        draw_label(draw, "step", (box[2] - 140, box[1] + 30), fonts, GREEN)


def draw_split_compare(draw: Any, box: tuple[int, int, int, int], labels: list[str], fonts: dict[str, Any]) -> None:
    x1, y1, x2, y2 = box
    mid = (x1 + x2) // 2
    left = (x1 + 12, y1 + 34, mid - 18, y2 - 34)
    right = (mid + 18, y1 + 34, x2 - 12, y2 - 34)
    for rect, label, color in [(left, labels[0] if labels else "before", BLUE), (right, labels[1] if len(labels) > 1 else "after", GREEN)]:
        draw.rounded_rectangle(rect, radius=24, fill=PANEL, outline=color, width=4)
        draw_centered_text(draw, label, center(rect), fonts["small"], WHITE)


def draw_pass_fail_grid(draw: Any, box: tuple[int, int, int, int], fonts: dict[str, Any]) -> None:
    x1, y1, x2, y2 = box
    card_w = int((x2 - x1 - 42) / 3)
    y = y1 + int((y2 - y1) * 0.28)
    labels = [("task 1", "pass", GREEN), ("task 2", "pass", GREEN), ("task 3", "fail", PINK)]
    for index, (task, result, color) in enumerate(labels):
        left = x1 + index * (card_w + 21)
        rect = (left, y, left + card_w, y + int((y2 - y1) * 0.44))
        draw.rounded_rectangle(rect, radius=26, fill=PANEL, outline=color, width=5)
        draw_centered_text(draw, task, (center(rect)[0], rect[1] + 58), fonts["tiny"], MUTED)
        draw_centered_text(draw, result, center(rect), fonts["small"], WHITE)
    draw_label(draw, "real workflow", (x1 + 18, y2 - 58), fonts, YELLOW)


def draw_benchmark_bars(draw: Any, box: tuple[int, int, int, int], fonts: dict[str, Any]) -> None:
    x1, y1, x2, y2 = box
    labels = [("old agents", 0.12, BLUE), ("new agents", 0.663, TEAL), ("human", 0.72, GREEN)]
    bar_left = x1 + 230
    bar_right = x2 - 28
    for index, (label, amount, color) in enumerate(labels):
        y = y1 + 80 + index * 118
        draw.text((x1 + 24, y + 6), label, font=fonts["tiny"], fill=WHITE)
        draw.rounded_rectangle((bar_left, y, bar_right, y + 42), radius=20, fill=PANEL)
        draw.rounded_rectangle((bar_left, y, bar_left + int((bar_right - bar_left) * amount), y + 42), radius=20, fill=color)
        draw.text((bar_left + int((bar_right - bar_left) * amount) + 12, y + 2), f"{amount * 100:.0f}%", font=fonts["tiny"], fill=MUTED)
    draw_label(draw, "OSWorld", (x1 + 24, y1 + 18), fonts, YELLOW)


def draw_scorecard_crack(draw: Any, box: tuple[int, int, int, int], fonts: dict[str, Any]) -> None:
    x1, y1, x2, y2 = box
    card = (x1 + 68, y1 + 42, x2 - 68, y2 - 42)
    draw.rounded_rectangle(card, radius=30, fill=PANEL, outline=YELLOW, width=5)
    draw_centered_text(draw, "66%", (center(card)[0], card[1] + 110), fonts["headline"], WHITE)
    draw_centered_text(draw, "task success", (center(card)[0], card[1] + 205), fonts["small"], MUTED)
    crack = [(center(card)[0] - 20, card[1] + 18), (center(card)[0] + 12, card[1] + 105), (center(card)[0] - 8, card[1] + 180), (center(card)[0] + 28, card[3] - 32)]
    draw.line(crack, fill=PINK, width=5)
    for idx, label in enumerate(["cost", "consistency", "severity"]):
        draw_label(draw, label, (card[0] + 42 + idx * 185, card[3] - 86), fonts, [BLUE, TEAL, PINK][idx])


def draw_reliability_quadrants(draw: Any, box: tuple[int, int, int, int], labels: list[str], fonts: dict[str, Any]) -> None:
    x1, y1, x2, y2 = box
    mid_x = (x1 + x2) // 2
    mid_y = (y1 + y2) // 2
    draw.line((mid_x, y1 + 30, mid_x, y2 - 30), fill=LINE, width=4)
    draw.line((x1 + 30, mid_y, x2 - 30, mid_y), fill=LINE, width=4)
    rects = [
        (x1 + 30, y1 + 30, mid_x - 20, mid_y - 20),
        (mid_x + 20, y1 + 30, x2 - 30, mid_y - 20),
        (x1 + 30, mid_y + 20, mid_x - 20, y2 - 30),
        (mid_x + 20, mid_y + 20, x2 - 30, y2 - 30),
    ]
    colors = [TEAL, BLUE, YELLOW, PINK]
    for rect, label, color in zip(rects, labels[:4], colors):
        draw.rounded_rectangle(rect, radius=24, fill=PANEL, outline=color, width=4)
        draw_centered_text(draw, label, center(rect), fonts["tiny"], WHITE)


def draw_cost_accuracy(draw: Any, box: tuple[int, int, int, int], fonts: dict[str, Any]) -> None:
    x1, y1, x2, y2 = box
    axis_y = y2 - 64
    axis_x = x1 + 74
    draw.line((axis_x, y1 + 44, axis_x, axis_y), fill=LINE, width=4)
    draw.line((axis_x, axis_y, x2 - 44, axis_y), fill=LINE, width=4)
    points = [(0.22, 0.38, "cheap", BLUE), (0.58, 0.62, "costly", YELLOW), (0.82, 0.72, "useful", GREEN)]
    for px, py, label, color in points:
        point = (axis_x + int((x2 - axis_x - 70) * px), axis_y - int((axis_y - y1 - 70) * py))
        draw.ellipse((point[0] - 14, point[1] - 14, point[0] + 14, point[1] + 14), fill=color)
        draw_label(draw, label, (point[0] + 16, point[1] - 22), fonts, color)
    draw.text((axis_x + 6, y1 + 16), "accuracy", font=fonts["tiny"], fill=MUTED)
    draw.text((x2 - 134, axis_y + 16), "cost", font=fonts["tiny"], fill=MUTED)


def draw_guardrails(draw: Any, box: tuple[int, int, int, int], labels: list[str], fonts: dict[str, Any]) -> None:
    x1, y1, x2, y2 = box
    lane = (x1 + 68, (y1 + y2) // 2 - 42, x2 - 68, (y1 + y2) // 2 + 42)
    draw.rounded_rectangle(lane, radius=28, fill=PANEL, outline=TEAL, width=4)
    draw_arrow(draw, (lane[0] + 28, center(lane)[1]), (lane[2] - 28, center(lane)[1]), TEAL, width=6)
    gate_xs = [lane[0] + 145, center(lane)[0], lane[2] - 145]
    for label, gate_x, color in zip(labels[:3], gate_xs, [BLUE, YELLOW, GREEN]):
        draw.line((gate_x, lane[1] - 92, gate_x, lane[3] + 92), fill=color, width=5)
        draw_label(draw, label, (gate_x - 62, lane[1] - 138), fonts, color)


def draw_supervision_loop(draw: Any, box: tuple[int, int, int, int], labels: list[str], fonts: dict[str, Any]) -> None:
    x1, y1, x2, y2 = box
    rects = row_rects(draw, labels[:4], fonts["tiny"], x1 + 20, x2 - 20, (y1 + y2) // 2, gap=18)
    colors = [BLUE, TEAL, YELLOW, GREEN]
    for index, rect in enumerate(rects):
        draw_card(draw, rect, labels[index], fonts["tiny"], colors[index])
        if index < len(rects) - 1:
            draw_arrow(draw, (rect[2] + 8, center(rect)[1]), (rects[index + 1][0] - 8, center(rect)[1]), colors[index], width=4)
    draw.arc((x1 + 150, y1 + 38, x2 - 150, y2 - 38), start=205, end=338, fill=MUTED, width=4)


def draw_safe_fail_loop(draw: Any, box: tuple[int, int, int, int], labels: list[str], fonts: dict[str, Any]) -> None:
    draw_loop_visual(draw, box, labels, fonts)
    x1, y1, x2, y2 = box
    shield = [(x2 - 162, y1 + 42), (x2 - 84, y1 + 70), (x2 - 104, y1 + 160), (x2 - 162, y1 + 198), (x2 - 220, y1 + 160), (x2 - 240, y1 + 70)]
    draw.polygon(shield, outline=GREEN, fill=None)
    draw.line((x2 - 198, y1 + 124, x2 - 170, y1 + 152, x2 - 122, y1 + 100), fill=GREEN, width=6)


def evaluate_slide_deck(export_dir: Path) -> dict[str, Any]:
    manifest_path = export_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    slides = [Slide(**slide) for slide in manifest.get("slides", [])]
    pngs = sorted(export_dir.glob("*.png"))
    slide_pngs = [path for path in pngs if path.name != "contact_sheet.png"]
    width = int(manifest.get("width", 0) or 0)
    height = int(manifest.get("height", 0) or 0)
    scores = {
        "format_match": score_slide_format(width, height, manifest.get("platform", "")),
        "slide_count": score_slide_count(len(slides)),
        "text_load": score_slide_text_load(slides),
        "hook_strength": score_slide_hook(slides[0] if slides else None),
        "visual_variety": score_visual_variety(slides),
        "export_completeness": 100.0 if len(slide_pngs) == len(slides) and (export_dir / "contact_sheet.png").exists() else 55.0,
    }
    overall = round(sum(scores.values()) / max(1, len(scores)), 1)
    result = {
        "export_dir": str(export_dir),
        "platform": manifest.get("platform", ""),
        "width": width,
        "height": height,
        "slides": len(slides),
        "scores": scores,
        "overall": overall,
        "verdict": slide_verdict(overall),
        "notes": slide_notes(scores),
    }
    return result


def write_slide_evaluation(result: dict[str, Any], output: Path) -> None:
    lines = [
        "# Slide Deck Evaluation",
        "",
        f"Export: `{result['export_dir']}`",
        f"Platform: {result['platform']}",
        f"Format: {result['width']}x{result['height']}",
        f"Slides: {result['slides']}",
        f"Overall: {result['overall']}/100",
        f"Verdict: {result['verdict']}",
        "",
        "## Scores",
        "",
    ]
    for key, score in result["scores"].items():
        lines.append(f"- {key}: {score}/100")
    lines.extend(["", "## Notes", ""])
    for note in result["notes"]:
        lines.append(f"- {note}")
    lines.append("")
    output.write_text("\n".join(lines), encoding="utf-8")


def score_slide_format(width: int, height: int, platform: str) -> float:
    expected = SLIDE_SIZES.get(platform)
    if not expected:
        return 60.0
    return 100.0 if (width, height) == expected else 55.0


def score_slide_count(count: int) -> float:
    if 6 <= count <= 9:
        return 100.0
    if 5 <= count <= 10:
        return 84.0
    return 55.0


def score_slide_text_load(slides: list[Slide]) -> float:
    if not slides:
        return 0.0
    score = 100.0
    for slide in slides:
        if len(slide.headline.split()) > 8:
            score -= 8
        if len(slide.body.split()) > 24:
            score -= 8
        if sum(len(bullet.split()) for bullet in slide.bullets) > 14:
            score -= 6
    return max(0.0, score)


def score_slide_hook(slide: Slide | None) -> float:
    if not slide:
        return 0.0
    lower = f"{slide.headline} {slide.body}".lower()
    score = 65.0
    if any(word in lower for word in ["not", "hidden", "same", "different", "stop", "trick", "fail", "hype", "hire"]):
        score += 25
    if "?" in slide.headline:
        score += 10
    if len(slide.headline.split()) <= 7:
        score += 10
    return min(100.0, score)


def score_visual_variety(slides: list[Slide]) -> float:
    if not slides:
        return 0.0
    unique = len({slide.visual for slide in slides})
    ratio = unique / len(slides)
    if ratio >= 0.75:
        return 100.0
    if ratio >= 0.55:
        return 82.0
    return 62.0


def slide_verdict(overall: float) -> str:
    if overall >= 90:
        return "postable slide draft"
    if overall >= 78:
        return "needs light slide revision"
    return "needs another slide pass"


def slide_notes(scores: dict[str, float]) -> list[str]:
    notes = [f"{name} needs attention" for name, score in scores.items() if score < 78]
    return notes or ["Slide deck passes the basic carousel checks."]


def load_slide_fonts(width: int) -> dict[str, Any]:
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
        "eyebrow": font(max(18, int(31 * scale))),
        "number": font(max(20, int(36 * scale))),
        "headline": font(max(42, int(82 * scale))),
        "body": font(max(26, int(42 * scale))),
        "small": font(max(22, int(34 * scale))),
        "tiny": font(max(17, int(25 * scale))),
        "footer": font(max(18, int(27 * scale))),
    }


def draw_multiline(
    draw: Any,
    text: str,
    xy: tuple[int, int],
    font: Any,
    fill: tuple[int, int, int],
    max_width: int,
    *,
    max_lines: int,
    spacing: int,
) -> None:
    x, y = xy
    for line in wrap_text(draw, text, font, max_width, max_lines=max_lines):
        draw.text((x, y), line, font=font, fill=fill)
        y += text_height(draw, line, font) + spacing


def draw_card(draw: Any, rect: tuple[int, int, int, int], text: str, font: Any, outline: tuple[int, int, int]) -> None:
    draw.rounded_rectangle(rect, radius=18, fill=PANEL, outline=outline, width=4)
    draw_centered_text(draw, text, center(rect), font, WHITE)


def draw_label(draw: Any, text: str, xy: tuple[int, int], fonts: dict[str, Any], color: tuple[int, int, int]) -> None:
    x, y = xy
    font = fonts["tiny"]
    bbox = draw.textbbox((0, 0), text, font=font)
    pad_x, pad_y = 15, 9
    rect = (x, y, x + bbox[2] - bbox[0] + pad_x * 2, y + bbox[3] - bbox[1] + pad_y * 2)
    draw.rounded_rectangle(rect, radius=13, fill=PANEL, outline=color, width=3)
    draw.text((x + pad_x, y + pad_y), text, font=font, fill=WHITE)


def draw_arrow(draw: Any, start: tuple[float, float], end: tuple[float, float], fill: tuple[int, int, int], width: int = 5) -> None:
    draw.line((start[0], start[1], end[0], end[1]), fill=fill, width=width)
    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    head = 17
    left = (end[0] - head * math.cos(angle - 0.55), end[1] - head * math.sin(angle - 0.55))
    right = (end[0] - head * math.cos(angle + 0.55), end[1] - head * math.sin(angle + 0.55))
    draw.polygon([end, left, right], fill=fill)


def row_rects(
    draw: Any,
    labels: list[str],
    font: Any,
    x1: int,
    x2: int,
    center_y: int,
    *,
    gap: int,
) -> list[tuple[int, int, int, int]]:
    height = text_height(draw, "Ag", font) + 34
    widths = []
    for label in labels:
        bbox = draw.textbbox((0, 0), label, font=font)
        widths.append(max(88, bbox[2] - bbox[0] + 42))
    total = sum(widths) + gap * (len(widths) - 1)
    available = x2 - x1
    if total > available:
        scale = max(0.68, (available - gap * (len(widths) - 1)) / max(1, sum(widths)))
        widths = [max(62, int(width * scale)) for width in widths]
        total = sum(widths) + gap * (len(widths) - 1)
    x = x1 + max(0, (available - total) // 2)
    rects = []
    for width in widths:
        rects.append((x, center_y - height // 2, x + width, center_y + height // 2))
        x += width + gap
    return rects


def draw_progress_dots(draw: Any, width: int, height: int, count: int, active: int) -> None:
    gap = 19
    radius = 5
    total = count * radius * 2 + (count - 1) * gap
    x = (width - total) // 2
    y = height - int(height * 0.035)
    for index in range(1, count + 1):
        fill = TEAL if index == active else LINE
        draw.ellipse((x, y, x + radius * 2, y + radius * 2), fill=fill)
        x += radius * 2 + gap


def contact_sheet(slide_paths: list[Path], output: Path) -> None:
    from PIL import Image, ImageDraw

    if not slide_paths:
        return
    thumbs = []
    for path in slide_paths:
        image = Image.open(path).convert("RGB")
        image.thumbnail((220, 390))
        canvas = Image.new("RGB", (220, 390), INK)
        canvas.paste(image, ((220 - image.width) // 2, (390 - image.height) // 2))
        thumbs.append(canvas)
    cols = min(4, len(thumbs))
    rows = math.ceil(len(thumbs) / cols)
    sheet = Image.new("RGB", (cols * 240 + 20, rows * 420 + 20), (17, 24, 39))
    draw = ImageDraw.Draw(sheet)
    for index, thumb in enumerate(thumbs):
        x = 20 + (index % cols) * 240
        y = 20 + (index // cols) * 420
        sheet.paste(thumb, (x, y))
        draw.rectangle((x, y, x + 220, y + 390), outline=LINE, width=2)
    sheet.save(output)


def draw_contours(draw: Any, center: tuple[int, int], color: tuple[int, int, int], scale: float = 1.0) -> None:
    for radius in [92, 62, 34]:
        rx = int(radius * scale)
        ry = int(radius * 0.58 * scale)
        draw.ellipse((center[0] - rx, center[1] - ry, center[0] + rx, center[1] + ry), outline=color, width=4)


def gradient_points(box: tuple[int, int, int, int]) -> list[tuple[int, int]]:
    x1, y1, x2, y2 = box
    points = []
    top = y1 + int((y2 - y1) * 0.08)
    graph_height = int((y2 - y1) * 0.72)
    for i in range(96):
        t = i / 95
        x = -2.7 + 5.4 * t
        px = x1 + int(t * (x2 - x1))
        py = top + int((1 - (x * x) / 7.29) * graph_height)
        points.append((px, py))
    return points


def center(rect: tuple[int, int, int, int]) -> tuple[int, int]:
    return (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
