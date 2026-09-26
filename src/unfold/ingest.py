"""Create a video folder and turn its paper into paper.json and paper.md.

arXiv LaTeX source is preferred because it gives exact equations. PDF-only
papers fall back to page text, and the math check has nothing to diff against.
"""

from __future__ import annotations

import gzip
import io
import json
import re
import shutil
import tarfile
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

from .project import VIDEOS, settings, slugify, ssl_context

ARXIV_ID = re.compile(
    r"(?:arxiv\.org/(?:abs|pdf|e-print)/)?"
    r"(\d{4}\.\d{4,5}(?:v\d+)?|[a-z\-]+(?:\.[A-Z]{2})?/\d{7}(?:v\d+)?)",
    re.I,
)
ATOM = {"a": "http://www.w3.org/2005/Atom"}
EQ_ENVS = tuple("equation align gather multline eqnarray displaymath flalign alignat".split())
THM_ENVS = tuple("theorem lemma proposition corollary definition claim remark assumption".split())
LEVELS = ("highschool", "undergrad", "grad", "expert")


def arxiv_id(source: str) -> str | None:
    if Path(source).expanduser().exists():
        return None
    m = ARXIV_ID.search(source.strip())
    return m.group(1) if m else None


def new_video(
    source: str,
    level: str = "grad",
    minutes: float = 5,
    focus: str | None = None,
    voice: str | None = None,
    name: str | None = None,
) -> tuple[Path, dict]:
    """Create (or refresh) ``videos/<name>/`` for a paper and ingest it."""
    if level not in LEVELS:
        raise SystemExit(f"level must be one of {', '.join(LEVELS)}")
    aid = arxiv_id(source)
    if not aid and not Path(source).expanduser().is_file():
        raise SystemExit(f"{source!r} is not an arXiv link or ID, and no file has that name.")
    video = VIDEOS / (name or slugify(aid or Path(source).stem))
    video.mkdir(parents=True, exist_ok=True)
    cfg = {
        "source": source,
        "level": level,
        "minutes": minutes,
        "focus": focus or "whole paper",
        "voice": voice,
        "language": "en",
    }
    cfg = {**settings(video), **{k: v for k, v in cfg.items() if v}}
    (video / "video.yaml").write_text(yaml.safe_dump(cfg, sort_keys=False))
    for sub in ("scenes", "audio", "checks"):
        (video / sub).mkdir(exist_ok=True)
    return video, ingest(source, video)


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "unfold (paper-to-video tool)"})
    with urllib.request.urlopen(req, timeout=60, context=ssl_context()) as r:
        return r.read()


def fetch_arxiv(aid: str, dest: Path) -> dict:
    meta = {"arxiv_id": aid, "url": f"https://arxiv.org/abs/{aid}"}
    try:
        entry = ET.fromstring(_get(f"https://export.arxiv.org/api/query?id_list={aid}")).find(
            "a:entry", ATOM
        )
        if entry is not None:
            meta["title"] = " ".join(entry.findtext("a:title", "", ATOM).split())
            meta["abstract"] = " ".join(entry.findtext("a:summary", "", ATOM).split())
            meta["authors"] = [
                a.findtext("a:name", "", ATOM) for a in entry.findall("a:author", ATOM)
            ]
            meta["published"] = entry.findtext("a:published", "", ATOM)[:10]
    except Exception as e:  # the metadata is nice to have, the paper is not optional
        meta["metadata_error"] = str(e)

    (dest / "paper.pdf").write_bytes(_get(f"https://arxiv.org/pdf/{aid}"))
    src = dest / "source"
    src.mkdir(parents=True, exist_ok=True)
    blob = _get(f"https://arxiv.org/e-print/{aid}")
    try:
        with tarfile.open(fileobj=io.BytesIO(blob), mode="r:*") as tar:
            tar.extractall(src, filter="data")
    except tarfile.ReadError:
        try:
            blob = gzip.decompress(blob)
        except OSError:
            pass
        if blob[:4] == b"%PDF":
            meta["source_error"] = "arXiv has no LaTeX source for this paper (PDF only)"
        else:
            (src / "main.tex").write_bytes(blob)
    return meta


def _strip_comments(tex: str) -> str:
    return re.sub(r"(?<!\\)%.*", "", tex)


def _find_main(src: Path) -> Path | None:
    candidates = []
    for path in src.rglob("*.tex"):
        text = path.read_text(errors="ignore")
        if "\\documentclass" in text:
            candidates.append(("\\begin{document}" in text, len(text), path))
    return max(candidates)[2] if candidates else None


def _flatten(path: Path, root: Path, depth: int = 0) -> str:
    text = _strip_comments(path.read_text(errors="ignore"))
    if depth > 8:
        return text

    def inline(m):
        name = m.group(2).strip()
        for cand in (
            root / name,
            root / f"{name}.tex",
            path.parent / name,
            path.parent / f"{name}.tex",
        ):
            if cand.is_file():
                return _flatten(cand, root, depth + 1)
        return ""

    return re.sub(r"\\(input|include)\s*\{([^}]+)\}", inline, text)


