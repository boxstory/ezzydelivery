
from venv import create
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.contrib.auth.models import User
import uuid
from fleet import models as fleet_models


#@receiver(post_save, sender=fleet_models.Driver)
def fleet_register_pre_save_receiver(sender, instance, created, *args, **kwargs):
    print("Driver post save receiver")
    if created:
        print(instance)

        if instance not in fleet_models.DriverVehicle.objects.values_list('driver_id', flat=True):
            fleet_models.DriverVehicle.objects.create(
                driver=instance,
                vehicle_type='none',
                vehicle_status='Inactive',
            )
            instance.save()
        if instance not in fleet_models.DriverDocument.objects.values_list('driver_id', flat=True):
            fleet_models.DriverDocument.objects.create(
                driver=instance,
                qid_expirey_date='2022-12-31',

            )
            instance.save()
