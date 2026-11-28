from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.db.models import Q
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

import logging
import secrets

logger = logging.getLogger(__name__)

from .activity import log_activity
from .models import ActivityLog, Role
from .permissions import IsAdminRole
from .serializers import (
    ActivityLogSerializer,
    PasswordChangeSerializer,
    ProfileUpdateSerializer,
    RegisterSerializer,
    RoleSerializer,
    UserSerializer,
)

User = get_user_model()


def blacklist_tokens(user):
    """Revoke every outstanding refresh token for an account."""
    from rest_framework_simplejwt.token_blacklist.models import (
        BlacklistedToken, OutstandingToken,
    )

    for outstanding in OutstandingToken.objects.filter(user=user):
        BlacklistedToken.objects.get_or_create(token=outstanding)


def password_errors(password, user):
    try:
        validate_password(password, user)
    except Exception as exc:
        return getattr(exc, "messages", None) or [str(exc)]
    return []


def send_verification_email(user, request=None):
    """Issue a fresh verification token, email the link and return it."""
    user.email_verification_token = secrets.token_urlsafe(32)
    user.email_verification_sent_at = timezone.now()
    user.save(update_fields=["email_verification_token", "email_verification_sent_at"])
    verify_url = f"{settings.FRONTEND_URL}/verify-email?token={user.email_verification_token}"
    try:
        send_mail(
            "Verify your SpecForge AI email address",
            "Confirm this address to finish setting up your account:\n\n"
            f"{verify_url}\n\nIf you did not create an account, ignore this email.",
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
        )
    except Exception:  # a broken mail server must not fail registration
        logger.exception("Could not send verification email to %s", user.email)

    log_activity(user, ActivityLog.Action.EMAIL_VERIFICATION_SENT, request, user.email)
    return verify_url


class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        log_activity(user, ActivityLog.Action.REGISTER, request, "Account created")
        body = dict(UserSerializer(user).data)
        verify_url = send_verification_email(user, request)
        body["detail"] = "Account created. Check your email to verify the address."
        if settings.DEBUG:
            body["verification_url"] = verify_url
        return Response(body, status=status.HTTP_201_CREATED)


class EmailVerificationConfirmView(APIView):
    """Consume the token from the verification email and confirm the address."""

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        token = (request.data.get("token") or "").strip()
        if not token:
            return Response({"token": ["A verification token is required."]}, status=400)
        user = User.objects.filter(email_verification_token=token).first()
        if user is None:
            return Response(
                {"detail": "This verification link is invalid or has already been used."},
                status=400,
            )
        user.email_verified = True
        user.email_verification_token = ""
        user.save(update_fields=["email_verified", "email_verification_token"])
        log_activity(user, ActivityLog.Action.EMAIL_VERIFIED, request, user.email)
        return Response(
            {"detail": "Email verified. You can sign in normally.", "email": user.email}
        )


class EmailVerificationRequestView(APIView):
    """Send (or resend) the verification link for an address."""

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = (request.data.get("email") or "").strip()
        user = User.objects.filter(email__iexact=email, is_active=True).first()
        detail = "If that address needs verification, a new link has been sent."
        body = {"detail": detail}
        if user is not None and not user.email_verified:
            verify_url = send_verification_email(user, request)
            if settings.DEBUG:
                body["verification_url"] = verify_url
        elif user is not None:
            body["detail"] = "That address is already verified."
        return Response(body)


class LoginView(TokenObtainPairView):
    """Returns access + refresh tokens and logs every attempt."""

    def post(self, request, *args, **kwargs):
        user = User.objects.filter(username=request.data.get("username", "")).first()
        if (
            user is not None
            and not user.is_active
            and user.check_password(request.data.get("password", ""))
        ):
            log_activity(
                user,
                ActivityLog.Action.LOGIN,
                request,
                "Login blocked (account deactivated)",
                status_code=403,
            )
            return Response(
                {"detail": "This account has been deactivated. Contact an administrator."},
                status=403,
            )
        try:
            response = super().post(request, *args, **kwargs)
        except Exception as exc:
            log_activity(
                user,
                ActivityLog.Action.LOGIN,
                request,
                f"Login failed ({getattr(exc, 'default_detail', exc)})",
                status_code=getattr(exc, "status_code", 401),
            )
            raise
        if response.status_code < 400:
            log_activity(user, ActivityLog.Action.LOGIN, request, "Login succeeded")
        else:
            log_activity(
                user,
                ActivityLog.Action.LOGIN,
                request,
                "Login failed (bad credentials)",
                status_code=response.status_code,
            )
        return response


