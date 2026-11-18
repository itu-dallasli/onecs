"""Directory staging and model-profile contracts with mocked remote services.

These tests validate local policy, transport ordering and persisted state. A passing
mocked transport test is not evidence of a real institutional LDAP/AI connection.
"""

import base64
import json
import ssl
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cryptography.fernet import Fernet
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from administration.models import ConfigurationVersion, LDAPIdentity, LDAPImportBatch
from administration.security import decrypt_secrets
from administration.services import _ldap_subject, update_configuration
from core.models import AuditEvent, OrgNode, RoleGrant, User


class DirectoryProfileFixtures(TestCase):
    def setUp(self):
        self.override = override_settings(
            ONECS_ENCRYPTION_KEY=Fernet.generate_key().decode(),
            ONECS_ALLOWED_INTEGRATION_HOSTS="directory.example.test,api.example.test,other.example.test",
            ONECS_ALLOW_PRIVATE_INTEGRATION_HOSTS="",
        )
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.directory = OrgNode.objects.create(
            code="ICT-CS", name="Synthetic Directorate", kind="DIRECTORATE"
        )
        self.unit = OrgNode.objects.create(
            code="ICT-CS-OS", name="Synthetic Unit", kind="UNIT", parent=self.directory
        )
        self.other = OrgNode.objects.create(
            code="OTHER", name="Outside Directorate", kind="DIRECTORATE"
        )
        self.admin = User.objects.create_user(
            username="directory-admin", primary_org=self.unit
        )
        self.director = User.objects.create_user(
            username="directory-director", primary_org=self.directory
        )
        self.employee = User.objects.create_user(
            username="ordinary-employee", primary_org=self.unit
        )
        RoleGrant.objects.create(user=self.admin, role="SYSTEM_ADMIN")
        RoleGrant.objects.create(user=self.director, role="SYSTEM_ADMIN")
        RoleGrant.objects.create(
            user=self.director, role="DIRECTOR", org_node=self.directory
        )
        RoleGrant.objects.create(
            user=self.employee, role="EMPLOYEE", org_node=self.unit
        )
        self.dns_patch = patch(
            "administration.security.socket.getaddrinfo",
            return_value=[(None, None, None, None, ("93.184.216.34", 0))],
        )
        self.dns_patch.start()
        self.addCleanup(self.dns_patch.stop)
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def configure_directory(self, **overrides):
        return update_configuration(
            self.admin,
            "ldap",
            {
                "enabled": True,
                "url": "ldap://directory.example.test:389",
                "start_tls": True,
                "bind_dn": "cn=onecs-reader,dc=example,dc=test",
                "base_dn": "dc=example,dc=test",
                "user_filter": "(uid={username})",
                **overrides,
            },
            {"bind_password": "synthetic-directory-test-value"},
        )

    @staticmethod
    def ldap_entry(username="alice", subject=b"synthetic-uuid-alice", dn=None, **attributes):
        dn = dn or f"uid={username},ou=people,dc=example,dc=test"
        values = {
            "uid": username,
            "sAMAccountName": username,
            "cn": f"Synthetic {username}",
            "displayName": f"Synthetic {username}",
            "mail": f"{username}@example.test",
            "department": "Synthetic operations",
            "title": "Unit Head",
            "memberOf": ["cn=Directors,ou=groups,dc=example,dc=test"],
            **attributes,
        }
        entry = Mock()
        entry.entry_dn = dn
        entry.entry_raw_attributes = {"entryUUID": [subject]} if subject else {}
        entry.entry_attributes_as_dict = values
        entry.__getitem__ = Mock(
            side_effect=lambda name: SimpleNamespace(
                value=values.get(name),
                values=values.get(name) if isinstance(values.get(name), list) else [values.get(name)],
            )
        )
        return entry


