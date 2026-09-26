"""
Periodic background command for Opmaint CMMS PTW module.
Scans for permits whose planned_end validity window has passed and auto-expires them.

Can be scheduled via Linux cron / Celery beat / Heroku/Railway scheduler:
    * * * * * python manage.py expire_permits
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from permits.models import Permit


class Command(BaseCommand):
    help = "Scans all active/approved/pending/suspended permits and expires any whose validity window has passed."

    def handle(self, *args, **options):
        now = timezone.now()
        self.stdout.write(f"[{now.strftime('%Y-%m-%d %H:%M:%S UTC')}] Scanning for expired permits...")

        expirable_statuses = [
            Permit.Status.PENDING_APPROVAL,
            Permit.Status.APPROVED,
            Permit.Status.ACTIVE,
            Permit.Status.SUSPENDED,
        ]

        candidates = Permit.objects.filter(
            status__in=expirable_statuses,
            planned_end__lt=now
        )

        expired_count = 0
        for permit in candidates:
            if permit.check_and_update_expiry():
                expired_count += 1
                self.stdout.write(self.style.WARNING(
                    f"-> Expired {permit.permit_number} ({permit.title[:40]}) - planned end was {permit.planned_end}"
                ))

        self.stdout.write(self.style.SUCCESS(
            f"Expiry check completed. {expired_count} permits transitioned to EXPIRED."
        ))
