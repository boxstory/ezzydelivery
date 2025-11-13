import json
import logging
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from datetime import datetime, timedelta, timezone
from django.forms import inlineformset_factory
import pandas as pd
from django.contrib import messages
import requests
from woocommerce import API as WooAPI
from decouple import config

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

logger = logging.getLogger('orders')

# orders---------------------------------------------------------------------------------------------------------------------


@login_required(login_url='account_login')
def orders_all_list(request):
    # Get user's business (with authorization check)
    try:
        business = business_models.Business.objects.get(user_id=request.user.id)
        logger.info(f"User {request.user.id} accessing orders list for business {business.business_id}")
    except business_models.Business.DoesNotExist:
        logger.warning(f"User {request.user.id} has no associated business")
        messages.error(request, "No business associated with your account")
        return redirect('business_dashboard')

    # FIX: Use select_related for ForeignKeys and prefetch_related for reverse relations
    items = orders_models.Order.objects.filter(
        business=business.business_id
    ).select_related(
        'business',              # FK: Order → Business
        'pickup_location',       # FK: Order → PickupLocation
        'address_verified_by',   # FK: Order → User (address verifier)
        'verified_by',           # FK: Order → User (order verifier)
    ).prefetch_related(
        'order_product_list',          # Reverse FK: Order ← OrderProductList
        'delivery_task',               # Reverse FK: Order ← DeliveryTask
        'delivery_task__driver',       # Through: DeliveryTask → Driver
        'delivery_task__business',     # Through: DeliveryTask → Business
    ).order_by('-id')

    logger.debug(f"Fetching orders for business {business.business_id}")

    default_page = 1
    page = request.GET.get('page', default_page)
    # Paginate items
    items_per_page = 10  # Increased from 5 for better UX
    paginator = Paginator(items, items_per_page)

    try:
        orders = paginator.page(page)
        logger.debug(f"Displaying page {page} with {len(orders)} orders")
    except PageNotAnInteger:
        orders = paginator.page(default_page)
        logger.debug(f"Invalid page number, displaying page {default_page}")
    except EmptyPage:
        orders = paginator.page(paginator.num_pages)
        logger.debug(f"Empty page, displaying last page {paginator.num_pages}")

    context = {
        'orders': orders,
        'business': business,
        'len': items.count()  # Use .count() instead of len() for better performance
    }
    return render(request, 'orders/orders_all_list.html', context)


@login_required(login_url='account_login')
def orders_pending_list(request):
    # Get user's business (with authorization check)
    try:
        business = business_models.Business.objects.get(user_id=request.user.id)
        logger.info(f"User {request.user.id} accessing pending orders for business {business.business_id}")
    except business_models.Business.DoesNotExist:
        logger.warning(f"User {request.user.id} has no associated business")
        messages.error(request, "No business associated with your account")
        return redirect('business_dashboard')

    # FIX: Optimize with select_related and prefetch_related
    orders = orders_models.Order.objects.filter(
        delivery_task__dl_task_status_dms__in=['4', '5', '6'],
        business=business.business_id
    ).select_related(
        'business',
        'pickup_location',
        'address_verified_by',
        'verified_by',
    ).prefetch_related(
        'order_product_list',
        'delivery_task',
        'delivery_task__driver',
        'delivery_task__business',
    ).order_by('-id')

    logger.debug(f"Fetching pending orders for business {business.business_id}")

    default_page = 1
    page = request.GET.get('page', default_page)
    # Paginate items
    items_per_page = 10
    paginator = Paginator(orders, items_per_page)

    try:
        orders = paginator.page(page)
        logger.debug(f"Displaying page {page} with {len(orders)} pending orders")
    except PageNotAnInteger:
        orders = paginator.page(default_page)
        logger.debug(f"Invalid page number, displaying page {default_page}")
    except EmptyPage:
        orders = paginator.page(paginator.num_pages)
        logger.debug(f"Empty page, displaying last page {paginator.num_pages}")

    context = {
        'orders': orders,
        'business': business,
    }
    return render(request, 'orders/orders_pending_list.html', context)

