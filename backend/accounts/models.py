from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models


class Role(models.Model):
    """Configurable RBAC role; its permission set is editable at runtime."""

    name = models.CharField(max_length=64, unique=True)
    description = models.TextField(blank=True)
    is_admin = models.BooleanField(
        default=False,
        help_text="Admin roles manage roles, users and see all activity.",
    )
    permissions = models.ManyToManyField(
        "auth.Permission", blank=True, related_name="roles"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class User(AbstractUser):
    email = models.EmailField(unique=True)
    role = models.ForeignKey(
        Role, null=True, blank=True, on_delete=models.SET_NULL, related_name="users"
    )

    REQUIRED_FIELDS = ["email"]

    @property
    def is_admin_role(self):
        return bool(self.is_superuser or (self.role is not None and self.role.is_admin))

    @property
    def permission_codenames(self):
        if self.is_superuser:
            from django.contrib.auth.models import Permission

            return set(Permission.objects.values_list("codename", flat=True))
        if self.role is None:
            return set()
        return set(self.role.permissions.values_list("codename", flat=True))


class ActivityLog(models.Model):
    """Audit trail of authentication events and API activity."""

    class Action(models.TextChoices):
        REQUEST = "request", "API request"
        LOGIN = "login", "Login"
        LOGOUT = "logout", "Logout"
        REGISTER = "register", "Registration"
        PASSWORD_RESET_REQUEST = "password_reset_request", "Password reset requested"
        PASSWORD_RESET = "password_reset", "Password reset"
        ROLE_CHANGE = "role_change", "Role changed"
        ROLE_CHANGE_FAILED = "role_change_failed", "Role change denied"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="activity",
    )
    username = models.CharField(max_length=150, blank=True)
    action = models.CharField(max_length=32, choices=Action.choices, db_index=True)
    method = models.CharField(max_length=8, blank=True)
    path = models.CharField(max_length=255, blank=True)
    status_code = models.PositiveIntegerField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    detail = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "activity logs"

    def __str__(self):
        return f"{self.username} {self.action} {self.path}"
