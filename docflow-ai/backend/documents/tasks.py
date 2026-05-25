"""Documents Celery tasks — PDF generation, email, reminders (FIXED)"""

import logging
from decimal import Decimal
from typing import Dict, Any

from celery import shared_task
from django.template.loader import render_to_string
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from django.utils import timezone
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


# =========================================================
# PDF GENERATION - FIXED
# =========================================================

@shared_task(bind=True, max_retries=3, autoretry_for=(Exception,))
def generate_invoice_pdf(self, invoice_id: str) -> Dict[str, Any]:
    """
    Generate PDF for an invoice and store it.

    FIXED:
    - Proper error handling
    - Exponential backoff for retries
    - Better S3 error handling
    - Logging improvements
    """
    try:
        from .models import Invoice

        try:
            invoice = Invoice.objects.select_related(
                "company",
                "client"
            ).prefetch_related("line_items").get(
                id=invoice_id,
                is_deleted=False
            )
        except Invoice.DoesNotExist:
            logger.error(f"Invoice {invoice_id} not found")
            return {"status": "error", "reason": "Invoice not found"}

        # Render HTML template
        html = render_to_string("invoices/invoice_pdf.html", {
            "invoice": invoice,
            "company": invoice.company,
            "client": invoice.client,
            "line_items": invoice.line_items.all(),
        })

        # Convert HTML to PDF
        try:
            from weasyprint import HTML as WeasyHTML, CSS

            pdf_bytes = WeasyHTML(
                string=html,
                base_url=settings.FRONTEND_URL
            ).write_pdf()

        except ImportError:
            logger.error("WeasyPrint not available")
            return {"status": "error", "reason": "WeasyPrint not installed"}
        except Exception as e:
            logger.error(f"PDF rendering failed for invoice {invoice_id}: {e}")
            raise

        filename = f"invoices/{invoice.company.id}/{invoice.number}.pdf"

        # Store in S3 or local storage
        if settings.DEFAULT_FILE_STORAGE == "storages.backends.s3boto3.S3Boto3Storage":
            try:
                import boto3

                s3 = boto3.client("s3")
                s3.put_object(
                    Bucket=settings.AWS_STORAGE_BUCKET_NAME,
                    Key=filename,
                    Body=pdf_bytes,
                    ContentType="application/pdf",
                    ServerSideEncryption="AES256",  # Encrypt in transit
                )

                logger.info(f"PDF uploaded to S3 for invoice {invoice.number}")

            except ClientError as e:
                logger.error(f"S3 upload failed for {invoice_id}: {e}")
                # Exponential backoff: 60s, 120s, 240s
                countdown = 2 ** self.request.retries * 60
                raise self.retry(exc=e, countdown=countdown)

            except Exception as e:
                logger.error(f"Unexpected error uploading to S3: {e}")
                countdown = 2 ** self.request.retries * 60
                raise self.retry(exc=e, countdown=countdown)
        else:
            # Local storage
            try:
                from django.core.files.base import ContentFile
                invoice.pdf_file.save(
                    f"{invoice.number}.pdf",
                    ContentFile(pdf_bytes),
                    save=False
                )
            except Exception as e:
                logger.error(f"Local file save failed for {invoice_id}: {e}")
                countdown = 2 ** self.request.retries * 60
                raise self.retry(exc=e, countdown=countdown)

        # Update invoice record
        invoice.pdf_file = filename
        invoice.save(update_fields=["pdf_file"])

        logger.info(
            "Invoice PDF generated",
            extra={
                "invoice_id": str(invoice.id),
                "invoice_number": invoice.number,
                "file_size_kb": len(pdf_bytes) / 1024,
            }
        )

        return {
            "status": "success",
            "invoice_id": str(invoice_id),
            "file_size": len(pdf_bytes),
        }

    except Exception as exc:
        logger.error(f"PDF generation failed for {invoice_id}: {exc}", exc_info=True)
        countdown = 2 ** self.request.retries * 60
        raise self.retry(exc=exc, countdown=countdown)


# =========================================================
# EMAIL SENDING - FIXED
# =========================================================

