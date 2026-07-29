"""Local and hosted word-level alignment for synthesized narration."""

from __future__ import annotations

import json
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from .io import portable
from .models import NarrationCue, NarrationTrack, WordTiming


DEFAULT_WORD_ALIGNER_MODEL = "mlx-community/whisper-large-v3-turbo-asr-fp16"
ALIGNMENT_METHOD = "mlx_audio_whisper_cross_attention_dtw_script_map"
DEFAULT_DEEPGRAM_ALIGNER_MODEL = "nova-3"
DEEPGRAM_LISTEN_URL = "https://api.deepgram.com/v1/listen"
DEEPGRAM_ALIGNMENT_METHOD = "deepgram_listen_word_timestamps_script_map"
WORD_RE = re.compile(r"\S+")


class WordAlignmentError(RuntimeError):
    pass


@dataclass(frozen=True)
class _ASRWord:
    text: str
    start: float
    end: float
    probability: Optional[float] = None


def _normalized_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def mlx_whisper_available(python_path: Path, model: str, *, local_only: bool) -> bool:
    if not python_path.is_file():
        return False
    model_path = Path(model)
    if model_path.exists():
        cache_check = "from pathlib import Path; import sys; assert Path(sys.argv[1]).exists()"
    elif local_only:
        cache_check = (
            "import sys; from huggingface_hub import snapshot_download; "
            "snapshot_download("
            "repo_id=sys.argv[1], local_files_only=True, "
            "allow_patterns=['*.json','*.safetensors','*.txt','*.model']"
            ")"
        )
    else:
        cache_check = "import sys"
    check = (
        "import mlx_audio.stt; "
        + cache_check
    )
    try:
        completed = subprocess.run(
            [str(python_path), "-c", check, model],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def _normalized_edit_distance(reference: str, hypothesis: str) -> float:
    if reference == hypothesis:
        return 0.0
    if not reference or not hypothesis:
        return 1.0
    previous = list(range(len(hypothesis) + 1))
    for row, left in enumerate(reference, start=1):
        current = [row]
        for column, right in enumerate(hypothesis, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[column] + 1,
                    previous[column - 1] + (left != right),
                )
            )
        previous = current
    return previous[-1] / max(len(reference), len(hypothesis))


def _substitution_cost(reference: str, hypothesis: str) -> float:
    if reference == hypothesis:
        return 0.0
    return 0.75 + 0.25 * _normalized_edit_distance(reference, hypothesis)


def _alignment_operations(
    script_words: Sequence[str],
    asr_words: Sequence[_ASRWord],
) -> List[Tuple[str, int, int, int, int]]:
    reference = [_normalized_token(word) for word in script_words]
    hypothesis = [_normalized_token(word.text) for word in asr_words]
    rows, columns = len(reference), len(hypothesis)
    costs = [[float("inf")] * (columns + 1) for _ in range(rows + 1)]
    back: List[List[Optional[Tuple[str, int, int]]]] = [
        [None] * (columns + 1) for _ in range(rows + 1)
    ]
    costs[0][0] = 0.0
    for row in range(rows + 1):
        for column in range(columns + 1):
            current = costs[row][column]
            if current == float("inf"):
                continue

            def offer(
                next_row: int,
                next_column: int,
                operation: str,
                added_cost: float,
            ) -> None:
                candidate = current + added_cost
                if candidate < costs[next_row][next_column] - 1e-9:
                    costs[next_row][next_column] = candidate
                    back[next_row][next_column] = (operation, row, column)

            if row < rows and column < columns:
                operation = "equal" if reference[row] == hypothesis[column] else "substitute"
                offer(
                    row + 1,
                    column + 1,
                    operation,
                    _substitution_cost(reference[row], hypothesis[column]),
                )
            if row < rows and column + 1 < columns:
                combined_hypothesis = hypothesis[column] + hypothesis[column + 1]
                merge_distance = _normalized_edit_distance(reference[row], combined_hypothesis)
                if merge_distance == 0:
                    offer(row + 1, column + 2, "merge_asr", 0.05)
                elif merge_distance <= 0.40:
                    offer(
                        row + 1,
                        column + 2,
                        "merge_asr_substitute",
                        0.25 + merge_distance,
                    )
            if row + 1 < rows and column < columns:
                combined_reference = reference[row] + reference[row + 1]
                merge_distance = _normalized_edit_distance(combined_reference, hypothesis[column])
                if merge_distance == 0:
                    offer(row + 2, column + 1, "merge_script", 0.05)
                elif merge_distance <= 0.40:
                    offer(
                        row + 2,
                        column + 1,
                        "merge_script_substitute",
                        0.25 + merge_distance,
                    )
            if row < rows:
                offer(row + 1, column, "delete", 1.0)
            if column < columns:
                offer(row, column + 1, "insert", 1.0)

    operations: List[Tuple[str, int, int, int, int]] = []
    row, column = rows, columns
    while row or column:
        item = back[row][column]
        if item is None:
            raise WordAlignmentError("could not map Whisper words to the narration script")
        operation, previous_row, previous_column = item
        operations.append((operation, previous_row, row, previous_column, column))
        row, column = previous_row, previous_column
    operations.reverse()
    return operations


