"""§3.6 JepxConnection のユニットテスト

テスト観点:
- _create_ssl_context: Mode A (OS ストア) / Mode B (CA ファイル) / Mode C (検証なし)
- connect: 成功・失敗→ JepxConnectionError
- send: 正常・writer なし・writer closing・OSError
- receive: ETX 検出・タイムアウト→ JepxTimeoutError・空チャンク→ JepxConnectionError
- is_alive: writer を持つ/持たない/closing 状態
- close: writer あり・なし
"""
import asyncio
import ssl
import unittest
from unittest.mock import AsyncMock, MagicMock, patch, call

import os
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django
django.setup()

from apps.jepx_client.connection import JepxConnection
from apps.jepx_client.exceptions import JepxConnectionError, JepxTimeoutError


# ---------------------------------------------------------------------------
# SSL Context テスト
# ---------------------------------------------------------------------------

class TestCreateSSLContext(unittest.TestCase):
    """_create_ssl_context の3モードテスト"""

    def test_mode_c_no_verify(self):
        """Mode C: JEPX_TLS_VERIFY=False → CERT_NONE"""
        with patch('apps.jepx_client.connection.settings') as mock_settings:
            mock_settings.JEPX_TLS_VERIFY = False
            mock_settings.JEPX_TLS_CA_CERT = None
            ctx = JepxConnection._create_ssl_context()
        self.assertEqual(ctx.verify_mode, ssl.CERT_NONE)

    def test_mode_b_ca_file(self):
        """Mode B: JEPX_TLS_CA_CERT=<path> → CERT_REQUIRED, load_verify_locations 呼出"""
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.pem', delete=False) as f:
            ca_path = f.name
        try:
            with patch('apps.jepx_client.connection.settings') as mock_settings:
                mock_settings.JEPX_TLS_VERIFY = True
                mock_settings.JEPX_TLS_CA_CERT = ca_path
                with patch.object(ssl.SSLContext, 'load_verify_locations') as mock_load:
                    ctx = JepxConnection._create_ssl_context()
                    mock_load.assert_called_once_with(ca_path)
            self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)
        finally:
            os.unlink(ca_path)

    def test_mode_a_os_store(self):
        """Mode A: TLS_CA_CERT=None, VERIFY=True → CERT_REQUIRED, load_default_certs 呼出"""
        with patch('apps.jepx_client.connection.settings') as mock_settings:
            mock_settings.JEPX_TLS_VERIFY = True
            mock_settings.JEPX_TLS_CA_CERT = None
            with patch.object(ssl.SSLContext, 'load_default_certs') as mock_certs:
                ctx = JepxConnection._create_ssl_context()
                mock_certs.assert_called_once()
        self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)

    def test_tls_minimum_version_is_1_3(self):
        """TLS 1.3 強制設定がされていること"""
        with patch('apps.jepx_client.connection.settings') as mock_settings:
            mock_settings.JEPX_TLS_VERIFY = False
            mock_settings.JEPX_TLS_CA_CERT = None
            ctx = JepxConnection._create_ssl_context()
        self.assertEqual(ctx.minimum_version, ssl.TLSVersion.TLSv1_3)


# ---------------------------------------------------------------------------
# connect テスト
# ---------------------------------------------------------------------------

class TestJepxConnectionConnect(unittest.IsolatedAsyncioTestCase):
    """connect() の成功・失敗テスト"""

    async def test_connect_success(self):
        """正常接続: reader/writer が設定されること"""
        conn = JepxConnection.__new__(JepxConnection)
        conn._ssl_ctx = MagicMock()
        conn.last_used = 0

        mock_reader = MagicMock()
        mock_writer = MagicMock()

        with patch('asyncio.open_connection', AsyncMock(return_value=(mock_reader, mock_writer))):
            await conn.connect('127.0.0.1', 8888)

        self.assertIs(conn.reader, mock_reader)
        self.assertIs(conn.writer, mock_writer)

    async def test_connect_os_error_raises_jepx_connection_error(self):
        """OSError が JepxConnectionError に変換されること"""
        conn = JepxConnection.__new__(JepxConnection)
        conn._ssl_ctx = MagicMock()
        conn.last_used = 0

        with patch('asyncio.open_connection', side_effect=OSError("refused")):
            with self.assertRaises(JepxConnectionError) as ctx:
                await conn.connect('127.0.0.1', 8888)

        self.assertIn('127.0.0.1', str(ctx.exception))

    async def test_connect_ssl_error_raises_jepx_connection_error(self):
        """ssl.SSLError が JepxConnectionError に変換されること"""
        conn = JepxConnection.__new__(JepxConnection)
        conn._ssl_ctx = MagicMock()
        conn.last_used = 0

        with patch('asyncio.open_connection', side_effect=ssl.SSLError("cert fail")):
            with self.assertRaises(JepxConnectionError):
                await conn.connect('127.0.0.1', 8888)


