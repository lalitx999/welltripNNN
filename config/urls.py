"""
WellTrip URL Configuration.
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include

from apps.accommodations import views as views_accommodations
from apps.ai_recommendations import views as views_ai

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('apps.core.urls')),
    path('accounts/', include('apps.accounts.urls')),
    path('accommodations/', include('apps.accommodations.urls')),
    path('services/', include('apps.services.urls')),
    path('otop/', include('apps.otop.urls')),
    path('bookings/', include('apps.bookings.urls')),
    path('payments/', include('apps.payments.urls')),
    path('community/', include('apps.community.urls')),
    path('ai/', include('apps.ai_recommendations.urls')),
    
    # Original Next.js Route Aliases (direct view handlers without namespace collision)
    path('hotels/', views_accommodations.list_view, name='hotels_alias'),
    path('health/', views_ai.assessment_view, name='health_alias'),
]


from django.views.static import serve
from django.urls import re_path

urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]

