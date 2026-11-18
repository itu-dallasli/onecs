import json
from unittest.mock import patch

from cryptography.fernet import Fernet
from django.test import TestCase, override_settings
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from core.models import OrgNode, RoleGrant, User
from administration.models import AIUsage, ConfigurationVersion
from administration.security import (
    decrypt_secrets,
    encrypt_secrets,
    validate_destination,
)
from administration.services import (
    authenticate_ldap,
    generate_ai_report,
    public_configuration,
    test_integration as run_integration_test,
    update_configuration,
)


class IntegrationServiceTests(TestCase):
    def setUp(self):
        self.key = Fernet.generate_key().decode()
        self.override = override_settings(
            ATLAS_ENCRYPTION_KEY=self.key,
            ATLAS_ALLOWED_INTEGRATION_HOSTS="api.example.test,localhost",
            ATLAS_ALLOW_PRIVATE_INTEGRATION_HOSTS="localhost",
        )
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.user = User.objects.create_user(
            username="admin", password="Atlas-Integration-123"
        )

    def test_secret_encryption_and_no_plaintext_readback(self):
        update_configuration(
            self.user, "ai", {"model": "test"}, {"api_key": "secret-never-read-back"}, 0
        )
        stored = ConfigurationVersion.objects.get()
        self.assertNotIn("secret-never-read-back", stored.encrypted_secrets)
        self.assertEqual(
            decrypt_secrets(stored.encrypted_secrets)["api_key"],
            "secret-never-read-back",
        )
        self.assertNotIn(
            "secret-never-read-back", json.dumps(public_configuration("ai"))
        )
        self.assertEqual(public_configuration("ai")["secret_fields"], ["api_key"])

    def test_stale_configuration_version_rejected(self):
        update_configuration(
            self.user,
            "general",
            {"support_email": "one@example.test"},
            expected_version=0,
        )
        with self.assertRaises(ValidationError):
            update_configuration(
                self.user,
                "general",
                {"support_email": "two@example.test"},
                expected_version=0,
            )
        self.assertEqual(
            public_configuration("general")["config"]["support_email"],
            "one@example.test",
        )

    def test_missing_encryption_key_is_not_silently_replaced(self):
        with override_settings(ATLAS_ENCRYPTION_KEY=""):
            with self.assertRaises(ValidationError):
                encrypt_secrets({"api_key": "nope"})

    def test_disabled_integration_reports_unconfigured(self):
        result = run_integration_test(self.user, "ai")
        self.assertEqual(result["status"], "unconfigured")
        self.assertEqual(AIUsage.objects.count(), 0)

    def test_no_plain_ldap_or_unapproved_network(self):
        # LDAP/389 is allowed only when the configuration requires verified StartTLS.
        with patch("administration.security.socket.getaddrinfo", return_value=[(None, None, None, None, ("127.0.0.1", 0))]):
            with self.assertRaises(ValidationError):
                update_configuration(self.user, "ldap", {"enabled": True, "url": "ldap://localhost:389", "bind_dn": "service", "start_tls": False})
        with self.assertRaises(ValidationError):
            validate_destination("169.254.169.254")
        with patch(
            "administration.security.socket.getaddrinfo",
            return_value=[(None, None, None, None, ("127.0.0.1", 0))],
        ):
            with self.assertRaises(ValidationError):
                validate_destination("api.example.test")
            self.assertEqual(
                validate_destination("localhost", scheme="http"), "localhost"
            )

    @patch(
        "administration.security.socket.getaddrinfo",
        return_value=[(None, None, None, None, ("93.184.216.34", 0))],
    )
    @patch("administration.services._ai_call")
    def test_ai_measured_usage_cost_and_citations(self, call, dns):
        update_configuration(
            self.user,
            "ai",
            {
                "enabled": True,
                "base_url": "https://api.example.test/v1",
                "model": "unit-model",
                "input_price_per_million": "2",
                "output_price_per_million": "4",
            },
        )
        call.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {"text": "İş tamamlandı [work-1]", "citations": ["work-1"]}
                        )
                    }
                }
            ],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50},
        }
        result = generate_ai_report(
            self.user, [{"id": "work-1", "title": "Güvenlik işi"}]
        )
        self.assertEqual(result["status"], "success")
        usage = AIUsage.objects.get()
        self.assertEqual(usage.measurement, "provider")
        self.assertEqual(str(usage.estimated_cost), "0.00040000")
        self.assertEqual(usage.reserved_tokens, 150)

    @patch(
        "administration.security.socket.getaddrinfo",
        return_value=[(None, None, None, None, ("93.184.216.34", 0))],
    )
    @patch("administration.services._ai_call")
    def test_invented_citation_is_rejected_and_unknown_cost_retained(self, call, dns):
        update_configuration(
            self.user,
            "ai",
            {
                "enabled": True,
                "base_url": "https://api.example.test",
                "model": "unit-model",
            },
        )
        call.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {"text": "Unsupported", "citations": ["hidden-id"]}
                        )
                    }
                }
            ]
        }
        result = generate_ai_report(
            self.user, [{"id": "allowed-id", "title": "Allowed"}]
        )
        self.assertEqual(result["status"], "failed")
        usage = AIUsage.objects.get()
        self.assertEqual(usage.status, "unknown")
        self.assertIsNone(usage.input_tokens)
        self.assertIsNone(usage.estimated_cost)
        self.assertGreater(usage.reserved_tokens, 0)

    @patch(
        "administration.security.socket.getaddrinfo",
        return_value=[(None, None, None, None, ("93.184.216.34", 0))],
    )
    def test_budget_blocks_provider_before_call(self, dns):
        update_configuration(
            self.user,
            "ai",
            {
                "enabled": True,
                "base_url": "https://api.example.test",
                "model": "unit-model",
                "daily_token_limit": 5,
            },
        )
        with patch("administration.services._ai_call") as call:
            result = generate_ai_report(self.user, [{"id": "work-1", "title": "Task"}])
            self.assertEqual(result["status"], "budget_or_request_limit")
            self.assertEqual(result["mode"], "RULE_BASED")
            call.assert_not_called()

    @patch(
        "administration.security.socket.getaddrinfo",
        return_value=[(None, None, None, None, ("93.184.216.34", 0))],
    )
    @patch("administration.services._ai_call")
    def test_job_retry_reuses_result_without_second_provider_charge(self, call, dns):
        update_configuration(
            self.user,
            "ai",
            {
                "enabled": True,
                "base_url": "https://api.example.test",
                "model": "unit-model",
            },
        )
        call.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {"text": "Taslak", "citations": ["work-1"]}
                        )
                    }
                }
            ]
        }
        sources = [{"id": "work-1", "title": "Task", "version": 2}]
        first = generate_ai_report(self.user, sources, request_id="job-123")
        second = generate_ai_report(self.user, sources, request_id="job-123")
        self.assertEqual(first, second)
        self.assertEqual(call.call_count, 1)
        self.assertEqual(AIUsage.objects.count(), 1)

    def test_empty_ldap_password_never_authenticates(self):
        self.assertIsNone(authenticate_ldap("admin", ""))


