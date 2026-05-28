"""
DocFlow AI — notifications/push.py

Push notification dispatcher supporting:
  • Expo Push Notification Service (primary — covers iOS + Android via Expo SDK)
  • Firebase Cloud Messaging / FCM  (direct Android — fallback / enterprise)
  • Apple Push Notification Service / APNS  (direct iOS — fallback / enterprise)
  • Web Push (future — placeholder)

Architecture:
  ┌──────────────────────────────────────────────────────────────────────────┐
  │  PushDispatcher                                                          │
  │    send_to_user(user, payload)                                           │
  │      → queries all active PushToken rows for user                       │
  │      → groups tokens by platform                                         │
  │      → dispatches to the right provider                                  │
  │      → handles receipts / dead-token cleanup                             │
  │                                                                          │
  │  ExpoProvider    — wraps the Expo push API (batch up to 100/request)    │
  │  FCMProvider     — wraps google-auth + FCM HTTP v1                      │
  │  APNSProvider    — wraps httpx + APNS/2 HTTP/2                          │
  └──────────────────────────────────────────────────────────────────────────┘

Expo Push docs:    https://docs.expo.dev/push-notifications/sending-notifications/
FCM HTTP v1 docs:  https://firebase.google.com/docs/cloud-messaging/http-server-ref
APNS docs:         https://developer.apple.com/documentation/usernotifications

Required settings:
    EXPO_ACCESS_TOKEN     (optional — for enhanced Expo delivery)
    FCM_SERVICE_ACCOUNT   (path to Google service-account JSON or dict)
    APNS_KEY_ID           Apple Key ID
    APNS_TEAM_ID          Apple Team ID
    APNS_AUTH_KEY_PATH    Path to .p8 key file
    APNS_BUNDLE_ID        e.g. "com.docflowai.app"
    APNS_USE_SANDBOX      True in development, False in production
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)

EXPO_PUSH_URL  = "https://exp.host/--/api/v2/push/send"
EXPO_RECEIPT_URL = "https://exp.host/--/api/v2/push/getReceipts"
FCM_SEND_URL   = "https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
APNS_HOST_PROD = "https://api.push.apple.com"
APNS_HOST_SAND = "https://api.sandbox.push.apple.com"

# Maximum tokens per Expo batch request
EXPO_BATCH_SIZE = 100


# ---------------------------------------------------------------------------
# Push payload dataclass
# ---------------------------------------------------------------------------

@dataclass
class PushPayload:
    """
    Normalised push payload — provider adapters translate this to their
    native format.
    """
    title:      str
    body:       str
    data:       dict[str, Any]   = field(default_factory=dict)
    badge:      int | None        = None     # iOS badge count
    sound:      str               = "default"
    category:   str               = ""       # Maps to NotificationCategory
    priority:   str               = "normal" # "normal" | "high" | "critical"
    # Deep-link URL for tap action
    action_url: str               = ""
    # Collapse key — replaces outstanding notification of same key on device
    collapse_id: str              = ""
    # TTL in seconds (0 = don't store if device offline)
    ttl:         int              = 86_400    # 24 hours default

    @property
    def expo_priority(self) -> str:
        return "high" if self.priority in ("high", "critical") else "normal"

    @property
    def apns_priority(self) -> str:
        return "10" if self.priority in ("high", "critical") else "5"

    @property
    def fcm_priority(self) -> str:
        return "high" if self.priority in ("high", "critical") else "normal"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class PushDispatchError(Exception):
    """Raised for transient provider errors — Celery will retry."""


class DeadTokenError(Exception):
    """Raised when a token is definitely invalid — caller should deactivate it."""


# ---------------------------------------------------------------------------
# Expo Provider
# ---------------------------------------------------------------------------

class ExpoProvider:
    """
    Sends push notifications via the Expo Push API.
    Supports batching up to EXPO_BATCH_SIZE tokens per request.
    Returns a list of (token, ticket_id_or_None) tuples.
    """

    @classmethod
    def send_batch(
        cls,
        tokens: list[str],
        payload: PushPayload,
    ) -> list[dict]:
        """
        Send to a batch of Expo tokens.
        Returns raw Expo ticket list.
        Raises PushDispatchError on HTTP / network failure.
        """
        import httpx  # noqa: PLC0415

        messages = [
            cls._build_message(token, payload)
            for token in tokens
        ]

        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        access_token = getattr(settings, "EXPO_ACCESS_TOKEN", None)
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"

        try:
            response = httpx.post(
                EXPO_PUSH_URL,
                json=messages,
                headers=headers,
                timeout=15.0,
            )
            response.raise_for_status()
            data = response.json()
            tickets = data.get("data", [])
            logger.info(
                "ExpoProvider: sent %d messages, got %d tickets",
                len(messages), len(tickets),
            )
            return tickets
        except httpx.HTTPStatusError as exc:
            logger.exception("ExpoProvider: HTTP error %s", exc.response.status_code)
            raise PushDispatchError(f"Expo HTTP {exc.response.status_code}") from exc
        except Exception as exc:
            logger.exception("ExpoProvider: unexpected error: %s", exc)
            raise PushDispatchError(str(exc)) from exc

    @classmethod
    def fetch_receipts(cls, ticket_ids: list[str]) -> dict[str, dict]:
        """
        Poll Expo for receipt status of previously sent tickets.
        Returns {receipt_id: receipt_obj} dict.
        Used by the hourly receipt-check Celery task.
        """
        import httpx  # noqa: PLC0415

        if not ticket_ids:
            return {}

        headers = {"Content-Type": "application/json"}
        access_token = getattr(settings, "EXPO_ACCESS_TOKEN", None)
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"

        try:
            response = httpx.post(
                EXPO_RECEIPT_URL,
                json={"ids": ticket_ids},
                headers=headers,
                timeout=15.0,
            )
            response.raise_for_status()
            return response.json().get("data", {})
        except Exception as exc:
            logger.exception("ExpoProvider.fetch_receipts: %s", exc)
            return {}

    @staticmethod
    def _build_message(token: str, payload: PushPayload) -> dict:
        msg: dict[str, Any] = {
            "to":       token,
            "title":    payload.title,
            "body":     payload.body,
            "data":     {
                **payload.data,
                "category":   payload.category,
                "action_url": payload.action_url,
            },
            "sound":    payload.sound,
            "priority": payload.expo_priority,
            "ttl":      payload.ttl,
            "channelId": _category_to_android_channel(payload.category),
        }
        if payload.badge is not None:
            msg["badge"] = payload.badge
        if payload.collapse_id:
            msg["collapseKey"] = payload.collapse_id
        return msg

    @staticmethod
    def is_dead_token_error(ticket: dict) -> bool:
        """Return True if the Expo ticket indicates the token is invalid."""
        if ticket.get("status") == "error":
            details = ticket.get("details", {})
            return details.get("error") in ("DeviceNotRegistered", "InvalidCredentials")
        return False


# ---------------------------------------------------------------------------
# FCM Provider (HTTP v1)
# ---------------------------------------------------------------------------

class FCMProvider:
    """
    Sends to a single FCM registration token using the HTTP v1 API.
    Obtains a short-lived OAuth2 access token from the service account.
    """

    _access_token: str | None = None
    _token_expiry: float       = 0.0

    @classmethod
    def _get_access_token(cls) -> str:
        """Fetch (or return cached) OAuth2 access token for FCM."""
        if cls._access_token and time.time() < cls._token_expiry - 60:
            return cls._access_token

        try:
            from google.oauth2 import service_account  # noqa: PLC0415
            from google.auth.transport.requests import Request as GRequest  # noqa: PLC0415

            sa_config = getattr(settings, "FCM_SERVICE_ACCOUNT", None)
            if not sa_config:
                raise PushDispatchError("FCM_SERVICE_ACCOUNT not configured")

            if isinstance(sa_config, str):
                with open(sa_config) as f:
                    sa_config = json.load(f)

            creds = service_account.Credentials.from_service_account_info(
                sa_config,
                scopes=["https://www.googleapis.com/auth/firebase.messaging"],
            )
            creds.refresh(GRequest())
            cls._access_token = creds.token
            cls._token_expiry  = creds.expiry.timestamp() if creds.expiry else time.time() + 3600
            return cls._access_token
        except Exception as exc:
            raise PushDispatchError(f"FCM auth failed: {exc}") from exc

    @classmethod
    def send(cls, token: str, payload: PushPayload) -> str | None:
        """
        Send to one FCM token. Returns FCM message name on success.
        Raises DeadTokenError if token is invalid.
        Raises PushDispatchError on transient failure.
        """
        import httpx  # noqa: PLC0415

        sa_config = getattr(settings, "FCM_SERVICE_ACCOUNT", None)
        if not sa_config:
            logger.warning("FCMProvider: FCM_SERVICE_ACCOUNT not set — skipping.")
            return None

        project_id = sa_config.get("project_id") if isinstance(sa_config, dict) else "docflow-ai"
        url = FCM_SEND_URL.format(project_id=project_id)

        message = {
            "message": {
                "token": token,
                "notification": {
                    "title": payload.title,
                    "body":  payload.body,
                },
                "android": {
                    "priority": payload.fcm_priority,
                    "ttl":      f"{payload.ttl}s",
                    "notification": {
                        "channel_id": _category_to_android_channel(payload.category),
                        "sound":      payload.sound,
                    },
                },
                "data": {
                    k: str(v) for k, v in {
                        **payload.data,
                        "category":   payload.category,
                        "action_url": payload.action_url,
                    }.items()
                },
            }
        }

        try:
            access_token = cls._get_access_token()
            response = httpx.post(
                url,
                json=message,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type":  "application/json",
                },
                timeout=15.0,
            )

            if response.status_code == 404:
                raise DeadTokenError(f"FCM token not found: {token[:20]}...")
            if response.status_code == 400:
                body = response.json()
                if "INVALID_ARGUMENT" in str(body):
                    raise DeadTokenError(f"FCM invalid token: {token[:20]}...")

            response.raise_for_status()
            result = response.json()
            return result.get("name")

        except (DeadTokenError, PushDispatchError):
            raise
        except httpx.HTTPStatusError as exc:
            raise PushDispatchError(f"FCM HTTP {exc.response.status_code}") from exc
        except Exception as exc:
            raise PushDispatchError(str(exc)) from exc


# ---------------------------------------------------------------------------
# APNS Provider
# ---------------------------------------------------------------------------

class APNSProvider:
    """
    Sends to Apple Push Notification Service using HTTP/2 (token-based auth).
    Uses httpx with HTTP/2 support.
    """

    _jwt_token: str | None  = None
    _jwt_expiry: float       = 0.0

    @classmethod
    def _get_jwt(cls) -> str:
        """Generate or return cached APNS JWT (expires after 50 minutes)."""
        if cls._jwt_token and time.time() < cls._jwt_expiry - 60:
            return cls._jwt_token

        try:
            import jwt as pyjwt  # noqa: PLC0415

            key_id   = getattr(settings, "APNS_KEY_ID", "")
            team_id  = getattr(settings, "APNS_TEAM_ID", "")
            key_path = getattr(settings, "APNS_AUTH_KEY_PATH", "")

            if not all([key_id, team_id, key_path]):
                raise PushDispatchError("APNS credentials not fully configured (APNS_KEY_ID, APNS_TEAM_ID, APNS_AUTH_KEY_PATH).")

            with open(key_path) as f:
                private_key = f.read()

            now = int(time.time())
            token = pyjwt.encode(
                {"iss": team_id, "iat": now},
                private_key,
                algorithm="ES256",
                headers={"kid": key_id},
            )
            cls._jwt_token  = token if isinstance(token, str) else token.decode()
            cls._jwt_expiry = now + 3000  # 50 minutes
            return cls._jwt_token

        except (PushDispatchError, FileNotFoundError):
            raise
        except Exception as exc:
            raise PushDispatchError(f"APNS JWT generation failed: {exc}") from exc

    @classmethod
    def send(cls, device_token: str, payload: PushPayload) -> None:
        """
        Send a push to one APNS device token.
        Raises DeadTokenError if device is unregistered.
        Raises PushDispatchError on transient failure.
        """
        bundle_id  = getattr(settings, "APNS_BUNDLE_ID", "com.docflowai.app")
        use_sandbox= getattr(settings, "APNS_USE_SANDBOX", False)
        host       = APNS_HOST_SAND if use_sandbox else APNS_HOST_PROD
        url        = f"{host}/3/device/{device_token}"

        apns_payload = {
            "aps": {
                "alert": {"title": payload.title, "body": payload.body},
                "sound": payload.sound,
                "badge": payload.badge,
                "content-available": 1,
                "mutable-content":   1,
                "category":          payload.category.upper(),
            },
            **payload.data,
            "action_url": payload.action_url,
            "category":   payload.category,
        }
        if payload.badge is None:
            del apns_payload["aps"]["badge"]

        headers = {
            "authorization":  f"bearer {cls._get_jwt()}",
            "apns-topic":     bundle_id,
            "apns-push-type": "alert",
            "apns-priority":  payload.apns_priority,
            "apns-expiration": str(int(time.time()) + payload.ttl),
        }
        if payload.collapse_id:
            headers["apns-collapse-id"] = payload.collapse_id

        try:
            import httpx  # noqa: PLC0415
            # http2=True requires httpx[http2]
            with httpx.Client(http2=True, timeout=15.0) as client:
                response = client.post(url, json=apns_payload, headers=headers)

            if response.status_code == 200:
                return  # Success

            body = {}
            try:
                body = response.json()
            except Exception:
                pass

            reason = body.get("reason", "")
            if reason in ("BadDeviceToken", "Unregistered", "DeviceTokenNotForTopic"):
                raise DeadTokenError(f"APNS dead token: {reason}")
            raise PushDispatchError(f"APNS error {response.status_code}: {reason}")

        except (DeadTokenError, PushDispatchError):
            raise
        except Exception as exc:
            raise PushDispatchError(f"APNS unexpected error: {exc}") from exc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _category_to_android_channel(category: str) -> str:
    """
    Map notification category to Android notification channel ID.
    Channels must be created in the Expo / React Native app on first launch.
    """
    security_cats = {
        "security", "password_changed", "two_fa_enabled",
        "two_fa_disabled", "new_login", "payment_failed",
    }
    if category in security_cats:
        return "security"
    invoice_cats = {
        "invoice_paid", "invoice_overdue", "payment_received",
        "payment_reminder", "invoice_sent",
    }
    if category in invoice_cats:
        return "invoices"
    if category in {"contract_signed", "contract_expiring", "ai_review_done"}:
        return "contracts"
    return "general"


# ---------------------------------------------------------------------------
# PushDispatcher — main entry point
# ---------------------------------------------------------------------------

class PushDispatcher:
    """
    Routes push notifications to the correct provider(s) based on device platform.

    Usage (called from tasks.py):
        PushDispatcher.send_to_user(user, payload)

    Handles:
      • Querying active PushToken rows
      • Grouping by platform
      • Expo batch dispatch
      • FCM / APNS per-token dispatch
      • Dead token deactivation
      • Ticket ID recording on the Notification
    """

    @classmethod
    def send_to_user(
        cls,
        user,
        payload: PushPayload,
        notification=None,   # Optional Notification instance to update
    ) -> int:
        """
        Dispatch push to all active devices for a user.
        Returns the number of tokens successfully dispatched to.
        """
        from notifications.models import PushToken, PushTokenPlatform, Channel  # noqa: PLC0415

        tokens = list(
            PushToken.objects.filter(user=user, is_active=True)
            .values("id", "token", "platform")
        )

        if not tokens:
            logger.debug("PushDispatcher: no active tokens for user %s", user.pk)
            return 0

        # Group by platform
        expo_tokens:  list[dict] = []
        fcm_tokens:   list[dict] = []
        apns_tokens:  list[dict] = []

        for t in tokens:
            if t["platform"] in (PushTokenPlatform.EXPO,):
                expo_tokens.append(t)
            elif t["platform"] == PushTokenPlatform.FCM:
                fcm_tokens.append(t)
            elif t["platform"] == PushTokenPlatform.APNS:
                apns_tokens.append(t)

        total_sent = 0

        # ── Expo ──────────────────────────────────────────────────────
        if expo_tokens:
            total_sent += cls._send_expo(expo_tokens, payload, notification)

        # ── FCM ───────────────────────────────────────────────────────
        for t in fcm_tokens:
            try:
                FCMProvider.send(t["token"], payload)
                total_sent += 1
            except DeadTokenError:
                cls._deactivate_token(t["id"])
            except PushDispatchError as exc:
                logger.warning("FCM dispatch failed for token %s: %s", t["id"], exc)

        # ── APNS ──────────────────────────────────────────────────────
        for t in apns_tokens:
            try:
                APNSProvider.send(t["token"], payload)
                total_sent += 1
            except DeadTokenError:
                cls._deactivate_token(t["id"])
            except PushDispatchError as exc:
                logger.warning("APNS dispatch failed for token %s: %s", t["id"], exc)

        if notification and total_sent > 0:
            notification.mark_channel_sent(Channel.PUSH)

        logger.info(
            "PushDispatcher: sent to %d/%d devices for user %s",
            total_sent, len(tokens), user.pk,
        )
        return total_sent

    @classmethod
    def _send_expo(
        cls,
        token_rows: list[dict],
        payload:    PushPayload,
        notification=None,
    ) -> int:
        """Batch-send to Expo tokens. Returns successful count."""
        from notifications.models import PushToken  # noqa: PLC0415

        all_tokens = [t["token"] for t in token_rows]
        token_id_map = {t["token"]: t["id"] for t in token_rows}
        sent = 0

        # Split into batches of EXPO_BATCH_SIZE
        for i in range(0, len(all_tokens), EXPO_BATCH_SIZE):
            batch = all_tokens[i:i + EXPO_BATCH_SIZE]
            try:
                tickets = ExpoProvider.send_batch(batch, payload)
            except PushDispatchError as exc:
                logger.warning("ExpoProvider batch failed: %s", exc)
                continue

            for token, ticket in zip(batch, tickets):
                if ticket.get("status") == "ok":
                    sent += 1
                    # Optionally store ticket_id for receipt polling
                    if notification and ticket.get("id"):
                        notification.push_ticket_id = ticket["id"]
                        notification.save(update_fields=["push_ticket_id"])
                elif ExpoProvider.is_dead_token_error(ticket):
                    token_id = token_id_map.get(token)
                    if token_id:
                        cls._deactivate_token(token_id)
                else:
                    logger.warning(
                        "Expo ticket error for token %s: %s",
                        token[:20], ticket.get("message", ""),
                    )

        return sent

    @staticmethod
    def _deactivate_token(token_id) -> None:
        """Mark a PushToken as inactive (dead token cleanup)."""
        from notifications.models import PushToken  # noqa: PLC0415
        try:
            PushToken.objects.filter(id=token_id).update(is_active=False)
            logger.info("PushDispatcher: deactivated dead token %s", token_id)
        except Exception as exc:
            logger.exception("PushDispatcher: failed to deactivate token %s: %s", token_id, exc)

    @classmethod
    def build_payload_from_notification(cls, notification) -> PushPayload:
        """Convenience: build a PushPayload from a Notification instance."""
        return PushPayload(
            title      = notification.title,
            body       = notification.body,
            data       = {
                "notification_id": str(notification.pk),
                **notification.data,
            },
            category   = notification.category,
            priority   = notification.priority,
            action_url = notification.action_url,
            collapse_id= f"{notification.category}:{notification.user_id}",
        )