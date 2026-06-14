from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


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


def clean_work_type(value: str) -> str:
    value = value.lower().strip()
    aliases = {"ebook": "book", "essays": "essay", "stories": "story"}
    value = aliases.get(value, value)
    return value if value in WORK_TYPES else "unknown"


def author_sort_key(author: str) -> str:
    if author == "Unknown":
        return "zzzzzz unknown"
    return author.lower()


@dataclass
class Config:
    inbox: Path
    library: Path
    index: Path
    state: Path
    ingest_log: Path
    sent_log: Path
    status_log: Path
    quarantine: Path
    drafts: Path
    ocr_outputs: Path
    supported_extensions: set[str] = field(default_factory=lambda: set(SUPPORTED_EXTENSIONS))
    reading_words_per_minute: int = 250
    max_filename_stem_chars: int = 96
    ocr_command: list[str] = field(default_factory=lambda: ["ocrmypdf", "--skip-text"])
    use_catalog_lookup: bool = False
    catalog_timeout_seconds: float = 5.0
    use_model_assistance: bool = False
    model_command: list[str] = field(default_factory=list)
    model_max_input_chars: int = 12000
    require_external_model_approval: bool = True
    email_from: str = ""
    email_to: str = ""
    message_to: str = ""


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
    primer_prompts: list[str] = field(default_factory=list)
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
    history: "DigestHistory"


@dataclass
class LibraryStatus:
    total: int
    unread: int
    read: int
    skipped: int
    digest_ready: int
    unsent_ready: int
    inbox_count: int
    review_count: int
    next_title: str
    next_author: str
    next_after_title: str


@dataclass
class DigestHistory:
    sent_count: int = 0
    last_sent: str = ""
    skip_count: int = 0


@dataclass
class ModelEnrichment:
    summary: str = ""
    primer_prompts: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    related: str = ""


@dataclass
class ModelEnrichmentAttempt:
    enrichment: ModelEnrichment | None = None
    reason: str = ""


@dataclass
class MountRecommendation:
    model_command: list[str]
    model_note: str
    digest_command: str
    checks: list[tuple[str, str, str]]
