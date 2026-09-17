# Reading Librarian

Reading Librarian is a local-first CLI for people with messy folders of PDFs, EPUBs, essays, and saved texts who want a clean reading library without adopting a database-backed app.

It keeps the shape deliberately simple: drop files into `inbox/`, preview deterministic filenames, apply the move into a flat `library/`, and maintain one readable `library/index.md`.

No database. No wiki. No author folders. No cloud account. Catalog lookup, OCR, model enrichment, local notifications, Messages delivery, and email all stay behind explicit commands or local config.

Status: public alpha. The tool is designed to be safe and inspectable, but users should review dry-run output before applying changes to a real library.

## Quickstart

Requires Python **3.11 or newer**. Core file operations and Markdown drafts work on macOS and Linux; notification, file-opening, Messages, Finder, and launchd integrations require macOS. Windows is not currently verified.

```bash
git clone https://github.com/Spencer-Norwick/librarian.git
cd librarian
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[pdf]'

librarian --help
librarian mount --check
librarian mount --privacy local --model none
librarian mount --privacy local --model none --apply
```

The `pdf` extra enables local PDF extraction; use `python -m pip install -e .` if you only need the core command. `mount` previews configuration; `--apply` saves it. Copy a few files into `inbox/`, then review before applying:

```bash
librarian ingest
librarian ingest --apply
librarian lint
librarian status
```

Run workspace commands **from this directory**: the current working directory determines which inbox, library, and config are used. Activation only adds this virtual environment's commands to your terminal's search path; it does not select the library. In a new terminal, `cd` here and activate again, or use `.venv/bin/librarian` directly. `librarian --help` works from anywhere once the command is on your path. The package also provides `reading-librarian` as an alias if the generic command name conflicts.

For a separate reading workspace, keep the installed command available, create an empty directory, `cd` into it, run `librarian mount --check`, then `librarian init`. `init` creates missing setup files immediately and preserves existing files; it is the explicit setup exception to dry-run defaults.

Ingest alone does **not** make entries weekly-ready. Weekly picks require reviewed metadata, `Next action: clean`, a useful summary, and primer prompts. Configure an optional model hook and explicitly run enrichment, or supply reviewed summaries/prompts yourself in the established index format. `librarian weekly` previews a ready pick; `librarian weekly --apply` writes the draft and sent state without external delivery. See the [synthetic first-run walkthrough](docs/examples.md) for a complete demo without a provider or account, and the [mount guide](docs/mount.md) for real model setup.

## Why This Exists

Reading Librarian is for a narrower job than Calibre, Zotero, Paperless-ngx, Readwise Reader, Kavita, or Komga.

Use those if you want reader UI, citation management, household document archival, SaaS sync, or a media server. Use this if you want a durable local reading backlog that remains understandable as plain files.

## Supported Files

Supported inbox extensions are `.pdf`, `.epub`, `.txt`, `.md`, and `.docx`.

- `.pdf`: ingest plus local metadata/text extraction when `pypdf` is installed.
- `.txt` and `.md`: ingest plus local text extraction.
- `.epub` and `.docx`: ingest plus lightweight stdlib text extraction; entries are marked for review if extraction fails or metadata remains weak.

Install optional PDF extraction support with:

```bash
python -m pip install -e '.[pdf]'
```

## Runtime Layout

- `inbox/`: files waiting to be ingested
- `library/`: flat reading files plus `index.md`
- `_state/`: ignored local config and Markdown logs
- `_quarantine/`: files needing manual review
- `_output/weekly-read-drafts/`: generated weekly draft files

Test/sample files live under `tests/fixtures/`. Real reading files should live directly in `library/`.

## Core Commands

Run `librarian --help` for an aligned list of every command and a short explanation. Use `librarian COMMAND --help` (for example, `librarian ingest --help`) for that command's options.

Commands that modify files or Markdown are dry-run by default. Use `--apply` to write.

