# ─────────────────────────────────────────────────────────────────────────────
# DocFlow AI — documents/admin.py
# ================================
# Enterprise-grade Django admin for all document models.
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import csv
from decimal import Decimal

from django.contrib import admin, messages
from django.db.models import Count, QuerySet, Sum
from django.http import HttpResponse, HttpRequest
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import (
    ActivityAction,
    Contract,
    ContractStatus,
    DocumentActivity,
    DocumentAttachment,
    DocumentVersion,
    Invoice,
    InvoiceStatus,
    LineItem,
    LineItemType,
    PaymentRecord,
    Quotation,
    QuotationStatus,
    RecurringInvoice,
)


# ===========================================================================
# HELPERS
# ===========================================================================

# Status → (background, text) hex pairs
_STATUS_COLORS: dict[str, tuple[str, str]] = {
    # Invoice
    "draft":     ("#F3F4F6", "#374151"),
    "sent":      ("#DBEAFE", "#1D4ED8"),
    "viewed":    ("#E0F2FE", "#0369A1"),
    "partial":   ("#FEF3C7", "#92400E"),
    "paid":      ("#D1FAE5", "#065F46"),
    "overdue":   ("#FEE2E2", "#991B1B"),
    "void":      ("#F3F4F6", "#9CA3AF"),
    "cancelled": ("#F3F4F6", "#9CA3AF"),
    # Quotation
    "accepted":  ("#D1FAE5", "#065F46"),
    "declined":  ("#FEE2E2", "#991B1B"),
    "expired":   ("#FEF3C7", "#92400E"),
    # Contract
    "pending":   ("#FEF3C7", "#92400E"),
    "signed":    ("#D1FAE5", "#065F46"),
    "active":    ("#DCFCE7", "#15803D"),
    "completed": ("#E0F2FE", "#0369A1"),
}


def _status_badge(status_value: str) -> str:
    bg, fg = _STATUS_COLORS.get(status_value, ("#F3F4F6", "#374151"))
    return format_html(
        '<span style="'
        "background:{bg};color:{fg};padding:2px 8px;"
        "border-radius:9999px;font-size:11px;font-weight:600;"
        'white-space:nowrap">{label}</span>',
        bg=bg, fg=fg,
        label=status_value.upper(),
    )


def _currency_display(amount: Decimal, currency: str = "USD") -> str:
    return format_html(
        '<span style="font-family:monospace">{} {:,.2f}</span>',
        currency,
        amount,
    )


def _export_csv(queryset: QuerySet, fields: list[str], filename: str) -> HttpResponse:
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow(fields)
    for obj in queryset.values_list(*fields):
        writer.writerow(obj)
    return response


# ===========================================================================
# INLINES
# ===========================================================================

class LineItemInline(admin.TabularInline):
    model       = LineItem
    extra       = 0
    can_delete  = True
    show_change_link = False
    fields      = [
        "sort_order", "item_type", "description",
        "quantity", "unit_of_measure", "unit_label",
        "unit_price", "discount_percent", "tax_rate",
        "gross_amount_col", "line_total_col",
    ]
    readonly_fields = ["gross_amount_col", "line_total_col"]
    ordering        = ["sort_order", "created_at"]

    @admin.display(description=_("Gross"))
    def gross_amount_col(self, obj: LineItem) -> str:
        return format_html('<span style="font-family:monospace">{:,.2f}</span>', obj.gross_amount)

    @admin.display(description=_("Line Total"))
    def line_total_col(self, obj: LineItem) -> str:
        return format_html('<span style="font-family:monospace;font-weight:bold">{:,.2f}</span>', obj.line_total)


class PaymentRecordInline(admin.TabularInline):
    model       = PaymentRecord
    extra       = 0
    can_delete  = False
    fields      = [
        "payment_date", "amount", "currency",
        "payment_method", "reference",
        "is_reversed", "reversed_at", "recorded_by",
    ]
    readonly_fields = ["is_reversed", "reversed_at", "recorded_by", "created_at"]
    ordering        = ["-payment_date"]

    def has_add_permission(self, request, obj=None):
        return False


