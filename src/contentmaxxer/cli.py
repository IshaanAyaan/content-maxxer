"""Command-line interface for source-grounded content production."""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Optional

from . import __version__
from .alignment import DEFAULT_WORD_ALIGNER_MODEL
from .manim_scene import ANIMATION_STYLES, manim_available
from .pipeline import (
    GroundingBlocked,
    QAFailure,
    build_five_post_set,
    build_gpt56_set,
    job_path,
    research_job,
    run_director,
    run_slides,
)
from .planning import HOOK_STYLES, PlanningError
from .raster import TARGET_PROFILES
from .sources import SourceError


def _shared_sources(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--source-url", action="append", default=[], help="repeatable URL to snapshot and cite")
    parser.add_argument("--source-file", action="append", default=[], type=Path, help="repeatable local note/source file")
    parser.add_argument("--offline", action="store_true", help="use only an existing per-job source cache")


def _shared_job(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("topic", help="editorial topic")
    parser.add_argument("--job", help="job directory name; defaults to a slug of the topic")
    parser.add_argument("--output-dir", type=Path, default=Path("jobs"), help="root output directory")
    _shared_sources(parser)


PRODUCE_CONFIG_KEYS = {
    "topic",
    "job",
    "output_dir",
    "source_urls",
    "source_files",
    "offline",
    "hook_style",
    "renderer",
    "animation_style",
    "allow_ungrounded",
    "voice_provider",
    "voice",
    "voice_rate",
    "voice_pronunciations",
    "voice_instruction",
    "word_aligner",
    "word_aligner_model",
    "burn_captions",
}

REVIEW_CHECKLIST = """# Review checklist: {job}

Machine QA passed, but QA is not taste. Before posting:

1. Watch `video/reel.mp4` (and `video/reel-captioned.mp4` if burned) start to finish with sound.
2. Listen for pronunciation problems; independent ASR spelling lives in `qa/video.json` and
   `video/narration/`. If a word is wrong, run a voice-only A/B (`contentmaxxer voice-lab`)
   with `--voice-pronunciation WORD=IPA` before any full rerender.
3. Check the first two seconds: is the hook alone, concrete, and readable?
4. Open `video/contact-sheet.png` and `video/motion-contact-sheet.png`: one evolving world,
   no dead space, no stray labels, every motion tied to narration.
5. Confirm claims against `citations.md`; keep factual framing source-bound.
6. If accepted: keep reel, narration master, timings, QA, contact sheets, spec, and sources;
   Trash `video/manim_media/` and `video/narration/segments/` to reclaim space.
"""


def _load_produce_config(path: Path, output_dir_override: Optional[Path]) -> dict:
    if not path.is_file():
        raise ValueError(f"produce config does not exist: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"produce config is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("produce config must be a JSON object")
    unknown = sorted(set(payload) - PRODUCE_CONFIG_KEYS)
    if unknown:
        raise ValueError(
            "unknown produce config keys: " + ", ".join(unknown)
            + "; allowed keys: " + ", ".join(sorted(PRODUCE_CONFIG_KEYS))
        )
    topic = str(payload.get("topic", "")).strip()
    if not topic:
        raise ValueError("produce config needs a non-empty topic")
    config = {
        "topic": topic,
        "job": payload.get("job"),
        "output_dir": Path(payload.get("output_dir", "build")),
        "source_urls": [str(item) for item in payload.get("source_urls", [])],
        "source_files": [Path(item) for item in payload.get("source_files", [])],
        "offline": bool(payload.get("offline", False)),
        "hook_style": payload.get("hook_style", "direct"),
        "renderer": payload.get("renderer", "manim"),
        "animation_style": payload.get("animation_style", "director_cut"),
        "allow_ungrounded": bool(payload.get("allow_ungrounded", False)),
        "voice_provider": payload.get("voice_provider", "deepgram"),
        "voice": payload.get("voice", ""),
        "voice_rate": int(payload.get("voice_rate", 170)),
        "voice_pronunciations": [str(item) for item in payload.get("voice_pronunciations", [])],
        "voice_instruction": payload.get("voice_instruction", ""),
        "word_aligner": payload.get("word_aligner", "auto"),
        "burn_captions": bool(payload.get("burn_captions", False)),
    }
    if "word_aligner_model" in payload:
        config["word_aligner_model"] = str(payload["word_aligner_model"])
    if output_dir_override is not None:
        config["output_dir"] = output_dir_override
    return config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="contentmaxxer", description="Source-grounded, Manim-first social content production")
    parser.add_argument("--version", action="version", version=f"contentmaxxer {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    research = subparsers.add_parser("research", help="snapshot sources and build a deterministic claim map")
    _shared_job(research)

    director = subparsers.add_parser("director", help="create a cited 9:16 reel; Manim is the polished default")
    _shared_job(director)
    director.add_argument("--hook-style", choices=HOOK_STYLES, default="direct")
    director.add_argument("--renderer", choices=("auto", "manim", "raster"), default="auto")
    director.add_argument(
        "--animation-style",
        choices=ANIMATION_STYLES,
        default="hand_drawn",
        help="visual language for the Manim reel; hand_drawn preserves the existing renderer",
    )
    director.add_argument("--allow-ungrounded", action="store_true", help="render a visibly marked speculative placeholder")
    director.add_argument(
        "--voice-provider",
        choices=("auto", "none", "say", "elevenlabs", "deepgram", "qwen3", "chatterbox", "file"),
        default="auto",
        help=(
            "narration backend; Deepgram is explicit opt-in, while auto preserves the existing "
            "ElevenLabs, local Qwen3/MLX, Chatterbox, then macOS say order"
        ),
    )
    director.add_argument(
        "--voice",
        default="",
        help="provider voice/model; Deepgram defaults to aura-2-thalia-en and Qwen3 defaults to Aiden",
    )
    director.add_argument(
        "--voice-rate",
        type=int,
        default=170,
        help="target WPM; Deepgram maps 170 WPM to Aura speed 1.0 and clamps to its 0.7-1.5 range",
    )
    director.add_argument(
        "--voice-pronunciation",
        action="append",
        default=[],
        metavar="WORD=IPA",
        help="repeatable Deepgram Aura-2 pronunciation override, such as softmax=ˈsɔftmæks",
    )
    director.add_argument(
        "--voice-instruction",
        default="",
        help="delivery instruction for Qwen3 CustomVoice, such as warm, curious, and conversational",
    )
    director.add_argument("--qwen3-python", type=Path, help="Python executable in the external MLX-Audio environment")
    director.add_argument(
        "--qwen3-model",
        default="mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-4bit",
        help="local MLX Qwen3-TTS model id",
    )
    director.add_argument("--voice-reference", type=Path, help="optional clean 5–10 second voice prompt for Chatterbox")
    director.add_argument("--narration-file", type=Path, help="existing audio to import when --voice-provider=file")
    director.add_argument(
        "--narration-timings",
        type=Path,
        help="optional timings.json to import with --voice-provider=file for exact beat and caption sync",
    )
    director.add_argument(
        "--word-aligner",
        choices=("auto", "none", "mlx-whisper", "deepgram"),
        default="auto",
        help=(
            "word timing refinement; auto uses a locally cached MLX Whisper model for newly synthesized "
            "proportional timings, while imported timing maps are preserved unless mlx-whisper or "
            "deepgram is explicit; deepgram uses hosted Nova speech-to-text word timestamps"
        ),
    )
    director.add_argument(
        "--burn-captions",
        action="store_true",
        help=(
            "also write video/reel-captioned.mp4 with word-synced caption cards burned into the "
            "lower safe zone; the clean reel.mp4 master is kept unchanged"
        ),
    )
    director.add_argument(
        "--word-aligner-python",
        type=Path,
        help="Python executable with MLX-Audio STT; defaults to .venv-tts/bin/python",
    )
    director.add_argument(
        "--word-aligner-model",
        default=DEFAULT_WORD_ALIGNER_MODEL,
        help="MLX Whisper model id or local path used for cross-attention word timestamps",
    )

    voice_lab = subparsers.add_parser(
        "voice-lab",
        help="bounded audio-only Deepgram voice A/B; pick narration before any full render",
    )
    voice_lab.add_argument("text", help="one representative script sentence to synthesize")
    voice_lab.add_argument(
        "--voice",
        action="append",
        default=[],
        help="repeatable Deepgram Aura voice id, for example aura-2-thalia-en",
    )
    voice_lab.add_argument("--output-dir", type=Path, default=Path("build/voice-lab"))
    voice_lab.add_argument("--voice-rate", type=int, default=170, help="target words per minute")
    voice_lab.add_argument(
        "--voice-pronunciation",
        action="append",
        default=[],
        help="repeatable WORD=IPA pronunciation override",
    )
    voice_lab.add_argument(
        "--no-asr-check",
        action="store_true",
        help="skip the independent Deepgram transcript for each sample",
    )

    produce = subparsers.add_parser(
        "produce",
        help="one-command reel production from a JSON job config (research -> narration -> render -> QA)",
    )
    produce.add_argument("config", type=Path, help="JSON config with topic, sources, voice, and render options")
    produce.add_argument(
        "--output-dir",
        type=Path,
        help="override the output root from the config (default build)",
    )

    slides = subparsers.add_parser("slides", help="create exact-count, ratio-adapted cited carousels")
    _shared_job(slides)
    slides.add_argument("--hook-style", choices=HOOK_STYLES, default="direct")
    slides.add_argument("--count", type=int, default=8, help="exact number of slides per target")
    slides.add_argument(
        "--target",
        action="append",
        choices=("all",) + tuple(TARGET_PROFILES),
        help="repeat to export multiple adapted targets; defaults to 9:16 and 4:5",
    )
    slides.add_argument("--allow-ungrounded", action="store_true", help="render a visibly marked speculative placeholder")
    slides.add_argument(
        "--style",
        choices=("editorial", "paper-meme"),
        default="editorial",
        help="cinematic editorial or code-native paper/meme art direction",
    )

    render = subparsers.add_parser("render", help="render a bespoke hand-authored Manim scene")
    render.add_argument("scene", type=Path)
    render.add_argument("--scene-class", default="ContentMaxxerScene")
    render.add_argument("--output-dir", type=Path, default=Path("media"))
    render.add_argument("--quality", choices=("ql", "qm", "qh", "qk"), default="qh")

    gpt = subparsers.add_parser("gpt56-set", help="build both locked July 9, 2026 GPT-5.6 jobs")
    gpt.add_argument("--output-dir", type=Path, default=Path("jobs"))
    gpt.add_argument("--renderer", choices=("auto", "manim", "raster"), default="auto")
    gpt.add_argument("--count", type=int, default=7, help="exact slides per carousel variant")

    five = subparsers.add_parser("five-post-set", help="build the five-post editorial vs paper/meme creative test")
    five.add_argument("--output-dir", type=Path, default=Path("jobs"))
    five.add_argument("--count", type=int, default=7, help="exact slides per carousel variant")
    return parser


def _manual_render(scene: Path, scene_class: str, output_dir: Path, quality: str) -> int:
    if not scene.is_file():
        raise RuntimeError(f"scene file does not exist: {scene}")
    if not manim_available():
        raise RuntimeError("Manim is unavailable; install it before using the manual render command.")
    output_dir.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, "-m", "manim", str(scene), scene_class, f"-{quality}", "--media_dir", str(output_dir)]
    return subprocess.run(command).returncode


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "research":
            directory = job_path(args.output_dir, args.job, args.topic)
            sources, claims = research_job(
                args.topic,
                directory,
                source_urls=args.source_url,
                source_files=args.source_file,
                offline=args.offline,
            )
            print(json.dumps({"job_dir": str(directory), "sources": len(sources), "claims": len(claims)}))
            return 0
        if args.command == "director":
            result = run_director(
                args.topic,
                args.output_dir,
                job=args.job,
                source_urls=args.source_url,
                source_files=args.source_file,
                offline=args.offline,
                hook_style=args.hook_style,
                renderer=args.renderer,
                animation_style=args.animation_style,
                allow_ungrounded=args.allow_ungrounded,
                voice_provider=args.voice_provider,
                voice=args.voice,
                voice_rate=args.voice_rate,
                voice_pronunciations=args.voice_pronunciation,
                voice_instruction=args.voice_instruction,
                qwen3_python=args.qwen3_python,
                qwen3_model=args.qwen3_model,
                voice_reference=args.voice_reference,
                narration_file=args.narration_file,
                narration_timings=args.narration_timings,
                word_aligner=args.word_aligner,
                word_aligner_python=args.word_aligner_python,
                word_aligner_model=args.word_aligner_model,
                burn_captions=args.burn_captions,
            )
            print(json.dumps(result.__dict__))
            return 0
        if args.command == "voice-lab":
            from .audio import run_voice_lab

            report = run_voice_lab(
                args.text,
                args.voice or ["aura-2-thalia-en"],
                args.output_dir,
                rate_wpm=args.voice_rate,
                pronunciations=args.voice_pronunciation,
                check_asr=not args.no_asr_check,
            )
            print(json.dumps(report, indent=2))
            print(
                f"\nListen to the samples under {args.output_dir} and compare each "
                "asr_transcript against the script before choosing a voice.",
                file=sys.stderr,
            )
            return 0
        if args.command == "produce":
            config = _load_produce_config(args.config, args.output_dir)
            result = run_director(
                config["topic"],
                config["output_dir"],
                job=config["job"],
                source_urls=config["source_urls"],
                source_files=config["source_files"],
                offline=config["offline"],
                hook_style=config["hook_style"],
                renderer=config["renderer"],
                animation_style=config["animation_style"],
                allow_ungrounded=config["allow_ungrounded"],
                voice_provider=config["voice_provider"],
                voice=config["voice"],
                voice_rate=config["voice_rate"],
                voice_pronunciations=config["voice_pronunciations"],
                voice_instruction=config["voice_instruction"],
                word_aligner=config["word_aligner"],
                word_aligner_model=config.get(
                    "word_aligner_model", DEFAULT_WORD_ALIGNER_MODEL
                ),
                burn_captions=config["burn_captions"],
            )
            job_dir = Path(result.job_dir)
            review = job_dir / "REVIEW.md"
            review.write_text(
                REVIEW_CHECKLIST.format(job=job_dir.name), encoding="utf-8"
            )
            print(json.dumps(result.__dict__))
            print(f"review checklist: {review}", file=sys.stderr)
            return 0
        if args.command == "slides":
            result = run_slides(
                args.topic,
                args.output_dir,
                job=args.job,
                source_urls=args.source_url,
                source_files=args.source_file,
                offline=args.offline,
                hook_style=args.hook_style,
                count=args.count,
                targets=args.target or ("9:16", "4:5"),
                allow_ungrounded=args.allow_ungrounded,
                visual_theme="paper_meme_v1" if args.style == "paper-meme" else "editorial_heat_v1",
            )
            print(json.dumps(result.__dict__))
            return 0
        if args.command == "render":
            return _manual_render(args.scene, args.scene_class, args.output_dir, args.quality)
        if args.command == "gpt56-set":
            results = build_gpt56_set(args.output_dir, renderer=args.renderer, count=args.count)
            print(json.dumps([result.__dict__ for result in results]))
            return 0
        if args.command == "five-post-set":
            results = build_five_post_set(args.output_dir, count=args.count)
            print(json.dumps([result.__dict__ for result in results]))
            return 0
    except GroundingBlocked as exc:
        print(f"blocked: {exc}", file=sys.stderr)
        return 2
    except (SourceError, PlanningError, QAFailure, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
