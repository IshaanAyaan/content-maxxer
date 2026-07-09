# Content Maxxer Handoff

Project moved to:

```text
/Users/ish/Documents/contentmaxxer
```

GitHub repo:

```text
https://github.com/IshaanAyaan/content-maxxer
```

Latest pushed commit at handoff:

```text
10e9f1e Add AI agent reliability carousel
```

## What This Repo Is

Content Maxxer is a backend workflow for turning AI/research ideas into postable educational content.

The current best lane is not animated video. The strongest current lane is static social carousels for TikTok Photo Mode, Reels-style slides, and Instagram carousels.

## Current Best Post Candidate

Use this first:

```text
AI agents are not employees yet.
```

Hook:

```text
Would you hire a 1-in-3 failure?
```

Generated post files:

```text
/Users/ish/Documents/contentmaxxer/outputs/ai-agents-reliability-carousel
```

Repo job:

```text
/Users/ish/Documents/contentmaxxer/content_jobs/ai_agents_reliability_slides
```

Why this topic:

- Timely AI topic.
- Slightly spicy without being dishonest.
- Explains real agent reliability issues.
- Stronger than another generic "how LLMs work" post.

Sources used:

- Stanford AI Index 2026 technical performance.
- Towards a Science of AI Agent Reliability.
- AI Agents That Matter.

## Main Commands

Set up:

```bash
cd /Users/ish/Documents/contentmaxxer
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
```

Generate the best current carousel:

```bash
make slides-agents
make evaluate-slides-agents
```

Generate the LLM carousel:

```bash
make slides-llm
make evaluate-slides-llm
```

Generate the Nexus carousel:

```bash
make slides-nexus
make evaluate-slides-nexus
```

Run tests:

```bash
make test
```

## Important Files

Slide backend:

```text
src/content_maxxer/slides.py
```

CLI wiring:

```text
src/content_maxxer/cli.py
```

Slide docs:

```text
docs/slide-system.md
docs/slide-test-report.md
```

Video/director docs:

```text
docs/director-system.md
docs/director-test-report.md
docs/human-explainer-study.md
```

## Current Content Jobs

Best current carousel:

```text
content_jobs/ai_agents_reliability_slides
```

Other generated slide decks:

```text
content_jobs/large_language_models_slides
content_jobs/nexus_slides
```

Older/director video experiments:

```text
content_jobs/large_language_models_director
content_jobs/gradient_descent_director
content_jobs/nexus_director
```

Seed/reference job:

```text
content_jobs/nexus_explainer_h
```

## What To Do Next

The next useful project task is to improve hooks and editorial art direction for the slide lane.

Recommended next implementation:

1. Add a `hook_style` option for slide decks.
2. Create hook templates:
   - question hook;
   - contrarian hook;
   - "everyone is wrong about X" hook;
   - benchmark shock hook;
   - practical warning hook.
3. Add an automatic full-size slide QA pass that detects:
   - overlapping text;
   - overly long body copy;
   - tiny labels;
   - weak first-slide hook.
4. Add Instagram 4:5 export alongside TikTok 9:16.

## Notes For The Next Codex Session

Start from:

```text
/Users/ish/Documents/contentmaxxer
```

The old side-chat workspace was:

```text
/Users/ish/Documents/Codex/2026-07-06/amke
```

Do not continue there unless you are intentionally looking for old scratch files.

The local `outputs/` folder is ignored by git on purpose. It contains convenient copies of generated content for posting/review. The canonical reproducible artifacts are still under `content_jobs/`.
