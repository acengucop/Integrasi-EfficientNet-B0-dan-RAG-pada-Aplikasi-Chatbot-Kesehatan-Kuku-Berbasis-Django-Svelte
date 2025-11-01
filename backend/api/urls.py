# api/urls.py
from django.urls import path
from .views import AnalyzeView, LabelsView

urlpatterns = [
    path('analyze', AnalyzeView.as_view(), name='analyze'),
    path('labels', LabelsView.as_view(), name='labels'),
]
