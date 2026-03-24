from django.core.management.base import BaseCommand
from orders.tasks import sync_all_temp_orders


class Command(BaseCommand):
    help = 'Sync all external sources into TempOrder table'

    def handle(self, *args, **options):
        self.stdout.write('Starting temp orders sync...')
        result = sync_all_temp_orders()
        created = result.get('created', 0)
        updated = result.get('updated', 0)
        errors = result.get('errors', [])
        self.stdout.write(self.style.SUCCESS(
            f'Sync complete: {created} created, {updated} updated, {len(errors)} errors'
        ))
        for e in errors[:10]:
            self.stdout.write(self.style.WARNING(f'  {e}'))
