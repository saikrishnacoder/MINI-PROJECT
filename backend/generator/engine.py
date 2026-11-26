"""Phase 4 - Backend Development Engine.

Turns an approved project's approved functional requirements into a real,
runnable DRF app (models, serializers, permissions, viewsets, routes, docs and
tests). Every generated resource is traced back to its requirement IDs, and the
generated test suite is executed against SQLite after generation.
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# Phrases stripped from the front of a requirement title to find the resource.
_FILLER_PREFIXES = [
    "users should be able to",
    "user should be able to",
    "users can be able to",
    "users can",
    "user can",
    "the system shall",
    "system shall",
    "the system should",
    "system should",
    "the user can",
    "the application shall",
    "the application should",
    "i want to",
    "we want to",
    "ability to",
    "allow",
    "allows",
]

_STOP_WORDS = {"a", "an", "the", "to", "be", "of", "and", "or", "in", "on", "for", "with", "my", "our"}


def derive_resource(title: str) -> str:
    """Deterministically map a requirement title to a snake_case resource name."""
    text = title.lower().strip().rstrip(".")
    for filler in _FILLER_PREFIXES:
        if text.startswith(filler):
            text = text[len(filler):].strip()
            break
    words = [w for w in re.split(r"[^a-z0-9]+", text) if w]
    words = [w for w in words if w not in _STOP_WORDS][:3] or ["item"]
    return "_".join(words)


def class_name(resource: str) -> str:
    return "".join(w.capitalize() for w in resource.split("_"))


def _plural(resource: str) -> str:
    if resource.endswith("s"):
        return resource
    if resource.endswith("y"):
        return resource[:-1] + "ies"
    return resource + "s"


def _model(resource: str, name: str) -> str:
    return f'''from django.conf import settings
from django.db import models


class {name}(models.Model):
    """Generated from the approved requirements (trace_rids in docs)."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="{_plural(resource)}"
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name
'''


def _serializers(name: str) -> str:
    return f'''from rest_framework import serializers

from .models import {name}


class {name}Serializer(serializers.ModelSerializer):
    class Meta:
        model = {name}
        fields = ["id", "name", "description", "created_at", "updated_at"]
        read_only_fields = ["created_at", "updated_at"]
'''


def _permissions() -> str:
    return '''from rest_framework import permissions


class IsOwner(permissions.BasePermission):
    """Only the owner of an object may read or change it."""

    def has_object_permission(self, request, view, obj):
        return obj.owner_id == request.user.id
'''


def _views(name: str, serializer: str) -> str:
    return f'''from rest_framework import permissions, viewsets

from .models import {name}
from .permissions import IsOwner
from .serializers import {serializer}Serializer


class {name}ViewSet(viewsets.ModelViewSet):
    """CRUD API for {name}, scoped to the requesting user."""

    serializer_class = {serializer}Serializer
    permission_classes = [permissions.IsAuthenticated, IsOwner]

    def get_queryset(self):
        return {name}.objects.filter(owner=self.request.user)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)
'''


def _urls(route: str, name: str) -> str:
    return f'''from rest_framework.routers import DefaultRouter

from .views import {name}ViewSet

router = DefaultRouter()
router.register(r"{route}", {name}ViewSet, basename="{route}")

urlpatterns = router.urls
'''


def _tests(name: str, route: str) -> str:
    return f'''from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import test

from .models import {name}


class {name}APITests(test.APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="owner", email="owner@example.com", password="strong-pass-123"
        )
        self.client.force_authenticate(self.user)
        self.list_url = reverse("{route}-list")

    def _create(self):
        return self.client.post(
            self.list_url, {{"name": "Sample", "description": "d"}}, format="json"
        )

    def test_unauthenticated_access_is_denied(self):
        anon = test.APIClient()
        self.assertEqual(anon.get(self.list_url).status_code, 401)

    def test_owner_can_create_and_retrieve(self):
        res = self._create()
        self.assertEqual(res.status_code, 201, res.data)
        res = self.client.get(self.list_url)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data["results"]), 1)

    def test_owner_can_update_and_delete(self):
        self._create()
        detail_url = reverse("{route}-detail", args=[1])
        self.assertEqual(
            self.client.patch(detail_url, {{"name": "Changed"}}, format="json").status_code, 200
        )
        self.assertEqual(self.client.delete(detail_url).status_code, 204)

    def test_other_user_cannot_see_object(self):
        self._create()
        other = get_user_model().objects.create_user(
            username="other", email="other@example.com", password="strong-pass-123"
        )
        self.client.force_authenticate(other)
        detail_url = reverse("{route}-detail", args=[1])
        self.assertIn(self.client.get(detail_url).status_code, (403, 404))
