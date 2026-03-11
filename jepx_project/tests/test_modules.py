"""§9 コード定義ローダー / §8.3 マスキング / §5.4 InMemoryStore /
§5.2 シリアライザ / §6.3 ファイルパーサー / §4.2 排他制御 のテスト

複数の小モジュールをまとめてテスト。
"""
import unittest
import logging
import json
import os, sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django
django.setup()


# ============================================================
# §9 コード定義ローダー
# ============================================================

from apps.common.codes import (
    load_master_codes,
    get_area_name,
    is_valid_bid_type,
    is_valid_area_code,
    is_valid_area_group_code,
    get_time_code_range,
    get_limits,
)


class TestMasterCodes(unittest.TestCase):
    """§9 jepx_master.yaml の読み込みとマスターデータ解決ロジック(メモリ展開)の検証"""

    def test_load_master_codes(self):
        """YAML読み込みが成功すること"""
        codes = load_master_codes()
        self.assertIn('areas', codes)
        self.assertIn('bid_types', codes)
        self.assertIn('time_codes', codes)
        self.assertIn('limits', codes)

    def test_area_codes_count(self):
        """エリアコード: 1〜9 の9エリア"""
        codes = load_master_codes()
        self.assertEqual(len(codes['areas']), 9)

    def test_get_area_name(self):
        self.assertEqual(get_area_name('1'), '北海道')
        self.assertEqual(get_area_name('3'), '東京')
        self.assertIn('不明', get_area_name('99'))

    def test_bid_types(self):
        """入札種別が6種類登録されていること"""
        codes = load_master_codes()
        self.assertEqual(len(codes['bid_types']), 6)
        self.assertTrue(is_valid_bid_type('SELL-LIMIT'))
        self.assertTrue(is_valid_bid_type('BUY-MARKET'))
        self.assertFalse(is_valid_bid_type('UNKNOWN'))

    def test_area_group_codes(self):
        """エリアグループコード (A1,A2等) が存在すること"""
        self.assertTrue(is_valid_area_group_code('A1'))
        self.assertTrue(is_valid_area_group_code('A9'))
        self.assertFalse(is_valid_area_group_code('A3'))

    def test_time_code_range(self):
        """時間帯コード: 1〜48"""
        min_tc, max_tc = get_time_code_range()
        self.assertEqual(min_tc, 1)
        self.assertEqual(max_tc, 48)

    def test_limits(self):
        """制限値が定義されていること"""
        limits = get_limits()
        self.assertIn('max_bid_price', limits)
        self.assertIn('max_bid_volume', limits)
        self.assertEqual(limits['max_bid_price'], 999.0)
        self.assertEqual(limits['max_bid_volume'], 5000.0)


# ============================================================
# §8.3 MaskingFilter
# ============================================================

from apps.common.logging import MaskingFilter


class TestMaskingFilter(unittest.TestCase):
    """§8.3 マスキングフィルターのテスト"""

    def setUp(self):
        self.filter = MaskingFilter()

    def test_mask_member_id(self):
        """memberId がマスクされること"""
        record = logging.LogRecord(
            'test', logging.INFO, '', 0,
            '{"memberId": "0841"}', (), None,
        )
        self.filter.filter(record)
        self.assertNotIn('0841', record.msg)
        self.assertIn('********', record.msg)

    def test_mask_password(self):
        """password がマスクされること"""
        record = logging.LogRecord(
            'test', logging.INFO, '', 0,
            '{"password": "secret123"}', (), None,
        )
        self.filter.filter(record)
        self.assertNotIn('secret123', record.msg)

    def test_mask_client_secret(self):
        """client_secret がマスクされること"""
        record = logging.LogRecord(
            'test', logging.INFO, '', 0,
            '{"client_secret": "my-secret-value"}', (), None,
        )
        self.filter.filter(record)
        self.assertNotIn('my-secret-value', record.msg)

    def test_no_mask_normal_message(self):
        """機密情報を含まないメッセージはそのまま"""
        msg = '[API_COMM] api=DAH1001, elapsed=0.5s'
        record = logging.LogRecord(
            'test', logging.INFO, '', 0, msg, (), None,
        )
        self.filter.filter(record)
        self.assertEqual(record.msg, msg)


# ============================================================
# §5.4 ITN InMemoryStore
# ============================================================

from apps.itn_stream.store import ItnMemoryStore


