#!/usr/bin/env python3
"""Generate a batch of local Qwen3-TTS segments in one MLX model session."""

import argparse
import json
import re
from pathlib import Path

import numpy as np
from mlx_audio.tts.utils import load_model
from scipy.io import wavfile


def _pcm16(audio: object) -> np.ndarray:
    waveform = np.asarray(audio, dtype=np.float32).squeeze()
    if waveform.ndim != 1:
        raise RuntimeError(f"expected mono waveform, got shape={waveform.shape}")
    peak = float(np.max(np.abs(waveform))) if waveform.size else 0.0
    if peak > 1.0:
        waveform = waveform / peak
    return (np.clip(waveform, -1.0, 1.0) * 32767.0).astype(np.int16)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    request = json.loads(args.request.read_text(encoding="utf-8"))
    model_id = str(request["model"])
    speaker = str(request.get("speaker") or "Aiden")
    language = str(request.get("language") or "English")
    instruction = str(request.get("instruction") or "").strip() or None
    temperature = float(request.get("temperature", 0.82))
    target_wpm = int(request.get("target_wpm", 165))

    model = load_model(model_id)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    outputs = []
    for index, segment in enumerate(request["segments"], start=1):
        text = str(segment["text"])
        word_count = max(1, len(re.findall(r"\S+", text)))
        expected_seconds = word_count / max(100, target_wpm) * 60.0
        waveform = None
        actual_seconds = 0.0
        for attempt in range(2):
            max_tokens = max(96, min(360, int(word_count * (7.0 if attempt == 0 else 6.0) + 24)))
            attempt_instruction = (
                (instruction or "")
                + " Speak at a natural short-form educational video pace. "
                "Do not add commentary, repeat words, or insert long dramatic pauses."
            )
            results = list(
                model.generate_custom_voice(
                    text=text,
                    speaker=speaker,
                    language=language,
                    instruct=attempt_instruction,
                    temperature=temperature if attempt == 0 else min(temperature, 0.68),
                    max_tokens=max_tokens,
                    top_p=0.92 if attempt == 0 else 0.84,
                    repetition_penalty=1.12 if attempt == 0 else 1.18,
                    stream=False,
                )
            )
            if not results:
                continue
            waveform = np.concatenate([np.asarray(result.audio).squeeze() for result in results])
            actual_seconds = waveform.size / float(model.sample_rate)
            if actual_seconds <= max(4.0, expected_seconds * 1.85):
                break
            waveform = None
        if waveform is None:
            raise RuntimeError(
                f"Qwen3-TTS produced implausibly long speech for {segment['id']} "
                f"(last_duration={actual_seconds:.2f}s, expected_about={expected_seconds:.2f}s)"
            )
        destination = args.output_dir / f"{index:02d}-{segment['id']}-qwen3-native.wav"
        wavfile.write(destination, int(model.sample_rate), _pcm16(waveform))
        outputs.append(
            {
                "id": segment["id"],
                "path": destination.name,
                "sample_rate": int(model.sample_rate),
                "duration_seconds": round(actual_seconds, 4),
                "expected_seconds": round(expected_seconds, 4),
            }
        )

    print(json.dumps({"model": model_id, "speaker": speaker, "outputs": outputs}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
