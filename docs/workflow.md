# Contentmaxx Workflow

## Concise read of the current method

Your current prompt is a high-context production brief. It tells the model the source, the expected quality bar, the audience, the duration, the visual technique, and the process constraints. The Nexus render shows the method working as a visual-first explainer: dark high-contrast design, short labels, a few precise diagrams, loss landscapes, and a final one-sentence takeaway.

What is missing is the production wrapper around it: saved research notes, stable templates, scene-by-scene review, voiceover/captions, export variants, and a repeatable command path.

## Upgrade plan

1. Intake
   Capture source URL, target viewer, desired duration, output format, and the one belief the viewer should leave with.

2. Research pack
   Extract abstract, claims, definitions, figures, equations, and analogies. Save them in the job folder before writing code.

3. Script and storyboard
   Force every video into five beats: hook, setup, mechanism, implementation detail, takeaway. Keep each beat renderable as its own section.

4. Manim scene modules
   Build scene sections independently, render each in draft quality, then stitch only after every section passes visual review.

5. QA loop
   Generate a contact sheet, check text overflow, check awkward pauses, check camera motion, check final duration, and check mobile crop safety.

6. Finish pass
   Add voiceover, captions, audio mix, 16:9 master, 9:16 short, and thumbnail frame.

7. Slides lane later
   Reuse the same intake and research pack, but swap Manim scenes for slide templates and presenter notes.

## Definition of done

A content job is done when the repo contains:

- `prompt.md`: the exact production prompt.
- `brief.md`: audience, goal, constraints, and source.
- `research.md`: facts, figures, equations, and links.
- `script.md`: narration or captions.
- `storyboard.md`: scene-by-scene visual plan.
- `scene.py`: renderable Manim code.
- `reference/`: final export, contact sheet, and notable frames.
