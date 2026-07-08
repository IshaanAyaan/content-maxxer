from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from content_maxxer.backend import (
    evaluate_export,
    load_plan_from_job,
    make_plan,
    read_first_text,
    read_source,
    read_title,
    render_video,
    slugify,
    write_evaluation_report,
    write_plan_files,
)
from content_maxxer.director import build_director_plan, render_director_video, retime_plan, write_director_files


PLACEHOLDERS = {
    "{{TITLE}}": "Untitled Explainer",
    "{{SLUG}}": "untitled_explainer",
    "{{SOURCE_URL}}": "",
    "{{TOPIC}}": "the topic",
}


def find_repo_root() -> Path:
    candidates = [Path.cwd(), Path(__file__).resolve().parents[2]]
    for candidate in candidates:
        if (candidate / "content_jobs" / "_template").exists():
            return candidate
    raise SystemExit(
        "Could not find content_jobs/_template. Run this command from the repo root."
    )


def copy_text_template(source: Path, destination: Path, replacements: dict[str, str]) -> None:
    text = source.read_text(encoding="utf-8")
    for key, value in replacements.items():
        text = text.replace(key, value)
    destination.write_text(text, encoding="utf-8")


def command_new(args: argparse.Namespace) -> int:
    repo_root = find_repo_root()
    jobs_dir = repo_root / "content_jobs"
    template_dir = jobs_dir / "_template"
    job_dir = jobs_dir / args.slug

    if job_dir.exists() and not args.force:
        print(f"Job already exists: {job_dir}", file=sys.stderr)
        print("Use --force to overwrite template files.", file=sys.stderr)
        return 1

    replacements = {
        **PLACEHOLDERS,
        "{{TITLE}}": args.title,
        "{{SLUG}}": args.slug,
        "{{SOURCE_URL}}": args.source_url or "",
        "{{TOPIC}}": args.topic or args.title,
    }

    job_dir.mkdir(parents=True, exist_ok=True)
    for source in template_dir.rglob("*"):
        relative = source.relative_to(template_dir)
        destination = job_dir / relative
        if source.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.suffix in {".md", ".py", ".txt"}:
            copy_text_template(source, destination, replacements)
        else:
            shutil.copy2(source, destination)

    print(f"Created content job: {job_dir}")
    print(f"Next: edit {job_dir / 'prompt.md'} and {job_dir / 'storyboard.md'}")
    return 0


def command_render(args: argparse.Namespace) -> int:
    repo_root = find_repo_root()
    job_dir = repo_root / "content_jobs" / args.slug
    scene_file = job_dir / args.scene_file

    if not scene_file.exists():
        print(f"Scene file not found: {scene_file}", file=sys.stderr)
        return 1

    quality_flags = {
        "draft": "-ql",
        "medium": "-qm",
        "high": "-qh",
        "production": "-qp",
    }
    command = [
        "manim",
        quality_flags[args.quality],
        str(scene_file),
        args.scene,
        "--media_dir",
        str(job_dir / "media"),
    ]
    if args.open:
        command.insert(1, "-p")

    print("Running:", " ".join(command))
    return subprocess.run(command, cwd=repo_root, check=False).returncode


def command_make_video(args: argparse.Namespace) -> int:
    repo_root = find_repo_root()
    slug = args.slug or slugify(args.title)
    job_dir = repo_root / "content_jobs" / slug
    if job_dir.exists() and not args.force:
        print(f"Job already exists: {job_dir}", file=sys.stderr)
        print("Use --force to overwrite generated planning files.", file=sys.stderr)
        return 1
    plan = make_plan(
        slug=slug,
        title=args.title,
        idea=args.idea,
        source=args.source_url or args.pdf or "Concept prompt",
        video_format=args.format,
        duration=args.duration,
    )
    write_plan_files(job_dir, plan, args.idea)
    output = render_video(job_dir, plan, quality=args.quality, fps=args.fps)
    print(f"Generated video: {output}")
    return 0


