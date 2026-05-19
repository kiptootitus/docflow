from django.utils import timezone
from django.db import transaction

from documents.models import Invoice, InvoiceLineItem, Quotation


def clone_invoice(source_invoice, user):
    """
    Clone an existing invoice and its line items into a new draft invoice.
    """

    with transaction.atomic():

        new_invoice = Invoice.objects.create(
            company=source_invoice.company,
            client=source_invoice.client,
            created_by=user,
            number=source_invoice.company.next_invoice_number(),
            status=Invoice.Status.DRAFT,
            currency=source_invoice.currency,
            issue_date=timezone.now().date(),
            due_date=(
                timezone.now().date()
                + (
                    source_invoice.due_date - source_invoice.issue_date
                    if source_invoice.due_date and source_invoice.issue_date
                    else timezone.timedelta(days=14)
                )
            ),
            notes=source_invoice.notes,
            terms=source_invoice.terms,
            tax_rate=source_invoice.tax_rate,
            discount_amount=source_invoice.discount_amount,
        )

        for item in source_invoice.line_items.all():
            InvoiceLineItem.objects.create(
                invoice=new_invoice,
                description=item.description,
                quantity=item.quantity,
                unit_price=item.unit_price,
                order=item.order,
            )

        new_invoice.calculate_totals()

        return new_invoice


def convert_quotation_to_invoice(quotation, user):
    """
    Convert a quotation into an invoice.
    """

    with transaction.atomic():

        invoice = Invoice.objects.create(
            company=quotation.company,
            client=quotation.client,
            created_by=user,
            number=quotation.company.next_invoice_number(),
            status=Invoice.Status.DRAFT,
            currency=quotation.currency,
            issue_date=timezone.now().date(),
            due_date=timezone.now().date() + timezone.timedelta(days=14),
            notes=quotation.notes,
            terms=quotation.terms,
            tax_rate=quotation.tax_rate,
            discount_amount=quotation.discount_amount,
        )

        for item in quotation.line_items.all():
            InvoiceLineItem.objects.create(
                invoice=invoice,
                description=item.description,
                quantity=item.quantity,
                unit_price=item.unit_price,
                order=item.order,
            )

        invoice.calculate_totals()

        quotation.converted_to_invoice = invoice

        # only set this if your model supports it
        # quotation.status = Quotation.Status.CONVERTED

        quotation.save(update_fields=["converted_to_invoice"])

        return invoice