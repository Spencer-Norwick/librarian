# AGENTS.md

Project rules for this reading librarian:

- Keep the project simple.
- Do not add a database.
- Do not create a wiki.
- Do not send email unless the user explicitly invokes a configured email-sending command.
- Do not delete files automatically.
- Use dry-run by default for commands that modify files or Markdown.
- Keep `library/index.md` clean, compact, stable, and readable.
- Prefer deterministic file operations.
- Use model calls only when they materially improve metadata, summaries, tags, or reading prompts.
- Prefer local PDF/text metadata extraction before optional external catalog lookup.
- Follow the metadata pipeline: filename parse, embedded metadata, local text extraction, catalog lookup for weak metadata, OCR for scanned content, then model help only for semantic enrichment.
- Write tests for destructive-path behavior.
- Preserve original filenames in `index.md` and `_state/ingest-log.md`.
- Keep actual reading files directly in `library/`.
- Keep sample/test reading files under `tests/fixtures/`, not root-level `*_test` folders.
- Keep configured paths inside the project root; do not let config paths escape with absolute paths or `..`.
- Never use overwrite-style writes for new library files or weekly draft files.
- Reserve planned ingest filenames before moving files so same-batch collisions cannot overwrite.
- Ignore symlinked inbox files unless there is a deliberate, reviewed reason to support them.
- Keep `index.md` in the established heading and field format; update parser/lint tests when the format changes.

Mount protocol for new users or forks:

- Start with `librarian mount --check`.
- Treat `librarian mount` as dry-run setup preview.
- Write local config only with `librarian mount --apply`.
- Ask the user before choosing automatic model enrichment, email delivery, or write-state digest automation.
- Prefer `privacy=assisted` and `digest=notify`.
- Before sending text excerpts to an external model, check `_state/config.toml` for `require_external_model_approval`; if it is missing or true, ask for explicit user approval.
- If `require_external_model_approval = false`, the user has opted into external model enrichment for the configured `model_command`; still use dry-run review before broad batches.
- If model enrichment is desired, create the provider-specific hook in ignored local state such as `_state/model-enrich-local`, not in the public repo.
- The hook must read the librarian JSON payload from stdin and print the documented enrichment JSON to stdout.
- Test model hooks with synthetic non-library text before asking to enrich real files.
- Use `librarian ocr` for scanned-PDF repair; do not replace or delete library files automatically.
- See `docs/mount.md` for the full human and agent runbook.
- See `docs/automation.md` for daily, weekly, and reply automation setup.
