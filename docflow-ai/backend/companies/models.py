"""
DocFlow AI — companies/models.py

Company workspace, branding configuration, VAT settings,
and the CompanyMembership join table referenced by users/permissions.py.

Design principles:
  • One company = one workspace tenant; row-level isolation throughout.
  • UUIDs as PKs to prevent enumeration.
  • Branding stored in a 1-to-1 child model to keep Company lean.
  • VAT config stored in a 1-to-1 child to support future per-country rules.
  • SoftDelete on Company cascades to sub-models via signal (see signals.py).
  • CompanyMembership is the authoritative source for per-workspace roles.
"""

from __future__ import annotations

import uuid
from enum import StrEnum

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class MemberRole(StrEnum):
    """Per-workspace role stored on CompanyMembership."""
    OWNER      = "owner"
    STAFF      = "staff"
    ACCOUNTANT = "accountant"
    CLIENT     = "client"


class CompanySize(models.TextChoices):
    SOLO        = "solo",         _("Solo / Freelancer")
    SMALL       = "small",        _("2–10 employees")
    MEDIUM      = "medium",       _("11–50 employees")
    LARGE       = "large",        _("50+ employees")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _logo_upload_path(instance: "Company", filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower()
    return f"companies/{instance.pk}/logo/logo.{ext}"


def _stamp_upload_path(instance: "CompanyBranding", filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower()
    return f"companies/{instance.company_id}/stamp/stamp.{ext}"


def _signature_upload_path(instance: "CompanyBranding", filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower()
    return f"companies/{instance.company_id}/signature/signature.{ext}"


# ---------------------------------------------------------------------------
# Company
# ---------------------------------------------------------------------------

class Company(models.Model):
    """
    The central tenant entity. Every invoice, quotation, and contract
    belongs to exactly one Company.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Core identity
    name            = models.CharField(_("company name"), max_length=200)
    slug            = models.SlugField(
        _("slug"), max_length=220, unique=True,
        help_text=_("URL-safe identifier, auto-generated from name."),
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="owned_companies",
        verbose_name=_("owner"),
    )
    logo = models.ImageField(
        _("company logo"),
        upload_to=_logo_upload_path,
        null=True, blank=True,
    )

    # Contact & address
    email       = models.EmailField(_("business email"), blank=True)
    phone       = models.CharField(_("phone"), max_length=30, blank=True)
    website     = models.URLField(_("website"), blank=True)
    address_line1 = models.CharField(_("address line 1"), max_length=255, blank=True)
    address_line2 = models.CharField(_("address line 2"), max_length=255, blank=True)
    city          = models.CharField(_("city"),    max_length=100, blank=True)
    state         = models.CharField(_("state"),   max_length=100, blank=True)
    postal_code   = models.CharField(_("postal code"), max_length=20, blank=True)
    country       = models.CharField(
        _("country"), max_length=2, default="KE",
        help_text=_("ISO 3166-1 alpha-2 country code."),
    )

    # Business metadata
    registration_number = models.CharField(
        _("registration number"), max_length=100, blank=True,
    )
    size = models.CharField(
        _("company size"),
        max_length=20,
        choices=CompanySize.choices,
        default=CompanySize.SOLO,
    )
    industry = models.CharField(_("industry"), max_length=100, blank=True)

    # Locale defaults (used when generating documents)
    currency       = models.CharField(
        _("default currency"), max_length=3, default="USD",
        help_text=_("ISO 4217 currency code."),
    )
    timezone_name  = models.CharField(
        _("timezone"), max_length=60, default="UTC",
    )
    language       = models.CharField(
        _("language"), max_length=10, default="en",
    )
    date_format    = models.CharField(
        _("date format"), max_length=20, default="%d %b %Y",
        help_text=_("Python strftime format string."),
    )

    # Document numbering
    invoice_prefix    = models.CharField(_("invoice prefix"),    max_length=10, default="INV")
    quotation_prefix  = models.CharField(_("quotation prefix"),  max_length=10, default="QT")
    contract_prefix   = models.CharField(_("contract prefix"),   max_length=10, default="CNT")
    next_invoice_number   = models.PositiveIntegerField(default=1)
    next_quotation_number = models.PositiveIntegerField(default=1)
    next_contract_number  = models.PositiveIntegerField(default=1)

    # Payment terms default (days)
    default_payment_terms = models.PositiveSmallIntegerField(
        _("default payment terms (days)"), default=30,
    )

    # Bank / payment details shown on invoices
    bank_name          = models.CharField(_("bank name"),          max_length=100, blank=True)
    bank_account_name  = models.CharField(_("account name"),       max_length=100, blank=True)
    bank_account_number = models.CharField(_("account number"),    max_length=50,  blank=True)
    bank_branch_code   = models.CharField(_("branch / sort code"), max_length=30,  blank=True)
    swift_code         = models.CharField(_("SWIFT / BIC"),        max_length=20,  blank=True)
    iban               = models.CharField(_("IBAN"),               max_length=50,  blank=True)
    mpesa_paybill      = models.CharField(_("M-Pesa Paybill"),     max_length=20,  blank=True)
    mpesa_till         = models.CharField(_("M-Pesa Till"),        max_length=20,  blank=True)

    # Soft-delete & timestamps
    is_active  = models.BooleanField(_("active"), default=True)
    deleted_at = models.DateTimeField(_("deleted at"), null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name        = _("company")
        verbose_name_plural = _("companies")
        ordering            = ["-created_at"]
        indexes = [
            models.Index(fields=["owner", "is_active"]),
            models.Index(fields=["slug"]),
        ]

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    @property
    def full_address(self) -> str:
        parts = filter(bool, [
            self.address_line1, self.address_line2,
            self.city, self.state, self.postal_code, self.country,
        ])
        return ", ".join(parts)

    # ------------------------------------------------------------------
    # Methods
    # ------------------------------------------------------------------

    def get_next_invoice_number(self) -> str:
        """Return formatted invoice number and increment counter atomically."""
        from django.db import transaction
        with transaction.atomic():
            company = Company.objects.select_for_update().get(pk=self.pk)
            num = company.next_invoice_number
            Company.objects.filter(pk=self.pk).update(
                next_invoice_number=num + 1
            )
            self.next_invoice_number = num + 1
        return f"{self.invoice_prefix}-{num:04d}"

    def get_next_quotation_number(self) -> str:
        from django.db import transaction
        with transaction.atomic():
            company = Company.objects.select_for_update().get(pk=self.pk)
            num = company.next_quotation_number
            Company.objects.filter(pk=self.pk).update(
                next_quotation_number=num + 1
            )
            self.next_quotation_number = num + 1
        return f"{self.quotation_prefix}-{num:04d}"

    def get_next_contract_number(self) -> str:
        from django.db import transaction
        with transaction.atomic():
            company = Company.objects.select_for_update().get(pk=self.pk)
            num = company.next_contract_number
            Company.objects.filter(pk=self.pk).update(
                next_contract_number=num + 1
            )
            self.next_contract_number = num + 1
        return f"{self.contract_prefix}-{num:04d}"

    def soft_delete(self) -> None:
        self.is_active = False
        self.deleted_at = timezone.now()
        self.save(update_fields=["is_active", "deleted_at", "updated_at"])

    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return f"<Company id={self.id} name={self.name!r}>"


# ---------------------------------------------------------------------------
# Company Branding
# ---------------------------------------------------------------------------

class CompanyBranding(models.Model):
    """
    Visual identity configuration used when rendering PDF/HTML documents.
    One-to-one with Company; created automatically via post_save signal.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.OneToOneField(
        Company,
        on_delete=models.CASCADE,
        related_name="branding",
    )

    # Colours (stored as hex, e.g. "#1A56DB")
    primary_color   = models.CharField(_("primary colour"),   max_length=7, default="#1A56DB")
    secondary_color = models.CharField(_("secondary colour"), max_length=7, default="#6B7280")
    accent_color    = models.CharField(_("accent colour"),    max_length=7, default="#10B981")
    text_color      = models.CharField(_("text colour"),      max_length=7, default="#111827")
    background_color = models.CharField(_("background colour"), max_length=7, default="#FFFFFF")

    # Typography
    font_family    = models.CharField(
        _("font family"), max_length=60, default="Inter",
        help_text=_("Google Fonts family name loaded in PDF templates."),
    )
    font_size_body = models.PositiveSmallIntegerField(_("body font size (pt)"), default=10)

    # Optional assets
    stamp     = models.ImageField(
        _("company stamp / seal"), upload_to=_stamp_upload_path, null=True, blank=True,
    )
    signature = models.ImageField(
        _("authorised signature"), upload_to=_signature_upload_path, null=True, blank=True,
    )

    # Footer / header text injected into PDF templates
    invoice_header_text = models.TextField(_("invoice header text"), blank=True)
    invoice_footer_text = models.TextField(
        _("invoice footer text"), blank=True,
        default="Thank you for your business.",
    )
    quotation_footer_text = models.TextField(_("quotation footer text"), blank=True)
    contract_footer_text  = models.TextField(_("contract footer text"),  blank=True)

    # Terms & conditions snippets
    invoice_terms    = models.TextField(_("invoice terms"),    blank=True)
    quotation_terms  = models.TextField(_("quotation terms"),  blank=True)

    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name        = _("company branding")
        verbose_name_plural = _("company brandings")

    def __str__(self) -> str:
        return f"Branding({self.company.name})"


# ---------------------------------------------------------------------------
# VAT / Tax Configuration
# ---------------------------------------------------------------------------

class VATConfig(models.Model):
    """
    Tax configuration per company.
    Supports multiple named tax rates (VAT, WHT, GST, etc.).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.OneToOneField(
        Company,
        on_delete=models.CASCADE,
        related_name="vat_config",
    )

    # Primary VAT / sales tax
    vat_number      = models.CharField(_("VAT / TIN number"), max_length=50, blank=True)
    vat_registered  = models.BooleanField(_("VAT registered"), default=False)
    vat_rate        = models.DecimalField(
        _("VAT rate (%)"), max_digits=5, decimal_places=2, default=0,
        help_text=_("e.g. 16 for 16 % Kenyan VAT."),
    )
    vat_label       = models.CharField(_("VAT label"), max_length=20, default="VAT")

    # Withholding tax
    wht_applicable  = models.BooleanField(_("withholding tax applicable"), default=False)
    wht_rate        = models.DecimalField(
        _("WHT rate (%)"), max_digits=5, decimal_places=2, default=0,
    )
    wht_label       = models.CharField(_("WHT label"), max_length=20, default="WHT")

    # Additional tax line (e.g. County levy, GST)
    extra_tax_label  = models.CharField(_("extra tax label"), max_length=20, blank=True)
    extra_tax_rate   = models.DecimalField(
        _("extra tax rate (%)"), max_digits=5, decimal_places=2, default=0,
    )

    # Display preferences
    prices_include_tax = models.BooleanField(
        _("prices include tax"), default=False,
        help_text=_("If True, line item prices are treated as tax-inclusive."),
    )
    show_tax_breakdown = models.BooleanField(_("show tax breakdown on documents"), default=True)

    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name        = _("VAT configuration")
        verbose_name_plural = _("VAT configurations")

    def __str__(self) -> str:
        return f"VATConfig({self.company.name}, {self.vat_rate}%)"


# ---------------------------------------------------------------------------
# Company Membership (join table used by users/permissions.py)
# ---------------------------------------------------------------------------

class CompanyMembership(models.Model):
    """
    Maps users → companies with a workspace-scoped role.
    Referenced directly in users/permissions.py → IsCompanyMember.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="company_memberships",
    )
    role = models.CharField(
        _("workspace role"),
        max_length=20,
        choices=[(r.value, r.name.title()) for r in MemberRole],
        default=MemberRole.STAFF,
    )
    is_active   = models.BooleanField(_("active"), default=True)
    invited_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="sent_invitations",
    )
    joined_at   = models.DateTimeField(_("joined at"), null=True, blank=True)
    created_at  = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at  = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name        = _("company membership")
        verbose_name_plural = _("company memberships")
        unique_together     = [("company", "user")]
        indexes = [
            models.Index(fields=["company", "is_active"]),
            models.Index(fields=["user", "is_active"]),
        ]

    def accept(self) -> None:
        """Mark membership as accepted/active with a join timestamp."""
        self.is_active = True
        self.joined_at = timezone.now()
        self.save(update_fields=["is_active", "joined_at", "updated_at"])

    def __str__(self) -> str:
        return f"{self.user} @ {self.company} [{self.role}]"