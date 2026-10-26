from django.urls import path
from django.shortcuts import render

app_name = 'accommodations'

def index(request):
    return render(request, 'accommodations/list.html')

urlpatterns = [
    path('', index, name='list'),
]
