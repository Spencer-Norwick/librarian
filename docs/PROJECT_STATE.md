# Project State

Last updated: 2026-09-17
Repository: reading-librarian
Branch: codex/readable-cli-help
Last known-good baseline: a6e3114 — Add configurable short-reading mode for weekly picks (94 tests passed before this change).

## Current Objective

Make `librarian --help` display every command in an aligned vertical list with concise explanations and guidance for command-specific help.

## Verified State

- Top-level help lists all 21 commands with aligned descriptions, compact usage, and dry-run guidance; it works without creating a workspace.
- `weekly_mode = "all"` preserves the default selection behavior; `short` filters by work type or an explicit excerpt label and an estimated time ceiling.
- Weekly aliases, scheduled picks, replacement picks, retries, and queue status respect the filter. Empty queues never fall back to books.
- `weekly_max_minutes = 0` removes the time ceiling while retaining the short-form filter. Otherwise unknown and zero reading times are excluded.
- Mount settings are previewed before applying; omitted model/privacy options preserve saved settings.

## Recent Progress

- Added descriptions to every registered command and a regression check for complete, aligned help within 80 columns.
- Added saved preferences and per-run selection overrides, including an `excerpt` work type.
- Added regression coverage for delivery retries, empty queues, no-write previews, overrides, repeated picks, replacement picks, validation, and config preservation.

## Validation

| Check | Result | Evidence |
| --- | --- | --- |
| `.venv/bin/python -m pytest -q` | passed | 95 tests and 15 subtests, 2026-09-17 |
| `git diff --check` | passed | No whitespace errors |
| Local mount and weekly preview | passed | Saved short mode; index, sent log, and delivery journal unchanged |

## Active Problems

- No blockers for the selection mode. Eligibility depends on indexed types and text-derived time estimates; it does not extract excerpts from full books.

## Decisions and Constraints

- Default to all works for existing installations; enable short mode explicitly.
- Stop an excluded pending delivery without changing its journal. Widen the filter explicitly only after reviewing that pending pick.
- Keep library files, index format, and delivery schedules intact. See `README.md` and `docs/automation.md` for operation.

## Next Action

1. Run `.venv/bin/librarian --help` for the command overview, then `.venv/bin/librarian COMMAND --help` for options.
