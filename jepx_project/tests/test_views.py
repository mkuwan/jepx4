"""§5.2/§5.3 ITD API Views のユニットテスト

テスト観点:
- ItdBidView.post: 正常/JSONパースエラー/バリデーションエラー/重複入札/各JEPX例外
- ItdDeleteView.post: 正常/JSONパースエラー/bidNo 未入力/JEPX例外
- ItdInquiryView.get: 正常/deliveryDate 未入力/JEPX例外
- ItdContractView.get: 正常/deliveryDate 未入力/JEPX例外
- ItdSettlementView.get: 正常/fromDate 未入力/JEPX例外
- _handle_jepx_error: 各例外型のHTTPステータスコードマッピング
"""
import json
import unittest
from unittest.mock import AsyncMock, patch, MagicMock

import os
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django
django.setup()

from django.test import AsyncRequestFactory

from apps.itd_api.views import (
    ItdBidView,
    ItdDeleteView,
    ItdInquiryView,
    ItdContractView,
    ItdSettlementView,
    _handle_jepx_error,
)
from apps.jepx_client.exceptions import (
    JepxFormatError,
    JepxAuthError,
    JepxBusinessError,
    JepxSystemError,
    JepxConnectionError,
    JepxTimeoutError,
    JepxError,
)


# ---------------------------------------------------------------------------
# _handle_jepx_error テスト
# ---------------------------------------------------------------------------

class TestHandleJepxError(unittest.TestCase):
    """_handle_jepx_error の例外種別 → HTTPステータスのマッピングテスト"""

    def _json_body(self, response):
        return json.loads(response.content)

    def test_format_error_returns_502(self):
        resp = _handle_jepx_error(JepxFormatError("電文エラー"))
        self.assertEqual(resp.status_code, 502)
        self.assertEqual(self._json_body(resp)['error_code'], 'JEPX_FORMAT_ERROR')

    def test_auth_error_returns_502(self):
        resp = _handle_jepx_error(JepxAuthError("認証エラー"))
        self.assertEqual(resp.status_code, 502)
        self.assertEqual(self._json_body(resp)['error_code'], 'JEPX_AUTH_ERROR')

    def test_system_error_returns_502(self):
        resp = _handle_jepx_error(JepxSystemError("システムエラー"))
        self.assertEqual(resp.status_code, 502)
        self.assertEqual(self._json_body(resp)['error_code'], 'JEPX_SYSTEM_ERROR')

    def test_business_error_returns_400(self):
        resp = _handle_jepx_error(JepxBusinessError('400', '入札期間外'))
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(self._json_body(resp)['error_code'], 'JEPX_BUSINESS_ERROR')

    def test_connection_error_returns_503(self):
        resp = _handle_jepx_error(JepxConnectionError("接続失敗"))
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(self._json_body(resp)['error_code'], 'JEPX_CONNECTION_ERROR')

    def test_timeout_error_returns_504(self):
        resp = _handle_jepx_error(JepxTimeoutError("タイムアウト"))
        self.assertEqual(resp.status_code, 504)
        self.assertEqual(self._json_body(resp)['error_code'], 'JEPX_TIMEOUT')

    def test_unknown_error_returns_500(self):
        resp = _handle_jepx_error(RuntimeError("予期しないエラー"))
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(self._json_body(resp)['error_code'], 'INTERNAL_ERROR')

    def test_all_error_responses_have_success_false(self):
        """すべてのエラーレスポンスに success=False が含まれること"""
        errors = [
            JepxFormatError("f"), JepxAuthError("a"), JepxSystemError("s"),
            JepxBusinessError('400', 'b'), JepxConnectionError("c"),
            JepxTimeoutError("t"), RuntimeError("r"),
        ]
        for e in errors:
            resp = _handle_jepx_error(e)
            body = json.loads(resp.content)
            self.assertFalse(body['success'], f"{type(e).__name__} should return success=False")


# ---------------------------------------------------------------------------
# ItdBidView テスト
# ---------------------------------------------------------------------------

