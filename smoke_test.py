import os
import django
from django.test import Client
from django.urls import reverse

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ezzydelivery.settings')
django.setup()

client = Client()
print("Django Setup OK")
print(f"Testing index: {reverse('webpages:index')}")
response = client.get('/')
print(f"Index status: {response.status_code}")
