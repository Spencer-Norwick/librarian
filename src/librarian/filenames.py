from __future__ import annotations

import re
from pathlib import Path

from .domain import Config, WorkEntry


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
