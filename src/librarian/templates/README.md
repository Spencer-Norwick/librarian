# Your reading library

Drop readings into `inbox/`, preview their names, and keep them in one plain-file library.

Run commands **from this directory**. The `librarian` tool is installed separately; this folder contains your readings and local settings.

```bash
librarian mount --check
librarian ingest          # Preview files waiting in inbox/
librarian ingest --apply  # Move them into library/ and update the index
librarian status
```

Open **`library/index.md`** in any text editor or Markdown viewer. The reading files are beside it.

| Folder | What belongs here |
| --- | --- |
| `inbox/` | New readings |
| `library/` | Readings and `index.md` |
| `_state/` | Local settings, logs, and optional model hooks |
| `_output/` | Weekly drafts and OCR copies |
| `_quarantine/` | Files set aside for review |

`mount` previews settings; `mount --apply` saves them. File and Markdown changes also preview before `--apply`. Initial setup with `init` creates missing files immediately and preserves existing ones.

## Choose a reading

Weekly picks need indexed summaries and reading prompts. Add reviewed notes yourself or configure an optional model hook; ingest alone does not generate them.

```bash
librarian weekly          # Preview a ready pick
librarian weekly --apply  # Save a local draft and mark the pick sent
```

Saving a draft sends no message or email. Delivery requires explicit flags. Model enrichment may send excerpts to its provider even in a preview.

[Everyday usage](https://github.com/Spencer-Norwick/librarian/blob/main/docs/usage.md) · [Setup and models](https://github.com/Spencer-Norwick/librarian/blob/main/docs/mount.md) · [All commands](https://github.com/Spencer-Norwick/librarian/blob/main/docs/usage.md#command-reference)

Keep this workspace out of public repositories and back up your readings and state.
