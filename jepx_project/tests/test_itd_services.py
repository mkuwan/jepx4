"""§5 ITD業務サービス (apps/itd_api/services.py) のユニットテスト

テスト観点:
- execute_itd_bid: リクエストbody構築・オプション項目・JepxApiClient呼出
- execute_itd_delete: body構築
- execute_itd_inquiry: timeCd あり・なし
- execute_itd_contract: body構築
- execute_itd_settlement: toDate あり・なし
- check_duplicate_bid: 重複あり・なし・areaCd/bidTypeCd の一致判定
"""
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import os
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django
django.setup()

from apps.jepx_client.client import JepxApiClient
import apps.itd_api.services as services


def _patch_client(return_value=None, side_effect=None):
    """JepxApiClient.send_request をモックするコンテキストマネージャを返す"""
    mock_send = AsyncMock(return_value=return_value or {'status': '200', 'statusInfo': 'OK'})
    if side_effect:
        mock_send.side_effect = side_effect
    return patch.object(JepxApiClient, 'send_request', mock_send)


# ---------------------------------------------------------------------------
# execute_itd_bid テスト
# ---------------------------------------------------------------------------

class TestExecuteItdBid(unittest.IsolatedAsyncioTestCase):
    """execute_itd_bid のテスト"""

    async def test_basic_body_construction(self):
        """必須フィールドが正しく body に展開されること"""
        data = {
            'deliveryDate': '2026-04-01',
            'timeCd': '10',
            'areaCd': '3',
            'bidTypeCd': 'SELL-LIMIT',
            'price': 100.0,
            'volume': 50.0,
        }
        captured = {}

        async def mock_send(api_code, body):
            captured.update(body)
            return {'status': '200', 'bidNo': 'B001', 'statusInfo': 'OK'}

        with patch.object(JepxApiClient, 'send_request', side_effect=mock_send):
            with patch.object(JepxApiClient, '__init__', return_value=None):
                JepxApiClient.pool = MagicMock()
                JepxApiClient.member_id = '9999'
                JepxApiClient.max_retry = 3
                JepxApiClient.backoff_base = 0.01
                result = await services.execute_itd_bid(data)

        self.assertEqual(captured['deliveryDate'], '2026-04-01')
        self.assertEqual(captured['timeCd'], '10')
        self.assertEqual(captured['areaCd'], '3')
        self.assertEqual(captured['bidTypeCd'], 'SELL-LIMIT')
        self.assertEqual(captured['price'], 100.0)
        self.assertEqual(captured['volume'], 50.0)

    async def test_optional_delivery_contract_included(self):
        """deliveryContractCd が body に含まれること"""
        data = {
            'deliveryDate': '2026-04-01',
            'timeCd': '1',
            'areaCd': '1',
            'bidTypeCd': 'SELL-LIMIT',
            'price': 100.0,
            'volume': 50.0,
            'deliveryContractCd': 'BG001',
        }
        captured = {}

        async def mock_send(api_code, body):
            captured.update(body)
            return {'status': '200', 'bidNo': 'B001', 'statusInfo': 'OK'}

        with patch.object(JepxApiClient, 'send_request', side_effect=mock_send):
            with patch.object(JepxApiClient, '__init__', return_value=None):
                JepxApiClient.pool = MagicMock()
                JepxApiClient.member_id = '9999'
                JepxApiClient.max_retry = 3
                JepxApiClient.backoff_base = 0.01
                await services.execute_itd_bid(data)

        self.assertEqual(captured['deliveryContractCd'], 'BG001')

    async def test_optional_note_truncated_to_100(self):
        """note が100文字に切り詰められること"""
        data = {
            'deliveryDate': '2026-04-01',
            'timeCd': '1',
            'areaCd': '1',
            'bidTypeCd': 'SELL-LIMIT',
            'price': 100.0,
            'volume': 50.0,
            'note': 'A' * 150,
        }
        captured = {}

        async def mock_send(api_code, body):
            captured.update(body)
            return {'status': '200', 'bidNo': 'B001', 'statusInfo': 'OK'}

        with patch.object(JepxApiClient, 'send_request', side_effect=mock_send):
            with patch.object(JepxApiClient, '__init__', return_value=None):
                JepxApiClient.pool = MagicMock()
                JepxApiClient.member_id = '9999'
                JepxApiClient.max_retry = 3
                JepxApiClient.backoff_base = 0.01
                await services.execute_itd_bid(data)

        self.assertEqual(len(captured['note']), 100)

    async def test_no_note_if_not_provided(self):
        """note がない場合は body に含まれないこと"""
        data = {
            'deliveryDate': '2026-04-01',
            'timeCd': '1',
            'areaCd': '1',
            'bidTypeCd': 'SELL-LIMIT',
            'price': 100.0,
            'volume': 50.0,
        }
        captured = {}

        async def mock_send(api_code, body):
            captured.update(body)
            return {'status': '200', 'bidNo': 'B001', 'statusInfo': 'OK'}

        with patch.object(JepxApiClient, 'send_request', side_effect=mock_send):
            with patch.object(JepxApiClient, '__init__', return_value=None):
                JepxApiClient.pool = MagicMock()
                JepxApiClient.member_id = '9999'
                JepxApiClient.max_retry = 3
                JepxApiClient.backoff_base = 0.01
                await services.execute_itd_bid(data)

        self.assertNotIn('note', captured)

    async def test_uses_itd1001_api_code(self):
        """ITD1001 として呼ばれること"""
        data = {
            'deliveryDate': '2026-04-01',
            'timeCd': '1',
            'areaCd': '1',
            'bidTypeCd': 'SELL-LIMIT',
            'price': 100.0,
            'volume': 50.0,
        }
        captured_api = []

        async def mock_send(api_code, body):
            captured_api.append(api_code)
            return {'status': '200', 'bidNo': 'X', 'statusInfo': 'OK'}

        with patch.object(JepxApiClient, 'send_request', side_effect=mock_send):
            with patch.object(JepxApiClient, '__init__', return_value=None):
                JepxApiClient.pool = MagicMock()
                JepxApiClient.member_id = '9999'
                JepxApiClient.max_retry = 3
                JepxApiClient.backoff_base = 0.01
                await services.execute_itd_bid(data)

        self.assertEqual(captured_api[0], 'ITD1001')


