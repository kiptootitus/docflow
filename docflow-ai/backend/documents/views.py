"""Documents views - Enterprise Ready Version (FIXED)"""

from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.conf import settings

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from .models import Invoice, Quotation, Contract
from .serializers import (
    InvoiceSerializer,
    QuotationSerializer,
    ContractSerializer
)

from .tasks import generate_invoice_pdf, send_invoice_email
# Change from relative (.services...) to absolute project paths:
from documents.services.documents import clone_invoice, convert_quotation_to_invoice
from documents.services.portal_security import verify_signed_token, generate_signed_token
from documents.services.ledger import create_ledger_event


# =========================================================
# INVOICE VIEWSET
# =========================================================

class InvoiceViewSet(viewsets.ModelViewSet):
    serializer_class = InvoiceSerializer
    permission_classes = [IsAuthenticated]

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["status", "currency", "client"]
    search_fields = ["number", "client__name"]
    ordering_fields = ["created_at", "due_date", "total_amount"]

    def get_queryset(self):
        return Invoice.objects.filter(
            company__owner=self.request.user,
            is_deleted=False
        ).select_related("client", "company").prefetch_related("line_items")

    # -------------------------
    # CREATE + LEDGER
    # -------------------------
    def perform_create(self, serializer):
        company = serializer.validated_data["company"]

        with transaction.atomic():
            # Let the serializer build instance and lines atomically
            invoice = serializer.save(
                created_by=self.request.user,
                number=company.next_invoice_number()
            )

        # The lines are now calculated, snapshot total is correct!
        create_ledger_event(
            user=self.request.user,
            event_type="INVOICE_CREATED",
            snapshot={
                "id": str(invoice.id),
                "number": invoice.number,
                "total": str(invoice.total_amount),
            },
            invoice_id=invoice.id
        )

    # -------------------------
    # SIGNED PORTAL
    # -------------------------
    @action(detail=True, methods=["get"], url_path="portal", permission_classes=[AllowAny])
    def portal(self, request, pk=None):
        token = request.query_params.get("token")

        if not token:
            return Response({"error": "Missing token"}, status=400)

        # Optimized lookups preventing N+1 database leaks
        invoice = get_object_or_404(
            Invoice.objects.select_related("client", "company").prefetch_related("line_items"),
            id=pk,
            is_deleted=False
        )

        # Verify HMAC signature security + timestamp expiry bounds
        if not verify_signed_token(token, invoice.id):
            return Response({"error": "Invalid or expired link"}, status=403)

        # Update status safely if transition criteria are matched
        if invoice.status == Invoice.Status.SENT:
            invoice.status = Invoice.Status.VIEWED
            invoice.viewed_at = timezone.now()
            invoice.save(update_fields=["status", "viewed_at"])

            create_ledger_event(
                user=invoice.created_by,
                event_type="INVOICE_VIEWED",
                snapshot={
                    "id": str(invoice.id),
                    "number": invoice.number,
                    "total": str(invoice.total_amount),
                },
                invoice_id=invoice.id
            )

        return Response(
            InvoiceSerializer(invoice, context={"request": request}).data
        )

    # -------------------------
    # SIGNED LINK GENERATOR
    # -------------------------
    @action(detail=True, methods=["get"])
    def signed_link(self, request, pk=None):
        invoice = self.get_object()
        token = generate_signed_token(invoice.id, expires_in=86400)

        frontend_url = getattr(settings, "FRONTEND_URL", "").rstrip("/")
        url = f"{frontend_url}/portal/{invoice.id}?token={token}"

        return Response({"signed_url": url})

    # -------------------------
    # PDF GENERATION
    # -------------------------
    @action(detail=True, methods=["post"])
    def generate_pdf(self, request, pk=None):
        invoice = self.get_object()
        task = generate_invoice_pdf.delay(str(invoice.id))
        return Response({"task_id": task.id, "status": "queued"})

    # -------------------------
    # SEND EMAIL
    # -------------------------
    @action(detail=True, methods=["post"])
    def send_email(self, request, pk=None):
        invoice = self.get_object()

        if not invoice.client or not invoice.client.email:
            return Response({"error": "No client email context found."}, status=400)

        with transaction.atomic():
            invoice.status = Invoice.Status.SENT
            invoice.sent_at = timezone.now()
            invoice.save(update_fields=["status", "sent_at"])

        send_invoice_email.delay(str(invoice.id))
        return Response({"detail": "Invoice transmission queued."})

    # -------------------------
    # MARK PAID
    # -------------------------
    @action(detail=True, methods=["post"])
    def mark_paid(self, request, pk=None):
        invoice = self.get_object()

        if invoice.status == Invoice.Status.PAID:
            return Response({"error": "Invoice has already been resolved."}, status=400)

        with transaction.atomic():
            invoice.status = Invoice.Status.PAID
            invoice.paid_at = timezone.now()
            invoice.save(update_fields=["status", "paid_at"])

        create_ledger_event(
            user=request.user,
            event_type="INVOICE_PAID",
            snapshot={
                "id": str(invoice.id),
                "number": invoice.number,
                "total": str(invoice.total_amount),
            },
            invoice_id=invoice.id
        )

        return Response(InvoiceSerializer(invoice, context={"request": request}).data)

    # -------------------------
    # DUPLICATE
    # -------------------------
    @action(detail=True, methods=["post"])
    def duplicate(self, request, pk=None):
        invoice = self.get_object()
        new_invoice = clone_invoice(invoice, request.user)

        return Response(
            InvoiceSerializer(new_invoice, context={"request": request}).data,
            status=201
        )


# =========================================================
# QUOTATION VIEWSET
# =========================================================

class QuotationViewSet(viewsets.ModelViewSet):
    serializer_class = QuotationSerializer
    permission_classes = [IsAuthenticated]

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["status", "currency"]
    search_fields = ["number", "client__name"]

    def get_queryset(self):
        return Quotation.objects.filter(
            company__owner=self.request.user,
            is_deleted=False
        ).select_related("client", "company").prefetch_related("line_items")

    def perform_create(self, serializer):
        company = serializer.validated_data["company"]

        # Safely determine the sequence generation without bleeding into invoices
        quote_counter = Quotation.objects.filter(company=company).count() + 1
        number = f"QT-{quote_counter:04d}"

        with transaction.atomic():
            serializer.save(
                created_by=self.request.user,
                number=number
            )

    @action(detail=True, methods=["post"])
    def convert_to_invoice(self, request, pk=None):
        quotation = self.get_object()

        with transaction.atomic():
            invoice = convert_quotation_to_invoice(quotation, request.user)

        return Response(
            InvoiceSerializer(invoice, context={"request": request}).data,
            status=201
        )


# =========================================================
# CONTRACT VIEWSET
# =========================================================

class ContractViewSet(viewsets.ModelViewSet):
    serializer_class = ContractSerializer
    permission_classes = [IsAuthenticated]

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["status", "contract_type"]
    search_fields = ["title", "client__name"]

    def get_queryset(self):
        return Contract.objects.filter(
            company__owner=self.request.user
        ).select_related("client", "company")

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=["post"])
    def generate_pdf(self, request, pk=None):
        from .tasks import generate_contract_pdf

        contract = self.get_object()
        task = generate_contract_pdf.delay(str(contract.id))

        return Response({"task_id": task.id, "status": "queued"})