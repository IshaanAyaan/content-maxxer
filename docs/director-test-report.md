# Director Test Report

Date: 2026-07-08

## Why this pass exists

The first backend proved the mechanics of video generation, but the videos looked mechanical. This pass raises the bar from "MP4 exists" to "motion explains the idea."

The new `director` command uses a semantic scene graph before rendering:

```text
idea -> visual thesis -> scene graph -> storyboard -> subtitles -> video -> contact sheet -> evaluation
```

The renderer in this pass is still a lightweight Python renderer, not full Manim yet. That is intentional for fast end-to-end testing, but the planning model now follows the human-explainer direction from `docs/human-explainer-study.md`.

## What changed

- Added `content-maxxer director`.
- Added `src/content_maxxer/director.py`.
- Added visual thesis and scene graph files for generated jobs.
- Added semantic recipes for `Gradient Descent` and `Nexus`.
- Removed visible internal beat labels such as "Hook" from serious outputs.
- Added director-aware evaluation with `semantic_motion` and `human_storytelling` checks.
- Added larger callout and caption boxes so labels have more room around words.
- Added `--speed 1.75` pacing for faster shortform timing.
- Added an LLM-specific visual recipe.
- Generated real draft and production videos for three cases.

## Test case 1: Gradient Descent

Command:

```bash
content-maxxer director --slug gradient_descent_director --title "Gradient Descent" --idea "Gradient descent is how a model improves by reading the slope of the loss curve, taking a controlled downhill step, and repeating until it settles near a minimum." --format vertical --duration 32 --speed 1.75 --quality production --force
content-maxxer evaluate gradient_descent_director --format vertical --quality production --director
```

Output:

- `content_jobs/gradient_descent_director/visual_thesis.md`
- `content_jobs/gradient_descent_director/scene_graph.json`
- `content_jobs/gradient_descent_director/exports/gradient_descent_director_director_vertical_production.mp4`
- `content_jobs/gradient_descent_director/exports/gradient_descent_director_director_vertical_production.srt`
- `content_jobs/gradient_descent_director/exports/gradient_descent_director_director_vertical_production_contact.png`

Evaluation:

- Overall: 96.5/100
- Verdict: director draft - review visually
- Format: vertical production
- Duration: 18.3s
- Scenes: 5

Visual read:

The video now has one coherent object: a dot moving on a loss curve. The oversized step, local slope, small step, repeated correction, and final loop all refer to that same object. This is much closer to an explainer than the old template animation.

Remaining weakness:

It is still a clean prototype, not 3Blue1Brown-level craft. It needs smoother object transforms, richer graph annotations, and a true Manim implementation for equations, braces, highlights, and camera work.

## Test case 2: Nexus

Command:

```bash
content-maxxer director --slug nexus_director --title "Nexus" --idea "Nexus shows why two models can have the same pretraining loss but land in different optimization basins, and why downstream tasks care about the route through the landscape rather than only the score." --source-url "https://arxiv.org/pdf/2604.09258" --format vertical --duration 35 --speed 1.75 --quality production --force
content-maxxer evaluate nexus_director --format vertical --quality production --director
```

Output:

- `content_jobs/nexus_director/visual_thesis.md`
- `content_jobs/nexus_director/scene_graph.json`
- `content_jobs/nexus_director/exports/nexus_director_director_vertical_production.mp4`
- `content_jobs/nexus_director/exports/nexus_director_director_vertical_production.srt`
- `content_jobs/nexus_director/exports/nexus_director_director_vertical_production_contact.png`

Evaluation:

- Overall: 96.5/100
- Verdict: director draft - review visually
- Format: vertical production
- Duration: 20.0s
- Scenes: 5

Visual read:

The video carries a central landscape metaphor: two optimization routes, equal loss, different basins, downstream valley, task agreement, inner steps, and route over score. This is a better fit for the paper than generic abstract shapes.

Remaining weakness:

The Nexus recipe is still hand-authored and simplified. A real version should parse the paper, choose figure-level visual metaphors, and generate Manim scenes that can preserve objects across code-level transforms.

## Test case 3: Large Language Models

Command:

```bash
content-maxxer director --slug large_language_models_director --title "How Large Language Models Work" --idea "Explain how large language models work: text becomes tokens, tokens become vectors, attention mixes context, transformer layers refine meaning, the model predicts the next token, and repeating that loop creates an answer." --format vertical --duration 48 --speed 1.75 --quality production --force
content-maxxer evaluate large_language_models_director --format vertical --quality production --director
```

Output:

- `content_jobs/large_language_models_director/visual_thesis.md`
- `content_jobs/large_language_models_director/scene_graph.json`
- `content_jobs/large_language_models_director/exports/large_language_models_director_director_vertical_production.mp4`
- `content_jobs/large_language_models_director/exports/large_language_models_director_director_vertical_production.srt`
- `content_jobs/large_language_models_director/exports/large_language_models_director_director_vertical_production_contact.png`

Evaluation:

- Overall: 94.0/100
- Verdict: director draft - review visually
- Format: vertical production
- Duration: 27.42s
- Scenes: 6

Visual read:

The video carries one central object: text becomes token cards, token cards become vectors, vectors pass through attention and transformer layers, then a next-token probability chart becomes a repeated generation loop. The opening is stronger now: it starts from the hidden tokenization trick instead of a dry definition. This is the right skeleton for explaining LLMs without voice synthesis.

Remaining weakness:

The video is still a clean semantic draft, not a final human-edited explainer. A stronger version should use Manim transforms to make token-to-vector continuity smoother and should add a better opening surprise, such as "it is only guessing the next token, but that becomes reasoning when repeated."

## Quality conclusion

This is no longer the "slop" path. The old caption template remains as a low-level backend smoke test only. The director path is the new default direction for content quality. The pacing and text-box fixes make the outputs feel closer to shortform explainers, but the videos still need a Manim render-revise loop before they should be treated as final channel assets.

It is still not finished. The next important jump is to replace the lightweight renderer with generated Manim code and a render-revise loop that critiques contact sheets before accepting an output.

## Sources studied

- 3Blue1Brown about page: https://www.3blue1brown.com/about/
- 3Blue1Brown video source repo: https://github.com/3b1b/videos
- 3Blue1Brown Manim repo: https://github.com/3b1b/manim
- Grant Sanderson's Manim demo post: https://3blue1brown.substack.com/p/how-i-animate-3blue1brown
- Summer of Math Exposition: https://some.3b1b.co/
- Caleb Writes Code channel: https://www.youtube.com/@CalebWritesCode
