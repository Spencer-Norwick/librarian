"""Regression checks for setup without the application's source checkout."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path


def test_init_uses_bundled_templates_outside_source_checkout() -> None:
    package = Path(__file__).resolve().parents[1] / "src" / "librarian"
    with tempfile.TemporaryDirectory() as directory:
        temporary = Path(directory)
        site_packages = temporary / "site-packages"
        shutil.copytree(package, site_packages / "librarian", ignore=shutil.ignore_patterns("__pycache__"))
        workspace = temporary / "workspace"
        workspace.mkdir()
        environment = {key: value for key, value in os.environ.items() if not key.startswith("LIBRARIAN_")}
        environment["PYTHONPATH"] = str(site_packages)
        environment.pop("PYTHONHOME", None)
        result = subprocess.run(
            [sys.executable, "-S", "-m", "librarian", "init"],
            cwd=workspace,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "Initialized reading librarian workspace" in result.stdout
        assert (workspace / "library" / "index.md").is_file()
        assert (workspace / "_state" / "config.toml").is_file()
        assert "installed separately" in (workspace / "README.md").read_text()
        assert "require_external_model_approval" in (workspace / "AGENTS.md").read_text()
        metadata = tomllib.loads((workspace / "pyproject.toml").read_text())
        assert metadata["tool"]["librarian"]["workspace"] is True
        assert "project" not in metadata

        # A repeated setup must preserve the owner's existing workspace files.
        preserved = {}
        for relative in ["README.md", "AGENTS.md", "pyproject.toml", "_state/config.toml", "library/index.md"]:
            path = workspace / relative
            text = "# Owner's existing content\n" + path.read_text()
            path.write_text(text)
            preserved[relative] = text
        repeated = subprocess.run(
            [sys.executable, "-S", "-m", "librarian", "init"],
            cwd=workspace,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        assert repeated.returncode == 0, repeated.stdout + repeated.stderr
        for relative, expected in preserved.items():
            assert (workspace / relative).read_text() == expected
