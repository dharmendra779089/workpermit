"""
URL configuration for Opmaint Permit to Work (PTW) CMMS module.
"""

from django.contrib import admin
from django.urls import path, include, re_path
from permits.views import frontend_index

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('permits.urls')),
    # Catch-all routes serving SPA frontend
    re_path(r'^(?!static/|media/|api/|admin/).*$', frontend_index, name='frontend-app'),
]
