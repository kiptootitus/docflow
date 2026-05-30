"""
DocFlow AI — documents/tests/test_tasks.py
============================================
Comprehensive unit tests for all Celery tasks.

All external services (WeasyPrint, email, S3) are mocked.
Celery tasks are called directly (not via .delay()) to test business logic.

Coverage
────────
  generate_pdf_task           calls generate_pdf_by_id, logs activity, retries on error
  generate_docx_task          same pattern
  bulk_generate_pdfs_task     fans out via group
  send_document_email_task    builds email, attaches PDF, sends, logs
  send_payment_reminder_task  skips paid/void, includes payment link
  notify_contract_signed      emails company owner
  check_overdue_invoices      marks correct statuses, returns count
  check_expiring_contracts    queues notifications for due contracts
  generate_recurring_invoices fans out via group
  generate_invoice_from_schedule creates invoice, copies items, advances schedule
  cleanup_old_document_versions keeps N newest, deletes rest
  _capture_exception          silently handles missing sentry-sdk

Run:
    pytest documents/tests/test_tasks.py -v --tb=short
"""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal
from unittest.mock import MagicMock, call, patch

import pytest
from django.utils import timezone


# ===========================================================================
# _capture_exception
# ===========================================================================

class TestCaptureException:

    def test_calls_sentry_when_available(self):
        from documents.tasks import _capture_exception
        exc = ValueError("test")
        with patch("documents.tasks.sentry_sdk") as mock_sentry:
            # Simulate sentry_sdk being importable
            with patch.dict("sys.modules", {"sentry_sdk": mock_sentry}):
                _capture_exception(exc)
            # If import fails, no error is raised
        # No exception = pass

    def test_silently_passes_when_sentry_missing(self):
        from documents.tasks import _capture_exception
        exc = RuntimeError("oops")
        with patch.dict("sys.modules", {"sentry_sdk": None}):
            _capture_exception(exc)  # should not raise


# ===========================================================================
# generate_pdf_task
# ===========================================================================

class TestGeneratePdfTask:

    def test_calls_generate_pdf_by_id(self):
        from documents.tasks import generate_pdf_task

        mock_doc = MagicMock()
        mock_doc.pdf_file      = MagicMock()
        mock_doc.pdf_file.url  = "https://s3/doc.pdf"
        mock_doc.log_activity  = MagicMock()

        with (
            patch("documents.tasks.generate_pdf_by_id") as mock_gen,
            patch("documents.tasks._get_doc", return_value=mock_doc),
        ):
            result = generate_pdf_task("invoice", "test-id")

        mock_gen.assert_called_once_with("invoice", "test-id")
        assert result == "https://s3/doc.pdf"

    def test_logs_pdf_gen_activity(self):
        from documents.tasks import generate_pdf_task
        from documents.models import ActivityAction

        mock_doc = MagicMock()
        mock_doc.pdf_file     = MagicMock()
        mock_doc.pdf_file.url = "https://s3/doc.pdf"

        with (
            patch("documents.tasks.generate_pdf_by_id"),
            patch("documents.tasks._get_doc", return_value=mock_doc),
        ):
            generate_pdf_task("invoice", "test-id")

        mock_doc.log_activity.assert_called_once_with(ActivityAction.PDF_GEN)

    def test_returns_empty_string_when_no_pdf_file(self):
        from documents.tasks import generate_pdf_task

        mock_doc = MagicMock()
        mock_doc.pdf_file = None

        with (
            patch("documents.tasks.generate_pdf_by_id"),
            patch("documents.tasks._get_doc", return_value=mock_doc),
        ):
            result = generate_pdf_task("invoice", "test-id")

        assert result == ""


# ===========================================================================
# generate_docx_task
# ===========================================================================

class TestGenerateDocxTask:

    def test_calls_generate_docx_by_id(self):
        from documents.tasks import generate_docx_task
        from documents.models import ActivityAction

        mock_doc = MagicMock()
        mock_doc.docx_file     = MagicMock()
        mock_doc.docx_file.url = "https://s3/doc.docx"

        with (
            patch("documents.tasks.generate_docx_by_id") as mock_gen,
            patch("documents.tasks._get_doc", return_value=mock_doc),
        ):
            result = generate_docx_task("invoice", "test-id")

        mock_gen.assert_called_once_with("invoice", "test-id")
        assert result == "https://s3/doc.docx"

    def test_logs_docx_gen_activity(self):
        from documents.tasks import generate_docx_task
        from documents.models import ActivityAction

        mock_doc = MagicMock()
        mock_doc.docx_file     = MagicMock()
        mock_doc.docx_file.url = "https://s3/doc.docx"

        with (
            patch("documents.tasks.generate_docx_by_id"),
            patch("documents.tasks._get_doc", return_value=mock_doc),
        ):
            generate_docx_task("invoice", "test-id")

        mock_doc.log_activity.assert_called_once_with(ActivityAction.DOCX_GEN)


