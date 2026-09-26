"""Lint storyboard.yaml against the visual grammar rules, before any code exists."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .project import settings, storyboard
from .texsplit import split_symbols

ROLE_NAMES = {"sky", "amber", "mint", "rose", "violet"}
MAX_EQS = 2
MAX_WORDS_ON_SCREEN = 12
MAX_BEAT_WORDS = 60
WPM = 155
UNSPEAKABLE = re.compile(r"[\\$^_{}]")


@dataclass
class Issue:
    level: str  # "error" | "warn"
    where: str
    message: str

    def __str__(self):
        return f"{self.level.upper():5}  {self.where:10}  {self.message}"


def _symbols_in(tex: str, symbols: list[str]) -> list[str]:
    return [p for p in split_symbols(tex, symbols) if p in symbols]


def lint(video: Path) -> list[Issue]:
    sb = storyboard(video)
    cfg = settings(video)
    issues: list[Issue] = []

    def err(where, msg):
        issues.append(Issue("error", where, msg))

    def warn(where, msg):
        issues.append(Issue("warn", where, msg))

    if not sb:
        return [Issue("error", "storyboard", "storyboard.yaml is missing or empty")]
    for key in ("title", "guiding_question", "key_insight"):
        if not sb.get(key):
            err("storyboard", f"missing `{key}`")

    symbols = sb.get("symbols") or {}
    for sym, role in symbols.items():
        if str(role).lower() not in ROLE_NAMES:
            err("symbols", f"{sym!r} uses {role!r}; pick one of {sorted(ROLE_NAMES)}")
    sym_keys = list(symbols)

    paper_eqs = set()
    pj = video / "paper" / "paper.json"
    if pj.exists():
        paper_eqs = {e["id"] for e in json.loads(pj.read_text()).get("equations", [])}

    scenes = sb.get("scenes") or []
    if not scenes:
        err("storyboard", "no scenes")
    seen_scene = set()
    introduced: set[str] = set()
    total_words, total_pause = 0, 0.0

    for si, scene in enumerate(scenes):
        sid = scene.get("id", f"#{si + 1}")
        if not re.fullmatch(r"s\d\d", str(sid)):
            err(sid, "scene id must look like s01, s02, ...")
        if sid in seen_scene:
            err(sid, "duplicate scene id")
        seen_scene.add(sid)
        if not scene.get("title"):
            err(sid, "scene needs a `title` (used for chapters)")
        beats = scene.get("beats") or []
        if not beats:
            err(sid, "scene has no beats")
            continue
        if not any(b.get("transform") for b in beats):
            err(
                sid,
                "no beat has `transform: true`; every scene needs at least one continuous transform",
            )
        new_ideas = scene.get("new_ideas")
        if isinstance(new_ideas, list) and len(new_ideas) > 1:
            err(sid, f"introduces {len(new_ideas)} new ideas; at most one per scene")
        seen_beat = set()
        for b in beats:
            bid = b.get("id", "?")
            where = f"{sid}.{bid}"
            if bid in seen_beat:
                err(where, "duplicate beat id")
            seen_beat.add(bid)
            say = str(b.get("say") or "").strip()
            if not say:
                err(where, "beat has no narration (`say`)")
            if UNSPEAKABLE.search(say):
                err(
                    where,
                    "narration contains LaTeX or symbols; write it the way it should be spoken",
                )
            words = len(say.split())
            total_words += words
            if words > MAX_BEAT_WORDS:
                warn(where, f"narration is {words} words; split beats at about 1 to 3 sentences")
            if not b.get("show"):
                warn(where, "no `show:` description of what is on screen")
            text = b.get("text") or []
            text = [text] if isinstance(text, str) else text
            n_words = sum(len(str(t).split()) for t in text)
            if n_words > MAX_WORDS_ON_SCREEN:
                err(where, f"{n_words} words of on-screen text (max {MAX_WORDS_ON_SCREEN})")
            math = b.get("math") or []
            if len(math) > MAX_EQS:
                err(where, f"{len(math)} equations on screen (max {MAX_EQS})")
            for sym in b.get("introduces") or []:
                if sym not in symbols:
                    warn(where, f"introduces {sym!r} but it has no color in `symbols`")
                introduced.add(sym)
            for mi, item in enumerate(math):
                item = item if isinstance(item, dict) else {"tex": str(item)}
                tex = item.get("tex", "")
                if not tex:
                    err(where, f"math[{mi}] has no `tex`")
                    continue
                kinds = [k for k in ("source", "derived", "illustration") if item.get(k)]
                if len(kinds) != 1:
                    err(
                        where,
                        f"math[{mi}] needs exactly one of `source: eqN`, `derived: true`, "
                        "`illustration: true`",
                    )
                if item.get("source") and paper_eqs and item["source"] not in paper_eqs:
                    err(where, f"math[{mi}] cites {item['source']}, which is not in paper.json")
                for sym in _symbols_in(tex, sym_keys):
                    if sym not in introduced:
                        err(
                            where, f"{sym!r} appears in an equation before any beat `introduces` it"
                        )
            pause = b.get("pause")
            if b.get("hard") and pause is not None and float(pause) < 1.5:
                err(where, "hard step needs a pause of at least 1.5 s after the reveal")
            total_pause += float(pause if pause is not None else (1.5 if b.get("hard") else 0.35))

    minutes = cfg.get("minutes") or (sb.get("settings") or {}).get("minutes")
    est = total_words / WPM + total_pause / 60
    if minutes:
        if est < 0.7 * float(minutes) or est > 1.3 * float(minutes):
            warn("storyboard", f"narration runs about {est:.1f} min; target is {minutes} min")
    return issues


def estimate_minutes(video: Path) -> float:
    sb = storyboard(video)
    words = sum(
        len(str(b.get("say", "")).split()) for s in sb.get("scenes", []) for b in s.get("beats", [])
    )
    return words / WPM
