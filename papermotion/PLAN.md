# PaperMotion — Plan

## Vision

Turn research papers into **genuinely explanatory animated videos** — not narrated
slideshows. Existing tools (SciSpace, Mootion, generic PDF-to-video) lay a TTS voice
over the paper's own figures. PaperMotion instead generates 3Blue1Brown-style
programmatic animations (Manim) that illustrate the *method and the intuition*,
targeted at "explain it to a smart undergrad".

## Unique value

1. **Real animations, not slides** — every scene is generated Manim code that draws
   diagrams, animates data flow, morphs equations, and visualizes the core idea.
2. **Narrative arc, not summary** — hook → problem → key idea → how it works →
   results → takeaway. Written for comprehension, not compression.
3. **Self-healing codegen** — LLM-generated animation code is rendered in a
   validate/retry loop; scenes that repeatedly fail fall back to a deterministic
   kinetic-typography template so a full video *always* assembles.
4. **Local-first & resumable** — every stage writes a JSON/file intermediate to a
   work dir, so stages can be inspected, edited, and re-run independently.

## Pipeline

```
paper (arXiv id | PDF | text) 
  → ingest.py    → work/paper.json          (title, abstract, sections, figures)
  → script.py    → work/script.json         (scenes: narration + visual spec)   [LLM]
  → animate.py   → work/scenes/scene_XX.mp4 (Manim codegen + render/retry loop) [LLM]
  → tts.py       → work/audio/scene_XX.wav  (piper → espeak fallback; edge-tts when online)
  → assemble.py  → work/final.mp4           (sync durations, mux, concat, subtitles)
```

LLM access is through the `claude` CLI in headless mode (`llm.py`), so the tool
inherits whatever Claude auth the machine has — no API key management.

## Task breakdown (agent assignments)

| # | Task | Owner | Files |
|---|------|-------|-------|
| 1 | Scaffold, data models, LLM adapter, CLI skeleton | lead | `models.py`, `llm.py`, `cli.py` |
| 2 | Ingestion: arXiv fetch, PDF text/figure extraction, plain-text input | sonnet agent | `ingest.py` |
| 3 | Script generation: paper → narrative scenes w/ visual specs | opus agent | `script.py`, `prompts.py` |
| 4 | Animation: scene spec → Manim code → render/validate/retry, fallback scene | opus agent | `animate.py`, `manim_harness.py` |
| 5 | TTS + assembly: voices, duration sync, mux, concat, subtitles | sonnet agent | `tts.py`, `assemble.py` |
| 6 | Integration, E2E demo on a real paper, MVP polish | lead | — |

## Environment constraints (this dev container)

- Outbound net restricted to package registries + GitHub + Anthropic. arXiv and
  cloud TTS unreachable *here* (fine in normal use): demo uses locally-provided
  paper text and offline TTS (piper voice models mirrored on GitHub releases;
  espeak-ng fallback).
- `claude` CLI available at `/opt/node22/bin/claude` — use `-p --model sonnet|opus`.
- manim 0.20.1, ffmpeg, pymupdf installed. No LaTeX: **Manim code must avoid
  `Tex`/`MathTex`** (use `Text`/`MarkupText`) unless LaTeX is detected.

## MVP definition

`python -m papermotion.cli generate <input> -o out.mp4` produces a watchable
2–4 minute narrated animated explainer for a real paper, end to end, with no
manual intervention.
