"""ITD API URL定義 (§5.1)"""
from django.urls import path
from .views import (
    ItdBidView,
    ItdDeleteView,
    ItdInquiryView,
    ItdContractView,
    ItdSettlementView,
    HealthCheckView,
)
from apps.itn_stream.views import ItnStreamView

urlpatterns = [
    # ITD入札 API
    path('api/v1/itd/bid', ItdBidView.as_view(), name='itd_bid'),
    path('api/v1/itd/delete', ItdDeleteView.as_view(), name='itd_delete'),
    path('api/v1/itd/inquiry', ItdInquiryView.as_view(), name='itd_inquiry'),
    path('api/v1/itd/contract', ItdContractView.as_view(), name='itd_contract'),
    path('api/v1/itd/settlement', ItdSettlementView.as_view(), name='itd_settlement'),

    # ITN配信
    path('api/v1/itn/stream', ItnStreamView.as_view(), name='itn_stream'),

    # ヘルスチェック
    path('health', HealthCheckView.as_view(), name='health'),
]