class DocumentAttachmentInline(admin.TabularInline):
    model      = DocumentAttachment
    extra      = 0
    fields     = ["original_name", "attachment_type", "mime_type", "file_size_display", "uploaded_by", "created_at"]
    readonly_fields = ["original_name", "mime_type", "file_size_display", "uploaded_by", "created_at"]

    @admin.display(description=_("Size"))
    def file_size_display(self, obj: DocumentAttachment) -> str:
        kb = obj.file_size / 1024
        if kb > 1024:
            return f"{kb/1024:.1f} MB"
        return f"{kb:.0f} KB"


# ===========================================================================
# SHARED MIXIN
# ===========================================================================

class DocumentAdminMixin:
    """Shared behaviour for Invoice, Quotation, Contract admins."""

    # ── Display helpers ───────────────────────────────────────────────────

    @admin.display(description=_("Status"), ordering="status")
    def status_badge(self, obj) -> str:
        return _status_badge(obj.status)

    @admin.display(description=_("Company"), ordering="company__name")
    def company_link(self, obj) -> str:
        url = reverse("admin:companies_company_change", args=[obj.company_id])
        return format_html('<a href="{}">{}</a>', url, obj.company.name)

    @admin.display(description=_("Client"))
    def client_col(self, obj) -> str:
        return obj.client_display_name

    @admin.display(description=_("Total"), ordering="total")
    def total_col(self, obj) -> str:
        return _currency_display(obj.total, obj.currency)

    @admin.display(description=_("Balance Due"))
    def balance_col(self, obj) -> str:
        bd = obj.balance_due
        color = "#DC2626" if bd > 0 else "#16A34A"
        return format_html(
            '<span style="color:{};font-family:monospace;font-weight:600">{} {:,.2f}</span>',
            color, obj.currency, bd,
        )

    @admin.display(description=_("PDF"), boolean=False)
    def pdf_link(self, obj) -> str:
        if obj.pdf_file:
            return format_html('<a href="{}" target="_blank">📄 Download</a>', obj.pdf_file.url)
        return "—"

    @admin.display(description=_("Recent Audit Trail (Last 10)"))
    def recent_activity_log(self, obj) -> str:
        if not obj or not obj.pk:
            return format_html('<span style="color: #6B7280; font-style: italic;">{}</span>', _("Save document to view activity logs."))
        
        doc_type = obj._meta.model_name
        activities = DocumentActivity.objects.filter(doc_type=doc_type, doc_id=obj.pk).order_by("-created_at")[:10]
        
        if not activities.exists():
            return format_html('<span style="color: #6B7280; font-style: italic;">{}</span>', _("No activity logs recorded."))
        
        html = [
            '<div style="overflow-x:auto; max-height:250px;">',
            '<table style="width:100%; border-collapse: collapse; text-align: left; font-size: 12px;">',
            '<thead>',
            '<tr style="border-bottom: 2px solid #E5E7EB; background: #F9FAFB; color: #374151;">',
            '<th style="padding: 6px 8px;">Date & Time</th>',
            '<th style="padding: 6px 8px;">Action</th>',
            '<th style="padding: 6px 8px;">Actor</th>',
            '<th style="padding: 6px 8px;">Note</th>',
            '</tr>',
            '</thead>',
            '<tbody>'
        ]
        for act in activities:
            html.append('<tr style="border-bottom: 1px solid #F3F4F6; color: #4B5563;">')
            html.append(f'<td style="padding: 6px 8px; font-family: monospace;">{act.created_at.strftime("%Y-%m-%d %H:%M:%S")}</td>')
            html.append(f'<td style="padding: 6px 8px;"><span style="font-weight: 600; text-transform: uppercase; font-size: 10px; background: #EDF2F7; padding: 2px 6px; border-radius: 4px;">{act.action}</span></td>')
            html.append(f'<td style="padding: 6px 8px; font-weight: 500;">{act.actor if act.actor else "System"}</td>')
            html.append(f'<td style="padding: 6px 8px;">{act.note}</td>')
            html.append('</tr>')
            
        html.append('</tbody></table></div>')
        return format_html("".join(html))

    # ── Admin actions ─────────────────────────────────────────────────────

    @admin.action(description=_("Generate PDF for selected documents"))
    def generate_pdfs(self, request: HttpRequest, queryset: QuerySet) -> None:
        from .tasks import generate_pdf_task
        doc_type = queryset.model.__name__.lower()
        count = 0
        for doc in queryset:
            generate_pdf_task.delay(doc_type, str(doc.pk))
            count += 1
        self.message_user(request, _(f"PDF generation queued for {count} document(s)."), messages.SUCCESS)

    @admin.action(description=_("Send email for selected documents"))
    def send_emails(self, request: HttpRequest, queryset: QuerySet) -> None:
        from .tasks import send_document_email_task
        doc_type = queryset.model.__name__.lower()
        count = 0
        for doc in queryset.filter(client_email__isnull=False).exclude(client_email=""):
            send_document_email_task.delay(doc_type, str(doc.pk))
            count += 1
        self.message_user(request, _(f"Email queued for {count} document(s)."), messages.SUCCESS)

    @admin.action(description=_("Export selected to CSV"))
    def export_csv(self, request: HttpRequest, queryset: QuerySet) -> HttpResponse:
        doc_type = queryset.model.__name__.lower()
        fields   = ["number", "status", "client_name", "client_email",
                    "currency", "total", "created_at"]
        return _export_csv(queryset, fields, f"{doc_type}_export.csv")


