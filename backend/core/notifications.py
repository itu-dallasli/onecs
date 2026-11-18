"""Recipient inbox visibility and in-app announcement delivery share policy."""

import uuid

from django.db.models import Q
from django.utils import timezone

from .models import CaseNotice, Event, Notification, User
from .policy import (
    active_actor,
    api_narrow,
    api_scope_ids,
    audience_visible,
    can_publish_announcement,
    manager_scope_ids,
    report_source,
    visible_announcements,
    visible_cards,
    visible_credentials,
    visible_participations,
)


def notification_access(user, notice):
    if not active_actor(user):
        return False, None
    kind = notice.resource_type
    routes = {
        "work": "work",
        "project": "projects",
        "case": "cases",
        "community": "community",
        "credential": "credentials",
        "announcement": "announcements",
        "event": "events",
    }
    if kind not in {*routes, "participation", "case_notice"}:
        return api_scope_ids(user) is None, None
    try:
        resource_id = str(uuid.UUID(str(notice.resource_id)))
    except (ValueError, TypeError, AttributeError):
        return False, None
    if kind in ("work", "project", "case"):
        visible = report_source(user, kind, resource_id) is not None
    elif kind == "community":
        visible = visible_cards(user).filter(pk=resource_id).exists()
    elif kind == "credential":
        visible = visible_credentials(user).filter(pk=resource_id).exists()
    elif kind == "participation":
        request = visible_participations(user).filter(pk=resource_id).first()
        if request is None:
            return False, None
        route = "projects" if request.project_id else "cases"
        # Allocation authority does not imply access to the parent project/case.
        return True, f"/{route}?requests=1&request_id={resource_id}"
    elif kind == "case_notice":
        visible = (
            api_narrow(
                user,
                CaseNotice.objects.filter(
                    Q(created_by=user) | Q(owner_org_id__in=manager_scope_ids(user))
                ),
            )
            .filter(pk=resource_id)
            .exists()
        )
        return bool(
            visible
        ), f"/cases?notices=1&notice_id={resource_id}" if visible else None
    elif kind == "announcement":
        announcement = visible_announcements(user).filter(pk=resource_id).first()
        if announcement is None:
            return False, None
        if notice.dedup_key.startswith("announcement-proposed:"):
            visible = announcement.status == "DRAFT" and can_publish_announcement(
                user, announcement
            )
        elif notice.dedup_key.startswith("announcement-published:"):
            now = timezone.now()
            visible = (
                announcement.status == "PUBLISHED"
                and announcement.starts_at <= now
                and (announcement.ends_at is None or announcement.ends_at > now)
                and audience_visible(user, announcement)
            )
        else:
            visible = True
    else:
        visible = (
            api_narrow(
                user,
                Event.objects.filter(
                    Q(invitees=user) | Q(owner_org_id__in=manager_scope_ids(user))
                ),
            )
            .filter(pk=resource_id)
            .exists()
        )
    return bool(visible), f"/{routes[kind]}?id={resource_id}" if visible else None


def authorized_notifications(user):
    queryset = Notification.objects.filter(recipient=user).order_by(
        "-created_at", "-pk"
    )
    ids, urls, cache = [], {}, {}
    for notice in queryset:
        category = (
            notice.dedup_key.split(":", 1)[0]
            if notice.resource_type == "announcement"
            else ""
        )
        key = (notice.resource_type, notice.resource_id, category)
        if key not in cache:
            cache[key] = notification_access(user, notice)
        visible, url = cache[key]
        if visible:
            ids.append(notice.pk)
            urls[str(notice.pk)] = url
    return queryset.filter(pk__in=ids), urls


def _inapp(recipient, title, announcement, key):
    Notification.objects.get_or_create(
        dedup_key=f"{key}:{recipient.pk}:inapp",
        defaults={
            "recipient": recipient,
            "title": title,
            "message": announcement.title,
            "resource_type": "announcement",
            "resource_id": str(announcement.pk),
        },
    )


def notify_announcement_proposed(announcement):
    """The caller's domain transaction also owns these in-app records."""
    candidates = User.objects.filter(
        is_active=True,
        role_grants__role__in=("DIRECTOR", "UNIT_HEAD"),
        role_grants__active=True,
    ).distinct()
    for recipient in candidates:
        if can_publish_announcement(recipient, announcement):
            _inapp(
                recipient,
                "Anons yayın kararınızı bekliyor",
                announcement,
                f"announcement-proposed:{announcement.pk}:{announcement.version}",
            )


def notify_announcement_published(announcement):
    for recipient in User.objects.filter(is_active=True):
        if audience_visible(recipient, announcement):
            _inapp(
                recipient,
                "Yeni anons yayımlandı",
                announcement,
                f"announcement-published:{announcement.pk}:{announcement.version}",
            )