class AdministrationAPITests(TestCase):
    def setUp(self):
        self.org = OrgNode.objects.create(
            code="ICT-CS", name="Cyber Security", kind="DIRECTORATE"
        )
        self.admin = User.objects.create_user(
            username="technical", password="Atlas-Technical-123", primary_org=self.org
        )
        self.employee = User.objects.create_user(
            username="employee", password="Atlas-Employee-123", primary_org=self.org
        )
        RoleGrant.objects.create(user=self.admin, role="SYSTEM_ADMIN")
        RoleGrant.objects.create(user=self.employee, role="EMPLOYEE", org_node=self.org)
        self.client = APIClient()

    def test_employee_cannot_read_secrets_or_change_settings(self):
        self.client.force_authenticate(self.employee)
        self.assertEqual(self.client.get("/api/v1/admin/settings/ai/").status_code, 403)
        self.assertEqual(
            self.client.patch(
                "/api/v1/admin/settings/general/", {"config": {}}, format="json"
            ).status_code,
            403,
        )

    def test_root_settings_patch_requires_section_instead_of_crashing(self):
        self.client.force_authenticate(self.admin)
        response = self.client.patch(
            "/api/v1/admin/settings/", {"config": {}}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("section", response.data)

    def test_user_profile_stale_version_does_not_overwrite_current_record(self):
        self.client.force_authenticate(self.admin)
        version = self.employee.access_version
        first = self.client.patch(
            f"/api/v1/admin/users/{self.employee.pk}/",
            {"display_name": "Current Name", "expected_access_version": version},
            format="json",
        )
        self.assertEqual(first.status_code, 200, first.data)
        second = self.client.patch(
            f"/api/v1/admin/users/{self.employee.pk}/",
            {"display_name": "Old Editor Name", "expected_access_version": version},
            format="json",
        )
        self.assertEqual(second.status_code, 409)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.display_name, "Current Name")

    def test_admin_cannot_self_elevate_or_grant_business_role(self):
        self.client.force_authenticate(self.admin)
        response = self.client.patch(
            f"/api/v1/admin/users/{self.admin.pk}/",
            {"roles": [{"role": "DIRECTOR", "org_node": str(self.org.pk)}]},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        response = self.client.patch(
            f"/api/v1/admin/users/{self.employee.pk}/",
            {"roles": [{"role": "UNIT_HEAD", "org_node": str(self.org.pk)}]},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            self.employee.role_grants.filter(role="UNIT_HEAD", active=True).exists()
        )

    def test_safe_user_create_and_password_never_returned(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            "/api/v1/admin/users/",
            {
                "username": "new-person",
                "display_name": "New Person",
                "email": "new@example.test",
                "primary_org": str(self.org.pk),
                "password": "Atlas-New-Account-987",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertNotIn("password", response.data)
        created = User.objects.get(username="new-person")
        self.assertTrue(created.check_password("Atlas-New-Account-987"))
        self.assertTrue(created.role_grants.filter(role="EMPLOYEE").exists())

    def test_explicit_technical_and_director_authority_can_manage_other_users_roles(
        self,
    ):
        RoleGrant.objects.create(user=self.admin, role="DIRECTOR", org_node=self.org)
        self.client.force_authenticate(self.admin)
        response = self.client.patch(
            f"/api/v1/admin/users/{self.employee.pk}/",
            {
                "expected_access_version": self.employee.access_version,
                "roles": [
                    {"role": "EMPLOYEE", "org_node": str(self.org.pk)},
                    {"role": "UNIT_HEAD", "org_node": str(self.org.pk)},
                ],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(
            self.employee.role_grants.filter(role="UNIT_HEAD", active=True).exists()
        )
        own = self.client.patch(
            f"/api/v1/admin/users/{self.admin.pk}/",
            {"roles": [{"role": "DIRECTOR", "org_node": str(self.org.pk)}]},
            format="json",
        )
        self.assertEqual(own.status_code, 403)

    def test_settings_update_audited_without_secrets(self):
        self.client.force_authenticate(self.admin)
        with override_settings(ATLAS_ENCRYPTION_KEY=Fernet.generate_key().decode()):
            response = self.client.patch(
                "/api/v1/admin/settings/ai/",
                {
                    "config": {"model": "test"},
                    "secrets": {"api_key": "secret-test"},
                    "expected_version": 0,
                },
                format="json",
            )
        self.assertEqual(response.status_code, 200, response.data)
        from core.models import AuditEvent

        event = AuditEvent.objects.get(action="integration.configuration.updated")
        self.assertNotIn("secret-test", json.dumps(event.data))

    def test_jobs_metadata_excludes_payload_and_running_retry_rejected(self):
        from core.models import BackgroundJob

        job = BackgroundJob.objects.create(
            actor=self.employee,
            kind="REPORT",
            status="RUNNING",
            payload={"restricted": "private-report-content"},
        )
        self.client.force_authenticate(self.admin)
        response = self.client.get("/api/v1/admin/jobs/")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(
            "private-report-content", json.dumps(response.data, default=str)
        )
        response = self.client.post(
            f"/api/v1/admin/jobs/{job.pk}/retry/", {"kind": "job"}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        job.refresh_from_db()
        self.assertEqual(job.status, "RUNNING")

    def test_unknown_delivery_requires_explicit_acknowledgment(self):
        from core.models import OutboxEvent, AuditEvent

        event = OutboxEvent.objects.create(
            recipient=self.employee,
            key="delivery-unknown",
            title="Private title",
            resource_type="work",
            resource_id="123",
            status="UNKNOWN",
            attempts=2,
        )
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            f"/api/v1/admin/jobs/{event.pk}/retry/", {"kind": "outbox"}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        event.refresh_from_db()
        self.assertEqual(event.status, "UNKNOWN")
        response = self.client.post(
            f"/api/v1/admin/jobs/{event.pk}/retry/",
            {
                "kind": "outbox",
                "acknowledge_unknown": True,
                "reason": "Posta servisi kontrol edildi",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        event.refresh_from_db()
        self.assertEqual((event.status, event.attempts), ("PENDING", 0))
        self.assertTrue(
            AuditEvent.objects.filter(action="operations.manual_retry").exists()
        )

    def test_failed_job_retried_once_and_stale_second_retry_rejected(self):
        from core.models import BackgroundJob

        job = BackgroundJob.objects.create(
            actor=self.employee, kind="REPORT", status="FAILED", attempts=3
        )
        self.client.force_authenticate(self.admin)
        first = self.client.post(
            f"/api/v1/admin/jobs/{job.pk}/retry/", {"kind": "job"}, format="json"
        )
        second = self.client.post(
            f"/api/v1/admin/jobs/{job.pk}/retry/", {"kind": "job"}, format="json"
        )
        self.assertEqual(first.status_code, 200, first.data)
        self.assertEqual(second.status_code, 400)
        job.refresh_from_db()
        self.assertEqual(job.status, "PENDING")
