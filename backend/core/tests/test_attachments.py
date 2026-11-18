"""Files stay private across staging, domain binding and access revocation."""

import base64
import io
import tempfile
import uuid
import zipfile
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import transaction
from django.test import override_settings
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from core.attachments import (
    attachment_data, authorized_attachment, bind_attachments, private_path,
    stage_upload, validate_upload,
)
from core.models import Attachment, AuditEvent, Project, ProjectMembership, ProjectRevision, WorkItem
from core.tests.base import OnecsTestCase


BASE = "/api/v1/attachments/"
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jPwoAAAAASUVORK5CYII=")


@override_settings(ONECS_UPLOAD_ALLOW_UNSCANNED=True, ONECS_ENV="test", ONECS_UPLOAD_SCANNER_COMMAND="")
class AttachmentTests(OnecsTestCase):
    def setUp(self):
        super().setUp()
        self.directory = tempfile.TemporaryDirectory(prefix="onecs-upload-test-")
        self.addCleanup(self.directory.cleanup)
        self.storage_override = override_settings(ONECS_UPLOAD_ROOT=self.directory.name)
        self.storage_override.enable()
        self.addCleanup(self.storage_override.disable)

    def file(self, name="notes.txt", content=b"Authorized synthetic notes", mime="text/plain"):
        return SimpleUploadedFile(name, content, content_type=mime)

    def upload(self, actor=None, **kwargs):
        return stage_upload(actor or self.unit_head, self.file(**kwargs))

    def work(self):
        return WorkItem.objects.create(
            title="Synthetic task", owner_org=self.team, assigned_to=self.employee,
            created_by=self.unit_head, formal=True,
        )

    def bind(self, item=None, work=None):
        item, work = item or self.upload(), work or self.work()
        bind_attachments(self.unit_head, "work", work, [str(item.pk)])
        item.refresh_from_db()
        return item, work

    def test_login_is_required_for_upload_list_and_download(self):
        item = self.upload()
        for response in (
            self.client.get(BASE),
            self.client.get(f"{BASE}{item.pk}/download/"),
            self.client.post(BASE, {"file": self.file()}, format="multipart"),
        ):
            self.assertIn(response.status_code, (401, 403))

    def test_upload_and_download_use_private_storage_without_exposing_path(self):
        response = self.as_user(self.unit_head).post(BASE, {"file": self.file()}, format="multipart")
        self.assertEqual(response.status_code, 201, response.content)
        data = response.json()
        self.assertEqual(data["scan_status"], "unscanned")
        self.assertNotIn("storage_key", data)
        item = Attachment.objects.get(pk=data["id"])
        self.assertTrue(private_path(item.storage_key).exists())
        self.assertEqual(private_path(item.storage_key).stat().st_mode & 0o777, 0o600)
        response = self.client.get(f"{BASE}{item.pk}/download/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), b"Authorized synthetic notes")
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertIn("attachment", response["Content-Disposition"])

    def test_other_user_cannot_see_download_claim_or_delete_staged_file(self):
        item, work = self.upload(), self.work()
        self.assertEqual(self.as_user(self.employee).get(BASE).json()["results"], [])
        self.assertEqual(self.client.get(f"{BASE}{item.pk}/download/").status_code, 404)
        self.assertEqual(self.client.delete(f"{BASE}{item.pk}/").status_code, 404)
        with self.assertRaises(ValidationError):
            bind_attachments(self.employee, "work", work, [str(item.pk)])
        item.refresh_from_db()
        self.assertIsNone(item.resource_id)

    def test_upload_retry_is_one_file_and_different_payload_conflicts(self):
        key = str(uuid.uuid4())
        client = self.as_user(self.unit_head)
        first = client.post(BASE, {"file": self.file()}, format="multipart", HTTP_X_REQUEST_ID=key)
        second = client.post(BASE, {"file": self.file()}, format="multipart", HTTP_X_REQUEST_ID=key)
        changed = client.post(BASE, {"file": self.file(content=b"Changed")}, format="multipart", HTTP_X_REQUEST_ID=key)
        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(second.status_code, 201, second.content)
        self.assertEqual(first.json()["id"], second.json()["id"])
        self.assertEqual(changed.status_code, 409, changed.content)
        self.assertEqual(Attachment.objects.count(), 1)
        self.assertEqual(len(list(Path(self.directory.name).glob("*/*"))), 1)

    def test_successful_binding_revokes_staging_ownership_and_cannot_rebind(self):
        item, work = self.bind()
        other = self.work()
        with self.assertRaises(ValidationError):
            bind_attachments(self.unit_head, "work", other, [str(item.pk)])
        response = self.as_user(self.unit_head).delete(f"{BASE}{item.pk}/")
        self.assertEqual(response.status_code, 404)
        rows = self.as_user(self.employee).get(BASE, {"resource_type": "work", "resource_id": str(work.pk)})
        self.assertEqual(rows.status_code, 200, rows.content)
        self.assertEqual(rows.json()["results"][0]["id"], str(item.pk))
        self.assertEqual(self.as_user(self.outsider).get(f"{BASE}{item.pk}/download/").status_code, 404)

    def test_bound_file_requires_current_role_even_for_original_uploader(self):
        item, work = self.bind()
        self.unit_head.role_grants.filter(role="UNIT_HEAD").update(active=False)
        with self.assertRaises(NotFound):
            authorized_attachment(self.unit_head, item.pk)
        response = self.as_user(self.unit_head).get(BASE, {"resource_type": "work", "resource_id": str(work.pk)})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.client.get(f"{BASE}{item.pk}/download/").status_code, 404)

    def test_stale_user_object_does_not_survive_account_deactivation(self):
        item = self.upload()
        type(self.unit_head).objects.filter(pk=self.unit_head.pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            authorized_attachment(self.unit_head, item.pk)

    def test_binding_has_domain_policy_and_transactional_audit_rollback(self):
        item, work = self.upload(), self.work()
        with self.assertRaises(NotFound):
            bind_attachments(self.other_head, "work", work, [str(item.pk)])
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                bind_attachments(self.unit_head, "work", work, [str(item.pk)])
                raise RuntimeError("Synthetic domain failure")
        item.refresh_from_db()
        self.assertIsNone(item.resource_id)
        self.assertFalse(AuditEvent.objects.filter(action="attachment.bound", object_id=str(item.pk)).exists())
        self.assertTrue(private_path(item.storage_key).exists())

    def test_binding_rejects_duplicates_invalid_ids_and_more_than_five_files(self):
        item, work = self.upload(), self.work()
        for ids in ([str(item.pk)] * 2, [str(uuid.uuid4())], ["invalid"], "not-a-list", [str(uuid.uuid4())] * 6):
            with self.subTest(ids=ids), self.assertRaises(ValidationError):
                bind_attachments(self.unit_head, "work", work, ids)

    def test_binding_cannot_exceed_record_limit_across_calls(self):
        work = self.work()
        items = [self.upload() for _ in range(6)]
        bind_attachments(self.unit_head, "work", work, [str(item.pk) for item in items[:5]])
        with self.assertRaises(ValidationError):
            bind_attachments(self.unit_head, "work", work, [str(items[-1].pk)])

    @override_settings(ONECS_UPLOAD_ALLOW_UNSCANNED=False)
    def test_missing_scanner_keeps_upload_in_quarantine_but_can_bind(self):
        item, work = self.bind()
        self.assertEqual(item.status, "PENDING_SCAN")
        response = self.as_user(self.employee).get(f"{BASE}{item.pk}/download/")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(item.resource_id, work.pk)

    def test_local_unscanned_upload_cannot_download_when_override_is_removed(self):
        item = self.upload()
        self.assertEqual(item.scan_status, "unscanned")
        with override_settings(ONECS_UPLOAD_ALLOW_UNSCANNED=False):
            self.assertEqual(self.as_user(self.unit_head).get(f"{BASE}{item.pk}/download/").status_code, 400)

    @override_settings(ONECS_ENV="production", DEBUG=True, ONECS_UPLOAD_ALLOW_UNSCANNED=True)
    def test_production_never_accepts_development_unscanned_override(self):
        self.assertEqual(self.upload().status, "PENDING_SCAN")

    @override_settings(ONECS_UPLOAD_SCANNER_COMMAND="scanner --quiet")
    def test_scanner_clean_infected_and_error_results_are_distinct(self):
        for returncode, expected in ((0, ("READY", "clean")), (1, ("REJECTED", "infected")), (2, ("PENDING_SCAN", "error"))):
            with self.subTest(returncode=returncode), patch("core.attachments.subprocess.run", return_value=SimpleNamespace(returncode=returncode)) as scanner:
                item = self.upload()
                self.assertEqual((item.status, item.scan_status), expected)
                self.assertIsInstance(scanner.call_args.args[0], list)
                self.assertEqual(scanner.call_args.args[0][:2], ["scanner", "--quiet"])
        infected = Attachment.objects.get(scan_status="infected")
        with self.assertRaises(ValidationError):
            bind_attachments(self.unit_head, "work", self.work(), [str(infected.pk)])

    @override_settings(ONECS_UPLOAD_SCANNER_COMMAND="missing-scanner")
    def test_scanner_failure_does_not_mark_file_clean(self):
        with patch("core.attachments.subprocess.run", side_effect=OSError("Synthetic error")):
            item = self.upload()
        self.assertEqual((item.status, item.scan_status), ("PENDING_SCAN", "error"))

    def test_private_project_draft_cannot_be_read_by_its_pm_before_submit(self):
        project = Project.objects.create(title="Private draft", created_by=self.employee, owner_org=self.team, appointment=self.appointment)
        item = self.upload(actor=self.employee)
        bind_attachments(self.employee, "project", project, [str(item.pk)])
        with self.assertRaises(NotFound):
            authorized_attachment(self.pm, item.pk)
        project.status = "SUBMITTED"
        project.save()
        self.assertEqual(authorized_attachment(self.pm, item.pk).pk, item.pk)

    def test_project_summary_and_resource_manager_cannot_read_project_or_task_files(self):
        project = Project.objects.create(title="Restricted delivery", created_by=self.employee, owner_org=self.team, appointment=self.appointment, status="PLANNED", published_revision=1)
        project.audience.add(self.team)
        ProjectRevision.objects.create(project=project, number=1, author=self.employee, content={"title": "Shared summary"})
        ProjectMembership.objects.create(project=project, user=self.employee)
        project_file = self.upload(actor=self.pm)
        bind_attachments(self.pm, "project", project, [str(project_file.pk)])
        task = WorkItem.objects.create(title="Restricted task", created_by=self.pm, assigned_to=self.employee, owner_org=self.team, context="PROJECT_TASK", project=project)
        task_file = self.upload(actor=self.pm)
        bind_attachments(self.pm, "work", task, [str(task_file.pk)])
        for item in (project_file, task_file):
            with self.subTest(item=item.pk), self.assertRaises(NotFound):
                authorized_attachment(self.unit_head, item.pk)
            self.assertEqual(authorized_attachment(self.employee, item.pk).pk, item.pk)
        project.memberships.filter(user=self.employee).update(active=False)
        with self.assertRaises(NotFound):
            authorized_attachment(self.employee, project_file.pk)

    def test_failed_storage_metadata_transaction_removes_physical_file(self):
        with patch("core.attachments.audit", side_effect=RuntimeError("Synthetic audit failure")):
            with self.assertRaises(RuntimeError):
                self.upload()
        self.assertEqual(Attachment.objects.count(), 0)
        self.assertEqual(list(Path(self.directory.name).glob("*/*")), [])

    def test_own_staged_delete_tombstones_and_commit_purges(self):
        item = self.upload()
        path = private_path(item.storage_key)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.as_user(self.unit_head).delete(f"{BASE}{item.pk}/")
        self.assertEqual(response.status_code, 204)
        item.refresh_from_db()
        self.assertEqual(item.status, "DELETED")
        self.assertIsNotNone(item.purged_at)
        self.assertFalse(path.exists())

    def test_cleanup_previews_then_expires_staging_and_preserves_bound_files(self):
        orphan = self.upload()
        bound, _ = self.bind()
        Attachment.objects.filter(pk__in=[orphan.pk, bound.pk]).update(created_at=timezone.now() - timedelta(days=2))
        output = io.StringIO()
        call_command("cleanup_attachments", stdout=output)
        self.assertIn("Önizleme: 1", output.getvalue())
        self.assertTrue(private_path(orphan.storage_key).exists())
        call_command("cleanup_attachments", apply=True, stdout=io.StringIO())
        orphan.refresh_from_db()
        bound.refresh_from_db()
        self.assertEqual(orphan.status, "DELETED")
        self.assertFalse(private_path(orphan.storage_key).exists())
        self.assertEqual(bound.status, "READY")
        self.assertTrue(private_path(bound.storage_key).exists())
        output = io.StringIO()
        call_command("cleanup_attachments", stdout=output)
        self.assertIn("Önizleme: 0", output.getvalue())

    def test_invalid_file_signatures_empty_and_mismatched_mime_are_rejected(self):
        examples = (
            ("script.svg", b"<svg onload='alert(1)'/>", "image/svg+xml"),
            ("photo.png", b"Not an image", "image/png"),
            ("document.pdf", b"%PDF-1.7 fake", "application/pdf"),
            ("shell.txt", b"\x00binary", "text/plain"),
            ("page.txt", b"<script>unsafe()</script>", "text/plain"),
            ("empty.txt", b"", "text/plain"),
            ("notes.txt", b"Some text", "image/png"),
        )
        for name, content, mime in examples:
            with self.subTest(name=name), self.assertRaises(ValidationError):
                validate_upload(self.file(name, content, mime))
        self.assertFalse(Attachment.objects.exists())

    @override_settings(ONECS_UPLOAD_MAX_BYTES=10)
    def test_size_limit_is_enforced_before_storage(self):
        with self.assertRaises(ValidationError):
            self.upload(content=b"X" * 11)
        self.assertEqual(list(Path(self.directory.name).glob("*/*")), [])

    def test_allowed_raster_pdf_and_office_types_use_verified_mime(self):
        png = self.upload(name="photo.png", content=PNG, mime="image/png")
        self.assertEqual(png.content_type, "image/png")
        pdf = self.upload(name="report.pdf", content=b"%PDF-1.4\nsynthetic\n%%EOF", mime="application/pdf")
        self.assertEqual(pdf.content_type, "application/pdf")
        for suffix, required, mime in (
            ("docx", "word/document.xml", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
            ("xlsx", "xl/workbook.xml", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            ("pptx", "ppt/presentation.xml", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
        ):
            content = io.BytesIO()
            with zipfile.ZipFile(content, "w") as archive:
                archive.writestr("[Content_Types].xml", "<Types/>")
                archive.writestr(required, "<document/>")
            item = self.upload(name=f"document.{suffix}", content=content.getvalue(), mime=mime)
            self.assertEqual(item.content_type, mime)

    def test_office_macros_and_zip_bombs_are_not_accepted(self):
        for extra, declared_size in (("word/vbaProject.bin", None), ("../escape.txt", None)):
            content = io.BytesIO()
            with zipfile.ZipFile(content, "w") as archive:
                archive.writestr("[Content_Types].xml", "<Types/>")
                archive.writestr("word/document.xml", "<document/>")
                archive.writestr(extra, "unsafe")
            with self.subTest(extra=extra), self.assertRaises(ValidationError):
                validate_upload(self.file("document.docx", content.getvalue(), "application/octet-stream"))

    def test_filename_and_storage_key_never_traverse_directories(self):
        item = self.upload(name="../../nested\\notes.txt")
        self.assertEqual(item.name, "notes.txt")
        self.assertNotIn(self.directory.name, str(attachment_data(item)))
        with self.assertRaises(NotFound):
            private_path("../../file.txt")

    def test_malformed_attachment_ids_return_not_found(self):
        client = self.as_user(self.unit_head)
        self.assertEqual(client.get(BASE + "invalid/download/").status_code, 404)
        self.assertEqual(client.delete(BASE + "invalid/").status_code, 404)

    @override_settings(ONECS_UPLOAD_ALLOW_UNSCANNED=False)
    def test_bounded_scanner_command_releases_pending_files_and_keeps_audit(self):
        self.upload()
        self.upload()
        with override_settings(ONECS_UPLOAD_SCANNER_COMMAND="scanner"), patch("core.attachments.subprocess.run", return_value=SimpleNamespace(returncode=0)) as scanner:
            call_command("scan_attachments", limit=1, stdout=io.StringIO())
            self.assertEqual(scanner.call_count, 1)
            self.assertEqual(Attachment.objects.filter(status="READY", scan_status="clean").count(), 1)
            call_command("scan_attachments", limit=1, stdout=io.StringIO())
            self.assertEqual(scanner.call_count, 2)
        self.assertEqual(Attachment.objects.filter(status="PENDING_SCAN").count(), 0)
        self.assertEqual(AuditEvent.objects.filter(action="attachment.scan.completed").count(), 2)

    @override_settings(ONECS_UPLOAD_ALLOW_UNSCANNED=False)
    def test_scanner_command_rejects_storage_tampering_without_calling_scanner(self):
        item = self.upload()
        private_path(item.storage_key).write_bytes(b"Modified after upload")
        with override_settings(ONECS_UPLOAD_SCANNER_COMMAND="scanner"), patch("core.attachments.subprocess.run") as scanner:
            call_command("scan_attachments", limit=1, stdout=io.StringIO())
            scanner.assert_not_called()
        item.refresh_from_db()
        self.assertEqual((item.status, item.scan_status), ("REJECTED", "integrity_error"))
