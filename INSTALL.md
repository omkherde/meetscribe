# Setting up the full meeting-memory system from scratch

This guide builds the complete stack on a fresh Mac: every meeting, lecture, and
handwritten page transcribed/OCR'd locally, filed into an Obsidian vault, and
semantically searchable by Claude — for $0/month, with nothing leaving your
machine except what you explicitly choose. Each stage ends with a verification
step; each stage is optional beyond the first.

**Requirements:** macOS 14.4+, Apple Silicon recommended (16 GB RAM for local
summarization), Python 3.10+, Xcode Command Line Tools (`xcode-select --install`).

```
recordings (meetscribe) ─┐
Granola meetings ────────┼──► Obsidian vault (Markdown) ──► Supermemory index ──► Claude
handwritten notes (OCR) ─┘         │                          (localhost)
                                   └──► private vault — never indexed, never synced
```

## 1. meetscribe — record, transcribe, summarize, file

```bash
git clone https://github.com/omkherde/meetscribe.git
cd meetscribe
make install        # builds audiocap + ocrtext (Swift), installs the Python CLI
meetscribe init     # writes ~/.meetscribe/config.yaml + vault skeleton
```

For Apple Silicon, `pip install mlx-whisper` for faster transcription.

Edit `~/.meetscribe/config.yaml`:
- `user_name` and `vocabulary` — your name, colleagues, jargon, professor names.
  This is the single highest-impact accuracy setting.
- `subjects` — one per class/context, with descriptions. The summarizer files
  each meeting into the best fit.
- `transcription.model: small` is a good accuracy/speed balance.

**Verify:** `meetscribe record`, speak a few sentences, Ctrl+C. Grant the
microphone + system-audio permission prompts on first run, run again, and check
a note appears in `~/MeetingVault/Meetings/`.

## 2. Free local summarization (Ollama)

```bash
brew install ollama && brew services start ollama   # auto-starts at login
ollama pull llama3.1:8b
```

In the config: `summarization.backend: ollama`. Nothing leaves your Mac now.
(Alternative: keep the default Claude API backend — better summaries, pennies
per meeting, transcript text goes to Anthropic.)

## 3. Private partition (do this before anything gets indexed)

For meetings too sensitive for any index or cloud (e.g. lab work near patient
data), add to the config:

```yaml
private_vault: ~/MeetingVault-Private
subjects:
  - name: Lab Research
    description: Research meetings that may discuss sensitive data.
    private: true
```

Record those with an explicit `meetscribe record --subject "Lab Research"` —
don't rely on auto-classification for anything sensitive. The private vault is
a separate folder that the sync/index layers below never touch. Keep it out of
iCloud. Note the limits: this partition is behavioral, not enforced, and
recording restricted data onto a personal machine may violate your
institution's policies regardless of where it's stored — check first.

**Verify:** record a test with that subject; the note must land in
`~/MeetingVault-Private/`, not the main vault.

## 4. Obsidian (and optionally your phone)

Open `~/MeetingVault` as a vault in Obsidian. Done.

For phone access, the vault must live in Obsidian's iCloud container:
install Obsidian on the phone first (creates the container), then move the
vault to `~/Library/Mobile Documents/iCloud~md~obsidian/Documents/MeetingVault`
and leave a symlink at the old path so every config keeps working:

```bash
mv ~/MeetingVault ~/Library/Mobile\ Documents/iCloud~md~obsidian/Documents/
ln -s ~/Library/Mobile\ Documents/iCloud~md~obsidian/Documents/MeetingVault ~/MeetingVault
```

Turn **OFF** System Settings → Apple ID → iCloud → Drive → "Optimize Mac
Storage" (evicted files break local tools). The private vault stays outside.

## 5. Claude search over the vault (memobsidian + Supermemory Local)

