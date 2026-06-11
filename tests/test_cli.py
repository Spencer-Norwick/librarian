from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

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

    def test_sample_fixture_dirs_live_under_tests(self) -> None:
        self.assertTrue((FIXTURES / "inbox").is_dir())
        self.assertTrue((FIXTURES / "library").is_dir())

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
            self.assertFalse(source.exists())
            self.assertTrue((root / "library" / "OngWalter_OralityAndLiteracy_1982_book.txt").exists())

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
            self.assertIn("Wrote _output/weekly-read-drafts", output)
            entries = read_index(root / "library" / "index.md")
            self.assertEqual(entries[0].sent, today())
            self.assertEqual(len(list((root / "_output" / "weekly-read-drafts").glob("*.md"))), 1)

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
