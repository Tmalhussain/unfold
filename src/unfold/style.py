"""Unfold house style: the only Manim layer scene code should build on.

Scene files start with ``from unfold.style import *`` and subclass
``UnfoldScene``. The library fixes the look (palette, type, layout grid,
timing) and records a layout report on every render so the checker never
depends on vision alone.
"""

from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path

import numpy as np
import yaml
from manim import *  # noqa: F403  (scene files get Manim through this module)
from manim.mobject.text.tex_mobject import MathTexPart

from .texsplit import split_symbols

# Palette

BG = "#0E1116"
INK = "#E8EAED"
MUTED = "#9AA3B2"
ACCENT = "#FFF4D6"  # emphasis for things that are not symbols (warm white)
GRID = "#262D38"
PANEL = "#161B23"

SKY = "#5AB4FF"
AMBER = "#FFB547"
MINT = "#6EDC8C"
ROSE = "#FF6F91"
VIOLET = "#B79CFF"

# The five semantic colors. A storyboard assigns each symbol one of these
# names and the symbol keeps that color for the whole video. Use them only
# for symbols and the things they stand for; tint() them for fills.
ROLES = {"sky": SKY, "amber": AMBER, "mint": MINT, "rose": ROSE, "violet": VIOLET}

# Typography

FONT = "Avenir Next"
TITLE = 44
BODY = 34
CAPTION = 28
SMALL = 24
MIN_FONT = 22  # below this, text is hard to read at 720p

TEX = TexTemplate()
TEX.add_to_preamble(r"\usepackage{amsmath,amssymb,bm}")
TEX.add_to_preamble(r"\usepackage{newpxtext,newpxmath}")

# Timing

T_FAST = 0.5
T = 1.0
T_SLOW = 2.0
HOLD = 1.5  # minimum pause after a hard reveal
EASE = rate_functions.smooth

# Layout

FRAME_W = config.frame_width
MARGIN = 0.45


class Region:
    """A named rectangle of the frame that content is placed into."""

    def __init__(self, name, center, width, height):
        self.name = name
        self.center = np.array([center[0], center[1], 0.0])
        self.width = width
        self.height = height

    @property
    def top(self):
        return self.center[1] + self.height / 2

    @property
    def bottom(self):
        return self.center[1] - self.height / 2

    @property
    def left(self):
        return self.center[0] - self.width / 2

    @property
    def right(self):
        return self.center[0] + self.width / 2


_W = FRAME_W - 2 * MARGIN
TITLE_R = Region("title", (0, 3.1), _W, 0.8)
STAGE = Region("stage", (0, 0.35), _W, 4.5)
STAGE_L = Region("stage_left", (-_W / 4 - 0.1, 0.35), _W / 2 - 0.2, 4.5)
STAGE_R = Region("stage_right", (_W / 4 + 0.1, 0.35), _W / 2 - 0.2, 4.5)
EQ_BAR = Region("eq_bar", (0, -2.45), _W, 0.9)
CAPTION_R = Region("caption", (0, -3.2), _W - 1.0, 0.5)
REGIONS = {r.name: r for r in (TITLE_R, STAGE, STAGE_L, STAGE_R, EQ_BAR, CAPTION_R)}


def place(mob, region=STAGE, aligned=ORIGIN, buff=0.05):
    """Scale ``mob`` down to fit ``region`` (never up) and move it there.

    ``aligned`` pins an edge instead of centering, e.g. ``aligned=LEFT``.
    """
    if isinstance(region, str):
        region = REGIONS[region]
    w, h = region.width - 2 * buff, region.height - 2 * buff
    if mob.width > w or mob.height > h:
        mob.scale(min(w / max(mob.width, 1e-6), h / max(mob.height, 1e-6)))
    target = region.center + aligned * np.array([w / 2, h / 2, 0])
    mob.move_to(target, aligned_edge=aligned)
    return mob


# Video state

VIDEO_DIR = Path(os.environ["UNFOLD_VIDEO"]) if os.environ.get("UNFOLD_VIDEO") else None


def _load_yaml(path):
    try:
        return yaml.safe_load(Path(path).read_text()) or {}
    except (OSError, yaml.YAMLError):
        return {}


def _load_json(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError):
        return {}


