from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import sys
import tomllib
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


WORK_TYPES = {
    "book",
    "essay",
    "article",
    "paper",
    "chapter",
    "story",
    "poem",
    "letters",
    "lecture",
    "notes",
    "unknown",
}
SUPPORTED_EXTENSIONS = {".pdf", ".epub", ".txt", ".md", ".docx"}
DEFAULT_TAGS = ["reading"]


@dataclass
class Config:
    inbox: Path
    library: Path
    index: Path
    state: Path
    ingest_log: Path
    sent_log: Path
    quarantine: Path
    drafts: Path
    supported_extensions: set[str] = field(default_factory=lambda: set(SUPPORTED_EXTENSIONS))
    reading_words_per_minute: int = 250
    max_filename_stem_chars: int = 96
    use_catalog_lookup: bool = False
    catalog_timeout_seconds: float = 5.0


@dataclass
class WorkEntry:
    author: str = "Unknown"
    title: str = "Untitled"
    year: str = "nd"
    work_type: str = "unknown"
    filename: str = ""
    original_filename: str = ""
    status: str = "unread"
    sent: str = "never"
    reading_time: str = "~0m"
    summary: str = "Needs review."
    tags: list[str] = field(default_factory=lambda: list(DEFAULT_TAGS))
    related: str = "None."
    needs_review: list[str] = field(default_factory=list)
    next_action: str = "clean"
    added: str = ""

    @property
    def author_key(self) -> str:
        return author_sort_key(self.author)

    @property
    def display_title(self) -> str:
        return self.title or "Untitled"


@dataclass
class CatalogMatch:
    title: str = ""
    author: str = ""
    year: str = ""
    note: str = ""


@dataclass
class RenamePlan:
    source_name: str
    target_name: str


@dataclass
class MaintenancePlan:
    entries: list[WorkEntry]
    renames: list[RenamePlan]


@dataclass
class DigestPlan:
    entry: WorkEntry
    draft_path: Path
    body: str


def project_config(root: Path) -> Config:
    config_path = root / "_state" / "config.toml"
    raw: dict = {}
    if config_path.exists():
        raw = tomllib.loads(config_path.read_text(encoding="utf-8"))

    paths = raw.get("paths", {})
    behavior = raw.get("behavior", {})
    supported = behavior.get("supported_extensions", sorted(SUPPORTED_EXTENSIONS))

    def p(key: str, default: str) -> Path:
        return safe_project_path(root, paths.get(key, default))

    state = p("state", "_state")
    library = p("library", "library")
    return Config(
        inbox=p("inbox", "inbox"),
        library=library,
        index=p("index", "library/index.md"),
        state=state,
        ingest_log=p("ingest_log", "_state/ingest-log.md"),
        sent_log=p("sent_log", "_state/sent-log.md"),
        quarantine=p("quarantine", "_quarantine"),
        drafts=p("weekly_read_drafts", "_output/weekly-read-drafts"),
        supported_extensions={ext.lower() for ext in supported},
        reading_words_per_minute=int(behavior.get("reading_words_per_minute", 250)),
        max_filename_stem_chars=int(behavior.get("max_filename_stem_chars", 96)),
        use_catalog_lookup=bool(behavior.get("use_catalog_lookup", False)),
        catalog_timeout_seconds=float(behavior.get("catalog_timeout_seconds", 5.0)),
    )


def ensure_dirs(config: Config) -> None:
    for path in [config.inbox, config.library, config.state, config.quarantine, config.drafts]:
        path.mkdir(parents=True, exist_ok=True)


def safe_project_path(root: Path, value: str) -> Path:
    root = root.resolve()
    candidate = (root / value).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError(f"Configured path escapes project root: {value}")
    return candidate


def init_project(root: Path) -> int:
    config = project_config(root)
    ensure_dirs(config)
    write_if_missing(root / "AGENTS.md", agents_markdown())
    write_if_missing(root / "README.md", readme_markdown())
    write_if_missing(root / "pyproject.toml", pyproject_text())
    write_if_missing(config.state / "config.toml", sample_config())
    write_if_missing(config.ingest_log, "# Ingest Log\n\n")
    write_if_missing(config.sent_log, "# Sent Log\n\n")
    write_if_missing(config.index, render_index([]))
    print("Initialized reading librarian workspace.")
    return 0


def write_if_missing(path: Path, content: str) -> None:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def sample_config() -> str:
    return """[paths]
inbox = "inbox"
library = "library"
index = "library/index.md"
state = "_state"
ingest_log = "_state/ingest-log.md"
sent_log = "_state/sent-log.md"
quarantine = "_quarantine"
weekly_read_drafts = "_output/weekly-read-drafts"

[behavior]
supported_extensions = [".pdf", ".epub", ".txt", ".md", ".docx"]
reading_words_per_minute = 250
max_filename_stem_chars = 96
use_model_assistance = false
use_catalog_lookup = false
catalog_timeout_seconds = 5
"""


def pyproject_text() -> str:
    return Path(__file__).resolve().parents[2].joinpath("pyproject.toml").read_text(encoding="utf-8")


def agents_markdown() -> str:
    return """# AGENTS.md

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
"""


