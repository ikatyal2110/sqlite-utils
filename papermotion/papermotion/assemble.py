"""Assembly stage: per-scene video + audio -> ``work/final.mp4`` (+ .srt).

For every scene:

1. Probe the rendered scene video (``work/scenes/scene_XX.mp4``) and its
   narration audio (``work/audio/scene_XX.wav``) with ffprobe.
2. Decide a target duration = max(video duration, audio duration + a small
   "breathing room" pad after the narration ends), so a scene never gets cut
   off mid-sentence and never lingers in silence with nothing playing.
3. Mux video + audio into that target duration in one ffmpeg pass:
   - video is scaled/letterboxed/fps-normalized to a common canonical size
     (so concat is safe) and, if it's the shorter stream, extended by
     freezing its last frame (``tpad=stop_mode=clone``).
   - audio is padded with silence (``apad``) if it's the shorter stream.
   - output is hard-trimmed to the target duration and encoded
     ``-c:v libx264 -pix_fmt yuv420p -c:a aac``.
   Missing narration audio (partial pipeline / tts not run yet) is handled
   gracefully: the scene gets a silent audio track for its own duration.
4. All muxed scenes are concatenated (concat demuxer, re-encoded rather than
   stream-copied so scenes muxed at slightly different times/params still
   concatenate cleanly).
5. An .srt is generated from the narration text, timed to the *actual*
   assembled per-scene offsets, and written next to the output video
   (never burned into the video).
"""

from __future__ import annotations

import datetime
import subprocess
from pathlib import Path

import srt

from .models import Scene, VideoScript

BREATHING_ROOM = 0.4  # seconds of silence/hold added after narration ends
DEFAULT_WIDTH = 1280
DEFAULT_HEIGHT = 720
DEFAULT_FPS = 30.0
SAMPLE_RATE = 44100


class AssembleError(RuntimeError):
    pass


def assemble(vs: VideoScript, work: Path, output: Path) -> Path:
    work = Path(work)
    output = Path(output)
    scenes_dir = work / "scenes"
    audio_dir = work / "audio"
    mux_dir = work / "mux"
    mux_dir.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)

    video_paths = {s.id: scenes_dir / f"scene_{s.id:02d}.mp4" for s in vs.scenes}
    missing = [str(p) for p in video_paths.values() if not p.exists()]
    if missing:
        raise AssembleError(
            "Missing rendered scene video(s), run the animate stage first:\n  "
            + "\n  ".join(missing)
        )

    canonical_w, canonical_h, canonical_fps = _canonical_video_spec(list(video_paths.values()))
    print(f"[assemble] canonical spec: {canonical_w}x{canonical_h} @ {canonical_fps:.3f}fps")

    has_audio_dir = audio_dir.is_dir()
    if not has_audio_dir:
        print(f"[assemble] no audio dir at {audio_dir}, assembling with silent scenes")

    timeline: list[tuple[Scene, float, float | None]] = []  # (scene, final_dur, narration_audio_dur)

    for scene in vs.scenes:
        video_path = video_paths[scene.id]
        audio_path = audio_dir / f"scene_{scene.id:02d}.wav" if has_audio_dir else None
        mux_path = mux_dir / f"scene_{scene.id:02d}.mp4"

        vdur = _ffprobe_duration(video_path)
        adur: float | None = None

        if audio_path is not None and audio_path.exists():
            adur = _ffprobe_duration(audio_path)
            final_dur = max(vdur, adur + BREATHING_ROOM)
            _mux_scene_with_audio(
                video_path, audio_path, mux_path,
                vdur=vdur, adur=adur, final_dur=final_dur,
                width=canonical_w, height=canonical_h, fps=canonical_fps,
            )
        else:
            final_dur = vdur
            _mux_scene_silent(
                video_path, mux_path, vdur=vdur, final_dur=final_dur,
                width=canonical_w, height=canonical_h, fps=canonical_fps,
            )
        timeline.append((scene, final_dur, adur))

        audio_display = f"{adur:.2f}s" if adur is not None else "n/a"
        print(f"[assemble] scene_{scene.id:02d}: video={vdur:.2f}s audio={audio_display} "
              f"-> muxed {final_dur:.2f}s")

    _concat_scenes([mux_dir / f"scene_{s.id:02d}.mp4" for s, _, _ in timeline], output)

    srt_path = output.with_suffix(".srt")
    _write_srt(timeline, srt_path)

    print(f"[assemble] final video -> {output}")
    print(f"[assemble] subtitles -> {srt_path}")
    return output


