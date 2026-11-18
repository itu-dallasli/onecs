"""Dashboard decisions and inbox state follow current recipient permissions."""

import uuid
from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from core.models import (
    Announcement,
    ApiClient,
    AuditEvent,
    Case,
    CaseNotice,
    Notification,
    OutboxEvent,
    ParticipationRequest,
    Project,
    RoleGrant,
    User,
    WorkItem,
)
from core.tests.base import OnecsTestCase
from core.views import issue_token


class DashboardAnnouncementTests(OnecsTestCase):
    def announcement(self, title, *, owner=None, creator=None, audience=None, **extra):
        obj = Announcement.objects.create(
            title=title,
            body=f"Synthetic announcement: {title}",
            owner_org=owner or self.team,
            created_by=creator or self.employee,
            starts_at=timezone.now() - timedelta(hours=1),
            **extra,
        )
        obj.audience.set(audience if audience is not None else [self.unit])
        return obj

    def dashboard(self, actor):
        response = self.as_user(actor).get("/api/v1/dashboard/")
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    @staticmethod
    def ids(rows):
        return {row["id"] for row in rows}

    def test_live_published_announcements_follow_audience_and_publication_window(self):
        live = self.announcement("Audience live", status="PUBLISHED")
        global_notice = self.announcement(
            "Global live",
            owner=self.other_unit,
            creator=self.other_head,
            audience=[],
            all_cs=True,
            status="PUBLISHED",
        )
        hidden = [
            self.announcement("Unpublished body sentinel"),
            self.announcement("Withdrawn body sentinel", status="WITHDRAWN"),
            self.announcement(
                "Expired body sentinel",
                status="PUBLISHED",
                ends_at=timezone.now() - timedelta(minutes=1),
            ),
            self.announcement(
                "Outside audience sentinel",
                status="PUBLISHED",
                audience=[self.other_unit],
            ),
        ]
        future = self.announcement("Future body sentinel", status="PUBLISHED")
        Announcement.objects.filter(pk=future.pk).update(
            starts_at=timezone.now() + timedelta(days=1)
        )
        hidden.append(future)
        data = self.dashboard(self.colleague)
        self.assertEqual(
            self.ids(data["announcements"]), {str(live.pk), str(global_notice.pk)}
        )
        for obj in hidden:
            self.assertNotIn(obj.title, str(data))

    def test_live_announcements_report_the_total_and_keep_pinned_at_the_front(self):
        for i in range(7):
            self.announcement(f"Current bulletin {i}", status="PUBLISHED")
        pinned = self.announcement("Pinned bulletin", status="PUBLISHED", pinned=True)
        data = self.dashboard(self.colleague)
        self.assertEqual(len(data["announcements"]), data["announcement_limit"])
        self.assertEqual(data["announcement_counts"]["published"], 8)
        self.assertEqual(data["announcements"][0]["id"], str(pinned.pk))

    def test_own_pending_proposal_is_visible_without_granting_publication_authority(
        self,
    ):
        own = self.announcement("Own pending proposal")
        sibling = self.announcement(
            "Colleague private proposal sentinel", creator=self.colleague
        )
        data = self.dashboard(self.employee)
        self.assertEqual(self.ids(data["pending_announcements"]), {str(own.pk)})
        self.assertEqual(data["announcement_counts"], {"published": 0, "pending": 1})
        self.assertEqual(data["kpis"]["decisions"], 0)
        self.assertFalse(data["pending_announcements"][0]["permissions"]["publish"])
        self.assertNotIn(sibling.title, str(data))
        response = self.client.post(
            f"/api/v1/announcements/{own.pk}/publish/",
            {"version": own.version},
            format="json",
        )
        self.assertEqual(response.status_code, 403, response.content)
        own.refresh_from_db()
        self.assertEqual(own.status, "DRAFT")

    def test_publication_decisions_include_only_real_publishers_current_scope(self):
        local = self.announcement("Team awaiting decision")
        expired = self.announcement(
            "Expired proposal awaiting decision",
            ends_at=timezone.now() - timedelta(minutes=1),
        )
        self.announcement("Withdrawn proposal sentinel", status="WITHDRAWN")
        outside = self.announcement(
            "Other unit proposal sentinel", owner=self.other_unit, creator=self.outsider
        )
        data = self.dashboard(self.unit_head)
        self.assertEqual(
            self.ids(data["pending_announcements"]), {str(local.pk), str(expired.pk)}
        )
        self.assertEqual(data["kpis"]["decisions"], 2)
        permissions = {
            row["id"]: row["permissions"] for row in data["pending_announcements"]
        }
        self.assertTrue(permissions[str(local.pk)]["publish"])
        self.assertFalse(permissions[str(expired.pk)]["publish"])
        self.assertNotIn(outside.title, str(data))
        data = self.dashboard(self.team_manager)
        self.assertEqual(data["pending_announcements"], [])
        self.assertEqual(data["kpis"]["decisions"], 0)

    def test_pending_count_includes_all_decisions_beyond_the_visible_preview(self):
        for i in range(8):
            self.announcement(f"Pending decision {i}")
        data = self.dashboard(self.unit_head)
        self.assertEqual(len(data["pending_announcements"]), data["announcement_limit"])
        self.assertEqual(data["announcement_counts"]["pending"], 8)
        self.assertEqual(data["kpis"]["decisions"], 8)

    def test_revoked_publisher_role_removes_decision_and_publish_permission(self):
        pending = self.announcement("Role revocation pending proposal")
        self.assertEqual(self.dashboard(self.unit_head)["kpis"]["decisions"], 1)
        RoleGrant.objects.filter(user=self.unit_head, role="UNIT_HEAD").update(
            active=False
        )
        data = self.dashboard(self.unit_head)
        self.assertEqual(data["pending_announcements"], [])
        self.assertEqual(data["announcement_counts"]["pending"], 0)
        response = self.client.post(
            f"/api/v1/announcements/{pending.pk}/publish/",
            {"version": pending.version},
            format="json",
        )
        self.assertEqual(response.status_code, 404, response.content)
        pending.refresh_from_db()
        self.assertEqual(pending.status, "DRAFT")

    def test_scoped_token_cannot_expand_dashboard_announcement_scope(self):
        inside = self.announcement(
            "Inside token scope", owner=self.unit, status="PUBLISHED", all_cs=True
        )
        outside = self.announcement(
            "Outside token scope sentinel",
            owner=self.other_unit,
            creator=self.other_head,
            status="PUBLISHED",
            all_cs=True,
        )
        client_record = ApiClient.objects.create(
            name="Synthetic dashboard reader",
            user=self.director,
            org_node=self.unit,
            scopes=["onecs:read"],
        )
        bearer = APIClient()
        bearer.credentials(HTTP_AUTHORIZATION="Bearer " + issue_token(client_record))
        response = bearer.get("/api/v1/dashboard/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.ids(response.json()["announcements"]), {str(inside.pk)})
        self.assertNotIn(outside.title, response.content.decode())

    def test_scoped_reader_sees_only_scoped_pending_items_with_no_write_permissions(
        self,
    ):
        inside = self.announcement("Inside pending token scope", owner=self.unit)
        outside = self.announcement(
            "Outside pending token sentinel",
            owner=self.other_unit,
            creator=self.outsider,
        )
        client_record = ApiClient.objects.create(
            name="Synthetic pending reader",
            user=self.director,
            org_node=self.unit,
            scopes=["onecs:read"],
        )
        bearer = APIClient()
        bearer.credentials(HTTP_AUTHORIZATION="Bearer " + issue_token(client_record))
        response = bearer.get("/api/v1/dashboard/")
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual(self.ids(data["pending_announcements"]), {str(inside.pk)})
        self.assertEqual(data["announcement_counts"]["pending"], 1)
        self.assertEqual(
            data["pending_announcements"][0]["permissions"],
            {"publish": False, "withdraw": False},
        )
        self.assertNotIn(outside.title, str(data))


class NotificationStateRegressionTests(OnecsTestCase):
    def setUp(self):
        super().setUp()
        self.work = WorkItem.objects.create(
            title="Synthetic assigned work",
            created_by=self.unit_head,
            assigned_to=self.employee,
            owner_org=self.team,
        )
        self.hidden_work = WorkItem.objects.create(
            title="Another unit confidential sentinel",
            created_by=self.other_head,
            assigned_to=self.outsider,
            owner_org=self.other_unit,
        )

    def notice(self, *, recipient=None, work=None, **extra):
        return Notification.objects.create(
            recipient=recipient or self.employee,
            title="Synthetic work update",
            resource_type="work",
            resource_id=str((work or self.work).pk),
            dedup_key=f"inbox-regression:{uuid.uuid4()}",
            **extra,
        )

    def test_read_and_unread_mutations_ignore_the_current_list_filter(self):
        notice = self.notice()
        response = self.as_user(self.employee).post(
            f"/api/v1/notifications/{notice.pk}/read/?status=read",
            {"read": True},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        notice.refresh_from_db()
        self.assertIsNotNone(notice.read_at)
        response = self.client.post(
            f"/api/v1/notifications/{notice.pk}/read/?status=unread",
            {"read": False},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        notice.refresh_from_db()
        self.assertIsNone(notice.read_at)

    def test_mark_all_read_ignores_list_filter_and_persists_only_authorized_recipient_rows(
        self,
    ):
        first, second = self.notice(), self.notice()
        hidden = self.notice(work=self.hidden_work)
        different_recipient = self.notice(recipient=self.colleague)
        response = self.as_user(self.employee).post(
            "/api/v1/notifications/mark-all-read/?status=read",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["updated"], 2)
        for notice in (first, second, hidden, different_recipient):
            notice.refresh_from_db()
            self.assertEqual(notice.read_at is not None, notice in (first, second))
        response = self.client.post(
            "/api/v1/notifications/mark-all-read/", {}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["updated"], 0)

    def test_revoked_access_removes_notification_from_list_detail_and_mutations(self):
        notice = self.notice()
        self.as_user(self.employee)
        before = self.client.get("/api/v1/notifications/")
        self.assertEqual(before.status_code, 200, before.content)
        self.assertIn(str(notice.pk), {row["id"] for row in self.rows(before)})
        WorkItem.objects.filter(pk=self.work.pk).update(
            owner_org=self.other_unit, assigned_to=self.outsider
        )
        response = self.client.get("/api/v1/notifications/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.rows(response), [])
        self.assertEqual(
            self.client.get(f"/api/v1/notifications/{notice.pk}/").status_code, 404
        )
        self.assertEqual(
            self.client.post(
                f"/api/v1/notifications/{notice.pk}/read/", {}, format="json"
            ).status_code,
            404,
        )
        notice.refresh_from_db()
        self.assertIsNone(notice.read_at)

    def test_read_rejects_non_boolean_state_without_persisting_it(self):
        notice = self.notice()
        response = self.as_user(self.employee).post(
            f"/api/v1/notifications/{notice.pk}/read/",
            {"read": "false"},
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.content)
        notice.refresh_from_db()
        self.assertIsNone(notice.read_at)

    def test_counts_and_paging_use_all_currently_authorized_recipient_notifications(
        self,
    ):
        unread = [self.notice() for _ in range(3)]
        read = [self.notice(read_at=timezone.now()) for _ in range(2)]
        self.notice(work=self.hidden_work)
        self.notice(recipient=self.colleague)
        self.as_user(self.employee)
        for status, count in (("all", 5), ("unread", 3), ("read", 2)):
            with self.subTest(status=status):
                response = self.client.get(
                    "/api/v1/notifications/",
                    {"status": status, "limit": 1, "offset": 0},
                )
                self.assertEqual(response.status_code, 200, response.content)
                data = response.json()
                self.assertEqual(data["count"], count)
                self.assertEqual(data["unread_count"], 3)
                self.assertEqual(len(data["results"]), 1)
                self.assertEqual(data["limit"], 1)
                self.assertEqual(data["offset"], 0)
                self.assertEqual(data["next_offset"], 1)
        ids = set()
        offset = 0
        while offset is not None:
            response = self.client.get(
                "/api/v1/notifications/", {"limit": 2, "offset": offset}
            )
            self.assertEqual(response.status_code, 200, response.content)
            data = response.json()
            self.assertFalse(ids & {row["id"] for row in data["results"]})
            ids.update(row["id"] for row in data["results"])
            offset = data["next_offset"]
        self.assertEqual(ids, {str(obj.pk) for obj in [*unread, *read]})

    def test_invalid_status_or_paging_is_rejected(self):
        self.as_user(self.employee)
        for params in (
            {"status": "invalid"},
            {"limit": "abc"},
            {"limit": 0},
            {"limit": -1},
            {"offset": -1},
            {"offset": "abc"},
        ):
            with self.subTest(params=params):
                response = self.client.get("/api/v1/notifications/", params)
                self.assertEqual(response.status_code, 400, response.content)

    def test_malformed_or_deleted_known_sources_do_not_break_the_inbox_or_expose_titles(
        self,
    ):
        visible = self.notice()
        hidden = []
        for resource_type in (
            "work",
            "project",
            "case",
            "announcement",
            "community",
            "credential",
            "participation",
            "event",
        ):
            for resource_id in ("not-a-uuid", str(uuid.uuid4())):
                hidden.append(
                    Notification.objects.create(
                        recipient=self.employee,
                        title="Unavailable source sentinel",
                        resource_type=resource_type,
                        resource_id=resource_id,
                        dedup_key=f"stale-source:{uuid.uuid4()}",
                    )
                )
        response = self.as_user(self.employee).get("/api/v1/notifications/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual({row["id"] for row in self.rows(response)}, {str(visible.pk)})
        self.assertEqual(response.json()["count"], 1)
        self.assertEqual(response.json()["unread_count"], 1)
        self.assertNotIn("Unavailable source sentinel", response.content.decode())
        for notice in hidden:
            with self.subTest(
                resource_type=notice.resource_type, resource_id=notice.resource_id
            ):
                self.assertEqual(
                    self.client.get(f"/api/v1/notifications/{notice.pk}/").status_code,
                    404,
                )

    def test_openable_notification_uses_the_source_detail_url(self):
        notice = self.notice()
        response = self.as_user(self.employee).get(
            f"/api/v1/notifications/{notice.pk}/"
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["url"], f"/work?id={self.work.pk}")
        generic = Notification.objects.create(
            recipient=self.employee,
            title="Generic internal update",
            resource_type="unknown",
            resource_id="opaque",
            dedup_key=f"generic-source:{uuid.uuid4()}",
        )
        response = self.client.get(f"/api/v1/notifications/{generic.pk}/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIsNone(response.json()["url"])


class CaseNoticeNotificationTargetTests(OnecsTestCase):
    def setUp(self):
        super().setUp()
        self.case_notice = CaseNotice.objects.create(
            title="Synthetic employee case notice",
            description="Shareable observation awaiting review",
            created_by=self.employee,
            owner_org=self.team,
        )

    def notice(self, recipient, resource_id=None):
        return Notification.objects.create(
            recipient=recipient,
            title="Synthetic case notice update",
            resource_type="case_notice",
            resource_id=str(resource_id or self.case_notice.pk),
            dedup_key=f"case-notice-target:{uuid.uuid4()}",
        )

    def test_creator_and_current_manager_open_the_case_notice_with_its_canonical_url(
        self,
    ):
        for actor in (self.employee, self.unit_head):
            with self.subTest(actor=actor.username):
                notice = self.notice(actor)
                response = self.as_user(actor).get(
                    f"/api/v1/notifications/{notice.pk}/"
                )
                self.assertEqual(response.status_code, 200, response.content)
                self.assertEqual(
                    response.json()["url"],
                    f"/cases?notices=1&notice_id={self.case_notice.pk}",
                )
                self.assertEqual(
                    self.client.get(
                        f"/api/v1/case-notices/{self.case_notice.pk}/"
                    ).status_code,
                    200,
                )

    def test_unrelated_users_and_revoked_manager_cannot_open_or_mark_the_notification(
        self,
    ):
        actors = (self.colleague, self.outsider, self.unit_head)
        notices = {actor.pk: self.notice(actor) for actor in actors}
        manager_notice = notices[self.unit_head.pk]
        self.assertEqual(
            self.as_user(self.unit_head)
            .get(f"/api/v1/notifications/{manager_notice.pk}/")
            .status_code,
            200,
        )
        RoleGrant.objects.filter(user=self.unit_head, role="UNIT_HEAD").update(
            active=False
        )
        for actor in actors:
            with self.subTest(actor=actor.username):
                notice = notices[actor.pk]
                response = self.as_user(actor).get("/api/v1/notifications/")
                self.assertEqual(response.status_code, 200, response.content)
                self.assertEqual(response.json()["count"], 0)
                self.assertEqual(response.json()["unread_count"], 0)
                self.assertEqual(
                    self.client.get(f"/api/v1/notifications/{notice.pk}/").status_code,
                    404,
                )
                self.assertEqual(
                    self.client.post(
                        f"/api/v1/notifications/{notice.pk}/read/", {}, format="json"
                    ).status_code,
                    404,
                )
                notice.refresh_from_db()
                self.assertIsNone(notice.read_at)

    def test_malformed_and_deleted_case_notice_sources_are_absent_from_list_and_counts(
        self,
    ):
        valid = self.notice(self.employee)
        deleted = CaseNotice.objects.create(
            title="Deleted case notice sentinel",
            description="Deleted observation sentinel",
            created_by=self.employee,
            owner_org=self.team,
        )
        deleted_id = deleted.pk
        deleted.delete()
        stale = [
            self.notice(self.employee, "malformed-uuid"),
            self.notice(self.employee, deleted_id),
        ]
        response = self.as_user(self.employee).get("/api/v1/notifications/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual({row["id"] for row in self.rows(response)}, {str(valid.pk)})
        self.assertEqual(response.json()["count"], 1)
        self.assertEqual(response.json()["unread_count"], 1)
        self.assertNotIn("Deleted case notice sentinel", response.content.decode())
        for notice in stale:
            with self.subTest(resource_id=notice.resource_id):
                self.assertEqual(
                    self.client.get(f"/api/v1/notifications/{notice.pk}/").status_code,
                    404,
                )


class ParticipationNotificationTargetTests(OnecsTestCase):
    def participation(self, kind):
        if kind == "project":
            parent = Project.objects.create(
                title="Private project title sentinel",
                description="Private project body sentinel",
                created_by=self.outsider,
                owner_org=self.other_unit,
                appointment=self.appointment,
                status="PLANNED",
            )
        else:
            parent = Case.objects.create(
                title="Private case title sentinel",
                description="Private case body sentinel",
                created_by=self.other_head,
                coordinator=self.other_head,
                owner_org=self.other_unit,
            )
        return ParticipationRequest.objects.create(
            **{kind: parent},
            requested_by=self.pm,
            user=self.employee,
            target_org=self.team,
            summary="Synthetic shareable allocation request",
        )

    @staticmethod
    def notice(request, recipient):
        return Notification.objects.create(
            recipient=recipient,
            title="Synthetic resource allocation update",
            resource_type="participation",
            resource_id=str(request.pk),
            dedup_key=f"participation-target:{uuid.uuid4()}",
        )

    def test_target_manager_notification_opens_its_request_without_access_to_private_parent(
        self,
    ):
        for kind, route in (("project", "projects"), ("case", "cases")):
            with self.subTest(kind=kind):
                request = self.participation(kind)
                notice = self.notice(request, self.unit_head)
                response = self.as_user(self.unit_head).get(
                    f"/api/v1/notifications/{notice.pk}/"
                )
                self.assertEqual(response.status_code, 200, response.content)
                self.assertEqual(
                    response.json()["url"],
                    f"/{route}?requests=1&request_id={request.pk}",
                )
                self.assertEqual(
                    self.client.get(
                        f"/api/v1/participation-requests/{request.pk}/"
                    ).status_code,
                    200,
                )
                self.assertEqual(
                    self.client.get(
                        f"/api/v1/{route}/{getattr(request, kind + '_id')}/"
                    ).status_code,
                    404,
                )
                self.assertNotIn("Private", response.content.decode())

    def test_requester_receives_its_own_outcome_link_after_decision_without_target_manager_role(
        self,
    ):
        for kind, route in (("project", "projects"), ("case", "cases")):
            with self.subTest(kind=kind):
                request = self.participation(kind)
                request.status = "REJECTED"
                request.decided_by = self.unit_head
                request.save(update_fields=["status", "decided_by"])
                notice = self.notice(request, self.pm)
                response = self.as_user(self.pm).get(
                    f"/api/v1/notifications/{notice.pk}/"
                )
                self.assertEqual(response.status_code, 200, response.content)
                self.assertEqual(
                    response.json()["url"],
                    f"/{route}?requests=1&request_id={request.pk}",
                )
                response = self.client.get(
                    f"/api/v1/participation-requests/{request.pk}/"
                )
                self.assertEqual(response.status_code, 200, response.content)
                self.assertEqual(response.json()["status"], "REJECTED")

    def test_revoked_allocation_role_hides_old_target_notification_and_link(self):
        request = self.participation("project")
        notice = self.notice(request, self.unit_head)
        self.assertEqual(
            self.as_user(self.unit_head)
            .get(f"/api/v1/notifications/{notice.pk}/")
            .status_code,
            200,
        )
        RoleGrant.objects.filter(user=self.unit_head, role="UNIT_HEAD").update(
            active=False
        )
        response = self.client.get("/api/v1/notifications/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["count"], 0)
        self.assertEqual(response.json()["unread_count"], 0)
        self.assertEqual(
            self.client.get(f"/api/v1/notifications/{notice.pk}/").status_code, 404
        )
        self.assertEqual(
            self.client.post(
                f"/api/v1/notifications/{notice.pk}/read/", {}, format="json"
            ).status_code,
            404,
        )
        notice.refresh_from_db()
        self.assertIsNone(notice.read_at)

    def test_personnel_nomination_alone_and_outside_scoped_client_do_not_grant_request_access(
        self,
    ):
        request = self.participation("project")
        employee_notice = self.notice(request, self.employee)
        response = self.as_user(self.employee).get("/api/v1/notifications/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["count"], 0)
        self.assertEqual(
            self.client.get(f"/api/v1/notifications/{employee_notice.pk}/").status_code,
            404,
        )
        director_notice = self.notice(request, self.director)
        client_record = ApiClient.objects.create(
            name="Synthetic outside allocation reader",
            user=self.director,
            org_node=self.other_unit,
            scopes=["onecs:read"],
        )
        bearer = APIClient()
        bearer.credentials(HTTP_AUTHORIZATION="Bearer " + issue_token(client_record))
        response = bearer.get("/api/v1/notifications/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["count"], 0)
        self.assertEqual(
            bearer.get(f"/api/v1/notifications/{director_notice.pk}/").status_code, 404
        )


class AnnouncementNotificationTests(OnecsTestCase):
    def propose(self, **extra):
        payload = {
            "title": "Synthetic proposed announcement",
            "body": "Awaiting publication decision",
            **extra,
        }
        response = self.as_user(self.employee).post(
            "/api/v1/announcements/", payload, format="json"
        )
        self.assertEqual(response.status_code, 201, response.content)
        return Announcement.objects.get(pk=response.json()["id"])

    @staticmethod
    def notifications(obj, event):
        return Notification.objects.filter(
            resource_type="announcement",
            resource_id=str(obj.pk),
            dedup_key__startswith=f"announcement-{event}:",
        )

    def inbox(self, actor):
        response = self.as_user(actor).get("/api/v1/notifications/")
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def publish(self, obj, request_id=None):
        kwargs = {"HTTP_X_REQUEST_ID": request_id} if request_id else {}
        response = self.as_user(self.unit_head).post(
            f"/api/v1/announcements/{obj.pk}/publish/",
            {"version": obj.version},
            format="json",
            **kwargs,
        )
        self.assertEqual(response.status_code, 200, response.content)
        obj.refresh_from_db()
        return response

    def test_proposal_notifies_only_current_eligible_publishers_once_and_without_email(
        self,
    ):
        RoleGrant.objects.create(
            user=self.unit_head, role="UNIT_HEAD", org_node=self.unit
        )
        RoleGrant.objects.create(
            user=self.colleague,
            role="UNIT_HEAD",
            org_node=self.unit,
            expires_at=timezone.now() - timedelta(seconds=1),
        )
        disabled = User.objects.create_user(
            username="disabled-publisher", primary_org=self.unit, is_active=False
        )
        RoleGrant.objects.create(user=disabled, role="UNIT_HEAD", org_node=self.unit)
        obj = self.propose()
        self.assertEqual(
            set(
                self.notifications(obj, "proposed").values_list(
                    "recipient_id", flat=True
                )
            ),
            {self.director.pk, self.unit_head.pk},
        )
        self.assertEqual(self.notifications(obj, "proposed").count(), 2)
        self.assertFalse(
            OutboxEvent.objects.filter(
                resource_type="announcement", resource_id=str(obj.pk)
            ).exists()
        )
        self.assertTrue(
            AuditEvent.objects.filter(
                action="announcement.proposed",
                actor=self.employee,
                object_id=str(obj.pk),
            ).exists()
        )

    def test_publication_notifies_live_audience_and_removes_stale_decision_notifications(
        self,
    ):
        obj = self.propose(audience_org_ids=[str(self.unit.pk)])
        proposed = self.notifications(obj, "proposed").get(recipient=self.unit_head)
        self.assertIn(
            str(proposed.pk),
            {row["id"] for row in self.inbox(self.unit_head)["results"]},
        )
        self.publish(obj)
        expected_recipients = {
            self.unit_head.pk,
            self.team_manager.pk,
            self.employee.pk,
            self.colleague.pk,
            self.direct_employee.pk,
        }
        self.assertEqual(
            set(
                self.notifications(obj, "published").values_list(
                    "recipient_id", flat=True
                )
            ),
            expected_recipients,
        )
        self.assertEqual(
            self.notifications(obj, "published").count(), len(expected_recipients)
        )
        self.assertFalse(
            OutboxEvent.objects.filter(
                resource_type="announcement", resource_id=str(obj.pk)
            ).exists()
        )
        published = self.notifications(obj, "published").get(recipient=self.unit_head)
        data = self.inbox(self.unit_head)
        self.assertIn(str(published.pk), {row["id"] for row in data["results"]})
        self.assertNotIn(str(proposed.pk), {row["id"] for row in data["results"]})
        self.assertEqual(data["unread_count"], 1)
        self.assertEqual(self.inbox(self.outsider)["count"], 0)

    def test_publish_retry_does_not_duplicate_audience_notifications_or_audit(self):
        obj = self.propose()
        version = obj.version
        request_id = str(uuid.uuid4())
        first = self.publish(obj, request_id=request_id)
        count = self.notifications(obj, "published").count()
        repeated = self.client.post(
            f"/api/v1/announcements/{obj.pk}/publish/",
            {"version": version},
            format="json",
            HTTP_X_REQUEST_ID=request_id,
        )
        self.assertEqual(repeated.status_code, 200, repeated.content)
        self.assertEqual(repeated.json(), first.json())
        self.assertGreater(count, 0)
        self.assertEqual(self.notifications(obj, "published").count(), count)
        self.assertEqual(
            AuditEvent.objects.filter(
                action="announcement.published", object_id=str(obj.pk)
            ).count(),
            1,
        )

    def test_withdraw_or_expiry_hides_published_notification_and_blocks_its_old_link(
        self,
    ):
        obj = self.propose()
        self.publish(obj)
        notice = self.notifications(obj, "published").get(recipient=self.colleague)
        self.assertEqual(self.inbox(self.colleague)["count"], 1)
        Announcement.objects.filter(pk=obj.pk).update(
            ends_at=timezone.now() - timedelta(seconds=1)
        )
        self.assertEqual(self.inbox(self.colleague)["count"], 0)
        self.assertEqual(
            self.client.get(f"/api/v1/notifications/{notice.pk}/").status_code, 404
        )
        Announcement.objects.filter(pk=obj.pk).update(ends_at=None, status="WITHDRAWN")
        self.assertEqual(self.inbox(self.colleague)["count"], 0)
        self.assertEqual(
            self.client.post(
                f"/api/v1/notifications/{notice.pk}/read/", {}, format="json"
            ).status_code,
            404,
        )
        notice.refresh_from_db()
        self.assertIsNone(notice.read_at)

    def test_scheduled_publication_notification_stays_hidden_until_its_start(self):
        starts_at = timezone.now() + timedelta(days=1)
        obj = self.propose(starts_at=starts_at.isoformat())
        self.publish(obj)
        self.assertTrue(
            self.notifications(obj, "published")
            .filter(recipient=self.colleague)
            .exists()
        )
        self.assertEqual(self.inbox(self.colleague)["count"], 0)
        Announcement.objects.filter(pk=obj.pk).update(
            starts_at=timezone.now() - timedelta(seconds=1)
        )
        self.assertEqual(self.inbox(self.colleague)["count"], 1)

    def test_publication_failure_rolls_back_state_audit_and_new_notifications(self):
        obj = self.propose()
        before_notifications = set(Notification.objects.values_list("pk", flat=True))
        from core.views import audit as real_audit

        def fail_after_audit(actor, action, resource, data=None):
            real_audit(actor, action, resource, data)
            if action == "announcement.published":
                raise ValidationError("Synthetic persistence failure")

        with patch("core.views.audit", side_effect=fail_after_audit):
            response = self.as_user(self.unit_head).post(
                f"/api/v1/announcements/{obj.pk}/publish/",
                {"version": obj.version},
                format="json",
            )
        self.assertEqual(response.status_code, 400, response.content)
        obj.refresh_from_db()
        self.assertEqual(obj.status, "DRAFT")
        self.assertEqual(obj.version, 1)
        self.assertEqual(
            set(Notification.objects.values_list("pk", flat=True)), before_notifications
        )
        self.assertFalse(
            AuditEvent.objects.filter(
                action="announcement.published", object_id=str(obj.pk)
            ).exists()
        )
