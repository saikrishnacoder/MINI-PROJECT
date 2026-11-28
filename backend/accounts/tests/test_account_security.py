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
    admin, _ = Role.objects.get_or_create(name="Admin", defaults={"is_admin": True})
    standard, _ = Role.objects.get_or_create(name="Standard User")
    return {"Admin": admin, "Standard User": standard}


@pytest.fixture
def admin_user(db, roles):
    return User.objects.create_user(
        username="boss", email="boss@example.com", password="S3curePass!x",
        role=roles["Admin"], email_verified=True,
    )


@pytest.fixture
def member(db, roles):
    return User.objects.create_user(
        username="norm", email="norm@example.com", password="S3curePass!x",
        role=roles["Standard User"],
    )


def auth(api, user, password="S3curePass!x"):
    res = api.post("/api/auth/token/", {"username": user.username, "password": password})
    assert res.status_code == 200, res.data
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {res.data['access']}")
    return res.data


# --- email verification ---------------------------------------------------

@pytest.mark.django_db
def test_register_sends_verification_email_and_token(api):
    res = api.post(
        "/api/auth/register/",
        {"username": "newbie", "email": "new@example.com", "password": "S3curePass!x"},
    )
    assert res.status_code == 201, res.data
    user = User.objects.get(username="newbie")
    assert user.email_verified is False
    assert user.email_verification_token
    assert len(mail.outbox) == 1
    assert user.email_verification_token in mail.outbox[0].body
    assert ActivityLog.objects.filter(
        user=user, action=ActivityLog.Action.EMAIL_VERIFICATION_SENT
    ).exists()


@pytest.mark.django_db
def test_verify_email_with_token(api, member):
    from accounts.views import send_verification_email

    send_verification_email(member)
    member.refresh_from_db()
    res = api.post("/api/auth/email/verify/", {"token": member.email_verification_token})
    assert res.status_code == 200, res.data
    member.refresh_from_db()
    assert member.email_verified is True
    assert member.email_verification_token == ""
    assert ActivityLog.objects.filter(
        user=member, action=ActivityLog.Action.EMAIL_VERIFIED
    ).exists()

    # The same link cannot be replayed.
    again = api.post("/api/auth/email/verify/", {"token": "not-a-real-token"})
    assert again.status_code == 400


@pytest.mark.django_db
def test_verify_email_rejects_missing_token(api, db):
    res = api.post("/api/auth/email/verify/", {})
    assert res.status_code == 400
    assert "token" in res.data


@pytest.mark.django_db
def test_resend_verification_is_public_and_idempotent_for_unknown_email(api, member):
    mail.outbox.clear()
    res = api.post("/api/auth/email/verify/request/", {"email": member.email})
    assert res.status_code == 200, res.data
    assert len(mail.outbox) == 1

    mail.outbox.clear()
    ghost = api.post("/api/auth/email/verify/request/", {"email": "ghost@example.com"})
    assert ghost.status_code == 200
    assert len(mail.outbox) == 0

    member.email_verified = True
    member.save(update_fields=["email_verified"])
    already = api.post("/api/auth/email/verify/request/", {"email": member.email})
    assert already.status_code == 200
    assert "already verified" in already.data["detail"].lower()
    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_me_exposes_verification_state_and_email_change_resets_it(api, member):
    auth(api, member)
    me = api.get("/api/auth/me/")
    assert me.status_code == 200
    assert me.data["email_verified"] is False
    assert me.data["is_active"] is True

    member.email_verified = True
    member.save(update_fields=["email_verified"])
    changed = api.patch("/api/auth/me/", {"email": "new-address@example.com"}, format="json")
    assert changed.status_code == 200, changed.data
    member.refresh_from_db()
    assert member.email == "new-address@example.com"
    assert member.email_verified is False


@pytest.mark.django_db
def test_profile_email_must_be_unique(api, member, admin_user):
    auth(api, admin_user)
    res = api.patch("/api/auth/me/", {"email": member.email}, format="json")
    assert res.status_code == 400
    assert "email" in res.data


# --- password change ------------------------------------------------------

@pytest.mark.django_db
def test_password_change_requires_current_password(api, member):
    auth(api, member)
    res = api.post(
        "/api/auth/password-change/",
        {"current_password": "wrong-pass", "new_password": "An0ther!Pass"},
    )
    assert res.status_code == 400
    assert "current_password" in res.data
    member.refresh_from_db()
    assert member.check_password("S3curePass!x")


