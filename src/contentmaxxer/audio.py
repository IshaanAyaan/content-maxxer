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

from .alignment import (
    DEFAULT_DEEPGRAM_ALIGNER_MODEL,
    DEFAULT_WORD_ALIGNER_MODEL,
    WordAlignmentError,
    align_track_with_deepgram,
    align_track_with_mlx_whisper,
    mlx_whisper_available,
)
from .io import portable, write_json
from .models import ContentPlan, NarrationCue, NarrationTrack, VideoBeat, WordTiming


DEFAULT_SAMPLE_RATE = 48_000
DEFAULT_RATE_WPM = 170
BEAT_PAUSE_SECONDS = 0.18
WORD_RE = re.compile(r"\S+")
SPOKEN_SCRIPT_TOKEN_RE = re.compile(
    r"[A-Za-z0-9]+(?:['’.-][A-Za-z0-9]+)*"
)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_QWEN3_PYTHON = PROJECT_ROOT / ".venv-tts" / "bin" / "python"
DEFAULT_QWEN3_MODEL = "mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-4bit"
DEFAULT_DEEPGRAM_MODEL = "aura-2-thalia-en"
DEEPGRAM_SPEAK_URL = "https://api.deepgram.com/v1/speak"


class NarrationError(RuntimeError):
    pass


def _spoken_script_tokens(text: str) -> List[str]:
    return [
        token.casefold()
        for token in SPOKEN_SCRIPT_TOKEN_RE.findall(text.replace("‑", "-"))
    ]


def _local_env_value(name: str) -> str:
    configured = os.environ.get(name, "").strip()
    if configured:
        return configured
    for path in (PROJECT_ROOT / ".env.local", PROJECT_ROOT / ".env"):
        if not path.is_file():
            continue
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:].lstrip()
            key, separator, value = line.partition("=")
            if not separator or key.strip() != name:
                continue
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            return value.strip()
    return ""


def deepgram_speed_for_rate(rate_wpm: int) -> float:
    if rate_wpm <= 0:
        raise NarrationError("--voice-rate must be greater than zero")
    return round(min(1.5, max(0.7, rate_wpm / float(DEFAULT_RATE_WPM))), 3)


def _deepgram_pronunciation_map(values: Sequence[str]) -> Dict[str, str]:
    pronunciations: Dict[str, str] = {}
    for value in values:
        word, separator, ipa = value.partition("=")
        word = word.strip()
        ipa = re.sub(r"\s+", "", ipa.strip())
        if not separator or not word or not ipa:
            raise NarrationError(
                "Deepgram pronunciation overrides must use WORD=IPA, "
                "for example softmax=ˈsɔftmæks"
            )
        pronunciations[word] = ipa
    return pronunciations


def _apply_deepgram_pronunciations(text: str, pronunciations: Dict[str, str]) -> str:
    transformed = text
    for word, ipa in sorted(pronunciations.items(), key=lambda item: len(item[0]), reverse=True):
        control = (
            r'\{"word": '
            + json.dumps(word, ensure_ascii=False)
            + r', "pronounce": '
            + json.dumps(ipa, ensure_ascii=False)
            + r'\}'
        )
        transformed = re.sub(
            rf"(?<!\w){re.escape(word)}(?!\w)",
            lambda _match: control,
            transformed,
        )
    return transformed


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


