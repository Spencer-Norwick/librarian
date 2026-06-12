# Reading Librarian

A small, (mostly) local, flat-file CLI for managing a reading backlog.

It ingests supported files from `inbox/`, proposes deterministic filenames, moves them into a flat `library/` folder with `--apply`, and maintains one human and agent-readable `library/index.md`.

## Install for Local Development

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

The MVP has no required runtime dependencies. Install `pypdf` only if you want local PDF metadata/text extraction:

```bash
python -m pip install -e '.[pdf]'
```

You can also run without installing:

```bash
PYTHONPATH=src python3 -m librarian --help
```

## Project Layout

Runtime folders:

- `inbox/`: files waiting to be ingested
- `library/`: flat library files plus `index.md`
- `_state/`: config and Markdown logs
- `_quarantine/`: files needing manual review
- `_output/weekly-read-drafts/`: generated weekly draft files

Test/sample files live under `tests/fixtures/`. Do not put test inboxes or test libraries at the project root.

## Commands

```bash
librarian init
librarian mount --check
librarian mount
librarian mount --apply
librarian daily
librarian daily --apply
librarian weekly
librarian weekly --apply
librarian ingest
librarian ingest --lookup
librarian ingest --enrich --apply
librarian ingest --apply
librarian lint
librarian lint --apply
librarian reindex
librarian reindex --lookup
librarian reindex --enrich --apply
librarian reindex --apply
librarian maintain
librarian maintain --lookup
librarian maintain --enrich --apply
librarian maintain --apply
librarian enrich
librarian enrich "Title or filename" --apply
librarian ocr
librarian ocr "Title or filename" --apply
librarian digest
librarian digest --notify
librarian digest --email --apply
librarian weekly-pick
librarian weekly-pick --apply
librarian reply skip --apply
librarian reply read --apply
librarian reply new --apply
librarian list
librarian search "query"
librarian mark-read "Title or filename" --apply
librarian skip "Title or filename" --apply
```

Commands that modify files or Markdown are dry-run by default. Use `--apply` to write changes.

`mount` is the onboarding workflow for a new user or fork. It checks the local environment, detects available model CLIs, recommends a provider-neutral `model_command`, and previews `_state/config.toml` changes. `mount --check` is read-only. `mount --apply` writes local ignored config only.

See `docs/mount.md` for the human and agent setup runbook.
See `docs/automation.md` for daily and weekly scheduler setup.

`daily` is the automation-friendly daily workflow. It prepares scanned inbox PDFs with OCR when needed, ingests supported inbox files with optional catalog lookup and model enrichment, and then runs lint. Use `daily --apply --lookup --enrich` for the unattended new-file pipeline when catalog lookup and model enrichment are configured. Full-library maintenance remains explicit with `--maintain`. Dry-run remains non-mutating.

`weekly` is the automation-friendly digest workflow. It previews a notification by default. Use `weekly --apply` to write the draft and sent state, or `weekly --email --apply` to send email when configured.

For low-friction capture from Downloads, install the Finder Quick Action described in `docs/automation.md`. It appears as **Add to Librarian Inbox** and moves selected supported files into `inbox/` without overwriting existing files.

`lint --apply` only repairs missing index entries for files that are already in `library/`; it does not rename files, delete files, or resolve every lint issue automatically.

`reindex --apply` rebuilds `index.md` metadata for files already in `library/` while preserving each entry's status, sent date, and original filename when possible.

`ingest --lookup`, `reindex --lookup`, and `maintain --lookup` use Open Library as an optional catalog fallback for weak metadata. Local filename/PDF/text extraction is tried first, and lookup is off by default.

`ingest --enrich`, `reindex --enrich`, `maintain --enrich`, and `enrich` use a configured `model_command` to turn extracted text into a real summary, work-specific primer prompts, tags, and related-reading notes. Model enrichment is off by default.