# ===========================================================================
# INVOICE ADMIN
# ===========================================================================

@admin.register(Invoice)
class InvoiceAdmin(DocumentAdminMixin, admin.ModelAdmin):

    list_display    = [
        "number", "status_badge", "company_link", "client_col",
        "issue_date", "due_date",
        "total_col", "balance_col",
        "overdue_flag", "pdf_link",
        "created_at",
    ]
    list_filter     = [
        "status", "currency",
        ("issue_date",  admin.DateFieldListFilter),
        ("due_date",    admin.DateFieldListFilter),
        ("created_at",  admin.DateFieldListFilter),
        "company",
    ]
    search_fields   = ["number", "client_name", "client_email", "subject", "company__name"]
    date_hierarchy  = "issue_date"
    ordering        = ["-created_at"]
    readonly_fields = [
        "id", "number", "portal_token",
        "subtotal", "discount_amount", "tax_amount", "total", "amount_paid",
        "balance_due_display", "payment_percentage_display",
        "sent_at", "viewed_at", "paid_at",
        "stripe_payment_intent_id", "stripe_payment_link_url",
        "pdf_file", "docx_file",
        "created_by", "created_at", "updated_at", "deleted_at",
        "recent_activity_log",
    ]
    show_full_result_count = False
    inlines = [LineItemInline, PaymentRecordInline, DocumentAttachmentInline]
    actions = ["generate_pdfs", "send_emails", "export_csv", "bulk_void"]

    fieldsets = [
        (_("Identity"), {
            "fields": ["id", "number", "status", "company", "created_by"],
        }),
        (_("Client"), {
            "fields": [
                "client", "client_salutation",
                ("client_name", "client_email"),
                ("client_phone", "client_vat_number"),
                "client_address",
            ],
        }),
        (_("Dates & Currency"), {
            "fields": [("issue_date", "due_date"), "currency"],
        }),
        (_("Content"), {
            "fields": ["subject", "notes", "terms"],
            "classes": ["collapse"],
        }),
        (_("Financials"), {
            "fields": [
                ("subtotal", "discount_amount", "tax_amount", "total"),
                ("amount_paid", "balance_due_display", "payment_percentage_display"),
            ],
        }),
        (_("Stripe / Portal"), {
            "fields": [
                "stripe_payment_intent_id",
                "stripe_payment_link_url",
                "portal_token",
            ],
            "classes": ["collapse"],
        }),
        (_("Files"), {
            "fields": ["pdf_file", "docx_file"],
        }),
        (_("Timestamps"), {
            "fields": [("sent_at", "viewed_at", "paid_at"),
                       ("created_at", "updated_at", "deleted_at")],
            "classes": ["collapse"],
        }),
        (_("Audit Log"), {
            "fields": ["recent_activity_log"],
        }),
    ]

    @admin.display(description=_("Overdue"), boolean=True)
    def overdue_flag(self, obj: Invoice) -> bool:
        return obj.is_overdue

    @admin.display(description=_("Balance Due"))
    def balance_due_display(self, obj: Invoice) -> str:
        return f"{obj.currency} {obj.balance_due:,.2f}"

    @admin.display(description=_("Paid %"))
    def payment_percentage_display(self, obj: Invoice) -> str:
        pct = obj.payment_percentage
        color = "#16A34A" if pct >= 100 else "#D97706" if pct > 0 else "#6B7280"
        return format_html(
            '<div style="display:flex;align-items:center;gap:8px">'
            '<div style="background:#E5E7EB;border-radius:4px;height:8px;width:80px">'
            '<div style="background:{color};height:8px;border-radius:4px;width:{pct}%"></div></div>'
            '<span style="color:{color};font-weight:600">{pct}%</span></div>',
            color=color, pct=pct,
        )

    @admin.action(description=_("Void selected invoices"))
    def bulk_void(self, request: HttpRequest, queryset: QuerySet) -> None:
        safe = queryset.exclude(status__in=[InvoiceStatus.PAID, InvoiceStatus.VOID])
        count = safe.update(status=InvoiceStatus.VOID)
        self.message_user(request, _(f"{count} invoice(s) voided."), messages.WARNING)

    def get_queryset(self, request):
        return (
            super().get_queryset(request)
            .select_related("company", "client", "created_by")
            .prefetch_related("line_items", "payment_records")
        )


