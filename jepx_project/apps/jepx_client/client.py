"""JEPX API クライアント (§3.4)

業務ロジックはこのクラスの send_request() を呼ぶだけで、
Socket/TLS/gzip/SOH-ETXフレーミング を意識する必要がない。
"""
import asyncio
import logging
import time

from django.conf import settings

from .connection import JepxConnection
from .protocol import JepxProtocol
from .pool import ConnectionPool
from .exceptions import (
    JepxError,
    JepxFormatError,
    JepxAuthError,
    JepxBusinessError,
    JepxSystemError,
    JepxConnectionError,
    JepxTimeoutError,
)

logger = logging.getLogger('jepx.api')
audit_logger = logging.getLogger('jepx.audit')


class JepxApiClient:
    """JEPX API送受信を抽象化する高レベルクライアント

    システム内の全ての業務ロジック（DAH/ITD）はこのクラスを経由してJEPXと通信します。
    内部でコネクションプールからの接続取得、パケット組立、送信、受信、パース、エラーステータス検証、
    およびタイムアウト時やシステムエラー(STATUS=19)時の再送（リトライ）制御を隠蔽して行っており、
    呼び出し元へは純粋な業務結果であるレスポンスの辞書(Dict)だけを返却します。
    """

    _pool: ConnectionPool | None = None

    def __init__(self):
        if JepxApiClient._pool is None:
            JepxApiClient._pool = ConnectionPool(
                host=settings.JEPX_HOST,
                port=settings.JEPX_PORT,
                max_connections=settings.JEPX_MAX_CONNECTIONS,
            )
        self.pool = JepxApiClient._pool
        self.member_id = settings.JEPX_MEMBER_ID
        self.max_retry = settings.JEPX_RETRY_MAX
        self.backoff_base = settings.JEPX_RETRY_BACKOFF_BASE

    async def send_request(self, api_code: str, body: dict) -> dict:
        """指定された種類のJEPX APIを呼び出し、一連の通信シーケンスを経てレスポンスbody(dict)を返す。

        Args:
            api_code: "DAH1001", "ITD1003" などのJEPX仕様書に記載された機能ID
            body: リクエストJSON (dict)

        Returns:
            レスポンスボディのdict

        Raises:
            JepxFormatError: STATUS=10 (リトライ不可)
            JepxAuthError: STATUS=11 (リトライ不可)
            JepxBusinessError: body.status != "200"
            JepxError: リトライ上限超過
        """
        packet = JepxProtocol.build_packet(self.member_id, api_code, body)
        last_error = None

        for attempt in range(1, self.max_retry + 1):
            conn = None
            try:
                conn = await self.pool.acquire()
                start_time = time.monotonic()

                await conn.send(packet)
                raw_response = await conn.receive()

                elapsed = time.monotonic() - start_time
                header, resp_body = JepxProtocol.parse_response(raw_response)

                # 監査ログ出力
                audit_logger.info(
                    "[API_COMM] api=%s, elapsed=%.3fs, STATUS=%s, body_status=%s",
                    api_code, elapsed,
                    header.get('STATUS'), resp_body.get('status', '-'),
                )

                # ヘッダSTATUS検証
                JepxProtocol.validate_status(header)

                # ボディ業務ステータス検証
                body_status = resp_body.get('status', '')
                if body_status not in ('200', ''):
                    raise JepxBusinessError(
                        body_status, resp_body.get('statusInfo', '')
                    )

                await self.pool.release(conn)
                return resp_body

            except (JepxSystemError, JepxConnectionError, JepxTimeoutError) as e:
                # リトライ対象
                last_error = e
                logger.warning(
                    "[RETRY] api=%s attempt=%d/%d error=%s",
                    api_code, attempt, self.max_retry, str(e),
                )
                if conn:
                    await conn.close()
                wait = self.backoff_base * (2 ** (attempt - 1))
                await asyncio.sleep(wait)

            except (JepxFormatError, JepxAuthError, JepxBusinessError):
                # リトライ不可 → 即スロー
                if conn:
                    await self.pool.release(conn)
                raise

        raise JepxError(f"リトライ上限超過 ({self.max_retry}回): {last_error}")

    async def start_stream(self, api_code: str, body: dict):
        """時間前市場の板情報・約定情報(ITN)を継続受信するための非同期ジェネレータ (AsyncGenerator)

        一度接続したTLSセッションを「切断せず」に保持し続け、JEPXから流れてくる(Pushされる)
        差分イベントを yield でイベントドリブンに返却し続けます。
        
        Args:
            api_code: "ITN1001"
            body: リクエストJSON (dict)
           
        Yields: 
            (header_dict, body_dict) — 配信データが来るたびにyield
        """
        conn = None
        try:
            conn = JepxConnection()
            await conn.connect(settings.JEPX_HOST, settings.JEPX_PORT)

            # 配信開始リクエスト送信
            packet = JepxProtocol.build_packet(self.member_id, api_code, body)
            await conn.send(packet)

            # 最初のレスポンス（全量配信）
            raw = await conn.receive()
            header, resp_body = JepxProtocol.parse_response(raw)
            JepxProtocol.validate_status(header)
            yield header, resp_body

            # 以降は差分配信をループ受信
            while True:
                raw = await conn.receive()
                header, resp_body = JepxProtocol.parse_response(raw)
                yield header, resp_body

        finally:
            if conn:
                await conn.close()

    @classmethod
    def get_pool_status(cls) -> dict:
        """プール状態を返す (ヘルスチェック用)"""
        if cls._pool:
            return cls._pool.get_status()
        return {'active': 0, 'idle': 0, 'max': 0}
