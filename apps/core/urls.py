from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.landing_view, name='landing'),
    path('home/', views.tourist_home_view, name='home'),
    path('about/', views.about_view, name='about'),
    path('contact/', views.contact_view, name='contact'),
    path('terms/', views.terms_view, name='terms'),
    path('privacy/', views.terms_view, name='privacy'),
    path('api/search/live/', views.live_search_api, name='live_search_api'),
    path('manifest.json', views.manifest_view, name='manifest'),
    path('sw.js', views.service_worker_view, name='service_worker'),
    path('offline/', views.offline_view, name='offline'),
    path('robots.txt', views.robots_txt_view, name='robots_txt'),
    path('sitemap.xml', views.sitemap_xml_view, name='sitemap_xml'),
    path('llms.txt', views.llms_txt_view, name='llms_txt'),
    path('llm.txt', views.llms_txt_view, name='llm_txt'),
    path('llms-full.txt', views.llms_full_txt_view, name='llms_full_txt'),
    path('llm-full.txt', views.llms_full_txt_view, name='llm_full_txt'),
]

