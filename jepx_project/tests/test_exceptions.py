"""§3.3 例外クラス体系のユニットテスト

テスト観点:
- 例外階層 (JepxError基底)
- retryable フラグ
- JepxBusinessError の status/status_info 保持
"""
import unittest
import os, sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django
django.setup()

from apps.jepx_client.exceptions import (
    JepxError,
    JepxProtocolError,
    JepxFormatError,
    JepxAuthError,
    JepxSystemError,
    JepxConnectionError,
    JepxTimeoutError,
    JepxBusinessError,
)


class TestExceptionHierarchy(unittest.TestCase):
    """例外がすべて JepxError を継承していること
    
    アプリ層でのエラーハンドリングを一元化するため、細分化された通信・業務エラーが
    すべて単一の共通親クラスを正しく継承しているかを検証します。
    """

    def test_all_inherit_from_jepx_error(self):
        for cls in [
            JepxProtocolError, JepxFormatError, JepxAuthError,
            JepxSystemError, JepxConnectionError, JepxTimeoutError,
            JepxBusinessError,
        ]:
            self.assertTrue(issubclass(cls, JepxError), f"{cls} must inherit JepxError")


class TestRetryableFlags(unittest.TestCase):
    """§3.5 リトライポリシー判定表の retryable フラグ"""

    def test_retryable_true(self):
        """リトライ対象: SystemError, ConnectionError, TimeoutError"""
        self.assertTrue(JepxSystemError.retryable)
        self.assertTrue(JepxConnectionError.retryable)
        self.assertTrue(JepxTimeoutError.retryable)

    def test_retryable_false(self):
        """リトライ不可: FormatError, AuthError, BusinessError"""
        self.assertFalse(JepxFormatError.retryable)
        self.assertFalse(JepxAuthError.retryable)
        self.assertFalse(JepxBusinessError.retryable)

    def test_protocol_error_not_retryable(self):
        """プロトコルエラーもリトライ不可"""
        self.assertFalse(JepxProtocolError.retryable)


class TestBusinessError(unittest.TestCase):
    """JepxBusinessError の属性保持"""

    def test_stores_status_and_info(self):
        err = JepxBusinessError('400', '入札期間外です')
        self.assertEqual(err.status, '400')
        self.assertEqual(err.status_info, '入札期間外です')
        self.assertIn('400', str(err))
        self.assertIn('入札期間外', str(err))


if __name__ == '__main__':
    unittest.main()
