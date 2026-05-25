"""Documents views"""

from typing import Optional
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.db.models import Prefetch
from django.conf import settings

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.exceptions import ValidationError, PermissionDenied
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

import logging

from .models import Invoice, Quotation, Contract
from .serializers import InvoiceSerializer, QuotationSerializer, ContractSerializer
from .tasks import generate_invoice_pdf, send_invoice_email
from documents.services.documents import clone_invoice, convert_quotation_to_invoice
from documents.services.portal_security import verify_signed_token, generate_signed_token
from documents.services.ledger import create_ledger_event

logger = logging.getLogger(__name__)


# =========================================================
# THROTTLING
# =========================================================

class AnonThrottle(AnonRateThrottle):
    scope = "anon"
    rate = "100/hour"


class UserThrottle(UserRateThrottle):
    scope = "user"
    rate = "1000/hour"


# =========================================================
# SHARED HELPER
# =========================================================

def _verify_company_access(company, user):
    """
    Raise PermissionDenied if user does not own the given company.
    Centralised so all three viewsets use the same check.
    """
    if company.owner != user:
        raise PermissionDenied("You don't have access to this company.")


# =========================================================
# INVOICE VIEWSET
# =========================================================

class InvoiceViewSet(viewsets.ModelViewSet):
    """
    Full CRUD for invoices plus portal, email, PDF, and payment actions.

    Public endpoints (no auth required):
        GET  /invoices/{id}/portal/?token=<signed>   — client portal view

    Authenticated endpoints:
        GET  /invoices/{id}/signed_link/             — generate signed portal URL
        POST /invoices/{id}/generate_pdf/            — queue PDF generation
        POST /invoices/{id}/send_email/              — send invoice to client
        POST /invoices/{id}/mark_paid/               — record payment
        POST /invoices/{id}/duplicate/               — clone invoice
    """

    serializer_class = InvoiceSerializer
    permission_classes = [IsAuthenticated]
    throttle_classes = [AnonThrottle, UserThrottle]

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["status", "currency", "client"]
    search_fields = ["number", "client__name"]
    ordering_fields = ["created_at", "due_date", "total_amount"]
    ordering = ["-created_at"]

    def get_queryset(self):
        return (
            Invoice.objects.filter(
                company__owner=self.request.user,
                is_deleted=False,
            )
            .select_related("client", "company")
            .prefetch_related("line_items")
            .order_by("-created_at")
        )

    # -------------------------
    # CREATE
    # -------------------------
    def perform_create(self, serializer):
        company = serializer.validated_data.get("company")
        if not company:
            raise ValidationError({"company": "This field is required."})
        _verify_company_access(company, self.request.user)

        # FIX: inline invoice numbering — no dependency on a missing
        # Company.next_invoice_number() method, race-safe with select_for_update
        # inside the serializer's atomic create block.
        with transaction.atomic():
            count = (
                Invoice.objects.select_for_update()
                .filter(company=company, is_deleted=False)
                .count()
            )
            number = f"INV-{count + 1:04d}"

            invoice = serializer.save(
                created_by=self.request.user,
                number=number,
            )

        try:
            create_ledger_event(
                user=self.request.user,
                event_type="INVOICE_CREATED",
                snapshot={
                    "id": str(invoice.id),
                    "number": invoice.number,
                    "total": str(invoice.total_amount),
                    "client_id": str(invoice.client.id) if invoice.client else None,
                },
                invoice_id=invoice.id,
            )
        except Exception as e:
            logger.error(f"Ledger event failed for invoice {invoice.id}: {e}")

    # -------------------------
    # PUBLIC PORTAL
    # -------------------------
    @action(
        detail=True,
        methods=["get"],
        url_path="portal",
        permission_classes=[AllowAny],
        throttle_classes=[AnonThrottle],
    )
    def portal(self, request, pk: Optional[str] = None) -> Response:
        """
        Public client portal — retrieves invoice data via a signed token.

        URL:  GET /api/documents/invoices/{invoice_uuid}/portal/?token={signed}

        The frontend route should be:  /portal/:invoiceId
        and it must pass ?token= as a query parameter (not in the path).

        Flow:
            1. signed_link action generates the full URL and emails it to the client
            2. Client clicks link → lands on /portal/:invoiceId?token=...
            3. Frontend calls this endpoint with the invoice UUID + token
            4. Backend verifies HMAC signature, returns invoice data
        """
        token = request.query_params.get("token")
        if not token:
            return Response(
                {"detail": "Missing token.", "error": "missing_token"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        invoice = get_object_or_404(
            Invoice.objects.select_related("client", "company").prefetch_related("line_items"),
            id=pk,
            is_deleted=False,
        )

        if not verify_signed_token(token, invoice.id):
            logger.warning(f"Invalid/expired portal token for invoice {invoice.id}")
            return Response(
                {"detail": "This link has expired or is invalid.", "error": "invalid_token"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Atomic: only transition SENT → VIEWED once (race-safe)
        updated = Invoice.objects.filter(
            id=invoice.id,
            status=Invoice.Status.SENT,
        ).update(
            status=Invoice.Status.VIEWED,
            viewed_at=timezone.now(),
            portal_used=True,
        )

        if updated:
            invoice.refresh_from_db()
            try:
                create_ledger_event(
                    user=invoice.created_by,
                    event_type="INVOICE_VIEWED",
                    snapshot={
                        "id": str(invoice.id),
                        "number": invoice.number,
                        "total": str(invoice.total_amount),
                    },
                    invoice_id=invoice.id,
                )
            except Exception as e:
                logger.error(f"Ledger event failed on invoice view {invoice.id}: {e}")

        return Response(InvoiceSerializer(invoice, context={"request": request}).data)

    # -------------------------
    # SIGNED LINK GENERATOR
    # -------------------------
    @action(detail=True, methods=["get"])
    def signed_link(self, request, pk: Optional[str] = None) -> Response:
        """
        Generate a time-limited signed URL for the client portal.

        Returns:
            {
                "signed_url": "https://app.docflowai.com/portal/{id}?token={token}",
                "expires_in": 86400
            }
        """
        invoice = self.get_object()
        expires_in = 86400  # 24 hours

        try:
            token = generate_signed_token(invoice.id, expires_in=expires_in)
        except Exception as e:
            logger.error(f"Failed to generate signed token for invoice {invoice.id}: {e}")
            return Response(
                {"error": "Could not generate portal link."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        frontend_url = getattr(settings, "FRONTEND_URL", "").rstrip("/")
        url = f"{frontend_url}/portal/{invoice.id}?token={token}"

        return Response({"signed_url": url, "expires_in": expires_in})

    # -------------------------
    # PDF GENERATION
    # -------------------------
    @action(detail=True, methods=["post"])
    def generate_pdf(self, request, pk: Optional[str] = None) -> Response:
        """Queue PDF generation via Celery."""
        invoice = self.get_object()
        try:
            task = generate_invoice_pdf.delay(str(invoice.id))
            return Response({"task_id": task.id, "status": "queued"})
        except Exception as e:
            logger.error(f"Failed to queue PDF for invoice {invoice.id}: {e}")
            return Response(
                {"error": "Failed to queue PDF generation."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # -------------------------
    # SEND EMAIL
    # -------------------------
    @action(detail=True, methods=["post"])
    def send_email(self, request, pk: Optional[str] = None) -> Response:
        """
        Send invoice email to client and transition status to SENT.

        Validates client and company email before queuing the Celery task.
        """
        invoice = self.get_object()

        if not invoice.client:
            return Response(
                {"error": "No client is assigned to this invoice."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not invoice.client.email:
            return Response(
                {"error": "The assigned client has no email address."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not invoice.company.email:
            return Response(
                {"error": "Company sending email is not configured."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        with transaction.atomic():
            Invoice.objects.filter(id=invoice.id).update(
                status=Invoice.Status.SENT,
                sent_at=timezone.now(),
            )

        try:
            send_invoice_email.delay(str(invoice.id))
        except Exception as e:
            logger.error(f"Failed to queue email for invoice {invoice.id}: {e}")
            return Response(
                {"error": "Failed to queue email delivery."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response({
            "detail": "Invoice email has been queued for delivery.",
            "status": "sent",
        })

    # -------------------------
    # MARK PAID
    # -------------------------
    @action(detail=True, methods=["post"])
    def mark_paid(self, request, pk: Optional[str] = None) -> Response:
        """
        Mark invoice as paid. Uses select_for_update to prevent double-payment.
        """
        invoice = self.get_object()

        with transaction.atomic():
            updated = (
                Invoice.objects.select_for_update()
                .filter(id=invoice.id, is_deleted=False)
                .exclude(status=Invoice.Status.PAID)
                .update(status=Invoice.Status.PAID, paid_at=timezone.now())
            )

            if updated == 0:
                return Response(
                    {"error": "Invoice is already paid or has been deleted."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            invoice.refresh_from_db()

            try:
                create_ledger_event(
                    user=request.user,
                    event_type="INVOICE_PAID",
                    snapshot={
                        "id": str(invoice.id),
                        "number": invoice.number,
                        "total": str(invoice.total_amount),
                    },
                    invoice_id=invoice.id,
                )
            except Exception as e:
                logger.error(f"Ledger event failed on invoice payment {invoice.id}: {e}")

        return Response(InvoiceSerializer(invoice, context={"request": request}).data)

    # -------------------------
    # DUPLICATE
    # -------------------------
    @action(detail=True, methods=["post"])
    def duplicate(self, request, pk: Optional[str] = None) -> Response:
        """Clone an invoice (for creating recurring or similar invoices)."""
        invoice = self.get_object()

        try:
            new_invoice = clone_invoice(invoice, request.user)
        except Exception as e:
            logger.error(f"Failed to clone invoice {invoice.id}: {e}")
            return Response(
                {"error": "Failed to duplicate invoice."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            InvoiceSerializer(new_invoice, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


# =========================================================
# QUOTATION VIEWSET
# =========================================================

class QuotationViewSet(viewsets.ModelViewSet):
    """Full CRUD for quotations plus convert-to-invoice action."""

    serializer_class = QuotationSerializer
    permission_classes = [IsAuthenticated]
    throttle_classes = [AnonThrottle, UserThrottle]

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["status", "currency", "client"]
    search_fields = ["number", "client__name"]
    ordering_fields = ["created_at", "due_date", "total_amount"]
    ordering = ["-created_at"]

    def get_queryset(self):
        return (
            Quotation.objects.filter(
                company__owner=self.request.user,
                is_deleted=False,
            )
            .select_related("client", "company")
            .prefetch_related("line_items")
        )

    def perform_create(self, serializer):
        company = serializer.validated_data.get("company")
        if not company:
            raise ValidationError({"company": "This field is required."})
        _verify_company_access(company, self.request.user)

        with transaction.atomic():
            count = (
                Quotation.objects.select_for_update()
                .filter(company=company, is_deleted=False)
                .count()
            )
            number = f"QT-{count + 1:04d}"
            serializer.save(created_by=self.request.user, number=number)

    @action(detail=True, methods=["post"])
    def convert_to_invoice(self, request, pk: Optional[str] = None) -> Response:
        """Convert an accepted quotation into a draft invoice."""
        quotation = self.get_object()

        try:
            with transaction.atomic():
                invoice = convert_quotation_to_invoice(quotation, request.user)
        except Exception as e:
            logger.error(f"Failed to convert quotation {quotation.id}: {e}")
            return Response(
                {"error": "Failed to convert quotation to invoice."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            InvoiceSerializer(invoice, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


# =========================================================
# CONTRACT VIEWSET
# =========================================================

class ContractViewSet(viewsets.ModelViewSet):
    """Full CRUD for contracts plus PDF generation."""

    serializer_class = ContractSerializer
    permission_classes = [IsAuthenticated]
    throttle_classes = [AnonThrottle, UserThrottle]

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["status", "contract_type"]
    search_fields = ["title", "client__name"]
    ordering_fields = ["created_at", "start_date", "end_date"]
    ordering = ["-created_at"]

    def get_queryset(self):
        return (
            Contract.objects.filter(company__owner=self.request.user)
            .select_related("client", "company")
            .prefetch_related("versions")
        )

    def perform_create(self, serializer):
        company = serializer.validated_data.get("company")
        if not company:
            raise ValidationError({"company": "This field is required."})
        _verify_company_access(company, self.request.user)
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=["post"])
    def generate_pdf(self, request, pk: Optional[str] = None) -> Response:
        """Queue PDF generation for a contract via Celery."""
        from .tasks import generate_contract_pdf

        contract = self.get_object()
        try:
            task = generate_contract_pdf.delay(str(contract.id))
            return Response({"task_id": task.id, "status": "queued"})
        except Exception as e:
            logger.error(f"Failed to queue PDF for contract {contract.id}: {e}")
            return Response(
                {"error": "Failed to queue PDF generation."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )