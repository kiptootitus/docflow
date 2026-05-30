"""
DocFlow AI — documents/serializers.py
=======================================
Enterprise-grade serializers for all document types.

Serializer map
──────────────
  LineItemSerializer              writable nested inside invoice/quotation
  LineItemBulkUpdateSerializer    bulk sort-order reordering

  InvoiceSerializer               full create + update (nested line items)
  InvoiceListSerializer           lightweight — list endpoint only
  InvoiceDetailSerializer         retrieve — adds payment summary + latest activity
  InvoicePortalSerializer         public portal — strips internal & financial-admin fields
  InvoiceDuplicateSerializer      POST /invoices/<pk>/duplicate/ input

  QuotationSerializer             full create + update (nested line items)
  QuotationListSerializer         lightweight — list endpoint only

  ContractSerializer              full create + update (no line items)
  ContractListSerializer          lightweight — list endpoint only

  PaymentRecordSerializer         create a payment against an invoice
  PaymentRecordListSerializer     lightweight read

  DocumentActivitySerializer      read-only audit trail
  DocumentVersionSerializer       read-only version history

  RecurringInvoiceSerializer      CRUD for recurring schedules
  DocumentAttachmentSerializer    file upload + list

Design rules
────────────
• Totals (subtotal, discount_amount, tax_amount, total) are ALWAYS read-only
  — they are computed server-side in compute_totals().
• document `number` is ALWAYS read-only — assigned by Company.get_next_*().
• `created_by` is injected from request.user — never from the client payload.
• Status transitions that are illegal raise a 400 ValidationError here,
  not in the view, so the same guard applies to both DRF and direct API calls.
• CompanyPublicSerializer is imported from companies.serializers.
  If that module doesn't exist yet, replace the import with a plain
  UUIDField(source='company.id', read_only=True) stub.
"""

from __future__ import annotations

from decimal import Decimal

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

# Local import — adjust if companies lives outside this package
try:
    from companies.serializers import CompanyPublicSerializer
except ImportError:
    # Stub: show only the company UUID until the companies app exists
    class CompanyPublicSerializer(serializers.Serializer):
        id   = serializers.UUIDField(read_only=True)
        name = serializers.CharField(read_only=True)

from .models import (
    ActivityAction,
    AttachmentType,
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
    RecurringFrequency,
    RecurringInvoice,
)


# ===========================================================================
# HELPERS
# ===========================================================================

def _assign_number(validated_data: dict, company, doc_type: str) -> str:
    """Ask the company for the next document number."""
    method_map = {
        "invoice":   "get_next_invoice_number",
        "quotation": "get_next_quotation_number",
        "contract":  "get_next_contract_number",
    }
    method = getattr(company, method_map[doc_type], None)
    return method() if callable(method) else ""


# ===========================================================================
# LINE ITEM
# ===========================================================================

class LineItemSerializer(serializers.ModelSerializer):
    """
    Writable serializer used *nested* inside Invoice / Quotation serializers.
    Computed properties (gross_amount etc.) are always read-only.
    """

    gross_amount   = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    discount_value = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    line_total     = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model  = LineItem
        fields = [
            "id",
            "item_type",
            "description",
            "quantity",
            "unit_of_measure",
            "unit_label",
            "unit_price",
            "discount_percent",
            "tax_rate",
            "gross_amount",
            "discount_value",
            "line_total",
            "sort_order",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "gross_amount",
            "discount_value",
            "line_total",
            "created_at",
        ]
        extra_kwargs = {
            "description":     {"required": True},
            "unit_price":      {"required": True},
        }

    # ── Field-level validation ────────────────────────────────────────────

    def validate_quantity(self, value: Decimal) -> Decimal:
        if value <= 0:
            raise serializers.ValidationError(_("Quantity must be greater than zero."))
        return value

    def validate_unit_of_measure(self, value: Decimal) -> Decimal:
        if value <= 0:
            raise serializers.ValidationError(_("Unit of measure multiplier must be greater than zero."))
        return value

    def validate_unit_price(self, value: Decimal) -> Decimal:
        if value < 0:
            raise serializers.ValidationError(_("Unit price cannot be negative."))
        return value

    def validate_discount_percent(self, value: Decimal) -> Decimal:
        if not (0 <= value <= 100):
            raise serializers.ValidationError(_("Discount must be between 0 and 100."))
        return value

    def validate_tax_rate(self, value: Decimal) -> Decimal:
        if not (0 <= value <= 100):
            raise serializers.ValidationError(_("Tax rate must be between 0 and 100."))
        return value


