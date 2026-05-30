"""
DocFlow AI — documents/tasks.py
================================
Enterprise-grade Celery tasks for document generation, email delivery,
scheduled maintenance, and recurring invoice automation.

Task index
──────────
  Document generation
    generate_pdf_task(doc_type, doc_id)
    generate_docx_task(doc_type, doc_id)
    bulk_generate_pdfs_task(doc_type, doc_ids)

  Email delivery
    send_document_email_task(doc_type, doc_id)
    send_payment_reminder_task(invoice_id)
    notify_contract_signed(contract_id)          ← called from ContractViewSet.sign()

  Scheduled maintenance  [Celery Beat]
    check_overdue_invoices()                     ← daily
    check_expiring_contracts()                   ← daily
    generate_recurring_invoices()                ← daily
    cleanup_old_document_versions()              ← weekly

  Recurring billing
    generate_invoice_from_schedule(schedule_id)

  AI integration
    (stub) run_contract_ai_review(contract_id)   ← delegates to ai.tasks

Celery Beat schedule (add to CELERY_BEAT_SCHEDULE in settings):

    CELERY_BEAT_SCHEDULE = {
        "check-overdue-invoices":          {"task": "documents.check_overdue_invoices",   "schedule": crontab(hour=1, minute=0)},
        "check-expiring-contracts":        {"task": "documents.check_expiring_contracts", "schedule": crontab(hour=1, minute=15)},
        "generate-recurring-invoices":     {"task": "documents.generate_recurring_invoices","schedule": crontab(hour=6, minute=0)},
        "cleanup-old-document-versions":   {"task": "documents.cleanup_document_versions","schedule": crontab(day_of_week=0, hour=3, minute=0)},
    }
"""

from __future__ import annotations

import datetime
import logging

from celery import chord, group, shared_task
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sentry helper — reports errors without hard-depending on sentry-sdk
# ---------------------------------------------------------------------------

def _capture_exception(exc: Exception) -> None:
    try:
        import sentry_sdk
        sentry_sdk.capture_exception(exc)
    except ImportError:
        pass


# ---------------------------------------------------------------------------
# Model / document helpers
# ---------------------------------------------------------------------------

_DOC_MODEL_PATHS = {
    "invoice":   "documents.models.Invoice",
    "quotation": "documents.models.Quotation",
    "contract":  "documents.models.Contract",
}


def _import_model(doc_type: str):
    """Return the model class for a document type string."""
    if doc_type not in _DOC_MODEL_PATHS:
        raise ValueError(f"Unknown doc_type: {doc_type!r}")
    module_path, class_name = _DOC_MODEL_PATHS[doc_type].rsplit(".", 1)
    import importlib
    return getattr(importlib.import_module(module_path), class_name)


def _get_doc(doc_type: str, doc_id: str):
    """Fetch a document with all related data pre-loaded."""
    Model = _import_model(doc_type)
    return (
        Model.objects
        .select_related(
            "company",
            "company__branding",
            "company__vat_config",
            "company__owner",
            "client",
            "created_by",
        )
        .get(pk=doc_id)
    )


# ===========================================================================
# 1. PDF GENERATION
# ===========================================================================

@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    max_retries=3,
    name="documents.generate_pdf",
    acks_late=True,
)
def generate_pdf_task(self, doc_type: str, doc_id: str) -> str:
    """
    Generate a PDF for the document and upload to S3.
    Returns the storage URL on success.

    Called by:
      • InvoiceViewSet.download_pdf / QuotationViewSet.download_pdf / ContractViewSet.download_pdf
      • send_document_email_task (ensures PDF exists before attaching)
    """
    from .pdf_generator import generate_pdf_by_id
    from .models import ActivityAction

    logger.info("[PDF] Generating %s %s", doc_type, doc_id)
    try:
        generate_pdf_by_id(doc_type, doc_id)
        doc = _get_doc(doc_type, doc_id)
        url = doc.pdf_file.url if doc.pdf_file else ""

        # Log the generation activity
        try:
            doc.log_activity(ActivityAction.PDF_GEN)
        except Exception:
            pass

        logger.info("[PDF] Saved %s bytes → %s", doc_type, url)
        return url

    except Exception as exc:
        logger.exception("[PDF] Generation failed for %s %s: %s", doc_type, doc_id, exc)
        _capture_exception(exc)
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    max_retries=3,
    name="documents.generate_docx",
    acks_late=True,
)
def generate_docx_task(self, doc_type: str, doc_id: str) -> str:
    """
    Generate a DOCX for the document and upload to S3.
    Returns the storage URL on success.
    """
    from .docx_generator import generate_docx_by_id
    from .models import ActivityAction

    logger.info("[DOCX] Generating %s %s", doc_type, doc_id)
    try:
        generate_docx_by_id(doc_type, doc_id)
        doc = _get_doc(doc_type, doc_id)
        url = doc.docx_file.url if doc.docx_file else ""

        try:
            doc.log_activity(ActivityAction.DOCX_GEN)
        except Exception:
            pass

        logger.info("[DOCX] Saved → %s", url)
        return url

    except Exception as exc:
        logger.exception("[DOCX] Generation failed for %s %s: %s", doc_type, doc_id, exc)
        _capture_exception(exc)
        raise self.retry(exc=exc)


