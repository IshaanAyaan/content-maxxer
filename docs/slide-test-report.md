# Slide Test Report

Date: 2026-07-08

## What was tested

This pass tested a new static carousel lane, separate from the current video director:

```text
idea -> slide plan -> numbered PNG slides -> contact sheet -> slide evaluation
```

The goal was to see whether swipe-through carousels can produce cleaner educational content than the current animation renderer.

## Renderer changes

- Added `src/content_maxxer/slides.py`.
- Added `content-maxxer slides`.
- Added `content-maxxer evaluate-slides`.
- Added `make slides-llm`, `make slides-nexus`, and `make slides-agents`.
- Added slide planning docs: `slide_brief.md`, `slide_plan.json`, and `slide_storyboard.md`.
- Added a full-size visual inspection step after the contact sheet exposed too little detail.

## Test case 1: Large Language Models

Command:

```bash
make slides-llm
make evaluate-slides-llm
```

Output:

- `content_jobs/large_language_models_slides/slide_brief.md`
- `content_jobs/large_language_models_slides/slide_plan.json`
- `content_jobs/large_language_models_slides/slide_storyboard.md`
- `content_jobs/large_language_models_slides/exports/slides_tiktok_production/01_01_hook.png`
- `content_jobs/large_language_models_slides/exports/slides_tiktok_production/contact_sheet.png`
- `content_jobs/large_language_models_slides/exports/slides_tiktok_production/evaluation.md`

Evaluation:

- Overall: 100.0/100
- Verdict: postable slide draft
- Format: 1080x1920
- Slides: 8

Visual read:

This is the strongest output from the repo so far. The carousel explains the concept in a swipe-native way:

```text
hook -> whole loop -> tokens -> vectors -> attention -> layers -> next-token prediction -> repeat loop
```

Full-size inspection caught and fixed one real issue: the first slide originally had overlapping token labels. The labels were shortened and the deck was regenerated.

Remaining weakness:

The visual style is still system-generated. It is cleaner than the videos, but the next improvement should add more editorial art direction: stronger first-slide composition, optional light background variants, and more human-designed visual hierarchy.

## Test case 2: Nexus

Command:

```bash
make slides-nexus
make evaluate-slides-nexus
```

Output:

- `content_jobs/nexus_slides/slide_brief.md`
- `content_jobs/nexus_slides/slide_plan.json`
- `content_jobs/nexus_slides/slide_storyboard.md`
- `content_jobs/nexus_slides/exports/slides_tiktok_production/01_01_hook.png`
- `content_jobs/nexus_slides/exports/slides_tiktok_production/contact_sheet.png`
- `content_jobs/nexus_slides/exports/slides_tiktok_production/evaluation.md`

Evaluation:

- Overall: 100.0/100
- Verdict: postable slide draft
- Format: 1080x1920
- Slides: 6

Visual read:

The Nexus deck works as a paper-style backtest. It keeps the core metaphor from the director lane, but without awkward animation:

```text
same loss/different model -> loss as scoreboard -> downstream valleys -> task agreement -> clone/step/measure -> route takeaway
```

Remaining weakness:

The deck is simplified. A stronger paper carousel should include one slide grounded in the actual paper figure or a reconstructed figure-level diagram.

## Test case 3: AI Agent Reliability

Chosen topic:

```text
AI agents are not employees yet.
```

Reason:

This is a better near-term post topic than another generic LLM explainer. It is timely, AI-native, slightly contrarian, and grounded in real research: agents are improving fast, but reliability, cost, and safe failure are still the hard parts.

Command:

```bash
make slides-agents
make evaluate-slides-agents
```

Output:

- `content_jobs/ai_agents_reliability_slides/slide_brief.md`
- `content_jobs/ai_agents_reliability_slides/slide_plan.json`
- `content_jobs/ai_agents_reliability_slides/slide_storyboard.md`
- `content_jobs/ai_agents_reliability_slides/exports/slides_tiktok_production/01_01_hook.png`
- `content_jobs/ai_agents_reliability_slides/exports/slides_tiktok_production/contact_sheet.png`
- `content_jobs/ai_agents_reliability_slides/exports/slides_tiktok_production/evaluation.md`

Evaluation:

- Overall: 100.0/100
- Verdict: postable slide draft
- Format: 1080x1920
- Slides: 8

Visual read:

This is the strongest engagement hook so far:

```text
Would you hire a 1-in-3 failure?
```

It is pointed without being dishonest. The rest of the deck earns the hook by explaining benchmark progress, the leaderboard trap, reliability dimensions, cost, guardrails, supervision, and safe failure.

Sources behind the angle:

- Stanford AI Index 2026 technical performance chapter: AI agents improved on OSWorld but still fail roughly one in three attempts.
- Towards a Science of AI Agent Reliability: single success metrics hide consistency, robustness, predictability, and safety.
- AI Agents That Matter: agent evaluations should include cost and avoid benchmark shortcuts.

## Conclusion

The slide lane looks more promising than the current animation lane for near-term posting. The content is easier to inspect, the visuals are less likely to feel like random motion, and each slide has a clear job.

The next serious step is to build a slide critique loop:

1. render deck;
2. inspect every slide at full size;
3. detect text overlap and tiny labels;
4. produce a revised deck automatically;
5. optionally export both TikTok 9:16 and Instagram 4:5 variants.
