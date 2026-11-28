"""File builders for the Phase 4 generated DRF app.

Every function returns the exact text of one generated file. The app is real,
runnable Django: JWT auth, role-based permissions, a service layer with
transactions, a structured error handler, file upload validation, search and
filtering, pagination, lifecycle workflows, notifications, analytics and API
docs carrying request/response schemas.
"""
import json

from .schemas import ResourceSpec


def _plural(resource: str) -> str:
    if resource.endswith("s"):
        return resource
    if resource.endswith("y"):
        return resource[:-1] + "ies"
    return resource + "s"


def models_py(resources: list[ResourceSpec]) -> str:
    header = '''from django.conf import settings
from django.db import models


class Role(models.Model):
    """Configurable role. Flags drive the permissions generated for every resource."""

    name = models.CharField(max_length=50, unique=True)
    can_view_all = models.BooleanField(default=False)
    can_edit_others = models.BooleanField(default=False)
    can_manage_users = models.BooleanField(default=False)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class UserProfile(models.Model):
    """One role per user; created automatically when a user is created."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile"
    )
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="members")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user_id"]

    def __str__(self):
        return f"{self.user} ({self.role})"


LIFECYCLE_CHOICES = [
    ("draft", "Draft"),
    ("active", "Active"),
    ("archived", "Archived"),
]
'''
    models = [_resource_model(r) for r in resources]
    shared = _shared_models()
    return header + "\n\n" + "\n\n".join(models) + "\n\n" + shared


def _shared_models() -> str:
    return '''class StatusEvent(models.Model):
    """Audit row for every lifecycle transition of any generated resource."""

    resource = models.CharField(max_length=100)
    rid = models.CharField(max_length=32)
    object_id = models.PositiveIntegerField()
    from_status = models.CharField(max_length=16)
    to_status = models.CharField(max_length=16)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="status_events"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["resource", "object_id", "-created_at"])]

    def __str__(self):
        return f"{self.resource}#{self.object_id}: {self.from_status} -> {self.to_status}"


class Notification(models.Model):
    """In-app notification. Only its recipient can read or mark it."""

    class Kind(models.TextChoices):
        CREATED = "record_created", "Record created"
        UPDATED = "record_updated", "Record updated"
        DELETED = "record_deleted", "Record deleted"
        STATUS = "status_changed", "Status changed"

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    kind = models.CharField(max_length=32, choices=Kind.choices)
    resource = models.CharField(max_length=100)
    rid = models.CharField(max_length=32)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    title = models.CharField(max_length=200)
    message = models.TextField(blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["recipient", "read_at", "-created_at"])]

    def __str__(self):
        return f"{self.title} -> {self.recipient}"


class ProviderEvent(models.Model):
    """One real answer from a configured external provider. Never written speculatively."""

    provider = models.CharField(max_length=50)
    action = models.CharField(max_length=50)
    resource = models.CharField(max_length=100)
    object_id = models.PositiveIntegerField()
    http_status = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(max_length=16)
    detail = models.TextField(blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="provider_events"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.provider}:{self.action} {self.status} ({self.http_status})"
'''


def _resource_model(r: ResourceSpec) -> str:
    return f'''class {r.class_name}(models.Model):
    """Generated from {r.rid} - {r.title}."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="{_plural(r.resource)}"
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    attachment = models.FileField(upload_to="attachments/%Y/%m/", blank=True, null=True)
    status = models.CharField(max_length=16, choices=LIFECYCLE_CHOICES, default="draft")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["owner", "-created_at"]), models.Index(fields=["status"])]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "name"], name="uniq_{r.route}_owner_name"
            )
        ]

    def __str__(self):
        return self.name
'''


def roles_py() -> str:
    return '''"""Default roles, seeded after every migrate and used by the test suite."""
from .models import Role

DEFAULT_ROLES = {
    "admin": {
        "can_view_all": True,
        "can_edit_others": True,
        "can_manage_users": True,
    },
    "manager": {
        "can_view_all": True,
        "can_edit_others": True,
        "can_manage_users": False,
    },
    "user": {
        "can_view_all": False,
        "can_edit_others": False,
        "can_manage_users": False,
    },
}


def ensure_default_roles():
    """Idempotently create the three default roles."""
    for name, flags in DEFAULT_ROLES.items():
        Role.objects.get_or_create(name=name, defaults=flags)
'''


def signals_py() -> str:
    return '''"""Role seeding and profile creation."""
from django.contrib.auth import get_user_model
from django.db.models.signals import post_migrate, post_save
from django.dispatch import receiver

from .models import Role, UserProfile
from .roles import ensure_default_roles

User = get_user_model()


@receiver(post_migrate)
def _seed_roles(sender, **kwargs):
    if getattr(sender, "name", None) != "backendapp":
        return
    ensure_default_roles()


@receiver(post_save, sender=User)
def _ensure_profile(sender, instance, created, **kwargs):
    if not created:
        return
    role, _ = Role.objects.get_or_create(
        name="user",
        defaults={"can_view_all": False, "can_edit_others": False, "can_manage_users": False},
    )
    UserProfile.objects.get_or_create(user=instance, defaults={"role": role})
'''


def apps_py() -> str:
    return '''from django.apps import AppConfig


class BackendappConfig(AppConfig):
    name = "backendapp"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from . import signals  # noqa: F401  (registers post_migrate / post_save)
'''


def permissions_py() -> str:
    return '''from rest_framework import permissions

from .models import UserProfile


def role_of(user):
    """Return the user's Role (fresh from the database), or None.

    Reading through the database instead of the cached reverse OneToOne keeps
    permission checks correct when a role is assigned while a user object is
    already loaded.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return None
    profile = (
        UserProfile.objects.filter(user_id=user.pk).select_related("role").first()
    )
    return profile.role if profile else None


class IsOwnerOrRole(permissions.BasePermission):
    """Object-level access.

    * the owner always has full access;
    * roles with ``can_view_all`` may read any record;
    * roles with ``can_edit_others`` may also update and delete them.
    """

    message = "You do not have access to this record."

    def has_object_permission(self, request, view, obj):
        if obj.owner_id == request.user.id:
            return True
        role = role_of(request.user)
        if role is None:
            return False
        if request.method in permissions.SAFE_METHODS:
            return role.can_view_all
        return role.can_edit_others


class IsAdminRole(permissions.BasePermission):
    """Only roles with ``can_manage_users`` (default: admin) may manage users."""

    message = "Only administrators can manage users and roles."

    def has_permission(self, request, view):
        role = role_of(request.user)
        return bool(role and role.can_manage_users)
'''


def serializers_py(resources: list[ResourceSpec]) -> str:
    head = '''from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Role, UserProfile, Notification, StatusEvent
'''
    imports = "\n".join(f"from .models import {r.class_name}" for r in resources)
    tail = '''

User = get_user_model()


class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ["id", "name", "can_view_all", "can_edit_others", "can_manage_users"]


class UserSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "email", "is_active", "date_joined", "role"]
        read_only_fields = fields

    def get_role(self, obj):
        # Fresh lookup: a role assignment must be visible on the same instance.
        profile = UserProfile.objects.filter(user_id=obj.pk).select_related("role").first()
        if profile is None:
            return None
        return RoleSerializer(profile.role).data


class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(min_length=8, max_length=128, write_only=True)

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("This username is already taken.")
        return value

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("This email is already registered.")
        return value

    def create(self, validated_data):
        return User.objects.create_user(
            username=validated_data["username"],
            email=validated_data["email"],
            password=validated_data["password"],
        )


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class RoleAssignSerializer(serializers.Serializer):
    role = serializers.CharField(max_length=50)


class TransitionSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["draft", "active", "archived"])


class StatusEventSerializer(serializers.ModelSerializer):
    actor_username = serializers.SerializerMethodField()

    class Meta:
        model = StatusEvent
        fields = ["id", "resource", "rid", "object_id", "from_status", "to_status",
                  "actor_username", "created_at"]

    def get_actor_username(self, obj):
        return obj.actor.username if obj.actor_id else None


class NotificationSerializer(serializers.ModelSerializer):
    read = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = ["id", "kind", "resource", "rid", "object_id", "title", "message",
                  "read", "read_at", "created_at"]

    def get_read(self, obj):
        return obj.read_at is not None


def issue_tokens(user):
    refresh = RefreshToken.for_user(user)
    return {"refresh": str(refresh), "access": str(refresh.access_token)}
'''

    serializers = "\n\n".join(_resource_serializer(r) for r in resources)
    return head + imports + "\n\n" + serializers + "\n" + tail


def _resource_serializer(r: ResourceSpec) -> str:
    fields = ", ".join(f'"{f}"' for f in r.readable_fields)
    read_only = ", ".join(
        f'"{f}"' for f in ["id", "attachment_url", "status", "created_at", "updated_at"]
    )
    search = ", ".join(r.search_fields)
    return f'''class {r.class_name}Serializer(serializers.ModelSerializer):
    """{r.rid} - {r.title}. Searchable fields: {search}."""

    attachment_url = serializers.SerializerMethodField()

    class Meta:
        model = {r.class_name}
        fields = [{fields}]
        read_only_fields = [{read_only}]
        extra_kwargs = {{"name": {{"max_length": 200}}}}

    def get_attachment_url(self, obj):
        if not obj.attachment:
            return None
        request = self.context.get("request")
        url = obj.attachment.url
        return request.build_absolute_uri(url) if request else url
'''


