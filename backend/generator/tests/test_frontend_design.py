"""Phase 9 - professional UI/UX and responsive design.

The generated app must ship a real design system, a responsive shell, an
accessible table/pagination surface and a theme switch - and it must still
type-check and build.
"""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from projects.models import ApprovalEvent, Project, Requirement

GENERATE = "generate-frontend"


@pytest.fixture
def client(django_user_model):
    user = django_user_model.objects.create_user(
        username="designer", email="designer@example.com", password="strong-pass-123"
    )
    client = APIClient()
    client.force_authenticate(user)
    client.user = user
    return client


def _approved_project(user):
    project = Project.objects.create(owner=user, name="Design Shop", status=Project.Status.APPROVED)
    ApprovalEvent.objects.create(
        project=project, actor=user, action=ApprovalEvent.Action.APPROVE
    )
    Requirement.objects.create(
        project=project, rid="REQ-001", title="Users can manage products",
        req_type=Requirement.Type.FUNCTIONAL, status=Requirement.Status.APPROVED,
        approved_by=user, approved_at="2026-11-26T12:00:00Z",
    )
    return project


@pytest.fixture(scope="module")
def generated(django_db_setup, django_db_blocker):
    """Generate once for the module: the harness runs a real type check and build."""
    from django.contrib.auth import get_user_model

    with django_db_blocker.unblock():
        User = get_user_model()
        user = User.objects.create_user(
            username="designer-module", email="module@example.com", password="strong-pass-123"
        )
        client = APIClient()
        client.force_authenticate(user)
        project = _approved_project(user)
        res = client.post(reverse(GENERATE, args=[project.pk]))
        assert res.status_code == 201, res.data
        data = res.data
        yield data
        project.delete()
        user.delete()


def test_design_system_modules_and_tokens_are_generated(generated):
    artifacts = generated["artifacts"]
    assert "src/ui.ts" in artifacts
    assert "src/components/ConfirmDialog.tsx" in artifacts

    css = artifacts["src/index.css"]
    assert '[data-theme="light"]' in css
    assert "--accent-ink" in css
    assert ":focus-visible" in css
    assert "prefers-reduced-motion" in css

    html = artifacts["index.html"]
    assert 'name="description"' in html
    assert "theme-color" in html
    assert 'rel="icon"' in html


def test_generated_pages_use_the_type_scale_and_tokens(generated):
    offenders = []
    for path, body in generated["artifacts"].items():
        if not path.endswith(".tsx"):
            continue
        for marker in ("text-[10px]", "text-[11px]", "#052e16", "#1e2a44"):
            if marker in body:
                offenders.append((path, marker))
    assert offenders == []


def test_responsive_shell_and_accessibility(generated):
    app = generated["artifacts"]["src/App.tsx"]
    assert "Skip to main content" in app
    assert 'aria-controls="primary-nav"' in app
    assert "aria-expanded={navOpen}" in app
    assert "Open navigation" in app
    assert "md:flex" in app

    notifications = generated["artifacts"]["src/components/Notifications.tsx"]
    assert 'aria-haspopup="dialog"' in notifications
    assert 'aria-controls="notifications-panel"' in notifications
    assert "pointerdown" in notifications

    dialog = generated["artifacts"]["src/components/ConfirmDialog.tsx"]
    assert "showModal" in dialog
    assert "aria-labelledby" in dialog and "aria-describedby" in dialog


def test_lists_render_a_table_with_pagination(generated):
    listing = generated["artifacts"]["src/pages/ResourceListPage.tsx"]
    assert "<table" in listing
    assert "<caption" in listing
    assert 'scope="col"' in listing
    assert "md:hidden" in listing
    assert 'aria-label="Pagination"' in listing
    assert "Previous" in listing and "Next" in listing
    assert "data?.next" in listing
    assert "ConfirmDialog" in listing

    api = generated["artifacts"]["src/api.ts"]
    assert "next:" in api and "previous:" in api


def test_theme_switch_follows_the_system_and_build_still_passes(generated):
    preferences = generated["artifacts"]["src/preferences.tsx"]
    assert "data-theme" in preferences
    assert "prefers-color-scheme" in preferences

    settings = generated["artifacts"]["src/pages/Settings.tsx"]
    assert "Appearance" in settings and 'name="theme"' in settings

    assert generated["build_passed"] is True
    assert "error" not in generated["build_output"].lower()
