from django.urls import path
from . import views

app_name = 'services'

urlpatterns = [
    path('', views.list_view, name='list'),
    path('food/', views.list_view, name='food'),
    path('wellness/', views.list_view, name='wellness'),
    path('detail/<str:service_type>/<uuid:item_id>/', views.service_detail_view, name='detail'),
    path('studio/restaurant/', views.restaurant_studio_view, name='restaurant_studio'),
    path('studio/restaurant/delete/<uuid:food_id>/', views.food_delete_view, name='food_delete'),
    path('studio/wellness/', views.wellness_studio_view, name='wellness_studio'),
    path('studio/wellness/slot/create/', views.wellness_slot_create_view, name='wellness_slot_create'),
    path('studio/wellness/slot/delete/<int:slot_id>/', views.wellness_slot_delete_view, name='wellness_slot_delete'),
]