def services_py(resources: list[ResourceSpec]) -> str:
    models = ", ".join(r.class_name for r in resources)
    header = '''"""Business-logic layer.

Views never touch the ORM directly: every write goes through these functions,
which hold the transaction boundary and turn domain violations into
``ServiceError`` (rendered by the shared exception handler).
"""
import logging
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.utils import timezone

from .exceptions import ServiceError
from .permissions import role_of
from .models import ''' + models + ''', Notification, ProviderEvent, StatusEvent, UserProfile

logger = logging.getLogger("backendapp.services")

MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024
ALLOWED_ATTACHMENT_SUFFIXES = {".csv", ".jpeg", ".jpg", ".pdf", ".png", ".txt"}

# Lifecycle: draft -> active -> archived, and back. Anything else is rejected.
STATUS_TRANSITIONS = {
    "draft": ("active",),
    "active": ("draft", "archived"),
    "archived": ("active",),
}


def allowed_transitions(current):
    """Statuses reachable from ``current``."""
    return list(STATUS_TRANSITIONS.get(current, ()))


def validate_attachment(upload):
    """Reject uploads that are too large or of an unsupported type."""
    if not upload:
        return
    name = getattr(upload, "name", "") or ""
    suffix = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if suffix not in ALLOWED_ATTACHMENT_SUFFIXES:
        raise ServiceError(
            "unsupported_attachment",
            "Attachments must be pdf, png, jpg, jpeg, txt or csv.",
            {"suffix": suffix, "allowed": sorted(ALLOWED_ATTACHMENT_SUFFIXES)},
        )
    size = getattr(upload, "size", 0) or 0
    if size > MAX_ATTACHMENT_BYTES:
        raise ServiceError(
            "attachment_too_large",
            "Attachments are limited to 5 MB.",
            {"size": size, "max_size": MAX_ATTACHMENT_BYTES},
        )


def notify_record(*, instance, resource, rid, kind, title, message=""):
    """Write one Notification row per recipient: the owner and viewers of everything.

    Recipients are resolved from the database so a role change applies at once.
    """
    recipients = {instance.owner_id}
    recipients.update(
        UserProfile.objects.filter(role__can_view_all=True).values_list("user_id", flat=True)
    )
    rows = [
        Notification(
            recipient_id=recipient,
            kind=kind,
            resource=resource,
            rid=rid,
            object_id=instance.pk,
            title=title,
            message=message,
        )
        for recipient in sorted(recipients)
    ]
    Notification.objects.bulk_create(rows)
    return len(rows)


@transaction.atomic
def transition_status(*, instance, resource, rid, target_status, actor):
    """Move a record along the lifecycle and audit the change."""
    target = (target_status or "").strip().lower()
    if target not in STATUS_TRANSITIONS:
        raise ServiceError(
            "invalid_status",
            f"Unknown status {target!r}.",
            {"allowed": sorted(STATUS_TRANSITIONS)},
        )
    if target == instance.status:
        raise ServiceError(
            "no_status_change", f"Record is already {target}.", {"status": target}
        )
    if target not in STATUS_TRANSITIONS[instance.status]:
        raise ServiceError(
            "invalid_transition",
            f"{instance.status} -> {target} is not allowed.",
            {"from": instance.status, "to": target, "allowed": allowed_transitions(instance.status)},
        )
    previous = instance.status
    instance.status = target
    instance.save(update_fields=["status", "updated_at"])
    StatusEvent.objects.create(
        resource=resource,
        rid=rid,
        object_id=instance.pk,
        from_status=previous,
        to_status=target,
        actor=actor,
    )
    notify_record(
        instance=instance,
        resource=resource,
        rid=rid,
        kind=Notification.Kind.STATUS,
        title=f"{instance.name} moved to {target}",
        message=f"{previous} -> {target}",
    )
    logger.info("transitioned %s id=%s %s->%s", resource, instance.pk, previous, target)
    return instance


def analytics_summary(*, user):
    """Per-resource counts scoped by the caller's role, from the database."""
    role = role_of(user)
    since = timezone.now() - timedelta(days=7)
    can_view_all = bool(role and role.can_view_all)
    rows = []
    totals = {"total": 0, "mine": 0, "created_last_7_days": 0}
    for model, route, rid in _ANALYTICS_MODELS:
        visible = model.objects.all() if can_view_all else model.objects.filter(owner_id=user.pk)
        aggregate = visible.aggregate(
            total=Count("id"), recent=Count("id", filter=Q(created_at__gte=since))
        )
        mine = model.objects.filter(owner_id=user.pk).count()
        by_status = {
            row["status"]: row["n"] for row in visible.values("status").annotate(n=Count("id"))
        }
        rows.append(
            {
                "resource": route,
                "rid": rid,
                "total": aggregate["total"],
                "mine": mine,
                "created_last_7_days": aggregate["recent"],
                "by_status": by_status,
            }
        )
        totals["total"] += aggregate["total"]
        totals["mine"] += mine
        totals["created_last_7_days"] += aggregate["recent"]
    return {"generated_at": timezone.now().isoformat(), "totals": totals, "resources": rows}


_ANALYTICS_MODELS = [
''' + "\n".join(
        f'    ({r.class_name}, "{r.route}", "{r.rid}"),' for r in resources
    ) + '''
]
'''
    bodies = _resource_services(resources)
    payment = ""
    if any("payments" in r.capabilities for r in resources):
        payment = '''

def request_checkout(*, instance, resource, rid, actor):
    """Ask the configured payment provider; nothing is recorded without a real answer.

    Deliberately not atomic: a failure must leave its ProviderEvent row committed.
    """
    from . import integrations

    return integrations.request_payment(
        action="checkout",
        resource=resource,
        rid=rid,
        object_id=instance.pk,
        payload={"reference": f"{resource}:{instance.pk}", "label": instance.name},
        actor=actor,
    )
'''
    return header + "\n\n" + bodies + payment


def _resource_services(resources: list[ResourceSpec]) -> str:
    return "\n".join(_one_resource_services(r) for r in resources)


def _one_resource_services(r: ResourceSpec) -> str:
    return f'''@transaction.atomic
def create_{r.route}(*, owner, serializer):
    """Create one {r.class_name} for ``owner``; duplicate names are a conflict."""
    data = serializer.validated_data
    validate_attachment(data.get("attachment"))
    try:
        with transaction.atomic():
            obj = serializer.save(owner=owner)
    except IntegrityError as exc:
        raise ServiceError(
            "duplicate_name",
            "You already have a {r.resource} with this name.",
            {{"name": data.get("name")}},
            status_code=409,
        ) from exc
    notify_record(
        instance=obj,
        resource="{r.route}",
        rid="{r.rid}",
        kind=Notification.Kind.CREATED,
        title=f"{{obj.name}} created",
        message="{r.rid} {r.title}",
    )
    logger.info("created %s id=%s owner=%s", "{r.route}", obj.pk, owner.pk)
    return obj


@transaction.atomic
def update_{r.route}(*, instance, serializer, actor=None):
    """Update one {r.class_name} inside a transaction."""
    validate_attachment(serializer.validated_data.get("attachment"))
    try:
        with transaction.atomic():
            obj = serializer.save()
    except IntegrityError as exc:
        raise ServiceError(
            "duplicate_name",
            "You already have a {r.resource} with this name.",
            {{"name": serializer.validated_data.get("name")}},
            status_code=409,
        ) from exc
    notify_record(
        instance=obj,
        resource="{r.route}",
        rid="{r.rid}",
        kind=Notification.Kind.UPDATED,
        title=f"{{obj.name}} updated",
        message=f"Updated by {{getattr(actor, 'username', 'system')}}",
    )
    return obj


@transaction.atomic
def delete_{r.route}(*, instance, actor=None):
    """Delete one {r.class_name} inside a transaction."""
    pk = instance.pk
    name = instance.name
    owner_id = instance.owner_id
    instance.delete()
    Notification.objects.create(
        recipient_id=owner_id,
        kind=Notification.Kind.DELETED,
        resource="{r.route}",
        rid="{r.rid}",
        object_id=pk,
        title=f"{{name}} deleted",
        message=f"Deleted by {{getattr(actor, 'username', 'system')}}",
    )
    logger.info("deleted %s id=%s", "{r.route}", pk)
'''


