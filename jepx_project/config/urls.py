"""URL設定 — config/urls.py"""
from django.urls import path, include

urlpatterns = [
    # ITD/ITN API (§5.1)
    path('', include('apps.itd_api.urls')),
]
