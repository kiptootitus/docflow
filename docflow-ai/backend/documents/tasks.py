"""
DocFlow AI — documents/tasks.py

Celery tasks for document generation and email delivery.

Tasks:
  generate_pdf_task(doc_type, doc_id)
  generate_docx_task(doc_type, doc_id)
  send_document_email_task(doc_type, doc_id)
  check_overdue_invoices()      — beat scheduler, daily
  check_expiring_contracts()    — beat scheduler, daily
  send_payment_reminder_task(invoice_id)

All tasks are idempotent and log errors to Sentry if configured.
"""

from __future__ import annotations

import logging

from celery import shared_task
from django.conf import settings
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _import_model(doc_type: str):
    """Return the model class for a given document type string."""
    mapping = {
        "invoice":   "documents.models.Invoice",
        "quotation": "documents.models.Quotation",
        "contract":  "documents.models.Contract",
    }
    if doc_type not in mapping:
        raise ValueError(f"Unknown doc_type: {doc_type!r}")
    module_path, class_name = mapping[doc_type].rsplit(".", 1)
    import importlib
    return getattr(importlib.import_module(module_path), class_name)


def _get_doc(doc_type: str, doc_id: str):
    Model = _import_model(doc_type)
    return (
        Model.objects
        .select_related("company", "company__branding", "company__vat_config", "created_by")
        .get(pk=doc_id)
    )


# ---------------------------------------------------------------------------
# PDF generation
# ---------------------------------------------------------------------------

@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
    name="documents.generate_pdf",
)
def generate_pdf_task(self, doc_type: str, doc_id: str) -> str:
    """
    Generate a PDF for the document and store it in S3.
    Returns the storage URL on success.
    """
    from .pdf_generator import generate_pdf_by_id

    logger.info("Generating PDF: %s %s", doc_type, doc_id)
    try:
        generate_pdf_by_id(doc_type, doc_id)
        doc = _get_doc(doc_type, doc_id)
        url = doc.pdf_file.url if doc.pdf_file else ""
        logger.info("PDF saved: %s", url)
        return url
    except Exception as exc:
        logger.exception("PDF generation failed for %s %s: %s", doc_type, doc_id, exc)
        raise self.retry(exc=exc)


# ---------------------------------------------------------------------------
# DOCX generation
# ---------------------------------------------------------------------------

@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
    name="documents.generate_docx",
)
def generate_docx_task(self, doc_type: str, doc_id: str) -> str:
    """
    Generate a DOCX file for the document and store it in S3.
    Returns the storage URL on success.
    """
    from .docx_generator import generate_docx_by_id

    logger.info("Generating DOCX: %s %s", doc_type, doc_id)
    try:
        generate_docx_by_id(doc_type, doc_id)
        doc = _get_doc(doc_type, doc_id)
        url = doc.docx_file.url if doc.docx_file else ""
        logger.info("DOCX saved: %s", url)
        return url
    except Exception as exc:
        logger.exception("DOCX generation failed for %s %s: %s", doc_type, doc_id, exc)
        raise self.retry(exc=exc)


# ---------------------------------------------------------------------------
# Email delivery
# ---------------------------------------------------------------------------

@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=5,
    name="documents.send_document_email",
)
def send_document_email_task(self, doc_type: str, doc_id: str) -> None:
    """
    Send the document to the client via email.
    Ensures a PDF exists before sending; generates one if missing.

    Email is sent via Django Anymail (SendGrid / Mailgun).
    """
    from django.core.mail import EmailMultiAlternatives
    from django.template.loader import render_to_string

    logger.info("Sending %s email for %s", doc_type, doc_id)

    try:
        doc = _get_doc(doc_type, doc_id)
    except Exception as exc:
        logger.error("Document not found: %s %s — %s", doc_type, doc_id, exc)
        return

    # Ensure PDF exists
    if not doc.pdf_file:
        from .pdf_generator import generate_pdf
        generate_pdf(doc_type, doc)
        doc.refresh_from_db()

    recipient = doc.client_email or (doc.client.email if doc.client else None)
    if not recipient:
        logger.warning("No recipient email for %s %s — skipping", doc_type, doc_id)
        return

    subject_map = {
        "invoice":   f"Invoice {doc.number} from {doc.company.name}",
        "quotation": f"Quotation {doc.number} from {doc.company.name}",
        "contract":  f"Contract {doc.number} from {doc.company.name}",
    }
    subject = subject_map.get(doc_type, f"Document {doc.number}")

    # Render email body
    context = {
        "doc":     doc,
        "company": doc.company,
        "doc_type": doc_type,
    }
    text_body = render_to_string(f"emails/{doc_type}_sent.txt", context)
    html_body = render_to_string(f"emails/{doc_type}_sent.html", context)

    from_email = (
        doc.company.email
        or getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@docflowai.com")
    )

    email = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=from_email,
        to=[recipient],
    )
    email.attach_alternative(html_body, "text/html")

    # Attach PDF
    if doc.pdf_file:
        try:
            doc.pdf_file.open("rb")
            email.attach(
                filename=f"{doc.number}.pdf",
                content=doc.pdf_file.read(),
                mimetype="application/pdf",
            )
            doc.pdf_file.close()
        except Exception as exc:
            logger.warning("Could not attach PDF: %s", exc)

    try:
        email.send(fail_silently=False)
        logger.info("%s email sent to %s", doc_type, recipient)
    except Exception as exc:
        logger.exception("Email send failed for %s %s: %s", doc_type, doc_id, exc)
        raise self.retry(exc=exc)


