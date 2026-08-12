"""Drives the `audiocap` Swift helper to record system audio + microphone."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from .config import CONFIG_DIR, Config
from .platform_detect import detect_platform

REPO_ROOT = Path(__file__).resolve().parent.parent


def find_audiocap() -> Path:
    """Locate the audiocap binary (env var, ~/.meetscribe/bin, or repo build)."""
    candidates = []
    if os.environ.get("MEETSCRIBE_AUDIOCAP"):
        candidates.append(Path(os.environ["MEETSCRIBE_AUDIOCAP"]))
    candidates.append(CONFIG_DIR / "bin" / "audiocap")
    candidates.append(REPO_ROOT / "audio" / ".build" / "release" / "audiocap")
    for c in candidates:
        if c.is_file() and os.access(c, os.X_OK):
            return c
    raise FileNotFoundError(
        "audiocap binary not found. Build it with `make build` (or "
        "`cd audio && swift build -c release`), or set MEETSCRIBE_AUDIOCAP."
    )


def record(config: Config, title: str | None = None) -> Path:
    """Record until Ctrl+C. Returns the session directory containing the WAVs."""
    started = datetime.now()
    session_dir = config.recordings_dir / started.strftime("%Y%m%d-%H%M%S")
    session_dir.mkdir(parents=True, exist_ok=True)

    platform = detect_platform()

    binary = find_audiocap()
    proc = subprocess.Popen(
        [str(binary), str(session_dir)],
        stdout=subprocess.PIPE,
        stderr=sys.stderr,
        text=True,
    )

    # Wait for the READY line so we know capture actually started.
    ready = False
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.strip()
        if line == "READY":
            ready = True
            break
    if not ready:
        proc.wait()
        raise RuntimeError(
            "audiocap exited before recording started. If this is the first "
            "run, grant System Audio Recording and Microphone access to your "
            "terminal in System Settings > Privacy & Security, then retry."
        )

    print(
        f"● Recording ({platform or 'unknown platform'}) — press Ctrl+C here "
        "(or run `meetscribe stop` in another terminal) to stop."
    )
    pidfile = CONFIG_DIR / "recording.pid"
    pidfile.parent.mkdir(parents=True, exist_ok=True)
    pidfile.write_text(str(os.getpid()))

    # Stop cleanly on SIGTERM too (e.g. when driven by another process).
    def _on_sigterm(signum, frame):
        raise KeyboardInterrupt

    previous_handler = signal.signal(signal.SIGTERM, _on_sigterm)
    try:
        while proc.poll() is None:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        signal.signal(signal.SIGTERM, previous_handler)
        pidfile.unlink(missing_ok=True)
        if proc.poll() is None:
            proc.send_signal(signal.SIGINT)
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.terminate()
                proc.wait(timeout=5)

    ended = datetime.now()
    meta = {
        "title": title,
        "platform": platform,
        "started": started.isoformat(timespec="seconds"),
        "ended": ended.isoformat(timespec="seconds"),
        "duration_seconds": int((ended - started).total_seconds()),
    }
    (session_dir / "meta.json").write_text(json.dumps(meta, indent=2))
    print(f"■ Recording stopped ({meta['duration_seconds']}s) → {session_dir}")
    return session_dir


def load_meta(session_dir: Path) -> dict:
    meta_path = session_dir / "meta.json"
    if meta_path.exists():
        return json.loads(meta_path.read_text())
    return {}