# ===========================================================================
# QUOTATION ADMIN
# ===========================================================================

@admin.register(Quotation)
class QuotationAdmin(DocumentAdminMixin, admin.ModelAdmin):

    list_display  = [
        "number", "status_badge", "company_link", "client_col",
        "issue_date", "valid_until",
        "total_col", "expiry_status",
        "pdf_link", "created_at",
    ]
    list_filter   = [
        "status", "currency",
        ("issue_date",  admin.DateFieldListFilter),
        ("valid_until", admin.DateFieldListFilter),
        "company",
    ]
    search_fields   = ["number", "client_name", "client_email", "subject", "company__name"]
    date_hierarchy  = "issue_date"
    ordering        = ["-created_at"]
    readonly_fields = [
        "id", "number",
        "subtotal", "discount_amount", "tax_amount", "total",
        "sent_at", "accepted_at", "declined_at",
        "pdf_file", "docx_file",
        "created_by", "created_at", "updated_at",
        "recent_activity_log",
    ]
    show_full_result_count = False
    inlines = [LineItemInline, DocumentAttachmentInline]
    actions = ["generate_pdfs", "send_emails", "export_csv"]

    fieldsets = [
        (_("Identity"),     {"fields": ["id", "number", "status", "company", "created_by"]}),
        (_("Client"),       {"fields": [
            "client", "client_salutation",
            ("client_name", "client_email"),
            ("client_phone", "client_vat_number"),
            "client_address",
        ]}),
        (_("Dates"),        {"fields": [("issue_date", "due_date", "valid_until"), "currency"]}),
        (_("Content"),      {"fields": ["subject", "notes", "terms"], "classes": ["collapse"]}),
        (_("Financials"),   {"fields": [("subtotal", "discount_amount", "tax_amount", "total")]}),
        (_("Timestamps"),   {"fields": [("sent_at", "accepted_at", "declined_at"),
                                         ("created_at", "updated_at")], "classes": ["collapse"]}),
        (_("Files"),        {"fields": ["pdf_file", "docx_file"]}),
        (_("Audit Log"), {
            "fields": ["recent_activity_log"],
        }),
    ]

    @admin.display(description=_("Validity"))
    def expiry_status(self, obj: Quotation) -> str:
        if obj.is_expired:
            return format_html('<span style="color:#DC2626;font-weight:600">Expired</span>')
        if obj.days_until_expiry is not None and obj.days_until_expiry <= 3:
            return format_html(
                '<span style="color:#D97706;font-weight:600">{} days left</span>',
                obj.days_until_expiry,
            )
        if obj.days_until_expiry is not None:
            return format_html('<span style="color:#16A34A">{} days</span>', obj.days_until_expiry)
        return "—"

    def get_queryset(self, request):
        return (
            super().get_queryset(request)
            .select_related("company", "client", "created_by")
            .prefetch_related("line_items")
        )


# ===========================================================================
# CONTRACT ADMIN
# ===========================================================================

