from django.core.management.base import BaseCommand, CommandError

from apps.core.models import ReportingPeriod
from apps.signals.pipeline import refresh_annual_index


class Command(BaseCommand):
    help = "Rebuild BNN signal indicators, aggregate incidents, calculate the v2 index and publish it."

    def add_arguments(self, p):
        p.add_argument("--period", help="Reporting period slug (default: current).")
        p.add_argument("--no-publish", action="store_true", help="Leave the snapshot as a draft.")

    def handle(self, *a, period=None, no_publish=False, **o):
        per = ReportingPeriod.objects.filter(slug=period).first() if period else ReportingPeriod.current()
        if per is None:
            raise CommandError("Reporting period not found.")
        out = refresh_annual_index(per, publish_result=not no_publish)
        self.stdout.write(self.style.SUCCESS(str(out)))
