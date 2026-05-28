"""
DocFlow AI — notifications/views.py

REST API views for the notifications app.

Endpoints:
  GET    /notifications/                         NotificationListView
  GET    /notifications/<pk>/                    NotificationDetailView
  POST   /notifications/<pk>/read/               MarkReadView
  POST   /notifications/read-all/               MarkAllReadView
  DELETE /notifications/<pk>/                    DeleteNotificationView
  GET    /notifications/unread-count/            UnreadCountView

  GET    /notifications/preferences/            PreferenceListView
  PATCH  /notifications/preferences/<category>/ PreferenceUpdateView

  GET    /notifications/push-tokens/            PushTokenListView
  POST   /notifications/push-tokens/            PushTokenCreateView
  PATCH  /notifications/push-tokens/<pk>/       PushTokenUpdateView
  DELETE /notifications/push-tokens/<pk>/       PushTokenDeleteView

Design:
  • All endpoints require IsActiveUser (authenticated + not soft-deleted).
  • Users can only see/modify their own notifications and preferences.
  • No cross-user access — queryset always filtered by request.user.
  • Bulk mark-all-read uses .update() for efficiency (no per-row saves).
"""

from __future__ import annotations

import logging

from django.db.models import QuerySet
from django.utils.translation import gettext_lazy as _
from rest_framework import generics, serializers as drf_serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from users.permissions import IsActiveUser

