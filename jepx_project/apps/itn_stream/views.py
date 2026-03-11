"""ITN配信View — SSE/ポーリング (§5.4)"""
import asyncio
import json
import time

from django.http import JsonResponse, StreamingHttpResponse
from django.views import View


class ItnStreamView(View):
    """社内クライアント（WebブラウザのJSダッシュボード等）に対して、ITNデータをリアルタイム配信するAPIエンドポイント。

    クライアントの能力に応じて、以下の2つのモードのいずれかで動作します。
    - mode=sse: サーバー・セント・イベント(SSE)を用いた真のリアルタイム・プッシュ配信 (推奨)
    - mode=poll: バージョン番号を指定するロングポーリング方式（SSE非対応やレガシーな環境向け）
    """

    @staticmethod
    async def get(request):
        """ITNデータを取得する。

        クエリパラメータ:
          - mode=sse: Server-Sent Events (ストリーム)
          - mode=poll (default): 最新スナップショットを返す
          - version=N: ポーリング時、version>N の場合のみ200を返す
        """
        # ASGIアプリからグローバルstoreを取得
        from config.asgi import itn_store

        mode = request.GET.get('mode', 'poll')

        if mode == 'sse':
            return StreamingHttpResponse(
                _sse_generator(itn_store),
                content_type='text/event-stream',
            )
        else:
            # ポーリングモード
            client_version = int(request.GET.get('version', 0))
            current_version = itn_store.get_version()

            if client_version >= current_version:
                return JsonResponse({'changed': False, 'version': current_version})

            snapshot = itn_store.get_snapshot()
            return JsonResponse({
                'changed': True,
                **snapshot,
            })


async def _sse_generator(store):
    """SSE(Server-Sent Events)のストリームを生成し続ける非同期ジェネレータ。
    
    インメモリストア側の更新バージョン番号を周期的に監視し、前回送信時から変更(インクリメント)があった場合のみ
    `data: {JSON}\n\n` の標準的なSSEフォーマット形式でテキストチャンクを下流ブラウザへ流し込みます。
    """
    last_version = 0
    while True:
        current_version = store.get_version()
        if current_version > last_version:
            snapshot = store.get_snapshot()
            data = json.dumps(snapshot, ensure_ascii=False, default=str)
            yield f"data: {data}\n\n"
            last_version = current_version
        await asyncio.sleep(1)  # 1秒ポーリング
