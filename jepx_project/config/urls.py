"""URL設定 — config/urls.py"""
from django.urls import path, include

urlpatterns = [
    # 外部(Excel VBA等)からアクセスされるAPI群のルート定義
    path('', include('apps.itd_api.urls')),
    
    # 画面UI (Django Templates) 用のルーティング
    path('ui/', include('apps.web_ui.urls')),
]
