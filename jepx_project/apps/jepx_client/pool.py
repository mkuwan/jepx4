"""JEPX コネクションプール (§3.7)

一般通信(DAH/ITD): プール上限 5 本
配信通信(ITN): 専用 1 本 (プールとは別管理)
"""
import asyncio
import logging
import time

from django.conf import settings

from .connection import JepxConnection

logger = logging.getLogger('jepx.api')


class ConnectionPool:
    """JEPX Socket コネクションプール

    TCP接続(TLSハンドシェイク等)はコストが高いため、使いまわす(Keep-Alive)仕組みを提供します。
    - `acquire()` でプールから空き接続を取得するか、上限内で新規作成します。
    - 使用後（送受信の1セット後など）は直ちに `release()` でプールへ返却(Idle化)します。
    """

    def __init__(
        self,
        host: str,
        port: int,
        max_connections: int = 5,
        tls_verify: bool = True,
        ca_cert: str | None = None,
    ):
        self.host = host
        self.port = port
        self.max_connections = max_connections
        self._idle: list[JepxConnection] = []
        self._in_use: set[JepxConnection] = set()
        self._lock = asyncio.Lock()

    async def acquire(self) -> JepxConnection:
        """プールから利用可能なSocket接続を1本取得する。

        - 空き接続があれば即座にそれを再利用します。
        - 空きがなく、上限数(max_connections)未満なら新規にTLS接続を確立して返却します。
        - 上限数に達していれば RuntimeError となります。（ITD等の同時打鍵制限に直結）
        """
        async with self._lock:
            # Idle接続があれば再利用
            while self._idle:
                conn = self._idle.pop(0)
                if conn.is_alive():
                    self._in_use.add(conn)
                    logger.debug(
                        "[POOL] 再利用 (idle=%d, in_use=%d)",
                        len(self._idle), len(self._in_use),
                    )
                    return conn
                else:
                    await conn.close()

            # 上限チェック
            total = len(self._in_use)
            if total >= self.max_connections:
                raise RuntimeError(
                    f"JEPX接続プール上限 ({self.max_connections}) に到達"
                )

            # 新規作成
            conn = JepxConnection()
            await conn.connect(self.host, self.port)
            self._in_use.add(conn)
            logger.info(
                "[POOL] 新規接続 (idle=%d, in_use=%d)",
                len(self._idle), len(self._in_use),
            )
            return conn

    async def release(self, conn: JepxConnection) -> None:
        """通信が済んだ接続をプールに返却し、他のリクエストが使えるようにする。

        もしサーバ側から切断されていたり、致命的なエラーが起きた後の接続なら、
        Idleリストには戻さずその場で完全に破棄します。
        """
        async with self._lock:
            self._in_use.discard(conn)
            if conn.is_alive():
                self._idle.append(conn)
            else:
                await conn.close()

    def get_idle_connections(self) -> list[JepxConnection]:
        """Idle接続の一覧を返す (Keep-Alive用)"""
        return list(self._idle)

    def get_status(self) -> dict:
        """プール状態を返す (ヘルスチェック用)"""
        return {
            'active': len(self._in_use),
            'idle': len(self._idle),
            'max': self.max_connections,
        }

    async def close_all(self) -> None:
        """全接続を閉じる"""
        async with self._lock:
            for conn in self._idle + list(self._in_use):
                await conn.close()
            self._idle.clear()
            self._in_use.clear()
