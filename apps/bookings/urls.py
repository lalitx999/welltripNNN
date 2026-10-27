from django.urls import path
from . import views

app_name = 'bookings'

urlpatterns = [
    path('cart/', views.cart_view, name='cart'),
    path('cart/add/', views.cart_add_view, name='cart_add'),
    path('cart/remove/<int:index>/', views.cart_remove_view, name='cart_remove'),
    path('checkout/', views.checkout_view, name='checkout'),
    path('my/', views.my_bookings_view, name='my_bookings'),
    path('my-orders/', views.my_bookings_view, name='my_orders'),
    path('detail/<uuid:booking_id>/', views.booking_detail_view, name='detail'),
]
