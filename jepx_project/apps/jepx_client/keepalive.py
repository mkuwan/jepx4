"""JEPX Keep-Aliveデーモン (§3.8)

901接続技術書 §2.3: 3分間通信がないとサーバ側Socketが切断される。
これを回避するため、Idle接続に定期的にSYS1001を送信する。
"""
import asyncio
import logging
import time

from django.conf import settings

from .pool import ConnectionPool
from .protocol import JepxProtocol

logger = logging.getLogger('jepx.api')


class KeepAliveManager:
    """プール内の利用可能な全Idle接続に対し、切断予防のSYS1001パケットを定期送信するマネージャ。

    JEPXの仕様上「3分間通信がないと強制切断」されるため、バックグラウンドの非同期タスクとして
    常にプールを監視し、一定時間（目安:150秒）未使用のソケットがあれば自動でSYS1001を送信します。
    """

    def __init__(self, pool: ConnectionPool):
        self.pool = pool
        self.interval = settings.JEPX_KEEPALIVE_INTERVAL_SEC  # 150秒
        self._task: asyncio.Task | None = None

    def start(self):
        """バックグラウンドタスクとしてKeep-Aliveループを開始"""
        self._task = asyncio.create_task(self._keepalive_loop())

    def stop(self):
        """Keep-Aliveループを停止"""
        if self._task:
            self._task.cancel()

    async def _keepalive_loop(self):
        """10秒ごとにIdle接続をスキャンし、最終使用から150秒経過したものにPing(SYS1001)を送信する無限ループ。
        
        このループはタスクとして常駐し、stop()が呼ばれるかアプリが終了するまで走り続けます。
        """
        while True:
            await asyncio.sleep(10)  # 10秒ごとにスキャン
            now = time.monotonic()

            for conn in self.pool.get_idle_connections():
                elapsed = now - conn.last_used
                if elapsed >= self.interval and conn.is_alive():
                    try:
                        packet = JepxProtocol.build_packet(
                            settings.JEPX_MEMBER_ID, 'SYS1001', {}
                        )
                        await conn.send(packet)
                        raw = await conn.receive()
                        header, body = JepxProtocol.parse_response(raw)

                        if body.get('status') == '200':
                            logger.debug(
                                "[KEEPALIVE] SYS1001成功 (idle=%.0fs)", elapsed
                            )
                        else:
                            logger.warning(
                                "[KEEPALIVE] SYS1001異常応答: %s", body
                            )
                            await conn.close()
                    except Exception as e:
                        logger.warning("[KEEPALIVE] SYS1001失敗: %s", e)
                        await conn.close()
