import binascii
from multiprocessing import context
import os
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from decouple import config
from django.core.files.storage import default_storage
from PIL import Image
import numpy as np
import requests, json
import shopify
from woocommerce import API as WooAPI

from client import models as business_models
from core import models as core_models
from ezzydelivery.settings import BASE_DIR
from orders import models as orders_models

from client import forms as business_forms
from datetime import datetime

# Create your views here.


# dashboard---------------------------------------------------------------------------------------------------------------------


@login_required(login_url='account_login')
def business_dashboard(request):
    print('business id', request.user.user_business.first().business_id)
    try:
        business = business_models.Business.objects.get(
            business_id=request.user.user_business.first().business_id)
        print('business', business)
        print('business.id', business.business_id)
        
        profile = core_models.Profile.objects.get(user_id=business.user_id)
        business_profile = business_models.BusinessProfile.objects.get_or_create(business_id=business.business_id)
        location = business_models.PickupLocation.objects.filter(
            business_id=business.business_id).all()
        
        orders = orders_models.Order.objects.filter(
            business=business.business_id).order_by('-id')[:10]

        print(business)

        context = {
            'profile': profile,
            'business': business,
            'business_profile': business_profile,
            'location': location,
            'orders': orders,
        }
        return render(request, 'client/business_dashboard.html', context)
    except business_models.Business.DoesNotExist:
        return redirect('core:main_dashboard')

# Driver contact list of business---------------------------------------------------------------------------------------------------------------------


def driver_directory(request):
    business = business_models.Business.objects.get(
        user_id=request.user.id)
    driver_directory = business_models.DriverDirectory.objects.filter(
        business_id=request.user.id).all()

    context = {
        'contacts': driver_directory,
        'business': business,
    }
    return render(request, 'client/parts/driver_directory.html', context)


# @todo:  fleet already added warning not showing
def driver_directory_add(request):

    form = business_forms.DriverDirectoryAddForm(request.POST or None)
    if request.method == 'POST':
        # Process the form data and save to the database
        # Example: Assuming the contact information is in the request.POST['contact_info']
        driver_id = request.POST['driver_id']
        print('driver_info', driver_id)
        business_id = request.user.id
        print('business_id', business_id)
        dict = business_models.DriverDirectory.objects.filter(business=business_id)
        print('dict')
        print(dict)
        # Save the contact to the database or perform any other necessary actions
        if not business_models.DriverDirectory.objects.filter(business_id=business_id, driver_id=driver_id).exists():

            # Create a new FavoriteItem record
            business_models.DriverDirectory.objects.create( business_id=business_id, driver_id=driver_id)
            return JsonResponse({'success': True, 'success': 'Driver Added'})
            # Return a JSON response indicating success
        else:
            pass
            print('already exists')
            return JsonResponse({'success': False, 'error': 'Driver Already Added'})

    # If the request method is not POST, return an error
    return JsonResponse({'success': False, 'error': 'Invalid request method'})


def driver_directory_delete(request, id):
    fleet = business_models.DriverDirectory.objects.get(id=id)
    print(fleet)
    fleet.delete()
    return redirect('core:main_dashboard')


# pickup location add------------------------------------------------------
@login_required(login_url='account_login')
def pickup_location_list(request):
    business = business_models.Business.objects.get(
        business_id=request.user.user_business.first().business_id)
    pickup_location = business_models.PickupLocation.objects.filter(
        business_id=business.business_id).all()
    if not pickup_location:
        return redirect('business:pickup_location_add')
    print('pickup_location', pickup_location)
    context = {
        'stores': pickup_location,
        'business': business, }
    return render(request, 'client/parts/pickup_location_list.html', context)


def pickup_location_add(request):

    business = business_models.Business.objects.get(
        business_id=request.user.user_business.first().business_id)
    form = business_forms.PickupLocationsAddForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            pickup_location = form.save(commit=False)
            pickup_location.business_id = business_models.Business.objects.get(
                user_id=request.user.id).business_id
            print(pickup_location.business)
            form.save()
            messages.success(request, "Successful Submission")
            return redirect("business:pickup_location_list")

    context = {
        'form': form,
        'business': business,
    }
    return render(request, 'client/parts/pickup_location_add.html', context)


def pickup_location_delete(request, pickup_location_id):
    pickup_location = business_models.PickupLocation.objects.get(
        id=pickup_location_id)
    pickup_location.delete()
    return redirect("business:pickup_location_list")


