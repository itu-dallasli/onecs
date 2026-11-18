from django.urls import path

from . import views


urlpatterns = [
    path("settings/", views.SettingsIndexView.as_view()),
    path("settings/<str:section>/", views.SettingsView.as_view()),
    path("integrations/<str:section>/test/", views.IntegrationTestView.as_view()),
    path("ai/usage/", views.AIUsageView.as_view()),
    path("ai-usage/", views.AIUsageView.as_view()),
    path("ai/profiles/", views.AIProfilesView.as_view()),
    path("ai/profiles/<uuid:profile_id>/", views.AIProfileDetailView.as_view()),
    path("ai/profiles/<uuid:profile_id>/test/", views.AIProfileTestView.as_view()),
    path("ai/profiles/<uuid:profile_id>/default/", views.AIProfileDefaultView.as_view()),
    path("ldap/discover/", views.LDAPDiscoverView.as_view()),
    path("ldap/search/", views.LDAPSearchView.as_view()),
    path("ldap/import/", views.LDAPImportView.as_view()),
    path("users/", views.UsersView.as_view()),
    path("users/<uuid:user_id>/", views.UserDetailView.as_view()),
    path("roles/", views.RolesView.as_view()),
    path("audit/", views.AuditView.as_view()),
    path("audit-events/", views.AuditView.as_view()),
    path("jobs/", views.JobsView.as_view()),
    path("jobs/<uuid:job_id>/retry/", views.JobRetryView.as_view()),
]
