"""
DocFlow AI — Celery Configuration
Location: docflow/celery.py
"""

import os
from celery import Celery

# Ensure Django settings are loaded
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "docflow.settings")

app = Celery("docflow")

# Load settings from Django settings.py using CELERY_ prefix
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks from all installed apps
app.autodiscover_tasks()


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
)


# -----------------------------
# Debug Task
# -----------------------------
@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f"[Celery DEBUG] Request: {self.request!r}")