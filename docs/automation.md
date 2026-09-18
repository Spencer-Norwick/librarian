# Automation and delivery

[← Back to the README](../README.md)

Start with a working manual flow and a [prepared weekly queue](usage.md#prepare-a-weekly-pick). Scheduling is optional. Setup commands do not install jobs for you.

## Preview, then schedule

From your checkout, preview both operations:

```bash
.venv/bin/librarian daily
.venv/bin/librarian weekly
```

`daily` prepares and ingests the inbox, then checks the index. It does not automatically create summaries and questions. `weekly` shows the next ready pick and its draft.

For a scheduler, use absolute paths and set its working directory to the checkout:

```bash
cd /path/to/reading-librarian
.venv/bin/librarian daily --apply
.venv/bin/librarian weekly-due --apply
```

These commands write library state and a local weekly draft. They do not send email or Messages. `weekly-due` exits cleanly when this week's delivery is complete and can resume a known incomplete step. Pause jobs in your scheduler; remove `--apply` to return to previews.

Add `--lookup` or `--enrich` only after choosing those external-service behaviors. Explicit `--enrich` invokes your configured hook even when per-batch approval is otherwise required. Use `--maintain` only for a deliberate library-wide repair pass.

To prefer essays and articles, [save a short-reading filter](usage.md#prefer-shorter-readings). Scheduled picks and `reply new` honor it; an empty filtered queue stops.

## macOS notifications and Messages

Preview first, then choose only the channels you want:

```bash
librarian weekly-due --notify-mac --open
librarian weekly-due --notify-mac --open --apply
```

`--notify-mac` posts a notification; `--open` opens the local reading file. Neither requires email. For Messages, first set `message_to` under `[behavior]` in ignored `_state/config.toml`, or set `LIBRARIAN_MESSAGE_TO` in the scheduler environment. Add `--message-self` to explicitly send the title, summary, first question, and library status to that recipient.

[`local.reading-librarian.daily.plist`](local.reading-librarian.daily.plist) and [`local.reading-librarian.weekly.plist`](local.reading-librarian.weekly.plist) are optional launchd templates. Replace **every** `/path/to/reading-librarian` before installing. The weekly template also runs at load and every 30 minutes; `weekly-due` prevents a second completed delivery in the same week.

**Review the bundled scripts before enabling them.** [`librarian-daily.sh`](../scripts/librarian-daily.sh) explicitly runs `daily --apply --lookup --enrich`. [`librarian-weekly-local.sh`](../scripts/librarian-weekly-local.sh) runs that same preflight, then requests notifications, file opening, and Messages. They are examples for a deliberately configured assisted workflow, not the local-only commands above. A failed daily preflight stops the weekly script.

### Finder Quick Action

A Quick Action can invoke [`add-to-inbox.sh`](../scripts/add-to-inbox.sh):

```sh
/path/to/reading-librarian/scripts/add-to-inbox.sh "$@"
```

This helper **moves selected files immediately**; it has no preview mode. It chooses a new name for an existing inbox filename and skips folders, symlinks, and unsupported types. You can always copy files into `inbox/` yourself instead.

## Email

Email uses Resend. Configure `RESEND_API_KEY`, `LIBRARIAN_EMAIL_FROM`, and `LIBRARIAN_EMAIL_TO` privately, then explicitly preview:

```bash
librarian weekly --email
```

Add `--apply` only to send. Never put credentials or recipients in a public scheduler file or issue.

## Record your response

```bash
librarian reply read
librarian reply skip
librarian reply new
```

Add `--apply` after reviewing the preview. `new` skips the latest pick and creates the next ready draft. `librarian resend-latest --apply` explicitly resends the previous selection to Messages; it does not choose a new filtered work.

## Recover an interrupted delivery

Weekly delivery records progress in `_state/weekly-delivery.json`. Completed steps are not repeated. If a pending pick no longer matches your filter, the retry stops and preserves the journal; review it before deliberately widening the filter.

An interrupted notification, file open, Messages send, or expired email retry may have an **unknown outcome**. The journal keeps `in_progress_step` and stops automatic retries. Read its `last_error` and check the actual destination before retrying.

- If delivery occurred, do not clear the marker to send again.
- If you confirm it did not occur, back up the journal, clear only `in_progress_step`, and rerun the matching command.
- If you cannot determine the outcome, leave it intact and [ask for help](https://github.com/Spencer-Norwick/librarian/issues) with redacted details.

Email retries reuse the original idempotency key. Uncertain email retries are allowed for less than 23 hours from journal creation; older attempts stop for review.

## Setting this up with an agent

Ask the agent to run `mount --check`, `daily`, and `weekly` as previews first. Approve scheduled writes, model calls, and delivery channels deliberately. Keep credentials and provider hooks in local state, and run `librarian lint` after changing the setup.
