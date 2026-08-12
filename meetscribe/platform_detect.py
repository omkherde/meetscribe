"""Best-effort detection of which meeting app is in use.

Because meetscribe records system audio, it works with any platform; this is
purely metadata for the meeting note.

Heuristic order:
1. The frontmost app, if it's a known meeting app — when you start recording,
   the meeting you're in is usually the window in front.
2. Otherwise, scan running processes — apps that only run while in use
   (FaceTime) rank above apps that idle in the background (Zoom, Teams,
   Slack, Discord), which rank above browsers.
"""

from __future__ import annotations

import re
import subprocess

# (process/app-name needle, human label). Order matters for the process scan:
# most-specific and least-likely-to-lurk first, browsers last.
_KNOWN_APPS = [
    ("FaceTime", "FaceTime"),
    ("zoom.us", "Zoom"),
    ("Microsoft Teams", "Microsoft Teams"),
    ("MSTeams", "Microsoft Teams"),
    ("Webex", "Webex"),
    ("Slack", "Slack"),
    ("Discord", "Discord"),
    ("Around", "Around"),
    ("Gather", "Gather"),
    ("Google Chrome", "Browser (Meet/other)"),
    ("Arc", "Browser (Meet/other)"),
    ("Safari", "Browser (Meet/other)"),
    ("firefox", "Browser (Meet/other)"),
    ("Microsoft Edge", "Browser (Meet/other)"),
]


def _match(name: str) -> str | None:
    for needle, label in _KNOWN_APPS:
        if needle.lower() in name.lower():
            return label
    return None


def _frontmost_app() -> str | None:
    """Name of the frontmost app via lsappinfo, or None."""
    try:
        asn = subprocess.run(
            ["lsappinfo", "front"], capture_output=True, text=True, timeout=5
        ).stdout.strip()
        if not asn:
            return None
        info = subprocess.run(
            ["lsappinfo", "info", "-only", "name", asn],
            capture_output=True, text=True, timeout=5,
        ).stdout
        m = re.search(r'"?LSDisplayName"?\s*=\s*"([^"]+)"', info)
        return m.group(1) if m else None
    except Exception:
        return None


def detect_platform() -> str | None:
    """Return a human-readable guess at the meeting platform, or None."""
    front = _frontmost_app()
    if front:
        label = _match(front)
        if label:
            return label

    try:
        out = subprocess.run(
            ["ps", "-axo", "%cpu=,comm="], capture_output=True, text=True, timeout=10
        ).stdout
    except Exception:
        return None

    # Max CPU per candidate app across its processes.
    busiest: dict[str, float] = {}
    for line in out.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) != 2:
            continue
        cpu_str, comm = parts
        try:
            cpu = float(cpu_str)
        except ValueError:
            continue
        label = _match(comm)
        if label:
            busiest[label] = max(busiest.get(label, 0.0), cpu)

    if not busiest:
        return None

    # An app actively in a call burns real CPU (audio/video pipelines); apps
    # that merely auto-start at login (Teams, Zoom, Slack) idle near zero.
    # Prefer the busiest candidate when one is clearly active — this is what
    # lets a Meet call inside a browser beat an idle Teams in the background.
    label, cpu = max(busiest.items(), key=lambda kv: kv[1])
    if cpu >= 10.0:
        return label

    # Nothing clearly active: fall back to specificity order.
    for _needle, lab in _KNOWN_APPS:
        if lab in busiest:
            return lab
    return None
