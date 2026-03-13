"""§4 DAH業務サービス (apps/dah_batch/services.py) のユニットテスト

テスト観点:
- _build_bid_offers: 必須・オプション項目の展開
- generate_report: OK/MISMATCH 判定・BOM付きUTF-8出力
- execute_bid: 成功・スキップ(冪等)・バリデーションエラー
- execute_inquiry: 正常フロー・PDF保存
- check_input_file: 存在する/しない
"""
import csv
import io
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import os
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django
django.setup()

from apps.jepx_client.client import JepxApiClient
from apps.sharepoint.client import SharePointClient
import apps.dah_batch.services as svc


# ---------------------------------------------------------------------------
# _build_bid_offers テスト
# ---------------------------------------------------------------------------

class TestBuildBidOffers(unittest.TestCase):
    """_build_bid_offers のテスト"""

    def test_basic_fields(self):
        """必須フィールドすべてが展開されること"""
        rows = [{
            'areaCd': '1',
            'timeCd': '10',
            'bidTypeCd': 'SELL-LIMIT',
            'price': '100',
            'volume': '50',
        }]
        offers = svc._build_bid_offers(rows)
        self.assertEqual(len(offers), 1)
        o = offers[0]
        self.assertEqual(o['areaCd'], '1')
        self.assertEqual(o['timeCd'], '10')
        self.assertEqual(o['bidTypeCd'], 'SELL-LIMIT')
        self.assertEqual(o['price'], 100.0)
        self.assertEqual(o['volume'], 50.0)

    def test_optional_delivery_contract_included(self):
        """deliveryContractCd が提供されれば offer に含まれること"""
        rows = [{
            'areaCd': '1', 'timeCd': '1', 'bidTypeCd': 'SELL-LIMIT',
            'price': '100', 'volume': '50',
            'deliveryContractCd': 'BG001',
        }]
        offers = svc._build_bid_offers(rows)
        self.assertEqual(offers[0]['deliveryContractCd'], 'BG001')

    def test_optional_note_included(self):
        """note が提供されれば offer に含まれること (100文字切捨て込み)"""
        rows = [{
            'areaCd': '1', 'timeCd': '1', 'bidTypeCd': 'SELL-LIMIT',
            'price': '100', 'volume': '50',
            'note': 'テスト備考',
        }]
        offers = svc._build_bid_offers(rows)
        self.assertEqual(offers[0]['note'], 'テスト備考')

    def test_note_truncated_to_100(self):
        """note が100文字超の場合は切り捨てられること"""
        rows = [{
            'areaCd': '1', 'timeCd': '1', 'bidTypeCd': 'SELL-LIMIT',
            'price': '100', 'volume': '50',
            'note': 'X' * 150,
        }]
        offers = svc._build_bid_offers(rows)
        self.assertEqual(len(offers[0]['note']), 100)

    def test_no_delivery_contract_if_not_provided(self):
        """deliveryContractCd がない場合は offer に含まれないこと"""
        rows = [{'areaCd': '1', 'timeCd': '1', 'bidTypeCd': 'SELL-LIMIT', 'price': '100', 'volume': '50'}]
        offers = svc._build_bid_offers(rows)
        self.assertNotIn('deliveryContractCd', offers[0])

    def test_multiple_rows(self):
        """複数行が正しく展開されること"""
        rows = [
            {'areaCd': '1', 'timeCd': '1', 'bidTypeCd': 'SELL-LIMIT', 'price': '100', 'volume': '50'},
            {'areaCd': '2', 'timeCd': '2', 'bidTypeCd': 'BUY-LIMIT', 'price': '200', 'volume': '100'},
        ]
        offers = svc._build_bid_offers(rows)
        self.assertEqual(len(offers), 2)
        self.assertEqual(offers[1]['areaCd'], '2')

    def test_none_price_defaults_to_zero(self):
        """price が None / 空の場合は 0.0 になること"""
        rows = [{'areaCd': '1', 'timeCd': '1', 'bidTypeCd': 'SELL-MARKET', 'price': None, 'volume': '50'}]
        offers = svc._build_bid_offers(rows)
        self.assertEqual(offers[0]['price'], 0.0)


# ---------------------------------------------------------------------------
# generate_report テスト
# ---------------------------------------------------------------------------

