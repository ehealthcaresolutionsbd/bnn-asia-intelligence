from django.core.management.base import BaseCommand

from apps.sources.models import DataSource
from apps.sources.services import test_source


class Command(BaseCommand):
    help = "Run the self-test of every registered data source and update the integration registry."

    def handle(self, *a, **o):
        for s in DataSource.objects.all():
            ok = test_source(s)
            self.stdout.write(f"{'OK  ' if ok else 'FAIL'} {s.slug:16} {s.status:11} {s.last_test_message[:110]}")
