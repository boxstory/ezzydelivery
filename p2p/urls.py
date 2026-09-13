# Purpose: Routes for the P2P booking flow, the confirm link and the sender's console.
# Used by: ezzydelivery/urls.py — included at /p2p/ AFTER webpages, so /p2p/pricing/ keeps resolving.
# Notes: /p2p/a/<token>/ is deliberately short and public — it is sent in a WhatsApp message.

from django.urls import path

from p2p import views

app_name = 'p2p'

urlpatterns = [
    path('verify-number/', views.verify_number, name='verify_number'),
    path('book/start/', views.book_start, name='book_start'),
    path('book/<str:token>/', views.book, name='book'),
    path('booking/<str:token>/', views.booking_confirmation, name='booking_confirmation'),
    path('a/<str:token>/', views.accept_price, name='accept_price'),
    path('my-deliveries/', views.my_deliveries, name='my_deliveries'),
    path('my-deliveries/<str:order_number>/', views.delivery_detail, name='delivery_detail'),
    path('my-deliveries/<str:order_number>/edit/', views.delivery_edit, name='delivery_edit'),
    path('my-deliveries/<str:order_number>/comment/', views.add_comment, name='add_comment'),
]
