from rest_framework import serializers
from orders import models as orders_models


class OrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = orders_models.Order
        fields = '__all__'