def _deepgram_segments(
    beats: Sequence[VideoBeat],
    directory: Path,
    voice: str,
    rate_wpm: int,
    pronunciation_values: Sequence[str],
) -> Tuple[Sequence[Tuple[VideoBeat, Path]], Dict[str, object]]:
    directory.mkdir(parents=True, exist_ok=True)
    api_key = _local_env_value("DEEPGRAM_API_KEY")
    if not api_key:
        raise NarrationError(
            "DEEPGRAM_API_KEY is required for the deepgram narration provider; "
            "set it in the environment or a git-ignored .env.local file"
        )
    model = voice.strip() or DEFAULT_DEEPGRAM_MODEL
    speed = deepgram_speed_for_rate(rate_wpm)
    pronunciations = _deepgram_pronunciation_map(pronunciation_values)
    query = urllib.parse.urlencode(
        {
            "model": model,
            "encoding": "linear16",
            "container": "wav",
            "sample_rate": str(DEFAULT_SAMPLE_RATE),
            "speed": f"{speed:.3f}",
        }
    )
    url = f"{DEEPGRAM_SPEAK_URL}?{query}"
    segments: List[Tuple[VideoBeat, Path]] = []
    requests: List[Dict[str, object]] = []
    total_characters = 0
    for index, beat in enumerate(beats, start=1):
        request_text = _apply_deepgram_pronunciations(beat.narration, pronunciations)
        request = urllib.request.Request(
            url,
            data=json.dumps({"text": request_text}, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Token {api_key}",
                "Content-Type": "application/json",
                "Accept": "audio/wav",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                audio_bytes = response.read()
                response_headers = response.headers
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise NarrationError(
                f"Deepgram narration failed for {beat.id}: HTTP {exc.code}: {detail[-1200:]}"
            ) from exc
        except urllib.error.URLError as exc:
            raise NarrationError(f"Deepgram narration failed for {beat.id}: {exc}") from exc
        if not audio_bytes:
            raise NarrationError(f"Deepgram returned no audio for {beat.id}")
        native = directory / f"{index:02d}-{beat.id}-deepgram-native.wav"
        wav = directory / f"{index:02d}-{beat.id}.wav"
        native.write_bytes(audio_bytes)
        _convert_to_wav(native, wav)
        _validate_spoken_wav(wav, beat.narration, rate_wpm)
        segments.append((beat, wav))

        header_character_count = response_headers.get("dg-char-count")
        try:
            character_count = int(header_character_count) if header_character_count else len(beat.narration)
        except ValueError:
            character_count = len(beat.narration)
        total_characters += character_count
        request_metadata: Dict[str, object] = {
            "beat_id": beat.id,
            "character_count": character_count,
            "duration_seconds": round(_audio_duration(wav), 4),
        }
        for header, key in (
            ("dg-request-id", "request_id"),
            ("dg-model-name", "response_model"),
            ("dg-model-uuid", "model_uuid"),
            ("dg-speed-used", "speed_used"),
            ("dg-pronunciations-applied", "pronunciations_applied"),
            ("dg-billed-duration", "billed_duration"),
        ):
            value = response_headers.get(header)
            if value:
                request_metadata[key] = value
        requests.append(request_metadata)
    return segments, {
        "endpoint": DEEPGRAM_SPEAK_URL,
        "model": model,
        "encoding": "linear16",
        "container": "wav",
        "sample_rate": DEFAULT_SAMPLE_RATE,
        "speed": speed,
        "pronunciations": [
            {"word": word, "ipa": ipa}
            for word, ipa in pronunciations.items()
        ],
        "character_count": total_characters,
        "request_count": len(requests),
        "requests": requests,
    }


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


def tts_sentence_chunks(text: str, max_words: int = 16) -> List[str]:
    if max_words < 4:
        raise NarrationError("TTS sentence chunks require max_words >= 4")
    compact = " ".join(text.split())
    if not compact:
        return []
    sentences = re.split(r"(?<=[.!?])\s+", compact)
    chunks: List[str] = []
    for sentence in sentences:
        clauses = re.split(r"(?<=[,;:])\s+", sentence)
        current: List[str] = []
        for clause in clauses:
            clause_words = clause.split()
            if len(clause_words) > max_words:
                if current:
                    chunks.append(" ".join(current))
                    current = []
                for start in range(0, len(clause_words), max_words):
                    chunks.append(" ".join(clause_words[start : start + max_words]))
                continue
            if current and len(current) + len(clause_words) > max_words:
                chunks.append(" ".join(current))
                current = []
            current.extend(clause_words)
        if current:
            chunks.append(" ".join(current))
    return chunks


def _qwen3_segments(
    beats: Sequence[VideoBeat],
    directory: Path,
    voice: str,
    instruction: str,
    python_path: Optional[Path],
    model_id: str,
    rate_wpm: int,
) -> Tuple[Sequence[Tuple[VideoBeat, Path]], Dict[str, object]]:
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
                "segments": [
                    {
                        "id": beat.id,
                        "text": beat.narration,
                        "chunks": tts_sentence_chunks(beat.narration),
                    }
                    for beat in beats
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    completed = _run(
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
    generation_payload: Dict[str, object] = {}
    try:
        generation_payload = json.loads(completed.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        generation_payload = {"metadata_parse_error": True}
    generation = []
    for item in generation_payload.get("outputs", []):
        if isinstance(item, dict):
            generation.append({key: value for key, value in item.items() if key != "path"})
    metadata = {
        "model": model_id or DEFAULT_QWEN3_MODEL,
        "speaker": voice or "Aiden",
        "sentence_chunking": True,
        "generation": generation,
    }
    return segments, metadata


def run_voice_lab(
    text: str,
    voices: Sequence[str],
    directory: Path,
    rate_wpm: int = DEFAULT_RATE_WPM,
    pronunciations: Sequence[str] = (),
    *,
    check_asr: bool = True,
) -> Dict[str, object]:
    """Synthesize one short sample per Deepgram Aura voice for an audio-only A/B.

    This is the bounded 'voice lab' step from the working rules: pick narration
    before spending on a full render. Each candidate gets a WAV plus an
    independent Deepgram transcript so pronunciation problems surface without a
    manual listen-first pass (still listen before publishing).
    """
    if not text.strip():
        raise NarrationError("voice lab needs a non-empty sample sentence")
    if not voices:
        raise NarrationError("voice lab needs at least one Deepgram voice")
    api_key = _local_env_value("DEEPGRAM_API_KEY")
    if not api_key:
        raise NarrationError(
            "DEEPGRAM_API_KEY is required for the voice lab; "
            "set it in the environment or a git-ignored .env.local file"
        )
    directory.mkdir(parents=True, exist_ok=True)
    beat = VideoBeat(
        id="voice_lab",
        purpose="voice_lab",
        headline="Voice lab",
        narration=text.strip(),
        on_screen_text="",
        claim_ids=[],
        source_label="voice-lab",
        primitive="none",
    )
    candidates: List[Dict[str, object]] = []
    for voice in voices:
        voice_dir = directory / voice
        segments, metadata = _deepgram_segments(
            [beat],
            voice_dir,
            voice,
            rate_wpm,
            pronunciations,
        )
        _beat, wav_path = segments[0]
        sample = voice_dir / "sample.wav"
        shutil.copy2(wav_path, sample)
        candidate: Dict[str, object] = {
            "voice": voice,
            "sample": str(sample),
            "duration_seconds": round(_audio_duration(sample), 3),
            "deepgram": metadata["requests"][0],
        }
        if check_asr:
            from .alignment import (
                DEFAULT_DEEPGRAM_ALIGNER_MODEL as _NOVA,
                WordAlignmentError as _AlignError,
                deepgram_words_to_whisper_payload,
                transcribe_with_deepgram,
            )

            try:
                payload = transcribe_with_deepgram(sample, api_key, _NOVA)
                words = deepgram_words_to_whisper_payload(payload)["segments"][0]["words"]
                candidate["asr_transcript"] = " ".join(str(w["word"]) for w in words)
            except _AlignError as exc:
                candidate["asr_transcript_error"] = str(exc)
        candidates.append(candidate)
    report = {
        "text": text.strip(),
        "rate_wpm": rate_wpm,
        "pronunciations": list(pronunciations),
        "candidates": candidates,
    }
    write_json(directory / "report.json", report)
    return report


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
    narration_timings: Optional[Path] = None,
    voice_reference: Optional[Path] = None,
    voice_instruction: str = "",
    qwen3_python: Optional[Path] = None,
    qwen3_model: str = DEFAULT_QWEN3_MODEL,
    voice_pronunciations: Sequence[str] = (),
    word_aligner: str = "none",
    word_aligner_python: Optional[Path] = None,
    word_aligner_model: str = DEFAULT_WORD_ALIGNER_MODEL,
) -> Optional[NarrationTrack]:
    selected = resolve_provider(provider)
    if selected == "none":
        return None
    if selected not in {"say", "elevenlabs", "deepgram", "qwen3", "chatterbox", "file"}:
        raise NarrationError(f"unknown narration provider: {selected}")
    work = job_dir / "video" / "narration" / "segments"
    work.mkdir(parents=True, exist_ok=True)
    if selected == "file" and narration_timings is not None:
        if narration_file is None:
            raise NarrationError("--narration-file is required when importing narration timings")
        if not narration_file.is_file():
            raise NarrationError(f"narration file does not exist: {narration_file}")
        if not narration_timings.is_file():
            raise NarrationError(f"narration timings do not exist: {narration_timings}")
        payload = json.loads(narration_timings.read_text(encoding="utf-8"))
        cues = [
            NarrationCue(
                beat_id=cue["beat_id"],
                text=cue["text"],
                start_seconds=float(cue["start_seconds"]),
                end_seconds=float(cue["end_seconds"]),
                words=[
                    WordTiming(
                        text=word["text"],
                        start_seconds=float(word["start_seconds"]),
                        end_seconds=float(word["end_seconds"]),
                        beat_id=word["beat_id"],
                    )
                    for word in cue.get("words", [])
                ],
            )
            for cue in payload.get("cues", [])
        ]
        expected_ids = [beat.id for beat in plan.beats]
        if [cue.beat_id for cue in cues] != expected_ids:
            raise NarrationError("imported narration timings do not match the current beat ids")
        rebound_cues: List[NarrationCue] = []
        punctuation_normalized_count = 0
        for cue, beat in zip(cues, plan.beats):
            imported_text = " ".join(cue.text.split())
            current_text = " ".join(beat.narration.split())
            exact_match = imported_text == current_text
            punctuation_match = (
                _spoken_script_tokens(imported_text)
                == _spoken_script_tokens(current_text)
                and len(cue.words) == len(WORD_RE.findall(current_text))
            )
            if not exact_match and not punctuation_match:
                raise NarrationError(
                    "imported narration timings do not match the current script"
                )
            current_words = WORD_RE.findall(current_text)
            rebound_words = [
                replace(word, text=current_word)
                for word, current_word in zip(cue.words, current_words)
            ]
            rebound_cues.append(
                replace(
                    cue,
                    text=current_text,
                    words=rebound_words,
                )
            )
            if not exact_match:
                punctuation_normalized_count += 1
        cues = rebound_cues
        output = job_dir / "video" / "narration" / "voiceover.wav"
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(narration_file, output)
        measured_duration = _audio_duration(output)
        timing_duration = float(payload["duration_seconds"])
        if abs(measured_duration - timing_duration) > 0.05:
            raise NarrationError("imported narration audio and timings have different durations")
        with wave.open(str(output), "rb") as audio:
            sample_rate = audio.getframerate()
        imported_metadata = dict(payload.get("metadata", {}))
        imported_metadata["imported_script_match"] = {
            "method": "exact_or_spoken_token_equivalent_v1",
            "exact_beat_count": len(cues) - punctuation_normalized_count,
            "punctuation_normalized_beat_count": (
                punctuation_normalized_count
            ),
            "lexical_change_allowed": False,
        }
        _copy_imported_alignment_artifacts(
            imported_metadata,
            narration_timings,
            job_dir,
        )
        imported_voice = str(
            payload.get("voice", narration_file.name)
        )
        if not imported_voice.endswith(" (master import)"):
            imported_voice += " (master import)"
        imported_track = NarrationTrack(
            provider=str(payload.get("provider", "file")),
            voice=imported_voice,
            audio_path=portable(output, job_dir),
            duration_seconds=round(measured_duration, 4),
            sample_rate=sample_rate,
            alignment_method=str(payload.get("alignment_method", "imported_master_timings")),
            cues=cues,
            metadata=imported_metadata,
        )
        return _maybe_align_narration(
            imported_track,
            job_dir,
            requested=word_aligner,
            python_path=word_aligner_python or qwen3_python,
            model=word_aligner_model,
            imported_timings=True,
        )
    alignments: Dict[str, List[WordTiming]] = {}
    provider_metadata: Dict[str, object] = {}
    if selected == "say":
        display_voice = voice or "system-default"
        segments = _say_segments(plan.beats, work, voice, rate_wpm)
        alignment_method = "measured_audio_proportional_words"
    elif selected == "elevenlabs":
        display_voice = voice
        segments, alignments = _elevenlabs_segments(plan.beats, work, voice)
        alignment_method = "provider_character_alignment"
    elif selected == "deepgram":
        segments, provider_metadata = _deepgram_segments(
            plan.beats,
            work,
            voice,
            rate_wpm,
            voice_pronunciations,
        )
        display_voice = str(provider_metadata["model"])
        alignment_method = "measured_audio_proportional_words"
    elif selected == "chatterbox":
        segments, device = _chatterbox_segments(plan.beats, work, voice_reference, rate_wpm)
        display_voice = voice_reference.name if voice_reference else f"built-in ({device})"
        alignment_method = "measured_audio_proportional_words"
    elif selected == "qwen3":
        segments, provider_metadata = _qwen3_segments(
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
    track = NarrationTrack(
        provider=selected,
        voice=display_voice,
        audio_path=portable(output, job_dir),
        duration_seconds=round(duration, 4),
        sample_rate=sample_rate,
        alignment_method=alignment_method,
        cues=cues,
        metadata=provider_metadata,
    )
    return _maybe_align_narration(
        track,
        job_dir,
        requested=word_aligner,
        python_path=word_aligner_python or qwen3_python,
        model=word_aligner_model,
        imported_timings=False,
    )


def _copy_imported_alignment_artifacts(
    metadata: Dict[str, object],
    narration_timings: Path,
    job_dir: Path,
) -> None:
    word_alignment = metadata.get("word_alignment")
    if not isinstance(word_alignment, dict):
        return
    raw_value = word_alignment.get("raw_transcript")
    if not raw_value:
        return
    relative = Path(str(raw_value))
    if relative.is_absolute() or ".." in relative.parts:
        raise NarrationError("imported word-alignment transcript path must be portable")
    source: Optional[Path] = None
    for base in (narration_timings.parent, *narration_timings.parents):
        candidate = base / relative
        if candidate.is_file():
            source = candidate
            break
    if source is None:
        raise NarrationError(
            f"imported word-alignment transcript is missing: {relative}"
        )
    destination = job_dir / relative
    try:
        destination.resolve().relative_to(job_dir.resolve())
    except ValueError as exc:
        raise NarrationError("imported word-alignment transcript escapes the job directory") from exc
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _maybe_align_narration(
    track: NarrationTrack,
    job_dir: Path,
    requested: str,
    python_path: Optional[Path],
    model: str,
    *,
    imported_timings: bool,
) -> NarrationTrack:
    if requested not in {"auto", "none", "mlx-whisper", "deepgram"}:
        raise NarrationError(f"unknown word aligner: {requested}")
    if requested == "none":
        return track
    if requested == "deepgram":
        api_key = _local_env_value("DEEPGRAM_API_KEY")
        if not api_key:
            raise NarrationError(
                "DEEPGRAM_API_KEY is required for the deepgram word aligner; "
                "set it in the environment or a git-ignored .env.local file"
            )
        aligner_model = (
            DEFAULT_DEEPGRAM_ALIGNER_MODEL if model == DEFAULT_WORD_ALIGNER_MODEL else model
        )
        try:
            return align_track_with_deepgram(track, job_dir, api_key, aligner_model)
        except WordAlignmentError as exc:
            raise NarrationError(str(exc)) from exc
    if requested == "auto" and (
        imported_timings or not track.alignment_method.startswith("measured_audio_proportional")
    ):
        return track
    executable = python_path or DEFAULT_QWEN3_PYTHON
    available = mlx_whisper_available(
        executable,
        model,
        local_only=requested == "auto",
    )
    if not available:
        if requested == "mlx-whisper":
            raise NarrationError(
                "the mlx-whisper word aligner needs an MLX-Audio environment and model; "
                f"checked {executable} with {model}"
            )
        metadata = dict(track.metadata)
        metadata["word_alignment"] = {
            "status": "unavailable",
            "engine": "mlx-audio Whisper cross-attention DTW",
            "model": model,
            "fallback": track.alignment_method,
        }
        return replace(track, metadata=metadata)
    try:
        return align_track_with_mlx_whisper(track, job_dir, executable, model)
    except WordAlignmentError as exc:
        if requested == "mlx-whisper":
            raise NarrationError(str(exc)) from exc
        metadata = dict(track.metadata)
        metadata["word_alignment"] = {
            "status": "rejected",
            "engine": "mlx-audio Whisper cross-attention DTW",
            "model": model,
            "reason": str(exc),
            "fallback": track.alignment_method,
        }
        return replace(track, metadata=metadata)


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


def _ass_timestamp(seconds: float) -> str:
    centis = int(round(seconds * 100))
    hours, centis = divmod(centis, 360_000)
    minutes, centis = divmod(centis, 6_000)
    secs, centis = divmod(centis, 100)
    return f"{hours:d}:{minutes:02d}:{secs:02d}.{centis:02d}"


def write_caption_ass(
    track: NarrationTrack,
    path: Path,
    *,
    width: int = 1080,
    height: int = 1920,
) -> Path:
    """Write word-synced caption cards as a styled ASS file for burn-in.

    One short phrase card at a time (<=5 words, <=2.6s) in the lower safe zone:
    no paragraph captions and no boxes. Cards are slightly longer than the SRT
    chunks so the burned cadence stays under roughly 32 transitions/minute with
    a median dwell above 1.7 seconds at typical narration rates.
    """
    words = [word for cue in track.cues for word in cue.words]
    margin_v = int(height * 0.16)
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Caption,Helvetica,72,&H00FFFFFF,&H00FFFFFF,&H00101010,&H64000000,"
        f"-1,0,0,0,100,100,0,0,1,5,0,2,90,90,{margin_v},1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for chunk in _caption_chunks(words, max_words=5, max_seconds=2.6):
        start = _ass_timestamp(chunk[0].start_seconds)
        end = _ass_timestamp(chunk[-1].end_seconds)
        text = " ".join(word.text for word in chunk).replace("{", "(").replace("}", ")")
        lines.append(f"Dialogue: 0,{start},{end},Caption,,0,0,0,,{text}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def burn_captions_into_reel(
    job_dir: Path,
    video_path: Path,
    track: NarrationTrack,
    *,
    width: int = 1080,
    height: int = 1920,
) -> Dict[str, object]:
    """Burn word-synced caption cards into a copy of the muxed reel.

    Writes video/reel-captioned.mp4 next to the clean reel so the caption-free
    master stays available for platforms that prefer native captions.
    """
    ass_path = write_caption_ass(
        track,
        job_dir / "video" / "captions.ass",
        width=width,
        height=height,
    )
    output_path = video_path.with_name("reel-captioned.mp4")
    escaped = str(ass_path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    _run(
        [
            get_ffmpeg_exe(),
            "-y",
            "-i",
            str(video_path),
            "-vf",
            f"ass='{escaped}'",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "copy",
            str(output_path),
        ],
        "caption burn-in",
    )
    streams = _media_streams(output_path)
    if not streams["has_video"] or not streams["has_audio"]:
        raise NarrationError("caption burn-in lost a stream; refusing to accept the output")
    source_streams = _media_streams(video_path)
    if abs(float(streams["duration_seconds"]) - float(source_streams["duration_seconds"])) > 0.15:
        raise NarrationError(
            "caption burn-in changed the reel duration "
            f"({source_streams['duration_seconds']}s -> {streams['duration_seconds']}s)"
        )
    words = [word for cue in track.cues for word in cue.words]
    chunks = _caption_chunks(words, max_words=5, max_seconds=2.6)
    duration = float(streams["duration_seconds"]) or 1.0
    dwells = sorted(chunk[-1].end_seconds - chunk[0].start_seconds for chunk in chunks)
    return {
        "captioned_mp4": portable(output_path, job_dir),
        "caption_transitions_per_minute": round(len(chunks) * 60.0 / duration, 2),
        "median_caption_dwell_seconds": round(dwells[len(dwells) // 2], 3) if dwells else 0.0,
        "ass": portable(ass_path, job_dir),
        "caption_card_count": len(chunks),
        "duration_seconds": streams["duration_seconds"],
    }


def _media_streams(path: Path) -> Dict[str, object]:
    completed = subprocess.run([get_ffmpeg_exe(), "-i", str(path)], capture_output=True, text=True)
    detail = completed.stderr or completed.stdout
    duration_match = re.search(r"Duration:\s+(\d+):(\d+):(\d+(?:\.\d+)?)", detail)
    audio_match = re.search(r"Stream #.*Audio:.*?,\s*(\d+)\s*Hz,\s*([^,\n]+)", detail)
    duration = 0.0
    if duration_match:
        duration = int(duration_match.group(1)) * 3600 + int(duration_match.group(2)) * 60 + float(duration_match.group(3))
    return {
        "has_audio": bool(re.search(r"Stream #.*Audio:", detail)),
        "has_video": bool(re.search(r"Stream #.*Video:", detail)),
        "duration_seconds": round(duration, 4),
        "encoded_sample_rate": int(audio_match.group(1)) if audio_match else None,
        "encoded_channel_layout": audio_match.group(2).strip() if audio_match else None,
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
            "-ar",
            "48000",
            "-ac",
            "1",
            "-af",
            "loudnorm=I=-16:LRA=7:TP=-2.5,alimiter=limit=0.80:level=false",
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
            "provider_metadata": track.metadata,
            "target_lufs": -16,
            "target_true_peak_dbfs": -2.5,
            "muxed": True,
            "sync_delta_seconds": round(abs(float(streams["duration_seconds"]) - track.duration_seconds), 4),
            **quality,
        }
    )
    return streams