@shared_task(bind=True, max_retries=3, autoretry_for=(Exception,))
def send_invoice_email(self, invoice_id: str) -> Dict[str, Any]:
    """
    Send invoice email to client.

    FIXED:
    - Comprehensive validation
    - Better error handling
    - Exponential backoff
    - Proper logging
    """
    try:
        from .models import Invoice

        try:
            invoice = Invoice.objects.select_related(
                "company",
                "client"
            ).get(id=invoice_id, is_deleted=False)
        except Invoice.DoesNotExist:
            logger.error(f"Invoice {invoice_id} not found")
            return {"status": "error", "reason": "Invoice not found"}

        # Validate client
        if not invoice.client:
            logger.warning(f"Invoice {invoice_id} has no client")
            return {"status": "skipped", "reason": "no client assigned"}

        if not invoice.client.email:
            logger.warning(f"Client {invoice.client.id} has no email")
            return {"status": "skipped", "reason": "no client email"}

        # Validate company
        if not invoice.company.email:
            logger.error(f"Company {invoice.company.id} has no email configured")
            return {
                "status": "error",
                "reason": "company email not configured"
            }

        # Generate portal URL
        portal_url = f"{settings.FRONTEND_URL}/portal/{invoice.id}"
        try:
            from documents.services.portal_security import generate_signed_token
            token = generate_signed_token(invoice.id, expires_in=86400 * 7)  # 7 days
            portal_url = f"{portal_url}?token={token}"
        except Exception as e:
            logger.error(f"Failed to generate token for invoice {invoice_id}: {e}")
            # Continue with unsigned URL
            pass

        # Render email template
        subject = f"Invoice {invoice.number} from {invoice.company.name}"

        try:
            html_body = render_to_string("emails/invoice_sent.html", {
                "invoice": invoice,
                "company": invoice.company,
                "client": invoice.client,
                "portal_url": portal_url,
            })
        except Exception as e:
            logger.error(f"Failed to render invoice email template: {e}")
            countdown = 2 ** self.request.retries * 60
            raise self.retry(exc=e, countdown=countdown)

        text_body = f"""
Dear {invoice.client.name},

Thank you for your business. Please find your invoice {invoice.number} attached.

Amount Due: {invoice.total_amount} {invoice.currency}
Due Date: {invoice.due_date}

View and pay online: {portal_url}

Thank you!
{invoice.company.name}
        """.strip()

        # Send email
        try:
            msg = EmailMultiAlternatives(
                subject=subject,
                body=text_body,
                from_email=invoice.company.email,
                to=[invoice.client.email],
                reply_to=[invoice.company.email],
            )
            msg.attach_alternative(html_body, "text/html")
            msg.send()

            logger.info(
                "Invoice email sent",
                extra={
                    "invoice_id": str(invoice.id),
                    "invoice_number": invoice.number,
                    "client_email": invoice.client.email,
                }
            )

            return {"status": "sent"}

        except Exception as e:
            logger.error(
                f"Email send failed for invoice {invoice_id}: {e}",
                exc_info=True
            )
            countdown = 2 ** self.request.retries * 120  # Longer backoff for email
            raise self.retry(exc=e, countdown=countdown)

    except Exception as exc:
        logger.error(f"Email task failed for {invoice_id}: {exc}", exc_info=True)
        countdown = 2 ** self.request.retries * 120
        raise self.retry(exc=exc, countdown=countdown)


# =========================================================
# PAYMENT REMINDERS - FIXED
# =========================================================

