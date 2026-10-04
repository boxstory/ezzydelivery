"""
Purpose: Drain the driver-document image-check queue — read number + expiry off each pending scan and mark it verified when they match.
Used by: per-minute crontab; by hand with --queue-existing to send documents uploaded before the check existed.
Notes: Logic lives in fleet/document_verify.py; this only picks rows and reports.
"""

from django.core.management.base import BaseCommand

from fleet import document_verify
from fleet.models import DriverDocument


class Command(BaseCommand):
    help = 'Read number and expiry off pending driver document scans and verify them.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=20, help='Most documents to read this run.')
        parser.add_argument('--queue-existing', action='store_true',
                            help='First queue every never-checked document that has a scan.')
        parser.add_argument('--quiet', action='store_true')

    def handle(self, *args, limit, queue_existing, quiet, **options):
        if queue_existing:
            queued = 0
            for doc in DriverDocument.objects.filter(ai_status=''):
                if document_verify.needs_image_check(doc):
                    status = DriverDocument.AI_PENDING
                    queued += 1
                elif doc.document_type == 'Selfie':
                    status = DriverDocument.AI_NOT_NEEDED
                else:
                    status = DriverDocument.AI_NO_IMAGE
                DriverDocument.objects.filter(pk=doc.pk).update(ai_status=status)
            self.stdout.write(f'Queued {queued} existing documents.')

        counts = {}
        for doc in document_verify.pending_documents(limit):
            status = document_verify.verify_document(doc)
            counts[status] = counts.get(status, 0) + 1
            if not quiet:
                self.stdout.write(f'#{doc.pk} {doc.document_type}: {status}')
        if counts or not quiet:
            self.stdout.write(f'Done: {counts or "nothing pending"}')
