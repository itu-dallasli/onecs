"""Central, deny-by-default Atlas relationship and organizational policies."""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from .models import (
    CommunityCard,
    Credential,
    ParticipationRequest,
    Announcement,
    OrgNode,
    Project,
    RoleGrant,
    WorkItem,
    Case,
)


def active_actor(user):
    return bool(user and getattr(user, "is_authenticated", False) and user.is_active)


def active_grants(user):
    if not active_actor(user):
        return RoleGrant.objects.none()
    return user.role_grants.filter(active=True).filter(
        Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())
    )


def has_role(user, role):
    return active_grants(user).filter(role=role).exists()


def is_god_mode(user):
    """Only middleware can attach this flag; simulation must use real policy."""
    return (
        active_actor(user)
        and settings.ATLAS_ENV in ("test", "demo")
        and settings.ATLAS_TEST_GOD_MODE
        and getattr(user, "_god_mode", False)
        and not getattr(user, "_real_actor", None)
        and has_role(user, "SYSTEM_ADMIN")
    )


def is_system_admin(user):
    return has_role(user, "SYSTEM_ADMIN")


def require_admin(user):
    if not is_system_admin(user):
        raise PermissionDenied("Bu işlem için sistem yöneticisi yetkisi gerekir.")


def descendants_ids(org_id):
    if not org_id:
        return set()
    nodes = list(OrgNode.objects.filter(active=True).values_list("id", "parent_id"))
    active_ids = {pk for pk, _ in nodes}
    if org_id not in active_ids:
        return set()
    result = {org_id}
    while True:
        found = {pk for pk, parent in nodes if parent in result} - result
        if not found:
            return result
        result |= found


def grant_scope_ids(grant):
    if not grant.org_node_id:
        return set()
    if grant.includes_descendants:
        return descendants_ids(grant.org_node_id)
    return {grant.org_node_id} if grant.org_node.active else set()


def api_scope_ids(user):
    """None means an internal/unrestricted client; an empty set denies all orgs."""
    client = getattr(user, "_api_client", None)
    return (
        descendants_ids(client.org_node_id) if client and client.org_node_id else None
    )


def api_org_allowed(user, org):
    scope = api_scope_ids(user)
    return scope is None or getattr(org, "pk", org) in scope


def manager_scope_ids(user, roles=("DIRECTOR", "UNIT_HEAD", "TEAM_MANAGER")):
    if is_god_mode(user):
        ids = set(OrgNode.objects.filter(active=True).values_list("id", flat=True))
    else:
        ids = set()
        for grant in (
            active_grants(user).filter(role__in=roles).select_related("org_node")
        ):
            ids |= grant_scope_ids(grant)
    scope = api_scope_ids(user)
    return ids if scope is None else ids & scope


def can_manage_org(user, org):
    return getattr(org, "pk", org) in manager_scope_ids(user)


def is_director(user):
    return has_role(user, "DIRECTOR")


def can_reroute_project(user, project):
    """Continuity authority survives a PM account being disabled."""
    if not active_actor(user):
        return False
    if is_god_mode(user):
        return True
    governing_org = project.appointment.governing_org_id
    return active_grants(user).filter(
        role="UNIT_HEAD", org_node_id=governing_org
    ).exists() or governing_org in manager_scope_ids(user, ("DIRECTOR",))


def can_manage_project(user, project, permission="manage"):
    if not active_actor(user):
        return False
    if is_god_mode(user):
        return True
    appointment = project.appointment
    if not appointment.active or not appointment.user.is_active:
        return False
    if appointment.user_id == user.id:
        return True
    if (
        active_grants(user)
        .filter(role="UNIT_HEAD", org_node_id=appointment.governing_org_id)
        .exists()
    ):
        return True
    grants = project.authorities.filter(
        user=user, active=True, expires_at__gt=timezone.now()
    ).select_related("granted_by")
    for grant in grants:
        readable_action = permission == "read" and bool(grant.permissions)
        if (
            not readable_action
            and permission not in grant.permissions
            and "manage" not in grant.permissions
        ):
            continue
        grantor = grant.granted_by
        if not active_actor(grantor):
            continue
        if (
            grantor.id == appointment.user_id
            or active_grants(grantor)
            .filter(role="UNIT_HEAD", org_node_id=appointment.governing_org_id)
            .exists()
        ):
            return True
    return False


def can_approve_project(user, project):
    author_id = project.created_by_id
    if project.submitted_revision:
        pending = project.revisions.filter(
            number=project.submitted_revision, decision="PENDING"
        ).first()
        if pending:
            author_id = pending.author_id
    return (
        active_actor(user)
        and author_id != user.id
        and can_manage_project(user, project, "approve")
    )