@shared_task(name="documents.bulk_generate_pdfs")
def bulk_generate_pdfs_task(doc_type: str, doc_ids: list[str]) -> dict:
    """
    Fan out PDF generation for a list of document IDs.
    Uses a Celery group so all run in parallel.

    Returns {"queued": N, "doc_ids": [...]}
    """
    job = group(generate_pdf_task.s(doc_type, doc_id) for doc_id in doc_ids)
    job.delay()
    logger.info("[PDF] Bulk queued %d %s PDFs", len(doc_ids), doc_type)
    return {"queued": len(doc_ids), "doc_type": doc_type}


# ===========================================================================
# 2. EMAIL DELIVERY
# ===========================================================================

@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=5,
    name="documents.send_document_email",
    acks_late=True,
)
def send_document_email_task(self, doc_type: str, doc_id: str) -> None:
    """
    Send the document to the client by email.

    Flow:
      1. Load document.
      2. If no PDF exists, generate one synchronously.
      3. Build HTML + text email from template.
      4. Attach the PDF.
      5. Send via Django Anymail (SendGrid / Mailgun).
      6. Log activity.
    """
    from django.core.mail import EmailMultiAlternatives
    from django.template.loader import render_to_string
    from .models import ActivityAction

    logger.info("[EMAIL] Sending %s email for %s", doc_type, doc_id)

    # ── Load document ────────────────────────────────────────────────────
    try:
        doc = _get_doc(doc_type, doc_id)
    except Exception as exc:
        logger.error("[EMAIL] Document not found: %s %s — %s", doc_type, doc_id, exc)
        return

    # ── Ensure PDF exists ────────────────────────────────────────────────
    if not doc.pdf_file:
        try:
            from .pdf_generator import generate_pdf
            generate_pdf(doc_type, doc)
            doc.refresh_from_db()
        except Exception as exc:
            logger.warning("[EMAIL] PDF generation failed, sending without attachment: %s", exc)

    # ── Determine recipient ──────────────────────────────────────────────
    recipient = doc.client_email or (
        doc.client.email if getattr(doc, "client", None) else None
    )
    if not recipient:
        logger.warning("[EMAIL] No recipient for %s %s — skipping", doc_type, doc_id)
        return

    # ── Build subject ────────────────────────────────────────────────────
    doc_labels = {
        "invoice":   "Invoice",
        "quotation": "Quotation",
        "contract":  "Contract",
    }
    label   = doc_labels.get(doc_type, "Document")
    subject = f"{label} {doc.number} from {doc.company.name}"

    # ── Render templates (fallback to plain strings if missing) ──────────
    ctx = {
        "doc":      doc,
        "company":  doc.company,
        "doc_type": doc_type,
        "label":    label,
    }
    try:
        text_body = render_to_string(f"emails/{doc_type}_sent.txt",  ctx)
        html_body = render_to_string(f"emails/{doc_type}_sent.html", ctx)
    except Exception:
        # Graceful fallback — plain text only
        text_body = (
            f"Dear {doc.client_formal_name},\n\n"
            f"Please find attached your {label.lower()} {doc.number}.\n\n"
            f"Total: {doc.currency} {doc.total:,.2f}\n\n"
            f"Regards,\n{doc.company.name}"
        )
        html_body = text_body.replace("\n", "<br>")

    from_email = (
        doc.company.email
        or getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@docflowai.com")
    )

    # ── Build email ──────────────────────────────────────────────────────
    email = EmailMultiAlternatives(
        subject    = subject,
        body       = text_body,
        from_email = from_email,
        to         = [recipient],
    )
    email.attach_alternative(html_body, "text/html")

    # ── Attach PDF ───────────────────────────────────────────────────────
    if doc.pdf_file:
        try:
            doc.pdf_file.open("rb")
            email.attach(
                filename = f"{doc.number}.pdf",
                content  = doc.pdf_file.read(),
                mimetype = "application/pdf",
            )
            doc.pdf_file.close()
        except Exception as exc:
            logger.warning("[EMAIL] Could not attach PDF: %s", exc)

    # ── Send ─────────────────────────────────────────────────────────────
    try:
        email.send(fail_silently=False)
        logger.info("[EMAIL] %s %s sent to %s", doc_type, doc.number, recipient)
        try:
            doc.log_activity(ActivityAction.EMAIL_SENT, note=f"To: {recipient}")
        except Exception:
            pass
    except Exception as exc:
        logger.exception("[EMAIL] Send failed for %s %s: %s", doc_type, doc_id, exc)
        _capture_exception(exc)
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
    name="documents.send_payment_reminder",
    acks_late=True,
)
def send_payment_reminder_task(self, invoice_id: str) -> None:
    """
    Send a payment reminder for an unpaid or overdue invoice.
    Can be triggered manually from the dashboard or by a Beat schedule.
    """
    from django.core.mail import EmailMultiAlternatives
    from .models import Invoice, InvoiceStatus, ActivityAction

    try:
        invoice = Invoice.objects.select_related("company").get(pk=invoice_id)
    except Invoice.DoesNotExist:
        logger.error("[REMINDER] Invoice not found: %s", invoice_id)
        return

    if invoice.status in (InvoiceStatus.PAID, InvoiceStatus.VOID, InvoiceStatus.CANCELLED):
        logger.info("[REMINDER] Invoice %s is %s — skipping", invoice.number, invoice.status)
        return

    recipient = invoice.client_email or (
        invoice.client.email if invoice.client else None
    )
    if not recipient:
        logger.warning("[REMINDER] No recipient for invoice %s", invoice.number)
        return

    overdue = invoice.is_overdue
    subject = (
        f"OVERDUE: Invoice {invoice.number} — {invoice.currency} {invoice.balance_due:,.2f}"
        if overdue else
        f"Reminder: Invoice {invoice.number} due {invoice.due_date}"
    )

    body = (
        f"Dear {invoice.client_formal_name},\n\n"
        f"{'This is an overdue notice' if overdue else 'This is a friendly reminder'} "
        f"for invoice {invoice.number} from {invoice.company.name}.\n\n"
        f"  Amount:     {invoice.currency} {invoice.total:,.2f}\n"
        f"  Paid:       {invoice.currency} {invoice.amount_paid:,.2f}\n"
        f"  Balance:    {invoice.currency} {invoice.balance_due:,.2f}\n"
        f"  Due Date:   {invoice.due_date}\n\n"
    )

    if invoice.stripe_payment_link_url:
        body += f"Pay online: {invoice.stripe_payment_link_url}\n\n"

    body += (
        f"Please arrange payment at your earliest convenience.\n\n"
        f"Regards,\n{invoice.company.name}"
    )

    from_email = invoice.company.email or settings.DEFAULT_FROM_EMAIL

    try:
        email = EmailMultiAlternatives(
            subject    = subject,
            body       = body,
            from_email = from_email,
            to         = [recipient],
        )
        email.send(fail_silently=False)
        logger.info("[REMINDER] Sent for invoice %s to %s", invoice.number, recipient)
        try:
            invoice.log_activity(ActivityAction.REMINDER, note=f"To: {recipient}")
        except Exception:
            pass
    except Exception as exc:
        logger.exception("[REMINDER] Failed for %s: %s", invoice_id, exc)
        _capture_exception(exc)
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
    name="documents.notify_contract_signed",
)
def notify_contract_signed(self, contract_id: str) -> None:
    """
    Notify the company owner when a contract is signed.
    Called from ContractViewSet.sign().
    Optionally delegates to a push notification service.
    """
    from django.core.mail import send_mail
    from .models import Contract

    try:
        contract = Contract.objects.select_related("company", "company__owner").get(pk=contract_id)
    except Contract.DoesNotExist:
        logger.error("[CONTRACT SIGNED] Contract not found: %s", contract_id)
        return

    owner_email = None
    try:
        owner_email = contract.company.owner.email
    except Exception:
        pass

    if not owner_email:
        logger.warning("[CONTRACT SIGNED] No owner email for company %s", contract.company)
        return

    try:
        send_mail(
            subject      = f"✓ Contract {contract.number} has been signed",
            message      = (
                f"Hello,\n\n"
                f"Contract {contract.number} ({contract.subject or 'No subject'}) "
                f"has been signed by {contract.signed_by_name}.\n\n"
                f"Signed at: {contract.signed_at}\n"
                f"IP address: {contract.signature_ip or 'not recorded'}\n\n"
                f"Log in to DocFlow AI to view the signed contract.\n\n"
                f"The DocFlow AI team"
            ),
            from_email   = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@docflowai.com"),
            recipient_list = [owner_email],
            fail_silently = False,
        )
        logger.info("[CONTRACT SIGNED] Notification sent to %s", owner_email)
    except Exception as exc:
        logger.warning("[CONTRACT SIGNED] Notification failed: %s", exc)
        raise self.retry(exc=exc)


