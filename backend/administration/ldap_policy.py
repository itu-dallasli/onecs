"""Validate explicit directory group grants without inferring business authority."""

import uuid

from ldap3.utils.dn import LDAPInvalidDnError, parse_dn
from rest_framework.exceptions import PermissionDenied, ValidationError

from core.models import OrgNode
from core.policy import active_grants, grant_scope_ids, require_admin


LDAP_MAPPING_ROLES = {"EMPLOYEE", "TEAM_MANAGER", "UNIT_HEAD", "DIRECTOR", "PROJECT_MANAGER"}
MAPPING_FIELDS = {"group_dn", "org_node", "role", "includes_descendants"}


def validate_group_role_mappings(mappings):
    if not isinstance(mappings, list) or len(mappings) > 64:
        raise ValidationError({"group_role_mappings": "En fazla 64 grup eşlemesi içeren bir liste gerekiyor."})
    validated, seen = [], set()
    for row in mappings:
        if not isinstance(row, dict) or set(row) - MAPPING_FIELDS:
            raise ValidationError({"group_role_mappings": "Grup DN, organizasyon, rol ve alt kapsam alanları gerekiyor."})
        group_dn = row.get("group_dn")
        if not isinstance(group_dn, str) or not 1 <= len(group_dn.strip()) <= 2000 or any(char in group_dn for char in ("*", "{", "}", "\x00")):
            raise ValidationError({"group_role_mappings": "Joker veya şablon içermeyen tam grup DN adresi gerekiyor."})
        try:
            if len(parse_dn(group_dn.strip(), strip=True)) < 2:
                raise ValueError()
        except (LDAPInvalidDnError, ValueError):
            raise ValidationError({"group_role_mappings": "Geçerli tam grup DN adresi gerekiyor."}) from None
        role = row.get("role")
        if not isinstance(role, str) or role not in LDAP_MAPPING_ROLES:
            raise ValidationError({"group_role_mappings": "Desteklenen organizasyon rolünü seçin; LDAP grubu sistem yöneticisi yetkisi vermez."})
        includes_descendants = row.get("includes_descendants", False)
        if not isinstance(includes_descendants, bool):
            raise ValidationError({"group_role_mappings": "Alt organizasyon kapsamı boolean olmalı."})
        try:
            org_id = uuid.UUID(str(row.get("org_node", "")))
        except (ValueError, TypeError, AttributeError):
            raise ValidationError({"group_role_mappings": "Geçerli organizasyon seçin."}) from None
        org = OrgNode.objects.filter(pk=org_id, active=True).first()
        if not org:
            raise ValidationError({"group_role_mappings": "Etkin organizasyon seçin."})
        if (role == "TEAM_MANAGER" and org.kind != "TEAM") or (role == "UNIT_HEAD" and org.kind != "UNIT"):
            raise ValidationError({"group_role_mappings": "Ekip yöneticisi ekip, birim yöneticisi birim kapsamında eşlenmeli."})
        item = {"group_dn": group_dn.strip(), "org_node": str(org.pk), "role": role, "includes_descendants": includes_descendants}
        key = (item["group_dn"].casefold(), item["org_node"], role, includes_descendants)
        if key in seen:
            raise ValidationError({"group_role_mappings": "Aynı grup ve yetki eşlemesi tekrarlanamaz."})
        seen.add(key)
        validated.append(item)
    return validated


def validate_mapping_authority(actor, previous, config):
    """Changing a delegated business grant needs its original scope authority."""
    before = previous.get("group_role_mappings", [])
    after = config.get("group_role_mappings", [])
    switches = ("auto_provision_enabled", "match_organization_groups")
    policy_changed = before != after or any(previous.get(key, True) != config.get(key, True) for key in switches)
    if not policy_changed:
        return
    require_admin(actor)
    if getattr(actor, "_real_actor", actor).pk != actor.pk:
        raise PermissionDenied("Kullanıcı görünümünde LDAP yetki eşlemesi değiştirilemez.")
    def key(row):
        return (row["group_dn"].casefold(), row["org_node"], row["role"], row.get("includes_descendants", False))

    before_keys, after_keys = {key(row) for row in before}, {key(row) for row in after}
    switches_changed = any(previous.get(name, True) != config.get(name, True) for name in switches)
    # Removing mappings can revoke access too, so check changed old/new scopes.
    affected = [row for row in before + after if switches_changed or key(row) in before_keys ^ after_keys]
    director_scope = set()
    for grant in active_grants(actor).filter(role="DIRECTOR").select_related("org_node"):
        director_scope |= grant_scope_ids(grant)
    for row in affected:
        if row.get("role") == "EMPLOYEE":
            continue
        org = OrgNode.objects.filter(pk=row["org_node"], active=True).first()
        if not org or org.pk not in director_scope:
            raise PermissionDenied("LDAP iş yönetimi eşlemesi için direktörün hedef organizasyonda yetkisi gerekiyor.")