def readme_markdown() -> str:
    return """# Reading Librarian

A small local flat-file CLI for managing a reading backlog.

It ingests supported files from `inbox/`, proposes deterministic filenames, moves them into a flat `library/` folder only with `--apply`, and maintains one human-readable `library/index.md`.

## Install for Local Development

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

The MVP has no required runtime dependencies. Install `pypdf` only if you want local PDF metadata/text extraction:

```bash
python -m pip install -e '.[pdf]'
```

You can also run without installing:

```bash
PYTHONPATH=src python3 -m librarian --help
```

## Project Layout

Runtime folders:

- `inbox/`: files waiting to be ingested
- `library/`: flat library files plus `index.md`
- `_state/`: config and Markdown logs
- `_quarantine/`: files needing manual review
- `_output/weekly-read-drafts/`: generated weekly draft files

Test/sample files live under `tests/fixtures/`. Do not put test inboxes or test libraries at the project root.

## Commands

```bash
librarian init
librarian ingest
librarian ingest --lookup
librarian ingest --apply
librarian lint
librarian lint --apply
librarian reindex
librarian reindex --lookup
librarian reindex --apply
librarian maintain
librarian maintain --lookup
librarian maintain --apply
librarian digest
librarian digest --notify
librarian digest --email --apply
librarian weekly-pick
librarian weekly-pick --apply
librarian list
librarian search "query"
librarian mark-read "Title or filename" --apply
librarian skip "Title or filename" --apply
```

Commands that modify files or Markdown are dry-run by default. Use `--apply` to write changes.

`lint --apply` only repairs missing index entries for files that are already in `library/`; it does not rename files, delete files, or resolve every lint issue automatically.

`ingest --lookup`, `reindex --lookup`, and `maintain --lookup` use Open Library as an optional catalog fallback for weak metadata. Local filename/PDF/text extraction is tried first, and lookup is off by default.

`maintain` is the normal repair workflow. It previews safe filename repairs, rebuilds `index.md`, and reports the next action for remaining weak entries. It is dry-run by default.

`digest` is the weekly read workflow. It renders a draft by default, writes the draft and sent state with `--apply`, prints an automation-friendly notification with `--notify`, and sends email only with `--email --apply` after email environment variables are configured. `weekly-pick` remains as a compatibility alias.

## Metadata Pipeline

The librarian uses the cheapest reliable step first:

1. Parse filenames.
2. Read embedded file metadata.
3. Extract local text with command-line libraries such as `pypdf`.
4. Use catalog lookup for weak title, author, or year metadata.
5. Use OCR only when a file has no extractable text and content-level work is needed.
6. Use model help only for semantic improvements such as summaries, tags, related works, and reading prompts.

Each index entry includes `Next action` so humans and agents know what to do next:

- `clean`: no immediate automated repair is needed.
- `needs_catalog`: run lookup before OCR or model work.
- `needs_ocr`: metadata is usable, but content extraction needs OCR.
- `needs_manual`: automated repair was not confident enough.
- `needs_model`: text and metadata are available; a model could improve summaries, tags, or prompts.

## Filename Convention

```text
LastFirst_Title_Subtitle_Year_WorkType.ext
```

Examples:

```text
DebordGuy_SocietyOfTheSpectacle_1967_book.pdf
Unknown_NotesOnCybernetics_nd_article.pdf
```

Collisions never overwrite existing files. A short stable hash suffix is appended when needed.

Ingest also reserves planned filenames before applying a batch, so two inbox files that resolve to the same target name are both kept.

## Safety

- New library files and weekly drafts are created with no-overwrite file operations.
- Supported files in `inbox/` are moved only by `ingest --apply`.
- After `librarian init`, `index.md`, ingest logs, sent logs, and weekly draft state are edited only by commands run with `--apply`.
- Configured paths are kept inside the project root.
- Symlinked inbox files are ignored.
- No SQL, database, wiki, or model call is used in the MVP.
- Email is sent only when explicitly requested with `digest --email --apply` and configured through environment variables.
- Optional catalog lookup uses Open Library only when explicitly requested with `--lookup` or enabled in `_state/config.toml`.

Email delivery uses Resend's HTTPS API without a required package dependency. Configure it with:

```bash
export RESEND_API_KEY="..."
export LIBRARIAN_EMAIL_FROM="Reading Librarian <reads@example.com>"
export LIBRARIAN_EMAIL_TO="you@example.com"
```

## Scheduling Examples

The CLI does not install scheduled jobs automatically.

### cron

```cron
0 8 * * * cd /path/to/reading-librarian && librarian ingest --apply
0 9 * * 1 cd /path/to/reading-librarian && librarian lint
0 10 * * 1 cd /path/to/reading-librarian && librarian digest --apply
```

### macOS launchd

Create `~/Library/LaunchAgents/local.reading-librarian.ingest.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>local.reading-librarian.ingest</string>
  <key>ProgramArguments</key>
  <array>
    <string>/path/to/venv/bin/librarian</string>
    <string>ingest</string>
    <string>--apply</string>
  </array>
  <key>WorkingDirectory</key>
  <string>/path/to/reading-librarian</string>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>8</integer>
    <key>Minute</key>
    <integer>0</integer>
  </dict>
</dict>
</plist>
```

Load it manually when ready:

```bash
launchctl load ~/Library/LaunchAgents/local.reading-librarian.ingest.plist
```

## Notes

- No SQL or database is used.
- No wiki or author-folder structure is created.
- Real email is sent only by `digest --email --apply` with email environment variables configured.
- Scanned or unreadable PDFs are marked for review instead of silently passing.
"""


def supported_files(config: Config, folder: Path) -> list[Path]:
    if not folder.exists():
        return []
    return sorted(
        path
        for path in folder.iterdir()
        if path.is_file() and not path.is_symlink() and path.suffix.lower() in config.supported_extensions
    )


def command_ingest(args: argparse.Namespace, root: Path) -> int:
    config = project_config(root)
    ensure_dirs(config)
    entries = read_index(config.index)
    existing_files = {entry.filename for entry in entries}
    reserved_names = {path.name for path in config.library.iterdir() if path.is_file()} if config.library.exists() else set()
    plans: list[tuple[Path, Path, WorkEntry]] = []
    use_catalog_lookup = args.lookup or config.use_catalog_lookup

    for source in supported_files(config, config.inbox):
        entry = infer_entry(source, config, use_catalog_lookup=use_catalog_lookup)
        target_name = unique_filename(config.library, make_filename(entry, config), source, reserved_names)
        reserved_names.add(target_name)
        entry.filename = target_name
        target = config.library / target_name
        if target_name in existing_files:
            entry.needs_review.append("Already indexed filename collision.")
        plans.append((source, target, entry))

    if not plans:
        print("No supported files found in inbox.")
        return 0

    for source, target, entry in plans:
        marker = "REVIEW" if entry.needs_review else "OK"
        print(f"[dry-run] {marker}: {source.name} -> {target.relative_to(root)}")
        if entry.needs_review:
            print(f"  Needs review: {'; '.join(entry.needs_review)}")

    if not args.apply:
        print("Dry run only. Re-run with --apply to move files and update Markdown.")
        return 0

    for source, target, entry in plans:
        move_without_overwrite(source, target)
        entries = upsert_entry(entries, entry)
        append_ingest_log(config.ingest_log, source.name, entry, target)

    write_index(config.index, entries)
    print(f"Applied ingest for {len(plans)} file(s).")
    return 0


def infer_entry(path: Path, config: Config, use_catalog_lookup: bool = False) -> WorkEntry:
    text = ""
    metadata: dict[str, str] = {}
    review: list[str] = []
    if path.suffix.lower() == ".pdf":
        metadata, text, pdf_review = extract_pdf(path)
        review.extend(pdf_review)
    elif path.suffix.lower() in {".txt", ".md"}:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            review.append(f"Could not read text: {exc}")
    else:
        review.append(f"Text extraction not implemented for {path.suffix.lower()}.")

    guessed = infer_from_name(path.stem)
    surname_hint = guessed.get("surname_hint") or path.stem.split("_", 1)[0]
    text_author = infer_author_from_text(text, surname_hint)
    text_identity = infer_identity_from_front_matter(text)
    if not text_author:
        text_author = text_identity.get("author", "")
    guessed_title = guessed.get("title") or path.stem
    if should_use_text_title(guessed_title, guessed.get("author", ""), text_identity.get("title", "")):
        guessed_title = text_identity["title"]
    title_source = metadata.get("title") if useful_pdf_title(metadata.get("title", "")) else ""
    title = clean_title(title_source or guessed_title)
    author = choose_author(guessed.get("author", ""), metadata.get("author", ""), text_author)
    title = remove_author_prefix_from_title(title, author)
    year = first_known_year(metadata.get("year", ""), guessed.get("year", ""), infer_year_from_text(text))
    if use_catalog_lookup and should_lookup_catalog(title, author, year):
        catalog = lookup_catalog_metadata(title, author, config)
        if catalog.author and author_needs_catalog_author(author, catalog.author):
            author = catalog.author
        if not year and catalog.year:
            year = catalog.year
        if catalog.note:
            review.append(catalog.note)
    year = year or "nd"
    guessed_work_type = clean_work_type(guessed.get("work_type", ""))
    work_type = guessed_work_type if guessed_work_type != "unknown" else infer_work_type(path, text)
    work_type = clean_work_type(work_type)

    if author == "Unknown":
        review.append("Author could not be inferred.")
    elif "," not in author:
        review.append("Author could not be fully inferred.")
    if title == "Untitled":
        review.append("Title could not be inferred.")
    if path.suffix.lower() == ".pdf" and not text.strip():
        review.append("No extractable PDF text found; may need OCR.")

    word_count = len(re.findall(r"\b\w+\b", text))
    reading_minutes = max(1, round(word_count / config.reading_words_per_minute)) if word_count else 0
    summary = summarize_text(title, text, review)
    tags = infer_tags(title, text, work_type)
    next_action = classify_next_action(
        author=author,
        title=title,
        year=year,
        text=text,
        review=review,
        summary=summary,
    )

    return WorkEntry(
        author=author,
        title=title,
        year=year,
        work_type=work_type,
        filename="",
        original_filename=path.name,
        reading_time=f"~{reading_minutes}m",
        summary=summary,
        tags=tags,
        related="None.",
        needs_review=dedupe(review),
        next_action=next_action,
        added=today(),
    )


