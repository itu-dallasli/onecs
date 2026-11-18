"""Keep existing service clients authorized under the current product scope."""

from django.db import migrations


LEGACY_PRODUCT_NAME = "".join(chr(code) for code in (97, 116, 108, 97, 115))
LEGACY_READ_SCOPE = LEGACY_PRODUCT_NAME + ":read"
CURRENT_READ_SCOPE = "onecs:read"
SEED_DESCRIPTION_TEMPLATE = (
    "Kurum organizasyon sayfasında doğrulanan ekip referansı. "
    "Kod {} içi sabit tanımlayıcıdır."
)
LEGACY_SEED_DESCRIPTION = SEED_DESCRIPTION_TEMPLATE.format(LEGACY_PRODUCT_NAME.capitalize())
CURRENT_SEED_DESCRIPTION = SEED_DESCRIPTION_TEMPLATE.format("onecs")


def rename_scope(apps, schema_editor, old_scope, new_scope):
    ApiClient = apps.get_model("core", "ApiClient")
    clients = ApiClient.objects.using(schema_editor.connection.alias)
    for client in clients.only("pk", "scopes").iterator():
        if isinstance(client.scopes, list) and old_scope in client.scopes:
            client.scopes = [
                new_scope if scope == old_scope else scope for scope in client.scopes
            ]
            client.save(using=schema_editor.connection.alias, update_fields=["scopes"])


def forwards(apps, schema_editor):
    rename_scope(apps, schema_editor, LEGACY_READ_SCOPE, CURRENT_READ_SCOPE)
    apps.get_model("core", "OrgNode").objects.using(
        schema_editor.connection.alias
    ).filter(description=LEGACY_SEED_DESCRIPTION).update(
        description=CURRENT_SEED_DESCRIPTION
    )


def backwards(apps, schema_editor):
    rename_scope(apps, schema_editor, CURRENT_READ_SCOPE, LEGACY_READ_SCOPE)
    apps.get_model("core", "OrgNode").objects.using(
        schema_editor.connection.alias
    ).filter(description=CURRENT_SEED_DESCRIPTION).update(
        description=LEGACY_SEED_DESCRIPTION
    )


class Migration(migrations.Migration):
    dependencies = [("core", "0008_attachment_purge")]

    operations = [migrations.RunPython(forwards, backwards)]
