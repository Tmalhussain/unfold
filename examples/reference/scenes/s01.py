from unfold.style import *


class S01(UnfoldScene):
    scene_id = "s01"

    def construct(self):
        unit = 5.5  # scene units per unit of length; the bar has length 2
        bar = Rectangle(width=2 * unit, height=0.7, stroke_color=MUTED, stroke_width=2).move_to(UP * 0.2)
        # 0 and 2 sit at the ends of the bar, so nothing below it competes with the inset later.
        zero = M("0", color=MUTED, font_size=34).next_to(bar, LEFT, buff=0.25)
        two = M("2", color=MUTED, font_size=34).next_to(bar, RIGHT, buff=0.25)
        shades = [tint(SKY, 0.9), tint(SKY, 0.6)]  # the filled bar is the running total
        main = VGroup(bar, zero, two)

        def piece(start, length, k):
            rect = Rectangle(width=length * unit, height=0.7, stroke_width=0,
                             fill_color=shades[k % 2], fill_opacity=1)
            rect.move_to(bar.get_left() + RIGHT * (start + length / 2) * unit)
            main.add(rect)
            return rect

        def label(rect, tex):
            # every label centered on one line above the bar
            lab = M(tex, font_size=30).move_to([rect.get_x(), bar.get_top()[1] + 0.5, 0])
            main.add(lab)
            return lab

        with self.beat("b1"):
            self.play(Create(bar), FadeIn(zero), FadeIn(two), run_time=self.share(0.4))
            first = piece(0, 1, 0)
            self.play(GrowFromEdge(first, LEFT), FadeIn(label(first, "1"), shift=DOWN * 0.1),
                      run_time=self.share(0.5))

        pieces = [(0.0, 1.0)]
        start, length, k = 1.0, 0.5, 1
        with self.beat("b2"):
            anims = []
            while k <= 5:
                rect = piece(start, length, k)
                group = [GrowFromEdge(rect, LEFT)]
                if k <= 4:
                    group.append(FadeIn(label(rect, rf"\frac{{1}}{{{2 ** k}}}"), shift=DOWN * 0.1))
                anims.append(AnimationGroup(*group))
                pieces.append((start, length))
                start, length, k = start + length, length / 2, k + 1
            self.play(LaggedStart(*anims, lag_ratio=0.55), run_time=self.share(0.95))

        # b3: a magnified view of the right end. After each new piece it zooms in 2x,
        # so the gap is the same size on screen every time: the picture repeats forever.
        # The window always spans exactly the gap, the last piece and the one before it (1:1:2).
        lift = 1.55
        mag = 16  # how much the inset magnifies the main bar
        scale = ValueTracker(mag * unit)
        window = 4 * (2 - start) * scale.get_value()
        panel = RoundedRectangle(width=window + 1.5, height=2.4, corner_radius=0.12, fill_color=PANEL,
                                 fill_opacity=1, stroke_color=ACCENT, stroke_width=2).move_to(DOWN * 1.4)
        left_edge = panel.get_left()[0] + 0.45
        right = left_edge + window
        y_mid = panel.get_center()[1] - 0.15
        fill = ValueTracker(start)
        done = list(pieces)

        def sx(v):
            return right - (2 - v) * scale.get_value()

        def strip(a, b, color):
            x0, x1 = max(sx(a), left_edge), min(sx(b), right)
            if x1 - x0 < 0.02:
                return VMobject()
            return Rectangle(width=x1 - x0, height=0.7, stroke_width=0, fill_color=color,
                             fill_opacity=1).move_to([(x0 + x1) / 2, y_mid, 0])

        def inset():
            g = VGroup(*[strip(s, s + ln, shades[i % 2]) for i, (s, ln) in enumerate(done)])
            last = done[-1][0] + done[-1][1]
            g.add(strip(last, fill.get_value(), shades[len(done) % 2]))
            top, bot = y_mid + 0.35, y_mid - 0.35
            g.add(VGroup(Line([left_edge, top, 0], [sx(2), top, 0]), Line([left_edge, bot, 0], [sx(2), bot, 0]),
                         Line([sx(2), top, 0], [sx(2), bot, 0])).set_stroke(MUTED, 2))
            f, gap = fill.get_value(), 2 - fill.get_value()
            arrow = DoubleArrow([sx(f), top + 0.3, 0], [sx(2), top + 0.3, 0], buff=0,
                                color=ACCENT, stroke_width=3, tip_length=0.16, max_tip_length_to_length_ratio=0.2)
            # labels are built once and only moved here: rebuilding text every frame is slow
            g.add(arrow, gap_word.copy().next_to(arrow, UP, buff=0.08))
            g.add(end_two.copy().next_to([sx(2), y_mid, 0], RIGHT, buff=0.25))
            return g

        gap_word = T("gap", size=26, color=ACCENT)
        end_two = M("2", color=MUTED, font_size=34)
        readout = [M(rf"\times {mag * 2 ** i}", color=INK, font_size=30)
                   .move_to([panel.get_left()[0] + 0.55, panel.get_top()[1] - 0.35, 0]) for i in range(3)]
        view = always_redraw(inset)

        def source_box():
            # the region of the main bar the inset shows; it shrinks as the inset zooms in
            w = window / scale.get_value() * unit
            return Rectangle(width=w, height=0.8, color=ACCENT, stroke_width=2).move_to(bar.get_right(),
                                                                                      aligned_edge=RIGHT)

        src = always_redraw(source_box)
        leaders = always_redraw(lambda: VGroup(
            Line(src.get_corner(DL), panel.get_corner(UL)), Line(src.get_corner(DR), panel.get_corner(UR)),
        ).set_stroke(ACCENT, 1.5, opacity=0.5))

        with self.beat("b3"):
            self.play(main.animate.shift(UP * lift), run_time=self.share(0.1))
            labels_only = VGroup(*[m for m in main if isinstance(m, MathTex) and m is not zero and m is not two])
            self.play(FadeIn(src), FadeIn(leaders), FadeIn(panel), FadeIn(view), FadeIn(readout[0]),
                      labels_only.animate.set_opacity(0.45), run_time=self.share(0.15))
            for i in range(2):
                gap = 2 - fill.get_value()
                new = piece(2 - gap, gap / 2, k)
                k += 1
                self.play(fill.animate.set_value(fill.get_value() + gap / 2), GrowFromEdge(new, LEFT),
                          run_time=self.share(0.13))
                done.append((2 - gap, gap / 2))
                self.play(scale.animate.set_value(scale.get_value() * 2), Transform(readout[0], readout[i + 1]),
                          run_time=self.share(0.13))
            end_two.set_color(ACCENT)  # the inset's 2 is the same point as the main bar's 2
            note = caption("each piece fills half the gap", color=INK)
            self.play(Indicate(two, color=ACCENT, scale_factor=1.6), run_time=self.share(0.06))
            self.play(FadeIn(note, shift=UP * 0.1), two.animate.set_color(ACCENT).scale(1.15),
                      run_time=self.share(0.08))
