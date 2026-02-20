import os, django, datetime
from pathlib import Path
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ezzydelivery.settings')
django.setup()
from django.db.migrations.recorder import MigrationRecorder
from django.utils import timezone

# Get all migrations from file system
apps_path = Path('.')
file_migrations = {}
for app_dir in apps_path.iterdir():
    if app_dir.is_dir() and (app_dir / 'migrations').exists():
        app_name = app_dir.name
        migrations_dir = app_dir / 'migrations'
        file_migrations[app_name] = []
        for mig_file in migrations_dir.glob('*.py'):
            if mig_file.stem != '__init__' and not mig_file.stem.startswith('.'):
                file_migrations[app_name].append(mig_file.stem)

# Get all migrations from database
db_migrations = set()
for mig in MigrationRecorder.Migration.objects.all():
    db_migrations.add((mig.app, mig.name))

# Find migrations in files but not in DB
missing = []
for app, migrations in file_migrations.items():
    for mig_name in migrations:
        if (app, mig_name) not in db_migrations:
            missing.append((app, mig_name))

print(f'Found {len(missing)} migrations in files but not in database:')
for app, mig in sorted(missing)[:30]:  # Show first 30
    print(f'{app}.{mig}')

# Add them all
if missing:
    print(f'\nAdding {len(missing)} missing migration records...')
    for app, mig in missing:
        MigrationRecorder.Migration.objects.create(
            app=app,
            name=mig,
            applied=timezone.now()
        )
    print('Done!')
