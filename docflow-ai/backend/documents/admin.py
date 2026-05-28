from decimal import Decimal

from django.contrib import admin, messages
from django.db.models import Sum, F
from django.utils import timezone

from .models import (
    Invoice,
    Quotation,
    Contract,
    LineItem,
    LineItemType,
    InvoiceStatus,
    QuotationStatus,
    ContractStatus,
)

# ----------------------------------------------------------------------
# INLINE: LINE ITEMS
# ----------------------------------------------------------------------

class LineItemInline(admin.TabularInline):
    model = LineItem
    extra = 0
    min_num = 1
    fields = (
        "item_type",
        "description",
        "quantity",
        "unit_of_measure",
        "unit_label",
        "unit_price",
        "discount_percent",
        "tax_rate",
        "sort_order",
        "gross_amount",
        "line_total",
    )
    readonly_fields = ("gross_amount", "line_total")
    ordering = ("sort_order",)

    def has_delete_permission(self, request, obj=None):
        return True


# ----------------------------------------------------------------------
# BASE ADMIN (SHARED LOGIC)
# ----------------------------------------------------------------------

class BaseDocumentAdmin(admin.ModelAdmin):
    list_display = (
        "number",
        "company",
        "client_display",
        "status",
        "total",
        "amount_paid",
        "balance_due_display",
        "issue_date",
        "due_date",
        "is_overdue_display",
        "is_active",
    )

    list_filter = (
        "status",
        "company",
        "currency",
        "is_active",
        "issue_date",
        "due_date",
    )

    search_fields = (
        "number",
        "client_name",
        "client_email",
        "client_phone",
    )

    readonly_fields = (
        "subtotal",
        "discount_amount",
        "tax_amount",
        "total",
        "amount_paid",
        "balance_due_display",
        "is_overdue_display",
        "created_at",
        "updated_at",
    )

    autocomplete_fields = ("company", "client", "created_by")

    fieldsets = (
        ("Core", {
            "fields": (
                "company",
                "number",
                "status",
                "currency",
                "is_active",
            )
        }),
        ("Client Info", {
            "fields": (
                "client",
                "client_salutation",
                "client_name",
                "client_email",
                "client_phone",
                "client_address",
                "client_vat_number",
            )
        }),
        ("Dates", {
            "fields": (
                "issue_date",
                "due_date",
            )
        }),
        ("Financials (Auto-calculated)", {
            "fields": (
                "subtotal",
                "discount_amount",
                "tax_amount",
                "total",
                "amount_paid",
                "balance_due_display",
            )
        }),
        ("Content", {
            "fields": (
                "subject",
                "notes",
                "terms",
            )
        }),
        ("System", {
            "fields": (
                "created_by",
                "created_at",
                "updated_at",
            )
        }),
    )

    def client_display(self, obj):
        return obj.client_display_name
    client_display.short_description = "Client"

    def balance_due_display(self, obj):
        return obj.balance_due
    balance_due_display.short_description = "Balance Due"

    def is_overdue_display(self, obj):
        return obj.is_overdue
    is_overdue_display.boolean = True
    is_overdue_display.short_description = "Overdue?"

    # ----------------------------
    # ACTIONS
    # ----------------------------

    def mark_as_sent(self, request, queryset):
        updated = queryset.update(status="sent", sent_at=timezone.now())
        self.message_user(request, f"{updated} documents marked as SENT", messages.SUCCESS)
    mark_as_sent.short_description = "Mark selected as SENT"

    def soft_delete(self, request, queryset):
        updated = queryset.update(is_active=False, deleted_at=timezone.now())
        self.message_user(request, f"{updated} documents soft deleted", messages.WARNING)
    soft_delete.short_description = "Soft delete selected"

    actions = ["mark_as_sent", "soft_delete"]


# ----------------------------------------------------------------------
# INVOICE ADMIN
# ----------------------------------------------------------------------

@admin.register(Invoice)
class InvoiceAdmin(BaseDocumentAdmin):
    inlines = [LineItemInline]

    list_display = BaseDocumentAdmin.list_display + (
        "paid_at",
        "sent_at",
    )

    list_filter = BaseDocumentAdmin.list_filter + (
        "status",
    )

    actions = BaseDocumentAdmin.actions + ["mark_as_paid"]

    def mark_as_paid(self, request, queryset):
        updated = 0
        for invoice in queryset:
            invoice.mark_paid()
            updated += 1

        self.message_user(
            request,
            f"{updated} invoices marked as PAID",
            messages.SUCCESS,
        )
    mark_as_paid.short_description = "Mark selected as PAID"


# ----------------------------------------------------------------------
# QUOTATION ADMIN
# ----------------------------------------------------------------------

@admin.register(Quotation)
class QuotationAdmin(BaseDocumentAdmin):
    inlines = [LineItemInline]

    list_display = BaseDocumentAdmin.list_display + (
        "valid_until",
        "accepted_at",
        "sent_at",
    )

    actions = BaseDocumentAdmin.actions + ["convert_to_invoice_action"]

    def convert_to_invoice_action(self, request, queryset):
        created = 0

        for quotation in queryset:
            invoice = quotation.convert_to_invoice()
            created += 1

        self.message_user(
            request,
            f"{created} invoices created from quotations",
            messages.SUCCESS,
        )

    convert_to_invoice_action.short_description = "Convert to Invoice"


# ----------------------------------------------------------------------
# CONTRACT ADMIN
# ----------------------------------------------------------------------

@admin.register(Contract)
class ContractAdmin(BaseDocumentAdmin):

    list_display = BaseDocumentAdmin.list_display + (
        "start_date",
        "end_date",
        "signed_at",
        "auto_renew",
    )

    list_filter = BaseDocumentAdmin.list_filter + (
        "auto_renew",
        "status",
    )

    readonly_fields = BaseDocumentAdmin.readonly_fields + (
        "ai_review",
    )

    fieldsets = BaseDocumentAdmin.fieldsets + (
        ("Contract Details", {
            "fields": (
                "body",
                "start_date",
                "end_date",
                "auto_renew",
                "renewal_notice_days",
            )
        }),
        ("Signature", {
            "fields": (
                "signed_at",
                "signed_by_name",
                "signature_ip",
                "docusign_envelope_id",
            )
        }),
        ("AI Review", {
            "fields": (
                "ai_review",
            )
        }),
    )


# ----------------------------------------------------------------------
# LINE ITEM ADMIN (optional direct access)
# ----------------------------------------------------------------------

@admin.register(LineItem)
class LineItemAdmin(admin.ModelAdmin):
    list_display = (
        "description",
        "item_type",
        "quantity",
        "unit_of_measure",
        "unit_label",
        "unit_price",
        "gross_amount",
        "line_total",
        "invoice",
        "quotation",
    )

    list_filter = ("item_type",)
    search_fields = ("description",)

    readonly_fields = ("gross_amount", "line_total")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("invoice", "quotation")