```bash
librarian mount --check
librarian ingest
librarian ingest --apply
librarian status
librarian weekly
librarian weekly --apply
librarian daily
librarian lint
librarian maintain
librarian enrich "Title or filename"
librarian ocr "Title or filename"
librarian reply skip|read|new
```

Useful optional flags:

- `--lookup`: use Open Library as a catalog fallback for weak metadata.
- `--enrich`: use a configured `model_command` for summaries, tags, and primer prompts.
- `--notify-mac --open --message-self`: local weekly delivery without email.
- `--email`: send digest email only when explicitly configured and combined with `--apply`.

Local weekly delivery example:

```bash
librarian weekly-due --apply --notify-mac --open --message-self
```

## Weekly Reading Size

Keep the whole library, but limit weekly picks to shorter readings:

```bash
librarian mount --weekly-mode short --weekly-max-minutes 0
librarian mount --weekly-mode short --weekly-max-minutes 0 --apply
librarian weekly
```

The first command previews the config change; the second saves it. Existing model and delivery settings are preserved. Scheduled `weekly-due` jobs and `reply new` use the saved preference automatically.

- `all` (the default) allows any digest-ready work.
- `short` allows essays, articles, stories, papers, chapters, and excerpts. A book must be explicitly labeled `excerpt` in its title or tags to qualify.
- `weekly_max_minutes` is an optional additional ceiling in short mode. The example uses `0`, so type alone decides eligibility. The built-in ceiling is 60 if you omit the setting; a positive ceiling excludes unknown or zero reading times. It has no effect in `all` mode.
- An empty filtered queue stops without substituting a longer work. Reading-time estimates depend on extracted text; the mode does not split books into excerpts.

Preview a one-run override with `librarian weekly --mode all` or `librarian weekly --mode short --max-minutes 30`. Add `--apply` only when you want to write/send that digest. To return permanently to all works, preview `librarian mount --weekly-mode all`, then rerun with `--apply`.

## Metadata Pipeline

The librarian uses the cheapest reliable step first:

1. Parse filenames.
2. Read embedded file metadata.
3. Extract local text.
4. Use catalog lookup only for weak title, author, or year metadata.
5. Use OCR when a PDF has missing or unusable extracted text and content-level work is needed.
6. Use model help only for semantic improvements such as summaries, tags, related works, and reading prompts.

Each index entry includes `Next action` so humans and agents know the next repair step: `clean`, `needs_catalog`, `needs_ocr`, `needs_manual`, or `needs_model`.

## Safety Rules

- New library files, OCR outputs, and weekly drafts use no-overwrite writes.
- Supported files in `inbox/` are moved only by `ingest --apply`.
- Apart from explicit workspace initialization, `index.md`, logs, and weekly draft state are changed only by commands run with `--apply`.
- Applied ingest batches roll back moved files and Markdown state when an operation fails.
- Configured paths are kept inside the project root.
- Symlinked inbox files are ignored.
- Dry-run enrichment can still send excerpts to the configured provider; dry-run limits local writes, not external calls. An explicit `--enrich` or `librarian enrich` approves model use for that batch. Configured automatic model calls run only after `require_external_model_approval = false` is deliberately set.
- Local notification, file opening, Messages delivery, and email happen only when explicitly requested.
- Optional catalog lookup uses Open Library only with `--lookup` or local config.

## Docs

- `docs/mount.md`: setup protocol for humans and agents
- `docs/automation.md`: daily/weekly scheduler and local delivery setup
- `docs/examples.md`: synthetic first-run walkthrough
- `CONTRIBUTING.md`: development and bug-report guidance
- `SECURITY.md`: security and privacy reporting
- `docs/release.md`: alpha release checklist
- `AGENTS.md`: project rules for Codex-style agents

## Development

```bash
python -m pip install -e '.[dev]'
PYTHONPATH=src python -m pytest
```

Licensed under the MIT License.