@admin.register(Contract)
class ContractAdmin(DocumentAdminMixin, admin.ModelAdmin):

    list_display  = [
        "number", "status_badge", "company_link", "client_col",
        "start_date", "end_date",
        "expiry_badge", "auto_renew",
        "signed_by_name",
        "pdf_link", "created_at",
    ]
    list_filter   = [
        "status", "auto_renew",
        ("start_date", admin.DateFieldListFilter),
        ("end_date",   admin.DateFieldListFilter),
        "company",
    ]
    search_fields   = ["number", "client_name", "client_email", "subject", "signed_by_name", "company__name"]
    date_hierarchy  = "issue_date"
    ordering        = ["-created_at"]
    readonly_fields = [
        "id", "number",
        "subtotal", "discount_amount", "tax_amount", "total",
        "sent_at", "signed_at", "signed_by_name", "signature_ip",
        "ai_reviewed_at",
        "pdf_file", "docx_file",
        "created_by", "created_at", "updated_at",
        "recent_activity_log",
    ]
    show_full_result_count = False
    inlines = [DocumentAttachmentInline]
    actions = ["generate_pdfs", "send_emails", "export_csv"]

    fieldsets = [
        (_("Identity"),     {"fields": ["id", "number", "status", "company", "created_by"]}),
        (_("Client"),       {"fields": [
            "client", "client_salutation",
            ("client_name", "client_email"),
            ("client_phone",),
            "client_address",
        ]}),
        (_("Dates"),        {"fields": [
            ("issue_date", "due_date"),
            ("start_date", "end_date"),
            ("auto_renew", "renewal_notice_days"),
        ]}),
        (_("Content"),      {"fields": ["subject", "currency", "body", "notes", "terms"]}),
        (_("Financials"),   {"fields": [("subtotal", "discount_amount", "tax_amount", "total")]}),
        (_("Signing"),      {"fields": [
            "sent_at", "signed_at", "signed_by_name", "signature_ip",
            "docusign_envelope_id", "hellosign_signature_id",
        ]}),
        (_("AI Review"),    {"fields": ["ai_review", "ai_reviewed_at"], "classes": ["collapse"]}),
        (_("Files"),        {"fields": ["pdf_file", "docx_file"]}),
        (_("Timestamps"),   {"fields": [("created_at", "updated_at")], "classes": ["collapse"]}),
        (_("Audit Log"), {
            "fields": ["recent_activity_log"],
        }),
    ]

    @admin.display(description=_("Expiry"), ordering="end_date")
    def expiry_badge(self, obj: Contract) -> str:
        if not obj.end_date:
            return "—"
        if obj.is_expired:
            return format_html('<span style="color:#DC2626;font-weight:600">Expired</span>')
        if obj.is_expiring_soon:
            return format_html(
                '<span style="color:#D97706;font-weight:600">⚠ {} days</span>',
                obj.days_until_expiry,
            )
        return format_html(
            '<span style="color:#6B7280">{}</span>', obj.end_date
        )

    def get_queryset(self, request):
        return (
            super().get_queryset(request)
            .select_related("company", "client", "created_by")
        )


# ===========================================================================
# LINE ITEM ADMIN (standalone)
# ===========================================================================

@admin.register(LineItem)
class LineItemAdmin(admin.ModelAdmin):
    list_display  = [
        "description", "item_type_badge",
        "invoice_link", "quotation_link",
        "quantity", "unit_price_col",
        "discount_percent", "line_total_col",
        "sort_order",
    ]
    list_filter   = ["item_type"]
    search_fields = ["description", "invoice__number", "quotation__number"]
    readonly_fields = [
        "id", "gross_amount_display",
        "discount_value_display", "line_total_display",
        "created_at",
    ]
    ordering = ["-created_at"]

    @admin.display(description=_("Type"))
    def item_type_badge(self, obj: LineItem) -> str:
        colors = {
            LineItemType.SERVICE:  ("#DBEAFE", "#1D4ED8"),
            LineItemType.PRODUCT:  ("#D1FAE5", "#065F46"),
            LineItemType.EXPENSE:  ("#FEF3C7", "#92400E"),
            LineItemType.DISCOUNT: ("#FEE2E2", "#991B1B"),
            LineItemType.OTHER:    ("#F3F4F6", "#374151"),
        }
        bg, fg = colors.get(obj.item_type, ("#F3F4F6", "#374151"))
        return format_html(
            '<span style="background:{};color:{};padding:1px 6px;border-radius:9999px;font-size:11px">{}</span>',
            bg, fg, obj.item_type.upper(),
        )

    @admin.display(description=_("Invoice"))
    def invoice_link(self, obj: LineItem) -> str:
        if obj.invoice:
            url = reverse("admin:documents_invoice_change", args=[obj.invoice_id])
            return format_html('<a href="{}">{}</a>', url, obj.invoice.number)
        return "—"

    @admin.display(description=_("Quotation"))
    def quotation_link(self, obj: LineItem) -> str:
        if obj.quotation:
            url = reverse("admin:documents_quotation_change", args=[obj.quotation_id])
            return format_html('<a href="{}">{}</a>', url, obj.quotation.number)
        return "—"

    @admin.display(description=_("Unit Price"))
    def unit_price_col(self, obj: LineItem) -> str:
        return format_html('<span style="font-family:monospace">{:,.2f}</span>', obj.unit_price)

    @admin.display(description=_("Line Total"))
    def line_total_col(self, obj: LineItem) -> str:
        return format_html('<span style="font-family:monospace;font-weight:bold">{:,.2f}</span>', obj.line_total)

    @admin.display(description=_("Gross Amount"))
    def gross_amount_display(self, obj: LineItem) -> str:
        return f"{obj.gross_amount:,.2f}"

    @admin.display(description=_("Discount Value"))
    def discount_value_display(self, obj: LineItem) -> str:
        return f"{obj.discount_value:,.2f}"

    @admin.display(description=_("Line Total"))
    def line_total_display(self, obj: LineItem) -> str:
        return f"{obj.line_total:,.2f}"


