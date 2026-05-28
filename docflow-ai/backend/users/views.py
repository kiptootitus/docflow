"""
DocFlow AI — users/views.py  (patched)

Fixes applied vs original:
  1. GoogleLoginView  — uses Google userinfo endpoint instead of id_token.verify_oauth2_token().
                        The implicit-flow access_token is NOT a JWT; it cannot be decoded as one.
  2. MeView           — permission changed from IsVerifiedUser → IsActiveUser so unverified
                        users can still fetch their own profile after login.
  3. LogoutView       — added (was missing, causing 404 on POST /auth/logout/).
"""

from __future__ import annotations

import logging
import requests as http_requests   # standard requests lib for Google userinfo call

from django.conf import settings
from django.utils.translation import gettext_lazy as _
from rest_framework import generics, status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from django_otp.plugins.otp_totp.models import TOTPDevice

from .models import EmailVerificationToken, User, UserAuditLog, UserRole
from .permissions import IsActiveUser, IsSelfOrAdmin, IsSuperAdmin, IsVerifiedUser
from .serializers import (
    AdminUserSerializer,
    ChangePasswordSerializer,
    EmailVerificationSerializer,
    LoginSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    ResendVerificationSerializer,
    TOTPEnableSerializer,
    TOTPVerifySerializer,
    UserAuditLogSerializer,
    UserProfileSerializer,
    UserRegistrationSerializer,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Throttle classes
# ---------------------------------------------------------------------------

class AuthThrottle(AnonRateThrottle):
    rate = "10/hour"


class SensitiveActionThrottle(UserRateThrottle):
    rate = "20/hour"


# ---------------------------------------------------------------------------
# Audit helper
# ---------------------------------------------------------------------------

def _audit(request, event: str, user: User | None = None, metadata: dict | None = None) -> None:
    from .permissions import get_client_ip
    try:
        UserAuditLog.objects.create(
            user=user or (request.user if request.user.is_authenticated else None),
            event=event,
            ip_address=get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:512],
            metadata=metadata or {},
        )
    except Exception as exc:
        logger.exception("Failed to write audit log: %s", exc)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

