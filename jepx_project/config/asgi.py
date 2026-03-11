"""ASGI config — config/asgi.py (§5.5)

ASGI起動時にITN受信バックグラウンドタスクを開始する。
"""
import os
import asyncio
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')
django_app = get_asgi_application()

# ITNストア（シングルトン）— Django初期化後にインポート
from apps.itn_stream.store import ItnMemoryStore  # noqa: E402
from apps.itn_stream.receiver import itn_receiver_loop  # noqa: E402

itn_store = ItnMemoryStore()
_itn_task = None


async def application(scope, receive, send):
    """ASGI(非同期サーバー網プロトコル) アプリケーションのエントリポイント。
    
    UvicornやDaphne等のサーバーミドルウェアから呼び出され、HTTP通信やSSEをDjangoアプリ層へルーティングします。
    また当システム固有の特徴として、サーバー起動プロセスの一環として初回リクエスト受付時に
    `itn_receiver_loop`（ITN配信受信用無限ループ）を非同期タスクとしてバックグラウンドへ放ちます。
    """
    global _itn_task
    if _itn_task is None:
        _itn_task = asyncio.create_task(itn_receiver_loop(itn_store))
    await django_app(scope, receive, send)
