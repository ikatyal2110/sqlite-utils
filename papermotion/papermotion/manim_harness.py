"""Manim render harness for the animation stage.

Responsibilities:
  * CODE_RULES — the system prompt that constrains LLM-generated Manim code so
    it renders in *this* environment (no LaTeX, no external files, fixed palette
    and class name).
  * render_scene_code() — write code to a temp module, invoke the `manim` CLI,
    and lift the resulting mp4 out of manim's nested media dir.
  * fallback_scene_code() — a deterministic kinetic-typography scene built from
    the Scene's own text. It uses only Text + basic mobjects, so it *always*
    renders; it is the safety net when codegen keeps failing.

No LaTeX is installed, so nothing here (or anything the LLM produces) may use
Tex / MathTex / SVGMobject / ImageMobject / external assets.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .models import Scene

# ---------------------------------------------------------------------------
# Shared visual language

BACKGROUND = "#0e1117"  # 16:9 dark background, applied via config by us

# 5-colour palette the LLM is required to draw from (plus BACKGROUND).
PALETTE = {
    "PM_TEXT": "#e6edf3",   # near-white, for text
    "PM_BLUE": "#4c8bf5",   # primary accent
    "PM_TEAL": "#2dd4bf",   # secondary accent
    "PM_AMBER": "#f5a623",  # highlight / emphasis
    "PM_RED": "#f45b69",    # contrast / "before" / negative
}

# Quality alias -> (manim flag, resolution-dir substring) . We glob for the mp4
# so the substring is only a sanity hint, not load-bearing.
_QUALITY = {
    "l": ("-ql", "480p15"),
    "m": ("-qm", "720p30"),
    "h": ("-qh", "1080p60"),
}

# Tokens generated code must never contain (also enforced in animate.py).
FORBIDDEN_TOKENS = (
    "MathTex", "Tex(", "SVGMobject", "ImageMobject", "open(",
    "requests", "urllib", "subprocess", "os.system", "eval(", "exec(",
    "Code(", "__import__",
)

_PALETTE_BLOCK = "\n".join(f"    {k} = \"{v}\"" for k, v in PALETTE.items())

CODE_RULES = f"""You write Manim Community v0.20 Python code that renders ONE scene of an \
explainer video. Output ONLY a single ```python code block, nothing else.

HARD REQUIREMENTS (violating any of these makes the code unusable):
1. Start with exactly `from manim import *`.
2. Define exactly one Scene subclass named `PMScene` with a `construct(self)` method.
3. NO LaTeX and NO external assets. This environment has no LaTeX and no files.
   FORBIDDEN: Tex, MathTex, SVGMobject, ImageMobject, Code, open(), requests,
   urllib, subprocess, os.system, eval, exec, __import__, reading/writing files,
   or any network access. Use ONLY Text(...) and MarkupText(...) for all text,
   including equations (write "a^2 + b^2 = c^2" as plain Text).
4. Do NOT set config.background_color or the frame size — the harness does that.
5. Use ONLY these colours (define them at the top of construct or use literals):
{_PALETTE_BLOCK}
   Background is {BACKGROUND} (dark). All text must use PM_TEXT or an accent so
   it is readable on the dark background.

LAYOUT (the frame is 14.22 x 8.0 Manim units, 16:9):
* Everything must stay on screen. After creating a text/group, constrain size:
  `label.scale_to_fit_width(min(label.width, 6))` for body text,
  and keep a title near the top with `.to_edge(UP)`.
* Never let two mobjects overlap unless intentional. Use .arrange(), .next_to(),
  .to_edge(), .shift() to place things. Prefer VGroup(...).arrange(DOWN/RIGHT).
* Font sizes: titles ~40, body ~28-32, small labels ~22.

MOTION (this is an *animation*, not a slide — make things move meaningfully):
* Reveal with Create/Write/FadeIn/GrowFromCenter/GrowArrow; stagger with
  lag_ratio or successive self.play calls so ideas build up.
* Show process/data-flow with Arrow/Line + Create, or a Dot moving along a path
  via MoveAlongPath. Show change with Transform/ReplacementTransform. Show
  quantities with growing Rectangle bars, a Circle/Sector, or an animated
  DecimalNumber counter (use ValueTracker + always_redraw / add_updater).
* Build a concrete visual metaphor for the scene's description — boxes+arrows
  for a pipeline, bars for a comparison, a morph for a transformation, etc.

TIMING (very important):
* The scene must last about TARGET_SECONDS seconds. Budget the sum of every
  self.play(run_time=...) plus every self.wait(...) to add up to ~TARGET_SECONDS.
  Use explicit run_time= on plays and self.wait() to pad. End the scene with a
  short self.wait so the final frame holds.

Return ONLY the code block."""


def build_user_prompt(scene: Scene) -> str:
    """Turn a Scene into the user message for the codegen LLM call."""
    vs = scene.visual_spec or {}
    desc = str(vs.get("description", "")).strip()
    style = str(vs.get("style", "")).strip()
    elements = vs.get("elements") or []
    lines = [
        f"Scene {scene.id}: {scene.title}",
        f"TARGET_SECONDS = {scene.duration_hint:.0f}",
        "",
        "NARRATION (what the voiceover says over this scene — the animation must "
        "visually match it):",
        scene.narration.strip(),
        "",
        "VISUAL SPEC:",
        f"  description: {desc}" if desc else "  description: (none given)",
    ]
    if style:
        lines.append(f"  style: {style}")
    if elements:
        lines.append("  elements to include:")
        lines += [f"    - {e}" for e in elements]
    lines += [
        "",
        f"Write the PMScene so it runs ~{scene.duration_hint:.0f}s and animates "
        "the idea above. Remember: Text/MarkupText only, no LaTeX, fixed palette, "
        "keep everything inside the frame.",
    ]
    return "\n".join(lines)


def build_fix_prompt(code: str, stderr_tail: str) -> str:
    """User message asking the LLM to repair code that failed to render."""
    return (
        "Your Manim code FAILED to render. Fix it and return the COMPLETE "
        "corrected file as one ```python block. Keep the same class name PMScene, "
        "Text/MarkupText only (no LaTeX/Tex/MathTex), the fixed palette, and keep "
        "everything on screen.\n\n"
        "The error (tail of manim's output):\n"
        f"```\n{stderr_tail[-2500:]}\n```\n\n"
        "The code that failed:\n"
        f"```python\n{code}\n```"
    )


