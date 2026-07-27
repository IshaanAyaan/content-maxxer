"""Narration synthesis, timing, captions, and final audio packaging."""

import aifc
import audioop
import base64
import importlib.util
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import wave
from dataclasses import replace
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from imageio_ffmpeg import get_ffmpeg_exe

from .io import portable, write_json
from .models import ContentPlan, NarrationCue, NarrationTrack, VideoBeat, WordTiming


DEFAULT_SAMPLE_RATE = 48_000
DEFAULT_RATE_WPM = 170
BEAT_PAUSE_SECONDS = 0.18
WORD_RE = re.compile(r"\S+")
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_QWEN3_PYTHON = PROJECT_ROOT / ".venv-tts" / "bin" / "python"
DEFAULT_QWEN3_MODEL = "mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-4bit"


class NarrationError(RuntimeError):
    pass


def _run(command: Sequence[str], label: str) -> subprocess.CompletedProcess:
    completed = subprocess.run(list(command), capture_output=True, text=True)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout)[-2200:]
        raise NarrationError(f"{label} failed: {detail}")
    return completed


def _audio_duration(path: Path) -> float:
    if path.suffix.lower() == ".wav":
        with wave.open(str(path), "rb") as audio:
            return audio.getnframes() / float(audio.getframerate())
    if path.suffix.lower() in {".aif", ".aiff"}:
        with aifc.open(str(path), "rb") as audio:
            return audio.getnframes() / float(audio.getframerate())
    raise NarrationError(f"unsupported uncompressed audio file: {path}")


def _validate_spoken_wav(path: Path, text: str, rate_wpm: int) -> None:
    with wave.open(str(path), "rb") as audio:
        frames = audio.readframes(audio.getnframes())
        duration = audio.getnframes() / float(audio.getframerate())
        rms = audioop.rms(frames, audio.getsampwidth()) if frames else 0
    word_count = max(1, len(WORD_RE.findall(text)))
    expected = word_count / max(80.0, float(rate_wpm)) * 60.0
    if duration < max(0.35, expected * 0.35) or rms < 8:
        raise NarrationError(
            "local speech synthesis produced empty or implausibly short audio "
            f"(duration={duration:.3f}s, rms={rms}, expected_about={expected:.3f}s). "
            "On macOS this usually means the speech service is unavailable in the current sandbox."
        )


def _convert_to_wav(
    source: Path,
    destination: Path,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    audio_filter: Optional[str] = None,
) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [
        get_ffmpeg_exe(),
        "-y",
        "-i",
        str(source),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
    ]
    if audio_filter:
        command.extend(["-af", audio_filter])
    command.extend(
        [
            "-c:a",
            "pcm_s16le",
            str(destination),
        ]
    )
    _run(
        command,
        "audio conversion",
    )
    return destination


def _word_weights(words: Sequence[str]) -> List[float]:
    return [float(max(1, len(re.sub(r"[^A-Za-z0-9]+", "", word)))) for word in words]


def proportional_word_timings(
    text: str,
    beat_id: str,
    start_seconds: float,
    end_seconds: float,
) -> List[WordTiming]:
    words = WORD_RE.findall(text)
    if not words:
        return []
    weights = _word_weights(words)
    total = sum(weights)
    usable = max(0.05, end_seconds - start_seconds)
    cursor = start_seconds
    timings: List[WordTiming] = []
    for index, (word, weight) in enumerate(zip(words, weights)):
        word_end = end_seconds if index == len(words) - 1 else cursor + usable * weight / total
        timings.append(WordTiming(word, round(cursor, 4), round(word_end, 4), beat_id))
        cursor = word_end
    return timings


