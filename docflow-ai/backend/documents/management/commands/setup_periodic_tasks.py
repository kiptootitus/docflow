from django.core.management.base import BaseCommand
from django_celery_beat.models import PeriodicTask, CrontabSchedule
import json

class Command(BaseCommand):
    help = "Set up Celery Beat periodic tasks"
    def handle(self, *args, **options):
        schedule, _ = CrontabSchedule.objects.get_or_create(minute="0", hour="8", day_of_week="*", day_of_month="*", month_of_year="*")
        PeriodicTask.objects.update_or_create(
            name="Check overdue invoices",
            defaults={"crontab": schedule, "task": "apps.documents.tasks.check_overdue_invoices", "args": json.dumps([])},
        )
        self.stdout.write(self.style.SUCCESS("Periodic tasks registered."))
