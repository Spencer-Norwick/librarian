"""Stable workspace guidance shipped with installed librarian distributions."""

from importlib.resources import files


def workspace_template(name: str) -> str:
    """Read a bundled initialization template without a source checkout."""
    return files("librarian").joinpath("templates", name).read_text(encoding="utf-8")
