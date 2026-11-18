from importlib import import_module
from types import SimpleNamespace

from django.apps import apps
from django.db import connection

from core.models import ApiClient, OrgNode
from core.tests.base import OnecsTestCase


class ProductScopeMigrationTests(OnecsTestCase):
    def test_seed_description_rename_preserves_customized_human_text(self):
        migration = import_module("core.migrations.0009_onecs_brand")
        schema_editor = SimpleNamespace(connection=connection)
        previous = migration.LEGACY_SEED_DESCRIPTION
        customized = previous + " Kurum içi insan notu."
        unrelated = "İnsan tarafından yazılan bağımsız ekip açıklaması."
        OrgNode.objects.filter(pk=self.unit.pk).update(description=previous)
        OrgNode.objects.filter(pk=self.team.pk).update(description=customized)
        OrgNode.objects.filter(pk=self.other_unit.pk).update(description=unrelated)

        for operation, expected in [
            (
                migration.forwards,
                "Kurum organizasyon sayfasında doğrulanan ekip referansı. "
                "Kod onecs içi sabit tanımlayıcıdır.",
            ),
            (migration.backwards, previous),
        ]:
            with self.subTest(direction=operation.__name__):
                operation(apps, schema_editor)
                operation(apps, schema_editor)
                self.unit.refresh_from_db()
                self.team.refresh_from_db()
                self.other_unit.refresh_from_db()
                self.assertEqual(self.unit.description, expected)
                self.assertEqual(self.team.description, customized)
                self.assertEqual(self.other_unit.description, unrelated)

    def test_scope_rename_and_reverse_preserve_client_authorization_boundaries(self):
        migration = import_module("core.migrations.0009_onecs_brand")
        schema_editor = SimpleNamespace(connection=connection)
        old_scope = migration.LEGACY_READ_SCOPE
        clients = [
            ApiClient.objects.create(
                name="Scoped service client",
                user=self.director,
                org_node=self.team,
                scopes=[old_scope, "work:read", "directory:read"],
                token_version=7,
            ),
            ApiClient.objects.create(
                name="Revoked service client",
                user=self.employee,
                org_node=self.team,
                scopes=["work:read", old_scope],
                active=False,
                token_version=11,
            ),
            ApiClient.objects.create(
                name="Unrelated narrow client",
                user=self.outsider,
                org_node=self.other_unit,
                scopes=["directory:read"],
                token_version=3,
            ),
        ]
        boundaries = {
            client.pk: (
                client.user_id,
                client.org_node_id,
                client.token_version,
                client.active,
            )
            for client in clients
        }
        original_scopes = [list(client.scopes) for client in clients]

        for operation, expected_scopes in [
            (migration.forwards, [
                ["onecs:read", "work:read", "directory:read"],
                ["work:read", "onecs:read"],
                ["directory:read"],
            ]),
            (migration.backwards, original_scopes),
        ]:
            with self.subTest(direction=operation.__name__):
                operation(apps, schema_editor)
                operation(apps, schema_editor)
                for client, scopes in zip(clients, expected_scopes):
                    client.refresh_from_db()
                    self.assertEqual(client.scopes, scopes)
                    self.assertEqual(
                        (
                            client.user_id,
                            client.org_node_id,
                            client.token_version,
                            client.active,
                        ),
                        boundaries[client.pk],
                    )