STORYBOARD = _load_yaml(VIDEO_DIR / "storyboard.yaml") if VIDEO_DIR else {}
TIMINGS = _load_json(VIDEO_DIR / "audio" / "timings.json") if VIDEO_DIR else {}

# symbol tex -> hex color, from the storyboard's `symbols:` map
SYMBOLS = {
    sym: ROLES.get(str(role).lower(), str(role))
    for sym, role in (STORYBOARD.get("symbols") or {}).items()
}

# Opt-in paper macros: the storyboard's `tex_preamble` lists the \newcommand lines on-screen math
# needs. Loading every macro from the paper breaks LaTeX (papers redefine existing commands).
for line in STORYBOARD.get("tex_preamble") or []:
    TEX.add_to_preamble(str(line))


def color_of(symbol, default=INK):
    return SYMBOLS.get(symbol, default)


# Base style

config.background_color = BG
Text.set_default(font=FONT, color=INK, font_size=BODY)
MarkupText.set_default(font=FONT, color=INK, font_size=BODY)
EQ = 46  # main equations
MathTex.set_default(color=INK, font_size=EQ, tex_template=TEX)
Tex.set_default(color=INK, font_size=EQ, tex_template=TEX)


def M(tex, colors=None, **kwargs):
    """MathTex with every known symbol in its semantic color.

    ``colors`` adds or overrides symbol colors for this equation only.
    Parts can be fetched later with ``eq.get_part_by_tex("x")``.
    """
    cmap = dict(SYMBOLS)
    if colors:
        cmap.update({k: ROLES.get(v, v) for k, v in colors.items()})
    present = [s for s in cmap if s in tex]
    parts = split_symbols(tex, present, split_equals=True)
    try:
        mob = MathTex(*parts, arg_separator="", **kwargs)
    except Exception:
        mob = MathTex(tex, **kwargs)
        mob.unfold_warning = f"could not isolate symbols in {tex!r}"
        return mob
    for sub in mob.submobjects:
        s = getattr(sub, "tex_string", None)
        if s in cmap:
            sub.set_color(cmap[s])
    mob.unfold_tex = tex
    return mob


def align_at(eq, ref, tex="="):
    """Shift ``eq`` sideways so its first ``tex`` part sits under ``ref``'s first one.

    Default is "=". Any ``{{ ... }}`` term works too, e.g. to stack matching terms.
    """
    a, b = terms(eq, tex), terms(ref, tex)
    if not len(a) or not len(b):
        raise ValueError(f"both equations need {tex!r} as its own part (use {{{{ ... }}}})")
    eq.shift(RIGHT * (b[0].get_center()[0] - a[0].get_center()[0]))
    return eq


def terms(eq, *texs):
    """The parts of ``eq`` whose tex is one of ``texs`` (whitespace ignored), as a VGroup.

    Use ``{{ ... }}`` groups in the tex to make a term its own part.
    """
    want = {t.replace(" ", "") for t in texs}
    return VGroup(
        *[p for p in eq.submobjects if str(getattr(p, "tex_string", "")).replace(" ", "") in want]
    )


def T(text, size=BODY, color=INK, **kwargs):
    """House-style text for words. Numbers and symbols use M(), even as labels.

    Rendered at 4x and scaled down: Pango kerning is uneven at small sizes.
    Keep on-screen text short (12 words or fewer).
    """
    return Text(text, font_size=size * 4, color=color, **kwargs).scale(0.25)


def quantity(num, unit, size=30, color=INK):
    """A number with its unit or noun, set as one text label: quantity("350", "GB").

    Prose labels (words, even with numbers) are all sans; bare numbers on diagrams use M().
    """
    return T(f"{num} {unit}", size=size, color=color)


def title(text):
    return place(T(text, size=TITLE, weight="SEMIBOLD"), TITLE_R)


def caption(text, color=MUTED, near=None, buff=0.55):
    """A short caption: in the caption band, or just under ``near`` if given."""
    cap = T(text, size=CAPTION, color=color)
    if near is None:
        return place(cap, CAPTION_R)
    return cap.next_to(near, DOWN, buff=buff)


def tint(color, amount=0.6):
    """``color`` mixed toward the background; for fills of things a symbol stands for."""
    return interpolate_color(ManimColor(BG), ManimColor(color), amount)


