"""Text-to-speech stage: scene narration -> ``work/audio/scene_XX.wav``.

Voice backend chain for ``voice="auto"`` (first one that actually works wins,
and is then reused for the rest of the run):

1. **edge-tts** -- Microsoft Edge's cloud neural voices. Best quality, but
   needs to reach Microsoft's speech endpoint. In network-restricted
   containers (like this dev sandbox) that host is unreachable, so this
   backend fails fast and we fall through. The code is kept as-is because it
   works out of the box on a normal internet connection.
2. **piper** -- offline neural TTS (VITS). This is the backend the sandboxed
   demo actually uses. The voice model (.onnx + .onnx.json) is not vendored
   in this repo; it is downloaded once over plain HTTPS from
   ``raw.githubusercontent.com`` (a public, unauthenticated CDN -- reachable
   both in this container and on any normal machine) and cached under
   ``~/.cache/papermotion/voices/``. The specific file used is the small
   test-fixture voice that ships inside the `rhasspy/piper` repo itself
   (``etc/test_voice.onnx``), pinned to a fixed commit so the URL never
   moves. It is a real trained Piper/VITS checkpoint (not a stub), so output
   is natural neural speech rather than robotic formant synthesis.
3. **espeak-ng** -- classic formant synthesizer. Always available once
   ``apt-get install espeak-ng`` has been run; guaranteed last resort so a
   video can always be assembled even with zero network access.

All backends render to a temp file and are then normalized to 44.1kHz
16-bit mono WAV via ffmpeg, so downstream assembly never has to care which
backend produced a given clip.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import urllib.request
import wave
from pathlib import Path

from .models import VideoScript

CACHE_DIR = Path.home() / ".cache" / "papermotion"
VOICES_DIR = CACHE_DIR / "voices"

# rhasspy/piper commit that has the test-fixture voice at etc/test_voice.onnx.
# Pinned so the download URL is stable and reproducible.
_PIPER_COMMIT = "73c04d81d5590ecc46e522de3601ce7fb29fc2be"
_PIPER_RAW_BASE = (
    f"https://raw.githubusercontent.com/rhasspy/piper/{_PIPER_COMMIT}/etc/test_voice"
)
PIPER_ONNX_PATH = VOICES_DIR / "piper_en_test_voice.onnx"
PIPER_JSON_PATH = VOICES_DIR / "piper_en_test_voice.onnx.json"

EDGE_VOICE = "en-US-GuyNeural"

BACKEND_CHAIN = ["edge", "piper", "espeak"]

TARGET_RATE = 44100
TARGET_SAMPLE_FMT = "s16"
TARGET_CHANNELS = 1


class TTSBackendUnavailable(RuntimeError):
    """Raised when a requested (or every auto-chain) TTS backend can't run."""


def synthesize_all(vs: VideoScript, work: Path, *, voice: str = "auto") -> None:
    """Render every scene's narration to ``work/audio/scene_{id:02d}.wav``.

    Existing files are left untouched (resumable). Once all scenes have
    audio, ``work/audio/.done`` is touched so the CLI can skip this stage on
    a later `generate` run.
    """
    work = Path(work)
    audio_dir = work / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    chain = _backend_chain(voice)
    preferred: str | None = None  # backend that has already proven to work
    backends_used: set[str] = set()

    for scene in vs.scenes:
        out_path = audio_dir / f"scene_{scene.id:02d}.wav"
        if out_path.exists():
            print(f"[tts] scene_{scene.id:02d}.wav already exists, skipping")
            continue

        text = (scene.narration or "").strip() or scene.title
        order = chain if preferred is None else (
            [preferred] + [b for b in chain if b != preferred]
        )

        last_err: Exception | None = None
        for backend in order:
            try:
                _synthesize_one(backend, text, out_path)
            except Exception as e:  # noqa: BLE001 - deliberately broad; we fall through
                last_err = e
                print(f"[tts]   backend={backend} failed for scene_{scene.id:02d}: {e}")
                continue
            preferred = backend
            backends_used.add(backend)
            print(f"[tts] scene_{scene.id:02d}.wav <- backend={backend}")
            break
        else:
            raise TTSBackendUnavailable(
                f"all TTS backends {order} failed for scene {scene.id}: {last_err}"
            )

    (audio_dir / ".done").touch()
    print(f"[tts] audio synthesis complete -> {audio_dir} "
          f"(backend(s) used: {sorted(backends_used) or 'none, all cached'})")


# ---------------------------------------------------------------------------
# Backend dispatch

def _backend_chain(voice: str) -> list[str]:
    if voice == "auto":
        return list(BACKEND_CHAIN)
    if voice in BACKEND_CHAIN:
        return [voice]
    raise ValueError(
        f"unknown voice backend {voice!r}, expected 'auto' or one of {BACKEND_CHAIN}"
    )


