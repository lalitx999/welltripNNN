from django.urls import path
from . import views

app_name = "ai_recommendations"

urlpatterns = [
    path("", views.assessment_view, name="assessment"),
    path("assess/", views.assess_htmx_view, name="assess_htmx"),
]
