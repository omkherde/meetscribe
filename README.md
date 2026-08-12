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
- **Private by default.** Audio never leaves your computer — transcription runs locally with Whisper. Only the finished *transcript text* is sent to the Claude API for summarization — and with the free Ollama backend, nothing leaves your machine at all.
- **Yours.** Output is plain Markdown in a folder you own. Open it in Obsidian and get backlinks + graph view for free.

## How it works

1. **`audiocap`** (Swift, ~300 lines) creates a system-wide Core Audio process tap and records system output to `system.wav`, while `AVAudioEngine` records your mic to `mic.wav`.
2. **Transcription** mixes the two tracks and runs [Whisper](https://github.com/openai/whisper) locally — `faster-whisper` everywhere, or `mlx-whisper` for extra speed on Apple Silicon.
3. **Summarization** turns the transcript into structured notes — title, subject classification, summary, key points, action items, Q&A, decisions, attendees, tags — using either the **Claude API** (best quality, pennies per meeting) or a **local model via Ollama** (100% free and offline).
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
- For summarization, one of:
  - an [Anthropic API key](https://platform.claude.com/) (Claude backend), **or**
  - [Ollama](https://ollama.com) with a pulled model (free local backend)

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
  backend: claude        # claude | ollama
  model: claude-opus-5   # used by the claude backend
  ollama_model: llama3.1:8b

subjects:
  - name: Work
    description: Job, team standups, client calls, projects at work.
  - name: School
    description: Classes, lectures, study groups, coursework.
  - name: College Consulting
    description: College application advising sessions.
```

Subjects are yours to define — the summarizer classifies each meeting into the best-fitting one (with your descriptions as guidance) or `Inbox` if nothing fits. Bump `transcription.model` to `small`/`medium` for better accuracy, or drop to `tiny` for speed.

## Cost — or free

Recording and transcription are always free and local. Summarization is the only step that can cost money, and you choose the backend:

| Backend | Cost per 1-hr meeting | Quality | Setup |
|---|---|---|---|
| `claude` + `claude-opus-5` | ~$0.10–0.15 | Best | API key |
| `claude` + `claude-sonnet-5` | ~$0.05 | Excellent | API key |
| `claude` + `claude-haiku-4-5` | ~$0.02 | Good | API key |
| `ollama` + `llama3.1:8b` | **$0** | Solid | `ollama pull llama3.1:8b` (~5 GB) |

### Free local mode

```bash
brew install ollama          # or download from https://ollama.com
ollama pull llama3.1:8b
```

Then set `summarization.backend: ollama` in your config. No API key needed, and the transcript never leaves your machine at all. Works well on Apple Silicon with 16 GB RAM (the 8B model uses ~5–7 GB while summarizing, which happens after the meeting ends). On tighter machines, `ollama_model: llama3.2:3b` runs in ~2.5 GB with a modest quality drop.

**Disk footprint:** ~1 GB for the base install (Python deps + Whisper model), plus ~5.5 GB if you add Ollama's 8B model. Raw recordings are large (~2 GB per meeting hour); set `keep_audio: false` to delete audio after processing — transcripts and notes are always kept.

## Privacy model

| Data | Where it goes |
|---|---|
| Audio (system + mic) | Stays on disk (`~/.meetscribe/recordings`), never uploaded |
| Transcription | 100% local (Whisper on your machine) |
| Transcript text | Sent to the Claude API for summarization only — or nowhere at all with the Ollama backend |
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

## License

MIT
