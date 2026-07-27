# contentmaxxer

`contentmaxxer` is a source-grounded, Manim-first production CLI for technical reels and carousels. It caches every URL or local note inside the job, turns evidence into typed claims, requires factual scenes and slides to cite those claims, and runs hard QA gates before declaring an artifact complete.

Educational reels use narration-led timing, four-word kinetic captions, hand-drawn multi-sketch explanations, actual rendered-frame contact sheets, and encoded-audio checks for loudness, peak, dead air, alignment, and A/V drift. See the [educational reel playbook](docs/EDUCATIONAL_REELS.md), [open-source voice notes](docs/OPEN_SOURCE_TTS.md), and [director prompt](prompts/educational-reel-system.md).

Carousels use an engagement-first editorial system: three scored angles, at least 12 hooks, a cover-to-payoff swipe narrative, original full-bleed art, three rendered cover tests, and hard gates for hook brevity, one idea per slide, visual variety, and save/share/comment payoff. See the [carousel engagement playbook](docs/CAROUSEL_ENGAGEMENT_PLAYBOOK.md) and [agent system prompt](prompts/carousel-system.md).

Manim is the polished director. `--renderer auto` prefers it and clearly records a `raster_fallback` when Manim is unavailable. The fallback is useful for smoke tests; it is never mislabeled as polished Manim output. The manual `render` command remains available for bespoke scenes. Remotion is intentionally not part of this runtime.

## Install and verify

```bash
python -m venv .venv
.venv/bin/python -m pip install -e '.[animation]'
.venv/bin/python -m unittest discover -s tests -v
```

Manim integration tests are opt-in with `CONTENTMAXXER_MANIM_INTEGRATION=1`. Cairo and Pango must also be available on the host (for example, `brew install pkg-config cairo pango` on macOS).

For the local Apple-Silicon voice path, use a separate Python 3.12 environment so the Manim environment can keep its own dependency set:

```bash
python3.12 -m venv .venv-tts
.venv-tts/bin/python -m pip install 'mlx-audio==0.4.6'
```

## Grounded workflow

```bash
contentmaxxer research "A sourced topic" \
  --job sourced_topic \
  --source-url https://example.com/reference \
  --source-file notes.md

contentmaxxer director "A sourced topic" \
  --job sourced_topic \
  --offline \
  --renderer auto \
  --hook-style question

# Local macOS narration with measured timing and word captions.
contentmaxxer director "A sourced topic" \
  --job sourced_topic \
  --offline \
  --renderer manim \
  --voice-provider say \
  --voice Samantha \
  --voice-rate 170

# Premium timestamped narration (uses ELEVENLABS_API_KEY).
contentmaxxer director "A sourced topic" \
  --job sourced_topic \
  --offline \
  --renderer manim \
  --voice-provider elevenlabs \
  --voice YOUR_ELEVENLABS_VOICE_ID

# Open-source, local Apple-Silicon narration with Qwen3-TTS through MLX-Audio.
# The first run downloads the selected model; later runs use the local cache.
contentmaxxer director "A sourced topic" \
  --job sourced_topic \
  --offline \
  --renderer manim \
  --voice-provider qwen3 \
  --voice Aiden \
  --voice-rate 165 \
  --voice-instruction "Warm, curious, conversational educational narrator. Speak only the supplied text once."

# Open-source local narration. Chatterbox is tested upstream on Python 3.11;
# use `pip install -e '.[animation,local-voice]'` in that environment.
contentmaxxer director "A sourced topic" \
  --job sourced_topic \
  --offline \
  --renderer manim \
  --voice-provider chatterbox \
  --voice-reference clean-voice-reference.wav

# Or import a finished narration track.
contentmaxxer director "A sourced topic" \
  --job sourced_topic \
  --offline \
  --renderer manim \
  --voice-provider file \
  --narration-file narration.wav

contentmaxxer slides "A sourced topic" \
  --job sourced_topic \
  --offline \
  --count 7 \
  --target 9:16 \
  --target 4:5

# Alternate code-native collage system; no AI-generated hero image.
contentmaxxer slides "A sourced topic" --offline --style paper-meme
```

Supported hook styles are `direct`, `question`, `contrarian`, `statistic`, `curiosity`, `story`, and `list`. A statistic hook is rejected unless at least one cited claim is numeric.

Without sufficient sources, `director` and `slides` write a blocked, ungrounded plan and stop before rendering. `--allow-ungrounded` is an explicit escape hatch for visibly speculative placeholders; such work fails the grounding QA gate by design.

`--voice-provider auto` prefers configured ElevenLabs, then the external Qwen3/MLX environment, then Chatterbox, then macOS speech. Qwen3 beat duration is measured from its actual WAV output, but its word timings are proportional estimates. Use an independent ASR or listening pass before publishing.

## Target profiles

Carousels are re-laid out for each profile rather than resized. Supported grouped targets are `9:16`, Instagram-native `3:4`, and `4:5`; platform-specific profiles include `tiktok`, `stories`, `reels`, `instagram`, and `linkedin`.

## GPT-5.6 set

```bash
contentmaxxer gpt56-set --output-dir jobs --renderer auto --count 7
```

This builds `gpt_5_6_family_tiers` and `gpt_5_6_capability_controls`, each with a reel and 9:16 plus 4:5 carousel variants. Their sources are locked to July 9, 2026 and point to the general-availability launch, current model docs, and GPT-5.6 System Card. If a source is unreachable, the command records that it used the packaged locked snapshot instead of pretending a network retrieval succeeded.

## Five-post creative test

```bash
contentmaxxer five-post-set --output-dir jobs --count 7
```

This builds the paper/meme clone, Fable 5 versus GPT-5.6 in both visual systems, and the model-economics angle in both systems. Every post exports 9:16, 3:4, and 4:5, with three cover tests per ratio. `paper_meme_v1` is entirely code-native: graph paper, marker typography, tape, receipts, doodles, and comparison cards, with no generated hero art.

## Job contract

Each completed job includes:

- source snapshots, normalized text, retrieval metadata, and SHA-256 digests;
- `claims.json`, content plans, and `citations.md`;
- a typed Manim spec and deterministic `scene.py`;
- reel MP4, burned caption rail, SRT, contact sheet, and scene-level citations;
- exact-count carousel PNGs and contact sheets per adapted target;
- portable `manifest.json` paths;
- initial and revised plans plus QA reports;
- `final-file-locations.md`.

QA is gate-based, not score-based: schema, grounding and citation coverage, dimensions, duration, caption rate, safe bounds, text size, truncation, overlap, density, blank or duplicate media, missing files, and manifest integrity must all pass after the single deterministic revision.

Carousel QA additionally requires 12 hook options, three angle options, three rendered cover candidates per target, concise cover/body copy, one idea per slide, a cover-to-payoff role progression, visual variety, a visible swipe cue, the selected visual theme, and a final engagement payoff.
