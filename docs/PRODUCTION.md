# Production flow: one source in, one reel out

Target: under 30 minutes of human time per finished reel. Machine time (render, TTS, QA) does not count; the human steps are the bottleneck being managed.

## The flow

### 1. Source note (human, ~10 min)

Write or approve `examples/reel-sources/<topic>.md`: grounded claims, exact numbers, framing cautions, source URLs, licensing notes for any imagery. This is the only step where factual quality is decided.

### 2. Voice lab (human, ~3 min)

One bounded audio-only A/B before any render spend:

```bash
PYTHONPATH=src .venv/bin/python -m contentmaxxer.cli voice-lab \
  "One representative sentence from the script, including any risky names." \
  --voice aura-2-thalia-en --voice aura-2-orion-en --voice aura-2-helena-en \
  --voice-rate 180 --output-dir build/<job>/voice-lab
```

Each candidate gets a WAV plus an independent Deepgram transcript in `report.json`. Listen, check the transcripts for pronunciation drift, pick one voice. Fix names with `--voice-pronunciation WORD=IPA` here, not with full rerenders.

### 3. Produce (machine, one command)

Save a job config once, then:

```bash
PYTHONPATH=src .venv/bin/python -m contentmaxxer.cli produce examples/reel-configs/<topic>.json
```

Config keys mirror the `director` flags (`topic`, `job`, `source_files`, `renderer`, `animation_style`, `voice_provider`, `voice`, `voice_rate`, `voice_pronunciations`, `word_aligner`, `burn_captions`, ...). Unknown keys fail loudly. The command runs research -> plan -> Deepgram narration -> word alignment -> Manim render -> mux -> QA -> manifest, and writes `REVIEW.md` into the job directory.

Aligner note: `--word-aligner deepgram` uses hosted Nova word timestamps (same >=95% coverage and <=15% WER acceptance gates as local MLX Whisper). Use it when the MLX model is not cached or when running off-Mac.

### 4. Review (human, ~10 min)

Follow `build/<job>/REVIEW.md`: watch the encoded reel with sound, inspect both contact sheets, verify claims against `citations.md`, check the first two seconds. Tests and QA are necessary, never sufficient.

### 5. Accept and slim (human, ~2 min)

One finalist only. After acceptance, Trash reproducible intermediates (`video/manim_media/`, `video/narration/segments/`); keep the reel, narration master, timing map, spec, QA, contact sheets, and source records.

## What stays manual on purpose

- Approving claims and framing (source note).
- Choosing the voice (voice lab).
- The final watch-and-listen before posting.

Everything else is one command.
