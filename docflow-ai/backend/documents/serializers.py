"""
DocFlow AI — documents/serializers.py

Serializers for Invoice, Quotation, Contract, and LineItem.

Key design choices:
  • LineItemSerializer is nested and writable (create/update via parent).
  • Totals are read-only — always recomputed server-side.
  • Document numbers are read-only — assigned via Company.get_next_*().
  • Portal / public serializers strip internal fields.
"""

from __future__ import annotations

from decimal import Decimal

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from companies.serializers import CompanyPublicSerializer

from .models import (
    Contract, ContractStatus,
    Invoice, InvoiceStatus,
    LineItem,
    Quotation, QuotationStatus,
)


# ---------------------------------------------------------------------------
# LineItem
# ---------------------------------------------------------------------------

class LineItemSerializer(serializers.ModelSerializer):
    gross_amount   = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    discount_value = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    line_total     = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model  = LineItem
        fields = [
            "id",
            "item_type", "description",
            "quantity", "unit_of_measure", "unit_label", "unit_price",
            "discount_percent", "tax_rate",
            "gross_amount", "discount_value", "line_total",
            "sort_order",
            "created_at",
        ]
        read_only_fields = ["id", "gross_amount", "discount_value", "line_total", "created_at"]

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


# ---------------------------------------------------------------------------
# Invoice
# ---------------------------------------------------------------------------

class InvoiceSerializer(serializers.ModelSerializer):
    line_items   = LineItemSerializer(many=True, required=False)
    company_detail = CompanyPublicSerializer(source="company", read_only=True)
    balance_due    = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    is_overdue     = serializers.BooleanField(read_only=True)
    client_display_name = serializers.CharField(read_only=True)

    class Meta:
        model  = Invoice
        fields = [
            "id", "company", "company_detail",
            "client", "client_salutation", "client_name", "client_email",
            "client_phone", "client_address", "client_vat_number",
            "number", "status",
            "issue_date", "due_date", "sent_at", "paid_at",
            "currency",
            "subject", "notes", "terms",
            "subtotal", "discount_amount", "tax_amount", "total",
            "amount_paid", "balance_due",
            "is_overdue",
            "client_display_name",
            "stripe_payment_link_url",
            "pdf_file", "docx_file",
            "line_items",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "number",
            "subtotal", "discount_amount", "tax_amount", "total",
            "balance_due", "is_overdue", "client_display_name",
            "stripe_payment_link_url", "portal_token",
            "sent_at", "paid_at",
            "pdf_file", "docx_file",
            "company_detail",
            "created_at", "updated_at",
        ]

    def validate_status(self, value: str) -> str:
        instance = getattr(self, "instance", None)
        if instance and instance.status == InvoiceStatus.VOID and value != InvoiceStatus.VOID:
            raise serializers.ValidationError(_("A voided invoice cannot be reinstated."))
        return value

    def _save_line_items(self, document: Invoice, items_data: list[dict]) -> None:
        document.line_items.all().delete()
        for idx, item_data in enumerate(items_data):
            item_data.setdefault("sort_order", idx)
            LineItem.objects.create(invoice=document, **item_data)

    def create(self, validated_data: dict) -> Invoice:
        items_data = validated_data.pop("line_items", [])
        company = validated_data["company"]
        validated_data["number"] = company.get_next_invoice_number()
        validated_data["created_by"] = self.context["request"].user

        invoice = Invoice.objects.create(**validated_data)
        self._save_line_items(invoice, items_data)
        invoice.compute_totals()
        invoice.save(update_fields=["subtotal", "discount_amount", "tax_amount", "total"])
        return invoice

    def update(self, instance: Invoice, validated_data: dict) -> Invoice:
        items_data = validated_data.pop("line_items", None)
        instance = super().update(instance, validated_data)
        if items_data is not None:
            self._save_line_items(instance, items_data)
        instance.compute_totals()
        instance.save(update_fields=["subtotal", "discount_amount", "tax_amount", "total", "updated_at"])
        return instance


class InvoiceListSerializer(serializers.ModelSerializer):
    balance_due = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    client_display_name = serializers.CharField(read_only=True)
    is_overdue  = serializers.BooleanField(read_only=True)

    class Meta:
        model  = Invoice
        fields = [
            "id", "number", "status",
            "client_display_name",
            "issue_date", "due_date",
            "currency", "total", "balance_due",
            "is_overdue",
            "created_at",
        ]
        read_only_fields = fields