'''


def _docs(project, resources) -> str:
    lines = [
        f"# Generated backend - {project.name}",
        "",
        f"Generated by SpecForge AI Phase 4 on approval of {project.name}.",
        "",
        "## Endpoint inventory",
        "",
        "| Requirement | Resource | Endpoints |",
        "|---|---|---|",
    ]
    for r in resources:
        lines.append(f"| {r['rid']} ({r['title']}) | `{r['route']}` | {', '.join(f'`{e}`' for e in r['endpoints'])} |")
    lines += ["", "## Permissions", "",
              "Every endpoint requires authentication and is scoped to the owning user",
              "(`IsOwner`).", ""]
    nf = project.requirements.filter(req_type="non_functional", status="approved")
    if nf.exists():
        lines += ["## Non-functional requirements carried through", ""]
        lines += [f"- **{req.rid}** {req.title}: {req.description}" for req in nf]
        lines.append("")
    return "\n".join(lines)


def _trace_map(resources) -> str:
    import json
    return json.dumps(resources, indent=2)


def _harness_files(resources) -> dict:
    urls_imports = "\n".join(f"from .views import {r['class_name']}ViewSet" for r in resources)
    router_lines = "\n".join(
        f'router.register(r"{r["route"]}", {r["class_name"]}ViewSet, basename="{r["route"]}")'
        for r in resources
    )
    root_urls = f'''from django.urls import include, path
from rest_framework.routers import DefaultRouter

{urls_imports}

router = DefaultRouter()
{router_lines}

urlpatterns = [path("api/", include(router.urls))]
'''
    settings_py = '''SECRET_KEY = "generated-harness-only"
DEBUG = True
ALLOWED_HOSTS = ["*"]
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "rest_framework",
    "backendapp",
]
DATABASES = {
    "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": "harness.sqlite3"}
}
ROOT_URLCONF = "backendapp.urls"
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework.authentication.BasicAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),

    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    "TEST_RUNNER": "django.test.runner.DiscoverRunner",
}
'''
    manage_py = '''#!/usr/bin/env python
import os
import sys


def main():
    os.environ["DJANGO_SETTINGS_MODULE"] = "settings"
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
'''
    apps_py = '''from django.apps import AppConfig


class BackendappConfig(AppConfig):
    name = "backendapp"
'''
    return {
        "settings.py": settings_py,
        "manage.py": manage_py,
        "backendapp/apps.py": apps_py,
        "backendapp/urls.py": root_urls,
    }


def generate_backend(project, user) -> dict:
    """Build the generated app for an approved project and run its tests.

    Returns a dict: {status, resources, artifacts, tests_passed, test_output, harness_dir}
    """
    approved = project.requirements.filter(status="approved")
    functional = [r for r in approved if r.req_type == "functional"]

    resources, seen = [], {}
    for req in functional:
        base = derive_resource(req.title)
        n = 2
        route = base
        while route in seen:
            route = f"{base}_{n}"
            n += 1
        seen[route] = True
        name = class_name(base)
        resources.append({
            "rid": req.rid,
            "title": req.title,
            "priority": req.priority,
            "resource": base,
            "route": route,
            "class_name": name,
            "endpoints": [
                f"GET /api/{route}/",
                f"POST /api/{route}/",
                f"GET /api/{route}/{{id}}/",
                f"PATCH /api/{route}/{{id}}/",
                f"DELETE /api/{route}/{{id}}/",
            ],
        })

    artifacts: dict = {}
    artifacts["backendapp/models.py"] = "\n\n".join(
        _model(r["resource"], r["class_name"]) for r in resources
    )
    artifacts["backendapp/serializers.py"] = "\n\n".join(
        _serializers(r["class_name"]) for r in resources
    )
    artifacts["backendapp/permissions.py"] = _permissions()
    artifacts["backendapp/views.py"] = "\n\n".join(
        _views(r["class_name"], r["class_name"]) for r in resources
    )
    artifacts["backendapp/tests.py"] = "\n\n".join(
        _tests(r["class_name"], r["route"]) for r in resources
    )
    artifacts["backendapp/docs.md"] = _docs(project, resources)
    artifacts["backendapp/requirements_map.json"] = _trace_map(resources)
    for path, content in _harness_files(resources).items():
        artifacts[path] = content

    harness_dir = Path(tempfile.mkdtemp(prefix=f"specforge_backend_{project.id}_"))
    for rel, content in artifacts.items():
        target = harness_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    (harness_dir / "backendapp/__init__.py").write_text("")
    # Hidden per-project record of where the artifacts were materialised.
    artifacts["harness_dir"] = str(harness_dir)

    tests_passed, output = _run_harness(harness_dir)
    return {
        "status": "success" if tests_passed else "failed",
        "resources": resources,
        "artifacts": artifacts,
        "tests_passed": tests_passed,
        "test_output": output,
        "harness_dir": str(harness_dir),
    }


def _run_harness(harness_dir: Path, timeout: int = 180) -> tuple[bool, str]:
    env_python = sys.executable
    commands = [
        [env_python, "manage.py", "makemigrations", "backendapp"],
        [env_python, "manage.py", "test", "backendapp", "-v", "1", "--noinput"],
    ]
    output_parts = []
    for cmd in commands:
        try:
            proc = subprocess.run(
                cmd, cwd=harness_dir, capture_output=True, text=True, timeout=timeout
            )
            output_parts.append(f"$ {' '.join(cmd[1:])}\n{proc.stdout}\n{proc.stderr}")
            if proc.returncode != 0:
                return False, "\n---\n".join(output_parts)
        except subprocess.TimeoutExpired:
            output_parts.append(f"$ {' '.join(cmd[1:])}\nTIMED OUT after {timeout}s")
            return False, "\n---\n".join(output_parts)
    return True, "\n---\n".join(output_parts)
