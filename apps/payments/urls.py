from django.urls import path
from . import views

app_name = 'payments'

urlpatterns = [
    path('instruction/<uuid:booking_id>/', views.payment_instruction_view, name='payment_instruction'),
]
