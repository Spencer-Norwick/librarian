# Reading library workspace rules

- Keep the library simple and flat-file based. Do not add a database or wiki.
- Run librarian commands from this workspace directory. Start with
  `librarian mount --check`; configuration and file changes require reviewed
  dry-run previews before `--apply`.
- Do not delete reading files automatically or overwrite existing reading files
  or weekly drafts. Keep reading files directly in `library/`.
- Keep `library/index.md` compact and in its established heading and field format.
  Preserve original filenames in the index and `_state/ingest-log.md`.
- Prefer deterministic local operations. Extract metadata from filenames,
  embedded metadata, and local text before optional catalog lookup, OCR, or
  model assistance. Use `librarian ocr` for scanned-PDF copies, then review them
  before any promotion; never replace or delete original files automatically.
- Keep configured paths inside this workspace. Ignore symlinked inbox files.
- Before sending text excerpts to an external model, check the ignored local
  `_state/config.toml`. If `require_external_model_approval` is missing or true,
  ask for explicit approval. If false, the user has opted into the configured
  model hook; still preview broad batches before applying them.
- Keep provider-specific hooks and credentials in private local state. Hooks
  read a JSON payload on stdin and emit the documented JSON response on stdout.
  Test a hook using synthetic text before processing real reading files.
- Do not choose automated enrichment, digest automation that writes state, or
  external delivery without explicit user authorization. Prefer assisted
  privacy and notification-only automation when configuring a new workspace.
- Do not send email or Messages unless the user explicitly invokes the relevant
  configured sending command. Local weekly drafts do not require email.
- Do not publish reading files, private configuration, logs, or model hooks.

Full human and agent setup runbook:
https://github.com/Spencer-Norwick/librarian/blob/main/docs/mount.md
