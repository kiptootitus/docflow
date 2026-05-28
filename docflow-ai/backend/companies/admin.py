"""
DocFlow AI — companies/admin.py

Django admin configuration for Company, Branding, VAT, and Membership.
"""

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import Company, CompanyBranding, CompanyMembership, VATConfig


# ---------------------------------------------------------------------------
# Inline admins
# ---------------------------------------------------------------------------

class CompanyBrandingInline(admin.StackedInline):
    model  = CompanyBranding
    extra  = 0
    fields = (
        "primary_color", "secondary_color", "accent_color",
        "font_family", "font_size_body",
        "invoice_footer_text", "invoice_terms",
    )


class VATConfigInline(admin.StackedInline):
    model  = VATConfig
    extra  = 0
    fields = (
        "vat_number", "vat_registered", "vat_rate", "vat_label",
        "wht_applicable", "wht_rate",
        "prices_include_tax", "show_tax_breakdown",
    )


class CompanyMembershipInline(admin.TabularInline):
    model  = CompanyMembership
    extra  = 0
    fields = ("user", "role", "is_active", "joined_at")
    readonly_fields = ("joined_at",)
    raw_id_fields   = ("user",)


# ---------------------------------------------------------------------------
# Company Admin
# ---------------------------------------------------------------------------

@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = (
        "name", "owner_email", "country", "currency",
        "is_active", "is_deleted_display", "created_at",
    )
    list_filter  = ("is_active", "country", "size", "created_at")
    search_fields = ("name", "slug", "email", "owner__email", "registration_number")
    readonly_fields = (
        "id", "slug", "created_at", "updated_at", "deleted_at",
        "next_invoice_number", "next_quotation_number", "next_contract_number",
    )
    raw_id_fields = ("owner",)
    inlines       = [CompanyBrandingInline, VATConfigInline, CompanyMembershipInline]

    fieldsets = (
        (_("Identity"), {
            "fields": ("id", "name", "slug", "owner", "logo", "is_active"),
        }),
        (_("Contact"), {
            "fields": (
                "email", "phone", "website",
                "address_line1", "address_line2", "city", "state",
                "postal_code", "country",
            ),
        }),
        (_("Business"), {
            "fields": ("registration_number", "size", "industry"),
        }),
        (_("Locale & Defaults"), {
            "fields": (
                "currency", "timezone_name", "language", "date_format",
                "default_payment_terms",
            ),
        }),
        (_("Document Numbering"), {
            "fields": (
                "invoice_prefix", "next_invoice_number",
                "quotation_prefix", "next_quotation_number",
                "contract_prefix", "next_contract_number",
            ),
        }),
        (_("Banking"), {
            "fields": (
                "bank_name", "bank_account_name", "bank_account_number",
                "bank_branch_code", "swift_code", "iban",
                "mpesa_paybill", "mpesa_till",
            ),
            "classes": ("collapse",),
        }),
        (_("Timestamps"), {
            "fields": ("created_at", "updated_at", "deleted_at"),
            "classes": ("collapse",),
        }),
    )

    def owner_email(self, obj: Company) -> str:
        return obj.owner.email
    owner_email.short_description = _("Owner")
    owner_email.admin_order_field = "owner__email"

    def is_deleted_display(self, obj: Company) -> str:
        if obj.is_deleted:
            return format_html('<span style="color:red;">✗ Deleted</span>')
        return format_html('<span style="color:green;">✓ Active</span>')
    is_deleted_display.short_description = _("Status")

    actions = ["soft_delete_selected", "restore_selected"]

    @admin.action(description=_("Soft-delete selected companies"))
    def soft_delete_selected(self, request, queryset):
        for company in queryset:
            company.soft_delete()
        self.message_user(request, _("Selected companies have been soft-deleted."))

    @admin.action(description=_("Restore selected companies"))
    def restore_selected(self, request, queryset):
        queryset.update(is_active=True, deleted_at=None)
        self.message_user(request, _("Selected companies have been restored."))


# ---------------------------------------------------------------------------
# Membership Admin
# ---------------------------------------------------------------------------

@admin.register(CompanyMembership)
class CompanyMembershipAdmin(admin.ModelAdmin):
    list_display  = ("user", "company", "role", "is_active", "joined_at", "created_at")
    list_filter   = ("role", "is_active")
    search_fields = ("user__email", "company__name")
    readonly_fields = ("id", "created_at", "updated_at", "joined_at")
    raw_id_fields   = ("user", "company", "invited_by")