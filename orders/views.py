import json
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from datetime import datetime, timedelta, timezone

import pandas as pd
from django.contrib import messages
import requests

from core import models as core_models
from orders import forms, models as orders_models
from client import models as business_models
from orders import forms as orders_forms
# Create your views here.
from django.core.paginator import (
    Paginator,
    EmptyPage,
    PageNotAnInteger,
)

# orders---------------------------------------------------------------------------------------------------------------------


@login_required(login_url='account_login')
def orders_all_list(request):
    business = business_models.Business.objects.get(user_id=request.user.id)
    print(business, "business order list")
    items = orders_models.Order.objects.filter(
        business=business.business_id).order_by('-id')
    print('order_product_list')
    #print(orders.order_product_list)

    
    
    default_page = 1
    page = request.GET.get('page', default_page)
    # Paginate items
    items_per_page = 10
    paginator = Paginator(items , items_per_page)
    try:
        orders = paginator.page(page)
        print(orders)
    except PageNotAnInteger:
        orders = paginator.page(default_page)
        print(orders)
    except EmptyPage:
        orders = paginator.page(paginator.num_pages)
        print(orders)
    context = {
        'orders': orders,
        'business': business,
        'len': len(items)
    }
    return render(request, 'orders/orders_all_list.html', context)


@login_required(login_url='account_login')
def orders_pending_list(request):
    business = business_models.Business.objects.get(user_id=request.user.id)

    print(business, "business order list")
    orders = orders_models.Order.objects.filter(
        delivery_task__dl_task_status_dms__in=[ '4', '5', '6'], business=business.business_id
    ).order_by('-id')
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

    context = {
        'orders': orders,
        'business': business,
    }
    return render(request, 'orders/orders_pending_list.html', context)

@login_required(login_url='account_login')
def orders_successfull_list(request):
    business = business_models.Business.objects.get(user_id=request.user.id)

    print(business, "business order list")
    orders = orders_models.Order.objects.filter(
        delivery_task__dl_task_status_dms='2' , business=business.business_id
    ).order_by('-id')
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

    context = {
        'orders': orders,
        'business': business,
    }
    return render(request, 'orders/orders_successfull_list.html', context)


@login_required(login_url='account_login')
def orders_unsuccessfull_list(request):
    business = business_models.Business.objects.get(user_id=request.user.id)

    print(business, "business order list")
    orders = orders_models.Order.objects.filter(
        delivery_task__dl_task_status_dms__in=[ '7', '8', '9'], business=business.business_id
    ).order_by('-id')
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

    context = {
        'orders': orders,
        'business': business,
    }
    return render(request, 'orders/orders_unsuccessfull_list.html', context)


@login_required(login_url='account_login')
def latest_orders_list(request):
    business = business_models.Business.objects.get(user_id=request.user.id)

    print(business, "latest 10 order list")
    orders = orders_models.Order.objects.filter(
        business=business.business_id).order_by('-id')
    
    
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

    context = {
        'orders': orders,
        'business': business,
    }
    return render(request, 'orders/orders_list.html', context)

# order uploading section ----------------------------------------------------------------



def order_upload_file(request):
    if request.method == 'POST':
        form = orders_forms.OrderFileUploadForm(request.POST, request.FILES)
        if form.is_valid():
            file = request.FILES['file']
            if file.name.endswith('.csv'):
                data = pd.read_csv(file)
            elif file.name.endswith('.xlsx'):
                data = pd.read_excel(file)
            else:
                messages.error(request, 'Unsupported file format. Please upload a CSV or Excel file.')
                return redirect('orders:order_upload_file')
            
            request.session['uploaded_data'] = data.to_dict(orient='records')
            return redirect('orders:order_upload_review_data')
    else:
        form = orders_forms.OrderFileUploadForm()
    return render(request, 'orders/order_upload_file.html', {'form': form})