# ---------------------------------------------------------------------------
# execute_itd_delete テスト
# ---------------------------------------------------------------------------

class TestExecuteItdDelete(unittest.IsolatedAsyncioTestCase):
    """execute_itd_delete のテスト"""

    async def _call_delete(self, data):
        captured = {}

        async def mock_send(api_code, body):
            captured['api_code'] = api_code
            captured.update(body)
            return {'status': '200', 'statusInfo': '削除完了'}

        with patch.object(JepxApiClient, 'send_request', side_effect=mock_send):
            with patch.object(JepxApiClient, '__init__', return_value=None):
                JepxApiClient.pool = MagicMock()
                JepxApiClient.member_id = '9999'
                JepxApiClient.max_retry = 3
                JepxApiClient.backoff_base = 0.01
                result = await services.execute_itd_delete(data)
        return result, captured

    async def test_uses_itd1002_api_code(self):
        """ITD1002 として呼ばれること"""
        _, captured = await self._call_delete({
            'deliveryDate': '2026-04-01',
            'bidNo': 'BID-001',
        })
        self.assertEqual(captured['api_code'], 'ITD1002')

    async def test_body_contains_bid_no(self):
        """JEPX仕様903: body の削除対象入札番号フィールドは targetBidNo であること"""
        _, captured = await self._call_delete({
            'deliveryDate': '2026-04-01',
            'bidNo': 'BID-001',
        })
        self.assertEqual(captured['targetBidNo'], 'BID-001')

    async def test_body_contains_delivery_date(self):
        """body に deliveryDate が含まれること"""
        _, captured = await self._call_delete({
            'deliveryDate': '2026-04-01',
            'bidNo': 'BID-001',
        })
        self.assertEqual(captured['deliveryDate'], '2026-04-01')


# ---------------------------------------------------------------------------
# execute_itd_inquiry テスト
# ---------------------------------------------------------------------------