class LineItemBulkUpdateSerializer(serializers.Serializer):
    """
    POST /invoices/<pk>/reorder/
    Accepts [{"id": "uuid", "sort_order": 0}, …] and bulk-updates sort_order.
    """

    class _ItemOrder(serializers.Serializer):
        id         = serializers.UUIDField()
        sort_order = serializers.IntegerField(min_value=0)

    items = _ItemOrder(many=True)

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError(_("At least one item is required."))
        return value


# ===========================================================================
# INVOICE
# ===========================================================================

class _InvoiceLineItemsMixin:
    """Shared _save_line_items for Invoice and Quotation serializers."""

    def _save_line_items(self, document, items_data: list[dict], fk_field: str) -> None:
        """Replace all line items with the new list (delete-and-recreate)."""
        document.line_items.all().delete()
        for idx, item_data in enumerate(items_data):
            item_data.setdefault("sort_order", idx)
            LineItem.objects.create(**{fk_field: document}, **item_data)


class InvoiceSerializer(_InvoiceLineItemsMixin, serializers.ModelSerializer):
    """
    Full read / create / update serializer for Invoice.

    On write:
      • line_items replaces existing items entirely on every update.
      • compute_totals() is called after saving line items.
      • number and created_by are server-assigned.
    """

    line_items           = LineItemSerializer(many=True, required=False)
    company_detail       = CompanyPublicSerializer(source="company", read_only=True)
    balance_due          = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    is_overdue           = serializers.BooleanField(read_only=True)
    is_paid_in_full      = serializers.BooleanField(read_only=True)
    payment_percentage   = serializers.IntegerField(read_only=True)
    client_display_name  = serializers.CharField(read_only=True)
    client_formal_name   = serializers.CharField(read_only=True)

    class Meta:
        model  = Invoice
        fields = [
            # Identity
            "id", "number",
            # Company
            "company", "company_detail",
            # Client
            "client", "client_salutation",
            "client_name", "client_email", "client_phone",
            "client_address", "client_vat_number",
            "client_display_name", "client_formal_name",
            # Status & dates
            "status",
            "issue_date", "due_date",
            "sent_at", "viewed_at", "paid_at",
            # Content
            "currency", "subject", "notes", "terms",
            # Financials (server-computed)
            "subtotal", "discount_amount", "tax_amount", "total",
            "amount_paid", "balance_due",
            "is_overdue", "is_paid_in_full", "payment_percentage",
            # Stripe
            "stripe_payment_intent_id", "stripe_payment_link_url",
            # Files
            "pdf_file", "docx_file",
            # Line items (nested)
            "line_items",
            # Meta
            "created_by", "is_active",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "number",
            "subtotal", "discount_amount", "tax_amount", "total",
            "balance_due", "is_overdue", "is_paid_in_full", "payment_percentage",
            "client_display_name", "client_formal_name",
            "stripe_payment_link_url",
            "sent_at", "viewed_at", "paid_at",
            "pdf_file", "docx_file",
            "company_detail",
            "created_by",
            "is_active",
            "created_at", "updated_at",
        ]

    # ── Object-level validation ───────────────────────────────────────────

    def validate_status(self, value: str) -> str:
        instance = self.instance
        if instance is None:
            return value  # create — any status OK at start

        # Paid invoices are immutable
        if instance.status == InvoiceStatus.PAID and value != InvoiceStatus.PAID:
            raise serializers.ValidationError(_("A paid invoice cannot change status."))

        # Voided invoices are immutable
        if instance.status == InvoiceStatus.VOID and value != InvoiceStatus.VOID:
            raise serializers.ValidationError(_("A voided invoice cannot be reinstated."))

        return value

    def validate(self, attrs: dict) -> dict:
        instance = self.instance

        # Paid invoices — disallow changing financial content
        if instance and instance.status in (InvoiceStatus.PAID, InvoiceStatus.VOID):
            immutable_fields = {"line_items", "currency", "subtotal", "tax_amount"}
            changed = immutable_fields & set(attrs.keys())
            if changed:
                raise serializers.ValidationError(
                    _("Paid or voided invoices cannot be edited.")
                )
        return attrs

    # ── Write helpers ─────────────────────────────────────────────────────

    def create(self, validated_data: dict) -> Invoice:
        items_data = validated_data.pop("line_items", [])
        company    = validated_data["company"]

        validated_data["number"]     = _assign_number(validated_data, company, "invoice")
        validated_data["created_by"] = self.context["request"].user

        invoice = Invoice.objects.create(**validated_data)
        self._save_line_items(invoice, items_data, "invoice")
        invoice.compute_totals(save=True)

        # Log activity
        invoice.log_activity(
            ActivityAction.CREATED,
            actor=validated_data["created_by"],
        )
        return invoice

    def update(self, instance: Invoice, validated_data: dict) -> Invoice:
        items_data = validated_data.pop("line_items", None)

        # Snapshot before major edit
        if items_data is not None and instance.status == InvoiceStatus.DRAFT:
            self._save_version(instance)

        instance = super().update(instance, validated_data)

        if items_data is not None:
            self._save_line_items(instance, items_data, "invoice")
            instance.compute_totals(save=True)

        instance.log_activity(
            ActivityAction.UPDATED,
            actor=self.context["request"].user,
        )
        return instance

    @staticmethod
    def _save_version(instance: Invoice) -> None:
        """Snapshot current state into DocumentVersion."""
        from rest_framework.renderers import JSONRenderer
        count = DocumentVersion.objects.filter(
            doc_type="invoice", doc_id=instance.pk
        ).count()
        DocumentVersion.objects.create(
            doc_type   = "invoice",
            doc_id     = instance.pk,
            version    = count + 1,
            snapshot   = {
                "number":   instance.number,
                "status":   instance.status,
                "total":    str(instance.total),
                "currency": instance.currency,
                "subject":  instance.subject,
            },
        )


