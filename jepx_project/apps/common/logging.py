"""監査ログ・マスキング (§8.3)

システム全体の監査ログおよびシステムエラーログを出力する際に、
JEPXから指定された認証情報(memberId, password)やGraph APIのclient_secretなど、
ログに残すべきではない機密情報を自動的にマスク(隠蔽)するための共通フィルター設定。
"""
import re
import logging

# ログメッセージ内に含まれる特定フィールドのJSONフォーマットを検知するための正規表現パターン。
# 例: {"memberId": "1234"} のような文字列を "memberId" と "1234" に分離・捕捉する仕組みです。
MASK_PATTERNS = {
    'memberId': r'("memberId"\s*:\s*")([^"]+)(")',
    'password': r'("password"\s*:\s*")([^"]+)(")',
    'client_secret': r'("client_secret"\s*:\s*")([^"]+)(")',
}


class MaskingFilter(logging.Filter):
    """ログレコードから機密情報をマスクするフィルター

    Djangoの LOGGING 設定ディクショナリの 'filters' セクションで指定して使用します。
    すべてのロガー（JEPX API通信ログ、エラーログなど）にこのフィルターを通すことで、
    誤って機密データを平文で保存してしまう事故を防ぎます。
    用法:
        'masking': {'()': 'apps.common.logging.MaskingFilter'}
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """ログ書き込みの直前に呼び出され、内容を検査・加工するメソッド。

        Args:
            record: メッセージ文字列やログレベルなどの情報を持つロギングレコード。
        Returns:
            True (ログ出力を許可する。内容のみ書き換える。)
        """
        # メッセージが文字列として存在しているか確認
        if hasattr(record, 'msg') and isinstance(record.msg, str):
            # MASK_PATTERNSに定義された全パターンを巡回
            for field, pattern in MASK_PATTERNS.items():
                # 正規表現にマッチした部分(パスワード本体など)を '********' のリテラルに置換する。
                # m.group(1) は前方のキー名部分、m.group(3)は後方のダブルクォーテーション。
                record.msg = re.sub(
                    pattern,
                    lambda m: m.group(1) + '********' + m.group(3),
                    record.msg,
                )
        return True
