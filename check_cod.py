import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ezzydelivery.settings')
django.setup()

from delivery.models import DeliveryTask
from datetime import date

# Check COD data
print("=== COD Data Check ===")
total_cod_tasks = DeliveryTask.objects.filter(cod_collected=True).count()
print(f"Total COD collected tasks: {total_cod_tasks}")

today_tasks = DeliveryTask.objects.filter(cod_collected=True, cod_collected_at__date=date(2026, 1, 15))
print(f"COD collected on 2026-01-15: {today_tasks.count()}")

# Show recent COD tasks
recent_cod = DeliveryTask.objects.filter(cod_collected=True).order_by('-cod_collected_at')[:5]
print(f"\nRecent COD tasks:")
for t in recent_cod:
    print(f"  Task {t.id}: Driver={t.driver_id}, Amount={t.cod_collected_amount}, Date={t.cod_collected_at}")

# Show all drivers with cod_in_hand
from fleet.models import Driver
drivers_with_cod = Driver.objects.filter(cod_in_hand__gt=0).select_related('user')
print(f"\nDrivers with COD in hand: {drivers_with_cod.count()}")
for d in drivers_with_cod[:5]:
    print(f"  {d.user.first_name} {d.user.last_name}: {d.cod_in_hand}")