def extract_pdf(path: Path) -> tuple[dict[str, str], str, list[str]]:
    review: list[str] = []
    metadata: dict[str, str] = {}
    text_parts: list[str] = []
    reader_class = None
    try:
        from pypdf import PdfReader  # type: ignore

        reader_class = PdfReader
    except Exception:
        try:
            from PyPDF2 import PdfReader  # type: ignore

            reader_class = PdfReader
        except Exception:
            review.append("No local PDF parser installed; install optional dependency `pypdf`.")
            return metadata, "", review

    try:
        reader = reader_class(str(path))
        info = getattr(reader, "metadata", None) or {}
        title = str(info.get("/Title") or info.get("title") or "").strip()
        author = str(info.get("/Author") or info.get("author") or "").strip()
        if title:
            metadata["title"] = title
        if author:
            metadata["author"] = author
        for page in getattr(reader, "pages", []):
            try:
                text_parts.append(page.extract_text() or "")
            except Exception:
                continue
    except Exception as exc:
        review.append(f"PDF extraction failed: {exc}")
    return metadata, "\n".join(text_parts), review


def infer_from_name(stem: str) -> dict[str, str]:
    archive = infer_from_archive_stem(stem)
    if archive:
        return archive

    comma_title = infer_from_comma_title_stem(stem)
    if comma_title:
        return comma_title

    structured = infer_from_structured_stem(stem)
    if structured:
        return structured

    normalized = re.sub(r"[_\-]+", " ", stem)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    tokens = normalized.split()
    result: dict[str, str] = {}
    if not tokens:
        return result

    for index, token in enumerate(tokens):
        if re.fullmatch(r"(1[5-9]\d{2}|20\d{2})", token):
            result["year"] = token
            before = tokens[:index]
            after = tokens[index + 1 :]
            if after:
                result["work_type"] = clean_work_type(after[0].lower())
            if len(before) >= 3 and looks_like_name(before[0]) and looks_like_name(before[1]):
                result["author"] = f"{before[0]}, {before[1]}"
                result["title"] = " ".join(before[2:])
            elif len(before) >= 2 and looks_like_author_key(before[0]):
                result["author"] = split_author_key(before[0])
                result["title"] = " ".join(before[1:])
            else:
                result["title"] = " ".join(before)
            return result

    result["title"] = normalized
    return result


def infer_from_archive_stem(stem: str) -> dict[str, str]:
    parts = [part.strip() for part in re.split(r"\s+--\s+", stem) if part.strip()]
    if len(parts) < 2:
        return {}
    result: dict[str, str] = {
        "title": clean_title(re.sub(r"\([^)]*\)", "", parts[0])),
    }
    author = author_from_comma_chunk(parts[1])
    if author:
        result["author"] = author
        result["surname_hint"] = author.split(",", 1)[0]
    year_match = re.search(r"\b(1[5-9]\d{2}|20\d{2})\b", parts[0])
    if year_match:
        result["year"] = year_match.group(1)
    return result


def infer_from_comma_title_stem(stem: str) -> dict[str, str]:
    match = re.match(r"^\s*([^,]+),\s+(.+?)\s+-\s+(.+?)(?:\s+-\s+[^-]+)?\s*$", stem)
    if not match:
        return {}
    return {
        "author": f"{match.group(1).strip()}, {match.group(2).strip()}",
        "surname_hint": match.group(1).strip(),
        "title": match.group(3).strip(),
    }


def author_from_comma_chunk(value: str) -> str:
    parts = [part.strip() for part in value.split(",") if part.strip()]
    if len(parts) < 2:
        return ""
    first = parts[1]
    if re.fullmatch(r"\d{4}(?:-\d{4})?", first) or first.lower() in {"author", "editor", "translator"}:
        return ""
    return f"{parts[0]}, {first}"


def infer_from_structured_stem(stem: str) -> dict[str, str]:
    parts = [part.strip() for part in stem.split("_") if part.strip()]
    year_index = next((index for index, part in enumerate(parts) if re.fullmatch(r"(1[5-9]\d{2}|20\d{2}|nd)", part)), None)
    if year_index is None:
        return {}

    before = parts[:year_index]
    after = parts[year_index + 1 :]
    if not before:
        return {"year": parts[year_index]}

    result: dict[str, str] = {"year": parts[year_index], "surname_hint": before[0]}
    if after:
        result["work_type"] = clean_work_type(after[0].lower())

    if len(before) >= 3 and looks_like_name(before[0]) and looks_like_name(before[1]):
        result["author"] = f"{before[0]}, {before[1]}"
        result["title"] = humanize_title(" ".join(before[2:]))
    elif len(before) >= 2:
        result["author"] = split_author_key(before[0]) if looks_like_author_key(before[0]) else before[0]
        result["title"] = humanize_title(" ".join(before[1:]))
    else:
        result["title"] = humanize_title(before[0])
    return result


def humanize_title(value: str) -> str:
    value = re.sub(r"([a-z])([A-Z])", r"\1 \2", value)
    value = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def useful_pdf_title(value: str) -> bool:
    value = clean_title(value)
    lower = value.lower()
    if lower in {"title", "untitled"}:
        return False
    if lower.startswith("microsoft word -"):
        return False
    if re.fullmatch(r"document\d*", lower):
        return False
    return bool(value)


def infer_author_from_text(text: str, surname_hint: str) -> str:
    if not text.strip() or not surname_hint:
        return ""
    surname = re.escape(surname_hint.strip())
    sample = re.sub(r"\s+", " ", text[:8000])
    name_word = r"[A-Z][A-Za-z'.]+"

    by_match = re.search(rf"\bby\s+({name_word}(?:\s+{name_word}){{1,2}})\b", sample)
    if by_match:
        candidate = normalize_author_candidate(by_match.group(1), surname_hint)
        if candidate and candidate.lower().endswith(surname_hint.lower()):
            return candidate

    comma_match = re.search(rf"\b{surname},\s+({name_word}(?:\s+{name_word}){{0,2}})\b", sample)
    if comma_match:
        return normalize_author_candidate(f"{comma_match.group(1)} {surname_hint}", surname_hint)

    for previous_words in [1, 2]:
        direct_match = re.search(rf"\b((?:{name_word}\s+){{{previous_words}}}{surname})\b", sample)
        if direct_match:
            candidate = normalize_author_candidate(direct_match.group(1), surname_hint)
            if candidate:
                return candidate
    return ""


def infer_identity_from_front_matter(text: str) -> dict[str, str]:
    lines = front_matter_lines(text)
    for index, line in enumerate(lines[:25]):
        if not probable_person_name_line(line):
            continue
        title = front_matter_title_before(lines, index)
        author = normalize_author_candidate(line)
        if title and author:
            return {"title": title, "author": author}
    return {}


def front_matter_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw_line in text.splitlines()[:80]:
        line = clean_title(raw_line)
        if not line:
            continue
        if front_matter_noise_line(line):
            continue
        lines.append(line)
    return lines


def front_matter_noise_line(line: str) -> bool:
    lower = line.lower()
    if len(line) <= 1:
        return True
    return any(
        marker in lower
        for marker in [
            "library of congress",
            "cataloging in publication",
            "isbn",
            "all rights reserved",
            "printed in",
            "copyright",
            "©",
        ]
    )


def probable_person_name_line(line: str) -> bool:
    words = re.findall(r"[A-Za-z'.]+", line)
    if not 2 <= len(words) <= 4:
        return False
    if line != line.upper():
        return False
    lower = line.lower()
    blocked = {"contents", "preface", "chapter", "press", "university", "library", "inc", "hall"}
    return not any(word.lower().strip(".'") in blocked for word in words) and " and " not in lower


def front_matter_title_before(lines: list[str], author_index: int) -> str:
    title_lines: list[str] = []
    for line in reversed(lines[max(0, author_index - 4) : author_index]):
        if not front_matter_title_line(line):
            break
        title_lines.insert(0, line)
    return clean_title(" ".join(title_lines))


