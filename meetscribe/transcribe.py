"""Local speech-to-text.

Everything runs on-device: audio is decoded and mixed with numpy, then
transcribed with mlx-whisper (Apple Silicon, if installed) or faster-whisper.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .config import Config

SAMPLE_RATE = 16000


@dataclass
class Segment:
    start: float
    end: float
    text: str


def _decode(path: Path) -> np.ndarray:
    """Decode any audio file to 16 kHz mono float32 (uses faster-whisper's PyAV)."""
    from faster_whisper.audio import decode_audio

    return np.asarray(decode_audio(str(path), sampling_rate=SAMPLE_RATE), dtype=np.float32)


def load_session_audio(session_dir_or_file: Path) -> np.ndarray:
    """Load audio for a session directory (mix system + mic) or a single file."""
    p = Path(session_dir_or_file)
    if p.is_file():
        return _decode(p)

    tracks = [p / "system.wav", p / "mic.wav"]
    arrays = [_decode(t) for t in tracks if t.exists()]
    if not arrays:
        raise FileNotFoundError(f"No audio found in {p} (expected system.wav / mic.wav)")
    if len(arrays) == 1:
        return arrays[0]

    length = max(a.shape[0] for a in arrays)
    mixed = np.zeros(length, dtype=np.float32)
    for a in arrays:
        mixed[: a.shape[0]] += a
    return np.clip(mixed, -1.0, 1.0)


def _pick_backend(config: Config) -> str:
    backend = config.transcription_backend
    if backend == "auto":
        try:
            import mlx_whisper  # noqa: F401

            return "mlx"
        except ImportError:
            return "faster-whisper"
    return backend


def transcribe(audio: np.ndarray, config: Config) -> list[Segment]:
    backend = _pick_backend(config)
    model = config.transcription_model
    language = config.transcription_language

    if backend == "mlx":
        import mlx_whisper

        repo = f"mlx-community/whisper-{model}-mlx"
        result = mlx_whisper.transcribe(
            audio, path_or_hf_repo=repo, language=language, verbose=None
        )
        return [
            Segment(start=float(s["start"]), end=float(s["end"]), text=s["text"].strip())
            for s in result.get("segments", [])
            if s.get("text", "").strip()
        ]

    if backend == "faster-whisper":
        from faster_whisper import WhisperModel

        wm = WhisperModel(model, device="cpu", compute_type="int8")
        segments, _info = wm.transcribe(audio, language=language, vad_filter=True)
        return [
            Segment(start=float(s.start), end=float(s.end), text=s.text.strip())
            for s in segments
            if s.text.strip()
        ]

    raise ValueError(f"Unknown transcription backend: {backend}")


def format_transcript(segments: list[Segment]) -> str:
    """Render segments as `[MM:SS] text` lines."""
    lines = []
    for seg in segments:
        m, s = divmod(int(seg.start), 60)
        h, m = divmod(m, 60)
        stamp = f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
        lines.append(f"[{stamp}] {seg.text}")
    return "\n".join(lines)
