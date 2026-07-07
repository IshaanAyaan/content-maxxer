# Backend Workflow

This repo now has a small backend path for caption-led explainer videos. It does not solve voice, avatars, or slides. It takes a paper idea or concept, creates a five-beat plan, renders a captioned MP4, writes an SRT file, creates a contact sheet, and evaluates the output.

Install it with:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Commands

Create and render a new concept video:

```bash
content-maxxer make-video \
  --slug gradient_descent_simple \
  --title "Gradient Descent" \
  --idea "Gradient descent improves a model by taking small downhill steps." \
  --format vertical \
  --duration 22 \
  --quality draft \
  --force
```

Package an existing job:

```bash
content-maxxer package nexus_explainer_h --format vertical --duration 25 --quality draft
```

Evaluate an export:

```bash
content-maxxer evaluate nexus_explainer_h --format vertical --quality draft
```

## Outputs

Each rendered job writes files under `content_jobs/<slug>/exports/`:

- `<slug>_vertical_draft.mp4`: rendered caption-led video.
- `<slug>_vertical_draft.srt`: matching subtitle file.
- `<slug>_vertical_draft.json`: render manifest.
- `<slug>_vertical_draft_contact.png`: nine-frame visual QA sheet.
- `<slug>_vertical_draft_evaluation.md`: postability report.
- `<slug>_vertical_draft_evaluation.json`: machine-readable evaluation.

## Evaluation

The evaluator scores the output with proxy checks:

- requested format match;
- subtitle readability;
- pacing;
- visual cadence;
- hook strength;
- text load.

These checks do not predict real platform performance. They are a backend guardrail that catches obvious problems before posting.

## Current limitation

The tested backend is caption-led and visual-first. Manim remains available as a separate render command, but it was not part of the verified path because local Manim system dependencies are not installed in this environment.
