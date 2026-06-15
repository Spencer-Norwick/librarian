from __future__ import annotations

import html
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path


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


def extract_epub(path: Path) -> tuple[str, list[str]]:
    review: list[str] = []
    text_parts: list[str] = []
    try:
        with zipfile.ZipFile(path) as archive:
            names = sorted(
                name
                for name in archive.namelist()
                if name.lower().endswith((".xhtml", ".html", ".htm"))
                and not name.endswith("/")
            )
            if not names:
                return "", ["EPUB contains no XHTML/HTML text files."]
            for name in names:
                try:
                    raw = archive.read(name)
                except KeyError:
                    continue
                text = html_document_text(raw)
                if text:
                    text_parts.append(text)
    except (OSError, zipfile.BadZipFile) as exc:
        review.append(f"EPUB extraction failed: {exc}")
    text = "\n\n".join(text_parts)
    if not text.strip() and not review:
        review.append("No extractable EPUB text found.")
    return text, review


def extract_docx(path: Path) -> tuple[str, list[str]]:
    try:
        with zipfile.ZipFile(path) as archive:
            try:
                xml = archive.read("word/document.xml")
            except KeyError:
                return "", ["DOCX is missing word/document.xml."]
    except (OSError, zipfile.BadZipFile) as exc:
        return "", [f"DOCX extraction failed: {exc}"]

    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        return "", [f"DOCX XML extraction failed: {exc}"]

    paragraphs: list[str] = []
    for paragraph in root.iter():
        if not paragraph.tag.endswith("}p") and paragraph.tag != "p":
            continue
        runs: list[str] = []
        for node in paragraph.iter():
            if node.tag.endswith("}t") or node.tag == "t":
                runs.append(node.text or "")
            elif node.tag.endswith("}tab") or node.tag == "tab":
                runs.append("\t")
        text = "".join(runs).strip()
        if text:
            paragraphs.append(text)

    text = "\n\n".join(paragraphs)
    if not text.strip():
        return "", ["No extractable DOCX text found."]
    return text, []


def html_document_text(raw: bytes) -> str:
    text = raw.decode("utf-8", errors="replace")
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", text)
    text = re.sub(r"(?is)<br\s*/?>", "\n", text)
    text = re.sub(r"(?is)</p\s*>", "\n\n", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = html.unescape(text)
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)
