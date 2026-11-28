"""Checks on the generated DRF app's full surface: service layer, JWT auth,
role-based access, uploads, filtering, docs and the SQLite/MySQL harness runs.
"""
import importlib
import sys

import pytest
from pydantic import ValidationError

from generator import engine
from generator.schemas import GenerationPlan, ResourceSpec
from projects.models import Project, Requirement


@pytest.fixture(scope="module")
def generated(django_db_setup, django_db_blocker):
    from django.contrib.auth import get_user_model

    with django_db_blocker.unblock():
        user_model = get_user_model()
        user = user_model.objects.create_user(
            username="surface_owner", email="surface@example.com", password="strong-pass-123"
        )
        project = Project.objects.create(
            owner=user, name="Surface Shop", status=Project.Status.APPROVED
        )
        for rid, title in (
            ("REQ-001", "Users can manage products"),
            ("REQ-002", "Users can manage orders"),
        ):
            Requirement.objects.create(
                project=project, rid=rid, title=title,
                req_type=Requirement.Type.FUNCTIONAL,
                status=Requirement.Status.APPROVED, approved_by=user,
            )
        result = engine.generate_backend(project, user)
        yield result, project
        Project.objects.filter(pk=project.pk).delete()
        user.delete()


def test_generated_app_ships_the_backend_layers(generated):
    result, _ = generated
    artifacts = result["artifacts"]

    for path in (
        "settings.py", "requirements.txt", ".env.example",
        "backendapp/config.py", "backendapp/models.py", "backendapp/serializers.py",
        "backendapp/services.py", "backendapp/exceptions.py", "backendapp/permissions.py",
        "backendapp/auth_views.py", "backendapp/views.py", "backendapp/urls.py",
        "backendapp/filters.py", "backendapp/pagination.py", "backendapp/middleware.py",
        "backendapp/roles.py", "backendapp/signals.py", "backendapp/tests.py",
        "backendapp/docs.md",
    ):
        assert path in artifacts, path

    assert "class ServiceError" in artifacts["backendapp/exceptions.py"]
    assert "api_exception_handler" in artifacts["backendapp/exceptions.py"]
    assert "def create_manage_products" in artifacts["backendapp/services.py"]
    assert "validate_attachment" in artifacts["backendapp/services.py"]
    assert "class Role(models.Model)" in artifacts["backendapp/models.py"]
    assert "JWTAuthentication" in artifacts["settings.py"]
    assert "DEFAULT_PAGINATION_CLASS" in artifacts["settings.py"]
    assert "class RegisterView" in artifacts["backendapp/auth_views.py"]
    assert "class LogoutView" in artifacts["backendapp/auth_views.py"]
    assert "IsAdminRole" in artifacts["backendapp/permissions.py"]
    assert "class DateRangeFilter" in artifacts["backendapp/filters.py"]
    assert "RequestIDMiddleware" in artifacts["backendapp/middleware.py"]
    # MySQL is a real, env-driven option, validated with pydantic.
    assert "GENERATED_DB_ENGINE" in artifacts["backendapp/config.py"]
    assert "django.db.backends.mysql" in artifacts["backendapp/config.py"]


def test_docs_cover_schemas_auth_permissions_and_errors(generated):
    result, _ = generated
    docs = result["artifacts"]["backendapp/docs.md"]

    for expected in (
        "## Authentication and role management",
        "| POST | `/api/auth/token/` | none | public | 200 |",
        "| POST | `/api/auth/logout/` | JWT | authenticated | 204 |",
        "## Roles",
        "## Error format",
        "validation_error",
        "duplicate_name",
        "## Pagination, search and filtering",
        "created_after",
        "Request body",
        "| Field | Type | Required | Notes |",
        "required",
        "## Database",
        "MySQL",
    ):
        assert expected in docs, expected
    # per-resource permission and endpoints are documented
    assert "| GET | `/api/manage_products/` | JWT |" in docs
    assert "REQ-002" in docs


def test_generated_suite_ran_on_sqlite(generated):
    result, _ = generated
    assert result["tests_passed"] is True
    assert "sqlite" in result["databases_tested"]
    output = result["test_output"]
    assert "AuthFlowTests" in output
    assert "RoleBasedAccessTests" in output
    assert "test_duplicate_name_is_a_409_conflict" in output
    assert "test_attachment_upload_and_type_validation" in output
    assert "OK" in output


def test_generated_suite_ran_on_mysql(generated):
    result, _ = generated
    assert result["tests_passed"] is True
    assert "mysql" in result["databases_tested"]
    assert "Ran " in result["test_output"]


def test_generated_database_config_is_pydantic_validated(generated):
    result, _ = generated
    harness_dir = result["harness_dir"]
    sys.path.insert(0, harness_dir)
    try:
        config_module = importlib.import_module("backendapp.config")
        sqlite_config = config_module.read_database_config({})
        assert sqlite_config.as_django()["ENGINE"] == "django.db.backends.sqlite3"

        mysql_config = config_module.read_database_config(
            {
                "GENERATED_DB_ENGINE": "mysql",
                "MYSQL_DATABASE": "generated_app",
                "MYSQL_USER": "root",
                "MYSQL_HOST": "127.0.0.1",
                "MYSQL_PORT": "3307",
            }
        )
        django_db = mysql_config.as_django()
        assert django_db["ENGINE"] == "django.db.backends.mysql"
        assert django_db["PORT"] == "3307"

        with pytest.raises(RuntimeError):
            config_module.read_database_config(
                {"GENERATED_DB_ENGINE": "mysql", "MYSQL_PORT": "99999"}
            )
    finally:
        sys.path.remove(harness_dir)
        for name in [m for m in sys.modules if m == "backendapp" or m.startswith("backendapp.")]:
            del sys.modules[name]


def test_plan_validation_rejects_malformed_specs():
    good = dict(
        rid="REQ-001", title="Users can manage products", resource="manage_products",
        route="manage_products", class_name="ManageProducts",
        endpoints=["GET /api/manage_products/"],
    )
    assert ResourceSpec(**good).route == "manage_products"

    with pytest.raises(ValidationError):
        ResourceSpec(**{**good, "route": "Manage Products"})
    with pytest.raises(ValidationError):
        ResourceSpec(**{**good, "endpoints": ["FETCH /api/manage_products/"]})
    with pytest.raises(ValidationError):
        ResourceSpec(**{**good, "rid": "REQ-abc"})
    with pytest.raises(ValidationError):
        GenerationPlan(
            project_id=1,
            resources=[ResourceSpec(**good), ResourceSpec(**good)],
        )
