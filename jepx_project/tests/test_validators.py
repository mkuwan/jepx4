"""§7 バリデーションエンジンのユニットテスト

テスト観点:
- V-001〜V-016 共通ルール
- V-D01〜V-D02 DAH固有ルール
- V-013 小数切捨て自動補正
- FAIL_FAST モード
"""
import unittest
import os, sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django
django.setup()

from apps.common.validators import BidValidator, ValidationError


def _valid_row(**overrides):
    """テスト用の正常な入力行を構築する"""
    base = {
        'deliveryDate': '2026-04-01',
        'areaCd': '1',
        'timeCd': '1',
        'bidTypeCd': 'SELL-LIMIT',
        'price': 100.0,
        'volume': 50.0,
        'deliveryContractCd': 'BG001',
        'note': '',
    }
    base.update(overrides)
    return base


class TestRequiredFields(unittest.TestCase):
    """V-001, V-003, V-005, V-007, V-009, V-012, V-015: 必須チェック"""

    def setUp(self):
        self.validator = BidValidator()

    def test_all_valid(self):
        """全項目が正常なら0件エラー"""
        errors = self.validator.validate([_valid_row()])
        self.assertEqual(len(errors), 0)

    def test_missing_delivery_date(self):
        """V-001: deliveryDate 未入力"""
        errors = self.validator.validate([_valid_row(deliveryDate='')])
        self.assertTrue(any(e.rule_id == 'V-001' for e in errors))

    def test_missing_area_cd(self):
        """V-003: areaCd 未入力"""
        errors = self.validator.validate([_valid_row(areaCd='')])
        self.assertTrue(any(e.rule_id == 'V-003' for e in errors))

    def test_missing_time_cd(self):
        """V-005: timeCd 未入力"""
        errors = self.validator.validate([_valid_row(timeCd='')])
        self.assertTrue(any(e.rule_id == 'V-005' for e in errors))

    def test_missing_bid_type(self):
        """V-007: bidTypeCd 未入力"""
        errors = self.validator.validate([_valid_row(bidTypeCd='')])
        self.assertTrue(any(e.rule_id == 'V-007' for e in errors))

    def test_missing_volume(self):
        """V-012: volume 未入力"""
        errors = self.validator.validate([_valid_row(volume=None)])
        self.assertTrue(any(e.rule_id == 'V-012' for e in errors))

    def test_missing_delivery_contract_cd(self):
        """V-015: deliveryContractCd 未入力"""
        errors = self.validator.validate([_valid_row(deliveryContractCd='')])
        self.assertTrue(any(e.rule_id == 'V-015' for e in errors))

    def test_price_not_required_for_market(self):
        """V-009: 成行注文ではprice不要"""
        row = _valid_row(bidTypeCd='SELL-MARKET', price=None)
        errors = self.validator.validate([row])
        self.assertFalse(any(e.rule_id == 'V-009' for e in errors))


class TestFormatChecks(unittest.TestCase):
    """V-002, V-016: 形式チェック"""

    def setUp(self):
        self.validator = BidValidator()

    def test_invalid_date_format(self):
        """V-002: deliveryDate が YYYY-MM-DD でない"""
        errors = self.validator.validate([_valid_row(deliveryDate='20260401')])
        self.assertTrue(any(e.rule_id == 'V-002' for e in errors))

    def test_valid_date_format(self):
        """V-002: 正しい日付形式"""
        errors = self.validator.validate([_valid_row(deliveryDate='2026-04-01')])
        self.assertFalse(any(e.rule_id == 'V-002' for e in errors))

    def test_note_too_long(self):
        """V-016: note が100文字超"""
        errors = self.validator.validate([_valid_row(note='A' * 101)])
        self.assertTrue(any(e.rule_id == 'V-016' for e in errors))

    def test_note_within_limit(self):
        """V-016: note が100文字以内"""
        errors = self.validator.validate([_valid_row(note='A' * 100)])
        self.assertFalse(any(e.rule_id == 'V-016' for e in errors))


