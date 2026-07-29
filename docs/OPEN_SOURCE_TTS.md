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
2. splits each beat into sentence- or clause-bounded generation units of at most 16 words;
3. detects output that reaches the audio-token ceiling and retries it with more token headroom;
4. retries implausibly long chunks with lower temperature and stronger repetition control;
5. rejects output that remains incomplete or much longer than the requested speech rate;
6. records chunk count, duration, attempts, token budget, and cap retries without exposing internal paths;
7. applies pitch-preserving tempo correction when needed;
8. runs the normal loudness, peak, silence, caption, and A/V synchronization gates.

The final AAC mux uses a −2.5 dB true-peak target plus a non-boosting limiter to leave headroom for codec overshoot, then pins delivery audio to 48 kHz mono so the loudness filter cannot leave an unnecessary high-rate stream. These checks catch runaway duration, clipped generation, unsafe peaks, and delivery-encode drift, but they do not prove semantic fidelity. Independently transcribe or listen to every finalist. The checked sample set used `mlx-community/whisper-large-v3-turbo-asr-fp16`; technical-name misses remain a reason to compare another voice or use a supported pronunciation control.

## Optional hosted quality comparison

Deepgram Aura-2 is available as an explicit hosted backend:

```bash
contentmaxxer director "A sourced topic" \
  --voice-provider deepgram \
  --voice aura-2-thalia-en \
  --voice-rate 170
```

Set `DEEPGRAM_API_KEY` in the process environment or a git-ignored `.env.local` file. The parser reads only the requested value and never executes the file. The provider requests mono Linear16 WAV at 48 kHz, then runs the same PCM normalization, measured beat timing, caption, loudness, silence, and A/V gates as the local providers.

`--voice-rate` maps 170 WPM to Aura speed `1.0`, with proportional values clamped to Deepgram’s documented `0.7`–`1.5` range. The default Deepgram model is `aura-2-thalia-en`; pass another Aura model through `--voice`. Request IDs, response model, effective speed, and billed character counts are recorded when Deepgram returns those headers. Deepgram remains opt-in and does not replace the tested Qwen/Aiden default automatically.

### Tested short-form cadence

For the 103-word open-weights educational script, Thalia at `--voice-rate 200` mapped to Aura speed `1.176` and shortened the measured master from 49.52 to 40.04 seconds. Effective delivery increased from 126.0 to 155.8 WPM; short-pause time fell from 8.44 to 3.94 seconds; independent Whisper WER remained 1.92%; and all tested policy/technical terms were recovered. The faster master used five requests and 677 provider-reported characters. It was selected without changing the global 170 default because cadence depends on the voice and script.

The final aligned Director Cut import of that master passed encoded-media checks at 40.04 seconds, 154.3 caption WPM, −17.70 LUFS, −2.35 dBFS true peak, 0.0601 seconds A/V drift, 46.5% upper-diagram motion coverage, and a 3.2-second longest static run. Use `--voice-rate 200` as the current explicit Thalia starting point for energetic reels, then validate the actual master before paying for a full rerender.

For a denser five-stage mechanism, first tighten the script and then use `--voice-rate 190` as a less rushed starting point. The extractive DNS validation used five requests and 537 provider-reported characters at Aura speed `1.118`. Its 91-word master ran 30.08 seconds at 181.5 WPM, measured −16.94 LUFS with a −2.44 dBFS true peak, contained no long silence, and muxed with 0.0201 seconds of A/V drift. Unprompted Whisper mapped all 91 script words with 1.10% WER: `IP address` was recovered correctly, and the only edit was the orthographic homophone `cacheable`/`cashable`. No price or explicit cost value was present in the recorded response metadata, so the job records character counts and request IDs rather than estimating spend.

The same Thalia/rate pair was checked on an unrelated 88-word browser-navigation script. Five requests and 514 provider-reported characters produced a 32.64-second master at 161.8 WPM. Independent Whisper recovered URL, IP, DNS, TLS, HTTPS, HTTP GET, HTML, DOM, and CSSOM; the single substitution was `content transfer` to `contact transfer`, for 1.14% WER. The delivery encode measured −18.06 LUFS, −2.34 dBFS true peak, no long silence, and 0.0601 seconds of A/V drift. This supports `190` as a useful starting point, not a universal speed guarantee: the same requested speed delivered different effective cadence because the scripts and pauses differ.