# ===========================================================================
# 3. SCHEDULED: OVERDUE INVOICE CHECK
# ===========================================================================

@shared_task(name="documents.check_overdue_invoices")
def check_overdue_invoices() -> int:
    """
    Celery Beat task: run daily at 01:00.
    Marks SENT / VIEWED / PARTIAL invoices as OVERDUE if past due date.
    Returns count of invoices updated.
    """
    from .models import Invoice, InvoiceStatus

    today   = timezone.localdate()
    updated = (
        Invoice.objects
        .filter(
            status__in=[
                InvoiceStatus.SENT,
                InvoiceStatus.VIEWED,
                InvoiceStatus.PARTIAL,
            ],
            due_date__lt=today,
            is_active=True,
        )
        .update(status=InvoiceStatus.OVERDUE)
    )

    logger.info("[OVERDUE] Marked %d invoices as overdue", updated)

    # Optionally fire individual reminder tasks for newly-overdue invoices
    if updated > 0:
        _queue_overdue_reminders(today)

    return updated


def _queue_overdue_reminders(today) -> None:
    """Queue payment reminders for invoices that became overdue today."""
    from .models import Invoice, InvoiceStatus
    newly_overdue = Invoice.objects.filter(
        status=InvoiceStatus.OVERDUE,
        due_date=today - datetime.timedelta(days=1),
        is_active=True,
    ).exclude(client_email="")
    for inv in newly_overdue:
        send_payment_reminder_task.delay(str(inv.pk))


