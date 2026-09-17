#!/usr/bin/env python3
"""Build and smoke-test a wheel in a disposable workspace and isolated venv.

Run with a Python that has the `build` module installed. Build artifacts, runtime
state, and synthetic reading files stay in a temporary directory. The installed
CLI smoke test uses no model provider and no delivery endpoint.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import tarfile
import zipfile
import venv
from pathlib import Path


def run(command: list[str], cwd: Path, environment: dict[str, str], expected: int = 0) -> str:
    result = subprocess.run(command, cwd=cwd, env=environment, capture_output=True, text=True, check=False)
    if result.returncode != expected:
        raise RuntimeError(
            f"Command failed ({result.returncode}, expected {expected}): {command!r}\n"
            f"{result.stdout}{result.stderr}"
        )
    return result.stdout


def main() -> int:
    repository = Path(__file__).resolve().parents[1]
    environment = {
        key: value for key, value in os.environ.items()
        if key not in {"PYTHONPATH", "PYTHONHOME"} and not key.startswith("LIBRARIAN_")
    }
    with tempfile.TemporaryDirectory(prefix="librarian-installed-check-") as directory:
        temporary = Path(directory)
        source = temporary / "source"
        source.mkdir()
        for name in ["pyproject.toml", "README.md", "LICENSE"]:
            shutil.copy2(repository / name, source / name)
        shutil.copytree(repository / "src" / "librarian", source / "src" / "librarian",
                        ignore=shutil.ignore_patterns("__pycache__"))
        dist = temporary / "dist"
        run([sys.executable, "-m", "build", "--outdir", str(dist)], source, environment)
        sdists = list(dist.glob("*.tar.gz"))
        if len(sdists) != 1:
            raise RuntimeError(f"Expected exactly one source distribution, found {sdists!r}")
        package_paths = {
            "librarian/" + str(path.relative_to(repository / "src" / "librarian")).replace(os.sep, "/")
            for path in (repository / "src" / "librarian").rglob("*.py")
            if "__pycache__" not in path.parts
        }
        package_paths.update("librarian/templates/" + name for name in ["README.md", "AGENTS.md", "pyproject.toml"])
        egg_metadata = {"PKG-INFO", "SOURCES.txt", "dependency_links.txt", "entry_points.txt", "requires.txt", "top_level.txt"}
        source_allowed = {"LICENSE", "README.md", "pyproject.toml", "setup.cfg", "PKG-INFO"}
        source_allowed.update("src/" + name for name in package_paths)
        source_allowed.update("src/reading_librarian.egg-info/" + name for name in egg_metadata)
        with tarfile.open(sdists[0]) as archive:
            names = [member.name.split("/", 1)[1] for member in archive.getmembers() if member.isfile()]
            unexpected = set(names) - source_allowed
            assert not unexpected, f"Unexpected source distribution files: {sorted(unexpected)!r}"
            assert all("src/librarian/templates/" + name in names for name in ["README.md", "AGENTS.md", "pyproject.toml"])
        wheels = list(dist.glob("*.whl"))
        if len(wheels) != 1:
            raise RuntimeError(f"Expected exactly one wheel, found {wheels!r}")
        distribution, version = wheels[0].stem.split("-")[:2]
        metadata_prefix = distribution + "-" + version + ".dist-info/"
        wheel_allowed = package_paths | {
            metadata_prefix + name for name in ["METADATA", "WHEEL", "entry_points.txt", "top_level.txt", "RECORD", "licenses/LICENSE"]
        }
        with zipfile.ZipFile(wheels[0]) as archive:
            names = [name for name in archive.namelist() if not name.endswith("/")]
            unexpected = set(names) - wheel_allowed
            assert not unexpected, f"Unexpected wheel files: {sorted(unexpected)!r}"
            assert all("librarian/templates/" + name in names for name in ["README.md", "AGENTS.md", "pyproject.toml"])
        print(f"Archive inspection passed: {sdists[0].name} and {wheels[0].name}; only source, templates, and distribution metadata.")
        virtualenv = temporary / "venv"
        venv.EnvBuilder(with_pip=True).create(virtualenv)
        executable_dir = virtualenv / ("Scripts" if os.name == "nt" else "bin")
        python = executable_dir / ("python.exe" if os.name == "nt" else "python")
        workspace = temporary / "workspace"
        workspace.mkdir()
        run([str(python), "-m", "pip", "install", "--no-index", "--no-deps", str(wheels[0])], workspace, environment)

        # Remove the build checkout so missing-resource regressions cannot hide.
        shutil.rmtree(source)
        command = executable_dir / ("librarian.exe" if os.name == "nt" else "librarian")
        alias = executable_dir / ("reading-librarian.exe" if os.name == "nt" else "reading-librarian")
        cli = [str(command)]
        help_text = run(cli + ["--help"], workspace, environment)
        assert "commands:" in help_text and "edit" in help_text and "weekly" in help_text
        assert list(workspace.iterdir()) == [], "Help created workspace files"
        assert "commands:" in run([str(alias), "--help"], workspace, environment)
        run(cli + ["mount", "--check"], workspace, environment)
        assert not (workspace / "_state" / "config.toml").exists(), "Mount check wrote config"
        run(cli + ["init"], workspace, environment)
        for name in ["README.md", "AGENTS.md", "pyproject.toml", "_state/config.toml", "library/index.md"]:
            assert (workspace / name).is_file(), f"Missing initialized file: {name}"
        config_before = (workspace / "_state" / "config.toml").read_bytes()
        run(cli + ["mount", "--model", "none"], workspace, environment)
        assert (workspace / "_state" / "config.toml").read_bytes() == config_before

        inbox = workspace / "inbox" / "AdaExample_WalkAndWeather_2020_essay.txt"
        inbox.write_text("Walk and Weather\nBy Ada Example\n\nA synthetic essay about weather and walking.\n", encoding="utf-8")
        index_before = (workspace / "library" / "index.md").read_bytes()
        run(cli + ["ingest"], workspace, environment)
        assert inbox.is_file(), "Ingest preview moved the input"
        assert (workspace / "library" / "index.md").read_bytes() == index_before
        run(cli + ["ingest", "--apply"], workspace, environment)
        assert not inbox.exists(), "Applied ingest left the source in inbox"
        run(cli + ["status"], workspace, environment)
        blocked = run(cli + ["weekly", "--no-notify"], workspace, environment, expected=1)
        assert "No digest-ready" in blocked
        assert "enrich" in blocked
        assert not list((workspace / "_output" / "weekly-read-drafts").glob("*.md"))

        # Supply synthetic summaries/prompts manually, exercising a provider-free
        # weekly path with the installed index API and no external enrichment.
        run([str(python), "-c", "\n".join([
            "from pathlib import Path",
            "from librarian.index import read_index, write_index",
            "path = Path('library/index.md')",
            "entries = read_index(path)",
            "assert len(entries) == 1",
            "entry = entries[0]",
            "entry.work_type = 'essay'",
            "entry.summary = 'A synthetic reflection on observing weather during a walk.'",
            "entry.primer_prompts = ['What does the walker notice?', 'How does weather affect attention?']",
            "entry.next_action = 'clean'",
            "entry.needs_review = []",
            "write_index(path, entries)",
        ])], workspace, environment)
        draft_dir = workspace / "_output" / "weekly-read-drafts"
        index_before = (workspace / "library" / "index.md").read_bytes()
        run(cli + ["weekly", "--mode", "short", "--max-minutes", "0", "--no-notify"], workspace, environment)
        assert not list(draft_dir.glob("*.md")), "Weekly preview wrote a draft"
        assert (workspace / "library" / "index.md").read_bytes() == index_before
        run(cli + ["weekly", "--mode", "short", "--max-minutes", "0", "--no-notify", "--apply"], workspace, environment)
        drafts = list(draft_dir.glob("*.md"))
        assert len(drafts) == 1, f"Expected one local weekly draft, found {drafts!r}"
        assert "synthetic reflection" in drafts[0].read_text(encoding="utf-8")
        run(cli + ["lint"], workspace, environment)
        print(f"Built sdist and installed wheel smoke check passed: {wheels[0].name}; both commands, bundled init, dry runs, ingest, local short weekly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