The TCP feedback-loop experiment exposed take-to-take variation in the same Aura voice. Instead of spending another request or rerendering full videos, the accepted master reuses four independently checked Thalia segments from one take and the corrected loss segment from a later take. That beat-level selection made zero new provider requests. The resulting 121-word master ran 41.96 seconds; large Whisper alignment reached 100% coverage at 1.65% WER, while a separate tiny-Whisper transcription scored 12.4% WER and still recovered `network round trip`, `data still in flight`, and `tests capacity again`. The final encode measured −17.18 LUFS, −2.36 dBFS true peak, no long silence, and 0.0401 seconds of A/V drift. Available response metadata did not include a monetary-cost header, so the artifact records selected characters and source takes without inventing a dollar estimate.

### Local word alignment

The director defaults to `--word-aligner auto`. For newly synthesized narration with proportional word timings, auto uses a locally cached `mlx-community/whisper-large-v3-turbo-asr-fp16` model through MLX-Audio. It requests Whisper's cross-attention/DTW word timestamps, sequence-aligns the recognized tokens to the exact grounded script, and preserves the script spelling in captions. A result is accepted only with at least 95% timing coverage and at most 15% normalized WER; otherwise auto records the reason and retains the prior measured proportional timing. Auto does not download a model and does not alter imported timing maps.

Use explicit mode to download the configured model if needed or to refine an imported master:

```bash
contentmaxxer director "A sourced topic" \
  --voice-provider file \
  --narration-file voiceover.wav \
  --narration-timings timings.json \
  --word-aligner mlx-whisper
```

The raw local transcript, model, coverage, WER, edit counts, fallback count, and timing-shift distribution are recorded in the job. This alignment transcript is an internal timing artifact, not a replacement for the independent unprompted transcription/listening check used to judge narration quality.

The mapper was also checked on four preserved Qwen/Aiden mechanism masters: orbit, gradient descent, self-attention, and Bayesian updating. All four reached 100% script-word timing coverage with zero fallback words and 0–2.86% WER. Median word-start corrections ranged from 0.132 to 0.361 seconds and maximum corrections from 0.822 to 1.005 seconds. Approximate token merges safely recovered cases such as Whisper fusing “A softmax” into one recognized token, while unrelated-audio tests still fail the 15% WER gate.

In semantic Manim styles, the aligned words also drive motion directly. The opening caption retains its stage-entry animation; later captions swap on their normal phrase boundary, while style-native emphasis waits for the first semantic trigger word in that phrase. Scheduled-event counts, delays, and validity are recorded and hard-gated. Imported aligned timing maps copy their raw transcript into the new job so manifests remain portable.

For a checked technical name, repeat `--voice-pronunciation WORD=IPA`. The override is sent through Aura-2’s inline pronunciation control while the grounded script and caption text remain unchanged:

```bash
--voice-pronunciation 'softmax=ˈsɔftmæks'
```

Treat an override as an experiment, not an automatic fix. Deepgram expects contiguous IPA inside its inline JSON control; the CLI removes accidental internal whitespace before sending it. In the TCP probe, acronym overrides for `cwnd` and `ssthresh` still produced worse independent-ASR results than speaking the full technical terms, so the accepted reel uses `congestion window` and `slow-start threshold` with no pronunciation override. Validate names and acronyms with the actual audio or an independent transcript before selecting a take.

## Other viable options

- [Chatterbox](https://github.com/resemble-ai/chatterbox) is MIT-licensed and supports local expressive and cloned voices. It remains available as `--voice-provider chatterbox`; upstream currently targets Python 3.11.
- [Kokoro-MLX](https://github.com/gabrimatic/kokoro-mlx) is small and fast, but offers less instruction and cloning control for this use case.

Only clone a voice you own or have explicit permission to use.
