"""JEPX通信例外クラス体系 (§3.3)

JEPXとの通信で発生するあらゆるエラーをDjangoレイヤーで一元的に捕捉し、
「リトライすべきか」「即座に処理を中断すべきか」を判断できるよう専用の例外クラスを定義しています。
各ビジネスロジックは標準例外ではなくこの例外クラス群を捕捉して運用対処を行います。
"""

class JepxError(Exception):
    """JEPX通信関連エラーのすべての基底（親）クラス。
    
    属性:
        retryable (bool): このエラー発生時に自動リッチライ（再送）を試行してよいかどうか。
    """
    retryable = False

class JepxProtocolError(JepxError):
    """電文の解析不能・破損エラー。
    SOH/ETXの欠損やGZIPの破損など、プロトコルフォーマット違反により復号できなかった場合。
    """
    retryable = False

class JepxFormatError(JepxError):
    """STATUS=10: 電文フォーマット異常。
    送信したJSON項目が不足・型違いなど、要求の形式自体が間違っている場合。リトライしても直らない。
    """
    retryable = False

class JepxAuthError(JepxError):
    """STATUS=11: 会員ID権限なし。
    設定されたMEMBER IDで指定のAPIを操作する権限がない、あるいはパスワードエラー。
    """
    retryable = False

class JepxSystemError(JepxError):
    """STATUS=19: JEPXシステム異常。
    JEPX側のサーバーで一時的な障害が発生している状態。時間をおいてのリトライが推奨される。
    """
    retryable = True

class JepxConnectionError(JepxError):
    """TLS/Socket接続エラー。
    ネットワーク断絶や証明書エラー、JEPX側のポートダウンなどで物理的・暗号的接続が確立できない状態。
    """
    retryable = True

class JepxTimeoutError(JepxError):
    """送受信タイムアウト。
    通信は確立したが指定秒数(デフォルト5〜10秒)応答がない状態。経路遅延など。
    """
    retryable = True

class JepxBusinessError(JepxError):
    """body.status != "200": JEPX業務エラー
    JEPXのAPIから正常に応答(STATUS=00)は返ってきたが、中身であるビジネスステータスが
    エラー(例: 入札無効、存在しない入札No等)を示している状態。
    """
    retryable = False

    def __init__(self, status: str, status_info: str):
        """
        Args:
            status: 例 'E1000' などの業務エラーコード
            status_info: エラーの具体的な理由を示すテキスト
        """
        self.status = status
        self.status_info = status_info
        super().__init__(f"JEPX業務エラー: status={status}, info={status_info}")
