"""Documents views"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.shortcuts import get_object_or_404
from django.utils import timezone
from .models import Invoice, Quotation, Contract
from .serializers import InvoiceSerializer, QuotationSerializer, ContractSerializer
from .tasks import generate_invoice_pdf, send_invoice_email, send_payment_reminder


class InvoiceViewSet(viewsets.ModelViewSet):
    serializer_class = InvoiceSerializer
    filterset_fields = ["status", "currency", "client"]
    search_fields = ["number", "client__name"]
    ordering_fields = ["created_at", "due_date", "total_amount"]

    def get_queryset(self):
        return Invoice.objects.filter(
            company__owner=self.request.user
        ).select_related("client", "company").prefetch_related("line_items")

    def perform_create(self, serializer):
        company = serializer.validated_data["company"]
        number = company.next_invoice_number()
        serializer.save(created_by=self.request.user, number=number)

    @action(detail=True, methods=["post"])
    def generate_pdf(self, request, pk=None):
        invoice = self.get_object()
        task = generate_invoice_pdf.delay(str(invoice.id))
        return Response({"task_id": task.id, "status": "queued"})

    @action(detail=True, methods=["post"])
    def send_email(self, request, pk=None):
        invoice = self.get_object()
        if not invoice.client or not invoice.client.email:
            return Response({"error": "No client email."}, status=400)
        invoice.status = Invoice.Status.SENT
        invoice.sent_at = timezone.now()
        invoice.save(update_fields=["status", "sent_at"])
        send_invoice_email.delay(str(invoice.id))
        return Response({"detail": "Invoice sent."})

    @action(detail=True, methods=["post"])
    def mark_paid(self, request, pk=None):
        invoice = self.get_object()
        invoice.status = Invoice.Status.PAID
        invoice.paid_at = timezone.now()
        invoice.save(update_fields=["status", "paid_at"])
        return Response(InvoiceSerializer(invoice, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def duplicate(self, request, pk=None):
        invoice = self.get_object()
        line_items = list(invoice.line_items.values("description", "quantity", "unit_price", "order"))
        new_number = invoice.company.next_invoice_number()
        from django.utils.timezone import now
        import datetime
        new_invoice = Invoice.objects.create(
            company=invoice.company,
            client=invoice.client,
            created_by=request.user,
            number=new_number,
            currency=invoice.currency,
            issue_date=now().date(),
            due_date=now().date() + datetime.timedelta(days=invoice.company.payment_due_days),
            notes=invoice.notes,
            terms=invoice.terms,
            tax_rate=invoice.tax_rate,
        )
        from .models import InvoiceLineItem
        for item in line_items:
            InvoiceLineItem.objects.create(invoice=new_invoice, **item)
        new_invoice.calculate_totals()
        return Response(InvoiceSerializer(new_invoice, context={"request": request}).data, status=201)

    @action(detail=True, methods=["get"], url_path="portal", permission_classes=[AllowAny])
    def portal(self, request, pk=None):
        """Public client portal — accessed via token in URL."""
        token = request.query_params.get("token")
        invoice = get_object_or_404(Invoice, id=pk, portal_token=token)
        if invoice.status == Invoice.Status.SENT:
            invoice.status = Invoice.Status.VIEWED
            invoice.viewed_at = timezone.now()
            invoice.save(update_fields=["status", "viewed_at"])
        return Response(InvoiceSerializer(invoice, context={"request": request}).data)


class QuotationViewSet(viewsets.ModelViewSet):
    serializer_class = QuotationSerializer
    filterset_fields = ["status", "currency"]
    search_fields = ["number", "client__name"]

    def get_queryset(self):
        return Quotation.objects.filter(
            company__owner=self.request.user
        ).select_related("client", "company").prefetch_related("line_items")

    def perform_create(self, serializer):
        company = serializer.validated_data["company"]
        number = f"QT-{company.invoice_counter:04d}"
        serializer.save(created_by=self.request.user, number=number)

    @action(detail=True, methods=["post"])
    def convert_to_invoice(self, request, pk=None):
        quotation = self.get_object()
        line_items = list(quotation.line_items.values("description", "quantity", "unit_price", "order"))
        invoice_number = quotation.company.next_invoice_number()
        import datetime
        from django.utils.timezone import now
        invoice = Invoice.objects.create(
            company=quotation.company,
            client=quotation.client,
            created_by=request.user,
            number=invoice_number,
            currency=quotation.currency,
            issue_date=now().date(),
            due_date=now().date() + datetime.timedelta(days=quotation.company.payment_due_days),
            notes=quotation.notes,
            terms=quotation.terms,
            tax_rate=quotation.tax_rate,
        )
        from .models import InvoiceLineItem
        for item in line_items:
            InvoiceLineItem.objects.create(invoice=invoice, **item)
        invoice.calculate_totals()
        quotation.converted_to_invoice = invoice
        quotation.save(update_fields=["converted_to_invoice"])
        return Response(InvoiceSerializer(invoice, context={"request": request}).data, status=201)


class ContractViewSet(viewsets.ModelViewSet):
    serializer_class = ContractSerializer
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
