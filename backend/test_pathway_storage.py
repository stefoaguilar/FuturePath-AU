
import json
import sqlite3
import unittest

from contextlib import closing
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import database
import import_data

from pathway_storage import (
    save_draft_pathway,
    get_saved_pathway,
    edit_saved_step,
    approve_saved_pathway,
    export_approved_pathway,
    add_student_step,
    reorder_saved_steps,
    PathwayRevisionConflict
)


class TestPathwayStorage(unittest.TestCase):

    def setUp(self):

        # Create a separate temporary database
        # for each test.
        self.temp_dir = TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        self.test_db = (
            Path(self.temp_dir.name)
            / "futurepath_test.db"
        )

        # Create all five tables and import the
        # original opportunity dataset.
        # The real database is never modified.
        with patch.object(
            database,
            "DATABASE_PATH",
            self.test_db
        ), patch.object(
            import_data,
            "DATABASE_PATH",
            self.test_db
        ):
            database.create_database()
            import_data.import_opportunities()

        # Load Samer's source dataset.
        dataset_path = (
            Path(__file__).resolve().parent.parent
            / "data"
            / "opportunities.json"
        )

        dataset = json.loads(
            dataset_path.read_text(encoding="utf-8")
        )

        # Use SYN-10's opportunity.
        self.opportunity = next(
            item
            for item in dataset["opportunities"]
            if item["id"] == "OPP-005"
        )

        self.profile = {
            "education_level": "undergraduate",
            "citizenship_status": "australian_citizen"
        }

        self.reference_date = date(2026, 11, 28)

    def save_test_pathway(self):

        return save_draft_pathway(
            self.opportunity,
            self.profile,
            self.reference_date,
            database_path=self.test_db
        )

    # --------------------------------------------------
    # 1. Saving creates an unapproved pathway
    # --------------------------------------------------

    def test_save_creates_unapproved_draft(self):

        saved = self.save_test_pathway()

        self.assertTrue(saved["pathway_id"])
        self.assertEqual(
            saved["opportunity_id"],
            "OPP-005"
        )

        self.assertEqual(saved["revision"], 1)
        self.assertIsNone(saved["approved_revision"])

        self.assertEqual(saved["status"], "draft")
        self.assertFalse(saved["approved"])
        self.assertFalse(saved["can_export"])

        self.assertEqual(len(saved["steps"]), 5)

    # --------------------------------------------------
    # 2. Original source evidence is preserved
    # --------------------------------------------------

    def test_source_and_editable_fields_are_separate(self):

        saved = self.save_test_pathway()

        # Check the generated step structure.
        first_step = saved["steps"][0]

        self.assertEqual(
            first_step["origin"],
            "generated"
        )

        self.assertEqual(
            first_step["source_step_id"],
            "requirement:OPP-005-E1"
        )

        self.assertEqual(
            first_step["source_step"]["eligibility_status"],
            "uncertain"
        )

        self.assertEqual(first_step["student_note"], "")
        self.assertTrue(first_step["included"])

        # Verify the original opportunity snapshot.
        with closing(sqlite3.connect(self.test_db)) as connection:

            row = connection.execute(
                """
                SELECT source_snapshot_json
                FROM pathways
                WHERE id = ?
                """,
                (saved["pathway_id"],)
            ).fetchone()

            snapshot = json.loads(row[0])

            self.assertEqual(
                snapshot,
                self.opportunity
            )

            # Student profile answers are not
            # stored in the opportunity snapshot.
            self.assertNotIn("profile", snapshot)

            # Generated source content is separate
            # from student-editable fields.
            step_row = connection.execute(
                """
                SELECT
                    source_step_json,
                    title_override,
                    student_note
                FROM pathway_steps
                WHERE pathway_id = ?
                ORDER BY position
                LIMIT 1
                """,
                (saved["pathway_id"],)
            ).fetchone()

            self.assertIsNotNone(step_row[0])
            self.assertIsNone(step_row[1])
            self.assertEqual(step_row[2], "")

    # --------------------------------------------------
    # 3. Catalogue reimport preserves saved pathways
    # --------------------------------------------------

    def test_catalogue_reimport_preserves_pathway(self):

        saved = self.save_test_pathway()
        pathway_id = saved["pathway_id"]

        # Simulate Samer updating the dataset.
        with patch.object(
            import_data,
            "DATABASE_PATH",
            self.test_db
        ):
            import_data.import_opportunities()

        # Retrieve the pathway after reimporting.
        retrieved = get_saved_pathway(
            pathway_id,
            database_path=self.test_db
        )

        self.assertIsNotNone(retrieved)
        self.assertEqual(
            retrieved["pathway_id"],
            pathway_id
        )
        self.assertEqual(len(retrieved["steps"]), 5)

        self.assertFalse(retrieved["approved"])
        self.assertFalse(retrieved["can_export"])

    # --------------------------------------------------
    # 4. Failed saves must roll back completely
    # --------------------------------------------------

    def test_failed_save_rolls_back_everything(self):

        # Force duplicate step IDs.
        # The second step insertion must fail.
        with patch(
            "pathway_storage.uuid4",
            return_value="duplicate-id"
        ):

            with self.assertRaises(
                sqlite3.IntegrityError
            ):
                self.save_test_pathway()

        # Check that the failed transaction left
        # no partially saved pathway or steps.
        with closing(sqlite3.connect(self.test_db)) as connection:

            pathway_count = connection.execute(
                "SELECT COUNT(*) FROM pathways"
            ).fetchone()[0]

            step_count = connection.execute(
                "SELECT COUNT(*) FROM pathway_steps"
            ).fetchone()[0]

        self.assertEqual(pathway_count, 0)
        self.assertEqual(step_count, 0)

    # --------------------------------------------------
    # 5. Unknown pathway IDs return None
    # --------------------------------------------------

    def test_missing_pathway_returns_none(self):

        retrieved = get_saved_pathway(
            "does-not-exist",
            database_path=self.test_db
        )

        self.assertIsNone(retrieved)

    # --------------------------------------------------
    # 6. Missing database cannot be created accidentally
    # --------------------------------------------------

    def test_missing_database_is_not_created(self):

        missing_db = (
            Path(self.temp_dir.name)
            / "missing.db"
        )

        with self.assertRaises(FileNotFoundError):

            get_saved_pathway(
                "unknown-pathway",
                database_path=missing_db
            )

        self.assertFalse(missing_db.exists())


    # --------------------------------------------------
    # STE-07: Pathway editing tests
    # --------------------------------------------------

    def test_edit_generated_step_preserves_source(self):

        saved = self.save_test_pathway()

        pathway_id = saved["pathway_id"]
        first_step = saved["steps"][0]

        original_source = first_step["source_step"]

        updated = edit_saved_step(
            pathway_id=pathway_id,
            step_id=first_step["id"],
            expected_revision=1,
            title="Check my eligibility documents",
            student_note="Contact the provider for clarification.",
            included=False,
            database_path=self.test_db
        )

        self.assertEqual(updated["revision"], 2)
        self.assertFalse(updated["approved"])
        self.assertFalse(updated["can_export"])

        edited_step = updated["steps"][0]

        self.assertEqual(
            edited_step["title"],
            "Check my eligibility documents"
        )

        self.assertEqual(
            edited_step["student_note"],
            "Contact the provider for clarification."
        )

        self.assertFalse(edited_step["included"])

        # Published source information must be unchanged.
        self.assertEqual(
            edited_step["source_step"],
            original_source
        )

        self.assertEqual(
            edited_step["source_step_id"],
            "requirement:OPP-005-E1"
        )

    def test_edit_rejects_stale_revision(self):

        saved = self.save_test_pathway()

        pathway_id = saved["pathway_id"]
        step_id = saved["steps"][0]["id"]

        # First edit succeeds and advances revision to 2.
        edit_saved_step(
            pathway_id=pathway_id,
            step_id=step_id,
            expected_revision=1,
            title="First edit",
            student_note="Saved change",
            included=True,
            database_path=self.test_db
        )

        # A second edit using old revision 1 must fail.
        with self.assertRaises(PathwayRevisionConflict):

            edit_saved_step(
                pathway_id=pathway_id,
                step_id=step_id,
                expected_revision=1,
                title="Outdated edit",
                student_note="Should not be saved",
                included=False,
                database_path=self.test_db
            )

        retrieved = get_saved_pathway(
            pathway_id,
            database_path=self.test_db
        )

        self.assertEqual(retrieved["revision"], 2)

        self.assertEqual(
            retrieved["steps"][0]["title"],
            "First edit"
        )

        self.assertTrue(
            retrieved["steps"][0]["included"]
        )

    def test_edit_invalidates_existing_approval(self):

        saved = self.save_test_pathway()

        pathway_id = saved["pathway_id"]
        step_id = saved["steps"][0]["id"]

        # Simulate an already approved revision 1.
        # The real approval function is not implemented yet.
        with closing(
            sqlite3.connect(self.test_db)
        ) as connection:

            connection.execute(
                """
                UPDATE pathways
                SET approved_revision = 1,
                    approved_at = ?
                WHERE id = ?
                """,
                (
                    "2026-11-28T10:00:00+00:00",
                    pathway_id
                )
            )

            connection.commit()

        before_edit = get_saved_pathway(
            pathway_id,
            database_path=self.test_db
        )

        self.assertTrue(before_edit["approved"])
        self.assertTrue(before_edit["can_export"])

        # Editing must revoke that approval.
        updated = edit_saved_step(
            pathway_id=pathway_id,
            step_id=step_id,
            expected_revision=1,
            title="Updated after approval",
            student_note="Needs another review",
            included=True,
            database_path=self.test_db
        )

        self.assertEqual(updated["revision"], 2)
        self.assertIsNone(updated["approved_revision"])
        self.assertEqual(updated["status"], "draft")

        self.assertFalse(updated["approved"])
        self.assertFalse(updated["can_export"])

    def test_edit_rejects_invalid_input(self):

        saved = self.save_test_pathway()

        pathway_id = saved["pathway_id"]
        step_id = saved["steps"][0]["id"]

        invalid_changes = [
            {
                "expected_revision": 0,
                "title": "Valid title",
                "student_note": "",
                "included": True
            },
            {
                "expected_revision": 1,
                "title": "   ",
                "student_note": "",
                "included": True
            },
            {
                "expected_revision": 1,
                "title": "Valid title",
                "student_note": "x" * 2001,
                "included": True
            },
            {
                "expected_revision": 1,
                "title": "Valid title",
                "student_note": "",
                "included": "yes"
            }
        ]

        for changes in invalid_changes:

            with self.subTest(changes=changes):

                with self.assertRaises(ValueError):

                    edit_saved_step(
                        pathway_id=pathway_id,
                        step_id=step_id,
                        database_path=self.test_db,
                        **changes
                    )

        retrieved = get_saved_pathway(
            pathway_id,
            database_path=self.test_db
        )

        # No invalid edit should change the revision.
        self.assertEqual(retrieved["revision"], 1)

    def test_edit_rejects_unknown_pathway_or_step(self):

        saved = self.save_test_pathway()

        pathway_id = saved["pathway_id"]
        step_id = saved["steps"][0]["id"]

        with self.assertRaises(LookupError):

            edit_saved_step(
                pathway_id="nonexistent-pathway",
                step_id=step_id,
                expected_revision=1,
                title="Test",
                student_note="",
                included=True,
                database_path=self.test_db
            )

        with self.assertRaises(LookupError):

            edit_saved_step(
                pathway_id=pathway_id,
                step_id="nonexistent-step",
                expected_revision=1,
                title="Test",
                student_note="",
                included=True,
                database_path=self.test_db
            )

        retrieved = get_saved_pathway(
            pathway_id,
            database_path=self.test_db
        )

        self.assertEqual(retrieved["revision"], 1)

    def test_edit_cannot_modify_another_pathways_step(self):

        first = self.save_test_pathway()
        second = self.save_test_pathway()

        # Attempt to use pathway A with a step belonging
        # to pathway B.
        with self.assertRaises(LookupError):

            edit_saved_step(
                pathway_id=first["pathway_id"],
                step_id=second["steps"][0]["id"],
                expected_revision=1,
                title="Unauthorized cross-pathway edit",
                student_note="",
                included=True,
                database_path=self.test_db
            )

        first_after = get_saved_pathway(
            first["pathway_id"],
            database_path=self.test_db
        )

        second_after = get_saved_pathway(
            second["pathway_id"],
            database_path=self.test_db
        )

        self.assertEqual(first_after["revision"], 1)
        self.assertEqual(second_after["revision"], 1)

    # --------------------------------------------------
    # STE-07: Pathway approval tests
    # --------------------------------------------------

    def test_approval_requires_explicit_confirmation(self):

        saved = self.save_test_pathway()

        # Neither missing confirmation nor truthy
        # substitutes may approve a pathway.
        invalid_confirmations = [
            False,
            None,
            "true",
            1
        ]

        for confirmation in invalid_confirmations:

            with self.subTest(confirmation=confirmation):

                with self.assertRaises(ValueError):

                    approve_saved_pathway(
                        pathway_id=saved["pathway_id"],
                        expected_revision=1,
                        confirmed=confirmation,
                        database_path=self.test_db
                    )

        retrieved = get_saved_pathway(
            saved["pathway_id"],
            database_path=self.test_db
        )

        self.assertFalse(retrieved["approved"])
        self.assertFalse(retrieved["can_export"])
        self.assertIsNone(retrieved["approved_revision"])

    def test_successful_approval_records_current_revision(self):

        saved = self.save_test_pathway()

        approved = approve_saved_pathway(
            pathway_id=saved["pathway_id"],
            expected_revision=1,
            confirmed=True,
            database_path=self.test_db
        )

        self.assertEqual(approved["revision"], 1)
        self.assertEqual(approved["approved_revision"], 1)
        self.assertEqual(approved["status"], "approved")
        self.assertTrue(approved["approved"])
        self.assertTrue(approved["can_export"])

        # Confirm approval was stored in SQLite.
        with closing(
            sqlite3.connect(self.test_db)
        ) as connection:

            record = connection.execute(
                """
                SELECT approved_revision, approved_at
                FROM pathways
                WHERE id = ?
                """,
                (saved["pathway_id"],)
            ).fetchone()

        self.assertEqual(record[0], 1)
        self.assertIsNotNone(record[1])

    def test_approval_rejects_invalid_revision(self):

        saved = self.save_test_pathway()

        invalid_revisions = [
            0,
            -1,
            True,
            1.0,
            "1"
        ]

        for revision in invalid_revisions:

            with self.subTest(revision=revision):

                with self.assertRaises(ValueError):

                    approve_saved_pathway(
                        pathway_id=saved["pathway_id"],
                        expected_revision=revision,
                        confirmed=True,
                        database_path=self.test_db
                    )

        retrieved = get_saved_pathway(
            saved["pathway_id"],
            database_path=self.test_db
        )

        self.assertFalse(retrieved["approved"])

    def test_approval_rejects_stale_revision(self):

        saved = self.save_test_pathway()

        pathway_id = saved["pathway_id"]
        step_id = saved["steps"][0]["id"]

        # Student edits revision 1, creating revision 2.
        edited = edit_saved_step(
            pathway_id=pathway_id,
            step_id=step_id,
            expected_revision=1,
            title="My updated pathway action",
            student_note="Review this change.",
            included=True,
            database_path=self.test_db
        )

        self.assertEqual(edited["revision"], 2)

        # Approval based on revision 1 must fail.
        with self.assertRaises(PathwayRevisionConflict):

            approve_saved_pathway(
                pathway_id=pathway_id,
                expected_revision=1,
                confirmed=True,
                database_path=self.test_db
            )

        retrieved = get_saved_pathway(
            pathway_id,
            database_path=self.test_db
        )

        self.assertEqual(retrieved["revision"], 2)
        self.assertFalse(retrieved["approved"])
        self.assertFalse(retrieved["can_export"])

    def test_approval_rejects_pathway_with_no_included_steps(self):

        saved = self.save_test_pathway()

        # Simulate a draft where every action is excluded.
        with closing(
            sqlite3.connect(self.test_db)
        ) as connection:

            connection.execute(
                """
                UPDATE pathway_steps
                SET is_included = 0
                WHERE pathway_id = ?
                """,
                (saved["pathway_id"],)
            )

            connection.commit()

        with self.assertRaises(ValueError):

            approve_saved_pathway(
                pathway_id=saved["pathway_id"],
                expected_revision=1,
                confirmed=True,
                database_path=self.test_db
            )

        retrieved = get_saved_pathway(
            saved["pathway_id"],
            database_path=self.test_db
        )

        self.assertFalse(retrieved["approved"])
        self.assertFalse(retrieved["can_export"])

    def test_approval_rejects_unknown_pathway(self):

        with self.assertRaises(LookupError):

            approve_saved_pathway(
                pathway_id="nonexistent-pathway",
                expected_revision=1,
                confirmed=True,
                database_path=self.test_db
            )

    def test_editing_approved_pathway_requires_reapproval(self):

        saved = self.save_test_pathway()

        pathway_id = saved["pathway_id"]
        step_id = saved["steps"][0]["id"]

        # First approval succeeds.
        first_approval = approve_saved_pathway(
            pathway_id=pathway_id,
            expected_revision=1,
            confirmed=True,
            database_path=self.test_db
        )

        self.assertTrue(first_approval["approved"])

        # Editing invalidates the first approval.
        edited = edit_saved_step(
            pathway_id=pathway_id,
            step_id=step_id,
            expected_revision=1,
            title="Revised student action",
            student_note="Updated after approval.",
            included=True,
            database_path=self.test_db
        )

        self.assertEqual(edited["revision"], 2)
        self.assertIsNone(edited["approved_revision"])
        self.assertFalse(edited["approved"])
        self.assertFalse(edited["can_export"])

        # Student explicitly approves the new revision.
        second_approval = approve_saved_pathway(
            pathway_id=pathway_id,
            expected_revision=2,
            confirmed=True,
            database_path=self.test_db
        )

        self.assertEqual(second_approval["revision"], 2)
        self.assertEqual(second_approval["approved_revision"], 2)
        self.assertEqual(second_approval["status"], "approved")
        self.assertTrue(second_approval["approved"])
        self.assertTrue(second_approval["can_export"])

    # --------------------------------------------------
    # STE-07: Protected pathway export tests
    # --------------------------------------------------

    def test_export_blocks_unapproved_draft(self):

        saved = self.save_test_pathway()

        with self.assertRaises(PermissionError):
            export_approved_pathway(
                pathway_id=saved["pathway_id"],
                expected_revision=1,
                database_path=self.test_db
            )

        # Failed export must not approve the draft.
        retrieved = get_saved_pathway(
            saved["pathway_id"],
            database_path=self.test_db
        )

        self.assertFalse(retrieved["approved"])
        self.assertFalse(retrieved["can_export"])

    def test_export_succeeds_after_approval(self):

        saved = self.save_test_pathway()

        approve_saved_pathway(
            pathway_id=saved["pathway_id"],
            expected_revision=1,
            confirmed=True,
            database_path=self.test_db
        )

        exported = export_approved_pathway(
            pathway_id=saved["pathway_id"],
            expected_revision=1,
            database_path=self.test_db
        )

        self.assertEqual(
            exported["export_type"],
            "approved_pathway"
        )
        self.assertEqual(
            exported["pathway_id"],
            saved["pathway_id"]
        )
        self.assertEqual(
            exported["opportunity_id"],
            "OPP-005"
        )
        self.assertEqual(exported["revision"], 1)
        self.assertEqual(exported["approved_revision"], 1)
        self.assertEqual(exported["status"], "approved")

        self.assertIsNotNone(exported["approved_at"])
        self.assertEqual(len(exported["steps"]), 5)

        # The original opportunity is included
        # for source transparency.
        self.assertEqual(
            exported["source_snapshot"],
            self.opportunity
        )

    def test_export_rejects_stale_revision(self):

        saved = self.save_test_pathway()

        pathway_id = saved["pathway_id"]
        step_id = saved["steps"][0]["id"]

        # Change revision 1 into revision 2.
        edit_saved_step(
            pathway_id=pathway_id,
            step_id=step_id,
            expected_revision=1,
            title="Updated pathway action",
            student_note="Revision 2",
            included=True,
            database_path=self.test_db
        )

        # Exporting against the outdated revision
        # must fail before checking approval.
        with self.assertRaises(PathwayRevisionConflict):

            export_approved_pathway(
                pathway_id=pathway_id,
                expected_revision=1,
                database_path=self.test_db
            )

        retrieved = get_saved_pathway(
            pathway_id,
            database_path=self.test_db
        )

        self.assertEqual(retrieved["revision"], 2)

    def test_export_requires_reapproval_after_edit(self):

        saved = self.save_test_pathway()

        pathway_id = saved["pathway_id"]
        step_id = saved["steps"][0]["id"]

        # Approve the original draft.
        approve_saved_pathway(
            pathway_id=pathway_id,
            expected_revision=1,
            confirmed=True,
            database_path=self.test_db
        )

        # Revision 1 is exportable.
        original_export = export_approved_pathway(
            pathway_id=pathway_id,
            expected_revision=1,
            database_path=self.test_db
        )

        self.assertEqual(original_export["revision"], 1)

        # Editing invalidates approval.
        edit_saved_step(
            pathway_id=pathway_id,
            step_id=step_id,
            expected_revision=1,
            title="New action after approval",
            student_note="Requires another review",
            included=True,
            database_path=self.test_db
        )

        # Current revision 2 is not approved.
        with self.assertRaises(PermissionError):

            export_approved_pathway(
                pathway_id=pathway_id,
                expected_revision=2,
                database_path=self.test_db
            )

        # Explicitly approve revision 2.
        approve_saved_pathway(
            pathway_id=pathway_id,
            expected_revision=2,
            confirmed=True,
            database_path=self.test_db
        )

        # Export is permitted again.
        updated_export = export_approved_pathway(
            pathway_id=pathway_id,
            expected_revision=2,
            database_path=self.test_db
        )

        self.assertEqual(updated_export["revision"], 2)
        self.assertEqual(
            updated_export["approved_revision"],
            2
        )

    def test_export_excludes_disabled_steps(self):

        saved = self.save_test_pathway()

        pathway_id = saved["pathway_id"]
        first_step = saved["steps"][0]

        # Exclude one action from the pathway.
        edited = edit_saved_step(
            pathway_id=pathway_id,
            step_id=first_step["id"],
            expected_revision=1,
            title=first_step["title"],
            student_note="Exclude this action",
            included=False,
            database_path=self.test_db
        )

        self.assertEqual(edited["revision"], 2)

        approve_saved_pathway(
            pathway_id=pathway_id,
            expected_revision=2,
            confirmed=True,
            database_path=self.test_db
        )

        exported = export_approved_pathway(
            pathway_id=pathway_id,
            expected_revision=2,
            database_path=self.test_db
        )

        # Five original actions minus one excluded.
        self.assertEqual(len(exported["steps"]), 4)

        # Export positions should be sequential.
        self.assertEqual(
            [step["position"] for step in exported["steps"]],
            [1, 2, 3, 4]
        )

        # The excluded identity-review action
        # must not be exported as an active step.
        exported_source_ids = {
            step["original_source_step"]["step_id"]
            for step in exported["steps"]
            if step["original_source_step"] is not None
        }

        self.assertNotIn(
            "requirement:OPP-005-E1",
            exported_source_ids
        )

    def test_export_preserves_original_source_after_edit(self):

        saved = self.save_test_pathway()

        pathway_id = saved["pathway_id"]
        first_step = saved["steps"][0]

        original_source = first_step["source_step"]

        # Personalise the displayed action.
        edit_saved_step(
            pathway_id=pathway_id,
            step_id=first_step["id"],
            expected_revision=1,
            title="Contact UNE to discuss eligibility",
            student_note="Ask about the current cadetship round.",
            included=True,
            database_path=self.test_db
        )

        approve_saved_pathway(
            pathway_id=pathway_id,
            expected_revision=2,
            confirmed=True,
            database_path=self.test_db
        )

        exported = export_approved_pathway(
            pathway_id=pathway_id,
            expected_revision=2,
            database_path=self.test_db
        )

        exported_step = exported["steps"][0]

        # Student-edited content appears in export.
        self.assertEqual(
            exported_step["title"],
            "Contact UNE to discuss eligibility"
        )

        self.assertEqual(
            exported_step["student_note"],
            "Ask about the current cadetship round."
        )

        # Original requirement evidence is unchanged.
        self.assertEqual(
            exported_step["original_source_step"],
            original_source
        )

        self.assertEqual(
            exported_step["original_source_step"][
                "eligibility_status"
            ],
            "uncertain"
        )

    def test_export_rejects_invalid_revision_and_unknown_id(self):

        saved = self.save_test_pathway()

        invalid_revisions = [
            0,
            -1,
            True,
            1.0,
            "1"
        ]

        for revision in invalid_revisions:

            with self.subTest(revision=revision):

                with self.assertRaises(ValueError):

                    export_approved_pathway(
                        pathway_id=saved["pathway_id"],
                        expected_revision=revision,
                        database_path=self.test_db
                    )

        with self.assertRaises(LookupError):

            export_approved_pathway(
                pathway_id="nonexistent-pathway",
                expected_revision=1,
                database_path=self.test_db
            )

    def test_export_rejects_no_included_actions(self):

        saved = self.save_test_pathway()

        pathway_id = saved["pathway_id"]

        # Approve a valid initial pathway.
        approve_saved_pathway(
            pathway_id=pathway_id,
            expected_revision=1,
            confirmed=True,
            database_path=self.test_db
        )

        # Simulate an unexpected direct database change
        # that removes all included actions.
        # Export should fail even if an approval
        # record still exists.
        with closing(
            sqlite3.connect(self.test_db)
        ) as connection:

            connection.execute(
                """
                UPDATE pathway_steps
                SET is_included = 0
                WHERE pathway_id = ?
                """,
                (pathway_id,)
            )

            connection.commit()

        with self.assertRaises(PermissionError):

            export_approved_pathway(
                pathway_id=pathway_id,
                expected_revision=1,
                database_path=self.test_db
            )

    # --------------------------------------------------
    # STE-07: Student-created action tests
    # --------------------------------------------------

    def test_add_student_step_preserves_source_separation(self):

        saved = self.save_test_pathway()

        original_sources = [
            step["source_step"]
            for step in saved["steps"]
        ]

        updated = add_student_step(
            pathway_id=saved["pathway_id"],
            expected_revision=1,
            title="  Attend a career workshop  ",
            student_note="Register through my university.",
            included=True,
            database_path=self.test_db
        )

        self.assertEqual(updated["revision"], 2)
        self.assertEqual(len(updated["steps"]), 6)
        self.assertFalse(updated["approved"])
        self.assertFalse(updated["can_export"])

        new_step = updated["steps"][-1]

        self.assertEqual(new_step["position"], 6)
        self.assertEqual(new_step["origin"], "student")
        self.assertEqual(
            new_step["title"],
            "Attend a career workshop"
        )
        self.assertEqual(
            new_step["student_note"],
            "Register through my university."
        )
        self.assertTrue(new_step["included"])

        # Student actions must not masquerade
        # as official generated requirements.
        self.assertIsNone(new_step["source_step_id"])
        self.assertIsNone(new_step["source_step"])

        # The five generated steps remain unchanged.
        self.assertEqual(
            [
                step["source_step"]
                for step in updated["steps"][:5]
            ],
            original_sources
        )

    def test_adding_step_invalidates_approval(self):

        saved = self.save_test_pathway()
        pathway_id = saved["pathway_id"]

        approved = approve_saved_pathway(
            pathway_id=pathway_id,
            expected_revision=1,
            confirmed=True,
            database_path=self.test_db
        )

        self.assertTrue(approved["can_export"])

        # Adding an action creates revision 2.
        updated = add_student_step(
            pathway_id=pathway_id,
            expected_revision=1,
            title="Book an appointment with career services",
            student_note="Discuss internship preparation.",
            database_path=self.test_db
        )

        self.assertEqual(updated["revision"], 2)
        self.assertIsNone(updated["approved_revision"])
        self.assertFalse(updated["approved"])
        self.assertFalse(updated["can_export"])

        # Export is blocked until revision 2 is approved.
        with self.assertRaises(PermissionError):
            export_approved_pathway(
                pathway_id=pathway_id,
                expected_revision=2,
                database_path=self.test_db
            )

        approve_saved_pathway(
            pathway_id=pathway_id,
            expected_revision=2,
            confirmed=True,
            database_path=self.test_db
        )

        exported = export_approved_pathway(
            pathway_id=pathway_id,
            expected_revision=2,
            database_path=self.test_db
        )

        self.assertEqual(len(exported["steps"]), 6)
        self.assertEqual(
            exported["steps"][-1]["origin"],
            "student"
        )
        self.assertIsNone(
            exported["steps"][-1]["original_source_step"]
        )

    def test_add_student_step_rejects_stale_revision(self):

        saved = self.save_test_pathway()
        pathway_id = saved["pathway_id"]

        add_student_step(
            pathway_id=pathway_id,
            expected_revision=1,
            title="First custom action",
            database_path=self.test_db
        )

        # Revision 1 is no longer current.
        with self.assertRaises(PathwayRevisionConflict):
            add_student_step(
                pathway_id=pathway_id,
                expected_revision=1,
                title="Outdated custom action",
                database_path=self.test_db
            )

        retrieved = get_saved_pathway(
            pathway_id,
            database_path=self.test_db
        )

        self.assertEqual(retrieved["revision"], 2)
        self.assertEqual(len(retrieved["steps"]), 6)
        self.assertEqual(
            retrieved["steps"][-1]["title"],
            "First custom action"
        )

    def test_add_student_step_rejects_unknown_pathway(self):

        with self.assertRaises(LookupError):
            add_student_step(
                pathway_id="nonexistent-pathway",
                expected_revision=1,
                title="Should not be saved",
                database_path=self.test_db
            )

        with closing(
            sqlite3.connect(self.test_db)
        ) as connection:

            count = connection.execute(
                "SELECT COUNT(*) FROM pathway_steps"
            ).fetchone()[0]

        self.assertEqual(count, 0)

    def test_add_student_step_rejects_invalid_input(self):

        saved = self.save_test_pathway()

        valid = {
            "expected_revision": 1,
            "title": "Valid action",
            "student_note": "",
            "included": True
        }

        invalid_changes = [
            {"expected_revision": 0},
            {"expected_revision": True},
            {"expected_revision": "1"},
            {"title": ""},
            {"title": "   "},
            {"title": "x" * 201},
            {"title": None},
            {"student_note": None},
            {"student_note": "x" * 2001},
            {"included": "yes"},
            {"included": 1}
        ]

        for change in invalid_changes:

            with self.subTest(change=change):

                arguments = {**valid, **change}

                with self.assertRaises(ValueError):
                    add_student_step(
                        pathway_id=saved["pathway_id"],
                        database_path=self.test_db,
                        **arguments
                    )

        retrieved = get_saved_pathway(
            saved["pathway_id"],
            database_path=self.test_db
        )

        self.assertEqual(retrieved["revision"], 1)
        self.assertEqual(len(retrieved["steps"]), 5)

    def test_failed_student_step_addition_rolls_back(self):

        saved = self.save_test_pathway()

        pathway_id = saved["pathway_id"]
        existing_step_id = saved["steps"][0]["id"]

        # Force a primary-key collision.
        with patch(
            "pathway_storage.uuid4",
            return_value=existing_step_id
        ):

            with self.assertRaises(sqlite3.IntegrityError):
                add_student_step(
                    pathway_id=pathway_id,
                    expected_revision=1,
                    title="Duplicate ID test",
                    database_path=self.test_db
                )

        retrieved = get_saved_pathway(
            pathway_id,
            database_path=self.test_db
        )

        # No partial action or revision change.
        self.assertEqual(retrieved["revision"], 1)
        self.assertEqual(len(retrieved["steps"]), 5)
        self.assertFalse(retrieved["approved"])

    def test_student_created_step_can_be_edited(self):

        saved = self.save_test_pathway()

        pathway_id = saved["pathway_id"]

        added = add_student_step(
            pathway_id=pathway_id,
            expected_revision=1,
            title="Original custom action",
            database_path=self.test_db
        )

        student_step_id = added["steps"][-1]["id"]

        # Existing editing function must support
        # student-created actions as well.
        edited = edit_saved_step(
            pathway_id=pathway_id,
            step_id=student_step_id,
            expected_revision=2,
            title="Updated custom action",
            student_note="My personal reminder.",
            included=False,
            database_path=self.test_db
        )

        self.assertEqual(edited["revision"], 3)

        student_step = edited["steps"][-1]

        self.assertEqual(
            student_step["title"],
            "Updated custom action"
        )
        self.assertEqual(
            student_step["student_note"],
            "My personal reminder."
        )
        self.assertFalse(student_step["included"])
        self.assertEqual(student_step["origin"], "student")
        self.assertIsNone(student_step["source_step"])

        self.assertFalse(edited["can_export"])

    def test_excluded_student_step_is_not_exported(self):

        saved = self.save_test_pathway()

        pathway_id = saved["pathway_id"]

        updated = add_student_step(
            pathway_id=pathway_id,
            expected_revision=1,
            title="Optional personal action",
            included=False,
            database_path=self.test_db
        )

        # The excluded action remains saved.
        self.assertEqual(len(updated["steps"]), 6)
        self.assertFalse(updated["steps"][-1]["included"])

        approve_saved_pathway(
            pathway_id=pathway_id,
            expected_revision=2,
            confirmed=True,
            database_path=self.test_db
        )

        exported = export_approved_pathway(
            pathway_id=pathway_id,
            expected_revision=2,
            database_path=self.test_db
        )

        # Only the original five included actions
        # should appear in this export.
        self.assertEqual(len(exported["steps"]), 5)

        self.assertTrue(
            all(
                step["origin"] == "generated"
                for step in exported["steps"]
            )
        )

    # --------------------------------------------------
    # STE-07: Pathway reordering tests
    # --------------------------------------------------

    def test_reorder_generated_and_student_steps(self):

        saved = self.save_test_pathway()

        pathway_id = saved["pathway_id"]

        # Add a student-created action as the sixth step.
        added = add_student_step(
            pathway_id=pathway_id,
            expected_revision=1,
            title="Attend a career workshop",
            database_path=self.test_db
        )

        original_steps = added["steps"]

        original_sources = {
            step["id"]: step["source_step"]
            for step in original_steps
        }

        original_ids = [
            step["id"]
            for step in original_steps
        ]

        # Move the student action to the beginning.
        new_order = [
            original_ids[-1],
            *original_ids[:-1]
        ]

        reordered = reorder_saved_steps(
            pathway_id=pathway_id,
            expected_revision=2,
            step_ids=new_order,
            database_path=self.test_db
        )

        self.assertEqual(reordered["revision"], 3)
        self.assertFalse(reordered["approved"])
        self.assertFalse(reordered["can_export"])

        self.assertEqual(
            [step["id"] for step in reordered["steps"]],
            new_order
        )

        self.assertEqual(
            [step["position"] for step in reordered["steps"]],
            [1, 2, 3, 4, 5, 6]
        )

        # Student-created action now appears first.
        self.assertEqual(
            reordered["steps"][0]["origin"],
            "student"
        )

        # Reordering must not alter source evidence.
        for step in reordered["steps"]:

            self.assertEqual(
                step["source_step"],
                original_sources[step["id"]]
            )

    def test_unchanged_order_preserves_approval(self):

        saved = self.save_test_pathway()

        pathway_id = saved["pathway_id"]

        approved = approve_saved_pathway(
            pathway_id=pathway_id,
            expected_revision=1,
            confirmed=True,
            database_path=self.test_db
        )

        original_ids = [
            step["id"]
            for step in approved["steps"]
        ]

        # Submit the exact same order.
        unchanged = reorder_saved_steps(
            pathway_id=pathway_id,
            expected_revision=1,
            step_ids=original_ids,
            database_path=self.test_db
        )

        # No actual change means no revision increase.
        self.assertEqual(unchanged["revision"], 1)

        self.assertEqual(
            unchanged["approved_revision"],
            1
        )

        self.assertTrue(unchanged["approved"])
        self.assertTrue(unchanged["can_export"])

        # Previously approved export still works.
        exported = export_approved_pathway(
            pathway_id=pathway_id,
            expected_revision=1,
            database_path=self.test_db
        )

        self.assertEqual(exported["revision"], 1)

    def test_reordering_approved_pathway_requires_reapproval(self):

        saved = self.save_test_pathway()

        pathway_id = saved["pathway_id"]

        approve_saved_pathway(
            pathway_id=pathway_id,
            expected_revision=1,
            confirmed=True,
            database_path=self.test_db
        )

        # Reverse the five generated actions.
        new_order = [
            step["id"]
            for step in reversed(saved["steps"])
        ]

        expected_titles = [
            step["title"]
            for step in reversed(saved["steps"])
        ]

        reordered = reorder_saved_steps(
            pathway_id=pathway_id,
            expected_revision=1,
            step_ids=new_order,
            database_path=self.test_db
        )

        self.assertEqual(reordered["revision"], 2)
        self.assertIsNone(reordered["approved_revision"])
        self.assertFalse(reordered["approved"])
        self.assertFalse(reordered["can_export"])

        # Export must be blocked after changing order.
        with self.assertRaises(PermissionError):

            export_approved_pathway(
                pathway_id=pathway_id,
                expected_revision=2,
                database_path=self.test_db
            )

        # Approve the reordered revision.
        approve_saved_pathway(
            pathway_id=pathway_id,
            expected_revision=2,
            confirmed=True,
            database_path=self.test_db
        )

        exported = export_approved_pathway(
            pathway_id=pathway_id,
            expected_revision=2,
            database_path=self.test_db
        )

        self.assertEqual(
            [step["title"] for step in exported["steps"]],
            expected_titles
        )

        self.assertEqual(
            [step["position"] for step in exported["steps"]],
            [1, 2, 3, 4, 5]
        )

    def test_reorder_rejects_invalid_step_lists(self):

        saved = self.save_test_pathway()

        pathway_id = saved["pathway_id"]

        original_ids = [
            step["id"]
            for step in saved["steps"]
        ]

        invalid_orders = [
            [],
            tuple(original_ids),
            [original_ids[0], original_ids[0]],
            [""],
            [" invalid-step-id "],
            [None],
        ]

        for invalid_order in invalid_orders:

            with self.subTest(order=invalid_order):

                with self.assertRaises(ValueError):

                    reorder_saved_steps(
                        pathway_id=pathway_id,
                        expected_revision=1,
                        step_ids=invalid_order,
                        database_path=self.test_db
                    )

        retrieved = get_saved_pathway(
            pathway_id,
            database_path=self.test_db
        )

        self.assertEqual(retrieved["revision"], 1)

        self.assertEqual(
            [step["id"] for step in retrieved["steps"]],
            original_ids
        )

    def test_reorder_rejects_missing_and_foreign_steps(self):

        first = self.save_test_pathway()
        second = self.save_test_pathway()

        first_ids = [
            step["id"]
            for step in first["steps"]
        ]

        foreign_step_id = second["steps"][0]["id"]

        # Missing one step.
        with self.assertRaises(ValueError):

            reorder_saved_steps(
                pathway_id=first["pathway_id"],
                expected_revision=1,
                step_ids=first_ids[:-1],
                database_path=self.test_db
            )

        # Replace a valid step with a step from
        # another pathway.
        with self.assertRaises(ValueError):

            reorder_saved_steps(
                pathway_id=first["pathway_id"],
                expected_revision=1,
                step_ids=[
                    *first_ids[:-1],
                    foreign_step_id
                ],
                database_path=self.test_db
            )

        first_after = get_saved_pathway(
            first["pathway_id"],
            database_path=self.test_db
        )

        second_after = get_saved_pathway(
            second["pathway_id"],
            database_path=self.test_db
        )

        self.assertEqual(first_after["revision"], 1)
        self.assertEqual(second_after["revision"], 1)

        self.assertEqual(
            [step["id"] for step in first_after["steps"]],
            first_ids
        )

    def test_reorder_rejects_stale_revision(self):

        saved = self.save_test_pathway()

        pathway_id = saved["pathway_id"]

        # First edit creates revision 2.
        edited = edit_saved_step(
            pathway_id=pathway_id,
            step_id=saved["steps"][0]["id"],
            expected_revision=1,
            title="Updated first action",
            student_note="",
            included=True,
            database_path=self.test_db
        )

        self.assertEqual(edited["revision"], 2)

        original_ids = [
            step["id"]
            for step in saved["steps"]
        ]

        with self.assertRaises(PathwayRevisionConflict):

            reorder_saved_steps(
                pathway_id=pathway_id,
                expected_revision=1,
                step_ids=list(reversed(original_ids)),
                database_path=self.test_db
            )

        retrieved = get_saved_pathway(
            pathway_id,
            database_path=self.test_db
        )

        self.assertEqual(retrieved["revision"], 2)

        self.assertEqual(
            [step["id"] for step in retrieved["steps"]],
            original_ids
        )

    def test_reorder_rejects_unknown_pathway(self):

        saved = self.save_test_pathway()

        step_ids = [
            step["id"]
            for step in saved["steps"]
        ]

        with self.assertRaises(LookupError):

            reorder_saved_steps(
                pathway_id="nonexistent-pathway",
                expected_revision=1,
                step_ids=step_ids,
                database_path=self.test_db
            )

    def test_failed_reorder_rolls_back_positions_and_approval(self):

        saved = self.save_test_pathway()

        pathway_id = saved["pathway_id"]

        approved = approve_saved_pathway(
            pathway_id=pathway_id,
            expected_revision=1,
            confirmed=True,
            database_path=self.test_db
        )

        original_ids = [
            step["id"]
            for step in approved["steps"]
        ]

        # Create a temporary SQLite trigger that
        # deliberately fails during phase 2.
        with closing(
            sqlite3.connect(self.test_db)
        ) as connection:

            connection.executescript("""
                CREATE TRIGGER reject_position_two
                BEFORE UPDATE OF position
                ON pathway_steps
                WHEN NEW.position = 2
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'Simulated reorder failure'
                    );
                END;
            """)

            connection.commit()

        # Reordering begins but must roll back
        # when the trigger rejects position 2.
        with self.assertRaises(sqlite3.IntegrityError):

            reorder_saved_steps(
                pathway_id=pathway_id,
                expected_revision=1,
                step_ids=list(reversed(original_ids)),
                database_path=self.test_db
            )

        retrieved = get_saved_pathway(
            pathway_id,
            database_path=self.test_db
        )

        # No partial changes should survive.
        self.assertEqual(retrieved["revision"], 1)

        self.assertEqual(
            [step["id"] for step in retrieved["steps"]],
            original_ids
        )

        self.assertEqual(
            [step["position"] for step in retrieved["steps"]],
            [1, 2, 3, 4, 5]
        )

        # A failed reorder must not revoke approval.
        self.assertTrue(retrieved["approved"])
        self.assertTrue(retrieved["can_export"])

if __name__ == "__main__":
    unittest.main()
