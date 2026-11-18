"""Directory discovery and inbox state use the same current access checks."""

import uuid
from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APIClient

from core.models import ApiClient as ApiClientRecord
from core.models import Notification, Project, ProjectRevision, RoleGrant, WorkItem
from core.tests.base import AtlasTestCase
from core.views import issue_token


class TurkishDirectorySearchTests(AtlasTestCase):
    def setUp(self):
        super().setUp()
        self.director.display_name = "Emin İslam Tatlı"
        self.director.save(update_fields=["display_name"])
        self.other_head.display_name = "Abdurrahman Şakar"
        self.other_head.save(update_fields=["display_name"])
        self.work = WorkItem.objects.create(
            title="Güvenlik görünürlüğü",
            description="Erişim talepleri için ortak değerlendirme",
            created_by=self.unit_head,
            assigned_to=self.employee,
            owner_org=self.team,
        )

    def search(self, user, query):
        response = self.as_user(user).get("/api/v1/search/", {"q": query})
        self.assertEqual(response.status_code, 200, response.content)
        return self.rows(response)

    def test_turkish_dotted_and_dotless_i_have_the_same_name_search_result(self):
        for query in ("islam", "ISLAM", "İSLAM", "ıslam"):
            with self.subTest(query=query):
                rows = self.search(self.employee, query)
                self.assertIn(str(self.director.pk), {row["id"] for row in rows})

    def test_turkish_accents_are_optional_for_name_discovery(self):
        for query in ("sakar", "Şakar", "SAKAR"):
            with self.subTest(query=query):
                rows = self.search(self.employee, query)
                self.assertIn(str(self.other_head.pk), {row["id"] for row in rows})

    def test_full_text_prefix_finds_accented_work_title(self):
        rows = self.search(self.employee, "guven")
        self.assertIn(str(self.work.pk), {row["id"] for row in rows})

    def test_description_phrase_is_searchable_without_turkish_accents(self):
        rows = self.search(self.employee, "erisim talepleri")
        self.assertIn(str(self.work.pk), {row["id"] for row in rows})

    def test_full_text_terms_can_match_in_a_different_order_than_the_description(self):
        rows = self.search(self.employee, "ortak erisim")
        self.assertIn(str(self.work.pk), {row["id"] for row in rows})

    def test_project_summary_reader_cannot_search_its_private_body(self):
        project = Project.objects.create(
            title="Reviewed programme overview",
            description="FiligranRiskProjesiGizli",
            expected_outcome="An internal unreviewed outcome",
            created_by=self.employee,
            owner_org=self.unit,
            appointment=self.appointment,
            status="PLANNED",
            published_revision=1,
        )
        project.audience.add(self.unit)
        ProjectRevision.objects.create(
            project=project,
            number=1,
            author=self.employee,
            decision="APPROVE",
            content={"title": "Reviewed programme overview", "expected_outcome": "Reviewed public outcome"},
        )
        public_rows = self.search(self.colleague, "Reviewed")
        self.assertIn(str(project.pk), {row["id"] for row in public_rows})
        hidden_rows = self.search(self.colleague, "FiligranRiskProjesiGizli")
        self.assertNotIn(str(project.pk), {row["id"] for row in hidden_rows})
        full_rows = self.search(self.pm, "FiligranRiskProjesiGizli")
        self.assertIn(str(project.pk), {row["id"] for row in full_rows})

    def test_normalized_search_does_not_expand_scoped_token_resource_or_people_access(self):
        hidden = WorkItem.objects.create(
            title="Gizli Güvenlik IAM planı",
            description="Erişim talepleri için gizli IAM değerlendirmesi",
            created_by=self.other_head,
            assigned_to=self.outsider,
            owner_org=self.other_unit,
        )
        client_record = ApiClientRecord.objects.create(
            name="OS directory reader", user=self.director, org_node=self.unit, scopes=["atlas:read"]
        )
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="Bearer " + issue_token(client_record))
        response = client.get("/api/v1/search/", {"q": "guven"})
        self.assertEqual(response.status_code, 200, response.content)
        ids = {row["id"] for row in self.rows(response)}
        self.assertIn(str(self.work.pk), ids)
        self.assertNotIn(str(hidden.pk), ids)
        self.assertNotIn("Gizli", response.content.decode())
        response = client.get("/api/v1/search/", {"q": "sakar"})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertNotIn(str(self.other_head.pk), {row["id"] for row in self.rows(response)})
        self.assertEqual(client.get(f"/api/v1/work/{hidden.pk}/").status_code, 404)


