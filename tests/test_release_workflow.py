from __future__ import annotations

import datetime as dt
import io
import json
import os
import subprocess
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from librarian import cli
from librarian.config import project_config
from librarian.domain import DigestHistory, DigestPlan, MaintenancePlan, ModelEnrichment, ModelEnrichmentAttempt, RenamePlan, WorkEntry
from librarian.index import read_index, render_index


class ReleaseWorkflowTests(unittest.TestCase):
    def run_cli(self, root: Path, *args: str) -> tuple[int, str]:
        output = io.StringIO()
        with redirect_stdout(output):
            result = cli.main(list(args), root=root)
        return result, output.getvalue()

    def init(self, root: Path) -> None:
        self.assertEqual(self.run_cli(root, "init")[0], 0)

    def ready(self, filename: str = "SmithJane_SyntheticEssay_2024_essay.txt") -> WorkEntry:
        return WorkEntry(author="Smith, Jane", title="Synthetic Essay", year="2024", work_type="essay",
                         filename=filename, original_filename="original synthetic essay.txt", reading_time="~2m",
                         summary="The synthetic essay compares two ways to care for a shared resource.",
                         primer_prompts=["Which tradeoff does the argument emphasize?"], added="2024-01-01")

    def test_synthetic_ingest_enrich_maintain_short_weekly_and_repeat_guard(self) -> None:
        with TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True):
            root = Path(tmp).resolve()
            self.init(root)
            originals = ["AlphaAnne_LongBook_2024_book.txt", "ZuluZoe_SyntheticEssay_2024_essay.txt"]
            for original in originals:
                (root / "inbox" / original).write_text("A synthetic argument about caring for shared resources. " * 80)
            config_path = root / "_state" / "config.toml"
            config_path.write_text(config_path.read_text().replace("model_command = []", 'model_command = ["synthetic-hook"]'))
            before = (root / "library" / "index.md").read_bytes()
            self.assertEqual(self.run_cli(root, "ingest")[0], 0)
            self.assertEqual((root / "library" / "index.md").read_bytes(), before)
            self.assertTrue(all((root / "inbox" / name).exists() for name in originals))
            self.assertEqual(self.run_cli(root, "ingest", "--apply")[0], 0)
            enrichment = ModelEnrichmentAttempt(ModelEnrichment(
                summary="This synthetic work describes a choice about caring for shared resources.",
                primer_prompts=["Which choice is defended, and on what evidence?"], tags=["synthetic"]))
            with patch("librarian.cli.try_enrich_from_model", return_value=enrichment) as model:
                self.assertEqual(self.run_cli(root, "enrich", "--apply")[0], 0)
                self.assertEqual(model.call_count, 2)
            self.assertEqual(self.run_cli(root, "maintain", "--apply")[0], 0)
            entries = read_index(root / "library" / "index.md")
            self.assertEqual({entry.original_filename for entry in entries}, set(originals))
            self.assertTrue(all(entry.added and entry.primer_prompts for entry in entries))
            before = (root / "library" / "index.md").read_bytes()
            with patch("librarian.cli.run_delivery_step") as delivery:
                self.assertEqual(self.run_cli(root, "weekly", "--mode", "short", "--max-minutes", "0")[0], 0)
                self.assertEqual((root / "library" / "index.md").read_bytes(), before)
                self.assertEqual(list((root / "_output" / "weekly-read-drafts").iterdir()), [])
                self.assertEqual(self.run_cli(root, "weekly-due", "--mode", "short", "--apply")[0], 0)
                self.assertEqual(self.run_cli(root, "weekly-due", "--mode", "short", "--apply")[0], 0)
                delivery.assert_not_called()
            entries = read_index(root / "library" / "index.md")
            self.assertEqual([entry.work_type for entry in entries if entry.sent != "never"], ["essay"])
            self.assertEqual(len(list((root / "_output" / "weekly-read-drafts").iterdir())), 1)

    def test_automatic_model_settings_do_not_override_default_approval(self) -> None:
        for command in ("ingest", "reindex", "maintain", "daily"):
            with self.subTest(command=command), TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True):
                root = Path(tmp).resolve()
                self.init(root)
                (root / "inbox" / "SmithJane_SyntheticEssay_2024_essay.txt").write_text("Synthetic argument. " * 60)
                config_path = root / "_state" / "config.toml"
                config_path.write_text(config_path.read_text().replace("use_model_assistance = false", "use_model_assistance = true")
                                       .replace("model_command = []", 'model_command = ["synthetic-hook"]'))
                with patch("librarian.cli.try_enrich_from_model") as model:
                    self.run_cli(root, "ingest", "--apply")
                    self.run_cli(root, command)
                    model.assert_not_called()

    def test_uninitialized_ingest_removes_transaction_created_index_on_log_failure(self) -> None:
        with TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True):
            root = Path(tmp).resolve()
            (root / "inbox").mkdir()
            source = root / "inbox" / "SmithJane_SyntheticEssay_2024_essay.txt"
            source.write_text("Synthetic reading content. " * 60)
            before = source.read_bytes()
            atomic = cli.write_text_atomic

            def fail_log(path: Path, text: str) -> None:
                if path.name == "ingest-log.md":
                    raise OSError("synthetic log-write failure")
                atomic(path, text)

            with patch("librarian.cli.write_text_atomic", side_effect=fail_log):
                code, output = self.run_cli(root, "ingest", "--apply")
            self.assertEqual(code, 2)
            self.assertIn("log-write failure", output)
            self.assertEqual(source.read_bytes(), before)
            self.assertFalse((root / "library" / "index.md").exists())
            self.assertFalse((root / "_state" / "ingest-log.md").exists())
            self.assertEqual(list((root / "library").iterdir()), [])

    def test_edit_and_status_writes_preserve_original_added_and_review_notes(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            self.init(root)
            entry = self.ready()
            entry.needs_review = ["Check the synthetic source against its bibliography."]
            source = root / "library" / entry.filename
            source.write_text("synthetic reading")
            index = root / "library" / "index.md"
            index.write_text(render_index([entry]))
            before = index.read_bytes()
            self.assertEqual(self.run_cli(root, "edit", "Synthetic Essay", "--title", "Revised Essay")[0], 0)
            self.assertEqual(index.read_bytes(), before)
            self.assertTrue(source.exists())
            self.assertEqual(self.run_cli(root, "edit", "Synthetic Essay", "--title", "Revised Essay", "--apply")[0], 0)
            self.assertEqual(self.run_cli(root, "mark-read", "Revised Essay", "--apply")[0], 0)
            saved = read_index(index)[0]
            self.assertEqual(saved.original_filename, entry.original_filename)
            self.assertEqual(saved.added, entry.added)
            self.assertEqual(saved.needs_review, entry.needs_review)
            self.assertTrue((root / "library" / saved.filename).exists())

    def test_maintenance_rolls_back_renames_after_index_write_failure(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            self.init(root)
            config = project_config(root)
            entry = self.ready("old.txt")
            source = config.library / entry.filename
            source.write_text("preserve this synthetic content")
            config.index.write_text(render_index([entry]))
            before = config.index.read_bytes()
            target = "SmithJane_SyntheticEssay_2024_essay.txt"
            plan = MaintenancePlan([self.ready(target)], [RenamePlan("old.txt", target)])
            with patch("librarian.cli.build_maintenance_plan", return_value=plan), patch("librarian.cli.write_index", side_effect=OSError("synthetic write failure")):
                code, _ = self.run_cli(root, "maintain", "--apply")
            self.assertEqual(code, 2)
            self.assertEqual(config.index.read_bytes(), before)
            self.assertEqual(source.read_text(), "preserve this synthetic content")
            self.assertFalse((config.library / target).exists())

    def test_maintenance_rolls_back_first_rename_when_later_target_collides(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            self.init(root)
            config = project_config(root)
            (config.library / "one.txt").write_text("first")
            (config.library / "two.txt").write_text("second")
            (config.library / "occupied.txt").write_text("existing")
            before = config.index.read_bytes()
            plan = MaintenancePlan([], [RenamePlan("one.txt", "new.txt"), RenamePlan("two.txt", "occupied.txt")])
            with patch("librarian.cli.build_maintenance_plan", return_value=plan):
                self.assertEqual(self.run_cli(root, "maintain", "--apply")[0], 2)
            self.assertEqual(config.index.read_bytes(), before)
            self.assertEqual((config.library / "one.txt").read_text(), "first")
            self.assertEqual((config.library / "two.txt").read_text(), "second")
            self.assertEqual((config.library / "occupied.txt").read_text(), "existing")
            self.assertFalse((config.library / "new.txt").exists())

    def test_messages_timeout_retains_uncertainty_and_blocks_automatic_retry(self) -> None:
        with TemporaryDirectory() as tmp, patch.dict(os.environ, {"LIBRARIAN_MESSAGE_TO": "synthetic@example.invalid"}, clear=True):
            root = Path(tmp).resolve()
            self.init(root)
            entry = self.ready()
            (root / "library" / entry.filename).write_text("synthetic reading")
            (root / "library" / "index.md").write_text(render_index([entry]))
            with patch("librarian.cli.run_delivery_step", side_effect=TimeoutError("synthetic ambiguous timeout")) as delivery:
                self.assertEqual(self.run_cli(root, "weekly-due", "--apply", "--message-self")[0], 2)
                self.assertEqual(self.run_cli(root, "weekly-due", "--apply", "--message-self")[0], 2)
                self.assertEqual(delivery.call_count, 1)
            state = json.loads((root / "_state" / "weekly-delivery.json").read_text())
            self.assertEqual(state["in_progress_step"], "message_self")
            self.assertEqual(read_index(root / "library" / "index.md")[0].sent, "never")

    def test_maintenance_incomplete_rollback_preserves_both_files_and_reports_error(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            self.init(root)
            config = project_config(root)
            source = config.library / "old.txt"
            source.write_text("original reading")
            plan = MaintenancePlan([], [RenamePlan("old.txt", "new.txt")])

            def fail_index(*args: object) -> None:
                source.write_text("concurrent new file")
                raise OSError("synthetic index failure")

            with patch("librarian.cli.build_maintenance_plan", return_value=plan), patch("librarian.cli.write_index", side_effect=fail_index):
                code, output = self.run_cli(root, "maintain", "--apply")
            self.assertEqual(code, 2)
            self.assertIn("OPERATION_ERROR", output)
            self.assertIn("rollback was incomplete", output)
            self.assertEqual(source.read_text(), "concurrent new file")
            self.assertEqual((config.library / "new.txt").read_text(), "original reading")

    def test_edit_rename_rolls_back_after_index_write_failure(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            self.init(root)
            entry = self.ready()
            source = root / "library" / entry.filename
            source.write_text("original synthetic reading")
            index = root / "library" / "index.md"
            index.write_text(render_index([entry]))
            before = index.read_bytes()
            with patch("librarian.cli.write_index", side_effect=OSError("synthetic index failure")):
                code, _ = self.run_cli(root, "edit", "Synthetic Essay", "--title", "Revised Essay", "--apply")
            self.assertEqual(code, 2)
            self.assertEqual(index.read_bytes(), before)
            self.assertEqual(source.read_text(), "original synthetic reading")
            self.assertEqual([path.name for path in (root / "library").iterdir() if path.suffix == ".txt"], [entry.filename])

    def test_pending_email_reuses_key_across_week_boundary(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            self.init(root)
            config = project_config(root)
            entry = self.ready()
            plan = DigestPlan(entry, config.drafts / "synthetic.md", "synthetic digest", DigestHistory())
            with patch("librarian.cli.current_week_id", return_value="2026-W37"):
                state = cli.start_weekly_delivery_state(config, plan, ["email"], root)
            key = state["email_idempotency_key"]
            with patch("librarian.cli.current_week_id", return_value="2026-W38"), patch("librarian.cli.send_digest_email") as send:
                cli.run_delivery_steps(config, plan, root, ["email"], state)
            self.assertEqual(send.call_args.kwargs["idempotency_key"], key)
            saved = json.loads(cli.weekly_delivery_state_path(config).read_text())
            self.assertEqual(saved["email_idempotency_key"], key)

    def test_wrapped_email_timeout_preserves_unknown_outcome(self) -> None:
        with TemporaryDirectory() as tmp, patch.dict(os.environ, {
            "RESEND_API_KEY": "synthetic-token",
            "LIBRARIAN_EMAIL_FROM": "sender@example.invalid",
            "LIBRARIAN_EMAIL_TO": "reader@example.invalid",
        }, clear=True):
            root = Path(tmp).resolve()
            self.init(root)
            config = project_config(root)
            entry = self.ready()
            plan = DigestPlan(entry, config.drafts / "synthetic.md", "synthetic digest", DigestHistory())
            state = cli.start_weekly_delivery_state(config, plan, ["email"], root)
            with patch("librarian.cli.urllib.request.urlopen", side_effect=TimeoutError("synthetic provider timeout")) as transport:
                with self.assertRaisesRegex(ValueError, "Email delivery failed"):
                    cli.run_delivery_steps(config, plan, root, ["email"], state)
                state["created_at"] = (dt.datetime.now() - dt.timedelta(hours=24)).isoformat()
                with self.assertRaisesRegex(ValueError, "outcome is unknown"):
                    cli.run_delivery_steps(config, plan, root, ["email"], state)
                self.assertEqual(transport.call_count, 1)
            saved = json.loads(cli.weekly_delivery_state_path(config).read_text())
            self.assertEqual(saved["in_progress_step"], "email")
            self.assertIn("provider timeout", saved["last_error"])

    def test_legacy_pending_email_key_uses_persisted_week_and_expired_timeout_is_blocked(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            self.init(root)
            config = project_config(root)
            entry = self.ready()
            plan = DigestPlan(entry, config.drafts / "synthetic.md", "synthetic digest", DigestHistory())
            state = cli.start_weekly_delivery_state(config, plan, ["email"], root)
            state.pop("email_idempotency_key")
            state.update(week="2026-W37", in_progress_step="email", created_at=(dt.datetime.now() - dt.timedelta(hours=24)).isoformat())
            with patch("librarian.cli.send_digest_email") as send:
                with self.assertRaisesRegex(ValueError, "outcome is unknown"):
                    cli.run_delivery_steps(config, plan, root, ["email"], state)
                send.assert_not_called()
            state["in_progress_step"] = ""
            with patch("librarian.cli.current_week_id", return_value="2026-W38"), patch("librarian.cli.send_digest_email") as send:
                cli.run_delivery_steps(config, plan, root, ["email"], state)
            self.assertEqual(send.call_args.kwargs["idempotency_key"], cli.digest_email_idempotency_key(entry, "2026-W37"))

    def test_ocr_promotion_second_move_failure_restores_original_and_preserves_copy(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            self.init(root)
            config = project_config(root)
            source = config.library / "synthetic.pdf"
            source.write_bytes(b"synthetic original scan")
            copy = config.ocr_outputs / "synthetic.pdf"
            copy.write_bytes(b"synthetic searchable copy")
            originals = config.ocr_outputs / "original-library-files"
            originals.mkdir()
            existing = originals / source.name
            existing.write_bytes(b"existing unrelated original")
            move = cli.move_without_overwrite

            def fail_second(source_path: Path, target_path: Path) -> None:
                if source_path == copy:
                    raise OSError("synthetic second-move failure")
                move(source_path, target_path)

            with patch("librarian.cli.move_without_overwrite", side_effect=fail_second):
                with self.assertRaisesRegex(OSError, "second-move failure"):
                    cli.promote_ocr_copy(config, source, copy)
            self.assertEqual(source.read_bytes(), b"synthetic original scan")
            self.assertEqual(copy.read_bytes(), b"synthetic searchable copy")
            self.assertEqual(existing.read_bytes(), b"existing unrelated original")
            self.assertEqual(list(originals.iterdir()), [existing])

    def test_ocr_promotion_rollback_collision_preserves_every_file(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            self.init(root)
            config = project_config(root)
            source = config.library / "synthetic.pdf"
            source.write_bytes(b"synthetic original scan")
            copy = config.ocr_outputs / source.name
            copy.write_bytes(b"synthetic searchable copy")
            move = cli.move_without_overwrite

            def collide_second(source_path: Path, target_path: Path) -> None:
                if source_path == copy:
                    target_path.write_bytes(b"concurrent new library file")
                move(source_path, target_path)

            with patch("librarian.cli.move_without_overwrite", side_effect=collide_second):
                with self.assertRaisesRegex(RuntimeError, "rollback was incomplete"):
                    cli.promote_ocr_copy(config, source, copy)
            self.assertEqual(source.read_bytes(), b"concurrent new library file")
            self.assertEqual(copy.read_bytes(), b"synthetic searchable copy")
            preserved = config.ocr_outputs / "original-library-files" / source.name
            self.assertEqual(preserved.read_bytes(), b"synthetic original scan")

    def test_ocr_batch_index_failure_restores_originals_and_retains_searchable_copies(self) -> None:
        with TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True):
            root = Path(tmp).resolve()
            self.init(root)
            config = project_config(root)
            entries = [self.ready("SmithJane_FirstEssay_2024_essay.pdf"), self.ready("SmithJane_SecondEssay_2024_essay.pdf")]
            for entry in entries:
                entry.next_action = "needs_ocr"
                (config.library / entry.filename).write_bytes(b"synthetic original " + entry.filename.encode())
            config.index.write_text(render_index(entries))
            before = config.index.read_bytes()

            def fake_ocr(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
                Path(command[-1]).write_bytes(b"synthetic searchable " + Path(command[-2]).name.encode())
                return subprocess.CompletedProcess(command, 0, "", "")

            def fail_index(*args: object) -> None:
                config.index.write_text("synthetic incomplete index")
                raise OSError("synthetic final index failure")

            with patch("librarian.cli.command_available", return_value=True), patch("librarian.cli.subprocess.run", side_effect=fake_ocr), patch(
                "librarian.cli.infer_entry", side_effect=lambda path, *args, **kwargs: self.ready(path.name)
            ), patch("librarian.cli.write_index", side_effect=fail_index):
                code, output = self.run_cli(root, "ocr", "--apply", "--promote")
            self.assertEqual(code, 2)
            self.assertIn("final index failure", output)
            self.assertEqual(config.index.read_bytes(), before)
            for entry in entries:
                self.assertEqual((config.library / entry.filename).read_bytes(), b"synthetic original " + entry.filename.encode())
                self.assertEqual((config.ocr_outputs / entry.filename).read_bytes(), b"synthetic searchable " + entry.filename.encode())
            self.assertEqual(list((config.ocr_outputs / "original-library-files").iterdir()), [])


if __name__ == "__main__":
    unittest.main()