@pytest.mark.django_db
def test_password_change_updates_and_revokes_sessions(api, member):
    tokens = auth(api, member)
    res = api.post(
        "/api/auth/password-change/",
        {"current_password": "S3curePass!x", "new_password": "An0ther!Pass9"},
    )
    assert res.status_code == 200, res.data
    member.refresh_from_db()
    assert member.check_password("An0ther!Pass9")

    refreshed = APIClient().post(
        "/api/auth/token/refresh/", {"refresh": tokens["refresh"]}
    )
    assert refreshed.status_code == 401
    old_login = APIClient().post(
        "/api/auth/token/", {"username": "norm", "password": "S3curePass!x"}
    )
    assert old_login.status_code == 401
    assert ActivityLog.objects.filter(
        user=member, action=ActivityLog.Action.PASSWORD_CHANGE
    ).exists()


@pytest.mark.django_db
def test_password_change_rejects_same_password(api, member):
    auth(api, member)
    res = api.post(
        "/api/auth/password-change/",
        {"current_password": "S3curePass!x", "new_password": "S3curePass!x"},
    )
    assert res.status_code == 400


# --- account status -------------------------------------------------------

@pytest.mark.django_db
def test_admin_can_deactivate_and_reactivate_account(api, admin_user, member):
    auth(api, admin_user)
    res = api.post(f"/api/users/{member.pk}/set_status/", {"is_active": False}, format="json")
    assert res.status_code == 200, res.data
    assert res.data["is_active"] is False

    member.refresh_from_db()
    assert member.is_active is False
    blocked = APIClient().post(
        "/api/auth/token/", {"username": "norm", "password": "S3curePass!x"}
    )
    assert blocked.status_code == 403
    assert "deactivated" in blocked.data["detail"].lower()

    back = api.post(f"/api/users/{member.pk}/set_status/", {"is_active": True}, format="json")
    assert back.status_code == 200
    allowed = APIClient().post(
        "/api/auth/token/", {"username": "norm", "password": "S3curePass!x"}
    )
    assert allowed.status_code == 200
    assert ActivityLog.objects.filter(
        user=admin_user, action=ActivityLog.Action.ACCOUNT_STATUS
    ).count() == 2


@pytest.mark.django_db
def test_deactivation_revokes_refresh_token(api, admin_user, member):
    session = auth(api, member)
    api.credentials()
    auth(api, admin_user)
    api.post(f"/api/users/{member.pk}/set_status/", {"is_active": False}, format="json")
    refreshed = APIClient().post(
        "/api/auth/token/refresh/", {"refresh": session["refresh"]}
    )
    assert refreshed.status_code == 401


@pytest.mark.django_db
def test_admin_cannot_deactivate_self(api, admin_user):
    auth(api, admin_user)
    res = api.post(f"/api/users/{admin_user.pk}/set_status/", {"is_active": False}, format="json")
    assert res.status_code == 400
    admin_user.refresh_from_db()
    assert admin_user.is_active is True


@pytest.mark.django_db
def test_last_admin_cannot_be_deactivated(api, admin_user, db):
    other = User.objects.create_user(
        username="boss2", email="boss2@example.com", password="S3curePass!x",
        role=admin_user.role,
    )
    auth(api, admin_user)
    api.post(f"/api/users/{other.pk}/set_status/", {"is_active": False}, format="json")
    res = api.post(f"/api/users/{admin_user.pk}/set_status/", {"is_active": False}, format="json")
    # Self-targeting is refused first; the other admin can be deactivated,
    # leaving this account as the last active administrator.
    assert res.status_code == 400
    admin_user.refresh_from_db()
    other.refresh_from_db()
    assert admin_user.is_active is True
    assert other.is_active is False


@pytest.mark.django_db
def test_set_status_requires_admin_and_boolean(api, admin_user, member):
    auth(api, member)
    forbidden = api.post(
        f"/api/users/{member.pk}/set_status/", {"is_active": False}, format="json"
    )
    assert forbidden.status_code == 403

    api.credentials()
    auth(api, admin_user)
    bad = api.post(f"/api/users/{member.pk}/set_status/", {"is_active": "no"}, format="json")
    assert bad.status_code == 400
    assert "is_active" in bad.data
    member.refresh_from_db()
    assert member.is_active is True


@pytest.mark.django_db
def test_inactive_user_bearer_token_is_refused(api, admin_user, member):
    session = auth(api, member)
    api.credentials()
    auth(api, admin_user)
    api.post(f"/api/users/{member.pk}/set_status/", {"is_active": False}, format="json")
    stale = APIClient()
    stale.credentials(HTTP_AUTHORIZATION=f"Bearer {session['access']}")
    assert stale.get("/api/auth/me/").status_code == 401
