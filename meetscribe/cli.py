"""meetscribe command-line interface."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from . import __version__
from .config import CONFIG_PATH, load_config, write_default_config


def cmd_init(args: argparse.Namespace) -> int:
    path = write_default_config()
    config = load_config()
    from .vault import ensure_vault

    ensure_vault(config)
    print(f"Config:  {path}")
    print(f"Vault:   {config.vault}  (open this folder as a vault in Obsidian)")
    print("Edit the config to set your subjects, then run `meetscribe record`.")
    return 0


def _process_session(session_dir: Path, title: str | None, subject: str | None) -> int:
    config = load_config()
    from .recorder import load_meta
    from .summarize import summarize
    from .transcribe import format_transcript, load_session_audio, transcribe
    from .vault import ensure_vault, write_meeting

    meta = load_meta(session_dir) if session_dir.is_dir() else {}
    if title:
        meta["title"] = title

    print("→ Transcribing locally (this can take a bit on first run while the "
          "Whisper model downloads)...")
    audio = load_session_audio(session_dir)
    if not meta.get("duration_seconds"):
        meta["duration_seconds"] = int(len(audio) / 16000)
    segments = transcribe(audio, config)
    transcript = format_transcript(segments)

    if len(transcript.strip()) < 20:
        print("No meaningful speech detected in this recording; nothing to file.")
        return 1

    # Keep a plain-text copy alongside the audio regardless of what happens next.
    if session_dir.is_dir():
        (session_dir / "transcript.txt").write_text(transcript)

    print("→ Summarizing with Claude...")
    try:
        notes = summarize(transcript, config, meta)
    except TypeError as e:
        if "authentication" in str(e).lower():
            print(
                "error: no Anthropic API credentials found. Set ANTHROPIC_API_KEY "
                "(or run `ant auth login`) and re-run:\n"
                f"  meetscribe process {session_dir}\n"
                f"The transcript was saved to {session_dir / 'transcript.txt'}",
                file=sys.stderr,
            )
            return 1
        raise
    if subject:
        notes.subject = subject

    ensure_vault(config)
    written = write_meeting(config, notes, transcript, meta)

    if not config.keep_audio and session_dir.is_dir():
        for wav in session_dir.glob("*.wav"):
            wav.unlink()

    print(f"✓ Filed under {notes.subject}: {written.note_path}")
    return 0


def cmd_record(args: argparse.Namespace) -> int:
    config = load_config()
    from .recorder import record

    session_dir = record(config, title=args.title)
    if args.no_process:
        print(f"Recording saved. Process it later with: meetscribe process {session_dir}")
        return 0
    return _process_session(session_dir, args.title, args.subject)


def cmd_process(args: argparse.Namespace) -> int:
    path = Path(args.path).expanduser().resolve()
    if not path.exists():
        print(f"error: {path} does not exist", file=sys.stderr)
        return 1
    return _process_session(path, args.title, args.subject)


def cmd_transcribe(args: argparse.Namespace) -> int:
    config = load_config()
    from .transcribe import format_transcript, load_session_audio, transcribe

    path = Path(args.path).expanduser().resolve()
    audio = load_session_audio(path)
    segments = transcribe(audio, config)
    print(format_transcript(segments))
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    config = load_config()
    meetings_dir = config.vault / "Meetings"
    if not meetings_dir.exists():
        print("No meetings yet.")
        return 0
    notes = sorted(meetings_dir.rglob("*.md"), key=lambda p: p.name, reverse=True)
    for note in notes:
        print(note.stem)
    return 0


def cmd_config(args: argparse.Namespace) -> int:
    print(CONFIG_PATH)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="meetscribe",
        description="Local-first AI meeting recorder: system-audio capture, "
        "local Whisper transcription, Claude summaries, Obsidian vault.",
    )
    parser.add_argument("--version", action="version", version=f"meetscribe {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="create the config file and vault skeleton")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("record", help="record a meeting (Ctrl+C to stop), then process it")
    p.add_argument("--title", help="title hint for the meeting")
    p.add_argument("--subject", help="force a subject instead of auto-classifying")
    p.add_argument("--no-process", action="store_true",
                   help="just record; skip transcription/summarization")
    p.set_defaults(func=cmd_record)

    p = sub.add_parser("process", help="transcribe + summarize a recording (session dir or audio file)")
    p.add_argument("path")
    p.add_argument("--title", help="title hint for the meeting")
    p.add_argument("--subject", help="force a subject instead of auto-classifying")
    p.set_defaults(func=cmd_process)

    p = sub.add_parser("transcribe", help="print the transcript of a recording, nothing else")
    p.add_argument("path")
    p.set_defaults(func=cmd_transcribe)

    p = sub.add_parser("list", help="list meetings in the vault")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("config", help="print the config file path")
    p.set_defaults(func=cmd_config)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
