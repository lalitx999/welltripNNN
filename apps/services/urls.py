from django.urls import path
from django.shortcuts import render

app_name = 'services'

def index(request):
    return render(request, 'services/list.html')

urlpatterns = [
    path('', index, name='list'),
]