def pickup_location_update(request, pickup_location_id):
    business = business_models.Business.objects.get(
        business_id=request.user.user_business.first().business_id)
    id = pickup_location_id
    print(pickup_location_id)
    print('pickup_location_update')
    pickup_location = get_object_or_404(
        business_models.PickupLocation, id=pickup_location_id)
    print(pickup_location)
    print(pickup_location.pickup_zone_no)
    form = business_forms.PickupLocationsAddForm(
        request.POST or None, instance=pickup_location)
    if request.method == 'POST':
        if form.is_valid():
            print('pickup_location_update valid')
            form.save()
            return redirect("business:pickup_location_list")

    context = {
        'business' : business,
        'form': form,
        'id': id,

    }
    return render(request, 'client/parts/pickup_location_update.html', context)

# frontend ---------------------------------------------------------------------------------------------------------------------


def business_profile(request):
    try:
        business = business_models.Business.objects.get(
            business_id=request.user.user_business.first().business_id)
        profile = core_models.Profile.objects.filter(user_id=request.user.id)
        business_profile = business_models.BusinessProfile.objects.get_or_create(business_id = business.business_id )
        business_profile = business_profile[0]
        #print('business_profile', business_profile)
        location = business_models.PickupLocation.objects.filter(
            business_id=business.business_id).values_list('pickup_location_title', flat=True)[:2]
        business_logo = business_models.BusinessLogo.objects.select_related('business').get_or_create(business_id = business.business_id )
        instakey = config("INSTAGRAM_TOKEN_FEEDS_KEY")
        business_logo = business_logo[0].business_logo.url


        context = {
            'profile': profile,
            'business': business,
            'location': location,
            'business_profile': business_profile,
            'business_logo_img': business_logo,
            'instakey': instakey,
        }
        return render(request, 'client/frontend/business_profile.html', context)
    except business_models.Business.DoesNotExist:

        return redirect("/join_us/")

def business_profile_display(request, business_id):
    try:
        business = business_models.Business.objects.get(
            business_id=business_id)
        location = business_models.PickupLocation.objects.filter(
            business_id=business.business_id).values_list('pickup_location_title', flat=True)[:2]
        business_logo = business_models.BusinessLogo.objects.select_related('business').get(business_id = business.business_id )
        business_logo = business_logo.business_logo.url


        context = {
            'business': business,
            'location': location,
            'business_logo_img': business_logo,
        }
        return render(request, 'client/frontend/business_profile.html', context)
    except business_models.Business.DoesNotExist:
        
        return redirect("/profile/")


def all_business(request):
    business = business_models.Business.objects.all()
    
    

    context = {
        'all_business': business,
    }
    return render(request, 'client/frontend/all_business.html', context)

#business_settings---------------------------------------------------------------------------------------------------------------------


def business_profile_update(request, business_id):
    print('business_profile_update')
    print('request.user.id', request.user.id)
    print('business_id', business_id)
    if request.user.user_business.first().business_id == business_id:
        print(':matched')
        redirect('core:main_dashboard')
        print('business_profile_update', business_id)
        print('request.user.id', request.user.id)
        business =  business_models.Business.objects.get(
        business_id=request.user.user_business.first().business_id)
        print('business', business)
        print('business.business_id', business.business_id)
        form = business_forms.businessRegisterForm(instance=business)
        print('form')
        if request.method == 'POST':
            print('businessRegisterForm')
            form = business_forms.businessRegisterForm(
                request.POST, request.FILES, instance=business)
            if form.is_valid():
                f = form.save(commit=False)
                print('f.user')

                print(f.user)

                form.save()
                print('ok')
                messages.success(request, "Successful Submission")
                return redirect("business:business_dashboard")
            else:
                print('driver_directory_add not valid')
                messages.error(request, "Error")
        context = {
            'form': form,
            'business_id': business.business_id
        }

        return render(request, 'client/frontend/business_profile_update.html', context)
    else:
        return redirect("business:business_dashboard")



def business_profile_info_update(request, business_id):
    if request.user.user_business.first().business_id == business_id:
        print(':matched')
        redirect('core:main_dashboard')
        print('business_profile_update', business_id)
        print('request.user.id', request.user.id)
        business =  business_models.Business.objects.get(
        business_id=request.user.user_business.first().business_id)
        business_profile =  business_models.BusinessProfile.objects.get(business_id=business_id)

        print('business', business)
        print('business.business_id', business.business_id)
        form = business_forms.BusinessProfileForm(instance=business_profile)
        print('form')
        if request.method == 'POST':
            print('BusinessProfileForm')
            form = business_forms.BusinessProfileForm(
                request.POST,   instance=business_profile)
            if form.is_valid():
                f = form.save(commit=False)
                print('f.user')
                website = f.business_website

                if website and isinstance(website, str) and  not website.startswith('https://') and not website.startswith('http://'):
                    f.business_website = 'https://' + website
                elif website and isinstance(website, str) and  website.startswith('http://'):
                    f.business_website = 'https://' + website
                else:
                    f.business_website = website
                

                print(f.business_id)
                f.business_id = business_id

                form.save()
                print('ok')
                messages.success(request, "Successful Submission")
                return redirect("business:business_profile")
            else:
                print('business_profile_info_update not valid')
                messages.error(request, "Error")
        context = {
            'form': form,
            'business': business,
            'business_profile' : business_profile,
        }

        return render(request, 'client/frontend/business_profile_update.html', context)
    else:
        return redirect("business:business_profile")