def exceptions_py() -> str:
    return '''"""Structured API errors.

Every failure - validation, auth, permissions, domain conflicts and unhandled
exceptions - is rendered as
``{"error": {"code", "message", "details", "request_id"}}``.
"""
import logging

from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger("backendapp.api")

_STATUS_CODES = {
    400: "validation_error",
    401: "not_authenticated",
    403: "permission_denied",
    404: "not_found",
    405: "method_not_allowed",
    415: "unsupported_media_type",
    429: "rate_limited",
    500: "internal_error",
}

_ERROR_MESSAGES = {
    "validation_error": "Request validation failed.",
    "not_authenticated": "Authentication credentials were not provided or are invalid.",
    "permission_denied": "You do not have permission to perform this action.",
    "not_found": "The requested resource was not found.",
    "method_not_allowed": "That HTTP method is not allowed on this endpoint.",
    "unsupported_media_type": "The request media type is not supported.",
    "rate_limited": "Too many requests, slow down.",
    "internal_error": "An unexpected error occurred.",
}


class ServiceError(APIException):
    """Domain error raised by the service layer."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "service_error"
    default_detail = "The request could not be completed."

    def __init__(self, code, message, details=None, status_code=None):
        self.error_code = code
        self.details = details or {}
        self.detail = message
        if status_code is not None:
            self.status_code = status_code


def _envelope(code, message, details, request_id, status_code):
    return Response(
        {
            "error": {
                "code": code,
                "message": message,
                "details": details,
                "request_id": request_id,
            }
        },
        status=status_code,
    )


def api_exception_handler(exc, context):
    request = context.get("request")
    request_id = getattr(request, "request_id", None)

    if isinstance(exc, ServiceError):
        return _envelope(exc.error_code, str(exc.detail), exc.details, request_id, exc.status_code)

    response = exception_handler(exc, context)
    if response is None:
        logger.exception("unhandled API error", exc_info=exc)
        return _envelope(
            "internal_error",
            "An unexpected error occurred.",
            {},
            request_id,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    data = response.data
    details = data if isinstance(data, dict) else {"non_field_errors": data}
    code = _STATUS_CODES.get(response.status_code, "error")
    if isinstance(data, dict) and set(data) == {"detail"}:
        message = str(data["detail"])
        details = {}
    else:
        message = _ERROR_MESSAGES.get(code, "Request failed.")
    return _envelope(code, message, details, request_id, response.status_code)
'''


def middleware_py() -> str:
    return '''"""Request id propagation and one structured log line per request."""
import json
import logging
import time
import uuid

logger = logging.getLogger("backendapp.request")


class RequestIDMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request.request_id = request_id
        started = time.monotonic()
        response = self.get_response(request)
        response["X-Request-ID"] = request_id
        logger.info(
            json.dumps(
                {
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.path,
                    "status": response.status_code,
                    "duration_ms": round((time.monotonic() - started) * 1000, 1),
                }
            )
        )
        return response
'''


def pagination_py() -> str:
    return '''from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class StandardPagination(PageNumberPagination):
    """Page-number pagination with a server-side cap (``?page_size=`` <= 100)."""

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_paginated_response(self, data):
        return Response(
            {
                "count": self.page.paginator.count,
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "page": self.page.number,
                "page_size": self.get_page_size(self.request),
                "results": data,
            }
        )
'''


def filters_py() -> str:
    return '''from datetime import datetime, time

from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import filters
from rest_framework.exceptions import ValidationError

STATUS_VALUES = ("draft", "active", "archived")


def _start_of_day(day):
    return timezone.make_aware(datetime.combine(day, time.min), timezone.get_current_timezone())


def _end_of_day(day):
    return timezone.make_aware(datetime.combine(day, time.max), timezone.get_current_timezone())


class DateRangeFilter(filters.BaseFilterBackend):
    """``?created_after=YYYY-MM-DD`` and ``?created_before=YYYY-MM-DD``."""

    def filter_queryset(self, request, queryset, view):
        after = request.query_params.get("created_after")
        before = request.query_params.get("created_before")
        if after:
            parsed = parse_date(after)
            if parsed is None:
                raise ValidationError({"created_after": "Expected an ISO date, e.g. 2026-01-31."})
            queryset = queryset.filter(created_at__gte=_start_of_day(parsed))
        if before:
            parsed = parse_date(before)
            if parsed is None:
                raise ValidationError({"created_before": "Expected an ISO date, e.g. 2026-01-31."})
            queryset = queryset.filter(created_at__lte=_end_of_day(parsed))
        return queryset


class StatusFilter(filters.BaseFilterBackend):
    """``?status=draft|active|archived`` for the record lifecycle."""

    def filter_queryset(self, request, queryset, view):
        value = request.query_params.get("status")
        if not value:
            return queryset
        if value not in STATUS_VALUES:
            raise ValidationError({"status": f"Choose one of {', '.join(STATUS_VALUES)}."})
        return queryset.filter(status=value)
'''


def auth_views_py() -> str:
    return '''"""Authentication and role-management endpoints (JWT)."""
from django.contrib.auth import authenticate
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from .exceptions import ServiceError
from .models import Role, UserProfile
from .permissions import IsAdminRole
from .serializers import (
    LoginSerializer,
    LogoutSerializer,
    RegisterSerializer,
    RoleAssignSerializer,
    UserSerializer,
    issue_tokens,
)


class RegisterView(APIView):
    """POST /api/auth/register/ - create a standard user and return tokens."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            {"user": UserSerializer(user).data, **issue_tokens(user)},
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    """POST /api/auth/token/ - exchange credentials for an access/refresh pair."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(
            request,
            username=serializer.validated_data["username"],
            password=serializer.validated_data["password"],
        )
        if user is None or not user.is_active:
            raise ServiceError(
                "invalid_credentials",
                "Invalid username or password.",
                status_code=status.HTTP_401_UNAUTHORIZED,
            )
        return Response({"user": UserSerializer(user).data, **issue_tokens(user)})


class LogoutView(APIView):
    """POST /api/auth/logout/ - blacklist the refresh token."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            RefreshToken(serializer.validated_data["refresh"]).blacklist()
        except TokenError as exc:
            raise ServiceError(
                "invalid_refresh_token",
                "The refresh token is invalid or already blacklisted.",
                status_code=status.HTTP_400_BAD_REQUEST,
            ) from exc
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    """GET /api/auth/me/ - the authenticated user and their role."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)


class UserViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Admin-only user directory: GET /api/users/ and PATCH /api/users/{id}/role/."""

    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated, IsAdminRole]
    queryset = UserSerializer.Meta.model.objects.select_related("profile__role").order_by("id")

    @action(detail=True, methods=["patch"], url_path="role")
    def set_role(self, request, pk=None):
        target = self.get_object()
        serializer = RoleAssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        role_name = serializer.validated_data["role"]
        role = Role.objects.filter(name=role_name).first()
        if role is None:
            raise ServiceError(
                "unknown_role",
                "No role with that name exists.",
                {"role": role_name, "known_roles": list(Role.objects.values_list("name", flat=True))},
            )
        if target == request.user and not role.can_manage_users:
            raise ServiceError(
                "self_lockout",
                "You cannot remove your own administrative access.",
            )
        UserProfile.objects.update_or_create(user=target, defaults={"role": role})
        return Response(UserSerializer(target).data)
'''


def views_py(resources: list[ResourceSpec]) -> str:
    header = '''from rest_framework import parsers, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .features import FEATURES, SUMMARY
from .filters import DateRangeFilter, StatusFilter
from .integrations import describe_integrations
from .models import ''' + ", ".join(r.class_name for r in resources) + ''', Notification, StatusEvent
from .permissions import IsOwnerOrRole, role_of
from .serializers import (
''' + "".join(f"    {r.class_name}Serializer,\n" for r in resources) + '''    NotificationSerializer,
    StatusEventSerializer,
    TransitionSerializer,
)


def _visible_to(user, queryset):
    """Own records, or every record for roles with can_view_all."""
    role = role_of(user)
    if role and role.can_view_all:
        return queryset
    return queryset.filter(owner=user)


class AnalyticsSummaryView(APIView):
    """GET /api/analytics/summary/ - live counts scoped to the caller's role."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(services.analytics_summary(user=request.user))
'''
    views = "\n\n".join(_resource_view(r) for r in resources)
    ops = '''

class NotificationListView(APIView):
    """GET /api/notifications/ - the caller's inbox, newest first (``?unread=true``)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        queryset = Notification.objects.filter(recipient=request.user)
        if request.query_params.get("unread") in {"1", "true", "yes"}:
            queryset = queryset.filter(read_at__isnull=True)
        return Response(NotificationSerializer(queryset[:100], many=True).data)


class UnreadCountView(APIView):
    """GET /api/notifications/unread_count/ - ``{"unread": n}`` for the caller."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        count = Notification.objects.filter(
            recipient=request.user, read_at__isnull=True
        ).count()
        return Response({"unread": count})


class MarkReadView(APIView):
    """POST /api/notifications/{id}/read/ - only the recipient may mark a row."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        notification = Notification.objects.filter(recipient=request.user, pk=pk).first()
        if notification is None:
            return Response(
                {"error": {"code": "not_found", "message": "No such notification.",
                           "details": {}, "request_id": getattr(request, "request_id", "")}},
                status=404,
            )
        if notification.read_at is None:
            from django.utils import timezone

            notification.read_at = timezone.now()
            notification.save(update_fields=["read_at"])
        return Response(NotificationSerializer(notification).data)


class MarkAllReadView(APIView):
    """POST /api/notifications/read_all/ - mark every unread row of the caller."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        from django.utils import timezone

        marked = Notification.objects.filter(
            recipient=request.user, read_at__isnull=True
        ).update(read_at=timezone.now())
        return Response({"marked": marked})


class IntegrationStatusView(APIView):
    """GET /api/integrations/ - which external integrations are configured.

    Required environment variable names are listed; their values never leave the server.
    Unconfigured integrations are reported as such - nothing is simulated.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response({"integrations": describe_integrations()})


class FeaturesView(APIView):
    """GET /api/features/ - requirement -> capability -> code -> test traceability."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response({"summary": SUMMARY, "features": FEATURES})
'''
    return header + "\n\n" + views + ops