def project_resource_scope_ids(user, project):
    scope = manager_scope_ids(user)
    if not scope:
        return set()
    member_orgs = set(
        project.memberships.filter(active=True, user__is_active=True).values_list(
            "user__primary_org_id", flat=True
        )
    )
    return scope if member_orgs & scope else set()


def can_read_project_detail(user, project):
    if not active_actor(user) or not api_org_allowed(user, project.owner_org_id):
        return False
    if is_god_mode(user):
        return True
    if not project.published_revision and project.created_by_id == user.id:
        return True
    if (
        project.status != "DRAFT"
        and can_reroute_project(user, project)
        and active_grants(user)
        .filter(role="UNIT_HEAD", org_node_id=project.appointment.governing_org_id)
        .exists()
    ):
        return True
    return (
        can_manage_project(user, project, "read")
        or project.memberships.filter(user=user, active=True).exists()
    )


def can_read_project(user, project):
    if not active_actor(user) or not api_org_allowed(user, project.owner_org_id):
        return False
    if is_god_mode(user):
        return True
    if project.status == "DRAFT":
        return project.created_by_id == user.id
    if (
        not project.appointment.active or not project.appointment.user.is_active
    ) and can_reroute_project(user, project):
        return True
    if can_manage_project(user, project, "read"):
        return True
    if not project.published_revision:
        return project.created_by_id == user.id
    director_scope = manager_scope_ids(user, ("DIRECTOR",))
    if (
        project.owner_org_id in director_scope
        or project.appointment.governing_org_id in director_scope
    ):
        return True
    if project.memberships.filter(user=user, active=True).exists():
        return True
    if project_resource_scope_ids(user, project):
        return True
    return user.primary_org_id is not None and any(
        user.primary_org_id in descendants_ids(org_id)
        for org_id in project.audience.values_list("id", flat=True)
    )


def can_manage_case(user, case):
    return active_actor(user) and (
        case.coordinator_id == user.id or can_manage_org(user, case.owner_org_id)
    )


def can_read_case(user, case):
    return (
        active_actor(user)
        and api_org_allowed(user, case.owner_org_id)
        and (
            can_manage_case(user, case)
            or case.members.filter(id=user.id).exists()
            or can_verify_case(user, case)
        )
    )


def can_verify_case(user, case):
    if not active_actor(user) or case.closure_requested_by_id == user.id:
        return False
    if is_god_mode(user):
        return True
    if case.owner_org_id in manager_scope_ids(user, ("DIRECTOR", "UNIT_HEAD")):
        return True
    if case.verifier_id == user.id and any(
        has_role(user, role) for role in ("TEAM_MANAGER", "UNIT_HEAD", "DIRECTOR")
    ):
        return True
    return any(
        "case.verify" in grant.permissions
        and case.owner_org_id in grant_scope_ids(grant)
        for grant in active_grants(user)
    )


def can_open_case(user, org):
    if not active_actor(user):
        return False
    org_id = getattr(org, "pk", org)
    if org_id in manager_scope_ids(user, ("DIRECTOR", "UNIT_HEAD")):
        return True
    return any(
        "case.create" in grant.permissions and org_id in grant_scope_ids(grant)
        for grant in active_grants(user)
    )


def can_read_work(user, work):
    if not active_actor(user) or not api_org_allowed(user, work.owner_org_id):
        return False
    if work.context == "PROJECT_TASK":
        return can_read_project(user, work.project) and (
            can_read_project_detail(user, work.project)
            or work.assigned_to_id == user.id
            or can_manage_org(user, work.assigned_to.primary_org_id)
        )
    if work.context == "CASE_ACTION":
        return can_read_case(user, work.case)
    return work.assigned_to_id == user.id or can_manage_org(user, work.owner_org_id)


def can_manage_work(user, work):
    if not active_actor(user):
        return False
    if work.context == "PROJECT_TASK":
        return can_manage_project(user, work.project)
    if work.context == "CASE_ACTION":
        return can_manage_case(user, work.case)
    return can_manage_org(user, work.owner_org_id)


def can_update_work(user, work):
    return active_actor(user) and (
        can_manage_work(user, work) or work.assigned_to_id == user.id
    )


def can_read_progress(user, entry):
    if not active_actor(user):
        return False
    if entry.project_id:
        return can_read_project_detail(user, entry.project) or (
            can_read_project(user, entry.project)
            and can_manage_org(user, entry.author_org_id)
        )
    if entry.case_id:
        return can_read_case(user, entry.case)
    if entry.work_id:
        return can_read_work(user, entry.work)
    return False


