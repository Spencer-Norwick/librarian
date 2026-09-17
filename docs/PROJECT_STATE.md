# Project State

Last updated: 2026-09-17
Repository: reading-librarian
Branch: codex/weekly-short-reads
Last known-good baseline: 415a4d7 — Make weekly delivery idempotent (85 tests passed before this change).

## Current Objective

Let users keep a mixed library while selecting only short readings for weekly delivery. Save the preference through the dry-run-first mount workflow and preserve existing model and delivery settings.

## Verified State

- `weekly_mode = "all"` preserves the default selection behavior; `short` filters by work type or an explicit excerpt label and an estimated time ceiling.
- Weekly aliases, scheduled picks, replacement picks, retries, and queue status respect the filter. Empty queues never fall back to books.
- `weekly_max_minutes = 0` removes the time ceiling while retaining the short-form filter. Otherwise unknown and zero reading times are excluded.
- Mount settings are previewed before applying; omitted model/privacy options preserve saved settings.

## Recent Progress

- Added saved preferences and per-run selection overrides, including an `excerpt` work type.
- Added regression coverage for delivery retries, empty queues, no-write previews, overrides, repeated picks, replacement picks, validation, and config preservation.

## Validation

| Check | Result | Evidence |
| --- | --- | --- |
| `.venv/bin/python -m pytest -q` | passed | 94 tests and 15 subtests, 2026-09-17 |
| `git diff --check` | passed | No whitespace errors |
| Local mount and weekly preview | passed | Saved short mode; index, sent log, and delivery journal unchanged |

## Active Problems

- No blockers for the selection mode. Eligibility depends on indexed types and text-derived time estimates; it does not extract excerpts from full books.

## Decisions and Constraints

- Default to all works for existing installations; enable short mode explicitly.
- Stop an excluded pending delivery without changing its journal. Widen the filter explicitly only after reviewing that pending pick.
- Keep library files, index format, and delivery schedules intact. See `README.md` and `docs/automation.md` for operation.

## Next Action

1. Preview future selections with `.venv/bin/librarian weekly`; use `--mode` and `--max-minutes` for temporary overrides.
