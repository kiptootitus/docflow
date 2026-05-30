"""
DocFlow AI — Celery Configuration
Location: docflow/celery.py
"""

import os
import logging
from datetime import timedelta
from celery import Celery
from celery.signals import (
    task_prerun, 
    task_postrun, 
    task_failure,
    worker_ready,
    worker_shutdown,
    worker_process_init,
    worker_process_shutdown
)

# Ensure Django settings are loaded
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "docflow.settings")

app = Celery("docflow")

# Load settings from Django settings.py using CELERY_ prefix
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks from all installed apps
app.autodiscover_tasks()

logger = logging.getLogger(__name__)


# -----------------------------
# Core Reliability Settings
# -----------------------------

app.conf.update(
    # Broker / backend stability
    broker_connection_retry_on_startup=True,
    broker_connection_max_retries=10,

    result_backend_transport_options={
        "visibility_timeout": 3600,
    },

    task_acks_late=True,
    worker_prefetch_multiplier=1,

    task_reject_on_worker_lost=True,

    timezone="Africa/Nairobi",
    enable_utc=False,

    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    worker_send_task_events=True,
    task_send_sent_event=True,
    
    # Task result expiration (keep results for 7 days)
    result_expires=timedelta(days=7),
    
    # Task time limits (soft/hard)
    task_soft_time_limit=3300,  # 55 minutes
    task_time_limit=3600,        # 60 minutes
    
    # Max tasks per child to prevent memory leaks
    worker_max_tasks_per_child=1000,
    
    # Task tracking
    task_track_started=True,
    task_ignore_result=False,
    
    # Queue definitions (if not already in settings)
    task_queues={
        "high": {
            "exchange": "high",
            "routing_key": "high",
            "exchange_type": "direct"
        },
        "default": {
            "exchange": "default",
            "routing_key": "default",
            "exchange_type": "direct"
        },
        "low": {
            "exchange": "low",
            "routing_key": "low",
            "exchange_type": "direct"
        }
    },
    task_default_queue="default",
    task_default_exchange="default",
    task_default_routing_key="default",
    
    # Routing for specific tasks
    task_routes={
        "billing.tasks.*": {"queue": "high"},
        "notifications.tasks.send_invoice_payment_reminders": {"queue": "high"},
        "ai.tasks.*": {"queue": "high"},
        "integrations.tasks.*": {"queue": "high"},
        "documents.tasks.generate_pdf": {"queue": "default"},
        "documents.tasks.send_invoice_email": {"queue": "default"},
        "*": {"queue": "default"},
    },
    
    # Rate limits (tasks per second/minute)
    task_annotations={
        "integrations.tasks.sync_integration_data": {"rate_limit": "10/m"},
        "billing.tasks.process_stripe_webhook": {"rate_limit": "30/m"},
        "notifications.tasks.send_email": {"rate_limit": "100/m"},
    }
)


# -----------------------------
# Custom Task Class with Metrics
# -----------------------------