# ---------------------------------------------------------------------------
# send テスト
# ---------------------------------------------------------------------------

class TestJepxConnectionSend(unittest.IsolatedAsyncioTestCase):
    """send() のテスト"""

    def _conn_with_writer(self, closing=False) -> JepxConnection:
        conn = JepxConnection.__new__(JepxConnection)
        conn.reader = MagicMock()
        conn.last_used = 0
        mock_writer = MagicMock()
        mock_writer.is_closing.return_value = closing
        mock_writer.drain = AsyncMock()
        conn.writer = mock_writer
        return conn

    async def test_send_success_writes_and_drains(self):
        """正常送信: write と drain が呼ばれること"""
        conn = self._conn_with_writer()
        data = b'\x01HEADER\x02BODY\x03'

        await conn.send(data)

        conn.writer.write.assert_called_once_with(data)
        conn.writer.drain.assert_awaited_once()

    async def test_send_updates_last_used(self):
        """送信後に last_used が更新されること"""
        conn = self._conn_with_writer()
        old_last_used = conn.last_used

        await conn.send(b'\x01\x02\x03')

        self.assertGreaterEqual(conn.last_used, old_last_used)

    async def test_send_without_writer_raises(self):
        """writer が None → JepxConnectionError"""
        conn = JepxConnection.__new__(JepxConnection)
        conn.writer = None
        conn.reader = None
        conn.last_used = 0

        with self.assertRaises(JepxConnectionError):
            await conn.send(b'data')

    async def test_send_closing_writer_raises(self):
        """writer.is_closing() == True → JepxConnectionError"""
        conn = self._conn_with_writer(closing=True)

        with self.assertRaises(JepxConnectionError):
            await conn.send(b'data')

    async def test_send_os_error_converted(self):
        """写き込み時の OSError が JepxConnectionError に変換されること"""
        conn = self._conn_with_writer()
        conn.writer.write.side_effect = OSError("broken pipe")

        with self.assertRaises(JepxConnectionError) as ctx:
            await conn.send(b'data')

        self.assertIn('送信エラー', str(ctx.exception))


# ---------------------------------------------------------------------------
# receive テスト
# ---------------------------------------------------------------------------