class TestItdBidView(unittest.IsolatedAsyncioTestCase):
    """ItdBidView.post のテスト"""

    def setUp(self):
        self.factory = AsyncRequestFactory()
        self.view = ItdBidView.as_view()
        self._valid_data = {
            'deliveryDate': '2026-04-01',
            'areaCd': '1',
            'timeCd': '1',
            'bidTypeCd': 'SELL-LIMIT',
            'price': 100.0,
            'volume': 50.0,
            'deliveryContractCd': 'BG001',
        }

    def _post(self, data):
        return self.factory.post(
            '/api/v1/itd/bid',
            data=json.dumps(data),
            content_type='application/json',
        )

    def _json_body(self, response):
        return json.loads(response.content)

    async def test_valid_bid_returns_200(self):
        """正常系: 200 と success=True が返ること"""
        req = self._post(self._valid_data)
        jepx_result = {'status': '200', 'bidNo': 'BID-001', 'statusInfo': '登録完了'}

        with patch('apps.itd_api.views.services.check_duplicate_bid', AsyncMock(return_value=None)):
            with patch('apps.itd_api.views.services.execute_itd_bid', AsyncMock(return_value=jepx_result)):
                resp = await self.view(req)

        self.assertEqual(resp.status_code, 200)
        body = self._json_body(resp)
        self.assertTrue(body['success'])
        self.assertEqual(body['bid_no'], 'BID-001')

    async def test_invalid_json_returns_400(self):
        """JSONパースエラー: 400 が返ること"""
        req = self.factory.post(
            '/api/v1/itd/bid',
            data='NOT_JSON',
            content_type='application/json',
        )
        resp = await self.view(req)
        self.assertEqual(resp.status_code, 400)
        body = self._json_body(resp)
        self.assertEqual(body['error_code'], 'VALIDATION_ERROR')

    async def test_validation_error_returns_400(self):
        """バリデーションエラー: 400 が返ること"""
        bad_data = {**self._valid_data, 'areaCd': '99'}  # 無効エリアコード
        req = self._post(bad_data)
        resp = await self.view(req)
        self.assertEqual(resp.status_code, 400)
        body = self._json_body(resp)
        self.assertEqual(body['error_code'], 'VALIDATION_ERROR')

    async def test_duplicate_bid_returns_409(self):
        """重複入札チェック: 409 Conflict が返ること"""
        req = self._post(self._valid_data)
        dup = {'bidNo': 'EXISTING-001'}

        with patch('apps.itd_api.views.services.check_duplicate_bid', AsyncMock(return_value=dup)):
            resp = await self.view(req)

        self.assertEqual(resp.status_code, 409)
        body = self._json_body(resp)
        self.assertEqual(body['error_code'], 'DUPLICATE_BID')
        self.assertIn('EXISTING-001', body['message'])

    async def test_jepx_business_error_returns_400(self):
        """JepxBusinessError: 400 が返ること"""
        req = self._post(self._valid_data)

        with patch('apps.itd_api.views.services.check_duplicate_bid', AsyncMock(return_value=None)):
            with patch('apps.itd_api.views.services.execute_itd_bid',
                       AsyncMock(side_effect=JepxBusinessError('400', '入札期間外'))):
                resp = await self.view(req)

        self.assertEqual(resp.status_code, 400)

    async def test_jepx_connection_error_returns_503(self):
        """JepxConnectionError: 503 が返ること"""
        req = self._post(self._valid_data)

        with patch('apps.itd_api.views.services.check_duplicate_bid', AsyncMock(return_value=None)):
            with patch('apps.itd_api.views.services.execute_itd_bid',
                       AsyncMock(side_effect=JepxConnectionError("接続失敗"))):
                resp = await self.view(req)

        self.assertEqual(resp.status_code, 503)

    async def test_jepx_timeout_returns_504(self):
        """JepxTimeoutError: 504 が返ること"""
        req = self._post(self._valid_data)

        with patch('apps.itd_api.views.services.check_duplicate_bid', AsyncMock(return_value=None)):
            with patch('apps.itd_api.views.services.execute_itd_bid',
                       AsyncMock(side_effect=JepxTimeoutError("タイムアウト"))):
                resp = await self.view(req)

        self.assertEqual(resp.status_code, 504)

    async def test_response_is_json(self):
        """レスポンスの Content-Type が application/json であること"""
        req = self._post(self._valid_data)

        with patch('apps.itd_api.views.services.check_duplicate_bid', AsyncMock(return_value=None)):
            with patch('apps.itd_api.views.services.execute_itd_bid',
                       AsyncMock(return_value={'status': '200', 'bidNo': 'BID-001', 'statusInfo': 'OK'})):
                resp = await self.view(req)

        self.assertIn('application/json', resp['Content-Type'])