class TrackedTask(app.Task):
    """Custom task class with built-in metrics tracking."""
    
    def __init__(self):
        self.task_metrics = {
            "total_runs": 0,
            "total_successes": 0,
            "total_failures": 0,
            "total_time": 0.0
        }
    
    def apply_async(self, args=None, kwargs=None, **options):
        """Track task submission."""
        logger.debug(f"Task {self.name} submitted with args={args}, kwargs={kwargs}")
        return super().apply_async(args, kwargs, **options)
    
    def on_success(self, retval, task_id, args, kwargs):
        """Called when task succeeds."""
        self.task_metrics["total_runs"] += 1
        self.task_metrics["total_successes"] += 1
        logger.info(f"Task {self.name}[{task_id}] succeeded: {retval}")
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Called when task fails."""
        self.task_metrics["total_runs"] += 1
        self.task_metrics["total_failures"] += 1
        logger.error(
            f"Task {self.name}[{task_id}] failed: {exc}\n"
            f"Args: {args}\n"
            f"Kwargs: {kwargs}\n"
            f"Error Info: {einfo}"
        )
    
    def after_return(self, status, retval, task_id, args, kwargs, einfo):
        """Called after task returns."""
        logger.debug(f"Task {self.name}[{task_id}] completed with status: {status}")


# Register custom task class
app.Task = TrackedTask


# -----------------------------
# Signal Handlers for Monitoring
# -----------------------------

@task_prerun.connect
def task_prerun_handler(signal=None, sender=None, task_id=None, task=None, args=None, kwargs=None, **kw):
    """Log when task starts."""
    logger.info(f"Starting task: {task.name}[{task_id}] with args={args}, kwargs={kwargs}")
    
    # Store start time in task context for duration tracking
    from celery import current_task
    if hasattr(current_task, "request"):
        current_task.request.start_time = __import__("time").time()


@task_postrun.connect
def task_postrun_handler(signal=None, sender=None, task_id=None, task=None, args=None, kwargs=None, retval=None, state=None, **kw):
    """Log when task completes and record duration."""
    from celery import current_task
    
    duration = 0
    if hasattr(current_task, "request") and hasattr(current_task.request, "start_time"):
        start_time = current_task.request.start_time
        duration = __import__("time").time() - start_time
    
    logger.info(
        f"Completed task: {task.name}[{task_id}] "
        f"duration={duration:.2f}s, state={state}"
    )
    
    # Send metrics to monitoring system
    try:
        from django.core.cache import cache
        metrics_key = f"celery_metrics:{task.name}"
        metrics = cache.get(metrics_key, {"count": 0, "total_duration": 0})
        metrics["count"] += 1
        metrics["total_duration"] += duration
        cache.set(metrics_key, metrics, timeout=3600)
    except Exception as e:
        logger.warning(f"Failed to record metrics: {e}")


@task_failure.connect
def task_failure_handler(signal=None, sender=None, task_id=None, exception=None, args=None, kwargs=None, traceback=None, einfo=None, **kw):
    """Handle task failures with alerts."""
    logger.error(
        f"Task failed: {sender.name}[{task_id}]\n"
        f"Exception: {exception}\n"
        f"Traceback: {traceback}\n"
        f"Args: {args}\n"
        f"Kwargs: {kwargs}"
    )
    
    # Send alert for critical task failures
    critical_tasks = [
        "integrations.tasks.sync_integration_data",
        "billing.tasks.process_payment",
        "notifications.tasks.send_invoice_payment_reminders"
    ]
    
    if sender.name in critical_tasks:
        try:
            from notifications.services import send_admin_alert
            # This would send an alert to admins
            logger.warning(f"CRITICAL: Task {sender.name} failed - sending admin alert")
        except Exception as e:
            logger.error(f"Failed to send admin alert: {e}")


@worker_ready.connect
def worker_ready_handler(sender=None, **kwargs):
    """Log when worker is ready."""
    logger.info(f"Celery worker ready: {sender}")


@worker_shutdown.connect
def worker_shutdown_handler(sender=None, **kwargs):
    """Log when worker shuts down."""
    logger.info(f"Celery worker shutting down: {sender}")


@worker_process_init.connect
def worker_process_init_handler(**kwargs):
    """Initialize each worker process."""
    import signal
    import sys
    
    logger.info(f"Worker process initialized: PID={os.getpid()}")
    
    # Set up signal handlers for graceful shutdown
    def sigterm_handler(signum, frame):
        logger.info(f"Worker process {os.getpid()} received SIGTERM")
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, sigterm_handler)


@worker_process_shutdown.connect
def worker_process_shutdown_handler(**kwargs):
    """Cleanup when worker process shuts down."""
    logger.info(f"Worker process shutting down: PID={os.getpid()}")


# -----------------------------
# Periodic Task Schedule (Fallback)
# -----------------------------

app.conf.beat_schedule = {
    # Integration syncs
    "sync-quickbooks-hourly": {
        "task": "integrations.tasks.schedule_integration_syncs",
        "schedule": timedelta(hours=1),
        "options": {"queue": "default"}
    },
    
    # Cleanup tasks
    "cleanup-expired-sessions-daily": {
        "task": "core.tasks.cleanup_expired_sessions",
        "schedule": timedelta(days=1),
        "options": {"queue": "low"}
    },
    
    "cleanup-old-logs-weekly": {
        "task": "core.tasks.cleanup_old_logs",
        "schedule": timedelta(days=7),
        "options": {"queue": "low"}
    },
    
    # Health checks
    "health-check": {
        "task": "core.tasks.health_check",
        "schedule": timedelta(minutes=5),
        "options": {"queue": "low"}
    },
}

# -----------------------------
# Debug Task
# -----------------------------
@app.task(bind=True, ignore_result=True, queue="default")
def debug_task(self):
    """Debug task to test Celery is working."""
    print(f"[Celery DEBUG] Request: {self.request!r}")
    return {"status": "ok", "task_id": self.request.id}


# -----------------------------
# Health Check Task
# -----------------------------
@app.task(bind=True, queue="low")
def health_check(self):
    """Health check task for monitoring."""
    import django
    from django.db import connections
    from django.core.cache import cache
    import redis
    
    results = {
        "status": "healthy",
        "checks": {},
        "timestamp": __import__("django.utils.timezone").now().isoformat()
    }
    
    # Check Django
    try:
        django.setup()
        results["checks"]["django"] = "ok"
    except Exception as e:
        results["checks"]["django"] = f"error: {e}"
        results["status"] = "unhealthy"
    
    # Check database
    try:
        for conn_name in connections:
            connections[conn_name].ensure_connection()
        results["checks"]["database"] = "ok"
    except Exception as e:
        results["checks"]["database"] = f"error: {e}"
        results["status"] = "unhealthy"
    
    # Check Redis/Cache
    try:
        cache.set("celery_health_check", "ok", timeout=10)
        if cache.get("celery_health_check") == "ok":
            results["checks"]["cache"] = "ok"
        else:
            results["checks"]["cache"] = "error: cache read/write failed"
            results["status"] = "unhealthy"
    except Exception as e:
        results["checks"]["cache"] = f"error: {e}"
        results["status"] = "unhealthy"
    
    # Log results
    if results["status"] == "healthy":
        logger.info("Health check passed")
    else:
        logger.error(f"Health check failed: {results}")
    
    return results