class Build(LaggedStart):
    """Write an equation part by part (so each term is earned on screen).

    When it finishes, the scene holds the whole equation again rather than loose parts,
    so later animations and the layout checks see one object.
    """

    def __init__(self, eq, lag=0.25, **kwargs):
        self.eq = eq
        parts = [p for p in eq.submobjects if any(len(x.points) for x in p.get_family())]
        super().__init__(*[Write(p) for p in parts], lag_ratio=lag, **kwargs)

    def clean_up_from_scene(self, scene):
        super().clean_up_from_scene(scene)
        scene.remove(*self.eq.submobjects)
        scene.add(self.eq)


def highlight_term(eq, tex, color=None):
    """Draw attention to one term of ``eq`` and give it its color."""
    part = eq.get_part_by_tex(tex)
    if part is None:
        raise ValueError(f"{tex!r} is not an isolated part of the equation")
    color = color or color_of(tex, AMBER)
    return AnimationGroup(part.animate.set_color(color), Circumscribe(part, color=color, buff=0.08))


def morph_between(a, b, **kwargs):
    """Continuous transform from one expression to the next."""
    if isinstance(a, MathTex) and isinstance(b, MathTex):
        return TransformMatchingTex(a, b, **kwargs)
    return ReplacementTransform(a, b, **kwargs)


def _places(step):
    step = float(step)
    for k in range(4):
        if abs(step * 10**k - round(step * 10**k)) < 1e-9:
            return k
    return 2


def styled_axes(x_range, y_range, width=9, height=4.5, labels=True, **kwargs):
    """Axes in the house style; tick labels use as many decimals as the step needs."""
    ax = Axes(
        x_range=x_range,
        y_range=y_range,
        x_length=width,
        y_length=height,
        tips=False,
        axis_config={"color": MUTED, "stroke_width": 2, "include_ticks": True},
        x_axis_config={
            "decimal_number_config": {"num_decimal_places": _places(x_range[2]), "color": MUTED}
        },
        y_axis_config={
            "decimal_number_config": {"num_decimal_places": _places(y_range[2]), "color": MUTED}
        },
        **kwargs,
    )
    if labels:
        ax.add_coordinates(font_size=CAPTION)
    return ax


def styled_plane(**kwargs):
    kwargs.setdefault("background_line_style", {"stroke_color": GRID, "stroke_width": 1.5})
    kwargs.setdefault("axis_config", {"stroke_color": MUTED})
    return NumberPlane(**kwargs)


def number_line_walk(line: NumberLine, values, dot=None, run_time=None, color=AMBER):
    """A dot that walks along ``line`` through ``values``. Returns (dot, animation)."""
    dot = dot or Dot(line.n2p(values[0]), color=color, radius=0.09)
    steps = [dot.animate.move_to(line.n2p(v)) for v in values[1:]]
    anim = Succession(*steps) if steps else FadeIn(dot)
    if run_time:
        anim.run_time = run_time
    return dot, anim


def graph_with_tracker(axes, func, x_start, color=SKY, x_range=None):
    """Graph plus a dot riding on it. Animate ``g.tracker`` to move the dot."""
    graph = axes.plot(func, color=color, x_range=x_range)
    tracker = ValueTracker(x_start)
    dot = always_redraw(
        lambda: Dot(
            axes.c2p(tracker.get_value(), func(tracker.get_value())), color=AMBER, radius=0.08
        )
    )
    group = VGroup(graph, dot)
    group.graph, group.dot, group.tracker = graph, dot, tracker
    return group


def matrix_transform(plane, matrix, **kwargs):
    """Apply ``matrix`` to a plane (and anything else passed along)."""
    return ApplyMatrix(np.array(matrix), plane, **kwargs)


def geometric_proof_step(shapes, note=None, color=AMBER):
    """Flash the shapes a proof step talks about, optionally with a caption."""
    shapes = shapes if isinstance(shapes, (list, tuple)) else [shapes]
    anims = [s.animate.set_fill(color, opacity=0.35).set_stroke(color) for s in shapes]
    if note is not None:
        anims.append(FadeIn(caption(note) if isinstance(note, str) else note, shift=UP * 0.1))
    return AnimationGroup(*anims)


