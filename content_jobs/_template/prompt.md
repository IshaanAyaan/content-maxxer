# Production Prompt: {{TITLE}}

Use Manim Community.

Docs: https://docs.manim.community/en/stable/

Create a high quality Manim animation explaining {{TOPIC}} from the ground up. Use the source below as the main reference:

{{SOURCE_URL}}

Requirements:

- Explain the topic for a smart general audience without flattening the real mechanism.
- Build the video as a sequence of small visual scenes, then stitch them together.
- Use precise diagrams, graphs, labels, and motion to make the idea intuitive.
- Do not rush. Aim for about one minute.
- Avoid awkward transitions, floating text, cramped labels, and unexplained symbols.
- Render modules one at a time in draft quality and review every frame before final export.
- Prefer elegant, maintainable scene code over one-off hacks.

Suggested structure:

1. Hook: why the idea matters.
2. Setup: the simple mental model.
3. Mechanism: the actual process.
4. Engineering detail: how it is implemented or optimized.
5. Payoff: the memorable takeaway.