def _resource_view(r: ResourceSpec) -> str:
    search = ", ".join(f'"{f}"' for f in r.search_fields)
    ordering = ", ".join(f'"{f}"' for f in r.ordering_fields)
    actions = f'''

    @action(detail=True, methods=["post"], url_path="transition")
    def transition(self, request, pk=None):
        """Move the record along the lifecycle (draft -> active -> archived)."""
        instance = self.get_object()
        serializer = TransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = services.transition_status(
            instance=instance,
            resource="{r.route}",
            rid="{r.rid}",
            target_status=serializer.validated_data["status"],
            actor=request.user,
        )
        return Response(self.get_serializer(updated).data)

    @action(detail=True, methods=["get"], url_path="history")
    def history(self, request, pk=None):
        """Every lifecycle transition of this record, newest first."""
        instance = self.get_object()
        events = StatusEvent.objects.filter(
            resource="{r.route}", object_id=instance.pk
        ).select_related("actor")
        return Response(StatusEventSerializer(events, many=True).data)
'''
    if "payments" in r.capabilities:
        actions += f'''
    @action(detail=True, methods=["post"], url_path="checkout")
    def checkout(self, request, pk=None):
        """Ask the configured payment provider. 503 while it is unconfigured."""
        instance = self.get_object()
        result = services.request_checkout(
            instance=instance, resource="{r.route}", rid="{r.rid}", actor=request.user
        )
        return Response(
            {{"record": self.get_serializer(instance).data, "provider": result["provider"],
              "provider_status": result["provider_status"], "payload": result["payload"]}}
        )
'''
    return f'''class {r.class_name}ViewSet(viewsets.ModelViewSet):
    """CRUD for {r.class_name} ({r.rid}: {r.title}).

    Search with ``?search=``, order with ``?ordering=``, filter with
    ``?created_after=`` / ``?created_before=`` / ``?status=``, paginate with ``?page=``.
    """

    serializer_class = {r.class_name}Serializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrRole]
    parser_classes = [parsers.JSONParser, parsers.MultiPartParser, parsers.FormParser]
    filter_backends = [SearchFilter, OrderingFilter, DateRangeFilter, StatusFilter]
    search_fields = [{search}]
    ordering_fields = [{ordering}]
    ordering = ["-created_at"]

    def get_queryset(self):
        queryset = {r.class_name}.objects.select_related("owner")
        return _visible_to(self.request.user, queryset)

    def perform_create(self, serializer):
        services.create_{r.route}(owner=self.request.user, serializer=serializer)

    def perform_update(self, serializer):
        services.update_{r.route}(
            instance=serializer.instance, serializer=serializer, actor=self.request.user
        )

    def perform_destroy(self, instance):
        services.delete_{r.route}(instance=instance, actor=self.request.user)
{actions}'''


def urls_py(resources: list[ResourceSpec]) -> str:
    imports = "\n".join(f"from .views import {r.class_name}ViewSet" for r in resources)
    operational = (
        "from .views import (\n"
        "    AnalyticsSummaryView,\n"
        "    FeaturesView,\n"
        "    IntegrationStatusView,\n"
        "    MarkAllReadView,\n"
        "    MarkReadView,\n"
        "    NotificationListView,\n"
        "    UnreadCountView,\n"
        ")\n"
    )
    registrations = "\n".join(
        f'router.register(r"{r.route}", {r.class_name}ViewSet, basename="{r.route}")'
        for r in resources
    )
    return f'''from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from .auth_views import LoginView, LogoutView, MeView, RegisterView, UserViewSet
{imports}
{operational}
router = DefaultRouter()
{registrations}
router.register(r"users", UserViewSet, basename="user")

urlpatterns = [
    path("api/auth/register/", RegisterView.as_view(), name="auth-register"),
    path("api/auth/token/", LoginView.as_view(), name="auth-token"),
    path("api/auth/token/refresh/", TokenRefreshView.as_view(), name="auth-token-refresh"),
    path("api/auth/logout/", LogoutView.as_view(), name="auth-logout"),
    path("api/auth/me/", MeView.as_view(), name="auth-me"),
    path("api/analytics/summary/", AnalyticsSummaryView.as_view(), name="analytics-summary"),
    path("api/notifications/", NotificationListView.as_view(), name="notification-list"),
    path("api/notifications/unread_count/", UnreadCountView.as_view(), name="notification-unread"),
    path("api/notifications/read_all/", MarkAllReadView.as_view(), name="notification-read-all"),
    path("api/notifications/<int:pk>/read/", MarkReadView.as_view(), name="notification-read"),
    path("api/integrations/", IntegrationStatusView.as_view(), name="integration-status"),
    path("api/features/", FeaturesView.as_view(), name="feature-matrix"),
    path("api/", include(router.urls)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
'''


def config_py() -> str:
    return '''"""Database configuration validated with pydantic at process start.

    GENERATED_DB_ENGINE=sqlite (default) | mysql
    MYSQL_DATABASE, MYSQL_USER, MYSQL_HOST, MYSQL_PORT
    SQLITE_PATH (defaults to ./generated_app.sqlite3)
    The MySQL password is read from the MYSQL_PASSWORD environment variable only.
"""
import os
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, field_validator


class DatabaseConfig(BaseModel):
    engine: Literal["sqlite", "mysql"] = "sqlite"
    name: str = Field(min_length=1, max_length=128)
    user: str = "root"
    password: str = ""
    host: str = "127.0.0.1"
    port: int = 3306

    @field_validator("port")
    @classmethod
    def _port_in_range(cls, value: int) -> int:
        if not 1 <= value <= 65535:
            raise ValueError("port must be between 1 and 65535")
        return value

    def as_django(self) -> dict:
        if self.engine == "mysql":
            import pymysql

            pymysql.install_as_MySQLdb()
            return {
                "ENGINE": "django.db.backends.mysql",
                "NAME": self.name,
                "USER": self.user,
                "PASSWORD": self.password,
                "HOST": self.host,
                "PORT": str(self.port),
                "OPTIONS": {
                    "charset": "utf8mb4",
                    "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
                },
            }
        return {"ENGINE": "django.db.backends.sqlite3", "NAME": self.name}


def read_database_config(env=None) -> DatabaseConfig:
    env = os.environ if env is None else env
    engine = (env.get("GENERATED_DB_ENGINE") or "sqlite").strip().lower()
    try:
        return DatabaseConfig(
            engine=engine,
            name=(
                (env.get("MYSQL_DATABASE") or "generated_app")
                if engine == "mysql"
                else (env.get("SQLITE_PATH") or "generated_app.sqlite3")
            ),
            user=env.get("MYSQL_USER") or "root",
            password=env.get("MYSQL_PASSWORD") or "",
            host=env.get("MYSQL_HOST") or "127.0.0.1",
            port=int(env.get("MYSQL_PORT") or 3306),
        )
    except (ValidationError, ValueError) as exc:
        raise RuntimeError(f"invalid database configuration: {exc}") from exc


def get_database_config() -> dict:
    return read_database_config().as_django()
'''


def settings_py() -> str:
    return '''"""Settings for the app generated by SpecForge AI.

Database selection is validated by backendapp/config.py:
    GENERATED_DB_ENGINE=sqlite (default) | mysql
    MYSQL_DATABASE, MYSQL_USER, MYSQL_HOST, MYSQL_PORT, MYSQL_PASSWORD
"""
import os
from datetime import timedelta
from pathlib import Path

from backendapp.config import get_database_config

BASE_DIR = Path(__file__).resolve().parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "generated-harness-only")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = [
    h for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",") if h
]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "backendapp",
]

MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "backendapp.middleware.RequestIDMiddleware",
]

DATABASES = {"default": get_database_config()}

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

ROOT_URLCONF = "backendapp.urls"
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_PAGINATION_CLASS": "backendapp.pagination.StandardPagination",
    "PAGE_SIZE": 20,
    "EXCEPTION_HANDLER": "backendapp.exceptions.api_exception_handler",
    "TEST_RUNNER": "django.test.runner.DiscoverRunner",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"json": {"format": "%(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "json"}},
    "loggers": {
        "backendapp": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}
'''


def manage_py() -> str:
    return '''#!/usr/bin/env python
import os
import sys


def main():
    os.environ["DJANGO_SETTINGS_MODULE"] = "settings"
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
'''


def requirements_txt() -> str:
    return '''Django>=5.0,<6.0
djangorestframework>=3.15
djangorestframework-simplejwt>=5.3
PyMySQL>=1.1
pydantic>=2.6
'''


