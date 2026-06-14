# Reading Librarian

Reading Librarian is a local-first CLI for people with messy folders of PDFs, EPUBs, essays, and saved texts who want a clean reading library without adopting a database-backed app.

It keeps the shape deliberately simple: drop files into `inbox/`, preview deterministic filenames, apply the move into a flat `library/`, and maintain one readable `library/index.md`.

No database. No wiki. No author folders. No cloud account. Catalog lookup, OCR, model enrichment, local notifications, Messages delivery, and email all stay behind explicit commands or local config.

Status: public alpha. The tool is designed to be safe and inspectable, but users should review dry-run output before applying changes to a real library.

## Quickstart

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .

librarian mount --check
librarian ingest
librarian ingest --apply
librarian status
librarian weekly
```

The installed command is `librarian`. The package also provides `reading-librarian` as a non-breaking alias for environments where the generic command name conflicts.

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
librarian weekly --apply --notify-mac --open --message-self
```

## Metadata Pipeline

The librarian uses the cheapest reliable step first:

1. Parse filenames.
2. Read embedded file metadata.
3. Extract local text.
4. Use catalog lookup only for weak title, author, or year metadata.
5. Use OCR only when a file has no extractable text and content-level work is needed.
6. Use model help only for semantic improvements such as summaries, tags, related works, and reading prompts.

Each index entry includes `Next action` so humans and agents know the next repair step: `clean`, `needs_catalog`, `needs_ocr`, `needs_manual`, or `needs_model`.

## Safety Rules

- New library files, OCR outputs, and weekly drafts use no-overwrite writes.
- Supported files in `inbox/` are moved only by `ingest --apply`.
- `index.md`, ingest logs, sent logs, status logs, and weekly draft state are changed only by commands run with `--apply`.
- Configured paths are kept inside the project root.
- Symlinked inbox files are ignored.
- Model calls happen only when explicitly requested or configured.
- Local notification, file opening, Messages delivery, and email happen only when explicitly requested.
- Optional catalog lookup uses Open Library only with `--lookup` or local config.

## Docs

- `docs/mount.md`: setup protocol for humans and agents
- `docs/automation.md`: daily/weekly scheduler and local delivery setup
- `AGENTS.md`: project rules for Codex-style agents

## Development

```bash
python -m pip install -e '.[dev]'
PYTHONPATH=src python -m pytest
```

Licensed under the MIT License.
