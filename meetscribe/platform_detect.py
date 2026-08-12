"""Best-effort detection of which meeting app is running.

Because meetscribe records system audio, it works with any platform; this is
purely metadata for the meeting note.
"""

from __future__ import annotations

import subprocess

# Ordered: more specific apps first, browsers last.
_KNOWN_APPS = [
    ("zoom.us", "Zoom"),
    ("Microsoft Teams", "Microsoft Teams"),
    ("MSTeams", "Microsoft Teams"),
    ("Slack", "Slack"),
    ("Discord", "Discord"),
    ("Webex", "Webex"),
    ("FaceTime", "FaceTime"),
    ("Around", "Around"),
    ("Gather", "Gather"),
    ("Google Chrome", "Browser (Meet/other)"),
    ("Arc", "Browser (Meet/other)"),
    ("Safari", "Browser (Meet/other)"),
    ("firefox", "Browser (Meet/other)"),
    ("Microsoft Edge", "Browser (Meet/other)"),
]


def detect_platform() -> str | None:
    """Return a human-readable guess at the meeting platform, or None."""
    try:
        out = subprocess.run(
            ["ps", "-axo", "comm"], capture_output=True, text=True, timeout=10
        ).stdout
    except Exception:
        return None
    for needle, label in _KNOWN_APPS:
        if needle.lower() in out.lower():
            return label
    return None