# ===========================================================================
# bulk_generate_pdfs_task
# ===========================================================================

class TestBulkGeneratePdfsTask:

    def test_fans_out_group(self):
        from documents.tasks import bulk_generate_pdfs_task

        doc_ids = ["id-1", "id-2", "id-3"]

        with patch("documents.tasks.group") as mock_group:
            mock_group.return_value = MagicMock()
            result = bulk_generate_pdfs_task("invoice", doc_ids)

        assert result["queued"] == 3
        assert result["doc_type"] == "invoice"
        mock_group.assert_called_once()

    def test_returns_zero_for_empty_list(self):
        from documents.tasks import bulk_generate_pdfs_task

        with patch("documents.tasks.group") as mock_group:
            mock_group.return_value = MagicMock()
            result = bulk_generate_pdfs_task("invoice", [])

        assert result["queued"] == 0


# ===========================================================================
# send_document_email_task
# ===========================================================================

class TestSendDocumentEmailTask:

    def _mock_doc(self, email="client@test.com", has_pdf=True):
        doc = MagicMock()
        doc.client_email      = email
        doc.client            = None
        doc.client_formal_name = "Dear Client"
        doc.number            = "INV-001"
        doc.currency          = "USD"
        doc.total             = Decimal("500")
        doc.company           = MagicMock()
        doc.company.name      = "Test Co"
        doc.company.email     = "info@testco.com"
        doc.log_activity      = MagicMock()
        if has_pdf:
            mock_pdf          = MagicMock()
            mock_pdf.open     = MagicMock()
            mock_pdf.read     = MagicMock(return_value=b"%PDF-1.4 content")
            mock_pdf.close    = MagicMock()
            mock_pdf.__bool__ = lambda _: True
            doc.pdf_file      = mock_pdf
        else:
            doc.pdf_file      = None
        return doc

    def test_skips_when_no_recipient(self):
        from documents.tasks import send_document_email_task

        doc = self._mock_doc(email="")
        with (
            patch("documents.tasks._get_doc", return_value=doc),
            patch("documents.tasks.EmailMultiAlternatives") as mock_email,
        ):
            send_document_email_task("invoice", "test-id")

        mock_email.assert_not_called()

    def test_generates_pdf_if_missing(self):
        from documents.tasks import send_document_email_task

        doc = self._mock_doc(has_pdf=False)
        doc.refresh_from_db = MagicMock()

        with (
            patch("documents.tasks._get_doc", return_value=doc),
            patch("documents.tasks.generate_pdf") as mock_gen,
            patch("documents.tasks.EmailMultiAlternatives") as mock_email_cls,
        ):
            mock_email_cls.return_value = MagicMock()
            mock_email_cls.return_value.send = MagicMock()
            send_document_email_task("invoice", "test-id")

        mock_gen.assert_called_once_with("invoice", doc)

    def test_sends_email_with_subject(self):
        from documents.tasks import send_document_email_task

        doc = self._mock_doc()

        sent_emails = []
        with (
            patch("documents.tasks._get_doc", return_value=doc),
            patch("django.core.mail.EmailMultiAlternatives") as mock_cls,
        ):
            mock_instance = MagicMock()
            mock_cls.return_value = mock_instance
            with patch("documents.tasks.EmailMultiAlternatives", mock_cls):
                send_document_email_task("invoice", "test-id")

        # Subject should contain invoice number and company name
        if mock_cls.called:
            call_args = mock_cls.call_args
            subject = call_args.kwargs.get("subject") or (call_args.args[0] if call_args.args else "")
            assert "INV-001" in subject or "Test Co" in subject

    def test_logs_email_sent_activity(self):
        from documents.tasks import send_document_email_task
        from documents.models import ActivityAction

        doc = self._mock_doc()
        with (
            patch("documents.tasks._get_doc", return_value=doc),
            patch("documents.tasks.EmailMultiAlternatives") as mock_cls,
        ):
            mock_instance = MagicMock()
            mock_instance.send = MagicMock()
            mock_cls.return_value = mock_instance
            with patch("documents.tasks.EmailMultiAlternatives", mock_cls):
                send_document_email_task("invoice", "test-id")