# ---------------------------------------------------------------------------
# ItdDeleteView テスト
# ---------------------------------------------------------------------------

class TestItdDeleteView(unittest.IsolatedAsyncioTestCase):
    """ItdDeleteView.post のテスト"""

    def setUp(self):
        self.factory = AsyncRequestFactory()
        self.view = ItdDeleteView.as_view()

    def _post(self, data):
        return self.factory.post(
            '/api/v1/itd/delete',
            data=json.dumps(data),
            content_type='application/json',
        )

    def _json_body(self, response):
        return json.loads(response.content)

    async def test_valid_delete_returns_200(self):
        """正常系: 200 と success=True が返ること"""
        req = self._post({'deliveryDate': '2026-04-01', 'bidNo': 'BID-001'})
        jepx_result = {'status': '200', 'statusInfo': '削除完了'}

        with patch('apps.itd_api.views.services.execute_itd_delete', AsyncMock(return_value=jepx_result)):
            resp = await self.view(req)

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(self._json_body(resp)['success'])

    async def test_invalid_json_returns_400(self):
        """JSONパースエラー: 400"""
        req = self.factory.post(
            '/api/v1/itd/delete',
            data='NOT_JSON',
            content_type='application/json',
        )
        resp = await self.view(req)
        self.assertEqual(resp.status_code, 400)

    async def test_missing_bid_no_returns_400(self):
        """bidNo 未入力: 400"""
        req = self._post({'deliveryDate': '2026-04-01'})
        resp = await self.view(req)
        self.assertEqual(resp.status_code, 400)
        body = self._json_body(resp)
        self.assertEqual(body['error_code'], 'VALIDATION_ERROR')

    async def test_jepx_error_returns_error_status(self):
        """JepxConnectionError: 503"""
        req = self._post({'deliveryDate': '2026-04-01', 'bidNo': 'BID-001'})

        with patch('apps.itd_api.views.services.execute_itd_delete',
                   AsyncMock(side_effect=JepxConnectionError("接続失敗"))):
            resp = await self.view(req)

        self.assertEqual(resp.status_code, 503)

    async def test_jepx_business_error_returns_400(self):
        """JepxBusinessError: 400"""
        req = self._post({'deliveryDate': '2026-04-01', 'bidNo': 'BID-001'})

        with patch('apps.itd_api.views.services.execute_itd_delete',
                   AsyncMock(side_effect=JepxBusinessError('404', '入札が見つかりません'))):
            resp = await self.view(req)

        self.assertEqual(resp.status_code, 400)


# ---------------------------------------------------------------------------
# ItdInquiryView テスト
# ---------------------------------------------------------------------------

class TestItdInquiryView(unittest.IsolatedAsyncioTestCase):
    """ItdInquiryView.get のテスト"""

    def setUp(self):
        self.factory = AsyncRequestFactory()
        self.view = ItdInquiryView.as_view()

    def _json_body(self, response):
        return json.loads(response.content)

    async def test_valid_inquiry_returns_200(self):
        """正常系: 200 と bids が返ること"""
        req = self.factory.get('/api/v1/itd/inquiry', {'deliveryDate': '2026-04-01'})
        jepx_result = {'bids': [{'bidNo': 'B1'}, {'bidNo': 'B2'}]}

        with patch('apps.itd_api.views.services.execute_itd_inquiry', AsyncMock(return_value=jepx_result)):
            resp = await self.view(req)

        self.assertEqual(resp.status_code, 200)
        body = self._json_body(resp)
        self.assertTrue(body['success'])
        self.assertEqual(body['count'], 2)

    async def test_missing_delivery_date_returns_400(self):
        """deliveryDate 未入力: 400"""
        req = self.factory.get('/api/v1/itd/inquiry')
        resp = await self.view(req)
        self.assertEqual(resp.status_code, 400)
        body = self._json_body(resp)
        self.assertEqual(body['error_code'], 'VALIDATION_ERROR')

    async def test_jepx_timeout_returns_504(self):
        """JepxTimeoutError: 504"""
        req = self.factory.get('/api/v1/itd/inquiry', {'deliveryDate': '2026-04-01'})

        with patch('apps.itd_api.views.services.execute_itd_inquiry',
                   AsyncMock(side_effect=JepxTimeoutError("タイムアウト"))):
            resp = await self.view(req)

        self.assertEqual(resp.status_code, 504)

    async def test_with_time_cd_param(self):
        """timeCd パラメータが渡されること"""
        req = self.factory.get('/api/v1/itd/inquiry', {
            'deliveryDate': '2026-04-01',
            'timeCd': '5',
        })

        captured = {}

        async def mock_inquiry(data):
            captured.update(data)
            return {'bids': []}

        with patch('apps.itd_api.views.services.execute_itd_inquiry', side_effect=mock_inquiry):
            resp = await self.view(req)

        self.assertEqual(captured.get('timeCd'), '5')


