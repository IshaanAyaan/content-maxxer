# Slide System

The slide lane is a separate Content Maxxer path for static social carousels. It keeps the current video/director work, but adds a simpler format that may be more postable right now: swipe-through explainers.

## Why this exists

The video renderer still looks too much like AI-generated motion. Static slides avoid that failure mode. Each slide can be judged like a designed post:

- one claim;
- one visual;
- low text load;
- strong first-slide hook;
- consistent format;
- numbered export files that can be posted directly.

## Supported formats

The renderer supports:

- `tiktok`: 1080x1920, full-screen vertical;
- `reels`: 1080x1920, full-screen vertical;
- `instagram`: 1080x1350, portrait feed carousel;
- `square`: 1080x1080.

The current default is `tiktok` because it gives us the full phone canvas and works naturally for TikTok Photo Mode-style swipe posts. Instagram portrait output is available for feed carousels.

## Hook Style

The first slide should not sound like a textbook title. Use a pointed question or contrarian claim, then make the rest of the deck earn the click with accurate explanation.

Good:

```text
Would you hire a 1-in-3 failure?
```

Weak:

```text
Understanding AI agent reliability
```

## Pipeline

```text
idea/paper -> slide thesis -> slide plan -> storyboard -> numbered PNGs -> contact sheet -> evaluation
```

The important difference from the video lane is that slides do not need fake motion. The output is a sequence of designed stills.

## Commands

Generate the LLM carousel:

```bash
content-maxxer slides \
  --slug large_language_models_slides \
  --title "How Large Language Models Work" \
  --idea "Explain how large language models work: text becomes tokens, tokens become vectors, attention mixes context, transformer layers refine meaning, the model predicts the next token, and repeating that loop creates an answer." \
  --platform tiktok \
  --quality production \
  --force
```

Evaluate it:

```bash
content-maxxer evaluate-slides large_language_models_slides --platform tiktok --quality production
```

Convenience targets:

```bash
make slides-llm
make evaluate-slides-llm
make slides-nexus
make evaluate-slides-nexus
make slides-agents
make evaluate-slides-agents
```

## Output shape

For a job named `large_language_models_slides`, outputs land in:

```text
content_jobs/large_language_models_slides/
  slide_brief.md
  slide_plan.json
  slide_storyboard.md
  exports/slides_tiktok_production/
    01_01_hook.png
    02_02_map.png
    ...
    contact_sheet.png
    manifest.json
    evaluation.md
    evaluation.json
```

## Quality gates

A slide deck should pass these checks before posting:

- first slide creates a curiosity gap;
- 5-10 slides for the main educational carousel;
- one idea per slide;
- visible text is readable on a phone;
- no text overlap at full-size inspection;
- contact sheet reads as one coherent story;
- every slide has a different job, not repeated decoration;
- all slides share the same dimensions and visual system.

## Current recipes

The first pass includes semantic recipes for:

- large language models;
- AI agent reliability and benchmark hype;
- Nexus;
- gradient descent;
- generic concept explainers.

The LLM recipe uses this structure:

```text
hook -> whole loop -> tokens -> vectors -> attention -> layers -> next-token prediction -> repeated loop
```

The Nexus recipe uses this structure:

```text
same loss/different model -> loss as scoreboard -> downstream valleys -> task agreement -> inner loop -> route takeaway
```

The AI agent reliability recipe uses this structure:

```text
1-in-3 failure hook -> benchmark progress -> leaderboard trap -> reliability dimensions -> cost trap -> boxed tasks -> supervision wrapper -> safe-failure takeaway
```

## Sources

- Instagram Help, image resolution guidance: https://help.instagram.com/1631821640426723/
- TikTok Ads Manager, vertical creative guidance and safe-zone note: https://ads.tiktok.com/help/article/tiktok-auction-in-feed-ads
- TikTok Photo Mode sizing references checked for 1080x1920 carousel convention: https://moda.app/resources/sizes/tiktok
