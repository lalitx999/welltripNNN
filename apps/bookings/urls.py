from django.urls import path
from django.shortcuts import render

app_name = 'bookings'

def index(request):
    return render(request, 'bookings/cart.html')

urlpatterns = [
    path('', index, name='cart'),
]