def heatmap(
    rows, cols, width, height=None, color=SKY, seed=0, lo=0.25, hi=0.95, values=None, gap=0.02
):
    """A matrix drawn as a grid of tinted cells; opacity carries the value (0 to 1).

    Stands in for a weight matrix. ``values`` (rows x cols, 0..1) overrides the random fill.
    Cells are ``m.cells[i][j]``.
    """
    height = height if height is not None else width * rows / cols
    cw, ch = width / cols, height / rows
    rng = np.random.default_rng(seed)
    vals = (
        np.asarray(values, dtype=float) if values is not None else rng.uniform(lo, hi, (rows, cols))
    )
    grid = VGroup()
    cells = []
    for i in range(rows):
        row = []
        for j in range(cols):
            c = Rectangle(
                width=max(cw - gap, 0.005),
                height=max(ch - gap, 0.005),
                stroke_width=0,
                fill_color=color,
                fill_opacity=float(vals[i][j]),
            )
            c.move_to([(j + 0.5) * cw - width / 2, height / 2 - (i + 0.5) * ch, 0])
            row.append(c)
            grid.add(c)
        cells.append(row)
    grid.cells = cells
    return grid


def column(n, cell=0.3, color=AMBER, seed=0, values=None, lo=0.3, hi=0.95):
    """A vector as a column of n tinted cells."""
    return heatmap(n, 1, cell, n * cell, color=color, seed=seed, values=values, lo=lo, hi=hi)


def funnel(h_in, h_out, length, color, opacity=0.8):
    """A trapezoid for a matrix in a flow diagram: h_in tall on the left, h_out on the right."""
    return Polygon(
        [-length / 2, h_in / 2, 0],
        [length / 2, h_out / 2, 0],
        [length / 2, -h_out / 2, 0],
        [-length / 2, -h_in / 2, 0],
        stroke_color=color,
        stroke_width=2,
        fill_color=color,
        fill_opacity=opacity,
    )


def scissors(size=0.8, color=ACCENT):
    """A cut / ablation icon: two finger loops and two crossed blades, pointing right."""
    loops = VGroup(
        Circle(radius=0.13).move_to([-0.32, 0.17, 0]),
        Circle(radius=0.13).move_to([-0.32, -0.17, 0]),
    )
    blades = VGroup(Line([-0.2, 0.1, 0], [0.5, -0.12, 0]), Line([-0.2, -0.1, 0], [0.5, 0.12, 0]))
    pivot = Dot([0.05, 0, 0], radius=0.03, color=color)
    icon = VGroup(loops, blades, pivot)
    loops.set_stroke(color, 3)
    blades.set_stroke(color, 3.5)
    return icon.scale(size / 0.85)


TEXT_TYPES = (Text, MarkupText, Paragraph, SingleStringMathTex, DecimalNumber, Integer, MathTexPart)


def _text_leaves(mobjects):
    out = []

    def walk(m):
        if getattr(m, "unfold_ignore", False):
            return
        if isinstance(m, TEXT_TYPES):
            out.append(m)
            return
        for s in m.submobjects:
            walk(s)

    for m in mobjects:
        walk(m)
    return out


def _segments(mobjects):
    """Straight strokes that should never run through text: lines and box edges."""
    segs = []

    def walk(m):
        if getattr(m, "unfold_ignore", False) or isinstance(m, TEXT_TYPES):
            return
        if isinstance(m, Line) and not isinstance(m, NumberLine) and m.get_stroke_opacity() > 0.3:
            a, b = m.get_start(), m.get_end()
            if np.linalg.norm(b - a) > 0.3:
                segs.append((a[:2], b[:2], m))
        # A real box, not a cell of a heatmap.
        elif (
            isinstance(m, Rectangle)
            and m.get_stroke_opacity() > 0.3
            and m.get_stroke_width() > 0
            and min(m.width, m.height) > 0.4
        ):
            x0, y0, x1, y1 = m.get_left()[0], m.get_bottom()[1], m.get_right()[0], m.get_top()[1]
            for a, b in (
                ((x0, y0), (x1, y0)),
                ((x1, y0), (x1, y1)),
                ((x1, y1), (x0, y1)),
                ((x0, y1), (x0, y0)),
            ):
                segs.append((np.array(a), np.array(b), m))
        for sub in m.submobjects:
            walk(sub)

    for m in mobjects:
        walk(m)
    return segs


