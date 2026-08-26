# Purpose: Backfill the category tag ("ZyDrv" / "ZyBuz") onto the end of every lead's contact name.
# Used by: manual run (python manage.py tag_lead_contacts [--dry-run] [--undo] [--category driver]).
# Notes: Idempotent — re-running changes nothing. Covers the bulk_create paths that skip Lead.save().

from django.core.management.base import BaseCommand

from crm.contact_tags import CONTACT_TAGS, apply_tag, strip_tags
from crm.models import Lead


class Command(BaseCommand):
    help = ('Append the category tag to every lead contact name — driver leads get '
            f'"{CONTACT_TAGS["driver"]}", business leads "{CONTACT_TAGS["business"]}". Safe to re-run.')

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Report what would change without writing.')
        parser.add_argument('--undo', action='store_true',
                            help='Strip the tags back off instead of adding them.')
        parser.add_argument('--category', choices=sorted(CONTACT_TAGS),
                            help='Limit to one board (default: both).')

    def handle(self, *args, **options):
        dry_run, undo = options['dry_run'], options['undo']
        qs = Lead.objects.exclude(contact_name='').order_by('pk')
        if options['category']:
            qs = qs.filter(category=options['category'])

        changed, samples = [], []
        for lead in qs.iterator():
            new_name = (strip_tags(lead.contact_name) if undo
                        else apply_tag(lead.contact_name, lead.category))
            if new_name == lead.contact_name:
                continue
            changed.append((lead.pk, new_name))
            if len(samples) < 5:
                samples.append(f'  #{lead.pk}  {lead.contact_name!r} -> {new_name!r}')

        verb = 'strip' if undo else 'tag'
        done = 'Stripped' if undo else 'Tagged'
        if not changed:
            self.stdout.write(self.style.SUCCESS(f'Nothing to {verb} — all contact names already correct.'))
            return

        for line in samples:
            self.stdout.write(line)
        if dry_run:
            self.stdout.write(self.style.WARNING(f'[dry-run] Would {verb} {len(changed)} lead(s).'))
            return

        # bulk_update, not save() — the model hook would re-append on an --undo run.
        for start in range(0, len(changed), 500):
            batch = changed[start:start + 500]
            objs = []
            for pk, name in batch:
                lead = Lead(pk=pk)
                lead.contact_name = name
                objs.append(lead)
            Lead.objects.bulk_update(objs, ['contact_name'])
        self.stdout.write(self.style.SUCCESS(f'{done} {len(changed)} lead contact name(s).'))