class LDAPImmutableSubjectTests(DirectoryProfileFixtures):
    def test_subject_is_stable_when_dn_and_display_name_change(self):
        before = self.ldap_entry()
        after = self.ldap_entry(
            dn="uid=renamed,ou=other,dc=example,dc=test", displayName="Renamed person"
        )
        self.assertEqual(_ldap_subject(before), _ldap_subject(after))
        self.assertEqual(
            _ldap_subject(before),
            "entryUUID:" + base64.b64encode(b"synthetic-uuid-alice").decode(),
        )

    def test_missing_immutable_uuid_is_rejected_instead_of_using_dn(self):
        with self.assertRaises(ValidationError):
            _ldap_subject(self.ldap_entry(subject=None))


class LDAPTransportTests(DirectoryProfileFixtures):
    def test_starttls_is_verified_and_completed_before_credentials_are_bound(self):
        from administration.services import _ldap_connection

        config = {
            "url": "ldap://directory.example.test:389",
            "start_tls": True,
            "bind_dn": "cn=onecs-reader,dc=example,dc=test",
            "timeout_seconds": 10,
        }
        events = []
        connection = Mock()
        connection.open.side_effect = lambda: events.append("open") or True
        connection.start_tls.side_effect = lambda: events.append("tls") or True
        connection.bind.side_effect = lambda: events.append("bind") or True
        with (
            patch("ldap3.Connection", return_value=connection) as connect,
            patch("ldap3.Server") as server,
            patch("ldap3.Tls") as tls,
        ):
            self.assertIs(
                _ldap_connection(config, {"bind_password": "synthetic-value"}),
                connection,
            )
        self.assertEqual(events, ["open", "tls", "bind"])
        self.assertEqual(connect.call_args.kwargs["auto_bind"], False)
        self.assertEqual(tls.call_args.kwargs["validate"], ssl.CERT_REQUIRED)
        self.assertFalse(server.call_args.kwargs["use_ssl"])
        self.assertEqual(server.call_args.kwargs["port"], 389)

    def test_starttls_failure_never_attempts_credential_bind(self):
        from administration.services import _ldap_connection

        connection = Mock()
        connection.open.return_value = True
        connection.start_tls.return_value = False
        with (
            patch("ldap3.Connection", return_value=connection),
            patch("ldap3.Server"),
            patch("ldap3.Tls"),
        ):
            with self.assertRaises(ValidationError):
                _ldap_connection(
                    {
                        "url": "ldap://directory.example.test:389",
                        "start_tls": True,
                        "bind_dn": "cn=onecs-reader,dc=example,dc=test",
                    },
                    {"bind_password": "synthetic-value"},
                )
        connection.bind.assert_not_called()

    def test_tls_failure_with_broken_socket_cleanup_remains_validation_error(self):
        from administration.services import _ldap_connection
        from ldap3.core.exceptions import LDAPSocketSendError

        connection = Mock()
        connection.open.return_value = True
        connection.start_tls.side_effect = ssl.SSLCertVerificationError("certificate has expired")
        connection.unbind.side_effect = LDAPSocketSendError("bad file descriptor")
        with (
            patch("ldap3.Connection", return_value=connection),
            patch("ldap3.Server"),
            patch("ldap3.Tls"),
        ):
            with self.assertRaises(ValidationError) as caught:
                _ldap_connection({"url": "ldap://directory.example.test:389", "start_tls": True, "bind_dn": "synthetic-reader"}, {"bind_password": "synthetic-secret"})
        self.assertEqual(caught.exception.status_code, 400)
        connection.bind.assert_not_called()
        connection.unbind.assert_called_once()

    def test_failed_tls_cleanup_is_safe_at_directory_http_boundary(self):
        from ldap3.core.exceptions import LDAPSocketSendError

        self.configure_directory()
        connection = Mock()
        connection.open.return_value = True
        connection.start_tls.side_effect = ssl.SSLCertVerificationError("certificate has expired")
        connection.unbind.side_effect = LDAPSocketSendError("bad file descriptor")
        with (
            patch("ldap3.Connection", return_value=connection),
            patch("ldap3.Server"),
            patch("ldap3.Tls"),
        ):
            response = self.client.post("/api/v1/admin/ldap/discover/", {}, format="json")
        self.assertEqual(response.status_code, 400, response.data)
        connection.bind.assert_not_called()

    def test_plain_ldap_without_starttls_is_rejected_before_connection(self):
        with patch("ldap3.Connection") as connection:
            with self.assertRaises(ValidationError):
                self.configure_directory(start_tls=False)
        connection.assert_not_called()

    def test_ldaps_preserves_certificate_verification_without_starttls(self):
        from administration.services import _ldap_connection

        connection = Mock()
        connection.open.return_value = True
        connection.bind.return_value = True
        with (
            patch("ldap3.Connection", return_value=connection),
            patch("ldap3.Server") as server,
            patch("ldap3.Tls") as tls,
        ):
            _ldap_connection(
                {
                    "url": "ldaps://directory.example.test:636",
                    "start_tls": False,
                    "bind_dn": "cn=onecs-reader,dc=example,dc=test",
                },
                {"bind_password": "synthetic-value"},
            )
        connection.start_tls.assert_not_called()
        self.assertEqual(tls.call_args.kwargs["validate"], ssl.CERT_REQUIRED)
        self.assertTrue(server.call_args.kwargs["use_ssl"])
        self.assertEqual(server.call_args.kwargs["port"], 636)