class InvoiceListSerializer(serializers.ModelSerializer):
    """Lightweight serializer — used for GET /invoices/ list responses."""

    balance_due         = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    client_display_name = serializers.CharField(read_only=True)
    is_overdue          = serializers.BooleanField(read_only=True)
    payment_percentage  = serializers.IntegerField(read_only=True)

    class Meta:
        model  = Invoice
        fields = [
            "id", "number", "status",
            "client_display_name",
            "issue_date", "due_date",
            "currency", "total", "amount_paid", "balance_due",
            "is_overdue", "payment_percentage",
            "pdf_file",
            "created_at",
        ]
        read_only_fields = fields


class InvoiceDetailSerializer(InvoiceSerializer):
    """
    Rich retrieve serializer — adds the last 5 activities and payment summary.
    Used for GET /invoices/<pk>/.
    """

    recent_activity = serializers.SerializerMethodField()
    payments        = serializers.SerializerMethodField()

    class Meta(InvoiceSerializer.Meta):
        fields = InvoiceSerializer.Meta.fields + ["recent_activity", "payments"]
        read_only_fields = InvoiceSerializer.Meta.read_only_fields + [
            "recent_activity", "payments"
        ]

    def get_recent_activity(self, obj: Invoice) -> list:
        qs = DocumentActivity.objects.filter(
            doc_type="invoice", doc_id=obj.pk
        ).order_by("-created_at")[:5]
        return DocumentActivitySerializer(qs, many=True).data

    def get_payments(self, obj: Invoice) -> list:
        qs = obj.payment_records.filter(is_reversed=False).order_by("-payment_date")
        return PaymentRecordListSerializer(qs, many=True).data


