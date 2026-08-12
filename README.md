# meetscribe

**A local-first AI meeting recorder for macOS.** No bot joins your calls. meetscribe listens to your computer's own audio — whatever your speakers play plus your microphone — so it works identically with **Zoom, Google Meet, Microsoft Teams, Webex, Slack huddles, Discord, FaceTime**, or anything else that makes sound.

Every meeting becomes a clean Markdown note — summary, action items, questions asked & answered, decisions — filed into an **Obsidian vault** organized by subject (Work, School, College Consulting, …), so your meeting history turns into a browsable knowledge graph.

```
🎙  system audio + mic  ──►  🔒 local Whisper transcription  ──►  🧠 Claude summary  ──►  🗂  Obsidian vault
```

## Why not a meeting bot?

Tools like Fathom or Otter join your meetings as a visible participant. meetscribe doesn't:

- **Nothing joins the call.** Capture happens on your machine via macOS Core Audio process taps.
- **Universal.** Any meeting platform, any browser, even in-person meetings (mic only).
- **Private by default.** Audio never leaves your computer — transcription runs locally with Whisper. Only the finished *transcript text* is sent to the Claude API for summarization.
- **Yours.** Output is plain Markdown in a folder you own. Open it in Obsidian and get backlinks + graph view for free.

## How it works

1. **`audiocap`** (Swift, ~300 lines) creates a system-wide Core Audio process tap and records system output to `system.wav`, while `AVAudioEngine` records your mic to `mic.wav`.
2. **Transcription** mixes the two tracks and runs [Whisper](https://github.com/openai/whisper) locally — `faster-whisper` everywhere, or `mlx-whisper` for extra speed on Apple Silicon.
3. **Summarization** sends the transcript to Claude with a structured-output schema and gets back a title, subject classification, summary, key points, action items, Q&A, decisions, attendees, and tags.
4. **The vault writer** files everything as Markdown with wikilinks:

```
MeetingVault/
├── Home.md                          # master index
├── Subjects/
│   ├── Work.md                      # subject hubs, auto-updated
│   ├── School.md
│   └── College Consulting.md
├── Meetings/
│   └── 2026/
│       └── 2026-08-12 1400 Q3 Planning Sync.md
└── Transcripts/
    └── 2026-08-12 1400 Q3 Planning Sync (Transcript).md
```

Each meeting note links to its subject hub (`[[Work]]`) and attendees (`[[Alice]]`), so Obsidian's graph view stratifies your meetings by subject and person automatically.

## Requirements

- macOS **14.4+** (Core Audio process taps)
- Xcode Command Line Tools (`xcode-select --install`) to build the capture helper
- Python **3.10+**
- An [Anthropic API key](https://platform.claude.com/) for summarization

## Install

```bash
git clone https://github.com/omkherde/meetscribe.git
cd meetscribe
make install          # builds the Swift helper + installs the Python CLI
```

On Apple Silicon, optionally install the faster transcription backend:

```bash
pip install mlx-whisper
```

Set your API key (either works):

```bash
export ANTHROPIC_API_KEY=sk-ant-...
# or: ant auth login
```

## Usage

```bash
meetscribe init                  # create config + vault skeleton
meetscribe record                # start recording; Ctrl+C when the meeting ends
```

That's it. On Ctrl+C, meetscribe transcribes locally, summarizes with Claude, and files the note. Other commands:

```bash
meetscribe record --title "1:1 with Sam" --subject Work
meetscribe record --no-process               # record now, process later
meetscribe process ~/.meetscribe/recordings/20260812-140002
meetscribe process some-meeting.m4a          # works on any audio file too
meetscribe transcribe <path>                 # transcript only, printed to stdout
meetscribe list                              # meetings in the vault
```

**First run:** macOS will ask for *System Audio Recording* and *Microphone* permission for your terminal app. Grant both, then re-run.

## Configuration

`meetscribe init` writes `~/.meetscribe/config.yaml`:

```yaml
vault: ~/MeetingVault
keep_audio: true

transcription:
  backend: auto        # auto | faster-whisper | mlx
  model: base          # tiny | base | small | medium | large-v3

summarization:
  model: claude-opus-5

subjects:
  - name: Work
    description: Job, team standups, client calls, projects at work.
  - name: School
    description: Classes, lectures, study groups, coursework.
  - name: College Consulting
    description: College application advising sessions.
```

Subjects are yours to define — the summarizer classifies each meeting into the best-fitting one (with your descriptions as guidance) or `Inbox` if nothing fits. Bump `transcription.model` to `small`/`medium` for better accuracy, or drop to `tiny` for speed.

## Privacy model

| Data | Where it goes |
|---|---|
| Audio (system + mic) | Stays on disk (`~/.meetscribe/recordings`), never uploaded |
| Transcription | 100% local (Whisper on your machine) |
| Transcript text | Sent to the Claude API for summarization only |
| Notes & transcripts | Plain Markdown in your vault |

Set `keep_audio: false` to delete WAVs after processing.

> ⚠️ **Recording consent:** many jurisdictions require the consent of all parties before recording a conversation. You are responsible for complying with the laws that apply to you — tell people you're recording.

## Repository layout

```
audio/          Swift package: audiocap (system audio + mic capture)
meetscribe/     Python package: CLI, transcription, summarization, vault writer
Makefile        build + install
```

## Roadmap

- Speaker diarization (who said what)
- Menu bar app with auto-start when a meeting app launches
- Calendar integration to name meetings from your schedule
- Local LLM summarization option (Ollama)

## License

MIT
