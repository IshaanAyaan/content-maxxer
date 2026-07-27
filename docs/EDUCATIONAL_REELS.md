# Educational reels

The reel workflow converts a grounded note into a narrated 1080×1920 Manim video:

`sources → ordered claims → five-beat script → narration → measured timing → five complementary hand-drawn sketches → captions → loudness-normalized MP4 → actual-frame and transcript QA`

The animation system uses a restrained chalkboard language: deterministic multi-pass rough strokes, marker lettering, sticky-note callouts, a persistent five-sketch rail, narration-triggered highlights, and quick erase-and-redraw transitions. Each beat gets a different explanatory composition while palette, typography, source badge, and caption rail stay coherent.

## Reproduce the three reference renders

Run these from the repository root after installing the `animation` extra and the Cairo/Pango system packages described in the README:

```bash
.venv/bin/python -m contentmaxxer director \
  "Why satellites stay in orbit" \
  --job satellites_handdrawn_qwen3_final \
  --output-dir build/handdrawn-reels \
  --source-file examples/reel-sources/orbits.md \
  --hook-style question \
  --renderer manim \
  --voice-provider qwen3 \
  --voice Aiden \
  --voice-rate 165

.venv/bin/python -m contentmaxxer director \
  "How gradient descent learns" \
  --job gradient_descent_handdrawn_qwen3_v2 \
  --output-dir build/handdrawn-reels \
  --source-file examples/reel-sources/gradient-descent.md \
  --hook-style question \
  --renderer manim \
  --voice-provider qwen3 \
  --voice Aiden \
  --voice-rate 165

.venv/bin/python -m contentmaxxer director \
  "How self-attention builds context" \
  --job self_attention_handdrawn_qwen3 \
  --output-dir build/handdrawn-reels \
  --source-file examples/reel-sources/self-attention.md \
  --hook-style question \
  --renderer manim \
  --voice-provider qwen3 \
  --voice Aiden \
  --voice-rate 165
```

Each job contains `video/reel.mp4`, the editable generated Manim scene, the source-backed plan, word timing JSON, SRT captions, actual rendered preview frames, a contact sheet, the original voiceover WAV, citations, a portable manifest, and the complete QA report.

## Narration providers

- `elevenlabs`: premium synthesis with provider character timestamps; requires `ELEVENLABS_API_KEY` and a voice ID.
- `qwen3`: local Qwen3-TTS through an external MLX-Audio environment; supports instruction-controlled built-in voices on Apple Silicon. The tested 0.6B 4-bit model is cached after first use.
- `chatterbox`: MIT-licensed local/open-source synthesis through the official `chatterbox-tts` package; upstream recommends Python 3.11. An optional clean voice reference may be supplied only when you have permission to use that voice.
- `say`: dependency-light local macOS fallback. Audio duration is measured, while word boundaries are distributed proportionally within each spoken beat.
- `file`: imports a finished narration track and apportions it to the grounded script.

`auto` prefers configured ElevenLabs, then the external Qwen3 environment, then an installed Chatterbox package, then macOS speech. Provider, voice, timing method, duration, sample rate, alignment counts, loudness, peak, silence, and A/V drift are recorded in the job.

Qwen3 does not return the word timestamps used here. Beat boundaries come from measured segment audio, and words are distributed proportionally inside each beat. Before publishing, independently transcribe or listen to the rendered voiceover; the checked final set was verified with Whisper large-v3-turbo as described in [OPEN_SOURCE_TTS.md](OPEN_SOURCE_TTS.md).

## Quality contract

Approval requires grounded claim coverage, an explicit explanatory progression, at least four meaningfully different explanatory sketches, concise copy, 25–60 second runtime, readable caption rate, 1080×1920 frames, nonblank and nonduplicate samples, safe layout boxes, audio and video streams, at least 95% timing coverage, no long dead-air interval, −20 to −12 integrated LUFS, true peak at or below −1 dBFS, at most 0.25 seconds of A/V drift, and a portable complete manifest.

The three checked-in example notes are intentionally short and cite primary teaching references. Raw reference lines remain in the source snapshot and citations but are filtered out of narration.
