# Backend Test Report

Date: 2026-07-07

## Current status

These outputs were useful backend tests, but they are not the target quality bar. After review, they should be treated as rejected prototype artifacts: they prove file generation works, but they do not look like good human-made explainers.

The previous evaluator over-scored them because it measured mechanical properties such as format, pacing, and subtitle length. It did not measure semantic motion, visual continuity, or taste. That evaluator has since been tightened to mark the template renderer as a mechanical prototype, not channel-ready content.

## What was tested

The tested backend path was:

1. Load or create a content job.
2. Build a five-beat caption plan.
3. Render a vertical MP4 with burned-in subtitles.
4. Write a matching SRT file and render manifest.
5. Create a contact sheet for visual QA.
6. Run the heuristic evaluator.

## Test case 1: Nexus

Command:

```bash
content-maxxer package nexus_explainer_h --format vertical --duration 25 --quality draft
content-maxxer evaluate nexus_explainer_h --format vertical --quality draft
```

Output:

- `content_jobs/nexus_explainer_h/exports/nexus_explainer_h_vertical_draft.mp4`
- `content_jobs/nexus_explainer_h/exports/nexus_explainer_h_vertical_draft_contact.png`
- `content_jobs/nexus_explainer_h/exports/nexus_explainer_h_vertical_draft_evaluation.md`

Original mechanical result:

- Overall: 100/100
- Verdict: postable draft
- Format: 540x960
- Duration: 25s
- Beats: 5

Finding:

The first pass exposed a real issue: long source-script captions were too dense. The backend was updated to turn script paragraphs into short on-screen captions. That fixed readability but not the deeper quality problem: the motion is still template-driven instead of idea-driven.

## Test case 2: Gradient Descent

Command:

```bash
content-maxxer make-video --slug gradient_descent_simple --title "Gradient Descent" --idea "Gradient descent is how a model improves by measuring which direction makes its error smaller, taking a small step downhill, and repeating until the solution is good enough." --format vertical --duration 22 --quality draft --force
content-maxxer evaluate gradient_descent_simple --format vertical --quality draft
```

Output:

- `content_jobs/gradient_descent_simple/exports/gradient_descent_simple_vertical_draft.mp4`
- `content_jobs/gradient_descent_simple/exports/gradient_descent_simple_vertical_draft_contact.png`
- `content_jobs/gradient_descent_simple/exports/gradient_descent_simple_vertical_draft_evaluation.md`

Original mechanical result:

- Overall: 97/100
- Verdict: postable draft
- Format: 540x960
- Duration: 22s
- Beats: 5

Finding:

The clean concept path creates the job docs, video plan, subtitles, export, contact sheet, and evaluation from one concept prompt. It is still not good enough as content, because the visuals are generic and do not behave like a crafted explainer.

## Remaining weaknesses

- The visual system is intentionally simple and template-driven.
- The backend does not yet parse PDFs or paper URLs deeply.
- The evaluator is a proxy; it catches obvious pacing and readability issues but cannot replace real audience data.
- Manim is still separate from the verified caption-led path because local Manim dependencies are missing.

## New direction

The next backend should follow `docs/human-explainer-study.md` and `docs/director-system.md`: generate a visual thesis, produce a semantic scene graph, create Manim code, render, critique the actual visuals, and revise. The goal is not "video exists"; the goal is "the animation teaches through meaningful transformation."
