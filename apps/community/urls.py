from django.urls import path
from . import views

app_name = 'community'

urlpatterns = [
    path('map/', views.map_view, name='map'),
    path('api/locations/', views.locations_api_view, name='locations_api'),
    path('passport/', views.passport_view, name='passport'),
    path('stamp/<str:qr_secret>/', views.claim_stamp_view, name='claim_stamp'),
]
