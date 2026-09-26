"""Render every scene at full quality and join them into one MP4 with subtitles and chapters."""

from __future__ import annotations

import json
import subprocess
import textwrap
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .project import ffmpeg, load_json, slugify, storyboard
from .render import inputs_hash, render_scene
from .voice import duration

LOUDNESS = "loudnorm=I=-16:TP=-1.5:LRA=11"
AUDIO = "-c:a aac -ar 48000 -ac 2 -b:a 192k".split()


def _has_audio(clip: Path) -> bool:
    cmd = "ffprobe -v error -select_streams a -show_entries stream=index -of csv=p=0".split()
    return bool(subprocess.run([*cmd, str(clip)], capture_output=True, text=True).stdout.strip())


def _normalize_clip(src: Path, dst: Path) -> None:
    """The same audio format for every clip, with silence added to clips that have none."""
    if _has_audio(src):
        ffmpeg("-i", str(src), "-c:v", "copy", *AUDIO, str(dst))
    else:
        silence = "-f lavfi -i anullsrc=r=48000:cl=stereo -shortest".split()
        ffmpeg("-i", str(src), *silence, "-c:v", "copy", *AUDIO, str(dst))


def _needs_render(video: Path, scene_id: str, quality: str, fps: int | None) -> bool:
    clip = video / "renders" / quality / f"{scene_id}.mp4"
    if not clip.exists():
        return True
    stamp = clip.with_suffix(".inputs")
    if stamp.exists():
        return stamp.read_text().strip() != inputs_hash(video, scene_id, fps)
    # Renders from before fingerprints existed: fall back to comparing times.
    inputs = [
        video / "scenes" / f"{scene_id}.py",
        video / "scenes" / "common.py",
        *(video / "audio").glob(f"{scene_id}_*.wav"),
    ]
    return any(clip.stat().st_mtime < f.stat().st_mtime for f in inputs if f.exists())


def _timestamp(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _cues(text: str, start: float, length: float, width: int = 42):
    """Two-line cues timed by character count; a short last line joins the cue before it."""
    lines = textwrap.wrap(text, width)
    chunks = [" ".join(lines[i : i + 2]) for i in range(0, len(lines), 2)] or [text]
    if len(chunks) > 1 and len(chunks[-1]) < 20:
        chunks[-2:] = [f"{chunks[-2]} {chunks[-1]}"]
    total = sum(len(c) for c in chunks)
    t = start
    for chunk in chunks:
        end = t + length * len(chunk) / total
        yield t, end, "\n".join(textwrap.wrap(chunk, max(width, len(chunk) // 2 + 6)))
        t = end


def assemble(
    video: Path,
    quality: str = "high",
    rerender: bool = False,
    jobs: int = 3,
    fps: int | None = None,
) -> dict:
    sb = storyboard(video)
    scenes = sb.get("scenes", [])
    final = video / "final"
    work = final / ".work"
    work.mkdir(parents=True, exist_ok=True)

    todo = [s["id"] for s in scenes if rerender or _needs_render(video, s["id"], quality, fps)]
    if todo:
        print(f"rendering {', '.join(todo)} at {quality} quality ...", flush=True)
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            renders = pool.map(lambda sid: render_scene(video, sid, quality, fps=fps), todo)
        for sid, res in zip(todo, renders):
            if not res["ok"]:
                raise SystemExit(f"{sid} failed to render:\n{res['error']}")
            if res.get("defects"):
                print(f"  warning: {len(res['defects'])} layout defects in {sid}")

    clips, starts, t = [], [], 0.0
    for s in scenes:
        clip = work / f"{s['id']}.mp4"
        _normalize_clip(video / "renders" / quality / f"{s['id']}.mp4", clip)
        clips.append(clip)
        starts.append(t)
        t += duration(clip)

    (work / "list.txt").write_text("".join(f"file '{c.name}'\n" for c in clips))
    ffmpeg("-f", "concat", "-safe", "0", "-i", "list.txt", "-c", "copy", "joined.mp4", cwd=work)

    titles = [s.get("title", s["id"]) for s in scenes]
    ends = starts[1:] + [t]
    meta = [";FFMETADATA1", f"title={sb.get('title', '')}"]
    for title, a, b in zip(titles, starts, ends):
        meta += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={int(a * 1000)}", f"END={int(b * 1000)}"]
        meta.append(f"title={title}")
    (work / "chapters.ffmeta").write_text("\n".join(meta) + "\n")

    name = slugify(sb.get("title") or video.name)
    out = final / f"{name}.mp4"
    cmd = ["-i", str(work / "joined.mp4"), "-i", str(work / "chapters.ffmeta")]
    music = next(iter(sorted(video.glob("music.*"))), None)  # optional, kept quiet under the voice
    if music:
        mix = f"[2:a]volume=0.07[m];[0:a][m]amix=inputs=2:duration=first:normalize=0,{LOUDNESS}[a]"
        cmd += ["-stream_loop", "-1", "-i", str(music)]
        cmd += ["-filter_complex", mix, "-map", "0:v", "-map", "[a]"]
    else:
        cmd += ["-af", LOUDNESS, "-map", "0:v", "-map", "0:a"]
    finish = "-map_metadata 1 -map_chapters 1 -c:v copy -c:a aac -b:a 192k -ar 48000 -movflags +faststart"
    ffmpeg(*cmd, *finish.split(), str(out))

    cues = []
    for s, start in zip(scenes, starts):
        said = {b["id"]: str(b.get("say", "")).strip() for b in s.get("beats", [])}
        for beat in load_json(video / "checks" / f"{s['id']}.layout.json").get("beats", []):
            if said.get(beat["id"]):
                cues += _cues(said[beat["id"]], start + beat["start"], beat["audio"])
    srt = final / f"{name}.srt"
    srt.write_text(
        "\n".join(
            f"{n}\n{_timestamp(a)} --> {_timestamp(b)}\n{text}\n"
            for n, (a, b, text) in enumerate(cues, 1)
        )
    )

    listing = [f"{int(a // 60)}:{int(a % 60):02d} {title}" for title, a in zip(titles, starts)]
    (final / "chapters.txt").write_text("\n".join(listing) + "\n")
    marks = [{"start": round(a, 3), "title": title} for title, a in zip(titles, starts)]
    index = {"duration": round(t, 3), "chapters": marks}
    (final / "chapters.json").write_text(json.dumps(index, indent=2))
    return {"video": str(out), "srt": str(srt), "duration": round(t, 1), "chapters": listing}
