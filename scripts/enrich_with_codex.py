#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["summary", "primer_prompts", "tags", "related"],
    "properties": {
        "summary": {"type": "string"},
        "primer_prompts": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 3},
        "tags": {"type": "array", "items": {"type": "string"}, "maxItems": 6},
        "related": {"type": "string"},
    },
}


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(f"Invalid enrichment input JSON: {exc}", file=sys.stderr)
        return 2

    codex = find_codex()
    if not codex:
        print("Could not find Codex CLI. Set CODEX_BIN to the Codex executable.", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory(prefix="librarian-codex-") as tmp:
        tmp_path = Path(tmp)
        schema_path = tmp_path / "schema.json"
        output_path = tmp_path / "output.json"
        schema_path.write_text(json.dumps(SCHEMA), encoding="utf-8")

        command = [
            codex,
            "exec",
            "--ephemeral",
            "--sandbox",
            "read-only",
            "--output-schema",
            str(schema_path),
            "-o",
            str(output_path),
            build_prompt(payload),
        ]
        model = os.environ.get("LIBRARIAN_CODEX_MODEL", "").strip()
        if model:
            command[2:2] = ["--model", model]

        try:
            completed = subprocess.run(
                command,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=int(os.environ.get("LIBRARIAN_CODEX_TIMEOUT", "300")),
                check=False,
            )
        except subprocess.TimeoutExpired:
            print("Codex enrichment timed out.", file=sys.stderr)
            return 2

        if completed.stdout.strip():
            print(completed.stdout.strip(), file=sys.stderr)
        if completed.stderr.strip():
            print(completed.stderr.strip(), file=sys.stderr)
        if completed.returncode != 0:
            return completed.returncode

        raw = output_path.read_text(encoding="utf-8") if output_path.exists() else completed.stdout

    try:
        result = normalize_result(raw)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(json.dumps(result, ensure_ascii=False))
    return 0


def find_codex() -> str:
    configured = os.environ.get("CODEX_BIN", "").strip()
    if configured:
        return configured
    found = shutil.which("codex")
    if found:
        return found
    bundled = Path("/Applications/Codex.app/Contents/Resources/codex")
    return str(bundled) if bundled.exists() else ""


def build_prompt(payload: dict) -> str:
    return (
        "You enrich a reading-library index entry.\n"
        "Use only the JSON payload below. Do not run commands, inspect files, or add commentary.\n"
        "Return only JSON matching the requested schema.\n\n"
        "Rules:\n"
        "- Write a concise, specific summary in 1-3 sentences.\n"
        "- Write 2-3 primer_prompts tailored to this exact work, not generic reading questions.\n"
        "- Tags should be short, lowercase topical labels.\n"
        "- Do not invent bibliographic facts beyond the metadata and excerpt.\n"
        "- If the excerpt is mostly front matter, say what can be inferred from it without pretending to know more.\n\n"
        f"Payload:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def normalize_result(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Codex did not return valid JSON: {exc}") from exc

    summary = one_line(str(parsed.get("summary", "")))
    prompts = [one_line(str(item)) for item in parsed.get("primer_prompts", []) if one_line(str(item))]
    tags = [normalize_tag(str(item)) for item in parsed.get("tags", []) if normalize_tag(str(item))]
    related = one_line(str(parsed.get("related", ""))) or "None."
    if not summary or len(prompts) < 2:
        raise ValueError("Codex enrichment output was missing summary or primer_prompts.")
    return {
        "summary": summary,
        "primer_prompts": prompts[:3],
        "tags": tags[:6],
        "related": related,
    }


def one_line(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def normalize_tag(value: str) -> str:
    value = re.sub(r"[^a-z0-9 -]+", "", value.lower())
    value = re.sub(r"\s+", "-", value).strip("-")
    return value[:32]


if __name__ == "__main__":
    raise SystemExit(main())
