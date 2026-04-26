import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("config")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# Periodic tasks
app.conf.beat_schedule = {
    "process-pending-payouts": {
        "task": "payouts.tasks.process_pending_payouts",
        "schedule": 5.0,  # Every 5 seconds
    },
    "retry-stuck-payouts": {
        "task": "payouts.tasks.retry_stuck_payouts",
        "schedule": 10.0,  # Every 10 seconds
    },
    "cleanup-expired-idempotency-keys": {
        "task": "payouts.tasks.cleanup_expired_idempotency_keys",
        "schedule": crontab(minute=0, hour="*/1"),  # Every hour
    },
}