def _crosses(seg_a, seg_b, box, shrink=0.12):
    """Does the segment pass through the (slightly shrunk) box?"""
    x0, y0, x1, y1 = box
    dx, dy = (x1 - x0) * shrink, (y1 - y0) * shrink
    x0, x1, y0, y1 = x0 + dx, x1 - dx, y0 + dy, y1 - dy
    if x1 <= x0 or y1 <= y0:
        return False
    # Liang-Barsky clip of the segment against the box
    t0, t1 = 0.0, 1.0
    d = seg_b - seg_a
    for p, q in (
        (-d[0], seg_a[0] - x0),
        (d[0], x1 - seg_a[0]),
        (-d[1], seg_a[1] - y0),
        (d[1], y1 - seg_a[1]),
    ):
        if abs(p) < 1e-12:
            if q < 0:
                return False
        else:
            t = q / p
            if p < 0:
                t0 = max(t0, t)
            else:
                t1 = min(t1, t)
    return t0 < t1


def _visible(m):
    try:
        fam = [x for x in m.get_family() if len(x.points)]
        if not fam:
            return False
        return max(max(x.get_fill_opacity(), x.get_stroke_opacity()) for x in fam) > 0.05
    except Exception:
        return True


def _box(m):
    return (m.get_left()[0], m.get_bottom()[1], m.get_right()[0], m.get_top()[1])


def _label(m):
    for attr in ("unfold_tex", "original_text", "tex_string", "text"):
        v = getattr(m, attr, None)
        if v:
            v = str(v).replace("\n", " ")
            return v if len(v) <= 40 else v[:37] + "..."
    return type(m).__name__


