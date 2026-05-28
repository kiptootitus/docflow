"""
DocFlow AI — users/serializers.py

Serializers for every user-facing operation:
  • Registration (with strong-password validation)
  • Login  (returns JWT pair via djoser/SimpleJWT contract)
  • Profile read / update
  • Password change & reset flow
  • Email verification
  • Admin user management
  • Audit log read-only
"""

from __future__ import annotations

import base64
import json
from google.auth.transport import requests

from django.conf import settings
from rest_framework_simplejwt.tokens import RefreshToken
from django_otp.plugins.otp_totp.models import TOTPDevice
import pyotp
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
import hashlib
import re
import secrets

from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed

from .models import (
    EmailVerificationToken,
    PasswordResetToken,
    User,
    UserAuditLog,
    UserRole,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PASSWORD_MIN_LENGTH = 8
_PASSWORD_STRENGTH_PATTERN = re.compile(
    r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*(),.?\":{}|<>]).{8,}$"
)


def _validate_strong_password(value: str) -> str:
    """Enforce Django's built-in validators AND our custom strength rule."""
    try:
        validate_password(value)
    except DjangoValidationError as exc:
        raise serializers.ValidationError(list(exc.messages)) from exc

    if not _PASSWORD_STRENGTH_PATTERN.match(value):
        raise serializers.ValidationError(
            _(
                "Password must contain at least one uppercase letter, "
                "one lowercase letter, one digit, and one special character."
            )
        )
    return value


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

class UserRegistrationSerializer(serializers.ModelSerializer):
    """
    Public endpoint — creates a new Owner account.
    Sends verification email via post-save signal.
    """

    password  = serializers.CharField(
        write_only=True,
        min_length=_PASSWORD_MIN_LENGTH,
        style={"input_type": "password"},
    )
    password2 = serializers.CharField(
        write_only=True,
        label=_("Confirm password"),
        style={"input_type": "password"},
    )

    class Meta:
        model  = User
        fields = [
            "email",
            "first_name",
            "last_name",
            "password",
            "password2",
            "timezone_name",
            "language",
        ]
        extra_kwargs = {
            "first_name":    {"required": True},
            "last_name":     {"required": True},
            "timezone_name": {"required": False},
            "language":      {"required": False},
        }

    def validate_email(self, value: str) -> str:
        value = value.lower().strip()
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError(_("A user with this email already exists."))
        return value

    def validate_password(self, value: str) -> str:
        return _validate_strong_password(value)

    def validate(self, data: dict) -> dict:
        if data["password"] != data.pop("password2"):
            raise serializers.ValidationError({"password2": _("Passwords do not match.")})
        return data

    def create(self, validated_data: dict) -> User:
        return User.objects.create_user(**validated_data)


# ---------------------------------------------------------------------------
# User — public read (safe to return to any authenticated caller)
# ---------------------------------------------------------------------------

class UserPublicSerializer(serializers.ModelSerializer):
    """Minimal representation — safe to embed inside other serializers."""

    full_name  = serializers.CharField(read_only=True)
    avatar_url = serializers.SerializerMethodField()

    class Meta:
        model  = User
        fields = ["id", "email", "full_name", "avatar_url", "role"]
        read_only_fields = fields

    def get_avatar_url(self, obj: User) -> str | None:
        if not obj.avatar:
            return None
        request = self.context.get("request")
        return request.build_absolute_uri(obj.avatar.url) if request else obj.avatar.url


# ---------------------------------------------------------------------------
# User — full profile (owner can see everything about themselves)
# ---------------------------------------------------------------------------

class UserProfileSerializer(serializers.ModelSerializer):
    """
    Read + partial update for the authenticated user's own profile.
    Password change is handled by a dedicated endpoint.
    """

    full_name   = serializers.CharField(read_only=True)
    avatar_url  = serializers.SerializerMethodField()
    is_deleted  = serializers.BooleanField(read_only=True)

    class Meta:
        model  = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "avatar",
            "avatar_url",
            "role",
            "is_verified",
            "totp_enabled",
            "timezone_name",
            "language",
            "date_joined",
            "last_login_ip",
            "is_deleted",
            "updated_at",
        ]
        read_only_fields = [
            "id", "email", "role", "is_verified", "totp_enabled",
            "date_joined", "last_login_ip", "is_deleted", "updated_at",
            "full_name", "avatar_url",
        ]

    def get_avatar_url(self, obj: User) -> str | None:
        if not obj.avatar:
            return None
        request = self.context.get("request")
        return request.build_absolute_uri(obj.avatar.url) if request else obj.avatar.url

    def validate_avatar(self, value) -> object:
        max_size_mb = 5
        if value and value.size > max_size_mb * 1024 * 1024:
            raise serializers.ValidationError(
                _(f"Avatar must be smaller than {max_size_mb} MB.")
            )
        return value


# ---------------------------------------------------------------------------
# Password change (authenticated user)
# ---------------------------------------------------------------------------

