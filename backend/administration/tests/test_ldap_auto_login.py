"""LDAP first-login policy with synthetic directory entries and mocked transport.

These tests prove local authentication/provisioning contracts. They do not prove
that any institutional directory or an actual user's password is reachable.
"""

import json
import ssl
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from unittest.mock import Mock, patch

from django.db import close_old_connections, connection, connections
from django.test import TransactionTestCase, override_settings
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.test import APIClient

from administration.models import (
    ConfigurationVersion,
    LDAPIdentity,
    LDAPManagedGrant,
)
from administration.services import _ldap_subject, authenticate_ldap, update_configuration
from administration.tests.test_directory_profiles import DirectoryProfileFixtures
from core.models import Announcement, AuditEvent, OrgNode, RoleGrant, User
from core.policy import audience_visible


class LDAPAutoLoginFixtures(DirectoryProfileFixtures):
    password = "synthetic-user-password"

    def configure_auto_login(self, **overrides):
        return self.configure_directory(
            auto_provision_enabled=True,
            match_organization_groups=True,
            **overrides,
        )

    def group_dn(self, org=None):
        return f"cn={(org or self.unit).code},ou=groups,dc=example,dc=test"

    def login_entry(self, username="alice", **attributes):
        return self.ldap_entry(
            username=username,
            memberOf=attributes.pop("memberOf", [self.group_dn()]),
            **attributes,
        )

    @staticmethod
    def connection_for(entries, *, accepted=True):
        transport = Mock()
        transport.entries = entries
        transport.search.return_value = True
        transport.rebind.return_value = accepted
        return transport

    def authenticate(self, entry=None, *, username="alice", password=None, accepted=True):
        transport = self.connection_for(
            [entry if entry is not None else self.login_entry()], accepted=accepted
        )
        with patch("administration.services._ldap_connection", return_value=transport):
            user = authenticate_ldap(username, self.password if password is None else password)
        return user, transport

    @staticmethod
    def persistent_counts():
        return (
            User.objects.count(),
            LDAPIdentity.objects.count(),
            RoleGrant.objects.count(),
            LDAPManagedGrant.objects.count(),
            AuditEvent.objects.count(),
        )

    def mapping(self, *, group_dn=None, org=None, role="UNIT_HEAD", descendants=True):
        return {
            "group_dn": group_dn or "cn=Synthetic Unit Heads,ou=groups,dc=example,dc=test",
            "org_node": str((org or self.unit).pk),
            "role": role,
            "includes_descendants": descendants,
        }