# business settings links and veirfy status ---------------------------------------------------------------------------------------------------------------------
def business_settings(request, business_id):
    business =  business_models.Business.objects.filter(business_id=business_id).first()
    business_apis = business_models.BusinessApiSettings.objects.filter(business_id=business_id)

    teams = business_models.BusinessTeamProfile.objects.filter(business_id=business_id).all()
    stores = business_models.PickupLocation.objects.filter(business_id=business_id).all()
    print('business', business)
    print('business_apis', business_apis)
    print('teams', teams)
    print('stores', stores)

    
    

    context = {
        'business': business,
        'business_apis': business_apis,
        'teams': teams,
        'stores': stores,

    }
    return render(request, 'client/parts/business_settings.html', context)


#business_settings_api---------------------------------------------------------------------------------------------------------------------
def business_settings_api_update(request, business_id, api_id ):
    if request.user.id == request.user.user_business.first().user_id:
        
        business =  business_models.Business.objects.filter(business_id=business_id).first()
        business_apis = business_models.BusinessApiSettings.objects.filter(id=api_id).first()
        form = business_forms.businessApiSettingsForm(instance=business_apis)
        form.fields['business'].queryset = business_models.Business.objects.filter(business_id=request.user.user_business.first().business_id)
        
        if request.method == 'POST':
            print('businessSettingsFormUpdate')
            form = business_forms.businessApiSettingsForm(
                request.POST, instance=business_apis)
            
            if form.is_valid():
                f = form.save(commit=False)
                if f.is_verify_api == True:
                    f.is_verify_api = False

                form.save()
                print('businessSettingsForm Update ok')
                messages.success(request, "Successful Submission")
                return redirect("business:business_settings", business_id)
            else:
                print('businessSettingsForm_update not valid')
                messages.error(request, "Error")
        context = {
            'business': business,
            'form': form,
            'api_id': api_id,

            'form_title': 'Business API Settings Add'
        }

        return render(request, 'client/parts/business_settings_api_update.html', context)
    else:
        return redirect("business:business_dashboard")



def business_settings_api_add(request, business_id):
    if request.user.id == request.user.user_business.first().user_id:
        
        business =  business_models.Business.objects.filter(business_id=business_id).first()
        business_apis = business_models.BusinessApiSettings.objects.filter(business_id=business_id)
        form = business_forms.businessApiSettingsForm()
        form.fields['business'].queryset = business_models.Business.objects.filter(business_id=request.user.user_business.first().business_id)
        
        if request.method == 'POST':
            print('businessSettingsForm')
            form = business_forms.businessApiSettingsForm(
                request.POST)
            
            if form.is_valid():
                f = form.save(commit=False)

                
                form.save()
                print('businessSettingsForm ok')
                messages.success(request, "Successful Submission")
                return redirect("business:business_settings", business_id)
            else:
                print('businessSettingsForm_update not valid')
                messages.error(request, "Error")
        context = {
            'business': business,
            'form': form,

            'form_title': 'Business API Settings Adding Form'
        }

        return render(request, 'client/parts/business_settings_api_add.html', context)
    else:
        return redirect("business:business_dashboard")


def business_settings_api_list(request, business_id):
    business =  business_models.Business.objects.filter(business_id=business_id).first()
    business_apis = business_models.BusinessApiSettings.objects.filter(business_id=business_id)
    
    

    context = {
        'business': business,
        'business_apis': business_apis,
    }
    return render(request, 'client/parts/business_settings_api_list.html', context)

def business_settings_api_test(request, business_id, api_id):
    business =  business_models.Business.objects.filter(business_id=business_id).first()
    business_apis = business_models.BusinessApiSettings.objects.filter(business_id=business_id, id=api_id).first()
    
    

    context = {
        'business': business,
        'api': business_apis,
    }
    return render(request, 'client/parts/business_settings_api_test.html', context)