class TestCodeChecks(unittest.TestCase):
    """V-004, V-006, V-008: コードチェック"""

    def setUp(self):
        self.validator = BidValidator()

    def test_invalid_area_code(self):
        """V-004: 無効なエリアコード"""
        errors = self.validator.validate([_valid_row(areaCd='99')])
        self.assertTrue(any(e.rule_id == 'V-004' for e in errors))

    def test_valid_area_code(self):
        """V-004: 有効なエリアコード (1〜9)"""
        for code in ['1', '2', '3', '4', '5', '6', '7', '8', '9']:
            errors = self.validator.validate([_valid_row(areaCd=code)])
            self.assertFalse(
                any(e.rule_id == 'V-004' for e in errors),
                f"areaCd={code} should be valid",
            )

    def test_invalid_time_code(self):
        """V-006: 時間帯コードが範囲外"""
        errors = self.validator.validate([_valid_row(timeCd='49')])
        self.assertTrue(any(e.rule_id == 'V-006' for e in errors))

    def test_valid_time_code_range(self):
        """V-006: 時間帯コード 1〜48 は有効"""
        for tc in ['1', '24', '48']:
            errors = self.validator.validate([_valid_row(timeCd=tc)])
            self.assertFalse(
                any(e.rule_id == 'V-006' for e in errors),
                f"timeCd={tc} should be valid",
            )

    def test_invalid_bid_type(self):
        """V-008: 無効な入札種別コード"""
        errors = self.validator.validate([_valid_row(bidTypeCd='INVALID')])
        self.assertTrue(any(e.rule_id == 'V-008' for e in errors))

    def test_valid_bid_types(self):
        """V-008: 有効な入札種別"""
        for bt in ['SELL-LIMIT', 'BUY-LIMIT', 'SELL-MARKET', 'BUY-MARKET', 'FIT', 'DEL']:
            errors = self.validator.validate([_valid_row(bidTypeCd=bt)])
            self.assertFalse(
                any(e.rule_id == 'V-008' for e in errors),
                f"bidTypeCd={bt} should be valid",
            )


class TestUnitAndRangeChecks(unittest.TestCase):
    """V-010, V-011, V-014: 単位・範囲チェック"""

    def setUp(self):
        self.validator = BidValidator()

    def test_price_not_multiple_of_10(self):
        """V-010: 入札価格が10の倍数でない"""
        errors = self.validator.validate([_valid_row(price=55.0)])
        self.assertTrue(any(e.rule_id == 'V-010' for e in errors))

    def test_price_multiple_of_10(self):
        """V-010: 入札価格が10の倍数"""
        errors = self.validator.validate([_valid_row(price=100.0)])
        self.assertFalse(any(e.rule_id == 'V-010' for e in errors))

    def test_price_out_of_range(self):
        """V-011: 入札価格が上限超過"""
        errors = self.validator.validate([_valid_row(price=1000.0)])
        self.assertTrue(any(e.rule_id == 'V-011' for e in errors))

    def test_volume_out_of_range(self):
        """V-014: 入札量が上限超過"""
        errors = self.validator.validate([_valid_row(volume=5001.0)])
        self.assertTrue(any(e.rule_id == 'V-014' for e in errors))


class TestVolumeAutoCorrection(unittest.TestCase):
    """§7.3 V-013: 小数切捨て自動補正"""

    def setUp(self):
        self.validator = BidValidator()

    def test_truncate_to_first_decimal(self):
        """V-013: 100.56 → 100.5 に自動補正"""
        row = _valid_row(volume=100.56)
        self.validator.validate([row])
        self.assertEqual(row['volume'], 100.5)

    def test_no_truncation_needed(self):
        """V-013: 100.5 はそのまま"""
        row = _valid_row(volume=100.5)
        self.validator.validate([row])
        self.assertEqual(row['volume'], 100.5)

    def test_integer_volume(self):
        """V-013: 整数値はそのまま"""
        row = _valid_row(volume=100.0)
        self.validator.validate([row])
        self.assertEqual(row['volume'], 100.0)


class TestDahSpecificRules(unittest.TestCase):
    """V-D02: DAH固有の重複チェック"""

    def setUp(self):
        self.validator = BidValidator()

    def test_duplicate_entries(self):
        """V-D02: 同一(deliveryDate, areaCd, timeCd)の重複"""
        row1 = _valid_row()
        row2 = _valid_row()  # 同一キー
        errors = self.validator.validate([row1, row2], market='DAH')
        self.assertTrue(any(e.rule_id == 'V-D02' for e in errors))

    def test_no_duplicate(self):
        """V-D02: 異なるキーなら重複なし"""
        row1 = _valid_row(timeCd='1')
        row2 = _valid_row(timeCd='2')
        errors = self.validator.validate([row1, row2], market='DAH')
        self.assertFalse(any(e.rule_id == 'V-D02' for e in errors))


if __name__ == '__main__':
    unittest.main()
