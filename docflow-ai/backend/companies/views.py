"""
DocFlow AI — companies/views.py  (patched)

Fixes vs original:
  1. CompanyViewSet.get_permissions()
       - list/create now use IsActiveUser (not IsCompanyMember).
         A brand-new user has zero memberships so IsCompanyMember would
         always return an empty queryset or 403 before they create anything.
       - retrieve still uses IsCompanyMember (member of that specific company).
  2. CompanyViewSet.get_queryset()
       - Owners who aren't a member yet (edge-case during onboarding) see
         companies they own directly, not just via membership.
  3. No functional changes to Branding, VAT, or Member views.
"""

from __future__ import annotations

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from users.permissions import IsActiveUser, IsCompanyMember, IsOwner, IsSuperAdmin, IsVerifiedUser

from .models import Company, CompanyBranding, CompanyMembership, MemberRole, VATConfig
from .serializers import (
    CompanyBrandingSerializer,
    CompanyMembershipSerializer,
    CompanySerializer,
    InviteMemberSerializer,
    UpdateMemberRoleSerializer,
    VATConfigSerializer,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_company_for_owner(pk, user) -> Company:
    """Return company if the user is the owner or a super-admin."""
    from users.models import UserRole
    qs = Company.objects.filter(is_active=True)
    if user.role != UserRole.SUPER_ADMIN:
        qs = qs.filter(owner=user)
    return get_object_or_404(qs, pk=pk)


# ---------------------------------------------------------------------------
# Company
# ---------------------------------------------------------------------------

class CompanyViewSet(viewsets.ModelViewSet):
    """
    list     GET    /companies/                — any active user (see their companies)
    create   POST   /companies/                — any active user (creates a new workspace)
    retrieve GET    /companies/<pk>/           — company member only
    update   PATCH  /companies/<pk>/           — owner only
    destroy  DELETE /companies/<pk>/           — owner only
    restore  POST   /companies/<pk>/restore/   — super-admin only
    """

    serializer_class  = CompanySerializer
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_permissions(self):
        if self.action in ("update", "partial_update", "destroy"):
            return [IsVerifiedUser(), IsOwner()]
        if self.action in ("list", "create"):
            # ↓ FIXED: was IsCompanyMember — new users have no memberships yet
            return [IsActiveUser()]
        # retrieve, restore, and any other action: must be a company member
        return [IsCompanyMember()]

    def get_queryset(self):
        user = self.request.user
        from users.models import UserRole

        if user.role == UserRole.SUPER_ADMIN:
            return (
                Company.objects.filter(is_active=True)
                .select_related("owner", "branding", "vat_config")
                .order_by("-created_at")
            )

        # Companies the user is a member of
        member_company_ids = CompanyMembership.objects.filter(
            user=user, is_active=True
        ).values_list("company_id", flat=True)

        # Also include companies the user owns directly (covers the edge case
        # where the membership row hasn't been created yet during onboarding).
        # Use Q objects to keep a single queryset so select_related/order_by
        # apply correctly — the | operator on two separate querysets silently
        # drops chained calls on the left-hand side.
        from django.db.models import Q
        return (
            Company.objects.filter(is_active=True)
            .filter(Q(id__in=member_company_ids) | Q(owner=user))
            .distinct()
            .select_related("owner", "branding", "vat_config")
            .order_by("-created_at")
        )

    def perform_create(self, serializer: CompanySerializer) -> None:
        # owner is injected inside CompanySerializer.create() via request context
        serializer.save()

    def perform_destroy(self, instance: Company) -> None:
        instance.soft_delete()

    @action(
        detail=True,
        methods=["post"],
        url_path="restore",
        permission_classes=[IsVerifiedUser, IsSuperAdmin],
    )
    def restore(self, request: Request, pk=None) -> Response:
        """POST /companies/<pk>/restore/ — super-admin only."""
        company = get_object_or_404(Company, pk=pk)
        company.is_active = True
        company.deleted_at = None
        company.save(update_fields=["is_active", "deleted_at", "updated_at"])
        return Response({"detail": _("Company restored.")})


# ---------------------------------------------------------------------------
# Branding
# ---------------------------------------------------------------------------

class CompanyBrandingView(APIView):
    """
    GET   /companies/<pk>/branding/ — any member
    PATCH /companies/<pk>/branding/ — owner only
    """

    def get_permissions(self):
        if self.request.method in ("PATCH", "PUT"):
            return [IsVerifiedUser(), IsOwner()]
        return [IsCompanyMember()]

    def _get_branding(self, pk, user) -> CompanyBranding:
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            company = get_object_or_404(Company, pk=pk, is_active=True)
        else:
            company = _get_company_for_owner(pk, user)
        branding, _ = CompanyBranding.objects.get_or_create(company=company)
        return branding

    def get(self, request: Request, pk=None) -> Response:
        branding = self._get_branding(pk, request.user)
        return Response(
            CompanyBrandingSerializer(branding, context={"request": request}).data
        )

    def patch(self, request: Request, pk=None) -> Response:
        branding = self._get_branding(pk, request.user)
        serializer = CompanyBrandingSerializer(
            branding,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


# ---------------------------------------------------------------------------
# VAT Config
# ---------------------------------------------------------------------------

class VATConfigView(APIView):
    """
    GET   /companies/<pk>/vat/ — accountant+ member
    PATCH /companies/<pk>/vat/ — owner only
    """

    def get_permissions(self):
        if self.request.method in ("PATCH", "PUT"):
            return [IsVerifiedUser(), IsOwner()]
        from users.permissions import IsAccountant
        return [IsAccountant()]

    def _get_vat(self, pk) -> VATConfig:
        company = get_object_or_404(Company, pk=pk, is_active=True)
        vat, _ = VATConfig.objects.get_or_create(company=company)
        return vat

    def get(self, request: Request, pk=None) -> Response:
        vat = self._get_vat(pk)
        return Response(VATConfigSerializer(vat).data)

    def patch(self, request: Request, pk=None) -> Response:
        vat = self._get_vat(pk)
        serializer = VATConfigSerializer(vat, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


# ---------------------------------------------------------------------------
# Company Members
# ---------------------------------------------------------------------------

class CompanyMemberViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """
    list         GET   /companies/<company_pk>/members/
    retrieve     GET   /companies/<company_pk>/members/<pk>/
    destroy      DEL   /companies/<company_pk>/members/<pk>/  — owner only
    invite       POST  /companies/<company_pk>/members/invite/
    update_role  PATCH /companies/<company_pk>/members/<pk>/role/
    """

    serializer_class = CompanyMembershipSerializer

    def get_permissions(self):
        if self.action in ("destroy", "update_role", "invite"):
            return [IsVerifiedUser(), IsOwner()]
        return [IsCompanyMember()]

    def _get_company(self) -> Company:
        return get_object_or_404(
            Company, pk=self.kwargs["company_pk"], is_active=True
        )

    def get_queryset(self):
        company = self._get_company()
        return (
            CompanyMembership.objects.filter(company=company)
            .select_related("user", "invited_by")
            .order_by("-created_at")
        )

    def perform_destroy(self, instance: CompanyMembership) -> None:
        if instance.role == MemberRole.OWNER:
            raise PermissionDenied(_("You cannot remove the workspace owner."))
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])

    @action(detail=False, methods=["post"], url_path="invite")
    def invite(self, request: Request, company_pk=None) -> Response:
        """POST /companies/<company_pk>/members/invite/"""
        company = self._get_company()
        serializer = InviteMemberSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data["_user"]
        role = serializer.validated_data["role"]

        membership, created = CompanyMembership.objects.get_or_create(
            company=company,
            user=user,
            defaults={
                "role":       role,
                "invited_by": request.user,
                "is_active":  True,
            },
        )
        if not created:
            if membership.is_active:
                return Response(
                    {"detail": _("This user is already a member.")},
                    status=status.HTTP_409_CONFLICT,
                )
            membership.is_active  = True
            membership.role       = role
            membership.invited_by = request.user
            membership.save(update_fields=["is_active", "role", "invited_by", "updated_at"])

        return Response(
            CompanyMembershipSerializer(membership, context={"request": request}).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @action(detail=True, methods=["patch"], url_path="role")
    def update_role(self, request: Request, company_pk=None, pk=None) -> Response:
        """PATCH /companies/<company_pk>/members/<pk>/role/"""
        membership = get_object_or_404(
            CompanyMembership, pk=pk, company__pk=company_pk
        )
        if (
            membership.role == MemberRole.OWNER
            and membership.user == membership.company.owner
        ):
            raise PermissionDenied(_("Cannot change the workspace owner's role."))

        serializer = UpdateMemberRoleSerializer(
            membership, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            CompanyMembershipSerializer(membership, context={"request": request}).data
        )