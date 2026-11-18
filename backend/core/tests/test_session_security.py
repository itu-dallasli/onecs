"""CSRF and current authorization also apply when replaying a safe retry."""

import uuid

from django.conf import settings
from rest_framework.test import APIClient

from core.models import IdempotencyRecord, WorkItem
from core.tests.base import OnecsTestCase


class SessionSecurityTests(OnecsTestCase):
    def test_product_authentication_names_are_consistent(self):
        self.assertEqual(settings.JWT_ISSUER, "onecs")
        self.assertEqual(settings.JWT_AUDIENCE, "onecs-readonly-api")
        self.assertEqual(settings.SESSION_COOKIE_NAME, "onecs_sessionid")
        self.assertEqual(settings.CSRF_COOKIE_NAME, "onecs_csrftoken")

    def csrf_client(self, user=None):
        client = APIClient(enforce_csrf_checks=True)
        if user:
            client.force_login(user)
        response = client.get("/api/v1/auth/csrf/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn(settings.CSRF_COOKIE_NAME, client.cookies)
        if user:
            self.assertIn(settings.SESSION_COOKIE_NAME, client.cookies)
        return client, response.json()["csrf_token"]

    def test_local_login_and_logout_obey_csrf_and_session_lifecycle(self):
        self.employee.set_password("Onecs-test-account-2026!")
        self.employee.save()
        client, token = self.csrf_client()
        payload = {
            "username": self.employee.username,
            "password": "Onecs-test-account-2026!",
            "method": "local",
        }
        denied = client.post("/api/v1/auth/login/", payload, format="json")
        self.assertEqual(denied.status_code, 403, denied.content)
        response = client.post(
            "/api/v1/auth/login/", payload, format="json", HTTP_X_CSRFTOKEN=token
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(client.get("/api/v1/auth/me/").status_code, 200)
        current_token = response.json()["csrf_token"]
        self.assertEqual(
            client.post(
                "/api/v1/auth/logout/",
                {},
                format="json",
                HTTP_X_CSRFTOKEN=current_token,
            ).status_code,
            200,
        )
        self.assertIn(client.get("/api/v1/auth/me/").status_code, (401, 403))

    def test_idempotency_replay_cannot_bypass_csrf(self):
        client, token = self.csrf_client(self.unit_head)
        request_id = str(uuid.uuid4())
        payload = {
            "title": "Session assignment",
            "assignee_id": str(self.employee.pk),
            "personal": False,
        }
        first = client.post(
            "/api/v1/work/",
            payload,
            format="json",
            HTTP_X_CSRFTOKEN=token,
            HTTP_X_REQUEST_ID=request_id,
        )
        self.assertEqual(first.status_code, 201, first.content)
        replay = client.post(
            "/api/v1/work/", payload, format="json", HTTP_X_REQUEST_ID=request_id
        )
        self.assertEqual(replay.status_code, 403, replay.content)
        self.assertEqual(WorkItem.objects.count(), 1)

    def test_idempotency_replay_checks_revoked_manager_grant(self):
        client, token = self.csrf_client(self.unit_head)
        request_id = str(uuid.uuid4())
        payload = {
            "title": "Previously authorized assignment",
            "assignee_id": str(self.employee.pk),
            "personal": False,
        }
        first = client.post(
            "/api/v1/work/",
            payload,
            format="json",
            HTTP_X_CSRFTOKEN=token,
            HTTP_X_REQUEST_ID=request_id,
        )
        self.assertEqual(first.status_code, 201, first.content)
        self.unit_head.role_grants.filter(role="UNIT_HEAD").update(active=False)
        replay = client.post(
            "/api/v1/work/",
            payload,
            format="json",
            HTTP_X_CSRFTOKEN=token,
            HTTP_X_REQUEST_ID=request_id,
        )
        self.assertEqual(replay.status_code, 403, replay.content)
        self.assertEqual(WorkItem.objects.count(), 1)
        self.assertEqual(IdempotencyRecord.objects.count(), 1)

    def test_invalid_retry_key_is_a_validation_error_and_creates_nothing(self):
        response = self.as_user(self.unit_head).post(
            "/api/v1/work/",
            {
                "title": "Invalid retry",
                "assignee_id": str(self.employee.pk),
                "personal": False,
            },
            format="json",
            HTTP_X_REQUEST_ID="not-a-request-uuid",
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertFalse(WorkItem.objects.exists())

    def test_disabled_account_loses_existing_session_immediately(self):
        self.as_user(self.employee)
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 200)
        self.employee.is_active = False
        self.employee.save()
        self.assertIn(self.client.get("/api/v1/auth/me/").status_code, (401, 403))
