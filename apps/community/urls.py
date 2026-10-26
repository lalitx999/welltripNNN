from django.urls import path
from django.shortcuts import render

app_name = 'community'

def index(request):
    return render(request, 'community/map.html')

urlpatterns = [
    path('', index, name='map'),
]
