"""Verified directory discovery, metadata preview and explicit staged provisioning."""
import re
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from core.models import OrgNode, RoleGrant
from core.policy import require_admin, has_role, can_manage_org
from core.services import audit
from .models import LDAPIdentity, LDAPImportBatch
from .security import decrypt_secrets


ATTRIBUTE_KEYS = ("username_attribute", "display_name_attribute", "email_attribute", "department_attribute", "title_attribute", "manager_attribute", "membership_attribute")
DENIED_ATTRIBUTES = {"userpassword", "unicodepwd", "supplementalcredentials", "msds-managedpassword", "peklist"}


def _require_real_admin(actor):
    require_admin(actor)
    if getattr(actor, "_real_actor", actor).pk != actor.pk:
        raise PermissionDenied("Kullanıcı görünümü denenirken dizin yönetimi yapılamaz.")


def validate_directory_attributes(config):
    for key in ATTRIBUTE_KEYS:
        attribute = config.get(key, "")
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9-]{0,63}", attribute) or attribute.lower() in DENIED_ATTRIBUTES:
            raise ValidationError({key: "Güvenli bir dizin öznitelik adı gerekiyor."})


def _values(entry, attribute):
    attributes = getattr(entry, "entry_attributes_as_dict", {})
    value = next((value for key, value in attributes.items() if key.lower() == attribute.lower()), [])
    values = value if isinstance(value, list) else [value]
    return [str(item)[:1000] for item in values if item is not None][:50]


def _first(entry, attribute):
    values = _values(entry, attribute)
    return values[0] if values else ""


def root_dse(connection):
    import ldap3
    connection.search("", "(objectClass=*)", search_scope=ldap3.BASE, attributes=["defaultNamingContext", "namingContexts", "vendorName", "supportedLDAPVersion"])
    if not connection.entries:
        raise ValidationError({"ldap": "RootDSE bilgisi okunamadı; Base DN girin."})
    entry = connection.entries[0]
    bases = _values(entry, "namingContexts")
    preferred = _first(entry, "defaultNamingContext")
    if preferred and preferred not in bases:
        bases.insert(0, preferred)
    return {"base_dns": bases, "default_base_dn": preferred or (bases[0] if len(bases) == 1 else ""), "vendor": _first(entry, "vendorName"), "ldap_versions": _values(entry, "supportedLDAPVersion")}


def directory_base(connection, config, kind, selected=None):
    configured = config.get("user_search_base" if kind == "users" else "group_search_base") or config.get("base_dn")
    if selected:
        selected = str(selected).strip()
        roots = [configured] if configured else root_dse(connection)["base_dns"]
        if not any(selected.lower() == root.lower() or selected.lower().endswith("," + root.lower()) for root in roots):
            raise ValidationError({"base_dn": "Seçilen Base DN yapılandırılmış/keşfedilmiş kapsamın dışında."})
        return selected
    if configured:
        return configured
    discovered = root_dse(connection)
    if discovered["default_base_dn"]:
        return discovered["default_base_dn"]
    raise ValidationError({"base_dn": "Birden fazla dizin kapsamı var; Base DN açıkça seçilmeli."})


def directory_filter(config, kind, query, *, login=False):
    from ldap3.utils.conv import escape_filter_chars
    escaped = escape_filter_chars(str(query)[:150])
    if login:
        # Login is always an exact username match, even when the preview filter uses wildcards.
        return "(" + config.get("username_attribute", "sAMAccountName") + "=" + escaped + ")"
    template = config.get("user_filter" if kind == "users" else "group_filter") or ("(cn=*{query}*)" if kind == "groups" else "(sAMAccountName=*{query}*)")
    return template.replace("{query}", escaped).replace("{username}", escaped)


def _configured_connection():
    from .services import integration_snapshot, _ldap_connection
    _, version, config = integration_snapshot("ldap")
    if not version or not config.get("enabled"):
        raise ValidationError({"ldap": "LDAP yapılandırılmadı veya etkin değil."})
    validate_directory_attributes(config)
    return _ldap_connection(config, decrypt_secrets(version.encrypted_secrets)), version, config


def directory_discover(actor):
    _require_real_admin(actor)
    connection, version, config = _configured_connection()
    try:
        result = root_dse(connection)
        result.update({"server": config["url"], "configuration_version": version.version, "config_version": version.version})
        return result
    finally:
        from .services import _safe_ldap_unbind
        _safe_ldap_unbind(connection)