[memobsidian](https://github.com/akash-sr/memobsidian) (MIT) indexes the vault
into Supermemory Local — a semantic search engine on `localhost` with built-in
local embeddings; no API keys, nothing uploaded — and exposes `search_memory`
to Claude via MCP.

Clone it, run `memobsidian init` pointed at your vault, and let it install
Supermemory Local and register the MCP server with Claude Desktop / Claude
Code. Start the engine with `memobsidian start`.

Two operational facts (from real use — they will bite you otherwise):

1. **The Obsidian plugin's sync only ever adds new notes** — it never updates
   edited notes or removes deleted ones. Reconcile the index against disk
   periodically instead: list documents via Supermemory's local REST API
   (`POST /v3/documents/list` on `localhost:8787`, key `local`), delete + re-add
   what changed, purge what's gone, add what's missing (compare content with
   trailing whitespace stripped — storage trims it). A ~100-line Python script
   does this idempotently; point any coding assistant at the API and it will
   write one. Once you have it, the plugin's sync button is redundant.
2. **Auto-start**: Supermemory doesn't start at login. A LaunchAgent with
   `RunAtLoad` running `memobsidian start` (it's idempotent) removes the last
   manual step.

In Claude's connector settings, set the vault search to **ask before every
call** if the vault could ever hold sensitive-adjacent content — whatever a
search returns becomes part of your Claude conversation.

**Verify:** in Claude Desktop ask "search my meeting notes for <something you
recorded>" and approve the prompt.

## 6. Granola meetings/lectures (optional)

If you use [Granola](https://granola.ai): add its official connector to Claude
(free tier ≈ last 30 days). To make notes *permanent*, set up an archive
ritual: a Claude Code slash command that pulls every meeting via the Granola
MCP and writes each as Markdown into `vault/granola-notes/` (per-class folders
for course-code-titled lectures, `YYYY/MM/` otherwise), deduped by
`granola_id` in frontmatter. Run it at least every 4 weeks — a repeating
calendar event with the steps in its description is the reliable guardrail.
There is no supported way to export Granola's local cache directly (it's
encrypted app-side since v7.427); the MCP is the free path.

## 7. Handwritten notes (iPad → searchable)

Name your GoodNotes/Notability notebooks so a configured subject name appears
in them (e.g. "NEU 330 Behavioral Neuro") — exports inherit the notebook name
and route automatically. In the config:

```yaml
notes:
  inbox: ~/Library/Mobile Documents/com~apple~CloudDocs/MeetingNotes Inbox
```

Create that folder, and on the tablet export the **whole notebook** as PDF into
it after writing — no page selection. `meetscribe notes` sweeps it: local OCR
(Apple Vision — reads handwriting, ~1s/page), then files the PDF + a searchable
Markdown companion into `vault/Handwritten/<Subject>/`. An export with no date
in the filename maintains a single *living document* per notebook (each export
replaces the last — no redundant accumulation); a `YYYY-MM-DD` in the filename
files a frozen dated snapshot instead. Equations/diagrams don't OCR; the PDF
next to the note is the artifact you read.

To make it zero-command, add a LaunchAgent with `WatchPaths` on the inbox
running `meetscribe notes` + your index-refresh script, plus a `StartInterval`
(e.g. 1800 s) safety net — cloud sync can trigger the watch before a file
finishes downloading, so a failed file is left in the inbox for the retry.

**Verify:** drop a PDF in the inbox; within a couple of minutes the pair
appears in the vault and Claude can find its content.

## 8. Steady state

| When | What |
|---|---|
| After lectures | Export handwritten PDF to the inbox (~15 s). Everything else is automatic |
| Every 2 weeks (calendar event) | Granola archive command, then the index-refresh script (~3 min) |
| After a reboot | Nothing, if you set up the auto-start agents |
| New semester | Update subjects in the config + rename notebooks |

Total standing cost: ~150 MB RAM (Supermemory), ~0% CPU. The heavy moments
(Whisper + LLM after a recording) are transient and local by design.