class InvoicePortalSerializer(serializers.ModelSerializer):
    line_items  = LineItemSerializer(many=True, read_only=True)
    balance_due = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    company_detail = CompanyPublicSerializer(source="company", read_only=True)

    class Meta:
        model  = Invoice
        fields = [
            "id", "number", "status",
            "company_detail",
            "client_salutation", "client_name", "client_email",
            "issue_date", "due_date",
            "currency",
            "subject", "notes", "terms",
            "subtotal", "discount_amount", "tax_amount", "total",
            "amount_paid", "balance_due",
            "stripe_payment_link_url",
            "line_items",
        ]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Quotation
# ---------------------------------------------------------------------------

class QuotationSerializer(serializers.ModelSerializer):
    line_items     = LineItemSerializer(many=True, required=False)
    company_detail = CompanyPublicSerializer(source="company", read_only=True)
    balance_due    = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model  = Quotation
        fields = [
            "id", "company", "company_detail",
            "client", "client_salutation", "client_name", "client_email",
            "client_phone", "client_address", "client_vat_number",
            "number", "status",
            "issue_date", "due_date", "valid_until",
            "sent_at", "accepted_at",
            "currency",
            "subject", "notes", "terms",
            "subtotal", "discount_amount", "tax_amount", "total",
            "amount_paid", "balance_due",
            "pdf_file", "docx_file",
            "line_items",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "number",
            "subtotal", "discount_amount", "tax_amount", "total",
            "balance_due", "sent_at", "accepted_at",
            "pdf_file", "docx_file", "company_detail",
            "created_at", "updated_at",
        ]

    def _save_line_items(self, document: Quotation, items_data: list[dict]) -> None:
        document.line_items.all().delete()
        for idx, item_data in enumerate(items_data):
            item_data.setdefault("sort_order", idx)
            LineItem.objects.create(quotation=document, **item_data)

    def create(self, validated_data: dict) -> Quotation:
        items_data = validated_data.pop("line_items", [])
        company = validated_data["company"]
        validated_data["number"] = company.get_next_quotation_number()
        validated_data["created_by"] = self.context["request"].user
        quotation = Quotation.objects.create(**validated_data)
        self._save_line_items(quotation, items_data)
        quotation.compute_totals()
        quotation.save(update_fields=["subtotal", "discount_amount", "tax_amount", "total"])
        return quotation

    def update(self, instance: Quotation, validated_data: dict) -> Quotation:
        items_data = validated_data.pop("line_items", None)
        instance = super().update(instance, validated_data)
        if items_data is not None:
            self._save_line_items(instance, items_data)
        instance.compute_totals()
        instance.save(update_fields=["subtotal", "discount_amount", "tax_amount", "total", "updated_at"])
        return instance


class QuotationListSerializer(serializers.ModelSerializer):
    client_display_name = serializers.CharField(read_only=True)

    class Meta:
        model  = Quotation
        fields = [
            "id", "number", "status",
            "client_display_name",
            "issue_date", "valid_until",
            "currency", "total",
            "created_at",
        ]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Contract
# ---------------------------------------------------------------------------

class ContractSerializer(serializers.ModelSerializer):
    company_detail = CompanyPublicSerializer(source="company", read_only=True)

    class Meta:
        model  = Contract
        fields = [
            "id", "company", "company_detail",
            "client", "client_salutation", "client_name", "client_email",
            "client_phone", "client_address",
            "number", "status",
            "issue_date", "due_date",
            "start_date", "end_date",
            "auto_renew", "renewal_notice_days",
            "currency",
            "subject", "body", "notes", "terms",
            "subtotal", "discount_amount", "tax_amount", "total",
            "sent_at", "signed_at", "signed_by_name",
            "ai_review",
            "pdf_file", "docx_file",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "number",
            "subtotal", "discount_amount", "tax_amount", "total",
            "sent_at", "signed_at", "signed_by_name", "signature_ip",
            "ai_review", "company_detail",
            "pdf_file", "docx_file",
            "created_at", "updated_at",
        ]

    def create(self, validated_data: dict) -> Contract:
        company = validated_data["company"]
        validated_data["number"] = company.get_next_contract_number()
        validated_data["created_by"] = self.context["request"].user
        return Contract.objects.create(**validated_data)


class ContractListSerializer(serializers.ModelSerializer):
    client_display_name = serializers.CharField(read_only=True)
    is_expiring_soon = serializers.BooleanField(read_only=True)

    class Meta:
        model  = Contract
        fields = [
            "id", "number", "status",
            "client_display_name",
            "issue_date", "start_date", "end_date",
            "is_expiring_soon",
            "subject",
            "created_at",
        ]
        read_only_fields = fields