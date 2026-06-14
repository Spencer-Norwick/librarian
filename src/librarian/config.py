from __future__ import annotations

import os
import shlex
import tomllib
from pathlib import Path

from .domain import SUPPORTED_EXTENSIONS, Config


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
        status_log=p("status_log", "_state/status-log.md"),
        quarantine=p("quarantine", "_quarantine"),
        drafts=p("weekly_read_drafts", "_output/weekly-read-drafts"),
        ocr_outputs=p("ocr_outputs", "_output/ocr"),
        supported_extensions={ext.lower() for ext in supported},
        reading_words_per_minute=int(behavior.get("reading_words_per_minute", 250)),
        max_filename_stem_chars=int(behavior.get("max_filename_stem_chars", 96)),
        ocr_command=ocr_command(behavior.get("ocr_command", ["ocrmypdf", "--skip-text"])),
        use_catalog_lookup=bool(behavior.get("use_catalog_lookup", False)),
        catalog_timeout_seconds=float(behavior.get("catalog_timeout_seconds", 5.0)),
        use_model_assistance=bool(behavior.get("use_model_assistance", False)),
        model_command=model_command(behavior.get("model_command", [])),
        model_max_input_chars=int(behavior.get("model_max_input_chars", 12000)),
        require_external_model_approval=bool(behavior.get("require_external_model_approval", True)),
        email_from=str(behavior.get("email_from", "")),
        email_to=str(behavior.get("email_to", "")),
        message_to=str(behavior.get("message_to", "")),
    )


def ensure_dirs(config: Config) -> None:
    for path in [config.inbox, config.library, config.state, config.quarantine, config.drafts, config.ocr_outputs]:
        path.mkdir(parents=True, exist_ok=True)


def safe_project_path(root: Path, value: str) -> Path:
    root = root.resolve()
    candidate = (root / value).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError(f"Configured path escapes project root: {value}")
    return candidate


def model_command(value: object) -> list[str]:
    env_value = os.environ.get("LIBRARIAN_MODEL_COMMAND", "")
    if env_value:
        return shlex.split(env_value)
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return shlex.split(value)
    return []


def ocr_command(value: object) -> list[str]:
    env_value = os.environ.get("LIBRARIAN_OCR_COMMAND", "")
    if env_value:
        return shlex.split(env_value)
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return shlex.split(value)
    return ["ocrmypdf", "--skip-text"]


def sample_config() -> str:
    return """[paths]
inbox = "inbox"
library = "library"
index = "library/index.md"
state = "_state"
ingest_log = "_state/ingest-log.md"
sent_log = "_state/sent-log.md"
status_log = "_state/status-log.md"
quarantine = "_quarantine"
weekly_read_drafts = "_output/weekly-read-drafts"
ocr_outputs = "_output/ocr"

[behavior]
supported_extensions = [".pdf", ".epub", ".txt", ".md", ".docx"]
reading_words_per_minute = 250
max_filename_stem_chars = 96
ocr_command = ["ocrmypdf", "--skip-text"]
use_model_assistance = false
model_command = []
model_max_input_chars = 12000
require_external_model_approval = true
use_catalog_lookup = false
catalog_timeout_seconds = 5
email_from = ""
email_to = ""
message_to = ""
"""
