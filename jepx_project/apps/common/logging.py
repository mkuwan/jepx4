"""監査ログ・マスキング (§8.3)

MaskingFilter: ログレコードから機密情報(memberId, password, client_secret)を
マスクして出力するフィルター。
"""
import re
import logging

# マスク対象パターン (JSONフィールド)
MASK_PATTERNS = {
    'memberId': r'("memberId"\s*:\s*")([^"]+)(")',
    'password': r'("password"\s*:\s*")([^"]+)(")',
    'client_secret': r'("client_secret"\s*:\s*")([^"]+)(")',
}


class MaskingFilter(logging.Filter):
    """ログレコードから機密情報をマスクするフィルター

    LOGGING設定の 'filters' で指定して使用する:
        'masking': {'()': 'apps.common.logging.MaskingFilter'}
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if hasattr(record, 'msg') and isinstance(record.msg, str):
            for field, pattern in MASK_PATTERNS.items():
                record.msg = re.sub(
                    pattern,
                    lambda m: m.group(1) + '********' + m.group(3),
                    record.msg,
                )
        return True
