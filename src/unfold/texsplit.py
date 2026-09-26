"""Split LaTeX so each colored symbol compiles as its own part (no Manim import)."""

from __future__ import annotations

import re

_CONTROL_WORD = re.compile(r"\\[A-Za-z]+")
_TEXT_ARG = re.compile(r"\\(?:text|mathrm|operatorname|textbf|textit|mbox)\s*\{[^{}]*\}")


def split_symbols(tex, symbols, split_equals=False):
    """Split ``tex`` into parts so each colored symbol is its own part.

    Symbols are matched longest first and never inside a control word or a
    \\text{} argument. Each symbol is wrapped in braces so scripts and accents
    around it still attach.
    """
    if not symbols and not split_equals:
        return [tex]
    blocked = [False] * len(tex)
    for rx in (_CONTROL_WORD, _TEXT_ARG):
        for m in rx.finditer(tex):
            for i in range(m.start(), m.end()):
                blocked[i] = True
    order = sorted(symbols, key=len, reverse=True)
    parts, buf, i, depth = [], "", 0, 0
    while i < len(tex):
        hit = None
        for s in order:
            if tex.startswith(s, i) and _can_isolate(tex, i, s, blocked):
                hit = s
                break
        if hit:
            # Braces keep a following script or a preceding accent/script attached
            # to the symbol even though it is compiled as its own part.
            parts.append(buf + " {")
            parts.append(hit)
            buf = "} "
            i += len(hit)
            continue
        c = tex[i]
        if split_equals and c == "=" and depth == 0 and not blocked[i]:
            # A top-level "=" becomes its own part (no braces, so relation spacing
            # is kept) so equations can be aligned at it.
            if buf.strip():
                parts.append(buf)
            parts.append("=")
            buf = ""
            i += 1
            continue
        if c == "\\" and i + 1 < len(tex):
            buf += tex[i : i + 2]
            i += 2
            continue
        depth += (c == "{") - (c == "}")
        buf += c
        i += 1
    if buf:
        parts.append(buf)
    return parts


def _can_isolate(tex, i, s, blocked):
    end = i + len(s)
    if s.startswith("\\"):
        lead = _CONTROL_WORD.match(s)
        here = _CONTROL_WORD.match(tex, i)
        return bool(lead and here and lead.group(0) == here.group(0))
    return not any(blocked[i:end])
