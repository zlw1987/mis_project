"""
external_auth URL Configuration

FoxPro external authentication endpoints.
"""

from django.urls import path
from . import views

app_name = 'external_auth'

urlpatterns = [
    path('foxpro-launch/', views.foxpro_launch, name='foxpro_launch'),
]