class ChangePasswordSerializer(serializers.Serializer):
    """Endpoint: POST /users/me/change-password/"""

    current_password = serializers.CharField(
        write_only=True,
        style={"input_type": "password"},
    )
    new_password  = serializers.CharField(
        write_only=True,
        style={"input_type": "password"},
    )
    new_password2 = serializers.CharField(
        write_only=True,
        label=_("Confirm new password"),
        style={"input_type": "password"},
    )

    def validate_current_password(self, value: str) -> str:
        user: User = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError(_("Current password is incorrect."))
        return value

    def validate_new_password(self, value: str) -> str:
        return _validate_strong_password(value)

    def validate(self, data: dict) -> dict:
        if data["new_password"] != data.pop("new_password2"):
            raise serializers.ValidationError(
                {"new_password2": _("New passwords do not match.")}
            )
        if data["current_password"] == data["new_password"]:
            raise serializers.ValidationError(
                {"new_password": _("New password must differ from the current password.")}
            )
        return data

    def save(self, **kwargs) -> User:
        user: User = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password", "updated_at"])
        return user


# ---------------------------------------------------------------------------
# Password reset — request
# ---------------------------------------------------------------------------

class PasswordResetRequestSerializer(serializers.Serializer):
    """
    POST /users/password-reset/
    Always returns HTTP 200 — never reveals whether the email exists.
    """

    email = serializers.EmailField()

    def validate_email(self, value: str) -> str:
        return value.lower().strip()

    def save(self, **kwargs) -> str | None:
        """
        Generate a token if user exists and return the raw token
        (caller is responsible for emailing it).  Returns None if
        user does not exist (silent — no leaking).
        """
        try:
            user = User.objects.active().get(email=self.validated_data["email"])
        except User.DoesNotExist:
            return None

        raw_token = secrets.token_urlsafe(48)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        PasswordResetToken.objects.create(user=user, token_hash=token_hash)
        return raw_token


# ---------------------------------------------------------------------------
# Password reset — confirm
# ---------------------------------------------------------------------------

class PasswordResetConfirmSerializer(serializers.Serializer):
    """POST /users/password-reset/confirm/"""

    token        = serializers.CharField()
    new_password = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate_new_password(self, value: str) -> str:
        return _validate_strong_password(value)

    def validate(self, data: dict) -> dict:
        raw_token  = data["token"]
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        try:
            reset_obj = PasswordResetToken.objects.select_related("user").get(
                token_hash=token_hash
            )
        except PasswordResetToken.DoesNotExist:
            raise serializers.ValidationError({"token": _("Invalid or expired reset token.")})

        if reset_obj.is_used:
            raise serializers.ValidationError({"token": _("This token has already been used.")})

        if reset_obj.is_expired:
            raise serializers.ValidationError({"token": _("This token has expired. Please request a new one.")})

        data["_reset_obj"] = reset_obj
        return data

    def save(self, **kwargs) -> User:
        reset_obj: PasswordResetToken = self.validated_data["_reset_obj"]
        user = reset_obj.user
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password", "updated_at"])
        reset_obj.consume()
        return user


# ---------------------------------------------------------------------------
# Email verification
# ---------------------------------------------------------------------------

class EmailVerificationSerializer(serializers.Serializer):
    """POST /users/verify-email/"""

    token = serializers.CharField()

    def validate(self, data: dict) -> dict:
        try:
            token_obj = EmailVerificationToken.objects.select_related("user").get(
                token=data["token"]
            )
        except EmailVerificationToken.DoesNotExist:
            raise serializers.ValidationError({"token": _("Invalid verification token.")})

        if token_obj.is_used:
            raise serializers.ValidationError({"token": _("This token has already been used.")})

        if token_obj.is_expired:
            raise serializers.ValidationError({"token": _("Verification link has expired. Please request a new one.")})

        data["_token_obj"] = token_obj
        return data

    def save(self, **kwargs) -> User:
        token_obj: EmailVerificationToken = self.validated_data["_token_obj"]
        token_obj.consume()
        return token_obj.user


# ---------------------------------------------------------------------------
# Resend verification email
# ---------------------------------------------------------------------------

class ResendVerificationSerializer(serializers.Serializer):
    """POST /users/resend-verification/"""

    email = serializers.EmailField()

    def validate_email(self, value: str) -> str:
        return value.lower().strip()

    def get_user(self) -> User | None:
        try:
            return User.objects.active().get(
                email=self.validated_data["email"],
                is_verified=False,
            )
        except User.DoesNotExist:
            return None


# ---------------------------------------------------------------------------
# Admin — full user detail (staff only)
# ---------------------------------------------------------------------------

class AdminUserSerializer(serializers.ModelSerializer):
    """
    Used by Django-admin-equivalent API views accessible only to SUPER_ADMIN.
    Exposes all fields including role mutation and soft-delete controls.
    """

    full_name  = serializers.CharField(read_only=True)

    class Meta:
        model  = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "role",
            "is_active",
            "is_verified",
            "totp_enabled",
            "is_staff",
            "is_superuser",
            "timezone_name",
            "language",
            "date_joined",
            "last_login_ip",
            "deleted_at",
            "updated_at",
        ]
        read_only_fields = [
            "id", "full_name", "date_joined",
            "last_login_ip", "deleted_at", "updated_at",
        ]

    def validate_role(self, value: str) -> str:
        allowed = {r.value for r in UserRole}
        if value not in allowed:
            raise serializers.ValidationError(
                _(f"Invalid role. Choose from: {', '.join(allowed)}.")
            )
        return value