# ---------------------------------------------------------------------------
# Rendering


def render_scene_code(code: str, out_mp4: Path, quality: str = "m",
                      timeout: int = 300) -> tuple[bool, str]:
    """Render Manim `code` (defining PMScene) to `out_mp4`.

    Returns (ok, stderr_tail). On success the rendered mp4 is moved to out_mp4.
    """
    flag, _res = _QUALITY.get(quality, _QUALITY["m"])
    out_mp4.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="pm_render_") as td:
        tdp = Path(td)
        module = tdp / "pm_scene.py"
        # Prepend a fixed preamble so config is always right regardless of code.
        # Force our dark 16:9 background regardless of what the code does.
        preamble = (
            "from manim import config as _pm_config\n"
            f"_pm_config.background_color = \"{BACKGROUND}\"\n"
        )
        module.write_text(preamble + "\n" + code)
        media = tdp / "media"
        cmd = [
            "manim", flag, "--disable_caching", "--media_dir", str(media),
            str(module), "PMScene",
        ]
        try:
            proc = subprocess.run(
                cmd, cwd=td, capture_output=True, text=True, timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return False, f"manim timed out after {timeout}s"

        output = (proc.stdout or "") + "\n" + (proc.stderr or "")
        tail = output.strip()[-3000:]

        if proc.returncode != 0:
            return False, tail

        # manim writes to media/videos/<module>/<res>/PMScene.mp4 — glob for it.
        found = sorted(media.rglob("PMScene.mp4"))
        found = [f for f in found if "partial_movie_files" not in f.parts]
        if not found:
            return False, "manim exited 0 but produced no PMScene.mp4\n" + tail
        shutil.move(str(found[0]), str(out_mp4))
        return True, tail


# ---------------------------------------------------------------------------
# Deterministic fallback scene


def _chunk_narration(text: str, lo: int = 3, hi: int = 5) -> list[str]:
    """Split narration into lo..hi short display chunks."""
    text = re.sub(r"\s+", " ", (text or "").strip())
    if not text:
        return ["..."]
    # Sentence-ish split.
    parts = re.split(r"(?<=[.!?;:])\s+", text)
    parts = [p.strip() for p in parts if p.strip()]
    if not parts:
        parts = [text]
    # Break over-long parts on commas / word budget.
    pieces: list[str] = []
    for p in parts:
        if len(p) <= 90:
            pieces.append(p)
            continue
        buf = ""
        for word in p.split(" "):
            if len(buf) + len(word) + 1 > 90 and buf:
                pieces.append(buf.strip())
                buf = word
            else:
                buf = f"{buf} {word}".strip()
        if buf:
            pieces.append(buf.strip())
    # Merge down to <= hi chunks.
    while len(pieces) > hi:
        merged: list[str] = []
        i = 0
        while i < len(pieces):
            if i + 1 < len(pieces) and len(merged) < hi - 1:
                merged.append((pieces[i] + " " + pieces[i + 1]).strip())
                i += 2
            else:
                merged.append(pieces[i])
                i += 1
        if len(merged) == len(pieces):
            break
        pieces = merged
    # Pad up to lo chunks by splitting the longest.
    while len(pieces) < lo and any(len(p) > 30 for p in pieces):
        idx = max(range(len(pieces)), key=lambda i: len(pieces[i]))
        words = pieces[idx].split(" ")
        mid = len(words) // 2
        if mid == 0:
            break
        pieces[idx:idx + 1] = [" ".join(words[:mid]).strip(),
                               " ".join(words[mid:]).strip()]
    return pieces[:hi] or ["..."]


def fallback_scene_code(scene: Scene) -> str:
    """Deterministic kinetic-typography scene — guaranteed to render.

    Title banner + accent underline at the top, then narration chunks fade in
    and out in the centre, timed to ~duration_hint. Uses only Text + Line, so it
    has no LaTeX / asset dependencies.
    """
    duration = max(6.0, float(scene.duration_hint or 20.0))
    title = re.sub(r"\s+", " ", (scene.title or "Scene").strip()) or "Scene"
    chunks = _chunk_narration(scene.narration, lo=3, hi=5)
    n = len(chunks)

    # Timing budget: title intro, then per-chunk (fade in + hold + fade out),
    # plus a small tail hold.
    intro = 1.5
    tail = 1.0
    fade_in, fade_out = 0.5, 0.4
    per_chunk_fixed = fade_in + fade_out
    remaining = max(0.0, duration - intro - tail - n * per_chunk_fixed)
    hold = max(0.8, remaining / n)

    title_lit = json.dumps(title)
    chunks_lit = json.dumps(chunks)

    return f'''from manim import *


class PMScene(Scene):
    def construct(self):
        PM_TEXT = "{PALETTE['PM_TEXT']}"
        PM_BLUE = "{PALETTE['PM_BLUE']}"
        PM_TEAL = "{PALETTE['PM_TEAL']}"
        PM_AMBER = "{PALETTE['PM_AMBER']}"

        title = Text({title_lit}, color=PM_TEXT, weight=BOLD, font_size=42)
        title.scale_to_fit_width(min(title.width, 12))
        title.to_edge(UP, buff=0.7)

        underline = Line(LEFT, RIGHT, color=PM_BLUE, stroke_width=6)
        underline.set_width(title.width * 1.02)
        underline.next_to(title, DOWN, buff=0.2)

        self.play(FadeIn(title, shift=DOWN * 0.3), run_time=0.9)
        self.play(GrowFromEdge(underline, LEFT), run_time=0.6)

        chunks = {chunks_lit}
        accents = [PM_TEAL, PM_AMBER, PM_BLUE, PM_TEAL, PM_AMBER]
        for i, phrase in enumerate(chunks):
            body = Text(phrase, color=PM_TEXT, font_size=32)
            body.scale_to_fit_width(min(body.width, 11))
            body.move_to(ORIGIN + DOWN * 0.3)
            bar = Line(LEFT, RIGHT, color=accents[i % len(accents)],
                       stroke_width=5)
            bar.set_width(max(1.0, body.width * 0.5))
            bar.next_to(body, DOWN, buff=0.35)
            self.play(FadeIn(body, shift=UP * 0.25),
                      GrowFromCenter(bar), run_time={fade_in})
            self.wait({hold:.2f})
            self.play(FadeOut(body), FadeOut(bar), run_time={fade_out})

        self.wait({tail})
'''