def order_upload_review_data(request):
    if 'uploaded_data' not in request.session:
        messages.error(request, 'No data to review. Please upload a file first.')
        return redirect('orders:order_upload_file')
    print(request.session['uploaded_data'])
    data = request.session['uploaded_data']

    if request.method == 'POST':
        print("post request")
        print(len(data))
        # Process edited data
        edited_data = []
        for i, row in enumerate(data):
            print("processing row {}".format(i))
            
            edited_row = {}
            for key in row.keys():
                field_name = f'data[{i}][{key}]'
                edited_row[key] = request.POST.get(field_name, row[key])
                print('edited_row')
                print(edited_row)
            edited_data.append(edited_row)
            print('edited_data')
            print(edited_data)
            for row in edited_data:
                print('row')
                print(row)
                order_form = orders_forms.AddOrderForm(row)
                if order_form.is_valid():
                    print("order_form is valid")
                    order_form.save()
                else:

                    messages.error(request, f'Error in row {i}: {order_form.errors}')
                    print(messages.error)
                    return redirect('orders:order_upload_review_data')
        
        del request.session['uploaded_data']
        messages.success(request, 'Data successfully uploaded to the database.')
        return redirect('orders:orders_all_list')

    return render(request, 'orders/order_upload_review.html', {'data': data})






# order creation ----------------------------------------------------------------

@login_required(login_url='account_login')
def add_order(request):
    business = business_models.Business.objects.get(
        user_id=request.user.id)
    pickup_locations = business_models.PickupLocation.objects.filter(
        business_id=request.user.id).all()

    print('pickup_locations : ', pickup_locations)
    if not pickup_locations:
        print("pickup_locations is None")
        return redirect('/business/pickup_location/add/')
    else:
        if request.method == 'POST':
            print("POST form in views")
            form = orders_forms.AddOrderForm(request.POST)
            #print(form)

            # @todo
            # form.fields['product_list'].queryset = orders_models.Items.objects.filter(
            #     business=request.user.business)
            if form.is_valid():
                print("valid form")
                order = form.save(commit=False)
                order.business = business_models.Business.objects.get(
                    business_id=request.user.id)

                print(order.business_id)


                order = form.save()
                print('order.id')
                print(order.id)
                
                return  redirect('orders:orders_all_list')
        else:
            print("load form")
            form = orders_forms.AddOrderForm(business_id=business.business_id)
    return render(request, 'orders/add_order.html', {'form': form, 'business': business, })


@login_required(login_url='account_login')
def order_update(request, order_id):
    order = orders_models.Order.objects.get(id=order_id)
    if request.method == 'POST':
        form = orders_forms.UpdateOrderForm(request.POST, instance=order)
        print('form valid checking')
        if form.is_valid():
            print('form valid')
            form.save()
            return  redirect('orders:orders_all_list')
    else:
        form = orders_forms.UpdateOrderForm(instance=order)

    context = {
        'form': form,
        'order': order,
        'order_id': order_id
    }
    return render(request, 'orders/order_update.html', context)


@login_required(login_url='account_login')
def delete_order(request, order_id):
    order = orders_models.Order.objects.get(id=order_id)
    print(order.business.user_id)
    if request.user.id == order.business.user_id:
        print("true")
        order.delete
    # order.delete()
    return  redirect('orders:orders_all_list')


@login_required(login_url='account_login')
def order_details(request, order_id):
    order = orders_models.Order.objects.get(id=order_id)
    data = {
        'order': order
    }
    return render(request, 'orders/order_details.html', data)


# add products to order
@login_required(login_url='account_login')
def add_order_product(request, order_id):
    order = orders_models.Order.objects.get(id=order_id)
    try:
        order_product_list = orders_models.OrderProductList.objects.get(order_id=order_id)
    except:
        order_product_list = orders_models.OrderProductList.objects.create(order_id=order_id)
    if request.method == 'POST':
            print("POST form in views")
            form = orders_forms.AddOrderProductsForm(request.POST, instance=order_product_list)
            #print(form)
            if form.is_valid():
                print("valid form")
                form.save()
                return  redirect('orders:orders_all_list')
    else:
        form = orders_forms.AddOrderProductsForm(instance=order_product_list)
        print('else form')
    data = {
        'order': order,
        'form': form
    }
    return render(request, 'orders/add_order_product.html', data)


