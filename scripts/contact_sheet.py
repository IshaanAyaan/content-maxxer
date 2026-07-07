from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a video contact sheet with ffmpeg.")
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--every", type=int, default=7, help="Sample one frame every N seconds.")
    parser.add_argument("--cols", type=int, default=3)
    parser.add_argument("--rows", type=int, default=3)
    parser.add_argument("--width", type=int, default=480, help="Width of each sampled frame.")
    args = parser.parse_args()

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SystemExit("ffmpeg is missing. Install with: brew install ffmpeg")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    vf = (
        f"fps=1/{args.every},"
        f"scale={args.width}:-1,"
        f"tile={args.cols}x{args.rows}:padding=10:margin=10:color=0x111827"
    )
    command = [
        ffmpeg,
        "-hide_banner",
        "-i",
        str(args.input),
        "-vf",
        vf,
        "-frames:v",
        "1",
        str(args.output),
        "-y",
    ]
    return subprocess.run(command, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