class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        refresh = request.data.get("refresh", "")
        if not refresh:
            return Response({"detail": "A refresh token is required."}, status=400)
        try:
            RefreshToken(refresh).blacklist()
        except TokenError:
            return Response({"detail": "Invalid or expired token."}, status=400)
        log_activity(
            request.user, ActivityLog.Action.LOGOUT, request, "Refresh token blacklisted"
        )
        return Response({"detail": "Logged out."}, status=200)


class PasswordResetView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = (request.data.get("email") or "").strip()
        user = User.objects.filter(email__iexact=email, is_active=True).first()
        detail = "If an account exists for that email, a reset link has been sent."
        if user is not None:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            reset_url = f"{settings.FRONTEND_URL}/reset-password?uid={uid}&token={token}"
            send_mail(
                "Reset your SpecForge AI password",
                f"Use this link to reset your password (valid for a short time):\n\n{reset_url}",
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
                fail_silently=True,
            )
            log_activity(user, ActivityLog.Action.PASSWORD_RESET_REQUEST, request)
            if settings.DEBUG:
                detail = f"Reset link (dev mode): {reset_url}"
        else:
            log_activity(
                None, ActivityLog.Action.PASSWORD_RESET_REQUEST, request, "Unknown email"
            )
        body = {"detail": detail}
        if user is not None and settings.DEBUG:
            body.update({"uid": uid, "token": token})
        return Response(body)


class PasswordResetConfirmView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        uid = request.data.get("uid", "")
        token = request.data.get("token", "")
        password = request.data.get("password", "")
        try:
            user = User.objects.get(pk=force_str(urlsafe_base64_decode(uid)))
        except (User.DoesNotExist, ValueError, TypeError):
            user = None

        if user is None or not default_token_generator.check_token(user, token):
            return Response(
                {"detail": "This reset link is invalid or has expired."}, status=400
            )

        try:
            validate_password(password, user)
        except Exception as exc:
            messages = getattr(exc, "messages", None) or [str(exc)]
            return Response({"password": messages}, status=400)

        user.set_password(password)
        user.save(update_fields=["password"])
        # Invalidate every outstanding refresh token for this account.
        blacklist_tokens(user)
        log_activity(
            user, ActivityLog.Action.PASSWORD_RESET, request, "Password changed via reset link"
        )
        return Response({"detail": "Password updated. Please sign in again."})


