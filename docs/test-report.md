# Backend Test Report

Date: 2026-07-07

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

Result:

- Overall: 100/100
- Verdict: postable draft
- Format: 540x960
- Duration: 25s
- Beats: 5

Finding:

The first pass exposed a real issue: long source-script captions were too dense. The backend was updated to turn script paragraphs into short on-screen captions, then the video was regenerated and re-evaluated successfully.

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

Result:

- Overall: 97/100
- Verdict: postable draft
- Format: 540x960
- Duration: 22s
- Beats: 5

Finding:

The clean concept path works well. It creates the job docs, video plan, subtitles, export, contact sheet, and evaluation from one concept prompt.

## Remaining weaknesses

- The visual system is intentionally simple and template-driven.
- The backend does not yet parse PDFs or paper URLs deeply.
- The evaluator is a proxy; it catches obvious pacing and readability issues but cannot replace real audience data.
- Manim is still separate from the verified caption-led path because local Manim dependencies are missing.
