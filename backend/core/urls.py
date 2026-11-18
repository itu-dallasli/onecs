from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from .schema import configure

configure(views)
router = DefaultRouter()
for prefix, view, base in [
    ("organization", views.OrgViewSet, "organization"),
    ("people", views.PeopleViewSet, "people"),
    ("project-managers", views.PMViewSet, "project-managers"),
    ("projects", views.ProjectViewSet, "projects"),
    ("participation-requests", views.ParticipationViewSet, "participation"),
    ("work", views.WorkViewSet, "work"),
    ("cases", views.CaseViewSet, "cases"),
    ("case-notices", views.CaseNoticeViewSet, "case-notices"),
    ("announcements", views.AnnouncementViewSet, "announcements"),
    ("community", views.CommunityViewSet, "community"),
    ("events", views.EventViewSet, "events"),
    ("credentials", views.CredentialViewSet, "credentials"),
    ("report-selections", views.ReportSelectionViewSet, "report-selections"),
    ("reports", views.ReportViewSet, "reports"),
    ("notifications", views.NotificationViewSet, "notifications"),
    ("api-clients", views.ApiClientViewSet, "api-clients"),
    ("sla-policies", views.SLAPolicyViewSet, "sla-policies"),
    ("contributions", views.ContributionViewSet, "contributions"),
]:
    router.register(prefix, view, basename=base)
urlpatterns = [
    path("auth/csrf/", views.csrf_view),
    path("auth/login/", views.login_view),
    path("auth/me/", views.me_view),
    path("auth/logout/", views.logout_view),
    path("dashboard/", views.dashboard_view),
    path("activity/", views.activity_view),
    path("search/", views.search_view),
    path("test-mode/", views.test_mode_view),
    path("health/", views.health_view),
    path("", include(router.urls)),
]
