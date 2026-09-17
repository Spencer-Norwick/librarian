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
.venv/bin/librarian daily --apply
```

Plain daily ingestion does not create weekly summaries or prompts. Prepare the queue through reviewed enrichment before enabling weekly writes. Add `--lookup --enrich` only after the user has chosen catalog lookup and model enrichment for unattended new-file operation. Use `--maintain` only for a deliberate full-library repair pass.

Weekly digest:

```bash
cd /path/to/reading-librarian
.venv/bin/librarian weekly --apply
```

This writes one weekly draft, marks the selected work sent, and appends `_state/sent-log.md`. It does not send email.

Weekly selection can be limited without changing the scheduler or removing books:

```bash
.venv/bin/librarian mount --weekly-mode short --weekly-max-minutes 0
.venv/bin/librarian mount --weekly-mode short --weekly-max-minutes 0 --apply
```

Short mode permits essays, articles, stories, papers, chapters, and explicitly labeled excerpts. The example uses `0` for the type filter alone. Set a positive number if you also want an estimated time ceiling; omitting this setting retains the configured ceiling (60 on a new workspace). Weekly commands, replacement picks, and the status queue use this preference; `--mode all` overrides it for one invocation. If no eligible work remains, delivery stops rather than choosing a book. The full library remains available.

If an incomplete delivery's pick is excluded by a newly saved filter, its retry stops before sending anything further and preserves the delivery journal. Review that pending pick before explicitly widening the mode or ceiling to finish its delivery. `resend-latest` is an explicit resend of the previous selection, not a new filtered pick.

macOS local delivery (requires a digest-ready queue and configured Messages recipient):

```bash
cd /path/to/reading-librarian
.venv/bin/librarian daily --apply
.venv/bin/librarian weekly-due --apply --notify-mac --open --message-self
```

Notifications, file opening, Messages, Finder Quick Actions, and launchd are macOS integrations. Markdown-only weekly drafts do not require them.

For launchd, `scripts/librarian-weekly-local.sh` runs the daily pipeline first, then calls the idempotent weekly delivery path. The weekly command writes a delivery journal at `_state/weekly-delivery.json`, posts a macOS notification, opens the local reading file, sends the title, summary, first prompt, and compact library status through Messages, then marks the pick sent only after requested delivery steps succeed. If a delivery step fails, a later launchd run retries the incomplete step without duplicating completed steps. Configure the Messages recipient with `LIBRARIAN_MESSAGE_TO` in the scheduler environment or `message_to` in ignored `_state/config.toml`.

Email retries retain the original weekly idempotency key. The CLI permits an uncertain email retry for less than 23 hours from journal creation, conservatively inside Resend's 24-hour retention window. For older email attempts and for notification, file-open, and Messages steps, an interruption, timeout, connection failure, or failed AppleScript process may leave the outcome unknown. The journal preserves `in_progress_step` and stops automatic retries. Check the actual channel and the journal's `last_error` first: if delivery occurred, do not clear the marker to resend. If you confirm it did not occur and deliberately want a retry, back up the journal, clear only `in_progress_step` in `_state/weekly-delivery.json`, then rerun the matching command. If the outcome cannot be determined, leave the marker intact and seek help with redacted details.

## Preview Before Enabling

```bash
cd /path/to/reading-librarian
.venv/bin/librarian daily
.venv/bin/librarian weekly
```

Expected safe output:

- `daily` reports OCR preparation, pending inbox moves, and lint status, or says no supported files were found.
- `weekly` prints a notification preview and draft body without writing a draft or sent state.
- `weekly-due` is for schedulers: it exits cleanly once the current week is complete and otherwise resumes incomplete delivery from `_state/weekly-delivery.json`.
- The launchd weekly script intentionally runs daily first; if daily fails, weekly delivery stops instead of choosing from stale state.

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
