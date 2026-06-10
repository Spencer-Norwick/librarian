from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from librarian.cli import WorkEntry, filename_convention_ok, infer_year_from_text, main, read_index, render_index, today

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

    def test_sample_fixture_dirs_live_under_tests(self) -> None:
        self.assertTrue((FIXTURES / "inbox").is_dir())
        self.assertTrue((FIXTURES / "library").is_dir())

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

    def test_year_inference_prefers_first_published_over_later_edition(self) -> None:
        text = "This paperback edition published by Verso 2014 First published in English by Verso 2002 © Verso 2002, 2014"

        self.assertEqual(infer_year_from_text(text), "2002")

    def test_weekly_pick_avoids_already_sent_work(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_project(root)
            entries = [
                WorkEntry(author="A, Author", title="Already Sent", filename="AAuthor_AlreadySent_2000_book.txt", sent="2026-01-01"),
                WorkEntry(author="B, Author", title="Never Sent", filename="BAuthor_NeverSent_2001_book.txt", sent="never"),
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
            entry = WorkEntry(author="B, Author", title="Never Sent", filename="BAuthor_NeverSent_2001_book.txt", sent="never")
            (root / "library" / "index.md").write_text(render_index([entry]), encoding="utf-8")
            existing = root / "_output" / "weekly-read-drafts" / f"{today()}_NeverSent.md"
            existing.write_text("existing draft", encoding="utf-8")

            code, _ = self.run_cli(root, "weekly-pick", "--apply")

            self.assertEqual(code, 0)
            self.assertEqual(existing.read_text(encoding="utf-8"), "existing draft")
            self.assertTrue((root / "_output" / "weekly-read-drafts" / f"{today()}_NeverSent_2.md").exists())

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