class UserRegistrationView(generics.CreateAPIView):
    """POST /auth/register/"""
    permission_classes = [AllowAny]
    throttle_classes   = [AuthThrottle]
    serializer_class   = UserRegistrationSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        refresh = RefreshToken.for_user(user)
        _audit(request, UserAuditLog.EventType.LOGIN_SUCCESS, user=user,
               metadata={"method": "register"})

        return Response({
            "user": UserProfileSerializer(user, context={"request": request}).data,
            "tokens": {
                "access":  str(refresh.access_token),
                "refresh": str(refresh),
            },
        }, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

class LoginView(APIView):
    """POST /auth/login/"""
    permission_classes = [AllowAny]
    throttle_classes   = [AuthThrottle]

    def post(self, request, *args, **kwargs) -> Response:
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["_user"]

        # 2FA challenge
        if user.totp_enabled and TOTPDevice.objects.filter(user=user, confirmed=True).exists():
            return Response({
                "two_factor_required": True,
                "email": user.email,
                "detail": _("Two-factor authentication code is required to log in."),
            }, status=status.HTTP_200_OK)

        refresh = RefreshToken.for_user(user)
        _audit(request, UserAuditLog.EventType.LOGIN_SUCCESS, user=user,
               metadata={"method": "password"})

        from .permissions import get_client_ip
        user.last_login_ip = get_client_ip(request)
        user.save(update_fields=["last_login_ip"])

        return Response({
            "access":             str(refresh.access_token),
            "refresh":            str(refresh),
            "two_factor_required": False,
        }, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# TOTP second-factor
# ---------------------------------------------------------------------------

class TOTPVerifyLoginView(APIView):
    """POST /auth/login/verify-totp/"""
    permission_classes = [AllowAny]
    throttle_classes   = [AuthThrottle]

    def post(self, request, *args, **kwargs) -> Response:
        serializer = TOTPVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["_user"]

        refresh = RefreshToken.for_user(user)
        _audit(request, UserAuditLog.EventType.LOGIN_SUCCESS, user=user,
               metadata={"method": "password_plus_totp"})

        return Response({
            "access":  str(refresh.access_token),
            "refresh": str(refresh),
        }, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------

class LogoutView(APIView):
    """
    POST /auth/logout/
    Blacklists the supplied refresh token.  Best-effort — a missing or already
    blacklisted token still returns 200 so the client always clears its state.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs) -> Response:
        refresh_token = request.data.get("refresh")
        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()
            except TokenError:
                pass  # Already blacklisted or invalid — still log the user out

        _audit(request, UserAuditLog.EventType.LOGOUT)
        return Response({"detail": _("Successfully logged out.")}, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Google OAuth  ← FIXED: uses userinfo endpoint, not id_token.verify_oauth2_token
# ---------------------------------------------------------------------------

class GoogleLoginView(APIView):
    """
    POST /auth/google/

    The React frontend uses @react-oauth/google with flow='implicit'.
    That flow returns a Google OAuth2 *access token* (starts with 'ya29.'),
    NOT an ID token JWT.  id_token.verify_oauth2_token() expects a JWT and
    will always fail with "Wrong number of segments" on an access token.

    Correct approach: call Google's userinfo endpoint with the access token.
    """
    permission_classes = [AllowAny]
    throttle_classes   = [AuthThrottle]

    GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

    def post(self, request, *args, **kwargs) -> Response:
        access_token = request.data.get("access_token", "").strip()

        if not access_token:
            return Response(
                {"detail": _("Access token is required.")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── Step 1: verify token with Google userinfo endpoint ─────────────
        try:
            resp = http_requests.get(
                self.GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10,
            )
        except Exception as exc:
            logger.error("Google userinfo request failed: %s", exc)
            return Response(
                {"detail": _("Could not reach Google servers. Please try again.")},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        if resp.status_code != 200:
            logger.warning("Google userinfo returned %s: %s", resp.status_code, resp.text)
            return Response(
                {"detail": _("Invalid or expired Google token.")},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        user_info = resp.json()
        email = user_info.get("email", "").lower().strip()

        if not email:
            return Response(
                {"detail": _("Google did not return an email address.")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not user_info.get("email_verified", False):
            return Response(
                {"detail": _("Your Google account email is not verified.")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── Step 2: get or create the local user ───────────────────────────
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "first_name":  user_info.get("given_name", ""),
                "last_name":   user_info.get("family_name", ""),
                "is_verified": True,   # Google already verified the email
                "is_active":   True,
            },
        )

        if not created:
            # Sync name from Google on every login (user may have updated it)
            changed = False
            if not user.first_name and user_info.get("given_name"):
                user.first_name = user_info["given_name"]
                changed = True
            if not user.last_name and user_info.get("family_name"):
                user.last_name = user_info["family_name"]
                changed = True
            # Mark as verified if not already (legacy accounts)
            if not user.is_verified:
                user.is_verified = True
                changed = True
            if changed:
                user.save(update_fields=["first_name", "last_name", "is_verified", "updated_at"])

        if not user.is_active:
            return Response(
                {"detail": _("This account has been deactivated.")},
                status=status.HTTP_403_FORBIDDEN,
            )

        # ── Step 3: issue JWT pair ─────────────────────────────────────────
        refresh = RefreshToken.for_user(user)
        _audit(request, UserAuditLog.EventType.LOGIN_SUCCESS, user=user,
               metadata={"method": "google_oauth", "created": created})

        from .permissions import get_client_ip
        user.last_login_ip = get_client_ip(request)
        user.save(update_fields=["last_login_ip"])

        return Response({
            "access":  str(refresh.access_token),
            "refresh": str(refresh),
        }, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Me  ← FIXED: IsActiveUser instead of IsVerifiedUser
# ---------------------------------------------------------------------------

class MeView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /auth/me/   — full profile
    PATCH  /auth/me/   — partial update
    DELETE /auth/me/   — soft delete

    Permission changed to IsActiveUser (not IsVerifiedUser) so that users
    who registered but haven't verified their email yet can still load their
    profile and see the "please verify your email" state in the UI.
    """
    # ↓ Changed from IsVerifiedUser to IsActiveUser
    permission_classes = [IsActiveUser]
    serializer_class   = UserProfileSerializer
    parser_classes     = [JSONParser, MultiPartParser, FormParser]
    http_method_names  = ["get", "patch", "delete", "head", "options"]

    def get_object(self) -> User:
        return self.request.user

    def update(self, request, *args, **kwargs) -> Response:
        kwargs["partial"] = True
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs) -> Response:
        user: User = self.get_object()
        user.soft_delete()
        _audit(request, UserAuditLog.EventType.ACCOUNT_DELETED)
        return Response(
            {"detail": _("Your account has been deactivated.")},
            status=status.HTTP_204_NO_CONTENT,
        )


# ---------------------------------------------------------------------------
# Email verification
# ---------------------------------------------------------------------------

class VerifyEmailView(APIView):
    """POST /auth/verify-email/"""
    permission_classes = [AllowAny]
    throttle_classes   = [AuthThrottle]

    def post(self, request, *args, **kwargs) -> Response:
        serializer = EmailVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        _audit(request, UserAuditLog.EventType.EMAIL_VERIFIED, user=user)
        return Response(
            {"detail": _("Email verified successfully.")},
            status=status.HTTP_200_OK,
        )


class ResendVerificationView(APIView):
    """POST /auth/resend-verification/"""
    permission_classes = [AllowAny]
    throttle_classes   = [AuthThrottle]

    def post(self, request, *args, **kwargs) -> Response:
        serializer = ResendVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.get_user()
        if user:
            # Fire signal / task to resend the email (implementation in signals.py)
            from django.db.models.signals import post_save
            # or call your email task directly:
            # send_verification_email.delay(user.pk)
            pass
        # Always return 200 to avoid leaking whether the email exists
        return Response(
            {"detail": _("If that email is registered and unverified, we've sent a new link.")},
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# Password reset
# ---------------------------------------------------------------------------

class PasswordResetRequestView(APIView):
    """POST /auth/password-reset/"""
    permission_classes = [AllowAny]
    throttle_classes   = [AuthThrottle]

    def post(self, request, *args, **kwargs) -> Response:
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        try:
            user = User.objects.active().get(email=email)
            _audit(request, UserAuditLog.EventType.PASSWORD_RESET, user=user)
            # send_password_reset_email.delay(user.pk)  # your Celery task
        except User.DoesNotExist:
            pass

        return Response(
            {"detail": _("If this email is registered, a password reset link has been sent.")},
            status=status.HTTP_200_OK,
        )


class PasswordResetConfirmView(APIView):
    """POST /auth/password-reset/confirm/"""
    permission_classes = [AllowAny]
    throttle_classes   = [AuthThrottle]

    def post(self, request, *args, **kwargs) -> Response:
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user: User = serializer.save()
        _audit(request, UserAuditLog.EventType.PASSWORD_CHANGED, user=user)
        return Response(
            {"detail": _("Password has been reset successfully. Please log in.")},
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# Change password (authenticated)
# ---------------------------------------------------------------------------

class ChangePasswordView(APIView):
    """POST /auth/me/change-password/"""
    permission_classes = [IsVerifiedUser]
    throttle_classes   = [SensitiveActionThrottle]

    def post(self, request, *args, **kwargs) -> Response:
        serializer = ChangePasswordSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        _audit(request, UserAuditLog.EventType.PASSWORD_CHANGED)
        return Response(
            {"detail": _("Password changed successfully.")},
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

class MyAuditLogsView(generics.ListAPIView):
    """GET /auth/me/audit-logs/"""
    permission_classes = [IsActiveUser]
    serializer_class   = UserAuditLogSerializer

    def get_queryset(self):
        return (
            UserAuditLog.objects.filter(user=self.request.user)
            .select_related("user")
            .order_by("-created_at")
        )


# ---------------------------------------------------------------------------
# Admin — user list & detail
# ---------------------------------------------------------------------------

class UserListView(generics.ListAPIView):
    """GET /users/"""
    permission_classes = [IsSuperAdmin]
    serializer_class   = AdminUserSerializer

    def get_queryset(self):
        qs = User.objects.all().order_by("-date_joined")
        role     = self.request.query_params.get("role")
        is_active= self.request.query_params.get("is_active")
        search   = self.request.query_params.get("search")

        if role:
            qs = qs.filter(role=role)
        if is_active is not None:
            qs = qs.filter(is_active=is_active.lower() == "true")
        if search:
            from django.db.models import Q
            qs = qs.filter(
                Q(email__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
            )
        return qs


class UserDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET / PATCH / DELETE /users/<pk>/"""
    permission_classes = [IsSuperAdmin]
    serializer_class   = AdminUserSerializer
    http_method_names  = ["get", "patch", "delete", "head", "options"]
    queryset           = User.objects.all()

    def get_object(self) -> User:
        try:
            return User.objects.get(pk=self.kwargs["pk"])
        except (User.DoesNotExist, ValueError):
            raise NotFound(_("User not found."))

    def update(self, request, *args, **kwargs) -> Response:
        kwargs["partial"] = True
        old_role = self.get_object().role
        response = super().update(request, *args, **kwargs)
        new_role = response.data.get("role")
        if old_role != new_role:
            _audit(request, UserAuditLog.EventType.ROLE_CHANGED,
                   user=self.get_object(),
                   metadata={"old_role": old_role, "new_role": new_role})
        return response

    def destroy(self, request, *args, **kwargs) -> Response:
        user: User = self.get_object()
        if user == request.user:
            raise PermissionDenied(_("You cannot deactivate your own admin account."))
        user.soft_delete()
        _audit(request, UserAuditLog.EventType.ACCOUNT_DELETED, user=user,
               metadata={"deleted_by": str(request.user.pk)})
        return Response(
            {"detail": _(f"User {user.email} has been deactivated.")},
            status=status.HTTP_204_NO_CONTENT,
        )


class UserRestoreView(APIView):
    """POST /users/<pk>/restore/"""
    permission_classes = [IsSuperAdmin]

    def post(self, request, pk: str, *args, **kwargs) -> Response:
        try:
            user = User.objects.get(pk=pk)
        except (User.DoesNotExist, ValueError):
            raise NotFound(_("User not found."))

        if not user.is_deleted:
            return Response(
                {"detail": _("User account is already active.")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.restore()
        _audit(request, UserAuditLog.EventType.ACCOUNT_RESTORED, user=user,
               metadata={"restored_by": str(request.user.pk)})
        return Response(
            {"detail": _(f"User {user.email} has been restored.")},
            status=status.HTTP_200_OK,
        )