# ---------------------------------------------------------------------------
# Scheduled: overdue invoice check
# ---------------------------------------------------------------------------

@shared_task(name="documents.check_overdue_invoices")
def check_overdue_invoices() -> int:
    """
    Celery Beat task: run daily.
    Marks sent/viewed invoices as OVERDUE if past due date.
    Returns count of invoices updated.
    """
    from django.utils import timezone
    from .models import Invoice, InvoiceStatus

    today   = timezone.localdate()
    updated = Invoice.objects.filter(
        status__in=[InvoiceStatus.SENT, InvoiceStatus.VIEWED, InvoiceStatus.PARTIAL],
        due_date__lt=today,
        is_active=True,
    ).update(status=InvoiceStatus.OVERDUE)

    logger.info("check_overdue_invoices: %d invoices marked overdue", updated)
    return updated


# ---------------------------------------------------------------------------
# Scheduled: expiring contract alerts
# ---------------------------------------------------------------------------

@shared_task(name="documents.check_expiring_contracts")
def check_expiring_contracts() -> int:
    """
    Celery Beat task: run daily.
    Fires push notifications for contracts expiring within renewal_notice_days.
    Returns count of contracts alerted.
    """
    import datetime
    from django.utils import timezone
    from django.db.models import F
    from .models import Contract, ContractStatus

    today = timezone.localdate()
    alerted = 0

    # Find contracts where today == end_date - renewal_notice_days
    contracts = Contract.objects.filter(
        status__in=[ContractStatus.ACTIVE, ContractStatus.SIGNED],
        end_date__isnull=False,
        is_active=True,
    ).select_related("company", "created_by")

    for contract in contracts:
        notice_date = contract.end_date - datetime.timedelta(days=contract.renewal_notice_days)
        if notice_date == today:
            _notify_contract_expiring(contract)
            alerted += 1

    logger.info("check_expiring_contracts: %d notifications sent", alerted)
    return alerted


def _notify_contract_expiring(contract) -> None:
    """Send in-app notification + email to company owner about expiring contract."""
    try:
        from django.core.mail import send_mail
        send_mail(
            subject=f"Contract {contract.number} expiring soon",
            message=(
                f"Your contract {contract.number} with {contract.client_display_name} "
                f"expires on {contract.end_date}."
            ),
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@docflowai.com"),
            recipient_list=[contract.company.owner.email],
            fail_silently=True,
        )
    except Exception as exc:
        logger.warning("Could not send expiry notification: %s", exc)


# ---------------------------------------------------------------------------
# Payment reminder
# ---------------------------------------------------------------------------

@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
    name="documents.send_payment_reminder",
)
def send_payment_reminder_task(self, invoice_id: str) -> None:
    """
    Send a payment reminder email for an unpaid invoice.
    Called manually from the dashboard or by a Beat schedule.
    """
    try:
        from .models import Invoice
        invoice = Invoice.objects.select_related("company").get(pk=invoice_id)
    except Exception as exc:
        logger.error("Invoice not found: %s — %s", invoice_id, exc)
        return

    if invoice.status == "paid":
        logger.info("Invoice %s already paid — skipping reminder", invoice.number)
        return

    recipient = invoice.client_email or (invoice.client.email if invoice.client else None)
    if not recipient:
        return

    from django.core.mail import send_mail
    try:
        send_mail(
            subject=f"Reminder: Invoice {invoice.number} is due",
            message=(
                f"Dear {invoice.client_display_name},\n\n"
                f"This is a friendly reminder that invoice {invoice.number} "
                f"for {invoice.currency} {invoice.total:,.2f} "
                f"is {'overdue' if invoice.is_overdue else f'due on {invoice.due_date}'}.\n\n"
                f"Please arrange payment at your earliest convenience.\n\n"
                f"Thank you,\n{invoice.company.name}"
            ),
            from_email=invoice.company.email or settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            fail_silently=False,
        )
        logger.info("Payment reminder sent for invoice %s to %s", invoice.number, recipient)
    except Exception as exc:
        logger.exception("Reminder email failed for %s: %s", invoice_id, exc)
        raise self.retry(exc=exc)
