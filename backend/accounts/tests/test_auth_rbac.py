import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from rest_framework.test import APIClient

from accounts.models import ActivityLog, Role

User = get_user_model()


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def roles(db):
    admin, _ = Role.objects.get_or_create(
        name="Admin", defaults={"is_admin": True}
    )
    manager, _ = Role.objects.get_or_create(name="Manager")
    standard, _ = Role.objects.get_or_create(name="Standard User")
    return {"Admin": admin, "Manager": manager, "Standard User": standard}


@pytest.fixture
def admin_user(db, roles):
    return User.objects.create_user(
        username="boss", email="boss@example.com", password="S3curePass!x", role=roles["Admin"]
    )


def auth(api, user, password="S3curePass!x"):
    res = api.post("/api/auth/token/", {"username": user.username, "password": password})
    assert res.status_code == 200, res.data
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {res.data['access']}")
    return res.data


# --- registration & login -------------------------------------------------

@pytest.mark.django_db
def test_register_assigns_standard_role_and_logs(api):
    res = api.post(
        "/api/auth/register/",
        {"username": "newbie", "email": "new@example.com", "password": "S3curePass!x"},
    )
    assert res.status_code == 201, res.data
    user = User.objects.get(username="newbie")
    assert user.role.name == "Standard User"
    assert ActivityLog.objects.filter(user=user, action="register").exists()


@pytest.mark.django_db
def test_login_success_and_failure_logged(api, db, admin_user):
    ok = api.post("/api/auth/token/", {"username": "boss", "password": "S3curePass!x"})
    assert ok.status_code == 200
    bad = api.post("/api/auth/token/", {"username": "boss", "password": "wrong"})
    assert bad.status_code == 401
    actions = list(
        ActivityLog.objects.filter(username="boss", action="login").values_list("detail", flat=True)
    )
    assert any("succeeded" in d for d in actions), actions
    assert any("failed" in d for d in actions), actions


# --- refresh rotation & logout --------------------------------------------

@pytest.mark.django_db
def test_refresh_rotates_and_old_refresh_is_blacklisted(api, admin_user):
    tokens = auth(api, admin_user)
    old_refresh = tokens["refresh"]
    res = api.post("/api/auth/token/refresh/", {"refresh": old_refresh})
    assert res.status_code == 200, res.data
    assert res.data["refresh"] != old_refresh
    # The old refresh token can no longer be used.
    reuse = api.post("/api/auth/token/refresh/", {"refresh": old_refresh})
    assert reuse.status_code == 401


@pytest.mark.django_db
def test_logout_blacklists_refresh_token(api, admin_user):
    tokens = auth(api, admin_user)
    res = api.post("/api/auth/logout/", {"refresh": tokens["refresh"]})
    assert res.status_code == 200, res.data
    reuse = api.post("/api/auth/token/refresh/", {"refresh": tokens["refresh"]})
    assert reuse.status_code == 401
    assert ActivityLog.objects.filter(user=admin_user, action="logout").exists()


# --- password reset -------------------------------------------------------

@pytest.mark.django_db
def test_password_reset_flow(api, admin_user, settings):
    settings.DEBUG = True
    res = api.post("/api/auth/password-reset/", {"email": admin_user.email})
    assert res.status_code == 200
    assert len(mail.outbox) == 1
    uid, token = res.data["uid"], res.data["token"]

    new = api.post(
        "/api/auth/password-reset/confirm/",
        {"uid": uid, "token": token, "password": "Br4ndNew!pass"},
    )
    assert new.status_code == 200, new.data
    assert User.objects.get(pk=admin_user.pk).check_password("Br4ndNew!pass")

    # Old password no longer works; reset event logged.
    assert api.post("/api/auth/token/", {"username": "boss", "password": "S3curePass!x"}).status_code == 401
    assert ActivityLog.objects.filter(user=admin_user, action="password_reset").exists()


@pytest.mark.django_db
def test_password_reset_unknown_email_never_leaks(api, db):
    res = api.post("/api/auth/password-reset/", {"email": "ghost@example.com"})
    assert res.status_code == 200
    assert "uid" not in res.data


@pytest.mark.django_db
def test_password_reset_rejects_weak_password(api, admin_user, settings):
    settings.DEBUG = True
    res = api.post("/api/auth/password-reset/", {"email": admin_user.email})
    weak = api.post(
        "/api/auth/password-reset/confirm/",
        {"uid": res.data["uid"], "token": res.data["token"], "password": "123"},
    )
    assert weak.status_code == 400
    assert not User.objects.get(pk=admin_user.pk).check_password("123")


# --- RBAC -----------------------------------------------------------------

@pytest.mark.django_db
def test_role_crud_is_admin_only(api, roles, admin_user):
    auth(api, admin_user)
    created = api.post("/api/roles/", {"name": "Auditor", "description": "Read-only auditor"})
    assert created.status_code == 201, created.data

    member = User.objects.create_user(username="norm", email="n@example.com", password="S3curePass!x")
    tokens = auth(api, member)
    denied = api.post("/api/roles/", {"name": "Sneaky"})
    assert denied.status_code == 403
    listing = api.get("/api/roles/")
    assert listing.status_code == 200  # readable by any authenticated user


@pytest.mark.django_db
def test_admin_can_assign_role_but_not_own(api, roles, admin_user):
    tokens = auth(api, admin_user)
    member = User.objects.create_user(username="norm", email="n@example.com", password="S3curePass!x")
    res = api.post(f"/api/users/{member.pk}/set_role/", {"role": "Manager"})
    assert res.status_code == 200, res.data
    assert User.objects.get(pk=member.pk).role.name == "Manager"

    own = api.post(f"/api/users/{admin_user.pk}/set_role/", {"role": "Manager"})
    assert own.status_code == 400
    assert User.objects.get(pk=admin_user.pk).role.name == "Admin"


@pytest.mark.django_db
def test_me_returns_role_and_permissions(api, roles, admin_user):
    auth(api, admin_user)
    res = api.get("/api/auth/me/")
    assert res.status_code == 200
    assert res.data["role_name"] == "Admin"
    assert res.data["is_admin_role"] is True


# --- activity log & middleware -------------------------------------------

@pytest.mark.django_db
def test_middleware_logs_api_requests_with_jwt_user(api, admin_user):
    auth(api, admin_user)
    before = ActivityLog.objects.count()
    api.get("/api/projects/")
    assert ActivityLog.objects.count() == before + 1
    entry = ActivityLog.objects.latest("created_at")
    assert entry.user_id == admin_user.pk
    assert entry.method == "GET"
    assert entry.path == "/api/projects/"


@pytest.mark.django_db
def test_activity_visibility_admin_vs_standard(api, roles, admin_user):
    auth(api, admin_user)
    member = User.objects.create_user(username="norm", email="n@example.com", password="S3curePass!x", role=roles["Standard User"])
    member_client = APIClient()
    member_tokens = api.post("/api/auth/token/", {"username": "norm", "password": "S3curePass!x"}).data
    member_client.credentials(HTTP_AUTHORIZATION=f"Bearer {member_tokens['access']}")

    # Admin sees everything; standard user sees only their own entries.
    all_logs = api.get("/api/activity/")
    own_logs = member_client.get("/api/activity/")
    assert all_logs.status_code == 200 and own_logs.status_code == 200
    assert all(
        r["username"] == "norm" for r in own_logs.data["results"]
    )
    assert any(r["username"] == "boss" for r in all_logs.data["results"])
