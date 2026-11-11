from django.core.management.base import BaseCommand

from apps.core.management.commands.seed_platform import INCIDENT_INDICATOR_MAP
from apps.core.models import ReportingPeriod
from apps.incidents.services import aggregate_incidents


class Command(BaseCommand):
    help = "Aggregate verified incidents into indicator observations for the current period."

    def handle(self, *a, **o):
        n = aggregate_incidents(ReportingPeriod.current(), INCIDENT_INDICATOR_MAP)
        self.stdout.write(f"{n} incident-based observations written")
