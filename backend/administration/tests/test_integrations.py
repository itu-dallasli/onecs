import json
from unittest.mock import patch

from cryptography.fernet import Fernet
from django.test import TestCase, override_settings
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from core.models import OrgNode, RoleGrant, User
from administration.models import AIUsage, ConfigurationVersion, IntegrationConfiguration
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
            ONECS_ENCRYPTION_KEY=self.key,
            ONECS_ALLOWED_INTEGRATION_HOSTS="api.example.test,localhost",
            ONECS_ALLOW_PRIVATE_INTEGRATION_HOSTS="localhost",
        )
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.user = User.objects.create_user(
            username="admin", password="Onecs-Integration-123"
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

    def test_inherited_product_name_updates_without_rewriting_configuration_history(self):
        configuration = IntegrationConfiguration.objects.create(
            section="general", active_version=1
        )
        previous = ConfigurationVersion.objects.create(
            configuration=configuration,
            version=1,
            config={"application_name": "Previous product", "support_email": "old@example.test"},
            created_by=self.user,
        )
        self.assertEqual(
            public_configuration("general")["config"]["application_name"], "onecs"
        )
        result = update_configuration(
            self.user,
            "general",
            {"support_email": "new@example.test"},
            expected_version=1,
        )
        self.assertEqual(result["config"]["application_name"], "onecs")
        self.assertEqual(result["config"]["support_email"], "new@example.test")
        self.assertEqual(
            configuration.versions.get(version=2).config["application_name"], "onecs"
        )
        previous.refresh_from_db()
        self.assertEqual(previous.config["application_name"], "Previous product")
        self.assertEqual(previous.config["support_email"], "old@example.test")

    def test_product_name_accepts_current_brand_and_rejects_arbitrary_name(self):
        result = update_configuration(
            self.user, "general", {"application_name": "onecs"}, expected_version=0
        )
        self.assertEqual(result["config"]["application_name"], "onecs")
        self.assertEqual(
            ConfigurationVersion.objects.get().config["application_name"], "onecs"
        )
        with self.assertRaises(ValidationError) as caught:
            update_configuration(
                self.user,
                "general",
                {"application_name": "Other product"},
                expected_version=1,
            )
        self.assertIn("onecs", str(caught.exception.detail["application_name"]))
        self.assertEqual(ConfigurationVersion.objects.count(), 1)
        self.assertEqual(public_configuration("general")["version"], 1)

    def test_missing_encryption_key_is_not_silently_replaced(self):
        with override_settings(ONECS_ENCRYPTION_KEY=""):
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
        self.assertEqual(result["failure_code"], "invalid_citations")
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

    @patch("administration.security.socket.getaddrinfo", return_value=[(None, None, None, None, ("93.184.216.34", 0))])
    @patch("administration.services._ai_call")
    def test_success_attaches_system_inventory_when_model_text_omits_critical_source(self, call, dns):
        update_configuration(self.user, "ai", {"enabled": True, "base_url": "https://api.example.test/v1", "model": "unit-model"})
        original = "Haftalık çalışma kısa özeti."
        call.return_value = {"choices": [{"message": {"content": json.dumps({"text": original, "citations": ["ordinary-1"]})}}]}
        sources = [{"id": "ordinary-1", "title": "Normal çalışma"}, {"id": "critical-9", "title": "Kritik erişim aksiyonu"}]
        first = generate_ai_report(self.user, sources, request_id="source-index-job")
        second = generate_ai_report(self.user, sources, request_id="source-index-job")
        self.assertEqual(first["status"], "success", first)
        self.assertEqual(first["ai_original_text"], original)
        self.assertEqual(first["citations"], ["ordinary-1"])
        inventory, cited = first["markdown"].split("## AI tarafından atıf yapılanlar", 1)
        self.assertIn("## Dahil edilen kaynaklar (sistem kaydı)", inventory)
        self.assertIn("critical-9", inventory)
        self.assertIn("Kritik erişim aksiyonu", inventory)
        self.assertNotIn("critical-9", cited)
        self.assertIn("ordinary-1", cited)
        self.assertEqual(first, second)
        self.assertEqual(first["markdown"].count("## Dahil edilen kaynaklar (sistem kaydı)"), 1)
        self.assertEqual(call.call_count, 1)

    @patch("administration.security.socket.getaddrinfo", return_value=[(None, None, None, None, ("93.184.216.34", 0))])
    @patch("administration.services._ai_call")
    def test_project_brief_compacts_evidence_and_preserves_valid_metrics_within_configured_limit(self, call, dns):
        update_configuration(self.user, "ai", {"enabled": True, "base_url": "https://api.example.test/v1", "model": "unit-model", "max_input_tokens": 6000, "max_output_tokens": 4096})
        metrics = {"delivery": 76.25, "quality": None, "overall": None, "coverage": {"teams": 4, "deliverables": 18, "quality_rated": 9}, "formula": "Eksik kanıtla kesin başarı puanı üretilmez."}
        metrics_json = json.dumps(metrics, ensure_ascii=False)
        sources = [{"id": "project:metrics", "title": "Hesaplanan ölçümler", "type": "project_metrics", "status": "DETERMINISTIC", "summary": metrics_json}]
        sources.extend({"id": f"00000000-0000-0000-0000-{index:012d}", "title": "Kapsamlı teslimat başlığı " * 12, "type": "project_deliverable", "status": "RECORDED", "summary": "Güvenlik değerlendirmesinin tam kaynak kanıtı korunur. " * 30} for index in range(1, 20))
        call.return_value = {"choices": [{"message": {"content": json.dumps({"text": "Kısa yönetici taslağı.", "citations": ["project:metrics"]})}}]}
        result = generate_ai_report(self.user, sources, report_kind="PROJECT_WEEKLY", request_id="compact-project-brief")
        self.assertEqual(result["status"], "success", result)
        config, _, messages, output_limit = call.call_args.args
        self.assertEqual(config["max_input_tokens"], 6000)
        self.assertEqual(config["max_output_tokens"], 4096)
        self.assertEqual(output_limit, 4096)
        self.assertLessEqual(sum(len(message["content"].encode()) for message in messages) + 100, 6000)
        compact_sources = json.loads(messages[1]["content"])
        compact_metrics = next(source for source in compact_sources if source["type"] == "project_metrics")
        self.assertEqual(json.loads(compact_metrics["summary"]), metrics)
        self.assertEqual(compact_metrics["summary"], metrics_json)
        self.assertTrue(all(len(source["summary"]) <= 180 for source in compact_sources if source["type"] != "project_metrics"))
        self.assertTrue(result["context_abridged"])
        self.assertEqual(len(result["included_sources"]), len(sources))
        self.assertTrue(all(source["id"] in result["markdown"] for source in sources))
        self.assertIn("tam kaynak kanıtı", sources[1]["summary"])
        call.reset_mock()
        weekly = generate_ai_report(self.user, sources, report_kind="weekly", request_id="unchanged-weekly-limit")
        self.assertEqual(weekly["status"], "input_limit")
        call.assert_not_called()

    @patch("administration.security.socket.getaddrinfo", return_value=[(None, None, None, None, ("93.184.216.34", 0))])
    @patch("administration.services._ai_call")
    def test_project_truncated_output_has_safe_diagnostics_without_retrying_unknown_usage(self, call, dns):
        update_configuration(self.user, "ai", {"enabled": True, "base_url": "https://api.example.test/v1", "model": "unit-model", "max_output_tokens": 4096})
        raw = '{"text":"provider-private-marker-with-secret-value'
        call.return_value = {"choices": [{"finish_reason": "length", "message": {"content": raw, "reasoning_content": "private-reasoning"}}]}
        sources = [{"id": "project:metrics", "type": "project_metrics", "title": "Ölçümler", "summary": '{"coverage":null}'}]
        result = generate_ai_report(self.user, sources, report_kind="PROJECT_CLOSURE", request_id="truncated-project-job")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["mode"], "RULE_BASED")
        self.assertEqual(result["failure_code"], "output_truncated")
        self.assertEqual(result["provider_diagnostics"], {"finish_reason": "length", "content_characters": len(raw), "valid_json": None})
        self.assertEqual(result["ai_context"]["output_token_limit"], 4096)
        self.assertEqual(call.call_args.args[3], 4096)
        self.assertIn("150 kelime ve 3 kaynak atfı", call.call_args.args[2][0]["content"])
        self.assertNotIn("provider-private-marker", json.dumps(result))
        self.assertNotIn("private-reasoning", json.dumps(result))
        usage = AIUsage.objects.get()
        self.assertEqual(usage.status, "unknown")
        self.assertGreater(usage.reserved_tokens, 0)
        self.assertEqual(generate_ai_report(self.user, sources, report_kind="PROJECT_CLOSURE", request_id="truncated-project-job"), result)
        self.assertEqual(call.call_count, 1)

    @patch("administration.security.socket.getaddrinfo", return_value=[(None, None, None, None, ("93.184.216.34", 0))])
    @patch("administration.services._ai_call")
    def test_weekly_output_limit_is_unchanged_and_invalid_json_is_identified_safely(self, call, dns):
        update_configuration(self.user, "ai", {"enabled": True, "base_url": "https://api.example.test/v1", "model": "unit-model", "max_output_tokens": 4096})
        call.return_value = {"choices": [{"finish_reason": "stop", "message": {"content": "private-invalid-json"}}]}
        result = generate_ai_report(self.user, [{"id": "work-1", "title": "İş"}], report_kind="weekly")
        self.assertEqual(call.call_args.args[3], 4096)
        self.assertEqual(result["failure_code"], "invalid_json")
        self.assertEqual(result["provider_diagnostics"], {"finish_reason": "stop", "content_characters": 20, "valid_json": False})
        self.assertNotIn("private-invalid-json", json.dumps(result))

    def test_empty_ldap_password_never_authenticates(self):
        self.assertIsNone(authenticate_ldap("admin", ""))


