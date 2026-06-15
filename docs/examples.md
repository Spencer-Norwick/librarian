# Examples

Synthetic examples only. Real reading files belong directly in `library/`, not in this document or the repo.

## Ingest Filename

Inbox file:

```text
Ong_Walter_OralityAndLiteracy_1982_book.txt
```

Dry-run preview:

```bash
librarian ingest
```

Expected move after review:

```text
inbox/Ong_Walter_OralityAndLiteracy_1982_book.txt
library/OngWalter_OralityAndLiteracy_1982_book.txt
```

The original filename remains recorded in `library/index.md` and `_state/ingest-log.md`.

## Index Entry

`library/index.md` stays compact and human-readable:

```markdown
# Reading Library Index

## Recently Added

- Orality And Literacy — Ong, Walter (`OngWalter_OralityAndLiteracy_1982_book.txt`)

## Authors

### Ong, Walter

- **Orality And Literacy** (1982) — book
  File: `OngWalter_OralityAndLiteracy_1982_book.txt`
  Original filename: `Ong_Walter_OralityAndLiteracy_1982_book.txt`
  Status: unread
  Sent: never
  Reading time: ~1m
  Summary: Writing restructures consciousness.
  Primer prompts: None.
  Tags: book, language
  Related: None.
  Next action: needs_model
```

## Weekly Flow

Default weekly preview:

```bash
librarian weekly
```

Local delivery, only after review:

```bash
librarian weekly --apply --notify-mac --open --message-self
```

Email remains explicit optional behavior:

```bash
librarian weekly --email --apply
```