def integrations_py() -> str:
    return '''"""External integration configuration.

Every value is read from the environment. Nothing is simulated: an
unconfigured integration raises 503 ``integration_not_configured`` before a
single request is made, and ``ProviderEvent`` is written only from a real
provider answer.
"""
import json
import os
import urllib.error
import urllib.request

from .exceptions import ServiceError
from .models import ProviderEvent

INTEGRATIONS = {
    "payments": {
        "label": "Payment provider",
        "url_env": "PAYMENT_PROVIDER_URL",
        "key_env": "PAYMENT_API_KEY",
    },
    "external_api": {
        "label": "External API",
        "url_env": "EXTERNAL_API_URL",
        "key_env": "EXTERNAL_API_KEY",
    },
}


def describe_integrations():
    """Configured flag and required variable names per integration (never values)."""
    rows = []
    for name, config in INTEGRATIONS.items():
        required = [config["url_env"], config["key_env"]]
        missing = [env for env in required if not os.environ.get(env, "").strip()]
        rows.append(
            {
                "name": name,
                "label": config["label"],
                "configured": not missing,
                "env": required,
                "missing": missing,
            }
        )
    return rows


def request_payment(*, action, resource, rid, object_id, payload, actor):
    """POST to the configured payment provider and record its real answer."""
    config = INTEGRATIONS["payments"]
    url = os.environ.get(config["url_env"], "").strip()
    key = os.environ.get(config["key_env"], "").strip()
    if not url or not key:
        raise ServiceError(
            "integration_not_configured",
            "Payments are not configured; no payment was attempted.",
            {"integration": "payments", "env": [config["url_env"], config["key_env"]]},
            status_code=503,
        )
    body = json.dumps(
        {"action": action, "resource": resource, "rid": rid, "object_id": object_id, **payload}
    ).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            http_status = response.status
            raw = response.read() or b"{}"
    except urllib.error.HTTPError as exc:
        detail = (exc.read() or b"")[:500].decode("utf-8", "replace")
        ProviderEvent.objects.create(
            provider="payments", action=action, resource=resource, object_id=object_id,
            http_status=exc.code, status="failed", detail=detail, actor=actor,
        )
        raise ServiceError(
            "provider_error",
            f"The payment provider answered {exc.code}; nothing was charged.",
            {"http_status": exc.code},
            status_code=502,
        ) from exc
    except urllib.error.URLError as exc:
        ProviderEvent.objects.create(
            provider="payments", action=action, resource=resource, object_id=object_id,
            http_status=None, status="failed", detail=str(exc.reason)[:500], actor=actor,
        )
        raise ServiceError(
            "provider_unreachable",
            "The payment provider could not be reached; nothing was charged.",
            {"reason": str(exc.reason)},
            status_code=502,
        ) from exc
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (ValueError, AttributeError):
        parsed = {"raw": str(raw)[:500]}
    succeeded = 200 <= http_status < 300
    ProviderEvent.objects.create(
        provider="payments", action=action, resource=resource, object_id=object_id,
        http_status=http_status, status="succeeded" if succeeded else "failed",
        detail=json.dumps(parsed)[:500], actor=actor,
    )
    if not succeeded:
        raise ServiceError(
            "provider_error",
            f"The payment provider answered {http_status}; nothing was charged.",
            {"http_status": http_status},
            status_code=502,
        )
    return {"provider": "payments", "provider_status": http_status, "payload": parsed}
'''


def features_py(features: list[dict], summary: dict) -> str:
    return f'''"""Generated business-logic matrix (Phase 8).

Each entry maps one approved functional requirement to the capabilities that
back it, the service functions and tables it writes, and the tests that cover
it. ``status`` is ``implemented`` or ``configuration_required`` (with a written
reason) - no requirement is listed without one of the two.
"""
import json

FEATURES = json.loads({json.dumps(json.dumps(features))})
SUMMARY = json.loads({json.dumps(json.dumps(summary))})
'''


def env_example() -> str:
    # The MySQL password is deliberately absent: it is read from the
    # environment (or the Vault) and must never be committed.
    return '''# Generated app configuration (copy to .env or export in the shell).
# The MySQL password comes from the MYSQL_PASSWORD environment variable only.
DJANGO_SECRET_KEY=change-me
DJANGO_DEBUG=1
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

# sqlite (default) | mysql
GENERATED_DB_ENGINE=sqlite
# SQLITE_PATH=generated_app.sqlite3

# Used when GENERATED_DB_ENGINE=mysql
MYSQL_DATABASE=generated_app
MYSQL_USER=root
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306

# External integrations. Leave empty to keep them disabled: calls then return
# 503 integration_not_configured and no transaction is simulated.
# PAYMENT_PROVIDER_URL=
# PAYMENT_API_KEY=
# EXTERNAL_API_URL=
# EXTERNAL_API_KEY=
'''


def tests_py(resources: list[ResourceSpec]) -> str:
    blocks = [_resource_tests(r) for r in resources]
    blocks.append(_auth_tests())
    blocks.append(_role_tests(resources[0]))
    blocks.append(_analytics_tests(resources))
    blocks.append(_feature_matrix_tests(resources))
    blocks.append(_integration_status_tests())
    for r in resources:
        if "payments" in r.capabilities:
            blocks.append(_payment_tests(r))
    return test_header(resources) + "\n\n" + "\n\n".join(blocks)


def test_header(resources: list[ResourceSpec]) -> str:
    imports = "\n".join(f"from .models import {r.class_name}" for r in resources)
    return f'''import os
import urllib.error
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from rest_framework import test

from .models import Notification, ProviderEvent, Role, StatusEvent, UserProfile
{imports}
from .roles import ensure_default_roles
'''


def _resource_tests(r: ResourceSpec) -> str:
    return f'''@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class {r.class_name}APITests(test.APITestCase):
    """{r.rid} - {r.title}: CRUD, permissions, search, uploads, errors."""

    def setUp(self):
        ensure_default_roles()
        self.user = get_user_model().objects.create_user(
            username="owner_{r.route}", email="owner@example.com", password="strong-pass-123"
        )
        self.client.force_authenticate(self.user)
        self.list_url = reverse("{r.route}-list")

    def _create(self, name="Sample", **extra):
        payload = {{"name": name, "description": "d"}}
        payload.update(extra)
        return self.client.post(self.list_url, payload, format="json")

    def test_unauthenticated_access_is_denied(self):
        anon = test.APIClient()
        res = anon.get(self.list_url)
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.data["error"]["code"], "not_authenticated")

    def test_owner_can_create_and_retrieve(self):
        res = self._create()
        self.assertEqual(res.status_code, 201, res.data)
        res = self.client.get(self.list_url)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data["results"]), 1)

    def test_owner_can_update_and_delete(self):
        self._create()
        obj = {r.class_name}.objects.get()
        detail_url = reverse("{r.route}-detail", args=[obj.pk])
        self.assertEqual(
            self.client.patch(detail_url, {{"name": "Changed"}}, format="json").status_code, 200
        )
        self.assertEqual(self.client.delete(detail_url).status_code, 204)

    def test_other_user_cannot_see_object(self):
        self._create()
        obj = {r.class_name}.objects.get()
        other = get_user_model().objects.create_user(
            username="other_{r.route}", email="other@example.com", password="strong-pass-123"
        )
        self.client.force_authenticate(other)
        detail_url = reverse("{r.route}-detail", args=[obj.pk])
        self.assertIn(self.client.get(detail_url).status_code, (403, 404))

    def test_duplicate_name_is_a_409_conflict(self):
        self.assertEqual(self._create(name="Same").status_code, 201)
        res = self._create(name="Same")
        self.assertEqual(res.status_code, 409, res.data)
        self.assertEqual(res.data["error"]["code"], "duplicate_name")

    def test_search_and_ordering(self):
        self.assertEqual(self._create(name="Alpha").status_code, 201)
        self.assertEqual(self._create(name="Beta").status_code, 201)
        res = self.client.get(self.list_url, {{"search": "Beta"}})
        self.assertEqual(res.data["count"], 1)
        self.assertEqual(res.data["results"][0]["name"], "Beta")
        res = self.client.get(self.list_url, {{"ordering": "name"}})
        self.assertEqual([row["name"] for row in res.data["results"]], ["Alpha", "Beta"])

    def test_attachment_upload_and_type_validation(self):
        upload = SimpleUploadedFile("notes.txt", b"hello", content_type="text/plain")
        res = self.client.post(
            self.list_url,
            {{"name": "With file", "description": "x", "attachment": upload}},
            format="multipart",
        )
        self.assertEqual(res.status_code, 201, res.data)
        self.assertTrue(res.data["attachment_url"])

        bad = SimpleUploadedFile("evil.exe", b"x", content_type="application/octet-stream")
        res = self.client.post(
            self.list_url, {{"name": "Bad file", "attachment": bad}}, format="multipart"
        )
        self.assertEqual(res.status_code, 400, res.data)
        self.assertEqual(res.data["error"]["code"], "unsupported_attachment")

    def test_validation_error_uses_error_envelope(self):
        res = self.client.post(self.list_url, {{"description": "no name"}}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data["error"]["code"], "validation_error")
        self.assertIn("name", res.data["error"]["details"])

    def test_response_carries_request_id(self):
        res = self.client.get(self.list_url, HTTP_X_REQUEST_ID="trace-123")
        self.assertEqual(res["X-Request-ID"], "trace-123")

    def test_status_transitions_follow_the_workflow(self):
        self._create(name="Workflow record")
        obj = {r.class_name}.objects.get()
        url = reverse("{r.route}-transition", args=[obj.pk])

        res = self.client.post(url, {{"status": "archived"}}, format="json")
        self.assertEqual(res.status_code, 400, res.data)
        self.assertEqual(res.data["error"]["code"], "invalid_transition")
        self.assertEqual(res.data["error"]["details"]["allowed"], ["active"])

        res = self.client.post(url, {{"status": "active"}}, format="json")
        self.assertEqual(res.status_code, 200, res.data)
        obj.refresh_from_db()
        self.assertEqual(obj.status, "active")

        res = self.client.post(url, {{"status": "nonsense"}}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data["error"]["code"], "validation_error")
        self.assertEqual(
            StatusEvent.objects.filter(resource="{r.route}", object_id=obj.pk).count(), 1
        )

    def test_history_records_every_transition(self):
        self._create(name="History record")
        obj = {r.class_name}.objects.get()
        url = reverse("{r.route}-transition", args=[obj.pk])
        self.assertEqual(
            self.client.post(url, {{"status": "active"}}, format="json").status_code, 200
        )
        self.assertEqual(
            self.client.post(url, {{"status": "draft"}}, format="json").status_code, 200
        )
        res = self.client.get(reverse("{r.route}-history", args=[obj.pk]))
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(len(res.data), 2)
        self.assertEqual(res.data[0]["from_status"], "active")
        self.assertEqual(res.data[0]["to_status"], "draft")
        self.assertEqual(res.data[0]["actor_username"], self.user.username)

    def test_date_range_and_status_filter(self):
        self.assertEqual(self._create(name="Filtered").status_code, 201)
        res = self.client.get(self.list_url, {{"created_after": "2999-01-01"}})
        self.assertEqual(res.data["count"], 0)
        res = self.client.get(self.list_url, {{"created_before": "2999-01-01"}})
        self.assertEqual(res.data["count"], 1)
        res = self.client.get(self.list_url, {{"status": "draft"}})
        self.assertEqual(res.data["count"], 1)
        res = self.client.get(self.list_url, {{"status": "archived"}})
        self.assertEqual(res.data["count"], 0)
        res = self.client.get(self.list_url, {{"status": "nonsense"}})
        self.assertEqual(res.status_code, 400)

    def test_owner_is_notified_on_create(self):
        self.assertEqual(self._create(name="Notify me").status_code, 201)
        notifications = Notification.objects.filter(recipient=self.user)
        self.assertEqual(notifications.count(), 1)
        self.assertEqual(notifications.first().kind, "record_created")
        self.assertEqual(notifications.first().rid, "{r.rid}")

    def test_notifications_are_private_to_the_recipient(self):
        self.assertEqual(self._create(name="Private").status_code, 201)
        other = get_user_model().objects.create_user(
            username="outsider_{r.route}", email="outsider@example.com", password="strong-pass-123"
        )
        notification = Notification.objects.get(recipient=self.user)
        self.client.force_authenticate(other)
        self.assertEqual(self.client.get("/api/notifications/").data, [])
        self.assertEqual(self.client.get("/api/notifications/unread_count/").data["unread"], 0)
        self.assertEqual(
            self.client.post(f"/api/notifications/{{notification.pk}}/read/").status_code, 404
        )

        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get("/api/notifications/unread_count/").data["unread"], 1)
        res = self.client.post(f"/api/notifications/{{notification.pk}}/read/")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertTrue(res.data["read"])
        self.assertEqual(self.client.get("/api/notifications/unread_count/").data["unread"], 0)
        res = self.client.post("/api/notifications/read_all/")
        self.assertEqual(res.status_code, 200)
'''