class TestExecuteItdInquiry(unittest.IsolatedAsyncioTestCase):
    """execute_itd_inquiry のテスト"""

    async def _call_inquiry(self, data):
        captured = {}

        async def mock_send(api_code, body):
            captured['api_code'] = api_code
            captured.update(body)
            return {'bids': []}

        with patch.object(JepxApiClient, 'send_request', side_effect=mock_send):
            with patch.object(JepxApiClient, '__init__', return_value=None):
                JepxApiClient.pool = MagicMock()
                JepxApiClient.member_id = '9999'
                JepxApiClient.max_retry = 3
                JepxApiClient.backoff_base = 0.01
                result = await services.execute_itd_inquiry(data)
        return result, captured

    async def test_uses_itd1003_api_code(self):
        """ITD1003 として呼ばれること"""
        _, captured = await self._call_inquiry({'deliveryDate': '2026-04-01'})
        self.assertEqual(captured['api_code'], 'ITD1003')

    async def test_without_time_cd(self):
        """timeCd がない場合は body に含まれないこと"""
        _, captured = await self._call_inquiry({'deliveryDate': '2026-04-01'})
        self.assertNotIn('timeCd', captured)

    async def test_with_time_cd(self):
        """timeCd がある場合は body に含まれること"""
        _, captured = await self._call_inquiry({
            'deliveryDate': '2026-04-01',
            'timeCd': '12',
        })
        self.assertEqual(captured['timeCd'], '12')


# ---------------------------------------------------------------------------
# execute_itd_contract テスト
# ---------------------------------------------------------------------------

class TestExecuteItdContract(unittest.IsolatedAsyncioTestCase):
    """execute_itd_contract のテスト"""

    async def test_uses_itd1004_and_includes_delivery_date(self):
        """ITD1004 として呼ばれ, deliveryDate が body に含まれること"""
        captured = {}

        async def mock_send(api_code, body):
            captured['api_code'] = api_code
            captured.update(body)
            return {'contractResults': []}

        with patch.object(JepxApiClient, 'send_request', side_effect=mock_send):
            with patch.object(JepxApiClient, '__init__', return_value=None):
                JepxApiClient.pool = MagicMock()
                JepxApiClient.member_id = '9999'
                JepxApiClient.max_retry = 3
                JepxApiClient.backoff_base = 0.01
                await services.execute_itd_contract({'deliveryDate': '2026-04-01'})

        self.assertEqual(captured['api_code'], 'ITD1004')
        self.assertEqual(captured['deliveryDate'], '2026-04-01')


# ---------------------------------------------------------------------------
# execute_itd_settlement テスト
# ---------------------------------------------------------------------------

class TestExecuteItdSettlement(unittest.IsolatedAsyncioTestCase):
    """execute_itd_settlement のテスト"""

    async def _call_settlement(self, data):
        captured = {}

        async def mock_send(api_code, body):
            captured['api_code'] = api_code
            captured.update(body)
            return {'settlements': []}

        with patch.object(JepxApiClient, 'send_request', side_effect=mock_send):
            with patch.object(JepxApiClient, '__init__', return_value=None):
                JepxApiClient.pool = MagicMock()
                JepxApiClient.member_id = '9999'
                JepxApiClient.max_retry = 3
                JepxApiClient.backoff_base = 0.01
                result = await services.execute_itd_settlement(data)
        return result, captured

    async def test_uses_itd9001_api_code(self):
        """ITD9001 として呼ばれること"""
        _, captured = await self._call_settlement({'fromDate': '2026-04-01'})
        self.assertEqual(captured['api_code'], 'ITD9001')

    async def test_from_date_in_body(self):
        """fromDate が body に含まれること"""
        _, captured = await self._call_settlement({'fromDate': '2026-04-01'})
        self.assertEqual(captured['fromDate'], '2026-04-01')

    async def test_to_date_in_body_when_provided(self):
        """toDate が提供された場合 body に含まれること"""
        _, captured = await self._call_settlement({
            'fromDate': '2026-04-01',
            'toDate': '2026-04-30',
        })
        self.assertEqual(captured['toDate'], '2026-04-30')

    async def test_to_date_excluded_when_not_provided(self):
        """toDate が提供されない場合, body に含まれないこと"""
        _, captured = await self._call_settlement({'fromDate': '2026-04-01'})
        self.assertNotIn('toDate', captured)


# ---------------------------------------------------------------------------
# check_duplicate_bid テスト
# ---------------------------------------------------------------------------