def command_package(args: argparse.Namespace) -> int:
    repo_root = find_repo_root()
    job_dir = repo_root / "content_jobs" / args.slug
    if not job_dir.exists():
        print(f"Job not found: {job_dir}", file=sys.stderr)
        return 1
    plan = load_plan_from_job(job_dir, video_format=args.format, duration=args.duration)
    output = render_video(job_dir, plan, quality=args.quality, fps=args.fps)
    print(f"Packaged video: {output}")
    return 0


def command_director(args: argparse.Namespace) -> int:
    repo_root = find_repo_root()
    slug = args.slug or slugify(args.title)
    job_dir = repo_root / "content_jobs" / slug
    title = args.title or (read_title(job_dir) if job_dir.exists() else slug.replace("_", " ").title())
    idea = args.idea or read_first_text(job_dir / "brief.md") or read_first_text(job_dir / "research.md") or title
    source = args.source_url or args.pdf or (read_source(job_dir) if job_dir.exists() else "Concept prompt")
    if job_dir.exists() and (job_dir / "scene_graph.json").exists() and not args.force:
        print(f"Director files already exist: {job_dir}", file=sys.stderr)
        print("Use --force to regenerate them.", file=sys.stderr)
        return 1
    plan = build_director_plan(
        title=title,
        idea=idea,
        slug=slug,
        source=source,
        video_format=args.format,
        duration=args.duration,
    )
    try:
        plan = retime_plan(plan, args.speed)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1
    write_director_files(job_dir, plan, idea)
    output = render_director_video(job_dir, plan, quality=args.quality, fps=args.fps)
    print(f"Director video: {output}")
    print(f"Scene graph: {job_dir / 'scene_graph.json'}")
    return 0


def command_evaluate(args: argparse.Namespace) -> int:
    repo_root = find_repo_root()
    if args.video:
        video_path = Path(args.video)
    else:
        job_dir = repo_root / "content_jobs" / args.slug
        prefix = f"{args.slug}_{args.format}_{args.quality}.mp4"
        director_prefix = f"{args.slug}_director_{args.format}_{args.quality}.mp4"
        director_video = job_dir / "exports" / director_prefix
        video_path = director_video if args.director and director_video.exists() else job_dir / "exports" / prefix
    if not video_path.exists():
        print(f"Video not found: {video_path}", file=sys.stderr)
        return 1
    result = evaluate_export(video_path)
    report_path = video_path.with_name(video_path.stem + "_evaluation.md")
    json_path = video_path.with_name(video_path.stem + "_evaluation.json")
    write_evaluation_report(result, report_path)
    json_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Evaluation: {result['overall']}/100 ({result['verdict']})")
    print(f"Report: {report_path}")
    return 0


