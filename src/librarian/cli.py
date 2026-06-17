from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import tomllib
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .config import ensure_dirs, project_config, sample_config
from .domain import (
    WORK_TYPES,
    CatalogMatch,
    Config,
    DigestHistory,
    DigestPlan,
    LibraryStatus,
    MaintenancePlan,
    ModelEnrichment,
    ModelEnrichmentAttempt,
    MountRecommendation,
    RenamePlan,
    WorkEntry,
    clean_work_type,
)
from .extraction import extract_docx, extract_epub, extract_pdf
from .filesystem import (
    move_without_overwrite,
    supported_files,
    unique_filename,
    unique_path,
    write_text_atomic,
    write_text_without_overwrite,
)
from .filenames import compact_pascal, make_filename, normalize_filename
from .index import (
    entry_needs_review,
    inline_code,
    one_line,
    read_index,
    render_index,
    review_reasons,
    upsert_entry,
    write_index,
)
from .metadata import (
    author_needs_catalog_author,
    choose_author,
    clean_author,
    clean_title,
    clean_year,
    first_known_year,
    infer_author_from_text,
    infer_from_name,
    infer_identity_from_front_matter,
    infer_work_type,
    infer_year_from_text,
    normalize_lookup_text,
    remove_author_prefix_from_title,
    should_lookup_catalog,
    should_use_text_title,
    useful_pdf_title,
)


def init_project(root: Path) -> int:
    config = project_config(root)
    ensure_dirs(config)
    write_if_missing(root / "AGENTS.md", agents_markdown())
    write_if_missing(root / "README.md", readme_markdown())
    write_if_missing(root / "pyproject.toml", pyproject_text())
    write_if_missing(config.state / "config.toml", sample_config())
    write_if_missing(config.ingest_log, "# Ingest Log\n\n")
    write_if_missing(config.sent_log, "# Sent Log\n\n")
    write_if_missing(config.status_log, "# Status Log\n\n")
    write_if_missing(config.index, render_index([]))
    print("Initialized reading librarian workspace.")
    return 0


def write_if_missing(path: Path, content: str) -> None:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def pyproject_text() -> str:
    return Path(__file__).resolve().parents[2].joinpath("pyproject.toml").read_text(encoding="utf-8")


def agents_markdown() -> str:
    return Path(__file__).resolve().parents[2].joinpath("AGENTS.md").read_text(encoding="utf-8")


def readme_markdown() -> str:
    return Path(__file__).resolve().parents[2].joinpath("README.md").read_text(encoding="utf-8")


def command_ingest(args: argparse.Namespace, root: Path) -> int:
    config = project_config(root)
    ensure_dirs(config)
    use_model_enrichment = args.enrich or config.use_model_assistance
    if use_model_enrichment and not config.model_command:
        print("Model enrichment requires `model_command` in _state/config.toml or LIBRARIAN_MODEL_COMMAND.")
        return 2
    entries = read_index(config.index)
    existing_files = {entry.filename for entry in entries}
    reserved_names = {path.name for path in config.library.iterdir() if path.is_file()} if config.library.exists() else set()
    plans: list[tuple[Path, Path, WorkEntry]] = []
    use_catalog_lookup = args.lookup or config.use_catalog_lookup

    for source in supported_files(config, config.inbox):
        entry = infer_entry(source, config, use_catalog_lookup=use_catalog_lookup, use_model_enrichment=use_model_enrichment)
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


def infer_entry(path: Path, config: Config, use_catalog_lookup: bool = False, use_model_enrichment: bool = False) -> WorkEntry:
    text = ""
    metadata: dict[str, str] = {}
    review: list[str] = []
    if path.suffix.lower() == ".pdf":
        metadata, text, pdf_review = extract_pdf(path)
        review.extend(pdf_review)
        visual_text = pdf_title_page_ocr_text(path) if pdf_needs_visual_title_fallback(path, metadata, text) else ""
        if visual_text:
            text = merge_front_matter_text(visual_text, text)
    elif path.suffix.lower() in {".txt", ".md"}:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            review.append(f"Could not read text: {exc}")
    elif path.suffix.lower() == ".epub":
        text, extraction_review = extract_epub(path)
        review.extend(extraction_review)
    elif path.suffix.lower() == ".docx":
        text, extraction_review = extract_docx(path)
        review.extend(extraction_review)
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
    author = choose_author(guessed.get("author", ""), metadata.get("author", ""), text_author)
    if not title_source and text_identity.get("title") and clean_author(guessed.get("author", "Unknown")) == "Unknown" and author != "Unknown":
        guessed_title = text_identity["title"]
    title = clean_title(title_source or guessed_title)
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
    primer_prompts: list[str] = []
    next_action = classify_next_action(
        author=author,
        title=title,
        year=year,
        text=text,
        review=review,
        summary=summary,
    )
    if use_model_enrichment and next_action == "needs_model":
        attempt = try_enrich_from_model(
            config=config,
            entry=WorkEntry(author=author, title=title, year=year, work_type=work_type, original_filename=path.name),
            text=text,
        )
        enrichment = attempt.enrichment
        if enrichment:
            summary = enrichment.summary
            primer_prompts = enrichment.primer_prompts
            if enrichment.tags:
                tags = dedupe(tags + enrichment.tags)[:6]
            if enrichment.related:
                related = enrichment.related
            else:
                related = "None."
            next_action = "clean"
        else:
            review.append(f"Model enrichment failed: {attempt.reason}.")
            related = "None."
    else:
        related = "None."

    return WorkEntry(
        author=author,
        title=title,
        year=year,
        work_type=work_type,
        filename="",
        original_filename=path.name,
        reading_time=f"~{reading_minutes}m",
        summary=summary,
        primer_prompts=primer_prompts,
        tags=tags,
        related=related,
        needs_review=dedupe(review),
        next_action=next_action,
        added=today(),
    )


def pdf_needs_visual_title_fallback(path: Path, metadata: dict[str, str], text: str) -> bool:
    if path.suffix.lower() != ".pdf":
        return False
    if useful_pdf_title(metadata.get("title", "")):
        return False
    identity = infer_identity_from_front_matter(text)
    guessed = infer_from_name(path.stem)
    guessed_title = clean_title(guessed.get("title") or path.stem)
    if identity.get("title") and identity.get("author"):
        return False
    if guessed_title in {"Untitled", "Unknown"}:
        return True
    if re.fullmatch(r"[a-f0-9]{16,}", normalize_lookup_text(guessed_title).replace(" ", "")):
        return True
    if clean_author(guessed.get("author", "Unknown")) == "Unknown":
        return True
    return False


def merge_front_matter_text(front_text: str, body_text: str) -> str:
    front = front_text.strip()
    body = body_text.strip()
    if not front:
        return body_text
    if not body:
        return front
    if normalize_lookup_text(front) and normalize_lookup_text(front) in normalize_lookup_text(body[:2000]):
        return body_text
    return f"{front}\n{body_text}"


