from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required
# Add these imports at the top of your View file
from django.core.paginator import (
    Paginator,
    EmptyPage,
    PageNotAnInteger,
)
from django.urls import reverse
# Create your views here.
from client import models as business_models
from core import models as core_models
from orders import models as orders_models
from delivery import models as delivery_models

from client import forms as business_forms





@login_required(login_url='/accounts/login/')
def wf_dashboard(request):
    profile = core_models.Profile.objects.get(user_id=request.user.id)

    data = {
        'profile': profile,

    }
    return render(request, 'workforce/wf_base_dashboard.html', data)


# Orders section  ------------------------------------------------------------------------------------------------------




def all_orders(request):
    orders  = orders_models.Order.objects.all().order_by('-created_at')
        
    default_page = 1
    page = request.GET.get('page', default_page)
    # Paginate items
    items_per_page = 10
    paginator = Paginator(orders , items_per_page)
    try:
        orders = paginator.page(page)
        print(orders)
    except PageNotAnInteger:
        orders = paginator.page(default_page)
        print(orders)
    except EmptyPage:
        orders = paginator.page(paginator.num_pages)
        print(orders)

    data = {
        'orders': orders,
    }
    return render(request, 'workforce/parts/lists/orders_list.html', data)




def orders_to_publish(request):
    #orders = orders_models.Order.objects.filter(task_created = False).order_by('-created_at')
    orders = orders_models.Order.objects.filter(task_created = False).order_by('-created_at')
    print(orders)
 
    default_page = 1
    page = request.GET.get('page', default_page)
    # Paginate items
    items_per_page = 10
    paginator = Paginator(orders , items_per_page)
    try:
        orders = paginator.page(page)
        print(orders)
    except PageNotAnInteger:
        orders = paginator.page(default_page)
        print(orders)
    except EmptyPage:
        orders = paginator.page(paginator.num_pages)
        print(orders)

    data = {
        'orders': orders,
    }
    return render(request, 'workforce/parts/lists/orders_list.html', data)


def orders_published(request):
    #orders = orders_models.Order.objects.filter(task_created = False).order_by('-created_at')
    orders = orders_models.Order.objects.filter(task_created = True).order_by('-created_at')
    print(orders)
 
    default_page = 1
    page = request.GET.get('page', default_page)
    # Paginate items
    items_per_page = 10
    paginator = Paginator(orders , items_per_page)
    try:
        orders = paginator.page(page)
        print(orders)
    except PageNotAnInteger:
        orders = paginator.page(default_page)
        print(orders)
    except EmptyPage:
        orders = paginator.page(paginator.num_pages)
        print(orders)

    data = {
        'orders': orders,
    }
    return render(request, 'workforce/parts/lists/orders_list.html', data)

def submit_to_task(request, order_id):
    order = get_object_or_404(orders_models.Order, id=order_id)
    
    delivery_models.DeliveryTask.objects.create(
                dl_task_number=order.order_number,
                dl_task_number_dms=order.order_number,
                order = order,
                business = order.business,
                )
    orders_models.Order.objects.filter(id=order_id).update(
                                       task_created = True)
    
    delivery_models.DlAddressUpdate.objects.create(
                full_name=order.customer_name,
                dl_task_number=order.order_number,
                mobile_no=order.customer_phone,
                dl_zone=order.dl_zone,
                dl_street=order.dl_street,
                dl_building=order.dl_building,
                dl_longitude='0',
                dl_latitude = '0', 
                order_id = order_id, 
                dl_unit = '0', )

    return redirect(reverse('workforce:all_orders'))


    

    





# Order Uploading verification section  ------------------------------------------------------------------------------------------------------


#@todo


# Delivery Tasks section  ------------------------------------------------------------------------------------------------------

def dl_list_all(request):
    dl_tasks  = delivery_models.DeliveryTask.objects.all().order_by('-created_at')
    #print(orders)
        
    default_page = 1
    page = request.GET.get('page', default_page)
    # Paginate items
    items_per_page = 10
    paginator = Paginator(dl_tasks , items_per_page)
    try:
        dl_tasks = paginator.page(page)
        print(dl_tasks)
    except PageNotAnInteger:
        dl_tasks = paginator.page(default_page)
        print(dl_tasks)
    except EmptyPage:
        dl_tasks = paginator.page(paginator.num_pages)
        print(dl_tasks)
    data = {
        'dl_tasks': dl_tasks,
    }
    return render(request, 'workforce/parts/lists/dl_list_all.html', data)


def dl_list_incompleted_details(request):
    orders  = orders_models.Order.objects.all().order_by('-created_at')
        
    default_page = 1
    page = request.GET.get('page', default_page)
    # Paginate items
    items_per_page = 10
    paginator = Paginator(orders , items_per_page)
    try:
        orders = paginator.page(page)
        print(orders)
    except PageNotAnInteger:
        orders = paginator.page(default_page)
        print(orders)
    except EmptyPage:
        orders = paginator.page(paginator.num_pages)
        print(orders)

    data = {
        'orders': orders,
    }
    return render(request, 'workforce/parts/lists/dl_list_incompleted.html', data)




def dl_list_published_to_dms(request):
    orders  = delivery_models.DeliveryTask.objects.filter().order_by('-created_at')
        
    default_page = 1
    page = request.GET.get('page', default_page)
    # Paginate items
    items_per_page = 10
    paginator = Paginator(orders , items_per_page)
    try:
        orders = paginator.page(page)
        print(orders)
    except PageNotAnInteger:
        orders = paginator.page(default_page)
        print(orders)
    except EmptyPage:
        orders = paginator.page(paginator.num_pages)
        print(orders)

    data = {
        'orders': orders,
    }
    return render(request, 'workforce/parts/lists/dl_list_all.html', data)


def dl_list_ready_to_published_to_dms(request):
    orders  = orders_models.Order.objects.filter(task_created = False).order_by('-created_at')
        
    default_page = 1
    page = request.GET.get('page', default_page)
    # Paginate items
    items_per_page = 10
    paginator = Paginator(orders , items_per_page)
    try:
        orders = paginator.page(page)
        print(orders)
    except PageNotAnInteger:
        orders = paginator.page(default_page)
        print(orders)
    except EmptyPage:
        orders = paginator.page(paginator.num_pages)
        print(orders)

    data = {
        'orders': orders,
    }
    return render(request, 'workforce/parts/lists/dl_list_all.html', data)




# DMS section  ------------------------------------------------------------------------------------------------------