class InvoicePortalSerializer(serializers.ModelSerializer):
    """
    Public portal serializer — shown at /portal/?token=<jwt>.
    Strips all internal / admin-only fields.
    """

    line_items     = LineItemSerializer(many=True, read_only=True)
    balance_due    = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    company_detail = CompanyPublicSerializer(source="company", read_only=True)

    class Meta:
        model  = Invoice
        fields = [
            "id", "number", "status",
            "company_detail",
            "client_salutation", "client_name", "client_email",
            "issue_date", "due_date",
            "currency", "subject", "notes", "terms",
            "subtotal", "discount_amount", "tax_amount", "total",
            "amount_paid", "balance_due",
            "stripe_payment_link_url",
            "line_items",
        ]
        read_only_fields = fields


class InvoiceDuplicateSerializer(serializers.Serializer):
    """
    POST /invoices/<pk>/duplicate/
    Optional field: reset_status (default True → clones as DRAFT).
    """

    reset_status  = serializers.BooleanField(default=True)
    target_company = serializers.UUIDField(
        required=False,
        help_text=_("Duplicate into a different company (super-admin only)."),
    )


# ===========================================================================
# QUOTATION
# ===========================================================================

class QuotationSerializer(_InvoiceLineItemsMixin, serializers.ModelSerializer):

    line_items          = LineItemSerializer(many=True, required=False)
    company_detail      = CompanyPublicSerializer(source="company", read_only=True)
    balance_due         = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    client_display_name = serializers.CharField(read_only=True)
    client_formal_name  = serializers.CharField(read_only=True)
    is_expired          = serializers.BooleanField(read_only=True)
    days_until_expiry   = serializers.IntegerField(read_only=True)

    class Meta:
        model  = Quotation
        fields = [
            "id", "number",
            "company", "company_detail",
            "client", "client_salutation",
            "client_name", "client_email", "client_phone",
            "client_address", "client_vat_number",
            "client_display_name", "client_formal_name",
            "status",
            "issue_date", "due_date", "valid_until",
            "sent_at", "accepted_at", "declined_at", "decline_reason",
            "currency", "subject", "notes", "terms",
            "subtotal", "discount_amount", "tax_amount", "total",
            "amount_paid", "balance_due",
            "is_expired", "days_until_expiry",
            "pdf_file", "docx_file",
            "line_items",
            "created_by", "is_active",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "number",
            "subtotal", "discount_amount", "tax_amount", "total",
            "balance_due",
            "client_display_name", "client_formal_name",
            "is_expired", "days_until_expiry",
            "sent_at", "accepted_at", "declined_at",
            "pdf_file", "docx_file",
            "company_detail",
            "created_by", "is_active",
            "created_at", "updated_at",
        ]

    def validate_status(self, value: str) -> str:
        instance = self.instance
        if instance is None:
            return value
        if instance.status == QuotationStatus.ACCEPTED and value not in (
            QuotationStatus.ACCEPTED,
        ):
            raise serializers.ValidationError(_("An accepted quotation cannot be changed."))
        return value

    def create(self, validated_data: dict) -> Quotation:
        items_data = validated_data.pop("line_items", [])
        company    = validated_data["company"]

        validated_data["number"]     = _assign_number(validated_data, company, "quotation")
        validated_data["created_by"] = self.context["request"].user

        quotation = Quotation.objects.create(**validated_data)
        self._save_line_items(quotation, items_data, "quotation")
        quotation.compute_totals(save=True)
        quotation.log_activity(ActivityAction.CREATED, actor=validated_data["created_by"])
        return quotation

    def update(self, instance: Quotation, validated_data: dict) -> Quotation:
        items_data = validated_data.pop("line_items", None)
        instance   = super().update(instance, validated_data)

        if items_data is not None:
            self._save_line_items(instance, items_data, "quotation")
            instance.compute_totals(save=True)

        instance.log_activity(ActivityAction.UPDATED, actor=self.context["request"].user)
        return instance