def pdf_title_page_ocr_text(path: Path) -> str:
    if not command_available("qlmanage") or not command_available("tesseract"):
        return ""
    try:
        with tempfile.TemporaryDirectory(prefix="librarian-title-page-") as tmp:
            output_dir = Path(tmp)
            rendered = render_pdf_title_page(path, output_dir)
            if not rendered:
                return ""
            completed = subprocess.run(
                ["tesseract", str(rendered), "stdout"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
                timeout=30,
            )
            if completed.returncode != 0:
                return ""
            return completed.stdout.strip()
    except Exception:
        return ""


def render_pdf_title_page(path: Path, output_dir: Path) -> Path | None:
    before = {item.name for item in output_dir.iterdir()} if output_dir.exists() else set()
    completed = subprocess.run(
        ["qlmanage", "-t", "-s", "1600", "-o", str(output_dir), str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        timeout=30,
    )
    if completed.returncode != 0:
        return None
    candidates = [item for item in output_dir.iterdir() if item.name not in before and item.suffix.lower() in {".png", ".jpg", ".jpeg"}]
    if not candidates:
        candidates = [item for item in output_dir.iterdir() if item.suffix.lower() in {".png", ".jpg", ".jpeg"}]
    return sorted(candidates, key=lambda item: item.stat().st_mtime, reverse=True)[0] if candidates else None


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


def enrich_from_model(config: Config, entry: WorkEntry, text: str) -> ModelEnrichment | None:
    return try_enrich_from_model(config, entry, text).enrichment


def try_enrich_from_model(config: Config, entry: WorkEntry, text: str) -> ModelEnrichmentAttempt:
    if not config.model_command or not text.strip():
        if not config.model_command:
            return ModelEnrichmentAttempt(reason="model_command is not configured")
        return ModelEnrichmentAttempt(reason="no text excerpt is available")
    payload = {
        "task": "enrich_reading_index_entry",
        "instructions": [
            "Return only JSON.",
            "Write a concise, specific summary of the work in 1-3 sentences.",
            "Write 3 work-specific primer_prompts that help a reader enter the work.",
            "Use short lowercase tags when useful.",
            "Do not invent bibliographic facts not supported by the metadata or text excerpt.",
        ],
        "work": {
            "title": entry.display_title,
            "author": entry.author,
            "year": entry.year,
            "work_type": entry.work_type,
            "filename": entry.filename,
            "original_filename": entry.original_filename,
        },
        "text_excerpt": text[: config.model_max_input_chars],
        "expected_schema": {
            "summary": "string",
            "primer_prompts": ["string", "string", "string"],
            "tags": ["string"],
            "related": "string",
        },
    }
    try:
        completed = subprocess.run(
            config.model_command,
            input=json.dumps(payload, ensure_ascii=True),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=120,
            check=False,
        )
    except OSError as exc:
        return ModelEnrichmentAttempt(reason=f"model command could not be started: {one_line(str(exc))}")
    except subprocess.TimeoutExpired:
        return ModelEnrichmentAttempt(reason="model command timed out after 120 seconds")
    if completed.returncode != 0:
        details = one_line(completed.stderr.strip() or completed.stdout.strip())
        reason = f"model command exited with code {completed.returncode}"
        if details:
            reason = f"{reason}: {truncate(details, 240)}"
        return ModelEnrichmentAttempt(reason=reason)
    try:
        raw = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return ModelEnrichmentAttempt(reason=f"model command did not return valid JSON: {exc.msg}")
    if not isinstance(raw, dict):
        return ModelEnrichmentAttempt(reason="model command returned JSON that was not an object")
    enrichment = ModelEnrichment(
        summary=one_line(str(raw.get("summary", ""))),
        primer_prompts=[one_line(str(item)) for item in raw.get("primer_prompts", []) if one_line(str(item))],
        tags=[normalize_tag(str(item)) for item in raw.get("tags", []) if normalize_tag(str(item))],
        related=one_line(str(raw.get("related", ""))),
    )
    reason = enrichment_validation_reason(entry, enrichment)
    if reason:
        return ModelEnrichmentAttempt(reason=reason)
    return ModelEnrichmentAttempt(enrichment=enrichment)


def enrichment_is_usable(entry: WorkEntry, enrichment: ModelEnrichment) -> bool:
    return not enrichment_validation_reason(entry, enrichment)


def enrichment_validation_reason(entry: WorkEntry, enrichment: ModelEnrichment) -> str:
    title_key = normalize_lookup_text(entry.display_title)
    summary_key = normalize_lookup_text(enrichment.summary)
    if len(enrichment.summary.split()) < 12:
        return "summary is too short"
    if title_key and summary_key == title_key:
        return "summary only repeats the title"
    if len(enrichment.primer_prompts) < 2:
        return "fewer than two primer prompts were returned"
    return ""


def normalize_tag(value: str) -> str:
    value = re.sub(r"[^a-z0-9 -]+", "", value.lower())
    value = re.sub(r"\s+", "-", value).strip("-")
    return value[:32]


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


def command_mount(args: argparse.Namespace, root: Path) -> int:
    config = project_config(root)
    ensure_dirs(config)
    recommendation = build_mount_recommendation(root, args)

    print("Mount check")
    for status, label, detail in recommendation.checks:
        print(f"{status} {label}: {detail}")
    print(f"Recommended model command: {shell_join(recommendation.model_command) if recommendation.model_command else 'none'}")
    print(f"Model note: {recommendation.model_note}")
    print("Model hook setup: create provider-specific hooks in ignored local state such as _state/model-enrich-local.")
    print(f"Recommended digest command: {recommendation.digest_command}")

    if args.check:
        return 0

    raw = read_config_raw(root)
    mounted = mounted_config(raw, args, recommendation.model_command)
    rendered = render_config_toml(mounted)
    print(f"[dry-run] Mount config target: {config.state.relative_to(root)}/config.toml")
    print(rendered.rstrip())
    if not args.apply:
        print("Dry run only. Re-run with --apply to write _state/config.toml.")
        return 0

    write_text_atomic(config.state / "config.toml", rendered)
    print("Applied mount config.")
    return 0


def build_mount_recommendation(root: Path, args: argparse.Namespace) -> MountRecommendation:
    python = project_python(root)
    checks: list[tuple[str, str, str]] = []
    checks.append(("OK", "project_root", str(root)))
    checks.append(("OK" if (root / ".git").exists() else "WARN", "git", "Git repo found." if (root / ".git").exists() else "No .git directory found."))
    checks.append(("OK" if Path(python).exists() or shutil.which(python) else "WARN", "python", python))
    checks.append(("OK" if python_has_module(python, "pypdf") else "WARN", "pdf_parser", "pypdf available" if python_has_module(python, "pypdf") else "Install optional dependency with `python -m pip install -e '.[pdf]'`."))
    checks.append(("OK" if shutil.which("ocrmypdf") else "WARN", "ocr_tool", "ocrmypdf available" if shutil.which("ocrmypdf") else "Install `ocrmypdf` for local scanned-PDF repair."))
    checks.append(("OK" if shutil.which("tesseract") else "WARN", "ocr_engine", "tesseract available" if shutil.which("tesseract") else "`ocrmypdf` usually needs Tesseract installed."))

    detected = detected_model_commands()
    for name, path in detected.items():
        checks.append(("OK", f"model_cli_{name}", path))
    if not detected:
        checks.append(("WARN", "model_cli", "No supported model CLI found in PATH."))

    model_command_value, note = recommended_mount_model_command(root, args, detected)
    digest_command = recommended_digest_command(root, args.digest)
    return MountRecommendation(model_command=model_command_value, model_note=note, digest_command=digest_command, checks=checks)


def project_python(root: Path) -> str:
    venv_python = root / ".venv" / "bin" / "python"
    return str(venv_python.relative_to(root)) if venv_python.exists() else "python3"


def python_has_module(python: str, module: str) -> bool:
    try:
        completed = subprocess.run([python, "-c", f"import {module}"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    except OSError:
        return False
    return completed.returncode == 0


def command_available(command: str) -> bool:
    path = Path(command)
    if path.parent != Path("."):
        return path.exists() and os.access(path, os.X_OK)
    return shutil.which(command) is not None


def detected_model_commands() -> dict[str, str]:
    names = ["codex", "claude", "openai", "ollama"]
    detected: dict[str, str] = {}
    for name in names:
        path = shutil.which(name)
        if path:
            detected[name] = path
    bundled_codex = Path("/Applications/Codex.app/Contents/Resources/codex")
    if "codex" not in detected and bundled_codex.exists():
        detected["codex"] = str(bundled_codex)
    return detected


def recommended_mount_model_command(root: Path, args: argparse.Namespace, detected: dict[str, str]) -> tuple[list[str], str]:
    if args.model_command:
        return shlex.split(args.model_command), "Using explicit --model-command."
    if args.model == "none" or args.privacy == "local":
        return [], "Model enrichment disabled."
    if args.model == "custom":
        raise ValueError("--model custom requires --model-command.")
    if args.model == "codex":
        if "codex" in detected:
            return [], "Codex CLI detected, but no model command was configured. Provide --model-command with a JSON-compatible Codex wrapper."
        raise ValueError("Codex was requested, but no Codex CLI was found.")
    if detected:
        names = ", ".join(sorted(detected))
        return [], f"Detected model CLI(s): {names}. Provide --model-command for the provider-specific JSON hook you want to use."
    return [], "No model CLI found. Provide --model-command later or use --model none."


def recommended_digest_command(root: Path, mode: str) -> str:
    librarian = ".venv/bin/librarian" if (root / ".venv" / "bin" / "librarian").exists() else "librarian"
    commands = {
        "none": "none",
        "notify": f"{librarian} weekly",
        "apply": f"{librarian} weekly --apply",
        "email": f"{librarian} weekly --email --apply",
    }
    return commands[mode]


def read_config_raw(root: Path) -> dict:
    path = root / "_state" / "config.toml"
    if not path.exists():
        return {}
    return tomllib.loads(path.read_text(encoding="utf-8"))


def mounted_config(raw: dict, args: argparse.Namespace, recommended_model_command: list[str]) -> dict:
    paths = dict(raw.get("paths", {}))
    behavior = dict(raw.get("behavior", {}))
    defaults = tomllib.loads(sample_config())
    merged = {
        "paths": {**defaults.get("paths", {}), **paths},
        "behavior": {**defaults.get("behavior", {}), **behavior},
    }
    merged["behavior"]["model_command"] = recommended_model_command
    merged["behavior"]["use_model_assistance"] = args.privacy == "automatic" and bool(recommended_model_command)
    merged["behavior"]["use_catalog_lookup"] = bool(behavior.get("use_catalog_lookup", False))
    merged["behavior"]["require_external_model_approval"] = bool(behavior.get("require_external_model_approval", True))
    return merged


def render_config_toml(raw: dict) -> str:
    lines: list[str] = []
    for section in ["paths", "behavior"]:
        lines.append(f"[{section}]")
        for key, value in raw.get(section, {}).items():
            lines.append(f"{key} = {toml_literal(value)}")
        lines.append("")
    return "\n".join(lines)


def toml_literal(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(toml_literal(item) for item in value) + "]"
    return json.dumps(str(value))


def shell_join(command: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in command)


def shell_quote(value: str) -> str:
    return shlex.quote(value)


def command_reindex(args: argparse.Namespace, root: Path) -> int:
    config = project_config(root)
    ensure_dirs(config)
    use_model_enrichment = args.enrich or config.use_model_assistance
    if use_model_enrichment and not config.model_command:
        print("Model enrichment requires `model_command` in _state/config.toml or LIBRARIAN_MODEL_COMMAND.")
        return 2
    existing_entries = {entry.filename: entry for entry in read_index(config.index)}
    rebuilt: list[WorkEntry] = []
    use_catalog_lookup = args.lookup or config.use_catalog_lookup

    for path in library_reading_files(config):
        entry = infer_entry(path, config, use_catalog_lookup=use_catalog_lookup, use_model_enrichment=use_model_enrichment)
        entry.filename = path.name
        old = existing_entries.get(path.name)
        if old:
            preserve_existing_state(entry, old)
            if not use_model_enrichment:
                preserve_existing_semantics(entry, old)
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
    use_model_enrichment = args.enrich or config.use_model_assistance
    if use_model_enrichment and not config.model_command:
        print("Model enrichment requires `model_command` in _state/config.toml or LIBRARIAN_MODEL_COMMAND.")
        return 2
    use_catalog_lookup = args.lookup or config.use_catalog_lookup
    plan = build_maintenance_plan(config, use_catalog_lookup=use_catalog_lookup, use_model_enrichment=use_model_enrichment)

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


def command_prepare_inbox(args: argparse.Namespace, root: Path) -> int:
    config = project_config(root)
    ensure_dirs(config)
    plans = build_inbox_preparation_plan(config, use_catalog_lookup=args.lookup)
    if not plans:
        print("No inbox preparation needed.")
        return 0

    prefix = "[dry-run] " if not args.apply else ""
    for source, ocr_target, original_target in plans:
        print(f"{prefix}OCR inbox PDF: {source.relative_to(root)} -> {ocr_target.relative_to(root)}")
        print(f"{prefix}Preserve original scan: {original_target.relative_to(root)}")

    if not args.apply:
        print("Dry run only. Re-run with --apply to prepare scanned inbox PDFs.")
        return 0

    if not config.ocr_command:
        print("OCR requires `ocr_command` in _state/config.toml or LIBRARIAN_OCR_COMMAND.")
        return 2
    if not command_available(config.ocr_command[0]):
        print(f"OCR command not found: {config.ocr_command[0]}")
        return 2

    changed = 0
    for source, ocr_target, original_target in plans:
        ocr_target.parent.mkdir(parents=True, exist_ok=True)
        original_target.parent.mkdir(parents=True, exist_ok=True)
        completed = subprocess.run(
            config.ocr_command + [str(source), str(ocr_target)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            print(f"SKIP {source.name}: OCR command failed.")
            if completed.stderr.strip():
                print(completed.stderr.strip())
            continue
        move_without_overwrite(source, original_target)
        changed += 1
        print(f"Prepared OCR inbox copy {ocr_target.relative_to(root)}; preserved original at {original_target.relative_to(root)}.")
    print(f"Prepared {changed} scanned inbox PDF{'s' if changed != 1 else ''}.")
    return 0


def build_inbox_preparation_plan(config: Config, use_catalog_lookup: bool = False) -> list[tuple[Path, Path, Path]]:
    plans: list[tuple[Path, Path, Path]] = []
    reserved_inbox = {path.name for path in config.inbox.iterdir() if path.is_file()} if config.inbox.exists() else set()
    original_dir = config.ocr_outputs / "original-inbox-scans"
    reserved_originals = {path.name for path in original_dir.iterdir() if path.is_file()} if original_dir.exists() else set()

    for source in supported_files(config, config.inbox):
        if source.suffix.lower() != ".pdf":
            continue
        _metadata, text, review = extract_pdf(source)
        if text.strip():
            continue
        if any("PDF extraction failed" in item for item in review):
            continue
        entry = infer_entry(source, config, use_catalog_lookup=use_catalog_lookup, use_model_enrichment=False)
        target_name = make_filename(entry, config, source.suffix.lower())
        if target_name == source.name or target_name.startswith("Unknown_") or not filename_convention_ok(target_name):
            target_name = f"{source.stem}_ocr{source.suffix.lower()}"
        target_name = unique_filename(config.inbox, target_name, source, reserved_inbox - {source.name})
        reserved_inbox.add(target_name)
        original_name = unique_filename(original_dir, source.name, source, reserved_originals)
        reserved_originals.add(original_name)
        plans.append((source, config.inbox / target_name, original_dir / original_name))
    return plans


def command_daily(args: argparse.Namespace, root: Path) -> int:
    config = project_config(root)
    ensure_dirs(config)
    before_entries = read_index(config.index)
    before_inbox = len(supported_files(config, config.inbox))
    auto_lookup = args.lookup or config.use_catalog_lookup
    auto_enrich = args.enrich or config.use_model_assistance
    if auto_enrich and not config.model_command:
        print("Daily workflow: model enrichment skipped; model_command is not configured.")
        auto_enrich = False

    print("Daily workflow: prepare inbox")
    prepare_code = command_prepare_inbox(
        argparse.Namespace(apply=args.apply, lookup=auto_lookup),
        root,
    )
    if prepare_code:
        return prepare_code

    print("Daily workflow: ingest")
    ingest_code = command_ingest(
        argparse.Namespace(apply=args.apply, lookup=auto_lookup, enrich=auto_enrich),
        root,
    )
    if ingest_code:
        return ingest_code

    if args.maintain:
        print("Daily workflow: maintain")
        maintain_code = command_maintain(
            argparse.Namespace(apply=args.apply, lookup=auto_lookup, enrich=auto_enrich),
            root,
        )
        if maintain_code:
            return maintain_code

    print("Daily workflow: lint")
    lint_code = command_lint(argparse.Namespace(apply=False), root)
    if lint_code == 0:
        after_entries = read_index(config.index)
        print(render_run_summary("Daily summary", config, before_entries, after_entries, before_inbox))
    return lint_code


def render_run_summary(label: str, config: Config, before_entries: list[WorkEntry], after_entries: list[WorkEntry], before_inbox: int | None = None) -> str:
    before_names = {entry.filename for entry in before_entries}
    after_names = {entry.filename for entry in after_entries}
    added = len(after_names - before_names)
    before_ready = sum(entry_digest_ready(entry) for entry in before_entries)
    after_status = build_library_status(config, after_entries)
    ready_delta = after_status.digest_ready - before_ready
    inbox_part = f"; inbox {before_inbox}->{after_status.inbox_count}" if before_inbox is not None else f"; inbox {after_status.inbox_count}"
    return "\n".join(
        [
            label,
            f"Works: {len(before_entries)}->{len(after_entries)} ({added} added); digest-ready {before_ready}->{after_status.digest_ready} ({ready_delta:+d}){inbox_part}.",
            f"Review blockers: {after_status.review_count}; unsent ready: {after_status.unsent_ready}.",
            f"Next weekly pick: {after_status.next_title if not after_status.next_author else after_status.next_title + ' by ' + after_status.next_author}.",
        ]
    )


def command_repair(args: argparse.Namespace, root: Path) -> int:
    config = project_config(root)
    ensure_dirs(config)
    if args.enrich and not config.model_command:
        print("Model enrichment requires `model_command` in _state/config.toml or LIBRARIAN_MODEL_COMMAND.")
        return 2

    entries = read_index(config.index)
    selected = match_entries(entries, args.query) if args.query else repair_candidates(entries)
    if not selected:
        print("No entries matched repair criteria.")
        return 0

    action_prefix = "[dry-run]" if not args.apply else "[apply]"
    print(f"{action_prefix} Repair {len(selected)} entr{'y' if len(selected) == 1 else 'ies'}.")
    selected_names = {entry.filename for entry in selected}

    if args.ocr:
        for entry in selected:
            if entry.next_action == "needs_ocr":
                print(f"{action_prefix} OCR/promote: {entry.filename}")

    metadata_plan = build_targeted_metadata_repair_plan(config, selected_names, use_catalog_lookup=args.lookup)
    rename_sources = {rename.source_name for rename in metadata_plan.renames}
    rename_targets = {rename.target_name for rename in metadata_plan.renames}
    preview_names = (selected_names - rename_sources) | rename_targets
    for rename in metadata_plan.renames:
        print(f"{action_prefix} RENAME: {rename.source_name} -> {rename.target_name}")
    for entry in sorted(metadata_plan.entries, key=lambda item: (item.author_key, item.display_title.lower())):
        if entry.filename in preview_names and entry_needs_review(entry):
            print(f"{action_prefix} REVIEW {entry.next_action}: {entry.filename} — {entry.author} — {entry.display_title}: {'; '.join(review_reasons(entry))}")

    if args.enrich:
        for entry in selected:
            if entry.next_action == "needs_model" or not entry.primer_prompts or not usable_digest_summary(entry):
                print(f"{action_prefix} ENRICH: {entry.filename}")

    if not args.apply:
        print("Dry run only. Re-run with --apply to repair matching entries.")
        return 0

    if args.ocr:
        for entry in list(selected):
            if entry.next_action == "needs_ocr":
                code = command_ocr(
                    argparse.Namespace(query=entry.filename, apply=True, promote=True, lookup=args.lookup, enrich=False),
                    root,
                )
                if code:
                    return code
        entries = read_index(config.index)
        selected = [entry for entry in entries if entry.filename in selected_names or (args.query and match_entries([entry], args.query))]
        selected_names = {entry.filename for entry in selected}

    if args.lookup:
        metadata_plan = build_targeted_metadata_repair_plan(config, selected_names, use_catalog_lookup=True)
        rename_sources = {rename.source_name for rename in metadata_plan.renames}
        rename_targets = {rename.target_name for rename in metadata_plan.renames}
        for rename in metadata_plan.renames:
            move_without_overwrite(config.library / rename.source_name, config.library / rename.target_name)
        write_index(config.index, metadata_plan.entries)
        print(f"Applied metadata repair: {len(metadata_plan.renames)} rename(s).")
        entries = read_index(config.index)
        selected_names = (selected_names - rename_sources) | rename_targets
        selected = [entry for entry in entries if entry.filename in selected_names]

    if args.enrich:
        changed = apply_targeted_enrichment(config, selected)
        if changed:
            entries = read_index(config.index)
            by_filename = {entry.filename: entry for entry in entries}
            for enriched in changed:
                if enriched.filename in by_filename:
                    by_filename[enriched.filename].summary = enriched.summary
                    by_filename[enriched.filename].primer_prompts = enriched.primer_prompts
                    by_filename[enriched.filename].tags = enriched.tags
                    by_filename[enriched.filename].related = enriched.related
                    by_filename[enriched.filename].next_action = enriched.next_action
            write_index(config.index, entries)
        print(f"Applied enrichment for {len(changed)} entr{'y' if len(changed) == 1 else 'ies'}.")

    print("Repair complete.")
    return command_lint(argparse.Namespace(apply=False), root)


def repair_candidates(entries: list[WorkEntry]) -> list[WorkEntry]:
    return [entry for entry in entries if entry.status not in {"read", "skipped"} and not entry_digest_ready(entry)]


def build_targeted_metadata_repair_plan(config: Config, filenames: set[str], use_catalog_lookup: bool = False) -> MaintenancePlan:
    existing_entries = {entry.filename: entry for entry in read_index(config.index)}
    library_files = library_reading_files(config)
    reserved = {path.name for path in library_files}
    rebuilt: list[WorkEntry] = []
    renames: list[RenamePlan] = []

    for path in library_files:
        old = existing_entries.get(path.name)
        if path.name not in filenames:
            if old:
                rebuilt.append(old)
            continue
        entry = infer_entry(path, config, use_catalog_lookup=use_catalog_lookup, use_model_enrichment=False)
        if old:
            preserve_existing_state(entry, old)
            if old.next_action == "clean" and entry_needs_review(entry):
                preserve_existing_semantics(entry, old)
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


def apply_targeted_enrichment(config: Config, entries: list[WorkEntry]) -> list[WorkEntry]:
    changed: list[WorkEntry] = []
    for entry in entries:
        if entry.status in {"read", "skipped"}:
            continue
        if entry.next_action != "needs_model" and entry.primer_prompts and usable_digest_summary(entry):
            continue
        path = config.library / entry.filename
        text, review = extract_text_for_enrichment(path)
        if review:
            print(f"SKIP {entry.filename}: {'; '.join(review)}")
            continue
        attempt = try_enrich_from_model(config, entry, text)
        enrichment = attempt.enrichment
        if not enrichment:
            print(f"SKIP {entry.filename}: {attempt.reason}.")
            continue
        entry.summary = enrichment.summary
        entry.primer_prompts = enrichment.primer_prompts
        entry.tags = dedupe(entry.tags + enrichment.tags)[:6]
        entry.related = enrichment.related or entry.related
        entry.next_action = "clean"
        changed.append(entry)
    return changed


def command_weekly(args: argparse.Namespace, root: Path) -> int:
    return command_digest(
        argparse.Namespace(
            apply=args.apply,
            allow_repeats=args.allow_repeats,
            notify=not args.no_notify,
            email=args.email,
            notify_mac=args.notify_mac,
            open=args.open,
            message_self=args.message_self,
        ),
        root,
    )


def build_maintenance_plan(config: Config, use_catalog_lookup: bool = False, use_model_enrichment: bool = False) -> MaintenancePlan:
    existing_entries = {entry.filename: entry for entry in read_index(config.index)}
    library_files = library_reading_files(config)
    reserved = {path.name for path in library_files}
    rebuilt: list[WorkEntry] = []
    renames: list[RenamePlan] = []

    for path in library_files:
        entry = infer_entry(path, config, use_catalog_lookup=use_catalog_lookup, use_model_enrichment=use_model_enrichment)
        old = existing_entries.get(path.name)
        if old:
            preserve_existing_state(entry, old)
            if not use_model_enrichment:
                preserve_existing_semantics(entry, old)

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


def preserve_existing_semantics(entry: WorkEntry, old: WorkEntry) -> None:
    if old.next_action != "clean":
        return
    entry.summary = old.summary
    entry.primer_prompts = list(old.primer_prompts)
    entry.tags = list(old.tags)
    entry.related = old.related
    entry.next_action = old.next_action


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
        if entry.next_action == "clean" and not entry.primer_prompts:
            issues.append(LintIssue("MISSING_FIELD", f"`{entry.title}` is missing primer prompts."))

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
    before_entries = [replace_entry(entry) for entry in entries]
    plan = build_digest_plan(config, entries, allow_repeats=args.allow_repeats)

    if not plan:
        print("No digest-ready unread works found. Run `librarian enrich --apply` or ingest new files with `librarian ingest --enrich --apply`.")
        guidance = digest_blocker_guidance(entries)
        if guidance:
            print("Next actions:")
            for line in guidance:
                print(f"- {line}")
        return 1

    if args.apply and args.email:
        require_email_config(config)
    if args.apply and args.message_self:
        require_message_config(config)
    prefix = "[dry-run] " if not args.apply else ""
    print(f"{prefix}Digest pick: {plan.entry.display_title} by {plan.entry.author}")
    print(f"{prefix}Draft path: {plan.draft_path.relative_to(root)}")
    if args.notify_mac:
        print(f"{prefix}Mac notification: {plan.entry.display_title}")
    if args.open:
        print(f"{prefix}Open file: {(config.library / plan.entry.filename).relative_to(root)}")
    if args.message_self:
        recipient = configured_message_recipient(config) or "unconfigured recipient"
        print(f"{prefix}Message self: {recipient}")
    if args.notify:
        print(render_digest_notification(plan.entry, plan.draft_path, plan.history))
    if not args.apply:
        print(plan.body)
        print("Dry run only. Re-run with --apply to write the draft and sent log.")
        if args.email:
            print("Email not sent in dry-run mode.")
        if args.notify_mac or args.open or args.message_self:
            print("Local delivery not run in dry-run mode.")
        return 0

    write_text_without_overwrite(plan.draft_path, plan.body)
    if args.email:
        send_digest_email(config, plan.entry, plan.body)
    plan.entry.sent = today()
    entries = upsert_entry(entries, plan.entry)
    write_index(config.index, entries)
    append_sent_log(config.sent_log, plan.entry, plan.draft_path, emailed=args.email)
    print(f"Wrote {plan.draft_path.relative_to(root)}.")
    if args.email:
        print("Sent digest email.")
    run_local_delivery(config, plan, root, args)
    print(render_run_summary("Weekly summary", config, before_entries, entries))
    return 0


def replace_entry(entry: WorkEntry) -> WorkEntry:
    return WorkEntry(
        author=entry.author,
        title=entry.title,
        year=entry.year,
        work_type=entry.work_type,
        filename=entry.filename,
        original_filename=entry.original_filename,
        status=entry.status,
        sent=entry.sent,
        reading_time=entry.reading_time,
        summary=entry.summary,
        primer_prompts=list(entry.primer_prompts),
        tags=list(entry.tags),
        related=entry.related,
        needs_review=list(entry.needs_review),
        next_action=entry.next_action,
        added=entry.added,
    )


def command_reply(args: argparse.Namespace, root: Path) -> int:
    config = project_config(root)
    ensure_dirs(config)
    entries = read_index(config.index)
    current = latest_sent_entry(config, entries)
    if not current:
        print("No sent digest found. Run `librarian weekly --apply` before using reply commands.")
        return 1

    target_status = "read" if args.action == "read" else "skipped"
    prefix = "[dry-run] " if not args.apply else ""
    print(f"{prefix}Latest digest: {current.display_title}: {current.status} -> {target_status}")

    if args.action in {"read", "skip"}:
        if not args.apply:
            print("Dry run only. Re-run with --apply to update index.md.")
            return 0
        update_entry_status(config, entries, current, target_status)
        print(f"Updated {current.display_title} to {target_status}.")
        return 0

    old_status = current.status
    current.status = "skipped"
    plan = build_digest_plan(config, entries, allow_repeats=args.allow_repeats)
    if not plan:
        current.status = old_status
        print("No replacement digest-ready unread works found.")
        if not args.apply:
            print("Dry run only. Re-run with --apply to mark the latest digest skipped anyway.")
        return 1

    print(f"{prefix}Replacement digest pick: {plan.entry.display_title} by {plan.entry.author}")
    print(f"{prefix}Draft path: {plan.draft_path.relative_to(root)}")
    if not args.no_notify:
        print(render_digest_notification(plan.entry, plan.draft_path, plan.history))
    if not args.apply:
        print(plan.body)
        print("Dry run only. Re-run with --apply to skip the current pick and write the replacement draft.")
        if args.email:
            print("Email not sent in dry-run mode.")
        return 0

    if args.email:
        require_email_config(config)
    write_text_without_overwrite(plan.draft_path, plan.body)
    if args.email:
        send_digest_email(config, plan.entry, plan.body)
    if old_status != "skipped":
        append_status_log(config.status_log, current, old_status, "skipped")
    plan.entry.sent = today()
    entries = upsert_entry(entries, plan.entry)
    write_index(config.index, entries)
    append_sent_log(config.sent_log, plan.entry, plan.draft_path, emailed=args.email)
    print(f"Updated {current.display_title} to skipped.")
    print(f"Wrote {plan.draft_path.relative_to(root)}.")
    if args.email:
        print("Sent digest email.")
    return 0


def latest_sent_entry(config: Config, entries: list[WorkEntry]) -> WorkEntry | None:
    filename = latest_sent_filename(config.sent_log)
    if filename:
        return next((entry for entry in entries if entry.filename == filename), None)
    sent_entries = [entry for entry in entries if entry.sent != "never"]
    if not sent_entries:
        return None
    return sorted(sent_entries, key=lambda entry: (entry.sent, entry.author_key, entry.display_title.lower()), reverse=True)[0]


def latest_sent_filename(path: Path) -> str:
    if not path.exists():
        return ""
    for line in reversed(path.read_text(encoding="utf-8").splitlines()):
        match = re.search(r"`([^`]+)`", line)
        if match:
            return match.group(1)
    return ""


def update_entry_status(config: Config, entries: list[WorkEntry], entry: WorkEntry, status: str) -> None:
    old_status = entry.status
    entry.status = status
    write_index(config.index, entries)
    if old_status != status:
        append_status_log(config.status_log, entry, old_status, status)


def command_enrich(args: argparse.Namespace, root: Path) -> int:
    config = project_config(root)
    ensure_dirs(config)
    if not config.model_command:
        print("Model enrichment requires `model_command` in _state/config.toml or LIBRARIAN_MODEL_COMMAND.")
        return 2
    entries = read_index(config.index)
    selected = match_entries(entries, args.query) if args.query else [entry for entry in entries if entry.next_action == "needs_model"]
    if not selected:
        print("No entries matched enrichment criteria.")
        return 1

    changed = 0
    for entry in selected:
        path = config.library / entry.filename
        text, review = extract_text_for_enrichment(path)
        if review:
            print(f"[dry-run] SKIP {entry.filename}: {'; '.join(review)}")
            continue
        attempt = try_enrich_from_model(config, entry, text)
        enrichment = attempt.enrichment
        if not enrichment:
            print(f"[dry-run] SKIP {entry.filename}: {attempt.reason}.")
            continue
        print(f"[dry-run] ENRICH {entry.filename}: {enrichment.summary}")
        if args.apply:
            entry.summary = enrichment.summary
            entry.primer_prompts = enrichment.primer_prompts
            entry.tags = dedupe(entry.tags + enrichment.tags)[:6]
            entry.related = enrichment.related or entry.related
            entry.next_action = "clean"
            changed += 1

    if not args.apply:
        print("Dry run only. Re-run with --apply to update index.md.")
        return 0
    if changed:
        write_index(config.index, entries)
    print(f"Applied enrichment for {changed} entr{'y' if changed == 1 else 'ies'}.")
    return 0


def command_ocr(args: argparse.Namespace, root: Path) -> int:
    config = project_config(root)
    ensure_dirs(config)
    entries = read_index(config.index)
    selected = match_entries(entries, args.query) if args.query else [entry for entry in entries if entry.next_action == "needs_ocr"]
    if not selected:
        print("No entries matched OCR criteria.")
        return 1

    plans: list[tuple[WorkEntry, Path, Path]] = []
    for entry in selected:
        source = config.library / entry.filename
        if source.suffix.lower() != ".pdf":
            print(f"[dry-run] SKIP {entry.filename}: OCR is only implemented for PDF files.")
            continue
        if not source.exists():
            print(f"[dry-run] SKIP {entry.filename}: missing library file.")
            continue
        target = unique_path(config.ocr_outputs / entry.filename)
        plans.append((entry, source, target))

    if not plans:
        print("No OCR-ready PDF entries found.")
        return 1

    prefix = "[dry-run] " if not args.apply else ""
    for entry, source, target in plans:
        print(f"{prefix}OCR {entry.display_title}: {source.relative_to(root)} -> {target.relative_to(root)}")

    if args.promote and not args.apply:
        print("Promotion only runs with --apply; dry run will not replace library files.")
    if not args.apply:
        print("Dry run only. Re-run with --apply to write OCR copies under _output/ocr/.")
        return 0

    if args.promote and args.enrich and not config.model_command:
        print("Model enrichment requires `model_command` in _state/config.toml or LIBRARIAN_MODEL_COMMAND.")
        return 2

    if not config.ocr_command:
        print("OCR requires `ocr_command` in _state/config.toml or LIBRARIAN_OCR_COMMAND.")
        return 2
    if not command_available(config.ocr_command[0]):
        print(f"OCR command not found: {config.ocr_command[0]}")
        return 2

    changed = 0
    entries_changed = False
    for entry, source, target in plans:
        target.parent.mkdir(parents=True, exist_ok=True)
        completed = subprocess.run(
            config.ocr_command + [str(source), str(target)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            print(f"SKIP {entry.filename}: OCR command failed.")
            if completed.stderr.strip():
                print(completed.stderr.strip())
            continue
        changed += 1
        print(f"Wrote {target.relative_to(root)}.")
        if args.promote:
            promoted = promote_ocr_copy(config, source, target)
            print(f"Promoted OCR copy to {promoted.relative_to(root)} and preserved original.")
            repaired = infer_entry(promoted, config, use_catalog_lookup=args.lookup, use_model_enrichment=args.enrich)
            repaired.filename = promoted.name
            preserve_existing_state(repaired, entry)
            entries = upsert_entry(entries, repaired)
            entries_changed = True
    if entries_changed:
        write_index(config.index, entries)
    print(f"Applied OCR for {changed} entr{'y' if changed == 1 else 'ies'}.")
    return 0


def promote_ocr_copy(config: Config, source: Path, ocr_copy: Path) -> Path:
    original_dir = config.ocr_outputs / "original-library-files"
    original_dir.mkdir(parents=True, exist_ok=True)
    preserved = unique_path(original_dir / source.name)
    move_without_overwrite(source, preserved)
    move_without_overwrite(ocr_copy, source)
    return source


def extract_text_for_enrichment(path: Path) -> tuple[str, list[str]]:
    if not path.exists():
        return "", [f"Missing file: {path.name}"]
    if path.suffix.lower() == ".pdf":
        _, text, review = extract_pdf(path)
        if not text.strip() and not review:
            review.append("No extractable text found; OCR is needed before model enrichment.")
        return text, review
    if path.suffix.lower() in {".txt", ".md"}:
        try:
            return path.read_text(encoding="utf-8", errors="replace"), []
        except OSError as exc:
            return "", [f"Could not read text: {exc}"]
    if path.suffix.lower() == ".epub":
        return extract_epub(path)
    if path.suffix.lower() == ".docx":
        return extract_docx(path)
    return "", [f"Text extraction not implemented for {path.suffix.lower()}."]


def build_digest_plan(config: Config, entries: list[WorkEntry], allow_repeats: bool = False) -> DigestPlan | None:
    candidates = [
        entry
        for entry in entries
        if entry_digest_ready(entry)
        and (allow_repeats or entry.sent == "never")
    ]
    if not candidates and allow_repeats:
        candidates = [entry for entry in entries if entry_digest_ready(entry)]
    if not candidates:
        return None

    pick = sorted(candidates, key=lambda item: (item.sent != "never", item.author_key, item.display_title.lower()))[0]
    history = digest_history(config, pick)
    draft_name = f"{today()}_{normalize_filename(compact_pascal(pick.display_title) or 'Read')}.md"
    draft_path = unique_path(config.drafts / draft_name)
    status = build_library_status(config, entries, current_pick=pick)
    draft = digest_draft(pick, config.library / pick.filename, history, status)
    return DigestPlan(pick, draft_path, draft, history)


def digest_blocker_guidance(entries: list[WorkEntry], limit: int = 3) -> list[str]:
    blocked = [
        entry
        for entry in entries
        if entry.status not in {"read", "skipped"} and not entry_digest_ready(entry)
    ]
    ranked = sorted(blocked, key=lambda entry: (digest_blocker_rank(entry), entry.author_key, entry.display_title.lower()))
    return [digest_blocker_line(entry) for entry in ranked[:limit]]


def digest_blocker_rank(entry: WorkEntry) -> int:
    ranks = {
        "needs_model": 0,
        "needs_catalog": 1,
        "needs_ocr": 2,
        "needs_manual": 3,
    }
    if entry.next_action in ranks:
        return ranks[entry.next_action]
    if not entry.primer_prompts or not usable_digest_summary(entry):
        return 0
    return 4


def digest_blocker_line(entry: WorkEntry) -> str:
    title = one_line(entry.display_title)
    if entry.next_action == "needs_model":
        return f"{title} ({entry.author}) needs model enrichment -> librarian enrich {shell_quote(title)}"
    if entry.next_action == "needs_ocr":
        return f"{title} ({entry.author}) needs OCR -> librarian ocr {shell_quote(title)}"
    if entry.next_action == "needs_catalog":
        return f"{title} ({entry.author}) has weak metadata -> librarian maintain --lookup"
    if entry.next_action == "needs_manual":
        reasons = "; ".join(review_reasons(entry)) or "manual review is needed"
        return f"{title} ({entry.author}) needs manual review: {one_line(reasons)}"
    if not entry.primer_prompts or not usable_digest_summary(entry):
        return f"{title} ({entry.author}) needs model enrichment -> librarian enrich {shell_quote(title)}"
    return f"{title} ({entry.author}) is not digest-ready: {one_line('; '.join(review_reasons(entry)) or entry.next_action)}"


def digest_draft(entry: WorkEntry, local_path: Path, history: DigestHistory, status: LibraryStatus | None = None) -> str:
    del local_path
    footer = f"\n{render_status_footer(status, history)}" if status else ""
    return f"""Subject: Read of the Week: {entry.display_title} by {entry.author}

Title: {entry.display_title}
Author: {entry.author}

Summary:
{entry.summary}

Why this is worth reading now:
{digest_rationale(history)}

Primer prompts:
{render_prompt_bullets(entry.primer_prompts)}
{footer}
"""


def build_library_status(config: Config, entries: list[WorkEntry], current_pick: WorkEntry | None = None) -> LibraryStatus:
    ready = [entry for entry in entries if entry_digest_ready(entry)]
    unsent_ready = [entry for entry in ready if entry.sent == "never"]
    current_pick_pending = current_pick is not None and current_pick.sent == "never"
    remaining_unsent_ready = [
        entry
        for entry in unsent_ready
        if current_pick is None or entry.filename != current_pick.filename
    ]
    next_entry = sorted(unsent_ready, key=lambda item: (item.author_key, item.display_title.lower()))
    display_next = current_pick or (next_entry[0] if next_entry else None)
    future = [entry for entry in unsent_ready if display_next is None or entry.filename != display_next.filename]
    future = sorted(future, key=lambda item: (item.author_key, item.display_title.lower()))
    return LibraryStatus(
        total=len(entries),
        unread=sum(entry.status == "unread" for entry in entries),
        read=sum(entry.status == "read" for entry in entries),
        skipped=sum(entry.status == "skipped" for entry in entries),
        sent_total=sum(entry.sent != "never" for entry in entries) + (1 if current_pick_pending else 0),
        digest_ready=len(ready),
        unsent_ready=len(remaining_unsent_ready),
        inbox_count=len(supported_files(config, config.inbox)),
        review_count=sum(entry.status not in {"read", "skipped"} and not entry_digest_ready(entry) for entry in entries),
        next_title=display_next.display_title if display_next else "None",
        next_author=display_next.author if display_next else "",
        next_after_title=future[0].display_title if future else "None",
    )


def render_status_footer(status: LibraryStatus, history: DigestHistory | None = None) -> str:
    lines = [
        "-----",
        "Library status",
    ]
    if history:
        lines.append(f"This work: {human_digest_history(history)}")
    lines.extend(
        [
            f"Library: {status.total} total works; {status.sent_total} sent; {status.read} read; {status.unread} unread; {status.skipped} skipped.",
            f"Queue: {status.unsent_ready} unsent digest-ready works; {status.digest_ready} digest-ready total.",
            f"Needs attention: {status.review_count}; inbox: {status.inbox_count} pending file{'s' if status.inbox_count != 1 else ''}.",
        ]
    )
    return "\n".join(lines)


def render_status_summary(status: LibraryStatus) -> str:
    next_line = status.next_title if not status.next_author else f"{status.next_title} by {status.next_author}"
    return "\n".join(
        [
            "Library status",
            f"Total works: {status.total}",
            f"Total sent: {status.sent_total}",
            f"Read: {status.read}; unread: {status.unread}; skipped: {status.skipped}",
            f"Digest-ready: {status.digest_ready}; unsent ready: {status.unsent_ready}",
            f"Inbox pending: {status.inbox_count}",
            f"Review blockers: {status.review_count}",
            f"Next weekly pick: {next_line}",
            f"Next after that: {status.next_after_title}",
        ]
    )


def command_status(args: argparse.Namespace, root: Path) -> int:
    config = project_config(root)
    ensure_dirs(config)
    entries = read_index(config.index)
    print(render_status_summary(build_library_status(config, entries)))
    return 0


def digest_history(config: Config, entry: WorkEntry) -> DigestHistory:
    sent_count = count_log_entries(config.sent_log, entry.filename)
    if entry.sent != "never" and sent_count == 0:
        sent_count = 1
    skip_count = count_status_transitions(config.status_log, entry.filename, "skipped") if sent_count else 0
    if sent_count and entry.status == "skipped" and skip_count == 0:
        skip_count = 1
    return DigestHistory(sent_count=sent_count, last_sent="" if entry.sent == "never" else entry.sent, skip_count=skip_count)


def count_log_entries(path: Path, filename: str) -> int:
    if not path.exists() or not filename:
        return 0
    marker = inline_code(filename)
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if marker in line)


def count_status_transitions(path: Path, filename: str, status: str) -> int:
    if not path.exists() or not filename:
        return 0
    marker = inline_code(filename)
    target = f"-> {status}"
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if marker in line and target in line)


def human_digest_history(history: DigestHistory) -> str:
    if history.sent_count == 0:
        sent = "First time in the digest"
    elif history.sent_count == 1:
        sent = f"Sent once{last_sent_suffix(history)}"
    else:
        sent = f"Sent {history.sent_count} times{last_sent_suffix(history)}"

    if history.skip_count == 0:
        skipped = "never skipped"
    elif history.skip_count == 1:
        skipped = "skipped once"
    else:
        skipped = f"skipped {history.skip_count} times"
    return f"{sent}; {skipped}."


def last_sent_suffix(history: DigestHistory) -> str:
    return f"; last sent {history.last_sent}" if history.last_sent else ""


def digest_rationale(history: DigestHistory) -> str:
    if history.sent_count == 0:
        return "This unread work is already in the local library and has not been sent before."
    return "This unread work is already in the local library and is being repeated intentionally."


def render_prompt_bullets(prompts: list[str]) -> str:
    return "\n".join(f"- {one_line(prompt)}" for prompt in prompts if one_line(prompt))


def first_primer_prompt(entry: WorkEntry) -> str:
    return one_line(entry.primer_prompts[0]) if entry.primer_prompts else "Review the enriched digest draft before reading."


def entry_digest_ready(entry: WorkEntry) -> bool:
    return (
        entry.status not in {"read", "skipped"}
        and not entry_needs_review(entry)
        and entry.next_action == "clean"
        and usable_digest_summary(entry)
        and bool(entry.primer_prompts)
    )


def usable_digest_summary(entry: WorkEntry) -> bool:
    summary_key = normalize_lookup_text(entry.summary)
    title_key = normalize_lookup_text(entry.display_title)
    if not summary_key or summary_key == title_key:
        return False
    blocked = ["needs review", "no extractable text", "ocr is needed"]
    return not any(marker in entry.summary.lower() for marker in blocked)


def render_digest_notification(entry: WorkEntry, draft_path: Path, history: DigestHistory) -> str:
    del draft_path
    return "\n".join(
        [
            f"NOTIFY: Read of the Week: {entry.display_title}",
            f"Author: {entry.author}",
            f"Summary: {entry.summary}",
            f"History: {human_digest_history(history)}",
            f"Primer prompt: {first_primer_prompt(entry)}",
        ]
    )


def run_local_delivery(config: Config, plan: DigestPlan, root: Path, args: argparse.Namespace) -> None:
    if args.notify_mac:
        send_mac_notification(plan.entry, plan.draft_path)
        print("Posted Mac notification.")
    if args.open:
        open_local_file(config.library / plan.entry.filename)
        print(f"Opened {Path(plan.entry.filename).name}.")
    if args.message_self:
        send_message_to_self(config, plan.entry, plan.draft_path, plan.history)
        print("Sent Messages notification.")


def send_mac_notification(entry: WorkEntry, draft_path: Path) -> None:
    script = (
        'display notification '
        f'{applescript_literal(first_primer_prompt(entry))} '
        'with title "Read of the Week" '
        f'subtitle {applescript_literal(entry.display_title)}'
    )
    run_osascript(script, "Mac notification failed")


def open_local_file(path: Path) -> None:
    completed = subprocess.run(["open", str(path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    if completed.returncode != 0:
        details = one_line(completed.stderr.strip() or completed.stdout.strip())
        raise ValueError(f"Could not open local file: {details}")


def send_message_to_self(config: Config, entry: WorkEntry, draft_path: Path, history: DigestHistory) -> None:
    recipient = require_message_config(config)
    status = build_library_status(config, read_index(config.index), current_pick=entry)
    message = render_self_message(entry, draft_path, history, status)
    script = (
        'tell application "Messages"\n'
        f"  set targetBuddy to {applescript_literal(recipient)}\n"
        '  set targetService to 1st service whose service type = iMessage\n'
        f"  send {applescript_literal(message)} to buddy targetBuddy of targetService\n"
        "end tell"
    )
    run_osascript(script, "Messages send failed")


def render_self_message(entry: WorkEntry, draft_path: Path, history: DigestHistory, status: LibraryStatus) -> str:
    del draft_path
    return "\n".join(
        [
            f"Read of the Week: {entry.display_title}",
            f"Author: {entry.author}",
            f"Summary: {entry.summary}",
            f"Prompt: {first_primer_prompt(entry)}",
            render_status_footer(status, history),
        ]
    )


def run_osascript(script: str, error_prefix: str) -> None:
    completed = subprocess.run(["osascript", "-e", script], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    if completed.returncode != 0:
        details = one_line(completed.stderr.strip() or completed.stdout.strip())
        raise ValueError(f"{error_prefix}: {details}")


def applescript_literal(value: str) -> str:
    return json.dumps(value)


def configured_message_recipient(config: Config) -> str:
    return os.environ.get("LIBRARIAN_MESSAGE_TO", "") or config.message_to


def require_message_config(config: Config) -> str:
    recipient = configured_message_recipient(config)
    if not recipient:
        raise ValueError("Messages delivery requires LIBRARIAN_MESSAGE_TO or message_to in _state/config.toml.")
    return recipient


def send_digest_email(config: Config, entry: WorkEntry, body: str) -> None:
    api_key, sender, recipient = require_email_config(config)
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


def require_email_config(config: Config | None = None) -> tuple[str, str, str]:
    api_key = os.environ.get("RESEND_API_KEY", "")
    sender = os.environ.get("LIBRARIAN_EMAIL_FROM", "") or (config.email_from if config else "")
    recipient = os.environ.get("LIBRARIAN_EMAIL_TO", "") or (config.email_to if config else "")
    if not api_key or not sender or not recipient:
        raise ValueError("Email delivery requires RESEND_API_KEY plus LIBRARIAN_EMAIL_FROM/LIBRARIAN_EMAIL_TO or email_from/email_to in _state/config.toml.")
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
    old_status = entry.status
    print(f"[dry-run] {entry.display_title}: {entry.status} -> {status}")
    if not args.apply:
        print("Dry run only. Re-run with --apply to update index.md.")
        return 0
    entry.status = status
    write_index(config.index, entries)
    append_status_log(config.status_log, entry, old_status, status)
    print(f"Updated {entry.display_title} to {status}.")
    return 0


def append_status_log(path: Path, entry: WorkEntry, old_status: str, new_status: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"- {now_stamp()} — {inline_code(entry.filename)} {old_status} -> {new_status}\n")


def match_entries(entries: list[WorkEntry], query: str) -> list[WorkEntry]:
    needle = query.lower()
    return [
        entry
        for entry in entries
        if needle in entry.title.lower() or needle in entry.filename.lower() or needle in entry.author.lower()
    ]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="librarian")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init")

    mount = sub.add_parser("mount")
    mount.add_argument("--check", action="store_true", help="Inspect mount readiness without printing or writing config changes.")
    mount.add_argument("--apply", action="store_true")
    mount.add_argument("--privacy", choices=["local", "assisted", "automatic"], default="assisted")
    mount.add_argument("--model", choices=["auto", "none", "codex", "custom"], default="auto")
    mount.add_argument("--model-command", help="Explicit JSON enrichment command. Receives JSON on stdin and prints JSON on stdout.")
    mount.add_argument("--digest", choices=["none", "notify", "apply", "email"], default="notify")

    ingest = sub.add_parser("ingest")
    ingest.add_argument("--apply", action="store_true")
    ingest.add_argument("--lookup", action="store_true", help="Use optional Open Library catalog lookup for weak metadata.")
    ingest.add_argument("--enrich", action="store_true", help="Use configured model_command to enrich summary, tags, and primer prompts.")

    lint = sub.add_parser("lint")
    lint.add_argument("--apply", action="store_true")

    reindex = sub.add_parser("reindex")
    reindex.add_argument("--apply", action="store_true")
    reindex.add_argument("--lookup", action="store_true", help="Use optional Open Library catalog lookup for weak metadata.")
    reindex.add_argument("--enrich", action="store_true", help="Use configured model_command to enrich summary, tags, and primer prompts.")

    maintain = sub.add_parser("maintain")
    maintain.add_argument("--apply", action="store_true")
    maintain.add_argument("--lookup", action="store_true", help="Use optional Open Library catalog lookup for weak metadata.")
    maintain.add_argument("--enrich", action="store_true", help="Use configured model_command to enrich summary, tags, and primer prompts.")

    daily = sub.add_parser("daily")
    daily.add_argument("--apply", action="store_true")
    daily.add_argument("--lookup", action="store_true", help="Use optional Open Library catalog lookup for weak metadata.")
    daily.add_argument("--enrich", action="store_true", help="Use configured model_command to enrich summary, tags, and primer prompts.")
    daily.add_argument("--maintain", action="store_true", help="Also run the full library maintenance pass.")

    repair = sub.add_parser("repair")
    repair.add_argument("query", nargs="?", help="Optional title, author, or filename query. Defaults to current review blockers.")
    repair.add_argument("--apply", action="store_true")
    repair.add_argument("--ocr", action="store_true", help="OCR and promote entries marked needs_ocr.")
    repair.add_argument("--lookup", action="store_true", help="Use optional Open Library catalog lookup for weak metadata.")
    repair.add_argument("--enrich", action="store_true", help="Use configured model_command to enrich semantic metadata.")

    weekly = sub.add_parser("weekly")
    weekly.add_argument("--apply", action="store_true")
    weekly.add_argument("--allow-repeats", action="store_true")
    weekly.add_argument("--no-notify", action="store_true")
    weekly.add_argument("--email", action="store_true")
    weekly.add_argument("--notify-mac", action="store_true", help="Post a macOS notification after writing the weekly draft.")
    weekly.add_argument("--open", action="store_true", help="Open the selected local reading file after writing the weekly draft.")
    weekly.add_argument("--message-self", action="store_true", help="Send title, summary, and first prompt to the configured Messages recipient.")

    enrich = sub.add_parser("enrich")
    enrich.add_argument("query", nargs="?", help="Optional title, author, or filename query. Defaults to all needs_model entries.")
    enrich.add_argument("--apply", action="store_true")

    ocr = sub.add_parser("ocr")
    ocr.add_argument("query", nargs="?", help="Optional title, author, or filename query. Defaults to all needs_ocr entries.")
    ocr.add_argument("--apply", action="store_true")
    ocr.add_argument("--promote", action="store_true", help="Preserve the original library PDF and replace it with the OCR-searchable copy.")
    ocr.add_argument("--lookup", action="store_true", help="Use catalog lookup when rebuilding promoted OCR metadata.")
    ocr.add_argument("--enrich", action="store_true", help="Use configured model_command when rebuilding promoted OCR metadata.")

    weekly = sub.add_parser("weekly-pick")
    weekly.add_argument("--apply", action="store_true")
    weekly.add_argument("--allow-repeats", action="store_true")
    weekly.add_argument("--notify", action="store_true")
    weekly.add_argument("--email", action="store_true")
    weekly.add_argument("--notify-mac", action="store_true")
    weekly.add_argument("--open", action="store_true")
    weekly.add_argument("--message-self", action="store_true")

    digest = sub.add_parser("digest")
    digest.add_argument("--apply", action="store_true")
    digest.add_argument("--allow-repeats", action="store_true")
    digest.add_argument("--notify", action="store_true")
    digest.add_argument("--email", action="store_true")
    digest.add_argument("--notify-mac", action="store_true", help="Post a macOS notification after writing the digest draft.")
    digest.add_argument("--open", action="store_true", help="Open the selected local reading file after writing the digest draft.")
    digest.add_argument("--message-self", action="store_true", help="Send title, summary, and first prompt to the configured Messages recipient.")

    reply = sub.add_parser("reply")
    reply.add_argument("action", choices=["skip", "read", "new"])
    reply.add_argument("--apply", action="store_true")
    reply.add_argument("--allow-repeats", action="store_true")
    reply.add_argument("--no-notify", action="store_true")
    reply.add_argument("--email", action="store_true")

    sub.add_parser("list")
    sub.add_parser("status")

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
        if args.command == "mount":
            return command_mount(args, root)
        if args.command == "ingest":
            return command_ingest(args, root)
        if args.command == "lint":
            return command_lint(args, root)
        if args.command == "reindex":
            return command_reindex(args, root)
        if args.command == "maintain":
            return command_maintain(args, root)
        if args.command == "daily":
            return command_daily(args, root)
        if args.command == "repair":
            return command_repair(args, root)
        if args.command == "weekly":
            return command_weekly(args, root)
        if args.command == "weekly-pick":
            return command_weekly_pick(args, root)
        if args.command == "digest":
            return command_digest(args, root)
        if args.command == "reply":
            return command_reply(args, root)
        if args.command == "enrich":
            return command_enrich(args, root)
        if args.command == "ocr":
            return command_ocr(args, root)
        if args.command == "list":
            return command_list(args, root)
        if args.command == "status":
            return command_status(args, root)
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
