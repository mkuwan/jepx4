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

    acquire() で接続を取得し、使用後に release() で返却する。
    接続が不足している場合は新規作成する。
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
        """プールから接続を取得する。空ならば新規作成。"""
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
        """接続をプールに返却する"""
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
