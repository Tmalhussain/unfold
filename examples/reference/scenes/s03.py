from unfold.style import *


def total(n):
    return 2 - 1 / 2 ** (n - 1)


class S03(UnfoldScene):
    scene_id = "s03"

    def construct(self):
        ax = styled_axes([0, 8.5, 1], [0, 2.25, 0.5], width=10, height=3.9, labels=False)
        place(ax, Region("plot", (0, 0.65), 11.5, 4.2))
        ax.add_coordinates(range(1, 9), {v: M(t, color=MUTED, font_size=30) for v, t in
                                         ((0.5, "0.5"), (1, "1"), (1.5, "1.5"), (2, "2"))}, font_size=30)
        n_label = M("n").next_to(ax.x_axis, RIGHT, buff=0.2)
        s_label = M("s_n").next_to(ax.y_axis, UP, buff=0.15)
        r = 0.08
        dots = VGroup(*[Dot(ax.c2p(n, total(n)), color=color_of("s_n"), radius=r) for n in range(1, 9)])
        formula = place(M(r"s_n = 2 - \frac{1}{2^{n-1}}"), EQ_BAR)

        with self.beat("b1"):
            self.play(Create(ax), FadeIn(n_label), FadeIn(s_label), run_time=self.share(0.3))
            self.play(LaggedStart(*[GrowFromCenter(d) for d in dots], lag_ratio=0.3), run_time=self.share(0.4))
            self.play(Build(formula), run_time=self.share(0.3))

        # The line at 2 is the value of the whole sum S, so it takes S's color.
        line = DashedLine(ax.c2p(0, 2), ax.c2p(8.5, 2), color=color_of("S"), stroke_width=4,
                          dash_length=0.2, dashed_ratio=0.6)
        line_y = line.get_center()[1]

        def gap_bar(axes, n, radius):
            return Line(axes.c2p(n, total(n)) + UP * radius, axes.c2p(n, 2), color=ROSE, stroke_width=5)

        def tag(bar, tex, size=28):
            # one rule for every gap label: centered on its bar, a fixed distance to the right;
            # a label taller than its bar moves further out so it clears the dot
            t = M(tex, color=ROSE, font_size=size).next_to(bar, RIGHT, buff=0.15)
            if t.height > bar.get_length():
                t.shift(RIGHT * 0.15)
                over = t.get_top()[1] - (bar.get_top()[1] - 0.06)
                t.shift(DOWN * max(0, over))
            return t

        # Only bars longer than a dot are drawn at this scale; the inset shows the rest.
        bars = VGroup(*[gap_bar(ax, n, r) for n in range(1, 5)])
        tags = VGroup(*[tag(bars[i], t) for i, t in enumerate(["1", r"\frac{1}{2}", r"\frac{1}{4}"])])

        with self.beat("b2"):
            self.play(Create(line), run_time=self.share(0.25))
            self.play(LaggedStart(*[Create(b) for b in bars], lag_ratio=0.3), run_time=self.share(0.3))
            self.play(LaggedStart(*[FadeIn(t, shift=LEFT * 0.1) for t in tags], lag_ratio=0.4),
                      run_time=self.share(0.3))

        # A zoomed plot of dots 4 to 6 in the empty lower right, with its own axes so the
        # stretched vertical scale is stated, not hidden. It grows out of the source box.
        src = Rectangle(color=ACCENT, stroke_width=2)
        src.stretch_to_fit_width(ax.c2p(6.4, 0)[0] - ax.c2p(3.6, 0)[0])
        src.stretch_to_fit_height(ax.c2p(0, 2.05)[1] - ax.c2p(0, 1.78)[1]).move_to(ax.c2p(5, 1.915))
        panel_box = Region("inset", ax.c2p(6.25, 0.8), ax.c2p(8.4, 0)[0] - ax.c2p(4.1, 0)[0],
                           ax.c2p(0, 1.5)[1] - ax.c2p(0, 0.1)[1])
        panel = RoundedRectangle(width=panel_box.width, height=panel_box.height, corner_radius=0.1,
                                 fill_color=PANEL, fill_opacity=1, stroke_color=ACCENT, stroke_width=2)
        panel.move_to(panel_box.center)
        zx = Axes(x_range=[3.5, 6.5, 1], y_range=[1.86, 2.02, 0.05], x_length=panel.width - 1.4,
                  y_length=panel.height - 0.95, tips=False,
                  axis_config={"color": MUTED, "stroke_width": 1.5, "include_ticks": False})
        zx.move_to(panel).shift(RIGHT * 0.3 + UP * 0.22)
        zticks = VGroup(*[M(t, color=MUTED, font_size=24).next_to(zx.c2p(3.5, v), LEFT, buff=0.12)
                          for v, t in ((1.9, "1.9"), (2, "2"))])
        zline = DashedLine(zx.c2p(3.5, 2), zx.c2p(6.5, 2), color=color_of("S"), stroke_width=4,
                           dash_length=0.2, dashed_ratio=0.6)
        zdots = VGroup(*[Dot(zx.c2p(n, total(n)), color=color_of("s_n"), radius=r) for n in (4, 5, 6)])
        zbars = VGroup(*[gap_bar(zx, n, r) for n in (4, 5, 6)])
        ztags = VGroup(*[tag(zbars[i], t, 28) for i, t in
                         enumerate([r"\frac{1}{8}", r"\frac{1}{16}", r"\frac{1}{32}"])])
        zn = VGroup(*[M(str(n), color=color_of("n"), font_size=26).next_to(zx.c2p(n, 1.86), DOWN, buff=0.12)
                      for n in (4, 5, 6)])
        leaders = VGroup(Line(src.get_corner(DL), panel.get_corner(UL)), Line(src.get_corner(DR), panel.get_corner(UR)))
        leaders.set_stroke(ACCENT, 1.5, opacity=0.6)

        with self.beat("b3"):
            self.play(Create(src), run_time=self.share(0.1))
            self.play(Create(leaders), ReplacementTransform(src.copy(), panel), run_time=self.share(0.12))
            segment = DashedLine(ax.c2p(3.6, 2), ax.c2p(6.4, 2), color=color_of("S"), stroke_width=4,
                                 dash_length=0.2, dashed_ratio=0.6)
            self.play(ReplacementTransform(segment, zline), TransformFromCopy(VGroup(*dots[3:6]), zdots),
                      FadeIn(zx), FadeIn(zticks), FadeIn(zn), run_time=self.share(0.15))
            self.play(LaggedStart(*[AnimationGroup(Create(b), FadeIn(t)) for b, t in zip(zbars, ztags)],
                                  lag_ratio=0.5), run_time=self.share(0.3))
            note = caption("the gap halves every step")
            self.play(FadeIn(note, shift=UP * 0.1), run_time=self.share(0.12))