def _alignment_word_timings(
    text: str,
    beat_id: str,
    offset_seconds: float,
    alignment: Dict[str, object],
) -> List[WordTiming]:
    characters = alignment.get("characters", [])
    starts = alignment.get("character_start_times_seconds", [])
    ends = alignment.get("character_end_times_seconds", [])
    if not isinstance(characters, list) or not isinstance(starts, list) or not isinstance(ends, list):
        return []
    if not (len(characters) == len(starts) == len(ends)):
        return []
    joined = "".join(str(item) for item in characters)
    timings: List[WordTiming] = []
    for match in WORD_RE.finditer(joined):
        first = match.start()
        last = match.end() - 1
        timings.append(
            WordTiming(
                match.group(0),
                round(offset_seconds + float(starts[first]), 4),
                round(offset_seconds + float(ends[last]), 4),
                beat_id,
            )
        )
    if len(timings) != len(WORD_RE.findall(text)):
        return []
    return timings


def _concat_wavs(
    segments: Sequence[Tuple[VideoBeat, Path]],
    destination: Path,
    pause_seconds: float = BEAT_PAUSE_SECONDS,
    aligned_words: Optional[Dict[str, List[WordTiming]]] = None,
) -> Tuple[List[NarrationCue], float, int]:
    if not segments:
        raise NarrationError("cannot create narration without video beats")
    destination.parent.mkdir(parents=True, exist_ok=True)
    cues: List[NarrationCue] = []
    cursor = 0.0
    with wave.open(str(segments[0][1]), "rb") as first:
        channels = first.getnchannels()
        width = first.getsampwidth()
        rate = first.getframerate()
        compression = first.getcomptype()
    if channels != 1 or width != 2 or compression != "NONE":
        raise NarrationError("narration segments must be mono 16-bit PCM WAV")
    silence = b"\x00" * int(round(rate * pause_seconds)) * channels * width
    with wave.open(str(destination), "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(width)
        output.setframerate(rate)
        for index, (beat, path) in enumerate(segments):
            with wave.open(str(path), "rb") as audio:
                params = (audio.getnchannels(), audio.getsampwidth(), audio.getframerate(), audio.getcomptype())
                if params != (channels, width, rate, compression):
                    raise NarrationError(f"inconsistent narration segment format: {path}")
                frames = audio.readframes(audio.getnframes())
                segment_duration = audio.getnframes() / float(rate)
            start = cursor
            spoken_end = start + segment_duration
            output.writeframes(frames)
            if index < len(segments) - 1:
                output.writeframes(silence)
                cursor = spoken_end + pause_seconds
            else:
                cursor = spoken_end
            words = list((aligned_words or {}).get(beat.id, []))
            if words:
                words = [
                    WordTiming(word.text, word.start_seconds + start, word.end_seconds + start, word.beat_id)
                    for word in words
                ]
            else:
                words = proportional_word_timings(beat.narration, beat.id, start, spoken_end)
            cues.append(
                NarrationCue(
                    beat_id=beat.id,
                    text=beat.narration,
                    start_seconds=round(start, 4),
                    end_seconds=round(cursor, 4),
                    words=words,
                )
            )
    return cues, cursor, rate


def _say_segments(
    beats: Sequence[VideoBeat],
    directory: Path,
    voice: str,
    rate_wpm: int,
) -> Sequence[Tuple[VideoBeat, Path]]:
    executable = shutil.which("say")
    if not executable:
        raise NarrationError("macOS `say` is unavailable; choose another narration provider")
    segments: List[Tuple[VideoBeat, Path]] = []
    for index, beat in enumerate(beats, start=1):
        aiff = directory / f"{index:02d}-{beat.id}.aiff"
        wav = directory / f"{index:02d}-{beat.id}.wav"
        command = [executable, "-r", str(rate_wpm), "-o", str(aiff)]
        if voice:
            command.extend(["-v", voice])
        command.append(beat.narration)
        _run(command, f"macOS narration for {beat.id}")
        _convert_to_wav(aiff, wav)
        _validate_spoken_wav(wav, beat.narration, rate_wpm)
        segments.append((beat, wav))
    return segments


def _elevenlabs_segments(
    beats: Sequence[VideoBeat],
    directory: Path,
    voice: str,
) -> Tuple[Sequence[Tuple[VideoBeat, Path]], Dict[str, List[WordTiming]]]:
    api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not api_key:
        raise NarrationError("ELEVENLABS_API_KEY is required for the elevenlabs narration provider")
    if not voice:
        raise NarrationError("--voice is required for the elevenlabs narration provider")
    segments: List[Tuple[VideoBeat, Path]] = []
    alignments: Dict[str, List[WordTiming]] = {}
    quoted_voice = urllib.parse.quote(voice, safe="")
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{quoted_voice}/with-timestamps"
    for index, beat in enumerate(beats, start=1):
        request = urllib.request.Request(
            url,
            data=json.dumps({"text": beat.narration, "model_id": "eleven_multilingual_v2"}).encode("utf-8"),
            headers={"Content-Type": "application/json", "xi-api-key": api_key},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise NarrationError(f"ElevenLabs narration failed for {beat.id}: HTTP {exc.code}: {detail[-1200:]}")
        except urllib.error.URLError as exc:
            raise NarrationError(f"ElevenLabs narration failed for {beat.id}: {exc}")
        encoded = payload.get("audio_base64")
        if not encoded:
            raise NarrationError(f"ElevenLabs returned no audio for {beat.id}")
        source = directory / f"{index:02d}-{beat.id}.mp3"
        wav = directory / f"{index:02d}-{beat.id}.wav"
        source.write_bytes(base64.b64decode(encoded))
        _convert_to_wav(source, wav)
        segments.append((beat, wav))
        alignment = payload.get("normalized_alignment") or payload.get("alignment") or {}
        words = _alignment_word_timings(beat.narration, beat.id, 0.0, alignment)
        if words:
            alignments[beat.id] = words
    return segments, alignments


def _chatterbox_segments(
    beats: Sequence[VideoBeat],
    directory: Path,
    voice_reference: Optional[Path],
    rate_wpm: int,
) -> Tuple[Sequence[Tuple[VideoBeat, Path]], str]:
    try:
        import torch
        import torchaudio
        from chatterbox.tts import ChatterboxTTS
    except ImportError as exc:
        raise NarrationError(
            "the chatterbox provider requires a Python 3.11 environment with `chatterbox-tts` installed"
        ) from exc
    if voice_reference is not None and not voice_reference.is_file():
        raise NarrationError(f"Chatterbox voice reference does not exist: {voice_reference}")
    if torch.cuda.is_available():
        device = "cuda"
    elif bool(getattr(torch.backends, "mps", None)) and torch.backends.mps.is_available():
        device = "mps"
    else:
        device = "cpu"
    try:
        model = ChatterboxTTS.from_pretrained(device=device)
    except Exception as exc:
        raise NarrationError(f"Chatterbox model loading failed on {device}: {exc}") from exc
    segments: List[Tuple[VideoBeat, Path]] = []
    for index, beat in enumerate(beats, start=1):
        native = directory / f"{index:02d}-{beat.id}-chatterbox-native.wav"
        wav = directory / f"{index:02d}-{beat.id}.wav"
        generate_args = {"audio_prompt_path": str(voice_reference)} if voice_reference else {}
        try:
            waveform = model.generate(beat.narration, **generate_args)
            if getattr(waveform, "ndim", 0) == 1:
                waveform = waveform.unsqueeze(0)
            torchaudio.save(str(native), waveform.detach().cpu(), int(model.sr))
        except Exception as exc:
            raise NarrationError(f"Chatterbox narration failed for {beat.id}: {exc}") from exc
        _convert_to_wav(native, wav)
        _validate_spoken_wav(wav, beat.narration, rate_wpm)
        segments.append((beat, wav))
    return segments, device


def _qwen3_python(requested: Optional[Path]) -> Path:
    configured = requested or (
        Path(os.environ["CONTENTMAXXER_QWEN3_PYTHON"])
        if os.environ.get("CONTENTMAXXER_QWEN3_PYTHON")
        else DEFAULT_QWEN3_PYTHON
    )
    if not configured.is_file():
        raise NarrationError(
            "the qwen3 provider needs a Python 3.10+ MLX environment; expected "
            f"{configured}. Create it with `python3.12 -m venv .venv-tts` and install `mlx-audio`."
        )
    return configured


def qwen3_available(python_path: Optional[Path] = None) -> bool:
    try:
        executable = _qwen3_python(python_path)
    except NarrationError:
        return False
    completed = subprocess.run(
        [str(executable), "-c", "import mlx_audio"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    return completed.returncode == 0


def _qwen3_segments(
    beats: Sequence[VideoBeat],
    directory: Path,
    voice: str,
    instruction: str,
    python_path: Optional[Path],
    model_id: str,
    rate_wpm: int,
) -> Sequence[Tuple[VideoBeat, Path]]:
    executable = _qwen3_python(python_path)
    worker = PROJECT_ROOT / "scripts" / "qwen3_tts_worker.py"
    if not worker.is_file():
        raise NarrationError(f"Qwen3-TTS worker is missing: {worker}")
    request = directory / "qwen3-request.json"
    request.write_text(
        json.dumps(
            {
                "model": model_id or DEFAULT_QWEN3_MODEL,
                "speaker": voice or "Aiden",
                "language": "English",
                "instruction": instruction
                or "Warm, curious educational narrator. Clear pacing, natural emphasis, confident but conversational.",
                "temperature": 0.82,
                "target_wpm": rate_wpm,
                "segments": [{"id": beat.id, "text": beat.narration} for beat in beats],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    _run(
        [
            str(executable),
            str(worker),
            "--request",
            str(request),
            "--output-dir",
            str(directory),
        ],
        "local Qwen3-TTS narration",
    )
    segments: List[Tuple[VideoBeat, Path]] = []
    for index, beat in enumerate(beats, start=1):
        native = directory / f"{index:02d}-{beat.id}-qwen3-native.wav"
        if not native.is_file():
            raise NarrationError(f"Qwen3-TTS did not create the expected segment: {native}")
        wav = directory / f"{index:02d}-{beat.id}.wav"
        native_duration = _audio_duration(native)
        expected_duration = max(0.75, len(WORD_RE.findall(beat.narration)) / max(100, rate_wpm) * 60.0)
        if native_duration > expected_duration * 1.9:
            raise NarrationError(
                f"Qwen3-TTS segment {beat.id} is implausibly long "
                f"(duration={native_duration:.2f}s; expected_about={expected_duration:.2f}s)"
            )
        tempo = native_duration / expected_duration
        tempo_filter = f"atempo={min(1.75, tempo):.4f}" if tempo > 1.08 else None
        _convert_to_wav(native, wav, audio_filter=tempo_filter)
        _validate_spoken_wav(wav, beat.narration, rate_wpm)
        segments.append((beat, wav))
    return segments


def _file_segment(beats: Sequence[VideoBeat], directory: Path, source: Path) -> Sequence[Tuple[VideoBeat, Path]]:
    if not source.is_file():
        raise NarrationError(f"narration file does not exist: {source}")
    complete = directory / "imported-complete.wav"
    _convert_to_wav(source, complete)
    duration = _audio_duration(complete)
    weights = [max(1, len(WORD_RE.findall(beat.narration))) for beat in beats]
    total_weight = sum(weights)
    segments: List[Tuple[VideoBeat, Path]] = []
    start = 0.0
    for index, (beat, weight) in enumerate(zip(beats, weights), start=1):
        end = duration if index == len(beats) else start + duration * weight / total_weight
        segment = directory / f"{index:02d}-{beat.id}.wav"
        _run(
            [
                get_ffmpeg_exe(),
                "-y",
                "-ss",
                f"{start:.6f}",
                "-to",
                f"{end:.6f}",
                "-i",
                str(complete),
                "-ac",
                "1",
                "-ar",
                str(DEFAULT_SAMPLE_RATE),
                "-c:a",
                "pcm_s16le",
                str(segment),
            ],
            f"narration split for {beat.id}",
        )
        segments.append((beat, segment))
        start = end
    return segments


def resolve_provider(requested: str) -> str:
    if requested != "auto":
        return requested
    if os.environ.get("ELEVENLABS_API_KEY", "").strip():
        return "elevenlabs"
    if qwen3_available():
        return "qwen3"
    if importlib.util.find_spec("chatterbox") is not None:
        return "chatterbox"
    if shutil.which("say"):
        return "say"
    return "none"


def synthesize_narration(
    plan: ContentPlan,
    job_dir: Path,
    provider: str = "auto",
    voice: str = "",
    rate_wpm: int = DEFAULT_RATE_WPM,
    narration_file: Optional[Path] = None,
    voice_reference: Optional[Path] = None,
    voice_instruction: str = "",
    qwen3_python: Optional[Path] = None,
    qwen3_model: str = DEFAULT_QWEN3_MODEL,
) -> Optional[NarrationTrack]:
    selected = resolve_provider(provider)
    if selected == "none":
        return None
    if selected not in {"say", "elevenlabs", "qwen3", "chatterbox", "file"}:
        raise NarrationError(f"unknown narration provider: {selected}")
    work = job_dir / "video" / "narration" / "segments"
    work.mkdir(parents=True, exist_ok=True)
    alignments: Dict[str, List[WordTiming]] = {}
    if selected == "say":
        display_voice = voice or "system-default"
        segments = _say_segments(plan.beats, work, voice, rate_wpm)
        alignment_method = "measured_audio_proportional_words"
    elif selected == "elevenlabs":
        display_voice = voice
        segments, alignments = _elevenlabs_segments(plan.beats, work, voice)
        alignment_method = "provider_character_alignment"
    elif selected == "chatterbox":
        segments, device = _chatterbox_segments(plan.beats, work, voice_reference, rate_wpm)
        display_voice = voice_reference.name if voice_reference else f"built-in ({device})"
        alignment_method = "measured_audio_proportional_words"
    elif selected == "qwen3":
        segments = _qwen3_segments(
            plan.beats,
            work,
            voice,
            voice_instruction,
            qwen3_python,
            qwen3_model,
            rate_wpm,
        )
        display_voice = f"{voice or 'Aiden'} · {qwen3_model}"
        alignment_method = "measured_audio_proportional_words"
    else:
        if narration_file is None:
            raise NarrationError("--narration-file is required for the file narration provider")
        display_voice = narration_file.name
        segments = _file_segment(plan.beats, work, narration_file)
        alignment_method = "measured_audio_proportional_script"
    output = job_dir / "video" / "narration" / "voiceover.wav"
    pause = 0.0 if selected == "file" else BEAT_PAUSE_SECONDS
    cues, duration, sample_rate = _concat_wavs(segments, output, pause_seconds=pause, aligned_words=alignments)
    return NarrationTrack(
        provider=selected,
        voice=display_voice,
        audio_path=portable(output, job_dir),
        duration_seconds=round(duration, 4),
        sample_rate=sample_rate,
        alignment_method=alignment_method,
        cues=cues,
    )


def retime_plan(plan: ContentPlan, track: Optional[NarrationTrack]) -> ContentPlan:
    if track is None:
        return plan
    cue_by_id = {cue.beat_id: cue for cue in track.cues}
    beats = []
    for beat in plan.beats:
        cue = cue_by_id.get(beat.id)
        duration = beat.duration_seconds if cue is None else max(0.1, cue.end_seconds - cue.start_seconds)
        beats.append(replace(beat, duration_seconds=round(duration, 4)))
    return replace(plan, beats=beats)


def write_narration_track(job_dir: Path, track: NarrationTrack) -> Path:
    path = job_dir / "video" / "narration" / "timings.json"
    write_json(path, track)
    return path


def _timestamp(seconds: float) -> str:
    millis = int(round(seconds * 1000))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _caption_chunks(words: Iterable[WordTiming], max_words: int = 4, max_seconds: float = 1.9) -> List[List[WordTiming]]:
    chunks: List[List[WordTiming]] = []
    current: List[WordTiming] = []
    for word in words:
        current.append(word)
        duration = current[-1].end_seconds - current[0].start_seconds
        terminal = bool(re.search(r"[.!?]$", word.text))
        if len(current) >= max_words or duration >= max_seconds or terminal:
            chunks.append(current)
            current = []
    if current:
        chunks.append(current)
    return chunks


def write_aligned_srt(track: NarrationTrack, path: Path) -> Path:
    words = [word for cue in track.cues for word in cue.words]
    blocks = []
    for index, chunk in enumerate(_caption_chunks(words), start=1):
        text = " ".join(word.text for word in chunk)
        blocks.append(
            f"{index}\n{_timestamp(chunk[0].start_seconds)} --> {_timestamp(chunk[-1].end_seconds)}\n{text}\n"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(blocks), encoding="utf-8")
    return path


def _media_streams(path: Path) -> Dict[str, object]:
    completed = subprocess.run([get_ffmpeg_exe(), "-i", str(path)], capture_output=True, text=True)
    detail = completed.stderr or completed.stdout
    duration_match = re.search(r"Duration:\s+(\d+):(\d+):(\d+(?:\.\d+)?)", detail)
    duration = 0.0
    if duration_match:
        duration = int(duration_match.group(1)) * 3600 + int(duration_match.group(2)) * 60 + float(duration_match.group(3))
    return {
        "has_audio": bool(re.search(r"Stream #.*Audio:", detail)),
        "has_video": bool(re.search(r"Stream #.*Video:", detail)),
        "duration_seconds": round(duration, 4),
    }


def _audio_quality(path: Path, duration_seconds: float) -> Dict[str, object]:
    loudness = subprocess.run(
        [
            get_ffmpeg_exe(),
            "-i",
            str(path),
            "-af",
            "loudnorm=I=-16:LRA=7:TP=-1.5:print_format=json",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
    )
    detail = loudness.stderr or loudness.stdout
    measurements: Dict[str, object] = {}
    blocks = re.findall(r"\{\s*\"input_i\".*?\}", detail, re.S)
    if blocks:
        try:
            payload = json.loads(blocks[-1])
            measurements.update(
                {
                    "integrated_lufs": round(float(payload["input_i"]), 2),
                    "true_peak_dbfs": round(float(payload["input_tp"]), 2),
                    "loudness_range_lu": round(float(payload["input_lra"]), 2),
                }
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            pass
    silence = subprocess.run(
        [
            get_ffmpeg_exe(),
            "-i",
            str(path),
            "-af",
            "silencedetect=noise=-45dB:d=0.8",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
    )
    silence_detail = silence.stderr or silence.stdout
    long_silence = sum(float(value) for value in re.findall(r"silence_duration:\s*([\d.]+)", silence_detail))
    measurements["long_silence_seconds"] = round(long_silence, 3)
    measurements["long_silence_ratio"] = round(long_silence / max(0.1, duration_seconds), 4)
    return measurements


def mux_narration(job_dir: Path, video_path: Path, track: NarrationTrack) -> Dict[str, object]:
    audio_path = job_dir / track.audio_path
    temporary = video_path.with_name(video_path.stem + ".muxed.mp4")
    _run(
        [
            get_ffmpeg_exe(),
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(audio_path),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-af",
            "loudnorm=I=-16:LRA=7:TP=-1.5",
            "-shortest",
            "-movflags",
            "+faststart",
            str(temporary),
        ],
        "voiceover mux",
    )
    temporary.replace(video_path)
    streams = _media_streams(video_path)
    quality = _audio_quality(video_path, float(streams["duration_seconds"]))
    streams.update(
        {
            "provider": track.provider,
            "voice": track.voice,
            "path": track.audio_path,
            "timings": "video/narration/timings.json",
            "alignment_method": track.alignment_method,
            "sample_rate": track.sample_rate,
            "target_lufs": -16,
            "muxed": True,
            "sync_delta_seconds": round(abs(float(streams["duration_seconds"]) - track.duration_seconds), 4),
            **quality,
        }
    )
    return streams
