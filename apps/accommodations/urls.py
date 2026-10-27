from django.urls import path
from . import views

app_name = 'accommodations'

urlpatterns = [
    path('', views.list_view, name='list'),
    path('<str:identifier>/', views.detail_view, name='detail'),
    path('studio/', views.homestay_studio_view, name='homestay_studio'),
    path('studio/room/create/', views.room_create_view, name='room_create'),
    path('studio/calendar/', views.calendar_view, name='calendar'),
]