class LDAPStagingAPITests(DirectoryProfileFixtures):
    def stage(self, *, username="alice", subject=b"synthetic-uuid-alice"):
        self.configure_directory()
        connection = Mock()
        connection.entries = [self.ldap_entry(username, subject)]
        with patch("administration.services._ldap_connection", return_value=connection):
            response = self.client.post(
                "/api/v1/admin/ldap/search/",
                {"kind": "users", "query": username, "base_dn": "dc=example,dc=test"},
                format="json",
            )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertIn("batch_id", response.data)
        return response.data

    def import_candidate(self, staged, *, role="EMPLOYEE", org=None, **overrides):
        return self.client.post(
            "/api/v1/admin/ldap/import/",
            {
                "batch_id": str(staged["batch_id"]),
                "entries": [
                    {
                        "subject": staged["results"][0]["subject"],
                        "org_node": str((org or self.unit).pk),
                        "role": role,
                    }
                ],
                **overrides,
            },
            format="json",
        )

    def test_employee_cannot_discover_preview_or_import(self):
        self.client.force_authenticate(self.employee)
        with patch("administration.services._ldap_connection") as connection:
            for action in ("discover", "search", "import"):
                response = self.client.post(
                    f"/api/v1/admin/ldap/{action}/", {}, format="json"
                )
                self.assertEqual(response.status_code, 403, (action, response.data))
        connection.assert_not_called()

    def test_rootdse_discovery_returns_bases_without_creating_users_or_roles(self):
        self.configure_directory(base_dn="")
        connection = Mock()
        connection.entries = [
            self.ldap_entry(
                namingContexts=["dc=example,dc=test", "dc=other,dc=test"],
                defaultNamingContext="dc=example,dc=test",
            )
        ]
        user_count, role_count = User.objects.count(), RoleGrant.objects.count()
        with patch("administration.services._ldap_connection", return_value=connection):
            response = self.client.post(
                "/api/v1/admin/ldap/discover/", {}, format="json"
            )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            set(response.data["base_dns"]),
            {"dc=example,dc=test", "dc=other,dc=test"},
        )
        self.assertEqual(User.objects.count(), user_count)
        self.assertEqual(RoleGrant.objects.count(), role_count)
        self.assertEqual(connection.search.call_args.args[0], "")

    def test_ambiguous_rootdse_requires_explicit_base_before_preview(self):
        self.configure_directory(base_dn="")
        connection = Mock()
        connection.entries = [
            self.ldap_entry(
                namingContexts=["dc=example,dc=test", "dc=other,dc=test"],
                defaultNamingContext="",
            )
        ]
        with patch("administration.services._ldap_connection", return_value=connection):
            response = self.client.post(
                "/api/v1/admin/ldap/search/", {"kind": "users", "query": "alice"}, format="json"
            )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(LDAPImportBatch.objects.exists())
        self.assertFalse(User.objects.filter(username="alice").exists())

    def test_preview_metadata_and_manager_hints_do_not_create_roles(self):
        user_count, role_count = User.objects.count(), RoleGrant.objects.count()
        staged = self.stage()
        candidate = staged["results"][0]
        self.assertEqual(candidate["username"], "alice")
        self.assertEqual(candidate["title"], "Unit Head")
        self.assertEqual(candidate["department"], "Synthetic operations")
        self.assertIn("role_hint", candidate)
        self.assertEqual(User.objects.count(), user_count)
        self.assertEqual(RoleGrant.objects.count(), role_count)
        self.assertNotIn("synthetic-directory-test-value", json.dumps(staged, default=str))

    def test_import_requires_explicit_role_and_org_and_is_atomic(self):
        staged = self.stage()
        subject = staged["results"][0]["subject"]
        for entry in (
            {"subject": subject, "role": "EMPLOYEE"},
            {"subject": subject, "org_node": str(self.unit.pk)},
        ):
            response = self.client.post(
                "/api/v1/admin/ldap/import/",
                {"batch_id": str(staged["batch_id"]), "entries": [entry]},
                format="json",
            )
            self.assertEqual(response.status_code, 400, response.data)
            self.assertFalse(User.objects.filter(username="alice").exists())
            self.assertFalse(LDAPIdentity.objects.exists())

    def test_technical_admin_can_import_employee_with_unusable_local_password(self):
        staged = self.stage()
        response = self.import_candidate(staged)
        self.assertIn(response.status_code, (200, 201), response.data)
        imported = User.objects.get(username="alice")
        self.assertEqual(imported.identity_source, "ldap")
        self.assertEqual(imported.primary_org_id, self.unit.pk)
        self.assertFalse(imported.has_usable_password())
        self.assertEqual(
            set(imported.role_grants.filter(active=True).values_list("role", flat=True)),
            {"EMPLOYEE"},
        )
        self.assertEqual(imported.ldap_identity.subject, staged["results"][0]["subject"])
        self.assertTrue(AuditEvent.objects.filter(actor=self.admin).exists())

    def test_technical_admin_cannot_convert_directory_hints_into_business_role(self):
        staged = self.stage()
        response = self.import_candidate(staged, role="UNIT_HEAD")
        self.assertEqual(response.status_code, 403, response.data)
        self.assertFalse(User.objects.filter(username="alice").exists())
        self.assertFalse(LDAPIdentity.objects.exists())
        self.assertFalse(RoleGrant.objects.filter(role="UNIT_HEAD").exists())

    def test_director_imports_business_role_only_within_their_scope(self):
        self.client.force_authenticate(self.director)
        staged = self.stage()
        denied = self.import_candidate(staged, role="UNIT_HEAD", org=self.other)
        self.assertEqual(denied.status_code, 403, denied.data)
        self.assertFalse(User.objects.filter(username="alice").exists())
        accepted = self.import_candidate(staged, role="UNIT_HEAD")
        self.assertIn(accepted.status_code, (200, 201), accepted.data)
        imported = User.objects.get(username="alice")
        self.assertTrue(
            imported.role_grants.filter(
                role="UNIT_HEAD", org_node=self.unit, active=True
            ).exists()
        )

    def test_local_username_collision_is_not_rebound_to_ldap(self):
        local = User.objects.create_user(username="alice", primary_org=self.unit)
        staged = self.stage()
        response = self.import_candidate(staged)
        self.assertIn(response.status_code, (400, 409), response.data)
        local.refresh_from_db()
        self.assertEqual(local.identity_source, "local")
        self.assertFalse(LDAPIdentity.objects.filter(user=local).exists())
        self.assertFalse(local.role_grants.exists())

    def test_renamed_directory_username_preserves_existing_immutable_identity(self):
        existing = User.objects.create_user(
            username="original-alice", identity_source="ldap", primary_org=self.unit
        )
        entry = self.ldap_entry()
        LDAPIdentity.objects.create(
            user=existing,
            subject=_ldap_subject(entry),
            distinguished_name=entry.entry_dn,
        )
        RoleGrant.objects.create(user=existing, role="EMPLOYEE", org_node=self.unit)
        staged = self.stage(username="renamed-alice")
        response = self.import_candidate(staged)
        self.assertIn(response.status_code, (200, 201), response.data)
        self.assertFalse(User.objects.filter(username="renamed-alice").exists())
        self.assertEqual(LDAPIdentity.objects.get().user_id, existing.pk)
        existing.refresh_from_db()
        self.assertEqual(existing.username, "original-alice")
        self.assertEqual(existing.role_grants.filter(active=True).count(), 1)

    def test_import_service_denies_business_role_while_using_another_actors_view(self):
        from administration.directory import directory_import
        from rest_framework.exceptions import PermissionDenied

        self.client.force_authenticate(self.director)
        staged = self.stage()
        self.director._real_actor = self.admin
        self.addCleanup(lambda: delattr(self.director, "_real_actor"))
        with self.assertRaises(PermissionDenied):
            directory_import(
                self.director,
                staged["batch_id"],
                [{"subject": staged["results"][0]["subject"], "org_node": str(self.unit.pk), "role": "UNIT_HEAD"}],
            )
        self.assertFalse(User.objects.filter(username="alice").exists())
        self.assertFalse(LDAPIdentity.objects.exists())

    def test_config_version_change_invalidates_staged_directory_import(self):
        staged = self.stage()
        current = ConfigurationVersion.objects.get(configuration__section="ldap")
        update_configuration(
            self.admin,
            "ldap",
            {"base_dn": "ou=changed,dc=example,dc=test"},
            expected_version=current.version,
        )
        response = self.import_candidate(staged, expected_config_version=current.version)
        self.assertIn(response.status_code, (400, 409), response.data)
        self.assertFalse(User.objects.filter(username="alice").exists())
        self.assertFalse(LDAPIdentity.objects.exists())


    def test_staging_batch_cannot_be_imported_by_another_administrator(self):
        staged = self.stage()
        self.client.force_authenticate(self.director)
        response = self.import_candidate(staged)
        self.assertIn(response.status_code, (403, 404), response.data)
        self.assertFalse(User.objects.filter(username="alice").exists())

    def test_expired_batch_does_not_provision_a_user(self):
        staged = self.stage()
        LDAPImportBatch.objects.filter(pk=staged["batch_id"]).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )
        response = self.import_candidate(staged)
        self.assertIn(response.status_code, (400, 409), response.data)
        self.assertFalse(User.objects.filter(username="alice").exists())
        self.assertFalse(LDAPIdentity.objects.exists())

    def test_bulk_import_rolls_back_earlier_employee_when_later_business_role_is_denied(self):
        self.configure_directory()
        connection = Mock()
        connection.entries = [
            self.ldap_entry("alice", b"synthetic-uuid-alice"),
            self.ldap_entry("bob", b"synthetic-uuid-bob"),
        ]
        with patch("administration.services._ldap_connection", return_value=connection):
            staged = self.client.post(
                "/api/v1/admin/ldap/search/",
                {"kind": "users", "query": "", "base_dn": "dc=example,dc=test"},
                format="json",
            )
        self.assertEqual(staged.status_code, 200, staged.data)
        candidates = staged.data["results"]
        self.assertEqual(len(candidates), 2)
        response = self.client.post(
            "/api/v1/admin/ldap/import/",
            {
                "batch_id": str(staged.data["batch_id"]),
                "entries": [
                    {"subject": candidates[0]["subject"], "org_node": str(self.unit.pk), "role": "EMPLOYEE"},
                    {"subject": candidates[1]["subject"], "org_node": str(self.unit.pk), "role": "UNIT_HEAD"},
                ],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403, response.data)
        self.assertFalse(User.objects.filter(username__in=["alice", "bob"]).exists())
        self.assertFalse(LDAPIdentity.objects.exists())
        self.assertEqual(
            LDAPImportBatch.objects.get(pk=staged.data["batch_id"]).imported_subjects,
            [],
        )


class AIConnectionProfileAPITests(DirectoryProfileFixtures):
    def setUp(self):
        super().setUp()
        update_configuration(
            self.admin,
            "ai",
            {
                "model": "shared-model-v1",
                "temperature": 1,
                "max_output_tokens": 4096,
                "timeout_seconds": 180,
            },
        )

    def create_profile(self, name="Primary", endpoint="https://api.example.test/v1"):
        response = self.client.post(
            "/api/v1/admin/ai/profiles/",
            {
                "name": name,
                "config": {
                    "enabled": True,
                    "provider": "openai-compatible",
                    "base_url": endpoint,
                },
                "secrets": {"api_key": f"synthetic-{name.lower()}-credential"},
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    @staticmethod
    def provider_result():
        return {
            "choices": [
                {"message": {"content": json.dumps({"text": "Taslak [work-1]", "citations": ["work-1"]})}}
            ],
            "usage": {"prompt_tokens": 20, "completion_tokens": 10},
        }

    def test_employee_cannot_list_or_create_connection_profiles(self):
        self.client.force_authenticate(self.employee)
        self.assertEqual(
            self.client.get("/api/v1/admin/ai/profiles/").status_code, 403
        )
        response = self.client.post(
            "/api/v1/admin/ai/profiles/", {"name": "Unauthorized"}, format="json"
        )
        self.assertEqual(response.status_code, 403)

    def test_profiles_keep_connection_versions_and_secrets_independent(self):
        first = self.create_profile()
        second = self.create_profile("Secondary", "https://other.example.test/v1")
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(first["version"], 1)
        self.assertEqual(second["version"], 1)
        self.assertEqual(first["secret_fields"], ["api_key"])
        self.assertFalse(first["ready"])
        self.assertFalse(second["ready"])
        self.assertNotIn("synthetic-primary-credential", json.dumps(first, default=str))
        response = self.client.patch(
            f"/api/v1/admin/ai/profiles/{first['id']}/",
            {
                "expected_version": first["version"],
                "secrets": {"api_key": "synthetic-primary-rotated"},
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["version"], 2)
        other = self.client.get("/api/v1/admin/ai/profiles/")
        self.assertEqual(other.status_code, 200)
        items = other.data.get("results", other.data.get("profiles", []))
        second_current = next(item for item in items if str(item["id"]) == str(second["id"]))
        self.assertEqual(second_current["version"], 1)
        self.assertEqual(second_current["config"]["base_url"], "https://other.example.test/v1")
        encrypted_versions = ConfigurationVersion.objects.exclude(encrypted_secrets="")
        self.assertGreaterEqual(encrypted_versions.count(), 3)
        self.assertTrue(
            all("synthetic-" not in value for value in encrypted_versions.values_list("encrypted_secrets", flat=True))
        )
        decoded = [decrypt_secrets(item.encrypted_secrets).get("api_key") for item in encrypted_versions]
        self.assertIn("synthetic-primary-credential", decoded)
        self.assertIn("synthetic-secondary-credential", decoded)
        self.assertIn("synthetic-primary-rotated", decoded)

    def test_stale_profile_update_cannot_overwrite_rotated_connection(self):
        profile = self.create_profile()
        endpoint = f"/api/v1/admin/ai/profiles/{profile['id']}/"
        accepted = self.client.patch(
            endpoint,
            {"expected_version": 1, "config": {"base_url": "https://other.example.test/v1"}},
            format="json",
        )
        self.assertEqual(accepted.status_code, 200, accepted.data)
        stale = self.client.patch(
            endpoint,
            {"expected_version": 1, "config": {"base_url": "https://api.example.test/stale"}},
            format="json",
        )
        self.assertIn(stale.status_code, (400, 409), stale.data)
        listing = self.client.get("/api/v1/admin/ai/profiles/")
        items = listing.data.get("results", listing.data.get("profiles", []))
        current = next(item for item in items if str(item["id"]) == str(profile["id"]))
        self.assertEqual(current["version"], 2)
        self.assertEqual(current["config"]["base_url"], "https://other.example.test/v1")

    def test_profile_test_readiness_is_independent_and_shared_model_version_bound(self):
        first = self.create_profile()
        second = self.create_profile("Secondary", "https://other.example.test/v1")
        with patch("administration.services._ai_call", return_value=self.provider_result()) as call:
            tested = self.client.post(
                f"/api/v1/admin/ai/profiles/{first['id']}/test/", {}, format="json"
            )
        self.assertEqual(tested.status_code, 200, tested.data)
        self.assertEqual(tested.data["status"], "success")
        self.assertEqual(call.call_args.args[0]["model"], "shared-model-v1")
        listing = self.client.get("/api/v1/admin/ai/profiles/")
        items = listing.data.get("results", listing.data.get("profiles", []))
        self.assertTrue(next(item for item in items if str(item["id"]) == str(first["id"]))["ready"])
        self.assertFalse(next(item for item in items if str(item["id"]) == str(second["id"]))["ready"])
        current = ConfigurationVersion.objects.filter(configuration__section="ai").order_by("-version").first()
        update_configuration(
            self.admin, "ai", {"model": "shared-model-v2"}, expected_version=current.version
        )
        listing = self.client.get("/api/v1/admin/ai/profiles/")
        items = listing.data.get("results", listing.data.get("profiles", []))
        self.assertFalse(next(item for item in items if str(item["id"]) == str(first["id"]))["ready"])

    def test_queued_ai_job_uses_pinned_profile_and_shared_settings_after_default_changes(self):
        from administration.services import generate_ai_report, selected_ai_snapshot

        first = self.create_profile()
        second = self.create_profile("Secondary", "https://other.example.test/v1")
        selected = self.client.post(
            f"/api/v1/admin/ai/profiles/{first['id']}/default/", {}, format="json"
        )
        self.assertEqual(selected.status_code, 200, selected.data)
        pinned = selected_ai_snapshot()
        self.assertEqual(str(pinned["profile_id"]), str(first["id"]))
        changed = self.client.patch(
            f"/api/v1/admin/ai/profiles/{first['id']}/",
            {
                "expected_version": first["version"],
                "config": {"base_url": "https://api.example.test/changed"},
                "secrets": {"api_key": "synthetic-new-secret"},
            },
            format="json",
        )
        self.assertEqual(changed.status_code, 200, changed.data)
        current = ConfigurationVersion.objects.filter(configuration__section="ai").order_by("-version").first()
        update_configuration(
            self.admin, "ai", {"model": "shared-model-v2"}, expected_version=current.version
        )
        selected = self.client.post(
            f"/api/v1/admin/ai/profiles/{second['id']}/default/", {}, format="json"
        )
        self.assertEqual(selected.status_code, 200, selected.data)
        with patch("administration.services._ai_call", return_value=self.provider_result()) as call:
            result = generate_ai_report(
                self.admin,
                [{"id": "work-1", "title": "Synthetic task"}],
                request_id="synthetic-pinned-job",
                **pinned,
            )
        self.assertEqual(result["status"], "success", result)
        used_config, used_secrets = call.call_args.args[:2]
        self.assertEqual(used_config["base_url"], "https://api.example.test/v1")
        self.assertEqual(used_config["model"], "shared-model-v1")
        self.assertEqual(used_secrets["api_key"], "synthetic-primary-credential")

    def test_job_queued_without_any_ai_config_never_uses_future_default(self):
        from administration.services import generate_ai_report, selected_ai_snapshot
        from administration.models import IntegrationConfiguration

        IntegrationConfiguration.objects.filter(section="ai").delete()
        pinned = selected_ai_snapshot()
        self.assertEqual(pinned, {"profile_id": None, "configuration_version": 0, "settings_version": 0})
        update_configuration(self.admin, "ai", {"model": "future-model"})
        profile = self.create_profile()
        selected = self.client.post(f"/api/v1/admin/ai/profiles/{profile['id']}/default/", {}, format="json")
        self.assertEqual(selected.status_code, 200, selected.data)
        with patch("administration.services._ai_call") as call:
            result = generate_ai_report(self.admin, [{"id": "work-1", "title": "Queued before AI"}], request_id="before-ai-enabled", **pinned)
        self.assertEqual(result["mode"], "RULE_BASED")
        self.assertEqual(result["status"], "unconfigured")
        call.assert_not_called()