class DirectoryProfileTests(AtlasTestCase):
    def test_profile_identifies_reference_or_demo_account_and_actual_scoped_roles(self):
        self.unit_head.profile_kind = "OFFICIAL_REFERENCE"
        self.unit_head.save(update_fields=["profile_kind"])
        self.employee.profile_kind = "DEMO"
        self.employee.save(update_fields=["profile_kind"])
        RoleGrant.objects.create(user=self.unit_head, role="SYSTEM_ADMIN", org_node=self.unit, expires_at=timezone.now() - timedelta(seconds=1))
        response = self.as_user(self.employee).get(f"/api/v1/people/{self.unit_head.pk}/")
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual(data["profile_kind"], "OFFICIAL_REFERENCE")
        self.assertEqual(data["identity_source"], "local")
        self.assertEqual(data["role_label"], "Birim yöneticisi")
        grant = next(role for role in data["roles"] if role["role"] == "UNIT_HEAD")
        self.assertEqual(grant["org_id"], str(self.unit.pk))
        self.assertEqual(grant["org_name"], self.unit.name)
        self.assertTrue(grant["includes_descendants"])
        self.assertIsNone(grant["expires_at"])
        self.assertNotIn("SYSTEM_ADMIN", {role["role"] for role in data["roles"]})
        response = self.client.get(f"/api/v1/people/{self.employee.pk}/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["profile_kind"], "DEMO")
        self.assertEqual(response.json()["role_label"], "Çalışan")

    def test_organization_manager_links_are_user_ids_with_the_same_profile_contract(self):
        response = self.as_user(self.employee).get(f"/api/v1/organization/{self.unit.pk}/")
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual(data["manager_id"], str(self.unit_head.pk))
        self.assertEqual(data["manager_ids"], [str(self.unit_head.pk)])
        self.assertEqual(data["managers"][0]["id"], str(self.unit_head.pk))
        self.assertEqual(data["managers"][0]["role_label"], "Birim yöneticisi")
        self.assertFalse(data["is_demo"])


class NotificationReadStateTests(AtlasTestCase):
    def setUp(self):
        super().setUp()
        self.visible_work = WorkItem.objects.create(title="Assigned review", assigned_to=self.employee, created_by=self.unit_head, owner_org=self.team)
        self.hidden_work = WorkItem.objects.create(title="Other unit private work", assigned_to=self.outsider, created_by=self.other_head, owner_org=self.other_unit)
        self.unread = self.notice(self.employee, self.visible_work)
        self.read = self.notice(self.employee, self.visible_work, read_at=timezone.now() - timedelta(days=1))
        self.hidden = self.notice(self.employee, self.hidden_work)
        self.other_recipient = self.notice(self.colleague, self.visible_work)

    @staticmethod
    def notice(recipient, work, **extra):
        return Notification.objects.create(
            recipient=recipient,
            title="Work update",
            resource_type="work",
            resource_id=str(work.pk),
            dedup_key=f"notification-test:{uuid.uuid4()}",
            **extra,
        )

    def inbox_ids(self, status=None):
        params = {"status": status} if status else {}
        response = self.as_user(self.employee).get("/api/v1/notifications/", params)
        self.assertEqual(response.status_code, 200, response.content)
        return {row["id"] for row in self.rows(response)}

    def test_read_and_unread_filters_apply_after_current_resource_authorization(self):
        self.assertSetEqual(self.inbox_ids("unread"), {str(self.unread.pk)})
        self.assertSetEqual(self.inbox_ids("read"), {str(self.read.pk)})
        self.assertSetEqual(self.inbox_ids(), {str(self.unread.pk), str(self.read.pk)})

    def test_recipient_can_mark_read_and_explicitly_mark_unread_again(self):
        url = f"/api/v1/notifications/{self.unread.pk}/read/"
        response = self.as_user(self.employee).post(url, {}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.unread.refresh_from_db()
        self.assertIsNotNone(self.unread.read_at)
        response = self.client.post(url, {"read": False}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.unread.refresh_from_db()
        self.assertIsNone(self.unread.read_at)
        response = self.as_user(self.colleague).post(url, {"read": True}, format="json")
        self.assertEqual(response.status_code, 404, response.content)

    def test_mark_all_read_updates_only_unread_currently_authorized_notifications(self):
        another_visible = self.notice(self.employee, self.visible_work)
        response = self.as_user(self.employee).post("/api/v1/notifications/mark-all-read/", {}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["updated"], 2)
        for notice in (self.unread, another_visible):
            notice.refresh_from_db()
            self.assertIsNotNone(notice.read_at)
        self.hidden.refresh_from_db()
        self.other_recipient.refresh_from_db()
        self.assertIsNone(self.hidden.read_at)
        self.assertIsNone(self.other_recipient.read_at)
        response = self.client.post("/api/v1/notifications/mark-all-read/", {}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["updated"], 0)

    def test_revoked_work_visibility_prevents_marking_previously_visible_notification(self):
        WorkItem.objects.filter(pk=self.visible_work.pk).update(assigned_to=self.outsider, owner_org=self.other_unit)
        self.assertSetEqual(self.inbox_ids("unread"), set())
        response = self.client.post(f"/api/v1/notifications/{self.unread.pk}/read/", {}, format="json")
        self.assertEqual(response.status_code, 404, response.content)
        response = self.client.post("/api/v1/notifications/mark-all-read/", {}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["updated"], 0)
        self.unread.refresh_from_db()
        self.assertIsNone(self.unread.read_at)
