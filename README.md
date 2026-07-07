# Content Maxxer

Content Maxxer is a public repo for turning high-context prompts into shortform explainer videos, starting with Manim-based research animations.

The first seed example is `nexus_explainer_h`: a 56 second 1920x1080 Manim-style visual explainer. It has no audio track yet, which makes it a clean reference for the visual workflow before adding narration, captions, shorts crops, and slide content later.

## What this method is

The current method is not just "make an animation." It is a repeatable content job:

1. Start with a dense source, usually a paper, doc, or technical topic.
2. Write one strong prompt that defines the audience, quality bar, duration, animation style, concepts to explain, and requirement to render/check scene modules.
3. Break the idea into teachable visual beats: hook, mental model, core mechanism, engineering detail, takeaway.
4. Build each beat as a Manim scene or scene section.
5. Render, review for awkward frames or overlaps, then stitch into the final shortform asset.

The goal is to make "contentmaxxing" systematic: one source in, one polished video out, with the prompt, source notes, storyboard, scene code, render artifacts, and final output all saved together.

For the current research pass on AI-native shorts workflows, see [docs/ai-shorts-research.md](docs/ai-shorts-research.md).

For the new quality reset after studying human-made visual explainers, see [docs/human-explainer-study.md](docs/human-explainer-study.md) and [docs/director-system.md](docs/director-system.md).

## Quick start

Install the backend video dependencies first:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
content-maxxer doctor
```

Manim rendering is still available as an optional path. For Manim scenes, install the system render dependencies and optional extra:

```bash
brew install ffmpeg cairo pango pkg-config
pip install -e ".[manim]"
```

Create a new content job:

```bash
content-maxxer new my_explainer --title "My Explainer" --source-url "https://example.com/source.pdf"
```

Render a job:

```bash
content-maxxer render my_explainer --quality draft
content-maxxer render my_explainer --quality high
```

Render the seed Nexus job:

```bash
content-maxxer render nexus_explainer_h --quality draft
```

Generate a caption-led video directly from an idea:

```bash
content-maxxer make-video \
  --title "Gradient Descent" \
  --idea "Gradient descent improves a model by taking small downhill steps." \
  --format vertical \
  --duration 22 \
  --quality draft
```

Package an existing job into a captioned MP4:

```bash
content-maxxer package nexus_explainer_h --format vertical --duration 25 --quality draft
```

Evaluate a generated export:

```bash
content-maxxer evaluate nexus_explainer_h --format vertical --quality draft
```

## Repo layout

```text
content_jobs/
  _template/                 Reusable content job starter files.
  nexus_explainer_h/         Seed example based on the existing Nexus render.
    prompt.md                The high-context prompt pattern.
    scene.py                 Manim scene scaffold matching the reference style.
    reference/               Existing MP4 and generated contact sheet.
docs/
  workflow.md                Concise upgrade plan for the contentmaxx workflow.
  ai-shorts-research.md      Research memo on tools, methods, and channel workflow.
  backend-workflow.md        Small backend path for idea-to-captioned-video.
  human-explainer-study.md   What good human visual explainers do differently.
  director-system.md         Target AI director loop for Manim-style explainers.
  test-report.md             Results from generated backend test videos.
src/content_maxxer/
  cli.py                     Commands for creating and rendering jobs.
  backend.py                 Caption-led video renderer and evaluator.
```

## Next lanes

Video comes first. Slides should become a parallel content lane later, using the same intake, research, outline, and review structure, but with slide deck templates instead of Manim scenes.
