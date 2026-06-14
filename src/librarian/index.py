from __future__ import annotations

import re
from pathlib import Path

from .domain import WorkEntry, author_sort_key, clean_work_type
from .filesystem import write_text_atomic


def write_index(path: Path, entries: list[WorkEntry]) -> None:
    write_text_atomic(path, render_index(entries))


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
        elif line.startswith("Primer prompts:"):
            entry.primer_prompts = parse_inline_list(line.removeprefix("Primer prompts:").strip(), separator=" | ")
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


def parse_inline_list(value: str, separator: str = " | ") -> list[str]:
    if not value or value == "None.":
        return []
    return [item.strip() for item in value.split(separator) if item.strip()]


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
        f"  Primer prompts: {render_inline_list(entry.primer_prompts)}  ",
        f"  Tags: {one_line(', '.join(entry.tags))}  ",
        f"  Related: {one_line(entry.related)}  ",
        f"  Next action: {one_line(entry.next_action)}",
    ]


def render_inline_list(values: list[str]) -> str:
    cleaned = [one_line(value) for value in values if one_line(value)]
    return " | ".join(cleaned) if cleaned else "None."


def upsert_entry(entries: list[WorkEntry], entry: WorkEntry) -> list[WorkEntry]:
    kept = [existing for existing in entries if existing.filename != entry.filename]
    kept.append(entry)
    return kept


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
    if entry.next_action == "needs_model":
        reasons.append("Model enrichment is needed for a reliable summary and work-specific primer prompts.")
    if "needs review" in summary:
        reasons.append("Summary or metadata needs review.")
    if "no extractable text" in summary or "ocr is needed" in summary:
        reasons.append("No extractable text found; may need OCR.")
    if entry.author == "Unknown" or "," not in entry.author:
        reasons.append("Author could not be fully inferred.")
    if entry.title == "Untitled":
        reasons.append("Title could not be inferred.")
    return _dedupe(reasons)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
