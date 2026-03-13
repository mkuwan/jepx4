"""§3.4 JepxApiClient のユニットテスト

テスト観点:
- send_request: 正常系・リトライ・上限超過・リトライ不可例外の即時再スロー
- body status 検証 → JepxBusinessError
- Connection / Pool との連携 (モック使用)
- get_pool_status
"""
import asyncio
import json
import unittest
import zlib
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django
django.setup()

from apps.jepx_client.client import JepxApiClient
from apps.jepx_client.exceptions import (
    JepxError,
    JepxFormatError,
    JepxAuthError,
    JepxBusinessError,
    JepxSystemError,
    JepxConnectionError,
    JepxTimeoutError,
)
from apps.jepx_client.protocol import SOH, STX, ETX


def _build_raw_response(header_str: str, body: dict) -> bytes:
    """テスト用レスポンス電文を組み立てる"""
    compressed = zlib.compress(json.dumps(body).encode('utf-8'))
    header = f"{header_str},SIZE={len(compressed)}".encode('ascii')
    return SOH + header + STX + compressed + ETX


def _ok_response(body_status='200', **kwargs) -> bytes:
    """STATUS=00, body.status=<body_status> のレスポンス"""
    body = {'status': body_status, 'statusInfo': 'OK', **kwargs}
    return _build_raw_response('STATUS=00', body)


