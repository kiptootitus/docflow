"""
DocFlow AI — users/permissions.py

Custom DRF permission classes for the platform.

Hierarchy (most → least privileged):
  IsSuperAdmin  — platform staff only
  IsOwner       — workspace owner
  IsCompanyMember — any active member of a company workspace
  IsAccountant  — can view financials, cannot modify
  IsClientReadOnly — external clients viewing their own portal data

Design notes:
  • All classes are safe (never raise unhandled exceptions).
  • Permissions compose well with DRF's default AND/OR behaviour.
  • Object-level permissions delegate to the model's company FK.
  • get_client_ip() is provided for rate-limiting / audit use.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rest_framework.permissions import BasePermission, IsAuthenticated, SAFE_METHODS
from rest_framework.request import Request
from rest_framework.views import APIView

from .models import UserRole

if TYPE_CHECKING:
    from django.db.models import Model


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_client_ip(request: Request) -> str:
    """Extract real client IP, respecting common reverse-proxy headers."""
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def _has_role(request: Request, *roles: str) -> bool:
    """Return True if the authenticated user has one of the given roles."""
    return (
        request.user
        and request.user.is_authenticated
        and not request.user.is_deleted
        and request.user.role in roles
    )


# ---------------------------------------------------------------------------
# Base guard — always enforced
# ---------------------------------------------------------------------------

class IsActiveUser(IsAuthenticated):
    """
    Extends IsAuthenticated: additionally rejects soft-deleted accounts
    and unverified accounts on sensitive actions.
    """

    message = "Your account is inactive or has been removed."

    def has_permission(self, request: Request, view: APIView) -> bool:
        if not super().has_permission(request, view):
            return False
        user = request.user
        return user.is_active and not user.is_deleted


class IsVerifiedUser(IsActiveUser):
    """Active AND email-verified. Gate unverified users from sensitive endpoints."""

    message = "Please verify your email address before continuing."

    def has_permission(self, request: Request, view: APIView) -> bool:
        if not super().has_permission(request, view):
            return False
        return request.user.is_verified


# ---------------------------------------------------------------------------
# Role-based permissions
# ---------------------------------------------------------------------------

class IsSuperAdmin(IsActiveUser):
    """
    Platform-level super admin only (DocFlow internal staff).
    Used for: user management API, billing overrides, analytics.
    """

    message = "Only platform administrators can perform this action."

    def has_permission(self, request: Request, view: APIView) -> bool:
        return super().has_permission(request, view) and _has_role(
            request, UserRole.SUPER_ADMIN
        )


class IsOwner(IsActiveUser):
    """
    Workspace owner. Can manage team members, billing, and company settings.
    Super admins are implicitly allowed too.
    """

    message = "Only workspace owners can perform this action."

    def has_permission(self, request: Request, view: APIView) -> bool:
        if not super().has_permission(request, view):
            return False
        return _has_role(request, UserRole.OWNER, UserRole.SUPER_ADMIN)

    def has_object_permission(self, request: Request, view: APIView, obj: "Model") -> bool:
        """
        Object-level: the requesting user must own the object's company,
        OR be a SUPER_ADMIN.
        Assumes obj has a `company` FK with an `owner` FK back to User.
        Falls back gracefully if those attrs don't exist.
        """
        if request.user.role == UserRole.SUPER_ADMIN:
            return True

        # Documents / invoices owned by the company
        company = getattr(obj, "company", None)
        if company:
            return getattr(company, "owner_id", None) == request.user.pk

        # The object IS the user
        if isinstance(obj, type(request.user)):
            return obj.pk == request.user.pk

        return False


class IsCompanyMember(IsActiveUser):
    """
    Any active member of the same company workspace.
    Owner + Staff + Accountant roles qualify.
    """

    message = "You must be a member of this workspace to perform this action."

    def has_permission(self, request: Request, view: APIView) -> bool:
        if not super().has_permission(request, view):
            return False
        return _has_role(
            request,
            UserRole.OWNER,
            UserRole.STAFF,
            UserRole.ACCOUNTANT,
            UserRole.SUPER_ADMIN,
        )

    def has_object_permission(self, request: Request, view: APIView, obj: "Model") -> bool:
        if request.user.role == UserRole.SUPER_ADMIN:
            return True

        # Check company membership via CompanyMembership join table
        # (companies app) — imported lazily to avoid circular imports.
        try:
            from companies.models import CompanyMembership  # noqa: PLC0415

            company = getattr(obj, "company", None) or obj
            return CompanyMembership.objects.filter(
                company=company,
                user=request.user,
                is_active=True,
            ).exists()
        except Exception:  # pragma: no cover
            return False


class IsAccountant(IsActiveUser):
    """
    Accountant role: full read access to financial data, no mutations.
    Use together with IsCompanyMember for object-level checks.
    """

    message = "Accountant role required."

    def has_permission(self, request: Request, view: APIView) -> bool:
        if not super().has_permission(request, view):
            return False
        return _has_role(
            request,
            UserRole.ACCOUNTANT,
            UserRole.OWNER,
            UserRole.SUPER_ADMIN,
        )


class IsClientReadOnly(IsActiveUser):
    """
    External client: read-only access to their own portal data.
    Safe methods (GET, HEAD, OPTIONS) only.
    """

    message = "Clients have read-only access."

    def has_permission(self, request: Request, view: APIView) -> bool:
        if not super().has_permission(request, view):
            return False
        if not _has_role(request, UserRole.CLIENT):
            return False
        return request.method in SAFE_METHODS

    def has_object_permission(self, request: Request, view: APIView, obj: "Model") -> bool:
        """Clients may only view documents addressed to them."""
        if request.method not in SAFE_METHODS:
            return False
        client_field = getattr(obj, "client", None) or getattr(obj, "client_id", None)
        if client_field is None:
            return False
        pk = getattr(client_field, "pk", client_field)
        return pk == request.user.pk


# ---------------------------------------------------------------------------
# Ownership shortcuts (for generic use)
# ---------------------------------------------------------------------------

class IsOwnerOrReadOnly(IsActiveUser):
    """
    Allow all authenticated active users to READ; restrict writes to owners.
    Useful for public-ish resources (e.g., company profile preview).
    """

    def has_permission(self, request: Request, view: APIView) -> bool:
        return super().has_permission(request, view)

    def has_object_permission(self, request: Request, view: APIView, obj: "Model") -> bool:
        if request.method in SAFE_METHODS:
            return True
        owner_pk = getattr(obj, "owner_id", None) or getattr(
            getattr(obj, "company", None), "owner_id", None
        )
        return owner_pk == request.user.pk


class IsSelfOrAdmin(IsActiveUser):
    """
    Users can edit their own records; super admins can edit any record.
    Used on /users/<pk>/ endpoints.
    """

    def has_object_permission(self, request: Request, view: APIView, obj: "Model") -> bool:
        if request.user.role == UserRole.SUPER_ADMIN:
            return True
        return obj.pk == request.user.pk


# ---------------------------------------------------------------------------
# Token-based (portal access — no session required)
# ---------------------------------------------------------------------------

class HasValidPortalToken(BasePermission):
    """
    Validates a signed JWT passed as ?token=<jwt> in the query string.
    Used by the public client portal (/portal/:token).
    Does NOT require the user to be logged in.
    """

    message = "A valid portal access token is required."

    def has_permission(self, request: Request, view: APIView) -> bool:
        from rest_framework_simplejwt.tokens import AccessToken  # noqa: PLC0415
        from rest_framework_simplejwt.exceptions import TokenError  # noqa: PLC0415

        raw_token = request.query_params.get("token") or request.data.get("token")
        if not raw_token:
            return False

        try:
            token = AccessToken(raw_token)
            # Portal tokens carry a custom claim
            if token.get("token_type") != "portal":
                return False
            request._portal_token_payload = dict(token)  # type: ignore[attr-defined]
            return True
        except TokenError:
            return False