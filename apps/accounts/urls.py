from django.urls import path
from . import views
from . import admin_views

app_name = 'accounts'

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register_view, name='register'),
    path('register/merchant/', views.merchant_register_view, name='register_merchant'),
    path('profile/', views.profile_view, name='profile'),
    path('portal/', views.portal_dashboard_view, name='portal_dashboard'),
    path('admin-center/', views.admin_dashboard_view, name='admin_dashboard'),
    
    # Admin Operations Center
    path('admin/approvals/', admin_views.admin_approvals_view, name='admin_approvals'),
    path('admin/approvals/merchant/<uuid:user_id>/', admin_views.admin_approve_merchant_view, name='admin_approve_merchant'),
    path('admin/approvals/merchant/<uuid:user_id>/reject/', admin_views.admin_reject_merchant_view, name='admin_reject_merchant'),
    path('admin/users/', admin_views.admin_users_view, name='admin_users'),
    path('admin/users/<uuid:user_id>/delete/', admin_views.admin_delete_user_view, name='admin_delete_user'),
    path('admin/catalog/', admin_views.admin_catalog_view, name='admin_catalog'),
    path('admin/audit/', admin_views.admin_audit_log_view, name='admin_audit'),
]

