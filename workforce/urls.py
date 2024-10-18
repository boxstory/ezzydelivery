from django.urls import path
from webpages import views as webpages_views
from workforce import views as workforce_views
from delivery import views as delivery_views
from orders import views as orders_views
from core import views as core_views

app_name = 'workforce'
urlpatterns = [
    path('dashboard/', workforce_views.wf_dashboard, name='wf_dashboard'),

    #Orders sections urls -------------------------------------------------------------------
    path('orders/all/', workforce_views.all_orders, name='all_orders'),
    path('orders/to_publish/', workforce_views.orders_to_publish, name='orders_to_publish'),
    path('orders/published/', workforce_views.orders_published, name='orders_published'),
    path('orders/submit_to_task/<int:order_id>/', workforce_views.submit_to_task, name='submit_to_task'),



    #Deliveries sections urls ----------------------------------------------------------------
    path('tasks/dl_list_all/', workforce_views.dl_list_all, name='dl_list_all'),
    path('tasks/dl_list_unpublished/', workforce_views.dl_list_ready_to_published_to_dms, name='dl_list_ready_to_published_to_dms'),
    path('tasks/dl_list_published/', workforce_views.dl_list_published_to_dms, name='dl_list_published_to_dms'),
    path('tasks/dl_list_incompleted/', workforce_views.dl_list_incompleted_details, name='dl_list_incompleted_details'),
    


    #DMS sections urls -----------------------------------------------------------------------



    #Documents sections urls -----------------------------------------------------------------



]
