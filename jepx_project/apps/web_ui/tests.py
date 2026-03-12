from django.test import SimpleTestCase
from django.urls import reverse
from unittest.mock import patch, MagicMock
from django.conf import settings
from django.contrib.sessions.backends.signed_cookies import SessionStore
from django.http import HttpResponseRedirect

class WebUiSSOTests(SimpleTestCase):
    def setUp(self):
        # Cookie-based session test setup
        pass
        
    def _create_session_cookie(self, user_data=None):
        session = SessionStore()
        if user_data:
            session['user'] = user_data
        session.save()
        self.client.cookies[settings.SESSION_COOKIE_NAME] = session.session_key

    def test_unauthenticated_access_redirects_to_login(self):
        """未ログインで保護されたページにアクセスするとlogin画面へリダイレクトされる(302)こと"""
        protected_urls = [
            'web_ui:dah_dashboard',
            'web_ui:dah_upload',
            'web_ui:dah_bid',
            'web_ui:dah_inquiry',
            'web_ui:dah_report',
            'web_ui:itd_dashboard',
            'web_ui:itd_inquiry',
        ]
        for url_name in protected_urls:
            response = self.client.get(reverse(url_name))
            self.assertEqual(response.status_code, 302, f"Failed on {url_name}")
            self.assertEqual(response.url, reverse('web_ui:login'))

    def test_authenticated_access_is_allowed(self):
        """ログイン済みの場合は保護されたページにアクセスできること"""
        self._create_session_cookie({'name': 'Test User', 'email': 'test@example.com'})
        
        response = self.client.get(reverse('web_ui:dah_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'web_ui/dah_dashboard.html')

    @patch('apps.web_ui.views.oauth.microsoft.authorize_redirect')
    def test_login_view_redirects_to_sso(self, mock_redirect):
        """loginエンドポイントがSSOプロバイダへのリダイレクトを試行すること"""
        mock_redirect.return_value = HttpResponseRedirect('https://login.microsoftonline.com/dummy')
        response = self.client.get(reverse('web_ui:login'))
        self.assertEqual(response.status_code, 302)
        self.assertTrue('login.microsoftonline.com' in response.url)
        mock_redirect.assert_called_once()

    def test_logout_view_flushes_session(self):
        """ログアウトするとセッションが破棄され、ダッシュボード経由でログイン画面へリダイレクトされること"""
        self._create_session_cookie({'name': 'To Be Logged Out'})
        
        response = self.client.get(reverse('web_ui:logout'))
        # ログアウト完了後はdah_dashboardへリダイレクトされる
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('web_ui:dah_dashboard'))
        
        # セッションCookieが削除されたか確認
        session_cookie = response.cookies.get(settings.SESSION_COOKIE_NAME)
        self.assertTrue(session_cookie.value == '' or session_cookie.value is None or session_cookie.max_age == 0)

    @patch('apps.web_ui.views.oauth.microsoft.authorize_access_token')
    def test_auth_callback_sets_session(self, mock_authorize):
        """SSOコールバック成功時にセッションが確立されること"""
        mock_authorize.return_value = {
            'userinfo': {
                'name': 'SSO User',
                'preferred_username': 'sso@example.com'
            }
        }
        
        response = self.client.get(reverse('web_ui:callback') + '?code=dummycode')
        
        # コールバック処理完了後、ダッシュボードへリダイレクト
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('web_ui:dah_dashboard'))
        
        # 新しいセッションの内容を確認
        session_key = response.cookies[settings.SESSION_COOKIE_NAME].value
        session = SessionStore(session_key=session_key)
        
        self.assertEqual(session['user']['name'], 'SSO User')
        self.assertEqual(session['user']['email'], 'sso@example.com')
