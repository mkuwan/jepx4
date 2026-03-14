from django.views.generic import TemplateView
from django.urls import reverse_lazy, reverse
from django.contrib import messages
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.conf import settings
from zoneinfo import ZoneInfo
from datetime import datetime, timedelta

from .auth import oauth, cookie_login_required

# ==========================================
# SSO Authentication Views
# ==========================================
def login_view(request):
    """Azure SSOログイン画面へリダイレクト（dev環境ではバイパス可能）"""
    # DEV_SSO_BYPASS=True の場合は Azure 認証をスキップして即ログイン済みにする
    if getattr(settings, 'DEV_SSO_BYPASS', False):
        request.session['user'] = settings.DEV_SSO_BYPASS_USER
        return redirect('web_ui:dah_dashboard')
    redirect_uri = request.build_absolute_uri(reverse('web_ui:callback'))
    return oauth.microsoft.authorize_redirect(request, redirect_uri)

def auth_callback_view(request):
    """Azure SSOからのコールバックを受け取りCookieセッションを確立"""
    token = oauth.microsoft.authorize_access_token(request)
    userinfo = token.get('userinfo')
    
    if userinfo:
        request.session['user'] = {
            'name': userinfo.get('name'),
            'email': userinfo.get('preferred_username', ''),
        }
    return redirect('web_ui:dah_dashboard')

def logout_view(request):
    """ログアウト（Cookieセッションの破棄）"""
    request.session.flush()
    # 完全にログアウト後、とりあえず再度ダッシュボードにアクセスさせログインへ飛ばす
    return redirect('web_ui:dah_dashboard')

# ==========================================
# DAH (翌日市場) Views
# ==========================================
@method_decorator(cookie_login_required, name='dispatch')
class DahDashboardView(TemplateView):
    template_name = 'web_ui/dah_dashboard.html'

@method_decorator(cookie_login_required, name='dispatch')
class DahUploadView(TemplateView):
    template_name = 'web_ui/dah_upload.html'

@method_decorator(cookie_login_required, name='dispatch')
class DahBidView(TemplateView):
    template_name = 'web_ui/dah_bid.html'

@method_decorator(cookie_login_required, name='dispatch')
class DahInquiryView(TemplateView):
    template_name = 'web_ui/dah_inquiry.html'

@method_decorator(cookie_login_required, name='dispatch')
class DahReportView(TemplateView):
    template_name = 'web_ui/dah_report.html'

# ==========================================
# ITD (時間前市場) Views
# ==========================================
@method_decorator(cookie_login_required, name='dispatch')
class ItdDashboardView(TemplateView):
    template_name = 'web_ui/itd_dashboard.html'

@method_decorator(cookie_login_required, name='dispatch')
class ItdInquiryView(TemplateView):
    template_name = 'web_ui/itd_inquiry.html'