@login_required(login_url='account_login')
def update_order_product(request, order_id):
    order = orders_models.Order.objects.get(id=order_id)
    try:
        order_product_list = orders_models.OrderProductList.objects.get(order_id=order_id)
    except:
        order_product_list = orders_models.OrderProductList.objects.create(order_id=order_id)
    if request.method == 'POST':
            print("POST form in views")
            form = orders_forms.AddOrderProductsForm(request.POST, instance=order_product_list)
            #print(form)
            if form.is_valid():
                print("valid form")
                form.save()
                return  redirect('orders:orders_all_list')
    else:
        form = orders_forms.AddOrderProductsForm(instance=order_product_list)
        print('else form')
    data = {
        'order': order,
        'form': form
    }
    return render(request, 'orders/update_order_product.html', data)

def order_product_list(request, order_id):
    order = get_object_or_404(orders_models.Order, id=order_id)
    print('order' + str(order))
    ordered_products = order.order_product_list.all()
    listed_product = []
    processed_order_products = []

    for ordered_product in ordered_products:
        product_list = []
        for field in orders_models.OrderProductList._meta.get_fields():
            if 'product' in field.name and 'name' in field.name:
                qty_field = field.name.replace('name', 'qty')
                product_name = getattr(ordered_product, field.name)
                product_qty = getattr(ordered_product, qty_field)
                if product_name and product_qty > 0:  # Filter out products with zero quantity
                    product_list.append({
                        'name': product_name,
                        'qty': product_qty
                    })
        if product_list:  # Only add non-empty product lists
            listed_product.append(product_list)
      
     


    print( ordered_products)
    print( listed_product)

    data = {
        'order': order,
        'ordered_products': ordered_products,
        'listed_product': listed_product,
    }
    return render(request, 'orders/parts/order_product_list.html', data)

# operation links

@require_POST
def update_order_status(request):
    if request.method == 'POST' and request.is_ajax():
        # Assuming you have a model named "YourModel" with a "status" field
        order_id = request.POST.get('order_id')
        print('update_order_status - view', order_id)
        status = request.POST.get('status')
        print(status)
        order = orders_models.Order.objects.get(pk=order_id)
        order.order_status = status
        print(order.order_status)
        order.save()

        # Return a JSON response indicating success
        return JsonResponse({'status': 'success'})

    # Return a JSON response indicating failure
    return JsonResponse({'status': 'error'})



#get_by_api from shopify

def get_order_by_api(request):
    headers = {
        'Content-Type': 'application/json',
        'X-Shopify-Access-Token': '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'
    }
    get_orders = requests.get('https://hn0d1z-qe.myshopify.com/admin/api/2024-10/orders.json?status=any', headers=headers)
    # Parse message as json
    GetQuestion_response = "json.loads(GetQuestion_response['Message'])"
    print(request.POST.get('start_date'))
    if request.method == 'POST':
        order_list_start_date = request.POST.get('start_date')
        order_list_end_date = request.POST.get('end_date')
        print( "posted dates")
    else:
        order_list_start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        order_list_end_date = datetime.now().strftime('%Y-%m-%d')
        print( "default dates")
    
    print(order_list_start_date)
    print(order_list_end_date)

    if get_orders.status_code == 200:
        order_data = get_orders.json()
        orders = order_data.get('orders', [])
        filtered_orders = [
            order for order in orders
            if order_list_start_date <= order['created_at'][:10] <= order_list_end_date
        ]
        filtered_orders.sort(key=lambda x: x['created_at'], reverse=True)
        
        data={
            'GetQuestion_response' : GetQuestion_response,
            "order_data": order_data,
            "orders": orders
        }
        return render(request, 'orders\get_order_by_api.html', data)
    else:
        return JsonResponse({'status': 'error', 'message': 'Failed to fetch orders from Shopify'})







