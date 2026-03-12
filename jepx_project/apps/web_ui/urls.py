from django.urls import path
from . import views

app_name = 'web_ui'

urlpatterns = [
    # Auth (SSO)
    path('login/', views.login_view, name='login'),
    path('callback/', views.auth_callback_view, name='callback'),
    path('logout/', views.logout_view, name='logout'),

    # DAH (翌日市場) Web UI
    path('dah/', views.DahDashboardView.as_view(), name='dah_dashboard'),
    path('dah/upload/', views.DahUploadView.as_view(), name='dah_upload'),
    path('dah/bid/', views.DahBidView.as_view(), name='dah_bid'),
    path('dah/inquiry/', views.DahInquiryView.as_view(), name='dah_inquiry'),
    path('dah/report/', views.DahReportView.as_view(), name='dah_report'),

    # ITD (時間前市場) Web UI
    path('itd/', views.ItdDashboardView.as_view(), name='itd_dashboard'),
    path('itd/inquiry/', views.ItdInquiryView.as_view(), name='itd_inquiry'),
]