class TestCheckDuplicateBid(unittest.IsolatedAsyncioTestCase):
    """check_duplicate_bid のテスト"""

    async def _call_check(self, input_data, existing_bids):
        async def mock_send(api_code, body):
            return {'bids': existing_bids}

        with patch.object(JepxApiClient, 'send_request', side_effect=mock_send):
            with patch.object(JepxApiClient, '__init__', return_value=None):
                JepxApiClient.pool = MagicMock()
                JepxApiClient.member_id = '9999'
                JepxApiClient.max_retry = 3
                JepxApiClient.backoff_base = 0.01
                return await services.check_duplicate_bid(input_data)

    async def test_no_duplicate_returns_none(self):
        """重複なし → None を返すこと"""
        result = await self._call_check(
            {'deliveryDate': '2026-04-01', 'timeCd': '1', 'areaCd': '1', 'bidTypeCd': 'SELL-LIMIT'},
            [],
        )
        self.assertIsNone(result)

    async def test_exact_match_returns_bid(self):
        """完全一致する未キャンセル入札がある場合はその bid を返すこと"""
        dup_bid = {
            'bidNo': 'DUP-001',
            'timeCd': '1',
            'areaCd': '1',
            'bidTypeCd': 'SELL-LIMIT',
            'deleteCd': '0',  # 未キャンセル
        }
        result = await self._call_check(
            {'deliveryDate': '2026-04-01', 'timeCd': '1', 'areaCd': '1', 'bidTypeCd': 'SELL-LIMIT'},
            [dup_bid],
        )
        self.assertIsNotNone(result)
        self.assertEqual(result['bidNo'], 'DUP-001')

    async def test_cancelled_bid_not_duplicate(self):
        """deleteCd='1' (キャンセル済み) の入札は重複と見なさないこと"""
        cancelled_bid = {
            'bidNo': 'DEL-001',
            'timeCd': '1',
            'areaCd': '1',
            'bidTypeCd': 'SELL-LIMIT',
            'deleteCd': '1',  # キャンセル済み
        }
        result = await self._call_check(
            {'deliveryDate': '2026-04-01', 'timeCd': '1', 'areaCd': '1', 'bidTypeCd': 'SELL-LIMIT'},
            [cancelled_bid],
        )
        self.assertIsNone(result)

    async def test_different_area_not_duplicate(self):
        """areaCd が異なる場合は重複なし"""
        bid = {
            'bidNo': 'B001',
            'timeCd': '1',
            'areaCd': '2',  # 別エリア
            'bidTypeCd': 'SELL-LIMIT',
            'deleteCd': '0',
        }
        result = await self._call_check(
            {'deliveryDate': '2026-04-01', 'timeCd': '1', 'areaCd': '1', 'bidTypeCd': 'SELL-LIMIT'},
            [bid],
        )
        self.assertIsNone(result)

    async def test_different_bid_type_not_duplicate(self):
        """bidTypeCd が異なる場合は重複なし"""
        bid = {
            'bidNo': 'B001',
            'timeCd': '1',
            'areaCd': '1',
            'bidTypeCd': 'BUY-LIMIT',  # 別種別
            'deleteCd': '0',
        }
        result = await self._call_check(
            {'deliveryDate': '2026-04-01', 'timeCd': '1', 'areaCd': '1', 'bidTypeCd': 'SELL-LIMIT'},
            [bid],
        )
        self.assertIsNone(result)

    async def test_multiple_bids_returns_first_match(self):
        """複数入札のうち最初にマッチした入札を返すこと"""
        bids = [
            {'bidNo': 'NO-MATCH', 'timeCd': '2', 'areaCd': '1', 'bidTypeCd': 'SELL-LIMIT', 'deleteCd': '0'},
            {'bidNo': 'MATCH', 'timeCd': '1', 'areaCd': '1', 'bidTypeCd': 'SELL-LIMIT', 'deleteCd': '0'},
        ]
        result = await self._call_check(
            {'deliveryDate': '2026-04-01', 'timeCd': '1', 'areaCd': '1', 'bidTypeCd': 'SELL-LIMIT'},
            bids,
        )
        self.assertEqual(result['bidNo'], 'MATCH')


if __name__ == '__main__':
    unittest.main()
