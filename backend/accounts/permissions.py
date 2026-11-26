from rest_framework import permissions


class IsAdminRole(permissions.BasePermission):
    """Allows superusers and any user whose role is marked is_admin."""

    message = "Requires an administrator role."

    def has_permission(self, request, view):
        user = request.user
        return user.is_authenticated and user.is_admin_role


def has_permission(codename):
    """Return a DRF permission class checking the given permission codename
    against the user's (configurable) role."""

    class _RolePermission(permissions.BasePermission):
        message = f"Requires the '{codename}' permission."

        def has_permission(self, request, view):
            user = request.user
            return user.is_authenticated and codename in user.permission_codenames

    _RolePermission.__name__ = f"HasPermission_{codename}"
    _RolePermission.__qualname__ = _RolePermission.__name__
    return _RolePermission
