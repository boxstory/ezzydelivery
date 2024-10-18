from django.http import JsonResponse
from django.shortcuts import render
import requests
from rest_framework import permissions
from rest_framework import generics
from decouple import config

from orders import models as orders_models
from ezzy_api import serializers as ezzy_api_serializers
from shipday import Shipday


# class OrderList(APIView):
#     permission_classes = [permissions.IsAuthenticated]

#     def get(self, request, format=None):
#         orders = orders_models.Order.objects.all()
#         serializer = ezzy_api_serializers.OrderSerializer(orders, many=True)
#         return Response(serializer.data)

#     def post(self, request, format=None):
#         serializer = ezzy_api_serializers.OrderSerializer(data=request.data)
#         if serializer.is_valid():
#             serializer.save()
#             return Response(serializer.data, status=status.HTTP_201_CREATED)
#         return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class OrderList(generics.ListCreateAPIView):

    permission_classes = [permissions.IsAuthenticated]
    queryset = orders_models.Order.objects.all()
    serializer_class = ezzy_api_serializers.OrderSerializer

API_KEY = config("SHIPDAY_API_KEY")
shipday_obj = Shipday(api_key=API_KEY)


def shipday_order_list(request):
    print(shipday_obj)
    orderNumber = "BMS045-1636-A222"
    my_orders = shipday_obj.OrderService.get_orders()
    #print(my_carriers)
    #data = my_carriers.json()
    #return JsonResponse(my_carriers, safe=False)
    return render(request, 'ezzy_api/orders_in_shipday.html', {'orders_in_shipday': my_orders})

def shipday_feet_list(request):
    
    my_carriers = shipday_obj.CarrierService.get_carriers()
    #print(my_carriers)
    #data = my_carriers.json()
    #return JsonResponse(my_carriers, safe=False)
    return render(request, 'ezzy_api/carriers.html', {'carriers': my_carriers})


def ShipdayOrderList(request):
    API_KEY = config("SHIPDAY_API_KEY")
    my_shipday = Shipday(api_key=API_KEY)
    my_carriers = my_shipday.CarrierService.get_carriers()
    print('I have {} carriers'.format(len(my_carriers)))

    import requests

    url = "https://api.shipday.com/partner/members/1234/completedOrders"

    headers = {
        "accept": "application/json",
        "PARTNER-API-KEY": API_KEY
    }

    response = requests.get(url, headers=headers)

    print(response.text)

    data = response.json()
    return data







class TookanAPI:
    base_url = "https://api.tookanapp.com/"
    api_key = config("TOOKAN_API_KEY")

    def __init__(self, api_key):
        self.api_key = api_key

    def _make_request(self, endpoint, method="GET", data=None):
        url = self.base_url + endpoint
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        response = requests.request(method, url, json=data, headers=headers)
        response.raise_for_status()
        return response.json()

    def get_teams(self):
        endpoint = "team/"
        return self._make_request(endpoint)

    def create_task(self, task_data):
        endpoint = "create_task/"
        return self._make_request(endpoint, method="POST", data=task_data)

    def get_task(self, task_id):
        endpoint = f"get_task/{task_id}"
        return self._make_request(endpoint)

    # Add more methods for other API endpoints as needed