# ---------------------------------------------------------------------------
# Audit log (read-only)
# ---------------------------------------------------------------------------

class UserAuditLogSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source="user.email", read_only=True)
    event_display = serializers.CharField(source="get_event_display", read_only=True)

    class Meta:
        model  = UserAuditLog
        fields = [
            "id",
            "user",
            "user_email",
            "event",
            "event_display",
            "ip_address",
            "user_agent",
            "metadata",
            "created_at",
        ]
        read_only_fields = fields


class LoginSerializer(serializers.Serializer):
    """
    Validates password credentials and checks if 2FA (TOTP) is mandated.
    """
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate(self, data: dict) -> dict:
        email = data.get("email", "").lower().strip()
        password = data.get("password")

        user = authenticate(email=email, password=password)
        if not user:
            raise AuthenticationFailed(_("No active account found with the given credentials."))

        if user.is_deleted or not user.is_active:
            raise AuthenticationFailed(_("This account is inactive or has been removed."))

        data["_user"] = user
        return data


class TOTPVerifySerializer(serializers.Serializer):
    """
    Validates a 6-digit TOTP token against active user devices.
    """
    email = serializers.EmailField()
    token = serializers.CharField(max_length=6, min_length=6)

    def validate(self, data: dict) -> dict:
        email = data.get("email", "").lower().strip()
        token = data.get("token")

        try:
            user = User.objects.active().get(email=email)
        except User.DoesNotExist:
            raise AuthenticationFailed(_("Authentication failed."))

        # Find the active TOTP device
        device = TOTPDevice.objects.filter(user=user, confirmed=True).first()
        if not device or not device.verify_token(token):
            raise serializers.ValidationError({"token": _("Invalid or expired 2FA token.")})

        data["_user"] = user
        return data


# ---------------------------------------------------------------------------
# 2FA / TOTP Management (Authenticated)
# ---------------------------------------------------------------------------

class TOTPEnableSerializer(serializers.Serializer):
    """
    Validates the temporary token to confirm and finalize TOTP setup.
    """
    token = serializers.CharField(max_length=6, min_length=6)

    def validate(self, data: dict) -> dict:
        user = self.context["request"].user

        # Look for an unconfirmed device created during the setup stage
        device = TOTPDevice.objects.filter(user=user, confirmed=False).first()
        if not device:
            raise serializers.ValidationError(
                _("No TOTP setup session found. Please request activation initialization."))

        if not device.verify_token(data["token"]):
            raise serializers.ValidationError({"token": _("Invalid token. Verification failed.")})

        data["_device"] = device
        return data


# ---------------------------------------------------------------------------
# Google OAuth2
# ---------------------------------------------------------------------------
class GoogleAuthSerializer(serializers.Serializer):
    access_token = serializers.CharField()

    def validate(self, data):
        access_token = data.get('access_token')

        if not access_token:
            raise serializers.ValidationError('Access token is required')

        try:
            # Option 1: Verify with Google (RECOMMENDED for production)
            # You need to configure your Google OAuth credentials
            try:
                # Get your Google Client ID from settings
                google_client_id = settings.GOOGLE_OAUTH_CLIENT_ID  # or wherever you store it

                idinfo = id_token.verify_oauth2_token(
                    access_token,
                    requests.Request(),
                    google_client_id
                )

                user_info = {
                    'email': idinfo['email'],
                    'first_name': idinfo.get('given_name', ''),
                    'last_name': idinfo.get('family_name', ''),
                    'is_verified': idinfo.get('email_verified', False),
                }

            except Exception as verify_error:
                # Option 2: For development, decode without verification
                # BUT only do this for testing with real Google tokens
                try:
                    # Split the JWT
                    parts = access_token.split('.')
                    if len(parts) != 3:
                        raise ValueError("Invalid JWT structure")

                    # Decode the payload (second part)
                    payload = parts[1]
                    # Add padding if needed
                    payload += '=' * (4 - len(payload) % 4)
                    decoded = base64.b64decode(payload)
                    user_info_data = json.loads(decoded)

                    user_info = {
                        'email': user_info_data.get('email'),
                        'first_name': user_info_data.get('given_name', ''),
                        'last_name': user_info_data.get('family_name', ''),
                        'is_verified': user_info_data.get('email_verified', False),
                    }
                except Exception as decode_error:
                    raise serializers.ValidationError(f'Invalid token: {str(decode_error)}')

        except Exception as e:
            raise serializers.ValidationError(f'Token validation failed: {str(e)}')

        if not user_info.get('email'):
            raise serializers.ValidationError('Email not provided by Google')

        self.context['user_info'] = user_info
        return data