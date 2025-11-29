from django.urls import path
from . import views

app_name = 'blog'

urlpatterns = [
    path('', views.blog_index, name='index'),
    path('category/', views.blog_category, name='category_all'),
    path('category/<slug:slug>/', views.blog_category, name='category'),
    path('post/<slug:slug>/', views.blog_post_detail, name='post_detail'),
]
