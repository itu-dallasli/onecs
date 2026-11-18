"""Optional recipient mail keeps record access and durable delivery boundaries."""

import uuid
from datetime import timedelta
from unittest.mock import patch

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException

from core.models import (
    Announcement,
    Case,
    CaseNotice,
    CommunityCard,
    Credential,
    Event,
    Notification,
    OutboxEvent,
    Project,
    RecordEmailPreference,
    RoleGrant,
    WorkItem,
)
from core.policy import can_read_project, can_read_work
from core.record_notifications import (
    dispatch_record_email_preference,
    save_record_email_preference,
)
from core.services import enqueue_notification
from core.tests.base import OnecsTestCase
from core.worker import process_outbox


class RecordEmailPreferenceTests(OnecsTestCase):
    def work(self):
        return WorkItem.objects.create(
            title="Synthetic restricted work",
            description="Private work details must stay in the application",
            created_by=self.unit_head,
            assigned_to=self.employee,
            owner_org=self.team,
        )

    def project(self):
        return Project.objects.create(
            title="Synthetic private proposal",
            created_by=self.employee,
            owner_org=self.unit,
            appointment=self.appointment,
        )

    def announcement(self, **extra):
        obj = Announcement.objects.create(
            title="Synthetic announcement",
            body="A scoped announcement body",
            created_by=self.unit_head,
            owner_org=self.unit,
            **extra,
        )
        obj.audience.add(self.unit)
        return obj

    @staticmethod
    def payload(*recipients, send_email=True):
        return {
            "send_email": send_email,
            "notification_recipient_ids": [str(person.pk) for person in recipients],
        }

    @staticmethod
    def mail(resource_type, obj):
        return OutboxEvent.objects.filter(
            resource_type=resource_type, resource_id=str(obj.pk)
        )

    @staticmethod
    def notices(resource_type, obj):
        return Notification.objects.filter(
            resource_type=resource_type, resource_id=str(obj.pk)
        )

    def preference(self, resource_type, obj):
        return RecordEmailPreference.objects.get(
            resource_type=resource_type, resource_id=obj.pk
        )

    def test_omitted_preference_defaults_to_no_additional_email(self):
        work = self.work()
        save_record_email_preference(self.unit_head, "work", work, {})
        self.assertFalse(RecordEmailPreference.objects.exists())
        self.assertFalse(self.mail("work", work).exists())

    def test_direct_record_notifies_one_selected_authorized_recipient_once(self):
        work = self.work()
        payload = self.payload(self.team_manager)
        payload["notification_recipient_ids"] *= 2
        for _ in range(2):
            save_record_email_preference(self.unit_head, "work", work, payload)
        self.assertEqual(
            self.preference("work", work).recipient_ids, [str(self.team_manager.pk)]
        )
        self.assertEqual(self.mail("work", work).count(), 1)
        self.assertEqual(self.notices("work", work).count(), 1)
        self.assertEqual(self.mail("work", work).get().recipient_id, self.team_manager.pk)

    def test_invalid_preference_contract_rolls_back_new_record_and_delivery(self):
        invalid_payloads = (
            {"send_email": "true", "notification_recipient_ids": []},
            {"send_email": 1, "notification_recipient_ids": []},
            {"send_email": None, "notification_recipient_ids": []},
            {"send_email": True, "notification_recipient_ids": str(self.employee.pk)},
            {"send_email": True, "notification_recipient_ids": None},
            {"send_email": True, "notification_recipient_ids": ["invalid-uuid"]},
            {"send_email": True, "notification_recipient_ids": [None]},
            {"send_email": True, "notification_recipient_ids": [7]},
            {
                "send_email": True,
                "notification_recipient_ids": [str(uuid.uuid4()) for _ in range(21)],
            },
        )
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                work_id = None
                with self.assertRaises(APIException):
                    with transaction.atomic():
                        work = self.work()
                        work_id = work.pk
                        save_record_email_preference(self.unit_head, "work", work, payload)
                self.assertFalse(WorkItem.objects.filter(pk=work_id).exists())
                self.assertFalse(RecordEmailPreference.objects.exists())
                self.assertFalse(OutboxEvent.objects.exists())
                self.assertFalse(Notification.objects.exists())

    def test_unknown_resource_type_cannot_create_preference_or_delivery(self):
        work = self.work()
        with self.assertRaises(APIException):
            with transaction.atomic():
                save_record_email_preference(
                    self.unit_head, "unsupported", work, self.payload(self.employee)
                )
        self.assertFalse(RecordEmailPreference.objects.exists())
        self.assertFalse(OutboxEvent.objects.exists())

    def test_unknown_disabled_and_unauthorized_recipients_rollback_the_whole_create(self):
        self.colleague.is_active = False
        self.colleague.save(update_fields=["is_active"])
        for recipient_id in (self.outsider.pk, self.colleague.pk, uuid.uuid4()):
            with self.subTest(recipient_id=recipient_id):
                work_id = None
                with self.assertRaises(APIException):
                    with transaction.atomic():
                        work = self.work()
                        work_id = work.pk
                        save_record_email_preference(
                            self.unit_head,
                            "work",
                            work,
                            {
                                "send_email": True,
                                "notification_recipient_ids": [
                                    str(self.team_manager.pk),
                                    str(recipient_id),
                                ],
                            },
                        )
                self.assertFalse(WorkItem.objects.filter(pk=work_id).exists())
                self.assertFalse(RecordEmailPreference.objects.exists())
                self.assertFalse(OutboxEvent.objects.exists())
                self.assertFalse(Notification.objects.exists())

    def test_selecting_a_recipient_never_grants_record_access(self):
        work = self.work()
        self.assertFalse(can_read_work(self.outsider, work))
        with self.assertRaises(APIException):
            with transaction.atomic():
                save_record_email_preference(
                    self.unit_head, "work", work, self.payload(self.outsider)
                )
        self.assertFalse(can_read_work(self.outsider, work))
        self.assertFalse(self.mail("work", work).exists())

    def test_additional_email_opt_out_preserves_mandatory_assignment_notice_and_email(self):
        work = self.work()
        enqueue_notification(
            self.employee, "An assignment update", "work", work.pk, f"assign:{work.pk}:1"
        )
        save_record_email_preference(
            self.unit_head,
            "work",
            work,
            self.payload(self.team_manager, send_email=False),
        )
        self.assertFalse(self.preference("work", work).send_email)
        self.assertEqual(self.mail("work", work).count(), 1)
        self.assertEqual(self.mail("work", work).get().recipient_id, self.employee.pk)
        self.assertEqual(self.notices("work", work).count(), 1)

    def test_selected_mandatory_assignment_recipient_does_not_get_a_second_email(self):
        work = self.work()
        enqueue_notification(
            self.employee, "An assignment update", "work", work.pk, f"assign:{work.pk}:1"
        )
        save_record_email_preference(
            self.unit_head, "work", work, self.payload(self.employee)
        )
        self.assertEqual(self.mail("work", work).count(), 1)
        self.assertEqual(self.notices("work", work).count(), 1)

    def test_private_project_stores_prospective_pm_recipient_until_submission(self):
        project = self.project()
        self.assertFalse(can_read_project(self.pm, project))
        save_record_email_preference(
            self.employee, "project", project, self.payload(self.pm)
        )
        self.assertEqual(self.preference("project", project).recipient_ids, [str(self.pm.pk)])
        self.assertFalse(self.mail("project", project).exists())
        self.assertFalse(self.notices("project", project).exists())
        self.assertFalse(can_read_project(self.pm, project))

        project.status = "SUBMITTED"
        project.submitted_revision = 1
        project.save()
        dispatch_record_email_preference(self.employee, "project", project)
        dispatch_record_email_preference(self.employee, "project", project)
        self.assertTrue(can_read_project(self.pm, project))
        self.assertEqual(self.mail("project", project).count(), 1)

    def test_project_dispatch_deduplicates_the_mandatory_pm_submission_email(self):
        project = self.project()
        save_record_email_preference(
            self.employee, "project", project, self.payload(self.pm)
        )
        project.status = "SUBMITTED"
        project.save(update_fields=["status"])
        enqueue_notification(
            self.pm, "A proposal requires review", "project", project.pk, f"project-submit:{project.pk}:1"
        )
        dispatch_record_email_preference(self.employee, "project", project)
        self.assertEqual(self.mail("project", project).count(), 1)
        self.assertEqual(self.notices("project", project).count(), 1)

    def test_draft_announcement_and_community_preferences_do_not_send_early(self):
        announcement = self.announcement()
        card = CommunityCard.objects.create(
            title="Synthetic team update",
            body="This body requires publication",
            created_by=self.unit_head,
            owner_org=self.unit,
        )
        card.audience.add(self.unit)
        for resource_type, obj in (("announcement", announcement), ("community", card)):
            with self.subTest(resource_type=resource_type):
                save_record_email_preference(
                    self.unit_head, resource_type, obj, self.payload(self.employee)
                )
                dispatch_record_email_preference(self.unit_head, resource_type, obj)
                self.assertFalse(self.mail(resource_type, obj).exists())
                self.assertFalse(self.notices(resource_type, obj).exists())
                obj.status = "PUBLISHED"
                obj.save(update_fields=["status"])
                dispatch_record_email_preference(self.unit_head, resource_type, obj)
                self.assertEqual(self.mail(resource_type, obj).count(), 1)

    def test_scheduled_announcement_mail_is_due_at_publication_start(self):
        starts_at = timezone.now() + timedelta(days=1)
        obj = self.announcement(starts_at=starts_at)
        save_record_email_preference(
            self.unit_head, "announcement", obj, self.payload(self.employee)
        )
        self.assertFalse(self.mail("announcement", obj).exists())
        obj.status = "PUBLISHED"
        obj.save(update_fields=["status"])
        dispatch_record_email_preference(self.unit_head, "announcement", obj)
        mail = self.mail("announcement", obj).get()
        self.assertEqual(mail.next_attempt_at, starts_at)
        with patch("administration.services.deliver_email") as deliver:
            self.assertFalse(process_outbox())
        deliver.assert_not_called()

    def test_dispatch_skips_selected_person_who_left_the_publication_audience(self):
        obj = self.announcement()
        save_record_email_preference(
            self.unit_head, "announcement", obj, self.payload(self.employee)
        )
        self.employee.primary_org = self.other_unit
        self.employee.save(update_fields=["primary_org"])
        obj.status = "PUBLISHED"
        obj.save(update_fields=["status"])
        dispatch_record_email_preference(self.unit_head, "announcement", obj)
        obj.refresh_from_db()
        self.assertEqual(obj.status, "PUBLISHED")
        self.assertFalse(self.mail("announcement", obj).exists())

    def test_case_notice_event_and_credential_use_their_existing_reader_scope(self):
        case = Case.objects.create(
            title="Synthetic scoped incident",
            created_by=self.unit_head,
            coordinator=self.team_manager,
            owner_org=self.unit,
        )
        case.members.add(self.employee)
        notice = CaseNotice.objects.create(
            title="Synthetic incident notice",
            description="A synthetic report",
            created_by=self.employee,
            owner_org=self.team,
        )
        event = Event.objects.create(
            title="Synthetic incident workshop",
            created_by=self.unit_head,
            owner_org=self.unit,
        )
        event.invitees.add(self.employee)
        credential = Credential.objects.create(
            user=self.employee, name="Synthetic qualification", issuer="Test issuer"
        )
        cases = (
            ("case", case, self.employee),
            ("case_notice", notice, self.team_manager),
            ("event", event, self.employee),
            ("credential", credential, self.team_manager),
        )
        for resource_type, obj, recipient in cases:
            with self.subTest(resource_type=resource_type):
                save_record_email_preference(
                    self.unit_head, resource_type, obj, self.payload(recipient)
                )
                self.assertEqual(self.mail(resource_type, obj).count(), 1)
                self.assertEqual(self.mail(resource_type, obj).get().recipient_id, recipient.pk)
                with self.assertRaises(APIException):
                    with transaction.atomic():
                        save_record_email_preference(
                            self.unit_head, resource_type, obj, self.payload(self.outsider)
                        )
                self.assertEqual(self.mail(resource_type, obj).count(), 1)


