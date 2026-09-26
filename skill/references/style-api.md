# Writing scene code

Every scene file looks like this:

```python
from unfold.style import *


class S03(UnfoldScene):
    scene_id = "s03"

    def construct(self):
        eq = place(M(r"a^2 + b^2 = c^2"), EQ_BAR)
        with self.beat("b1"):
            self.play(Build(eq), run_time=self.share(0.6))
        with self.beat("b2"):
            ...
```

Worked examples: `<repo>/examples/reference/scenes/s01.py` (geometry, labels, lagged growth),
`s02.py` (equations built term by term, stacked and morphed), `s03.py` (axes, dots, a moving gap
bar, a camera zoom).

## Hard rules (the static check or the sandbox enforces them)

- Imports: only `from unfold.style import *`, plus `numpy`, `math`, `random`, `itertools`,
  `functools` if needed. Everything from Manim is already in scope.
- Exactly one class, subclassing `UnfoldScene`, with `scene_id = "sNN"` matching the file name.
- No file, network, or OS access; no `open`, `exec`, `eval`, `getattr`, `setattr`, dunder
  attributes, `config`, `os`, `sys`, `Path`.

## Beats and timing

- Wrap every storyboard beat in `with self.beat("bN"):`, in storyboard order, all beats present.
  The beat starts that beat's narration clip and, on exit, waits until the clip (plus the pause)
  has finished. So never add your own trailing `self.wait()`.
- Give each `play` a `run_time=self.share(f)`: `f` is the fraction of the beat's narration it
  should take. The shares in one beat should add up to about 0.7 to 1.0. Going over 1.0 makes the
  animation run past the narration (reported as a warning).
- `self.remaining()` is the time left in the current beat.
- Build objects before the `with` block when they are only positioned there; animate inside.

## Style: use these instead of raw Manim

| Need | Use |
| --- | --- |
| Math | `M(r"tex")`: MathTex with every storyboard symbol in its color; top-level `=` is its own part |
| A term you will move, match, or highlight | wrap it `{{ ... }}` with spaces around: `M(r"S = {{ 1 }} + {{ \tfrac{1}{2} }}")` |
| Text (words only) | `T("words", size=BODY)`; sizes `TITLE` 44, `BODY` 34, `CAPTION` 28, `SMALL` 24 (never below 22) |
| A label with words, even with numbers in it ("350 GB", "100 copies: 35 TB") | `T(...)` or `quantity("350", "GB")`: prose is all sans, one font per label |
| Bare numbers on a diagram (tick labels, cell values, piece sizes) | `M("2")`, `M(r"\frac{1}{8}", font_size=30)`, never `T("2")`: one math font for all numbers |
| A scene title / a caption | `title("...")`, `caption("...")` in the caption band, or `caption("...", near=diagram)` just under it |
| Placement | `place(mob, REGION, aligned=LEFT)`; regions `TITLE_R`, `STAGE`, `STAGE_L`, `STAGE_R`, `EQ_BAR`, `CAPTION_R`; `Region(name, center, w, h)` for a custom box |
| Build an equation term by term | `Build(eq, lag=0.25)` |
| Morph one expression into the next | `morph_between(a, b)` (TransformMatchingTex for math) |
| Highlight one term | `highlight_term(eq, r"\theta")` |
| Parts of an equation | `terms(eq, r"\tfrac{1}{2}", r"\cdots")` -> VGroup |
| Line equations up | `align_at(lower, upper)` at "=", or `align_at(lower, upper, r"\tfrac{1}{2}")` at a term |
| Axes | `styled_axes([x0, x1, step], [y0, y1, step], width, height)`; points via `ax.c2p(x, y)` |
| Plane | `styled_plane()`; `matrix_transform(plane, [[a, b], [c, d]])` |
| Moving point on a graph | `g = graph_with_tracker(ax, f, x_start)`; animate `g.tracker.animate.set_value(x)` |
| A weight matrix | `heatmap(rows, cols, width, color=SKY, seed=1)`; cells at `m.cells[i][j]` (opacity = value) |
| A vector | `column(n, cell=0.3, color=color_of("x"))` |
| A matrix in a flow diagram | `funnel(h_in, h_out, length, color)`: a trapezoid, e.g. A squeezing k down to r |
| Knock out / cut / ablate | `scissors(size=0.8)`: an icon pointing right |
| Helpers or data shared by several scenes | put them in `scenes/common.py` (same rules) and `from common import *` |
| Walk along a number line | `dot, anim = number_line_walk(line, [0, 1, 1.5])` |
| Proof step on shapes | `geometric_proof_step([shape1, shape2], "caption words")` |
| Symbol color outside math | `color_of("x")` |
| Colors | `SKY AMBER MINT ROSE VIOLET` (semantic), `INK` text, `MUTED` secondary, `ACCENT` emphasis, `GRID`, `PANEL`, `BG` |
| Fill for something a symbol stands for | `tint(color_of("S"), 0.6)` (two tints alternate well) |
| Timing constants | `T_FAST` 0.5, `T` 1.0, `T_SLOW` 2.0, `HOLD` 1.5; easing `EASE` |
| Camera | `self.camera.frame.animate.scale(0.5).move_to(point)` (MovingCameraScene) |