@login_required(login_url='account_login')
def orders_successfull_list(request):
    # Get user's business (with authorization check)
    try:
        business = business_models.Business.objects.get(user_id=request.user.id)
        logger.info(f"User {request.user.id} accessing successful orders for business {business.business_id}")
    except business_models.Business.DoesNotExist:
        logger.warning(f"User {request.user.id} has no associated business")
        messages.error(request, "No business associated with your account")
        return redirect('business_dashboard')

    # FIX: Optimize with select_related and prefetch_related
    orders = orders_models.Order.objects.filter(
        delivery_task__dl_task_status_dms='2',
        business=business.business_id
    ).select_related(
        'business',
        'pickup_location',
        'address_verified_by',
        'verified_by',
    ).prefetch_related(
        'order_product_list',
        'delivery_task',
        'delivery_task__driver',
        'delivery_task__business',
    ).order_by('-id')

    logger.debug(f"Fetching successful orders for business {business.business_id}")

    default_page = 1
    page = request.GET.get('page', default_page)
    # Paginate items
    items_per_page = 10
    paginator = Paginator(orders, items_per_page)

    try:
        orders = paginator.page(page)
        logger.debug(f"Displaying page {page} with {len(orders)} successful orders")
    except PageNotAnInteger:
        orders = paginator.page(default_page)
        logger.debug(f"Invalid page number, displaying page {default_page}")
    except EmptyPage:
        orders = paginator.page(paginator.num_pages)
        logger.debug(f"Empty page, displaying last page {paginator.num_pages}")

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
        business=business.business_id).order_by('-id')[:5]
    
    
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
    return render(request, 'orders/orders_list_view.html', context)

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
    
    business = business_models.Business.objects.get(user_id=request.user.id)
    context = {
        'form': form,
        'business': business
    }
    return render(request, 'orders/order_upload_file.html',  context)

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
    print(business.business_id)
    pickup_locations = business_models.PickupLocation.objects.filter(
        business_id=business.business_id).all()

    print('pickup_locations : ', pickup_locations)
    if not pickup_locations:
        print("pickup_locations is None")
        return redirect('client:pickup_location_add')
    else:
        if request.method == 'POST':
            print("POST form in views")
            form = orders_forms.AddOrderForm(request.POST)
            
            if form.is_valid():
                print("valid form")
                order = form.save(commit=False)
                order.business = business_models.Business.objects.get(
                    business_id=business.business_id)
                print(order.business_id)
                order = form.save()
                print('order.id')
                print(order.id)
                return  redirect('orders:add_order_product', order_id=order.id)
        else:
            print("load add_order form")
            form = orders_forms.AddOrderForm(business_id=business.business_id)
    return render(request, 'orders/add_order.html', {'form': form, 'business': business, })




# add products to order
@login_required(login_url='account_login')
def add_order_product(request, order_id):
    try:
        # IDOR FIX: Verify order belongs to user's business
        business = business_models.Business.objects.get(user_id=request.user.id)
        order = orders_models.Order.objects.get(id=order_id, business=business)

        logger.info(f"User {request.user.id} adding products to order {order_id}")

        try:
            order_product_list = orders_models.OrderProductList.objects.get(order_id=order_id)
        except orders_models.OrderProductList.DoesNotExist:
            order_product_list = orders_models.OrderProductList.objects.create(order_id=order_id)

        if request.method == 'POST':
            logger.info(f"Processing product addition for order {order_id}")
            form = orders_forms.AddOrderProductsForm(request.POST, instance=order_product_list)

            if form.is_valid():
                logger.info(f"Products added successfully to order {order_id}")
                form.save()
                messages.success(request, "Products added to order successfully")
                return redirect('orders:orders_all_list')
            else:
                logger.warning(f"Invalid product form for order {order_id}: {form.errors}")
        else:
            form = orders_forms.AddOrderProductsForm(instance=order_product_list)

        data = {
            'order': order,
            'form': form,
            'business': business
        }
        return render(request, 'orders/add_order_product.html', data)

    except orders_models.Order.DoesNotExist:
        logger.warning(f"Order {order_id} not found or unauthorized access by user {request.user.id}")
        messages.error(request, "Order not found")
        return redirect('orders:orders_all_list')
    except business_models.Business.DoesNotExist:
        logger.error(f"Business not found for user {request.user.id}")
        messages.error(request, "Business not found")
        return redirect('business:business_dashboard')



