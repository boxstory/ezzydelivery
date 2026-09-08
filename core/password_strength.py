"""
Purpose: Server-side mirror of the client password rules in account/js/password-strength.js.
Used by: core/password_signals.py (flags weak passwords at login), core/views_password_warning.py
Notes: Django's configured validators cover length/common/numeric/similarity; this adds the house
       rules — repeated patterns, guessable word stems, sequences, and character composition.
       The word list is read from django.contrib.auth's own 20k file, the same source the client
       list is generated from (core/management/commands/build_common_passwords.py), so both agree.
"""

import gzip
import os
import re
from functools import lru_cache

from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError

MIN_LENGTH = 8
MIN_WORD_LENGTH = 3
MAX_WORD_LENGTH = 16

# Three or more identical characters in a row: aaa, 111, !!!
RUN_OF_THREE = re.compile(r'(.)\1{2,}')
# A 2-4 character unit repeated back to back: abab, 1212, Ab12Ab12
REPEATED_UNIT = re.compile(r'(.{2,4})\1+')

KEYBOARD_ROWS = ('qwertyuiop', 'asdfghjkl', 'zxcvbnm', '1234567890')

LEET = {
    '@': 'a', '4': 'a', '0': 'o', '1': 'i', '!': 'i', '|': 'i',
    '3': 'e', '$': 's', '5': 's', '7': 't', '8': 'b',
}

# Vocabulary Django's global list has no reason to carry.
LOCAL_WORDS = frozenset({
    'qatar', 'doha', 'lusail', 'wakrah', 'wakra', 'alkhor', 'khor', 'rayyan',
    'mesaieed', 'dukhan', 'msheireb', 'katara', 'corniche', 'souq', 'waqif',
    'pearl', 'aspire', 'sealine', 'zubarah', 'ummsalal', 'sadd', 'thumama',
    'ezzy', 'ezzydelivery', 'delivery', 'deliver', 'courier', 'driver',
    'logistics', 'shipping', 'cargo', 'company', 'business', 'office',
})


@lru_cache(maxsize=1)
def common_words():
    """Alphabetic stems from django.contrib.auth's common-password list, plus local vocabulary."""
    source = os.path.join(
        os.path.dirname(password_validation.__file__), 'common-passwords.txt.gz'
    )
    try:
        with gzip.open(source, 'rt', encoding='utf-8') as handle:
            words = {
                word.strip().lower() for word in handle
                if word.strip().isalpha()
                and MIN_WORD_LENGTH <= len(word.strip()) <= MAX_WORD_LENGTH
            }
    except OSError:
        words = set()
    return frozenset(words | LOCAL_WORDS)


def _normalize_leet(value):
    return ''.join(LEET.get(char, char) for char in value.lower())


def _is_known_word(core):
    """A word with at most a couple of letters bolted on is still that word."""
    words = common_words()
    for trim in range(3):
        candidate = core[:-trim] if trim else core
        if len(candidate) >= MIN_WORD_LENGTH and candidate in words:
            return True
    return False


def has_sequence(password):
    """Four or more steps along the alphabet, the number line, or a keyboard row."""
    lower = password.lower()

    run, direction = 1, 0
    for index in range(1, len(lower)):
        step = ord(lower[index]) - ord(lower[index - 1])
        if step in (1, -1):
            run = run + 1 if step == direction else 2
            direction = step
            if run >= 4:
                return True
        else:
            run, direction = 1, 0

    for row in KEYBOARD_ROWS:
        reversed_row = row[::-1]
        for start in range(len(row) - 3):
            if row[start:start + 4] in lower or reversed_row[start:start + 4] in lower:
                return True
    return False


def is_predictable(password):
    """True when the password is a known word wearing a costume — Qatar2026!, P@ssw0rd."""
    if not password:
        return False
    if has_sequence(password):
        return True

    cores = (
        re.sub(r'[^a-z]', '', password.lower()),
        re.sub(r'[^a-z]', '', _normalize_leet(password)),
    )
    return any(_is_known_word(core) for core in cores if core)


def has_repeats(password):
    return bool(RUN_OF_THREE.search(password) or REPEATED_UNIT.search(password))


def password_weaknesses(password, user=None):
    """Return the rule keys this password fails; empty list means it passes everything."""
    if not password:
        return ['length']

    failed = []

    if len(password) < MIN_LENGTH:
        failed.append('length')
    if has_repeats(password):
        failed.append('repeats')
    if is_predictable(password):
        failed.append('predictable')
    if not (re.search(r'[a-z]', password) and re.search(r'[A-Z]', password)):
        failed.append('case')
    if not re.search(r'\d', password):
        failed.append('number')
    if not re.search(r'[^A-Za-z0-9]', password):
        failed.append('symbol')

    # Whatever AUTH_PASSWORD_VALIDATORS is configured with (similarity, common, numeric…).
    try:
        password_validation.validate_password(password, user)
    except ValidationError:
        if 'django' not in failed:
            failed.append('django')

    return failed


def is_weak(password, user=None):
    return bool(password_weaknesses(password, user))
