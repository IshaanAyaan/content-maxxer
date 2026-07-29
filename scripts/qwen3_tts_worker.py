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
        chunks = [str(chunk).strip() for chunk in segment.get("chunks", []) if str(chunk).strip()] or [text]
        piece_waveforms = []
        piece_metadata = []
        for chunk_index, chunk in enumerate(chunks, start=1):
            chunk_word_count = max(1, len(re.findall(r"\S+", chunk)))
            chunk_expected_seconds = chunk_word_count / max(100, target_wpm) * 60.0
            waveform = None
            actual_seconds = 0.0
            token_cap_retries = 0
            used_max_tokens = 0
            attempts = 0
            for attempt in range(3):
                attempts = attempt + 1
                base_tokens = max(80, min(320, int(chunk_word_count * 8.0 + 32)))
                max_tokens = min(640, int(base_tokens * (1.0 if attempt == 0 else 1.6 + 0.4 * (attempt - 1))))
                used_max_tokens = max_tokens
                attempt_instruction = (
                    (instruction or "")
                    + " Speak at a natural short-form educational video pace. "
                    "Finish every supplied sentence. Do not add commentary, repeat words, "
                    "or insert long dramatic pauses."
                )
                results = list(
                    model.generate_custom_voice(
                        text=chunk,
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
                near_token_cap = actual_seconds >= (max_tokens / 12.0) * 0.93
                implausibly_long = actual_seconds > max(3.0, chunk_expected_seconds * 2.2)
                if near_token_cap:
                    token_cap_retries += 1
                if not near_token_cap and not implausibly_long:
                    break
                waveform = None
            if waveform is None:
                raise RuntimeError(
                    f"Qwen3-TTS could not complete {segment['id']} chunk {chunk_index} "
                    f"(last_duration={actual_seconds:.2f}s, expected_about={chunk_expected_seconds:.2f}s)"
                )
            piece_waveforms.append(waveform)
            if chunk_index < len(chunks):
                piece_waveforms.append(np.zeros(int(model.sample_rate * 0.10), dtype=np.float32))
            piece_metadata.append(
                {
                    "chunk_index": chunk_index,
                    "word_count": chunk_word_count,
                    "duration_seconds": round(actual_seconds, 4),
                    "attempts": attempts,
                    "max_tokens": used_max_tokens,
                    "token_cap_retries": token_cap_retries,
                }
            )
        waveform = np.concatenate(piece_waveforms)
        actual_seconds = waveform.size / float(model.sample_rate)
        destination = args.output_dir / f"{index:02d}-{segment['id']}-qwen3-native.wav"
        wavfile.write(destination, int(model.sample_rate), _pcm16(waveform))
        outputs.append(
            {
                "id": segment["id"],
                "path": destination.name,
                "sample_rate": int(model.sample_rate),
                "duration_seconds": round(actual_seconds, 4),
                "expected_seconds": round(expected_seconds, 4),
                "chunk_count": len(chunks),
                "chunks": piece_metadata,
            }
        )

    print(json.dumps({"model": model_id, "speaker": speaker, "outputs": outputs}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
