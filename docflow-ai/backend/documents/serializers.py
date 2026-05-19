from django.db import transaction
from django.conf import settings
from rest_framework import serializers
from .models import (
    Invoice, InvoiceLineItem,
    Quotation, QuotationLineItem,
    Contract, DocumentVersion
)


# =========================
# INVOICE LINE ITEM
# =========================

class InvoiceLineItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceLineItem
        fields = ["id", "description", "quantity", "unit_price", "amount", "order"]
        read_only_fields = ["id", "amount"]


# =========================
# INVOICE
# =========================

class InvoiceSerializer(serializers.ModelSerializer):
    line_items = InvoiceLineItemSerializer(many=True, required=False)
    client_name = serializers.CharField(source="client.name", read_only=True)
    portal_url = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = [
            "id", "company", "client", "client_name", "created_by", "number",
            "status", "currency", "issue_date", "due_date", "notes", "terms",
            "subtotal", "tax_rate", "tax_amount", "discount_amount", "total_amount",
            "pdf_file", "docx_file", "portal_token", "portal_url", "sent_at",
            "viewed_at", "paid_at", "portal_used", "is_deleted", "stripe_payment_intent_id",
            "stripe_payment_link", "line_items", "created_at", "updated_at"
        ]
        read_only_fields = [
            "id",
            "created_by",
            "subtotal",
            "tax_amount",
            "total_amount",
            "portal_token",
            "pdf_file",
            "docx_file",
            "created_at",
            "updated_at",
        ]

    def get_portal_url(self, obj):
        if obj.portal_token:
            frontend_url = getattr(settings, "FRONTEND_URL", "").rstrip("/")
            return f"{frontend_url}/portal/{obj.portal_token}"
        return None

    def create(self, validated_data):
        line_items_data = validated_data.pop("line_items", [])

        with transaction.atomic():
            invoice = Invoice.objects.create(**validated_data)

            for item in line_items_data:
                InvoiceLineItem.objects.create(invoice=invoice, **item)

            invoice.calculate_totals()

        return invoice

    def update(self, instance, validated_data):
        line_items_data = validated_data.pop("line_items", None)

        with transaction.atomic():
            instance = super().update(instance, validated_data)

            if line_items_data is not None:
                # Flush and recreate strategy
                instance.line_items.all().delete()

                for item in line_items_data:
                    InvoiceLineItem.objects.create(invoice=instance, **item)

                instance.calculate_totals()

        return instance


# =========================
# QUOTATION LINE ITEM
# =========================

class QuotationLineItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuotationLineItem
        fields = ["id", "description", "quantity", "unit_price", "amount", "order"]
        read_only_fields = ["id", "amount"]


# =========================
# QUOTATION
# =========================

class QuotationSerializer(serializers.ModelSerializer):
    line_items = QuotationLineItemSerializer(many=True, required=False)
    client_name = serializers.CharField(source="client.name", read_only=True)
    portal_url = serializers.SerializerMethodField()

    class Meta:
        model = Quotation
        fields = [
            "id", "company", "client", "client_name", "created_by", "number",
            "status", "currency", "issue_date", "due_date", "notes", "terms",
            "subtotal", "tax_rate", "tax_amount", "discount_amount", "total_amount",
            "pdf_file", "docx_file", "portal_token", "portal_url", "sent_at",
            "viewed_at", "paid_at", "portal_used", "is_deleted", "valid_until",
            "converted_to_invoice", "line_items", "created_at", "updated_at"
        ]
        read_only_fields = [
            "id",
            "created_by",
            "subtotal",
            "tax_amount",
            "total_amount",
            "portal_token",
            "pdf_file",
            "docx_file",
            "created_at",
            "updated_at",
        ]

    def get_portal_url(self, obj):
        if obj.portal_token:
            frontend_url = getattr(settings, "FRONTEND_URL", "").rstrip("/")
            return f"{frontend_url}/portal/{obj.portal_token}"
        return None

    def create(self, validated_data):
        line_items_data = validated_data.pop("line_items", [])

        with transaction.atomic():
            quotation = Quotation.objects.create(**validated_data)

            for item in line_items_data:
                QuotationLineItem.objects.create(quotation=quotation, **item)

            quotation.calculate_totals()

        return quotation

    def update(self, instance, validated_data):
        line_items_data = validated_data.pop("line_items", None)

        with transaction.atomic():
            instance = super().update(instance, validated_data)

            if line_items_data is not None:
                instance.line_items.all().delete()

                for item in line_items_data:
                    QuotationLineItem.objects.create(quotation=instance, **item)

                instance.calculate_totals()

        return instance


# =========================
# CONTRACT
# =========================

class ContractSerializer(serializers.ModelSerializer):
    versions_count = serializers.IntegerField(source="versions.count", read_only=True)
    client_name = serializers.CharField(source="client.name", read_only=True)

    class Meta:
        model = Contract
        fields = [
            "id", "company", "client", "client_name", "created_by", "title",
            "contract_type", "content", "status", "start_date", "end_date",
            "auto_renew", "renewal_notice_days", "value", "currency", "pdf_file",
            "portal_token", "signed_at", "versions_count", "created_at", "updated_at"
        ]
        read_only_fields = [
            "id",
            "created_by",
            "portal_token",
            "pdf_file",
            "created_at",
            "updated_at",
        ]


# =========================
# DOCUMENT VERSION
# =========================

class DocumentVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentVersion
        fields = ["id", "contract", "version_number", "content", "created_by", "created_at"]
        read_only_fields = [
            "id",
            "created_by",
            "created_at",
        ]