class TestJepxApiClientSendRequest(unittest.IsolatedAsyncioTestCase):
    """send_request のテスト"""

    def setUp(self):
        """各テストでシングルトンプールをリセット"""
        JepxApiClient._pool = None

    def _make_client(self, conn_mock=None, max_retry=3):
        """モックプールを持つ JepxApiClient インスタンスを作成"""
        client = JepxApiClient.__new__(JepxApiClient)
        client.member_id = '9999'
        client.max_retry = max_retry
        client.backoff_base = 0.001  # テスト高速化 (sleep をほぼゼロに)

        pool_mock = MagicMock()
        if conn_mock is None:
            conn_mock = AsyncMock()
        pool_mock.acquire = AsyncMock(return_value=conn_mock)
        pool_mock.release = AsyncMock()
        client.pool = pool_mock
        return client, pool_mock, conn_mock

    # -------------------------------------------------------
    # 正常系
    # -------------------------------------------------------
    async def test_send_request_success_returns_body(self):
        """正常系: レスポンスのBodyが返ること"""
        client, pool_mock, conn_mock = self._make_client()
        conn_mock.send = AsyncMock()
        conn_mock.receive = AsyncMock(
            return_value=_ok_response('200', bidNo='1234567890')
        )

        result = await client.send_request('ITD1001', {'deliveryDate': '2026-04-01'})

        self.assertEqual(result['status'], '200')
        self.assertEqual(result['bidNo'], '1234567890')
        pool_mock.acquire.assert_awaited_once()
        pool_mock.release.assert_awaited_once()

    async def test_send_request_releases_conn_on_success(self):
        """正常系: 成功後に release が呼ばれること"""
        client, pool_mock, conn_mock = self._make_client()
        conn_mock.send = AsyncMock()
        conn_mock.receive = AsyncMock(return_value=_ok_response())

        await client.send_request('DAH1001', {})

        pool_mock.release.assert_awaited_once_with(conn_mock)

    async def test_send_request_empty_body_status_ok(self):
        """body.status が空文字列(一部APIは statusなし) でも正常終了すること"""
        client, pool_mock, conn_mock = self._make_client()
        conn_mock.send = AsyncMock()
        # status '' → 通常完了とみなす
        conn_mock.receive = AsyncMock(
            return_value=_ok_response('')
        )

        result = await client.send_request('SYS1001', {})
        self.assertEqual(result.get('status', ''), '')

    # -------------------------------------------------------
    # リトライ対象例外
    # -------------------------------------------------------
    async def test_retry_on_system_error_then_success(self):
        """JepxSystemError → 1回リトライして成功"""
        client, pool_mock, _ = self._make_client(max_retry=3)

        conn_fail = AsyncMock()
        conn_fail.send = AsyncMock(side_effect=JepxSystemError("システム障害"))
        conn_fail.close = AsyncMock()

        conn_ok = AsyncMock()
        conn_ok.send = AsyncMock()
        conn_ok.receive = AsyncMock(return_value=_ok_response())

        pool_mock.acquire = AsyncMock(side_effect=[conn_fail, conn_ok])

        result = await client.send_request('DAH1001', {})
        self.assertEqual(result['status'], '200')
        self.assertEqual(pool_mock.acquire.await_count, 2)

    async def test_retry_on_connection_error(self):
        """JepxConnectionError → リトライ上限まで試行して JepxError が発生すること"""
        client, pool_mock, conn_mock = self._make_client(max_retry=2)
        conn_mock.send = AsyncMock(side_effect=JepxConnectionError("接続失敗"))
        conn_mock.close = AsyncMock()
        pool_mock.acquire = AsyncMock(return_value=conn_mock)

        with self.assertRaises(JepxError):
            await client.send_request('DAH1001', {})

        # max_retry=2 回だけ試みた
        self.assertEqual(pool_mock.acquire.await_count, 2)

    async def test_retry_on_timeout_error(self):
        """JepxTimeoutError → リトライ対象"""
        client, pool_mock, conn_mock = self._make_client(max_retry=2)
        conn_mock.send = AsyncMock(side_effect=JepxTimeoutError("タイムアウト"))
        conn_mock.close = AsyncMock()
        pool_mock.acquire = AsyncMock(return_value=conn_mock)

        with self.assertRaises(JepxError):
            await client.send_request('DAH1001', {})

        self.assertEqual(pool_mock.acquire.await_count, 2)

    async def test_retry_receive_then_success(self):
        """receive 失敗 → リトライして成功"""
        client, pool_mock, _ = self._make_client(max_retry=3)

        conn_fail = AsyncMock()
        conn_fail.send = AsyncMock()
        conn_fail.receive = AsyncMock(side_effect=JepxConnectionError("受信エラー"))
        conn_fail.close = AsyncMock()

        conn_ok = AsyncMock()
        conn_ok.send = AsyncMock()
        conn_ok.receive = AsyncMock(return_value=_ok_response())

        pool_mock.acquire = AsyncMock(side_effect=[conn_fail, conn_ok])

        result = await client.send_request('DAH1001', {})
        self.assertEqual(result['status'], '200')

    async def test_retry_exhausted_error_message_contains_attempt_count(self):
        """リトライ上限超過した JepxError に回数情報が含まれること"""
        client, pool_mock, conn_mock = self._make_client(max_retry=3)
        conn_mock.send = AsyncMock(side_effect=JepxConnectionError("接続エラー"))
        conn_mock.close = AsyncMock()
        pool_mock.acquire = AsyncMock(return_value=conn_mock)

        with self.assertRaises(JepxError) as ctx:
            await client.send_request('DAH1001', {})

        self.assertIn('3', str(ctx.exception))

    # -------------------------------------------------------
    # リトライ不可例外 → 即スロー
    # -------------------------------------------------------
    async def test_format_error_not_retried(self):
        """JepxFormatError は即スロー (1回のみ acquire)"""
        client, pool_mock, conn_mock = self._make_client(max_retry=3)
        conn_mock.send = AsyncMock()
        conn_mock.receive = AsyncMock(
            return_value=_build_raw_response('STATUS=10', {'status': '200'})
        )

        with self.assertRaises(JepxFormatError):
            await client.send_request('DAH1001', {})

        self.assertEqual(pool_mock.acquire.await_count, 1)

    async def test_auth_error_not_retried(self):
        """JepxAuthError は即スロー"""
        client, pool_mock, conn_mock = self._make_client(max_retry=3)
        conn_mock.send = AsyncMock()
        conn_mock.receive = AsyncMock(
            return_value=_build_raw_response('STATUS=11', {'status': '200'})
        )

        with self.assertRaises(JepxAuthError):
            await client.send_request('DAH1001', {})

        self.assertEqual(pool_mock.acquire.await_count, 1)

    async def test_business_error_on_body_400(self):
        """body.status='400' → JepxBusinessError が発生すること"""
        client, pool_mock, conn_mock = self._make_client()
        conn_mock.send = AsyncMock()
        conn_mock.receive = AsyncMock(
            return_value=_ok_response('400')
        )

        with self.assertRaises(JepxBusinessError) as ctx:
            await client.send_request('DAH1001', {})

        self.assertEqual(ctx.exception.status, '400')

    async def test_business_error_not_retried(self):
        """JepxBusinessError はリトライ不可 (1回のみ acquire)"""
        client, pool_mock, conn_mock = self._make_client(max_retry=3)
        conn_mock.send = AsyncMock()
        conn_mock.receive = AsyncMock(
            return_value=_ok_response('E001')
        )

        with self.assertRaises(JepxBusinessError):
            await client.send_request('DAH1001', {})

        self.assertEqual(pool_mock.acquire.await_count, 1)

    async def test_business_error_status_info_preserved(self):
        """JepxBusinessError に status_info が保持されること"""
        client, pool_mock, conn_mock = self._make_client()
        body = {'status': '400', 'statusInfo': '入札期間外です'}
        compressed = zlib.compress(json.dumps(body).encode('utf-8'))
        raw = SOH + f"STATUS=00,SIZE={len(compressed)}".encode('ascii') + STX + compressed + ETX
        conn_mock.send = AsyncMock()
        conn_mock.receive = AsyncMock(return_value=raw)

        with self.assertRaises(JepxBusinessError) as ctx:
            await client.send_request('DAH1001', {})

        self.assertEqual(ctx.exception.status_info, '入札期間外です')

    # -------------------------------------------------------
    # get_pool_status
    # -------------------------------------------------------
    def test_get_pool_status_no_pool(self):
        """プール未作成時はデフォルト値を返す"""
        JepxApiClient._pool = None
        status = JepxApiClient.get_pool_status()
        self.assertEqual(status, {'active': 0, 'idle': 0, 'max': 0})

    def test_get_pool_status_with_pool(self):
        """プール作成済みの場合はプール状態を返す"""
        pool_mock = MagicMock()
        pool_mock.get_status.return_value = {'active': 1, 'idle': 2, 'max': 5}
        JepxApiClient._pool = pool_mock

        status = JepxApiClient.get_pool_status()
        self.assertEqual(status['active'], 1)
        self.assertEqual(status['idle'], 2)
        self.assertEqual(status['max'], 5)

    def tearDown(self):
        JepxApiClient._pool = None


if __name__ == '__main__':
    unittest.main()
