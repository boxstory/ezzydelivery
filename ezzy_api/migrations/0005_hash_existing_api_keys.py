# Purpose: Backfill hashed key material for existing ClientApiKeys.
# Used by: one-time data migration (run after 0004 adds key_hash/key_prefix/scope).
# Notes: Hashes each existing plaintext api_key into key_hash, records a display
#        prefix, grandfathers existing keys to the 'admin' scope, and clears the
#        plaintext column. Non-breaking — clients keep using their current keys.

import hashlib
from django.db import migrations


def hash_existing_keys(apps, schema_editor):
    ClientApiKey = apps.get_model('ezzy_api', 'ClientApiKey')
    for key in ClientApiKey.objects.all().iterator():
        raw = key.api_key
        if not raw or key.key_hash:
            continue
        key.key_hash = hashlib.sha256(raw.encode('utf-8')).hexdigest()
        key.key_prefix = raw[:16]
        key.scope = 'admin'          # grandfather existing keys to full access
        key.api_key = None           # drop the stored plaintext
        key.save(update_fields=['key_hash', 'key_prefix', 'scope', 'api_key'])


def reverse_noop(apps, schema_editor):
    # Irreversible: plaintext keys cannot be recovered from their hashes.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('ezzy_api', '0004_clientapikey_key_hash_clientapikey_key_prefix_and_more'),
    ]

    operations = [
        migrations.RunPython(hash_existing_keys, reverse_noop),
    ]
