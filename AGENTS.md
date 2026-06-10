# AGENTS.md

Project rules for this reading librarian:

- Keep the project simple.
- Do not add a database.
- Do not create a wiki.
- Do not send email.
- Do not delete files automatically.
- Use dry-run by default for commands that modify files or Markdown.
- Keep `library/index.md` clean, compact, stable, and readable.
- Prefer deterministic file operations.
- Use model calls only when they materially improve metadata, summaries, tags, or reading prompts.
- Prefer local PDF/text metadata extraction before optional external catalog lookup.
- Write tests for destructive-path behavior.
- Preserve original filenames in `index.md` and `_state/ingest-log.md`.
- Keep actual reading files directly in `library/`.
- Keep sample/test reading files under `tests/fixtures/`, not root-level `*_test` folders.
- Keep configured paths inside the project root; do not let config paths escape with absolute paths or `..`.
- Never use overwrite-style writes for new library files or weekly draft files.
- Reserve planned ingest filenames before moving files so same-batch collisions cannot overwrite.
- Ignore symlinked inbox files unless there is a deliberate, reviewed reason to support them.
- Keep `index.md` in the established heading and field format; update parser/lint tests when the format changes.
