"""The `unfold` command. See `unfold --help`."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import library
from .ingest import LEVELS, new_video, summary
from .project import REPO, VIDEOS, all_videos, final_video, load_json, scene_ids, video_dir
from .voice import (
    default_voice,
    elevenlabs_voices,
    install_kokoro,
    kokoro_status,
    kokoro_voices,
    openai_voices,
    say_voices,
    speak,
)


def cmd_new(a):
    if os.environ.get("UNFOLD_JOB"):
        raise SystemExit(
            "this background run already has its video; resume it with `unfold status`"
        )
    video, paper = new_video(a.source, a.level, a.minutes, a.focus, a.voice, a.name)
    print(f"video folder: {video}")
    print(summary(paper))


def cmd_lint(a):
    from .storyboard import estimate_minutes, lint

    video = video_dir(a.video)
    issues = lint(video)
    for issue in issues:
        print(issue)
    errors = sum(i.level == "error" for i in issues)
    print(
        f"{errors} errors, {len(issues) - errors} warnings; narration about {estimate_minutes(video):.1f} min"
    )
    return 1 if errors else 0


def cmd_voice(a):
    from .voice import voice_video

    res = voice_video(video_dir(a.video), a.scene, a.force, a.voice)
    print(f"voiced {res['voiced']} beats, {res['cached']} unchanged, voice {res['voice']}")


def _print_defects(defects: list[dict]) -> None:
    """One line per kind of problem, with a count when it repeats."""
    groups: dict[tuple, list] = {}
    for d in defects:
        groups.setdefault((d["kind"], d.get("beat"), d["what"][0], d["what"][-1]), []).append(d)
    for (kind, beat, _, _), found in groups.items():
        d = found[0]
        line = f"   {kind:10} {beat}  {d['what']}  at {d['time']}s"
        if len(found) > 1:
            line += f"  (x{len(found)})"
        if d.get("detail"):
            line += f"  ({d['detail']})"
        print(line)


def cmd_render(a):
    from .render import CodeError, render_scene

    if a.no_sandbox and os.environ.get("UNFOLD_JOB"):
        raise SystemExit("--no-sandbox is not available in background runs")
    video = video_dir(a.video)

    def render(sid):
        try:
            return sid, render_scene(video, sid, a.quality, sandbox=not a.no_sandbox)
        except CodeError as e:
            return sid, {"ok": False, "error": f"code check failed\n{e}"}

    with ThreadPoolExecutor(max_workers=max(1, a.jobs)) as pool:
        results = list(pool.map(render, a.scene or scene_ids(video)))
    for sid, res in results:
        if not res["ok"]:
            print(f"{sid}: FAILED\n{res['error']}")
            continue
        defects = res.get("defects", [])
        print(
            f"{sid}: rendered {res['video']} ({res.get('duration', 0):.1f}s), {len(defects)} layout defects"
        )
        _print_defects(defects)
        for warning in res.get("warnings", []):
            print(f"   warning: {warning}")
        if res.get("sheet"):
            print(f"   contact sheet: {video / res['sheet']}")
            print(f"   critic input:  {video / res['critic_input']}")
    return 1 if any(not res["ok"] for _, res in results) else 0


def cmd_mathcheck(a):
    from .mathcheck import run

    out = run(video_dir(a.video))
    for r in out["items"]:
        if r["status"] in ("FAILED", "unchecked") or a.verbose:
            print(f"{r['status']:12} {r['scene']}.{r['beat']}  {r['tex'][:60]!r}  {r['detail']}")
    print("totals:", ", ".join(f"{k} {v}" for k, v in sorted(out["counts"].items())) or "no math")
    return 1 if out["counts"].get("FAILED") else 0


def cmd_assemble(a):
    from .assemble import assemble

    res = assemble(video_dir(a.video), a.quality, a.rerender, a.jobs, a.fps)
    print(f"final video: {res['video']} ({res['duration']} s)")
    print(f"subtitles:   {res['srt']}")
    for chapter in res["chapters"]:
        print(f"   {chapter}")


def _scene_row(s: dict) -> tuple[str, ...]:
    render = "fresh" if s["rendered"] else "stale" if s["stale_render"] else "-"
    layout = (
        "-" if s["defects"] is None else "clean" if s["defects"] == 0 else f"{s['defects']} defects"
    )
    critic = f"{s['verdict']} {s['score'] or ''}".strip() if s["verdict"] else "-"
    if s["critic_stale"]:
        critic += " (stale)"
    return (
        s["id"],
        str(s["beats"]),
        "ok" if s["voiced"] else "needed",
        "yes" if s["coded"] else "-",
        render,
        layout,
        critic,
        "yes" if s["final"] else "-",
    )


def cmd_status(a):
    video = video_dir(a.video)
    rows = [("scene", "beats", "voice", "code", "render", "layout", "critic", "final")]
    rows += [_scene_row(s) for s in library.scenes(video)]
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    for r in rows:
        print("  ".join(cell.ljust(w) for cell, w in zip(r, widths)))
    info = library.summary(video)
    math = load_json(video / "checks" / "mathcheck.json").get("counts")
    print(f"\nlevel {info['level']}, target {info['minutes']} min, voice {info['voice']}")
    if math:
        print("math:", ", ".join(f"{k} {v}" for k, v in sorted(math.items())))
    if info["job"]:
        print(f"background run: {info['job']['state']}")
    final = final_video(video)
    print(f"final video: {final}" if final else f"next: {info['stage_label'].lower()}")


def cmd_list(a):
    videos = all_videos()
    if not videos:
        print("no videos yet")
    for video in videos:
        info = library.summary(video)
        state = "finished" if info["final"] else info["stage_label"].lower()
        print(f"{video.name:28} {state:28} {info['title']}")


def cmd_open(a):
    final = final_video(video_dir(a.video))
    if not final:
        raise SystemExit("no final video yet; run `unfold assemble` first")
    subprocess.run(["open", str(final)], check=False)
    print(final)


def cmd_clean(a):
    """Remove render caches; keeps the plan, audio, scene code, and the final video."""
    video = video_dir(a.video)
    targets = [".media", "renders/low", "final/.work"] + (
        ["renders/high", "renders/medium"] if a.all else []
    )
    freed = 0
    for sub in targets:
        path = video / sub
        if path.exists():
            freed += sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
            shutil.rmtree(path)
    print(f"freed {freed / 1e6:.0f} MB")


def cmd_where(a):
    print(f"repo:   {REPO}")
    print(f"videos: {VIDEOS}")
    print(f"skill:  {REPO / 'skill'}")


def cmd_web(a):
    from .web import serve

    serve(a.port, open_browser=not a.no_open)


TOOLS = {
    "ffmpeg": "brew install ffmpeg",
    "ffprobe": "brew install ffmpeg",
    "latex": "brew install texlive",
    "dvisvgm": "brew install dvisvgm",
    "say": "macOS only",
    "sandbox-exec": "macOS only; renders run unsandboxed without it",
    "claude": "optional: needed by `unfold web` to make videos (https://claude.com/claude-code)",
}


def cmd_doctor(a):
    """Check that everything a render needs is installed."""
    missing = 0

    def check(good, name, detail="", fix=""):
        nonlocal missing
        optional = fix.startswith("optional")
        missing += not good and not optional
        mark = "ok  " if good else "--  " if optional else "MISS"
        print(f"{mark}  {name:22} {detail}" + (f"\n      fix: {fix}" if not good and fix else ""))

    for tool, fix in TOOLS.items():
        check(shutil.which(tool), tool, shutil.which(tool) or "", fix)
    kpsewhich = shutil.which("kpsewhich")
    for sty in ("newpxtext.sty", "newpxmath.sty", "standalone.cls", "preview.sty"):
        run = (
            subprocess.run([kpsewhich, sty], capture_output=True, text=True) if kpsewhich else None
        )
        check(run and run.stdout.strip(), sty, "", "tlmgr install newpx standalone preview")
    try:
        import manim
        import manimpango

        check(True, "manim", manim.__version__)
        check("Avenir Next" in manimpango.list_fonts(), "font Avenir Next", "", "any macOS has it")
    except ImportError:
        check(False, "manim", "", "uv sync (in the repo)")
    kokoro = kokoro_status()
    check(
        kokoro == "ready",
        "voice kokoro (local)",
        kokoro,
        "optional: unfold voices --install kokoro",
    )
    premium = [v for v in say_voices() if "(Premium)" in v or "(Enhanced)" in v]
    hint = (
        "optional: download one (e.g. Zoe or Ava) in "
        "System Settings > Accessibility > Spoken Content"
    )
    check(premium, "premium macOS voices", ", ".join(premium[:4]), hint)
    skill = Path.home() / ".claude" / "skills" / "unfold"
    link = f"ln -s {REPO / 'skill'} {skill}"
    check(skill.exists(), "/unfold skill", str(skill.resolve()) if skill.exists() else "", link)
    if missing:
        print("\nsome required pieces are missing (see fixes above)")
        return 1
    print("\nall required pieces are installed")


def cmd_voices(a):
    """List voices, install the local Kokoro voice, or preview one."""
    if a.install:
        if a.install != "kokoro":
            raise SystemExit("only `--install kokoro` is supported")
        install_kokoro()
        print(f"kokoro: {kokoro_status()}")
        return
    if a.preview:
        with tempfile.TemporaryDirectory() as tmp:
            clip = Path(tmp) / "preview.wav"
            speak(a.text, a.preview, clip)
            subprocess.run(["afplay", str(clip)], check=False)
        return
    kokoro = [v for v in kokoro_voices() if v.startswith(("af_", "am_", "bf_", "bm_"))]
    print("kokoro:     " + (", ".join(f"kokoro:{v}" for v in kokoro) or f"({kokoro_status()})"))
    print("macOS say:  " + ", ".join(f"say:{v}" for v in say_voices()))
    openai = ", ".join(f"openai:{v}" for v in openai_voices()) or "(set OPENAI_API_KEY)"
    eleven = ", ".join(f"elevenlabs:{v['id']} ({v['name']})" for v in elevenlabs_voices())
    print(f"openai:     {openai}")
    print(f"elevenlabs: {eleven or '(set ELEVENLABS_API_KEY)'}")
    print(f"\ndefault for new videos: {default_voice()}")
    print("preview one:  unfold voices --preview kokoro:af_heart")


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="unfold", description="Turn a paper into an animated explainer video."
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    def command(name, fn, help, video=False):
        s = sub.add_parser(name, help=help)
        s.set_defaults(fn=fn)
        if video:
            s.add_argument("video", help="video folder name (see `unfold list`) or path")
        return s

    s = command("new", cmd_new, "create a video folder and ingest the paper")
    s.add_argument("source", help="arXiv id or link, or a PDF path")
    s.add_argument("--name", help="folder name (default: from the arXiv id or file name)")
    s.add_argument("--level", default="grad", choices=LEVELS)
    s.add_argument("--minutes", type=float, default=5)
    s.add_argument("--focus", help="sections to focus on")
    s.add_argument(
        "--voice", help="kokoro:af_heart, say:Samantha@175, openai:alloy, elevenlabs:<id>"
    )

    command("lint", cmd_lint, "check storyboard.yaml against the visual grammar rules", video=True)

    s = command("voice", cmd_voice, "voice every beat and record its length", video=True)
    s.add_argument("--scene")
    s.add_argument("--voice", help="switch the video to this voice")
    s.add_argument("--force", action="store_true")

    s = command(
        "render", cmd_render, "render scenes in the sandbox and write layout reports", video=True
    )
    s.add_argument("--scene", action="append", help="scene id (repeatable); default all")
    s.add_argument("--quality", default="low", choices=["low", "medium", "high", "4k"])
    s.add_argument("--jobs", "-j", type=int, default=4, help="scenes to render in parallel")
    s.add_argument("--no-sandbox", action="store_true", help="skip sandbox-exec (debugging only)")

    s = command(
        "mathcheck",
        cmd_mathcheck,
        "check on-screen math against the paper and with SymPy",
        video=True,
    )
    s.add_argument("-v", "--verbose", action="store_true")

    s = command(
        "assemble",
        cmd_assemble,
        "render at full quality and build the MP4, subtitles, chapters",
        video=True,
    )
    s.add_argument("--quality", default="high", choices=["medium", "high", "4k"])
    s.add_argument("--rerender", action="store_true")
    s.add_argument("--jobs", "-j", type=int, default=3, help="scenes to render in parallel")
    s.add_argument(
        "--fps", type=int, default=30, help="30 (default) or 60, which is smoother and much slower"
    )

    command("status", cmd_status, "show each scene and the checks it has passed", video=True)
    command("list", cmd_list, "list videos")
    command("open", cmd_open, "open the final video", video=True)

    s = command(
        "clean",
        cmd_clean,
        "delete render caches (keeps plan, audio, code, final video)",
        video=True,
    )
    s.add_argument("--all", action="store_true", help="also delete full-quality scene renders")

    s = command("web", cmd_web, "open the Unfold web app")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--no-open", action="store_true", help="don't open a browser")

    command("where", cmd_where, "print where the repo, videos, and skill are")
    command("doctor", cmd_doctor, "check that everything a render needs is installed")

    s = command("voices", cmd_voices, "list voices, preview one, or install the local kokoro voice")
    s.add_argument("--install", metavar="kokoro")
    s.add_argument("--preview", metavar="VOICE")
    s.add_argument(
        "--text",
        default="Every piece covers half of the gap that is left, so the total closes in on two.",
    )

    a = p.parse_args(argv)
    sys.exit(a.fn(a) or 0)


if __name__ == "__main__":
    main()