from .models import (
    Channel,
    Notification,
    NotificationCategory,
    NotificationPreference,
    PushToken,
    PushTokenPlatform,
    MANDATORY_EMAIL_CATEGORIES,
)
from .serializers import (
    NotificationSerializer,
    NotificationPreferenceSerializer,
    PushTokenSerializer,
    PushTokenWriteSerializer,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Throttles
# ---------------------------------------------------------------------------

class PushTokenThrottle(UserRateThrottle):
    """Limit token registration to prevent abuse."""
    rate = "30/hour"


# ---------------------------------------------------------------------------
# Notification views
# ---------------------------------------------------------------------------

class NotificationListView(generics.ListAPIView):
    """
    GET /notifications/
    Returns the authenticated user's notifications, newest first.
    Supports ?unread_only=true and ?category=<value> filters.
    """
    permission_classes = [IsActiveUser]
    serializer_class   = NotificationSerializer

    def get_queryset(self) -> QuerySet:
        qs = (
            Notification.objects
            .filter(user=self.request.user)
            .order_by("-created_at")
        )

        unread_only = self.request.query_params.get("unread_only", "").lower()
        if unread_only in ("true", "1", "yes"):
            qs = qs.filter(read_at__isnull=True)

        category = self.request.query_params.get("category")
        if category:
            qs = qs.filter(category=category)

        priority = self.request.query_params.get("priority")
        if priority:
            qs = qs.filter(priority=priority)

        return qs


class NotificationDetailView(generics.RetrieveAPIView):
    """GET /notifications/<pk>/"""
    permission_classes = [IsActiveUser]
    serializer_class   = NotificationSerializer

    def get_object(self) -> Notification:
        try:
            return Notification.objects.get(
                pk=self.kwargs["pk"],
                user=self.request.user,
            )
        except (Notification.DoesNotExist, ValueError):
            raise NotFound(_("Notification not found."))


class MarkReadView(APIView):
    """POST /notifications/<pk>/read/"""
    permission_classes = [IsActiveUser]

    def post(self, request, pk: str, *args, **kwargs) -> Response:
        try:
            notif = Notification.objects.get(pk=pk, user=request.user)
        except (Notification.DoesNotExist, ValueError):
            raise NotFound(_("Notification not found."))

        notif.mark_read()
        return Response(
            {"detail": _("Notification marked as read."), "id": str(notif.pk)},
            status=status.HTTP_200_OK,
        )


class MarkAllReadView(APIView):
    """
    POST /notifications/read-all/
    Marks ALL unread notifications for the current user as read.
    Uses bulk .update() for efficiency.
    """
    permission_classes = [IsActiveUser]

    def post(self, request, *args, **kwargs) -> Response:
        from django.utils import timezone  # noqa: PLC0415
        updated = Notification.objects.filter(
            user=request.user,
            read_at__isnull=True,
        ).update(read_at=timezone.now())

        return Response(
            {"detail": _(f"{updated} notification(s) marked as read."), "count": updated},
            status=status.HTTP_200_OK,
        )


class DeleteNotificationView(APIView):
    """
    DELETE /notifications/<pk>/
    Removes a single notification for the current user.
    Note: audit-trail notifications (security events) cannot be deleted.
    """
    permission_classes = [IsActiveUser]

    UNDELETABLE_CATEGORIES = {
        NotificationCategory.SECURITY,
        NotificationCategory.PASSWORD_CHANGED,
        NotificationCategory.TWO_FA_ENABLED,
        NotificationCategory.TWO_FA_DISABLED,
    }

    def delete(self, request, pk: str, *args, **kwargs) -> Response:
        try:
            notif = Notification.objects.get(pk=pk, user=request.user)
        except (Notification.DoesNotExist, ValueError):
            raise NotFound(_("Notification not found."))

        if notif.category in self.UNDELETABLE_CATEGORIES:
            raise PermissionDenied(
                _("Security notifications cannot be deleted — they form part of your audit trail.")
            )

        notif.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class UnreadCountView(APIView):
    """
    GET /notifications/unread-count/
    Returns the number of unread notifications + per-priority breakdown.
    Lightweight endpoint polled by the frontend bell icon.
    """
    permission_classes = [IsActiveUser]

    def get(self, request, *args, **kwargs) -> Response:
        qs = Notification.objects.filter(user=request.user, read_at__isnull=True)
        total = qs.count()
        critical = qs.filter(priority="critical").count()
        high     = qs.filter(priority="high").count()

        return Response({
            "total":    total,
            "critical": critical,
            "high":     high,
            "normal":   total - critical - high,
        })


# ---------------------------------------------------------------------------
# Preference views
# ---------------------------------------------------------------------------

class PreferenceListView(generics.ListAPIView):
    """
    GET /notifications/preferences/
    Returns all category preferences for the current user.
    Categories with no explicit preference show the system default.
    """
    permission_classes = [IsActiveUser]
    serializer_class   = NotificationPreferenceSerializer

    def get_queryset(self) -> QuerySet:
        return NotificationPreference.objects.filter(user=self.request.user)

    def list(self, request, *args, **kwargs):
        """
        Override to merge user prefs with defaults for categories that
        have no explicit preference row — so the frontend always sees a
        full list of all categories.
        """
        from .models import CATEGORY_DEFAULTS  # noqa: PLC0415

        existing = {
            p.category: p
            for p in self.get_queryset()
        }

        result = []
        for cat_value, _ in NotificationCategory.choices:
            if cat_value in existing:
                pref = existing[cat_value]
                result.append({
                    "id":          str(pref.pk),
                    "category":    cat_value,
                    "channels":    pref.channels,
                    "email":       bool(pref.channels & Channel.EMAIL),
                    "push":        bool(pref.channels & Channel.PUSH),
                    "in_app":      bool(pref.channels & Channel.IN_APP),
                    "is_default":  False,
                    "is_mandatory_email": cat_value in MANDATORY_EMAIL_CATEGORIES,
                })
            else:
                default_channels = CATEGORY_DEFAULTS.get(cat_value, Channel.IN_APP)
                result.append({
                    "id":          None,
                    "category":    cat_value,
                    "channels":    default_channels,
                    "email":       bool(default_channels & Channel.EMAIL),
                    "push":        bool(default_channels & Channel.PUSH),
                    "in_app":      bool(default_channels & Channel.IN_APP),
                    "is_default":  True,
                    "is_mandatory_email": cat_value in MANDATORY_EMAIL_CATEGORIES,
                })

        return Response(result)


class PreferenceUpdateView(APIView):
    """
    PATCH /notifications/preferences/<category>/
    Body: {"email": true, "push": false, "in_app": true}

    Creates or updates the preference row.
    Enforces mandatory email for security categories.
    """
    permission_classes = [IsActiveUser]

    def patch(self, request, category: str, *args, **kwargs) -> Response:
        # Validate category
        valid_cats = {c for c, _ in NotificationCategory.choices}
        if category not in valid_cats:
            raise NotFound(_(f"Category '{category}' not found."))

        email  = request.data.get("email")
        push   = request.data.get("push")
        in_app = request.data.get("in_app")

        # Build new channel bitmask
        pref, _ = NotificationPreference.objects.get_or_create(
            user=request.user,
            category=category,
            defaults={"channels": NotificationPreference._meta.get_field("channels").default},
        )

        channels = pref.channels
        if email is not None:
            if email:
                channels = channels | int(Channel.EMAIL)
            else:
                # Cannot disable mandatory email categories
                if category in MANDATORY_EMAIL_CATEGORIES:
                    raise PermissionDenied(
                        _("Email notifications for security events cannot be disabled.")
                    )
                channels = channels & ~int(Channel.EMAIL)

        if push is not None:
            if push:
                channels = channels | int(Channel.PUSH)
            else:
                channels = channels & ~int(Channel.PUSH)

        if in_app is not None:
            if in_app:
                channels = channels | int(Channel.IN_APP)
            else:
                channels = channels & ~int(Channel.IN_APP)

        pref.channels = channels
        pref.save(update_fields=["channels", "updated_at"])

        return Response({
            "category": category,
            "channels": channels,
            "email":    bool(channels & Channel.EMAIL),
            "push":     bool(channels & Channel.PUSH),
            "in_app":   bool(channels & Channel.IN_APP),
            "is_mandatory_email": category in MANDATORY_EMAIL_CATEGORIES,
        })


# ---------------------------------------------------------------------------
# Push token views
# ---------------------------------------------------------------------------

class PushTokenListView(generics.ListAPIView):
    """GET /notifications/push-tokens/ — list current user's registered devices."""
    permission_classes = [IsActiveUser]
    serializer_class   = PushTokenSerializer

    def get_queryset(self) -> QuerySet:
        return PushToken.objects.filter(user=self.request.user, is_active=True)


class PushTokenCreateView(generics.CreateAPIView):
    """
    POST /notifications/push-tokens/
    Register a new device push token.
    If the token already exists (same device, app reinstalled) it is
    reactivated and its device_name updated.
    """
    permission_classes = [IsActiveUser]
    serializer_class   = PushTokenWriteSerializer
    throttle_classes   = [PushTokenThrottle]

    def create(self, request, *args, **kwargs) -> Response:
        token_str = request.data.get("token", "").strip()
        platform  = request.data.get("platform", PushTokenPlatform.EXPO)
        device_name = request.data.get("device_name", "")

        if not token_str:
            return Response(
                {"token": [_("A push token is required.")]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Upsert — deactivate any existing token with this value for other users
        # (device was transferred), then create/update for current user
        PushToken.objects.filter(
            token=token_str
        ).exclude(user=request.user).update(is_active=False)

        push_token, created = PushToken.objects.update_or_create(
            user=request.user,
            token=token_str,
            defaults={
                "platform":    platform,
                "device_name": device_name,
                "is_active":   True,
            },
        )

        serializer = PushTokenSerializer(push_token)
        resp_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(serializer.data, status=resp_status)


class PushTokenUpdateView(generics.UpdateAPIView):
    """
    PATCH /notifications/push-tokens/<pk>/
    Update device name or refresh token string (token rotation on app relaunch).
    """
    permission_classes = [IsActiveUser]
    serializer_class   = PushTokenWriteSerializer
    http_method_names  = ["patch", "head", "options"]

    def get_object(self) -> PushToken:
        try:
            return PushToken.objects.get(pk=self.kwargs["pk"], user=self.request.user)
        except (PushToken.DoesNotExist, ValueError):
            raise NotFound(_("Push token not found."))


class PushTokenDeleteView(APIView):
    """
    DELETE /notifications/push-tokens/<pk>/
    Deactivate a device push token (logout / unregister device).
    """
    permission_classes = [IsActiveUser]

    def delete(self, request, pk: str, *args, **kwargs) -> Response:
        try:
            token = PushToken.objects.get(pk=pk, user=request.user)
        except (PushToken.DoesNotExist, ValueError):
            raise NotFound(_("Push token not found."))

        token.deactivate()
        return Response(status=status.HTTP_204_NO_CONTENT)