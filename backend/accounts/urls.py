from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from . import views

router = DefaultRouter()
router.register("roles", views.RoleViewSet, basename="role")
router.register("users", views.UserViewSet, basename="user")
router.register("activity", views.ActivityLogViewSet, basename="activity")

urlpatterns = [
    path("auth/register/", views.RegisterView.as_view(), name="register"),
    path("auth/token/", views.LoginView.as_view(), name="token_obtain_pair"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("auth/logout/", views.LogoutView.as_view(), name="logout"),
    path("auth/password-reset/", views.PasswordResetView.as_view(), name="password_reset"),
    path(
        "auth/password-reset/confirm/",
        views.PasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path(
        "auth/password-change/",
        views.PasswordChangeView.as_view(),
        name="password_change",
    ),
    path(
        "auth/email/verify/",
        views.EmailVerificationConfirmView.as_view(),
        name="email_verify",
    ),
    path(
        "auth/email/verify/request/",
        views.EmailVerificationRequestView.as_view(),
        name="email_verify_request",
    ),
    path("auth/me/", views.MeView.as_view(), name="me"),
    path("", include(router.urls)),
]
