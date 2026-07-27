# Open-source narration

The practical local ElevenLabs-style path for this project is Qwen3-TTS through MLX-Audio on Apple Silicon.

## Chosen stack

- [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS) provides open models for custom voices, voice design, cloning, instruction control, and streaming.
- [MLX-Audio](https://github.com/Blaizzy/mlx-audio) runs quantized Qwen3-TTS models locally on Apple Silicon.
- The tested default is `mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-4bit` with the built-in English speaker `Aiden`.
- The inference library is MIT-licensed. Check the license on the exact model repository before redistributing weights or a hosted service.

This is not a complete ElevenLabs replacement. It gives the reel pipeline a good private, local narrator and avoids per-render API charges, but it does not provide ElevenLabs’ hosted editing, production voice library, or provider-returned character timestamps.

## Installation

Keep MLX-Audio in a separate Python 3.12 environment:

```bash
python3.12 -m venv .venv-tts
.venv-tts/bin/python -m pip install 'mlx-audio==0.4.6'
```

The main CLI discovers `.venv-tts/bin/python` automatically. Override it with `--qwen3-python` or `CONTENTMAXXER_QWEN3_PYTHON`.

## Generation safeguards

The Qwen worker:

1. loads the model once for all five beats;
2. caps generation tokens from script length;
3. retries an implausibly long segment with lower temperature and stronger repetition control;
4. rejects output that remains much longer than the requested speech rate;
5. applies pitch-preserving tempo correction when needed;
6. runs the normal loudness, peak, silence, caption, and A/V synchronization gates.

These checks catch runaway duration, but they do not prove semantic fidelity. The final sample set was independently transcribed with `mlx-community/whisper-large-v3-turbo-asr-fp16`; normalized word error against the scripts was 0.0% for orbit, 0.9% for gradient descent, and 3.3% for self-attention. The attention miss centered on the pronunciation/transcription of “softmax.”

## Other viable options

- [Chatterbox](https://github.com/resemble-ai/chatterbox) is MIT-licensed and supports local expressive and cloned voices. It remains available as `--voice-provider chatterbox`; upstream currently targets Python 3.11.
- [Kokoro-MLX](https://github.com/gabrimatic/kokoro-mlx) is small and fast, but offers less instruction and cloning control for this use case.

Only clone a voice you own or have explicit permission to use.
