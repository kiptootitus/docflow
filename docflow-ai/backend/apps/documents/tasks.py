"""Documents Celery tasks — PDF generation, email, reminders"""
import logging
from celery import shared_task
from django.template.loader import render_to_string
from django.core.mail import EmailMultiAlternatives
from django.conf import settings

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def generate_invoice_pdf(self, invoice_id: str):
    """Generate PDF for an invoice and store it."""
    try:
        from .models import Invoice
        invoice = Invoice.objects.select_related("company", "client").prefetch_related("line_items").get(id=invoice_id)

        html = render_to_string("invoices/invoice_pdf.html", {
            "invoice": invoice,
            "company": invoice.company,
            "client": invoice.client,
            "line_items": invoice.line_items.all(),
        })

        try:
            from weasyprint import HTML as WeasyHTML
            pdf_bytes = WeasyHTML(string=html, base_url=settings.FRONTEND_URL).write_pdf()
        except ImportError:
            logger.warning("WeasyPrint not available, skipping PDF generation.")
            return {"status": "skipped", "reason": "WeasyPrint not installed"}

        filename = f"invoices/{invoice.number}.pdf"

        if settings.DEFAULT_FILE_STORAGE == "storages.backends.s3boto3.S3Boto3Storage":
            import boto3
            from io import BytesIO
            s3 = boto3.client("s3")
            s3.put_object(
                Bucket=settings.AWS_STORAGE_BUCKET_NAME,
                Key=filename,
                Body=pdf_bytes,
                ContentType="application/pdf",
            )
            invoice.pdf_file = filename
        else:
            from django.core.files.base import ContentFile
            invoice.pdf_file.save(f"{invoice.number}.pdf", ContentFile(pdf_bytes), save=False)

        invoice.save(update_fields=["pdf_file"])
        logger.info(f"PDF generated for invoice {invoice.number}")
        return {"status": "success", "invoice_id": invoice_id}

    except Exception as exc:
        logger.error(f"PDF generation failed for {invoice_id}: {exc}")
        raise self.retry(exc=exc, countdown=60)


@shared_task(bind=True, max_retries=3)
def send_invoice_email(self, invoice_id: str):
    """Send invoice email to client."""
    try:
        from .models import Invoice
        invoice = Invoice.objects.select_related("company", "client").get(id=invoice_id)
        if not invoice.client or not invoice.client.email:
            return {"status": "skipped", "reason": "no client email"}

        portal_url = f"{settings.FRONTEND_URL}/portal/{invoice.portal_token}"
        subject = f"Invoice {invoice.number} from {invoice.company.name}"

        html_body = render_to_string("emails/invoice_sent.html", {
            "invoice": invoice,
            "company": invoice.company,
            "client": invoice.client,
            "portal_url": portal_url,
        })
        text_body = f"Dear {invoice.client.name},\n\nPlease find your invoice {invoice.number}.\n\nView: {portal_url}"

        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=f"{invoice.company.name} <{invoice.company.email}>",
            to=[invoice.client.email],
        )
        msg.attach_alternative(html_body, "text/html")
        msg.send()

        logger.info(f"Invoice {invoice.number} emailed to {invoice.client.email}")
        return {"status": "sent"}

    except Exception as exc:
        logger.error(f"Email send failed for invoice {invoice_id}: {exc}")
        raise self.retry(exc=exc, countdown=120)


@shared_task
def send_payment_reminder(invoice_id: str):
    """Send payment reminder for overdue invoices."""
    from .models import Invoice
    from django.utils import timezone

    invoice = Invoice.objects.select_related("company", "client").get(id=invoice_id)
    if invoice.status not in [Invoice.Status.SENT, Invoice.Status.VIEWED]:
        return {"status": "skipped"}

    if invoice.due_date and invoice.due_date < timezone.now().date():
        invoice.status = Invoice.Status.OVERDUE
        invoice.save(update_fields=["status"])

    portal_url = f"{settings.FRONTEND_URL}/portal/{invoice.portal_token}"
    subject = f"REMINDER: Invoice {invoice.number} is overdue"
    text_body = f"This is a reminder that invoice {invoice.number} for {invoice.total_amount} {invoice.currency} is overdue.\n\nPay here: {portal_url}"

    msg = EmailMultiAlternatives(
        subject=subject, body=text_body,
        from_email=invoice.company.email,
        to=[invoice.client.email],
    )
    msg.send()
    return {"status": "reminder_sent"}


@shared_task
def generate_contract_pdf(contract_id: str):
    """Generate PDF for a contract."""
    try:
        from .models import Contract
        contract = Contract.objects.select_related("company", "client").get(id=contract_id)
        html = render_to_string("contracts/contract_pdf.html", {"contract": contract})

        try:
            from weasyprint import HTML as WeasyHTML
            pdf_bytes = WeasyHTML(string=html, base_url=settings.FRONTEND_URL).write_pdf()
        except ImportError:
            return {"status": "skipped"}

        from django.core.files.base import ContentFile
        contract.pdf_file.save(f"contract_{contract.id}.pdf", ContentFile(pdf_bytes), save=False)
        contract.save(update_fields=["pdf_file"])
        return {"status": "success"}
    except Exception as exc:
        logger.error(f"Contract PDF generation failed: {exc}")
        return {"status": "error", "detail": str(exc)}


@shared_task
def check_overdue_invoices():
    """Scheduled task: flag overdue invoices and send reminders."""
    from .models import Invoice
    from django.utils import timezone

    overdue = Invoice.objects.filter(
        status__in=[Invoice.Status.SENT, Invoice.Status.VIEWED],
        due_date__lt=timezone.now().date(),
    )
    for invoice in overdue:
        invoice.status = Invoice.Status.OVERDUE
        invoice.save(update_fields=["status"])
        if invoice.client and invoice.client.email:
            send_payment_reminder.delay(str(invoice.id))

    logger.info(f"Marked {overdue.count()} invoices as overdue")
    return {"overdue_count": overdue.count()}