class QuotationListSerializer(serializers.ModelSerializer):
    client_display_name = serializers.CharField(read_only=True)
    is_expired          = serializers.BooleanField(read_only=True)
    days_until_expiry   = serializers.IntegerField(read_only=True)

    class Meta:
        model  = Quotation
        fields = [
            "id", "number", "status",
            "client_display_name",
            "issue_date", "valid_until",
            "currency", "total",
            "is_expired", "days_until_expiry",
            "created_at",
        ]
        read_only_fields = fields


# ===========================================================================
# CONTRACT
# ===========================================================================

class ContractSerializer(serializers.ModelSerializer):

    company_detail      = CompanyPublicSerializer(source="company", read_only=True)
    client_display_name = serializers.CharField(read_only=True)
    client_formal_name  = serializers.CharField(read_only=True)
    is_expiring_soon    = serializers.BooleanField(read_only=True)
    days_until_expiry   = serializers.IntegerField(read_only=True)
    is_expired          = serializers.BooleanField(read_only=True)

    class Meta:
        model  = Contract
        fields = [
            "id", "number",
            "company", "company_detail",
            "client", "client_salutation",
            "client_name", "client_email", "client_phone",
            "client_address",
            "client_display_name", "client_formal_name",
            "status",
            "issue_date", "due_date",
            "start_date", "end_date",
            "auto_renew", "renewal_notice_days",
            "currency", "subject", "body", "notes", "terms",
            "subtotal", "discount_amount", "tax_amount", "total",
            "sent_at", "signed_at", "signed_by_name",
            "docusign_envelope_id", "hellosign_signature_id",
            "ai_review", "ai_reviewed_at",
            "is_expiring_soon", "days_until_expiry", "is_expired",
            "pdf_file", "docx_file",
            "created_by", "is_active",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "number",
            "subtotal", "discount_amount", "tax_amount", "total",
            "client_display_name", "client_formal_name",
            "is_expiring_soon", "days_until_expiry", "is_expired",
            "sent_at", "signed_at", "signed_by_name",
            "signature_ip",
            "ai_review", "ai_reviewed_at",
            "company_detail",
            "pdf_file", "docx_file",
            "created_by", "is_active",
            "created_at", "updated_at",
        ]

    def validate(self, attrs: dict) -> dict:
        start = attrs.get("start_date") or (self.instance and self.instance.start_date)
        end   = attrs.get("end_date")   or (self.instance and self.instance.end_date)
        if start and end and end < start:
            raise serializers.ValidationError(
                {"end_date": _("End date must be on or after start date.")}
            )
        return attrs

    def create(self, validated_data: dict) -> Contract:
        company = validated_data["company"]
        validated_data["number"]     = _assign_number(validated_data, company, "contract")
        validated_data["created_by"] = self.context["request"].user
        contract = Contract.objects.create(**validated_data)
        contract.log_activity(ActivityAction.CREATED, actor=validated_data["created_by"])
        return contract

    def update(self, instance: Contract, validated_data: dict) -> Contract:
        instance = super().update(instance, validated_data)
        instance.log_activity(ActivityAction.UPDATED, actor=self.context["request"].user)
        return instance


class ContractListSerializer(serializers.ModelSerializer):
    client_display_name = serializers.CharField(read_only=True)
    is_expiring_soon    = serializers.BooleanField(read_only=True)
    days_until_expiry   = serializers.IntegerField(read_only=True)
    is_expired          = serializers.BooleanField(read_only=True)

    class Meta:
        model  = Contract
        fields = [
            "id", "number", "status",
            "client_display_name",
            "issue_date", "start_date", "end_date",
            "is_expiring_soon", "days_until_expiry", "is_expired",
            "auto_renew",
            "subject",
            "currency", "total",
            "created_at",
        ]
        read_only_fields = fields


