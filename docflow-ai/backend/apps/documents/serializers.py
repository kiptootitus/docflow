"""Documents serializers"""
from rest_framework import serializers
from .models import Invoice, InvoiceLineItem, Quotation, QuotationLineItem, Contract, DocumentVersion


class InvoiceLineItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceLineItem
        fields = ["id", "description", "quantity", "unit_price", "amount", "order"]
        read_only_fields = ["id", "amount"]


class InvoiceSerializer(serializers.ModelSerializer):
    line_items = InvoiceLineItemSerializer(many=True, required=False)
    client_name = serializers.CharField(source="client.name", read_only=True)
    portal_url = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = "__all__"
        read_only_fields = [
            "id", "created_by", "subtotal", "tax_amount", "total_amount",
            "portal_token", "pdf_file", "docx_file", "created_at", "updated_at",
        ]

    def get_portal_url(self, obj):
        request = self.context.get("request")
        if request:
            from django.conf import settings
            return f"{settings.FRONTEND_URL}/portal/{obj.portal_token}"
        return None

    def create(self, validated_data):
        line_items_data = validated_data.pop("line_items", [])
        invoice = Invoice.objects.create(**validated_data)
        for item_data in line_items_data:
            InvoiceLineItem.objects.create(invoice=invoice, **item_data)
        invoice.calculate_totals()
        return invoice

    def update(self, instance, validated_data):
        line_items_data = validated_data.pop("line_items", None)
        instance = super().update(instance, validated_data)
        if line_items_data is not None:
            instance.line_items.all().delete()
            for item_data in line_items_data:
                InvoiceLineItem.objects.create(invoice=instance, **item_data)
            instance.calculate_totals()
        return instance


class QuotationLineItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuotationLineItem
        fields = ["id", "description", "quantity", "unit_price", "amount", "order"]
        read_only_fields = ["id", "amount"]


class QuotationSerializer(serializers.ModelSerializer):
    line_items = QuotationLineItemSerializer(many=True, required=False)

    class Meta:
        model = Quotation
        fields = "__all__"
        read_only_fields = ["id", "created_by", "subtotal", "tax_amount", "total_amount",
                            "portal_token", "pdf_file", "created_at", "updated_at"]


class ContractSerializer(serializers.ModelSerializer):
    versions_count = serializers.IntegerField(source="versions.count", read_only=True)

    class Meta:
        model = Contract
        fields = "__all__"
        read_only_fields = ["id", "created_by", "portal_token", "pdf_file", "created_at", "updated_at"]


class DocumentVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentVersion
        fields = "__all__"
        read_only_fields = ["id", "created_by", "created_at"]
