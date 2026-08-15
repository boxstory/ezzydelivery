"""
Purpose: Rewrite any stored email address that is not already trimmed and lower-case.
Used by: staff, after an import or a bulk update that bypassed model save().
Notes: New writes are normalized automatically (EmailNormalizedModel + core.email_signals);
       this only exists to clean rows written before that, or by queryset.update().
"""

from django.core.management.base import BaseCommand

from core.email_normalize import normalize_email


def _targets():
    """(model, field) pairs for every email column we store."""
    from django.contrib.auth import get_user_model

    from business.models import Business, BusinessProfile, BusinessTeamProfile
    from core.models import Profile
    from fleet.models import ReceiptTemplate
    from warehouse.models import Warehouse
    from webpages.models import Careers, ContactUs, DeliveryRequest, PricingEnquiry

    pairs = [
        (get_user_model(), 'email'),
        (Profile, 'email'),
        (Business, 'business_email'),
        (BusinessProfile, 'business_email'),
        (BusinessTeamProfile, 'team_email'),
        (ContactUs, 'email'),
        (Careers, 'email'),
        (PricingEnquiry, 'email'),
        (DeliveryRequest, 'customer_email'),
        (Warehouse, 'email'),
        (ReceiptTemplate, 'company_email'),
    ]

    try:
        from allauth.account.models import EmailAddress
        pairs.append((EmailAddress, 'email'))
    except ImportError:
        pass

    return pairs


class Command(BaseCommand):
    help = "Lower-case and trim every stored email address."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Report what would change without writing anything.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        total = 0

        for model, field in _targets():
            label = f'{model.__name__}.{field}'
            changed = 0

            for obj in model.objects.exclude(**{field: ''}).exclude(**{f'{field}__isnull': True}).iterator():
                current = getattr(obj, field)
                fixed = normalize_email(current)
                if fixed == current:
                    continue
                changed += 1
                self.stdout.write(f'  {label} #{obj.pk}: {current} -> {fixed}')
                if not dry_run:
                    setattr(obj, field, fixed)
                    obj.save(update_fields=[field])

            total += changed
            if changed:
                self.stdout.write(self.style.WARNING(f'{label}: {changed} row(s)'))

        verb = 'would be normalized' if dry_run else 'normalized'
        self.stdout.write(self.style.SUCCESS(f'{total} email(s) {verb}.'))
