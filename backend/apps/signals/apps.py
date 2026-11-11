from django.apps import AppConfig


class SignalsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.signals"
    label = "signals"

    def ready(self):
        from . import tasks_index  # noqa: F401  (registers the weekly index refresh task with Celery)
