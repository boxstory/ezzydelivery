"""
Purpose: One canonical form for every stored email address — trimmed and lower-cased.
Used by: models that hold an email (core.Profile, business.*, webpages.*, warehouse.Warehouse,
         fleet.InvoiceSettings) via EmailNormalizedModel, and core.email_signals for auth.User.
Notes: Deliberately free of Django model imports so any app's models.py can import it.
"""


def normalize_email(value):
    """
    Return the canonical form of an email address.

    Trims surrounding whitespace and lower-cases the whole address. Mail
    domains are case-insensitive and no mail provider we deal with treats the
    local part as case-sensitive, so one stored casing keeps lookups,
    de-duplication and on-screen text consistent.

    None and blank are returned untouched, so this never turns an empty field
    into a value — and never puts None into a column that does not allow it.
    """
    if not value:
        return value
    return value.strip().lower()


class EmailNormalizedModel:
    """
    Mixin that normalizes the fields listed in EMAIL_FIELDS on every save.

    Put it before models.Model in the bases and list the columns:

        class Warehouse(EmailNormalizedModel, models.Model):
            EMAIL_FIELDS = ('email',)

    Normalizing here rather than in each form means every write path — forms,
    staff edit endpoints, the API, imports, admin — lands the same value.
    Bulk paths that bypass save() (queryset.update, bulk_create) are not
    covered; normalize explicitly there.
    """

    EMAIL_FIELDS = ()

    def save(self, *args, **kwargs):
        for field in self.EMAIL_FIELDS:
            current = getattr(self, field, None)
            normalized = normalize_email(current)
            if normalized != current:
                setattr(self, field, normalized)
        super().save(*args, **kwargs)