# ---------------------------------------------------------------------------
# ItdContractView テスト
# ---------------------------------------------------------------------------

class TestItdContractView(unittest.IsolatedAsyncioTestCase):
    """ItdContractView.get のテスト"""

    def setUp(self):
        self.factory = AsyncRequestFactory()
        self.view = ItdContractView.as_view()

    def _json_body(self, response):
        return json.loads(response.content)

    async def test_valid_contract_returns_200(self):
        """正常系: 200 と contracts が返ること"""
        req = self.factory.get('/api/v1/itd/contract', {'deliveryDate': '2026-04-01'})
        jepx_result = {'contractResults': [{'bidNo': 'B1', 'contractPrice': 100}]}

        with patch('apps.itd_api.views.services.execute_itd_contract', AsyncMock(return_value=jepx_result)):
            resp = await self.view(req)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self._json_body(resp)['count'], 1)

    async def test_missing_delivery_date_returns_400(self):
        """deliveryDate 未入力: 400"""
        req = self.factory.get('/api/v1/itd/contract')
        resp = await self.view(req)
        self.assertEqual(resp.status_code, 400)

    async def test_jepx_system_error_returns_502(self):
        """JepxSystemError: 502"""
        req = self.factory.get('/api/v1/itd/contract', {'deliveryDate': '2026-04-01'})

        with patch('apps.itd_api.views.services.execute_itd_contract',
                   AsyncMock(side_effect=JepxSystemError("システムエラー"))):
            resp = await self.view(req)

        self.assertEqual(resp.status_code, 502)


# ---------------------------------------------------------------------------
# ItdSettlementView テスト
# ---------------------------------------------------------------------------

class TestItdSettlementView(unittest.IsolatedAsyncioTestCase):
    """ItdSettlementView.get のテスト"""

    def setUp(self):
        self.factory = AsyncRequestFactory()
        self.view = ItdSettlementView.as_view()

    def _json_body(self, response):
        return json.loads(response.content)

    async def test_valid_settlement_returns_200(self):
        """正常系: 200 と settlements が返ること"""
        req = self.factory.get('/api/v1/itd/settlement', {'fromDate': '2026-04-01'})
        jepx_result = {'settlements': [{'settlementNo': 'S001'}]}

        with patch('apps.itd_api.views.services.execute_itd_settlement', AsyncMock(return_value=jepx_result)):
            resp = await self.view(req)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self._json_body(resp)['count'], 1)

    async def test_missing_from_date_returns_400(self):
        """fromDate 未入力: 400"""
        req = self.factory.get('/api/v1/itd/settlement')
        resp = await self.view(req)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(self._json_body(resp)['error_code'], 'VALIDATION_ERROR')

    async def test_jepx_auth_error_returns_502(self):
        """JepxAuthError: 502"""
        req = self.factory.get('/api/v1/itd/settlement', {'fromDate': '2026-04-01'})

        with patch('apps.itd_api.views.services.execute_itd_settlement',
                   AsyncMock(side_effect=JepxAuthError("認証エラー"))):
            resp = await self.view(req)

        self.assertEqual(resp.status_code, 502)

    async def test_with_to_date_param(self):
        """toDate パラメータが service に渡されること"""
        req = self.factory.get('/api/v1/itd/settlement', {
            'fromDate': '2026-04-01',
            'toDate': '2026-04-30',
        })

        captured = {}

        async def mock_settlement(data):
            captured.update(data)
            return {'settlements': []}

        with patch('apps.itd_api.views.services.execute_itd_settlement', side_effect=mock_settlement):
            resp = await self.view(req)

        self.assertEqual(captured.get('toDate'), '2026-04-30')


if __name__ == '__main__':
    unittest.main()
