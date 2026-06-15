from __future__ import annotations

import re
from pathlib import Path

from .domain import WORK_TYPES, clean_work_type


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
    for index, line in enumerate(lines[:30]):
        by_match = re.match(r"(?i)^by\s+(.+)$", line)
        if by_match:
            title = front_matter_title_before(lines, index)
            author = normalize_author_candidate(by_match.group(1))
            if title and author:
                return {"title": title, "author": author}
    for index, line in enumerate(lines[:30]):
        if not probable_author_line(line):
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
    return probable_author_line(line, require_uppercase=True)


def probable_author_line(line: str, require_uppercase: bool = False) -> bool:
    words = re.findall(r"[A-Za-z'.]+", line)
    if not 2 <= len(words) <= 4:
        return False
    if require_uppercase and line != line.upper():
        return False
    lower = line.lower()
    blocked = {"contents", "preface", "chapter", "press", "university", "library", "inc", "hall", "book", "design", "thinking", "things"}
    if any(word.lower().strip(".'") in blocked for word in words) or " and " in lower:
        return False
    return all(word[:1].isupper() for word in words if word)


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
    if clean_author(guessed_author or "Unknown") == "Unknown" and title_key.startswith("unknown "):
        return True
    if clean_author(guessed_author or "Unknown") == "Unknown" and any(sep in guessed_title for sep in ["-", "_"]):
        return True
    return False


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


def normalize_lookup_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def year_context_is_digitization(text: str, start: int, end: int) -> bool:
    context = text[max(0, start - 80) : min(len(text), end + 80)].lower()
    return any(marker in context for marker in ["digitized", "internet archive", "funding from", "scanned"])


def clean_title(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip(" -_\t\r\n")
    return polish_title(value) or "Untitled"


def polish_title(value: str) -> str:
    value = re.sub(r"\bPreventionof\b", "Prevention of", value)
    value = re.sub(r"\bGuideto\b", "Guide to", value)
    value = re.sub(r"\bFundamentalsof\b", "Fundamentals of", value)
    value = re.sub(r"\bReproducability\b", "Reproducibility", value)
    trailing_articles = {"The", "A", "An"}
    words = value.split()
    if len(words) > 2 and words[-1] in trailing_articles:
        value = " ".join([words[-1], *words[:-1]])
    return value


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