def _synthesize_one(backend: str, text: str, out_path: Path) -> None:
    """Render `text` with `backend` into a temp file, then normalize to `out_path`."""
    tmp_path = out_path.with_suffix(out_path.suffix + f".{backend}.tmp")
    try:
        if backend == "edge":
            _synth_edge(text, tmp_path)
        elif backend == "piper":
            _synth_piper(text, tmp_path)
        elif backend == "espeak":
            _synth_espeak(text, tmp_path)
        else:
            raise ValueError(f"unknown backend {backend!r}")
        _normalize_wav(tmp_path, out_path)
    finally:
        tmp_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Backend 1: edge-tts (cloud, best quality, needs internet)

def _synth_edge(text: str, tmp_path: Path) -> None:
    try:
        import edge_tts
    except ImportError as e:
        raise TTSBackendUnavailable("edge-tts is not installed") from e

    mp3_path = tmp_path.with_suffix(".mp3")

    async def _run() -> None:
        communicate = edge_tts.Communicate(text, EDGE_VOICE, connect_timeout=8, receive_timeout=20)
        await communicate.save(str(mp3_path))

    try:
        asyncio.run(_run())
    except Exception as e:
        mp3_path.unlink(missing_ok=True)
        raise TTSBackendUnavailable(f"edge-tts request failed (likely no network access "
                                     f"to Microsoft's speech endpoint): {e}") from e

    if not mp3_path.exists() or mp3_path.stat().st_size == 0:
        mp3_path.unlink(missing_ok=True)
        raise TTSBackendUnavailable("edge-tts produced no audio")

    mp3_path.rename(tmp_path)


# ---------------------------------------------------------------------------
# Backend 2: piper (offline neural VITS TTS)

_piper_voice_cache = None  # lazily-loaded piper.PiperVoice, reused across scenes


def _ensure_piper_voice_files() -> None:
    VOICES_DIR.mkdir(parents=True, exist_ok=True)
    for suffix, dest in ((".onnx", PIPER_ONNX_PATH), (".onnx.json", PIPER_JSON_PATH)):
        if dest.exists() and dest.stat().st_size > 0:
            continue
        url = _PIPER_RAW_BASE + suffix
        print(f"[tts]   downloading piper voice: {url} -> {dest}")
        tmp = dest.with_suffix(dest.suffix + ".part")
        try:
            urllib.request.urlretrieve(url, tmp)
        except Exception as e:
            tmp.unlink(missing_ok=True)
            raise TTSBackendUnavailable(f"could not download piper voice model: {e}") from e
        tmp.rename(dest)


def _get_piper_voice():
    global _piper_voice_cache
    if _piper_voice_cache is not None:
        return _piper_voice_cache
    try:
        from piper import PiperVoice
    except ImportError as e:
        raise TTSBackendUnavailable("piper-tts is not installed (pip install piper-tts)") from e

    _ensure_piper_voice_files()
    try:
        _piper_voice_cache = PiperVoice.load(str(PIPER_ONNX_PATH), str(PIPER_JSON_PATH))
    except Exception as e:
        raise TTSBackendUnavailable(f"failed to load piper voice model: {e}") from e
    return _piper_voice_cache


def _synth_piper(text: str, tmp_path: Path) -> None:
    voice = _get_piper_voice()
    try:
        with wave.open(str(tmp_path), "wb") as wf:
            voice.synthesize_wav(text, wf)
    except Exception as e:
        raise TTSBackendUnavailable(f"piper synthesis failed: {e}") from e
    if not tmp_path.exists() or tmp_path.stat().st_size == 0:
        raise TTSBackendUnavailable("piper produced no audio")


# ---------------------------------------------------------------------------
# Backend 3: espeak-ng (guaranteed offline fallback)

def _synth_espeak(text: str, tmp_path: Path) -> None:
    exe = shutil.which("espeak-ng") or shutil.which("espeak")
    if not exe:
        raise TTSBackendUnavailable("espeak-ng is not installed (apt-get install espeak-ng)")
    proc = subprocess.run(
        [exe, "-w", str(tmp_path), text],
        capture_output=True, text=True,
    )
    if proc.returncode != 0 or not tmp_path.exists() or tmp_path.stat().st_size == 0:
        raise TTSBackendUnavailable(f"espeak-ng failed ({proc.returncode}): {proc.stderr[:500]}")


# ---------------------------------------------------------------------------
# Normalization

def _normalize_wav(src: Path, dst: Path) -> None:
    """ffmpeg -> 44.1kHz 16-bit mono PCM WAV, whatever the source format."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(src),
        "-ar", str(TARGET_RATE),
        "-ac", str(TARGET_CHANNELS),
        "-sample_fmt", TARGET_SAMPLE_FMT,
        str(dst),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg normalization failed: {proc.stderr[:1000]}")
