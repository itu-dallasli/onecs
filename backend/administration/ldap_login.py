"""LDAP authentication and atomic provisioning from verified direct memberships.

Directory searches and the personal bind finish before any account or grant is
written. A permanent directory subject identifies the account; names and email
addresses never join a directory account to an existing local account.
"""

import hashlib
import json
import re

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from core.models import OrgNode, RoleGrant
from core.services import audit

from .models import IntegrationConfiguration, LDAPIdentity, LDAPManagedGrant


MAX_MEMBERSHIPS = 2000


def _decoded_dn_value(value):
    """Decode RFC 4514 escapes, including UTF-8 hexadecimal octets."""
    # BER-encoded values need schema knowledge. They cannot be used as a safe
    # text group match, so fail closed rather than equating their spellings.
    if value.startswith("#"):
        raise ValueError("Unsupported directory name encoding")
    decoded = bytearray()
    index = 0
    while index < len(value):
        if value[index] != "\\":
            decoded.extend(value[index].encode("utf-8"))
            index += 1
            continue
        index += 1
        if index >= len(value):
            raise ValueError("Incomplete directory name escape")
        if index + 1 < len(value) and re.fullmatch(r"[0-9a-fA-F]{2}", value[index:index + 2]):
            decoded.append(int(value[index:index + 2], 16))
            index += 2
        else:
            decoded.extend(value[index].encode("utf-8"))
            index += 1
    return decoded.decode("utf-8").casefold()


def _canonical_dn(dn, *, minimum_rdns=2):
    """Keep RDN boundaries while comparing decoded, case-insensitive values."""
    from ldap3.utils.dn import parse_dn

    if not isinstance(dn, str) or not dn or len(dn) > 2000:
        raise ValueError("Invalid directory name")
    rdns, current = [], []
    for attribute, value, separator in parse_dn(dn, strip=True):
        current.append((attribute.casefold(), _decoded_dn_value(value)))
        if separator != "+":
            rdns.append(tuple(sorted(current)))
            current = []
    if current or len(rdns) < minimum_rdns:
        raise ValueError("Invalid directory name")
    return tuple(rdns)


def _group_key(group, role, org_id, includes_descendants):
    value = json.dumps(
        [group, role, str(org_id), includes_descendants],
        separators=(",", ":"), ensure_ascii=False,
    )
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def resolve_group_grants(config, groups):
    """Resolve direct group DNs to bounded grants, without modifying accounts.

    An explicit full-DN mapping takes precedence over the organization-code
    fallback for that same group. The fallback grants EMPLOYEE for one active
    organization whose code exactly matches the decoded leaf CN within the
    configured or service-discovered directory partition.
    """
    from .ldap_policy import validate_group_role_mappings

    if not isinstance(groups, (list, tuple)) or len(groups) > MAX_MEMBERSHIPS:
        raise ValueError("Invalid directory memberships")
    memberships = {_canonical_dn(group) for group in groups}
    mappings = validate_group_role_mappings(config.get("group_role_mappings", []))
    explicit = {}
    for row in mappings:
        group = _canonical_dn(row["group_dn"])
        explicit.setdefault(group, []).append(row)

    active_orgs = list(OrgNode.objects.filter(active=True))
    orgs_by_id = {str(org.pk): org for org in active_orgs}
    orgs_by_code = {}
    for org in active_orgs:
        orgs_by_code.setdefault(org.code.casefold(), []).append(org)

    base_dn = config.get("group_search_base") or config.get("base_dn") or config.get("_resolved_group_base")
    group_base = _canonical_dn(base_dn, minimum_rdns=1) if base_dn else None

    resolved = {}
    # Sorting makes the primary organization stable across memberOf ordering.
    for group in sorted(memberships):
        matches = explicit.get(group, [])
        if matches:
            for row in matches:
                org = orgs_by_id.get(str(row["org_node"]))
                if org is None:
                    raise ValueError("Inactive mapped organization")
                descendants = row.get("includes_descendants", False)
                key = _group_key(group, row["role"], org.pk, descendants)
                resolved[key] = {
                    "key": key, "role": row["role"], "org_node": org,
                    "includes_descendants": descendants,
                }
            continue
        if config.get("match_organization_groups", True) is not True:
            continue
        # Organization-code convenience matching stays in the configured
        # directory partition. Equal CNs in another directory cannot grant it.
        # Explicit full-DN mappings above remain an administrator's choice.
        if group_base is None or len(group) < len(group_base) or group[-len(group_base):] != group_base:
            continue
        cns = [value for attribute, value in group[0] if attribute == "cn"]
        if len(cns) != 1:
            continue
        candidates = orgs_by_code.get(cns[0], [])
        if len(candidates) > 1:
            raise ValueError("Ambiguous organization code")
        if not candidates:
            continue
        org = candidates[0]
        key = _group_key(group, "EMPLOYEE", org.pk, False)
        resolved[key] = {
            "key": key, "role": "EMPLOYEE", "org_node": org,
            "includes_descendants": False,
        }
    return [resolved[key] for key in sorted(resolved)]