def _flatten_asr_words(payload: Dict[str, object]) -> List[_ASRWord]:
    words: List[_ASRWord] = []
    segments = payload.get("segments", [])
    if not isinstance(segments, list):
        return words
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        segment_words = segment.get("words", [])
        if not isinstance(segment_words, list):
            continue
        for item in segment_words:
            if not isinstance(item, dict):
                continue
            text = str(item.get("word", "")).strip()
            try:
                start = float(item["start"])
                end = float(item["end"])
            except (KeyError, TypeError, ValueError):
                continue
            if not text or start < 0 or end <= start:
                continue
            probability: Optional[float]
            try:
                probability = float(item["probability"])
            except (KeyError, TypeError, ValueError):
                probability = None
            words.append(_ASRWord(text=text, start=start, end=end, probability=probability))
    return words


def map_whisper_words_to_script(
    cues: Sequence[NarrationCue],
    payload: Dict[str, object],
) -> Tuple[List[NarrationCue], Dict[str, object]]:
    script_entries: List[Tuple[str, str, NarrationCue, Optional[WordTiming]]] = []
    for cue in cues:
        existing = list(cue.words)
        words = WORD_RE.findall(cue.text)
        for index, word in enumerate(words):
            prior = existing[index] if index < len(existing) else None
            script_entries.append((cue.beat_id, word, cue, prior))
    asr_words = _flatten_asr_words(payload)
    if not script_entries or not asr_words:
        raise WordAlignmentError("Whisper returned no usable word timestamps")

    operations = _alignment_operations(
        [entry[1] for entry in script_entries],
        asr_words,
    )
    mapped: Dict[int, Tuple[float, float]] = {}
    substitutions = insertions = deletions = merged_tokens = 0
    for operation, script_start, script_end, asr_start, asr_end in operations:
        if operation in {"equal", "substitute", "merge_asr", "merge_asr_substitute"}:
            if operation in {"substitute", "merge_asr_substitute"}:
                substitutions += 1
            if operation in {"merge_asr", "merge_asr_substitute"}:
                merged_tokens += asr_end - asr_start - 1
            mapped[script_start] = (
                min(word.start for word in asr_words[asr_start:asr_end]),
                max(word.end for word in asr_words[asr_start:asr_end]),
            )
        elif operation in {"merge_script", "merge_script_substitute"}:
            if operation == "merge_script_substitute":
                substitutions += 1
            merged_tokens += script_end - script_start - 1
            start = asr_words[asr_start].start
            end = asr_words[asr_start].end
            weights = [
                max(1, len(_normalized_token(script_entries[index][1])))
                for index in range(script_start, script_end)
            ]
            cursor = start
            total = sum(weights)
            for offset, weight in enumerate(weights):
                index = script_start + offset
                word_end = end if index == script_end - 1 else cursor + (end - start) * weight / total
                mapped[index] = (cursor, word_end)
                cursor = word_end
        elif operation == "delete":
            deletions += script_end - script_start
        elif operation == "insert":
            insertions += asr_end - asr_start

    script_count = len(script_entries)
    timing_coverage = len(mapped) / script_count
    wer = (substitutions + insertions + deletions) / script_count
    if timing_coverage < 0.95 or wer > 0.15:
        raise WordAlignmentError(
            "Whisper alignment did not meet acceptance thresholds "
            f"(coverage={timing_coverage:.3f}; wer={wer:.3f})"
        )

    shifts: List[float] = []
    by_beat: Dict[str, List[WordTiming]] = {}
    last_start_by_beat: Dict[str, float] = {}
    for index, (beat_id, text, cue, prior) in enumerate(script_entries):
        if index in mapped:
            start, end = mapped[index]
            start = max(cue.start_seconds, min(cue.end_seconds, start))
            end = max(start + 0.02, min(cue.end_seconds, end))
            previous_start = last_start_by_beat.get(beat_id, cue.start_seconds)
            start = max(previous_start, start)
            end = max(start + 0.02, end)
            end = min(cue.end_seconds, end)
            if prior is not None:
                shifts.append(abs(start - prior.start_seconds))
        elif prior is not None:
            start, end = prior.start_seconds, prior.end_seconds
        else:
            raise WordAlignmentError("an unmatched script word had no fallback timing")
        if end <= start:
            raise WordAlignmentError("Whisper produced a non-positive mapped word interval")
        last_start_by_beat[beat_id] = start
        by_beat.setdefault(beat_id, []).append(
            WordTiming(
                text=text,
                start_seconds=round(start, 4),
                end_seconds=round(end, 4),
                beat_id=beat_id,
            )
        )

    aligned_cues = [
        replace(cue, words=by_beat.get(cue.beat_id, list(cue.words)))
        for cue in cues
    ]
    ordered_shifts = sorted(shifts)
    median_shift = ordered_shifts[len(ordered_shifts) // 2] if ordered_shifts else 0.0
    p95_index = min(len(ordered_shifts) - 1, int(len(ordered_shifts) * 0.95)) if ordered_shifts else 0
    p95_shift = ordered_shifts[p95_index] if ordered_shifts else 0.0
    report: Dict[str, object] = {
        "script_word_count": script_count,
        "asr_word_count": len(asr_words),
        "timing_coverage_percent": round(timing_coverage * 100, 2),
        "wer": round(wer, 4),
        "substitutions": substitutions,
        "insertions": insertions,
        "deletions": deletions,
        "merged_tokens": merged_tokens,
        "fallback_word_count": script_count - len(mapped),
        "median_absolute_start_shift_seconds": round(median_shift, 4),
        "p95_absolute_start_shift_seconds": round(p95_shift, 4),
        "max_absolute_start_shift_seconds": round(max(shifts) if shifts else 0.0, 4),
    }
    return aligned_cues, report


def deepgram_words_to_whisper_payload(payload: Dict[str, object]) -> Dict[str, object]:
    """Convert a Deepgram /v1/listen response into the segments/words shape the mapper uses."""
    words: List[Dict[str, object]] = []
    results = payload.get("results")
    if isinstance(results, dict):
        channels = results.get("channels")
        if isinstance(channels, list) and channels:
            channel = channels[0]
            if isinstance(channel, dict):
                alternatives = channel.get("alternatives")
                if isinstance(alternatives, list) and alternatives:
                    alternative = alternatives[0]
                    if isinstance(alternative, dict):
                        raw_words = alternative.get("words")
                        if isinstance(raw_words, list):
                            for item in raw_words:
                                if not isinstance(item, dict):
                                    continue
                                text = str(item.get("word", "")).strip()
                                try:
                                    start = float(item["start"])
                                    end = float(item["end"])
                                except (KeyError, TypeError, ValueError):
                                    continue
                                if not text or start < 0 or end <= start:
                                    continue
                                entry: Dict[str, object] = {
                                    "word": text,
                                    "start": start,
                                    "end": end,
                                }
                                try:
                                    entry["probability"] = float(item["confidence"])
                                except (KeyError, TypeError, ValueError):
                                    pass
                                words.append(entry)
    return {"segments": [{"words": words}]}


def transcribe_with_deepgram(
    audio_path: Path,
    api_key: str,
    model: str = DEFAULT_DEEPGRAM_ALIGNER_MODEL,
) -> Dict[str, object]:
    """Request word-level timestamps from Deepgram speech-to-text for a local WAV file."""
    if not audio_path.is_file():
        raise WordAlignmentError(f"narration audio is missing: {audio_path}")
    query = urllib.parse.urlencode(
        {
            "model": model,
            "punctuate": "false",
            "smart_format": "false",
            "numerals": "false",
            "filler_words": "false",
            "language": "en",
        }
    )
    request = urllib.request.Request(
        f"{DEEPGRAM_LISTEN_URL}?{query}",
        data=audio_path.read_bytes(),
        headers={
            "Authorization": f"Token {api_key}",
            "Content-Type": "audio/wav",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            body = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise WordAlignmentError(
            f"Deepgram word alignment failed: HTTP {exc.code}: {detail[-1200:]}"
        ) from exc
    except urllib.error.URLError as exc:
        raise WordAlignmentError(f"Deepgram word alignment failed: {exc}") from exc
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WordAlignmentError(f"Deepgram returned invalid alignment JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise WordAlignmentError("Deepgram returned an unexpected alignment response shape")
    return payload


def align_track_with_deepgram(
    track: NarrationTrack,
    job_dir: Path,
    api_key: str,
    model: str = DEFAULT_DEEPGRAM_ALIGNER_MODEL,
    *,
    transcribe=transcribe_with_deepgram,
) -> NarrationTrack:
    """Align narration words with Deepgram speech-to-text timestamps.

    Uses the same script-exact mapping and acceptance thresholds (>=95% timing
    coverage, <=15% normalized WER) as the local MLX Whisper path, so hosted
    alignment cannot silently lower the bar.
    """
    audio_path = job_dir / track.audio_path
    raw_payload = transcribe(audio_path, api_key, model)
    output_path = job_dir / "video" / "narration" / "deepgram-word-alignment.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(raw_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    aligned_cues, report = map_whisper_words_to_script(
        track.cues,
        deepgram_words_to_whisper_payload(raw_payload),
    )
    metadata_block = raw_payload.get("metadata")
    request_id = ""
    if isinstance(metadata_block, dict):
        request_id = str(metadata_block.get("request_id", ""))
    report.update(
        {
            "status": "aligned",
            "engine": "Deepgram speech-to-text word timestamps",
            "model": model,
            "request_id": request_id,
            "raw_transcript": portable(output_path, job_dir),
        }
    )
    metadata = dict(track.metadata)
    metadata["word_alignment"] = report
    return replace(
        track,
        alignment_method=DEEPGRAM_ALIGNMENT_METHOD,
        cues=aligned_cues,
        metadata=metadata,
    )


def align_track_with_mlx_whisper(
    track: NarrationTrack,
    job_dir: Path,
    python_path: Path,
    model: str = DEFAULT_WORD_ALIGNER_MODEL,
) -> NarrationTrack:
    audio_path = job_dir / track.audio_path
    if not audio_path.is_file():
        raise WordAlignmentError(f"narration audio is missing: {audio_path}")
    prefix = job_dir / "video" / "narration" / "whisper-word-alignment"
    output_path = prefix.with_suffix(".json")
    command = [
        str(python_path),
        "-m",
        "mlx_audio.stt.generate",
        "--model",
        model,
        "--audio",
        str(audio_path),
        "--output-path",
        str(prefix),
        "--format",
        "json",
        "--language",
        "en",
        "--gen-kwargs",
        json.dumps(
            {
                "word_timestamps": True,
                "temperature": 0.0,
                "condition_on_previous_text": True,
            },
            separators=(",", ":"),
        ),
    ]
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout)[-2000:]
        raise WordAlignmentError(f"local Whisper alignment failed: {detail}")
    if not output_path.is_file():
        raise WordAlignmentError("local Whisper alignment did not produce JSON output")
    try:
        payload = json.loads(output_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WordAlignmentError(f"local Whisper alignment JSON is invalid: {exc}") from exc
    aligned_cues, report = map_whisper_words_to_script(track.cues, payload)
    report.update(
        {
            "status": "aligned",
            "engine": "mlx-audio Whisper cross-attention DTW",
            "model": model,
            "raw_transcript": portable(output_path, job_dir),
        }
    )
    metadata = dict(track.metadata)
    metadata["word_alignment"] = report
    return replace(
        track,
        alignment_method=ALIGNMENT_METHOD,
        cues=aligned_cues,
        metadata=metadata,
    )
