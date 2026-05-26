"""Documents serializers — modified to allow manual on-the-fly text without database persistence."""

from django.db import transaction
from django.conf import settings
from django.utils import timezone
from rest_framework import serializers

from .models import (
    Invoice, InvoiceLineItem,
    Quotation, QuotationLineItem,
    Contract, DocumentVersion,
)


# ──────────────────────────────────────────────
# Document Version Serializer
# ──────────────────────────────────────────────

class DocumentVersionSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = DocumentVersion
        fields = ["id", "version_number", "content", "created_by", "created_by_name", "created_at"]
        read_only_fields = ["id", "version_number", "created_by", "created_at"]

    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name() or obj.created_by.email
        return None


# ──────────────────────────────────────────────
# Contract Serializers
# ──────────────────────────────────────────────

class ContractListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views — no heavy nested data."""
    client_name = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    contract_type_display = serializers.CharField(source="get_contract_type_display", read_only=True)
    is_expiring_soon = serializers.SerializerMethodField()
    days_until_expiry = serializers.SerializerMethodField()

    class Meta:
        model = Contract
        fields = [
            "id", "title", "contract_type", "contract_type_display",
            "status", "status_display", "client_name", "created_by_name",
            "start_date", "end_date", "auto_renew", "value", "currency",
            "signed_at", "is_expiring_soon", "days_until_expiry",
            "created_at", "updated_at",
        ]
        read_only_fields = fields

    def get_client_name(self, obj):
        return getattr(obj.client, "name", str(obj.client)) if obj.client else None

    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name() or obj.created_by.email
        return None

    def get_days_until_expiry(self, obj):
        if obj.end_date:
            return (obj.end_date - timezone.now().date()).days
        return None

    def get_is_expiring_soon(self, obj):
        days = self.get_days_until_expiry(obj)
        return False if days is None else 0 <= days <= obj.renewal_notice_days


class ContractDetailSerializer(serializers.ModelSerializer):
    """Full serializer for retrieve / create / update."""
    versions = DocumentVersionSerializer(many=True, read_only=True)
    client_name = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    contract_type_display = serializers.CharField(source="get_contract_type_display", read_only=True)
    is_expiring_soon = serializers.SerializerMethodField()
    days_until_expiry = serializers.SerializerMethodField()
    version_count = serializers.SerializerMethodField()

    class Meta:
        model = Contract
        fields = [
            "id", "company", "client", "client_name", "created_by", "created_by_name",
            "title", "contract_type", "contract_type_display", "content",
            "status", "status_display", "start_date", "end_date", "auto_renew",
            "renewal_notice_days", "value", "currency", "pdf_file", "portal_token",
            "signed_at", "is_expiring_soon", "days_until_expiry", "version_count",
            "versions", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "company", "created_by", "portal_token",
            "signed_at", "pdf_file", "created_at", "updated_at",
        ]

    def get_client_name(self, obj):
        return getattr(obj.client, "name", str(obj.client)) if obj.client else None

    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name() or obj.created_by.email
        return None

    def get_days_until_expiry(self, obj):
        if obj.end_date:
            return (obj.end_date - timezone.now().date()).days
        return None

    def get_is_expiring_soon(self, obj):
        days = self.get_days_until_expiry(obj)
        return False if days is None else 0 <= days <= obj.renewal_notice_days

    def get_version_count(self, obj):
        return obj.versions.count()

    def validate(self, attrs):
        start_date = attrs.get("start_date") or (self.instance and self.instance.start_date)
        end_date = attrs.get("end_date") or (self.instance and self.instance.end_date)
        if start_date and end_date and end_date <= start_date:
            raise serializers.ValidationError({"end_date": "End date must be after start date."})
        return attrs

    def validate_renewal_notice_days(self, value):
        if not 1 <= value <= 365:
            raise serializers.ValidationError("Renewal notice days must be between 1 and 365.")
        return value

    def validate_value(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError("Contract value cannot be negative.")
        return value

    def validate_currency(self, value):
        if len(value) != 3 or not value.isalpha():
            raise serializers.ValidationError("Currency must be a valid 3-letter ISO code (e.g. KES, USD).")
        return value.upper()

    def create(self, validated_data):
        request = self.context.get("request")
        if request:
            validated_data["company"] = request.user.company
            validated_data["created_by"] = request.user
        contract = super().create(validated_data)
        DocumentVersion.objects.create(
            contract=contract,
            version_number=1,
            content=contract.content,
            created_by=contract.created_by,
        )
        return contract

    def update(self, instance, validated_data):
        new_content = validated_data.get("content")
        content_changed = new_content and new_content != instance.content
        contract = super().update(instance, validated_data)
        if content_changed:
            # FIX: use contract (updated object), not the stale instance reference
            last_version = contract.versions.first()
            next_number = (last_version.version_number + 1) if last_version else 1
            request = self.context.get("request")
            DocumentVersion.objects.create(
                contract=contract,
                version_number=next_number,
                content=new_content,
                created_by=request.user if request else None,
            )
        return contract


# ──────────────────────────────────────────────
# Status Transition Serializer
# ──────────────────────────────────────────────

class ContractStatusSerializer(serializers.ModelSerializer):
    """PATCH /contracts/{id}/status/ — enforces valid transitions only."""
    VALID_TRANSITIONS = {
        Contract.Status.DRAFT:     [Contract.Status.PENDING, Contract.Status.CANCELLED],
        Contract.Status.PENDING:   [Contract.Status.SIGNED, Contract.Status.CANCELLED, Contract.Status.EXPIRED],
        Contract.Status.SIGNED:    [Contract.Status.COMPLETED, Contract.Status.EXPIRED],
        Contract.Status.COMPLETED: [],
        Contract.Status.EXPIRED:   [Contract.Status.DRAFT],
        Contract.Status.CANCELLED: [Contract.Status.DRAFT],
    }

    class Meta:
        model = Contract
        fields = ["status", "signed_at"]
        extra_kwargs = {"signed_at": {"required": False}}

    def validate(self, attrs):
        new_status = attrs.get("status")
        current_status = self.instance.status
        allowed = self.VALID_TRANSITIONS.get(current_status, [])
        if new_status not in allowed:
            raise serializers.ValidationError({
                "status": (
                    f"Cannot transition from '{current_status}' to '{new_status}'. "
                    f"Allowed: {[s.value for s in allowed] or 'none'}."
                )
            })
        if new_status == Contract.Status.SIGNED and not attrs.get("signed_at"):
            attrs["signed_at"] = timezone.now()
        return attrs


# ──────────────────────────────────────────────
# Public Portal Serializer
# ──────────────────────────────────────────────

class ContractPortalSerializer(serializers.ModelSerializer):
    """Read-only for public client portal (/portal/:token). No sensitive fields."""
    client_name = serializers.SerializerMethodField()
    company_name = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    contract_type_display = serializers.CharField(source="get_contract_type_display", read_only=True)

    class Meta:
        model = Contract
        fields = [
            "id", "title", "contract_type_display", "status", "status_display",
            "client_name", "company_name", "content", "start_date", "end_date",
            "value", "currency", "signed_at", "pdf_file",
        ]
        read_only_fields = fields

    def get_client_name(self, obj):
        return getattr(obj.client, "name", str(obj.client)) if obj.client else None

    def get_company_name(self, obj):
        return getattr(obj.company, "name", str(obj.company))


# ──────────────────────────────────────────────
# Invoice Line Item
# ──────────────────────────────────────────────

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


# ──────────────────────────────────────────────
# Invoice Serializer
# ──────────────────────────────────────────────

class InvoiceSerializer(serializers.ModelSerializer):
    line_items = InvoiceLineItemSerializer(many=True, required=True)
    client_name = serializers.CharField(source="client.name", read_only=True)
    company_name = serializers.CharField(source="company.name", read_only=True)
    portal_url = serializers.SerializerMethodField()

    # On-the-fly manual text — write-only, never persisted as dedicated columns
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
        issue_date = attrs.get("issue_date")
        due_date = attrs.get("due_date")
        if issue_date and due_date and due_date < issue_date:
            raise serializers.ValidationError({"due_date": "Due date cannot be before issue date."})
        if not attrs.get("client") and not attrs.get("raw_client_name"):
            raise serializers.ValidationError(
                {"client": "Please select a client profile or provide a manual client name."}
            )
        return attrs

    def get_portal_url(self, obj):
        # FIX: use portal_token (secure), not obj.id
        if obj.portal_token:
            frontend_url = getattr(settings, "FRONTEND_URL", "").rstrip("/")
            return f"{frontend_url}/portal/{obj.portal_token}"
        return None

    def _pop_raw_fields(self, validated_data):
        """Extract all raw_* fields before hitting the ORM."""
        return {
            "client":  validated_data.pop("raw_client_name", None),
            "company": validated_data.pop("raw_company_name", None),
            "address": validated_data.pop("raw_company_address", None),
            "city":    validated_data.pop("raw_company_city", None),
            "phone":   validated_data.pop("raw_company_location_number", None),
        }

    def create(self, validated_data):
        raw = self._pop_raw_fields(validated_data)
        line_items_data = validated_data.pop("line_items", [])

        with transaction.atomic():
            invoice = Invoice.objects.create(**validated_data)

            if raw["client"] or raw["company"]:
                meta = (
                    f"\n[Billing Issuer: {raw['company'] or 'N/A'} | "
                    f"Address: {raw['address'] or ''}, {raw['city'] or ''} | "
                    f"Contact: {raw['phone'] or ''} | "
                    f"Attention To: {raw['client'] or ''}]"
                )
                invoice.notes = (invoice.notes or "") + meta
                invoice.save(update_fields=["notes"])

            InvoiceLineItem.objects.bulk_create([
                InvoiceLineItem(invoice=invoice, **item) for item in line_items_data
            ])
            invoice.calculate_totals()

        return invoice

    def update(self, instance, validated_data):
        # FIX: pop ALL five raw fields, not just two
        self._pop_raw_fields(validated_data)
        line_items_data = validated_data.pop("line_items", None)

        with transaction.atomic():
            instance = super().update(instance, validated_data)
            if line_items_data is not None:
                instance.line_items.all().delete()
                InvoiceLineItem.objects.bulk_create([
                    InvoiceLineItem(invoice=instance, **item) for item in line_items_data
                ])
                instance.calculate_totals()
        return instance


# ──────────────────────────────────────────────
# Quotation Line Item
# ──────────────────────────────────────────────

class QuotationLineItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuotationLineItem
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


# ──────────────────────────────────────────────
# Quotation Serializer
# ──────────────────────────────────────────────

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
        # FIX: added missing date validation (mirrors InvoiceSerializer)
        issue_date = attrs.get("issue_date")
        due_date = attrs.get("due_date")
        if issue_date and due_date and due_date < issue_date:
            raise serializers.ValidationError({"due_date": "Due date cannot be before issue date."})
        valid_until = attrs.get("valid_until")
        if issue_date and valid_until and valid_until < issue_date:
            raise serializers.ValidationError({"valid_until": "Valid until date cannot be before issue date."})
        return attrs

    def get_portal_url(self, obj):
        # FIX: use portal_token (secure), not obj.id
        if obj.portal_token:
            frontend_url = getattr(settings, "FRONTEND_URL", "").rstrip("/")
            return f"{frontend_url}/portal/{obj.portal_token}"
        return None

    def _pop_raw_fields(self, validated_data):
        return {
            "client":  validated_data.pop("raw_client_name", None),
            "company": validated_data.pop("raw_company_name", None),
            "address": validated_data.pop("raw_company_address", None),
            "city":    validated_data.pop("raw_company_city", None),
            "phone":   validated_data.pop("raw_company_location_number", None),
        }

    def create(self, validated_data):
        raw = self._pop_raw_fields(validated_data)
        line_items_data = validated_data.pop("line_items", [])

        with transaction.atomic():
            quotation = Quotation.objects.create(**validated_data)

            if raw["client"] or raw["company"]:
                meta = (
                    f"\n[Proposal From: {raw['company'] or 'N/A'} | "
                    f"Address: {raw['address'] or ''}, {raw['city'] or ''} | "
                    f"Contact: {raw['phone'] or ''} | "
                    f"Attn: {raw['client'] or ''}]"
                )
                quotation.notes = (quotation.notes or "") + meta
                quotation.save(update_fields=["notes"])

            QuotationLineItem.objects.bulk_create([
                QuotationLineItem(quotation=quotation, **item) for item in line_items_data
            ])
            quotation.calculate_totals()

        return quotation

    def update(self, instance, validated_data):
        # FIX: added missing update() — previously fell back to DRF default
        self._pop_raw_fields(validated_data)
        line_items_data = validated_data.pop("line_items", None)

        with transaction.atomic():
            instance = super().update(instance, validated_data)
            if line_items_data is not None:
                instance.line_items.all().delete()
                QuotationLineItem.objects.bulk_create([
                    QuotationLineItem(quotation=instance, **item) for item in line_items_data
                ])
                instance.calculate_totals()
        return instance