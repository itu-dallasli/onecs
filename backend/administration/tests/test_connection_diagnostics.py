"""Safe connection diagnostics using synthetic transport errors only.

These checks exercise error classification, policy and persisted readiness. They
do not establish connectivity to any real directory or model service.
"""

import json
import os
import socket
import ssl
from unittest.mock import Mock, patch

import httpx
from django.test import SimpleTestCase
from ldap3.core.exceptions import LDAPBindError, LDAPSocketSendError, LDAPStartTLSError
from rest_framework.exceptions import ValidationError

from administration.diagnostics import connection_failure_message
from administration.models import AIUsage, ConfigurationVersion, IntegrationTest
from administration.services import _ai_call, _ldap_connection, update_configuration
from administration.tests.test_directory_profiles import DirectoryProfileFixtures
from core.models import AuditEvent


SECRET_MARKER = "synthetic-diagnostic-secret-never-expose"
BODY_MARKER = "synthetic-provider-body-never-expose"
RAW_URL = f"https://api.example.test/private-diagnostic-path?token={SECRET_MARKER}"


def certificate_error(code, reason):
    error = ssl.SSLCertVerificationError(
        1, f"certificate verify failed: {reason}; {SECRET_MARKER}; {RAW_URL}"
    )
    error.verify_code = code
    error.verify_message = reason
    return error


def http_status_error(status):
    request = httpx.Request(
        "POST", RAW_URL, headers={"Authorization": f"Bearer {SECRET_MARKER}"}
    )
    response = httpx.Response(
        status, request=request, json={"error": BODY_MARKER, "key": SECRET_MARKER}
    )
    return httpx.HTTPStatusError(
        f"HTTP {status}: {RAW_URL}; {BODY_MARKER}; {SECRET_MARKER}",
        request=request,
        response=response,
    )


class ConnectionFailureMessageTests(SimpleTestCase):
    def assert_safe_message(self, message):
        self.assertIsInstance(message, str)
        self.assertTrue(message)
        self.assertLessEqual(len(message), 350)
        for private_value in (SECRET_MARKER, BODY_MARKER, RAW_URL, "ErrorDetail("):
            self.assertNotIn(private_value, message)

    def test_tls_certificate_causes_are_distinct_and_never_echo_remote_details(self):
        examples = (
            (10, "certificate has expired", "süresi dolmuş"),
            (9, "certificate is not yet valid", "henüz geçerli değil"),
            (20, "unable to get local issuer certificate", "zincirine güvenilemiyor"),
            (62, "hostname mismatch", "adıyla eşleşmiyor"),
        )
        messages = []
        for code, reason, expected in examples:
            for section in ("ldap", "ai"):
                with self.subTest(code=code, section=section):
                    message = connection_failure_message(
                        certificate_error(code, reason), section
                    )
                    self.assert_safe_message(message)
                    self.assertIn(expected, message)
                    if section == "ldap":
                        messages.append(message)
        self.assertEqual(len(set(messages)), len(examples))

    def test_ldap_sdk_wrapper_retains_expired_certificate_diagnosis(self):
        error = LDAPStartTLSError(
            f"wrap socket error: certificate has expired; {SECRET_MARKER}"
        )
        message = connection_failure_message(error, "ldap")
        self.assert_safe_message(message)
        self.assertIn("süresi dolmuş", message)

    def test_httpx_exception_chain_retains_certificate_diagnosis(self):
        error = httpx.ConnectError(f"TLS connection failed: {RAW_URL}")
        error.__cause__ = certificate_error(10, "certificate has expired")
        message = connection_failure_message(error, "ai")
        self.assert_safe_message(message)
        self.assertIn("süresi dolmuş", message)

    def test_dns_timeout_and_bind_failures_have_separate_safe_guidance(self):
        examples = (
            (socket.gaierror(-2, f"Name or service not known: {SECRET_MARKER}"), "DNS"),
            (httpx.ReadTimeout(f"timed out: {SECRET_MARKER}"), "zaman aşımı"),
            (LDAPBindError(f"invalid credentials: {SECRET_MARKER}"), "bind"),
        )
        messages = []
        for error, expected in examples:
            with self.subTest(kind=type(error).__name__):
                message = connection_failure_message(error, "ldap")
                self.assert_safe_message(message)
                self.assertIn(expected, message)
                messages.append(message)
        self.assertEqual(len(set(messages)), len(examples))

    def test_http_status_guidance_keeps_only_safe_status_and_action(self):
        examples = (
            (401, "anahtar"),
            (403, "yetki"),
            (404, "model"),
            (429, "kota"),
            (500, "sunucu"),
            (503, "sunucu"),
        )
        for status, expected in examples:
            with self.subTest(status=status):
                message = connection_failure_message(http_status_error(status), "ai")
                self.assert_safe_message(message)
                self.assertIn(str(status), message)
                self.assertIn(expected, message.lower())

    def test_application_validation_is_plain_text_instead_of_error_detail_repr(self):
        message = connection_failure_message(
            ValidationError({"ldap": ["Servis bağlandı; Base DN okunamadı."]}),
            "ldap",
        )
        self.assertEqual(message, "Servis bağlandı; Base DN okunamadı.")
        self.assert_safe_message(message)

    def test_unknown_transport_error_does_not_expose_exception_text(self):
        message = connection_failure_message(
            RuntimeError(f"{RAW_URL}; {BODY_MARKER}; {SECRET_MARKER}"), "ai"
        )
        self.assert_safe_message(message)
        self.assertIn("bağlantısı doğrulanamadı", message)


