import json

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from projects.models import ApprovalEvent, Project, Requirement, TraceLink

GENERATE = "generate-frontend"
DETAIL = "generated-frontend-detail"


@pytest.fixture
def client(django_user_model):
    user = django_user_model.objects.create_user(
        username="owner", email="owner@example.com", password="strong-pass-123"
    )
    client = APIClient()
    client.force_authenticate(user)
    client.user = user
    return client


def _approved_project(user, name="Shop"):
    project = Project.objects.create(owner=user, name=name, status=Project.Status.APPROVED)
    ApprovalEvent.objects.create(
        project=project, actor=user, action=ApprovalEvent.Action.APPROVE
    )
    Requirement.objects.create(
        project=project, rid="REQ-001", title="Users can manage products",
        req_type=Requirement.Type.FUNCTIONAL, status=Requirement.Status.APPROVED,
        approved_by=user, approved_at="2026-11-26T12:00:00Z",
    )
    Requirement.objects.create(
        project=project, rid="REQ-002", title="Users can manage orders",
        req_type=Requirement.Type.FUNCTIONAL, status=Requirement.Status.APPROVED,
        approved_by=user, approved_at="2026-11-26T12:00:00Z",
    )
    Requirement.objects.create(
        project=project, rid="REQ-003", title="Response time under 200 ms",
        req_type=Requirement.Type.NON_FUNCTIONAL, status=Requirement.Status.APPROVED,
        approved_by=user, approved_at="2026-11-26T12:00:00Z",
    )
    return project


def test_frontend_generation_blocked_for_unapproved_project(client):
    project = Project.objects.create(owner=client.user, name="Draft", status=Project.Status.DRAFT)
    res = client.post(reverse(GENERATE, args=[project.pk]))
    assert res.status_code == 400
    assert "approved" in res.data["detail"]


def test_frontend_generation_blocked_without_functional_requirements(client):
    project = Project.objects.create(owner=client.user, name="Empty", status=Project.Status.APPROVED)
    res = client.post(reverse(GENERATE, args=[project.pk]))
    assert res.status_code == 400


def test_frontend_generation_builds_real_app_and_trace_links(client):
    project = _approved_project(client.user)
    res = client.post(reverse(GENERATE, args=[project.pk]))
    assert res.status_code == 201, res.data
    data = res.data

    assert data["status"] == "success"
    assert data["build_passed"] is True
    pages = {p["route"]: p["rid"] for p in data["pages"]}
    assert pages == {"manage_products": "REQ-001", "manage_orders": "REQ-002"}
    for path in (
        "package.json", "index.html", "src/main.tsx", "src/App.tsx", "src/api.ts",
        "src/auth.tsx", "src/pages/Login.tsx", "src/pages/Register.tsx",
        "src/pages/Dashboard.tsx", "src/pages/ResourceListPage.tsx",
        "src/pages/NotFound.tsx", "src/resources.ts", "docs.md",
        "requirements_map.json", "src/queries.ts", "src/preferences.tsx",
        "src/components/Toast.tsx", "src/pages/Landing.tsx",
        "src/pages/Profile.tsx", "src/pages/Settings.tsx",
        "src/components/Notifications.tsx", "src/pages/Features.tsx",
    ):
        assert path in data["artifacts"], path
    # the generated app uses the query library, icon set, toasts and filters it ships
    pkg = data["artifacts"]["package.json"]
    assert "@tanstack/react-query" in pkg and "lucide-react" in pkg
    queries = data["artifacts"]["src/queries.ts"]
    assert "useQuery" in queries and "useMutation" in queries
    app = data["artifacts"]["src/App.tsx"]
    for route in ('path="/dashboard"', 'path="/profile"', 'path="/settings"', 'path="/features"'):
        assert route in app, route
    notifications = data["artifacts"]["src/components/Notifications.tsx"]
    assert "useUnreadCount" in notifications and "markAllRead" in notifications
    features_page = data["artifacts"]["src/pages/Features.tsx"]
    assert "useFeatureMatrix" in features_page and "configuration_required" in features_page
    dashboard = data["artifacts"]["src/pages/Dashboard.tsx"]
    assert "useAnalytics" in dashboard and "created_last_7_days" in dashboard
    settings = data["artifacts"]["src/pages/Settings.tsx"]
    assert "useIntegrations" in settings and "not configured" in settings
    toast = data["artifacts"]["src/components/Toast.tsx"]
    assert 'role="status"' in toast and "aria-live" in toast
    listing = data["artifacts"]["src/pages/ResourceListPage.tsx"]
    for control in ("created_after", "created_before", "ordering", "Clear filters",
                    "useTransitionItem", "Request payment", "status"):
        assert control in listing, control
    assert "APP_NAME" in data["artifacts"]["src/pages/Landing.tsx"]
    # every generated page is traced to its requirement ID in the docs and registry
    assert "REQ-001" in data["artifacts"]["docs.md"]
    registry = data["artifacts"]["src/resources.ts"]
    for page in data["pages"]:
        assert page["rid"] in registry
        assert page["route"] in registry
    # the harness ran a real type check + production build
    assert "vite" in data["build_output"].lower()
    assert "error" not in data["build_output"].lower()

    links = TraceLink.objects.filter(requirement__project=project, kind=TraceLink.Kind.FRONTEND)
    assert links.count() == 2
    assert {link.requirement.rid for link in links} == {"REQ-001", "REQ-002"}
    assert all("frontendapp.src/pages/" in link.artifact for link in links)


def test_frontend_regenerate_replaces_pages(client):
    project = _approved_project(client.user)
    first = client.post(reverse(GENERATE, args=[project.pk])).data
    Requirement.objects.create(
        project=project, rid="REQ-004", title="Users can manage invoices",
        req_type=Requirement.Type.FUNCTIONAL, status=Requirement.Status.APPROVED,
        approved_by=client.user,
    )
    second = client.post(reverse(GENERATE, args=[project.pk]))
    assert second.status_code == 201
    assert {p["route"] for p in second.data["pages"]} == {
        "manage_products", "manage_orders", "manage_invoices",
    }
    assert second.data["id"] == first["id"]  # one record per project, replaced
    assert TraceLink.objects.filter(
        requirement__project=project, kind=TraceLink.Kind.FRONTEND
    ).count() == 3


def test_get_generated_frontend(client):
    project = _approved_project(client.user)
    assert client.get(reverse(DETAIL, args=[project.pk])).status_code == 404
    client.post(reverse(GENERATE, args=[project.pk]))
    res = client.get(reverse(DETAIL, args=[project.pk]))
    assert res.status_code == 200
    assert res.data["status"] == "success"


def test_frontend_cannot_generate_for_other_users_project(client, django_user_model):
    other = django_user_model.objects.create_user(
        username="other", email="other@example.com", password="strong-pass-123"
    )
    project = _approved_project(other)
    res = client.post(reverse(GENERATE, args=[project.pk]))
    assert res.status_code == 404