def api_narrow(user, queryset, org_field="owner_org_id"):
    if not active_actor(user):
        return queryset.none()
    scope = api_scope_ids(user)
    return queryset if scope is None else queryset.filter(**{org_field + "__in": scope})


def visible_credentials(user):
    return api_narrow(
        user,
        Credential.objects.filter(
            Q(user=user) | Q(user__primary_org_id__in=manager_scope_ids(user))
        ).select_related("user__primary_org"),
        "user__primary_org_id",
    )


def visible_participations(user):
    return api_narrow(
        user,
        ParticipationRequest.objects.filter(
            Q(target_org_id__in=manager_scope_ids(user)) | Q(requested_by=user)
        ).select_related("user__primary_org", "target_org"),
        "target_org_id",
    )


def visible_announcements(user):
    now = timezone.now()
    qs = api_narrow(
        user, Announcement.objects.select_related("created_by", "owner_org")
    )
    return qs.filter(
        pk__in=[
            obj.pk
            for obj in qs
            if obj.created_by_id == user.pk
            or can_manage_org(user, obj.owner_org_id)
            or obj.status == "PUBLISHED"
            and obj.starts_at <= now
            and (obj.ends_at is None or obj.ends_at > now)
            and audience_visible(user, obj)
        ]
    )


def visible_projects(user):
    qs = Project.objects.select_related(
        "appointment__user", "appointment__governing_org", "created_by", "owner_org"
    )
    if not active_actor(user):
        return qs.none()
    return api_narrow(
        user,
        qs.filter(
            id__in=[project.id for project in qs if can_read_project(user, project)]
        ),
    )


def visible_work(user):
    qs = WorkItem.objects.select_related(
        "project__appointment__user",
        "project__appointment__governing_org",
        "case",
        "assigned_to",
        "created_by",
        "owner_org",
    )
    if not active_actor(user):
        return qs.none()
    return api_narrow(
        user, qs.filter(id__in=[work.id for work in qs if can_read_work(user, work)])
    )


def visible_cases(user):
    qs = Case.objects.select_related("owner_org", "coordinator", "created_by")
    if not active_actor(user):
        return qs.none()
    return api_narrow(
        user, qs.filter(id__in=[case.id for case in qs if can_read_case(user, case)])
    )


def visible_org_ids(user):
    if not active_actor(user):
        return set()
    scope = api_scope_ids(user)
    return (
        set(OrgNode.objects.filter(active=True).values_list("id", flat=True))
        if scope is None
        else scope
    )


def audience_visible(user, obj):
    if not active_actor(user) or not api_org_allowed(user, obj.owner_org_id):
        return False
    if obj.all_cs:
        return True
    return user.primary_org_id is not None and any(
        user.primary_org_id in descendants_ids(org_id)
        for org_id in obj.audience.values_list("id", flat=True)
    )


def visible_cards(user):
    qs = api_narrow(
        user, CommunityCard.objects.select_related("created_by", "owner_org")
    )
    if not active_actor(user):
        return qs.none()
    if is_god_mode(user):
        return qs
    readable = []
    for card in qs:
        source_manager = False
        if (
            card.status in ("SUBMITTED", "CONTENT_APPROVED")
            and card.source_type == "project"
            and card.source_id
        ):
            try:
                project = Project.objects.filter(pk=card.source_id).first()
            except (ValueError, TypeError, DjangoValidationError):
                project = None
            source_manager = bool(project and can_manage_project(user, project))
        if (
            card.created_by_id == user.id
            or can_manage_org(user, card.owner_org_id)
            or source_manager
            or (card.status == "PUBLISHED" and audience_visible(user, card))
        ):
            readable.append(card.id)
    return qs.filter(id__in=readable)


def report_source(user, kind, pk):
    """Resolve one authorized source without scanning its whole collection."""
    if not isinstance(kind, str) or not active_actor(user):
        return None
    sources = {
        "work": (
            WorkItem,
            can_read_work,
            (
                "project__appointment__user",
                "project__appointment__governing_org",
                "case",
                "assigned_to",
                "created_by",
                "owner_org",
            ),
        ),
        "project": (
            Project,
            can_read_project,
            (
                "appointment__user",
                "appointment__governing_org",
                "created_by",
                "owner_org",
            ),
        ),
        "case": (Case, can_read_case, ("owner_org", "coordinator", "created_by")),
    }
    if kind not in sources:
        return None
    model, can_read, related = sources[kind]
    try:
        obj = api_narrow(
            user, model.objects.select_related(*related).filter(pk=pk)
        ).first()
        return obj if obj is not None and can_read(user, obj) else None
    except (ValueError, TypeError, DjangoValidationError):
        return None