# ===========================================================================
# 4. SCHEDULED: EXPIRING CONTRACT ALERTS
# ===========================================================================

@shared_task(name="documents.check_expiring_contracts")
def check_expiring_contracts() -> int:
    """
    Celery Beat task: run daily at 01:15.
    Fires email notifications for contracts expiring within their
    renewal_notice_days window.
    Returns count of notifications sent.
    """
    from .models import Contract, ContractStatus

    today   = timezone.localdate()
    alerted = 0

    contracts = (
        Contract.objects
        .filter(
            status__in=[ContractStatus.ACTIVE, ContractStatus.SIGNED],
            end_date__isnull=False,
            is_active=True,
        )
        .select_related("company", "company__owner", "created_by")
    )

    for contract in contracts:
        notice_date = contract.end_date - datetime.timedelta(days=contract.renewal_notice_days)
        if notice_date == today:
            _notify_contract_expiring.delay(str(contract.pk))
            alerted += 1

    logger.info("[EXPIRY] Queued %d contract expiry notifications", alerted)
    return alerted


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
    name="documents.notify_contract_expiring",
)
def _notify_contract_expiring(self, contract_id: str) -> None:
    """Send expiry warning email to company owner."""
    from django.core.mail import send_mail
    from .models import Contract

    try:
        contract = Contract.objects.select_related("company", "company__owner").get(pk=contract_id)
    except Contract.DoesNotExist:
        return

    try:
        owner_email = contract.company.owner.email
    except Exception:
        return

    try:
        send_mail(
            subject    = f"⚠ Contract {contract.number} expires on {contract.end_date}",
            message    = (
                f"Hello,\n\n"
                f"Contract {contract.number} with {contract.client_display_name} "
                f"is set to expire on {contract.end_date} "
                f"({contract.renewal_notice_days} days from today).\n\n"
                f"{'This contract will auto-renew unless cancelled.' if contract.auto_renew else 'Please arrange renewal if needed.'}\n\n"
                f"Log in to DocFlow AI to review and take action.\n\n"
                f"The DocFlow AI team"
            ),
            from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@docflowai.com"),
            recipient_list = [owner_email],
            fail_silently = True,
        )
        logger.info("[EXPIRY] Notified %s about contract %s", owner_email, contract.number)
    except Exception as exc:
        logger.warning("[EXPIRY] Notification failed for %s: %s", contract_id, exc)
        raise self.retry(exc=exc)


