"""Where things live: the repo, the videos folder, and one video's files."""

from __future__ import annotations

import json
import os
import re
import ssl
import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
VIDEOS = Path(os.environ.get("UNFOLD_HOME", REPO / "videos")).expanduser()
PYTHON = Path(sys.executable)


def video_dir(name: str | os.PathLike) -> Path:
    """A video by folder path, or by name under the videos folder."""
    for path in (Path(name).expanduser(), VIDEOS / str(name)):
        if path.is_dir():
            found = path.resolve()
            job = os.environ.get("UNFOLD_JOB")
            if job and found != Path(job).resolve():
                raise SystemExit(f"this background run can only work on {Path(job).name}")
            return found
    raise SystemExit(f"no video folder named {name!r} (looked in {VIDEOS})")


def all_videos() -> list[Path]:
    if not VIDEOS.exists():
        return []
    return sorted(p for p in VIDEOS.iterdir() if (p / "video.yaml").exists())


def slugify(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()[:60] or "video"


def load_yaml(path: Path) -> dict:
    return (yaml.safe_load(path.read_text()) or {}) if path.exists() else {}


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def storyboard(video: Path) -> dict:
    return load_yaml(video / "storyboard.yaml")


def settings(video: Path) -> dict:
    return load_yaml(video / "video.yaml")


def scene_ids(video: Path) -> list[str]:
    return [s["id"] for s in storyboard(video).get("scenes", []) if "id" in s]


def final_video(video: Path) -> Path | None:
    found = sorted((video / "final").glob("*.mp4"))
    return found[-1] if found else None


def ffmpeg(*args: str, cwd: Path | None = None) -> None:
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", *args], check=True, cwd=cwd)


def ssl_context() -> ssl.SSLContext:
    try:
        import certifi  # python.org builds ship without a CA bundle
    except ImportError:
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())