# ===========================================================================
# PAYMENT RECORD
# ===========================================================================

class PaymentRecordSerializer(serializers.ModelSerializer):
    """
    Full serializer for creating a PaymentRecord against an Invoice.
    The invoice FK is injected by the view (not supplied by the client).
    """

    recorded_by_name = serializers.SerializerMethodField()

    class Meta:
        model  = PaymentRecord
        fields = [
            "id",
            "invoice",
            "amount",
            "currency",
            "payment_method",
            "payment_date",
            "reference",
            "notes",
            "is_reversed",
            "reversed_at",
            "reversed_by",
            "recorded_by",
            "recorded_by_name",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "invoice",
            "is_reversed",
            "reversed_at",
            "reversed_by",
            "recorded_by",
            "recorded_by_name",
            "created_at",
        ]

    def get_recorded_by_name(self, obj: PaymentRecord) -> str:
        if obj.recorded_by:
            return getattr(obj.recorded_by, "full_name", None) or obj.recorded_by.email
        return "—"

    def validate_amount(self, value: Decimal) -> Decimal:
        if value <= 0:
            raise serializers.ValidationError(_("Payment amount must be greater than zero."))
        return value

    def create(self, validated_data: dict) -> PaymentRecord:
        request = self.context.get("request")
        validated_data["recorded_by"] = request.user if request else None
        record = super().create(validated_data)
        # Sync amount_paid cache on the invoice
        record.invoice.sync_amount_paid()
        # Auto-update invoice status
        invoice = record.invoice
        if invoice.is_paid_in_full and invoice.status != InvoiceStatus.PAID:
            from django.utils import timezone
            invoice.status  = InvoiceStatus.PAID
            invoice.paid_at = timezone.now()
            invoice.save(update_fields=["status", "paid_at", "updated_at"])
            invoice.log_activity(
                ActivityAction.PAID,
                actor=request.user if request else None,
                metadata={"amount": str(record.amount)},
            )
        elif invoice.amount_paid > 0 and invoice.status not in (
            InvoiceStatus.PAID, InvoiceStatus.VOID
        ):
            invoice.status = InvoiceStatus.PARTIAL
            invoice.save(update_fields=["status", "updated_at"])
            invoice.log_activity(
                ActivityAction.PARTIAL,
                actor=request.user if request else None,
                metadata={"amount": str(record.amount)},
            )
        return record


class PaymentRecordListSerializer(serializers.ModelSerializer):
    """Lightweight — used inside InvoiceDetailSerializer."""

    class Meta:
        model  = PaymentRecord
        fields = [
            "id", "amount", "currency",
            "payment_method", "payment_date",
            "reference", "is_reversed",
            "created_at",
        ]
        read_only_fields = fields


# ===========================================================================
# DOCUMENT ACTIVITY
# ===========================================================================

class DocumentActivitySerializer(serializers.ModelSerializer):
    """Read-only audit trail entry."""

    actor_name = serializers.SerializerMethodField()

    class Meta:
        model  = DocumentActivity
        fields = [
            "id",
            "doc_type", "doc_id", "doc_number",
            "action",
            "actor", "actor_name", "actor_ip",
            "note",
            "metadata",
            "created_at",
        ]
        read_only_fields = fields

    def get_actor_name(self, obj: DocumentActivity) -> str:
        if obj.actor:
            return getattr(obj.actor, "full_name", None) or obj.actor.email
        return "System"


# ===========================================================================
# DOCUMENT VERSION
# ===========================================================================