# ===========================================================================
# 5. RECURRING INVOICE AUTOMATION
# ===========================================================================

@shared_task(name="documents.generate_recurring_invoices")
def generate_recurring_invoices() -> int:
    """
    Celery Beat task: run daily at 06:00.
    Finds all due RecurringInvoice schedules and spawns individual
    invoice-generation tasks for each.
    Returns count of schedules processed.
    """
    from .models import RecurringInvoice

    today = timezone.localdate()
    due_schedules = (
        RecurringInvoice.objects
        .filter(is_active=True, next_invoice_date__lte=today)
        .select_related("company", "template", "created_by")
    )

    ids   = [str(s.pk) for s in due_schedules]
    count = len(ids)

    if count:
        # Fan out — one task per schedule
        group(
            generate_invoice_from_schedule.s(schedule_id) for schedule_id in ids
        ).delay()
        logger.info("[RECURRING] Queued %d recurring invoice generations", count)
    else:
        logger.info("[RECURRING] No schedules due today")

    return count


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=3,
    name="documents.generate_invoice_from_schedule",
    acks_late=True,
)
def generate_invoice_from_schedule(self, schedule_id: str) -> str:
    """
    Create a new Invoice from a RecurringInvoice template, then:
      • Computes totals
      • Advances the schedule's next_invoice_date
      • Optionally sends the email (if schedule.auto_send is True)

    Returns the new invoice's UUID string.
    """
    from .models import (
        ActivityAction,
        Invoice,
        InvoiceStatus,
        LineItem,
        RecurringInvoice,
    )

    try:
        schedule = (
            RecurringInvoice.objects
            .select_related("company", "template", "created_by")
            .get(pk=schedule_id)
        )
    except RecurringInvoice.DoesNotExist:
        logger.error("[RECURRING] Schedule not found: %s", schedule_id)
        return ""

    if not schedule.is_active:
        logger.info("[RECURRING] Schedule %s is inactive — skipping", schedule_id)
        return ""

    template = schedule.template
    company  = schedule.company

    try:
        new_invoice = Invoice(
            company           = company,
            client            = template.client,
            client_salutation = template.client_salutation,
            client_name       = template.client_name,
            client_email      = template.client_email,
            client_phone      = template.client_phone,
            client_address    = template.client_address,
            client_vat_number = template.client_vat_number,
            currency          = template.currency,
            subject           = template.subject,
            notes             = template.notes,
            terms             = template.terms,
            status            = InvoiceStatus.DRAFT,
            issue_date        = timezone.localdate(),
            due_date          = timezone.localdate() + datetime.timedelta(days=30),
            created_by        = schedule.created_by,
        )
        new_invoice.number = company.get_next_invoice_number()
        new_invoice.save()

        # Clone line items from template
        for item in template.line_items.all():
            LineItem.objects.create(
                invoice          = new_invoice,
                item_type        = item.item_type,
                description      = item.description,
                quantity         = item.quantity,
                unit_of_measure  = item.unit_of_measure,
                unit_label       = item.unit_label,
                unit_price       = item.unit_price,
                discount_percent = item.discount_percent,
                tax_rate         = item.tax_rate,
                sort_order       = item.sort_order,
            )

        new_invoice.compute_totals(save=True)

        # Log creation
        try:
            new_invoice.log_activity(
                ActivityAction.CREATED,
                note=f"Auto-generated from recurring schedule {schedule_id}",
                metadata={"schedule_id": schedule_id},
            )
        except Exception:
            pass

    except Exception as exc:
        logger.exception("[RECURRING] Invoice creation failed for schedule %s: %s", schedule_id, exc)
        _capture_exception(exc)
        raise self.retry(exc=exc)

    # Advance the schedule — this also deactivates if end conditions are met
    try:
        schedule.advance_next_date()
    except Exception as exc:
        logger.warning("[RECURRING] Failed to advance schedule %s: %s", schedule_id, exc)

    # Auto-send
    if schedule.auto_send and new_invoice.client_email:
        new_invoice.mark_sent()
        send_document_email_task.delay("invoice", str(new_invoice.pk))

    logger.info(
        "[RECURRING] Created invoice %s from schedule %s (next: %s)",
        new_invoice.number, schedule_id, schedule.next_invoice_date,
    )
    return str(new_invoice.pk)