class TestGenerateReport(unittest.IsolatedAsyncioTestCase):
    """generate_report のテスト"""

    def _make_sp_mock(self, plan_csv: str):
        sp = MagicMock(spec=SharePointClient)
        sp.download_file = AsyncMock(return_value=plan_csv.encode('utf-8'))
        sp.upload_file = AsyncMock()
        return sp

    async def test_ok_match(self):
        """計画量と約定量が一致する場合は 'OK' になること"""
        plan_csv = 'deliveryDate,timeCd,areaCd,price,volume\n2026-04-01,1,1,100,50\n'
        contract_data = [
            {'deliveryDate': '2026-04-01', 'timeCd': '1', 'areaCd': '1',
             'contractPrice': 100, 'contractVolume': 50.0}
        ]

        with patch('apps.dah_batch.services.SharePointClient', return_value=self._make_sp_mock(plan_csv)):
            result = await svc.generate_report('2026-04-01', contract_data)

        text = result.decode('utf-8-sig')  # BOM除去
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
        self.assertEqual(rows[0]['match'], 'OK')

    async def test_mismatch(self):
        """計画量と約定量が異なる場合は 'MISMATCH' になること"""
        plan_csv = 'deliveryDate,timeCd,areaCd,price,volume\n2026-04-01,1,1,100,100\n'
        contract_data = [
            {'deliveryDate': '2026-04-01', 'timeCd': '1', 'areaCd': '1',
             'contractPrice': 100, 'contractVolume': 50.0}  # 差分50
        ]

        with patch('apps.dah_batch.services.SharePointClient', return_value=self._make_sp_mock(plan_csv)):
            result = await svc.generate_report('2026-04-01', contract_data)

        text = result.decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
        self.assertEqual(rows[0]['match'], 'MISMATCH')

    async def test_no_contract_shows_mismatch(self):
        """入力には存在するが約定がない行は MISMATCH になること"""
        plan_csv = 'deliveryDate,timeCd,areaCd,price,volume\n2026-04-01,1,1,100,50\n'

        with patch('apps.dah_batch.services.SharePointClient', return_value=self._make_sp_mock(plan_csv)):
            result = await svc.generate_report('2026-04-01', [])

        text = result.decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
        self.assertEqual(rows[0]['match'], 'MISMATCH')

    async def test_bom_utf8_output(self):
        """出力がBOM付きUTF-8であること"""
        plan_csv = 'deliveryDate,timeCd,areaCd,price,volume\n2026-04-01,1,1,100,50\n'

        with patch('apps.dah_batch.services.SharePointClient', return_value=self._make_sp_mock(plan_csv)):
            result = await svc.generate_report('2026-04-01', [])

        # BOM (EF BB BF) で始まること
        self.assertTrue(result.startswith(b'\xef\xbb\xbf'))

    async def test_csv_headers_correct(self):
        """CSVヘッダが正しいこと"""
        plan_csv = 'deliveryDate,timeCd,areaCd,price,volume\n2026-04-01,1,1,100,50\n'

        with patch('apps.dah_batch.services.SharePointClient', return_value=self._make_sp_mock(plan_csv)):
            result = await svc.generate_report('2026-04-01', [])

        text = result.decode('utf-8-sig')
        first_line = text.split('\r\n')[0]
        expected_cols = ['deliveryDate', 'timeCd', 'areaCd', 'plan_price', 'plan_volume',
                         'contract_price', 'contract_volume', 'diff_volume', 'match']
        for col in expected_cols:
            self.assertIn(col, first_line)

    async def test_multiple_rows(self):
        """複数計画行が全て出力されること"""
        plan_csv = (
            'deliveryDate,timeCd,areaCd,price,volume\n'
            '2026-04-01,1,1,100,50\n'
            '2026-04-01,2,1,100,50\n'
        )

        with patch('apps.dah_batch.services.SharePointClient', return_value=self._make_sp_mock(plan_csv)):
            result = await svc.generate_report('2026-04-01', [])

        text = result.decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
        self.assertEqual(len(rows), 2)


# ---------------------------------------------------------------------------
# execute_bid テスト
# ---------------------------------------------------------------------------

