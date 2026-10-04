"""How far each video has got, for `unfold status`, `unfold list`, and the web app."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from . import jobs
from .project import final_video, load_json, settings, storyboard
from .voice import default_voice, voiced_scenes

STAGES = (
    ("paper", "Read the paper"),
    ("concepts", "Pull out the key ideas"),
    ("story", "Plan the story"),
    ("storyboard", "Storyboard every beat"),
    ("voice", "Record the narration"),
    ("scenes", "Animate and review scenes"),
    ("video", "Assemble the video"),
    ("review", "Review the whole video"),
)


def paper_info(video: Path) -> dict:
    paper = load_json(video / "paper" / "paper.json")
    url = str(paper.get("url") or "")
    if urlparse(url).scheme not in ("http", "https"):  # background runs can edit paper.json
        url = None
    title = paper.get("title") or paper.get("title_tex")
    return {
        "title": storyboard(video).get("title") or title or video.name,
        "paper_title": title,
        "authors": paper.get("authors", []),
        "url": url,
        "published": paper.get("published"),
    }


def scenes(video: Path) -> list[dict]:
    """One row per storyboard scene, with the furthest step it has reached."""
    timings = load_json(video / "audio" / "timings.json")
    voiced = voiced_scenes(video)
    rows = []
    for scene in storyboard(video).get("scenes", []):
        sid = scene["id"]
        code = video / "scenes" / f"{sid}.py"
        low = video / "renders" / "low" / f"{sid}.mp4"
        layout = load_json(video / "checks" / f"{sid}.layout.json")
        critic_file = video / "checks" / f"{sid}.critic.json"
        critic = load_json(critic_file)
        rendered = low.exists() and code.exists() and low.stat().st_mtime >= code.stat().st_mtime
        critic_stale = (
            bool(critic) and low.exists() and critic_file.stat().st_mtime < low.stat().st_mtime
        )
        frames = sorted((video / "frames" / sid).glob("[0-9][0-9].png"))

        if rendered and critic and not critic_stale:
            state = "passed" if critic.get("verdict") == "pass" else "revising"
        elif rendered:
            state = "rendered"
        else:
            state = "coded" if code.exists() else "voiced" if sid in voiced else "planned"

        beats = scene.get("beats", [])
        spoken = sum(t.get("duration", 0) for t in timings.get(sid, {}).values())
        words = sum(len(str(b.get("say", "")).split()) for b in beats)
        rows.append(
            {
                "id": sid,
                "title": scene.get("title", sid),
                "beats": len(beats),
                "seconds": round(spoken or words / 2.6, 1),
                "state": state,
                "voiced": sid in voiced,
                "coded": code.exists(),
                "rendered": rendered,
                "stale_render": low.exists() and not rendered,
                "defects": len(layout["defects"]) if layout else None,
                "verdict": critic.get("verdict"),
                "score": critic.get("score"),
                "critic_stale": critic_stale,
                "final": (video / "renders" / "high" / f"{sid}.mp4").exists(),
                "frame": (
                    f"frames/{sid}/{frames[-1].name}?v={frames[-1].stat().st_mtime_ns}"
                    if frames
                    else None
                ),
            }
        )
    return rows


def stages(video: Path, rows: list[dict] | None = None) -> list[dict]:
    rows = scenes(video) if rows is None else rows
    done = {
        "paper": (video / "paper" / "paper.json").exists(),
        "concepts": (video / "concepts.md").exists(),
        "story": (video / "story.md").exists(),
        "storyboard": bool(rows),
        "voice": bool(rows) and all(r["voiced"] for r in rows),
        "scenes": bool(rows) and all(r["state"] == "passed" for r in rows),
        "video": final_video(video) is not None,
        "review": (video / "checks" / "review.json").exists(),
    }
    return [{"key": key, "label": label, "done": done[key]} for key, label in STAGES]


def chapters(video: Path) -> dict:
    """Chapter starts and total length of the final video (written by `unfold assemble`)."""
    return load_json(video / "final" / "chapters.json") or {"duration": None, "chapters": []}


def beats(video: Path) -> list[dict]:
    """Every narrated beat of the final video: when it plays, what is said, and what is on screen."""
    timed = []
    for scene, mark in zip(storyboard(video).get("scenes", []), chapters(video)["chapters"]):
        planned = {b["id"]: b for b in scene.get("beats", [])}
        for beat in load_json(video / "checks" / f"{scene['id']}.layout.json").get("beats", []):
            plan = planned.get(beat["id"], {})
            if str(plan.get("say", "")).strip():
                timed.append(
                    {
                        "scene": scene["id"],
                        "title": scene.get("title", scene["id"]),
                        "start": round(mark["start"] + beat["start"], 3),
                        "end": round(mark["start"] + beat["end"], 3),
                        "say": str(plan["say"]).strip(),
                        "show": str(plan.get("show", "")).strip(),
                    }
                )
    return timed


def transcript(video: Path) -> list[dict]:
    return [{"start": b["start"], "end": b["end"], "text": b["say"]} for b in beats(video)]


def summary(video: Path) -> dict:
    cfg = settings(video)
    rows = scenes(video)
    steps = stages(video, rows)
    final = final_video(video)
    current = next((s for s in steps if not s["done"]), None)
    return {
        "name": video.name,
        **paper_info(video),
        "level": cfg.get("level"),
        "minutes": cfg.get("minutes"),
        "voice": cfg.get("voice") or default_voice(),
        "source": cfg.get("source"),
        "final": final.name if final else None,
        "duration": chapters(video).get("duration"),
        "stage": current["key"] if current else "done",
        "stage_label": current["label"] if current else "Done",
        "progress": sum(s["done"] for s in steps) / len(steps),
        "scene_states": [r["state"] for r in rows],
        "job": jobs.status(video),
        "updated": max((p.stat().st_mtime for p in video.iterdir()), default=0),
    }


def detail(video: Path) -> dict:
    sb = storyboard(video)
    rows = scenes(video)
    return {
        **summary(video),
        "question": sb.get("guiding_question"),
        "insight": sb.get("key_insight"),
        "scenes": rows,
        "stages": stages(video, rows),
        "chapters": chapters(video),
        "transcript": transcript(video) if final_video(video) else [],
        "review": load_json(video / "checks" / "review.json"),
        "math": load_json(video / "checks" / "mathcheck.json").get("counts", {}),
        "activity": jobs.activity(video),
    }
