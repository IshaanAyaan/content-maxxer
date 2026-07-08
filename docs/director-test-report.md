# Director Test Report

Date: 2026-07-07

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
- Generated real draft and production videos for two cases.

## Test case 1: Gradient Descent

Command:

```bash
content-maxxer director --slug gradient_descent_director --title "Gradient Descent" --idea "Gradient descent is how a model improves by reading the slope of the loss curve, taking a controlled downhill step, and repeating until it settles near a minimum." --format vertical --duration 32 --quality production --force
content-maxxer evaluate gradient_descent_director --format vertical --quality production --director
```

Output:

- `content_jobs/gradient_descent_director/visual_thesis.md`
- `content_jobs/gradient_descent_director/scene_graph.json`
- `content_jobs/gradient_descent_director/exports/gradient_descent_director_director_vertical_production.mp4`
- `content_jobs/gradient_descent_director/exports/gradient_descent_director_director_vertical_production.srt`
- `content_jobs/gradient_descent_director/exports/gradient_descent_director_director_vertical_production_contact.png`

Evaluation:

- Overall: 90.9/100
- Verdict: director draft - review visually
- Format: vertical production
- Duration: 32s
- Scenes: 5

Visual read:

The video now has one coherent object: a dot moving on a loss curve. The oversized step, local slope, small step, repeated correction, and final loop all refer to that same object. This is much closer to an explainer than the old template animation.

Remaining weakness:

It is still a clean prototype, not 3Blue1Brown-level craft. It needs smoother object transforms, richer graph annotations, and a true Manim implementation for equations, braces, highlights, and camera work.

## Test case 2: Nexus

Command:

```bash
content-maxxer director --slug nexus_director --title "Nexus" --idea "Nexus shows why two models can have the same pretraining loss but land in different optimization basins, and why downstream tasks care about the route through the landscape rather than only the score." --source-url "https://arxiv.org/pdf/2604.09258" --format vertical --duration 35 --quality production --force
content-maxxer evaluate nexus_director --format vertical --quality production --director
```

Output:

- `content_jobs/nexus_director/visual_thesis.md`
- `content_jobs/nexus_director/scene_graph.json`
- `content_jobs/nexus_director/exports/nexus_director_director_vertical_production.mp4`
- `content_jobs/nexus_director/exports/nexus_director_director_vertical_production.srt`
- `content_jobs/nexus_director/exports/nexus_director_director_vertical_production_contact.png`

Evaluation:

- Overall: 93.4/100
- Verdict: director draft - review visually
- Format: vertical production
- Duration: 35s
- Scenes: 5

Visual read:

The video carries a central landscape metaphor: two optimization routes, equal loss, different basins, downstream valley, task agreement, inner steps, and route over score. This is a better fit for the paper than generic abstract shapes.

Remaining weakness:

The Nexus recipe is still hand-authored and simplified. A real version should parse the paper, choose figure-level visual metaphors, and generate Manim scenes that can preserve objects across code-level transforms.

## Quality conclusion

This is no longer the "slop" path. The old caption template remains as a low-level backend smoke test only. The director path is the new default direction for content quality.

It is still not finished. The next important jump is to replace the lightweight renderer with generated Manim code and a render-revise loop that critiques contact sheets before accepting an output.

## Sources studied

- 3Blue1Brown about page: https://www.3blue1brown.com/about/
- 3Blue1Brown video source repo: https://github.com/3b1b/videos
- 3Blue1Brown Manim repo: https://github.com/3b1b/manim
- Grant Sanderson's Manim demo post: https://3blue1brown.substack.com/p/how-i-animate-3blue1brown
- Summer of Math Exposition: https://some.3b1b.co/
- Caleb Writes Code channel: https://www.youtube.com/@CalebWritesCode
