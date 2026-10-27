from django.urls import path
from . import views

app_name = 'community'

urlpatterns = [
    path('map/', views.map_view, name='map'),
    path('api/locations/', views.locations_api_view, name='locations_api'),
    path('passport/', views.passport_view, name='passport'),
    path('stamp/<str:qr_secret>/', views.claim_stamp_view, name='claim_stamp'),
    path('stories/', views.stories_list_view, name='stories_list'),
    path('stories/<uuid:story_id>/', views.story_detail_view, name='story_detail'),
    path('news/', views.stories_list_view, name='news'),
    path('recommended/', views.map_view, name='recommended'),
    path('help/', views.map_view, name='help'),
    path('settings/', views.my_location_events_view, name='settings'),
    path('coupon/validate/', views.validate_coupon_htmx_view, name='validate_coupon'),
    path('location/my-events/', views.my_location_events_view, name='my_location_events'),
]