#AddOrderWithProduct
def add_order_with_product(request):
    business = business_models.Business.objects.get(
        user_id=request.user.id)
    OrderFormset = inlineformset_factory(orders_models.Order, orders_models.OrderProductList, form=orders_forms.AddOrderProductsForm, extra=1)
    if request.method == 'POST':
        order_product_formset = OrderFormset(queryset=orders_models.OrderProductList.objects.none())
        
        
            
        if order_product_formset.is_valid():
                order_product_formset.save()
                
                return redirect('orders:orders_all_list')
    
    else:
        
        order_product_formset = OrderFormset(queryset=orders_models.OrderProductList.objects.none())
        
    
    context = {
        'business' :  business,
        
        'order_product_formset': order_product_formset,
    }
    return render(request, 'orders/add_order_with_product.html', context)
    








#costumer side*********************************************************************


@login_required(login_url='account_login')
def deliver_to_here(request, pickup_id):
    pickup_location = business_models.PickupLocation.objects.filter(
        id=pickup_id).first()
    if request.method == 'POST':
        form = orders_forms.UpdateOrderForm(request.POST, )
        print('form valid checking')
        if form.is_valid():
            print('form valid')
            form.save()
            form.business = business_models.Business.objects.get(
                    business_id=request.user.id)
            return  redirect('orders:orders_all_list')
    else:
        form = orders_forms.UpdateOrderForm()

    context = {
        'form': form, 
    }
    return render(request, 'orders/order_update.html', context)

@login_required(login_url='account_login')
def order_update(request, order_id):
    try:
        # IDOR FIX: Verify order belongs to user's business
        business = business_models.Business.objects.get(user_id=request.user.id)
        order = orders_models.Order.objects.get(id=order_id, business=business)

        logger.info(f"User {request.user.id} updating order {order_id}")

        if request.method == 'POST':
            form = orders_forms.UpdateOrderForm(request.POST, instance=order)

            if order.task_status == 'dl_task_listed':
                logger.warning(f"Cannot update order {order_id} - already published in delivery tasks")
                messages.error(request, 'Cannot update order published in Delivery Tasks. Contact Operation Admin')
                return redirect('orders:orders_all_list')

            if form.is_valid():
                logger.info(f"Order {order_id} updated successfully")
                form.save()
                messages.success(request, 'Order updated successfully.')
                return redirect('orders:orders_all_list')
            else:
                logger.warning(f"Invalid order update form for order {order_id}: {form.errors}")
        else:
            form = orders_forms.UpdateOrderForm(instance=order)

        context = {
            'form': form,
            'order': order,
            'order_id': order_id
        }
        return render(request, 'orders/order_update.html', context)

    except orders_models.Order.DoesNotExist:
        logger.warning(f"Order {order_id} not found or unauthorized access by user {request.user.id}")
        messages.error(request, "Order not found")
        return redirect('orders:orders_all_list')
    except business_models.Business.DoesNotExist:
        logger.error(f"Business not found for user {request.user.id}")
        messages.error(request, "Business not found")
        return redirect('business:business_dashboard')


@login_required(login_url='account_login')
def delete_order(request, order_id):
    try:
        # IDOR FIX: Verify order belongs to user's business
        business = business_models.Business.objects.get(user_id=request.user.id)
        order = orders_models.Order.objects.get(id=order_id, business=business)

        logger.info(f"User {request.user.id} deleting order {order_id}")
        order.delete()
        logger.info(f"Order {order_id} deleted successfully")
        messages.success(request, "Order deleted successfully")
        return redirect('orders:orders_all_list')

    except orders_models.Order.DoesNotExist:
        logger.warning(f"Order {order_id} not found or unauthorized access by user {request.user.id}")
        messages.error(request, "Order not found")
        return redirect('orders:orders_all_list')
    except business_models.Business.DoesNotExist:
        logger.error(f"Business not found for user {request.user.id}")
        messages.error(request, "Business not found")
        return redirect('business:business_dashboard')


