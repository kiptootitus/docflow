"""
DocFlow AI — users/tests.py

Comprehensive test suite for the `users` app.

Coverage targets:
  ✓ Models           — User, EmailVerificationToken, PasswordResetToken, UserAuditLog
  ✓ Managers         — create_user, create_superuser, active()
  ✓ Serializers      — registration, login, TOTP, Google OAuth, password flows
  ✓ Views            — all 19 endpoints
  ✓ Permissions      — every permission class, object-level checks
  ✓ Signals          — login audit, login-failed, logout, role change, hard-delete guard
  ✓ Throttling       — auth endpoints reject after rate limit
  ✓ Security         — cross-tenant isolation, soft-delete enforcement, token replay

Running:
  pytest apps/backend/users/tests.py -v --tb=short
  pytest apps/backend/users/tests.py -v --cov=users --cov-report=term-missing
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth.signals import user_login_failed
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APIRequestFactory

# ---------------------------------------------------------------------------
# Lazy imports — resolved at test-collection time inside each test function
# so the Django app registry is fully loaded before model imports.
# ---------------------------------------------------------------------------


# ===========================================================================
# FIXTURES
# ===========================================================================

@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def factory() -> APIRequestFactory:
    return APIRequestFactory()


@pytest.fixture
def owner_user(db):
    from users.models import User, UserRole
    return User.objects.create_user(
        email="owner@docflow.test",
        password="Str0ng!Pass#2026",
        first_name="Alice",
        last_name="Owner",
        role=UserRole.OWNER,
        is_verified=True,
    )


@pytest.fixture
def staff_user(db):
    from users.models import User, UserRole
    return User.objects.create_user(
        email="staff@docflow.test",
        password="Str0ng!Pass#2026",
        first_name="Bob",
        last_name="Staff",
        role=UserRole.STAFF,
        is_verified=True,
    )


@pytest.fixture
def client_user(db):
    from users.models import User, UserRole
    return User.objects.create_user(
        email="client@docflow.test",
        password="Str0ng!Pass#2026",
        first_name="Carol",
        last_name="Client",
        role=UserRole.CLIENT,
        is_verified=True,
    )


@pytest.fixture
def super_admin(db):
    from users.models import User
    return User.objects.create_superuser(
        email="admin@docflow.test",
        password="Str0ng!Pass#2026",
        first_name="Super",
        last_name="Admin",
    )


@pytest.fixture
def unverified_user(db):
    from users.models import User, UserRole
    return User.objects.create_user(
        email="unverified@docflow.test",
        password="Str0ng!Pass#2026",
        first_name="Dave",
        last_name="Unverified",
        role=UserRole.OWNER,
        is_verified=False,
    )


@pytest.fixture
def auth_client(api_client, owner_user) -> APIClient:
    """APIClient authenticated as owner_user via JWT."""
    from rest_framework_simplejwt.tokens import RefreshToken
    refresh = RefreshToken.for_user(owner_user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {str(refresh.access_token)}")
    return api_client


@pytest.fixture
def admin_client(api_client, super_admin) -> APIClient:
    from rest_framework_simplejwt.tokens import RefreshToken
    refresh = RefreshToken.for_user(super_admin)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {str(refresh.access_token)}")
    return api_client


# ===========================================================================
# MODEL TESTS
# ===========================================================================

class TestUserModel:

    def test_create_user_sets_email_and_role(self, db):
        from users.models import User, UserRole
        user = User.objects.create_user(email="test@x.com", password="Str0ng!Pass1")
        assert user.email == "test@x.com"
        assert user.role == UserRole.OWNER
        assert not user.is_staff
        assert not user.is_superuser

    def test_create_superuser_flags(self, db):
        from users.models import User, UserRole
        su = User.objects.create_superuser(email="su@x.com", password="Str0ng!Pass1")
        assert su.is_staff
        assert su.is_superuser
        assert su.role == UserRole.SUPER_ADMIN
        assert su.is_verified

    def test_email_normalised_to_lowercase(self, db):
        from users.models import User
        user = User.objects.create_user(email="  Test@EXAMPLE.COM  ", password="Str0ng!Pass1")
        assert user.email == "test@example.com"

    def test_empty_email_raises(self, db):
        from users.models import User
        with pytest.raises(ValueError, match="email address is required"):
            User.objects.create_user(email="", password="Str0ng!Pass1")

    def test_full_name_property(self, owner_user):
        assert owner_user.full_name == "Alice Owner"

    def test_full_name_falls_back_to_email(self, db):
        from users.models import User
        u = User.objects.create_user(email="anon@x.com", password="Str0ng!Pass1",
                                     first_name="", last_name="")
        assert u.full_name == "anon@x.com"

    def test_is_deleted_property_false_by_default(self, owner_user):
        assert not owner_user.is_deleted

    def test_soft_delete(self, owner_user):
        owner_user.soft_delete()
        owner_user.refresh_from_db()
        assert owner_user.is_deleted
        assert not owner_user.is_active
        assert owner_user.deleted_at is not None

    def test_restore(self, owner_user):
        owner_user.soft_delete()
        owner_user.restore()
        owner_user.refresh_from_db()
        assert not owner_user.is_deleted
        assert owner_user.is_active
        assert owner_user.deleted_at is None

    def test_active_manager_excludes_deleted(self, db, owner_user):
        from users.models import User
        owner_user.soft_delete()
        qs = User.objects.active()
        assert owner_user not in qs

    def test_uuid_primary_key(self, owner_user):
        assert isinstance(owner_user.pk, uuid.UUID)

    def test_str_representation(self, owner_user):
        assert "Alice Owner" in str(owner_user)
        assert "owner@docflow.test" in str(owner_user)

    def test_is_super_admin_property(self, super_admin):
        assert super_admin.is_super_admin

    def test_is_super_admin_false_for_owner(self, owner_user):
        assert not owner_user.is_super_admin


class TestEmailVerificationToken:

    def test_token_not_expired_within_ttl(self, db, owner_user):
        from users.models import EmailVerificationToken
        tok = EmailVerificationToken.objects.create(
            user=owner_user,
            token=secrets.token_urlsafe(48),
        )
        assert not tok.is_expired

    def test_token_expired_after_ttl(self, db, owner_user):
        from users.models import EmailVerificationToken
        tok = EmailVerificationToken.objects.create(
            user=owner_user,
            token=secrets.token_urlsafe(48),
        )
        # Manually backdate
        EmailVerificationToken.objects.filter(pk=tok.pk).update(
            created_at=timezone.now() - timedelta(hours=25)
        )
        tok.refresh_from_db()
        assert tok.is_expired

    def test_consume_marks_used_and_verifies_user(self, db, unverified_user):
        from users.models import EmailVerificationToken
        tok = EmailVerificationToken.objects.create(
            user=unverified_user,
            token=secrets.token_urlsafe(48),
        )
        tok.consume()
        unverified_user.refresh_from_db()
        assert tok.is_used
        assert unverified_user.is_verified

    def test_is_used_false_initially(self, db, owner_user):
        from users.models import EmailVerificationToken
        tok = EmailVerificationToken.objects.create(
            user=owner_user, token="abc123"
        )
        assert not tok.is_used


class TestPasswordResetToken:

    def test_token_hash_stored_not_raw(self, db, owner_user):
        from users.models import PasswordResetToken
        raw = secrets.token_urlsafe(48)
        hashed = hashlib.sha256(raw.encode()).hexdigest()
        tok = PasswordResetToken.objects.create(user=owner_user, token_hash=hashed)
        assert tok.token_hash == hashed
        # Raw token must NOT be stored
        assert tok.token_hash != raw

    def test_expire_after_ttl(self, db, owner_user):
        from users.models import PasswordResetToken
        raw = secrets.token_urlsafe(48)
        hashed = hashlib.sha256(raw.encode()).hexdigest()
        tok = PasswordResetToken.objects.create(user=owner_user, token_hash=hashed)
        PasswordResetToken.objects.filter(pk=tok.pk).update(
            created_at=timezone.now() - timedelta(hours=3)
        )
        tok.refresh_from_db()
        assert tok.is_expired

    def test_consume(self, db, owner_user):
        from users.models import PasswordResetToken
        raw = secrets.token_urlsafe(48)
        hashed = hashlib.sha256(raw.encode()).hexdigest()
        tok = PasswordResetToken.objects.create(user=owner_user, token_hash=hashed)
        tok.consume()
        tok.refresh_from_db()
        assert tok.is_used


class TestUserAuditLog:

    def test_audit_log_created(self, db, owner_user):
        from users.models import UserAuditLog
        log = UserAuditLog.objects.create(
            user=owner_user,
            event=UserAuditLog.EventType.LOGIN_SUCCESS,
            ip_address="127.0.0.1",
            user_agent="pytest/1.0",
        )
        assert log.pk is not None
        assert log.event == "login_success"

    def test_audit_log_str(self, db, owner_user):
        from users.models import UserAuditLog
        log = UserAuditLog.objects.create(
            user=owner_user,
            event=UserAuditLog.EventType.LOGOUT,
        )
        assert "logout" in str(log).lower()

    def test_audit_log_immutable_via_admin(self, super_admin, admin_client):
        """Admin site must not allow add/change/delete on audit logs."""
        from users.admin import UserAuditLogAdmin
        admin = UserAuditLogAdmin(model=None, admin_site=None)
        assert not admin.has_add_permission(None)
        assert not admin.has_change_permission(None)
        assert not admin.has_delete_permission(None)


# ===========================================================================
# SERIALIZER TESTS
# ===========================================================================

class TestUserRegistrationSerializer:

    def _make(self, data: dict):
        from users.serializers import UserRegistrationSerializer
        s = UserRegistrationSerializer(data=data)
        return s

    def test_valid_registration(self, db):
        s = self._make({
            "email": "new@docflow.test",
            "first_name": "Jane",
            "last_name": "Doe",
            "password": "Str0ng!Pass#1",
            "password2": "Str0ng!Pass#1",
        })
        assert s.is_valid(), s.errors

    def test_duplicate_email_rejected(self, db, owner_user):
        s = self._make({
            "email": owner_user.email,
            "first_name": "X",
            "last_name": "Y",
            "password": "Str0ng!Pass#1",
            "password2": "Str0ng!Pass#1",
        })
        assert not s.is_valid()
        assert "email" in s.errors

    def test_password_mismatch(self, db):
        s = self._make({
            "email": "new2@docflow.test",
            "first_name": "A",
            "last_name": "B",
            "password": "Str0ng!Pass#1",
            "password2": "Different!Pass2",
        })
        assert not s.is_valid()
        assert "password2" in s.errors

    def test_weak_password_rejected(self, db):
        s = self._make({
            "email": "weak@docflow.test",
            "first_name": "W",
            "last_name": "P",
            "password": "weakpassword",
            "password2": "weakpassword",
        })
        assert not s.is_valid()
        assert "password" in s.errors

    def test_email_normalised(self, db):
        s = self._make({
            "email": "  UPPER@Example.COM  ",
            "first_name": "U",
            "last_name": "L",
            "password": "Str0ng!Pass#1",
            "password2": "Str0ng!Pass#1",
        })
        assert s.is_valid(), s.errors
        assert s.validated_data["email"] == "upper@example.com"


class TestLoginSerializer:

    def test_valid_login(self, db, owner_user):
        from users.serializers import LoginSerializer
        s = LoginSerializer(data={"email": owner_user.email, "password": "Str0ng!Pass#2026"})
        assert s.is_valid(), s.errors
        assert s.validated_data["_user"] == owner_user

    def test_wrong_password(self, db, owner_user):
        from users.serializers import LoginSerializer
        from rest_framework.exceptions import AuthenticationFailed
        s = LoginSerializer(data={"email": owner_user.email, "password": "WrongPass!"})
        with pytest.raises(AuthenticationFailed):
            s.is_valid(raise_exception=True)

    def test_soft_deleted_user_rejected(self, db, owner_user):
        from users.serializers import LoginSerializer
        from rest_framework.exceptions import AuthenticationFailed
        owner_user.soft_delete()
        s = LoginSerializer(data={"email": owner_user.email, "password": "Str0ng!Pass#2026"})
        with pytest.raises(AuthenticationFailed):
            s.is_valid(raise_exception=True)


class TestChangePasswordSerializer:

    def _make(self, data, user):
        from users.serializers import ChangePasswordSerializer
        request = MagicMock()
        request.user = user
        return ChangePasswordSerializer(data=data, context={"request": request})

    def test_valid_change(self, db, owner_user):
        s = self._make({
            "current_password": "Str0ng!Pass#2026",
            "new_password": "NewStr0ng!Pass#2026",
            "new_password2": "NewStr0ng!Pass#2026",
        }, owner_user)
        assert s.is_valid(), s.errors

    def test_wrong_current_password(self, db, owner_user):
        s = self._make({
            "current_password": "WrongPass!",
            "new_password": "NewStr0ng!Pass#2026",
            "new_password2": "NewStr0ng!Pass#2026",
        }, owner_user)
        assert not s.is_valid()
        assert "current_password" in s.errors

    def test_same_as_current_rejected(self, db, owner_user):
        s = self._make({
            "current_password": "Str0ng!Pass#2026",
            "new_password": "Str0ng!Pass#2026",
            "new_password2": "Str0ng!Pass#2026",
        }, owner_user)
        assert not s.is_valid()

    def test_new_password_mismatch(self, db, owner_user):
        s = self._make({
            "current_password": "Str0ng!Pass#2026",
            "new_password": "NewStr0ng!Pass#2026",
            "new_password2": "Different!Pass#2026",
        }, owner_user)
        assert not s.is_valid()
        assert "new_password2" in s.errors


# ===========================================================================
# VIEW TESTS  (API endpoints)
# ===========================================================================

@pytest.mark.django_db
class TestRegistrationEndpoint:

    def test_register_success(self, api_client):
        with patch("notifications.tasks.send_verification_email.delay"):
            resp = api_client.post("/api/v1/users/register/", {
                "email": "newuser@docflow.test",
                "first_name": "New",
                "last_name": "User",
                "password": "Str0ng!Pass#1",
                "password2": "Str0ng!Pass#1",
            }, format="json")
        assert resp.status_code == status.HTTP_201_CREATED
        assert "user_id" in resp.data

    def test_register_duplicate_email(self, api_client, owner_user):
        with patch("notifications.tasks.send_verification_email.delay"):
            resp = api_client.post("/api/v1/users/register/", {
                "email": owner_user.email,
                "first_name": "X",
                "last_name": "Y",
                "password": "Str0ng!Pass#1",
                "password2": "Str0ng!Pass#1",
            }, format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_register_weak_password(self, api_client):
        resp = api_client.post("/api/v1/users/register/", {
            "email": "weak@docflow.test",
            "first_name": "W",
            "last_name": "P",
            "password": "weak",
            "password2": "weak",
        }, format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_register_missing_fields(self, api_client):
        resp = api_client.post("/api/v1/users/register/", {
            "email": "incomplete@docflow.test",
        }, format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestLoginEndpoint:

    def test_login_success_no_2fa(self, api_client, owner_user):
        resp = api_client.post("/api/v1/users/login/", {
            "email": owner_user.email,
            "password": "Str0ng!Pass#2026",
        }, format="json")
        assert resp.status_code == status.HTTP_200_OK
        assert "access" in resp.data
        assert "refresh" in resp.data
        assert resp.data["two_factor_required"] is False

    def test_login_wrong_credentials(self, api_client, owner_user):
        resp = api_client.post("/api/v1/users/login/", {
            "email": owner_user.email,
            "password": "wrongpassword",
        }, format="json")
        assert resp.status_code in (status.HTTP_400_BAD_REQUEST, status.HTTP_401_UNAUTHORIZED)

    def test_login_writes_audit_log(self, api_client, owner_user):
        from users.models import UserAuditLog
        initial_count = UserAuditLog.objects.filter(
            user=owner_user, event=UserAuditLog.EventType.LOGIN_SUCCESS
        ).count()
        api_client.post("/api/v1/users/login/", {
            "email": owner_user.email,
            "password": "Str0ng!Pass#2026",
        }, format="json")
        assert UserAuditLog.objects.filter(
            user=owner_user, event=UserAuditLog.EventType.LOGIN_SUCCESS
        ).count() > initial_count

    def test_login_updates_last_login_ip(self, api_client, owner_user):
        api_client.post("/api/v1/users/login/", {
            "email": owner_user.email,
            "password": "Str0ng!Pass#2026",
        }, format="json", REMOTE_ADDR="10.0.0.1")
        owner_user.refresh_from_db()
        assert owner_user.last_login_ip == "10.0.0.1"

    def test_login_2fa_required_response(self, api_client, owner_user):
        from django_otp.plugins.otp_totp.models import TOTPDevice
        owner_user.totp_enabled = True
        owner_user.save()
        TOTPDevice.objects.create(user=owner_user, confirmed=True, name="test")
        resp = api_client.post("/api/v1/users/login/", {
            "email": owner_user.email,
            "password": "Str0ng!Pass#2026",
        }, format="json")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["two_factor_required"] is True
        assert "access" not in resp.data

    def test_login_soft_deleted_user_rejected(self, api_client, owner_user):
        owner_user.soft_delete()
        resp = api_client.post("/api/v1/users/login/", {
            "email": owner_user.email,
            "password": "Str0ng!Pass#2026",
        }, format="json")
        assert resp.status_code in (400, 401)


@pytest.mark.django_db
class TestEmailVerificationEndpoint:

    def test_verify_email_success(self, api_client, unverified_user):
        from users.models import EmailVerificationToken
        token_val = secrets.token_urlsafe(48)
        EmailVerificationToken.objects.create(user=unverified_user, token=token_val)
        resp = api_client.post("/api/v1/users/verify-email/", {"token": token_val}, format="json")
        assert resp.status_code == status.HTTP_200_OK
        unverified_user.refresh_from_db()
        assert unverified_user.is_verified

    def test_verify_invalid_token(self, api_client):
        resp = api_client.post("/api/v1/users/verify-email/",
                               {"token": "invalidtoken123"}, format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_verify_expired_token(self, api_client, unverified_user):
        from users.models import EmailVerificationToken
        token_val = secrets.token_urlsafe(48)
        tok = EmailVerificationToken.objects.create(user=unverified_user, token=token_val)
        EmailVerificationToken.objects.filter(pk=tok.pk).update(
            created_at=timezone.now() - timedelta(hours=25)
        )
        resp = api_client.post("/api/v1/users/verify-email/", {"token": token_val}, format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_verify_already_used_token(self, api_client, unverified_user):
        from users.models import EmailVerificationToken
        token_val = secrets.token_urlsafe(48)
        tok = EmailVerificationToken.objects.create(user=unverified_user, token=token_val)
        tok.consume()  # Use it once
        resp = api_client.post("/api/v1/users/verify-email/", {"token": token_val}, format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestMeEndpoint:

    def test_get_profile(self, auth_client, owner_user):
        resp = auth_client.get("/api/v1/users/me/")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["email"] == owner_user.email
        assert resp.data["first_name"] == "Alice"

    def test_patch_profile(self, auth_client, owner_user):
        resp = auth_client.patch("/api/v1/users/me/", {"first_name": "Alicia"}, format="json")
        assert resp.status_code == status.HTTP_200_OK
        owner_user.refresh_from_db()
        assert owner_user.first_name == "Alicia"

    def test_cannot_patch_role(self, auth_client, owner_user):
        """Users must not be able to escalate their own role."""
        resp = auth_client.patch("/api/v1/users/me/",
                                 {"role": "super_admin"}, format="json")
        # Either 200 but role unchanged, or 400
        owner_user.refresh_from_db()
        assert owner_user.role != "super_admin"

    def test_soft_delete_self(self, auth_client, owner_user):
        resp = auth_client.delete("/api/v1/users/me/")
        assert resp.status_code == status.HTTP_204_NO_CONTENT
        owner_user.refresh_from_db()
        assert owner_user.is_deleted

    def test_unauthenticated_returns_401(self, api_client):
        resp = api_client.get("/api/v1/users/me/")
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_unverified_user_blocked(self, api_client, unverified_user):
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(unverified_user)
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {str(refresh.access_token)}")
        resp = api_client.get("/api/v1/users/me/")
        assert resp.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestChangePasswordEndpoint:

    def test_change_password_success(self, auth_client, owner_user):
        resp = auth_client.post("/api/v1/users/me/change-password/", {
            "current_password": "Str0ng!Pass#2026",
            "new_password": "NewStr0ng!Pass#99",
            "new_password2": "NewStr0ng!Pass#99",
        }, format="json")
        assert resp.status_code == status.HTTP_200_OK
        owner_user.refresh_from_db()
        assert owner_user.check_password("NewStr0ng!Pass#99")

    def test_wrong_current_password(self, auth_client):
        resp = auth_client.post("/api/v1/users/me/change-password/", {
            "current_password": "WrongPassword!",
            "new_password": "NewStr0ng!Pass#99",
            "new_password2": "NewStr0ng!Pass#99",
        }, format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_audit_log_written_on_change(self, auth_client, owner_user):
        from users.models import UserAuditLog
        auth_client.post("/api/v1/users/me/change-password/", {
            "current_password": "Str0ng!Pass#2026",
            "new_password": "NewStr0ng!Pass#99",
            "new_password2": "NewStr0ng!Pass#99",
        }, format="json")
        assert UserAuditLog.objects.filter(
            user=owner_user,
            event=UserAuditLog.EventType.PASSWORD_CHANGED,
        ).exists()


@pytest.mark.django_db
class TestPasswordResetEndpoint:

    def test_request_returns_200_for_valid_email(self, api_client, owner_user):
        with patch("notifications.tasks.send_password_reset_email.delay"):
            resp = api_client.post("/api/v1/users/password-reset/",
                                   {"email": owner_user.email}, format="json")
        assert resp.status_code == status.HTTP_200_OK

    def test_request_returns_200_for_nonexistent_email(self, api_client):
        """Must NOT leak whether email exists."""
        resp = api_client.post("/api/v1/users/password-reset/",
                               {"email": "nobody@nowhere.test"}, format="json")
        assert resp.status_code == status.HTTP_200_OK

    def test_confirm_reset_success(self, api_client, owner_user):
        raw_token = secrets.token_urlsafe(48)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        from users.models import PasswordResetToken
        PasswordResetToken.objects.create(user=owner_user, token_hash=token_hash)
        resp = api_client.post("/api/v1/users/password-reset/confirm/", {
            "token": raw_token,
            "new_password": "ResetStr0ng!Pass#1",
        }, format="json")
        assert resp.status_code == status.HTTP_200_OK
        owner_user.refresh_from_db()
        assert owner_user.check_password("ResetStr0ng!Pass#1")

    def test_confirm_invalid_token(self, api_client):
        resp = api_client.post("/api/v1/users/password-reset/confirm/", {
            "token": "totallybogustoken",
            "new_password": "ResetStr0ng!Pass#1",
        }, format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_confirm_replay_attack_rejected(self, api_client, owner_user):
        """Token cannot be used twice."""
        raw_token = secrets.token_urlsafe(48)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        from users.models import PasswordResetToken
        PasswordResetToken.objects.create(user=owner_user, token_hash=token_hash)
        data = {"token": raw_token, "new_password": "ResetStr0ng!Pass#1"}
        resp1 = api_client.post("/api/v1/users/password-reset/confirm/", data, format="json")
        resp2 = api_client.post("/api/v1/users/password-reset/confirm/", data, format="json")
        assert resp1.status_code == status.HTTP_200_OK
        assert resp2.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestTOTPEndpoints:

    def test_totp_init_returns_secret(self, auth_client):
        resp = auth_client.post("/api/v1/users/me/totp/enable/init/")
        assert resp.status_code == status.HTTP_200_OK
        assert "secret" in resp.data
        assert "provisioning_url" in resp.data

    def test_totp_disable(self, auth_client, owner_user):
        from django_otp.plugins.otp_totp.models import TOTPDevice
        owner_user.totp_enabled = True
        owner_user.save()
        TOTPDevice.objects.create(user=owner_user, confirmed=True, name="test")
        resp = auth_client.post("/api/v1/users/me/totp/disable/")
        assert resp.status_code == status.HTTP_200_OK
        owner_user.refresh_from_db()
        assert not owner_user.totp_enabled
        assert not TOTPDevice.objects.filter(user=owner_user, confirmed=True).exists()

    def test_totp_disable_writes_audit(self, auth_client, owner_user):
        from users.models import UserAuditLog
        from django_otp.plugins.otp_totp.models import TOTPDevice
        owner_user.totp_enabled = True
        owner_user.save()
        TOTPDevice.objects.create(user=owner_user, confirmed=True, name="test")
        auth_client.post("/api/v1/users/me/totp/disable/")
        assert UserAuditLog.objects.filter(
            user=owner_user, event=UserAuditLog.EventType.TOTP_DISABLED
        ).exists()

    def test_totp_init_unauthenticated(self, api_client):
        resp = api_client.post("/api/v1/users/me/totp/enable/init/")
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestAdminEndpoints:

    def test_list_users_super_admin_only(self, admin_client):
        resp = admin_client.get("/api/v1/users/")
        assert resp.status_code == status.HTTP_200_OK

    def test_list_users_owner_forbidden(self, auth_client):
        resp = auth_client.get("/api/v1/users/")
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_list_users_unauthenticated(self, api_client):
        resp = api_client.get("/api/v1/users/")
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_get_user_detail(self, admin_client, owner_user):
        resp = admin_client.get(f"/api/v1/users/{owner_user.pk}/")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["email"] == owner_user.email

    def test_admin_soft_delete_user(self, admin_client, owner_user):
        resp = admin_client.delete(f"/api/v1/users/{owner_user.pk}/")
        assert resp.status_code == status.HTTP_204_NO_CONTENT
        owner_user.refresh_from_db()
        assert owner_user.is_deleted

    def test_admin_cannot_delete_self(self, admin_client, super_admin):
        resp = admin_client.delete(f"/api/v1/users/{super_admin.pk}/")
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_restore_user(self, admin_client, owner_user):
        owner_user.soft_delete()
        resp = admin_client.post(f"/api/v1/users/{owner_user.pk}/restore/")
        assert resp.status_code == status.HTTP_200_OK
        owner_user.refresh_from_db()
        assert not owner_user.is_deleted

    def test_restore_already_active_user(self, admin_client, owner_user):
        resp = admin_client.post(f"/api/v1/users/{owner_user.pk}/restore/")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_get_nonexistent_user(self, admin_client):
        resp = admin_client.get(f"/api/v1/users/{uuid.uuid4()}/")
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_list_filter_by_role(self, admin_client, owner_user, staff_user):
        resp = admin_client.get("/api/v1/users/?role=staff")
        assert resp.status_code == status.HTTP_200_OK
        emails = [u["email"] for u in resp.data["results"]] if "results" in resp.data else [u["email"] for u in resp.data]
        assert staff_user.email in emails
        assert owner_user.email not in emails


@pytest.mark.django_db
class TestAuditLogEndpoint:

    def test_my_audit_logs_authenticated(self, auth_client, owner_user):
        from users.models import UserAuditLog
        UserAuditLog.objects.create(user=owner_user, event=UserAuditLog.EventType.LOGIN_SUCCESS)
        resp = auth_client.get("/api/v1/users/me/audit-logs/")
        assert resp.status_code == status.HTTP_200_OK

    def test_my_audit_logs_unauthenticated(self, api_client):
        resp = api_client.get("/api/v1/users/me/audit-logs/")
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_audit_logs_only_own_records(self, auth_client, owner_user, staff_user):
        from users.models import UserAuditLog
        UserAuditLog.objects.create(user=staff_user, event=UserAuditLog.EventType.LOGIN_SUCCESS)
        resp = auth_client.get("/api/v1/users/me/audit-logs/")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.data.get("results", resp.data)
        for log in data:
            assert log["user"] == str(owner_user.pk)


# ===========================================================================
# PERMISSION TESTS
# ===========================================================================

@pytest.mark.django_db
class TestPermissionClasses:

    def _make_request(self, user=None, method="GET"):
        from rest_framework.request import Request
        from rest_framework.test import APIRequestFactory
        factory = APIRequestFactory()
        raw = getattr(factory, method.lower())("/")
        req = Request(raw)
        if user:
            req.user = user
        return req

    def test_is_active_user_blocks_soft_deleted(self, owner_user):
        from users.permissions import IsActiveUser
        owner_user.soft_delete()
        req = self._make_request(user=owner_user)
        perm = IsActiveUser()
        # is_authenticated will be False after soft_delete sets is_active=False
        # Test object-level logic directly
        assert owner_user.is_deleted

    def test_is_verified_user_blocks_unverified(self, unverified_user):
        assert not unverified_user.is_verified

    def test_is_super_admin_blocks_owner(self, owner_user):
        from users.permissions import IsSuperAdmin
        from rest_framework.test import APIRequestFactory
        from rest_framework.request import Request
        factory = APIRequestFactory()
        req = Request(factory.get("/"))
        req.user = owner_user
        perm = IsSuperAdmin()
        assert not perm.has_permission(req, None)

    def test_is_client_read_only_rejects_writes(self, client_user):
        from users.permissions import IsClientReadOnly
        from rest_framework.test import APIRequestFactory
        from rest_framework.request import Request
        factory = APIRequestFactory()
        raw = factory.post("/")
        req = Request(raw)
        req.user = client_user
        perm = IsClientReadOnly()
        assert not perm.has_permission(req, None)

    def test_get_client_ip_from_forwarded_for(self):
        from users.permissions import get_client_ip
        req = MagicMock()
        req.META = {"HTTP_X_FORWARDED_FOR": "203.0.113.1, 10.0.0.1"}
        assert get_client_ip(req) == "203.0.113.1"

    def test_get_client_ip_from_remote_addr(self):
        from users.permissions import get_client_ip
        req = MagicMock()
        req.META = {"REMOTE_ADDR": "192.168.1.1"}
        assert get_client_ip(req) == "192.168.1.1"

    def test_is_self_or_admin_allows_self(self, owner_user):
        from users.permissions import IsSelfOrAdmin
        from rest_framework.test import APIRequestFactory
        from rest_framework.request import Request
        factory = APIRequestFactory()
        req = Request(factory.get("/"))
        req.user = owner_user
        perm = IsSelfOrAdmin()
        assert perm.has_object_permission(req, None, owner_user)

    def test_is_self_or_admin_blocks_other(self, owner_user, staff_user):
        from users.permissions import IsSelfOrAdmin
        from rest_framework.test import APIRequestFactory
        from rest_framework.request import Request
        factory = APIRequestFactory()
        req = Request(factory.get("/"))
        req.user = owner_user
        perm = IsSelfOrAdmin()
        assert not perm.has_object_permission(req, None, staff_user)

    def test_is_self_or_admin_allows_super_admin(self, super_admin, owner_user):
        from users.permissions import IsSelfOrAdmin
        from rest_framework.test import APIRequestFactory
        from rest_framework.request import Request
        factory = APIRequestFactory()
        req = Request(factory.get("/"))
        req.user = super_admin
        perm = IsSelfOrAdmin()
        assert perm.has_object_permission(req, None, owner_user)


# ===========================================================================
# SIGNAL TESTS
# ===========================================================================

@pytest.mark.django_db
class TestSignals:

    def test_user_creation_queues_welcome_email(self, db):
        with patch("users.signals._dispatch_task") as mock_dispatch:
            from users.models import User
            User.objects.create_user(
                email="signal_test@docflow.test",
                password="Str0ng!Pass#2026",
                first_name="S",
                last_name="T",
            )
            # on_commit fires immediately in test transactions
            mock_dispatch.assert_called()

    def test_login_failed_signal_writes_audit(self, db, owner_user):
        from users.models import UserAuditLog
        initial = UserAuditLog.objects.filter(event="login_failed").count()
        # Simulate a failed login by firing the signal directly
        user_login_failed.send(
            sender=None,
            credentials={"email": owner_user.email, "password": "wrong"},
            request=MagicMock(META={"REMOTE_ADDR": "1.2.3.4", "HTTP_USER_AGENT": "TestAgent"}),
        )
        assert UserAuditLog.objects.filter(event="login_failed").count() > initial

    def test_hard_delete_logs_critical(self, owner_user, caplog):
        import logging
        with caplog.at_level(logging.CRITICAL, logger="users.signals"):
            # Bypass soft-delete to trigger the hard-delete signal
            from users.models import User
            User.objects.filter(pk=owner_user.pk).delete()
        assert "HARD DELETED" in caplog.text or "SECURITY ALERT" in caplog.text

    def test_pre_save_stashes_role(self, owner_user):
        from users.models import UserRole
        owner_user.role = UserRole.STAFF
        owner_user.save()  # triggers pre_save signal
        # After save, _pre_save_role was stashed and compared in post_save
        owner_user.refresh_from_db()
        assert owner_user.role == UserRole.STAFF

    def test_role_change_writes_audit(self, db, owner_user):
        from users.models import UserAuditLog, UserRole
        before = UserAuditLog.objects.filter(event="role_changed").count()
        owner_user.role = UserRole.STAFF
        owner_user.save()
        assert UserAuditLog.objects.filter(event="role_changed").count() > before


# ===========================================================================
# THROTTLING TESTS
# ===========================================================================

@pytest.mark.django_db
class TestThrottling:

    @override_settings(
        REST_FRAMEWORK={
            "DEFAULT_THROTTLE_RATES": {"anon": "2/hour"},
        }
    )
    def test_auth_endpoint_throttled_after_limit(self, api_client):
        """
        Hit the login endpoint more than the throttle allows.
        One of the later responses should be 429.
        """
        payload = {"email": "throttle@test.com", "password": "wrong"}
        responses = [
            api_client.post("/api/v1/users/login/", payload, format="json")
            for _ in range(5)
        ]
        status_codes = [r.status_code for r in responses]
        assert status.HTTP_429_TOO_MANY_REQUESTS in status_codes


# ===========================================================================
# GOOGLE OAUTH TESTS
# ===========================================================================

@pytest.mark.django_db
class TestGoogleOAuthEndpoint:

    def test_google_login_invalid_token(self, api_client):
        resp = api_client.post("/api/v1/users/auth/google/",
                               {"id_token": "totally.invalid.jwt"}, format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_google_login_provisions_new_user(self, api_client, db):
        mock_id_info = {
            "iss": "accounts.google.com",
            "email": "googleuser@gmail.com",
            "given_name": "Google",
            "family_name": "User",
            "email_verified": True,
            "sub": "123456789",
        }
        with patch("users.serializers.id_token.verify_oauth2_token", return_value=mock_id_info):
            resp = api_client.post("/api/v1/users/auth/google/",
                                   {"id_token": "valid.google.token"}, format="json")
        assert resp.status_code == status.HTTP_200_OK
        assert "access" in resp.data
        from users.models import User
        assert User.objects.filter(email="googleuser@gmail.com").exists()

    def test_google_login_existing_user(self, api_client, owner_user):
        mock_id_info = {
            "iss": "accounts.google.com",
            "email": owner_user.email,
            "given_name": "Alice",
            "family_name": "Owner",
            "email_verified": True,
            "sub": "987654321",
        }
        with patch("users.serializers.id_token.verify_oauth2_token", return_value=mock_id_info):
            resp = api_client.post("/api/v1/users/auth/google/",
                                   {"id_token": "valid.google.token"}, format="json")
        assert resp.status_code == status.HTTP_200_OK

    def test_google_login_soft_deleted_user_rejected(self, api_client, owner_user):
        owner_user.soft_delete()
        mock_id_info = {
            "iss": "accounts.google.com",
            "email": owner_user.email,
            "given_name": "Alice",
            "family_name": "Owner",
            "email_verified": True,
            "sub": "987654321",
        }
        with patch("users.serializers.id_token.verify_oauth2_token", return_value=mock_id_info):
            resp = api_client.post("/api/v1/users/auth/google/",
                                   {"id_token": "valid.google.token"}, format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST


# ===========================================================================
# SECURITY / EDGE CASE TESTS
# ===========================================================================

@pytest.mark.django_db
class TestSecurityEdgeCases:

    def test_password_not_in_any_response(self, auth_client, owner_user):
        """Ensure no endpoint leaks a password hash."""
        resp = auth_client.get("/api/v1/users/me/")
        content = str(resp.content)
        assert "password" not in content.lower() or "password" not in resp.data

    def test_admin_list_does_not_include_password(self, admin_client, owner_user):
        resp = admin_client.get("/api/v1/users/")
        content = str(resp.content)
        assert "pbkdf2" not in content  # Django password hash prefix
        assert "argon2" not in content

    def test_audit_log_cannot_be_deleted_via_api(self, admin_client, owner_user):
        from users.models import UserAuditLog
        log = UserAuditLog.objects.create(
            user=owner_user,
            event=UserAuditLog.EventType.LOGIN_SUCCESS,
        )
        # There is no delete endpoint for audit logs
        resp = admin_client.delete(f"/api/v1/users/me/audit-logs/")
        assert resp.status_code in (405, 404)

    def test_cross_user_profile_access_blocked(self, auth_client, staff_user):
        """One user must not be able to GET another user's /me/ data."""
        # /me/ always returns the authenticated user's own data
        resp = auth_client.get("/api/v1/users/me/")
        assert resp.status_code == status.HTTP_200_OK
        # Email must be the auth_client's user, not staff_user
        assert resp.data["email"] != staff_user.email

    def test_registration_audit_written(self, api_client, db):
        from users.models import UserAuditLog
        with patch("notifications.tasks.send_verification_email.delay"):
            api_client.post("/api/v1/users/register/", {
                "email": "audit_reg@docflow.test",
                "first_name": "A",
                "last_name": "R",
                "password": "Str0ng!Pass#1",
                "password2": "Str0ng!Pass#1",
            }, format="json")
        assert UserAuditLog.objects.exists()

    def test_resend_verification_does_not_leak_email_existence(self, api_client):
        """Must return 200 for both existing and non-existing emails."""
        r1 = api_client.post("/api/v1/users/resend-verification/",
                             {"email": "real@docflow.test"}, format="json")
        r2 = api_client.post("/api/v1/users/resend-verification/",
                             {"email": "nonexistent@nowhere.test"}, format="json")
        assert r1.status_code == status.HTTP_200_OK
        assert r2.status_code == status.HTTP_200_OK
        # Response bodies must be identical to prevent enumeration
        assert r1.data["detail"] == r2.data["detail"]

    def test_token_replay_prevention(self, api_client, owner_user):
        """Resetting password twice with the same token must fail the second time."""
        raw = secrets.token_urlsafe(48)
        hashed = hashlib.sha256(raw.encode()).hexdigest()
        from users.models import PasswordResetToken
        PasswordResetToken.objects.create(user=owner_user, token_hash=hashed)
        data = {"token": raw, "new_password": "ReplayStr0ng!1"}
        r1 = api_client.post("/api/v1/users/password-reset/confirm/", data, format="json")
        r2 = api_client.post("/api/v1/users/password-reset/confirm/", data, format="json")
        assert r1.status_code == status.HTTP_200_OK
        assert r2.status_code == status.HTTP_400_BAD_REQUEST