def _profile_valid(profile, subject):
    username = profile.get("username")
    dn = profile.get("dn")
    return (
        isinstance(subject, str) and 0 < len(subject) <= 300
        and isinstance(username, str) and 0 < len(username) <= 150
        and username == username.strip()
        and not any(ord(character) < 32 for character in username)
        and isinstance(dn, str) and 0 < len(dn) <= 1000
        and profile.get("directory_enabled", True) is True
    )


def _select_primary_org(desired):
    """Prefer the deepest directly mapped organization, then its stable code."""
    parents = dict(OrgNode.objects.values_list("pk", "parent_id"))
    depths = {}

    def depth(org_id):
        if org_id in depths:
            return depths[org_id]
        visited, current_id = set(), org_id
        while current_id is not None:
            if current_id in visited:
                raise ValueError("Cyclic organization hierarchy")
            visited.add(current_id)
            current_id = parents.get(current_id)
        depths[org_id] = len(visited)
        return depths[org_id]

    priorities = {
        "EMPLOYEE": 0, "TEAM_MANAGER": 1, "UNIT_HEAD": 2,
        "DIRECTOR": 3, "PROJECT_MANAGER": 4,
    }
    return min(desired, key=lambda item: (
        -depth(item["org_node"].pk), item["org_node"].code.casefold(),
        priorities[item["role"]], str(item["org_node"].pk), item["key"],
    ))["org_node"]


def _reconcile_grants(identity, desired, *, revoke_only=False):
    """Change only grants carrying this LDAP identity's ownership marker."""
    owned = {
        link.key: link
        for link in LDAPManagedGrant.objects.select_for_update()
        .select_related("grant").filter(identity=identity)
    }
    keys = {item["key"] for item in desired}
    added, updated, revoked = 0, 0, 0
    for key, link in owned.items():
        if key not in keys and link.grant.active:
            link.grant.active = False
            link.grant.version += 1
            link.grant.save(update_fields=["active", "version", "updated_at"])
            revoked += 1
    if revoke_only:
        return {"added": added, "updated": updated, "revoked": revoked}
    for item in desired:
        link = owned.get(item["key"])
        expected = {
            "user_id": identity.user_id,
            "role": item["role"], "org_node_id": item["org_node"].pk,
            "includes_descendants": item["includes_descendants"],
            "active": True, "expires_at": None, "permissions": [],
        }
        if link is None:
            # The grant is created by directory policy, not by the person who
            # last edited its configuration or the person signing in.
            grant = RoleGrant.objects.create(granted_by=None, **expected)
            LDAPManagedGrant.objects.create(identity=identity, grant=grant, key=item["key"])
            added += 1
            continue
        grant = link.grant
        changed = [name for name, value in expected.items() if getattr(grant, name) != value]
        if changed:
            for name in changed:
                setattr(grant, name, expected[name])
            grant.version += 1
            grant.save(update_fields=[*changed, "version", "updated_at"])
            updated += 1
    return {"added": added, "updated": updated, "revoked": revoked}