@login_required(login_url='account_login')
def order_details(request, order_id):
    try:
        # IDOR FIX: Verify order belongs to user's business
        business = business_models.Business.objects.get(user_id=request.user.id)
        order = orders_models.Order.objects.select_related(
            'business', 'pickup_location', 'address_verified_by', 'verified_by'
        ).get(id=order_id, business=business)

        logger.info(f"User {request.user.id} viewing order details for order {order_id}")

        data = {
            'order': order
        }
        return render(request, 'orders/order_details.html', data)

    except orders_models.Order.DoesNotExist:
        logger.warning(f"Order {order_id} not found or unauthorized access by user {request.user.id}")
        messages.error(request, "Order not found")
        return redirect('orders:orders_all_list')
    except business_models.Business.DoesNotExist:
        logger.error(f"Business not found for user {request.user.id}")
        messages.error(request, "Business not found")
        return redirect('business:business_dashboard')




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

@login_required(login_url='account_login')
def get_order_by_api(request):
    # IDOR FIX: Get user's business with authorization check
    try:
        user_business = request.user.user_business.first()
        if not user_business:
            logger.warning(f"User {request.user.id} has no associated business")
            messages.error(request, "No business associated with your account")
            return redirect('business_dashboard')

        business = business_models.Business.objects.get(user_id=user_business.user_id)
    except business_models.Business.DoesNotExist:
        logger.warning(f"Business not found for user {request.user.id}")
        messages.error(request, "Business not found")
        return redirect('business_dashboard')

    api_data = business_models.BusinessApiSettings.objects.filter(
        business_id=business.business_id,
        is_verify_api='True',
        is_default='True'
    ).first()

    if not api_data:
        logger.warning(f"No API settings found for business {business.business_id}")
        messages.error(request, "No API configuration found. Please configure your Shopify API settings.")
        return redirect('business_settings')

    logger.debug(f"Using API settings for business {business.business_id}")

    # SECURITY FIX: Use environment variable for Shopify token instead of hardcoded value
    shopify_token = config('SHOPIFY_ACCESS_TOKEN', default='')
    if not shopify_token:
        logger.error("SHOPIFY_ACCESS_TOKEN not configured in .env file")
        messages.error(request, "Shopify API token not configured")
        return redirect('business_settings')

    headers = {
        'Content-Type': 'application/json',
        'X-Shopify-Access-Token': shopify_token
    }

    try:
        get_orders = requests.get('https://hn0d1z-qe.myshopify.com/admin/api/2024-10/orders.json?status=any', headers=headers, timeout=30)
    except requests.exceptions.RequestException as e:
        logger.error(f"Shopify API request failed: {e}")
        messages.error(request, "Failed to connect to Shopify API")
        return redirect('orders_all_list')
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
            'order_data': order_data,
            'orders': orders,
            'business': business,


        }
        return render(request, 'orders\get_order_by_api.html', data)
    else:
        return JsonResponse({'status': 'error', 'message': 'Failed to fetch orders from Shopify'})


