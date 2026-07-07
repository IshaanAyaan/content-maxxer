# Production Prompt: Nexus Explainer H

Use Manim Community.

Docs: https://docs.manim.community/en/stable/

For the paper called Nexus at https://arxiv.org/pdf/2604.09258, create a high quality Manim animation explaining the process from the ground up. Walk through the smallest parts using 3D graph animations, optimization functions, relational optimizer functions, and any figures needed from the paper.

Do not take the easy way from the developer standpoint. Avoid scrappy shortcuts. Be thorough and elegant, with no pressure to finish quickly.

The animation should:

- explain the concept to regular people without losing the real mechanism;
- port over useful figures from the paper when they make the idea clearer;
- use sub-scene modules that can be rendered one at a time;
- be reviewed frame by frame so animations do not feel awkward or out of place;
- stitch the modules together at the end;
- be about one minute long;
- move quickly enough for shortform, but not so fast that the viewer loses the analogy.

Target structure:

1. Show that the same pretraining score can hide different landing places.
2. Use a 3D landscape to make optimizer path differences visible.
3. Explain why closeness to the downstream valley matters.
4. Show the engineering adaptation: clone model, run inner steps, convert displacement into a gradient-like signal.
5. End with: optimize agreement, not just the score.
