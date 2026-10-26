from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register_view, name='register'),
    path('portal/', views.portal_dashboard_view, name='portal_dashboard'),
    path('admin-center/', views.admin_dashboard_view, name='admin_dashboard'),
]
