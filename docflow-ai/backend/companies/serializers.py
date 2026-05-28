"""
DocFlow AI — companies/serializers.py

Serializers for company workspace management:
  • Company CRUD (owner-scoped)
  • CompanyBranding read/update
  • VATConfig read/update
  • CompanyMembership invite / list / remove
  • Nested public read (safe for embedding in document serializers)
"""

from __future__ import annotations

import re

from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from .models import Company, CompanyBranding, CompanyMembership, MemberRole, VATConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _validate_hex_color(value: str) -> str:
    if not _HEX_COLOR_RE.match(value):
        raise serializers.ValidationError(
            _("Enter a valid hex colour, e.g. #1A56DB.")
        )
    return value.upper()


def _validate_currency(value: str) -> str:
    """Rudimentary ISO 4217 check — 3 uppercase letters."""
    if not re.match(r"^[A-Z]{3}$", value.upper()):
        raise serializers.ValidationError(_("Enter a valid 3-letter ISO 4217 currency code."))
    return value.upper()


# ---------------------------------------------------------------------------
# Branding
# ---------------------------------------------------------------------------

class CompanyBrandingSerializer(serializers.ModelSerializer):
    class Meta:
        model  = CompanyBranding
        fields = [
            "primary_color", "secondary_color", "accent_color",
            "text_color", "background_color",
            "font_family", "font_size_body",
            "stamp", "signature",
            "invoice_header_text", "invoice_footer_text",
            "quotation_footer_text", "contract_footer_text",
            "invoice_terms", "quotation_terms",
            "updated_at",
        ]
        read_only_fields = ["updated_at"]

    def validate_primary_color(self, v):   return _validate_hex_color(v)
    def validate_secondary_color(self, v): return _validate_hex_color(v)
    def validate_accent_color(self, v):    return _validate_hex_color(v)
    def validate_text_color(self, v):      return _validate_hex_color(v)
    def validate_background_color(self, v): return _validate_hex_color(v)

    def validate_font_size_body(self, value: int) -> int:
        if not 6 <= value <= 24:
            raise serializers.ValidationError(_("Font size must be between 6 and 24 pt."))
        return value


# ---------------------------------------------------------------------------
# VAT Config
# ---------------------------------------------------------------------------

class VATConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model  = VATConfig
        fields = [
            "vat_number", "vat_registered", "vat_rate", "vat_label",
            "wht_applicable", "wht_rate", "wht_label",
            "extra_tax_label", "extra_tax_rate",
            "prices_include_tax", "show_tax_breakdown",
            "updated_at",
        ]
        read_only_fields = ["updated_at"]

    def validate_vat_rate(self, value):
        if value < 0 or value > 100:
            raise serializers.ValidationError(_("VAT rate must be between 0 and 100."))
        return value

    def validate_wht_rate(self, value):
        if value < 0 or value > 100:
            raise serializers.ValidationError(_("WHT rate must be between 0 and 100."))
        return value


# ---------------------------------------------------------------------------
# Company — public minimal (safe to embed in documents)
# ---------------------------------------------------------------------------

class CompanyPublicSerializer(serializers.ModelSerializer):
    logo_url = serializers.SerializerMethodField()

    class Meta:
        model  = Company
        fields = [
            "id", "name", "slug", "logo_url",
            "email", "phone", "website", "full_address", "country",
            "currency",
        ]
        read_only_fields = fields

    def get_logo_url(self, obj: Company) -> str | None:
        if not obj.logo:
            return None
        req = self.context.get("request")
        return req.build_absolute_uri(obj.logo.url) if req else obj.logo.url


# ---------------------------------------------------------------------------
# Company — full (owner / super admin)
# ---------------------------------------------------------------------------