class RecordMailWorkerTests(OnecsTestCase):
    @staticmethod
    def pending(resource_type, obj, recipient, **extra):
        return OutboxEvent.objects.create(
            key=f"optional-record:{uuid.uuid4()}:email",
            recipient=recipient,
            title="A record update is available",
            resource_type=resource_type,
            resource_id=str(obj.pk),
            **extra,
        )

    def announcement(self, **extra):
        obj = Announcement.objects.create(
            title="Synthetic published announcement",
            body="Synthetic announcement body",
            created_by=self.unit_head,
            owner_org=self.unit,
            status="PUBLISHED",
            **extra,
        )
        obj.audience.add(self.unit)
        return obj

    def assert_cancelled_without_smtp(self, event):
        with patch("administration.services.deliver_email") as deliver:
            self.assertTrue(process_outbox())
        deliver.assert_not_called()
        event.refresh_from_db()
        self.assertEqual(event.status, "CANCELLED")
        self.assertIsNone(event.lease_until)

    def test_current_authorized_published_recipient_is_delivered_through_mock_adapter(self):
        obj = self.announcement()
        event = self.pending("announcement", obj, self.employee)
        with patch("administration.services.deliver_email") as deliver:
            self.assertTrue(process_outbox())
        deliver.assert_called_once()
        self.assertEqual(deliver.call_args.args[0], self.employee.email)
        event.refresh_from_db()
        self.assertEqual(event.status, "SENT")
        self.assertIsNotNone(event.sent_at)

    def test_future_announcement_with_stale_due_time_is_deferred_without_smtp(self):
        starts_at = timezone.now() + timedelta(hours=2)
        obj = self.announcement(starts_at=starts_at)
        event = self.pending("announcement", obj, self.employee)
        with patch("administration.services.deliver_email") as deliver:
            self.assertTrue(process_outbox())
        deliver.assert_not_called()
        event.refresh_from_db()
        self.assertIn(event.status, ("PENDING", "RETRY"))
        self.assertEqual(event.next_attempt_at, starts_at)
        self.assertEqual(event.attempts, 0)
        self.assertIsNone(event.lease_until)

    def test_withdrawn_and_expired_announcements_cancel_already_queued_mail(self):
        for expired in (False, True):
            with self.subTest(expired=expired):
                obj = self.announcement()
                event = self.pending("announcement", obj, self.employee)
                if expired:
                    obj.ends_at = timezone.now() - timedelta(seconds=1)
                    obj.save(update_fields=["ends_at"])
                else:
                    obj.status = "WITHDRAWN"
                    obj.save(update_fields=["status"])
                self.assert_cancelled_without_smtp(event)

    def test_announcement_audience_revocation_cancels_already_queued_mail(self):
        obj = self.announcement()
        event = self.pending("announcement", obj, self.employee)
        obj.audience.set([self.other_unit])
        self.assert_cancelled_without_smtp(event)

    def test_removed_case_member_cannot_receive_pending_record_mail(self):
        obj = Case.objects.create(
            title="Synthetic coordinated case",
            created_by=self.unit_head,
            coordinator=self.team_manager,
            owner_org=self.unit,
        )
        obj.members.add(self.employee)
        event = self.pending("case", obj, self.employee)
        obj.members.remove(self.employee)
        self.assert_cancelled_without_smtp(event)

    def test_removed_event_invitee_cannot_receive_pending_record_mail(self):
        obj = Event.objects.create(
            title="Synthetic scoped meeting",
            created_by=self.unit_head,
            owner_org=self.unit,
        )
        obj.invitees.add(self.employee)
        event = self.pending("event", obj, self.employee)
        obj.invitees.remove(self.employee)
        self.assert_cancelled_without_smtp(event)

    def test_revoked_manager_cannot_receive_case_notice_or_credential_mail(self):
        notice = CaseNotice.objects.create(
            title="Synthetic case report",
            description="Synthetic report body",
            created_by=self.employee,
            owner_org=self.team,
        )
        credential = Credential.objects.create(
            user=self.employee, name="Synthetic credential", issuer="Synthetic issuer"
        )
        events = [
            self.pending("case_notice", notice, self.team_manager),
            self.pending("credential", credential, self.team_manager),
        ]
        RoleGrant.objects.filter(user=self.team_manager, role="TEAM_MANAGER").update(active=False)
        for event in events:
            with self.subTest(resource_type=event.resource_type):
                self.assert_cancelled_without_smtp(event)

    def test_withdrawn_community_card_cannot_deliver_pending_publication_mail(self):
        obj = CommunityCard.objects.create(
            title="Synthetic withdrawn card",
            body="Synthetic card body",
            created_by=self.unit_head,
            owner_org=self.unit,
            status="WITHDRAWN",
        )
        obj.audience.add(self.unit)
        event = self.pending("community", obj, self.employee)
        self.assert_cancelled_without_smtp(event)
