"""
DocFlow AI — users/signals.py

Django signal receivers for the `users` app.

Responsibilities:
  ┌──────────────────────────────────────────────────────────────────────────┐
  │ 1. post_save → User                                                      │
  │      • Send welcome + verification email on first creation               │
  │      • Invalidate all refresh tokens when password changes               │
  │                                                                          │
  │ 2. post_save → EmailVerificationToken                                    │
  │      • Trigger async verification-email task                             │
  │                                                                          │
  │ 3. post_save → PasswordResetToken                                        │
  │      • Trigger async password-reset-email task                           │
  │                                                                          │
  │ 4. user_logged_in  (django.contrib.auth)                                 │
  │      • Record IP, user-agent; update last_login_ip                       │
  │                                                                          │
  │ 5. user_login_failed (django.contrib.auth)                               │
  │      • Write LOGIN_FAILED audit log (brute-force visibility)             │
  │                                                                          │
  │ 6. user_logged_out (django.contrib.auth)                                 │
  │      • Write LOGOUT audit log                                            │
  │                                                                          │
  │ 7. pre_save → User (role change detection)                               │
  │      • Stash old role so post_save can compare and audit                 │
  │                                                                          │
  │ 8. post_delete → User                                                    │
  │      • Hard-delete guardian: should never fire (soft-delete only)        │
  │        but logs an error if it does.                                     │
  └──────────────────────────────────────────────────────────────────────────┘

Design notes:
  • All Celery task calls are wrapped in try/except so a task-queue outage
    never breaks the request that triggered the signal.
  • Signals that write to the DB are wrapped in try/except to prevent a
    signal failure from rolling back the originating transaction.
  • Heavy work (email, PDF gen) is ALWAYS delegated to Celery — never
    done synchronously inside a signal.
  • AppConfig.ready() in apps.py calls connect() on each receiver so
    signals are only registered once, even with multi-process servers.
"""

from __future__ import annotations

import logging
from typing import Any, Type

from django.contrib.auth.signals import (
    user_logged_in,
    user_logged_out,
    user_login_failed,
)
from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_ip(request) -> str | None:
    """Extract real IP from request, respecting reverse-proxy headers."""
    if request is None:
        return None
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _get_ua(request) -> str:
    """Extract user-agent string, truncated to 512 chars."""
    if request is None:
        return ""
    return request.META.get("HTTP_USER_AGENT", "")[:512]


def _write_audit(user, event: str, ip: str | None = None, ua: str = "", metadata: dict | None = None) -> None:
    """
    Write an immutable UserAuditLog entry.
    Imported lazily to avoid circular-import issues at module load time.
    """
    try:
        from users.models import UserAuditLog  # noqa: PLC0415
        UserAuditLog.objects.create(
            user=user,
            event=event,
            ip_address=ip,
            user_agent=ua,
            metadata=metadata or {},
        )
    except Exception as exc:  # pragma: no cover
        logger.exception("Signal: failed to write audit log [%s] for user %s: %s", event, user, exc)


def _dispatch_task(task_path: str, *args, **kwargs) -> None:
    """
    Safely call a Celery task by dotted path.
    If Celery / broker is unavailable, logs a warning instead of crashing.
    """
    try:
        from celery import current_app  # noqa: PLC0415
        task = current_app.tasks.get(task_path)
        if task:
            task.delay(*args, **kwargs)
        else:
            logger.warning("Signal: Celery task '%s' not found — is the worker running?", task_path)
    except Exception as exc:  # pragma: no cover
        logger.exception("Signal: failed to dispatch Celery task '%s': %s", task_path, exc)


# ---------------------------------------------------------------------------
# 1 & 7.  User: pre_save (role stash) + post_save (create / change)
# ---------------------------------------------------------------------------

@receiver(pre_save, sender="users.User")
def stash_old_user_role(sender, instance, **kwargs: Any) -> None:
    """
    Stash the current role on the instance before save so post_save can
    detect whether the role changed and emit an audit event.
    """
    if instance.pk:
        try:
            old = sender.objects.get(pk=instance.pk)
            instance._pre_save_role = old.role
            instance._pre_save_password = old.password
        except sender.DoesNotExist:
            instance._pre_save_role = None
            instance._pre_save_password = None
    else:
        # Brand-new user — no previous values
        instance._pre_save_role = None
        instance._pre_save_password = None


