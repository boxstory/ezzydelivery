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
    path('orders/pending-verification/', workforce_views.orders_pending_verification, name='orders_pending_verification'),
    path('orders/<int:order_id>/verify-address/', workforce_views.verify_order_address, name='verify_order_address'),
    path('orders/<int:order_id>/verify/', workforce_views.verify_order, name='verify_order'),
    path('orders/submit_to_task/<int:order_id>/', workforce_views.submit_to_task, name='submit_to_task'),

    # AJAX endpoints for orders
    path('orders/<int:order_id>/publish/', workforce_views.publish_order_to_delivery, name='publish_order_to_delivery'),
    path('orders/<int:order_id>/update-status/', workforce_views.update_order_status, name='update_order_status'),
    path('orders/<int:order_id>/add-comment/', workforce_views.add_order_comment, name='add_order_comment'),



    #Deliveries sections urls ----------------------------------------------------------------
    path('tasks/dl_list_all/', workforce_views.dl_list_all, name='dl_list_all'),
    path('tasks/dl_list_unpublished/', workforce_views.dl_list_ready_to_published_to_dms, name='dl_list_ready_to_published_to_dms'),
    path('tasks/dl_list_published/', workforce_views.dl_list_published_to_dms, name='dl_list_published_to_dms'),
    path('tasks/dl_list_incompleted/', workforce_views.dl_list_incompleted_details, name='dl_list_incompleted_details'),

    # AJAX endpoints for delivery tasks
    path('delivery-task/<int:task_id>/publish-dms/', workforce_views.publish_task_to_dms, name='publish_task_to_dms'),
    path('delivery-task/<int:task_id>/publish-driver-app/', workforce_views.publish_task_to_driver_app, name='publish_task_to_driver_app'),
    path('delivery-task/<int:task_id>/assign-driver/', workforce_views.assign_driver_to_task, name='assign_driver_to_task'),
    path('delivery-task/<int:task_id>/update-status/', workforce_views.update_task_status, name='update_task_status'),
    


    #DMS sections urls -----------------------------------------------------------------------



    #Documents sections urls -----------------------------------------------------------------

    # Workflow guide
    path('workflow-guide/', workforce_views.workflow_guide, name='workflow_guide'),


]