# ===========================================================================
# PAYMENT RECORD ADMIN
# ===========================================================================

@admin.register(PaymentRecord)
class PaymentRecordAdmin(admin.ModelAdmin):
    list_display  = [
        "invoice_link", "amount_col", "currency",
        "payment_method", "payment_date",
        "reference", "reversed_badge", "recorded_by",
        "created_at",
    ]
    list_filter   = ["payment_method", "is_reversed", "currency",
                     ("payment_date", admin.DateFieldListFilter)]
    search_fields = ["invoice__number", "reference", "invoice__client_name"]
    date_hierarchy = "payment_date"
    ordering      = ["-payment_date"]
    readonly_fields = [
        "id", "is_reversed", "reversed_at", "reversed_by",
        "recorded_by", "created_at",
    ]

    @admin.display(description=_("Invoice"))
    def invoice_link(self, obj: PaymentRecord) -> str:
        url = reverse("admin:documents_invoice_change", args=[obj.invoice_id])
        return format_html('<a href="{}">{}</a>', url, obj.invoice.number)

    @admin.display(description=_("Amount"), ordering="amount")
    def amount_col(self, obj: PaymentRecord) -> str:
        return format_html(
            '<span style="font-family:monospace;font-weight:600">{:,.2f}</span>', obj.amount
        )

    @admin.display(description=_("Reversed"), boolean=True, ordering="is_reversed")
    def reversed_badge(self, obj: PaymentRecord) -> bool:
        return obj.is_reversed

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("invoice", "recorded_by", "reversed_by")


# ===========================================================================
# DOCUMENT ACTIVITY ADMIN (read-only)
# ===========================================================================

@admin.register(DocumentActivity)
class DocumentActivityAdmin(admin.ModelAdmin):
    list_display  = [
        "created_at", "doc_type", "doc_number_link",
        "action_badge", "actor", "actor_ip",
        "note_short",
    ]
    list_filter   = ["doc_type", "action",
                     ("created_at", admin.DateFieldListFilter)]
    search_fields = ["doc_number", "actor__email", "note"]
    date_hierarchy = "created_at"
    ordering      = ["-created_at"]
    readonly_fields = [f.name for f in DocumentActivity._meta.get_fields()
                       if hasattr(f, "name") and f.name != "id"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description=_("Document"))
    def doc_number_link(self, obj: DocumentActivity) -> str:
        admin_urls = {
            "invoice":   "admin:documents_invoice_change",
            "quotation": "admin:documents_quotation_change",
            "contract":  "admin:documents_contract_change",
        }
        url_name = admin_urls.get(obj.doc_type)
        if url_name:
            try:
                url = reverse(url_name, args=[obj.doc_id])
                return format_html('<a href="{}">#{}</a>', url, obj.doc_number or obj.doc_id)
            except Exception:
                pass
        return obj.doc_number or str(obj.doc_id)

    @admin.display(description=_("Action"))
    def action_badge(self, obj: DocumentActivity) -> str:
        action_colors = {
            ActivityAction.CREATED:    ("#DBEAFE", "#1D4ED8"),
            ActivityAction.SENT:       ("#E0F2FE", "#0369A1"),
            ActivityAction.PAID:       ("#D1FAE5", "#065F46"),
            ActivityAction.VOIDED:     ("#FEE2E2", "#991B1B"),
            ActivityAction.SIGNED:     ("#D1FAE5", "#065F46"),
            ActivityAction.AI_REVIEW:  ("#F3E8FF", "#6D28D9"),
            ActivityAction.DELETED:    ("#FEE2E2", "#991B1B"),
        }
        bg, fg = action_colors.get(obj.action, ("#F3F4F6", "#374151"))
        return format_html(
            '<span style="background:{};color:{};padding:1px 6px;border-radius:4px;font-size:11px">{}</span>',
            bg, fg, obj.action.upper(),
        )

    @admin.display(description=_("Note"))
    def note_short(self, obj: DocumentActivity) -> str:
        return (obj.note[:60] + "…") if len(obj.note) > 60 else obj.note