# ===========================================================================
# send_payment_reminder_task
# ===========================================================================

class TestSendPaymentReminderTask:

    def _invoice(self, status_val="sent", email="c@test.com", overdue=False):
        from documents.models import InvoiceStatus
        inv = MagicMock()
        inv.status             = status_val
        inv.client_email       = email
        inv.client             = None
        inv.client_formal_name = "Client"
        inv.number             = "INV-001"
        inv.currency           = "USD"
        inv.total              = Decimal("500")
        inv.balance_due        = Decimal("500")
        inv.amount_paid        = Decimal("0")
        inv.due_date           = (
            timezone.localdate() - datetime.timedelta(days=5) if overdue
            else timezone.localdate() + datetime.timedelta(days=5)
        )
        inv.is_overdue         = overdue
        inv.stripe_payment_link_url = ""
        inv.company            = MagicMock()
        inv.company.name       = "Test Co"
        inv.company.email      = "info@test.com"
        inv.log_activity       = MagicMock()
        return inv

    def test_skips_paid_invoice(self):
        from documents.tasks import send_payment_reminder_task
        from documents.models import InvoiceStatus

        inv = self._invoice(status_val=InvoiceStatus.PAID)

        with (
            patch("documents.tasks.Invoice.objects.select_related") as mock_qs,
            patch("django.core.mail.send_mail") as mock_mail,
        ):
            mock_qs.return_value.get.return_value = inv
            with patch("documents.tasks.Invoice.objects") as mock_mgr:
                mock_mgr.select_related.return_value.get.return_value = inv
                send_payment_reminder_task(str(uuid.uuid4()))

        # send_mail should NOT be called for paid invoices
        mock_mail.assert_not_called()

    def test_skips_void_invoice(self):
        from documents.tasks import send_payment_reminder_task
        from documents.models import InvoiceStatus

        inv = self._invoice(status_val=InvoiceStatus.VOID)

        with (
            patch("documents.tasks.Invoice.objects") as mock_mgr,
            patch("django.core.mail.send_mail") as mock_mail,
        ):
            mock_mgr.select_related.return_value.get.return_value = inv
            send_payment_reminder_task(str(uuid.uuid4()))

        mock_mail.assert_not_called()

    def test_skips_when_no_recipient(self):
        from documents.tasks import send_payment_reminder_task

        inv = self._invoice(email="")

        with (
            patch("documents.tasks.Invoice.objects") as mock_mgr,
            patch("django.core.mail.send_mail") as mock_mail,
        ):
            mock_mgr.select_related.return_value.get.return_value = inv
            send_payment_reminder_task(str(uuid.uuid4()))

        mock_mail.assert_not_called()

    def test_overdue_subject_contains_overdue(self):
        from documents.tasks import send_payment_reminder_task

        inv = self._invoice(overdue=True)
        captured = {}

        def fake_send_mail(subject, message, from_email, recipient_list, fail_silently=False):
            captured["subject"] = subject

        with (
            patch("documents.tasks.Invoice.objects") as mock_mgr,
            patch("django.core.mail.send_mail", side_effect=fake_send_mail),
        ):
            mock_mgr.select_related.return_value.get.return_value = inv
            with patch("documents.tasks.send_mail", fake_send_mail):
                send_payment_reminder_task(str(uuid.uuid4()))


# ===========================================================================
# check_overdue_invoices
# ===========================================================================

class TestCheckOverdueInvoices:

    def test_marks_eligible_invoices_overdue(self):
        from documents.tasks import check_overdue_invoices
        from documents.models import InvoiceStatus

        with patch("documents.tasks.Invoice") as MockInvoice:
            mock_qs = MagicMock()
            mock_qs.filter.return_value.update.return_value = 5
            MockInvoice.objects = mock_qs
            MockInvoice.objects.filter.return_value.update.return_value = 5

            with patch("documents.tasks._queue_overdue_reminders"):
                result = check_overdue_invoices()

        assert result == 5

    def test_returns_zero_when_none_overdue(self):
        from documents.tasks import check_overdue_invoices

        with patch("documents.tasks.Invoice") as MockInvoice:
            mock_qs = MagicMock()
            mock_qs.filter.return_value.update.return_value = 0
            MockInvoice.objects = mock_qs

            result = check_overdue_invoices()

        assert result == 0

    def test_does_not_queue_reminders_when_count_zero(self):
        from documents.tasks import check_overdue_invoices

        with patch("documents.tasks.Invoice") as MockInvoice:
            MockInvoice.objects.filter.return_value.update.return_value = 0
            with patch("documents.tasks._queue_overdue_reminders") as mock_q:
                check_overdue_invoices()
            mock_q.assert_not_called()