# ---------------------------------------------------------------------------
# ffprobe helpers

def _ffprobe_duration(path: Path) -> float:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not proc.stdout.strip():
        raise AssembleError(f"ffprobe failed on {path}: {proc.stderr[:500]}")
    return float(proc.stdout.strip())


def _ffprobe_video_spec(path: Path) -> tuple[int, int, float] | None:
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate",
        "-of", "csv=p=0",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    try:
        w_str, h_str, fps_str = proc.stdout.strip().split(",")
        num, _, den = fps_str.partition("/")
        fps = float(num) / float(den) if den and float(den) != 0 else float(num)
        return int(w_str), int(h_str), fps
    except (ValueError, ZeroDivisionError):
        return None


def _canonical_video_spec(video_paths: list[Path]) -> tuple[int, int, float]:
    for p in video_paths:
        spec = _ffprobe_video_spec(p)
        if spec:
            return spec
    return DEFAULT_WIDTH, DEFAULT_HEIGHT, DEFAULT_FPS


# ---------------------------------------------------------------------------
# Per-scene muxing

def _video_filter(width: int, height: int, fps: float, tpad_stop: float) -> str:
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,"
        f"setsar=1,"
        f"fps={fps},"
        f"tpad=stop_mode=clone:stop_duration={tpad_stop:.3f}"
    )


def _mux_scene_with_audio(video_path: Path, audio_path: Path, mux_path: Path,
                           *, vdur: float, adur: float, final_dur: float,
                           width: int, height: int, fps: float) -> None:
    tpad_stop = max(0.0, final_dur - vdur)
    apad_dur = max(0.0, final_dur - adur)
    vfilter = _video_filter(width, height, fps, tpad_stop)
    afilter = f"apad=pad_dur={apad_dur:.3f}"
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-filter_complex", f"[0:v]{vfilter}[v];[1:a]{afilter}[a]",
        "-map", "[v]", "-map", "[a]",
        "-t", f"{final_dur:.3f}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", str(SAMPLE_RATE),
        str(mux_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise AssembleError(f"ffmpeg mux failed for {video_path.name}: {proc.stderr[-2000:]}")


def _mux_scene_silent(video_path: Path, mux_path: Path,
                       *, vdur: float, final_dur: float,
                       width: int, height: int, fps: float) -> None:
    vfilter = _video_filter(width, height, fps, max(0.0, final_dur - vdur))
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(video_path),
        "-f", "lavfi", "-i", f"anullsrc=channel_layout=mono:sample_rate={SAMPLE_RATE}",
        "-filter_complex", f"[0:v]{vfilter}[v]",
        "-map", "[v]", "-map", "1:a",
        "-t", f"{final_dur:.3f}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", str(SAMPLE_RATE),
        "-shortest",
        str(mux_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise AssembleError(f"ffmpeg silent mux failed for {video_path.name}: {proc.stderr[-2000:]}")


# ---------------------------------------------------------------------------
# Concat

def _concat_scenes(mux_paths: list[Path], output: Path) -> None:
    missing = [str(p) for p in mux_paths if not p.exists()]
    if missing:
        raise AssembleError("Missing muxed scene(s) for concat:\n  " + "\n  ".join(missing))

    list_path = output.parent / f".{output.stem}_concat_list.txt"
    list_path.write_text(
        "\n".join(f"file '{p.resolve()}'" for p in mux_paths) + "\n"
    )
    try:
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", str(list_path),
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", str(SAMPLE_RATE),
            str(output),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise AssembleError(f"ffmpeg concat failed: {proc.stderr[-2000:]}")
    finally:
        list_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Subtitles

def _write_srt(timeline: list[tuple[Scene, float, float | None]], srt_path: Path) -> None:
    subs = []
    cursor = 0.0
    idx = 1
    for scene, final_dur, narration_dur in timeline:
        text = (scene.narration or "").strip()
        if text:
            dur = narration_dur if narration_dur is not None else final_dur
            dur = min(dur, final_dur)
            subs.append(srt.Subtitle(
                index=idx,
                start=datetime.timedelta(seconds=cursor),
                end=datetime.timedelta(seconds=cursor + dur),
                content=text,
            ))
            idx += 1
        cursor += final_dur
    srt_path.write_text(srt.compose(subs))