# ===========================================================================
# 6. AI REVIEW STUB
# ===========================================================================

@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=2,
    name="documents.run_contract_ai_review",
)
def run_contract_ai_review(self, contract_id: str) -> None:
    """
    Stub task — delegates to ai.tasks.run_contract_ai_review.
    The real implementation lives in the ai/ app to keep separation of concerns.
    """
    try:
        from ai.tasks import run_contract_ai_review as _ai_task
        _ai_task.delay(contract_id)
        logger.info("[AI] Delegated contract review to ai.tasks for %s", contract_id)
    except ImportError:
        logger.warning(
            "[AI] ai.tasks not available — cannot review contract %s. "
            "Enable the ai/ app and configure ANTHROPIC_API_KEY.",
            contract_id,
        )
    except Exception as exc:
        logger.exception("[AI] Failed to queue review for %s: %s", contract_id, exc)
        _capture_exception(exc)
        raise self.retry(exc=exc)


# ===========================================================================
# 7. HOUSEKEEPING
# ===========================================================================

@shared_task(name="documents.cleanup_document_versions")
def cleanup_old_document_versions(keep_per_doc: int = 10) -> int:
    """
    Celery Beat task: run weekly on Sunday at 03:00.
    Removes old DocumentVersion snapshots, keeping the most recent N per document.
    Returns count of versions deleted.
    """
    from .models import DocumentVersion

    deleted_total = 0

    # Get all unique (doc_type, doc_id) pairs that have more than keep_per_doc versions
    from django.db.models import Count
    oversize = (
        DocumentVersion.objects
        .values("doc_type", "doc_id")
        .annotate(cnt=Count("id"))
        .filter(cnt__gt=keep_per_doc)
    )

    for row in oversize:
        # Keep the latest `keep_per_doc`, delete the rest
        to_keep = (
            DocumentVersion.objects
            .filter(doc_type=row["doc_type"], doc_id=row["doc_id"])
            .order_by("-version")
            .values_list("id", flat=True)[:keep_per_doc]
        )
        deleted, _ = (
            DocumentVersion.objects
            .filter(doc_type=row["doc_type"], doc_id=row["doc_id"])
            .exclude(id__in=list(to_keep))
            .delete()
        )
        deleted_total += deleted

    logger.info("[CLEANUP] Deleted %d old document versions", deleted_total)
    return deleted_total


@shared_task(name="documents.cleanup_orphaned_files")
def cleanup_orphaned_files() -> int:
    """
    Optional housekeeping: finds pdf_file / docx_file fields pointing
    to S3 keys that no longer exist and clears the field.
    Runs separately — only use if you see stale file references.
    """
    from .models import Invoice, Quotation, Contract

    cleared = 0
    for Model in (Invoice, Quotation, Contract):
        for obj in Model.objects.exclude(pdf_file="").exclude(pdf_file__isnull=True):
            try:
                obj.pdf_file.url  # triggers storage existence check
            except Exception:
                obj.pdf_file = None
                obj.save(update_fields=["pdf_file"])
                cleared += 1
        for obj in Model.objects.exclude(docx_file="").exclude(docx_file__isnull=True):
            try:
                obj.docx_file.url
            except Exception:
                obj.docx_file = None
                obj.save(update_fields=["docx_file"])
                cleared += 1

    logger.info("[CLEANUP] Cleared %d orphaned file references", cleared)
    return cleared