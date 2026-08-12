"""Configuration loading for meetscribe.

Config lives at ~/.meetscribe/config.yaml (created by `meetscribe init`).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

CONFIG_DIR = Path(os.environ.get("MEETSCRIBE_HOME", Path.home() / ".meetscribe"))
CONFIG_PATH = CONFIG_DIR / "config.yaml"

DEFAULT_CONFIG_YAML = """\
# meetscribe configuration

# Your name. Helps the transcriber recognize it when spoken, and lets the
# summarizer attribute action items to "me" correctly.
user_name: null

# Names and terms the transcriber often gets wrong (colleagues, product names,
# jargon). These bias transcription and help the summarizer fix near-misses.
vocabulary: []
#  - Priya Sharma
#  - MeetScribe

# Where your Obsidian vault of meeting notes lives (open this folder in Obsidian).
vault: ~/MeetingVault

# Where raw recordings are stored while (and after) processing.
recordings_dir: ~/.meetscribe/recordings

# Keep the audio files after a meeting has been processed.
keep_audio: true

transcription:
  # auto = use mlx-whisper if installed (fastest on Apple Silicon), else faster-whisper.
  backend: auto            # auto | faster-whisper | mlx
  model: base              # tiny | base | small | medium | large-v3
  language: null           # e.g. "en"; null = auto-detect

summarization:
  # claude = best quality, costs ~$0.02-0.15 per meeting depending on model.
  # ollama = 100% free and local; requires Ollama (https://ollama.com) and a
  #          pulled model, e.g. `ollama pull llama3.1:8b`.
  backend: claude          # claude | ollama
  model: claude-opus-5
  max_tokens: 16000
  ollama_model: llama3.1:8b
  ollama_url: http://localhost:11434
  ollama_num_ctx: 16384    # context window; raise for very long meetings

# The subjects your meetings get filed under. The summarizer picks the best
# match; meetings that fit nothing land in "Inbox". Descriptions help Claude
# classify correctly.
subjects:
  - name: Work
    description: Job, team standups, client calls, projects at work.
  - name: School
    description: Classes, lectures, study groups, coursework.
  - name: College Consulting
    description: College application advising sessions.
  - name: Personal
    description: Everything else - family, friends, appointments.
"""


@dataclass
class Subject:
    name: str
    description: str = ""


@dataclass
class Config:
    vault: Path
    recordings_dir: Path
    keep_audio: bool = True
    transcription_backend: str = "auto"
    transcription_model: str = "base"
    transcription_language: str | None = None
    summarization_backend: str = "claude"
    summarization_model: str = "claude-opus-5"
    summarization_max_tokens: int = 16000
    ollama_model: str = "llama3.1:8b"
    ollama_url: str = "http://localhost:11434"
    ollama_num_ctx: int = 16384
    subjects: list[Subject] = field(default_factory=list)
    user_name: str | None = None
    vocabulary: list[str] = field(default_factory=list)

    @property
    def subject_names(self) -> list[str]:
        return [s.name for s in self.subjects]


def _expand(p: str) -> Path:
    return Path(os.path.expanduser(str(p))).resolve()


def load_config(path: Path | None = None) -> Config:
    path = path or CONFIG_PATH
    if not path.exists():
        raise FileNotFoundError(
            f"No config found at {path}. Run `meetscribe init` first."
        )
    raw = yaml.safe_load(path.read_text()) or {}
    tr = raw.get("transcription") or {}
    sm = raw.get("summarization") or {}
    subjects = [
        Subject(name=str(s.get("name")), description=str(s.get("description") or ""))
        for s in (raw.get("subjects") or [])
        if s.get("name")
    ]
    return Config(
        vault=_expand(raw.get("vault", "~/MeetingVault")),
        recordings_dir=_expand(raw.get("recordings_dir", "~/.meetscribe/recordings")),
        keep_audio=bool(raw.get("keep_audio", True)),
        transcription_backend=str(tr.get("backend", "auto")),
        transcription_model=str(tr.get("model", "base")),
        transcription_language=tr.get("language"),
        summarization_backend=str(sm.get("backend", "claude")),
        summarization_model=str(sm.get("model", "claude-opus-5")),
        summarization_max_tokens=int(sm.get("max_tokens", 16000)),
        ollama_model=str(sm.get("ollama_model", "llama3.1:8b")),
        ollama_url=str(sm.get("ollama_url", "http://localhost:11434")).rstrip("/"),
        ollama_num_ctx=int(sm.get("ollama_num_ctx", 16384)),
        subjects=subjects,
        user_name=(str(raw["user_name"]) if raw.get("user_name") else None),
        vocabulary=[str(v) for v in (raw.get("vocabulary") or [])],
    )


def write_default_config(path: Path | None = None) -> Path:
    path = path or CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(DEFAULT_CONFIG_YAML)
    return path
