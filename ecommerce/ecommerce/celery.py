import os
from celery.schedules import crontab
from celery import Celery

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "ecommerce.settings"
)

app = Celery("ecommerce")

app.config_from_object(
    "django.conf:settings",
    namespace="CELERY"
)

app.autodiscover_tasks()

CELERY_BEAT_SCHEDULE = {

    # your existing tasks...

    "close-inactive-sessions": {
        "task": "apps.activity.tasks.close_inactive_sessions",
        "schedule": crontab(minute="*/5")    # "schedule": 300.0,   # every 5 minutes
    },

}