@shared_task
def send_payment_reminder(invoice_id: str) -> Dict[str, Any]:
    """Send payment reminder for overdue invoices."""
    try:
        from .models import Invoice

        try:
            invoice = Invoice.objects.select_related(
                "company",
                "client"
            ).get(id=invoice_id, is_deleted=False)
        except Invoice.DoesNotExist:
            logger.error(f"Invoice {invoice_id} not found")
            return {"status": "error"}

        # Only send reminders for invoices in certain statuses
        if invoice.status not in [
            Invoice.Status.SENT,
            Invoice.Status.VIEWED,
            Invoice.Status.OVERDUE
        ]:
            return {"status": "skipped", "reason": "invalid status"}

        # Check if actually overdue
        if not invoice.due_date or invoice.due_date >= timezone.now().date():
            return {"status": "skipped", "reason": "not overdue"}

        # Mark as overdue if not already
        if invoice.status != Invoice.Status.OVERDUE:
            invoice.status = Invoice.Status.OVERDUE
            invoice.save(update_fields=["status"])

        # Send email
        if not invoice.client or not invoice.client.email:
            logger.warning(f"Cannot send reminder for invoice {invoice_id}: no client email")
            return {"status": "skipped"}

        if not invoice.company.email:
            logger.error(f"Cannot send reminder: company {invoice.company.id} has no email")
            return {"status": "error"}

        portal_url = f"{settings.FRONTEND_URL}/portal/{invoice.id}"
        subject = f"REMINDER: Invoice {invoice.number} is overdue"
        text_body = f"""
Dear {invoice.client.name},

This is a friendly reminder that invoice {invoice.number} for {invoice.total_amount} {invoice.currency} is now overdue.

Due date was: {invoice.due_date}

Please make payment at your earliest convenience: {portal_url}

If you have already paid, please disregard this notice.

Thank you,
{invoice.company.name}
        """.strip()

        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=invoice.company.email,
            to=[invoice.client.email],
        )
        msg.send()

        logger.info(f"Payment reminder sent for invoice {invoice.number}")
        return {"status": "reminder_sent"}

    except Exception as e:
        logger.error(f"Payment reminder failed for {invoice_id}: {e}", exc_info=True)
        return {"status": "error", "detail": str(e)}


# =========================================================
# CONTRACT PDF GENERATION - FIXED
# =========================================================

@shared_task(bind=True, max_retries=3)
def generate_contract_pdf(self, contract_id: str) -> Dict[str, Any]:
    """Generate PDF for a contract."""
    try:
        from .models import Contract

        try:
            contract = Contract.objects.select_related(
                "company",
                "client"
            ).get(id=contract_id)
        except Contract.DoesNotExist:
            logger.error(f"Contract {contract_id} not found")
            return {"status": "error", "reason": "Contract not found"}

        html = render_to_string("contracts/contract_pdf.html", {
            "contract": contract,
            "company": contract.company,
            "client": contract.client,
        })

        try:
            from weasyprint import HTML as WeasyHTML
            pdf_bytes = WeasyHTML(
                string=html,
                base_url=settings.FRONTEND_URL
            ).write_pdf()
        except ImportError:
            logger.error("WeasyPrint not available")
            return {"status": "error", "reason": "WeasyPrint not installed"}

        try:
            from django.core.files.base import ContentFile
            contract.pdf_file.save(
                f"contract_{contract.id}.pdf",
                ContentFile(pdf_bytes),
                save=False
            )
            contract.save(update_fields=["pdf_file"])

            logger.info(f"Contract PDF generated for {contract.id}")
            return {"status": "success", "contract_id": str(contract_id)}

        except Exception as e:
            logger.error(f"Failed to save contract PDF: {e}")
            countdown = 2 ** self.request.retries * 60
            raise self.retry(exc=e, countdown=countdown)

    except Exception as exc:
        logger.error(f"Contract PDF generation failed: {exc}", exc_info=True)
        return {"status": "error", "detail": str(exc)}


# =========================================================
# SCHEDULED TASKS
# =========================================================

@shared_task
def check_overdue_invoices() -> Dict[str, Any]:
    """Scheduled task: flag overdue invoices and send reminders."""
    try:
        from .models import Invoice

        overdue = Invoice.objects.filter(
            status__in=[
                Invoice.Status.SENT,
                Invoice.Status.VIEWED
            ],
            due_date__lt=timezone.now().date(),
            is_deleted=False
        )

        overdue_count = 0
        reminder_count = 0

        for invoice in overdue:
            try:
                invoice.status = Invoice.Status.OVERDUE
                invoice.save(update_fields=["status"])
                overdue_count += 1

                if invoice.client and invoice.client.email:
                    send_payment_reminder.delay(str(invoice.id))
                    reminder_count += 1
            except Exception as e:
                logger.error(f"Failed to process overdue invoice {invoice.id}: {e}")

        logger.info(
            "Overdue invoice check completed",
            extra={
                "overdue_count": overdue_count,
                "reminders_sent": reminder_count,
            }
        )

        return {
            "status": "success",
            "overdue_count": overdue_count,
            "reminders_sent": reminder_count,
        }

    except Exception as e:
        logger.error(f"Overdue invoice check failed: {e}", exc_info=True)
        return {"status": "error", "detail": str(e)}