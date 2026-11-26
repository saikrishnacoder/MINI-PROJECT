from django.conf import settings
from django.db import models


class Project(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING_APPROVAL = "pending_approval", "Pending approval"
        APPROVED = "approved", "Approved"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="projects"
    )
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=32, choices=Status.choices, default=Status.DRAFT, db_index=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = [("owner", "name")]

    def __str__(self):
        return self.name


class Requirement(models.Model):
    class Type(models.TextChoices):
        FUNCTIONAL = "functional", "Functional"
        NON_FUNCTIONAL = "non_functional", "Non-functional"

    class Priority(models.TextChoices):
        MUST = "must", "Must"
        SHOULD = "should", "Should"
        COULD = "could", "Could"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING = "pending", "Pending approval"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="requirements"
    )
    rid = models.CharField(max_length=32)  # e.g. REQ-001, unique per project
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    req_type = models.CharField(
        max_length=32, choices=Type.choices, default=Type.FUNCTIONAL
    )
    priority = models.CharField(
        max_length=16, choices=Priority.choices, default=Priority.MUST
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.DRAFT, db_index=True
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_requirements",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["rid"]
        unique_together = [("project", "rid")]

    def __str__(self):
        return f"{self.rid} {self.title}"


class TraceLink(models.Model):
    """Links an approved requirement to a real component of the generated app."""

    class Kind(models.TextChoices):
        FRONTEND = "frontend", "Frontend component"
        BACKEND = "backend", "Backend endpoint"
        DB = "db", "Database table"
        TEST = "test", "Test"

    requirement = models.ForeignKey(
        Requirement, on_delete=models.CASCADE, related_name="trace_links"
    )
    kind = models.CharField(max_length=16, choices=Kind.choices)
    artifact = models.CharField(max_length=255)  # e.g. backend/projects/views.py
    description = models.TextField(blank=True)
    test_passed = models.BooleanField(null=True, blank=True)  # only for kind=test
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["kind", "artifact"]


class ApprovalEvent(models.Model):
    """Audit trail: who approved/rejected what, and when."""

    class Action(models.TextChoices):
        SUBMIT = "submit", "Submitted for approval"
        APPROVE = "approve", "Approved"
        REJECT = "reject", "Rejected"

    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="approval_events"
    )
    requirement = models.ForeignKey(
        Requirement, on_delete=models.CASCADE, null=True, blank=True, related_name="approval_events"
    )
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    action = models.CharField(max_length=16, choices=Action.choices)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
