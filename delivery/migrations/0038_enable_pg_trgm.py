from django.contrib.postgres.operations import TrigramExtension
from django.db import migrations


class Migration(migrations.Migration):
    """Enable pg_trgm so zone/area names can be matched fuzzily (typo tolerance)."""

    dependencies = [
        ('delivery', '0037_pickuptask_deliverytask_source_pickup_task_and_more'),
    ]

    operations = [
        TrigramExtension(),
    ]