class AdministrationAPITests(TestCase):
    def setUp(self):
        self.org = OrgNode.objects.create(
            code="ICT-CS", name="Cyber Security", kind="DIRECTORATE"
        )
        self.admin = User.objects.create_user(
            username="technical", password="Onecs-Technical-123", primary_org=self.org
        )
        self.employee = User.objects.create_user(
            username="employee", password="Onecs-Employee-123", primary_org=self.org
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
                "password": "Onecs-New-Account-987",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertNotIn("password", response.data)
        created = User.objects.get(username="new-person")
        self.assertTrue(created.check_password("Onecs-New-Account-987"))
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
        with override_settings(ONECS_ENCRYPTION_KEY=Fernet.generate_key().decode()):
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

    def test_failed_project_insight_retry_reopens_report_with_same_pinned_job(self):
        from django.utils import timezone
        from core.models import BackgroundJob, PMAppointment, Project, ProjectInsightReport

        appointment = PMAppointment.objects.create(user=self.employee, governing_org=self.org)
        project = Project.objects.create(title="Synthetic project", created_by=self.employee, owner_org=self.org, appointment=appointment, status="ACTIVE")
        job = BackgroundJob.objects.create(actor=self.employee, kind="PROJECT_INSIGHT", status="FAILED", attempts=3, payload={"ai_profile_id": None, "ai_configuration_version": 0, "ai_settings_version": 0})
        report = ProjectInsightReport.objects.create(project=project, created_by=self.employee, kind="WEEKLY", period_start=timezone.localdate(), period_end=timezone.localdate(), status="FAILED", source_hash="synthetic-hash", job=job)
        original_payload = dict(job.payload)
        original_version = report.version
        self.client.force_authenticate(self.admin)
        response = self.client.post(f"/api/v1/admin/jobs/{job.pk}/retry/", {"kind": "job"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        job.refresh_from_db()
        report.refresh_from_db()
        self.assertEqual((job.status, job.attempts), ("PENDING", 0))
        self.assertEqual(report.status, "GENERATING")
        self.assertEqual(report.job_id, job.pk)
        self.assertEqual(report.version, original_version)
        self.assertEqual(job.payload, original_payload)