def _auth_tests() -> str:
    return '''@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class AuthFlowTests(test.APITestCase):
    """JWT register / login / refresh / me / logout against the real endpoints."""

    def test_register_login_refresh_me_and_logout(self):
        res = self.client.post(
            "/api/auth/register/",
            {"username": "alice", "email": "alice@example.com", "password": "strong-pass-123"},
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.data)
        self.assertIn("access", res.data)
        self.assertIn("refresh", res.data)
        self.assertEqual(res.data["user"]["role"]["name"], "user")

        self.client.credentials()
        res = self.client.post(
            "/api/auth/token/",
            {"username": "alice", "password": "strong-pass-123"},
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.data)
        access, refresh = res.data["access"], res.data["refresh"]

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        res = self.client.get("/api/auth/me/")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["username"], "alice")
        self.assertEqual(res.data["role"]["name"], "user")

        self.client.credentials()
        res = self.client.post("/api/auth/token/refresh/", {"refresh": refresh}, format="json")
        self.assertEqual(res.status_code, 200, res.data)
        rotated = res.data.get("refresh", refresh)

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        res = self.client.post("/api/auth/logout/", {"refresh": rotated}, format="json")
        self.assertEqual(res.status_code, 204, res.data)

        self.client.credentials()
        res = self.client.post("/api/auth/token/refresh/", {"refresh": rotated}, format="json")
        self.assertEqual(res.status_code, 401, res.data)

    def test_login_with_bad_password_is_401_with_error_envelope(self):
        get_user_model().objects.create_user(username="bob", password="strong-pass-123")
        res = self.client.post(
            "/api/auth/token/", {"username": "bob", "password": "wrong-pass"}, format="json"
        )
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.data["error"]["code"], "invalid_credentials")

    def test_register_rejects_duplicate_username(self):
        payload = {"username": "carol", "email": "carol@example.com", "password": "strong-pass-123"}
        self.assertEqual(
            self.client.post("/api/auth/register/", payload, format="json").status_code, 201
        )
        res = self.client.post("/api/auth/register/", payload, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("username", res.data["error"]["details"])
'''


def _role_tests(r: ResourceSpec) -> str:
    return f'''@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class RoleBasedAccessTests(test.APITestCase):
    """Configurable roles change what a caller may read, edit and administer."""

    def setUp(self):
        ensure_default_roles()
        self.owner = get_user_model().objects.create_user(
            username="admin_user", email="admin@example.com", password="strong-pass-123"
        )
        self.member = get_user_model().objects.create_user(
            username="member_user", email="member@example.com", password="strong-pass-123"
        )
        self.record = {r.class_name}.objects.create(owner=self.member, name="Member record")

    def _set_role(self, user, role_name):
        UserProfile.objects.filter(user=user).update(role=Role.objects.get(name=role_name))

    def test_standard_user_only_sees_own_records(self):
        self.client.force_authenticate(self.owner)
        res = self.client.get(reverse("{r.route}-list"))
        self.assertEqual(res.data["count"], 0)

    def test_admin_role_sees_and_edits_others_records(self):
        self._set_role(self.owner, "admin")
        self.client.force_authenticate(self.owner)
        res = self.client.get(reverse("{r.route}-list"))
        self.assertEqual(res.data["count"], 1)
        detail = reverse("{r.route}-detail", args=[self.record.pk])
        res = self.client.patch(detail, {{"name": "Renamed by admin"}}, format="json")
        self.assertEqual(res.status_code, 200, res.data)
        self.record.refresh_from_db()
        self.assertEqual(self.record.name, "Renamed by admin")

    def test_admin_can_assign_roles_but_standard_user_cannot(self):
        self.client.force_authenticate(self.member)
        res = self.client.get("/api/users/")
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.data["error"]["code"], "permission_denied")

        self._set_role(self.owner, "admin")
        self.client.force_authenticate(self.owner)
        res = self.client.patch(
            f"/api/users/{{self.member.pk}}/role/", {{"role": "manager"}}, format="json"
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["role"]["name"], "manager")

    def test_unknown_role_is_rejected(self):
        self._set_role(self.owner, "admin")
        self.client.force_authenticate(self.owner)
        res = self.client.patch(
            f"/api/users/{{self.member.pk}}/role/", {{"role": "wizard"}}, format="json"
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data["error"]["code"], "unknown_role")
'''


def _analytics_tests(resources: list[ResourceSpec]) -> str:
    creates = "\n".join(
        f'        {r.class_name}.objects.create(owner=self.user, name="{r.class_name} row")'
        for r in resources
    )
    checks = "\n".join(
        f'        self.assertEqual(by_resource["{r.route}"]["total"], '
        f'{r.class_name}.objects.filter(owner=self.user).count())'
        for r in resources
    )
    routes = ", ".join(f'"{r.route}"' for r in resources)
    return f'''@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class AnalyticsSummaryTests(test.APITestCase):
    """Dashboard analytics are aggregates of the real rows, not placeholders."""

    def setUp(self):
        ensure_default_roles()
        self.user = get_user_model().objects.create_user(
            username="analytics_user", email="analytics@example.com", password="strong-pass-123"
        )
        self.client.force_authenticate(self.user)

    def test_analytics_summary_matches_database(self):
{creates}
        res = self.client.get("/api/analytics/summary/")
        self.assertEqual(res.status_code, 200, res.data)
        by_resource = {{row["resource"]: row for row in res.data["resources"]}}
        self.assertEqual(sorted(by_resource), sorted([{routes}]))
{checks}
        self.assertEqual(res.data["totals"]["mine"], len(by_resource))
        self.assertEqual(res.data["totals"]["total"], len(by_resource))
        first = by_resource["{resources[0].route}"]
        self.assertEqual(first["by_status"]["draft"], 1)
        self.assertEqual(first["created_last_7_days"], 1)
'''


def _feature_matrix_tests(resources: list[ResourceSpec]) -> str:
    rids = ", ".join(f'"{r.rid}"' for r in resources)
    return f'''class FeatureMatrixTests(test.APITestCase):
    """Every approved requirement is traceable to code and tests, or says why not."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="feature_user", email="features@example.com", password="strong-pass-123"
        )
        self.client.force_authenticate(self.user)

    def test_features_endpoint_covers_every_requirement(self):
        res = self.client.get("/api/features/")
        self.assertEqual(res.status_code, 200, res.data)
        features = res.data["features"]
        self.assertEqual(sorted(feature["rid"] for feature in features), sorted([{rids}]))
        for feature in features:
            self.assertIn(feature["status"], ("implemented", "configuration_required"))
            self.assertTrue(feature["endpoints"])
            self.assertTrue(feature["tests"])
            self.assertTrue(feature["service"])
            if feature["status"] == "configuration_required":
                self.assertTrue(feature["reason"])
        self.assertEqual(res.data["summary"]["total"], len(features))
'''