class PasswordChangeView(APIView):
    """Self-service password change for a signed-in user."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        current = serializer.validated_data["current_password"]
        new = serializer.validated_data["new_password"]
        if not request.user.check_password(current):
            return Response(
                {"current_password": ["That is not your current password."]}, status=400
            )
        if current == new:
            return Response(
                {"new_password": ["Choose a password different from the current one."]},
                status=400,
            )
        errors = password_errors(new, request.user)
        if errors:
            return Response({"new_password": errors}, status=400)
        request.user.set_password(new)
        request.user.save(update_fields=["password"])
        blacklist_tokens(request.user)
        log_activity(
            request.user, ActivityLog.Action.PASSWORD_CHANGE, request, "Password changed"
        )
        return Response({"detail": "Password updated. Please sign in again."})


class MeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)

    def patch(self, request):
        serializer = ProfileUpdateSerializer(
            request.user, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        body = dict(UserSerializer(user).data)
        if request.data.get("email") and not user.email_verified:
            body["verification_url"] = send_verification_email(user, request)
            body["detail"] = "Email updated. Verify the new address from your inbox."
        return Response(body)


class RoleViewSet(viewsets.ModelViewSet):
    """Configurable roles. Readable by any authenticated user (for pickers),
    editable only by admin roles."""

    queryset = Role.objects.prefetch_related("permissions").order_by("name")
    serializer_class = RoleSerializer

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [permissions.IsAuthenticated()]
        return [permissions.IsAuthenticated(), IsAdminRole()]

    def perform_create(self, serializer):
        role = serializer.save()
        log_activity(
            self.request.user,
            ActivityLog.Action.ROLE_CHANGE,
            self.request,
            f"Created role '{role.name}'",
        )

    def perform_update(self, serializer):
        role = serializer.save()
        log_activity(
            self.request.user,
            ActivityLog.Action.ROLE_CHANGE,
            self.request,
            f"Updated role '{role.name}'",
        )

    def perform_destroy(self, instance):
        if instance.users.filter(is_active=True).exists():
            raise ValidationError({"detail": "Reassign its users before deleting this role."})
        log_activity(
            self.request.user,
            ActivityLog.Action.ROLE_CHANGE,
            self.request,
            f"Deleted role '{instance.name}'",
        )
        instance.delete()


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    """User directory for admins: list users and assign roles."""

    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminRole]

    def get_queryset(self):
        return User.objects.select_related("role").order_by("username")

    def create(self, request, *args, **kwargs):
        return Response(
            {"detail": "Use /api/auth/register/ to create accounts."}, status=405
        )

    def update(self, request, *args, **kwargs):
        return Response({"detail": "Only role assignment is allowed here."}, status=405)

    def destroy(self, request, *args, **kwargs):
        return Response({"detail": "Only role assignment is allowed here."}, status=405)

    @action(detail=True, methods=["post"])
    def set_role(self, request, pk=None):
        target = self.get_object()
        role = Role.objects.filter(name__iexact=request.data.get("role", "")).first()
        if role is None:
            return Response({"role": ["Unknown role."]}, status=400)
        if target == request.user:
            log_activity(
                request.user,
                ActivityLog.Action.ROLE_CHANGE_FAILED,
                request,
                "Attempted to change own role",
            )
            return Response(
                {"detail": "You cannot change your own role (lock-out protection)."},
                status=400,
            )
        old = target.role.name if target.role else None
        target.role = role
        target.save(update_fields=["role"])
        log_activity(
            request.user,
            ActivityLog.Action.ROLE_CHANGE,
            request,
            f"Changed role of '{target.username}': {old or 'none'} -> {role.name}",
        )
        return Response(UserSerializer(target).data)

    @action(detail=True, methods=["post"])
    def set_status(self, request, pk=None):
        """Activate or deactivate an account. Deactivation revokes its tokens."""
        target = self.get_object()
        desired = request.data.get("is_active")
        if not isinstance(desired, bool):
            return Response({"is_active": ["Send true or false."]}, status=400)
        if target == request.user:
            return Response(
                {"detail": "You cannot deactivate your own account (lock-out protection)."},
                status=400,
            )
        if not desired and target.is_admin_role:
            other_admins = (
                User.objects.filter(is_active=True, role__is_admin=True)
                .exclude(pk=target.pk)
                .count()
            )
            if other_admins == 0:
                return Response(
                    {"detail": "At least one active administrator must remain."}, status=400
                )
        if target.is_active == desired:
            return Response(UserSerializer(target).data)

        target.is_active = desired
        target.save(update_fields=["is_active"])
        if not desired:
            blacklist_tokens(target)
        log_activity(
            request.user,
            ActivityLog.Action.ACCOUNT_STATUS,
            request,
            f"{'Activated' if desired else 'Deactivated'} account '{target.username}'",
        )
        return Response(UserSerializer(target).data)


class ActivityLogViewSet(viewsets.ReadOnlyModelViewSet):
    """Admin roles see all activity; everyone else sees their own."""

    serializer_class = ActivityLogSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = ActivityLog.objects.all()
        if not user.is_admin_role:
            qs = qs.filter(user=user)
        search = self.request.query_params.get("search", "")
        if search:
            qs = qs.filter(
                Q(username__icontains=search)
                | Q(path__icontains=search)
                | Q(detail__icontains=search)
            )
        return qs
