"""Obsidian vault writer.

Vault layout:

    <vault>/
      Home.md                      master index (auto-maintained)
      Subjects/<Subject>.md        one hub note per subject (auto-maintained)
      Meetings/<YYYY>/<date time title>.md
      Transcripts/<date time title> (Transcript).md

Meeting notes wikilink to their subject hub and to attendees, so Obsidian's
graph view naturally clusters meetings by subject and by person.

Auto-maintained sections are bounded by `<!-- meetscribe:... -->` markers;
anything you write outside the markers is preserved.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .config import Config
from .summarize import MeetingNotes

MEETINGS_START = "<!-- meetscribe:meetings:start -->"
MEETINGS_END = "<!-- meetscribe:meetings:end -->"


@dataclass
class WrittenNote:
    note_path: Path
    transcript_path: Path


def _safe_filename(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|#^\[\]]', "", name).strip()
    name = re.sub(r"\s+", " ", name)
    return name[:80] or "Untitled"


def _tag(s: str) -> str:
    return re.sub(r"[^a-z0-9/_-]", "", s.lower().replace(" ", "-"))


def _yaml_list(items: list[str]) -> str:
    return "[" + ", ".join(f'"{i}"' for i in items) + "]"


def _fmt_duration(seconds: int | None) -> str | None:
    if not seconds:
        return None
    minutes = round(seconds / 60)
    if minutes < 60:
        return f"{minutes} min"
    h, m = divmod(minutes, 60)
    return f"{h}h {m:02d}m"


def ensure_vault(config: Config) -> None:
    vault = config.vault
    for sub in ("Subjects", "Meetings", "Transcripts"):
        (vault / sub).mkdir(parents=True, exist_ok=True)
    for subject in [*config.subject_names, "Inbox"]:
        _ensure_subject_page(vault, subject)
    _rebuild_home(config)


def _subject_page_path(vault: Path, subject: str) -> Path:
    return vault / "Subjects" / f"{_safe_filename(subject)}.md"


def _ensure_subject_page(vault: Path, subject: str) -> Path:
    path = _subject_page_path(vault, subject)
    if not path.exists():
        path.write_text(
            f"---\ntags: [subject]\n---\n\n"
            f"# {subject}\n\n"
            f"## Meetings\n\n{MEETINGS_START}\n{MEETINGS_END}\n"
        )
    return path


def _insert_in_marked_block(text: str, entry: str) -> str:
    """Prepend an entry inside the meetings marker block (newest first)."""
    if MEETINGS_START not in text or MEETINGS_END not in text:
        text = text.rstrip() + f"\n\n## Meetings\n\n{MEETINGS_START}\n{MEETINGS_END}\n"
    head, rest = text.split(MEETINGS_START, 1)
    block, tail = rest.split(MEETINGS_END, 1)
    lines = [ln for ln in block.strip().splitlines() if ln.strip()]
    if entry not in lines:
        lines.insert(0, entry)
    new_block = "\n".join(lines)
    return f"{head}{MEETINGS_START}\n{new_block}\n{MEETINGS_END}{tail}"


def write_meeting(
    config: Config,
    notes: MeetingNotes,
    transcript: str,
    meta: dict,
) -> WrittenNote:
    vault = config.vault
    ensure_dirs = [vault / "Subjects", vault / "Transcripts"]

    started = (
        datetime.fromisoformat(meta["started"]) if meta.get("started") else datetime.now()
    )
    date = started.strftime("%Y-%m-%d")
    hhmm = started.strftime("%H%M")
    year_dir = vault / "Meetings" / started.strftime("%Y")
    for d in [*ensure_dirs, year_dir]:
        d.mkdir(parents=True, exist_ok=True)

    base = f"{date} {hhmm} {_safe_filename(notes.title)}"
    note_path = year_dir / f"{base}.md"
    transcript_name = f"{base} (Transcript)"
    transcript_path = vault / "Transcripts" / f"{transcript_name}.md"

    duration = _fmt_duration(meta.get("duration_seconds"))
    platform = meta.get("platform")
    subject_file = _safe_filename(notes.subject)
    tags = ["meeting", *(_tag(t) for t in notes.tags if _tag(t))]

    # --- meeting note -------------------------------------------------------
    fm = [
        "---",
        f'title: "{notes.title}"',
        f"date: {date}",
        f'time: "{started.strftime("%H:%M")}"',
    ]
    if duration:
        fm.append(f'duration: "{duration}"')
    if platform:
        fm.append(f'platform: "{platform}"')
    fm.append(f'subject: "{notes.subject}"')
    if notes.people:
        fm.append(f"people: {_yaml_list(notes.people)}")
    fm.append(f"tags: {_yaml_list(tags)}")
    fm.append("---")

    body = [f"# {notes.title}", ""]
    info = [f"**Subject:** [[{subject_file}|{notes.subject}]]"]
    if platform:
        info.append(f"**Platform:** {platform}")
    if duration:
        info.append(f"**Duration:** {duration}")
    body.append(" · ".join(info))
    if notes.people:
        body.append("")
        body.append("**Attendees:** " + ", ".join(f"[[{_safe_filename(p)}]]" for p in notes.people))

    body += ["", "## Summary", "", notes.summary.strip()]

    if notes.key_points:
        body += ["", "## Key Points", ""]
        body += [f"- {p}" for p in notes.key_points]

    if notes.action_items:
        body += ["", "## Action Items", ""]
        for item in notes.action_items:
            line = f"- [ ] {item.get('task', '').strip()}"
            if item.get("owner"):
                line += f" — **{item['owner']}**"
            if item.get("due"):
                line += f" (due {item['due']})"
            body.append(line)

    if notes.questions:
        body += ["", "## Questions", ""]
        for q in notes.questions:
            if q.get("answered") and q.get("answer"):
                body.append(f"- **Q:** {q.get('question', '').strip()}")
                body.append(f"  **A:** {q['answer'].strip()}")
            else:
                body.append(f"- **Q (open):** {q.get('question', '').strip()}")

    if notes.decisions:
        body += ["", "## Decisions", ""]
        body += [f"- {d}" for d in notes.decisions]

    body += ["", "---", f"Full transcript: [[{transcript_name}]]", ""]
    note_path.write_text("\n".join(fm) + "\n\n" + "\n".join(body))

    # --- transcript note ----------------------------------------------------
    transcript_path.write_text(
        "---\n"
        f'title: "{notes.title} (Transcript)"\n'
        f"date: {date}\n"
        f'tags: ["transcript"]\n'
        "---\n\n"
        f"# Transcript — {notes.title}\n\n"
        f"Meeting note: [[{base}]]\n\n"
        "```\n" + transcript.strip() + "\n```\n"
    )

    # --- subject hub + home index -------------------------------------------
    subject_page = _ensure_subject_page(vault, notes.subject)
    entry = f"- [[{base}|{notes.title}]] — {date}"
    subject_page.write_text(_insert_in_marked_block(subject_page.read_text(), entry))
    _rebuild_home(config)

    return WrittenNote(note_path=note_path, transcript_path=transcript_path)


def _rebuild_home(config: Config) -> None:
    vault = config.vault
    subjects = sorted(
        p.stem for p in (vault / "Subjects").glob("*.md")
    ) if (vault / "Subjects").exists() else []

    meetings = sorted(
        (vault / "Meetings").rglob("*.md"), key=lambda p: p.name, reverse=True
    ) if (vault / "Meetings").exists() else []

    lines = [
        "---",
        'tags: ["index"]',
        "---",
        "",
        "# Meeting Vault",
        "",
        "All meetings, recorded and summarized by "
        "[meetscribe](https://github.com/omkherde/meetscribe).",
        "",
        "## Subjects",
        "",
    ]
    lines += [f"- [[{s}]]" for s in subjects]
    lines += ["", "## Recent Meetings", ""]
    lines += [f"- [[{p.stem}]]" for p in meetings[:25]]
    lines.append("")
    (vault / "Home.md").write_text("\n".join(lines))
