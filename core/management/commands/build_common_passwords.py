"""
Purpose: Generate the client-side common-password word list from Django's own 20k list.
Used by: templates/static/account/js/password-strength.js (fetches the generated files)
Notes: Re-run after upgrading Django — the source list ships inside django.contrib.auth.
"""

import gzip
import os

from django.conf import settings
from django.contrib.auth import password_validation
from django.core.management.base import BaseCommand

# Only alphabetic stems are useful client-side: entries like "123456" or "password1"
# are already caught by the sequence rule and by stripping digits before the lookup.
MIN_LENGTH = 3
MAX_LENGTH = 16

OUTPUT_DIR = os.path.join(settings.BASE_DIR, 'templates', 'static', 'account', 'data')
OUTPUT_NAME = 'common-passwords.txt'


class Command(BaseCommand):
    help = "Build the client-side common-password list from django.contrib.auth's 20k list."

    def handle(self, *args, **options):
        source = os.path.join(
            os.path.dirname(password_validation.__file__), 'common-passwords.txt.gz'
        )

        with gzip.open(source, 'rt', encoding='utf-8') as handle:
            raw = [line.strip().lower() for line in handle if line.strip()]

        words = sorted({
            word for word in raw
            if word.isalpha() and MIN_LENGTH <= len(word) <= MAX_LENGTH
        })
        payload = '\n'.join(words).encode('utf-8')

        os.makedirs(OUTPUT_DIR, exist_ok=True)
        plain_path = os.path.join(OUTPUT_DIR, OUTPUT_NAME)
        gz_path = plain_path + '.gz'

        with open(plain_path, 'wb') as handle:
            handle.write(payload)

        # mtime=0 keeps the output byte-identical between runs, so it stays out of diffs.
        with open(gz_path, 'wb') as handle:
            handle.write(gzip.compress(payload, compresslevel=9, mtime=0))

        self.stdout.write(self.style.SUCCESS(
            f"{len(words)} stems from {len(raw)} entries -> "
            f"{OUTPUT_NAME} ({len(payload) // 1024} KB) + .gz ({os.path.getsize(gz_path) // 1024} KB)"
        ))