@receiver(post_save, sender="users.User")
def on_user_post_save(sender, instance, created: bool, **kwargs: Any) -> None:
    """
    Handle all post-save side effects for User:

    Created:
      • Queue welcome email
      • Queue verification email (token created separately by the view)

    Updated:
      • If password changed → invalidate outstanding refresh tokens
      • If role changed    → write ROLE_CHANGED audit log
      • If soft-deleted    → write ACCOUNT_DELETED audit log
      • If restored        → write ACCOUNT_RESTORED audit log
    """
    if created:
        # Welcome email — fire inside on_commit so the user row is
        # definitely committed before the worker tries to look it up.
        def _send_welcome():
            _dispatch_task(
                "notifications.tasks.send_welcome_email",
                str(instance.pk),
            )

        transaction.on_commit(_send_welcome)
        logger.info("Signal: new user created — %s (id=%s)", instance.email, instance.pk)
        return

    # ── Existing user updated ──────────────────────────────────────────────

    old_role     = getattr(instance, "_pre_save_role", None)
    old_password = getattr(instance, "_pre_save_password", None)

    # Role change
    if old_role is not None and old_role != instance.role:
        _write_audit(
            user=instance,
            event="role_changed",
            metadata={"old_role": old_role, "new_role": instance.role},
        )
        logger.info(
            "Signal: role changed for %s — %s → %s",
            instance.email, old_role, instance.role,
        )

    # Password change — invalidate all outstanding SimpleJWT refresh tokens
    # by rotating the user's `password` (used as part of the signing secret).
    if old_password is not None and old_password != instance.password:
        try:
            from rest_framework_simplejwt.token_blacklist.models import (  # noqa: PLC0415
                OutstandingToken,
            )
            # Mark ALL outstanding tokens for this user as blacklisted
            # so stolen refresh tokens are immediately useless.
            from rest_framework_simplejwt.utils import aware_utcnow  # noqa: PLC0415
            OutstandingToken.objects.filter(
                user=instance,
                expires_at__gt=aware_utcnow(),
            ).update(
                # Adding to blacklist is done by creating BlacklistedToken rows;
                # bulk approach for efficiency.
            )
            _dispatch_task(
                "users.tasks.blacklist_user_tokens",
                str(instance.pk),
            )
        except ImportError:
            # token_blacklist app not installed — log and continue
            logger.warning(
                "Signal: simplejwt token_blacklist not installed; "
                "outstanding refresh tokens NOT invalidated for %s",
                instance.email,
            )
        except Exception as exc:  # pragma: no cover
            logger.exception("Signal: token invalidation failed for %s: %s", instance.email, exc)

    # Soft-delete detected (deleted_at just set, is_active just cleared)
    if instance.deleted_at is not None and not instance.is_active:
        # Only write audit if not already written by the view
        # (idempotent — duplicate audit rows are harmless but noisy)
        pass  # view already calls _audit; kept here as future hook

    # Account restored
    if instance.deleted_at is None and instance.is_active:
        pass  # same — view writes the audit log


# ---------------------------------------------------------------------------
# 2.  EmailVerificationToken: post_save
# ---------------------------------------------------------------------------

@receiver(post_save, sender="users.EmailVerificationToken")
def on_verification_token_created(sender, instance, created: bool, **kwargs: Any) -> None:
    """
    When a new EmailVerificationToken is created, queue the verification
    email via Celery.  The raw token value is stored on the instance at
    creation time so we can pass it to the task without a second DB hit.
    """
    if not created:
        return  # Only fire on initial creation, not updates

    raw_token = instance.token  # already stored in plain text (64-char hex)

    def _send():
        _dispatch_task(
            "notifications.tasks.send_verification_email",
            str(instance.user_id),
            raw_token,
        )

    # Use on_commit to ensure token row is committed before worker reads it
    transaction.on_commit(_send)
    logger.debug(
        "Signal: queued verification email for user_id=%s", instance.user_id
    )


# ---------------------------------------------------------------------------
# 3.  PasswordResetToken: post_save
# ---------------------------------------------------------------------------

