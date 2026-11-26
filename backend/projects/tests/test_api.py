import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from projects.models import ApprovalEvent, Project, Requirement, TraceLink


@pytest.fixture
def client(db):
    return APIClient()


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user(
        username="krishna", email="k@example.com", password="strong-pass-123"
    )


@pytest.fixture
def auth_client(client, user):
    client.force_authenticate(user)
    return client


def _create_project(auth_client, name="Demo App"):
    res = auth_client.post(
        "/api/projects/", {"name": name, "description": "A demo"}, format="json"
    )
    assert res.status_code == 201, res.data
    return res.data


def _create_requirement(auth_client, project_id, rid="REQ-001", title="Users can sign in"):
    res = auth_client.post(
        f"/api/projects/{project_id}/requirements/",
        {"rid": rid, "title": title, "priority": "must"},
        format="json",
    )
    assert res.status_code == 201, res.data
    return res.data


def test_register_and_login(client):
    res = client.post(
        "/api/auth/register/",
        {"username": "newuser", "email": "n@example.com", "password": "strong-pass-123"},
        format="json",
    )
    assert res.status_code == 201
    res = client.post(
        "/api/auth/token/", {"username": "newuser", "password": "strong-pass-123"}, format="json"
    )
    assert res.status_code == 200
    assert "access" in res.data


def test_projects_are_private(auth_client, db):
    _create_project(auth_client)
    res = APIClient().get("/api/projects/")
    assert res.status_code == 401  # unauthenticated sees nothing


def test_project_lifecycle_draft_pending_approved(auth_client):
    project = _create_project(auth_client)
    pid = project["id"]
    _create_requirement(auth_client, pid)

    res = auth_client.post(f"/api/projects/{pid}/submit_for_approval/")
    assert res.status_code == 200
    assert res.data["status"] == "pending_approval"

    res = auth_client.post(f"/api/projects/{pid}/approve/", {"comment": "looks good"}, format="json")
    assert res.status_code == 200
    assert res.data["status"] == "approved"
    assert res.data["approved_count"] == 1

    reqs = auth_client.get(f"/api/projects/{pid}/requirements/").data
    assert all(r["status"] == "approved" for r in reqs["results"])

    assert ApprovalEvent.objects.filter(project_id=pid).count() == 2


def test_reject_returns_project_to_draft(auth_client):
    project = _create_project(auth_client)
    pid = project["id"]
    _create_requirement(auth_client, pid)
    auth_client.post(f"/api/projects/{pid}/submit_for_approval/")
    res = auth_client.post(f"/api/projects/{pid}/reject/", {"comment": "too vague"}, format="json")
    assert res.status_code == 200
    assert res.data["status"] == "draft"


def test_cannot_approve_without_pending(auth_client):
    project = _create_project(auth_client)
    res = auth_client.post(f"/api/projects/{project['id']}/approve/")
    assert res.status_code == 400


def test_traceability_report_counts(auth_client):
    project = _create_project(auth_client)
    pid = project["id"]
    req = _create_requirement(auth_client, pid)
    _create_requirement(auth_client, pid, rid="REQ-002", title="Fast search")

    from projects.models import Requirement, TraceLink

    r1 = Requirement.objects.get(project_id=pid, rid="REQ-001")
    TraceLink.objects.create(requirement=r1, kind="backend", artifact="backend/projects/views.py")
    TraceLink.objects.create(requirement=r1, kind="test", artifact="tests/test_auth.py", test_passed=True)
    r2 = Requirement.objects.get(project_id=pid, rid="REQ-002")
    TraceLink.objects.create(requirement=r2, kind="test", artifact="tests/test_search.py", test_passed=False)

    res = auth_client.get(f"/api/projects/{pid}/traceability/")
    assert res.status_code == 200
    summary = res.data["summary"]
    assert summary["total"] == 2
    assert summary["with_trace_links"] == 2
    assert summary["with_tests"] == 2
    assert summary["tests_all_passing"] == 1  # only REQ-001's tests all pass


def test_project_detail_includes_requirements(auth_client):
    project = _create_project(auth_client)
    _create_requirement(auth_client, project["id"])
    res = auth_client.get(f"/api/projects/{project['id']}/")
    assert res.status_code == 200, res.data
    assert len(res.data["requirements"]) == 1
    assert res.data["requirements"][0]["rid"] == "REQ-001"


def test_rid_must_be_unique_per_project(auth_client):
    project = _create_project(auth_client)
    _create_requirement(auth_client, project["id"], rid="REQ-001")
    res = auth_client.post(
        f"/api/projects/{project['id']}/requirements/",
        {"rid": "REQ-001", "title": "Duplicate"},
        format="json",
    )
    assert res.status_code == 400


def test_other_users_projects_are_hidden(auth_client, django_user_model):
    project = _create_project(auth_client)
    other = django_user_model.objects.create_user(username="other", email="o@example.com", password="strong-pass-123")
    other_client = APIClient()
    other_client.force_authenticate(other)
    res = other_client.get(f"/api/projects/{project['id']}/")
    assert res.status_code == 404
