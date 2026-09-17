# Changelog

## Unreleased — public alpha readiness

- Integrate ingest rollback, external-model approval checks, interruption-aware weekly delivery, and index-field preservation.
- Improve metadata repair, garbled-PDF detection, and explicit identity correction through `librarian edit`.
- Add short-form weekly selection with an optional reading-time ceiling and readable command help.
- Make workspace initialization available from an installed package.
- Roll back failed maintenance and repair renames, preserve uncertain delivery outcomes for review, and reuse the original email retry identity.
- Clean up transaction-created copies and metadata when ingest fails, preserving original reading files.
- Add onboarding, synthetic first-run validation, contribution/security guidance, and automated validation.

This work prepares the next alpha; it is not a published release. Core workflows remain flat-file based, and optional providers/delivery services require deliberate setup.
