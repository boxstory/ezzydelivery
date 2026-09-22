# Purpose: Generate a collision-free Driver.driver_code — 3 letters + 2 digits (ABC12), the code a driver sees in the app and quotes to ops.
# Used by: core.views (both driver signup paths — the /join_us/driver/ application and the driver register form).
# Notes: driver_code is UNIQUE at the DB level, so a duplicate is an IntegrityError, not a silent overwrite.
#        O, I and L are omitted so a spoken or handwritten code cannot be confused with 0 and 1.
#        Uses apps.get_model to stay importable from fleet.models without a circular import.

import secrets
import string

from django.apps import apps

__all__ = ['generate_driver_code', 'CODE_ALPHABET', 'LETTERS', 'DIGITS']

# Look-alike letters dropped: O (vs 0), I and L (vs 1). Leaves 23 letters.
CODE_ALPHABET = ''.join(c for c in string.ascii_uppercase if c not in 'OIL')
CODE_DIGITS = string.digits

LETTERS = 3
DIGITS = 2

# 23**3 * 100 = 1,216,700 codes. After this many collisions we add a digit
# rather than spin forever, so a saturated fleet can still register a driver.
_MAX_ATTEMPTS = 20


def generate_driver_code(letters=LETTERS, digits=DIGITS):
    """Return a code (e.g. 'ABC12') that no existing Driver row is using.

    Not atomic on its own — the unique constraint on Driver.driver_code is what
    actually guarantees uniqueness under concurrent signups. This just makes the
    collision (and the resulting IntegrityError) vanishingly unlikely.
    """
    Driver = apps.get_model('fleet', 'Driver')
    attempts = 0
    while True:
        code = (''.join(secrets.choice(CODE_ALPHABET) for _ in range(letters))
                + ''.join(secrets.choice(CODE_DIGITS) for _ in range(digits)))
        if not Driver.objects.filter(driver_code=code).exists():
            return code
        attempts += 1
        if attempts >= _MAX_ATTEMPTS:
            attempts = 0
            digits += 1