@login_required(login_url='account_login')
def get_orders_by_base_api(request):
    # IDOR FIX: Get user's business with authorization check
    try:
        user_business = request.user.user_business.first()
        if not user_business:
            logger.warning(f"User {request.user.id} has no associated business")
            messages.error(request, "No business associated with your account")
            return redirect('business_dashboard')

        business = business_models.Business.objects.get(user_id=user_business.user_id)
        business_id = business.business_id
    except business_models.Business.DoesNotExist:
        logger.warning(f"Business not found for user {request.user.id}")
        messages.error(request, "Business not found")
        return redirect('business_dashboard')

    business_api = business_models.BusinessApiSettings.objects.filter(
        business_id=business_id,
        is_verify_api='True',
        is_default='True'
    ).first()

    if not business_api:
        logger.warning(f"No API settings found for business {business_id}")
        messages.error(request, "No API configuration found")
        return redirect('business:business_settings_api_list', business_id)

    logger.info(f"Fetching orders via {business_api.api_type} API for business {business_id}")
     

    BASE_API_KEY = business_api.api_key
    BASE_API_ACCESS_KEY = business_api.api_access_token
    BASE_API_SECRET = business_api.api_secret
    BASE_API_STORE_NAME = business_api.site_api_url
    BASE_API_ORDER_ENDPINT = business_api.order_api_endpoint
    BASE_API_PRODUCT_ENDPINT = business_api.product_api_endpoint

    BASE_API_STORE_NAME = BASE_API_STORE_NAME.replace('https://', '')


    if business_api.api_type == 'shopify':
        shop_creds = {
            'api_key': BASE_API_KEY,
            'api_secret': BASE_API_SECRET,
            'access_token': BASE_API_ACCESS_KEY, 
        }

        with open('shopify_creds.json', 'w') as f:
            json.dump(shop_creds, f)

        shop_url = "%s" % BASE_API_STORE_NAME
        print('shopify shop_url', shop_url)

        order_base_url = 'https://' + shop_url + BASE_API_ORDER_ENDPINT
        product_base_url = 'https://' + shop_url + BASE_API_PRODUCT_ENDPINT
        header_value = { 'X-Shopify-Access-Token': BASE_API_ACCESS_KEY, 'Content-Type': 'application/json' }

        order_response = requests.get(order_base_url, headers=header_value, params={'status': 'any', 'limit': 10})
        order_count = len(order_response.json().get('orders', []))

        print('order_count', order_count    )
        product_response = requests.get(product_base_url, headers=header_value )
        product_count = len(product_response.json().get('products', []))
        print('product_count', product_count)

    elif business_api.api_type == 'woocommerce':
        url="http://example.com",
        shop_url = 'https://' + BASE_API_STORE_NAME 
        print('woocommerce shop_url', shop_url)
 
        wcapi = WooAPI(
            url= shop_url,
            consumer_key= BASE_API_KEY,
            consumer_secret= BASE_API_SECRET,
            version="wc/v3",
        )

        
        #print(wcapi.get("products", params={"per_page": 20}).json())

        order_response = wcapi.get("orders")
        order_date = order_response.headers.get('Date')
        print('order_date', order_date)
        order_count = order_response.headers.get('X-WP-Total')
        print('order_count', order_count)
        product_response = wcapi.get("products", params={"per_page": 20})
        product_count = product_response.headers.get('X-WP-Total')
        print('product_count', product_count)
 
    else:
        order_response = None
        product_response = None


    start_date = (datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d')
    end_date = datetime.now().strftime('%Y-%m-%d')
    print('start_date', start_date)
    print('end_date', end_date)

    try:
        if order_response.status_code == 200:
            orders = []
            response_data = order_response.json()

            # Handle different API response formats
            if business_api.api_type == 'shopify':
                # Shopify wraps orders in {'orders': [...]}
                order_list = response_data.get('orders', []) if isinstance(response_data, dict) else []
            elif business_api.api_type == 'woocommerce':
                # WooCommerce returns orders directly as a list
                order_list = response_data if isinstance(response_data, list) else []
            else:
                order_list = []

            for order in order_list:
                print('order in order_response', order)

                # Extract customer info safely
                try:
                    if business_api.api_type == 'shopify':
                        customer_id = order.get('customer', {}).get('id')
                        if customer_id:
                            customer_response = requests.get(
                                f'https://{shop_url}/admin/api/2024-01/customers/{customer_id}.json',
                                headers=header_value
                            )
                            if customer_response.status_code == 200:
                                customer_data = customer_response.json().get('customer', {})
                                customer_info = {
                                    'first_name': customer_data.get('first_name', ''),
                                    'last_name': customer_data.get('last_name', ''),
                                    'email': customer_data.get('email', ''),
                                    'address': customer_data.get('default_address', {}).get('address1', '')
                                }
                            else:
                                customer_info = {
                                    'first_name': '',
                                    'last_name': '',
                                    'email': '',
                                    'address': ''
                                }
                        else:
                            customer_info = {
                                'first_name': '',
                                'last_name': '',
                                'email': '',
                                'address': ''
                            }
                    elif business_api.api_type == 'woocommerce':
                        # WooCommerce includes customer info in order
                        billing = order.get('billing', {})
                        customer_info = {
                            'first_name': billing.get('first_name', ''),
                            'last_name': billing.get('last_name', ''),
                            'email': billing.get('email', ''),
                            'address': f"{billing.get('address_1', '')} {billing.get('address_2', '')}".strip()
                        }
                    else:
                        customer_info = {
                            'first_name': '',
                            'last_name': '',
                            'email': '',
                            'address': ''
                        }

                    orders.append({
                        'id': order.get('id'),
                        'created_at': order.get('date_created') if business_api.api_type == 'woocommerce' else order.get('created_at'),
                        'payment_gateway_names': order.get('payment_method') if business_api.api_type == 'woocommerce' else order.get('payment_gateway_names'),
                        'total_price': order.get('total'),
                        'current_total_price': order.get('total'),
                        'currency': order.get('currency'),
                        'customer_info': customer_info,
                        'line_items': [
                            {
                                'title': item.get('name') if business_api.api_type == 'woocommerce' else item.get('title'),
                                'quantity': item.get('quantity'),
                                'price': item.get('price')
                            } for item in order.get('line_items', [])
                        ],
                    })
                except Exception as item_error:
                    logger.error(f"Error processing order item: {str(item_error)}")
                    continue

        else:
            logger.error(f"API returned status code: {order_response.status_code}")
            messages.error(request, f"API error: {order_response.status_code}")
            return redirect('business:business_settings_api_list', business_id)

        result = order_response.json()
        status = order_response.status_code
        context = {
            'business': business,
            'api': business_api,
            'orders': orders,
            'status': status,
            'result': result,
        }
        return render(request, 'orders\orders_api_list.html', context)

    except Exception as e:
        logger.error(f"Error fetching orders: {str(e)}")
        messages.error(request, f"Failed to fetch orders: {str(e)}")
        return redirect('business:business_settings_api_list', business_id)

# Location Verification View
def verify_location(request, token):
    """
    Public view for customers to verify their delivery location
    """
    from orders.models import AddressVerification
    from django.utils import timezone
    
    try:
        # Get address verification by token
        address_verification = get_object_or_404(
            AddressVerification,
            verification_token=token
        )
        
        # Check if token is expired
        if address_verification.is_token_expired():
            return render(request, 'orders/verification_expired.html', {
                'order': address_verification.order
            })
        
        order = address_verification.order
        
        if request.method == 'POST':
            # Get form data
            latitude = request.POST.get('latitude')
            longitude = request.POST.get('longitude')
            verified_address = request.POST.get('verified_address')
            zone_number = request.POST.get('zone_number')
            street_number = request.POST.get('street_number')
            building_number = request.POST.get('building_number')
            notes = request.POST.get('notes')
            
            # Update address verification
            address_verification.latitude = latitude
            address_verification.longitude = longitude
            address_verification.verified_address = verified_address or address_verification.original_address
            address_verification.zone_number = zone_number if zone_number else None
            address_verification.street_number = street_number if street_number else None
            address_verification.building_number = building_number if building_number else None
            address_verification.notes = notes
            address_verification.verification_result = 'address_verified'
            address_verification.customer_verified_at = timezone.now()
            address_verification.save()
            
            # Update order verification status
            order.verification_status = 'address_verified'
            order.save()
            
            return render(request, 'orders/verification_success.html', {
                'order': order
            })
        
        # GET request - show verification form with map
        context = {
            'order': order,
            'address_verification': address_verification,
            'google_maps_api_key': config('GOOGLE_MAPS_API_KEY', default=''),
        }
        
        return render(request, 'orders/verify_location.html', context)
        
    except Exception as e:
        logger.error(f"Error in location verification: {str(e)}")
        return render(request, 'orders/verification_error.html', {
            'error': 'Invalid or expired verification link'
        })