class TestExecuteBid(unittest.IsolatedAsyncioTestCase):
    """execute_bid のテスト"""

    def _make_sp_mock(self, csv_content: str):
        sp = MagicMock(spec=SharePointClient)
        sp.download_file = AsyncMock(return_value=csv_content.encode('utf-8'))
        sp.upload_file = AsyncMock()
        sp.upload_error_report = AsyncMock()
        return sp

    def _make_client_mock(self, bids=None, bid_result=None):
        client = MagicMock(spec=JepxApiClient)
        client.send_request = AsyncMock(side_effect=[
            {'bids': bids if bids is not None else []},     # DAH1002 (冪等性チェック)
            bid_result or {'status': '200', 'statusInfo': '入札完了'},  # DAH1001 (入札)
        ])
        return client

    async def test_success_flow(self):
        """正常系: status='success' が返ること"""
        valid_csv = (
            'deliveryDate,areaCd,timeCd,bidTypeCd,price,volume,deliveryContractCd\n'
            '2026-04-01,1,1,SELL-LIMIT,100,50,BG001\n'
        )
        sp_mock = self._make_sp_mock(valid_csv)
        client_mock = self._make_client_mock()

        with patch('apps.dah_batch.services.SharePointClient', return_value=sp_mock):
            with patch('apps.dah_batch.services.JepxApiClient', return_value=client_mock):
                result = await svc.execute_bid('2026-04-01')

        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['count'], 1)

    async def test_idempotent_skip_when_bids_exist(self):
        """冪等性チェックで既に入札済みの場合は 'skipped' を返すこと"""
        valid_csv = (
            'deliveryDate,areaCd,timeCd,bidTypeCd,price,volume,deliveryContractCd\n'
            '2026-04-01,1,1,SELL-LIMIT,100,50,BG001\n'
        )
        sp_mock = self._make_sp_mock(valid_csv)
        client_mock = MagicMock(spec=JepxApiClient)
        # 冪等性チェックで既存入札2件を返す
        client_mock.send_request = AsyncMock(return_value={
            'bids': [{'bidNo': 'EXISTING-001'}, {'bidNo': 'EXISTING-002'}],
        })

        with patch('apps.dah_batch.services.SharePointClient', return_value=sp_mock):
            with patch('apps.dah_batch.services.JepxApiClient', return_value=client_mock):
                result = await svc.execute_bid('2026-04-01')

        self.assertEqual(result['status'], 'skipped')
        self.assertEqual(result['count'], 2)

    async def test_validation_error_returns_error_status(self):
        """バリデーションエラーがある場合は 'error' を返すこと"""
        invalid_csv = (
            'deliveryDate,areaCd,timeCd,bidTypeCd,price,volume,deliveryContractCd\n'
            # areaCd='99' は無効
            '2026-04-01,99,1,SELL-LIMIT,100,50,BG001\n'
        )
        sp_mock = self._make_sp_mock(invalid_csv)

        with patch('apps.dah_batch.services.SharePointClient', return_value=sp_mock):
            with patch('apps.dah_batch.services.JepxApiClient', return_value=MagicMock()):
                result = await svc.execute_bid('2026-04-01')

        self.assertEqual(result['status'], 'error')
        self.assertIn('バリデーション', result['message'])

    async def test_validation_error_does_not_call_jepx(self):
        """バリデーションエラー時はJEPX (DAH1001) を呼ばないこと"""
        invalid_csv = (
            'deliveryDate,areaCd,timeCd,bidTypeCd,price,volume,deliveryContractCd\n'
            '2026-04-01,99,1,SELL-LIMIT,100,50,BG001\n'
        )
        sp_mock = self._make_sp_mock(invalid_csv)
        client_mock = MagicMock(spec=JepxApiClient)
        client_mock.send_request = AsyncMock()

        with patch('apps.dah_batch.services.SharePointClient', return_value=sp_mock):
            with patch('apps.dah_batch.services.JepxApiClient', return_value=client_mock):
                await svc.execute_bid('2026-04-01')

        # バリデーションエラー時のDAH1002/DAH1001呼び出しはなし
        client_mock.send_request.assert_not_awaited()


# ---------------------------------------------------------------------------
# execute_inquiry テスト
# ---------------------------------------------------------------------------

