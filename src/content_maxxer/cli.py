from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


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


def command_doctor(_: argparse.Namespace) -> int:
    checks = {
        "python": sys.executable,
        "manim": shutil.which("manim"),
        "ffmpeg": shutil.which("ffmpeg"),
    }
    for name, path in checks.items():
        status = path or "missing"
        print(f"{name}: {status}")

    if not checks["manim"] or not checks["ffmpeg"]:
        print()
        print("Install render dependencies on macOS with:")
        print("  brew install ffmpeg cairo pango pkg-config")
        print("  pip install -e .")
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

    doctor_parser = subparsers.add_parser("doctor", help="Check local render dependencies.")
    doctor_parser.set_defaults(func=command_doctor)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