class CompanySerializer(serializers.ModelSerializer):
    """Full company read + create/update for owners."""

    branding   = CompanyBrandingSerializer(read_only=True)
    vat_config = VATConfigSerializer(read_only=True)
    logo_url   = serializers.SerializerMethodField()
    full_address = serializers.CharField(read_only=True)
    is_deleted   = serializers.BooleanField(read_only=True)

    class Meta:
        model  = Company
        fields = [
            "id", "name", "slug",
            "logo", "logo_url",
            "email", "phone", "website",
            "address_line1", "address_line2", "city", "state",
            "postal_code", "country", "full_address",
            "registration_number", "size", "industry",
            "currency", "timezone_name", "language", "date_format",
            "invoice_prefix", "quotation_prefix", "contract_prefix",
            "next_invoice_number", "next_quotation_number", "next_contract_number",
            "default_payment_terms",
            "bank_name", "bank_account_name", "bank_account_number",
            "bank_branch_code", "swift_code", "iban",
            "mpesa_paybill", "mpesa_till",
            "is_active", "is_deleted",
            "branding", "vat_config",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "slug", "full_address", "is_deleted",
            "next_invoice_number", "next_quotation_number",
            "next_contract_number", "created_at", "updated_at",
            "logo_url", "branding", "vat_config",
        ]

    def get_logo_url(self, obj: Company) -> str | None:
        if not obj.logo:
            return None
        req = self.context.get("request")
        return req.build_absolute_uri(obj.logo.url) if req else obj.logo.url

    def validate_currency(self, value: str) -> str:
        return _validate_currency(value)

    def validate_name(self, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError(_("Company name must be at least 2 characters."))
        return value

    def validate_logo(self, value) -> object:
        if value and value.size > 5 * 1024 * 1024:
            raise serializers.ValidationError(_("Logo must be smaller than 5 MB."))
        return value

    def _generate_unique_slug(self, name: str, exclude_pk=None) -> str:
        base = slugify(name)[:200]
        slug = base
        qs = Company.objects.filter(slug=slug)
        if exclude_pk:
            qs = qs.exclude(pk=exclude_pk)
        counter = 1
        while qs.exists():
            slug = f"{base}-{counter}"
            qs = Company.objects.filter(slug=slug)
            if exclude_pk:
                qs = qs.exclude(pk=exclude_pk)
            counter += 1
        return slug

    def create(self, validated_data: dict) -> Company:
        validated_data["slug"] = self._generate_unique_slug(validated_data["name"])
        validated_data["owner"] = self.context["request"].user
        company = super().create(validated_data)
        # Auto-create child config models
        CompanyBranding.objects.get_or_create(company=company)
        VATConfig.objects.get_or_create(company=company)
        # Auto-add owner as active member
        CompanyMembership.objects.get_or_create(
            company=company,
            user=company.owner,
            defaults={"role": MemberRole.OWNER, "is_active": True},
        )
        return company

    def update(self, instance: Company, validated_data: dict) -> Company:
        if "name" in validated_data and validated_data["name"] != instance.name:
            validated_data["slug"] = self._generate_unique_slug(
                validated_data["name"], exclude_pk=instance.pk
            )
        return super().update(instance, validated_data)


# ---------------------------------------------------------------------------
# Membership
# ---------------------------------------------------------------------------

class CompanyMembershipSerializer(serializers.ModelSerializer):
    """Read representation of a membership (lists team members)."""

    user_email    = serializers.EmailField(source="user.email",    read_only=True)
    user_full_name = serializers.CharField(source="user.full_name", read_only=True)
    invited_by_email = serializers.EmailField(
        source="invited_by.email", read_only=True, allow_null=True,
    )

    class Meta:
        model  = CompanyMembership
        fields = [
            "id", "company",
            "user", "user_email", "user_full_name",
            "role", "is_active",
            "invited_by", "invited_by_email",
            "joined_at", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "company", "user", "user_email", "user_full_name",
            "invited_by", "invited_by_email",
            "joined_at", "created_at", "updated_at",
        ]


class InviteMemberSerializer(serializers.Serializer):
    """POST /companies/<pk>/members/invite/"""

    email = serializers.EmailField()
    role  = serializers.ChoiceField(
        choices=[(r.value, r.name.title()) for r in MemberRole],
        default=MemberRole.STAFF,
    )

    def validate_email(self, value: str) -> str:
        return value.lower().strip()

    def validate(self, data: dict) -> dict:
        from django.contrib.auth import get_user_model
        UserModel = get_user_model()
        try:
            data["_user"] = UserModel.objects.active().get(email=data["email"])
        except UserModel.DoesNotExist:
            raise serializers.ValidationError(
                {"email": _("No active account found with this email address.")}
            )
        return data


class UpdateMemberRoleSerializer(serializers.ModelSerializer):
    """PATCH /companies/<pk>/members/<member_pk>/"""

    class Meta:
        model  = CompanyMembership
        fields = ["role", "is_active"]