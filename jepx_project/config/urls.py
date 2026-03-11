"""URL設定 — config/urls.py"""
from django.urls import path, include

urlpatterns = [
    # 外部(Excel VBA等)からアクセスされるAPI群のルート定義
    # ※画面UIは本番環境に持たせないため、itd_api・itn_stream に向けた連携用APIルーティングのみを登録しています
    path('', include('apps.itd_api.urls')),
]
