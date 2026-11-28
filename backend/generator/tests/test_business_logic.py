"""Phase 8 - business logic per approved requirement.

The matrix must cover every approved functional requirement, say which
capabilities it implements, and either mark it implemented or carry a written
reason plus the exact integration configuration it needs.
"""
import json

import pytest

from generator import business, engine, templates
from generator.schemas import GenerationPlan
from generator.tests.test_generation import _approved_project
from projects.models import Project, Requirement


@pytest.fixture
def client(django_user_model):
    from rest_framework.test import APIClient

    user = django_user_model.objects.create_user(
        username="business_owner", email="business@example.com", password="strong-pass-123"
    )
    api = APIClient()
    api.force_authenticate(user)
    api.user = user
    return api


CAPABILITY_CASES = [
    ("Users can search and filter products", ["crud", "search", "filter"]),
    ("Managers approve publishing workflow", ["crud", "workflow"]),
    ("Users receive email notifications", ["crud", "notifications"]),
    ("Dashboard analytics and reports", ["crud", "analytics"]),
    ("Customers pay through checkout", ["crud", "payments"]),
    ("Users upload document attachments", ["crud", "upload"]),
    ("Admins manage roles and permissions", ["crud", "user_management"]),
]


@pytest.mark.parametrize("title,expected", CAPABILITY_CASES)
def test_capabilities_are_detected_from_requirement_text(title, expected):
    detected = business.detect_capabilities(title)
    for cap in expected:
        assert cap in detected, (title, detected)


def test_unknown_wording_still_gets_crud():
    assert business.detect_capabilities("Store widgets") == ["crud"]


def _project_with(user, requirements):
    project = Project.objects.create(owner=user, name="Matrix", status=Project.Status.APPROVED)
    for index, (title, status) in enumerate(requirements, start=1):
        Requirement.objects.create(
            project=project,
            rid=f"REQ-{index:03d}",
            title=title,
            req_type=Requirement.Type.FUNCTIONAL,
            status=status,
        )
    return project


def test_matrix_covers_every_approved_functional_requirement(django_user_model):
    user = django_user_model.objects.create_user(
        username="matrix", email="matrix@example.com", password="strong-pass-123"
    )
    project = _project_with(
        user,
        [
            ("Users can search products", Requirement.Status.APPROVED),
            ("Customers pay by invoice", Requirement.Status.APPROVED),
            ("Users can upload attachments", Requirement.Status.DRAFT),
        ],
    )
    plan = GenerationPlan(project_id=project.id, resources=engine._resource_specs(project))
    matrix = business.analyse(project, plan.resources)
    by_rid = {f["rid"]: f for f in matrix["features"]}

    assert set(by_rid) == {"REQ-001", "REQ-002"}  # draft requirement is out of scope
    for feature in by_rid.values():
        assert feature["status"] in {"implemented", "configuration_required"}
        assert feature["endpoints"]
        assert feature["tests"]
        assert feature["rules"]
        assert feature["validations"]
        assert feature["frontend"]
        assert feature["tables"]
    assert by_rid["REQ-002"]["status"] == "configuration_required"
    assert by_rid["REQ-002"]["reason"]
    assert by_rid["REQ-002"]["integration"]["env"] == ["PAYMENT_PROVIDER_URL", "PAYMENT_API_KEY"]
    assert matrix["summary"] == {
        "total": 2,
        "implemented": 1,
        "configuration_required": 1,
        "capabilities": {"crud": 2, "search": 1, "payments": 1},
    }


def test_generated_artifacts_contain_real_business_logic(client):
    project = _approved_project(client.user, name="Business artifacts")
    plan = GenerationPlan(project_id=project.id, resources=engine._resource_specs(project))
    matrix = business.analyse(project, plan.resources)
    artifacts = engine._build_artifacts(plan, project.name, ["sqlite"], matrix)

    services = artifacts["backendapp/services.py"]
    assert "def transition_status(" in services
    assert "STATUS_TRANSITIONS" in services
    assert "def analytics_summary(" in services
    assert "def notify_record(" in services

    views = artifacts["backendapp/views.py"]
    assert "AnalyticsSummaryView" in views
    assert "NotificationListView" in views
    assert "IntegrationStatusView" in views
    assert "FeaturesView" in views
    assert 'url_path="transition"' in views

    urls = artifacts["backendapp/urls.py"]
    for path in ("api/analytics/summary/", "api/notifications/", "api/integrations/", "api/features/"):
        assert path in urls

    integrations = artifacts["backendapp/integrations.py"]
    assert "integration_not_configured" in integrations
    assert "ProviderEvent" in integrations
    assert "PAYMENT_PROVIDER_URL" in integrations

    import ast
    import re

    source = artifacts["backendapp/features.py"]
    literal = re.search(r"FEATURES = json\.loads\((.+)\)", source).group(1)
    features = json.loads(ast.literal_eval(literal))
    assert {f["rid"] for f in features} == {"REQ-001", "REQ-002"}

    docs = artifacts["backendapp/docs.md"]
    assert "## Business logic per requirement" in docs
    assert "## External integrations" in docs
    assert "integration_not_configured" in docs

    generated_tests = artifacts["backendapp/tests.py"]
    for name in (
        "test_status_transitions_follow_the_workflow",
        "test_owner_is_notified_on_create",
        "test_analytics_summary_matches_database",
        "test_features_endpoint_covers_every_requirement",
        "test_integration_status_lists_required_environment",
    ):
        assert name in generated_tests


def test_payment_requirement_generates_checkout_and_failure_tests(client):
    project = Project.objects.create(
        owner=client.user, name="Payments", status=Project.Status.APPROVED
    )
    Requirement.objects.create(
        project=project, rid="REQ-001", title="Customers pay by checkout",
        req_type=Requirement.Type.FUNCTIONAL, status=Requirement.Status.APPROVED,
    )
    plan = GenerationPlan(project_id=project.id, resources=engine._resource_specs(project))
    matrix = business.analyse(project, plan.resources)
    artifacts = engine._build_artifacts(plan, project.name, ["sqlite"], matrix)

    assert 'url_path="checkout"' in artifacts["backendapp/views.py"]
    assert "def request_checkout(" in artifacts["backendapp/services.py"]
    assert "test_checkout_without_configuration_is_503" in artifacts["backendapp/tests.py"]
    assert "test_checkout_provider_failure_is_recorded" in artifacts["backendapp/tests.py"]
    feature = matrix["features"][0]
    assert feature["status"] == "configuration_required"
    assert "no payment is simulated" in feature["reason"]
    route = feature["resource"]
    assert feature["endpoints"] == [
        f"GET /api/{route}/",
        f"GET /api/{route}/{{id}}/",
        f"POST /api/{route}/{{id}}/checkout/",
    ]


def test_docs_mark_each_requirement_status(client):
    project = _project_with(
        client.user,
        [("Customers pay invoices", Requirement.Status.APPROVED)],
    )
    plan = GenerationPlan(project_id=project.id, resources=engine._resource_specs(project))
    matrix = business.analyse(project, plan.resources)
    docs = templates.docs_md(project.name, plan.resources, ["sqlite"], matrix["features"], matrix["summary"])
    assert "Status: **configuration_required**" in docs
    assert "PAYMENT_PROVIDER_URL" in docs
