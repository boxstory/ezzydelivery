"""
Step 2: Data migration - convert old Title Case status values to new snake_case.
Also handles invalid values from pre-existing bugs in core/views.py.
"""
from django.db import migrations


def convert_status_forward(apps, schema_editor):
    Driver = apps.get_model('fleet', 'Driver')
    mapping = {
        'Pending on Review': 'pending',
        'Processing': 'processing',
        'Approved': 'approved',
        'Rejected': 'rejected',
        'Blocked': 'blocked',
        # Handle buggy values from core/views.py
        'Active': 'approved',
        'Approval Pending': 'pending',
        'active': 'approved',
        'inactive': 'blocked',
    }
    for old_val, new_val in mapping.items():
        Driver.objects.filter(driver_status=old_val).update(driver_status=new_val)

    # Catch any remaining invalid values
    valid_values = ['pending', 'processing', 'approved', 'rejected', 'blocked', 'suspended']
    Driver.objects.exclude(driver_status__in=valid_values).update(driver_status='pending')

    # Set approved drivers with active delivery tasks to on_delivery
    DeliveryTask = apps.get_model('delivery', 'DeliveryTask')
    active_driver_ids = DeliveryTask.objects.filter(
        dl_task_status__in=['assigned', 'accepted', 'picked_up', 'in_transit', 'out_for_delivery', 'start_ride']
    ).values_list('driver_id', flat=True).distinct()
    Driver.objects.filter(
        driver_id__in=active_driver_ids, driver_status='approved'
    ).update(driver_availability='on_delivery')


def convert_status_reverse(apps, schema_editor):
    Driver = apps.get_model('fleet', 'Driver')
    mapping = {
        'pending': 'Pending on Review',
        'processing': 'Processing',
        'approved': 'Approved',
        'rejected': 'Rejected',
        'blocked': 'Blocked',
        'suspended': 'Blocked',
    }
    for new_val, old_val in mapping.items():
        Driver.objects.filter(driver_status=new_val).update(driver_status=old_val)


class Migration(migrations.Migration):

    dependencies = [
        ('fleet', '0009_driver_status_snake_case'),
        ('delivery', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(convert_status_forward, convert_status_reverse),
    ]
