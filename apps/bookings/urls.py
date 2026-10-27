from django.urls import path
from . import views

app_name = 'bookings'

urlpatterns = [
    path('cart/', views.cart_view, name='cart'),
    path('cart/add/', views.cart_add_view, name='cart_add'),
    path('cart/remove/<int:index>/', views.cart_remove_view, name='cart_remove'),
    path('cart/update/<int:index>/', views.cart_update_quantity_view, name='cart_update_quantity'),
    path('cart/address/add/', views.shipping_address_add_view, name='address_add'),
    path('cart/address/delete/<int:index>/', views.shipping_address_delete_view, name='address_delete'),
    path('cart/address/select/<int:index>/', views.shipping_address_select_view, name='address_select'),
    path('review/', views.review_view, name='review'),
    path('checkout/', views.checkout_view, name='checkout'),
    path('my/', views.my_bookings_view, name='my_bookings'),
    path('my-orders/', views.my_bookings_view, name='my_orders'),
    path('my-bookings/', views.my_bookings_view, name='my_bookings_alias'),
    path('detail/<uuid:booking_id>/', views.booking_detail_view, name='detail'),
]