class LDAPFirstLoginTests(LDAPAutoLoginFixtures):
    def test_public_first_login_establishes_session_with_group_derived_role(self):
        self.configure_auto_login()
        client = APIClient()
        transport = self.connection_for([self.login_entry()])
        with patch("administration.services._ldap_connection", return_value=transport):
            response = client.post("/api/v1/auth/login/", {"method": "ldap", "username": "alice", "password": self.password}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        user = User.objects.get(username="alice")
        self.assertEqual(client.session["_auth_user_id"], str(user.pk))
        self.assertEqual(response.data["primary_org"]["id"], str(self.unit.pk))
        self.assertEqual(response.data["roles"], [{"role": "EMPLOYEE", "org_id": str(self.unit.pk), "permissions": []}])
        self.assertFalse(response.data["permissions"]["system_admin"])
        self.assertTrue(AuditEvent.objects.filter(actor=user, action="auth.login", data__method="ldap").exists())

    def test_successful_rebind_creates_ldap_identity_and_scoped_employee_grant(self):
        self.configure_auto_login()
        before = self.persistent_counts()
        entry = self.login_entry(title="Director", department="Synthetic directorate")
        transport = self.connection_for([entry])

        def bind_only_before_provisioning(**kwargs):
            self.assertEqual(self.persistent_counts(), before)
            self.assertEqual(kwargs, {"user": entry.entry_dn, "password": self.password})
            return True

        transport.rebind.side_effect = bind_only_before_provisioning
        with patch("administration.services._ldap_connection", return_value=transport):
            user = authenticate_ldap("alice", self.password)

        self.assertIsNotNone(user)
        self.assertEqual(user.identity_source, "ldap")
        self.assertEqual(user.profile_kind, "LDAP")
        self.assertEqual(user.primary_org_id, self.unit.pk)
        self.assertFalse(user.has_usable_password())
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        identity = LDAPIdentity.objects.get(user=user)
        self.assertEqual(identity.subject, _ldap_subject(entry))
        self.assertEqual(identity.distinguished_name, entry.entry_dn)
        self.assertIsNotNone(identity.synced_at)
        grant = user.role_grants.get(active=True)
        self.assertEqual((grant.role, grant.org_node_id), ("EMPLOYEE", self.unit.pk))
        self.assertFalse(grant.includes_descendants)
        self.assertTrue(LDAPManagedGrant.objects.filter(identity=identity, grant=grant).exists())
        self.assertTrue(AuditEvent.objects.filter(actor=user, action="ldap.identity.provisioned").exists())
        transport.unbind.assert_called_once()
        search = transport.search.call_args
        self.assertEqual(search.args[1], "(sAMAccountName=alice)")
        self.assertEqual(search.kwargs["size_limit"], 2)
        self.assertIn("memberOf", search.kwargs["attributes"])
        self.assertIn("userAccountControl", search.kwargs["attributes"])

    def test_repeated_login_is_idempotent_and_uses_immutable_directory_subject(self):
        self.configure_auto_login()
        first, _ = self.authenticate()
        self.assertIsNotNone(first)
        identity = LDAPIdentity.objects.get(user=first)
        initial_counts = (User.objects.count(), LDAPIdentity.objects.count(), RoleGrant.objects.count(), LDAPManagedGrant.objects.count())
        renamed = self.login_entry(
            username="renamed-alice",
            dn="uid=renamed-alice,ou=other,dc=example,dc=test",
            displayName="Synthetic renamed person",
        )
        again, _ = self.authenticate(renamed, username="renamed-alice")
        self.assertIsNotNone(again)
        self.assertEqual(again.pk, first.pk)
        self.assertEqual((User.objects.count(), LDAPIdentity.objects.count(), RoleGrant.objects.count(), LDAPManagedGrant.objects.count()), initial_counts)
        identity.refresh_from_db()
        self.assertEqual(identity.subject, _ldap_subject(renamed))
        self.assertEqual(identity.distinguished_name, renamed.entry_dn)

    def test_case_insensitive_username_resolves_to_canonical_directory_name(self):
        self.configure_auto_login()
        user, _ = self.authenticate(self.login_entry(username="Alice"), username="aLiCe")
        self.assertIsNotNone(user)
        self.assertEqual(user.username, "Alice")
        again, _ = self.authenticate(self.login_entry(username="Alice"), username="ALICE")
        self.assertEqual(again.pk, user.pk)
        self.assertEqual(User.objects.filter(username__iexact="alice").count(), 1)

    def test_matching_group_cn_is_exact_and_case_insensitive(self):
        self.configure_auto_login()
        user, _ = self.authenticate(self.login_entry(memberOf=[self.group_dn().upper()]))
        self.assertIsNotNone(user)
        self.assertEqual(user.primary_org_id, self.unit.pk)

    def test_deepest_direct_group_selects_primary_org_and_preserves_both_scopes(self):
        self.configure_auto_login()
        for groups in ([self.group_dn(self.directory), self.group_dn()], [self.group_dn(), self.group_dn(self.directory)]):
            with self.subTest(groups=groups):
                user, _ = self.authenticate(self.login_entry(memberOf=groups))
                self.assertIsNotNone(user)
                self.assertEqual(user.primary_org_id, self.unit.pk)
                self.assertEqual(set(user.role_grants.filter(active=True).values_list("org_node_id", flat=True)), {self.unit.pk, self.directory.pk})
                self.assertFalse(user.role_grants.filter(active=True, includes_descendants=True).exists())

    def test_title_and_department_are_metadata_and_cannot_elevate_roles(self):
        self.configure_auto_login()
        user, _ = self.authenticate(self.login_entry(title="SYSTEM_ADMIN DIRECTOR", department=self.directory.code))
        self.assertIsNotNone(user)
        self.assertEqual(set(user.role_grants.filter(active=True).values_list("role", flat=True)), {"EMPLOYEE"})
        self.assertEqual(user.primary_org_id, self.unit.pk)

    def test_explicit_group_mapping_grants_only_approved_role_and_scope(self):
        mapping = self.mapping()
        self.configure_directory(auto_provision_enabled=True, match_organization_groups=True)
        update_configuration(self.director, "ldap", {"group_role_mappings": [mapping]})
        user, _ = self.authenticate(self.login_entry(memberOf=[mapping["group_dn"]]))
        self.assertIsNotNone(user)
        grant = user.role_grants.get(role="UNIT_HEAD", active=True)
        self.assertEqual(grant.org_node_id, self.unit.pk)
        self.assertTrue(grant.includes_descendants)
        self.assertFalse(user.role_grants.filter(role__in=["SYSTEM_ADMIN", "GOD_MODE"]).exists())

    def test_explicit_group_mapping_uses_entire_dn_not_matching_cn_elsewhere(self):
        mapping = self.mapping(role="EMPLOYEE", descendants=False)
        self.configure_auto_login(group_role_mappings=[mapping])
        before = self.persistent_counts()
        user, _ = self.authenticate(self.login_entry(memberOf=[mapping["group_dn"].replace("ou=groups", "ou=outside")]))
        self.assertIsNone(user)
        self.assertEqual(self.persistent_counts(), before)

    def test_imported_ldap_identity_can_login_when_auto_provisioning_is_disabled(self):
        self.configure_directory(auto_provision_enabled=False, match_organization_groups=False)
        entry = self.login_entry(memberOf=[])
        user = User.objects.create_user(username="alice", identity_source="ldap", profile_kind="LDAP", primary_org=self.unit)
        identity = LDAPIdentity.objects.create(user=user, subject=_ldap_subject(entry), distinguished_name=entry.entry_dn)
        grant = RoleGrant.objects.create(user=user, role="UNIT_HEAD", org_node=self.unit)
        result, _ = self.authenticate(entry)
        self.assertIsNotNone(result)
        self.assertEqual(result.pk, user.pk)
        identity.refresh_from_db()
        grant.refresh_from_db()
        self.assertTrue(grant.active)
        self.assertFalse(LDAPManagedGrant.objects.filter(identity=identity).exists())


class LDAPLoginDenialTests(LDAPAutoLoginFixtures):
    def setUp(self):
        super().setUp()
        self.configure_auto_login()

    def test_blank_credentials_do_not_open_directory_or_write_state(self):
        before = self.persistent_counts()
        with patch("administration.services._ldap_connection") as connect:
            for username, password in (("", self.password), ("alice", "")):
                with self.subTest(username=repr(username), password=repr(password)):
                    self.assertIsNone(authenticate_ldap(username, password))
        connect.assert_not_called()
        self.assertEqual(self.persistent_counts(), before)

    def test_wrong_password_cannot_create_user_identity_grants_or_audit(self):
        before = self.persistent_counts()
        user, transport = self.authenticate(accepted=False)
        self.assertIsNone(user)
        self.assertEqual(self.persistent_counts(), before)
        transport.rebind.assert_called_once()
        transport.unbind.assert_called_once()

    def test_zero_or_multiple_search_results_are_rejected_without_user_bind(self):
        before = self.persistent_counts()
        for entries in ([], [self.login_entry(), self.login_entry(username="other-alice", subject=b"second-subject")]):
            transport = self.connection_for(entries)
            with self.subTest(count=len(entries)), patch("administration.services._ldap_connection", return_value=transport):
                self.assertIsNone(authenticate_ldap("alice", self.password))
            transport.rebind.assert_not_called()
            self.assertEqual(self.persistent_counts(), before)

    def test_failed_search_never_uses_partial_entries(self):
        before = self.persistent_counts()
        transport = self.connection_for([self.login_entry()])
        transport.search.return_value = False
        with patch("administration.services._ldap_connection", return_value=transport):
            self.assertIsNone(authenticate_ldap("alice", self.password))
        transport.rebind.assert_not_called()
        self.assertEqual(self.persistent_counts(), before)

    def test_tls_failure_cannot_create_any_identity_or_grant(self):
        before = self.persistent_counts()
        with patch("administration.services._ldap_connection", side_effect=ssl.SSLCertVerificationError("synthetic invalid chain")):
            self.assertIsNone(authenticate_ldap("alice", self.password))
        self.assertEqual(self.persistent_counts(), before)

    def test_disabled_directory_account_never_binds_or_provisions(self):
        before = self.persistent_counts()
        user, transport = self.authenticate(self.login_entry(userAccountControl=514))
        self.assertIsNone(user)
        transport.rebind.assert_not_called()
        self.assertEqual(self.persistent_counts(), before)

    def test_missing_immutable_subject_or_canonical_username_is_rejected(self):
        before = self.persistent_counts()
        for entry in (self.login_entry(subject=None), self.login_entry(sAMAccountName=""), self.login_entry(sAMAccountName="someone-else")):
            with self.subTest(attributes=entry.entry_attributes_as_dict):
                user, _ = self.authenticate(entry)
                self.assertIsNone(user)
                self.assertEqual(self.persistent_counts(), before)

    def test_no_active_exact_group_match_denies_first_login(self):
        inactive = OrgNode.objects.create(code="INACTIVE", name="Inactive synthetic team", active=False)
        before = self.persistent_counts()
        for groups in (
            [],
            [f"cn=prefix-{self.unit.code},ou=groups,dc=example,dc=test"],
            [f"cn={self.unit.code}-suffix,ou=groups,dc=example,dc=test"],
            [f"ou={self.unit.code},dc=example,dc=test"],
            [f"cn={self.unit.code}"],
            [self.group_dn(inactive)],
        ):
            with self.subTest(groups=groups):
                user, _ = self.authenticate(self.login_entry(memberOf=groups))
                self.assertIsNone(user)
                self.assertEqual(self.persistent_counts(), before)

    def test_organization_code_group_outside_configured_directory_base_is_rejected(self):
        before = self.persistent_counts()
        external_group = f"cn={self.unit.code},ou=groups,dc=outside,dc=test"
        user, _ = self.authenticate(self.login_entry(memberOf=[external_group]))
        self.assertIsNone(user)
        self.assertEqual(self.persistent_counts(), before)

    def test_local_case_insensitive_username_collision_is_not_merged(self):
        local = User.objects.create_user(username="ALICE", password="synthetic-local-password", primary_org=self.other)
        before = self.persistent_counts()
        user, _ = self.authenticate()
        self.assertIsNone(user)
        local.refresh_from_db()
        self.assertEqual(local.identity_source, "local")
        self.assertEqual(local.primary_org_id, self.other.pk)
        self.assertTrue(local.check_password("synthetic-local-password"))
        self.assertEqual(self.persistent_counts(), before)
        self.assertFalse(LDAPIdentity.objects.filter(user=local).exists())

    def test_inactive_onecs_identity_is_not_reactivated(self):
        user, _ = self.authenticate()
        self.assertIsNotNone(user)
        user.is_active = False
        user.save(update_fields=["is_active"])
        before = self.persistent_counts()
        rejected, _ = self.authenticate()
        self.assertIsNone(rejected)
        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertEqual(self.persistent_counts(), before)

    def test_configuration_change_during_password_verification_prevents_writes(self):
        entry = self.login_entry()
        transport = self.connection_for([entry])
        before = self.persistent_counts()

        def change_configuration(**kwargs):
            update_configuration(self.admin, "ldap", {"timeout_seconds": 11})
            return True

        transport.rebind.side_effect = change_configuration
        with patch("administration.services._ldap_connection", return_value=transport):
            self.assertIsNone(authenticate_ldap("alice", self.password))
        self.assertEqual(self.persistent_counts()[:4], before[:4])
        self.assertFalse(AuditEvent.objects.filter(action__startswith="ldap.identity.").exists())

    def test_audit_failure_rolls_back_first_user_identity_and_grants_together(self):
        before = self.persistent_counts()
        transport = self.connection_for([self.login_entry()])
        with patch("administration.services._ldap_connection", return_value=transport), patch("administration.ldap_login.audit", side_effect=RuntimeError("synthetic audit failure")):
            self.assertIsNone(authenticate_ldap("alice", self.password))
        transport.rebind.assert_called_once()
        self.assertEqual(self.persistent_counts(), before)

    def test_login_search_escapes_filter_syntax_and_rejects_another_principal(self):
        before = self.persistent_counts()
        user, transport = self.authenticate(username="alice*)(objectClass=*)")
        self.assertIsNone(user)
        self.assertEqual(transport.search.call_args.args[1], "(sAMAccountName=alice\\2a\\29\\28objectClass=\\2a\\29)")
        transport.rebind.assert_not_called()
        self.assertEqual(self.persistent_counts(), before)

    def test_public_login_error_is_generic_and_does_not_fall_back_to_local_auth(self):
        local = User.objects.create_user(username="local-person", password=self.password)
        client = APIClient()
        expected = {"detail": "Kullanıcı adı veya parola hatalı.", "code": "invalid_credentials"}
        for username in ("unknown-person", local.username):
            transport = self.connection_for([])
            with self.subTest(username=username), patch("administration.services._ldap_connection", return_value=transport), patch("core.views.authenticate") as local_auth:
                response = client.post("/api/v1/auth/login/", {"method": "ldap", "username": username, "password": self.password}, format="json")
            self.assertEqual(response.status_code, 401, response.data)
            self.assertEqual(response.data, expected)
            local_auth.assert_not_called()
            self.assertNotIn("_auth_user_id", client.session)


class LDAPManagedGrantSynchronizationTests(LDAPAutoLoginFixtures):
    def setUp(self):
        super().setUp()
        self.configure_auto_login()

    def test_verified_reorganization_replaces_only_ldap_managed_grants(self):
        user, _ = self.authenticate()
        self.assertIsNotNone(user)
        old_grant = LDAPManagedGrant.objects.get(identity__user=user).grant
        manual = RoleGrant.objects.create(user=user, role="PROJECT_MANAGER", org_node=self.directory, granted_by=self.director)
        result, _ = self.authenticate(self.login_entry(memberOf=[self.group_dn(self.other)]))
        self.assertIsNotNone(result)
        self.assertEqual(result.pk, user.pk)
        user.refresh_from_db()
        old_grant.refresh_from_db()
        manual.refresh_from_db()
        self.assertEqual(user.primary_org_id, self.other.pk)
        self.assertFalse(old_grant.active)
        self.assertTrue(manual.active)
        self.assertTrue(user.role_grants.filter(role="EMPLOYEE", org_node=self.other, active=True, includes_descendants=False).exists())
        self.assertEqual(LDAPManagedGrant.objects.filter(identity__user=user, grant__active=True).count(), 1)
        self.assertTrue(AuditEvent.objects.filter(actor=user, action="ldap.identity.synchronized").exists())

    def test_group_removal_revokes_managed_grant_even_when_login_is_denied(self):
        user, _ = self.authenticate()
        self.assertIsNotNone(user)
        grant = LDAPManagedGrant.objects.get(identity__user=user).grant
        manual = RoleGrant.objects.create(user=user, role="EMPLOYEE", org_node=self.directory)
        result, transport = self.authenticate(self.login_entry(memberOf=[]))
        self.assertIsNone(result)
        transport.rebind.assert_called_once()
        grant.refresh_from_db()
        manual.refresh_from_db()
        self.assertFalse(grant.active)
        self.assertTrue(manual.active)

    def test_group_loss_clears_primary_org_and_removes_existing_session_audience_access(self):
        user, _ = self.authenticate()
        self.assertIsNotNone(user)
        announcement = Announcement.objects.create(
            title="Synthetic unit-only announcement",
            body="Visible only to the verified unit audience.",
            owner_org=self.unit,
            created_by=self.director,
            status="PUBLISHED",
        )
        announcement.audience.add(self.unit)
        existing_session = APIClient()
        existing_session.force_login(user)
        self.assertTrue(audience_visible(user, announcement))
        before = existing_session.get(f"/api/v1/announcements/{announcement.pk}/")
        self.assertEqual(before.status_code, 200, before.data)

        result, transport = self.authenticate(self.login_entry(memberOf=[]))
        self.assertIsNone(result)
        transport.rebind.assert_called_once()
        user.refresh_from_db()
        self.assertIsNone(user.primary_org_id)
        self.assertFalse(user.role_grants.filter(active=True).exists())
        self.assertFalse(audience_visible(user, announcement))
        after = existing_session.get(f"/api/v1/announcements/{announcement.pk}/")
        self.assertIn(after.status_code, (403, 404), after.data)

    def test_renamed_identity_collision_still_revokes_removed_manager_scope(self):
        mapping = self.mapping()
        update_configuration(self.director, "ldap", {"group_role_mappings": [mapping]})
        initial = self.login_entry(memberOf=[self.group_dn(self.directory), mapping["group_dn"]])
        user, _ = self.authenticate(initial)
        self.assertIsNotNone(user)
        self.assertEqual(user.primary_org_id, self.unit.pk)
        elevated = user.role_grants.get(role="UNIT_HEAD", active=True)
        employee = user.role_grants.get(role="EMPLOYEE", org_node=self.directory, active=True)
        identity = LDAPIdentity.objects.get(user=user)
        old_metadata = identity.metadata.copy()
        old_dn, old_synced_at = identity.distinguished_name, identity.synced_at
        old_username, old_display_name, old_email = user.username, user.display_name, user.email
        local = User.objects.create_user(username="renamed-alice", password="synthetic-local-password", primary_org=self.other)
        local_grant = RoleGrant.objects.create(user=local, role="EMPLOYEE", org_node=self.other)
        user_count, grant_count, managed_count = User.objects.count(), RoleGrant.objects.count(), LDAPManagedGrant.objects.count()
        changed = self.login_entry(
            username="renamed-alice",
            dn="uid=renamed-alice,ou=people,dc=example,dc=test",
            displayName="Collision profile must not be applied",
            mail="collision-change@example.test",
            memberOf=[self.group_dn(self.directory)],
        )

        result, transport = self.authenticate(changed, username="renamed-alice")
        self.assertIsNone(result)
        transport.rebind.assert_called_once()
        user.refresh_from_db()
        identity.refresh_from_db()
        elevated.refresh_from_db()
        employee.refresh_from_db()
        local.refresh_from_db()
        local_grant.refresh_from_db()
        self.assertFalse(elevated.active)
        self.assertTrue(employee.active)
        self.assertIsNone(user.primary_org_id)
        self.assertEqual((user.username, user.display_name, user.email), (old_username, old_display_name, old_email))
        self.assertEqual(identity.metadata, old_metadata)
        self.assertEqual((identity.distinguished_name, identity.synced_at), (old_dn, old_synced_at))
        self.assertEqual(identity.subject, _ldap_subject(changed))
        self.assertEqual(local.identity_source, "local")
        self.assertEqual(local.primary_org_id, self.other.pk)
        self.assertTrue(local.check_password("synthetic-local-password"))
        self.assertTrue(local_grant.active)
        self.assertFalse(LDAPIdentity.objects.filter(user=local).exists())
        self.assertEqual((User.objects.count(), RoleGrant.objects.count(), LDAPManagedGrant.objects.count()), (user_count, grant_count, managed_count))

    def test_failed_password_never_revokes_existing_grants_or_changes_metadata(self):
        user, _ = self.authenticate()
        self.assertIsNotNone(user)
        identity = LDAPIdentity.objects.get(user=user)
        old_metadata = identity.metadata.copy()
        before = self.persistent_counts()
        rejected, _ = self.authenticate(self.login_entry(memberOf=[], displayName="Unverified change"), accepted=False)
        self.assertIsNone(rejected)
        identity.refresh_from_db()
        self.assertEqual(identity.metadata, old_metadata)
        self.assertTrue(LDAPManagedGrant.objects.get(identity=identity).grant.active)
        self.assertEqual(self.persistent_counts(), before)

    def test_incomplete_ranged_memberships_do_not_revoke_existing_grants(self):
        user, _ = self.authenticate()
        self.assertIsNotNone(user)
        before = self.persistent_counts()
        entry = self.login_entry(memberOf=[], **{"memberOf;range=0-1499": [self.group_dn()]})
        rejected, transport = self.authenticate(entry)
        self.assertIsNone(rejected)
        transport.rebind.assert_not_called()
        self.assertTrue(LDAPManagedGrant.objects.get(identity__user=user).grant.active)
        self.assertEqual(self.persistent_counts(), before)

    def test_removed_explicit_mapping_role_does_not_survive_next_verified_login(self):
        mapping = self.mapping()
        update_configuration(self.director, "ldap", {"group_role_mappings": [mapping]})
        entry = self.login_entry(memberOf=[self.group_dn(), mapping["group_dn"]])
        user, _ = self.authenticate(entry)
        self.assertIsNotNone(user)
        elevated = user.role_grants.get(role="UNIT_HEAD", active=True)
        update_configuration(self.director, "ldap", {"group_role_mappings": []})
        result, _ = self.authenticate(entry)
        self.assertIsNotNone(result)
        elevated.refresh_from_db()
        self.assertFalse(elevated.active)
        self.assertTrue(user.role_grants.filter(role="EMPLOYEE", active=True).exists())

    def test_repeated_verified_login_never_turns_a_manual_grant_into_ldap_ownership(self):
        entry = self.login_entry()
        user = User.objects.create_user(username="alice", identity_source="ldap", profile_kind="LDAP", primary_org=self.unit)
        identity = LDAPIdentity.objects.create(user=user, subject=_ldap_subject(entry), distinguished_name=entry.entry_dn)
        manual = RoleGrant.objects.create(user=user, role="EMPLOYEE", org_node=self.unit, includes_descendants=False, granted_by=self.director)
        accepted, _ = self.authenticate(entry)
        self.assertIsNotNone(accepted)
        self.assertFalse(LDAPManagedGrant.objects.filter(identity=identity, grant=manual).exists())
        self.authenticate(self.login_entry(memberOf=[]))
        manual.refresh_from_db()
        self.assertTrue(manual.active)

    def test_login_audit_contains_neither_password_nor_raw_directory_profile(self):
        user, _ = self.authenticate(self.login_entry(department="Synthetic sensitive department"))
        self.assertIsNotNone(user)
        evidence = json.dumps(list(AuditEvent.objects.filter(actor=user).values("action", "data")), default=str)
        self.assertNotIn(self.password, evidence)
        self.assertNotIn("synthetic-directory-test-value", evidence)
        self.assertNotIn("Synthetic sensitive department", evidence)
        self.assertNotIn("memberOf", evidence)


class LDAPMappingConfigurationTests(LDAPAutoLoginFixtures):
    def setUp(self):
        super().setUp()
        self.configure_auto_login()

    def test_technical_admin_can_configure_employee_mapping(self):
        result = update_configuration(self.admin, "ldap", {"group_role_mappings": [self.mapping(role="EMPLOYEE", descendants=False)]})
        self.assertEqual(result["config"]["group_role_mappings"][0]["role"], "EMPLOYEE")

    def test_technical_admin_cannot_configure_business_role_mapping(self):
        versions = ConfigurationVersion.objects.count()
        with self.assertRaises(PermissionDenied):
            update_configuration(self.admin, "ldap", {"group_role_mappings": [self.mapping()]})
        self.assertEqual(ConfigurationVersion.objects.count(), versions)

    def test_director_can_configure_business_role_only_with_current_org_scope(self):
        versions = ConfigurationVersion.objects.count()
        with self.assertRaises(PermissionDenied):
            update_configuration(self.director, "ldap", {"group_role_mappings": [self.mapping(org=self.other, role="DIRECTOR")]})
        self.assertEqual(ConfigurationVersion.objects.count(), versions)
        accepted = update_configuration(self.director, "ldap", {"group_role_mappings": [self.mapping()]})
        self.assertEqual(accepted["config"]["group_role_mappings"][0]["org_node"], str(self.unit.pk))

    def test_director_without_system_admin_cannot_change_ldap_authorization_policy(self):
        self.director.role_grants.filter(role="SYSTEM_ADMIN").update(active=False)
        with self.assertRaises(PermissionDenied):
            update_configuration(self.director, "ldap", {"group_role_mappings": [self.mapping()]})

    def test_employee_cannot_change_ldap_provisioning_policy(self):
        with self.assertRaises(PermissionDenied):
            update_configuration(self.employee, "ldap", {"match_organization_groups": False})

    def test_another_users_view_cannot_approve_directory_roles(self):
        self.director._real_actor = self.admin
        self.addCleanup(lambda: delattr(self.director, "_real_actor"))
        with self.assertRaises(PermissionDenied):
            update_configuration(self.director, "ldap", {"group_role_mappings": [self.mapping()]})

    @override_settings(ONECS_ENV="test", ONECS_TEST_GOD_MODE=True)
    def test_god_mode_cannot_extend_directors_real_ldap_mapping_scope(self):
        self.director._god_mode = True
        self.addCleanup(lambda: delattr(self.director, "_god_mode"))
        with self.assertRaises(PermissionDenied):
            update_configuration(self.director, "ldap", {"group_role_mappings": [self.mapping(org=self.other, role="DIRECTOR")]})

    def test_invalid_mappings_cannot_publish_a_configuration_version(self):
        inactive = OrgNode.objects.create(code="OLD", name="Inactive synthetic org", active=False)
        invalid_mappings = [
            {**self.mapping(), "group_dn": "Synthetic Unit Heads"},
            {**self.mapping(), "group_dn": "cn=Synthetic Unit Heads"},
            {**self.mapping(), "org_node": str(inactive.pk)},
            {**self.mapping(), "org_node": ""},
            {**self.mapping(), "role": "SYSTEM_ADMIN"},
            {**self.mapping(), "role": "GOD_MODE"},
            {**self.mapping(), "role": "unrecognized-role"},
            {**self.mapping(), "includes_descendants": "true"},
        ]
        for mapping in invalid_mappings:
            versions = ConfigurationVersion.objects.count()
            with self.subTest(mapping=mapping), self.assertRaises(ValidationError):
                update_configuration(self.director, "ldap", {"group_role_mappings": [mapping]})
            self.assertEqual(ConfigurationVersion.objects.count(), versions)

    def test_ldap_auto_provisioning_flags_require_boolean_values(self):
        for key in ("auto_provision_enabled", "match_organization_groups"):
            with self.subTest(key=key), self.assertRaises(ValidationError):
                update_configuration(self.admin, "ldap", {key: "true"})


@skipUnless(connection.vendor == "postgresql", "Separate-connection provisioning requires PostgreSQL.")
class LDAPConcurrentProvisioningTests(TransactionTestCase):
    """Two real DB connections reach first-login persistence simultaneously."""

    setUp = DirectoryProfileFixtures.setUp
    configure_directory = DirectoryProfileFixtures.configure_directory
    ldap_entry = staticmethod(DirectoryProfileFixtures.ldap_entry)

    def test_simultaneous_verified_first_logins_create_one_identity_and_grant(self):
        self.configure_directory(auto_provision_enabled=True, match_organization_groups=True)
        ready = Barrier(2)
        user_password = "synthetic-concurrent-password"

        def directory_connection(*args, **kwargs):
            transport = Mock()
            transport.entries = [self.ldap_entry(memberOf=[f"cn={self.unit.code},ou=groups,dc=example,dc=test"])]
            transport.search.return_value = True

            def verified_user(**credentials):
                ready.wait(timeout=10)
                return credentials["password"] == user_password

            transport.rebind.side_effect = verified_user
            return transport

        def sign_in():
            close_old_connections()
            try:
                user = authenticate_ldap("alice", user_password)
                return user.pk if user else None
            finally:
                connections["default"].close()

        with patch("administration.services._ldap_connection", side_effect=directory_connection), ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(sign_in) for _ in range(2)]
            results = [future.result(timeout=20) for future in futures]

        self.assertIsNotNone(results[0])
        self.assertEqual(results[0], results[1])
        user = User.objects.get(username="alice")
        self.assertEqual(LDAPIdentity.objects.filter(user=user).count(), 1)
        self.assertEqual(user.role_grants.filter(active=True).count(), 1)
        self.assertEqual(LDAPManagedGrant.objects.filter(identity__user=user).count(), 1)
        self.assertEqual(AuditEvent.objects.filter(actor=user, action="ldap.identity.provisioned").count(), 1)
