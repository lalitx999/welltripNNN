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
    
    # Partner CRUD
    path('admin/partners/add/', admin_views.admin_partner_add_view, name='admin_partner_add'),
    path('admin/partners/<uuid:user_id>/edit/', admin_views.admin_partner_edit_view, name='admin_partner_edit'),
    path('admin/partners/<uuid:user_id>/delete/', admin_views.admin_partner_delete_view, name='admin_partner_delete'),

    # User CRUD
    path('admin/users/', admin_views.admin_users_view, name='admin_users'),
    path('admin/users/add/', admin_views.admin_user_add_view, name='admin_user_add'),
    path('admin/users/<uuid:user_id>/edit/', admin_views.admin_user_edit_view, name='admin_user_edit'),
    path('admin/users/<uuid:user_id>/toggle/', admin_views.admin_user_toggle_view, name='admin_user_toggle'),
    path('admin/users/<uuid:user_id>/reset-password/', admin_views.admin_user_reset_password_view, name='admin_user_reset_password'),
    path('admin/users/<uuid:user_id>/delete/', admin_views.admin_delete_user_view, name='admin_delete_user'),

    # Catalog CRUD
    path('admin/catalog/', admin_views.admin_catalog_view, name='admin_catalog'),
    path('admin/catalog/add/', admin_views.admin_catalog_add_view, name='admin_catalog_add'),
    path('admin/catalog/<str:item_type>/<uuid:item_id>/edit/', admin_views.admin_catalog_edit_view, name='admin_catalog_edit'),
    path('admin/catalog/<str:item_type>/<uuid:item_id>/delete/', admin_views.admin_catalog_delete_view, name='admin_catalog_delete'),
    path('admin/catalog/<str:item_type>/<uuid:item_id>/toggle/', admin_views.admin_catalog_toggle_view, name='admin_catalog_toggle'),

    # Locations CRUD
    path('admin/locations/add/', admin_views.admin_location_add_view, name='admin_location_add'),
    path('admin/locations/<uuid:location_id>/edit/', admin_views.admin_location_edit_view, name='admin_location_edit'),
    path('admin/locations/<uuid:location_id>/delete/', admin_views.admin_location_delete_view, name='admin_location_delete'),

    # Content / Stories CRUD
    path('admin/content/add/', admin_views.admin_content_add_view, name='admin_content_add'),
    path('admin/content/<uuid:entry_id>/edit/', admin_views.admin_content_edit_view, name='admin_content_edit'),
    path('admin/content/<uuid:entry_id>/delete/', admin_views.admin_content_delete_view, name='admin_content_delete'),

    # Payments & Slips Actions
    path('admin/payments/<uuid:payment_id>/edit/', admin_views.admin_payment_edit_view, name='admin_payment_edit'),
    path('admin/payments/<uuid:payment_id>/delete/', admin_views.admin_payment_delete_view, name='admin_payment_delete'),
    path('admin/slips/<uuid:slip_id>/delete/', admin_views.admin_slip_delete_view, name='admin_slip_delete'),

    # Security Audits
    path('admin/audit/', admin_views.admin_audit_log_view, name='admin_audit'),

    # Vouchers & Shipping Settings
    path('admin/vouchers/create/', admin_views.admin_coupon_create_view, name='admin_coupon_create'),
    path('admin/vouchers/<uuid:coupon_id>/toggle/', admin_views.admin_coupon_toggle_view, name='admin_coupon_toggle'),
    path('admin/vouchers/<uuid:coupon_id>/delete/', admin_views.admin_coupon_delete_view, name='admin_coupon_delete'),
    path('admin/shipping/update/', admin_views.admin_shipping_settings_update_view, name='admin_shipping_settings_update'),
]