def command_doctor(_: argparse.Namespace) -> int:
    checks = {
        "python": sys.executable,
        "manim": shutil.which("manim"),
        "ffmpeg": shutil.which("ffmpeg"),
    }
    optional_modules = ["PIL", "imageio", "imageio_ffmpeg", "numpy"]
    for name, path in checks.items():
        status = path or "missing"
        print(f"{name}: {status}")
    for module in optional_modules:
        try:
            __import__(module)
            status = "installed"
        except ImportError:
            status = "missing"
        print(f"{module}: {status}")

    if not checks["manim"] or not checks["ffmpeg"]:
        print()
        print("Manim rendering needs:")
        print("  brew install ffmpeg cairo pango pkg-config")
        print("  pip install -e \".[manim]\"")
    missing_backend = []
    for module in optional_modules:
        try:
            __import__(module)
        except ImportError:
            missing_backend.append(module)
    if missing_backend:
        print()
        print("Caption-led backend needs:")
        print("  pip install pillow imageio imageio-ffmpeg numpy")
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="content-maxxer",
        description="Create and render shortform Manim content jobs.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    new_parser = subparsers.add_parser("new", help="Create a new content job.")
    new_parser.add_argument("slug", help="Folder-safe job id, for example nexus_explainer_h.")
    new_parser.add_argument("--title", required=True, help="Human-readable video title.")
    new_parser.add_argument("--source-url", default="", help="Paper, doc, repo, or source URL.")
    new_parser.add_argument("--topic", default="", help="Plain-language topic, if different from title.")
    new_parser.add_argument("--force", action="store_true", help="Overwrite template files in an existing job.")
    new_parser.set_defaults(func=command_new)

    render_parser = subparsers.add_parser("render", help="Render a Manim content job.")
    render_parser.add_argument("slug", help="Job id under content_jobs/.")
    render_parser.add_argument("--scene-file", default="scene.py", help="Scene file inside the job folder.")
    render_parser.add_argument("--scene", default="MainScene", help="Manim scene class to render.")
    render_parser.add_argument(
        "--quality",
        choices=["draft", "medium", "high", "production"],
        default="draft",
        help="Manim render quality.",
    )
    render_parser.add_argument("--open", action="store_true", help="Open the rendered video after rendering.")
    render_parser.set_defaults(func=command_render)

    make_parser = subparsers.add_parser("make-video", help="Create a job and render a caption-led MP4.")
    make_parser.add_argument("--title", required=True, help="Human-readable video title.")
    make_parser.add_argument("--idea", required=True, help="Paper, idea, or concept description.")
    make_parser.add_argument("--slug", default="", help="Optional job id. Defaults to a slug from the title.")
    make_parser.add_argument("--source-url", default="", help="Optional source URL.")
    make_parser.add_argument("--pdf", default="", help="Optional local PDF path for tracking.")
    make_parser.add_argument("--format", choices=["vertical", "horizontal", "square"], default="vertical")
    make_parser.add_argument("--duration", type=float, default=25.0, help="Target duration in seconds.")
    make_parser.add_argument("--quality", choices=["draft", "production"], default="draft")
    make_parser.add_argument("--fps", type=int, default=24)
    make_parser.add_argument("--force", action="store_true", help="Overwrite generated planning files.")
    make_parser.set_defaults(func=command_make_video)

    package_parser = subparsers.add_parser("package", help="Render a caption-led MP4 from an existing job.")
    package_parser.add_argument("slug", help="Job id under content_jobs/.")
    package_parser.add_argument("--format", choices=["vertical", "horizontal", "square"], default="vertical")
    package_parser.add_argument("--duration", type=float, default=None, help="Optional target duration in seconds.")
    package_parser.add_argument("--quality", choices=["draft", "production"], default="draft")
    package_parser.add_argument("--fps", type=int, default=24)
    package_parser.set_defaults(func=command_package)

    director_parser = subparsers.add_parser("director", help="Generate a semantic scene graph and director-rendered MP4.")
    director_parser.add_argument("--title", default="", help="Human-readable video title.")
    director_parser.add_argument("--idea", default="", help="Paper, idea, or concept description.")
    director_parser.add_argument("--slug", default="", help="Job id. Can point to an existing job.")
    director_parser.add_argument("--source-url", default="", help="Optional source URL.")
    director_parser.add_argument("--pdf", default="", help="Optional local PDF path for tracking.")
    director_parser.add_argument("--format", choices=["vertical", "horizontal", "square"], default="vertical")
    director_parser.add_argument("--duration", type=float, default=30.0, help="Base planning duration before speed is applied.")
    director_parser.add_argument("--speed", type=float, default=1.75, help="Pacing multiplier. 1.75 makes the rendered video about 1.75x faster.")
    director_parser.add_argument("--quality", choices=["draft", "production"], default="draft")
    director_parser.add_argument("--fps", type=int, default=24)
    director_parser.add_argument("--force", action="store_true", help="Regenerate director files.")
    director_parser.set_defaults(func=command_director)

    evaluate_parser = subparsers.add_parser("evaluate", help="Evaluate a generated video export.")
    evaluate_parser.add_argument("slug", nargs="?", default="", help="Job id under content_jobs/.")
    evaluate_parser.add_argument("--video", default="", help="Optional explicit MP4 path.")
    evaluate_parser.add_argument("--format", choices=["vertical", "horizontal", "square"], default="vertical")
    evaluate_parser.add_argument("--quality", choices=["draft", "production"], default="draft")
    evaluate_parser.add_argument("--director", action="store_true", help="Prefer director-rendered export.")
    evaluate_parser.set_defaults(func=command_evaluate)

    doctor_parser = subparsers.add_parser("doctor", help="Check local render dependencies.")
    doctor_parser.set_defaults(func=command_doctor)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
