from __future__ import annotations

import io
import json
import os
import tempfile
import tomllib
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from librarian.cli import (
    WorkEntry,
    agents_markdown,
    clean_title,
    filename_convention_ok,
    infer_year_from_text,
    main,
    read_index,
    readme_markdown,
    render_index,
    today,
)

FIXTURES = Path(__file__).parent / "fixtures"


class LibrarianCliTests(unittest.TestCase):
    def run_cli(self, root: Path, *args: str) -> tuple[int, str]:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = main(list(args), root=root)
        return code, buffer.getvalue()

    def make_project(self, root: Path) -> None:
        code, _ = self.run_cli(root, "init")
        self.assertEqual(code, 0)

    def ready_entry(self, **kwargs: object) -> WorkEntry:
        values = {
            "author": "B, Author",
            "title": "Never Sent",
            "filename": "BAuthor_NeverSent_2001_book.txt",
            "sent": "never",
            "summary": "A specific summary that is ready for a weekly digest.",
            "primer_prompts": ["What question does this work open?", "Which claim should I test while reading?"],
            "next_action": "clean",
        }
        values.update(kwargs)
        return WorkEntry(**values)

    def fake_model_command(self, root: Path) -> str:
        script = root / "fake_model.py"
        script.write_text(
            "import json, sys\n"
            "json.load(sys.stdin)\n"
            "print(json.dumps({\n"
            "  'summary': 'This work argues through a concrete local example and gives the reader a focused problem to track.',\n"
            "  'primer_prompts': ['What problem does the author make visible?', 'Which terms does the work ask me to reconsider?', 'What would count as evidence against the argument?'],\n"
            "  'tags': ['theory', 'reading'],\n"
            "  'related': 'None.'\n"
            "}))\n",
            encoding="utf-8",
        )
        return f"python3 {script}"

    def fake_model_script(self, root: Path, name: str, body: str) -> str:
        script = root / name
        script.write_text(body, encoding="utf-8")
        return f"python3 {script}"

    def fake_ocr_command(self, root: Path) -> str:
        script = root / "fake_ocr.py"
        script.write_text(
            "import shutil, sys\n"
            "shutil.copyfile(sys.argv[-2], sys.argv[-1])\n",
            encoding="utf-8",
        )
        return f"python3 {script}"

    def write_epub(self, path: Path, body: str) -> None:
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("mimetype", "application/epub+zip")
            archive.writestr(
                "OPS/chapter.xhtml",
                f"""<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <body><p>{body}</p></body>
</html>
""",
            )

    def write_docx(self, path: Path, paragraphs: list[str]) -> None:
        body = "".join(f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>" for text in paragraphs)
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(
                "word/document.xml",
                f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>{body}</w:body>
</w:document>
""",
            )

    def test_sample_fixture_dirs_live_under_tests(self) -> None:
        self.assertTrue((FIXTURES / "inbox").is_dir())
        self.assertTrue((FIXTURES / "library").is_dir())

    def test_init_document_templates_follow_public_docs(self) -> None:
        root = FIXTURES.parents[1]
        readme = (root / "README.md").read_text(encoding="utf-8")
        agents = (root / "AGENTS.md").read_text(encoding="utf-8")

        self.assertEqual(readme_markdown(), readme)
        self.assertEqual(agents_markdown(), agents)
        self.assertIn("librarian weekly --apply --notify-mac --open --message-self", readme)
        self.assertIn(".epub` and `.docx`: ingest plus lightweight stdlib text extraction", readme)

    def test_package_keeps_librarian_command_and_alias(self) -> None:
        root = FIXTURES.parents[1]
        pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
        scripts = pyproject["project"]["scripts"]

        self.assertEqual(scripts["librarian"], "librarian.cli:main")
        self.assertEqual(scripts["reading-librarian"], "librarian.cli:main")

    def test_mount_check_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            config_path = root / "_state" / "config.toml"
            before = config_path.read_text(encoding="utf-8")

            code, output = self.run_cli(root, "mount", "--check")

            self.assertEqual(code, 0)
            self.assertIn("Mount check", output)
            self.assertIn("Recommended digest command:", output)
            self.assertIn("_state/model-enrich-local", output)
            self.assertEqual(config_path.read_text(encoding="utf-8"), before)

    def test_mount_dry_run_prints_config_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            config_path = root / "_state" / "config.toml"
            before = config_path.read_text(encoding="utf-8")

            code, output = self.run_cli(root, "mount", "--model", "none")

            self.assertEqual(code, 0)
            self.assertIn("[dry-run] Mount config target:", output)
            self.assertIn("model_command = []", output)
            self.assertIn("require_external_model_approval = true", output)
            self.assertIn("Dry run only", output)
            self.assertEqual(config_path.read_text(encoding="utf-8"), before)

    def test_mount_apply_writes_custom_model_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)

            code, output = self.run_cli(
                root,
                "mount",
                "--apply",
                "--privacy",
                "automatic",
                "--model",
                "custom",
                "--model-command",
                "claude enrich-json",
                "--digest",
                "apply",
            )

            self.assertEqual(code, 0)
            self.assertIn("Applied mount config.", output)
            config_text = (root / "_state" / "config.toml").read_text(encoding="utf-8")
            self.assertIn('model_command = ["claude", "enrich-json"]', config_text)
            self.assertIn("use_model_assistance = true", config_text)
            self.assertIn("Recommended digest command: librarian weekly --apply", output)

    def test_mount_custom_model_requires_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)

            code, output = self.run_cli(root, "mount", "--model", "custom")

            self.assertEqual(code, 2)
            self.assertIn("--model custom requires --model-command", output)

    def test_mount_codex_does_not_autoconfigure_provider_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)

            code, output = self.run_cli(root, "mount", "--model", "codex")

            self.assertEqual(code, 0)
            self.assertIn("Recommended model command: none", output)
            self.assertIn("no model command was configured", output)
            self.assertIn("JSON-compatible Codex wrapper", output)
            self.assertIn("model_command = []", output)

    def test_inbox_pdf_can_be_seen_in_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            copied = root / "inbox" / "sample-reading.pdf"
            copied.write_bytes(b"%PDF-1.4\n% tiny synthetic fixture\n")

            code, output = self.run_cli(root, "ingest")

            self.assertEqual(code, 0)
            self.assertIn(copied.name, output)
            self.assertTrue(copied.exists())

    def test_ingest_dry_run_makes_no_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            source = root / "inbox" / "Ong_Walter_OralityAndLiteracy_1982_book.txt"
            source.write_text("Writing restructures consciousness.", encoding="utf-8")

            code, output = self.run_cli(root, "ingest")

            self.assertEqual(code, 0)
            self.assertIn("Dry run only", output)
            self.assertTrue(source.exists())
            self.assertFalse((root / "library" / "OngWalter_OralityAndLiteracy_1982_book.txt").exists())
            self.assertEqual(read_index(root / "library" / "index.md"), [])

    def test_ingest_apply_moves_file_and_updates_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            source = root / "inbox" / "Ong_Walter_OralityAndLiteracy_1982_book.txt"
            source.write_text("Writing restructures consciousness.", encoding="utf-8")

            code, _ = self.run_cli(root, "ingest", "--apply")

            self.assertEqual(code, 0)
            target = root / "library" / "OngWalter_OralityAndLiteracy_1982_book.txt"
            self.assertTrue(target.exists())
            self.assertFalse(source.exists())
            index_text = (root / "library" / "index.md").read_text(encoding="utf-8")
            self.assertIn("### Ong, Walter", index_text)
            self.assertIn("Original filename: `Ong_Walter_OralityAndLiteracy_1982_book.txt`", index_text)
            log_text = (root / "_state" / "ingest-log.md").read_text(encoding="utf-8")
            self.assertIn("`Ong_Walter_OralityAndLiteracy_1982_book.txt`", log_text)
            self.assertIn("`OngWalter_OralityAndLiteracy_1982_book.txt`", log_text)

    def test_ingest_epub_extracts_text_without_ocr_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            source = root / "inbox" / "Ong_Walter_OralityAndLiteracy_1982_book.epub"
            self.write_epub(source, "Writing restructures consciousness. This book examines orality and literacy.")

            code, output = self.run_cli(root, "ingest", "--apply")

            self.assertEqual(code, 0)
            self.assertNotIn("Text extraction not implemented", output)
            entries = read_index(root / "library" / "index.md")
            self.assertEqual(entries[0].filename, "OngWalter_OralityAndLiteracy_1982_book.epub")
            self.assertEqual(entries[0].next_action, "needs_model")
            self.assertNotIn("Text extraction not implemented", entries[0].needs_review)
            self.assertNotEqual(entries[0].next_action, "needs_ocr")
            self.assertIn("Writing restructures consciousness.", entries[0].summary)

    def test_ingest_docx_extracts_text_without_ocr_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            source = root / "inbox" / "LeGuin_Ursula_CarrierBagTheory_1986_essay.docx"
            self.write_docx(
                source,
                ["The carrier bag theory reframes technology around gathering and holding.", "It is an essay about stories."],
            )

            code, output = self.run_cli(root, "ingest", "--apply")

            self.assertEqual(code, 0)
            self.assertNotIn("Text extraction not implemented", output)
            entries = read_index(root / "library" / "index.md")
            self.assertEqual(entries[0].filename, "LeGuinUrsula_CarrierBagTheory_1986_essay.docx")
            self.assertEqual(entries[0].next_action, "needs_model")
            self.assertNotEqual(entries[0].next_action, "needs_ocr")
            self.assertIn("carrier bag theory reframes technology", entries[0].summary)

    def test_daily_dry_run_does_not_move_inbox_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            source = root / "inbox" / "Ong_Walter_OralityAndLiteracy_1982_book.txt"
            source.write_text("Writing restructures consciousness.", encoding="utf-8")

            code, output = self.run_cli(root, "daily")

            self.assertEqual(code, 0)
            self.assertIn("Daily workflow: ingest", output)
            self.assertIn("Daily workflow: lint", output)
            self.assertNotIn("Daily workflow: maintain", output)
            self.assertTrue(source.exists())
            self.assertEqual(read_index(root / "library" / "index.md"), [])

    def test_daily_apply_ingests_and_lints(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            source = root / "inbox" / "Ong_Walter_OralityAndLiteracy_1982_book.txt"
            source.write_text("Writing restructures consciousness.", encoding="utf-8")

            code, output = self.run_cli(root, "daily", "--apply")

            self.assertEqual(code, 0)
            self.assertIn("Applied ingest for 1 file", output)
            self.assertIn("No lint issues found.", output)
            self.assertIn("Daily summary", output)
            self.assertIn("Works: 0->1 (1 added)", output)
            self.assertIn("Review blockers:", output)
            self.assertFalse(source.exists())
            self.assertTrue((root / "library" / "OngWalter_OralityAndLiteracy_1982_book.txt").exists())

    def test_daily_dry_run_previews_scanned_inbox_ocr_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            source = root / "inbox" / "BergerJohn_WaysOfSeeing_1972_book.pdf"
            source.write_bytes(b"scanned pdf placeholder")

            with patch("librarian.cli.extract_pdf", return_value=({}, "", [])):
                code, output = self.run_cli(root, "daily")

            self.assertEqual(code, 0)
            self.assertIn("Daily workflow: prepare inbox", output)
            self.assertIn("[dry-run] OCR inbox PDF", output)
            self.assertTrue(source.exists())
            self.assertEqual(list((root / "_output" / "ocr").glob("*.pdf")), [])

    def test_daily_apply_ocr_prepares_scanned_pdf_before_ingest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            source = root / "inbox" / "BergerJohn_WaysOfSeeing_1972_book.pdf"
            source.write_bytes(b"scanned pdf placeholder")
            command = self.fake_ocr_command(root)

            def fake_extract_pdf(path: Path):
                if path.name == "BergerJohn_WaysOfSeeing_1972_book.pdf":
                    return {}, "", []
                return {}, "Seeing comes before words. This book develops an argument about images and visual culture.", []

            with patch.dict(os.environ, {"LIBRARIAN_OCR_COMMAND": command}, clear=True):
                with patch("librarian.cli.extract_pdf", side_effect=fake_extract_pdf):
                    code, output = self.run_cli(root, "daily", "--apply")

            self.assertEqual(code, 0)
            self.assertIn("Prepared OCR inbox copy", output)
            self.assertIn("Applied ingest for 1 file", output)
            self.assertFalse(source.exists())
            self.assertTrue((root / "_output" / "ocr" / "original-inbox-scans" / "BergerJohn_WaysOfSeeing_1972_book.pdf").exists())
            self.assertTrue((root / "library" / "BergerJohn_WaysOfSeeing_1972_book.pdf").exists())

    def test_happy_path_ingest_enrich_weekly_and_reply_read(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            command = self.fake_model_command(root)
            source = root / "inbox" / "BakerAnn_AttentionTools_2001_essay.txt"
            source.write_text("This essay develops a focused argument about reading tools and attention.", encoding="utf-8")

            with patch.dict(os.environ, {"LIBRARIAN_MODEL_COMMAND": command}, clear=True):
                code, _ = self.run_cli(root, "ingest", "--enrich", "--apply")
            self.assertEqual(code, 0)

            code, output = self.run_cli(root, "weekly", "--apply")
            self.assertEqual(code, 0)
            self.assertIn("Digest pick: Attention Tools by Baker, Ann", output)
            self.assertEqual(len(list((root / "_output" / "weekly-read-drafts").glob("*.md"))), 1)

            code, output = self.run_cli(root, "reply", "read", "--apply")
            self.assertEqual(code, 0)
            self.assertIn("Updated Attention Tools to read.", output)
            entries = read_index(root / "library" / "index.md")
            self.assertEqual(entries[0].status, "read")
            self.assertIn("unread -> read", (root / "_state" / "status-log.md").read_text(encoding="utf-8"))

    def test_daily_maintain_opt_in_runs_full_library_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)

            code, output = self.run_cli(root, "daily", "--maintain")

            self.assertEqual(code, 0)
            self.assertIn("Daily workflow: maintain", output)
            self.assertIn("[dry-run] Maintain", output)

    def test_collision_gets_stable_hash_suffix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            existing = root / "library" / "OngWalter_OralityAndLiteracy_1982_book.txt"
            existing.write_text("existing", encoding="utf-8")
            source = root / "inbox" / "Ong_Walter_OralityAndLiteracy_1982_book.txt"
            source.write_text("new content", encoding="utf-8")

            code, _ = self.run_cli(root, "ingest", "--apply")

            self.assertEqual(code, 0)
            moved = list((root / "library").glob("OngWalter_OralityAndLiteracy_1982_book_*.txt"))
            self.assertEqual(len(moved), 1)
            self.assertTrue(existing.exists())

    def test_same_batch_collision_does_not_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            first = root / "inbox" / "Ong_Walter_OralityAndLiteracy_1982_book.txt"
            second = root / "inbox" / "OngWalter_OralityAndLiteracy_1982_book.txt"
            first.write_text("first", encoding="utf-8")
            second.write_text("second", encoding="utf-8")

            code, _ = self.run_cli(root, "ingest", "--apply")

            self.assertEqual(code, 0)
            files = sorted(path.name for path in (root / "library").glob("OngWalter_OralityAndLiteracy_1982_book*.txt"))
            self.assertEqual(len(files), 2)
            self.assertIn("first", "\n".join(path.read_text(encoding="utf-8") for path in (root / "library").glob("*.txt")))
            self.assertIn("second", "\n".join(path.read_text(encoding="utf-8") for path in (root / "library").glob("*.txt")))

    def test_author_sections_are_alphabetical(self) -> None:
        entries = [
            WorkEntry(author="Ong, Walter", title="Orality and Literacy", year="1982", work_type="book", filename="OngWalter_OralityAndLiteracy_1982_book.txt"),
            WorkEntry(author="Benjamin, Walter", title="Work of Art", year="1935", work_type="essay", filename="BenjaminWalter_WorkOfArt_1935_essay.txt"),
        ]

        text = render_index(entries)

        self.assertLess(text.index("### Benjamin, Walter"), text.index("### Ong, Walter"))

    def test_filename_lint_accepts_canonical_and_legacy_import_names(self) -> None:
        self.assertTrue(filename_convention_ok("OngWalter_OralityAndLiteracy_1982_book.txt"))
        self.assertTrue(filename_convention_ok("Ong_Walter_OralityAndLiteracy_1982_book.txt"))
        self.assertTrue(filename_convention_ok("Chomsky_Language and Freedom_1973_essay.pdf"))
        self.assertTrue(filename_convention_ok("Douglas_Brian_ControlTheory_2019_ebook.pdf"))
        self.assertTrue(filename_convention_ok("Chiang_StoriesOfYourLife_2002_stories.pdf"))
        self.assertTrue(filename_convention_ok("Rubin_Rick_CreativeActThe_AWayofBeing_2023_book.pdf"))
        self.assertTrue(filename_convention_ok("Wallace_David_Foster_EUnibusPluram_1993_essay.pdf"))
        self.assertFalse(filename_convention_ok("bad name.pdf"))

    def test_title_polish_repairs_known_filename_artifacts(self) -> None:
        self.assertEqual(clean_title("Preventionof Literature The"), "The Prevention of Literature")
        self.assertEqual(clean_title("Engineers Guideto Fundamentalsof Control Theory"), "Engineers Guide to Fundamentals of Control Theory")
        self.assertEqual(
            clean_title("Work Of Art In The Age Of Its Technological Reproducability The"),
            "The Work Of Art In The Age Of Its Technological Reproducibility",
        )

    def test_unknown_author_goes_to_needs_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            (root / "inbox" / "mystery.txt").write_text("A short anonymous note.", encoding="utf-8")

            code, _ = self.run_cli(root, "ingest", "--apply")

            self.assertEqual(code, 0)
            index_text = (root / "library" / "index.md").read_text(encoding="utf-8")
            self.assertIn("### Unknown", index_text)
            self.assertIn("## Needs Review", index_text)
            self.assertIn("Author could not be inferred", index_text)

    def test_ingest_infers_year_from_front_matter_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            source = root / "inbox" / "oppression-and-liberty.txt"
            source.write_text("Oppression and Liberty Simone Weil 1958 Contents PROSPECTS", encoding="utf-8")

            code, _ = self.run_cli(root, "ingest", "--apply")

            self.assertEqual(code, 0)
            entries = read_index(root / "library" / "index.md")
            self.assertEqual(entries[0].year, "1958")
            self.assertTrue((root / "library" / "Unknown_OppressionAndLiberty_1958_book.txt").exists())

    def test_ingest_uses_visual_pdf_title_page_ocr_for_weak_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            source = root / "inbox" / "d915f1d3f5b3da7daf4305874403f888.pdf"
            source.write_bytes(b"%PDF-1.4 visual title page fixture")

            with patch("librarian.cli.extract_pdf", return_value=({}, "Leonard Koren, (Berkeley: Stone Bridge Press) 2003", [])):
                with patch(
                    "librarian.cli.pdf_title_page_ocr_text",
                    return_value="Arranging Things\nA Rhetoric of Object Placement\nLeonard Koren",
                ):
                    code, _ = self.run_cli(root, "ingest", "--apply")

            self.assertEqual(code, 0)
            entries = read_index(root / "library" / "index.md")
            self.assertEqual(entries[0].author, "Koren, Leonard")
            self.assertEqual(entries[0].title, "Arranging Things A Rhetoric of Object Placement")
            self.assertEqual(entries[0].year, "2003")
            self.assertTrue((root / "library" / "KorenLeonard_ArrangingThingsARhetoricOfObjectPlacement_2003_unknown.pdf").exists())

    def test_ingest_infers_title_page_identity_for_opaque_filename(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            source = root / "inbox" / "224fecab4a6e9d1d7b402478e5361c80.txt"
            source.write_text(
                "\n".join(
                    [
                        "Attention",
                        "and Effort",
                        "DANIEL KAHNEMAN",
                        "The Hebrew University of Jerusalem",
                        "Copyright 1973 by Prentice-Hall",
                        "Contents",
                        "1 Basic issues in the study of attention",
                    ]
                ),
                encoding="utf-8",
            )

            code, _ = self.run_cli(root, "ingest", "--apply")

            self.assertEqual(code, 0)
            target = root / "library" / "KahnemanDaniel_AttentionAndEffort_1973_book.txt"
            self.assertTrue(target.exists())
            entries = read_index(root / "library" / "index.md")
            self.assertEqual(entries[0].author, "Kahneman, Daniel")
            self.assertEqual(entries[0].title, "Attention and Effort")
            self.assertEqual(entries[0].year, "1973")
            self.assertEqual(entries[0].original_filename, source.name)

    def test_year_inference_prefers_first_published_over_later_edition(self) -> None:
        text = "This paperback edition published by Verso 2014 First published in English by Verso 2002 © Verso 2002, 2014"

        self.assertEqual(infer_year_from_text(text), "2002")

    def test_weekly_pick_avoids_already_sent_work(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            entries = [
                self.ready_entry(author="A, Author", title="Already Sent", filename="AAuthor_AlreadySent_2000_book.txt", sent="2026-01-01"),
                self.ready_entry(),
            ]
            (root / "library" / "index.md").write_text(render_index(entries), encoding="utf-8")

            code, output = self.run_cli(root, "weekly-pick")

            self.assertEqual(code, 0)
            self.assertIn("Never Sent", output)
            self.assertNotIn("[dry-run] Weekly pick: Already Sent", output)

    def test_weekly_pick_apply_does_not_overwrite_existing_draft(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            entry = self.ready_entry()
            (root / "library" / "index.md").write_text(render_index([entry]), encoding="utf-8")
            existing = root / "_output" / "weekly-read-drafts" / f"{today()}_NeverSent.md"
            existing.write_text("existing draft", encoding="utf-8")

            code, _ = self.run_cli(root, "weekly-pick", "--apply")

            self.assertEqual(code, 0)
            self.assertEqual(existing.read_text(encoding="utf-8"), "existing draft")
            self.assertTrue((root / "_output" / "weekly-read-drafts" / f"{today()}_NeverSent_2.md").exists())

    def test_digest_dry_run_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            entry = self.ready_entry()
            (root / "library" / "index.md").write_text(render_index([entry]), encoding="utf-8")

            code, output = self.run_cli(root, "digest")

            self.assertEqual(code, 0)
            self.assertIn("Subject: Read of the Week", output)
            self.assertIn("Summary:\nA specific summary that is ready for a weekly digest.", output)
            self.assertIn("Reading history:\nFirst time in the digest; never skipped.", output)
            self.assertIn("Primer prompts:", output)
            self.assertEqual(list((root / "_output" / "weekly-read-drafts").glob("*.md")), [])

    def test_digest_notify_prints_automation_friendly_message(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            entry = self.ready_entry()
            (root / "library" / "index.md").write_text(render_index([entry]), encoding="utf-8")

            code, output = self.run_cli(root, "digest", "--notify")

            self.assertEqual(code, 0)
            self.assertIn("NOTIFY: Read of the Week: Never Sent", output)
            self.assertIn("Summary: A specific summary that is ready for a weekly digest.", output)
            self.assertIn("History: First time in the digest; never skipped.", output)
            self.assertIn("Primer prompt: What question does this work open?", output)

    def test_digest_includes_compact_library_status_footer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            entries = [
                self.ready_entry(title="First", filename="BAuthor_First_2001_book.txt"),
                self.ready_entry(title="Second", filename="BAuthor_Second_2002_book.txt"),
                self.ready_entry(title="Read Work", filename="BAuthor_ReadWork_2003_book.txt", status="read"),
            ]
            (root / "library" / "index.md").write_text(render_index(entries), encoding="utf-8")

            code, output = self.run_cli(root, "digest")

            self.assertEqual(code, 0)
            self.assertIn("-----\nLibrary status", output)
            self.assertIn("Library: 3 works; 1 read; 2 unread; 0 skipped.", output)
            self.assertIn("Ready queue: 2 unsent digest-ready works", output)
            self.assertIn("Next after this: Second.", output)

    def test_status_command_prints_library_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            entries = [
                self.ready_entry(title="First", filename="BAuthor_First_2001_book.txt"),
                self.ready_entry(title="Read Work", filename="BAuthor_ReadWork_2003_book.txt", status="read"),
                self.ready_entry(title="Needs Model", filename="BAuthor_NeedsModel_2004_book.txt", next_action="needs_model", primer_prompts=[]),
            ]
            (root / "library" / "index.md").write_text(render_index(entries), encoding="utf-8")
            (root / "inbox" / "pending.pdf").write_bytes(b"pending")

            code, output = self.run_cli(root, "status")

            self.assertEqual(code, 0)
            self.assertIn("Library status", output)
            self.assertIn("Total works: 3", output)
            self.assertIn("Digest-ready: 1; unsent ready: 1", output)
            self.assertIn("Inbox pending: 1", output)
            self.assertIn("Review blockers: 1", output)
            self.assertIn("Next weekly pick: First by B, Author", output)

    def test_weekly_defaults_to_notify_preview(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            entry = self.ready_entry()
            (root / "library" / "index.md").write_text(render_index([entry]), encoding="utf-8")

            code, output = self.run_cli(root, "weekly")

            self.assertEqual(code, 0)
            self.assertIn("NOTIFY: Read of the Week: Never Sent", output)
            self.assertIn("Dry run only", output)
            self.assertEqual(list((root / "_output" / "weekly-read-drafts").glob("*.md")), [])

    def test_weekly_apply_writes_digest_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            entry = self.ready_entry()
            (root / "library" / "index.md").write_text(render_index([entry]), encoding="utf-8")

            code, output = self.run_cli(root, "weekly", "--apply")

            self.assertEqual(code, 0)
            self.assertIn("NOTIFY: Read of the Week: Never Sent", output)
            self.assertIn("Digest pick: Never Sent by B, Author", output)
            self.assertNotIn("[dry-run] Digest pick", output)
            self.assertNotIn("[dry-run] Draft path", output)
            self.assertIn("Wrote _output/weekly-read-drafts", output)
            self.assertIn("Weekly summary", output)
            self.assertIn("unsent ready:", output)
            entries = read_index(root / "library" / "index.md")
            self.assertEqual(entries[0].sent, today())
            self.assertEqual(len(list((root / "_output" / "weekly-read-drafts").glob("*.md"))), 1)

    def test_weekly_local_delivery_dry_run_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            entry = self.ready_entry()
            (root / "library" / "index.md").write_text(render_index([entry]), encoding="utf-8")

            with patch("librarian.cli.subprocess.run") as run:
                code, output = self.run_cli(root, "weekly", "--notify-mac", "--open", "--message-self")

            self.assertEqual(code, 0)
            self.assertIn("[dry-run] Mac notification: Never Sent", output)
            self.assertIn("[dry-run] Open file: library/BAuthor_NeverSent_2001_book.txt", output)
            self.assertIn("[dry-run] Message self: unconfigured recipient", output)
            self.assertIn("Local delivery not run in dry-run mode.", output)
            self.assertFalse(run.called)
            self.assertEqual(list((root / "_output" / "weekly-read-drafts").glob("*.md")), [])

    def test_weekly_message_self_requires_recipient_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            entry = self.ready_entry()
            (root / "library" / "index.md").write_text(render_index([entry]), encoding="utf-8")

            code, output = self.run_cli(root, "weekly", "--apply", "--message-self")

            self.assertEqual(code, 2)
            self.assertIn("Messages delivery requires", output)
            self.assertEqual(list((root / "_output" / "weekly-read-drafts").glob("*.md")), [])

    def test_weekly_apply_runs_local_delivery_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            entry = self.ready_entry()
            (root / "library" / entry.filename).write_text("reading file", encoding="utf-8")
            (root / "library" / "index.md").write_text(render_index([entry]), encoding="utf-8")

            with patch.dict(os.environ, {"LIBRARIAN_MESSAGE_TO": "me@example.com"}, clear=True), patch("librarian.cli.subprocess.run") as run:
                run.return_value.returncode = 0
                run.return_value.stdout = ""
                run.return_value.stderr = ""
                code, output = self.run_cli(root, "weekly", "--apply", "--notify-mac", "--open", "--message-self")

            self.assertEqual(code, 0)
            self.assertIn("Posted Mac notification.", output)
            self.assertIn("Opened BAuthor_NeverSent_2001_book.txt.", output)
            self.assertIn("Sent Messages notification.", output)
            commands = [call.args[0] for call in run.call_args_list]
            self.assertEqual(commands[0][:2], ["osascript", "-e"])
            self.assertEqual(commands[1][0], "open")
            self.assertEqual(commands[2][:2], ["osascript", "-e"])
            self.assertIn("Read of the Week: Never Sent", commands[2][2])

    def test_digest_history_counts_prior_sends(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            entry = self.ready_entry(
                author="B, Author",
                title="Already Sent",
                filename="BAuthor_AlreadySent_2001_book.txt",
                sent="2026-01-01",
            )
            (root / "library" / "index.md").write_text(render_index([entry]), encoding="utf-8")
            (root / "_state" / "sent-log.md").write_text(
                "# Sent Log\n\n"
                "- 2026-01-01T09:00:00 — `BAuthor_AlreadySent_2001_book.txt` drafted as `draft-1.md`\n"
                "- 2026-01-08T09:00:00 — `BAuthor_AlreadySent_2001_book.txt` drafted as `draft-2.md`\n",
                encoding="utf-8",
            )

            code, output = self.run_cli(root, "digest", "--allow-repeats")

            self.assertEqual(code, 0)
            self.assertIn("Reading history:\nSent 2 times; last sent 2026-01-01; never skipped.", output)
            self.assertIn("is being repeated intentionally", output)

    def test_digest_history_counts_skips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            entry = self.ready_entry()
            (root / "library" / "index.md").write_text(render_index([entry]), encoding="utf-8")
            (root / "_state" / "status-log.md").write_text(
                "# Status Log\n\n"
                "- 2026-01-01T09:00:00 — `BAuthor_NeverSent_2001_book.txt` unread -> skipped\n",
                encoding="utf-8",
            )

            code, output = self.run_cli(root, "digest")

            self.assertEqual(code, 0)
            self.assertIn("Reading history:\nFirst time in the digest; skipped once.", output)

    def test_digest_email_requires_config_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            entry = self.ready_entry()
            (root / "library" / "index.md").write_text(render_index([entry]), encoding="utf-8")

            with patch.dict(os.environ, {}, clear=True):
                code, output = self.run_cli(root, "digest", "--email", "--apply")

            self.assertEqual(code, 2)
            self.assertIn("Email delivery requires", output)
            self.assertEqual(list((root / "_output" / "weekly-read-drafts").glob("*.md")), [])

    def test_digest_email_apply_sends_when_configured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            entry = self.ready_entry()
            (root / "library" / "index.md").write_text(render_index([entry]), encoding="utf-8")
            env = {
                "RESEND_API_KEY": "test-key",
                "LIBRARIAN_EMAIL_FROM": "reads@example.com",
                "LIBRARIAN_EMAIL_TO": "me@example.com",
            }

            with patch.dict(os.environ, env, clear=True), patch("urllib.request.urlopen") as urlopen:
                urlopen.return_value = io.BytesIO(b'{"id":"email_123"}')
                code, output = self.run_cli(root, "digest", "--email", "--apply")

            self.assertEqual(code, 0)
            self.assertIn("Sent digest email.", output)
            self.assertTrue(urlopen.called)
            self.assertIn("emailed and drafted as", (root / "_state" / "sent-log.md").read_text(encoding="utf-8"))

    def test_digest_email_can_use_configured_sender_and_recipient(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            entry = self.ready_entry()
            (root / "library" / "index.md").write_text(render_index([entry]), encoding="utf-8")
            config_path = root / "_state" / "config.toml"
            config_text = config_path.read_text(encoding="utf-8")
            config_text = config_text.replace('email_from = ""', 'email_from = "Reading Librarian <reads@example.com>"')
            config_text = config_text.replace('email_to = ""', 'email_to = "me@example.com"')
            config_path.write_text(config_text, encoding="utf-8")

            with patch.dict(os.environ, {"RESEND_API_KEY": "test-key"}, clear=True), patch("urllib.request.urlopen") as urlopen:
                urlopen.return_value = io.BytesIO(b'{"id":"email_123"}')
                code, output = self.run_cli(root, "digest", "--email", "--apply")

            self.assertEqual(code, 0)
            self.assertIn("Sent digest email.", output)
            request = urlopen.call_args.args[0]
            payload = json.loads(request.data.decode("utf-8"))
            self.assertEqual(payload["from"], "Reading Librarian <reads@example.com>")
            self.assertEqual(payload["to"], ["me@example.com"])

    def test_digest_skips_unenriched_model_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            entry = WorkEntry(
                author="B, Author",
                title="Never Sent",
                filename="BAuthor_NeverSent_2001_book.txt",
                sent="never",
                summary="Never Sent",
                next_action="needs_model",
            )
            (root / "library" / "index.md").write_text(render_index([entry]), encoding="utf-8")

            code, output = self.run_cli(root, "digest")

            self.assertEqual(code, 1)
            self.assertIn("No digest-ready unread works found", output)
            self.assertIn("Next actions:", output)
            self.assertIn("Never Sent (B, Author) needs model enrichment -> librarian enrich 'Never Sent'", output)

    def test_digest_empty_state_lists_ranked_next_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            entries = [
                WorkEntry(
                    author="B, Author",
                    title="Needs Model",
                    filename="BAuthor_NeedsModel_2001_book.txt",
                    summary="Needs Model",
                    next_action="needs_model",
                ),
                WorkEntry(
                    author="C, Author",
                    title="Needs OCR",
                    filename="CAuthor_NeedsOcr_2002_book.pdf",
                    summary="No extractable text found; OCR is needed before a reliable summary can be written.",
                    next_action="needs_ocr",
                ),
                WorkEntry(
                    author="Unknown",
                    title="Weak Metadata",
                    filename="Unknown_WeakMetadata_nd_unknown.txt",
                    summary="Needs review.",
                    next_action="needs_catalog",
                ),
            ]
            (root / "library" / "index.md").write_text(render_index(entries), encoding="utf-8")

            code, output = self.run_cli(root, "weekly")

            self.assertEqual(code, 1)
            self.assertIn("Next actions:", output)
            self.assertIn("Needs Model (B, Author) needs model enrichment -> librarian enrich 'Needs Model'", output)
            self.assertIn("Weak Metadata (Unknown) has weak metadata -> librarian maintain --lookup", output)
            self.assertIn("Needs OCR (C, Author) needs OCR -> librarian ocr 'Needs OCR'", output)

    def test_reply_skip_dry_run_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            entry = self.ready_entry(sent=today())
            (root / "library" / "index.md").write_text(render_index([entry]), encoding="utf-8")
            (root / "_state" / "sent-log.md").write_text(
                "# Sent Log\n\n"
                f"- 2026-01-01T09:00:00 — `{entry.filename}` drafted as `draft.md`\n",
                encoding="utf-8",
            )
            before_status_log = (root / "_state" / "status-log.md").read_text(encoding="utf-8")

            code, output = self.run_cli(root, "reply", "skip")

            self.assertEqual(code, 0)
            self.assertIn("[dry-run] Latest digest: Never Sent: unread -> skipped", output)
            self.assertIn("Dry run only", output)
            self.assertEqual(read_index(root / "library" / "index.md")[0].status, "unread")
            self.assertEqual((root / "_state" / "status-log.md").read_text(encoding="utf-8"), before_status_log)

    def test_reply_read_apply_marks_latest_digest_read(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            entry = self.ready_entry(sent=today())
            (root / "library" / "index.md").write_text(render_index([entry]), encoding="utf-8")
            (root / "_state" / "sent-log.md").write_text(
                "# Sent Log\n\n"
                f"- 2026-01-01T09:00:00 — `{entry.filename}` drafted as `draft.md`\n",
                encoding="utf-8",
            )

            code, output = self.run_cli(root, "reply", "read", "--apply")

            self.assertEqual(code, 0)
            self.assertIn("Latest digest: Never Sent: unread -> read", output)
            self.assertIn("Updated Never Sent to read.", output)
            self.assertEqual(read_index(root / "library" / "index.md")[0].status, "read")
            self.assertIn("unread -> read", (root / "_state" / "status-log.md").read_text(encoding="utf-8"))

    def test_reply_new_apply_skips_current_and_writes_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            current = self.ready_entry(title="Current Pick", filename="BAuthor_CurrentPick_2001_book.txt", sent=today())
            replacement = self.ready_entry(author="A, Author", title="Next Pick", filename="AAuthor_NextPick_2002_book.txt")
            (root / "library" / "index.md").write_text(render_index([current, replacement]), encoding="utf-8")
            (root / "_state" / "sent-log.md").write_text(
                "# Sent Log\n\n"
                f"- 2026-01-01T09:00:00 — `{current.filename}` drafted as `draft.md`\n",
                encoding="utf-8",
            )

            code, output = self.run_cli(root, "reply", "new", "--apply")

            self.assertEqual(code, 0)
            self.assertIn("Latest digest: Current Pick: unread -> skipped", output)
            self.assertIn("Replacement digest pick: Next Pick by A, Author", output)
            entries = {entry.title: entry for entry in read_index(root / "library" / "index.md")}
            self.assertEqual(entries["Current Pick"].status, "skipped")
            self.assertEqual(entries["Next Pick"].sent, today())
            self.assertEqual(len(list((root / "_output" / "weekly-read-drafts").glob("*.md"))), 1)
            self.assertIn("unread -> skipped", (root / "_state" / "status-log.md").read_text(encoding="utf-8"))
            self.assertIn("AAuthor_NextPick_2002_book.txt", (root / "_state" / "sent-log.md").read_text(encoding="utf-8"))

    def test_ingest_enrich_requires_model_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            (root / "inbox" / "BakerAnn_Test_2001_essay.txt").write_text("This is enough text to need semantic enrichment.", encoding="utf-8")

            with patch.dict(os.environ, {}, clear=True):
                code, output = self.run_cli(root, "ingest", "--enrich")

            self.assertEqual(code, 2)
            self.assertIn("Model enrichment requires", output)

    def test_ingest_enrich_populates_summary_and_primer_prompts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            command = self.fake_model_command(root)
            (root / "inbox" / "BakerAnn_Test_2001_essay.txt").write_text(
                "This essay develops a focused argument about reading tools and attention.",
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"LIBRARIAN_MODEL_COMMAND": command}, clear=True):
                code, _ = self.run_cli(root, "ingest", "--enrich", "--apply")

            self.assertEqual(code, 0)
            entries = read_index(root / "library" / "index.md")
            self.assertEqual(entries[0].next_action, "clean")
            self.assertIn("concrete local example", entries[0].summary)
            self.assertIn("What problem does the author make visible?", entries[0].primer_prompts)

    def test_enrich_existing_entry_updates_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            command = self.fake_model_command(root)
            filename = "AuthorB_Test_2001_essay.txt"
            (root / "library" / filename).write_text("This essay develops a focused argument about reading tools and attention.", encoding="utf-8")
            entry = WorkEntry(author="B, Author", title="Test", filename=filename, summary="Test.", next_action="needs_model")
            (root / "library" / "index.md").write_text(render_index([entry]), encoding="utf-8")

            with patch.dict(os.environ, {"LIBRARIAN_MODEL_COMMAND": command}, clear=True):
                code, output = self.run_cli(root, "enrich", "Test", "--apply")

            self.assertEqual(code, 0)
            self.assertIn("Applied enrichment for 1 entry", output)
            entries = read_index(root / "library" / "index.md")
            self.assertEqual(entries[0].next_action, "clean")
            self.assertEqual(len(entries[0].primer_prompts), 3)

    def test_enrich_reports_model_command_exit_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            command = self.fake_model_script(
                root,
                "failing_model.py",
                "import sys\n"
                "print('provider quota exceeded', file=sys.stderr)\n"
                "raise SystemExit(7)\n",
            )
            filename = "AuthorB_Test_2001_essay.txt"
            (root / "library" / filename).write_text("This essay develops a focused argument about reading tools and attention.", encoding="utf-8")
            entry = WorkEntry(author="B, Author", title="Test", filename=filename, summary="Test.", next_action="needs_model")
            (root / "library" / "index.md").write_text(render_index([entry]), encoding="utf-8")

            with patch.dict(os.environ, {"LIBRARIAN_MODEL_COMMAND": command}, clear=True):
                code, output = self.run_cli(root, "enrich", "Test")

            self.assertEqual(code, 0)
            self.assertIn("model command exited with code 7", output)
            self.assertIn("provider quota exceeded", output)

    def test_enrich_reports_invalid_model_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            command = self.fake_model_script(root, "invalid_json_model.py", "print('not json')\n")
            filename = "AuthorB_Test_2001_essay.txt"
            (root / "library" / filename).write_text("This essay develops a focused argument about reading tools and attention.", encoding="utf-8")
            entry = WorkEntry(author="B, Author", title="Test", filename=filename, summary="Test.", next_action="needs_model")
            (root / "library" / "index.md").write_text(render_index([entry]), encoding="utf-8")

            with patch.dict(os.environ, {"LIBRARIAN_MODEL_COMMAND": command}, clear=True):
                code, output = self.run_cli(root, "enrich", "Test")

            self.assertEqual(code, 0)
            self.assertIn("model command did not return valid JSON", output)

    def test_enrich_reports_incomplete_model_output_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            command = self.fake_model_script(
                root,
                "short_summary_model.py",
                "import json\n"
                "print(json.dumps({'summary': 'Too short.', 'primer_prompts': ['First?', 'Second?'], 'tags': [], 'related': 'None.'}))\n",
            )
            filename = "AuthorB_Test_2001_essay.txt"
            (root / "library" / filename).write_text("This essay develops a focused argument about reading tools and attention.", encoding="utf-8")
            entry = WorkEntry(author="B, Author", title="Test", filename=filename, summary="Test.", next_action="needs_model")
            (root / "library" / "index.md").write_text(render_index([entry]), encoding="utf-8")

            with patch.dict(os.environ, {"LIBRARIAN_MODEL_COMMAND": command}, clear=True):
                code, output = self.run_cli(root, "enrich", "Test")

            self.assertEqual(code, 0)
            self.assertIn("summary is too short", output)

    def test_mark_read_requires_apply(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            entry = WorkEntry(author="Ong, Walter", title="Orality and Literacy", filename="OngWalter_OralityAndLiteracy_1982_book.txt")
            (root / "library" / "index.md").write_text(render_index([entry]), encoding="utf-8")

            code, _ = self.run_cli(root, "mark-read", "Orality")
            self.assertEqual(code, 0)
            self.assertIn("Status: unread", (root / "library" / "index.md").read_text(encoding="utf-8"))

            code, _ = self.run_cli(root, "mark-read", "Orality", "--apply")
            self.assertEqual(code, 0)
            self.assertIn("Status: read", (root / "library" / "index.md").read_text(encoding="utf-8"))
            self.assertIn("unread -> read", (root / "_state" / "status-log.md").read_text(encoding="utf-8"))

    def test_lint_finds_missing_index_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            (root / "library" / "OngWalter_OralityAndLiteracy_1982_book.txt").write_text("text", encoding="utf-8")

            code, output = self.run_cli(root, "lint")

            self.assertEqual(code, 1)
            self.assertIn("MISSING_INDEX", output)

    def test_lint_reports_quarantine_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            (root / "_quarantine" / "bad.pdf").write_bytes(b"not a real pdf")

            code, output = self.run_cli(root, "lint")

            self.assertEqual(code, 1)
            self.assertIn("QUARANTINE", output)

    def test_lint_reports_malformed_index_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            (root / "library" / "index.md").write_text(
                "# Reading Library Index\n\n## Authors\n\n### Ong, Walter\n\n- **Broken** — book\n",
                encoding="utf-8",
            )

            code, output = self.run_cli(root, "lint")

            self.assertEqual(code, 1)
            self.assertIn("MALFORMED_INDEX", output)

    def test_reindex_refreshes_library_metadata_and_preserves_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            target = root / "library" / "Ong_Walter_OralityAndLiteracy_1982_book.txt"
            target.write_text("Writing restructures consciousness.", encoding="utf-8")
            old = WorkEntry(
                author="Unknown",
                title="Bad Metadata",
                filename=target.name,
                original_filename="original-upload.txt",
                status="read",
                sent="2026-01-01",
            )
            (root / "library" / "index.md").write_text(render_index([old]), encoding="utf-8")

            code, output = self.run_cli(root, "reindex", "--apply")

            self.assertEqual(code, 0)
            self.assertIn("Rebuilt index.md", output)
            entries = read_index(root / "library" / "index.md")
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].author, "Ong, Walter")
            self.assertEqual(entries[0].title, "Orality And Literacy")
            self.assertEqual(entries[0].original_filename, "original-upload.txt")
            self.assertEqual(entries[0].status, "read")
            self.assertEqual(entries[0].sent, "2026-01-01")

    def test_reindex_parses_canonical_author_key_and_text_year(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            target = root / "library" / "BaudrillardJean_SimulacraAndSimulation_nd_book.txt"
            target.write_text("Simulacra and Simulation Jean Baudrillard First published 1994 Contents", encoding="utf-8")

            code, _ = self.run_cli(root, "reindex", "--apply")

            self.assertEqual(code, 0)
            entries = read_index(root / "library" / "index.md")
            self.assertEqual(entries[0].author, "Baudrillard, Jean")
            self.assertEqual(entries[0].year, "1994")

    def test_reindex_repairs_opaque_unknown_filename_from_front_matter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            target = root / "library" / "Unknown_224fecab4a6e9d1d7b402478e5361c80_nd_unknown.txt"
            target.write_text(
                "\n".join(
                    [
                        "Attention",
                        "and Effort",
                        "DANIEL KAHNEMAN",
                        "Copyright 1973 by Prentice-Hall",
                        "Contents",
                        "1 Basic issues in the study of attention",
                    ]
                ),
                encoding="utf-8",
            )

            code, _ = self.run_cli(root, "reindex", "--apply")

            self.assertEqual(code, 0)
            entries = read_index(root / "library" / "index.md")
            self.assertEqual(entries[0].author, "Kahneman, Daniel")
            self.assertEqual(entries[0].title, "Attention and Effort")
            self.assertEqual(entries[0].year, "1973")
            self.assertEqual(entries[0].work_type, "book")

    def test_reindex_lookup_completes_surname_only_author(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            target = root / "library" / "Chiang_StoriesOfYourLife_2002_stories.txt"
            target.write_text("", encoding="utf-8")
            payload = {
                "docs": [
                    {
                        "title": "Stories of Your Life",
                        "author_name": ["Ted Chiang"],
                        "first_publish_year": 2002,
                    }
                ]
            }

            with patch("urllib.request.urlopen") as urlopen:
                urlopen.return_value = io.BytesIO(json.dumps(payload).encode("utf-8"))
                code, _ = self.run_cli(root, "reindex", "--lookup", "--apply")

            self.assertEqual(code, 0)
            entries = read_index(root / "library" / "index.md")
            self.assertEqual(entries[0].author, "Chiang, Ted")
            self.assertEqual(entries[0].title, "Stories Of Your Life")
            self.assertEqual(entries[0].year, "2002")
            self.assertEqual(entries[0].next_action, "needs_ocr")

    def test_ocr_dry_run_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            source = root / "library" / "ChiangTed_StoriesOfYourLife_2002_story.pdf"
            source.write_bytes(b"%PDF-1.4 scanned placeholder\n")
            entry = self.ready_entry(
                author="Chiang, Ted",
                title="Stories Of Your Life",
                filename=source.name,
                next_action="needs_ocr",
            )
            (root / "library" / "index.md").write_text(render_index([entry]), encoding="utf-8")

            code, output = self.run_cli(root, "ocr")

            self.assertEqual(code, 0)
            self.assertIn("[dry-run] OCR Stories Of Your Life", output)
            self.assertIn("Dry run only", output)
            self.assertEqual(list((root / "_output" / "ocr").glob("*.pdf")), [])

    def test_ocr_apply_writes_no_overwrite_copy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            source = root / "library" / "ChiangTed_StoriesOfYourLife_2002_story.pdf"
            source.write_bytes(b"%PDF-1.4 scanned placeholder\n")
            entry = self.ready_entry(
                author="Chiang, Ted",
                title="Stories Of Your Life",
                filename=source.name,
                next_action="needs_ocr",
            )
            (root / "library" / "index.md").write_text(render_index([entry]), encoding="utf-8")
            existing = root / "_output" / "ocr" / source.name
            existing.write_bytes(b"existing")

            with patch.dict(os.environ, {"LIBRARIAN_OCR_COMMAND": self.fake_ocr_command(root)}):
                code, output = self.run_cli(root, "ocr", "--apply")

            self.assertEqual(code, 0)
            self.assertIn("Wrote _output/ocr/ChiangTed_StoriesOfYourLife_2002_story_2.pdf", output)
            self.assertEqual(existing.read_bytes(), b"existing")
            self.assertEqual((root / "_output" / "ocr" / "ChiangTed_StoriesOfYourLife_2002_story_2.pdf").read_bytes(), source.read_bytes())

    def test_ocr_apply_promote_preserves_original_and_rebuilds_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            source = root / "library" / "Wallace_David_Foster_EUnibusPluram_1993_essay.pdf"
            source.write_bytes(b"original scan")
            entry = self.ready_entry(
                author="Wallace, David Foster",
                title="E Unibus Pluram",
                filename=source.name,
                next_action="needs_model",
                primer_prompts=[],
            )
            (root / "library" / "index.md").write_text(render_index([entry]), encoding="utf-8")

            def fake_extract_pdf(path: Path):
                if path.name == source.name:
                    return {}, "Television and U.S. fiction. This essay studies irony, spectatorship, image fiction, and literary culture.", []
                return {}, "", []

            with patch.dict(os.environ, {"LIBRARIAN_OCR_COMMAND": self.fake_ocr_command(root)}, clear=True):
                with patch("librarian.cli.extract_pdf", side_effect=fake_extract_pdf):
                    code, output = self.run_cli(root, "ocr", "E Unibus Pluram", "--apply", "--promote")

            self.assertEqual(code, 0)
            self.assertIn("Promoted OCR copy", output)
            self.assertTrue((root / "_output" / "ocr" / "original-library-files" / source.name).exists())
            self.assertTrue(source.exists())
            entries = read_index(root / "library" / "index.md")
            self.assertEqual(entries[0].filename, source.name)
            self.assertNotEqual(entries[0].next_action, "needs_ocr")

    def test_repair_dry_run_lists_current_blockers_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            blocker = WorkEntry(
                author="B, Author",
                title="Needs Model",
                filename="BAuthor_NeedsModel_2001_essay.txt",
                summary="Needs Model",
                next_action="needs_model",
            )
            ready = self.ready_entry(title="Ready", filename="BAuthor_Ready_2002_book.txt")
            (root / "library" / blocker.filename).write_text("A focused essay about attention and tools.", encoding="utf-8")
            (root / "library" / ready.filename).write_text("Already ready.", encoding="utf-8")
            (root / "library" / "index.md").write_text(render_index([blocker, ready]), encoding="utf-8")
            before = (root / "library" / "index.md").read_text(encoding="utf-8")

            code, output = self.run_cli(root, "repair")

            self.assertEqual(code, 0)
            self.assertIn("[dry-run] Repair 1 entry", output)
            self.assertIn("REVIEW", output)
            self.assertIn("Dry run only", output)
            self.assertEqual((root / "library" / "index.md").read_text(encoding="utf-8"), before)

    def test_repair_lookup_hardens_front_matter_byline_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            source = root / "library" / "Norman-TheDesignOfEverydayThings.txt"
            source.write_text(
                "\n".join(
                    [
                        "The Design of Everyday Things",
                        "by Don Norman",
                        "First published 1988",
                        "Contents",
                        "This book studies affordances, constraints, mappings, and the psychology of everyday action.",
                    ]
                ),
                encoding="utf-8",
            )
            old = WorkEntry(author="Unknown", title="Norman The Design Of Everyday Things", filename=source.name, next_action="needs_catalog")
            (root / "library" / "index.md").write_text(render_index([old]), encoding="utf-8")

            code, output = self.run_cli(root, "repair", "Norman", "--apply", "--lookup")

            self.assertEqual(code, 0)
            self.assertIn("Applied metadata repair", output)
            repaired = root / "library" / "NormanDon_TheDesignOfEverydayThings_1988_book.txt"
            self.assertTrue(repaired.exists())
            self.assertFalse(source.exists())
            entries = read_index(root / "library" / "index.md")
            self.assertEqual(entries[0].author, "Norman, Don")
            self.assertEqual(entries[0].title, "The Design of Everyday Things")
            self.assertEqual(entries[0].year, "1988")

    def test_repair_ocr_promotes_matching_scanned_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            source = root / "library" / "ChiangTed_StoriesOfYourLife_2002_story.pdf"
            source.write_bytes(b"original scan")
            entry = self.ready_entry(
                author="Chiang, Ted",
                title="Stories Of Your Life",
                filename=source.name,
                next_action="needs_ocr",
            )
            (root / "library" / "index.md").write_text(render_index([entry]), encoding="utf-8")

            def fake_extract_pdf(path: Path):
                if path.name == source.name:
                    return {}, "Stories of Your Life Ted Chiang 2002 This story has extractable text after OCR.", []
                return {}, "", []

            with patch.dict(os.environ, {"LIBRARIAN_OCR_COMMAND": self.fake_ocr_command(root)}, clear=True):
                with patch("librarian.cli.extract_pdf", side_effect=fake_extract_pdf):
                    code, output = self.run_cli(root, "repair", "Stories", "--apply", "--ocr")

            self.assertEqual(code, 0)
            self.assertIn("OCR/promote", output)
            self.assertIn("Promoted OCR copy", output)
            self.assertTrue((root / "_output" / "ocr" / "original-library-files" / source.name).exists())
            entries = read_index(root / "library" / "index.md")
            self.assertNotEqual(entries[0].next_action, "needs_ocr")

    def test_repair_enriches_only_selected_matching_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            command = self.fake_model_command(root)
            selected = WorkEntry(
                author="B, Author",
                title="Selected",
                filename="BAuthor_Selected_2001_essay.txt",
                summary="Selected",
                next_action="needs_model",
                original_filename="BAuthor_Selected_2001_essay.txt",
            )
            other = WorkEntry(
                author="C, Author",
                title="Other",
                filename="CAuthor_Other_2002_essay.txt",
                summary="Other",
                next_action="needs_model",
                original_filename="CAuthor_Other_2002_essay.txt",
            )
            (root / "library" / selected.filename).write_text("This essay develops a focused argument about reading tools and attention.", encoding="utf-8")
            (root / "library" / other.filename).write_text("This essay also needs model help but was not selected.", encoding="utf-8")
            (root / "library" / "index.md").write_text(render_index([selected, other]), encoding="utf-8")

            with patch.dict(os.environ, {"LIBRARIAN_MODEL_COMMAND": command}, clear=True):
                code, output = self.run_cli(root, "repair", "Selected", "--apply", "--enrich")

            self.assertEqual(code, 0)
            self.assertIn("Applied enrichment for 1 entry", output)
            entries = {entry.title: entry for entry in read_index(root / "library" / "index.md")}
            self.assertEqual(entries["Selected"].next_action, "clean")
            self.assertEqual(entries["Other"].next_action, "needs_model")

    def test_maintain_dry_run_proposes_stale_filename_repair_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            stale = root / "library" / "BaudrillardJean_SimulacraAndSimulation_nd_book.txt"
            stale.write_text("Simulacra and Simulation Jean Baudrillard First published 1994 Contents", encoding="utf-8")
            legacy = root / "library" / "Cage_John_Silence_1961_essays.txt"
            legacy.write_text("Silence John Cage 1961 Contents", encoding="utf-8")

            code, output = self.run_cli(root, "maintain")

            self.assertEqual(code, 0)
            self.assertIn("BaudrillardJean_SimulacraAndSimulation_nd_book.txt -> BaudrillardJean_SimulacraAndSimulation_1994_book.txt", output)
            self.assertNotIn("CageJohn_Silence_1961_essay.txt", output)
            self.assertTrue(stale.exists())

    def test_maintain_apply_renames_stale_file_and_rebuilds_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            stale = root / "library" / "BaudrillardJean_SimulacraAndSimulation_nd_book.txt"
            stale.write_text("Simulacra and Simulation Jean Baudrillard First published 1994 Contents", encoding="utf-8")

            code, output = self.run_cli(root, "maintain", "--apply")

            self.assertEqual(code, 0)
            self.assertIn("Applied maintenance: 1 rename", output)
            repaired = root / "library" / "BaudrillardJean_SimulacraAndSimulation_1994_book.txt"
            self.assertTrue(repaired.exists())
            self.assertFalse(stale.exists())
            entries = read_index(root / "library" / "index.md")
            self.assertEqual(entries[0].filename, repaired.name)
            self.assertEqual(entries[0].next_action, "needs_model")

    def test_maintain_preserves_existing_year_when_local_inference_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            stale = root / "library" / "BaudrillardJean_SimulacraAndSimulation_nd_book.txt"
            stale.write_text("Simulacra and Simulation Jean Baudrillard Contents", encoding="utf-8")
            old = WorkEntry(
                author="Baudrillard, Jean",
                title="Simulacra And Simulation",
                year="1994",
                work_type="book",
                filename=stale.name,
                original_filename="original.pdf",
                summary="Ready.",
            )
            (root / "library" / "index.md").write_text(render_index([old]), encoding="utf-8")

            code, output = self.run_cli(root, "maintain")

            self.assertEqual(code, 0)
            self.assertIn("BaudrillardJean_SimulacraAndSimulation_nd_book.txt -> BaudrillardJean_SimulacraAndSimulation_1994_book.txt", output)

    def test_reindex_is_dry_run_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            target = root / "library" / "Ong_Walter_OralityAndLiteracy_1982_book.txt"
            target.write_text("Writing restructures consciousness.", encoding="utf-8")

            code, output = self.run_cli(root, "reindex")

            self.assertEqual(code, 0)
            self.assertIn("Dry run only", output)
            self.assertEqual(read_index(root / "library" / "index.md"), [])

    def test_config_paths_must_stay_inside_project_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            (root / "_state" / "config.toml").write_text(
                '[paths]\nindex = "../outside.md"\n',
                encoding="utf-8",
            )

            code, output = self.run_cli(root, "lint")

            self.assertEqual(code, 2)
            self.assertIn("CONFIG_ERROR", output)


if __name__ == "__main__":
    unittest.main()