class TestExecuteInquiry(unittest.IsolatedAsyncioTestCase):
    """execute_inquiry のテスト"""

    async def test_returns_contracts_and_market_results(self):
        """contracts と market_results が返ること"""
        client_mock = MagicMock(spec=JepxApiClient)
        client_mock.send_request = AsyncMock(side_effect=[
            {'bidResults': [{'bidNo': 'B1'}]},           # DAH1030
            {'marketResults': [{'systemPrice': 100}]},   # DAH1050
            {'settlements': []},                          # DAH9001
        ])
        sp_mock = MagicMock(spec=SharePointClient)
        sp_mock.upload_file = AsyncMock()

        with patch('apps.dah_batch.services.JepxApiClient', return_value=client_mock):
            with patch('apps.dah_batch.services.SharePointClient', return_value=sp_mock):
                result = await svc.execute_inquiry('2026-04-01')

        self.assertEqual(len(result['contracts']), 1)
        self.assertEqual(len(result['market_results']), 1)

    async def test_pdf_saved_for_settlements(self):
        """清算データの PDF が SharePoint に保存されること"""
        import base64
        pdf_b64 = base64.b64encode(b'%PDF-1.4 fake').decode('ascii')

        client_mock = MagicMock(spec=JepxApiClient)
        client_mock.send_request = AsyncMock(side_effect=[
            {'bidResults': []},           # DAH1030
            {'marketResults': []},        # DAH1050
            {'settlements': [{'settlementDate': '2026-04-01', 'settlementNo': '001', 'pdf': pdf_b64}]},  # DAH9001
        ])
        sp_mock = MagicMock(spec=SharePointClient)
        sp_mock.upload_file = AsyncMock()

        with patch('apps.dah_batch.services.JepxApiClient', return_value=client_mock):
            with patch('apps.dah_batch.services.SharePointClient', return_value=sp_mock):
                await svc.execute_inquiry('2026-04-01')

        sp_mock.upload_file.assert_awaited_once()
        call_args = sp_mock.upload_file.call_args
        # ファイル名に日付と清算番号が含まれること
        self.assertIn('2026-04-01', call_args[0][0])
        self.assertIn('001', call_args[0][0])

    async def test_no_pdf_if_no_settlements(self):
        """清算データがない場合は upload_file が呼ばれないこと"""
        client_mock = MagicMock(spec=JepxApiClient)
        client_mock.send_request = AsyncMock(side_effect=[
            {'bidResults': []},
            {'marketResults': []},
            {'settlements': []},
        ])
        sp_mock = MagicMock(spec=SharePointClient)
        sp_mock.upload_file = AsyncMock()

        with patch('apps.dah_batch.services.JepxApiClient', return_value=client_mock):
            with patch('apps.dah_batch.services.SharePointClient', return_value=sp_mock):
                await svc.execute_inquiry('2026-04-01')

        sp_mock.upload_file.assert_not_awaited()


# ---------------------------------------------------------------------------
# check_input_file テスト
# ---------------------------------------------------------------------------

class TestCheckInputFile(unittest.IsolatedAsyncioTestCase):
    """check_input_file のテスト"""

    async def test_file_exists(self):
        """SharePoint にファイルがある場合は True を返すこと"""
        sp_mock = MagicMock(spec=SharePointClient)
        sp_mock.file_exists = AsyncMock(return_value=True)

        with patch('apps.dah_batch.services.SharePointClient', return_value=sp_mock):
            result = await svc.check_input_file('2026-04-01')

        self.assertTrue(result)
        sp_mock.file_exists.assert_awaited_once_with('input/2026-04-01.csv')

    async def test_file_not_exists(self):
        """SharePoint にファイルがない場合は False を返すこと"""
        sp_mock = MagicMock(spec=SharePointClient)
        sp_mock.file_exists = AsyncMock(return_value=False)

        with patch('apps.dah_batch.services.SharePointClient', return_value=sp_mock):
            result = await svc.check_input_file('2026-04-01')

        self.assertFalse(result)

    async def test_file_path_format(self):
        """ファイルパスが 'input/YYYY-MM-DD.csv' 形式であること"""
        sp_mock = MagicMock(spec=SharePointClient)
        sp_mock.file_exists = AsyncMock(return_value=True)

        with patch('apps.dah_batch.services.SharePointClient', return_value=sp_mock):
            await svc.check_input_file('2026-05-15')

        call_args = sp_mock.file_exists.call_args[0][0]
        self.assertEqual(call_args, 'input/2026-05-15.csv')


if __name__ == '__main__':
    unittest.main()
