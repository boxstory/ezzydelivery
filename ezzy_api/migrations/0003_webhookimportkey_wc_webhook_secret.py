# Purpose: Add wc_webhook_secret to WebhookImportKey for WooCommerce signature verification
# Used by: ezzy_api/models.py WebhookImportKey
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ezzy_api', '0002_webhook_import'),
    ]

    operations = [
        migrations.AddField(
            model_name='webhookimportkey',
            name='wc_webhook_secret',
            field=models.CharField(
                blank=True,
                default='',
                help_text='WooCommerce webhook secret for HMAC-SHA256 signature verification',
                max_length=64,
            ),
        ),
    ]
