from pathlib import Path
from unittest.mock import patch

import pytest

from librarian.filesystem import move_without_overwrite


def test_failed_source_removal_preserves_source_and_cleans_created_copy(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    target = tmp_path / "target.txt"
    source.write_text("original synthetic content", encoding="utf-8")
    unlink = Path.unlink

    def fail_source_removal(path: Path, *args: object, **kwargs: object) -> None:
        if path == source:
            raise PermissionError("synthetic source removal failure")
        unlink(path, *args, **kwargs)

    with patch.object(Path, "unlink", fail_source_removal):
        with pytest.raises(PermissionError, match="source removal failure"):
            move_without_overwrite(source, target)

    assert source.read_text(encoding="utf-8") == "original synthetic content"
    assert not target.exists()