def _balanced(s: str, start: int) -> tuple[str, int]:
    """The {...} group opening at ``start``, and the index just past it."""
    depth, i = 0, start
    while i < len(s):
        if s[i] == "\\":
            i += 2
            continue
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
            if depth == 0:
                return s[start + 1 : i], i + 1
        i += 1
    return s[start + 1 :], len(s)


MACRO_DEFS = (
    r"\\(?:re)?newcommand\*?\s*\{?\\[A-Za-z@]+\}?(?:\[\d\])?(?:\[[^\]]*\])?\s*\{",
    r"\\DeclareMathOperator\*?\s*\{\\[A-Za-z]+\}\s*\{",
    r"\\def\s*\\[A-Za-z@]+\s*\{",
)


def _macros(tex: str) -> list[str]:
    found = []
    for pattern in MACRO_DEFS:
        for m in re.finditer(pattern, tex):
            _, end = _balanced(tex, m.end() - 1)
            found.append((m.start(), tex[m.start() : end]))
    return [text for _, text in sorted(found)]


def _clean_eq(tex: str) -> str:
    tex = re.sub(r"\\label\s*\{[^}]*\}", "", tex)
    return re.sub(r"\\(nonumber|notag)\b", "", tex).strip()


def _squash(text: str) -> str:
    return " ".join(text.split())


def parse_latex(main: Path, root: Path) -> dict:
    full = _flatten(main, root)
    _, _, body = full.partition("\\begin{document}")
    body = body.split("\\end{document}")[0] if body else full

    abstract = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", body, re.S)
    tokens = re.compile(
        r"\\(?P<level>section|subsection|subsubsection)\*?\s*(?:\[[^\]]*\])?\s*\{"
        rf"|\\begin\{{(?P<env>(?:{'|'.join(EQ_ENVS)})\*?)\}}(?P<envbody>.*?)\\end\{{(?P=env)\}}"
        r"|\\\[(?P<brk>.*?)\\\]"
        r"|\$\$(?P<dd>.*?)\$\$",
        re.S,
    )
    sections = [{"id": "sec0", "title": "Front matter", "level": 1, "text": ""}]
    equations, md, pos = [], [], 0
    for m in tokens.finditer(body):
        sections[-1]["text"] += body[pos : m.start()]
        md.append(body[pos : m.start()])
        if m.group("level"):
            title, pos = _balanced(body, m.end() - 1)
            level = ("section", "subsection", "subsubsection").index(m.group("level")) + 1
            sections.append(
                {"id": f"sec{len(sections)}", "title": _squash(title), "level": level, "text": ""}
            )
            md.append(f"\n\n{'#' * (level + 1)} {_squash(title)}\n\n")
            continue
        raw = m.group("envbody") or m.group("brk") or m.group("dd") or ""
        label = re.search(r"\\label\s*\{([^}]*)\}", raw)
        eq = {
            "id": f"eq{len(equations) + 1}",
            "env": m.group("env") or ("displaymath" if m.group("brk") is not None else "dollars"),
            "tex": _clean_eq(raw),
            "label": label.group(1) if label else None,
            "section": sections[-1]["id"],
        }
        eq["ok"] = bool(eq["tex"]) and eq["tex"].count("{") == eq["tex"].count("}")
        equations.append(eq)
        tag = f"[{eq['id']}]" + (f" (label {eq['label']})" if eq["label"] else "")
        md.append(f"\n\n{tag}\n$$\n{eq['tex']}\n$$\n\n")
        pos = m.end()
    sections[-1]["text"] += body[pos:]
    md.append(body[pos:])
    for s in sections:
        s["text"] = s["text"].strip()

    theorem = rf"\\begin\{{({'|'.join(THM_ENVS)})\*?\}}(.*?)\\end\{{\1\*?\}}"
    theorems = [
        {"kind": m[1], "text": _squash(m[2])[:2000]} for m in re.finditer(theorem, body, re.S)
    ]
    captions = [
        _squash(_balanced(body, m.end() - 1)[0])[:600] for m in re.finditer(r"\\caption\s*\{", body)
    ]
    title = re.search(r"\\title\s*(?:\[[^\]]*\])?\s*\{", full)

    return {
        "title_tex": _squash(_balanced(full, title.end() - 1)[0]) if title else "",
        "abstract_tex": _squash(abstract.group(1)) if abstract else "",
        "macros": _macros(full),
        "sections": [s for s in sections if s["text"] or s["id"] != "sec0"],
        "equations": equations,
        "theorems": theorems,
        "figure_captions": captions,
        "markdown": "".join(md),
    }


def pdf_pages(pdf: Path) -> list[str]:
    import pymupdf

    with pymupdf.open(pdf) as doc:
        return [page.get_text() for page in doc]


