"""Fill an empty database with the fictional demo organisation. Used when the public demo starts.

Does nothing when an organisation already exists, so a restart that keeps its database keeps its data.
"""
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand

from organizations.models import Organization


class Command(BaseCommand):
    help = "Seed the demo organisation if the database has no organisations yet."

    def add_arguments(self, parser):
        parser.add_argument("--students", type=int, default=60)
        parser.add_argument("--days", type=int, default=14)

    def handle(self, *args, **options):
        if Organization.objects.exists():
            self.stdout.write("Database already has data; demo not re-seeded.")
            return
        call_command(
            "seed_test_data", students=options["students"], days=options["days"], password=settings.DEMO_PASSWORD,
            stdout=self.stdout,
        )
        self.stdout.write(self.style.SUCCESS("Demo data is ready."))
