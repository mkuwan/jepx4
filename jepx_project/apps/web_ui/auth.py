import functools
from django.shortcuts import redirect
from django.conf import settings
from authlib.integrations.django_client import OAuth

# --- Authlib (OAuthクライアント)の初期設定 ---
oauth = OAuth()

# .settings/sso_config.yml または環境変数からロードされた設定を使用
oauth.register(
    name='microsoft',
    client_id=settings.ENTRA_CLIENT_ID,
    client_secret=settings.ENTRA_CLIENT_SECRET,
    server_metadata_url=f'https://login.microsoftonline.com/{settings.ENTRA_TENANT_ID}/v2.0/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

def cookie_login_required(view_func):
    """
    DBレス環境(Signed Cookies) 用のアクセス制御デコレータ。
    セッション(Cookie)内に 'user' オブジェクトが存在しない場合、強制的にログイン画面へリダイレクトします。
    """
    @functools.wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        # Cookie(セッション)からユーザー情報を取得
        user = request.session.get('user')
        
        if not user:
            # 未ログインの場合はSSO認証開始エンドポイントへ飛ばす
            return redirect('web_ui:login')
            
        # ログイン済みなら元のViewを続行
        return view_func(request, *args, **kwargs)
        
    return _wrapped_view
