# Reading library workspace

This directory is your private, flat-file reading library. The `librarian` command
is installed separately; this workspace does not contain the application's source.
Run commands from this directory so they use this library's local configuration.

- `inbox/`: new reading files awaiting review and ingest.
- `library/`: reading files and the compact `index.md`.
- `_state/`: private configuration, logs, and optional model hooks.
- `_output/`: generated weekly drafts and OCR copies.
- `_quarantine/`: files reserved for manual review.

Start with `librarian mount --check`, then `librarian --help` for the command list.
`librarian mount` previews configuration; add `--apply` to save reviewed settings.
Put a file in `inbox/`, preview `librarian ingest`, then use
`librarian ingest --apply` to move and index it. `librarian maintain` previews
metadata and filename cleanup. Modification commands use dry-run previews unless
`--apply` is supplied; `init` itself creates missing setup files.

Weekly picks need indexed summaries and reading prompts. Configure an optional
model hook only after reviewing the privacy settings, or add those fields manually
as documented. `librarian enrich` previews enrichment and `librarian weekly`
previews an eligible pick. `librarian weekly --apply` saves a local draft;
notifications, opening files, Messages, and email require explicit delivery flags.
For short works use `librarian weekly --mode short --max-minutes 0`; the zero
removes the time ceiling while retaining the short-work filter.

Read the [setup runbook](https://github.com/Spencer-Norwick/librarian/blob/main/docs/mount.md)
and [command documentation](https://github.com/Spencer-Norwick/librarian#readme)
for supported formats, enrichment, delivery, and configuration details.
Keep this workspace and private reading files out of public repositories.
