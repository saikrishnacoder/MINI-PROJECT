from django.conf import settings
from django.db import models

from projects.models import Project


class GeneratedBackend(models.Model):
    class Status(models.TextChoices):
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

    project = models.OneToOneField(
        Project, on_delete=models.CASCADE, related_name="generated_backend"
    )
    status = models.CharField(max_length=16, choices=Status.choices)
    # [{"rid": "REQ-001", "resource": "sign_in", "class_name": "SignIn",
    #   "endpoints": ["GET /api/sign_in/", "POST /api/sign_in/", ...]}]
    resources = models.JSONField(default=list)
    # {"harness/backendapp/models.py": "...", "harness/backendapp/docs.md": "...", ...}
    artifacts = models.JSONField(default=dict)
    tests_passed = models.BooleanField(null=True, blank=True)
    test_output = models.TextField(blank=True)
    # Databases the generated suite was actually executed on, e.g. ["sqlite", "mysql"].
    databases_tested = models.JSONField(default=list, blank=True)
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="generated_backends",
    )
    generated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Backend for {self.project.name} ({self.status})"


class GeneratedFrontend(models.Model):
    class Status(models.TextChoices):
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

    project = models.OneToOneField(
        Project, on_delete=models.CASCADE, related_name="generated_frontend"
    )
    status = models.CharField(max_length=16, choices=Status.choices)
    # [{"rid": "REQ-001", "route": "manage_products", "label": "ManageProducts",
    #   "component": "src/pages/ResourceListPage.tsx", "api_base": "/api/manage_products/"}]
    pages = models.JSONField(default=list)
    # {"src/pages/Login.tsx": "...", "src/resources.ts": "...", ...}
    artifacts = models.JSONField(default=dict)
    build_passed = models.BooleanField(null=True, blank=True)
    build_output = models.TextField(blank=True)
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="generated_frontends",
    )
    generated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Frontend for {self.project.name} ({self.status})"
