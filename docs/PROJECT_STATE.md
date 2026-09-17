# Project State

Last updated: 2026-09-17
Repository: reading-librarian
Branch: main (integration target)
Last known-good commit: f7efd9f — Make command help and mount tests portable across CI environments.

## Current Objective

Keep reviewed development backed up and integrated on GitHub main. Safety/metadata and weekly/help consolidation, installed setup, onboarding, and failure recovery are locally and CI validated. The public delivery record is [pull request #1](https://github.com/Spencer-Norwick/librarian/pull/1); see [DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md).

## Verified State

- Both previous branches are integrated; help describes all 22 commands, including `edit`.
- Installed `init` uses bundled guidance and preserves existing setup files without a source checkout.
- Weekly short mode filters types and optionally duration; `0` disables the ceiling. Empty queues and excluded pending picks never fall back to books.
- Ingest, maintenance/repair, and OCR promotion recover from caught failures using no-overwrite moves; incomplete rollback reports preserved-file locations.
- Index writes preserve added dates, review notes, original filenames, and reading state. Automatic enrichment respects default approval requirements.
- Ambiguous delivery failures remain pending for review. Email retries reuse their original identity across week boundaries.
- Real reading files, local hooks/config, and delivery recipients remain untracked; development used temporary synthetic libraries only.

## Recent Progress

- Made checked push/merge part of routine delivery in repository and shared instructions; fixed environment-dependent mount tests and older-Python help alignment.
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
| Remote CI | passed | [Run 35271460793](https://github.com/Spencer-Norwick/librarian/actions/runs/35271460793): Linux/macOS, Python 3.11/3.14; suite and installed-package smoke checks passed |
| Live provider/OCR/delivery integrations | not run | Synthetic/mocked during development |

## Active Problems

- Independent human first-run testing remains before announcing a release.
- Windows remains unverified. Live provider, OCR-tool, and delivery behavior has not been exercised against real endpoints.
- Routine development must be pushed and merged after checks pass; local commits alone are not delivery. Version remains 0.1.0 until a separate alpha release is chosen.

## Decisions and Constraints

- Retain flat files, no database/wiki, dry-run defaults, explicit external-service consent, and no-overwrite operations.
- Rollback covers caught failures, not crash-proof filesystem transactions or concurrent writers. Keep independent backups.
- Keep real library files and ignored settings untouched. Do not run live delivery as validation.
- Routine GitHub push/merge is authorized as part of development completion. Independent human usability testing, versioned release publication, and deployment are separate steps. See [release.md](release.md).

## Next Action

1. Have an independent tester follow `docs/examples.md` from a fresh clone of GitHub main before announcing a versioned alpha release.
