"""Animation stage: scene spec -> Manim code -> rendered mp4.

For each scene we ask the LLM (constrained by manim_harness.CODE_RULES) for a
PMScene, run it through a static safety check, and render it. If the render
fails we feed the code + error back to the LLM to repair (self-healing loop,
bounded attempts). If it still fails, we render a deterministic kinetic-
typography fallback that is guaranteed to work — so a full video always
assembles.

Public entry point: render_all(vs, work, model=..., quality=...).
Outputs: work/scenes/scene_XX.mp4 for every scene, then work/scenes/.done.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from . import llm
from .manim_harness import (
    CODE_RULES,
    FORBIDDEN_TOKENS,
    build_fix_prompt,
    build_user_prompt,
    fallback_scene_code,
    render_scene_code,
)
from .models import Scene, VideoScript

# Max LLM render attempts (initial + repairs) before giving up to the fallback.
MAX_ATTEMPTS = 3


def _log(scene_id: int, msg: str) -> None:
    print(f"[animate][scene {scene_id:02d}] {msg}", flush=True)


def safety_check(code: str) -> tuple[bool, str]:
    """Reject code that uses forbidden constructs (LaTeX, IO, network, eval...).

    Returns (ok, reason). Also requires the PMScene class + manim import so a
    truncated / off-format reply is caught before we bother rendering.
    """
    if "from manim import" not in code:
        return False, "missing `from manim import`"
    if not re.search(r"class\s+PMScene\b", code):
        return False, "missing `class PMScene`"
    for tok in FORBIDDEN_TOKENS:
        if tok in code:
            return False, f"forbidden token {tok!r}"
    return True, "ok"


def probe_duration(path: Path) -> float | None:
    """Return the mp4 duration in seconds via ffprobe, or None on failure."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "json", str(path)],
            capture_output=True, text=True, timeout=30,
        )
        if out.returncode != 0:
            return None
        return float(json.loads(out.stdout)["format"]["duration"])
    except (subprocess.SubprocessError, KeyError, ValueError, json.JSONDecodeError):
        return None


def _generate_code(scene: Scene, model: str) -> str:
    """Initial codegen call."""
    reply = llm.complete(build_user_prompt(scene), system=CODE_RULES, model=model)
    return llm.extract_code(reply, "python")


def _repair_code(code: str, stderr: str, model: str) -> str:
    """Ask the LLM to fix code that failed to render."""
    reply = llm.complete(build_fix_prompt(code, stderr), system=CODE_RULES,
                         model=model)
    return llm.extract_code(reply, "python")


def render_scene(scene: Scene, out_mp4: Path, *, model: str, quality: str) -> None:
    """Render a single scene to out_mp4, self-healing then falling back."""
    code: str | None = None
    last_err = ""

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            if attempt == 1:
                code = _generate_code(scene, model)
            else:
                code = _repair_code(code or "", last_err, model)
        except llm.LLMError as e:
            last_err = f"LLM error: {e}"
            _log(scene.id, f"attempt {attempt}/{MAX_ATTEMPTS}: {last_err}")
            continue

        ok, reason = safety_check(code)
        if not ok:
            last_err = f"safety check rejected code: {reason}"
            _log(scene.id, f"attempt {attempt}/{MAX_ATTEMPTS}: {last_err}")
            continue

        _log(scene.id, f"attempt {attempt}/{MAX_ATTEMPTS}: rendering LLM code...")
        ok, tail = render_scene_code(code, out_mp4, quality)
        if ok:
            _log(scene.id, f"rendered from LLM code on attempt {attempt} "
                           f"(fallback=no)")
            _report_duration(scene, out_mp4)
            return
        last_err = tail
        _log(scene.id, f"attempt {attempt}/{MAX_ATTEMPTS}: render failed: "
                       f"{_err_summary(tail)}")

    # Self-healing exhausted -> deterministic fallback.
    _log(scene.id, f"all {MAX_ATTEMPTS} LLM attempts failed; using fallback scene")
    fb = fallback_scene_code(scene)
    ok, tail = render_scene_code(fb, out_mp4, quality)
    if not ok:
        # Should never happen; surface loudly so the pipeline notices.
        raise RuntimeError(
            f"[scene {scene.id:02d}] FALLBACK render failed too:\n{tail}"
        )
    _log(scene.id, "rendered from FALLBACK template (fallback=yes)")
    _report_duration(scene, out_mp4)


def _report_duration(scene: Scene, out_mp4: Path) -> None:
    dur = probe_duration(out_mp4)
    hint = float(scene.duration_hint or 0)
    if dur is None:
        _log(scene.id, "warning: could not probe output duration")
        return
    size_kb = out_mp4.stat().st_size / 1024
    line = f"output: {dur:.1f}s, {size_kb:.0f} KB (hint {hint:.0f}s)"
    if hint > 0 and abs(dur - hint) / hint > 0.40:
        line += "  [deviates >40% from hint; assembly will handle sync]"
    _log(scene.id, line)


def _err_summary(tail: str) -> str:
    """Pull the most informative one-liner out of a manim traceback tail."""
    lines = [l for l in tail.splitlines() if l.strip()]
    for l in reversed(lines):
        if "Error" in l or "Exception" in l:
            return l.strip()[:200]
    return (lines[-1][:200] if lines else "unknown error")


def render_all(vs: VideoScript, work: Path, *, model: str = "sonnet",
               quality: str = "m") -> None:
    """Render every scene of `vs` to work/scenes/scene_XX.mp4, then touch .done.

    Scenes whose mp4 already exists are skipped (resumable). A .done marker is
    written only after all scenes are present.
    """
    work = Path(work)
    scenes_dir = work / "scenes"
    scenes_dir.mkdir(parents=True, exist_ok=True)

    total = len(vs.scenes)
    for i, scene in enumerate(vs.scenes, 1):
        out_mp4 = scenes_dir / f"scene_{scene.id:02d}.mp4"
        if out_mp4.exists():
            _log(scene.id, f"({i}/{total}) already rendered, skipping")
            continue
        _log(scene.id, f"({i}/{total}) rendering {scene.title!r} "
                       f"(~{scene.duration_hint:.0f}s, q={quality})")
        render_scene(scene, out_mp4, model=model, quality=quality)

    (scenes_dir / ".done").touch()
    print(f"[animate] all {total} scenes present -> {scenes_dir}/.done",
          flush=True)
