import numpy as np
from manim import *


config.pixel_width = 1920
config.pixel_height = 1080
config.frame_rate = 60

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
        self.reset_camera()
        self.intro()
        self.loss_landscape()
        self.closeness()
        self.engineering_adaptation()
        self.takeaway()

    def reset_camera(self):
        self.set_camera_orientation(phi=0, theta=-90 * DEGREES, gamma=0, zoom=1.0)

    def headline(self, title: str, subtitle: str) -> VGroup:
        title_mob = Text(title, font_size=46, weight=BOLD, color=TEXT)
        subtitle_mob = Text(subtitle, font_size=22, color=MUTED)
        group = VGroup(title_mob, subtitle_mob).arrange(DOWN, buff=0.18)
        group.to_edge(UP, buff=0.38)
        return group

    def pill(self, label: str, color: str, font_size: int = 22) -> VGroup:
        text = Text(label, font_size=font_size, weight=BOLD, color=TEXT)
        box = RoundedRectangle(
            width=max(1.15, text.width + 0.35),
            height=0.45,
            corner_radius=0.12,
            stroke_color=color,
            fill_color=color,
            fill_opacity=0.18,
        )
        text.move_to(box)
        return VGroup(box, text)

    def intro(self):
        heading = self.headline(
            "Nexus",
            "Same pretraining loss. Better downstream generalization.",
        )
        labels = VGroup(
            self.pill("text", BLUE),
            self.pill("math", YELLOW),
            self.pill("code", TEAL),
            self.pill("reasoning", PINK),
        ).arrange(DOWN, buff=0.22).to_edge(LEFT, buff=0.85).shift(DOWN * 0.3)

        llm_box = RoundedRectangle(
            width=1.55,
            height=1.15,
            corner_radius=0.12,
            stroke_color=TEAL,
            fill_color=TEAL,
            fill_opacity=0.08,
        ).move_to(RIGHT * 3.0 + DOWN * 0.15)
        llm_text = Text("LLM", font_size=26, weight=BOLD, color=TEXT).next_to(llm_box, DOWN, buff=0.18)
        dots = VGroup(*[
            Square(0.115, fill_opacity=0.55, fill_color=TEAL, stroke_color=TEAL)
            for _ in range(24)
        ]).arrange_in_grid(rows=4, cols=6, buff=0.11).move_to(llm_box)

        curves = VGroup()
        for index, label in enumerate(labels):
            color = [BLUE, YELLOW, TEAL, PINK][index]
            curve = CubicBezier(
                label.get_right(),
                LEFT * 1.4 + UP * (0.55 - index * 0.25),
                RIGHT * 1.0 + UP * (0.4 - index * 0.2),
                llm_box.get_left(),
            ).set_stroke(color=color, width=2.2)
            dot = Dot(color=color, radius=0.035).move_to(label.get_right())
            curves.add(VGroup(curve, dot))

        self.play(FadeIn(heading, shift=DOWN * 0.2), run_time=0.8)
        self.play(LaggedStartMap(FadeIn, labels, lag_ratio=0.08), run_time=0.8)
        self.play(Create(VGroup(*[item[0] for item in curves])), FadeIn(llm_box), FadeIn(dots), FadeIn(llm_text), run_time=1.2)
        for item in curves:
            self.play(MoveAlongPath(item[1], item[0]), run_time=0.38)
        self.wait(0.7)
        self.play(FadeOut(VGroup(heading, labels, curves, llm_box, dots, llm_text)), run_time=0.7)

    def loss_landscape(self):
        heading = self.headline(
            "Same score, different landing places",
            "Averaging losses can hide whether task valleys agree.",
        )
        labels = VGroup(
            self.pill("average-type", GREEN, font_size=20),
            self.pill("intersection-type", TEAL, font_size=20),
        ).arrange(RIGHT, buff=0.28).to_corner(DL, buff=0.55)
        self.add_fixed_in_frame_mobjects(heading, labels)

        axes = ThreeDAxes(
            x_range=(-3, 3, 1),
            y_range=(-3, 3, 1),
            z_range=(-0.5, 3, 1),
            x_length=5.4,
            y_length=5.4,
            z_length=2.6,
        ).set_opacity(0.35)
        surface_a = Surface(
            lambda u, v: axes.c2p(u, v, 0.14 * ((u + 0.6) ** 2 + (v - 0.4) ** 2)),
            u_range=(-2.2, 2.2),
            v_range=(-2.2, 2.2),
            resolution=(26, 26),
            fill_opacity=0.44,
            checkerboard_colors=[TEAL, BLUE],
        )
        surface_b = Surface(
            lambda u, v: axes.c2p(u, v, 0.16 * ((u - 0.7) ** 2 + (v + 0.45) ** 2) + 0.2),
            u_range=(-2.2, 2.2),
            v_range=(-2.2, 2.2),
            resolution=(26, 26),
            fill_opacity=0.38,
            checkerboard_colors=[PINK, YELLOW],
        )
        group = VGroup(axes, surface_a, surface_b).shift(DOWN * 0.2)

        self.set_camera_orientation(phi=62 * DEGREES, theta=-46 * DEGREES, zoom=0.88)
        self.play(FadeIn(heading), FadeIn(labels), Create(axes), run_time=0.8)
        self.play(FadeIn(surface_a), FadeIn(surface_b), run_time=1.1)
        self.begin_ambient_camera_rotation(rate=0.1)
        self.wait(2.4)
        self.stop_ambient_camera_rotation()
        self.play(FadeOut(group), FadeOut(heading), FadeOut(labels), run_time=0.7)
        self.remove(heading, labels)
        self.reset_camera()

    def closeness(self):
        heading = self.headline(
            "Why closeness matters",
            "Downstream loss grows with distance and curvature.",
        )
        x_axis = Line(LEFT * 3.4, RIGHT * 3.4, color="#263244", stroke_width=2)
        y_axis = Line(DOWN * 1.65, UP * 1.8, color="#263244", stroke_width=2).shift(LEFT * 0.2)
        curve = ParametricFunction(
            lambda t: np.array([t, 0.34 * (t - 0.5) ** 2 - 1.05, 0]),
            t_range=(-2.8, 2.8),
            color=BLUE,
            stroke_width=5,
        )
        point = Dot(color=BLUE).move_to(curve.point_from_proportion(0.58))
        label = Text("best downstream point", font_size=18, color=BLUE).next_to(point, DOWN, buff=0.12)
        group = VGroup(heading, x_axis, y_axis, curve, point, label)

        self.play(FadeIn(heading), Create(x_axis), Create(y_axis), run_time=0.8)
        self.play(Create(curve), FadeIn(point), FadeIn(label), run_time=1.2)
        self.play(point.animate.move_to(curve.point_from_proportion(0.5)), label.animate.next_to(point, DOWN, buff=0.12), run_time=0.8)
        self.wait(0.8)
        self.play(FadeOut(group), run_time=0.7)

    def engineering_adaptation(self):
        heading = self.headline(
            "Engineering adaptation",
            "A temporary inner model turns mini-batch motion into g_hat.",
        )
        steps = VGroup(
            Text("1. clone model", font_size=20, color=MUTED),
            Text("2. NSGD steps on batches", font_size=20, color=MUTED),
            Text("3. displacement -> g_hat", font_size=20, color=MUTED),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.18).move_to(LEFT * 3.0 + DOWN * 0.25)

        model_tag = self.pill("model", BLUE, font_size=16).move_to(RIGHT * 1.55 + DOWN * 0.15)
        llm = RoundedRectangle(width=1.35, height=1.05, corner_radius=0.12, stroke_color=TEAL, fill_opacity=0.06, fill_color=TEAL).move_to(RIGHT * 2.75 + DOWN * 0.15)
        llm_dots = VGroup(*[
            Square(0.1, fill_opacity=0.55, fill_color=TEAL, stroke_color=TEAL)
            for _ in range(20)
        ]).arrange_in_grid(rows=4, cols=5, buff=0.1).move_to(llm)
        llm_text = Text("LLM", font_size=24, weight=BOLD, color=TEXT).next_to(llm, DOWN, buff=0.16)

        clone = RoundedRectangle(width=1.35, height=1.05, corner_radius=0.12, stroke_color=BLUE, fill_opacity=0.05, fill_color=BLUE).move_to(RIGHT * 2.75 + DOWN * 1.65)
        clone_text = Text("clone", font_size=18, color=MUTED).next_to(clone, UP, buff=0.1)
        batches = VGroup(
            self.pill("batch A", BLUE, 15),
            self.pill("batch B", YELLOW, 15),
            self.pill("batch C", PINK, 15),
        ).arrange(DOWN, buff=0.12).move_to(LEFT * 1.0 + DOWN * 1.7)
        arrow_down = Arrow(llm.get_bottom(), clone.get_top(), color=BLUE, buff=0.1)
        arrow_up = Arrow(clone.get_right(), llm.get_right() + UP * 0.05, color=GREEN, buff=0.1)
        ghat = Text("g_hat", font_size=22, color=GREEN).next_to(arrow_up, RIGHT, buff=0.12)

        group = VGroup(heading, steps, model_tag, llm, llm_dots, llm_text, clone, clone_text, batches, arrow_down, arrow_up, ghat)
        self.play(FadeIn(heading), FadeIn(steps), run_time=0.9)
        self.play(FadeIn(model_tag), FadeIn(llm), FadeIn(llm_dots), FadeIn(llm_text), run_time=0.8)
        self.play(Create(arrow_down), FadeIn(clone), FadeIn(clone_text), LaggedStartMap(FadeIn, batches, lag_ratio=0.1), run_time=1.1)
        self.play(Create(arrow_up), FadeIn(ghat), run_time=0.8)
        self.wait(0.9)
        self.play(FadeOut(group), run_time=0.7)

    def takeaway(self):
        heading = self.headline(
            "Optimize agreement, not just the score.",
            "Pretraining loss is a scorecard. Nexus changes the route through the landscape.",
        )
        curve = ParametricFunction(
            lambda t: np.array([t, 0.3 * (t * t) - 1.45, 0]),
            t_range=(-2.0, 2.0),
            color=TEAL,
            stroke_width=8,
        )
        dot = Dot(color=TEAL, radius=0.065).move_to(curve.point_from_proportion(0.5))
        glow = Circle(radius=0.22, color=TEAL, stroke_opacity=0.35).move_to(dot)
        group = VGroup(heading, curve, dot, glow)

        self.play(FadeIn(heading), Create(curve), FadeIn(dot), run_time=1.1)
        self.play(Flash(dot, color=TEAL, flash_radius=0.5), FadeIn(glow), run_time=0.8)
        self.wait(1.1)
        self.play(FadeOut(group), run_time=0.8)