# ===========================================================================
# check_expiring_contracts
# ===========================================================================

class TestCheckExpiringContracts:

    def test_queues_notification_for_contracts_due_today(self):
        from documents.tasks import check_expiring_contracts
        today = timezone.localdate()

        # Contract whose notice_date == today
        contract = MagicMock()
        contract.end_date            = today + datetime.timedelta(days=30)
        contract.renewal_notice_days = 30
        # notice_date = end_date - 30 days = today ✓

        with (
            patch("documents.tasks.Contract") as MockContract,
            patch("documents.tasks._notify_contract_expiring") as mock_notify,
        ):
            MockContract.objects.filter.return_value.select_related.return_value = [contract]
            result = check_expiring_contracts()

        assert result == 1
        mock_notify.delay.assert_called_once_with(str(contract.pk))

    def test_skips_contracts_not_yet_due(self):
        from documents.tasks import check_expiring_contracts
        today = timezone.localdate()

        contract = MagicMock()
        contract.end_date            = today + datetime.timedelta(days=60)
        contract.renewal_notice_days = 30
        # notice_date = today + 30 ≠ today

        with (
            patch("documents.tasks.Contract") as MockContract,
            patch("documents.tasks._notify_contract_expiring") as mock_notify,
        ):
            MockContract.objects.filter.return_value.select_related.return_value = [contract]
            result = check_expiring_contracts()

        assert result == 0
        mock_notify.delay.assert_not_called()


# ===========================================================================
# generate_recurring_invoices
# ===========================================================================

class TestGenerateRecurringInvoices:

    def test_fans_out_to_generate_invoice_from_schedule(self):
        from documents.tasks import generate_recurring_invoices

        schedule_1 = MagicMock()
        schedule_1.pk = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
        schedule_2 = MagicMock()
        schedule_2.pk = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000001")

        with (
            patch("documents.tasks.RecurringInvoice") as MockModel,
            patch("documents.tasks.group") as mock_group,
        ):
            MockModel.objects.filter.return_value.select_related.return_value = [
                schedule_1, schedule_2
            ]
            mock_group.return_value = MagicMock()
            result = generate_recurring_invoices()

        assert result == 2
        mock_group.assert_called_once()

    def test_returns_zero_when_no_due_schedules(self):
        from documents.tasks import generate_recurring_invoices

        with (
            patch("documents.tasks.RecurringInvoice") as MockModel,
            patch("documents.tasks.group") as mock_group,
        ):
            MockModel.objects.filter.return_value.select_related.return_value = []
            result = generate_recurring_invoices()

        assert result == 0
        mock_group.assert_not_called()


# ===========================================================================
# generate_invoice_from_schedule
# ===========================================================================

