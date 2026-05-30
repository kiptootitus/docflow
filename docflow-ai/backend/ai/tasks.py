from celery import shared_task
from django.utils import timezone
import logging

from .models import Contract, TaskExecution
from .compliance import JurisdictionComplianceMatcher

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3)
def execute_nightly_compliance_scan(self):
    """
    Celery background cron sweep that reviews un-terminated contract records 
    against updating regional legislative matrix settings.
    """
    execution_record = TaskExecution.objects.create(
        task_name=self.name,
        celery_task_id=self.request.id or "cron-triggered-run",
        status="RUNNING",
        started_at=timezone.now()
    )

    try:
        active_contracts = Contract.objects.filter(
            is_deleted=False
        ).exclude(
            status__in=[Contract.Status.TERMINATED, Contract.Status.EXPIRED]
        )

        scan_counter = 0
        alert_counter = 0

        for contract in active_contracts:
            matcher = JurisdictionComplianceMatcher(contract=contract)
            issued_alerts = matcher.audit_against_active_rules()
            scan_counter += 1
            alert_counter += len(issued_alerts)

        execution_record.status = "SUCCESS"
        execution_record.finished_at = timezone.now()
        execution_record.error_message = f"Scan complete. Evaluated {scan_counter} contracts. Generated {alert_counter} alerts."
        execution_record.save()
        return execution_record.error_message

    except Exception as exc:
        execution_record.status = "FAILED"
        execution_record.finished_at = timezone.now()
        execution_record.error_message = str(exc)
        execution_record.save()
        logger.error(f"Nightly system compliance execution failure: {str(exc)}")
        raise self.retry(exc=exc, countdown=60)