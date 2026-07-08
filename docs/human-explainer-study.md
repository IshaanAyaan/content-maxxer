# Human Explainer Study

Date: 2026-07-07

## Why the current videos fail

The current caption-led backend proves that the repo can produce an MP4, subtitles, contact sheets, and evaluation artifacts. It does not prove that the output is good content.

The videos feel bad because they are template motion:

- The visible labels expose internal structure, such as "Hook" and "Setup".
- The shapes move because the template says they should move, not because the idea requires that motion.
- The animation does not preserve one central visual object across the explanation.
- The viewer is asked to read captions while watching unrelated generic diagrams.
- The evaluator rewarded mechanics instead of taste.

That is not the target.

## What 3Blue1Brown is actually doing

3Blue1Brown is not simply "dark background plus math animation." The important pattern is visual exposition.

From 3Blue1Brown's own writing and repos:

- The channel goal is explaining math visually, with understanding as the path to making people love the subject.
- Almost all animations are made in Manim.
- Manim is useful when precision, loops, and abstraction make code feel liberating rather than restrictive.
- The 3b1b workflow is interactive: run a scene at a line, tweak a small piece of code, checkpoint the state, and record deliberate clips.
- Grant's public advice says not to start with definitions, to use concrete examples before abstractions, and to avoid pointless animations.
- Every movement should have an identifiable purpose and should reinforce the same point as the narration.

I also inspected the public `3b1b/videos` repository locally. The code repeatedly uses patterns that are missing from our prototype:

- `Transform`, `ReplacementTransform`, and `FadeTransform` to show one object becoming another.
- `SurroundingRectangle`, braces, arrows, and highlights to guide attention.
- `ValueTracker`, updaters, and continuous motion when a variable changes.
- Reused domain objects, such as transformer blocks, token rectangles, matrices, curves, and geometric constructions.
- Scene-specific helper functions instead of one generic global template.

## What Caleb-style AI explainers add

Caleb Writes Code sits closer to the short AI-explainer lane this repo is targeting. The useful pattern is different from pure math exposition:

- The topic starts from a timely technical question.
- The visuals stay punchy and legible rather than mathematically dense.
- Each screen is built around a named technical object, such as a model, GPU, agent loop, benchmark, or system diagram.
- The edit rhythm is faster than longform 3Blue1Brown, but still needs motion to mean something.

For Content Maxxer, the blended style target is:

```text
3Blue1Brown visual continuity + Caleb-style AI topic selection + shortform pacing
```

We should study techniques and structure, not copy exact assets, scenes, scripts, or branded visual identity.

## What human-quality explainers need

### 1. A visual thesis

Every video needs one central visual claim:

> "This paper is about X becoming Y under pressure Z."

If we cannot draw that sentence, we do not have a video yet.

### 2. Concrete before abstract

The first scene should be a concrete puzzle, example, or surprising contradiction. Definitions come later.

Bad:

> "Gradient descent is an optimization algorithm..."

Better:

> "This dot keeps choosing the steepest downhill step, but the size of the step changes whether it learns or explodes."

### 3. Semantic motion only

Every animation must answer:

- What object is changing?
- What does the motion mean?
- Why would a viewer understand more after seeing it move?

If the answer is "it looks dynamic," delete the motion.

### 4. One evolving object

Good scenes keep reusing the same visual object so the viewer can build memory. For paper explainers, that object might be:

- a model block;
- a loss landscape;
- a token sequence;
- a vector;
- a graph;
- a matrix;
- a training loop;
- a probability distribution.

The video should transform this object instead of cutting to unrelated templates.

### 5. Text is a pointer, not content

On-screen text should name the thing the viewer is already seeing. It should not carry the explanation by itself.

Allowed:

- short labels;
- equation fragments;
- callouts;
- one sentence takeaway.

Avoid:

- paragraph captions as the main content;
- structural labels like "Hook";
- animated text for its own sake.

### 6. The generator must be a director

The AI should not directly jump from prompt to video. It should produce and validate:

1. the core misconception or tension;
2. the central visual object;
3. the sequence of transformations;
4. the exact visible labels;
5. the Manim scene code;
6. a render;
7. a visual critique;
8. revisions.

## New target architecture

The old backend was:

```text
idea -> generic beats -> template video -> heuristic score
```

The new target should be:

```text
idea/paper -> visual thesis -> scene graph -> Manim code -> render -> visual critique -> revision -> postable export
```

## Non-negotiable quality gates

A generated video is not channel-ready unless:

- no internal beat labels are visible;
- every motion has a semantic reason;
- there is one central visual object or visual metaphor;
- the first 3 seconds present a concrete tension;
- captions/labels support visuals instead of replacing them;
- the same object is transformed across scenes;
- contact-sheet frames look like one coherent lesson;
- a human reviewer can describe what each motion means.

## Sources

- 3Blue1Brown about page: https://www.3blue1brown.com/about/
- 3Blue1Brown video source repo: https://github.com/3b1b/videos
- 3Blue1Brown Manim repo: https://github.com/3b1b/manim
- Grant Sanderson's Manim demo post: https://3blue1brown.substack.com/p/how-i-animate-3blue1brown
- Summer of Math Exposition: https://www.3blue1brown.com/blog/some1/
- Manim Community: https://www.manim.community/
- Caleb Writes Code channel: https://www.youtube.com/@CalebWritesCode
