from django.urls import path
from . import views

app_name = 'otop'

urlpatterns = [
    path('', views.list_view, name='list'),
    path('<uuid:product_id>/', views.detail_view, name='detail'),
    path('studio/', views.otop_studio_view, name='otop_studio'),
    path('studio/stock/<uuid:product_id>/', views.otop_stock_update_view, name='stock_update'),
]