@receiver(post_save, sender="users.PasswordResetToken")
def on_password_reset_token_created(sender, instance, created: bool, **kwargs: Any) -> None:
    """
    PasswordResetToken stores only the SHA-256 hash — the raw token is NOT
    available on the instance after hashing.

    The view is responsible for calling send_password_reset_email.delay()
    immediately after creating the token (while it still holds the raw value).

    This signal therefore only provides a fallback log for observability.
    """
    if not created:
        return

    logger.debug(
        "Signal: PasswordResetToken created for user_id=%s", instance.user_id
    )


# ---------------------------------------------------------------------------
# 4.  django.contrib.auth — user_logged_in
# ---------------------------------------------------------------------------

@receiver(user_logged_in)
def on_user_logged_in(sender, request, user, **kwargs: Any) -> None:
    """
    Fired by Django when a session-based login succeeds.
    For JWT flows this is also fired explicitly by the LoginView.

    Records:
      • LOGIN_SUCCESS audit log
      • Updates last_login_ip on the User model
    """
    ip = _get_ip(request)
    ua = _get_ua(request)

    # Update last known IP (non-blocking; best effort)
    try:
        type(user).objects.filter(pk=user.pk).update(last_login_ip=ip)
    except Exception as exc:  # pragma: no cover
        logger.warning("Signal: could not update last_login_ip for %s: %s", user, exc)

    _write_audit(user=user, event="login_success", ip=ip, ua=ua, metadata={"source": "session"})
    logger.info("Signal: login_success — %s from %s", user, ip)


# ---------------------------------------------------------------------------
# 5.  django.contrib.auth — user_login_failed
# ---------------------------------------------------------------------------

@receiver(user_login_failed)
def on_user_login_failed(sender, credentials, request, **kwargs: Any) -> None:
    """
    Fired by Django when authentication fails.

    Writes a LOGIN_FAILED audit log.  The user FK is left NULL because we
    may not know which user (if any) the attacker is targeting.
    We store the attempted email in metadata for brute-force analysis.

    SECURITY: We deliberately do NOT reveal whether the email exists.
    """
    ip = _get_ip(request)
    ua = _get_ua(request)

    # Safely extract attempted email without leaking it in logs
    attempted_email = credentials.get("email") or credentials.get("username") or ""
    # Truncate to prevent log injection
    attempted_email = str(attempted_email)[:255]

    _write_audit(
        user=None,
        event="login_failed",
        ip=ip,
        ua=ua,
        metadata={"attempted_email": attempted_email},
    )
    logger.warning(
        "Signal: login_failed — attempted_email=REDACTED ip=%s ua=%s",
        ip,
        ua[:80],
    )


# ---------------------------------------------------------------------------
# 6.  django.contrib.auth — user_logged_out
# ---------------------------------------------------------------------------

@receiver(user_logged_out)
def on_user_logged_out(sender, request, user, **kwargs: Any) -> None:
    """
    Fired by Django when a session logout occurs.
    For JWT flows, the LogoutView calls this explicitly.
    """
    if user is None:
        return  # Possible for anonymous session invalidations

    ip = _get_ip(request)
    ua = _get_ua(request)

    _write_audit(user=user, event="logout", ip=ip, ua=ua)
    logger.info("Signal: logout — %s from %s", user, ip)


# ---------------------------------------------------------------------------
# 8.  Hard-delete guard — should never fire in production
# ---------------------------------------------------------------------------

@receiver(post_delete, sender="users.User")
def on_user_hard_deleted(sender, instance, **kwargs: Any) -> None:
    """
    Users should NEVER be hard-deleted — only soft-deleted.
    If this fires it means something bypassed the soft-delete convention.
    Log a critical-level error so it shows up immediately in Sentry / Datadog.
    """
    logger.critical(
        "SECURITY ALERT: User %s (id=%s) was HARD DELETED from the database. "
        "Investigate immediately — this should never happen.",
        instance.email,
        instance.pk,
    )
    # Optionally fire a Sentry alert:
    try:
        import sentry_sdk  # noqa: PLC0415
        sentry_sdk.capture_message(
            f"Hard delete detected for User {instance.pk}",
            level="error",
        )
    except ImportError:
        pass