class TestItnMemoryStore(unittest.TestCase):
    """§5.4 InMemoryStore 3層構造のテスト"""

    def setUp(self):
        self.store = ItnMemoryStore()

    def test_initial_empty(self):
        """初期状態は空"""
        snap = self.store.get_snapshot()
        self.assertEqual(snap['version'], 0)
        self.assertEqual(len(snap['contracts']), 0)
        self.assertEqual(len(snap['boards']), 0)
        self.assertFalse(snap['connection']['connected'])

    def test_update_contracts(self):
        """CONTRACT通知がbidNoでマージされること"""
        self.store.update_notices([
            {'noticeType': 'CONTRACT', 'bidNo': '001', 'price': 100},
            {'noticeType': 'CONTRACT', 'bidNo': '002', 'price': 200},
        ])
        snap = self.store.get_snapshot()
        self.assertEqual(len(snap['contracts']), 2)
        self.assertEqual(snap['version'], 1)

    def test_update_boards(self):
        """BID-BOARD通知が(areaCd,timeCd)でマージされること"""
        self.store.update_notices([
            {'noticeType': 'BID-BOARD', 'areaCd': '1', 'timeCd': '1', 'volume': 100},
            {'noticeType': 'BID-BOARD', 'areaCd': '1', 'timeCd': '2', 'volume': 200},
        ])
        snap = self.store.get_snapshot()
        self.assertEqual(len(snap['boards']), 2)

    def test_board_merge_overwrites(self):
        """同一キーの板情報は上書きマージされること"""
        self.store.update_notices([
            {'noticeType': 'BID-BOARD', 'areaCd': '1', 'timeCd': '1', 'volume': 100},
        ])
        self.store.update_notices([
            {'noticeType': 'BID-BOARD', 'areaCd': '1', 'timeCd': '1', 'volume': 999},
        ])
        snap = self.store.get_snapshot()
        self.assertEqual(len(snap['boards']), 1)
        self.assertEqual(snap['boards'][0]['volume'], 999)

    def test_set_full_state_clears(self):
        """全量配信で既存データがリセットされること"""
        self.store.update_notices([
            {'noticeType': 'CONTRACT', 'bidNo': '001', 'price': 100},
        ])
        self.store.set_full_state([
            {'noticeType': 'CONTRACT', 'bidNo': '999', 'price': 500},
        ])
        snap = self.store.get_snapshot()
        self.assertEqual(len(snap['contracts']), 1)
        self.assertEqual(snap['contracts'][0]['bidNo'], '999')

    def test_connection_status(self):
        """接続状態の更新が反映されること"""
        self.store.set_connection_status(True)
        snap = self.store.get_snapshot()
        self.assertTrue(snap['connection']['connected'])

        self.store.set_connection_status(False, error='切断')
        snap = self.store.get_snapshot()
        self.assertFalse(snap['connection']['connected'])
        self.assertEqual(snap['connection']['error'], '切断')

    def test_version_increments(self):
        """更新のたびにバージョンが上がること"""
        v0 = self.store.get_version()
        self.store.update_notices([
            {'noticeType': 'CONTRACT', 'bidNo': '001'},
        ])
        v1 = self.store.get_version()
        self.assertGreater(v1, v0)


# ============================================================
# §5.2 ITD シリアライザ
# ============================================================

from apps.itd_api.serializers import (
    serialize_bid_response,
    serialize_delete_response,
    serialize_inquiry_response,
    serialize_contract_response,
    serialize_error,
)


class TestItdSerializers(unittest.TestCase):
    """§5.2 シリアライザのテスト"""

    def test_bid_response_success(self):
        resp = serialize_bid_response({
            'status': '200', 'bidNo': '1234567890', 'statusInfo': '登録完了',
        })
        self.assertTrue(resp['success'])
        self.assertEqual(resp['bid_no'], '1234567890')

    def test_bid_response_failure(self):
        resp = serialize_bid_response({'status': '400', 'statusInfo': 'エラー'})
        self.assertFalse(resp['success'])

    def test_delete_response(self):
        resp = serialize_delete_response({'status': '200', 'statusInfo': '削除完了'})
        self.assertTrue(resp['success'])

    def test_inquiry_response(self):
        resp = serialize_inquiry_response({'bids': [{'bidNo': '1'}, {'bidNo': '2'}]})
        self.assertTrue(resp['success'])
        self.assertEqual(resp['count'], 2)

    def test_contract_response(self):
        resp = serialize_contract_response({
            'contractResults': [{'bidNo': '1', 'contractPrice': 100}],
        })
        self.assertEqual(resp['count'], 1)

    def test_error_response(self):
        resp = serialize_error('VALIDATION_ERROR', 'invalid field')
        self.assertFalse(resp['success'])
        self.assertEqual(resp['error_code'], 'VALIDATION_ERROR')


# ============================================================
# §6.3 ファイルパーサー
# ============================================================

from apps.sharepoint.file_parser import parse_csv


class TestFileParser(unittest.TestCase):
    """§6.3 CSV パーサーのテスト"""

    def test_parse_csv(self):
        """BOM付きUTF-8 CSVのパース"""
        csv_content = '\ufeffdeliveryDate,areaCd,price\n2026-04-01,1,100\n2026-04-01,2,200\n'
        rows = parse_csv(csv_content.encode('utf-8'))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['deliveryDate'], '2026-04-01')
        self.assertEqual(rows[0]['areaCd'], '1')

    def test_parse_csv_no_bom(self):
        """BOMなしUTF-8 CSVのパース"""
        csv_content = 'deliveryDate,areaCd\n2026-04-01,3\n'
        rows = parse_csv(csv_content.encode('utf-8'))
        self.assertEqual(len(rows), 1)

    def test_parse_empty_csv(self):
        """空CSVのパース"""
        rows = parse_csv(b'deliveryDate,areaCd\n')
        self.assertEqual(len(rows), 0)


# ============================================================
# §4.2 排他制御
# ============================================================

from apps.dah_batch.lock import BatchLock


class TestBatchLock(unittest.TestCase):
    """§4.2 排他制御 (ファイルロック) のテスト"""

    def test_lock_acquire_release(self):
        """ロック取得・解放が正常に動作すること"""
        with BatchLock('test_cmd', '2026-04-01'):
            pass  # ロック取得→解放

    def test_double_lock_raises(self):
        """同一ロックの二重取得で RuntimeError が発生すること"""
        with BatchLock('test_dup', '2026-04-01'):
            with self.assertRaises(RuntimeError):
                with BatchLock('test_dup', '2026-04-01'):
                    pass

    def test_different_dates_no_conflict(self):
        """異なる受渡日のロックは競合しないこと"""
        with BatchLock('test_dates', '2026-04-01'):
            with BatchLock('test_dates', '2026-04-02'):
                pass  # 異なるキーなので競合しない


if __name__ == '__main__':
    unittest.main()
