from unfold.style import *

TERMS = (r"\frac{1}{2}", r"\frac{1}{4}", r"\frac{1}{8}", r"\cdots")


class S02(UnfoldScene):
    scene_id = "s02"

    def construct(self):
        top = M(r"S = {{ 1 }} + {{ \frac{1}{2} }} + {{ \frac{1}{4} }} + {{ \frac{1}{8} }} + {{ \cdots }}",
                font_size=56)
        place(top, STAGE)

        with self.beat("b1"):
            self.play(Build(top, lag=0.35), run_time=self.share(0.85))

        half = M(r"\frac{1}{2}\, S = {{ \frac{1}{2} }} + {{ \frac{1}{4} }} + {{ \frac{1}{8} }} + {{ \cdots }}",
                 font_size=56)

        with self.beat("b2"):
            self.play(top.animate.shift(UP * 0.9), run_time=self.share(0.2))
            # Stack the halved sum so each term sits under the same term above it: the tails line up.
            half.next_to(top, DOWN, buff=0.7)
            align_at(half, top, r"\frac{1}{2}")
            self.play(TransformMatchingTex(top.copy(), half, path_arc=-0.4), run_time=self.share(0.6))

        with self.beat("b3"):
            # A written subtraction: the minus sits in a gutter left of both lines, the rule spans both.
            rows = VGroup(top, half)
            minus = M("-", font_size=64).move_to([rows.get_left()[0] - 0.4, half.get_y(), 0])
            block = VGroup(rows, minus)
            rule = Line([block.get_left()[0] - 0.2, block.get_bottom()[1] - 0.3, 0],
                        [block.get_right()[0] + 0.2, block.get_bottom()[1] - 0.3, 0], color=MUTED, stroke_width=2)
            self.play(FadeIn(minus), Create(rule), run_time=self.share(0.12))
            # Each term cancels the one under it (with the + in front of it); the 1 has no partner.
            pairs = [VGroup(terms(top, t), terms(half, t)) for t in TERMS]
            plus = VGroup(terms(top, "+"), terms(half, "+"))
            self.play(plus.animate.set_opacity(0.35),
                      LaggedStart(*[p.animate.set_opacity(0.35) for p in pairs], lag_ratio=0.35),
                      run_time=self.share(0.25))
            mark = SurroundingRectangle(terms(top, "1"), color=ACCENT, buff=0.2, corner_radius=0.08, stroke_width=3)
            self.play(Create(mark), run_time=self.share(0.12))
            # What survives is written under the rule.
            gone = VGroup(*pairs, plus)
            rest = VGroup(*[p for eq in rows for p in eq.submobjects if not any(p in g.get_family() for g in gone)])
            diff = M(r"S - \frac{1}{2} S = 1", font_size=56).next_to(rule, DOWN, buff=0.35)
            self.play(TransformMatchingShapes(rest.copy(), diff), rest.animate.set_opacity(0.3),
                      minus.animate.set_opacity(0.3), rule.animate.set_opacity(0.3), run_time=self.share(0.3))

        with self.beat("b4"):
            self.play(FadeOut(VGroup(rows, minus, rule, mark)), diff.animate.move_to(STAGE.center),
                      run_time=self.share(0.2))
            half_s = M(r"\frac{1}{2} S = 1", font_size=56).scale(1.2).move_to(STAGE.center)
            self.play(TransformMatchingShapes(diff, half_s), run_time=self.share(0.25))
            result = M(r"S = 2", font_size=56).scale(2).move_to(STAGE.center)
            box = SurroundingRectangle(result, color=ACCENT, buff=0.3, corner_radius=0.1)
            self.play(TransformMatchingShapes(half_s, result), run_time=self.share(0.25))
            self.play(Create(box), run_time=self.share(0.15))
