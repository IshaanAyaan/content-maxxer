# Director System

This is the next Content Maxxer backend target. It replaces the current template renderer with an AI director loop for Manim-based explainers.

## User experience

The user gives:

```text
Make a 60 second 9:16 explainer about <paper or idea>.
Style: crisp 3Blue1Brown-like technical visual explanation.
Voice: I will record my own later.
```

The system produces:

- a visual thesis;
- a scene graph;
- Manim code;
- a rendered draft;
- subtitles or caption cards;
- a contact sheet;
- a visual critique;
- a revision plan;
- a final export.

## Pipeline

### 1. Intake

Capture:

- source text, PDF, URL, or plain idea;
- format, duration, and target audience;
- desired technical depth;
- one sentence the viewer should remember.

### 2. Visual thesis

Before code, the AI must write:

- the concrete tension;
- the central visual object;
- the transformation the viewer will watch;
- the final insight.

Example:

```text
Loss landscapes are not just scores. Nexus changes the training path so task valleys agree.
Central visual object: a dot moving across two overlapping landscapes.
Primary transformation: same final height, different landing basin.
```

### 3. Scene graph

Represent the video as semantic scenes, not generic beats:

```json
{
  "scene_id": "same_score_different_basin",
  "viewer_question": "How can two models tie on loss but differ downstream?",
  "visual_object": "two loss landscapes and a moving point",
  "motion": "two dots descend to equal-height but different basins",
  "meaning": "the score hides where optimization landed",
  "visible_text": ["same score", "different basin"],
  "duration": 8
}
```

### 4. Manim generation

Generate real Manim scenes from the scene graph.

Rules:

- Use `Transform` and `ReplacementTransform` for conceptual continuity.
- Use highlights, arrows, braces, and color to guide attention.
- Use `ValueTracker` or updaters when a variable changes continuously.
- Keep text short.
- Never show internal labels like "Hook" or "Setup".
- Prefer one reusable domain object over disconnected visuals.

### 5. Render and critique

After rendering, generate:

- contact sheet;
- frame samples;
- timing stats;
- label density report;
- motion-purpose report.

The critique must answer:

- What does each motion mean?
- Is the first scene concrete?
- Is the same visual object carried forward?
- Are labels readable?
- Does any animation happen only for decoration?

### 6. Revision

If critique fails, revise the scene graph and Manim code before claiming success.

## What the AI should optimize

Optimize for:

- visual intuition;
- causal motion;
- conceptual continuity;
- sparse text;
- memorable concrete examples;
- one coherent visual metaphor.

Do not optimize for:

- lots of motion;
- generic templates;
- decorative graphics;
- apparent activity;
- paragraph captions.

## Implementation order

1. Add a `director` command that writes `visual_thesis.md` and `scene_graph.json`.
2. Add a Manim scene generator that turns `scene_graph.json` into `scene.py`.
3. Add a quality evaluator for semantic motion and visible text.
4. Add a render/revise loop.
5. Only then package for vertical social output.
