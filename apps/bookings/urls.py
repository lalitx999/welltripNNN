from django.urls import path
from . import stay_views, views

app_name = 'bookings'

urlpatterns = [
    path('cart/', views.cart_view, name='cart'),
    path('cart/add/', views.cart_add_view, name='cart_add'),
    path('cart/remove/<int:index>/', views.cart_remove_view, name='cart_remove'),
    path('cart/update/<int:index>/', views.cart_update_quantity_view, name='cart_update_quantity'),
    path('cart/address/add/', views.shipping_address_add_view, name='address_add'),
    path('cart/address/delete/<int:index>/', views.shipping_address_delete_view, name='address_delete'),
    path('cart/address/select/<int:index>/', views.shipping_address_select_view, name='address_select'),
    path('coupon/apply/', views.coupon_apply_view, name='coupon_apply'),
    path('coupon/remove/', views.coupon_remove_view, name='coupon_remove'),
    path('review/', views.review_view, name='review'),
    path('checkout/', views.checkout_view, name='checkout'),
    path('my/', views.my_bookings_view, name='my_bookings'),
    path('my-orders/', views.my_bookings_view, name='my_orders'),
    path('my-bookings/', views.my_bookings_view, name='my_bookings_alias'),
    path('detail/<uuid:booking_id>/', views.booking_detail_view, name='detail'),
    # Homestay owners and admins: deposits, balance paid on site, cancellations
    path('stays/', stay_views.stay_bookings_view, name='stay_bookings'),
    path('stays/<uuid:booking_id>/slip/', stay_views.stay_slip_review_view, name='stay_slip_review'),
    path('stays/<uuid:booking_id>/balance-paid/', stay_views.stay_balance_paid_view, name='stay_balance_paid'),
    path('stays/<uuid:booking_id>/cancel/', stay_views.stay_cancel_view, name='stay_cancel'),
]
