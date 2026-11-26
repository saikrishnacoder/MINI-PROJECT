from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken

from .activity import log_activity
from .models import ActivityLog

SKIP_PREFIXES = ("/api/auth/activity/",)


class ActivityLogMiddleware:
    """Records every /api/ request (with the JWT user resolved) in ActivityLog."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        path = request.path
        if not path.startswith("/api/") or request.method == "OPTIONS":
            return response
        if any(path.startswith(p) for p in SKIP_PREFIXES):
            return response

        user = self._jwt_user(request)
        log_activity(
            user,
            ActivityLog.Action.REQUEST,
            request,
            status_code=response.status_code,
        )
        return response

    def _jwt_user(self, request):
        header = request.META.get("HTTP_AUTHORIZATION", "")
        if not header.lower().startswith("bearer "):
            return getattr(request, "user", None) or None
        try:
            token = AccessToken(header[7:].strip())
            user_id = token["user_id"]
        except (TokenError, KeyError, ValueError):
            return getattr(request, "user", None) or None

        from django.contrib.auth import get_user_model

        User = get_user_model()
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
