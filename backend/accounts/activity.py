from .models import ActivityLog


def client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip() or None
    return request.META.get("REMOTE_ADDR") or None


def log_activity(user, action, request=None, detail="", status_code=None):
    actor = user if (user is not None and getattr(user, "is_authenticated", True)) else None
    ActivityLog.objects.create(
        user=actor,
        username=getattr(actor, "username", "") or "anonymous",
        action=action,
        method=getattr(request, "method", "") if request else "",
        path=request.path[:255] if request else "",
        status_code=status_code,
        ip_address=client_ip(request) if request else None,
        detail=detail[:2000],
    )
