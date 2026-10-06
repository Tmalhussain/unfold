"""Make a video in the background: Claude Code runs the /unfold skill headless.

The paper is untrusted text, so the run is boxed in: it starts inside the video's
folder, may edit files only there, may read only the repo and the skill, and may
run no command but `unfold`. UNFOLD_JOB pins that command to this one video and
keeps scene renders sandboxed (see project.video_dir and the CLI). Claude Code
settings, hooks, and MCP servers found in the folder are ignored, and no run
starts while the folder holds any Claude Code config, since a run could plant it
for the next. The run's record and Claude's stream of events are kept next to
the folder, in ``<videos>/.runs/<name>/``, where the run cannot rewrite them.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import threading
import time
from pathlib import Path

from . import keys
from .project import REPO

PLANTED = {".claude", ".mcp.json", "claude.md", "claude.local.md"}


def allowed_tools(video: Path) -> list[str]:
    return [
        f"Bash({REPO}/.venv/bin/unfold:*)",
        "Bash(unfold:*)",
        f"Read(/{REPO}/**)",
        "Read(~/.claude/skills/unfold/**)",
        f"Edit(/{video}/**)",
        f"Write(/{video}/**)",
        "Agent",
        "Skill",
        "TodoWrite",
    ]


def denied_tools(video: Path) -> list[str]:
    paths = (".claude/**", ".mcp.json", "**/CLAUDE.md", "**/CLAUDE.local.md")
    return [f"{tool}(/{video}/{path})" for tool in ("Edit", "Write") for path in paths]


def planted_config(video: Path) -> list[str]:
    """Claude Code config anywhere in the folder, in any letter case (macOS ignores case)."""
    return [str(p.relative_to(video)) for p in video.rglob("*") if p.name.casefold() in PLANTED]


_lock = threading.Lock()


class JobError(Exception):
    pass


def _record_path(video: Path) -> Path:
    return video.parent / ".runs" / video.name / "job.json"


def _log_path(video: Path) -> Path:
    return video.parent / ".runs" / video.name / "claude.jsonl"


def _read(video: Path) -> dict | None:
    try:
        return json.loads(_record_path(video).read_text())
    except (OSError, ValueError):
        return None


def _write(video: Path, record: dict) -> None:
    with _lock:
        _record_path(video).write_text(json.dumps(record, indent=2))


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass
    return True


def _events(video: Path, record: dict, kind: str):
    """Events of one type from the current run's log (the log is compact JSON, one event per line)."""
    log = _log_path(video)
    if not log.exists():
        return
    prefix = f'{{"type":"{kind}"'.encode()
    with open(log, "rb") as f:
        f.seek(record.get("log_offset", 0))
        for line in f:
            if line.startswith(prefix):
                try:
                    yield json.loads(line)
                except ValueError:
                    continue


def start(video: Path) -> dict:
    if not shutil.which("claude"):
        raise JobError("Claude Code is not installed (the `claude` command was not found)")
    current = status(video)
    if current and current["state"] == "running":
        raise JobError("this video is already being made")
    if planted := planted_config(video):
        raise JobError(f"remove the Claude Code config in the video folder first: {planted[0]}")

    log = _log_path(video)
    log.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["claude", "-p", f"/unfold {video.name} autopilot", "--output-format", "stream-json"]
    cmd += ["--verbose", "--setting-sources", "user", "--strict-mcp-config"]
    cmd += ["--allowedTools", *allowed_tools(video), "--disallowedTools", *denied_tools(video)]
    offset = log.stat().st_size if log.exists() else 0
    with open(log, "ab") as out:
        env = keys.env()
        env["UNFOLD_JOB"] = str(video)
        env["PATH"] = f"{REPO / '.venv' / 'bin'}{os.pathsep}{env.get('PATH', '')}"  # finds `unfold`
        proc = subprocess.Popen(
            cmd,
            cwd=video,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    record = {
        "pid": proc.pid,
        "started": time.time(),
        "finished": None,
        "exit_code": None,
        "stopped": False,
        "log_offset": offset,
    }
    _write(video, record)
    threading.Thread(target=_reap, args=(video, proc), daemon=True).start()
    return status(video)


def _reap(video: Path, proc: subprocess.Popen) -> None:
    code = proc.wait()
    record = _read(video) or {}
    if record.get("pid") == proc.pid:
        _write(video, {**record, "finished": time.time(), "exit_code": code})


def stop(video: Path) -> dict:
    record = _read(video)
    if not record or not _alive(record["pid"]) or record.get("finished"):
        raise JobError("nothing is running for this video")
    try:
        os.killpg(record["pid"], signal.SIGTERM)
    except ProcessLookupError:
        pass
    _write(video, {**record, "stopped": True})
    return status(video)


def status(video: Path) -> dict | None:
    """``state`` is running, done, failed, or stopped; None if the video was never run here."""
    record = _read(video)
    if not record:
        return None
    result = next(_events(video, record, "result"), None)
    running = not record.get("finished") and _alive(record["pid"]) and not result
    if running:
        state = "running"
    elif result and not result.get("is_error") and result.get("subtype") == "success":
        state = "done"
    elif record.get("stopped"):
        state = "stopped"
    else:
        state = "failed"
    return {
        "state": state,
        "started": record["started"],
        "finished": record.get("finished"),
        "message": (result or {}).get("result") if state in ("done", "failed") else None,
    }


def _describe(tool: dict) -> str | None:
    """A short sentence for one tool call Claude made, or None for noise."""
    name, args = tool.get("name"), tool.get("input") or {}
    if name == "Bash":
        command = str(args.get("command", "")).replace(f"{REPO}/.venv/bin/", "")
        return args.get("description") or command[:120]
    if name in ("Write", "Edit"):
        path = Path(str(args.get("file_path", "")))
        verb = "Writing" if name == "Write" else "Editing"
        return (
            f"{verb} {path.parent.name}/{path.name}" if path.parent.name else f"{verb} {path.name}"
        )
    if name == "Agent":
        return f"Asked a reviewer: {args.get('description', 'subagent')}"
    if name == "Skill":
        return "Started the unfold skill"
    return None


def activity(video: Path, limit: int = 40) -> list[dict]:
    """The latest things Claude said and did in this video's current run."""
    record = _read(video)
    if not record:
        return []
    items = []
    for event in _events(video, record, "assistant"):
        if event.get("parent_tool_use_id"):
            continue  # subagent chatter stays out of the feed
        for block in event.get("message", {}).get("content", []):
            if block.get("type") == "text" and block.get("text", "").strip():
                items.append({"kind": "note", "text": block["text"].strip()[:600]})
            elif block.get("type") == "tool_use" and (text := _describe(block)):
                items.append({"kind": "step", "text": text})
    return items[-limit:]
