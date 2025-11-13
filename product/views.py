from django.shortcuts import redirect, render
from django.contrib.auth.decorators import login_required
from django.contrib import messages


from product import models as product_models
from client import models as business_models
from product import forms as product_forms
# Create your views here.


# ITEMS


@login_required(login_url='account_login')
def product_all_list(request):
    business=business_models.Business.objects.get(user_id=request.user.id)
    print(business)
    products = product_models.Product.objects.all()
    print(products)
    data = {
        'products': products,
        'business': business

    }
    return render(request, 'product/product_all_list.html', data)


@login_required(login_url='account_login')
def product_all_list_card(request):
    business=business_models.Business.objects.get(user_id=request.user.id)
    print(business)
    products = product_models.Product.objects.all()
    print(products)
    data = {
        'products': products,
        'business': business
    }
    return render(request, 'product/product_all_list_card.html', data)


@login_required(login_url='account_login')
def product_single_add(request):
    print('Product add')
    business = business_models.Business.objects.get(user_id=request.user.id)
    if request.method == 'POST':
        form = product_forms.AddItemsForm(request.POST, request.FILES)
        if form.is_valid():
            print('form valid')
            product = form.save(commit=False)
            product.business = business
            product.save()
            messages.success(request, 'Product added successfully!')
            return redirect('/product/all/')
        else:
            print('form errors:', form.errors)
            messages.error(request, 'Error adding product. Please check the form.')
    else:
        form = product_forms.AddItemsForm()

    data = {
        'form': form,
        'business': business

    }
    return render(request, 'product/product_single_add.html', data)


@login_required(login_url='account_login')
def product_single_delete(request, product_id):
    product = product_models.Product.objects.get(id=product_id)
    product.delete()

    data = {

    }
    return render(request, 'product/product_single_delete.html', data)


@login_required(login_url='account_login')
def product_single_update(request, product_id):
    
    business=business_models.Business.objects.get(user_id=request.user.id)
    product = product_models.Product.objects.get(id=product_id)
    form = product_forms.AddItemsForm(instance= product)
    if request.method == 'POST':
        form = product_forms.AddItemsForm( request.POST, request.FILES, instance= product)
        if form.is_valid():
            form.save()
            messages.success(
                request, f'Your product details has been Updated!')
            return redirect('/product/all/' )

    data = {
        'business': business,
        'form': form,
        'product': product,
    }
    return render(request, 'product/product_single_update.html', data)


def product_inventory(request):
    business = business_models.Business.objects.get(user_id=request.user.id)
    data = {
        'business': business

    }
    return render(request, 'product/product_inventory.html', data)



def product_categories(request):
    data = {

    }
    return render(request, 'product/product_categories.html', data)