def front_matter_title_line(line: str) -> bool:
    words = re.findall(r"[A-Za-z0-9]+", line)
    if not words or len(words) > 12:
        return False
    lower = line.lower()
    blocked = ["publisher", "university", "press", "series", "contents", "preface"]
    return not any(marker in lower for marker in blocked)


def should_use_text_title(guessed_title: str, guessed_author: str, text_title: str) -> bool:
    if not text_title:
        return False
    title_key = normalize_lookup_text(guessed_title)
    compact_key = title_key.replace(" ", "")
    if title_key in {"untitled", "unknown"}:
        return True
    if re.fullmatch(r"[a-f0-9]{16,}", compact_key):
        return True
    return clean_author(guessed_author or "Unknown") == "Unknown" and title_key.startswith("unknown ")


def choose_author(guessed_author: str, metadata_author: str, text_author: str) -> str:
    guessed = clean_author(guessed_author or "Unknown")
    metadata = clean_author(metadata_author or "Unknown")
    text = clean_author(text_author or "Unknown")

    if is_full_author(guessed):
        if is_full_author(text) and same_author_last_name(guessed, text) and text_has_more_first_names(guessed, text):
            return text
        return guessed
    if is_full_author(metadata):
        return metadata
    if is_full_author(text):
        return text
    if guessed != "Unknown":
        return guessed
    if metadata != "Unknown":
        return metadata
    return "Unknown"


def is_full_author(author: str) -> bool:
    return bool(author and author != "Unknown" and "," in author)


def same_author_last_name(left: str, right: str) -> bool:
    return left.split(",", 1)[0].strip().lower() == right.split(",", 1)[0].strip().lower()


def text_has_more_first_names(guessed: str, text: str) -> bool:
    guessed_first = guessed.split(",", 1)[1].strip().split()
    text_first = text.split(",", 1)[1].strip().split()
    return len(text_first) > len(guessed_first) and text_first[: len(guessed_first)] == guessed_first


def normalize_author_candidate(value: str, surname_hint: str = "") -> str:
    value = humanize_title(value)
    stop_words = {"the", "and", "of", "in", "on", "for", "from", "with", "press", "university"}
    words = [word for word in re.findall(r"[A-Za-z'.]+", value) if word.lower() not in stop_words]
    if surname_hint and len(words) >= 3 and words[-1].lower() == surname_hint.lower():
        repeated = [index for index, word in enumerate(words[:-1]) if word.lower() == surname_hint.lower()]
        if repeated and repeated[-1] + 1 < len(words) - 1:
            words = words[repeated[-1] + 1 :]
    if len(words) < 2:
        return ""
    return " ".join(word[:1].upper() + word[1:].lower() for word in words[:4])


def remove_author_prefix_from_title(title: str, author: str) -> str:
    if "," not in author:
        return title
    _, first = [part.strip() for part in author.split(",", 1)]
    first_words = [word.lower() for word in re.findall(r"[A-Za-z0-9]+", first)]
    title_words = re.findall(r"[A-Za-z0-9]+", title)
    while first_words and title_words and title_words[0].lower() == first_words[-1]:
        title_words = title_words[1:]
        first_words = first_words[:-1]
    return " ".join(title_words) if title_words else title