def _integration_status_tests() -> str:
    return '''class IntegrationConfigurationTests(test.APITestCase):
    """Unconfigured integrations are reported, never simulated as working."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="integration_user", email="integrations@example.com", password="strong-pass-123"
        )
        self.client.force_authenticate(self.user)

    def test_integration_status_lists_required_environment(self):
        res = self.client.get("/api/integrations/")
        self.assertEqual(res.status_code, 200, res.data)
        rows = {row["name"]: row for row in res.data["integrations"]}
        self.assertIn("payments", rows)
        self.assertIn("external_api", rows)
        for row in rows.values():
            self.assertIn("configured", row)
            self.assertTrue(row["env"])
            self.assertNotIn("value", row)
        self.assertEqual(rows["payments"]["env"], ["PAYMENT_PROVIDER_URL", "PAYMENT_API_KEY"])
        self.assertEqual(rows["external_api"]["env"], ["EXTERNAL_API_URL", "EXTERNAL_API_KEY"])
'''


def _payment_tests(r: ResourceSpec) -> str:
    return f'''@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class PaymentCheckoutTests(test.APITestCase):
    """{r.rid}: checkout is a real provider call, never a simulated success."""

    def setUp(self):
        ensure_default_roles()
        self.user = get_user_model().objects.create_user(
            username="payer_{r.route}", email="payer@example.com", password="strong-pass-123"
        )
        self.client.force_authenticate(self.user)
        self.record = {r.class_name}.objects.create(owner=self.user, name="Payable")
        self.url = reverse("{r.route}-checkout", args=[self.record.pk])

    def test_checkout_without_configuration_is_503(self):
        environment = {{
            key: value
            for key, value in os.environ.items()
            if key not in ("PAYMENT_PROVIDER_URL", "PAYMENT_API_KEY")
        }}
        with mock.patch.dict(os.environ, environment, clear=True):
            res = self.client.post(self.url, {{}}, format="json")
        self.assertEqual(res.status_code, 503, res.data)
        self.assertEqual(res.data["error"]["code"], "integration_not_configured")
        self.assertEqual(res.data["error"]["details"]["integration"], "payments")
        self.assertEqual(ProviderEvent.objects.count(), 0)

    def test_checkout_provider_failure_is_recorded(self):
        environment = {{
            "PAYMENT_PROVIDER_URL": "https://payments.invalid/checkout",
            "PAYMENT_API_KEY": "test-key",
        }}
        with mock.patch.dict(os.environ, environment):
            with mock.patch(
                "backendapp.integrations.urllib.request.urlopen",
                side_effect=urllib.error.URLError("provider down"),
            ):
                res = self.client.post(self.url, {{}}, format="json")
        self.assertEqual(res.status_code, 502, res.data)
        self.assertEqual(res.data["error"]["code"], "provider_unreachable")
        self.assertEqual(ProviderEvent.objects.filter(status="succeeded").count(), 0)
        event = ProviderEvent.objects.get()
        self.assertEqual(event.status, "failed")
        self.assertEqual(event.object_id, self.record.pk)
'''


def docs_md(
    project_name: str,
    resources: list[ResourceSpec],
    databases_tested: list[str],
    features: list[dict] | None = None,
    summary: dict | None = None,
) -> str:
    features = features or []
    summary = summary or {}
    lines = [
        f"# {project_name} - Generated Backend API",
        "",
        f"Generated from {len(resources)} approved functional requirement(s) by SpecForge AI "
        "(Phase 4 - Backend Development Engine). Django REST Framework, JWT auth, "
        "role-based access, MySQL or SQLite.",
        "",
        "## Base URL",
        "",
        "`http://localhost:8000`",
        "",
        "Every response carries an `X-Request-ID` header; send your own `X-Request-ID` to "
        "correlate logs.",
        "",
        "## Authentication and role management",
        "",
        "All endpoints except `register`, `token` and `token/refresh` require "
        "`Authorization: Bearer <access>`.",
        "",
        "| Method | Path | Auth | Permission | Success | Errors |",
        "| --- | --- | --- | --- | --- | --- |",
        "| POST | `/api/auth/register/` | none | public | 201 | 400 validation_error |",
        "| POST | `/api/auth/token/` | none | public | 200 | 400, 401 invalid_credentials |",
        "| POST | `/api/auth/token/refresh/` | none | public | 200 | 401 |",
        "| POST | `/api/auth/logout/` | JWT | authenticated | 204 | 400 invalid_refresh_token, 401 |",
        "| GET | `/api/auth/me/` | JWT | authenticated | 200 | 401 |",
        "| GET | `/api/users/` | JWT | role.can_manage_users | 200 | 401, 403 permission_denied |",
        "| GET | `/api/users/{id}/` | JWT | role.can_manage_users | 200 | 401, 403, 404 |",
        "| PATCH | `/api/users/{id}/role/` | JWT | role.can_manage_users | 200 | 400 unknown_role, 401, 403, 404 |",
        "",
        "### Operational endpoints",
        "",
        "| Method | Path | Auth | Success | Errors |",
        "| --- | --- | --- | --- | --- |",
        "| GET | `/api/analytics/summary/` | JWT | 200 aggregate counts | 401 |",
        "| GET | `/api/notifications/` | JWT | 200 own inbox (`?unread=true`) | 401 |",
        "| GET | `/api/notifications/unread_count/` | JWT | 200 `{\"unread\": n}` | 401 |",
        "| POST | `/api/notifications/{id}/read/` | JWT | 200 marked row | 401, 404 |",
        "| POST | `/api/notifications/read_all/` | JWT | 200 `{\"marked\": n}` | 401 |",
        "| GET | `/api/integrations/` | JWT | 200 configured flags + env names | 401 |",
        "| GET | `/api/features/` | JWT | 200 requirement -> code -> test matrix | 401 |",
        "",
        "### Register",
        "",
        "Request body:",
        "",
        "| Field | Type | Required | Notes |",
        "| --- | --- | --- | --- |",
        "| `username` | string | yes | max 150, unique (case-insensitive) |",
        "| `email` | string | yes | valid email, unique (case-insensitive) |",
        "| `password` | string | yes | 8-128 characters |",
        "",
        "Response `201`:",
        "",
        "```json",
        "{",
        '  "user": {"id": 2, "username": "alice", "email": "alice@example.com",',
        '           "is_active": true, "date_joined": "2026-01-01T10:00:00Z",',
        '           "role": {"id": 3, "name": "user", "can_view_all": false,',
        '                    "can_edit_others": false, "can_manage_users": false}},',
        '  "refresh": "<token>",',
        '  "access": "<token>"',
        "}",
        "```",
        "",
        "### Login (`token`)",
        "",
        "Request body: `username` (string, required), `password` (string, required). "
        "Response `200`: same shape as register (user + refresh + access). Access tokens "
        "live 30 minutes; refresh tokens 1 day and rotate on use.",
        "",
        "### Refresh (`token/refresh`)",
        "",
        "Request body: `refresh` (string, required). Response `200`: `{access, refresh}` "
        "(rotation is on, the previous refresh token is blacklisted).",
        "",
        "### Logout",
        "",
        "Request body: `refresh` (string, required). Response `204`; the token is blacklisted.",
        "",
        "### Me",
        "",
        "Response `200`: the user object shown above (without tokens).",
        "",
        "### Assign a role",
        "",
        "Request body: `role` (string, required - one of the role names below). "
        "Response `200`: the updated user with its new role. An admin cannot demote "
        "themselves (`400 self_lockout`).",
        "",
        "## Roles",
        "",
        "Roles are rows in the database (`backendapp.Role`), so new roles can be added "
        "without code changes. Three are seeded after every migrate:",
        "",
        "| Role | can_view_all | can_edit_others | can_manage_users |",
        "| --- | --- | --- | --- |",
        "| `admin` | yes | yes | yes |",
        "| `manager` | yes | yes | no |",
        "| `user` | no | no | no |",
        "",
        "Object access is `IsOwnerOrRole`: the owner always has full access; roles with "
        "`can_view_all` may read any record; roles with `can_edit_others` may also update "
        "and delete them. List endpoints return only the caller's records unless the role "
        "has `can_view_all`.",
        "",
        "## Error format",
        "",
        "Every error response uses one envelope:",
        "",
        "```json",
        "{",
        '  "error": {',
        '    "code": "validation_error",',
        '    "message": "Request validation failed.",',
        '    "details": {"name": ["This field is required."]},',
        '    "request_id": "6b1f2c..."',
        "  }",
        "}",
        "```",
        "",
        "| HTTP | `code` | When |",
        "| --- | --- | --- |",
        "| 400 | `validation_error` | invalid body, query or upload |",
        "| 400 | `unsupported_attachment`, `attachment_too_large` | file rejected by the service layer |",
        "| 400 | `invalid_credentials` | wrong username/password (401) |",
        "| 400 | `duplicate_name` | same name for the same owner (409) |",
        "| 400 | `unknown_role`, `self_lockout` | role assignment rejected |",
        "| 400 | `invalid_transition` | lifecycle move not allowed from the current status |",
        "| 400 | `invalid_status`, `no_status_change` | unknown or unchanged target status |",
        "| 502 | `provider_error`, `provider_unreachable` | configured payment provider failed; nothing charged |",
        "| 503 | `integration_not_configured` | integration credentials missing; nothing was attempted |",
        "| 401 | `not_authenticated` | missing/expired JWT |",
        "| 403 | `permission_denied` | authenticated but not allowed |",
        "| 404 | `not_found` | unknown id or not visible to the caller |",
        "| 500 | `internal_error` | unhandled server error (logged with the request id) |",
        "",
        "## Pagination, search and filtering",
        "",
        "| Query parameter | Applies to | Notes |",
        "| --- | --- | --- |",
        "| `page` | all list endpoints | 1-based page number |",
        "| `page_size` | all list endpoints | 1-100 (server cap), default 20 |",
        "| `search` | all list endpoints | case-insensitive match on name/description |",
        "| `ordering` | all list endpoints | `name`, `created_at`, `updated_at`; prefix `-` to reverse |",
        "| `created_after`, `created_before` | all list endpoints | `YYYY-MM-DD` |",
        "| `status` | all list endpoints | `draft`, `active` or `archived` |",
        "",
        "List response:",
        "",
        "```json",
        '{"count": 1, "next": null, "previous": null, "page": 1, "page_size": 20,',
        ' "results": [ ... ]}',
        "```",
        "",
        "## File uploads",
        "",
        "`POST` and `PATCH` accept `multipart/form-data` with an optional `attachment` "
        "file field (pdf, png, jpg, jpeg, txt, csv; max 5 MB). Files are stored under "
        "`MEDIA_ROOT/attachments/YYYY/MM/`; responses include `attachment` (relative URL) "
        "and `attachment_url` (absolute URL).",
        "",
        "## Database",
        "",
        "The database is chosen at process start and validated with pydantic "
        "(`backendapp/config.py`):",
        "",
        "- default: SQLite (`SQLITE_PATH`, defaults to `generated_app.sqlite3`);",
        "- MySQL/MariaDB: set `GENERATED_DB_ENGINE=mysql` plus `MYSQL_DATABASE`, "
        "`MYSQL_USER`, `MYSQL_HOST`, `MYSQL_PORT` and `MYSQL_PASSWORD` (environment only, "
        "never committed).",
        "",
        f"This build was verified by running the generated test suite on: "
        f"**{', '.join(databases_tested) or 'sqlite'}**.",
        "",
        "## Business logic per requirement",
        "",
    ]

    if features:
        lines.extend(_docs_business_logic(features, summary))

    lines.extend(["## Endpoints per requirement", ""])
    for r in resources:
        lines.extend(_docs_resource(r))

    lines.extend([
        "## Non-functional requirements",
        "",
        "- **Performance**: list queries are paginated, indexed on `(owner, created_at)`, "
        "and use `select_related` for the owner.",
        "- **Security**: JWT auth, hashed passwords, role checks on every object, upload "
        "type/size validation, transactional writes.",
        "- **Reliability**: every write runs in a transaction; duplicate names return 409; "
        "unhandled errors become a logged 500 with a request id.",
        "- **Observability**: JSON log line per request (`backendapp.request`) with request "
        "id, method, path, status and duration.",
        "- **Maintainability**: views delegate to `backendapp/services.py`; the database "
        "configuration is validated at start.",
        "",
        "## Requirement traceability",
        "",
        "| Requirement | Resource | Base path | Status | Endpoints | Permission |",
        "| --- | --- | --- | --- | --- | --- |",
    ])
    status_by_rid = {feature["rid"]: feature["status"] for feature in features}
    for r in resources:
        lines.append(
            f"| {r.rid} - {r.title} | `{r.resource}` | `/api/{r.route}/` | "
            f"{status_by_rid.get(r.rid, 'implemented')} | "
            f"{', '.join(r.endpoints)} | {r.permission} |"
        )
    lines.append("")
    return "\n".join(lines)


