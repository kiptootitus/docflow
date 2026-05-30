"""
DocFlow AI — notifications/push.py
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

EXPO_BATCH_SIZE = 100


@dataclass
class PushPayload:
    title:      str
    body:       str
    data:       dict[str, Any]   = field(default_factory=dict)
    badge:      int | None        = None
    sound:      str               = "default"
    category:   str               = ""
    priority:   str               = "normal"
    action_url: str               = ""
    collapse_id: str              = ""
    ttl:         int              = 86_400

    @property
    def expo_priority(self) -> str:
        return "high" if self.priority in ("high", "critical") else "normal"

    @property
    def apns_priority(self) -> str:
        return "10" if self.priority in ("high", "critical") else "5"

    @property
    def fcm_priority(self) -> str:
        return "high" if self.priority in ("high", "critical") else "normal"


class PushDispatchError(Exception):
    pass


class DeadTokenError(Exception):
    pass


class ExpoProvider:

    @classmethod
    def send_batch(cls, tokens: list[str], payload: PushPayload) -> list[dict]:
        import httpx

        messages = [cls._build_message(token, payload) for token in tokens]
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        access_token = getattr(settings, "EXPO_ACCESS_TOKEN", None)
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"

        try:
            response = httpx.post(EXPO_PUSH_URL, json=messages, headers=headers, timeout=15.0)
            response.raise_for_status()
            tickets = response.json().get("data", [])
            logger.info("ExpoProvider: sent %d messages, got %d tickets", len(messages), len(tickets))
            return tickets
        except httpx.HTTPStatusError as exc:
            logger.exception("ExpoProvider: HTTP error %s", exc.response.status_code)
            raise PushDispatchError(f"Expo HTTP {exc.response.status_code}") from exc
        except Exception as exc:
            logger.exception("ExpoProvider: unexpected error: %s", exc)
            raise PushDispatchError(str(exc)) from exc

    @classmethod
    def fetch_receipts(cls, ticket_ids: list[str]) -> dict[str, dict]:
        import httpx

        if not ticket_ids:
            return {}

        headers = {"Content-Type": "application/json"}
        access_token = getattr(settings, "EXPO_ACCESS_TOKEN", None)
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"

        try:
            response = httpx.post(EXPO_RECEIPT_URL, json={"ids": ticket_ids}, headers=headers, timeout=15.0)
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
        if ticket.get("status") == "error":
            return ticket.get("details", {}).get("error") in ("DeviceNotRegistered", "InvalidCredentials")
        return False


class FCMProvider:
    _access_token: str | None = None
    _token_expiry: float       = 0.0

    @classmethod
    def _get_access_token(cls) -> str:
        if cls._access_token and time.time() < cls._token_expiry - 60:
            return cls._access_token

        try:
            from google.oauth2 import service_account
            from google.auth.transport.requests import Request as GRequest

            sa_config = getattr(settings, "FCM_SERVICE_ACCOUNT", None)
            if not sa_config:
                raise PushDispatchError("FCM_SERVICE_ACCOUNT not configured")

            if isinstance(sa_config, str):
                with open(sa_config) as f:
                    sa_config = json.load(f)

            creds = service_account.Credentials.from_service_account_info(
                sa_config, scopes=["https://www.googleapis.com/auth/firebase.messaging"]
            )
            creds.refresh(GRequest())
            cls._access_token = creds.token
            cls._token_expiry  = creds.expiry.timestamp() if creds.expiry else time.time() + 3600
            return cls._access_token
        except Exception as exc:
            raise PushDispatchError(f"FCM auth failed: {exc}") from exc

    @classmethod
    def send(cls, token: str, payload: PushPayload) -> str | None:
        import httpx

        sa_config = getattr(settings, "FCM_SERVICE_ACCOUNT", None)
        if not sa_config:
            logger.warning("FCMProvider: FCM_SERVICE_ACCOUNT not set — skipping.")
            return None

        project_id = sa_config.get("project_id") if isinstance(sa_config, dict) else "docflow-ai"
        url = FCM_SEND_URL.format(project_id=project_id)

        message = {
            "message": {
                "token": token,
                "notification": {"title": payload.title, "body":  payload.body},
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
                url, json=message,
                headers={"Authorization": f"Bearer {access_token}", "Content-Type":  "application/json"},
                timeout=15.0
            )

            if response.status_code == 404:
                raise DeadTokenError(f"FCM token not found: {token[:20]}...")
            if response.status_code == 400 and "INVALID_ARGUMENT" in response.text:
                raise DeadTokenError(f"FCM invalid token: {token[:20]}...")

            response.raise_for_status()
            return response.json().get("name")
        except (DeadTokenError, PushDispatchError):
            raise
        except httpx.HTTPStatusError as exc:
            raise PushDispatchError(f"FCM HTTP {exc.response.status_code}") from exc
        except Exception as exc:
            raise PushDispatchError(str(exc)) from exc


class APNSProvider:
    _jwt_token: str | None  = None
    _jwt_expiry: float       = 0.0

    @classmethod
    def _get_jwt(cls) -> str:
        if cls._jwt_token and time.time() < cls._jwt_expiry - 60:
            return cls._jwt_token

        try:
            import jwt as pyjwt

            key_id   = getattr(settings, "APNS_KEY_ID", "")
            team_id  = getattr(settings, "APNS_TEAM_ID", "")
            key_path = getattr(settings, "APNS_AUTH_KEY_PATH", "")

            if not all([key_id, team_id, key_path]):
                raise PushDispatchError("APNS credentials not fully configured.")

            with open(key_path) as f:
                private_key = f.read()

            now = int(time.time())
            token = pyjwt.encode({"iss": team_id, "iat": now}, private_key, algorithm="ES256", headers={"kid": key_id})
            cls._jwt_token  = token if isinstance(token, str) else token.decode()
            cls._jwt_expiry = now + 3000
            return cls._jwt_token
        except (PushDispatchError, FileNotFoundError):
            raise
        except Exception as exc:
            raise PushDispatchError(f"APNS JWT generation failed: {exc}") from exc

    @classmethod
    def send(cls, device_token: str, payload: PushPayload) -> None:
        import httpx

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
            with httpx.Client(http2=True, timeout=15.0) as client:
                response = client.post(url, json=apns_payload, headers=headers)

            if response.status_code == 200:
                return

            reason = response.json().get("reason", "") if response.status_code != 500 else "Internal APNS Error"
            if reason in ("BadDeviceToken", "Unregistered", "DeviceTokenNotForTopic"):
                raise DeadTokenError(f"APNS dead token: {reason}")
            raise PushDispatchError(f"APNS error {response.status_code}: {reason}")
        except (DeadTokenError, PushDispatchError):
            raise
        except Exception as exc:
            raise PushDispatchError(f"APNS unexpected error: {exc}") from exc


def _category_to_android_channel(category: str) -> str:
    if category in {"security", "password_changed", "two_fa_enabled", "two_fa_disabled", "new_login", "payment_failed"}:
        return "security"
    if category in {"invoice_paid", "invoice_overdue", "payment_received", "payment_reminder", "invoice_sent"}:
        return "invoices"
    if category in {"contract_signed", "contract_expiring", "ai_review_done"}:
        return "contracts"
    return "general"


class PushDispatcher:

    @classmethod
    def send_to_user(cls, user, payload: PushPayload, notification=None) -> int:
        from notifications.models import PushToken, PushTokenPlatform, Channel

        tokens = list(PushToken.objects.filter(user=user, is_active=True).values("id", "token", "platform"))
        if not tokens:
            return 0

        expo_tokens, fcm_tokens, apns_tokens = [], [], []
        for t in tokens:
            if t["platform"] == PushTokenPlatform.EXPO:
                expo_tokens.append(t)
            elif t["platform"] == PushTokenPlatform.FCM:
                fcm_tokens.append(t)
            elif t["platform"] == PushTokenPlatform.APNS:
                apns_tokens.append(t)

        total_sent = 0
        if expo_tokens:
            total_sent += cls._send_expo(expo_tokens, payload, notification)

        for t in fcm_tokens:
            try:
                FCMProvider.send(t["token"], payload)
                total_sent += 1
            except DeadTokenError:
                cls._deactivate_token(t["id"])
            except PushDispatchError:
                pass

        for t in apns_tokens:
            try:
                APNSProvider.send(t["token"], payload)
                total_sent += 1
            except DeadTokenError:
                cls._deactivate_token(t["id"])
            except PushDispatchError:
                pass

        if notification and total_sent > 0:
            notification.mark_channel_sent(Channel.PUSH)

        return total_sent

    @classmethod
    def _send_expo(cls, token_rows: list[dict], payload: PushPayload, notification=None) -> int:
        all_tokens = [t["token"] for t in token_rows]
        token_id_map = {t["token"]: t["id"] for t in token_rows}
        sent = 0

        for i in range(0, len(all_tokens), EXPO_BATCH_SIZE):
            batch = all_tokens[i:i + EXPO_BATCH_SIZE]
            try:
                tickets = ExpoProvider.send_batch(batch, payload)
            except PushDispatchError:
                continue

            for token, ticket in zip(batch, tickets):
                if ticket.get("status") == "ok":
                    sent += 1
                    if notification and ticket.get("id"):
                        notification.push_ticket_id = ticket["id"]
                        notification.save(update_fields=["push_ticket_id"])
                elif ExpoProvider.is_dead_token_error(ticket):
                    token_id = token_id_map.get(token)
                    if token_id:
                        cls._deactivate_token(token_id)

        return sent

    @staticmethod
    def _deactivate_token(token_id) -> None:
        from notifications.models import PushToken
        PushToken.objects.filter(id=token_id).update(is_active=False)

    @classmethod
    def build_payload_from_notification(cls, notification) -> PushPayload:
        return PushPayload(
            title      = notification.title,
            body       = notification.body,
            data       = {"notification_id": str(notification.pk), **notification.data},
            category   = notification.category,
            priority   = notification.priority,
            action_url = notification.action_url,
            collapse_id= f"{notification.category}:{notification.user_id}",
        )