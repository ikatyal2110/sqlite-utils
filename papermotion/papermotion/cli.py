"""PaperMotion CLI.

Usage:
    python -m papermotion.cli generate <arxiv-id | pdf-path | txt-path> -o out.mp4
    python -m papermotion.cli ingest <input> --work work/
    python -m papermotion.cli script --work work/
    python -m papermotion.cli animate --work work/
    python -m papermotion.cli voice --work work/
    python -m papermotion.cli assemble --work work/ -o out.mp4

Each stage persists its output under the work dir, so any stage can be re-run
alone. `generate` runs all stages in order, skipping ones whose outputs exist
(use --force to redo everything).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


def _stage_ingest(args) -> None:
    from . import ingest
    paper = ingest.ingest(args.input, work_dir=Path(args.work))
    from .models import save_json
    save_json(paper, Path(args.work) / "paper.json")
    print(f"[ingest] {paper.title!r} -> {args.work}/paper.json "
          f"({len(paper.sections)} sections, {len(paper.figures)} figures)")


def _stage_script(args) -> None:
    from . import script
    from .models import load_paper, save_json
    paper = load_paper(Path(args.work) / "paper.json")
    vs = script.write_script(paper, audience=args.audience,
                             target_minutes=args.minutes, model=args.model)
    save_json(vs, Path(args.work) / "script.json")
    print(f"[script] {len(vs.scenes)} scenes -> {args.work}/script.json")


def _stage_animate(args) -> None:
    from . import animate
    from .models import load_script
    vs = load_script(Path(args.work) / "script.json")
    animate.render_all(vs, Path(args.work), model=args.model,
                       quality=args.quality)


def _stage_voice(args) -> None:
    from . import tts
    from .models import load_script
    vs = load_script(Path(args.work) / "script.json")
    tts.synthesize_all(vs, Path(args.work), voice=args.voice)


def _stage_assemble(args) -> None:
    from . import assemble
    from .models import load_script
    vs = load_script(Path(args.work) / "script.json")
    out = assemble.assemble(vs, Path(args.work), Path(args.output))
    print(f"[assemble] final video -> {out}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="papermotion",
                                 description="Research papers -> animated explainer videos")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p, needs_input=False):
        if needs_input:
            p.add_argument("input", help="arXiv id/URL, PDF path, or .txt/.md path")
        p.add_argument("--work", default="work", help="work directory (default: work/)")
        p.add_argument("--model", default="sonnet", help="LLM model alias")
        p.add_argument("--audience", default="smart undergraduate")
        p.add_argument("--minutes", type=float, default=3.0, help="target video length")
        p.add_argument("--quality", default="m", choices=["l", "m", "h"],
                       help="render quality: l=480p m=720p h=1080p")
        p.add_argument("--voice", default="auto", help="TTS voice (auto|piper|espeak|edge)")
        p.add_argument("-o", "--output", default="paper_video.mp4")
        p.add_argument("--force", action="store_true", help="re-run stages even if outputs exist")

    for name, fn, needs_input in [
        ("ingest", _stage_ingest, True), ("script", _stage_script, False),
        ("animate", _stage_animate, False), ("voice", _stage_voice, False),
        ("assemble", _stage_assemble, False), ("generate", None, True),
    ]:
        p = sub.add_parser(name)
        common(p, needs_input)
        if fn:
            p.set_defaults(fn=fn)

    args = ap.parse_args(argv)
    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)

    if args.cmd != "generate":
        args.fn(args)
        return 0

    # generate = run all stages, skipping completed ones unless --force
    t0 = time.time()
    stages = [
        ("ingest", _stage_ingest, work / "paper.json"),
        ("script", _stage_script, work / "script.json"),
        ("animate", _stage_animate, work / "scenes" / ".done"),
        ("voice", _stage_voice, work / "audio" / ".done"),
        ("assemble", _stage_assemble, None),
    ]
    for name, fn, marker in stages:
        if not args.force and marker is not None and marker.exists():
            print(f"[{name}] cached, skipping (--force to redo)")
            continue
        print(f"=== stage: {name} ===")
        fn(args)
    print(f"Done in {time.time() - t0:.0f}s -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
