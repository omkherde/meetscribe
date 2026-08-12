"""Meeting intelligence: turn a transcript into structured notes with Claude.

The transcript never needs to leave your machine for transcription; only the
transcript text (not the audio) is sent to the Claude API for summarization.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import anthropic

from .config import Config

SYSTEM_PROMPT = """\
You are a meticulous meeting analyst. You are given the transcript of a meeting
captured from one participant's computer (system audio + their microphone,
no speaker labels). Extract structured meeting notes.

Guidelines:
- Base everything strictly on the transcript. Never invent names, dates, or
  commitments that are not supported by what was said.
- The transcript may contain ASR errors; use context to interpret them, and
  prefer omitting a detail over guessing.
- "title": a short specific title (max ~8 words), no date in it.
- "subject": pick the single best-fitting subject from the provided list, or
  "Inbox" if nothing fits.
- "summary": 1-3 tight paragraphs in markdown covering purpose, what was
  discussed, and outcomes.
- "action_items": concrete follow-ups with an owner when identifiable from the
  conversation ("me" = the recording user). Include due dates only if stated.
- "questions": notable questions raised during the meeting. If a question was
  answered, capture the answer; if it was left open, set answered=false.
- "decisions": explicit decisions or agreements reached.
- "people": names of participants or people substantively discussed.
- "tags": 2-6 short lowercase topic tags (no '#', no spaces; use '-' instead).
"""


@dataclass
class MeetingNotes:
    title: str
    subject: str
    summary: str
    key_points: list[str] = field(default_factory=list)
    action_items: list[dict] = field(default_factory=list)
    questions: list[dict] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    people: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


def _schema(subject_names: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "subject": {"type": "string", "enum": [*subject_names, "Inbox"]},
            "summary": {"type": "string"},
            "key_points": {"type": "array", "items": {"type": "string"}},
            "action_items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "task": {"type": "string"},
                        "owner": {"type": ["string", "null"]},
                        "due": {"type": ["string", "null"]},
                    },
                    "required": ["task", "owner", "due"],
                    "additionalProperties": False,
                },
            },
            "questions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "question": {"type": "string"},
                        "answer": {"type": ["string", "null"]},
                        "answered": {"type": "boolean"},
                    },
                    "required": ["question", "answer", "answered"],
                    "additionalProperties": False,
                },
            },
            "decisions": {"type": "array", "items": {"type": "string"}},
            "people": {"type": "array", "items": {"type": "string"}},
            "tags": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "title", "subject", "summary", "key_points", "action_items",
            "questions", "decisions", "people", "tags",
        ],
        "additionalProperties": False,
    }


def _build_prompt(transcript: str, config: Config, meta: dict) -> str:
    subject_lines = "\n".join(
        f"- {s.name}: {s.description}" if s.description else f"- {s.name}"
        for s in config.subjects
    ) or "- (no subjects configured)"

    context_bits = []
    if config.user_name:
        context_bits.append(
            f"The person recording this meeting is {config.user_name} "
            '(referred to as "me" in action items).'
        )
    known = [n for n in [config.user_name, *config.vocabulary] if n]
    if known:
        context_bits.append(
            "Known names and terms (the transcriber may have garbled these — "
            "if a word in the transcript is a close phonetic match, use the "
            "correct spelling from this list): " + ", ".join(known)
        )
    if meta.get("started"):
        context_bits.append(f"Recorded: {meta['started']}")
    if meta.get("platform"):
        context_bits.append(f"Platform: {meta['platform']}")
    if meta.get("title"):
        context_bits.append(f"User-provided title hint: {meta['title']}")
    context = "\n".join(context_bits)

    return (
        f"Available subjects:\n{subject_lines}\n\n"
        + (f"Meeting context:\n{context}\n\n" if context else "")
        + f"Transcript:\n<transcript>\n{transcript}\n</transcript>"
    )


def summarize(transcript: str, config: Config, meta: dict | None = None) -> MeetingNotes:
    """Dispatch to the configured summarization backend."""
    meta = meta or {}
    backend = config.summarization_backend
    if backend == "claude":
        data = _summarize_claude(transcript, config, meta)
    elif backend == "ollama":
        data = _summarize_ollama(transcript, config, meta)
    else:
        raise ValueError(
            f"Unknown summarization backend {backend!r} (expected 'claude' or 'ollama')"
        )

    subject = data.get("subject") or "Inbox"
    if subject not in config.subject_names and subject != "Inbox":
        subject = "Inbox"

    return MeetingNotes(
        title=data.get("title") or meta.get("title") or "Untitled Meeting",
        subject=subject,
        summary=data.get("summary", ""),
        key_points=data.get("key_points", []),
        action_items=data.get("action_items", []),
        questions=data.get("questions", []),
        decisions=data.get("decisions", []),
        people=data.get("people", []),
        tags=data.get("tags", []),
    )


def _summarize_claude(transcript: str, config: Config, meta: dict) -> dict:
    client = anthropic.Anthropic()
    model = config.summarization_model
    schema = _schema(config.subject_names)
    prompt = _build_prompt(transcript, config, meta)

    kwargs: dict = dict(
        model=model,
        max_tokens=config.summarization_max_tokens,
        system=SYSTEM_PROMPT,
        output_config={"format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content": prompt}],
    )

    # On Claude Opus 5 / Fable 5, opt into server-side refusal fallbacks so a
    # rare safety-classifier decline is transparently re-served by another model.
    if model.startswith(("claude-opus-5", "claude-fable-5")):
        try:
            with client.beta.messages.stream(
                betas=["server-side-fallback-2026-07-01"],
                extra_body={"fallbacks": "default"},
                **kwargs,
            ) as stream:
                message = stream.get_final_message()
        except anthropic.BadRequestError:
            # Older API surface without the fallbacks beta - retry plainly.
            with client.messages.stream(**kwargs) as stream:
                message = stream.get_final_message()
    else:
        with client.messages.stream(**kwargs) as stream:
            message = stream.get_final_message()

    if message.stop_reason == "refusal":
        raise RuntimeError(
            "Claude declined to process this transcript (safety classifier). "
            "The raw transcript has still been saved."
        )
    if message.stop_reason == "max_tokens":
        raise RuntimeError(
            "Summary was truncated (max_tokens). Increase summarization.max_tokens "
            "in your config."
        )

    text = next(b.text for b in message.content if b.type == "text")
    return json.loads(text)


def _summarize_ollama(transcript: str, config: Config, meta: dict) -> dict:
    """Free, fully local summarization via Ollama's structured-output API."""
    import urllib.error
    import urllib.request

    payload = {
        "model": config.ollama_model,
        "stream": False,
        "format": _schema(config.subject_names),
        "options": {"num_ctx": config.ollama_num_ctx, "temperature": 0},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_prompt(transcript, config, meta)},
        ],
    }
    request = urllib.request.Request(
        f"{config.ollama_url}/api/chat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=1800) as response:
            body = json.loads(response.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        raise RuntimeError(
            f"Ollama returned an error ({e.code}): {detail}\n"
            f"If the model is missing, run: ollama pull {config.ollama_model}"
        ) from e
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"Could not reach Ollama at {config.ollama_url} ({e.reason}). "
            "Is it running? Install from https://ollama.com, then:\n"
            f"  ollama pull {config.ollama_model}"
        ) from e

    content = (body.get("message") or {}).get("content", "")
    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Ollama model {config.ollama_model} did not return valid JSON. "
            "Try a larger model (e.g. llama3.1:8b) in summarization.ollama_model."
        ) from e