class TestJepxConnectionReceive(unittest.IsolatedAsyncioTestCase):
    """receive() のテスト"""

    def _conn_with_reader(self) -> JepxConnection:
        conn = JepxConnection.__new__(JepxConnection)
        conn.writer = MagicMock()
        conn.last_used = 0
        conn.reader = MagicMock()
        return conn

    async def test_receive_without_reader_raises(self):
        """reader が None → JepxConnectionError"""
        conn = JepxConnection.__new__(JepxConnection)
        conn.reader = None
        conn.last_used = 0

        with self.assertRaises(JepxConnectionError):
            with patch('django.conf.settings') as s:
                s.JEPX_SOCKET_TIMEOUT_SEC = 30
                await conn.receive()

    async def test_receive_single_chunk_with_etx(self):
        """ETX(\\x03) を含む1チャンクで完了すること"""
        conn = self._conn_with_reader()
        data = b'\x01HEADER\x02BODY\x03'

        async def mock_wait_for(coro, timeout):
            return data

        with patch('asyncio.wait_for', side_effect=mock_wait_for):
            with patch('django.conf.settings') as s:
                s.JEPX_SOCKET_TIMEOUT_SEC = 30
                result = await conn.receive()

        self.assertEqual(result, data)

    async def test_receive_multiple_chunks(self):
        """複数チャンクに分割されても最終的にETXで終了すること"""
        conn = self._conn_with_reader()
        chunk1 = b'\x01HEADER\x02'
        chunk2 = b'BODY'
        chunk3 = b'\x03'

        chunks = iter([chunk1, chunk2, chunk3])

        async def mock_wait_for(coro, timeout):
            return next(chunks)

        with patch('asyncio.wait_for', side_effect=mock_wait_for):
            with patch('django.conf.settings') as s:
                s.JEPX_SOCKET_TIMEOUT_SEC = 30
                result = await conn.receive()

        self.assertEqual(result, chunk1 + chunk2 + chunk3)
        self.assertIn(b'\x03', result)

    async def test_receive_timeout_raises_jepx_timeout_error(self):
        """asyncio.TimeoutError → JepxTimeoutError に変換されること"""
        conn = self._conn_with_reader()

        async def mock_wait_for(coro, timeout):
            raise asyncio.TimeoutError()

        with patch('asyncio.wait_for', side_effect=mock_wait_for):
            with patch('django.conf.settings') as s:
                s.JEPX_SOCKET_TIMEOUT_SEC = 30
                with self.assertRaises(JepxTimeoutError) as ctx:
                    await conn.receive()

        self.assertIn('タイムアウト', str(ctx.exception))

    async def test_receive_empty_chunk_raises_connection_error(self):
        """空チャンク (接続切断) → JepxConnectionError"""
        conn = self._conn_with_reader()

        async def mock_wait_for(coro, timeout):
            return b''  # 接続切断を示す空バイト

        with patch('asyncio.wait_for', side_effect=mock_wait_for):
            with patch('django.conf.settings') as s:
                s.JEPX_SOCKET_TIMEOUT_SEC = 30
                with self.assertRaises(JepxConnectionError):
                    await conn.receive()

    async def test_receive_updates_last_used(self):
        """受信後に last_used が更新されること"""
        conn = self._conn_with_reader()
        conn.last_used = 0
        data = b'\x01\x02BODY\x03'

        async def mock_wait_for(coro, timeout):
            return data

        with patch('asyncio.wait_for', side_effect=mock_wait_for):
            with patch('django.conf.settings') as s:
                s.JEPX_SOCKET_TIMEOUT_SEC = 30
                await conn.receive()

        self.assertGreater(conn.last_used, 0)

    async def test_receive_os_error_raises_connection_error(self):
        """receive 中の OSError → JepxConnectionError"""
        conn = self._conn_with_reader()

        async def mock_wait_for(coro, timeout):
            raise OSError("reset by peer")

        with patch('asyncio.wait_for', side_effect=mock_wait_for):
            with patch('django.conf.settings') as s:
                s.JEPX_SOCKET_TIMEOUT_SEC = 30
                with self.assertRaises(JepxConnectionError):
                    await conn.receive()


# ---------------------------------------------------------------------------
# is_alive / close テスト
# ---------------------------------------------------------------------------

class TestJepxConnectionLifecycle(unittest.IsolatedAsyncioTestCase):
    """is_alive / close のテスト"""

    def test_is_alive_no_writer(self):
        """writer が None → False"""
        conn = JepxConnection.__new__(JepxConnection)
        conn.writer = None
        self.assertFalse(conn.is_alive())

    def test_is_alive_closing_writer(self):
        """writer.is_closing() == True → False"""
        conn = JepxConnection.__new__(JepxConnection)
        mock_writer = MagicMock()
        mock_writer.is_closing.return_value = True
        conn.writer = mock_writer
        self.assertFalse(conn.is_alive())

    def test_is_alive_open_writer(self):
        """writer | is_closing() == False → True"""
        conn = JepxConnection.__new__(JepxConnection)
        mock_writer = MagicMock()
        mock_writer.is_closing.return_value = False
        conn.writer = mock_writer
        self.assertTrue(conn.is_alive())

    async def test_close_calls_writer_close_and_wait_closed(self):
        """close(): writer.close() と wait_closed() が呼ばれ, writer が None になること"""
        conn = JepxConnection.__new__(JepxConnection)
        mock_writer = MagicMock()
        mock_writer.close = MagicMock()
        mock_writer.wait_closed = AsyncMock()
        conn.writer = mock_writer
        conn.reader = MagicMock()

        await conn.close()

        mock_writer.close.assert_called_once()
        mock_writer.wait_closed.assert_awaited_once()
        self.assertIsNone(conn.writer)
        self.assertIsNone(conn.reader)

    async def test_close_no_writer_no_error(self):
        """writer が None でも close() は例外を発生させないこと"""
        conn = JepxConnection.__new__(JepxConnection)
        conn.writer = None
        conn.reader = None

        await conn.close()  # 例外なし

    async def test_close_os_error_silenced(self):
        """close 中の OSError はサイレントに無視されること"""
        conn = JepxConnection.__new__(JepxConnection)
        mock_writer = MagicMock()
        mock_writer.close = MagicMock(side_effect=OSError("closed"))
        mock_writer.wait_closed = AsyncMock()
        conn.writer = mock_writer
        conn.reader = MagicMock()

        await conn.close()  # 例外なし
        self.assertIsNone(conn.writer)


if __name__ == '__main__':
    unittest.main()