class DocumentVersionSerializer(serializers.ModelSerializer):
    """Read-only version history snapshot."""

    class Meta:
        model  = DocumentVersion
        fields = [
            "id",
            "doc_type", "doc_id",
            "version",
            "snapshot",
            "created_by",
            "created_at",
        ]
        read_only_fields = fields


# ===========================================================================
# RECURRING INVOICE
# ===========================================================================

class RecurringInvoiceSerializer(serializers.ModelSerializer):

    is_due           = serializers.SerializerMethodField()
    company_name     = serializers.CharField(source="company.name", read_only=True)
    template_number  = serializers.CharField(source="template.number", read_only=True)

    class Meta:
        model  = RecurringInvoice
        fields = [
            "id",
            "company", "company_name",
            "template", "template_number",
            "frequency",
            "start_date", "end_date",
            "max_occurrences", "occurrences_sent",
            "next_invoice_date",
            "auto_send",
            "is_active",
            "is_due",
            "created_by",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id",
            "company_name", "template_number",
            "occurrences_sent",
            "is_due",
            "created_by",
            "created_at", "updated_at",
        ]

    def get_is_due(self, obj: RecurringInvoice) -> bool:
        return obj.is_due()

    def validate(self, attrs: dict) -> dict:
        start = attrs.get("start_date")
        end   = attrs.get("end_date")
        if start and end and end < start:
            raise serializers.ValidationError(
                {"end_date": _("End date must be on or after start date.")}
            )
        # Ensure template belongs to the same company
        template = attrs.get("template") or (self.instance and self.instance.template)
        company  = attrs.get("company")  or (self.instance and self.instance.company)
        if template and company and template.company_id != company.pk:
            raise serializers.ValidationError(
                {"template": _("Template invoice must belong to the same company.")}
            )
        return attrs

    def create(self, validated_data: dict) -> RecurringInvoice:
        request = self.context.get("request")
        validated_data["created_by"] = request.user if request else None
        # Default next_invoice_date to start_date if not set
        validated_data.setdefault(
            "next_invoice_date", validated_data.get("start_date")
        )
        return super().create(validated_data)


# ===========================================================================
# DOCUMENT ATTACHMENT
# ===========================================================================

class DocumentAttachmentSerializer(serializers.ModelSerializer):
    """
    File upload + list for Invoices, Quotations, and Contracts.
    The parent FK (invoice/quotation/contract) is injected by the view.
    """

    file_url      = serializers.SerializerMethodField()
    uploader_name = serializers.SerializerMethodField()

    class Meta:
        model  = DocumentAttachment
        fields = [
            "id",
            "invoice", "quotation", "contract",
            "file", "file_url",
            "original_name",
            "mime_type",
            "file_size",
            "attachment_type",
            "description",
            "uploaded_by", "uploader_name",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "invoice", "quotation", "contract",
            "file_url",
            "uploaded_by", "uploader_name",
            "created_at",
        ]

    def get_file_url(self, obj: DocumentAttachment) -> str | None:
        request = self.context.get("request")
        if obj.file and request:
            return request.build_absolute_uri(obj.file.url)
        return obj.file.url if obj.file else None

    def get_uploader_name(self, obj: DocumentAttachment) -> str:
        if obj.uploaded_by:
            return getattr(obj.uploaded_by, "full_name", None) or obj.uploaded_by.email
        return "—"

    def validate_file(self, value):
        max_mb = 25
        if value.size > max_mb * 1024 * 1024:
            raise serializers.ValidationError(
                _(f"File size must not exceed {max_mb} MB.")
            )
        return value

    def create(self, validated_data: dict) -> DocumentAttachment:
        request = self.context.get("request")
        if request:
            validated_data["uploaded_by"] = request.user
        file_obj = validated_data.get("file")
        if file_obj:
            validated_data.setdefault("original_name", file_obj.name)
            validated_data.setdefault("mime_type",     getattr(file_obj, "content_type", ""))
            validated_data.setdefault("file_size",     file_obj.size)
        return super().create(validated_data)