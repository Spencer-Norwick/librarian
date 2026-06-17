# Automation Runbook

Keep automation thin. Scheduled jobs should call the CLI and let the CLI handle dry-run defaults, no-overwrite writes, logs, and index updates.

Use absolute paths in scheduler files, but keep public examples portable. Replace `/path/to/reading-librarian` with the local checkout path.

## Finder Quick Action

The optional Finder Quick Action can call:

```sh
/path/to/reading-librarian/scripts/add-to-inbox.sh "$@"
```

The script moves selected `.pdf`, `.epub`, `.txt`, `.md`, and `.docx` files into `inbox/` without overwriting existing inbox files. Folders, symlinks, and unsupported files are skipped.

## Recommended Jobs

Daily ingest:

```bash
cd /path/to/reading-librarian
.venv/bin/librarian daily --apply --lookup --enrich
```

Add `--lookup --enrich` only after the user has chosen catalog lookup and model enrichment for unattended new-file operation. Use `--maintain` only for a deliberate full-library repair pass.

Weekly digest:

```bash
cd /path/to/reading-librarian
.venv/bin/librarian weekly --apply
```

This writes one weekly draft, marks the selected work sent, and appends `_state/sent-log.md`. It does not send email.

Low-friction local delivery:

```bash
cd /path/to/reading-librarian
.venv/bin/librarian daily --apply --lookup --enrich
.venv/bin/librarian weekly --apply --notify-mac --open --message-self
```

For launchd, `scripts/librarian-weekly-local.sh` runs the daily pipeline first, then writes the weekly draft, posts a macOS notification, opens the local reading file, and sends the title, summary, first prompt, and compact library status through Messages. Configure the Messages recipient with `LIBRARIAN_MESSAGE_TO` in the scheduler environment or `message_to` in ignored `_state/config.toml`.

## Preview Before Enabling

```bash
cd /path/to/reading-librarian
.venv/bin/librarian daily
.venv/bin/librarian weekly
```

Expected safe output:

- `daily` reports OCR preparation, pending inbox moves, and lint status, or says no supported files were found.
- `weekly` prints a notification preview and draft body without writing a draft or sent state.
- The launchd weekly script intentionally runs daily first; if daily fails, weekly stops instead of choosing from stale state.

## Reply Commands

Reply handlers should call the CLI instead of editing Markdown directly:

```bash
.venv/bin/librarian reply skip --apply
.venv/bin/librarian reply read --apply
.venv/bin/librarian reply new --apply
```

## Agent Setup Protocol

When an agent sets up automation for a user:

1. Run `.venv/bin/librarian mount --check`.
2. Run `.venv/bin/librarian daily` and `.venv/bin/librarian weekly`.
3. Ask before enabling write-state jobs.
4. Create or update scheduler jobs for the chosen daily and weekly commands.
5. Do not enable email delivery unless the user explicitly requests it.
6. Keep provider-specific hooks, credentials, and scheduler state out of the public repo.

## Changing Or Pausing

- To pause ingestion, disable the daily job.
- To pause weekly picks, disable the weekly job.
- To switch from preview to live, add `--apply`.
- To switch from live to preview, remove `--apply`.
- To enable Messages delivery, configure `LIBRARIAN_MESSAGE_TO` or `message_to` in ignored `_state/config.toml`.
- To enable email later, configure `RESEND_API_KEY`, `LIBRARIAN_EMAIL_FROM`, and `LIBRARIAN_EMAIL_TO`, then change the weekly command to `weekly --email --apply`.

Run `.venv/bin/librarian lint` after changing scheduler behavior.
