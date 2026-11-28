import json

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from projects.models import ApprovalEvent, Project, Requirement, TraceLink

GENERATE = "generate-backend"
DETAIL = "generated-backend-detail"


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
    req = Requirement.objects.create(
        project=project, rid="REQ-001", title="Users can manage products",
        req_type=Requirement.Type.FUNCTIONAL, status=Requirement.Status.APPROVED,
        approved_by=user, approved_at="2026-11-26T12:00:00Z",
    )
    req2 = Requirement.objects.create(
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


def test_generation_blocked_for_unapproved_project(client):
    project = Project.objects.create(owner=client.user, name="Draft", status=Project.Status.DRAFT)
    res = client.post(reverse(GENERATE, args=[project.pk]))
    assert res.status_code == 400
    assert "approved" in res.data["detail"]


def test_generation_blocked_without_functional_requirements(client):
    project = Project.objects.create(owner=client.user, name="Empty", status=Project.Status.APPROVED)
    res = client.post(reverse(GENERATE, args=[project.pk]))
    assert res.status_code == 400


def test_generation_produces_runnable_backend_and_trace_links(client):
    project = _approved_project(client.user)
    res = client.post(reverse(GENERATE, args=[project.pk]))
    assert res.status_code == 201, res.data
    data = res.data

    assert data["status"] == "success"
    assert data["tests_passed"] is True
    routes = {r["route"]: r["rid"] for r in data["resources"]}
    assert routes == {"manage_products": "REQ-001", "manage_orders": "REQ-002"}
    for path in (
        "backendapp/models.py", "backendapp/serializers.py", "backendapp/views.py",
        "backendapp/urls.py", "backendapp/permissions.py", "backendapp/docs.md",
        "backendapp/tests.py", "backendapp/requirements_map.json",
        "backendapp/services.py", "backendapp/exceptions.py", "backendapp/auth_views.py",
        "backendapp/config.py", "backendapp/filters.py", "backendapp/pagination.py",
        "backendapp/middleware.py", "backendapp/roles.py", "backendapp/signals.py",
        "backendapp/integrations.py", "backendapp/features.py",
    ):
        assert path in data["artifacts"], path
    assert "sqlite" in data["databases_tested"]
    assert "REQ-001" in data["artifacts"]["backendapp/docs.md"]
    # Phase 8: every approved functional requirement has a written feature entry
    features = {f["rid"]: f for f in data["features"]}
    assert set(features) == {"REQ-001", "REQ-002"}
    assert all(f["status"] == "implemented" for f in features.values())
    assert all("services.transition_status" in f["service"] for f in features.values())
    assert data["feature_summary"]["total"] == 2
    assert "## Business logic per requirement" in data["artifacts"]["backendapp/docs.md"]
    # trace map is valid JSON keyed by rid
    trace_map = json.loads(data["artifacts"]["backendapp/requirements_map.json"])
    assert {t["rid"] for t in trace_map} == {"REQ-001", "REQ-002"}

    links = TraceLink.objects.filter(requirement__project=project)
    backend_links = links.filter(kind=TraceLink.Kind.BACKEND)
    test_links = links.filter(kind=TraceLink.Kind.TEST)
    assert backend_links.count() == 2
    assert test_links.count() == 2
    assert all(link.test_passed is True for link in test_links)
    assert {link.requirement.rid for link in backend_links} == {"REQ-001", "REQ-002"}
    # the harness ran real generated tests
    assert "OK" in data["test_output"]


def test_regenerate_replaces_artifacts(client):
    project = _approved_project(client.user)
    first = client.post(reverse(GENERATE, args=[project.pk])).data
    Requirement.objects.create(
        project=project, rid="REQ-004", title="Users can manage invoices",
        req_type=Requirement.Type.FUNCTIONAL, status=Requirement.Status.APPROVED,
        approved_by=client.user,
    )
    second = client.post(reverse(GENERATE, args=[project.pk]))
    assert second.status_code == 201
    assert {r["route"] for r in second.data["resources"]} == {
        "manage_products", "manage_orders", "manage_invoices",
    }
    assert second.data["id"] == first["id"]  # one record per project, replaced


def test_get_generated_backend(client):
    project = _approved_project(client.user)
    assert client.get(reverse(DETAIL, args=[project.pk])).status_code == 404
    client.post(reverse(GENERATE, args=[project.pk]))
    res = client.get(reverse(DETAIL, args=[project.pk]))
    assert res.status_code == 200
    assert res.data["status"] == "success"
    assert "sqlite" in res.data["databases_tested"]
    assert {f["rid"] for f in res.data["features"]} == {"REQ-001", "REQ-002"}
    assert res.data["feature_summary"]["implemented"] == 2


def test_cannot_generate_for_other_users_project(client, django_user_model):
    other = django_user_model.objects.create_user(
        username="other", email="other@example.com", password="strong-pass-123"
    )
    project = _approved_project(other)
    res = client.post(reverse(GENERATE, args=[project.pk]))
    assert res.status_code == 404