def looks_like_name(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Z][A-Za-z'.]+", value))


def looks_like_author_key(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Z][a-z]+[A-Z][A-Za-z]+(?:EtAl)?", value)) or value == "Unknown"


def split_author_key(value: str) -> str:
    if value == "Unknown":
        return "Unknown"
    value = re.sub(r"EtAl$", " et al.", value)
    parts = re.findall(r"[A-Z][a-z'.]*|et al\.", value)
    if len(parts) >= 2:
        return f"{parts[0]}, {' '.join(format_author_part(part) for part in parts[1:])}"
    return value


def format_author_part(value: str) -> str:
    if value == "et al.":
        return value
    if len(value) == 1 and value.isalpha():
        return f"{value}."
    return value


def infer_work_type(path: Path, text: str) -> str:
    lower = f"{path.stem} {text[:2000]}".lower()
    if "table of contents" in lower or re.search(r"\bcontents\b", lower):
        return "book"
    for work_type in WORK_TYPES - {"unknown"}:
        if re.search(rf"\b{re.escape(work_type)}\b", lower):
            return work_type
    if path.suffix.lower() == ".md":
        return "notes"
    return "unknown"


def infer_year_from_text(text: str) -> str:
    if not text.strip():
        return ""
    sample = re.sub(r"\s+", " ", text[:50000])

    priority_patterns = [
        r"\bfirst published(?:\s+in\s+\w+)?(?:\s+by\s+[^.;:]{0,80}?)?\s+(1[5-9]\d{2}|20\d{2})\b",
        r"\bfirst published[^.;]{0,120}?\b(1[5-9]\d{2}|20\d{2})\b",
        r"(?:©|\bcopyright\b)[^.;]{0,120}?\b(1[5-9]\d{2}|20\d{2})\b",
    ]
    for pattern in priority_patterns:
        match = re.search(pattern, sample, flags=re.IGNORECASE)
        if match:
            return match.group(1)

    contents = re.search(r"\bcontents\b", sample, flags=re.IGNORECASE)
    front_matter = sample[: contents.start()] if contents else sample[:3000]
    candidates = [
        match
        for match in re.finditer(r"(?<![\d-])(1[5-9]\d{2}|20\d{2})(?![\d-])", front_matter)
        if not year_context_is_digitization(front_matter, match.start(), match.end())
    ]
    if candidates:
        return candidates[-1].group(1)
    return ""


def should_lookup_catalog(title: str, author: str, year: str) -> bool:
    if not title or title == "Untitled":
        return False
    return not year or author_needs_catalog_author(author, "")


def author_needs_catalog_author(author: str, catalog_author: str) -> bool:
    cleaned = clean_author(author or "Unknown")
    if cleaned == "Unknown":
        return bool(catalog_author)
    if "," in cleaned:
        return False
    if not catalog_author:
        return True
    return same_author_last_name(cleaned, catalog_author)


def lookup_catalog_metadata(title: str, author: str, config: Config) -> CatalogMatch:
    query = urllib.parse.urlencode(
        {
            "title": title,
            "author": "" if author == "Unknown" else author.replace(",", ""),
            "fields": "title,author_name,first_publish_year",
            "limit": "5",
        }
    )
    request = urllib.request.Request(
        f"https://openlibrary.org/search.json?{query}",
        headers={"User-Agent": "reading-librarian/0.1 (+local CLI)"},
    )
    try:
        with urllib.request.urlopen(request, timeout=config.catalog_timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        return CatalogMatch(note=f"Catalog lookup failed: {exc}")

    docs = payload.get("docs", [])
    title_key = normalize_lookup_text(title)
    author_last = author.split(",", 1)[0].strip().lower()
    for doc in docs:
        doc_title = normalize_lookup_text(str(doc.get("title") or ""))
        doc_author_names = [str(name) for name in doc.get("author_name") or []]
        doc_authors = [name.lower() for name in doc_author_names]
        title_matches = doc_title == title_key or title_key in doc_title or doc_title in title_key
        author_matches = author in {"", "Unknown"} or not author_last or any(author_last in name for name in doc_authors)
        if title_matches and author_matches:
            return CatalogMatch(
                title=str(doc.get("title") or ""),
                author=clean_author(doc_author_names[0]) if doc_author_names else "",
                year="" if clean_year(str(doc.get("first_publish_year") or "")) == "nd" else clean_year(str(doc.get("first_publish_year") or "")),
            )
    return CatalogMatch()


def lookup_catalog_year(title: str, author: str, config: Config) -> tuple[str, str]:
    match = lookup_catalog_metadata(title, author, config)
    return match.year, match.note


def normalize_lookup_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def year_context_is_digitization(text: str, start: int, end: int) -> bool:
    context = text[max(0, start - 80) : min(len(text), end + 80)].lower()
    return any(marker in context for marker in ["digitized", "internet archive", "funding from", "scanned"])


def clean_title(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip(" -_\t\r\n")
    return value or "Untitled"


def clean_author(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    if not value:
        return "Unknown"
    if " and " in value.lower() or ";" in value:
        first = re.split(r"\s+and\s+|;", value, maxsplit=1, flags=re.IGNORECASE)[0].strip()
        return f"{normalize_single_author(first)} et al."
    return normalize_single_author(value)


def normalize_single_author(value: str) -> str:
    if value.lower() in {"unknown", "anonymous"}:
        return "Unknown"
    if "," in value:
        parts = [part.strip() for part in value.split(",") if part.strip()]
        last = parts[0]
        first_parts = [
            part
            for part in parts[1:]
            if not re.fullmatch(r"\d{4}(?:-\d{4})?", part)
            and part.lower() not in {"author", "editor", "translator"}
        ]
        first = first_parts[0] if first_parts else ""
        return f"{last}, {first}".strip(", ")
    parts = value.split()
    if len(parts) >= 2:
        return f"{parts[-1]}, {' '.join(parts[:-1])}"
    return value


def clean_year(value: str) -> str:
    match = re.search(r"(1[5-9]\d{2}|20\d{2})", str(value))
    return match.group(1) if match else "nd"


def first_known_year(*values: str) -> str:
    for value in values:
        year = clean_year(value)
        if year != "nd":
            return year
    return ""


def clean_work_type(value: str) -> str:
    value = value.lower().strip()
    aliases = {"ebook": "book", "essays": "essay", "stories": "story"}
    value = aliases.get(value, value)
    return value if value in WORK_TYPES else "unknown"


def summarize_text(title: str, text: str, review: list[str]) -> str:
    if review and not text.strip():
        if any("No extractable" in item for item in review):
            return "No extractable text found; OCR is needed before a reliable summary can be written."
        return "Needs metadata or text review before a reliable summary can be written."
    first_sentence = re.split(r"(?<=[.!?])\s+", text.strip())[0] if text.strip() else ""
    if first_sentence:
        return truncate(first_sentence, 180)
    return f"Local reading file titled {title}."


def classify_next_action(author: str, title: str, year: str, text: str, review: list[str], summary: str) -> str:
    weak_metadata = author == "Unknown" or "," not in author or title == "Untitled" or year == "nd"
    no_text = not text.strip()
    if weak_metadata:
        return "needs_catalog"
    if no_text:
        return "needs_ocr"
    if any("Catalog lookup failed" in item or "failed" in item.lower() for item in review):
        return "needs_manual"
    if review:
        return "needs_manual"
    if model_would_help(summary):
        return "needs_model"
    return "clean"


def model_would_help(summary: str) -> bool:
    lower = summary.lower()
    if not summary.strip():
        return True
    return not any(marker in lower for marker in ["needs review", "no extractable text", "ocr is needed"])


def infer_tags(title: str, text: str, work_type: str) -> list[str]:
    lower = f"{title} {text[:5000]}".lower()
    tags = [work_type] if work_type != "unknown" else ["reading"]
    keywords = {
        "media": ["media", "television", "film", "image"],
        "philosophy": ["philosophy", "ontology", "dialectic"],
        "literature": ["poem", "literature", "novel", "poetry"],
        "technology": ["technology", "cybernetics", "computer", "software"],
        "language": ["language", "orality", "writing"],
        "politics": ["politics", "capital", "state", "freedom"],
    }
    for tag, words in keywords.items():
        if any(word in lower for word in words):
            tags.append(tag)
    return dedupe(tags)[:4]


def make_filename(entry: WorkEntry, config: Config, suffix: str | None = None) -> str:
    author = author_filename_key(entry.author)
    title = compact_pascal(entry.title) or "Untitled"
    year = entry.year or "nd"
    work_type = entry.work_type or "unknown"
    ext = suffix or Path(entry.original_filename).suffix.lower()
    stem = f"{author}_{title}_{year}_{work_type}"
    if len(stem) > config.max_filename_stem_chars:
        overflow = len(stem) - config.max_filename_stem_chars
        keep_title = max(18, len(title) - overflow)
        title = title[:keep_title].rstrip("_")
        stem = f"{author}_{title}_{year}_{work_type}"
    return normalize_filename(f"{stem}{ext}")


def author_filename_key(author: str) -> str:
    if author == "Unknown":
        return "Unknown"
    et_al = author.endswith(" et al.")
    author = author.removesuffix(" et al.")
    if "," in author:
        last, first = [part.strip() for part in author.split(",", 1)]
        key = compact_pascal(f"{last} {first}")
    else:
        key = compact_pascal(author)
    return f"{key}EtAl" if et_al else key


def compact_pascal(value: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", value)
    return "".join(word[:1].upper() + word[1:] for word in words)


def normalize_filename(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]", "", value)
    value = re.sub(r"_+", "_", value)
    return value.strip("._") or "Unknown_Untitled_nd_unknown"


def unique_filename(library: Path, filename: str, source: Path, reserved: set[str] | None = None) -> str:
    reserved = reserved or set()
    target = library / filename
    if not target.exists() and filename not in reserved:
        return filename
    suffix = stable_hash(source)
    path = Path(filename)
    candidate = f"{path.stem}_{suffix}{path.suffix}"
    counter = 2
    while (library / candidate).exists() or candidate in reserved:
        candidate = f"{path.stem}_{suffix}{counter}{path.suffix}"
        counter += 1
    return candidate


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    counter = 2
    while True:
        candidate = path.with_name(f"{path.stem}_{counter}{path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def move_without_overwrite(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    created_target = False
    try:
        with source.open("rb") as src:
            dst = target.open("xb")
            created_target = True
            with dst:
                shutil.copyfileobj(src, dst)
        shutil.copystat(source, target)
    except Exception:
        if created_target and target.exists():
            target.unlink()
        raise
    source.unlink()


def write_text_without_overwrite(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(text)


def write_index(path: Path, entries: list[WorkEntry]) -> None:
    write_text_atomic(path, render_index(entries))


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        temp.write_text(text, encoding="utf-8")
        temp.replace(path)
    finally:
        if temp.exists():
            temp.unlink()


def stable_hash(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        digest.update(path.name.encode("utf-8"))
    return digest.hexdigest()[:8]


def read_index(path: Path) -> list[WorkEntry]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    entries: list[WorkEntry] = []
    current_author = "Unknown"
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("### "):
            current_author = line[4:].strip()
            index += 1
            continue
        if line.startswith("- **"):
            block = [line]
            index += 1
            while index < len(lines) and (lines[index].startswith("  ") or not lines[index].strip()):
                if lines[index].strip():
                    block.append(lines[index])
                index += 1
            entries.append(parse_entry_block(current_author, block))
            continue
        index += 1
    return entries


def parse_entry_block(author: str, block: list[str]) -> WorkEntry:
    first = block[0]
    match = re.match(r"- \*\*(.*?)\*\* \((.*?)\) — ([A-Za-z]+)", first)
    entry = WorkEntry(author=author)
    if match:
        entry.title = match.group(1)
        entry.year = match.group(2)
        entry.work_type = clean_work_type(match.group(3))
    for raw in block[1:]:
        line = raw.strip()
        if line.startswith("File:"):
            entry.filename = strip_code(line.removeprefix("File:").strip())
        elif line.startswith("Original filename:"):
            entry.original_filename = strip_code(line.removeprefix("Original filename:").strip())
        elif line.startswith("Status:"):
            entry.status = line.removeprefix("Status:").strip()
        elif line.startswith("Sent:"):
            entry.sent = line.removeprefix("Sent:").strip()
        elif line.startswith("Reading time:"):
            entry.reading_time = line.removeprefix("Reading time:").strip()
        elif line.startswith("Summary:"):
            entry.summary = line.removeprefix("Summary:").strip()
        elif line.startswith("Tags:"):
            tags = line.removeprefix("Tags:").strip()
            entry.tags = [tag.strip() for tag in tags.split(",") if tag.strip()]
        elif line.startswith("Related:"):
            entry.related = line.removeprefix("Related:").strip()
        elif line.startswith("Next action:"):
            entry.next_action = line.removeprefix("Next action:").strip()
    return entry


def strip_code(value: str) -> str:
    return value.strip().strip("`")


def one_line(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def inline_code(value: str) -> str:
    value = one_line(value)
    fence = "``" if "`" in value else "`"
    return f"{fence}{value}{fence}"


def render_index(entries: list[WorkEntry]) -> str:
    entries = sorted(entries, key=lambda item: (item.author_key, item.display_title.lower(), item.year))
    recent = sorted(entries, key=lambda item: item.added or "", reverse=True)[:5]
    lines = ["# Reading Library Index", "", "## Recently Added", ""]
    if recent:
        for entry in recent:
            lines.append(f"- {one_line(entry.display_title)} — {one_line(entry.author)} ({inline_code(entry.filename)})")
    lines.extend(["", "## Authors", ""])

    by_author: dict[str, list[WorkEntry]] = {}
    for entry in entries:
        by_author.setdefault(entry.author, []).append(entry)

    for author in sorted(by_author, key=author_sort_key):
        lines.extend([f"### {author}", ""])
        for entry in sorted(by_author[author], key=lambda item: (item.display_title.lower(), item.year)):
            lines.extend(render_entry(entry))
            lines.append("")

    lines.extend(["## Tags", ""])
    tag_map: dict[str, list[str]] = {}
    for entry in entries:
        for tag in entry.tags:
            tag_map.setdefault(tag, []).append(f"{entry.display_title} ({entry.author})")
    if tag_map:
        for tag in sorted(tag_map):
            works = "; ".join(sorted(tag_map[tag])[:8])
            lines.append(f"- {tag}: {works}")
    lines.extend(["", "## Needs Review", ""])
    needs_review = [entry for entry in entries if entry_needs_review(entry)]
    if needs_review:
        for entry in sorted(needs_review, key=lambda item: (item.author_key, item.display_title.lower())):
            reasons = "; ".join(review_reasons(entry))
            lines.append(f"- {inline_code(entry.filename)} — {one_line(entry.display_title)} by {one_line(entry.author)}: {one_line(reasons)}")
    return "\n".join(lines).rstrip() + "\n"


def render_entry(entry: WorkEntry) -> list[str]:
    return [
        f"- **{one_line(entry.display_title)}** ({one_line(entry.year)}) — {one_line(entry.work_type)}  ",
        f"  File: {inline_code(entry.filename)}  ",
        f"  Original filename: {inline_code(entry.original_filename)}  ",
        f"  Status: {one_line(entry.status)}  ",
        f"  Sent: {one_line(entry.sent)}  ",
        f"  Reading time: {one_line(entry.reading_time)}  ",
        f"  Summary: {one_line(entry.summary)}  ",
        f"  Tags: {one_line(', '.join(entry.tags))}  ",
        f"  Related: {one_line(entry.related)}  ",
        f"  Next action: {one_line(entry.next_action)}",
    ]


def author_sort_key(author: str) -> str:
    if author == "Unknown":
        return "zzzzzz unknown"
    return author.lower()


def upsert_entry(entries: list[WorkEntry], entry: WorkEntry) -> list[WorkEntry]:
    kept = [existing for existing in entries if existing.filename != entry.filename]
    kept.append(entry)
    return kept


def append_ingest_log(path: Path, original: str, entry: WorkEntry, target: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            f"- {now_stamp()} — {inline_code(original)} -> {inline_code(target.name)}; "
            f"{one_line(entry.author)}; {one_line(entry.title)}; {one_line(entry.year)}; {one_line(entry.work_type)}\n"
        )


def command_lint(args: argparse.Namespace, root: Path) -> int:
    config = project_config(root)
    ensure_dirs(config)
    entries = read_index(config.index)
    issues = lint_entries(config, entries)
    for issue in issues:
        print(f"{issue.severity} {issue.code}: {issue.message}")

    if args.apply:
        changed = False
        indexed = {entry.filename for entry in entries}
        for path in library_reading_files(config):
            if path.name not in indexed:
                entry = infer_entry(path, config)
                entry.filename = path.name
                entries = upsert_entry(entries, entry)
                changed = True
        if changed:
            write_index(config.index, entries)
            print("Applied lint repairs for missing library entries.")
    errors = [issue for issue in issues if issue.severity == "ERROR"]
    if not issues:
        print("No lint issues found.")
    elif not errors:
        print("No lint errors found.")
    return 1 if errors else 0


def command_reindex(args: argparse.Namespace, root: Path) -> int:
    config = project_config(root)
    ensure_dirs(config)
    existing_entries = {entry.filename: entry for entry in read_index(config.index)}
    rebuilt: list[WorkEntry] = []
    use_catalog_lookup = args.lookup or config.use_catalog_lookup

    for path in library_reading_files(config):
        entry = infer_entry(path, config, use_catalog_lookup=use_catalog_lookup)
        entry.filename = path.name
        old = existing_entries.get(path.name)
        if old:
            preserve_existing_state(entry, old)
        rebuilt.append(entry)

    print(f"[dry-run] Reindex {len(rebuilt)} library file(s).")
    for entry in sorted(rebuilt, key=lambda item: (item.author_key, item.display_title.lower(), item.filename)):
        review = " REVIEW" if entry.needs_review else ""
        print(f"[dry-run]{review}: {entry.filename} -> {entry.author} — {entry.display_title} ({entry.year})")

    if not args.apply:
        print("Dry run only. Re-run with --apply to rebuild index.md metadata.")
        return 0

    write_index(config.index, rebuilt)
    print(f"Rebuilt index.md for {len(rebuilt)} library file(s).")
    return 0


def command_maintain(args: argparse.Namespace, root: Path) -> int:
    config = project_config(root)
    ensure_dirs(config)
    use_catalog_lookup = args.lookup or config.use_catalog_lookup
    plan = build_maintenance_plan(config, use_catalog_lookup=use_catalog_lookup)

    print(f"[dry-run] Maintain {len(plan.entries)} library file(s).")
    if plan.renames:
        for rename in plan.renames:
            print(f"[dry-run] RENAME: {rename.source_name} -> {rename.target_name}")
    else:
        print("[dry-run] No filename repairs proposed.")

    review_entries = [entry for entry in plan.entries if entry_needs_review(entry)]
    if review_entries:
        for entry in sorted(review_entries, key=lambda item: (item.author_key, item.display_title.lower())):
            reasons = "; ".join(review_reasons(entry))
            print(f"[dry-run] REVIEW {entry.next_action}: {entry.filename} — {entry.author} — {entry.display_title}: {reasons}")

    if not args.apply:
        print("Dry run only. Re-run with --apply to rename files and rebuild index.md.")
        return 0

    for rename in plan.renames:
        move_without_overwrite(config.library / rename.source_name, config.library / rename.target_name)
    write_index(config.index, plan.entries)
    print(f"Applied maintenance: {len(plan.renames)} rename(s), {len(plan.entries)} indexed file(s).")
    return 0


def build_maintenance_plan(config: Config, use_catalog_lookup: bool = False) -> MaintenancePlan:
    existing_entries = {entry.filename: entry for entry in read_index(config.index)}
    library_files = library_reading_files(config)
    reserved = {path.name for path in library_files}
    rebuilt: list[WorkEntry] = []
    renames: list[RenamePlan] = []

    for path in library_files:
        entry = infer_entry(path, config, use_catalog_lookup=use_catalog_lookup)
        old = existing_entries.get(path.name)
        if old:
            preserve_existing_state(entry, old)

        desired_name = make_filename(entry, config, path.suffix.lower())
        if should_repair_filename(path.name, entry, desired_name):
            target_name = unique_filename(config.library, desired_name, path, reserved - {path.name})
            if target_name != path.name:
                renames.append(RenamePlan(path.name, target_name))
                entry.filename = target_name
                reserved.discard(path.name)
                reserved.add(target_name)
            else:
                entry.filename = path.name
        else:
            entry.filename = path.name
        rebuilt.append(entry)

    return MaintenancePlan(rebuilt, renames)


def should_repair_filename(current_name: str, entry: WorkEntry, desired_name: str) -> bool:
    if current_name == desired_name:
        return False
    if not filename_convention_ok(current_name):
        return True
    return "_nd_" in current_name and entry.year != "nd"


def preserve_existing_state(entry: WorkEntry, old: WorkEntry) -> None:
    entry.original_filename = old.original_filename or entry.original_filename
    entry.status = old.status
    entry.sent = old.sent
    entry.added = old.added
    if entry.year == "nd" and old.year != "nd":
        entry.year = old.year


@dataclass
class LintIssue:
    code: str
    message: str
    severity: str = "ERROR"


def lint_entries(config: Config, entries: list[WorkEntry]) -> list[LintIssue]:
    issues: list[LintIssue] = []
    issues.extend(lint_index_shape(config.index))
    indexed = {entry.filename for entry in entries if entry.filename}
    library_files = {path.name for path in library_reading_files(config)}

    for filename in sorted(library_files - indexed):
        issues.append(LintIssue("MISSING_INDEX", f"`library/{filename}` is not listed in index.md."))
    for filename in sorted(indexed - library_files):
        issues.append(LintIssue("MISSING_FILE", f"`{filename}` is indexed but does not exist in library/."))
    for filename in sorted(library_files):
        if not filename_convention_ok(filename):
            issues.append(LintIssue("BAD_FILENAME", f"`{filename}` does not match the filename convention."))
        entry = next((item for item in entries if item.filename == filename), None)
        if entry and "_nd_" in filename and entry.year != "nd":
            issues.append(
                LintIssue(
                    "STALE_FILENAME",
                    f"`{filename}` still contains `_nd_` but index year is {entry.year}; run `librarian maintain --apply`.",
                    "WARN",
                )
            )

    seen_titles: dict[tuple[str, str], str] = {}
    author_keys: dict[str, str] = {}
    for entry in entries:
        key = (entry.author.lower(), entry.title.lower())
        if key in seen_titles:
            issues.append(LintIssue("DUPLICATE_TITLE", f"`{entry.title}` appears more than once for {entry.author}."))
        seen_titles[key] = entry.filename

        compact = compact_pascal(entry.author.replace(",", ""))
        if compact in author_keys and author_keys[compact] != entry.author:
            issues.append(LintIssue("AUTHOR_SPELLING", f"Possible inconsistent author spelling: {author_keys[compact]} / {entry.author}."))
        author_keys[compact] = entry.author

        for field_name in ["filename", "original_filename", "status", "sent", "summary", "next_action"]:
            if not getattr(entry, field_name):
                issues.append(LintIssue("MISSING_FIELD", f"`{entry.title}` is missing {field_name}."))

    quarantine_files = [path.name for path in supported_files(config, config.quarantine)]
    for filename in quarantine_files:
        issues.append(LintIssue("QUARANTINE", f"`_quarantine/{filename}` needs review."))
    return issues


def lint_index_shape(path: Path) -> list[LintIssue]:
    if not path.exists():
        return []
    issues: list[LintIssue] = []
    current_section = ""
    current_author = ""
    entry_pattern = re.compile(r"- \*\*.+\*\* \((?:\d{4}|nd)\) — [A-Za-z]+(?:  )?$")
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if line.startswith("## "):
            current_section = line.removeprefix("## ").strip()
            current_author = ""
        elif line.startswith("### "):
            current_author = line.removeprefix("### ").strip()
            if current_section != "Authors":
                issues.append(LintIssue("MALFORMED_INDEX", f"Author heading on line {line_number} is outside the Authors section."))
        elif line.startswith("- **") and current_section == "Authors":
            if not current_author:
                issues.append(LintIssue("MALFORMED_INDEX", f"Work entry on line {line_number} appears before an author heading."))
            if not entry_pattern.match(line):
                issues.append(LintIssue("MALFORMED_INDEX", f"Work entry on line {line_number} does not match the index entry format."))
    return issues


def library_reading_files(config: Config) -> list[Path]:
    return [path for path in supported_files(config, config.library) if path.resolve() != config.index.resolve()]


def filename_convention_ok(filename: str) -> bool:
    ext = re.escape(Path(filename).suffix.lower())
    work_types = "|".join(sorted(WORK_TYPES | {"ebook", "essays", "stories"}))
    year = r"(?:\d{4}|nd)"
    hash_suffix = r"(?:_[a-f0-9]{8}\d*)?"
    canonical = rf"^[A-Za-z0-9]+_[A-Za-z0-9]+_{year}_(?:{work_types}){hash_suffix}{ext}$"
    legacy_import = rf"^[A-Za-z0-9]+(?:_[A-Za-z0-9][A-Za-z0-9 ]*)+_{year}_(?:{work_types}){hash_suffix}{ext}$"
    return bool(re.fullmatch(canonical, filename) or re.fullmatch(legacy_import, filename))


def command_weekly_pick(args: argparse.Namespace, root: Path) -> int:
    return command_digest(args, root)


def command_digest(args: argparse.Namespace, root: Path) -> int:
    config = project_config(root)
    ensure_dirs(config)
    entries = read_index(config.index)
    plan = build_digest_plan(config, entries, allow_repeats=args.allow_repeats)

    if not plan:
        print("No eligible unread works found.")
        return 1

    print(f"[dry-run] Digest pick: {plan.entry.display_title} by {plan.entry.author}")
    print(f"[dry-run] Draft path: {plan.draft_path.relative_to(root)}")
    if args.notify:
        print(render_digest_notification(plan.entry, plan.draft_path))
    if not args.apply:
        print(plan.body)
        print("Dry run only. Re-run with --apply to write the draft and sent log.")
        if args.email:
            print("Email not sent in dry-run mode.")
        return 0

    if args.email:
        require_email_config()
    write_text_without_overwrite(plan.draft_path, plan.body)
    if args.email:
        send_digest_email(plan.entry, plan.body)
    plan.entry.sent = today()
    entries = upsert_entry(entries, plan.entry)
    write_index(config.index, entries)
    append_sent_log(config.sent_log, plan.entry, plan.draft_path, emailed=args.email)
    print(f"Wrote {plan.draft_path.relative_to(root)}.")
    if args.email:
        print("Sent digest email.")
    return 0


def build_digest_plan(config: Config, entries: list[WorkEntry], allow_repeats: bool = False) -> DigestPlan | None:
    candidates = [
        entry
        for entry in entries
        if entry.status not in {"read", "skipped"}
        and not entry_needs_review(entry)
        and (allow_repeats or entry.sent == "never")
    ]
    if not candidates and allow_repeats:
        candidates = [entry for entry in entries if entry.status not in {"read", "skipped"} and not entry_needs_review(entry)]
    if not candidates:
        return None

    pick = sorted(candidates, key=lambda item: (item.sent != "never", item.author_key, item.display_title.lower()))[0]
    draft_name = f"{today()}_{normalize_filename(compact_pascal(pick.display_title) or 'Read')}.md"
    draft_path = unique_path(config.drafts / draft_name)
    draft = digest_draft(pick, config.library / pick.filename)
    return DigestPlan(pick, draft_path, draft)


def digest_draft(entry: WorkEntry, local_path: Path) -> str:
    return f"""Subject: Read of the Week: {entry.display_title} by {entry.author}

Title: {entry.display_title}
Author: {entry.author}

Summary:
{entry.summary}

Why this is worth reading now:
This unread work is already in the local library and has not been sent before.

Primer prompts:
- What problem is this work responding to?
- Which claim or image should I carry into the week?
- What would change if I took this work seriously?

Local file path:
{local_path}
"""


def render_digest_notification(entry: WorkEntry, draft_path: Path) -> str:
    return "\n".join(
        [
            f"NOTIFY: Read of the Week: {entry.display_title}",
            f"Author: {entry.author}",
            f"Draft: {draft_path}",
        ]
    )


def send_digest_email(entry: WorkEntry, body: str) -> None:
    api_key, sender, recipient = require_email_config()
    payload = json.dumps(
        {
            "from": sender,
            "to": [recipient],
            "subject": f"Read of the Week: {entry.display_title} by {entry.author}",
            "text": body,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "reading-librarian/0.1 (+local CLI)",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            if getattr(response, "status", 200) >= 400:
                raise ValueError(f"Email delivery failed with HTTP {response.status}.")
    except Exception as exc:
        raise ValueError(f"Email delivery failed: {exc}") from exc


def require_email_config() -> tuple[str, str, str]:
    api_key = os.environ.get("RESEND_API_KEY", "")
    sender = os.environ.get("LIBRARIAN_EMAIL_FROM", "")
    recipient = os.environ.get("LIBRARIAN_EMAIL_TO", "")
    if not api_key or not sender or not recipient:
        raise ValueError("Email delivery requires RESEND_API_KEY, LIBRARIAN_EMAIL_FROM, and LIBRARIAN_EMAIL_TO.")
    return api_key, sender, recipient


def append_sent_log(path: Path, entry: WorkEntry, draft_path: Path, emailed: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    delivery = "emailed and drafted as" if emailed else "drafted as"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"- {now_stamp()} — {inline_code(entry.filename)} {delivery} {inline_code(draft_path.name)}\n")


def command_list(args: argparse.Namespace, root: Path) -> int:
    entries = read_index(project_config(root).index)
    for entry in sorted(entries, key=lambda item: (item.author_key, item.display_title.lower())):
        print(f"{entry.author} — {entry.display_title} ({entry.year}) [{entry.status}] `{entry.filename}`")
    return 0


def command_search(args: argparse.Namespace, root: Path) -> int:
    query = args.query.lower()
    entries = read_index(project_config(root).index)
    found = [
        entry
        for entry in entries
        if query in " ".join(
            [entry.author, entry.title, entry.year, entry.work_type, entry.filename, entry.summary, " ".join(entry.tags)]
        ).lower()
    ]
    for entry in found:
        print(f"{entry.author} — {entry.display_title} ({entry.year}) [{entry.status}] `{entry.filename}`")
    return 0 if found else 1


def command_mark(args: argparse.Namespace, root: Path, status: str) -> int:
    config = project_config(root)
    entries = read_index(config.index)
    matches = match_entries(entries, args.query)
    if not matches:
        print(f"No entry matched {args.query!r}.")
        return 1
    if len(matches) > 1:
        print(f"Multiple entries matched {args.query!r}; use a more specific title or filename.")
        for entry in matches:
            print(f"- {entry.display_title} `{entry.filename}`")
        return 1
    entry = matches[0]
    print(f"[dry-run] {entry.display_title}: {entry.status} -> {status}")
    if not args.apply:
        print("Dry run only. Re-run with --apply to update index.md.")
        return 0
    entry.status = status
    write_index(config.index, entries)
    print(f"Updated {entry.display_title} to {status}.")
    return 0


def match_entries(entries: list[WorkEntry], query: str) -> list[WorkEntry]:
    needle = query.lower()
    return [
        entry
        for entry in entries
        if needle in entry.title.lower() or needle in entry.filename.lower() or needle in entry.author.lower()
    ]


def entry_needs_review(entry: WorkEntry) -> bool:
    return bool(review_reasons(entry))


def review_reasons(entry: WorkEntry) -> list[str]:
    reasons = list(entry.needs_review)
    summary = entry.summary.lower()
    if entry.next_action == "needs_catalog":
        reasons.append("Metadata is weak; catalog lookup is the next cheap repair step.")
    if entry.next_action == "needs_ocr":
        reasons.append("OCR is needed before content-level summary or reading-time work.")
    if entry.next_action == "needs_manual":
        reasons.append("Automated metadata repair was not confident enough.")
    if "needs review" in summary:
        reasons.append("Summary or metadata needs review.")
    if "no extractable text" in summary or "ocr is needed" in summary:
        reasons.append("No extractable text found; may need OCR.")
    if entry.author == "Unknown" or "," not in entry.author:
        reasons.append("Author could not be fully inferred.")
    if entry.title == "Untitled":
        reasons.append("Title could not be inferred.")
    return dedupe(reasons)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="librarian")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init")

    ingest = sub.add_parser("ingest")
    ingest.add_argument("--apply", action="store_true")
    ingest.add_argument("--lookup", action="store_true", help="Use optional Open Library catalog lookup for weak metadata.")

    lint = sub.add_parser("lint")
    lint.add_argument("--apply", action="store_true")

    reindex = sub.add_parser("reindex")
    reindex.add_argument("--apply", action="store_true")
    reindex.add_argument("--lookup", action="store_true", help="Use optional Open Library catalog lookup for weak metadata.")

    maintain = sub.add_parser("maintain")
    maintain.add_argument("--apply", action="store_true")
    maintain.add_argument("--lookup", action="store_true", help="Use optional Open Library catalog lookup for weak metadata.")

    weekly = sub.add_parser("weekly-pick")
    weekly.add_argument("--apply", action="store_true")
    weekly.add_argument("--allow-repeats", action="store_true")
    weekly.add_argument("--notify", action="store_true")
    weekly.add_argument("--email", action="store_true")

    digest = sub.add_parser("digest")
    digest.add_argument("--apply", action="store_true")
    digest.add_argument("--allow-repeats", action="store_true")
    digest.add_argument("--notify", action="store_true")
    digest.add_argument("--email", action="store_true")

    sub.add_parser("list")

    search = sub.add_parser("search")
    search.add_argument("query")

    mark = sub.add_parser("mark-read")
    mark.add_argument("query")
    mark.add_argument("--apply", action="store_true")

    skip = sub.add_parser("skip")
    skip.add_argument("query")
    skip.add_argument("--apply", action="store_true")
    return parser


def main(argv: list[str] | None = None, root: Path | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = (root or Path.cwd()).resolve()
    try:
        if args.command == "init":
            return init_project(root)
        if args.command == "ingest":
            return command_ingest(args, root)
        if args.command == "lint":
            return command_lint(args, root)
        if args.command == "reindex":
            return command_reindex(args, root)
        if args.command == "maintain":
            return command_maintain(args, root)
        if args.command == "weekly-pick":
            return command_weekly_pick(args, root)
        if args.command == "digest":
            return command_digest(args, root)
        if args.command == "list":
            return command_list(args, root)
        if args.command == "search":
            return command_search(args, root)
        if args.command == "mark-read":
            return command_mark(args, root, "read")
        if args.command == "skip":
            return command_mark(args, root, "skipped")
    except ValueError as exc:
        print(f"CONFIG_ERROR: {exc}")
        return 2
    parser.error("unknown command")
    return 2


def dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def truncate(value: str, limit: int) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"


def today() -> str:
    return dt.date.today().isoformat()


def now_stamp() -> str:
    return dt.datetime.now().replace(microsecond=0).isoformat()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
