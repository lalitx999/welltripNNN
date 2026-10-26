from django.urls import path
from django.shortcuts import render

app_name = 'payments'

def index(request):
    return render(request, 'payments/checkout.html')

urlpatterns = [
    path('', index, name='checkout'),
]