def directory_search(actor, kind="users", query="", base_dn=None):
    _require_real_admin(actor)
    if kind not in {"users", "groups"}:
        raise ValidationError({"kind": "users veya groups seçin."})
    connection, version, config = _configured_connection()
    try:
        import ldap3
        from .services import _ldap_subject
        base = directory_base(connection, config, kind, base_dn)
        attributes = list({config[key] for key in ATTRIBUTE_KEYS} | {"entryUUID", "objectGUID", "cn", "description", "userAccountControl"})
        connection.search(base, directory_filter(config, kind, query), search_scope=ldap3.SUBTREE, attributes=attributes, size_limit=100, time_limit=min(config.get("timeout_seconds", 10), 30))
        candidates = []
        for entry in connection.entries[:100]:
            try:
                subject = _ldap_subject(entry)
            except ValidationError:
                continue
            title = _first(entry, config["title_attribute"])
            candidate = {"subject": subject, "dn": entry.entry_dn, "username": _first(entry, config["username_attribute"]), "display_name": _first(entry, config["display_name_attribute"]) or _first(entry, "cn"), "email": _first(entry, config["email_attribute"]), "department": _first(entry, config["department_attribute"]), "title": title, "manager_dn": _first(entry, config["manager_attribute"]), "groups": _values(entry, config["membership_attribute"]), "role_hint": "Yönetici görevi olabilir; açık rol onayı gerekir" if any(word in title.casefold() for word in ("manager", "müdür", "direktör", "head")) else "Çalışan", "directory_enabled": not (int(_first(entry, "userAccountControl") or 0) & 2)}
            if kind == "groups":
                candidate["username"] = _first(entry, "cn")
                candidate["role_hint"] = "Grup önizlemesi; otomatik rol veya üye aktarımı yok"
            candidates.append(candidate)
        batch = LDAPImportBatch.objects.create(actor=actor, configuration_version=version.version, kind=kind, base_dn=base, candidates=candidates, expires_at=timezone.now() + timedelta(minutes=15))
        audit(actor, "ldap.directory.previewed", batch, {"kind": kind, "count": len(candidates), "configuration_version": version.version})
        return {"batch_id": str(batch.pk), "kind": kind, "configuration_version": version.version, "base_dn": base, "results": candidates, "truncated": len(candidates) >= 100}
    finally:
        from .services import _safe_ldap_unbind
        _safe_ldap_unbind(connection)


@transaction.atomic
def directory_import(actor, batch_id, entries, expected_config_version=None):
    _require_real_admin(actor)
    from .services import integration_snapshot
    batch = LDAPImportBatch.objects.select_for_update().filter(pk=batch_id, actor=actor).first()
    if not batch:
        raise NotFound("LDAP önizleme paketi bulunamadı.")
    _, current, _ = integration_snapshot("ldap")
    if batch.expires_at <= timezone.now() or not current or current.version != batch.configuration_version or (expected_config_version is not None and expected_config_version != batch.configuration_version):
        raise ValidationError({"batch_id": "LDAP önizlemesinin süresi/sürümü değişti; tekrar arayın."})
    if batch.kind != "users" or not isinstance(entries, list) or not entries or len(entries) > 100:
        raise ValidationError({"entries": "Kullanıcı önizlemesinden açık kişi, organizasyon ve rol seçimi gerekir."})
    candidates = {item["subject"]: item for item in batch.candidates}
    selected = []
    imported = set(batch.imported_subjects)
    for choice in entries:
        if not isinstance(choice, dict) or choice.get("subject") not in candidates or not choice.get("org_node") or not choice.get("role"):
            raise ValidationError({"entries": "Her kişi için subject, org_node ve role açıkça seçilmeli."})
        candidate = candidates[choice["subject"]]
        if not candidate.get("directory_enabled", True):
            raise ValidationError({"entries": "Devre dışı dizin hesabı etkinleştirilemez."})
        role = choice["role"]
        if role not in {"EMPLOYEE", "TEAM_MANAGER", "UNIT_HEAD", "PROJECT_MANAGER", "DIRECTOR"}:
            raise ValidationError({"role": "Dizin aktarımı teknik sistem yöneticisi rolü vermez."})
        org = OrgNode.objects.filter(pk=choice["org_node"], active=True).first()
        if not org:
            raise ValidationError({"org_node": "Etkin organizasyon gerekiyor."})
        if role != "EMPLOYEE" and (not has_role(actor, "DIRECTOR") or not can_manage_org(actor, org)):
            raise PermissionDenied("İş yönetimi rolü için direktörün güncel kapsam onayı gerekiyor.")
        identity = LDAPIdentity.objects.select_related("user").filter(subject=candidate["subject"]).first()
        if identity:
            user = identity.user
            if user.pk == actor.pk:
                raise PermissionDenied("Dizin aktarımıyla kendi yetkiniz değiştirilemez.")
            if candidate["subject"] in imported:
                selected.append(user)
                continue
            # Existing mapped identity may update metadata; changing roles/org requires normal grants flow.
            if user.primary_org_id != org.pk or not user.role_grants.filter(role=role, org_node=org, active=True).exists():
                raise ValidationError({"entries": "Mevcut hesabın kapsam/rol değişikliğini kullanıcı yönetimi akışından yapın."})
        else:
            username = candidate.get("username", "")
            if not username or get_user_model().objects.filter(username__iexact=username).exists():
                raise ValidationError({"username": "Kullanıcı adı mevcut kimlikle çakışıyor; otomatik birleştirme yapılmadı."})
            kwargs = {"username": username[:150], "display_name": candidate["display_name"][:160], "email": candidate["email"][:254], "primary_org": org, "identity_source": "ldap"}
            if any(field.name == "profile_kind" for field in get_user_model()._meta.fields):
                kwargs["profile_kind"] = "LDAP"
            user = get_user_model()(**kwargs)
            user.set_unusable_password()
            user.save()
            RoleGrant.objects.create(user=user, role=role, org_node=org, granted_by=actor)
            identity = LDAPIdentity.objects.create(user=user, subject=candidate["subject"], distinguished_name=candidate["dn"])
        identity.metadata = {key: candidate.get(key) for key in ("department", "title", "manager_dn", "groups", "role_hint")}
        identity.synced_at = timezone.now()
        identity.save(update_fields=["metadata", "synced_at"])
        imported.add(candidate["subject"])
        selected.append(user)
        audit(actor, "ldap.identity.imported", user, {"batch_id": str(batch.pk), "role": role, "org_node": str(org.pk), "configuration_version": batch.configuration_version})
    batch.imported_subjects = sorted(imported)
    batch.save(update_fields=["imported_subjects"])
    return selected
