"""JEPX TLS Socket接続ラッパー (§3.6)

環境に応じたSSLContextを生成し、asyncio Socketで通信する。
- dev: 自己署名証明書許容 (MockServer)
- stage/prod: JEPXルートCA証明書で検証
"""
import asyncio
import ssl
import time

from django.conf import settings

from .exceptions import JepxConnectionError, JepxTimeoutError


class JepxConnection:
    """JEPX TLS Socket 接続ラッパー"""

    def __init__(self):
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self.last_used: float = 0
        self._ssl_ctx = self._create_ssl_context()

    @staticmethod
    def _create_ssl_context() -> ssl.SSLContext:
        """環境に応じたSSLContextを生成する"""
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_3  # TLS 1.3 強制
        ctx.maximum_version = ssl.TLSVersion.TLSv1_3

        if settings.JEPX_TLS_VERIFY:
            # stage/prod: JEPXルートCA証明書で検証
            ctx.verify_mode = ssl.CERT_REQUIRED
            ctx.check_hostname = False   # JEPX はIP直接接続のためホスト名検証不可
            ctx.load_verify_locations(settings.JEPX_TLS_CA_CERT)
        else:
            # dev: MockServerの自己署名証明書を許容
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        return ctx

    async def connect(self, host: str, port: int) -> None:
        """指定ホスト・ポートにTLS接続を確立する"""
        try:
            self.reader, self.writer = await asyncio.open_connection(
                host, port, ssl=self._ssl_ctx
            )
            self.last_used = time.monotonic()
        except (OSError, ssl.SSLError) as e:
            raise JepxConnectionError(f"TLS接続失敗: {host}:{port} - {e}") from e

    async def send(self, data: bytes) -> None:
        """データを送信する"""
        if not self.writer or self.writer.is_closing():
            raise JepxConnectionError("接続が確立されていません")
        try:
            self.writer.write(data)
            await self.writer.drain()
            self.last_used = time.monotonic()
        except (OSError, ConnectionError) as e:
            raise JepxConnectionError(f"送信エラー: {e}") from e

    async def receive(self) -> bytes:
        """ETX (0x03) が来るまでデータを受信する"""
        if not self.reader:
            raise JepxConnectionError("接続が確立されていません")
        buf = bytearray()
        try:
            while True:
                chunk = await asyncio.wait_for(
                    self.reader.read(8192),
                    timeout=settings.JEPX_SOCKET_TIMEOUT_SEC,
                )
                if not chunk:
                    raise JepxConnectionError("JEPX接続が切断されました")
                buf.extend(chunk)
                if b'\x03' in chunk:  # ETX検出
                    break
        except asyncio.TimeoutError:
            raise JepxTimeoutError(
                f"受信タイムアウト ({settings.JEPX_SOCKET_TIMEOUT_SEC}秒)"
            )
        except (OSError, ConnectionError) as e:
            raise JepxConnectionError(f"受信エラー: {e}") from e
        self.last_used = time.monotonic()
        return bytes(buf)

    async def close(self) -> None:
        """接続を閉じる"""
        if self.writer:
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except (OSError, ConnectionError):
                pass
            finally:
                self.writer = None
                self.reader = None

    def is_alive(self) -> bool:
        """接続が有効かどうかを返す"""
        return self.writer is not None and not self.writer.is_closing()