def _docs_business_logic(features: list[dict], summary: dict) -> list[str]:
    lines: list[str] = [
        f"{summary.get('total', len(features))} approved requirement(s): "
        f"{summary.get('implemented', 0)} fully implemented, "
        f"{summary.get('configuration_required', 0)} implemented with an integration "
        "configuration required. Every requirement below has running code and generated "
        "tests (`backendapp/tests.py`).",
        "",
    ]
    for feature in features:
        lines.extend(
            [
                f"### {feature['rid']} - {feature['title']}",
                "",
                f"Status: **{feature['status']}**. Capabilities: "
                f"{', '.join(feature['capability_labels']) or 'CRUD'}.",
                "",
                f"- Service: {', '.join(f'`{name}`' for name in feature['service'])}",
                f"- Tables: {', '.join(f'`{name}`' for name in feature['tables'])}",
                f"- Frontend: {', '.join(feature['frontend'])}",
                f"- Tests: {', '.join(f'`{name}`' for name in feature['tests'])}",
                "",
                "Business rules:",
                "",
            ]
        )
        lines.extend(f"- {rule}" for rule in feature["rules"])
        lines.append("")
        lines.append("Validation:")
        lines.append("")
        lines.extend(f"- {rule}" for rule in feature["validations"])
        lines.append("")
        if feature["reason"]:
            lines.extend([f"Documented gap: {feature['reason']}", ""])
    lines.extend(
        [
            "## External integrations",
            "",
            "Integrations are configuration, never simulated. Required environment "
            "variables (values are never returned by the API):",
            "",
            "| Integration | Environment variables | Behaviour while unconfigured |",
            "| --- | --- | --- |",
            "| payments | `PAYMENT_PROVIDER_URL`, `PAYMENT_API_KEY` | `503 "
            "integration_not_configured`, no `ProviderEvent` written |",
            "| external_api | `EXTERNAL_API_URL`, `EXTERNAL_API_KEY` | reported as "
            "unconfigured by `GET /api/integrations/` |",
            "",
            "`GET /api/integrations/` lists each integration with `configured`, the "
            "required variable names and the missing ones. A `ProviderEvent` row is only "
            "written after a real provider answer; an unreachable provider is `502` and is "
            "recorded as `failed`.",
            "",
        ]
    )
    return lines


def _docs_resource(r: ResourceSpec) -> list[str]:
    extra_rows = []
    if "workflow" in r.capabilities:
        extra_rows += [
            f"| POST | `/api/{r.route}/{{id}}/transition/` | JWT | owner, can_edit_others | 200 | 400 invalid_transition, 401, 403, 404 |",
            f"| GET | `/api/{r.route}/{{id}}/history/` | JWT | owner, can_view_all | 200 | 401, 403, 404 |",
        ]
    if "payments" in r.capabilities:
        extra_rows.append(
            f"| POST | `/api/{r.route}/{{id}}/checkout/` | JWT | owner, can_edit_others | 200 | 401, 403, 404, 502, 503 integration_not_configured |"
        )
    return [
        f"### {r.rid} - {r.title}",
        "",
        f"Resource `{r.resource}`, base path `/api/{r.route}/`, model `{r.class_name}`, "
        f"permission `{r.permission}`. Capabilities: {', '.join(r.capabilities)}.",
        "",
        "| Method | Path | Auth | Permission | Success | Errors |",
        "| --- | --- | --- | --- | --- | --- |",
        f"| GET | `/api/{r.route}/` | JWT | authenticated + role scoping | 200 | 401 |",
        f"| POST | `/api/{r.route}/` | JWT | authenticated | 201 | 400, 401, 409 duplicate_name |",
        f"| GET | `/api/{r.route}/{{id}}/` | JWT | owner, can_view_all | 200 | 401, 403, 404 |",
        f"| PATCH | `/api/{r.route}/{{id}}/` | JWT | owner, can_edit_others | 200 | 400, 401, 403, 404, 409 |",
        f"| PUT | `/api/{r.route}/{{id}}/` | JWT | owner, can_edit_others | 200 | 400, 401, 403, 404 |",
        f"| DELETE | `/api/{r.route}/{{id}}/` | JWT | owner, can_edit_others | 204 | 401, 403, 404 |",
        *extra_rows,
        "",
        "Request body (`POST` JSON or multipart; `PATCH` accepts a subset):",
        "",
        "| Field | Type | Required | Notes |",
        "| --- | --- | --- | --- |",
        "| `name` | string | yes | max 200, unique per owner |",
        "| `description` | string | no | free text |",
        "| `attachment` | file | no | pdf/png/jpg/jpeg/txt/csv, max 5 MB |",
        "",
        "`status` is read-only: change it with the transition endpoint "
        "(`draft` -> `active` -> `archived`, and back).",
        "",
        "Response `201`:",
        "",
        "```json",
        "{",
        '  "id": 1,',
        '  "name": "Sample",',
        '  "description": "d",',
        '  "attachment": null,',
        '  "attachment_url": null,',
        '  "status": "draft",',
        '  "created_at": "2026-01-01T10:00:00Z",',
        '  "updated_at": "2026-01-01T10:00:00Z"',
        "}",
        "```",
        "",
        "Error responses use the shared envelope above (e.g. `409 duplicate_name`, "
        "`400 unsupported_attachment`, `403 permission_denied`).",
        "",
    ]
