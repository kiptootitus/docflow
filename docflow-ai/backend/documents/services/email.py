# documents/services/email.py
# ─────────────────────────────────────────────────────────────────────────────
# Transactional email service for invoices and quotations.
# Uses Django Anymail (SendGrid / Mailgun backend).
# ─────────────────────────────────────────────────────────────────────────────

import logging
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings

logger = logging.getLogger(__name__)


def send_invoice_email(invoice) -> bool:
    """
    Send an invoice email to the client with a portal link.
    Returns True on success, False on failure.

    Template: templates/documents/email/invoice.html
    """
    if not invoice.client or not invoice.client.email:
        logger.warning(f"Invoice {invoice.number}: no client email — skipping send")
        return False

    context = {
        "invoice":     invoice,
        "company":     invoice.company,
        "client":      invoice.client,
        "portal_url":  invoice.portal_url,
        "amount":      f"{invoice.currency} {invoice.total_amount}",
    }

    subject   = f"Invoice {invoice.number} from {invoice.company.name}"
    html_body = render_to_string("documents/email/invoice.html", context)
    text_body = (
        f"Hi {invoice.client.name},\n\n"
        f"{invoice.company.name} has sent you invoice {invoice.number} "
        f"for {invoice.currency} {invoice.total_amount}.\n\n"
        f"View and pay online: {invoice.portal_url}\n\n"
        f"— {invoice.company.name}"
    )

    try:
        msg = EmailMultiAlternatives(
            subject   = subject,
            body      = text_body,
            from_email= f"{invoice.company.name} <{settings.DEFAULT_FROM_EMAIL}>",
            to        = [invoice.client.email],
        )
        msg.attach_alternative(html_body, "text/html")
        msg.send()

        # Mark as sent
        invoice.status = "sent"
        invoice.save(update_fields=["status"])

        logger.info(f"Invoice email sent: {invoice.number} → {invoice.client.email}")
        return True

    except Exception as e:
        logger.error(f"Invoice email failed for {invoice.number}: {e}")
        return False


def send_quotation_email(quotation) -> bool:
    """
    Send a quotation email to the client with a portal link.
    Returns True on success, False on failure.

    Template: templates/documents/email/quotation.html
    """
    if not quotation.client or not quotation.client.email:
        logger.warning(f"Quotation {quotation.number}: no client email — skipping")
        return False

    context = {
        "quotation":  quotation,
        "company":    quotation.company,
        "client":     quotation.client,
        "portal_url": quotation.portal_url,
        "amount":     f"{quotation.currency} {quotation.total_amount}",
        "expiry":     quotation.expiry_date,
    }

    subject   = f"Quotation {quotation.number} from {quotation.company.name}"
    html_body = render_to_string("documents/email/quotation.html", context)
    text_body = (
        f"Hi {quotation.client.name},\n\n"
        f"{quotation.company.name} has sent you a quotation {quotation.number} "
        f"for {quotation.currency} {quotation.total_amount}.\n\n"
        f"Valid until: {quotation.expiry_date}\n\n"
        f"View and accept here: {quotation.portal_url}\n\n"
        f"— {quotation.company.name}"
    )

    try:
        msg = EmailMultiAlternatives(
            subject   = subject,
            body      = text_body,
            from_email= f"{quotation.company.name} <{settings.DEFAULT_FROM_EMAIL}>",
            to        = [quotation.client.email],
        )
        msg.attach_alternative(html_body, "text/html")
        msg.send()

        quotation.status = "sent"
        quotation.save(update_fields=["status"])

        logger.info(f"Quotation email sent: {quotation.number} → {quotation.client.email}")
        return True

    except Exception as e:
        logger.error(f"Quotation email failed for {quotation.number}: {e}")
        return False