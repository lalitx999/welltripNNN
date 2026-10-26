from django.urls import path
from django.shortcuts import render

app_name = 'otop'

def index(request):
    return render(request, 'otop/list.html')

urlpatterns = [
    path('', index, name='list'),
]
