# Everyday usage

[← Back to the README](../README.md)

Run commands from your reading workspace. Preview a change, review it, then repeat with `--apply` to save it. `librarian COMMAND --help` lists the options for any command.

## Organize readings

Copy supported files into `inbox/`, then:

```bash
librarian ingest
librarian ingest --apply
librarian status
```

Applied ingest moves files into a flat `library/` and updates `library/index.md`. Original filenames stay in the index and ingest log. Existing destinations are never overwritten; symlinked inbox files are skipped.

| Format | Local extraction |
| --- | --- |
| PDF | Metadata and text with the optional `pdf` extra |
| EPUB, DOCX | Lightweight text extraction included |
| TXT, Markdown | Text extraction included |

Uncertain metadata is flagged for review. Local extraction cannot read image-only scans; those need OCR.

## Fix an entry

Check the entry's `Next action` in the index:

| Next action | What to do |
| --- | --- |
| `clean` | Metadata needs no repair; weekly picks also need notes |
| `needs_catalog` | Review identity; optionally try `librarian maintain --lookup` |
| `needs_ocr` | Preview `librarian ocr "Title"` |
| `needs_manual` | Inspect the entry's review notes and correct the problem |
| `needs_model` | Add reviewed notes yourself or use a configured model hook |

Correct identity and preview the corresponding filename change:

```bash
librarian edit "Reading With Care" --author "Example, Ada" --year 2026 --type essay
```

Repeat with `--apply` when the proposed change is right. `librarian maintain` previews wider metadata and filename repairs; `librarian lint` checks index structure and file consistency.

Metadata work starts with filenames, embedded metadata, and local text. Optional Open Library lookup can repair weak identity metadata; it sends bibliographic queries outside your machine. Models are for summaries, tags, and reading questions after usable text is available.

For scanned PDFs, install OCRmyPDF and its system dependencies separately. `librarian ocr "Title"` previews repair; adding `--apply` writes a copy under `_output/ocr/`. It does not replace the library original. The default `ocrmypdf --skip-text` handles image-only pages, not a broken existing text layer. Review the result before any deliberate promotion or replacement.

## Prepare a weekly pick

A weekly-ready entry needs a recognizable title and author, a useful summary, reading questions, no unresolved review notes, and `Next action: clean`. Ingest alone does not prepare all of these.

**Without a model:** edit the entry's `Summary` and `Primer prompts` fields in `library/index.md`. Separate questions with ` | `. Once you have resolved the review notes, set `Review notes: None.` and `Next action: clean`. Preserve the other fields and headings, then run `librarian lint`. The [sample walkthrough](examples.md#3-give-yourself-something-to-read) shows exact lines.

**With a model:** first [configure and test your own hook](mount.md#optional-model-assistance), then explicitly preview `librarian enrich "Title"`. Review the proposal before repeating with `--apply`. Even the preview executes the hook and may send text to its provider.

```bash
librarian weekly
librarian weekly --apply
```

The first command shows a draft. The second writes it under `_output/weekly-read-drafts/`, updates sent state, and appends the sent log. “Sent” means the pick was issued; it does not imply email delivery. If no entry is ready, the command explains what needs attention.

### Prefer shorter readings

```bash
librarian mount --weekly-mode short --weekly-max-minutes 0
librarian mount --weekly-mode short --weekly-max-minutes 0 --apply
```

Short mode admits essays, articles, stories, papers, chapters, and excerpts. A book qualifies only when explicitly labeled `excerpt` in its title or tags. It does not split books into excerpts.

`0` removes the time ceiling. Use a positive value to limit estimated minutes; entries with unknown or zero times are then excluded. On a new workspace the ceiling is 60 minutes. In `all` mode the ceiling has no effect. Empty queues stop without substituting a book.

For one preview, use `librarian weekly --mode short --max-minutes 30`. Return to all types by previewing `librarian mount --weekly-mode all`, then adding `--apply`. These config changes preserve your model and delivery settings.

### Finish, skip, or choose another

```bash
librarian reply read      # Mark the latest pick read
librarian reply skip      # Mark it skipped
librarian reply new       # Skip it and prepare another
```

These are previews. Add `--apply` to save. For schedules, notifications, Messages, email, and retries, see [automation and delivery](automation.md).

## Command reference

```bash
librarian --help
librarian ingest --help
```

| Task | Commands |
| --- | --- |
| Setup | `mount`, `init` |
| Organize | `ingest`, `edit`, `maintain`, `reindex` |
| Inspect | `status`, `lint` |
| Prepare | `enrich`, `ocr`, `repair` |
| Read | `weekly`, `weekly-pick`, `draft-digest`, `reply`, `mark-read`, `mark-skip` |
| Automate and deliver | `daily`, `weekly-due`, `resend-latest`, `notify`, `send-digest` |

`reading-librarian` is an alias for `librarian` if that name conflicts with another installed tool.