def _revoke_denied_identity(user, identity, version, desired, *, clear_managed_org=False):
    """Apply only revocations when verified LDAP credentials cannot open a session.

    A username collision must not prevent removal of obsolete LDAP privileges.
    Primary organization is access-bearing even without a role grant, so clear
    a stale managed organization within the same access-version transaction.
    """
    had_managed_grants = LDAPManagedGrant.objects.filter(identity=identity).exists()
    counts = _reconcile_grants(identity, desired, revoke_only=True)
    desired_orgs = {item["org_node"].pk for item in desired}
    clear_org = user.primary_org_id is not None and (
        (clear_managed_org and had_managed_grants)
        or (not clear_managed_org and user.primary_org_id not in desired_orgs)
    )
    if not any(counts.values()) and not clear_org:
        return
    fields = ["access_version"]
    if clear_org:
        user.primary_org = None
        fields.append("primary_org")
    user.access_version += 1
    user.save(update_fields=fields)
    audit(user, "ldap.identity.synchronized", user, {
        **counts, "configuration_version": version.version,
        "grant_count": len(desired), "organization_revoked_count": int(clear_org),
    })


@transaction.atomic
def sync_authenticated_identity(version, config, subject, profile, groups):
    """Persist an already authenticated directory snapshot under its config lock.

    Returning None after a group loss intentionally commits managed-grant
    revocation. An exception rolls back account, grant and audit writes together.
    """
    if not isinstance(profile, dict) or not _profile_valid(profile, subject):
        return None
    current = IntegrationConfiguration.objects.select_for_update().filter(
        pk=version.configuration_id, section="ldap",
    ).first()
    if current is None or current.active_version != version.version:
        return None
    if config.get("enabled") is not True:
        return None

    User = get_user_model()
    identity = LDAPIdentity.objects.select_for_update().filter(subject=subject).first()
    user = None
    if identity:
        user = User.objects.select_for_update().get(pk=identity.user_id)
        if not user.is_active or user.identity_source != "ldap":
            return None

    if config.get("auto_provision_enabled", True) is not True:
        # Preserve explicitly provisioned legacy accounts when automatic group
        # provisioning is disabled; this mode never creates or alters grants.
        return user

    desired = resolve_group_grants(config, groups)
    if not desired:
        if user is not None:
            _revoke_denied_identity(
                user, identity, version, [], clear_managed_org=True,
            )
        return None

    username = profile["username"]
    collision = User.objects.filter(username__iexact=username)
    if user is not None:
        collision = collision.exclude(pk=user.pk)
    if collision.exists():
        if user is not None:
            _revoke_denied_identity(user, identity, version, desired)
        return None

    created = user is None
    primary_org = _select_primary_org(desired)
    if created:
        user = User(
            username=username, identity_source="ldap", profile_kind="LDAP",
            primary_org=primary_org,
        )
        user.set_unusable_password()
    old_primary_org = user.primary_org_id
    user.username = username
    user.display_name = str(profile.get("display_name") or username)[:160]
    user.email = str(profile.get("email") or "")[:254]
    user.primary_org = primary_org
    user.profile_kind = "LDAP"
    user.save()
    if created:
        identity = LDAPIdentity.objects.create(
            user=user, subject=subject, distinguished_name=profile["dn"],
        )
    counts = _reconcile_grants(identity, desired)
    if not created and (any(counts.values()) or old_primary_org != primary_org.pk):
        user.access_version += 1
        user.save(update_fields=["access_version"])

    identity.distinguished_name = profile["dn"]
    identity.metadata = {
        key: str(profile.get(key) or "")[:1000]
        for key in ("department", "title", "manager_dn")
    }
    identity.metadata["groups"] = list(groups)
    identity.metadata["configuration_version"] = version.version
    identity.synced_at = timezone.now()
    identity.save(update_fields=["distinguished_name", "metadata", "synced_at"])
    audit(user, "ldap.identity.provisioned" if created else "ldap.identity.synchronized", user, {
        **counts, "configuration_version": version.version,
        "grant_count": len(desired),
    })
    return user