## Visual grammar

- Every beat changes something the narration is talking about at that moment.
- Prefer continuous motion: Transform, TransformMatchingTex, GrowFromEdge, animate a ValueTracker,
  move the camera. Avoid FadeOut-everything then FadeIn-everything.
- At most 2 equations on screen. Fade out or morph old ones before adding new ones.
- Keep text in its region; the layout report flags overlapping text (`overlap`), text cut by the
  frame edge, also while zoomed (`clipped`), text entirely off screen (`offscreen`), and text
  below size 22 (`too_small`).
- Symbols keep their storyboard color everywhere, including labels on diagrams (`color_of`).
- Semantic colors mean symbols. Never use one for something unrelated to its symbol (a limit line
  for the sum S takes S's color, not an unused one). Emphasis on non-symbols uses `ACCENT`.
- Start a lone opening equation at the center; move it when a second one arrives.
- Layering: things added later draw on top. Add fills and backgrounds before the numbers or labels
  that sit on them (or `self.bring_to_front(labels)`).
- End scenes on the payoff, large and emphasized (`scale(1.5)`, `SurroundingRectangle(..., color=ACCENT)`).
- Leave breathing room: nothing within 0.45 units of the frame edge unless it is a background.
- Numbers on screen should be real values from the worked example, computed in Python, not typed.

## Camera zooms

Zooms are the best way to show something too small to see, and the easiest way to make a mess.
- Fade labels and text out before zooming in and back in after (`self.camera.frame.save_state()`,
  zoom, then `Restore(self.camera.frame)`): at 0.2x a normal label fills the frame and gets cut off.
- Zoom scale 0.2 to 0.4. Scale dots by the same factor during the zoom so they keep their size.
- Anything you add while zoomed must be scaled by the zoom factor (`T(...).scale(zoom)`,
  tick lengths `0.4 * zoom`), and removed before zooming back out.

## Manim notes that save time

- `M()` parts: `eq.submobjects` are the parts in order; `eq.get_part_by_tex("=")` works.
- `TransformMatchingTex(a, b)` matches parts with identical tex; wrap matching terms in `{{ }}`.
- `always_redraw(lambda: ...)` for objects that follow a ValueTracker; add them with `self.add`.
- `DashedLine`, `Brace(mob, DOWN)`, `SurroundingRectangle(mob, color=AMBER, buff=0.1)`,
  `Arrow(start, end, buff=0)`, `Circumscribe`, `Indicate`, `LaggedStart(*anims, lag_ratio=0.3)`.
- Axes labels: `ax.get_x_axis_label(M("n"))`, or position `M("n").next_to(ax.x_axis, RIGHT)`.
- A render failure prints the last 40 lines of the traceback; the line in your scene file is there.
