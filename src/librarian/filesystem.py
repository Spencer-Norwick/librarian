from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path

from .domain import Config


def supported_files(config: Config, folder: Path) -> list[Path]:
    if not folder.exists():
        return []
    return sorted(
        path
        for path in folder.iterdir()
        if path.is_file() and not path.is_symlink() and path.suffix.lower() in config.supported_extensions
    )


def unique_filename(library: Path, filename: str, source: Path, reserved: set[str] | None = None) -> str:
    reserved = reserved or set()
    target = library / filename
    if not target.exists() and filename not in reserved:
        return filename
    suffix = stable_hash(source)
    path = Path(filename)
    candidate = f"{path.stem}_{suffix}{path.suffix}"
    counter = 2
    while (library / candidate).exists() or candidate in reserved:
        candidate = f"{path.stem}_{suffix}{counter}{path.suffix}"
        counter += 1
    return candidate


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    counter = 2
    while True:
        candidate = path.with_name(f"{path.stem}_{counter}{path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def move_without_overwrite(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    created_target = False
    try:
        with source.open("rb") as src:
            dst = target.open("xb")
            created_target = True
            with dst:
                shutil.copyfileobj(src, dst)
        shutil.copystat(source, target)
    except Exception:
        if created_target and target.exists():
            target.unlink()
        raise
    source.unlink()


def write_text_without_overwrite(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(text)


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        temp.write_text(text, encoding="utf-8")
        temp.replace(path)
    finally:
        if temp.exists():
            temp.unlink()


def stable_hash(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        digest.update(path.name.encode("utf-8"))
    return digest.hexdigest()[:8]