def _entry_values(entry, attribute):
    attributes = entry.entry_attributes_as_dict
    values = next((value for key, value in attributes.items() if key.casefold() == attribute.casefold()), [])
    if not isinstance(values, (list, tuple)):
        values = [values]
    return [str(value) for value in values if value is not None]


def _entry_first(entry, attribute):
    values = _entry_values(entry, attribute)
    return values[0] if values else ""


def _entry_snapshot(entry, config):
    membership_attribute = config["membership_attribute"]
    if any(
        key.casefold().startswith(membership_attribute.casefold() + ";range=")
        for key in entry.entry_attributes_as_dict
    ):
        # Active Directory may return a partial ranged membership attribute.
        # Treating that partial list as complete would revoke valid grants.
        raise ValueError("Incomplete directory memberships")
    groups = _entry_values(entry, membership_attribute)
    if len(groups) > MAX_MEMBERSHIPS:
        raise ValueError("Too many directory memberships")
    account_control = int(_entry_first(entry, "userAccountControl") or 0)
    profile = {
        "username": _entry_first(entry, config["username_attribute"]),
        "display_name": _entry_first(entry, config["display_name_attribute"]) or _entry_first(entry, "cn"),
        "email": _entry_first(entry, config["email_attribute"]),
        "department": _entry_first(entry, config["department_attribute"]),
        "title": _entry_first(entry, config["title_attribute"]),
        "manager_dn": _entry_first(entry, config["manager_attribute"]),
        "dn": entry.entry_dn,
        "directory_enabled": not bool(account_control & 2),
    }
    return profile, groups


def authenticate_ldap(username, password):
    """Validate the personal LDAP bind, then synchronize its identity and grants."""
    from . import services
    from .directory import ATTRIBUTE_KEYS, directory_base, directory_filter, validate_directory_attributes
    from .security import decrypt_secrets

    if (
        not isinstance(username, str) or not username or len(username) > 150
        or not isinstance(password, str) or not password
    ):
        return None
    _, version, config = services.integration_snapshot("ldap")
    if not version or config.get("enabled") is not True:
        return None
    try:
        validate_directory_attributes(config)
        connection = services._ldap_connection(config, decrypt_secrets(version.encrypted_secrets))
        try:
            user_base = directory_base(connection, config, "users")
            if not (config.get("group_search_base") or config.get("base_dn")):
                config = {
                    **config,
                    "_resolved_group_base": directory_base(connection, config, "groups"),
                }
            attributes = list({config[key] for key in ATTRIBUTE_KEYS} | {
                "entryUUID", "objectGUID", "cn", "userAccountControl",
            })
            found = connection.search(
                user_base,
                directory_filter(config, "users", username, login=True),
                attributes=attributes, size_limit=2,
                time_limit=min(config.get("timeout_seconds", 10), 30),
            )
            if found is False or len(connection.entries) != 1:
                return None
            entry = connection.entries[0]
            subject = services._ldap_subject(entry)
            profile, groups = _entry_snapshot(entry, config)
            if (
                not _profile_valid(profile, subject)
                or profile["username"].casefold() != username.casefold()
            ):
                return None
            # Bind the DN of this immutable subject, never a template that can
            # point to a different principal. Capture metadata while bound as
            # the directory service account, before the personal rebind.
            if not connection.rebind(user=profile["dn"], password=password):
                return None
        finally:
            services._safe_ldap_unbind(connection)
        return sync_authenticated_identity(version, config, subject, profile, groups)
    except Exception:
        # The public login endpoint deliberately uses one credential failure;
        # directory records, passwords and endpoint exceptions are not logged.
        return None
