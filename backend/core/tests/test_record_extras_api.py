"""Record creation, private claims and email intentions commit as one operation."""

import tempfile
import uuid

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from core.models import Attachment, AuditEvent, IdempotencyRecord, OutboxEvent, ProgressEntry, Project, RecordEmailPreference, RoleGrant, WorkItem
from core.tests.base import OnecsTestCase


class RecordExtrasAPITests(OnecsTestCase):
    def setUp(self):
        super().setUp()
        self.upload_root = tempfile.TemporaryDirectory()
        self.addCleanup(self.upload_root.cleanup)
        self.upload_settings = override_settings(
            ONECS_UPLOAD_ROOT=self.upload_root.name,
            ONECS_UPLOAD_ALLOW_UNSCANNED=True, ONECS_UPLOAD_SCANNER_COMMAND="",
            DEBUG=True, ONECS_ENV="test",
        )
        self.upload_settings.enable()
        self.addCleanup(self.upload_settings.disable)

    def upload(self, actor=None):
        response = self.as_user(actor or self.unit_head).post(
            "/api/v1/attachments/",
            {"file": SimpleUploadedFile("plan.txt", b"Synthetic implementation plan", content_type="text/plain")},
            format="multipart", HTTP_X_REQUEST_ID=str(uuid.uuid4()),
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["id"]

    def work_payload(self, attachment_id, **extra):
        return {
            "title": "Synthetic record with attachment",
            "assignee_id": str(self.employee.pk), "personal": False,
            "attachment_ids": [attachment_id],
            "send_email": True,
            "notification_recipient_ids": [str(self.employee.pk)], **extra,
        }

    def test_work_claim_email_and_retry_share_one_commit(self):
        attachment_id = self.upload()
        request_key = str(uuid.uuid4())
        payload = self.work_payload(attachment_id)
        client = self.as_user(self.unit_head)
        first = client.post("/api/v1/work/", payload, format="json", HTTP_X_REQUEST_ID=request_key)
        self.assertEqual(first.status_code, 201, first.content)
        second = client.post("/api/v1/work/", payload, format="json", HTTP_X_REQUEST_ID=request_key)
        self.assertEqual(second.status_code, 201, second.content)
        self.assertEqual(first.json()["id"], second.json()["id"])
        self.assertEqual(WorkItem.objects.count(), 1)
        item = Attachment.objects.get(pk=attachment_id)
        self.assertEqual(item.resource_type, "work")
        self.assertEqual(str(item.resource_id), first.json()["id"])
        # Optional notification must not duplicate the mandatory assignment.
        self.assertEqual(OutboxEvent.objects.filter(resource_id=first.json()["id"], recipient=self.employee).count(), 1)
        self.assertEqual(IdempotencyRecord.objects.filter(actor=self.unit_head, key=request_key).count(), 1)
        self.assertEqual(RecordEmailPreference.objects.count(), 1)
        download = self.as_user(self.employee).get(f"/api/v1/attachments/{item.pk}/download/")
        self.assertEqual(download.status_code, 200)
        self.assertEqual(b"".join(download.streaming_content), b"Synthetic implementation plan")

    def test_another_upload_owner_rolls_back_the_domain_assignment(self):
        attachment_id = self.upload(self.employee)
        audit_count = AuditEvent.objects.count()
        response = self.as_user(self.unit_head).post("/api/v1/work/", self.work_payload(attachment_id), format="json")
        self.assertIn(response.status_code, (400, 403, 404), response.content)
        self.assertFalse(WorkItem.objects.exists())
        self.assertFalse(OutboxEvent.objects.exists())
        self.assertFalse(RecordEmailPreference.objects.exists())
        self.assertEqual(AuditEvent.objects.count(), audit_count)
        self.assertIsNone(Attachment.objects.get(pk=attachment_id).resource_id)

    def test_out_of_scope_recipient_rolls_back_work_and_attachment_claim(self):
        attachment_id = self.upload()
        response = self.as_user(self.unit_head).post(
            "/api/v1/work/",
            self.work_payload(attachment_id, notification_recipient_ids=[str(self.outsider.pk)]), format="json",
        )
        self.assertEqual(response.status_code, 403, response.content)
        self.assertFalse(WorkItem.objects.exists())
        self.assertFalse(OutboxEvent.objects.exists())
        self.assertFalse(RecordEmailPreference.objects.exists())
        self.assertIsNone(Attachment.objects.get(pk=attachment_id).resource_id)

    def test_draft_project_stages_preference_and_submit_deduplicates_pm_mail(self):
        attachment_id = self.upload(self.employee)
        response = self.as_user(self.employee).post("/api/v1/projects/", {
            "title": "Synthetic project", "description": "Synthetic scope",
            "expected_outcome": "Verified output", "pm_id": str(self.pm.pk),
            "attachment_ids": [attachment_id], "send_email": True,
            "notification_recipient_ids": [str(self.pm.pk)],
        }, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        project = Project.objects.get(pk=response.json()["id"])
        self.assertFalse(OutboxEvent.objects.filter(resource_id=str(project.pk)).exists())
        hidden = self.as_user(self.pm).get(f"/api/v1/attachments/?resource_type=project&resource_id={project.pk}")
        self.assertIn(hidden.status_code, (403, 404), hidden.content)
        submitted = self.as_user(self.employee).post(f"/api/v1/projects/{project.pk}/submit/", {"version": project.version}, format="json")
        self.assertEqual(submitted.status_code, 200, submitted.content)
        self.assertEqual(OutboxEvent.objects.filter(resource_id=str(project.pk), recipient=self.pm).count(), 1)
        visible = self.as_user(self.pm).get(f"/api/v1/attachments/?resource_type=project&resource_id={project.pk}")
        self.assertEqual(visible.status_code, 200, visible.content)
        self.assertEqual(visible.json()["results"][0]["id"], attachment_id)

    def test_extras_on_a_state_action_are_rejected_without_state_change(self):
        response = self.as_user(self.employee).post("/api/v1/work/", {"title": "Personal"}, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        work = WorkItem.objects.get(pk=response.json()["id"])
        rejected = self.client.post(f"/api/v1/work/{work.pk}/progress/", {
            "version": work.version, "done": "Synthetic update", "attachment_ids": [],
        }, format="json")
        self.assertEqual(rejected.status_code, 400, rejected.content)
        work.refresh_from_db()
        self.assertEqual(work.version, 1)
        self.assertFalse(ProgressEntry.objects.exists())

    def test_initial_case_attachment_preserves_delegated_create_without_granting_read(self):
        RoleGrant.objects.create(user=self.team_manager, role="EMPLOYEE", org_node=self.other_unit, permissions=["case.create"])
        attachment_id = self.upload(self.team_manager)
        response = self.as_user(self.team_manager).post("/api/v1/cases/", {
            "title": "Delegated synthetic case", "owner_org_id": str(self.other_unit.pk),
            "coordinator_id": str(self.employee.pk), "attachment_ids": [attachment_id],
            "send_email": True, "notification_recipient_ids": [str(self.employee.pk)],
        }, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        attachment = Attachment.objects.get(pk=attachment_id)
        self.assertEqual(attachment.resource_type, "case")
        denied = self.client.get(f"/api/v1/attachments/{attachment_id}/download/")
        self.assertIn(denied.status_code, (403, 404), denied.content)
        permitted = self.as_user(self.employee).get(f"/api/v1/attachments/{attachment_id}/download/")
        self.assertEqual(permitted.status_code, 200)
        self.assertEqual(b"".join(permitted.streaming_content), b"Synthetic implementation plan")