class AITransportTrustTests(SimpleTestCase):
    config = {
        "base_url": "https://api.example.test/v1",
        "model": "synthetic-trust-model",
    }

    def test_custom_ca_context_preserves_certificate_and_hostname_verification(self):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ca_path = "/synthetic/private-trust/synthetic-ca-bundle.pem"
        with (
            patch.dict(os.environ, {"ONECS_AI_CA_FILE": ca_path}, clear=True),
            patch("administration.services.validate_url"),
            patch(
                "administration.services.ssl.create_default_context",
                return_value=context,
            ) as create_context,
            patch("administration.services.httpx.Client") as client,
        ):
            _ai_call(self.config, {"api_key": SECRET_MARKER}, [], 8)
        create_context.assert_called_once_with(cafile=ca_path)
        verification = client.call_args.kwargs["verify"]
        self.assertIs(verification, context)
        self.assertEqual(verification.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(verification.check_hostname)
        self.assertIs(client.call_args.kwargs["trust_env"], False)
        self.assertIs(client.call_args.kwargs["follow_redirects"], False)
        client.return_value.__enter__.return_value.post.assert_called_once()

    def test_missing_or_invalid_ca_bundle_stops_before_http_without_path_disclosure(self):
        ca_path = f"/synthetic/private-trust/{SECRET_MARKER}.pem"
        for error in (
            FileNotFoundError(f"No such file: {ca_path}"),
            ssl.SSLError(f"invalid CA bundle: {ca_path}"),
        ):
            with self.subTest(kind=type(error).__name__):
                with (
                    patch.dict(os.environ, {"ONECS_AI_CA_FILE": ca_path}, clear=True),
                    patch("administration.services.validate_url"),
                    patch(
                        "administration.services.ssl.create_default_context",
                        side_effect=error,
                    ),
                    patch("administration.services.httpx.Client") as client,
                ):
                    with self.assertRaises(ValidationError) as caught:
                        _ai_call(self.config, {"api_key": SECRET_MARKER}, [], 8)
                client.assert_not_called()
                client.return_value.__enter__.return_value.post.assert_not_called()
                message = connection_failure_message(caught.exception, "ai")
                self.assertIn("TLS CA dosyası okunamadı", message)
                self.assertNotIn(ca_path, message)
                self.assertNotIn(SECRET_MARKER, message)
                self.assertNotIn("ErrorDetail(", message)

    def test_default_ca_verification_remains_enabled_without_env_proxy_or_redirects(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("administration.services.validate_url"),
            patch("administration.services.ssl.create_default_context") as create_context,
            patch("administration.services.httpx.Client") as client,
        ):
            _ai_call(self.config, {"api_key": SECRET_MARKER}, [], 8)
        create_context.assert_not_called()
        self.assertIs(client.call_args.kwargs["verify"], True)
        self.assertIs(client.call_args.kwargs["trust_env"], False)
        self.assertIs(client.call_args.kwargs["follow_redirects"], False)
        client.return_value.__enter__.return_value.post.assert_called_once()


class LDAPConnectionDiagnosticAPITests(DirectoryProfileFixtures):
    def test_expired_starttls_never_binds_and_cleanup_cannot_replace_reason(self):
        connection = Mock()
        connection.open.return_value = True
        connection.start_tls.side_effect = certificate_error(
            10, "certificate has expired"
        )
        connection.unbind.side_effect = LDAPSocketSendError(SECRET_MARKER)
        with (
            patch("ldap3.Connection", return_value=connection),
            patch("ldap3.Server"),
            patch("ldap3.Tls"),
        ):
            with self.assertRaises(ValidationError) as caught:
                _ldap_connection(
                    {
                        "url": "ldap://directory.example.test:389",
                        "start_tls": True,
                        "bind_dn": "cn=synthetic-reader,dc=example,dc=test",
                    },
                    {"bind_password": SECRET_MARKER},
                )
        connection.bind.assert_not_called()
        connection.unbind.assert_called_once()
        message = connection_failure_message(caught.exception, "ldap")
        self.assertIn("süresi dolmuş", message)
        self.assertNotIn(SECRET_MARKER, message)
        self.assertNotIn("ErrorDetail(", message)

    def test_ldap_failure_message_is_persisted_and_exposed_without_error_repr(self):
        self.configure_directory()
        connection = Mock()
        connection.open.return_value = True
        connection.start_tls.side_effect = certificate_error(
            10, "certificate has expired"
        )
        with (
            patch("ldap3.Connection", return_value=connection),
            patch("ldap3.Server"),
            patch("ldap3.Tls"),
        ):
            response = self.client.post(
                "/api/v1/admin/integrations/ldap/test/", {}, format="json"
            )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(response.data["status"], "failure")
        self.assertIsInstance(response.data["message"], str)
        self.assertIn("süresi dolmuş", response.data["message"])
        connection.bind.assert_not_called()
        saved = IntegrationTest.objects.get(configuration__section="ldap")
        self.assertEqual(saved.message, response.data["message"])
        self.assertEqual(saved.checked_by_id, self.admin.pk)
        self.assertEqual(saved.configuration_version, 1)
        current = self.client.get("/api/v1/admin/settings/ldap/")
        self.assertEqual(current.status_code, 200)
        self.assertFalse(current.data["ready"])
        self.assertEqual(current.data["latest_test"]["message"], saved.message)
        public_result = json.dumps(response.data, default=str)
        public_result += json.dumps(current.data, default=str)
        self.assertNotIn(SECRET_MARKER, public_result)
        self.assertNotIn(RAW_URL, public_result)
        self.assertNotIn("ErrorDetail(", public_result)

    def test_employee_cannot_run_ldap_test_or_create_connection_evidence(self):
        self.configure_directory()
        self.client.force_authenticate(self.employee)
        with patch("administration.services._ldap_connection") as connection:
            response = self.client.post(
                "/api/v1/admin/integrations/ldap/test/", {}, format="json"
            )
        self.assertEqual(response.status_code, 403, response.data)
        connection.assert_not_called()
        self.assertFalse(IntegrationTest.objects.exists())
        self.assertFalse(
            AuditEvent.objects.filter(action="integration.connection.tested").exists()
        )


class AIConnectionDiagnosticAPITests(DirectoryProfileFixtures):
    def setUp(self):
        super().setUp()
        update_configuration(
            self.admin, "ai", {"model": "synthetic-shared-model-v1"}
        )
        response = self.client.post(
            "/api/v1/admin/ai/profiles/",
            {
                "name": "Synthetic diagnostic profile",
                "config": {
                    "enabled": True,
                    "provider": "openai-compatible",
                    "base_url": "https://api.example.test/v1",
                },
                "secrets": {"api_key": SECRET_MARKER},
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.profile = response.data
        self.endpoint = f"/api/v1/admin/ai/profiles/{self.profile['id']}/"

    def test_http_failure_reason_and_unknown_usage_survive_fresh_reads(self):
        for status in (401, 403, 404, 429, 503):
            with self.subTest(status=status):
                with patch(
                    "administration.services._ai_call",
                    side_effect=http_status_error(status),
                ):
                    response = self.client.post(
                        self.endpoint + "test/", {}, format="json"
                    )
                self.assertEqual(response.status_code, 400, response.data)
                self.assertEqual(response.data["status"], "failure")
                self.assertIn(str(status), response.data["message"])
                saved = IntegrationTest.objects.filter(
                    configuration__section=self.profile["section"]
                ).latest("checked_at")
                self.assertEqual(saved.message, response.data["message"])
                self.assertEqual(saved.checked_by_id, self.admin.pk)
                self.assertEqual(saved.status, "failure")
                fresh = self.client.get(self.endpoint)
                self.assertEqual(fresh.status_code, 200, fresh.data)
                self.assertFalse(fresh.data["ready"])
                self.assertEqual(fresh.data["latest_test"]["message"], saved.message)
                self.assertEqual(fresh.data["latest_test"]["status"], "failure")
                usage = AIUsage.objects.latest("created_at")
                self.assertEqual(usage.status, "unknown")
                self.assertEqual(usage.measurement, "unknown")
                self.assertEqual(usage.actor_id, self.admin.pk)
                self.assertEqual(str(usage.profile_id), self.profile["id"])
                self.assertIsNotNone(usage.completed_at)
                self.assertIsNone(usage.input_tokens)
                self.assertIsNone(usage.output_tokens)
                self.assertIsNone(usage.estimated_cost)
                self.assertGreater(usage.reserved_tokens, 0)
                public_result = json.dumps(response.data, default=str)
                public_result += json.dumps(fresh.data, default=str)
                public_result += json.dumps(
                    list(AuditEvent.objects.values_list("data", flat=True)), default=str
                )
                for private_value in (SECRET_MARKER, BODY_MARKER, RAW_URL, "ErrorDetail("):
                    self.assertNotIn(private_value, public_result)
        self.assertEqual(AIUsage.objects.count(), 5)
        self.assertEqual(IntegrationTest.objects.count(), 5)

    def test_failure_success_and_settings_change_preserve_truthful_readiness(self):
        with patch(
            "administration.services._ai_call", side_effect=http_status_error(401)
        ):
            failed = self.client.post(self.endpoint + "test/", {}, format="json")
        self.assertEqual(failed.status_code, 400, failed.data)
        self.assertFalse(self.client.get(self.endpoint).data["ready"])
        with patch(
            "administration.services._ai_call",
            return_value={
                "choices": [{"message": {"content": "OK"}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 1},
            },
        ):
            succeeded = self.client.post(self.endpoint + "test/", {}, format="json")
        self.assertEqual(succeeded.status_code, 200, succeeded.data)
        self.assertEqual(succeeded.data["status"], "success")
        self.assertTrue(self.client.get(self.endpoint).data["ready"])
        current = ConfigurationVersion.objects.filter(
            configuration__section="ai"
        ).latest("version")
        update_configuration(
            self.admin,
            "ai",
            {"model": "synthetic-shared-model-v2"},
            expected_version=current.version,
        )
        changed = self.client.get(self.endpoint)
        self.assertEqual(changed.status_code, 200, changed.data)
        self.assertFalse(changed.data["ready"])
        self.assertEqual(changed.data["latest_test"]["status"], "success")
        self.assertEqual(
            list(
                IntegrationTest.objects.filter(
                    configuration__section=self.profile["section"]
                ).order_by("checked_at").values_list("status", flat=True)
            ),
            ["failure", "success"],
        )
        self.assertEqual(AIUsage.objects.filter(status="unknown").count(), 1)
        self.assertEqual(AIUsage.objects.filter(status="success").count(), 1)

    def test_employee_cannot_run_profile_test_or_create_usage_evidence(self):
        self.client.force_authenticate(self.employee)
        with patch("administration.services._ai_call") as call:
            response = self.client.post(self.endpoint + "test/", {}, format="json")
        self.assertEqual(response.status_code, 403, response.data)
        call.assert_not_called()
        self.assertFalse(AIUsage.objects.exists())
        self.assertFalse(IntegrationTest.objects.exists())
        self.assertFalse(AuditEvent.objects.filter(action="ai.profile.tested").exists())