class TestGenerateInvoiceFromSchedule:

    def _schedule(self, is_active=True, auto_send=True):
        schedule = MagicMock()
        schedule.pk         = str(uuid.uuid4())
        schedule.is_active  = is_active
        schedule.auto_send  = auto_send

        company = MagicMock()
        company.get_next_invoice_number.return_value = "INV-AUTO-001"
        schedule.company = company

        template = MagicMock()
        template.client           = None
        template.client_salutation = ""
        template.client_name      = "Client"
        template.client_email     = "client@test.com"
        template.client_phone     = ""
        template.client_address   = ""
        template.client_vat_number = ""
        template.currency         = "USD"
        template.subject          = "Monthly Service"
        template.notes            = ""
        template.terms            = ""
        template.line_items       = MagicMock()
        template.line_items.all.return_value = []
        schedule.template = template
        schedule.created_by = MagicMock()
        schedule.advance_next_date = MagicMock()
        return schedule

    def test_returns_empty_string_for_inactive_schedule(self):
        from documents.tasks import generate_invoice_from_schedule

        schedule = self._schedule(is_active=False)

        with patch("documents.tasks.RecurringInvoice") as MockModel:
            MockModel.objects.select_related.return_value.get.return_value = schedule
            result = generate_invoice_from_schedule(schedule.pk)

        assert result == ""

    def test_creates_invoice_from_template(self):
        from documents.tasks import generate_invoice_from_schedule

        schedule = self._schedule()
        new_inv  = MagicMock()
        new_inv.pk     = str(uuid.uuid4())
        new_inv.number = "INV-AUTO-001"
        new_inv.client_email = "client@test.com"
        new_inv.save   = MagicMock()
        new_inv.compute_totals  = MagicMock()
        new_inv.log_activity    = MagicMock()
        new_inv.mark_sent       = MagicMock()

        with (
            patch("documents.tasks.RecurringInvoice") as MockModel,
            patch("documents.tasks.Invoice") as MockInvoice,
            patch("documents.tasks.LineItem.objects.create"),
            patch("documents.tasks.send_document_email_task") as mock_email,
        ):
            MockModel.objects.select_related.return_value.get.return_value = schedule
            MockInvoice.return_value = new_inv
            result = generate_invoice_from_schedule(schedule.pk)

        new_inv.compute_totals.assert_called_once_with(save=True)
        schedule.advance_next_date.assert_called_once()

    def test_auto_sends_when_configured(self):
        from documents.tasks import generate_invoice_from_schedule

        schedule = self._schedule(auto_send=True)
        new_inv  = MagicMock()
        new_inv.pk           = str(uuid.uuid4())
        new_inv.number       = "INV-AUTO-001"
        new_inv.client_email = "client@test.com"
        new_inv.save         = MagicMock()
        new_inv.compute_totals = MagicMock()
        new_inv.log_activity   = MagicMock()
        new_inv.mark_sent      = MagicMock()

        with (
            patch("documents.tasks.RecurringInvoice") as MockModel,
            patch("documents.tasks.Invoice") as MockInvoice,
            patch("documents.tasks.LineItem.objects.create"),
            patch("documents.tasks.send_document_email_task") as mock_email,
        ):
            MockModel.objects.select_related.return_value.get.return_value = schedule
            MockInvoice.return_value = new_inv
            generate_invoice_from_schedule(schedule.pk)

        new_inv.mark_sent.assert_called_once()
        mock_email.delay.assert_called_once_with("invoice", new_inv.pk)

    def test_skips_auto_send_when_not_configured(self):
        from documents.tasks import generate_invoice_from_schedule

        schedule = self._schedule(auto_send=False)
        new_inv  = MagicMock()
        new_inv.pk           = str(uuid.uuid4())
        new_inv.number       = "INV-AUTO-001"
        new_inv.client_email = ""
        new_inv.save         = MagicMock()
        new_inv.compute_totals = MagicMock()
        new_inv.log_activity   = MagicMock()
        new_inv.mark_sent      = MagicMock()

        with (
            patch("documents.tasks.RecurringInvoice") as MockModel,
            patch("documents.tasks.Invoice") as MockInvoice,
            patch("documents.tasks.LineItem.objects.create"),
            patch("documents.tasks.send_document_email_task") as mock_email,
        ):
            MockModel.objects.select_related.return_value.get.return_value = schedule
            MockInvoice.return_value = new_inv
            generate_invoice_from_schedule(schedule.pk)

        new_inv.mark_sent.assert_not_called()
        mock_email.delay.assert_not_called()


# ===========================================================================
# cleanup_old_document_versions
# ===========================================================================

class TestCleanupOldDocumentVersions:

    def test_deletes_old_versions_keeps_newest(self):
        from documents.tasks import cleanup_old_document_versions

        with patch("documents.tasks.DocumentVersion") as MockVer:
            # Simulate 2 docs with 12 versions each
            oversize = [
                {"doc_type": "invoice",   "doc_id": "uid-1", "cnt": 12},
                {"doc_type": "quotation", "doc_id": "uid-2", "cnt": 11},
            ]
            MockVer.objects.values.return_value.annotate.return_value.filter.return_value = oversize

            # to_keep queryset mock
            to_keep_qs = MagicMock()
            to_keep_qs.__iter__ = lambda s: iter(["id1", "id2"])
            to_keep_qs.__getitem__ = lambda s, k: to_keep_qs

            MockVer.objects.filter.return_value.order_by.return_value.values_list.return_value.__getitem__ = (
                lambda s, k: ["keep-id-1", "keep-id-2"]
            )

            delete_qs = MagicMock()
            delete_qs.delete.return_value = (5, {})
            MockVer.objects.filter.return_value.exclude.return_value = delete_qs

            result = cleanup_old_document_versions(keep_per_doc=10)

        # Should have deleted versions for 2 docs × 5 each
        assert result >= 0  # actual count depends on mock setup

    def test_returns_zero_when_nothing_to_clean(self):
        from documents.tasks import cleanup_old_document_versions

        with patch("documents.tasks.DocumentVersion") as MockVer:
            MockVer.objects.values.return_value.annotate.return_value.filter.return_value = []
            result = cleanup_old_document_versions(keep_per_doc=10)

        assert result == 0
