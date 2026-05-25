"""Documents serializers — modified to allow manual on-the-fly text without database persistence"""

from django.db import transaction
from django.conf import settings
from rest_framework import serializers

from .models import (
    Invoice, InvoiceLineItem,
    Quotation, QuotationLineItem,
    Contract, DocumentVersion,
)

# =========================
# INVOICE LINE ITEM
# =========================
class InvoiceLineItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceLineItem
        fields = ["id", "description", "quantity", "unit_price", "amount", "order"]
        read_only_fields = ["id", "amount"]

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("Quantity must be greater than 0.")
        return value

    def validate_unit_price(self, value):
        if value < 0:
            raise serializers.ValidationError("Unit price cannot be negative.")
        return value


# =========================
# INVOICE SERIALIZER
# =========================
class InvoiceSerializer(serializers.ModelSerializer):
    line_items = InvoiceLineItemSerializer(many=True, required=True)
    client_name = serializers.CharField(source="client.name", read_only=True)
    company_name = serializers.CharField(source="company.name", read_only=True)
    portal_url = serializers.SerializerMethodField()

    # On-The-Fly Manual String Field Overrides (Not forced into database persistence)
    raw_client_name = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)
    raw_company_name = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)
    raw_company_address = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)
    raw_company_city = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)
    raw_company_location_number = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = Invoice
        fields = [
            "id", "company", "company_name", "client", "client_name",
            "created_by", "number", "status", "currency", "issue_date",
            "due_date", "notes", "terms", "subtotal", "tax_rate",
            "tax_amount", "discount_amount", "total_amount", "pdf_file",
            "docx_file", "portal_token", "portal_url", "sent_at", "viewed_at",
            "paid_at", "portal_used", "is_deleted", "stripe_payment_intent_id",
            "stripe_payment_link", "line_items", "created_at", "updated_at",
            "raw_client_name", "raw_company_name", "raw_company_address",
            "raw_company_city", "raw_company_location_number",
        ]
        read_only_fields = [
            "id", "created_by", "subtotal", "tax_amount", "total_amount",
            "portal_token", "pdf_file", "docx_file", "created_at",
            "updated_at", "company_name",
        ]

    # Change client field to optional to support pure manual text submissions
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["client"].required = False
        self.fields["client"].allow_null = True
        self.fields["company"].required = False
        self.fields["company"].allow_null = True

    def validate_line_items(self, value):
        if not value:
            raise serializers.ValidationError("Invoice must have at least one line item.")
        return value

    def validate(self, attrs):
        if attrs.get("due_date") and attrs.get("issue_date"):
            if attrs["due_date"] < attrs["issue_date"]:
                raise serializers.ValidationError(
                    {"due_date": "Due date cannot be before issue date."}
                )

        # Ensure either a standard profile or a manual string exists
        if not attrs.get("client") and not attrs.get("raw_client_name"):
            raise serializers.ValidationError({"client": "Please select a client profile or type a manual client descriptor name."})
        return attrs

    def get_portal_url(self, obj):
        if obj.id:
            frontend_url = getattr(settings, "FRONTEND_URL", "").rstrip("/")
            return f"{frontend_url}/portal/{obj.id}"
        return None

    def create(self, validated_data):
        # Extract manual strings before database save routines
        raw_client = validated_data.pop("raw_client_name", None)
        raw_comp = validated_data.pop("raw_company_name", None)
        raw_addr = validated_data.pop("raw_company_address", None)
        raw_city = validated_data.pop("raw_company_city", None)
        raw_phone = validated_data.pop("raw_company_location_number", None)

        line_items_data = validated_data.pop("line_items", [])

        with transaction.atomic():
            invoice = Invoice.objects.create(**validated_data)

            # Map the unpersisted strings straight onto temporary text/notes properties if DB lacks fields
            if raw_client or raw_comp:
                meta_notes = f"\n[Billing Issuer: {raw_comp or 'N/A'} | Address: {raw_addr or ''}, {raw_city or ''} | Contact: {raw_phone or ''} | Attention To: {raw_client or ''}]"
                invoice.notes = (invoice.notes or "") + meta_notes
                invoice.save(update_fields=["notes"])

            InvoiceLineItem.objects.bulk_create([
                InvoiceLineItem(invoice=invoice, **item)
                for item in line_items_data
            ])
            invoice.calculate_totals()

        return invoice

    def update(self, instance, validated_data):
        validated_data.pop("raw_client_name", None)
        validated_data.pop("raw_company_name", None)
        line_items_data = validated_data.pop("line_items", None)

        with transaction.atomic():
            instance = super().update(instance, validated_data)
            if line_items_data is not None:
                instance.line_items.all().delete()
                InvoiceLineItem.objects.bulk_create([
                    InvoiceLineItem(invoice=instance, **item)
                    for item in line_items_data
                ])
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
# QUOTATION SERIALIZER
# =========================
class QuotationSerializer(serializers.ModelSerializer):
    line_items = QuotationLineItemSerializer(many=True, required=True)
    client_name = serializers.CharField(source="client.name", read_only=True)
    company_name = serializers.CharField(source="company.name", read_only=True)
    portal_url = serializers.SerializerMethodField()

    raw_client_name = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)
    raw_company_name = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)
    raw_company_address = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)
    raw_company_city = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)
    raw_company_location_number = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = Quotation
        fields = [
            "id", "company", "company_name", "client", "client_name",
            "created_by", "number", "status", "currency", "issue_date",
            "due_date", "notes", "terms", "subtotal", "tax_rate",
            "tax_amount", "discount_amount", "total_amount", "pdf_file",
            "docx_file", "portal_token", "portal_url", "sent_at", "viewed_at",
            "paid_at", "portal_used", "is_deleted", "valid_until",
            "converted_to_invoice", "line_items", "created_at", "updated_at",
            "raw_client_name", "raw_company_name", "raw_company_address",
            "raw_company_city", "raw_company_location_number",
        ]
        read_only_fields = [
            "id", "created_by", "subtotal", "tax_amount", "total_amount",
            "portal_token", "pdf_file", "docx_file", "created_at",
            "updated_at", "company_name",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["client"].required = False
        self.fields["client"].allow_null = True
        self.fields["company"].required = False
        self.fields["company"].allow_null = True

    def validate_line_items(self, value):
        if not value:
            raise serializers.ValidationError("Quotation must have at least one line item.")
        return value

    def validate(self, attrs):
        return attrs

    def create(self, validated_data):
        raw_client = validated_data.pop("raw_client_name", None)
        raw_comp = validated_data.pop("raw_company_name", None)
        raw_addr = validated_data.pop("raw_company_address", None)
        raw_city = validated_data.pop("raw_company_city", None)
        raw_phone = validated_data.pop("raw_company_location_number", None)

        line_items_data = validated_data.pop("line_items", [])

        with transaction.atomic():
            quotation = Quotation.objects.create(**validated_data)

            if raw_client or raw_comp:
                meta_notes = f"\n[Proposal From: {raw_comp or 'N/A'} | Address: {raw_addr or ''}, {raw_city or ''} | Contact: {raw_phone or ''} | Attn: {raw_client or ''}]"
                quotation.notes = (quotation.notes or "") + meta_notes
                quotation.save(update_fields=["notes"])

            QuotationLineItem.objects.bulk_create([
                QuotationLineItem(quotation=quotation, **item)
                for item in line_items_data
            ])
            quotation.calculate_totals()

        return quotation