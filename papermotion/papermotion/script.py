"""Script generation: paper -> narrative-arc VideoScript with visual specs.

This is stage 2 of the pipeline (see PLAN.md). It asks the LLM (via the headless
`claude` CLI in `llm.py`) for a comprehension-first, 3Blue1Brown-style script:
a hook -> problem -> key idea -> mechanism -> results -> caveat -> takeaway arc,
where each scene carries spoken narration plus a concrete, Manim-drawable visual
spec. The parsed JSON is validated; if it is malformed we do exactly one repair
round-trip through the LLM before giving up with LLMError.
"""

from __future__ import annotations

import json
import math
from typing import Any

from . import llm, prompts
from .models import Paper, Scene, VideoScript

# How much of the paper to show the model. Enough for method + results without
# blowing the context or drowning the core idea in appendix noise.
MAX_PAPER_CHARS = 24000

# Roughly one scene per 20 seconds of narration.
SECONDS_PER_SCENE = 20.0

_ALLOWED_STYLES = {"diagram", "chart", "typography", "comparison", "timeline"}

# Narration bounds (in words). The prompt asks for ~45-55; we accept a wider band
# so we don't reject genuinely good scenes, but flag the truly broken ones.
_MIN_WORDS = 18
_MAX_WORDS = 90


def scene_count_for(target_minutes: float) -> int:
    """Number of scenes for a target length (~20s each), clamped to a sane range."""
    n = round(target_minutes * 60.0 / SECONDS_PER_SCENE)
    return max(4, min(12, int(n)))


def write_script(paper: Paper, *, audience: str = "smart undergraduate",
                 target_minutes: float = 3.0, model: str = "sonnet") -> VideoScript:
    """Generate a narrative VideoScript for ``paper`` via the LLM.

    Raises ``llm.LLMError`` if the model cannot produce a valid script even after
    one repair attempt.
    """
    n_scenes = scene_count_for(target_minutes)
    paper_text = paper.full_text(max_chars=MAX_PAPER_CHARS)

    user_prompt = prompts.build_user_prompt(
        paper_text, audience=audience, minutes=target_minutes, scene_count=n_scenes,
    )

    data = llm.complete_json(user_prompt, system=prompts.SCRIPT_SYSTEM, model=model)
    problems = _validate(data, n_scenes)

    if problems:
        # One repair round-trip: hand the model its own reply and the problem list.
        repair_prompt = prompts.build_repair_prompt(
            _dump(data), problems, scene_count=n_scenes,
        )
        data = llm.complete_json(repair_prompt, system=prompts.SCRIPT_SYSTEM,
                                 model=model)
        problems = _validate(data, n_scenes)
        if problems:
            raise llm.LLMError(
                "LLM produced an invalid script after repair: "
                + "; ".join(problems[:8])
            )

    return _to_video_script(data, paper=paper, audience=audience)


# ---------------------------------------------------------------------------
# Validation

def _validate(data: Any, expected_scenes: int) -> list[str]:
    """Return a list of human-readable problems; empty means the script is usable."""
    problems: list[str] = []

    if not isinstance(data, dict):
        return ["top-level JSON is not an object"]
    scenes = data.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        return ["'scenes' must be a non-empty list"]

    # Scene count: advisory, so warn only on a large miss (breaks pacing badly).
    if abs(len(scenes) - expected_scenes) > 2:
        problems.append(
            f"expected about {expected_scenes} scenes, got {len(scenes)}"
        )

    for idx, sc in enumerate(scenes, start=1):
        where = f"scene {idx}"
        if not isinstance(sc, dict):
            problems.append(f"{where}: not an object")
            continue

        sid = sc.get("id")
        if sid != idx:
            problems.append(f"{where}: id should be {idx}, got {sid!r}")

        title = sc.get("title")
        if not isinstance(title, str) or not title.strip():
            problems.append(f"{where}: missing/empty title")

        narration = sc.get("narration")
        if not isinstance(narration, str) or not narration.strip():
            problems.append(f"{where}: missing/empty narration")
        else:
            w = len(narration.split())
            if w < _MIN_WORDS:
                problems.append(f"{where}: narration too short ({w} words)")
            elif w > _MAX_WORDS:
                problems.append(f"{where}: narration too long ({w} words)")
            if _has_forbidden_markup(narration):
                problems.append(f"{where}: narration contains markup/parentheses")

        spec = sc.get("visual_spec")
        if not isinstance(spec, dict):
            problems.append(f"{where}: missing visual_spec object")
            continue
        desc = spec.get("description")
        if not isinstance(desc, str) or len(desc.strip()) < 15:
            problems.append(f"{where}: visual_spec.description missing/too vague")
        style = spec.get("style")
        if style not in _ALLOWED_STYLES:
            problems.append(
                f"{where}: style {style!r} not one of {sorted(_ALLOWED_STYLES)}"
            )
        elements = spec.get("elements")
        if not isinstance(elements, list) or not elements:
            problems.append(f"{where}: visual_spec.elements must be a non-empty list")

    return problems


def _has_forbidden_markup(text: str) -> bool:
    # Read-aloud narration should have no markdown or parenthetical asides.
    if any(tok in text for tok in ("**", "##", "](", "- ")):
        return True
    if "(" in text or ")" in text:
        return True
    return False


# ---------------------------------------------------------------------------
# Construction

def _to_video_script(data: dict, *, paper: Paper, audience: str) -> VideoScript:
    scenes: list[Scene] = []
    for idx, sc in enumerate(data["scenes"], start=1):
        spec = dict(sc.get("visual_spec") or {})
        # Normalize the spec so downstream (animate.py) sees a stable shape.
        spec.setdefault("description", "")
        elements = spec.get("elements")
        spec["elements"] = list(elements) if isinstance(elements, list) else []
        style = spec.get("style")
        spec["style"] = style if style in _ALLOWED_STYLES else "diagram"
        duration = _coerce_float(spec.get("duration_hint"), SECONDS_PER_SCENE)
        spec["duration_hint"] = duration

        scenes.append(Scene(
            id=idx,
            title=str(sc.get("title", "")).strip(),
            narration=str(sc.get("narration", "")).strip(),
            visual_spec=spec,
            duration_hint=duration,
        ))

    return VideoScript(paper_title=paper.title, audience=audience, scenes=scenes)


def _coerce_float(value: Any, default: float) -> float:
    try:
        f = float(value)
        if math.isfinite(f) and f > 0:
            return f
    except (TypeError, ValueError):
        pass
    return default


def _dump(data: Any) -> str:
    try:
        return json.dumps(data, ensure_ascii=False, indent=2)
    except (TypeError, ValueError):
        return str(data)
