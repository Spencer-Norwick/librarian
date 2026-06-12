# Automation Runbook

This project keeps automation thin. Scheduled jobs should call the CLI and let the CLI handle dry-run defaults, no-overwrite writes, logs, and index updates.

## Finder Quick Action

The local setup can install a Finder Quick Action named **Add to Librarian Inbox**. It sends selected supported files to `/Users/spencer/librarian/inbox` without changing the global Downloads folder.

The Quick Action calls:

```sh
/Users/spencer/librarian/scripts/add-to-inbox.sh "$@"
```

Supported selected files are `.pdf`, `.epub`, `.txt`, `.md`, and `.docx`. Folders, symlinks, and unsupported files are skipped. Existing inbox filenames are never overwritten; a numeric suffix is added when needed.

## Recommended Jobs

Daily ingest:

```bash
.venv/bin/librarian daily --apply
```

This ingests only new supported files from `inbox/`, updates `library/index.md`, and runs lint. It does not reparse existing library files. Add `--lookup` or `--enrich` only after the user has chosen those behaviors. Add `--maintain` only for a deliberate full-library repair pass.

Weekly digest:

```bash
.venv/bin/librarian weekly --apply
```

This writes one weekly draft, marks the selected work sent, and appends `_state/sent-log.md`. It does not send email. Use `weekly --email --apply` only after the user explicitly configures and requests email.

Low-friction local delivery:

```bash
.venv/bin/librarian weekly --apply --notify-mac --open --message-self
```

This writes the weekly draft, posts a macOS notification, opens the local reading file, and sends the title, summary, first prompt, and draft path through Messages. Configure the Messages recipient with `LIBRARIAN_MESSAGE_TO` in the scheduler environment or `message_to` in ignored `_state/config.toml`.

## Preview Commands

Use these before enabling write-state automation:

```bash
.venv/bin/librarian daily
.venv/bin/librarian weekly
```

Expected safe output:

- `daily` reports pending inbox moves or says no supported files were found.
- `weekly` prints a notification preview and draft body without writing a draft or sent state.

## Reply Commands

Reply handlers should call the CLI instead of editing Markdown directly:

```bash
.venv/bin/librarian reply skip --apply
.venv/bin/librarian reply read --apply
.venv/bin/librarian reply new --apply
```

- `skip` marks the latest sent digest skipped.
- `read` marks the latest sent digest read.
- `new` marks the latest sent digest skipped and writes the next digest-ready draft.

These commands make future email or agent reply handling simple without adding an inbound email service to the core project.

## Agent Setup Protocol

When an agent sets up automation for a user:

1. Run `.venv/bin/librarian mount --check`.
2. Run `.venv/bin/librarian daily` and `.venv/bin/librarian weekly`.
3. Ask before enabling write-state jobs.
4. Create or update scheduler jobs for the recommended daily and weekly commands.
5. Do not enable email delivery unless the user explicitly requests it.
6. Keep provider-specific hooks, credentials, and scheduler state out of the public repo.

If the scheduler supports job names, use clear names such as `Daily librarian ingest` and `Weekly librarian digest`.

## Changing Or Pausing

- To pause ingestion, disable the daily job.
- To pause weekly picks, disable the weekly job.
- To switch from preview to live, add `--apply`.
- To switch from live to preview, remove `--apply`.
- To enable email later, configure `RESEND_API_KEY`, `LIBRARIAN_EMAIL_FROM`, and `LIBRARIAN_EMAIL_TO`, then change the weekly command to `weekly --email --apply`.
- Alternatively, keep `email_from` and `email_to` in ignored `_state/config.toml` and provide only `RESEND_API_KEY` through the scheduler environment. Do not store the Resend API key in the repo.
- To enable Messages delivery, configure `LIBRARIAN_MESSAGE_TO` or `message_to` in ignored `_state/config.toml`.

Run `.venv/bin/librarian lint` after changing scheduler behavior.
