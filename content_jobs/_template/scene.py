import numpy as np
from manim import *


TITLE = "{{TITLE}}"
SUBTITLE = "A short visual explanation of {{TOPIC}}."
BACKGROUND = "#070B13"
TEXT = "#F8FAFC"
MUTED = "#A7B0C0"
BLUE = "#60A5FA"
TEAL = "#2DD4BF"
YELLOW = "#FBBF24"
PINK = "#FB7185"
GREEN = "#34D399"


class MainScene(ThreeDScene):
    def construct(self):
        self.camera.background_color = BACKGROUND
        self.intro()
        self.visual_model()
        self.mechanism()
        self.takeaway()

    def headline(self, title: str, subtitle: str) -> VGroup:
        title_mob = Text(title, font_size=44, weight=BOLD, color=TEXT)
        subtitle_mob = Text(subtitle, font_size=22, color=MUTED)
        group = VGroup(title_mob, subtitle_mob).arrange(DOWN, buff=0.18)
        group.to_edge(UP, buff=0.4)
        return group

    def intro(self):
        heading = self.headline(TITLE, SUBTITLE)
        self.play(FadeIn(heading, shift=DOWN * 0.2), run_time=1.0)
        self.wait(0.5)
        self.play(FadeOut(heading), run_time=0.6)

    def visual_model(self):
        heading = self.headline("Mental model", "Show the viewer the shape of the problem first.")
        left_labels = VGroup(
            self.pill("input", BLUE),
            self.pill("signal", YELLOW),
            self.pill("constraint", TEAL),
            self.pill("tradeoff", PINK),
        ).arrange(DOWN, buff=0.22).to_edge(LEFT, buff=0.8)
        model = RoundedRectangle(width=1.8, height=1.25, corner_radius=0.12, color=TEAL)
        model.move_to(RIGHT * 3)
        model_label = Text("model", font_size=22, color=TEXT).next_to(model, DOWN, buff=0.2)
        dots = VGroup(*[
            Square(0.12, fill_opacity=0.65, fill_color=TEAL, stroke_color=TEAL)
            for _ in range(24)
        ]).arrange_in_grid(rows=4, cols=6, buff=0.12).move_to(model)
        arrows = VGroup(*[
            CubicBezier(label.get_right(), ORIGIN + LEFT, ORIGIN + RIGHT, model.get_left())
            .set_stroke(color=label[0].color, width=2)
            for label in left_labels
        ])
        self.play(FadeIn(heading), LaggedStartMap(FadeIn, left_labels, lag_ratio=0.08))
        self.play(Create(arrows), FadeIn(model), FadeIn(dots), FadeIn(model_label), run_time=1.4)
        self.wait(0.8)
        self.play(FadeOut(VGroup(heading, left_labels, arrows, model, dots, model_label)), run_time=0.7)

    def mechanism(self):
        heading = self.headline("Mechanism", "Use motion to reveal what the method changes.")
        axes = ThreeDAxes(
            x_range=(-3, 3, 1),
            y_range=(-3, 3, 1),
            z_range=(-1, 3, 1),
            x_length=5,
            y_length=5,
            z_length=2.5,
        ).set_opacity(0.45)
        surface_a = Surface(
            lambda u, v: axes.c2p(u, v, 0.18 * (u * u + v * v)),
            u_range=(-2.2, 2.2),
            v_range=(-2.2, 2.2),
            resolution=(24, 24),
            fill_opacity=0.42,
            checkerboard_colors=[BLUE, TEAL],
        )
        surface_b = Surface(
            lambda u, v: axes.c2p(u, v, 0.15 * ((u - 0.8) ** 2 + (v + 0.5) ** 2) + 0.35),
            u_range=(-2.2, 2.2),
            v_range=(-2.2, 2.2),
            resolution=(24, 24),
            fill_opacity=0.32,
            checkerboard_colors=[PINK, YELLOW],
        )
        group = VGroup(axes, surface_a, surface_b).move_to(DOWN * 0.3)
        self.set_camera_orientation(phi=62 * DEGREES, theta=-45 * DEGREES, zoom=0.9)
        self.play(FadeIn(heading), Create(axes), FadeIn(surface_a), run_time=1.1)
        self.play(FadeIn(surface_b), run_time=1.0)
        self.begin_ambient_camera_rotation(rate=0.12)
        self.wait(2.0)
        self.stop_ambient_camera_rotation()
        self.move_camera(phi=0, theta=-90 * DEGREES, zoom=1.0, run_time=0.8)
        self.play(FadeOut(VGroup(heading, group)), run_time=0.7)

    def takeaway(self):
        heading = self.headline("Takeaway", "One crisp sentence becomes the clip's memory hook.")
        curve = ParametricFunction(
            lambda t: np.array([t, 0.35 * (t * t) - 1.4, 0]),
            t_range=(-2.2, 2.2),
            color=TEAL,
            stroke_width=8,
        )
        dot = Dot(color=TEAL).move_to(curve.point_from_proportion(0.5))
        self.play(FadeIn(heading), Create(curve), FadeIn(dot), run_time=1.2)
        self.play(Flash(dot, color=TEAL, flash_radius=0.45), run_time=0.7)
        self.wait(1.0)
        self.play(FadeOut(VGroup(heading, curve, dot)), run_time=0.7)

    def pill(self, label: str, color: str) -> VGroup:
        text = Text(label, font_size=22, color=TEXT)
        box = RoundedRectangle(
            width=max(1.1, text.width + 0.35),
            height=0.45,
            corner_radius=0.12,
            stroke_color=color,
            fill_color=color,
            fill_opacity=0.18,
        )
        text.move_to(box)
        return VGroup(box, text)
