# Project State

Last updated: 2026-09-17
Repository: reading-librarian
Branch: codex/public-alpha-readiness
Last known-good commit: cda6878 — Restore library consistency after repair failures and preserve uncertain delivery state.

## Current Objective

Public alpha development is complete on the review branch: consolidate safety/metadata and weekly/help work, fix installed setup, document first-run usage, and verify failure recovery using synthetic libraries. See [DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md).

## Verified State

- Both previous branches are integrated; help describes all 22 commands, including `edit`.
- Installed `init` uses bundled guidance and preserves existing setup files without a source checkout.
- Weekly short mode filters types and optionally duration; `0` disables the ceiling. Empty queues and excluded pending picks never fall back to books.
- Ingest, maintenance/repair, and OCR promotion recover from caught failures using no-overwrite moves; incomplete rollback reports preserved-file locations.
- Index writes preserve added dates, review notes, original filenames, and reading state. Automatic enrichment respects default approval requirements.
- Ambiguous delivery failures remain pending for review. Email retries reuse their original identity across week boundaries.
- Real reading files, local hooks/config, and delivery recipients remain untracked; development used temporary synthetic libraries only.

## Recent Progress

- Closed maintenance, source-removal, absent-state ingest, and OCR promotion recovery gaps with regressions.
- Added onboarding, verified synthetic walkthrough, contribution/security guidance, unreleased notes, and a release checklist.
- Built/inspected sdist and wheel; exercised installed commands after removing the build checkout.
- Restored Linux/macOS CI with Python 3.11/3.14 and installed-package checks.

## Validation

| Check | Result | Evidence |
| --- | --- | --- |
| `python -m pytest -q` | passed | 124 tests and 19 subtests; macOS/Python 3.14, 2026-09-17 |
| Same suite from `git archive HEAD` | passed | 124 tests and 19 subtests without ignored files or local state |
| `python scripts/check-installed-package.py` | passed | sdist/wheel allowlists; fresh install; both aliases, setup, previews, ingest, local short weekly, lint |
| `docs/examples.md` workflow | passed | Synthetic ingest → local test-hook enrichment → maintain → short draft; no external delivery |
| `detect-secrets scan --all-files --no-verify` on exported historical text blobs | passed | 203 historical text blobs; no findings. Automated scanning is not a guarantee |
| Compilation and `git diff --check` | passed | No compilation or whitespace errors |
| Remote CI and live provider/OCR/delivery integrations | not run | CI awaits publication; integrations synthetic/mocked during development |

## Active Problems

- Independent human first-run testing remains before announcing a release.
- Python 3.11/Linux are configured in CI but not locally validated; Windows is unverified.
- Public `main` remains unchanged. The review branch is not pushed/released; version stays 0.1.0 until a fresh alpha version/tag is chosen.

## Decisions and Constraints

- Retain flat files, no database/wiki, dry-run defaults, explicit external-service consent, and no-overwrite operations.
- Rollback covers caught failures, not crash-proof filesystem transactions or concurrent writers. Keep independent backups.
- Keep real library files and ignored settings untouched. Do not run live delivery as validation.
- Separate completed development from human testing and authorized publication. See [release.md](release.md).

## Next Action

1. Review `git diff main...codex/public-alpha-readiness` before following the release checklist.
