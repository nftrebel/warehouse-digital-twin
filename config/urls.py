"""
URL configuration for Warehouse Digital Twin project.
"""

from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    # Django admin
    path('admin/', admin.site.urls),

    # API endpoints
    path('api/v1/', include('apps.api.urls', namespace='api')),

    # Web UI
    path('', include('apps.ui.urls', namespace='ui')),

    # Authentication
    path('accounts/', include('apps.accounts.urls', namespace='accounts')),
]
