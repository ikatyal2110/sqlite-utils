"""Core data contracts shared by every pipeline stage.

Every stage reads/writes these as JSON files inside a work directory, so stages
are independently runnable, inspectable, and resumable:

    work/paper.json    Paper
    work/script.json   VideoScript
    work/scenes/       scene_XX.py, scene_XX.mp4  (animate stage)
    work/audio/        scene_XX.wav               (tts stage)
    work/final.mp4     assembled video
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Section:
    heading: str
    text: str


@dataclass
class Paper:
    """Normalized representation of an ingested paper."""

    title: str
    authors: list[str] = field(default_factory=list)
    abstract: str = ""
    sections: list[Section] = field(default_factory=list)
    figures: list[str] = field(default_factory=list)  # paths to extracted images
    source: str = ""  # arxiv id, file path, or "text"

    def full_text(self, max_chars: int | None = None) -> str:
        parts = [f"# {self.title}", f"Authors: {', '.join(self.authors)}",
                 f"## Abstract\n{self.abstract}"]
        for s in self.sections:
            parts.append(f"## {s.heading}\n{s.text}")
        text = "\n\n".join(parts)
        return text[:max_chars] if max_chars else text


@dataclass
class Scene:
    """One scene of the video: narration + a spec for the visual."""

    id: int
    title: str
    narration: str  # what the voiceover says during this scene
    visual_spec: dict[str, Any] = field(default_factory=dict)
    # visual_spec keys:
    #   "description": free-text of what should be drawn/animated (required)
    #   "elements": optional list of concrete visual elements to include
    #   "style": optional hints ("diagram", "equation", "chart", "typography")
    duration_hint: float = 20.0  # seconds, advisory


@dataclass
class VideoScript:
    paper_title: str
    audience: str = "smart undergraduate"
    scenes: list[Scene] = field(default_factory=list)


# ---------------------------------------------------------------------------
# JSON (de)serialization helpers

def _to_jsonable(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: _to_jsonable(v) for k, v in dataclasses.asdict(obj).items()}
    return obj


def save_json(obj: Any, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(_to_jsonable(obj), indent=2, ensure_ascii=False))


def load_paper(path: str | Path) -> Paper:
    d = json.loads(Path(path).read_text())
    d["sections"] = [Section(**s) for s in d.get("sections", [])]
    return Paper(**d)


def load_script(path: str | Path) -> VideoScript:
    d = json.loads(Path(path).read_text())
    d["scenes"] = [Scene(**s) for s in d.get("scenes", [])]
    return VideoScript(**d)
