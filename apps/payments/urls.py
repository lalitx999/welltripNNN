from django.urls import path
from . import views

app_name = 'payments'

urlpatterns = [
    path('instruction/<uuid:booking_id>/', views.payment_instruction_view, name='payment_instruction'),
    path('slip-upload/<uuid:booking_id>/', views.payment_instruction_view, name='slip_upload'),
    path('admin/list/', views.admin_payments_list_view, name='admin_list'),
    path('admin/review/<uuid:payment_id>/', views.admin_payment_review_view, name='admin_review'),
]
