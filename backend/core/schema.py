"""OpenAPI request contracts for the handwritten domain action endpoints."""

from drf_spectacular.extensions import OpenApiAuthenticationExtension
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiParameter,
    extend_schema,
    extend_schema_view,
    extend_schema_field,
    inline_serializer,
)
from rest_framework import serializers as fields


class AtlasBearerScheme(OpenApiAuthenticationExtension):
    target_class = "core.authentication.ScopedJWTAuthentication"
    name = "AtlasBearer"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Salt okunur servis tokenı; scope ve güncel kayıt yetkisi birlikte uygulanır.",
        }


def body(name, properties, version=False):
    attrs = {"version": fields.IntegerField(min_value=1)} if version else {}
    attrs.update(properties)
    return inline_serializer(name=name, fields=attrs)


def configure(views):
    def text(**kw):
        return fields.CharField(**kw)

    def uuid(**kw):
        return fields.UUIDField(**kw)

    def date(**kw):
        return fields.DateTimeField(**kw)

    def choice(values, **kw):
        return fields.ChoiceField(choices=values, **kw)

    priorities = ["CRITICAL", "HIGH", "NORMAL"]
    version = body("VersionedAction", {}, True)
    progress = body(
        "ProgressAction",
        {
            "done": text(),
            "next_step": text(required=False),
            "blocker": text(required=False),
            "progress": fields.IntegerField(min_value=0, max_value=100, required=False),
        },
        True,
    )
    schemas = {
        "ProjectViewSet": {
            "create": body(
                "ProjectCreate",
                {
                    "title": text(max_length=240),
                    "description": text(),
                    "expected_outcome": text(required=False),
                    "appointment_id": uuid(required=False),
                    "pm_id": uuid(required=False),
                    "priority": choice(priorities, required=False),
                    "due_at": date(required=False),
                },
            ),
            "submit": version,
            "review": body(
                "ProjectReview",
                {
                    "decision": choice(["APPROVE", "REVISION", "REJECT"]),
                    "note": text(required=False),
                },
                True,
            ),
            "progress": progress,
            "members": body(
                "ProjectResourceRequest", {"user_id": uuid(), "summary": text()}, True
            ),
            "tasks": body(
                "ProjectTaskCreate",
                {
                    "title": text(),
                    "assignee_id": uuid(),
                    "description": text(required=False),
                    "due_at": date(required=False),
                },
                True,
            ),
            "close": body("ProjectClose", {"summary": text()}, True),
        },
        "WorkViewSet": {
            "create": body(
                "UnitWorkCreate",
                {
                    "title": text(),
                    "description": text(required=False),
                    "expected_outcome": text(required=False),
                    "assignee_id": uuid(required=False),
                    "personal": fields.BooleanField(required=False),
                    "kind": choice(["TASK", "COMMITMENT"], required=False),
                    "priority": choice(priorities, required=False),
                    "due_at": date(required=False),
                },
            ),
            "assign": body("WorkAssign", {"assignee_id": uuid()}, True),
            "adopt": body("WorkAdopt", {"priority": choice(priorities)}, True),
            "status": body(
                "WorkStatus",
                {
                    "status": text(),
                    "result": text(required=False),
                    "blocker": text(required=False),
                },
                True,
            ),
            "progress": progress,
            "children": body(
                "ChildWorkCreate",
                {
                    "title": text(),
                    "assignee_id": uuid(),
                    "expected_outcome": text(required=False),
                    "priority": choice(priorities, required=False),
                    "shared_parent_summary": text(required=False),
                },
                True,
            ),
            "sla_adjust": body(
                "SLAAdjustment",
                {
                    "due_at": date(),
                    "reason": text(),
                    "priority": choice(priorities, required=False),
                },
                True,
            ),
        },
        "CaseViewSet": {
            "create": body(
                "CaseCreate",
                {
                    "title": text(),
                    "description": text(required=False),
                    "priority": choice(priorities),
                    "owner_org_id": uuid(required=False),
                    "coordinator_id": uuid(required=False),
                    "kind": text(required=False),
                },
            ),
            "progress": progress,
            "actions": body(
                "CaseActionCreate",
                {
                    "title": text(),
                    "assignee_id": uuid(),
                    "description": text(required=False),
                    "due_at": date(required=False),
                },
                True,
            ),
            "request_close": body("CaseCloseRequest", {"summary": text()}, True),
            "verify_close": body("CaseVerifyClose", {"evidence": text()}, True),
        },
        "ParticipationViewSet": {
            "decide": body(
                "ResourceDecision",
                {
                    "decision": choice(["ACCEPT", "REJECT"]),
                    "note": text(required=False),
                },
                True,
            )
        },
        "ReportViewSet": {
            "create": body(
                "ReportCreate",
                {
                    "title": text(required=False),
                    "period_start": fields.DateField(required=False),
                    "period_end": fields.DateField(required=False),
                },
            ),
            "generate": version,
            "approve": body("ReportApproval", {"content_hash": text()}, True),
        },
        "EventViewSet": {
            "rsvp": body(
                "EventRSVPAction", {"answer": choice(["YES", "NO", "MAYBE"])}, True
            ),
            "poll_response": body(
                "PollResponseAction",
                {"poll_id": uuid(), "choices": fields.ListField(child=text())},
                True,
            ),
        },
        "CommunityViewSet": {
            "submit": version,
            "publish": version,
            "withdraw": version,
            "interest": version,
        },
        "AnnouncementViewSet": {"publish": version, "withdraw": version},
        "NotificationViewSet": {
            "read": body(
                "NotificationReadState", {"read": fields.BooleanField(required=False)}
            ),
            "mark_all_read": body("NotificationMarkAllRead", {}),
        },
    }
    for class_name, actions in schemas.items():
        cls = getattr(views, class_name, None)
        if cls is None:
            continue
        decorators = {
            action: extend_schema(
                request=schema, tags=[class_name.removesuffix("ViewSet")]
            )
            for action, schema in actions.items()
            if hasattr(cls, action)
        }
        extend_schema_view(**decorators)(cls)
    functions = {
        "csrf_view": {"responses": OpenApiTypes.OBJECT, "auth": []},
        "login_view": {
            "request": body(
                "LoginRequest",
                {
                    "username": text(),
                    "password": text(write_only=True),
                    "method": choice(["local", "ldap"], required=False),
                },
            ),
            "responses": OpenApiTypes.OBJECT,
            "auth": [],
        },
        "me_view": {"responses": OpenApiTypes.OBJECT},
        "logout_view": {"request": None, "responses": OpenApiTypes.OBJECT},
        "dashboard_view": {"responses": OpenApiTypes.OBJECT},
        "activity_view": {"responses": OpenApiTypes.OBJECT},
        "health_view": {"responses": OpenApiTypes.OBJECT},
        "search_view": {"responses": OpenApiTypes.OBJECT},
        "test_mode_view": {
            "request": body(
                "TestModeRequest",
                {
                    "mode": choice(["simulate", "god", "stop"]),
                    "user_id": uuid(required=False),
                },
            ),
            "responses": OpenApiTypes.OBJECT,
        },
    }
    for name, options in functions.items():
        if hasattr(views, name):
            setattr(
                views,
                name,
                extend_schema(
                    tags=[
                        "Identity"
                        if "auth" in name
                        or name in ("csrf_view", "login_view", "me_view", "logout_view")
                        else "Overview"
                    ],
                    **options,
                )(getattr(views, name)),
            )

    # Field types are explicit; schema generation does not need live user data.
    from . import serializers as outputs

    method_types = {
        "PersonSerializer": {
            "get_roles": {"type": "array", "items": {"type": "object"}},
            "get_role_label": OpenApiTypes.STR,
        },
        "OrgSerializer": {
            "get_manager_id": OpenApiTypes.UUID,
            "get_manager_ids": {
                "type": "array",
                "items": {"type": "string", "format": "uuid"},
            },
            "get_managers": outputs.PersonSerializer(many=True),
        },
        "SLASerializer": {"get_is_overdue": OpenApiTypes.BOOL},
        "WorkSerializer": {
            "get_parent_id": OpenApiTypes.UUID,
            "get_permissions": OpenApiTypes.OBJECT,
        },
        "ProjectSerializer": {
            "get_members": outputs.PersonSerializer(many=True),
            "get_contributions": outputs.ProgressSerializer(many=True),
            "get_audience_ids": {
                "type": "array",
                "items": {"type": "string", "format": "uuid"},
            },
            "get_permissions": OpenApiTypes.OBJECT,
        },
        "CaseSerializer": {"get_permissions": OpenApiTypes.OBJECT},
        "CardSerializer": {
            "get_interest_count": OpenApiTypes.INT,
            "get_interested": OpenApiTypes.BOOL,
            "get_source_accessible": OpenApiTypes.BOOL,
            "get_source_id": OpenApiTypes.STR,
            "get_source_type": OpenApiTypes.STR,
        },
        "PollSerializer": {
            "get_result": OpenApiTypes.OBJECT,
            "get_my_choices": {"type": "array", "items": {"type": "string"}},
        },
        "EventSerializer": {
            "get_counts": OpenApiTypes.OBJECT,
            "get_rsvp": OpenApiTypes.STR,
        },
    }
    for class_name, methods in method_types.items():
        serializer = getattr(outputs, class_name)
        for method, schema in methods.items():
            extend_schema_field(schema)(getattr(serializer, method))
    for class_name in (
        "ApiClientViewSet",
        "ReportSelectionViewSet",
        "SLAPolicyViewSet",
    ):
        cls = getattr(views, class_name)
        if not getattr(cls, "serializer_class", None):
            extend_schema_view(
                **{
                    method: extend_schema(
                        request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT
                    )
                    for method in (
                        "list",
                        "retrieve",
                        "create",
                        "partial_update",
                        "token",
                        "revoke",
                    )
                    if hasattr(cls, method)
                }
            )(cls)
    for cls in vars(views).values():
        if (
            not isinstance(cls, type)
            or cls is views.DomainViewSet
            or not issubclass(cls, views.DomainViewSet)
        ):
            continue
        methods = {
            name for name in ("retrieve", "partial_update") if hasattr(cls, name)
        }
        methods |= {
            method.__name__ for method in cls.get_extra_actions() if method.detail
        }
        extend_schema_view(
            **{
                name: extend_schema(
                    parameters=[
                        OpenApiParameter(
                            "id", OpenApiTypes.UUID, location=OpenApiParameter.PATH
                        )
                    ]
                )
                for name in methods
            }
        )(cls)


def canonical_endpoints(endpoints):
    """Keep compatibility aliases callable while documenting canonical URLs once."""
    selected = []
    for path, path_regex, method, callback in endpoints:
        if path in ("/api/v1/admin/ai-usage/", "/api/v1/admin/audit-events/"):
            continue
        if path == "/api/v1/admin/settings/" and method != "GET":
            continue
        selected.append((path, path_regex, method, callback))
    return selected
