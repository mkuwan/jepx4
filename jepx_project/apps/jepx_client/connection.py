"""JEPX TLS Socket接続ラッパー (§3.6)

環境に応じたSSLContextを生成し、asyncio Socketで通信する。

TLS検証モード (JEPX_TLS_VERIFY と JEPX_TLS_CA_CERT の組合せ):
  Mode A: OSストア    — VERIFY=True,  CA_CERT=None  → OS証明書ストア参照
  Mode B: ファイル指定 — VERIFY=True,  CA_CERT=path  → 指定CAファイルで検証
  Mode C: 検証なし    — VERIFY=False               → 証明書検証スキップ
"""
import asyncio
import logging
import ssl
import time

from django.conf import settings

from .exceptions import JepxConnectionError, JepxTimeoutError

logger = logging.getLogger('jepx.api')


class JepxConnection:
    """JEPX TLS Socket 接続ラッパー"""

    def __init__(self):
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self.last_used: float = 0
        self._ssl_ctx = self._create_ssl_context()

    @staticmethod
    def _create_ssl_context() -> ssl.SSLContext:
        """環境に応じたSSLContextを生成する。

        3つのモードを設定値で制御:
          Mode A (OSストア):    JEPX_TLS_VERIFY=True  + JEPX_TLS_CA_CERT=None
          Mode B (ファイル指定): JEPX_TLS_VERIFY=True  + JEPX_TLS_CA_CERT=<path>
          Mode C (検証なし):    JEPX_TLS_VERIFY=False
        """
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_3  # TLS 1.3 強制
        ctx.maximum_version = ssl.TLSVersion.TLSv1_3
        ctx.check_hostname = False  # JEPX はIP直接接続のためホスト名検証不可

        if not settings.JEPX_TLS_VERIFY:
            # Mode C: 検証なし (レガシーdev互換)
            ctx.verify_mode = ssl.CERT_NONE
            logger.info("[TLS] Mode C: 証明書検証なし")
        elif settings.JEPX_TLS_CA_CERT:
            # Mode B: 指定CAファイルで検証 (dev+MockServer CA / stage)
            ctx.verify_mode = ssl.CERT_REQUIRED
            ctx.load_verify_locations(settings.JEPX_TLS_CA_CERT)
            logger.info("[TLS] Mode B: ファイル指定 (%s)", settings.JEPX_TLS_CA_CERT)
        else:
            # Mode A: OS証明書ストア参照 (prod推奨)
            ctx.verify_mode = ssl.CERT_REQUIRED
            ctx.load_default_certs()
            logger.info("[TLS] Mode A: OS証明書ストア")
        return ctx

    async def connect(self, host: str, port: int) -> None:
        """指定されたJEPXホストに対し、非同期(asyncio)のTLSソケットストリーム接続を確立する。
        
        接続が成功すると、以後の通信に用いる reader / writer をクラス内部に保持します。
        """
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
        """JEPXから送信されたデータを、ETX (0x03) を終端記号として受信する。

        TCP/IPの性質上、パケットが分割されて届く可能性があるため、
        whileループ内でバッファ(`buf`)に順次チャンクを連結し、
        ETXフラグメントを発見した段階で1つの電文として返却します。
        
        Raises:
            JepxConnectionError: ソケット切断や読取エラー時
            JepxTimeoutError: 所定秒数以内にETXに到達しなかった場合
        """
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
