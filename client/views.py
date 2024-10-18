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

from client import models as business_models
from core import models as core_models
from ezzydelivery.settings import BASE_DIR
from orders import models as orders_models

from client import forms as business_forms

# Create your views here.


# dashboard---------------------------------------------------------------------------------------------------------------------


@login_required(login_url='account_login')
def business_dashboard(request):
    try:
        business = business_models.Business.objects.get(
            user_id=request.user.id)
        profile = core_models.Profile.objects.get(user_id=business.user_id)
        location = business_models.PickupLocation.objects.filter(
            business_id=business.business_id).all()
        print(business, "latest 10 order list")
        orders = orders_models.Order.objects.filter(
            business=business.business_id).order_by('-id')[:10]

        print(business)

        context = {
            'profile': profile,
            'business': business,
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
def pickup_location_list(request):
    business = business_models.Business.objects.get(
        user_id=request.user.id)
    pickup_location = business_models.PickupLocation.objects.filter(
        business_id=request.user.id).all()
    if not pickup_location:
        return redirect('business:pickup_location_add')
    print('pickup_location', pickup_location)
    context = {
        'pickup_location': pickup_location,
        'business': business, }
    return render(request, 'client/parts/pickup_location_list.html', context)


def pickup_location_add(request):
    business = business_models.Business.objects.get(
        user_id=request.user.id)
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
        'form': form,
        'id': id,

    }
    return render(request, 'client/parts/pickup_location_update.html', context)

# frontend ---------------------------------------------------------------------------------------------------------------------


def business_profile(request, business_id):
    try:
        business = business_models.Business.objects.get(
            business_id=business_id)
        profile = core_models.Profile.objects.filter(user_id=request.user.id)
        location = business_models.PickupLocation.objects.filter(
            business_id=business.business_id).values_list('pickup_location_title', flat=True)[:2]
        business_logo = business_models.BusinessLogo.objects.select_related('business').get_or_create(business_id = business.business_id )
        instakey = config("INSTAGRAM_TOKEN_FEEDS_KEY")
        business_logo = business_logo[0].business_logo.url


        context = {
            'profile': profile,
            'business': business,
            'location': location,
            'business_logo_img': business_logo,
            'instakey': instakey,
        }
        return render(request, 'client/frontend/business_profile.html', context)
    except business_models.Business.DoesNotExist:

        return redirect("/join_us/")


def business_profile_update(request, business_id):
    if request.user.id == business_id:
        print(':matched')
        redirect('core:main_dashboard')
        print('business_profile_update', business_id)
        print('request.user.id', request.user.id)
        business =  business_models.Business.objects.filter(business_id=business_id).first()
        print('business', business)
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


def all_business(request):
    business = business_models.Business.objects.all()
    
    

    context = {
        'all_business': business,
    }
    return render(request, 'client/frontend/all_business.html', context)


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
                return redirect("business:business_profile", business_id)
            
    context = {
            'form': form,
        }   
  
        
        
    return render(request, 'client/parts/business_logo_update.html', context)