class UnfoldScene(MovingCameraScene):
    """Base class for every Unfold scene.

    Set ``scene_id = "s03"`` and write the scene as a series of beats::

        with self.beat("b1"):
            self.play(Build(eq), run_time=self.share(0.5))

    Each beat plays its narration clip and lasts exactly as long as the clip
    plus the storyboard pause, so animation and voice stay in step.
    """

    scene_id = "s00"

    def setup(self):
        super().setup()
        self.camera.background_color = BG
        self._beats = []
        self._plays = []
        self._defects = {}
        self._warnings = []
        self._beat = None
        sb_scene = next(
            (s for s in STORYBOARD.get("scenes", []) if s.get("id") == self.scene_id), {}
        )
        self._sb_beats = {b.get("id"): b for b in sb_scene.get("beats", [])}

    def _beat_audio(self, beat_id):
        info = (TIMINGS.get(self.scene_id) or {}).get(beat_id)
        if info and VIDEO_DIR and (VIDEO_DIR / info["file"]).exists():
            return VIDEO_DIR / info["file"], float(info["duration"])
        words = len(str(self._sb_beats.get(beat_id, {}).get("say", "")).split())
        return None, max(1.5, words / 2.6)  # ~155 words per minute when not voiced yet

    def share(self, fraction):
        """A run_time that is ``fraction`` of the current beat's narration."""
        return max(0.25, fraction * (self._beat["audio"] if self._beat else 2.0))

    def remaining(self):
        return (
            max(0.0, self._beat["start"] + self._beat["target"] - self.time) if self._beat else 0.0
        )

    @contextlib.contextmanager
    def beat(self, beat_id):
        if self._beat is not None:
            raise RuntimeError("beats cannot be nested")
        audio, dur = self._beat_audio(beat_id)
        pause = float(self._sb_beats.get(beat_id, {}).get("pause", 0.35))
        if self._sb_beats.get(beat_id, {}).get("hard"):
            pause = max(pause, HOLD)
        start = self.time
        if audio:
            self.add_sound(str(audio))
        self._beat = {"id": beat_id, "start": start, "audio": dur, "target": dur + pause}
        try:
            yield self
        except BaseException:
            self._beat = None
            raise
        elapsed = self.time - start
        left = self._beat["target"] - elapsed
        if left > 0.02:
            self.wait(left)
        overrun = elapsed - self._beat["target"]
        if overrun > 1.0:
            self._warnings.append(f"{beat_id}: animation runs {overrun:.1f}s past the narration")
        self._beats.append(
            {
                "id": beat_id,
                "start": round(start, 3),
                "end": round(self.time, 3),
                "audio": round(dur, 3),
                "voiced": audio is not None,
            }
        )
        self._check_layout()
        self._beat = None

    def play(self, *args, **kwargs):
        super().play(*args, **kwargs)
        self._plays.append(
            {"beat": self._beat["id"] if self._beat else None, "end": round(self.time, 3)}
        )
        self._check_layout()

    def _check_layout(self):
        frame = self.camera.frame
        fx, fy = frame.get_center()[0], frame.get_center()[1]
        hw, hh = frame.width / 2, frame.height / 2
        scale = frame.width / FRAME_W
        margin = 0.15 * scale
        leaves = [m for m in _text_leaves(self.mobjects) if _visible(m)]
        on_screen = []
        t = round(self.time, 2)
        beat = self._beat["id"] if self._beat else None
        zoomed = abs(scale - 1) > 0.01
        for m in leaves:
            x0, y0, x1, y1 = _box(m)
            L, R, B, U = fx - hw, fx + hw, fy - hh, fy + hh
            inside = x1 > L and x0 < R and y1 > B and y0 < U
            if inside and (
                x0 < L + margin or x1 > R - margin or y0 < B + margin or y1 > U - margin
            ):
                self._defect("clipped", [m], t, beat)  # partly visible: cut by the frame edge
            elif not inside and not zoomed:
                self._defect("offscreen", [m], t, beat)  # never visible at the normal camera
            if not inside:
                continue
            fs = getattr(m, "font_size", None)
            if fs is not None and fs / scale < MIN_FONT - 0.5:
                self._defect(
                    "too_small", [m], t, beat, extra=f"font_size {fs / scale:.0f} < {MIN_FONT}"
                )
            w = getattr(m, "unfold_warning", None)
            if w and w not in self._warnings:
                self._warnings.append(w)
            on_screen.append(m)
        leaves = on_screen
        for i in range(len(leaves)):
            a = _box(leaves[i])
            for j in range(i + 1, len(leaves)):
                if isinstance(leaves[i], MathTexPart) and isinstance(leaves[j], MathTexPart):
                    continue  # loose parts of one equation touch by design
                b = _box(leaves[j])
                ix = min(a[2], b[2]) - max(a[0], b[0])
                iy = min(a[3], b[3]) - max(a[1], b[1])
                if ix <= 0 or iy <= 0:
                    continue
                area = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
                if area > 0 and ix * iy / area > 0.02:
                    self._defect("overlap", [leaves[i], leaves[j]], t, beat)
        for a, b, owner in _segments(self.mobjects):
            for m in leaves:
                if owner in m.get_family() or m in owner.get_family():
                    continue
                if _crosses(a, b, _box(m)):
                    self._defect("line_through_text", [m, owner], t, beat)

    def _defect(self, kind, mobs, t, beat, extra=None):
        key = (kind, tuple(sorted(id(m) for m in mobs)))
        if key in self._defects:
            self._defects[key]["last_seen"] = t
            return
        self._defects[key] = {
            "kind": kind,
            "what": [_label(m) for m in mobs],
            "time": t,
            "last_seen": t,
            "beat": beat,
            **({"detail": extra} if extra else {}),
        }

    def tear_down(self):
        super().tear_down()
        if self._beat is not None:
            self._warnings.append(f"beat {self._beat['id']} never closed")
        if not VIDEO_DIR:
            return
        out = VIDEO_DIR / "checks" / f"{self.scene_id}.layout.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        missing = [b for b in self._sb_beats if b not in {x["id"] for x in self._beats}]
        report = {
            "scene": self.scene_id,
            "duration": round(self.time, 3),
            "beats": self._beats,
            "plays": self._plays,
            "defects": list(self._defects.values()),
            "warnings": self._warnings + [f"storyboard beat {b} not played" for b in missing],
        }
        out.write_text(json.dumps(report, indent=2))


# Scene files do `from unfold.style import *`; keep helper modules out of that namespace.
__all__ = [
    n
    for n in dir()
    if not n.startswith("_")
    and n not in {"os", "json", "contextlib", "Path", "yaml", "annotations", "split_symbols"}
]