`ocr` is the local scanned-PDF repair bridge. It previews entries marked `needs_ocr` by default. With `--apply`, it runs the configured `ocr_command` and writes a no-overwrite OCR copy to `_output/ocr/` for review; it does not replace or delete library files.

`maintain` is the normal repair workflow. It previews safe filename repairs, rebuilds `index.md`, and reports the next action for remaining weak entries. It is dry-run by default.

`digest` is the weekly read workflow. It renders a draft by default, writes the draft and sent state with `--apply`, prints an automation-friendly notification with `--notify`, and sends email only with `--email --apply` after email environment variables are configured. `weekly-pick` remains as a compatibility alias.

Digest drafts include the work summary, a compact reading-history line, primer questions, and the local file path. `--notify` prints a shorter preview with the title, author, summary, history, one primer prompt, and draft path. Entries marked `needs_model` are not digest-ready.

Local delivery is available without email:

```bash
librarian weekly --apply --notify-mac --open --message-self
```

`--notify-mac` posts a macOS notification, `--open` opens the selected local reading file, and `--message-self` sends the title, summary, first prompt, and draft path through Messages. Configure the Messages recipient with `LIBRARIAN_MESSAGE_TO` or ignored local config:

```toml
[behavior]
message_to = "you@example.com"
```

`reply` is the command-line target for automation or email-reply handlers. It acts on the latest sent digest from `_state/sent-log.md`: `reply skip --apply` marks it skipped, `reply read --apply` marks it read, and `reply new --apply` marks it skipped and writes the next digest-ready draft. Like the rest of the tool, it previews by default.

## Metadata Pipeline

The librarian uses the cheapest reliable step first:

1. Parse filenames.
2. Read embedded file metadata.
3. Extract local text with command-line libraries such as `pypdf`.
4. Use catalog lookup for weak title, author, or year metadata.
5. Use OCR only when a file has no extractable text and content-level work is needed.
6. Use model help only for semantic improvements such as summaries, tags, related works, and reading prompts.

Each index entry includes `Next action` so humans and agents know what to do next:

- `clean`: no immediate automated repair is needed.
- `needs_catalog`: run lookup before OCR or model work.
- `needs_ocr`: metadata is usable, but content extraction needs OCR.
- `needs_manual`: automated repair was not confident enough.
- `needs_model`: text and metadata are available; a model could improve summaries, tags, or prompts.

## Model Enrichment Contract

Configure a model command in `_state/config.toml` or with `LIBRARIAN_MODEL_COMMAND`.

```toml
[behavior]
use_model_assistance = false
model_command = ["path/to/enrich-command"]
model_max_input_chars = 12000
require_external_model_approval = true
```

The command receives JSON on stdin with the work metadata, instructions, and a text excerpt. It must print JSON on stdout:

```json
{
  "summary": "One to three specific sentences about the work.",
  "primer_prompts": [
    "A work-specific question for entering the text.",
    "A second work-specific question.",
    "A third work-specific question."
  ],
  "tags": ["philosophy", "media"],
  "related": "Optional concise related-reading note."
}
```

The CLI rejects incomplete enrichment output. A usable enrichment needs a specific summary and at least two primer prompts.

### Provider Hooks

The public project does not ship provider-specific model adapters. Keep model use behind the `model_command` contract so a Codex, Claude, OpenAI, Ollama, or local-model user can provide the command that fits their environment.

```toml
[behavior]
model_command = ["path/to/json-enrichment-command"]
model_max_input_chars = 12000
```

Or for a one-off command:

```bash
LIBRARIAN_MODEL_COMMAND="path/to/json-enrichment-command" librarian enrich "Title or filename"
```

Use `--apply` only after reviewing the dry-run output:

```bash
LIBRARIAN_MODEL_COMMAND="path/to/json-enrichment-command" librarian enrich "Title or filename" --apply
```

The command may be a shell script, Python script, local binary, or model CLI wrapper. It must read the librarian JSON payload from stdin and print the enrichment JSON schema above to stdout.

