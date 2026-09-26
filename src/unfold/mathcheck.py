"""Check that every equation on screen is matched against the paper or verified.

Storyboard math items carry exactly one of:
  source: eqN          must match paper equation eqN (after normalizing)
  derived: true        a step the video adds; checked with SymPy when a
                       `check` is given, otherwise listed as unchecked
  illustration: true   numbers or labels that are not claims about the paper

`check` forms for derived items:
  check: identity                 the tex is "lhs = rhs"; verify lhs - rhs == 0
  check: {equals: "<tex>"}        the tex (an expression) equals this expression
  check: {at: {x: 2}, value: 5}   the expression evaluates to `value` at that point
"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path

from .project import storyboard

SPACING = re.compile(
    r"\\(?:,|;|:|!|quad|qquad|displaystyle|textstyle|left|right|big|Big|bigg|Bigg)(?![A-Za-z])"
)


def normalize(tex: str, macros: dict[str, str] | None = None) -> str:
    t = tex
    for name, body in (macros or {}).items():
        t = re.sub(re.escape(name) + r"(?![A-Za-z])", lambda _m: body, t)
    t = re.sub(r"\\label\s*\{[^}]*\}", "", t)
    t = re.sub(r"\\(nonumber|notag)(?![A-Za-z])", "", t)
    t = re.sub(r"\\[dt]frac", r"\\frac", t)
    t = SPACING.sub("", t).replace("{,}", "")
    t = t.replace("&", "").replace("\\\\", "")
    t = re.sub(r"\s+", "", t)
    t = re.sub(r"([_^])\{(\\?[A-Za-z0-9])\}", r"\1\2", t)  # m_{t} -> m_t
    t = re.sub(r"\\mathbf\{([^{}]*)\}", r"\\bm{\1}", t)
    t = t.rstrip(".,;")
    return t


def _simple_macros(lines: list[str]) -> dict[str, str]:
    """Argument-free \\newcommand definitions, for expanding paper notation."""
    out = {}
    for line in lines:
        m = re.match(r"\\(?:re)?newcommand\*?\s*\{?(\\[A-Za-z]+)\}?\s*\{(.*)\}\s*$", line, re.S)
        if m and "#" not in m.group(2):
            out[m.group(1)] = m.group(2)
        m = re.match(r"\\DeclareMathOperator\*?\s*\{(\\[A-Za-z]+)\}\s*\{(.*)\}\s*$", line, re.S)
        if m:
            out[m.group(1)] = r"\operatorname{" + m.group(2) + "}"
    return out


def _parse(tex: str):
    import sympy
    from sympy.parsing.latex import parse_latex

    t = SPACING.sub("", tex).replace("{,}", "")  # 12{,}288 is a digit group, not a tuple
    t = re.sub(r"\\[dt]frac", r"\\frac", t)
    # "r(d + k)" means r times (d + k), not a function r applied to d + k
    t = re.sub(r"(?<![\\A-Za-z])([A-Za-z0-9])\s*\(", r"\1 \\cdot (", t)
    # "d r" (letters side by side) is a product
    t = re.sub(r"(?<![\\A-Za-z])([A-Za-z])\s+(?=[A-Za-z(])", r"\1 \\cdot ", t)
    expr = parse_latex(t, backend="lark")
    if not isinstance(expr, sympy.Basic):
        raise ValueError("ambiguous parse")
    return expr


def _numeric_equal(a, b, trials=6) -> bool:
    import sympy

    syms = sorted((a.free_symbols | b.free_symbols), key=str)
    for _ in range(trials):
        vals = {s: sympy.Float(random.uniform(0.3, 2.7)) for s in syms}
        try:
            va, vb = complex(a.evalf(subs=vals)), complex(b.evalf(subs=vals))
        except Exception:
            return False
        if abs(va - vb) > 1e-7 * max(1.0, abs(va), abs(vb)):
            return False
    return True


def check_derived(tex: str, check) -> tuple[str, str]:
    import sympy

    try:
        if check == "identity":
            if tex.count("=") != 1:
                return "unchecked", "identity check needs exactly one '='"
            lhs, rhs = tex.split("=")
            a, b = _parse(lhs), _parse(rhs)
        elif isinstance(check, dict) and "equals" in check:
            a, b = _parse(tex.split("=")[-1] if "=" in tex else tex), _parse(check["equals"])
        elif isinstance(check, dict) and "at" in check:
            expr = _parse(tex.split("=")[-1] if "=" in tex else tex)
            subs = {sympy.Symbol(k): sympy.nsimplify(v) for k, v in check["at"].items()}
            got = expr.subs(subs).evalf()
            want = sympy.nsimplify(check["value"])
            ok = abs(complex(got) - complex(want)) < 1e-6 * max(1, abs(complex(want)))
            return (
                ("verified", f"= {got}")
                if ok
                else ("FAILED", f"evaluates to {got}, expected {want}")
            )
        else:
            return "unchecked", "no `check` given"
    except Exception as e:  # SymPy cannot parse everything papers write
        return "unchecked", f"SymPy could not parse it ({type(e).__name__})"
    try:
        if sympy.simplify(a - b) == 0:
            return "verified", "symbolic"
    except Exception:
        return "unchecked", "SymPy could not compare the two sides"
    if _numeric_equal(a, b):
        return "verified", "numeric, 6 random points"
    return "FAILED", "sides differ"


def run(video: Path) -> dict:
    sb = storyboard(video)
    pj = video / "paper" / "paper.json"
    paper = json.loads(pj.read_text()) if pj.exists() else {}
    macros = _simple_macros(paper.get("macros", []))
    eqs = {e["id"]: e for e in paper.get("equations", [])}
    results = []
    for s in sb.get("scenes", []):
        for b in s.get("beats", []):
            for i, item in enumerate(b.get("math") or []):
                item = item if isinstance(item, dict) else {"tex": str(item)}
                tex = item.get("tex", "")
                row = {"scene": s["id"], "beat": b.get("id"), "index": i, "tex": tex}
                if item.get("illustration"):
                    row.update(status="illustration", detail="not a claim")
                elif item.get("source"):
                    src = eqs.get(item["source"])
                    if not src:
                        row.update(
                            status="FAILED", detail=f"{item['source']} not found in paper.json"
                        )
                    else:
                        mine, theirs = normalize(tex, macros), normalize(src["tex"], macros)
                        if mine and (mine == theirs or mine in theirs):
                            row.update(
                                status="matched",
                                detail=f"{item['source']} (page {src.get('page')})",
                            )
                        else:
                            row.update(
                                status="FAILED",
                                detail=f"does not match {item['source']}: {src['tex'][:120]}",
                            )
                elif item.get("derived"):
                    status, detail = check_derived(tex, item.get("check"))
                    row.update(status=status, detail=detail)
                else:
                    row.update(status="FAILED", detail="needs source, derived, or illustration")
                results.append(row)
    counts: dict[str, int] = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    out = {"counts": counts, "items": results}
    (video / "checks").mkdir(exist_ok=True)
    (video / "checks" / "mathcheck.json").write_text(json.dumps(out, indent=2))
    return out
