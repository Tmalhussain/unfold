"""Check scene code, render it in a sandbox, and cut keyframes for the critic.

Generated scene code is untrusted. It must pass an import allowlist and a
few static rules, then renders under ``sandbox-exec`` with no network and
writes limited to the video folder and caches.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from .project import PYTHON, ffmpeg, storyboard

ALLOWED_IMPORTS = set("unfold.style manim numpy math random itertools functools common".split())
BANNED_CALLS = set(
    "open exec eval compile __import__ globals locals vars getattr setattr delattr "
    "input breakpoint help exit quit".split()
)
BANNED_NAMES = set(
    "os sys subprocess shutil socket pathlib Path importlib builtins __builtins__ "
    "yaml json utils plugins config".split()
)
QUALITY = {"low": "l", "medium": "m", "high": "h", "4k": "k"}  # 480p15, 720p30, 1080p60, 2160p60
TIMEOUT = {"low": 600, "medium": 900, "high": 1800, "4k": 3600}

SANDBOX_PROFILE = """
(version 1)
(allow default)
(deny network*)
(deny file-write*)
(allow file-write*
  (subpath (param "VIDEO"))
  (subpath (param "TMP"))
  (subpath "/private/tmp")
  (subpath "/private/var/folders")
  (subpath (param "CACHE1"))
  (subpath (param "CACHE2"))
  (subpath (param "CACHE3"))
  (subpath (param "CACHE4"))
  (literal "/dev/null") (literal "/dev/stdout") (literal "/dev/stderr") (literal "/dev/tty")
  (regex #"^/dev/fd/"))
"""


class CodeError(Exception):
    pass


def _rule_problems(tree) -> list[str]:
    problems = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name not in ALLOWED_IMPORTS:
                    problems.append(f"line {node.lineno}: import {a.name} is not allowed")
        elif isinstance(node, ast.ImportFrom):
            if node.module not in ALLOWED_IMPORTS or node.level:
                problems.append(f"line {node.lineno}: from {node.module} import is not allowed")
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in BANNED_CALLS
        ):
            problems.append(f"line {node.lineno}: call to {node.func.id}() is not allowed")
        elif isinstance(node, ast.Name) and node.id in BANNED_NAMES:
            problems.append(f"line {node.lineno}: name {node.id!r} is not allowed")
        elif (
            isinstance(node, ast.Attribute)
            and node.attr.startswith("__")
            and node.attr != "__init__"
        ):
            problems.append(f"line {node.lineno}: dunder attribute {node.attr} is not allowed")
    return problems


def _parse(path: Path):
    try:
        return ast.parse(path.read_text(), filename=str(path))
    except SyntaxError as e:
        raise CodeError(f"{path.name}: syntax error: {e}") from e


def check_common(path: Path) -> None:
    """A video's shared `scenes/common.py` follows the same rules, minus the scene class."""
    problems = _rule_problems(_parse(path))
    if problems:
        raise CodeError("common.py:\n" + "\n".join(problems))


def check_code(path: Path, scene_id: str) -> str:
    """Static checks. Returns the scene class name or raises CodeError."""
    tree = _parse(path)
    problems = _rule_problems(tree)
    classes = [
        n
        for n in tree.body
        if isinstance(n, ast.ClassDef)
        and any(getattr(b, "id", None) == "UnfoldScene" for b in n.bases)
    ]
    if len(classes) != 1:
        problems.append("the file must define exactly one class that subclasses UnfoldScene")
    else:
        ids = [
            n.value.value
            for n in classes[0].body
            if isinstance(n, ast.Assign)
            and any(getattr(t, "id", None) == "scene_id" for t in n.targets)
            and isinstance(n.value, ast.Constant)
        ]
        if ids != [scene_id]:
            problems.append(f'the class must set scene_id = "{scene_id}"')
    if problems:
        raise CodeError("\n".join(problems))
    return classes[0].name


def _sandboxed(cmd: list[str], video: Path, tmp: Path) -> list[str]:
    if not shutil.which("sandbox-exec"):
        return cmd
    home = Path.home()
    params = {
        "VIDEO": str(video.resolve()),
        "TMP": str(tmp.resolve()),
        "CACHE1": str(home / "Library" / "Caches"),
        "CACHE2": str(home / ".cache"),
        "CACHE3": str(home / ".dvisvgm"),
        "CACHE4": str(home / "Library" / "texlive"),
    }
    profile = tmp / "unfold.sb"
    profile.write_text(SANDBOX_PROFILE)
    out = ["sandbox-exec", "-f", str(profile)]
    for k, v in params.items():
        out += ["-D", f"{k}={v}"]
    return out + cmd


def inputs_hash(video: Path, scene_id: str, fps: int | None = None) -> str:
    """Fingerprint of what a render depends on: scene code, shared code, its voice clips, frame rate."""
    h = hashlib.sha256(str(fps).encode())
    scenes = video / "scenes"
    for f in [
        scenes / f"{scene_id}.py",
        scenes / "common.py",
        *sorted((video / "audio").glob(f"{scene_id}_*.wav")),
    ]:
        if f.exists():
            h.update(f.name.encode() + f.read_bytes())
    return h.hexdigest()


def render_scene(
    video: Path, scene_id: str, quality: str = "low", sandbox: bool = True, fps: int | None = None
) -> dict:
    code = video / "scenes" / f"{scene_id}.py"
    if not code.exists():
        raise SystemExit(f"missing {code}")
    # Taken before rendering, so an edit made mid-render counts as a change.
    stamp = inputs_hash(video, scene_id, fps)
    cls = check_code(code, scene_id)
    common = code.parent / "common.py"
    if common.exists():
        check_common(common)
    # One folder per scene: parallel renders must not share the LaTeX cache.
    media = video / ".media" / scene_id
    report = video / "checks" / f"{scene_id}.layout.json"
    report.unlink(missing_ok=True)
    env = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY")}
    env["UNFOLD_VIDEO"] = str(video.resolve())
    env["PYTHONPATH"] = str(code.parent.resolve())  # lets scenes `from common import *`
    (video / ".media").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=video / ".media") as t:
        tmp = Path(t)
        env["TMPDIR"] = str(tmp)
        cmd = [str(PYTHON), "-m", "manim", "render", f"-q{QUALITY[quality]}"]
        if fps:  # after the quality flag, which would otherwise reset the frame rate
            cmd += ["--frame_rate", str(fps)]
        cmd += ["--media_dir", str(media), "--disable_caching", "-o", scene_id, str(code), cls]
        if sandbox:
            cmd = _sandboxed(cmd, video, tmp)
        try:
            proc = subprocess.run(
                cmd, env=env, capture_output=True, text=True, timeout=TIMEOUT[quality], cwd=video
            )
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": f"render timed out after {TIMEOUT[quality]} s"}
    if proc.returncode != 0:
        lines = [
            ln
            for ln in (proc.stderr or proc.stdout).strip().splitlines()
            if "it/s]" not in ln and "s/it]" not in ln and ln.strip()
        ]
        tail = "\n".join(lines[-40:])
        return {"ok": False, "error": tail}
    # the newest file wins: an older render at another frame rate may still sit next to it
    found = sorted((media / "videos").rglob(f"{scene_id}.mp4"), key=lambda f: f.stat().st_mtime)
    if not found:
        return {"ok": False, "error": "render produced no video file"}
    out = found[-1]
    dest = video / "renders" / quality / f"{scene_id}.mp4"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(out, dest)
    dest.with_suffix(".inputs").write_text(stamp)
    result = {"ok": True, "video": str(dest.relative_to(video))}
    if report.exists():
        rep = json.loads(report.read_text())
        rep["quality"] = quality
        report.write_text(json.dumps(rep, indent=2))
        result.update(defects=rep["defects"], warnings=rep["warnings"], duration=rep["duration"])
        if quality != "high" and quality != "4k":
            result["sheet"] = str(contact_sheet(video, scene_id, dest, rep).relative_to(video))
            result["critic_input"] = str(critic_packet(video, scene_id, rep).relative_to(video))
    return result


def keyframe_times(report: dict, per_beat: int = 5) -> list[tuple[str, float]]:
    """The end state of each animation (up to ``per_beat`` per beat) plus the end of every beat."""
    times = []
    plays = report.get("plays", [])
    for b in report.get("beats", []):
        ends = [p["end"] for p in plays if p["beat"] == b["id"] and p["end"] < b["end"] - 0.4]
        if len(ends) > per_beat:
            step = len(ends) / per_beat
            ends = [ends[int(i * step + step - 1)] for i in range(per_beat)]
        if not plays and b["end"] - b["start"] > 6:
            ends = [(b["start"] + b["end"]) / 2]
        for i, t in enumerate(ends, 1):
            times.append((f"{b['id']}.{i}", max(b["start"], t - 0.05)))
        times.append((f"{b['id']} end", max(b["start"], b["end"] - 0.12)))
    return times


def contact_sheet(video: Path, scene_id: str, clip: Path, report: dict) -> Path:
    from PIL import Image, ImageDraw, ImageFont

    frames_dir = video / "frames" / scene_id
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True)
    shots = []
    for i, (label, t) in enumerate(keyframe_times(report)):
        png = frames_dir / f"{i:02d}.png"
        ffmpeg("-ss", f"{t:.2f}", "-i", str(clip), "-frames:v", "1", str(png))
        if png.exists():
            shots.append((f"{label} @ {t:.1f}s", png))
    if not shots:
        raise SystemExit("no keyframes extracted")
    imgs = [Image.open(p) for _, p in shots]
    w, h = imgs[0].size
    cols = 4 if len(imgs) > 9 else 3 if len(imgs) > 4 else 2
    rows = -(-len(imgs) // cols)
    pad, label_h = 12, 28
    size = (cols * (w + pad) + pad, rows * (h + label_h + pad) + pad)
    sheet = Image.new("RGB", size, (40, 44, 52))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 18)
    except OSError:
        font = ImageFont.load_default()
    for i, ((label, _), img) in enumerate(zip(shots, imgs)):
        x = pad + (i % cols) * (w + pad)
        y = pad + (i // cols) * (h + label_h + pad)
        sheet.paste(img, (x, y + label_h))
        draw.text((x, y + 4), label, fill=(230, 230, 230), font=font)
    out = frames_dir / "sheet.png"
    sheet.save(out)
    return out


def critic_packet(video: Path, scene_id: str, report: dict) -> Path:
    """Everything the critic subagent may see: frames, plan, checks. No code, no reasoning."""
    sb = storyboard(video)
    scene = next((s for s in sb.get("scenes", []) if s.get("id") == scene_id), {})
    lines = [
        f"# Critic input for {scene_id}: {scene.get('title', '')}",
        "",
        f"Contact sheet: {video / 'frames' / scene_id / 'sheet.png'}",
        f"Individual frames: {video / 'frames' / scene_id}/NN.png (same order as the sheet)",
        "",
        "## What the storyboard asked for",
        "",
    ]
    for b in scene.get("beats", []):
        lines.append(f"### {b.get('id')}")
        lines.append(f"- Narration: {b.get('say', '')}")
        lines.append(f"- On screen: {b.get('show', '')}")
        for m in b.get("math") or []:
            lines.append(f"- Math: `{m.get('tex') if isinstance(m, dict) else m}`")
        if b.get("text"):
            lines.append(f"- Text: {b.get('text')}")
        lines.append("")
    lines += ["## Symbol colors", ""]
    for sym, role in (sb.get("symbols") or {}).items():
        lines.append(f"- `{sym}`: {role}")
    lines += ["", "## Automated layout report", ""]
    if report["defects"]:
        for d in report["defects"]:
            lines.append(f"- {d['kind']} in {d.get('beat')}: {d['what']} at {d['time']}s")
    else:
        lines.append("- No overlaps, off-screen text, or tiny text found.")
    for w in report["warnings"]:
        lines.append(f"- warning: {w}")
    out = video / "checks" / f"{scene_id}.critic_input.md"
    out.write_text("\n".join(lines) + "\n")
    return out