If the command calls an external model provider, it may send selected work metadata and a text excerpt outside the user's machine. Keep dry-run review as the default, and do not use external enrichment for private or sensitive files unless that tradeoff is deliberate.

For public forks, provider-specific hooks should be created in ignored local state such as `_state/model-enrich-local`, then configured through `_state/config.toml` or `LIBRARIAN_MODEL_COMMAND`. See `docs/mount.md` for the agent setup protocol and synthetic hook test.

`require_external_model_approval` is the project-level consent toggle for agents. The public default is `true`; a local user can set it to `false` in ignored `_state/config.toml` after deciding that the configured provider may receive enrichment excerpts.

Codex CLI hooks require access to the user's Codex auth/state under `CODEX_HOME`, usually `~/.codex`, and may need network access. In managed sandboxed agent sessions, preview `librarian enrich ...` first; if Codex state, auth, or network sandbox errors appear, rerun the same dry-run command with explicit approval for escalated execution before using `--apply`.

## Filename Convention

```text
LastFirst_Title_Subtitle_Year_WorkType.ext
```

Examples:

```text
DebordGuy_SocietyOfTheSpectacle_1967_book.pdf
Unknown_NotesOnCybernetics_nd_article.pdf
```

Collisions never overwrite existing files. A short stable hash suffix is appended when needed.

Ingest also reserves planned filenames before applying a batch, so two inbox files that resolve to the same target name are both kept.

## Safety

- New library files and weekly drafts are created with no-overwrite file operations.
- Supported files in `inbox/` are moved only by `ingest --apply`.
- After `librarian init`, `index.md`, ingest logs, sent/status logs, and weekly draft state are edited only by commands run with `--apply`.
- Configured paths are kept inside the project root.
- Symlinked inbox files are ignored.
- No SQL, database, or wiki is used.
- Model calls happen only when `--enrich`, `librarian enrich`, or `use_model_assistance = true` is configured.
- Email is sent only when explicitly requested with `digest --email --apply` and configured through environment variables.
- Optional catalog lookup uses Open Library only when explicitly requested with `--lookup` or enabled in `_state/config.toml`.

Email delivery uses Resend's HTTPS API without a required package dependency. Configure it with:

```bash
export RESEND_API_KEY="..."
export LIBRARIAN_EMAIL_FROM="Reading Librarian <reads@example.com>"
export LIBRARIAN_EMAIL_TO="you@example.com"
```

Or keep the non-secret sender and recipient in ignored local config:

```toml
[behavior]
email_from = "Reading Librarian <reads@example.com>"
email_to = "you@example.com"
```

`RESEND_API_KEY` should still come from the environment.

## Scheduling Examples

The CLI does not install scheduled jobs automatically.

The recommended automation commands are documented in `docs/automation.md`.

### cron

```cron
0 8 * * * cd /path/to/reading-librarian && librarian daily --apply
0 9 * * 1 cd /path/to/reading-librarian && librarian lint
0 10 * * 1 cd /path/to/reading-librarian && librarian weekly --apply
```

### macOS launchd

Create `~/Library/LaunchAgents/local.reading-librarian.daily.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>local.reading-librarian.daily</string>
  <key>ProgramArguments</key>
  <array>
    <string>/path/to/venv/bin/librarian</string>
    <string>daily</string>
    <string>--apply</string>
  </array>
  <key>WorkingDirectory</key>
  <string>/path/to/reading-librarian</string>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>8</integer>
    <key>Minute</key>
    <integer>0</integer>
  </dict>
</dict>
</plist>
```

Load it manually when ready:

```bash
launchctl load ~/Library/LaunchAgents/local.reading-librarian.daily.plist
```

## Notes

- No SQL or database is used.
- No wiki or author-folder structure is created.
- Real email is sent only by `digest --email --apply` with email environment variables configured.
- Scanned or unreadable PDFs are marked for review instead of silently passing.