def business_settings_api_test_result(request, business_id, api_id):
    business =  business_models.Business.objects.filter(business_id=business_id).first()
    business_api = business_models.BusinessApiSettings.objects.filter(business_id=business_id, id=api_id).first()
    update_time = datetime.now().strftime('%Y-%m-%d  Time : %H:%M:%S')

    BASE_API_KEY = business_api.api_key
    BASE_API_ACCESS_KEY = business_api.api_access_token
    BASE_API_SECRET = business_api.api_secret
    BASE_API_VERSION = business_api.api_version
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
        order_count = order_response.headers.get('X-WP-Total')
        print('order_count', order_count)
        product_response = wcapi.get("products", params={"per_page": 20})
        product_count = product_response.headers.get('X-WP-Total')
        print('product_count', product_count)
 
    else:
        order_response = None
        product_response = None


    result = order_response.json()
    status = order_response.status_code

    order_count = order_count
    product_count = product_count

    context = {
        'business': business,
        'api': business_api,
        'update_time'  : update_time,
        'order_count'  : order_count,
        'product_count'  : product_count,

        'status'  : status,
        'result'  : result,

    }
    return render(request, 'client/parts/business_settings_api_test_result.html', context)



#business_logo_update---------------------------------------------------------------------------------------------------------------------
def business_logo_update(request , business_id):
    business_logos =  business_models.BusinessLogo.objects.get(business_id=business_id)
    business_code = business_models.Business.objects.get(business_id=business_id)
    
    # Check if the request user matches the business user
    if request.user.id != business_logos.business_id:
        return HttpResponseForbidden("You don't have permission to update this business logo.")
    form = business_forms.BusinessLogoForm()
    if request.method == 'POST':
            print(business_logos)
            print('business_id', business_logos.business_id)
            print('BusinessLogoForm')
            form = business_forms.BusinessLogoForm(
                    request.POST, request.FILES, instance=business_logos)
            if form.is_valid():
                f = form.save(commit=False)
                logo = business_logos.business_logo
                print(logo)

                # Delete the old logo file
                if business_logos.business_logo and business_logos.business_logo != 'business/avatar.png':
                    print('if BusinessLogo', business_logos.business_logo.path)
                    #os.remove(business_logo.business_logo.path)
                f.business_id = request.user.id
                print( business_id, f.business_id)
                f.path = f'business/{business_code}'
                print(f.path)
                f.save()
               
                print('ok')
                original_image = Image.open(f.business_logo.path)
                title, ext = os.path.splitext(f.business_logo.path)
                final_filepath = os.path.join(f.path, title + '_sm' + ext)
                print(final_filepath)
                new_width  = 200
                new_height = 200
                img = original_image.resize((new_width, new_height), Image.ANTIALIAS)
                print(img)
                img.save(final_filepath)
                messages.success(request, "Successful Submission")
                return redirect("business:business_profile")
            
    context = {
            'form': form,
            'form_title': 'Business logo Update',
        }   
  
        
        
    return render(request, 'client/parts/business_logo_update.html', context)




#business_teams---------------------------------------------------------------------------------------------------------------------

def business_teams(request, business_id):
    business =  business_models.Business.objects.filter(business_id=business_id).first()
    teams = business_models.BusinessTeamProfile.objects.filter(business_id=business_id).all()
    print('business', business)
    print('teams', teams)
    context = {
        'business': business,
        'teams': teams,
    }
    return render(request, 'client/parts/business_teams_list.html', context)

def business_teams_add(request, business_id):
    business =  business_models.Business.objects.filter(business_id=business_id).first()
    form = business_forms.BusinessTeamProfileForm()
    if request.method == 'POST':
        print('BusinessTeamProfileForm')
        form = business_forms.BusinessTeamProfileForm(
                request.POST)
        if form.is_valid():
            f = form.save(commit=False)
            f.business_id = business_id
            form.save()
            print('ok')
            messages.success(request, "Successful Submission")
            return redirect("business:business_teams", business_id)
        else:
            print('BusinessTeamProfileForm not valid')
            messages.error(request, "Error")
    context = {
            'business': business,
            'form': form,
            'form_title': 'Business Team Profile Adding Form'
        }   
  
        
        
    return render(request, 'client/parts/business_teams_add.html', context)



def business_teams_update(request, business_id, team_id):
    business =  business_models.Business.objects.filter(business_id=business_id).first()
    team = business_models.BusinessTeamProfile.objects.filter(id=team_id).first()
    form = business_forms.BusinessTeamProfileForm( instance=team)
    if request.method == 'POST':
        print('BusinessTeamProfileForm')
        form = business_forms.BusinessTeamProfileForm(
                request.POST, instance=team)
        if form.is_valid():
            f = form.save(commit=False)
            f.business_id = business_id
            form.save()
            print('ok')
            messages.success(request, "Successful Submission")
            return redirect("business:business_teams", business_id)
        else:
            print('BusinessTeamProfileForm not valid')
            messages.error(request, "Error")
    context = {
            'business': business,
            'form': form,
            'team': team,
            'form_title': 'Business Team Profile Update Form' 
        }   
  
        
        
    return render(request, 'client/parts/business_teams_update.html', context)