# ===========================================================================
# DOCUMENT VERSION ADMIN (read-only)
# ===========================================================================

@admin.register(DocumentVersion)
class DocumentVersionAdmin(admin.ModelAdmin):
    list_display  = ["doc_type", "doc_id", "version", "created_by", "created_at"]
    list_filter   = ["doc_type", ("created_at", admin.DateFieldListFilter)]
    search_fields = ["doc_id"]
    readonly_fields = ["id", "doc_type", "doc_id", "version", "snapshot", "created_by", "created_at"]
    ordering      = ["-created_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# ===========================================================================
# RECURRING INVOICE ADMIN
# ===========================================================================

@admin.register(RecurringInvoice)
class RecurringInvoiceAdmin(admin.ModelAdmin):
    list_display  = [
        "company_name", "template_link",
        "frequency", "next_invoice_date",
        "occurrences_sent", "max_occurrences",
        "auto_send", "active_badge",
        "created_at",
    ]
    list_filter   = [
        "frequency", "is_active", "auto_send",
        ("next_invoice_date", admin.DateFieldListFilter),
        "company",
    ]
    search_fields = ["company__name", "template__number"]
    ordering      = ["next_invoice_date"]
    readonly_fields = ["id", "occurrences_sent", "created_by", "created_at", "updated_at"]

    @admin.display(description=_("Company"), ordering="company__name")
    def company_name(self, obj: RecurringInvoice) -> str:
        return obj.company.name

    @admin.display(description=_("Template"), ordering="template__number")
    def template_link(self, obj: RecurringInvoice) -> str:
        url = reverse("admin:documents_invoice_change", args=[obj.template_id])
        return format_html('<a href="{}">{}</a>', url, obj.template.number)

    @admin.display(description=_("Active"), boolean=True)
    def active_badge(self, obj: RecurringInvoice) -> bool:
        return obj.is_active

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("company", "template", "created_by")


# ===========================================================================
# DOCUMENT ATTACHMENT ADMIN
# ===========================================================================

@admin.register(DocumentAttachment)
class DocumentAttachmentAdmin(admin.ModelAdmin):
    list_display  = [
        "original_name", "parent_document",
        "attachment_type", "mime_type",
        "file_size_col", "uploaded_by", "created_at",
    ]
    list_filter   = ["attachment_type",
                     ("created_at", admin.DateFieldListFilter)]
    search_fields = ["original_name", "invoice__number", "quotation__number", "contract__number"]
    readonly_fields = ["id", "uploaded_by", "created_at"]

    @admin.display(description=_("Document"))
    def parent_document(self, obj: DocumentAttachment) -> str:
        if obj.invoice_id:
            url = reverse("admin:documents_invoice_change", args=[obj.invoice_id])
            return format_html('<a href="{}">Invoice #{}</a>', url, obj.invoice.number)
        if obj.quotation_id:
            url = reverse("admin:documents_quotation_change", args=[obj.quotation_id])
            return format_html('<a href="{}">Quotation #{}</a>', url, obj.quotation.number)
        if obj.contract_id:
            url = reverse("admin:documents_contract_change", args=[obj.contract_id])
            return format_html('<a href="{}">Contract #{}</a>', url, obj.contract.number)
        return "—"

    @admin.display(description=_("Size"))
    def file_size_col(self, obj: DocumentAttachment) -> str:
        kb = obj.file_size / 1024
        if kb > 1024:
            return f"{kb/1024:.1f} MB"
        return f"{kb:.0f} KB"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            "invoice", "quotation", "contract", "uploaded_by"
        )