def pdf_title(pdf: Path) -> str | None:
    """The PDF's title metadata if it looks real, else the largest text on page 1."""
    import pymupdf

    with pymupdf.open(pdf) as doc:
        meta = (doc.metadata or {}).get("title", "").strip()
        if len(meta) > 8 and not meta.lower().endswith((".dvi", ".pdf", ".tex")):
            return meta
        if not len(doc):
            return None
        spans = [
            (span["size"], span["text"].strip(), line["bbox"][1])
            for block in doc[0].get_text("dict")["blocks"]
            for line in block.get("lines", [])
            for span in line["spans"]
            if span["text"].strip()
        ]
    if not spans:
        return None
    biggest = max(size for size, _, _ in spans)
    title = " ".join(
        text for size, text, _ in sorted(spans, key=lambda s: s[2]) if size >= biggest - 0.5
    )
    return title if 3 <= len(title) <= 200 else None


def _letters(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def assign_pages(paper: dict, pages: list[str]) -> None:
    """Best-effort page numbers for sections (by finding their titles) and their equations."""
    text = [_letters(p) for p in pages]
    last = 1
    for s in paper.get("sections", []):
        key = _letters(re.sub(r"\\[A-Za-z]+|[{}$]", "", s["title"]))[:40]
        s["page"] = next(
            (i + 1 for i, t in enumerate(text) if key and key in t and i + 1 >= last), last
        )
        last = s["page"]
    pages_by_section = {s["id"]: s["page"] for s in paper.get("sections", [])}
    for eq in paper.get("equations", []):
        eq["page"] = pages_by_section.get(eq["section"], 1)


def _per_page(pages: list[str]) -> str:
    return "\n\n".join(f"## Page {i}\n\n{text}" for i, text in enumerate(pages, 1))


def ingest(source: str, video: Path) -> dict:
    """Fill ``video/paper/`` from an arXiv id or link, or a local PDF."""
    dest = video / "paper"
    dest.mkdir(parents=True, exist_ok=True)
    aid = arxiv_id(source)
    if aid:
        meta = fetch_arxiv(aid, dest)
    else:
        pdf = Path(source).expanduser()
        shutil.copy(pdf, dest / "paper.pdf")
        meta = {"file": str(pdf.resolve()), "title": pdf_title(dest / "paper.pdf") or pdf.stem}

    pages = pdf_pages(dest / "paper.pdf")
    main = _find_main(dest / "source") if (dest / "source").exists() else None
    paper = parse_latex(main, dest / "source") if main else None
    if paper and not paper["equations"] and len(paper["sections"]) <= 1:
        meta["source_error"] = "the arXiv source only wraps a PDF, so there is no LaTeX to parse"
        paper = None
    if paper:
        paper.update(source="latex", main_tex=str(main.relative_to(dest)))
        assign_pages(paper, pages)
    else:
        paper = {
            "source": "pdf",
            "sections": [],
            "equations": [],
            "theorems": [],
            "figure_captions": [],
            "macros": [],
            "markdown": _per_page(pages),
        }
    paper.update(meta, pages=len(pages))

    head = [f"# {paper.get('title') or paper.get('title_tex') or 'Untitled'}", ""]
    if paper.get("authors"):
        head.append("Authors: " + ", ".join(paper["authors"]))
    if paper.get("url"):
        head.append(f"Link: {paper['url']}")
    if paper.get("abstract"):
        head += ["", f"Abstract: {paper['abstract']}"]
    if paper["equations"]:
        head += [
            "",
            "Display equations are tagged [eqN]; storyboard math cites them with `source: eqN`.",
            "",
        ]
    else:
        head += [
            "",
            "No LaTeX source: text below is per page. Mark paper equations `derived` in the storyboard.",
            "",
        ]
    (dest / "paper.md").write_text("\n".join(head) + "\n" + paper.pop("markdown"))
    (dest / "pages.md").write_text(_per_page(pages))
    (dest / "paper.json").write_text(json.dumps(paper, indent=2))
    return paper


def summary(paper: dict) -> str:
    eqs = paper.get("equations", [])
    ok = sum(1 for e in eqs if e.get("ok"))
    parsed = f"{ok}/{len(eqs)} ({100 * ok / len(eqs):.0f}%)" if eqs else "0 (no LaTeX source)"
    lines = [
        f"title:     {paper.get('title') or paper.get('title_tex')}",
        f"source:    {paper.get('source')}  pages: {paper.get('pages')}",
        f"sections:  {len(paper.get('sections', []))}",
        f"equations: {parsed} parsed",
        f"theorems:  {len(paper.get('theorems', []))}  figures: {len(paper.get('figure_captions', []))}",
    ]
    if paper.get("source_error"):
        lines.append(f"note:      {paper['source_error']}")
    if paper.get("source") == "pdf":
        lines.append(
            "note:      PDF only, so on-screen math cannot be diffed against the paper. "
            "Mark paper equations as `derived` and read them yourself."
        )
    return "\n".join(lines)
