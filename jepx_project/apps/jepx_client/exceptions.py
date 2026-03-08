"""JEPX通信例外クラス体系 (§3.3)"""


class JepxError(Exception):
    """JEPX通信関連エラーの基底クラス"""
    retryable = False


class JepxProtocolError(JepxError):
    """電文プロトコルの異常 (パース不能等)"""
    retryable = False


class JepxFormatError(JepxError):
    """STATUS=10: 電文フォーマット異常 (リトライ不可)"""
    retryable = False


class JepxAuthError(JepxError):
    """STATUS=11: 会員ID権限なし (リトライ不可)"""
    retryable = False


class JepxSystemError(JepxError):
    """STATUS=19: JEPXシステム異常 (リトライ対象)"""
    retryable = True


class JepxConnectionError(JepxError):
    """TLS/Socket接続エラー (リトライ対象)"""
    retryable = True


class JepxTimeoutError(JepxError):
    """読み取り/書き込みタイムアウト (リトライ対象)"""
    retryable = True


class JepxBusinessError(JepxError):
    """body.status != "200": JEPX業務エラー (リトライ不可)"""
    retryable = False

    def __init__(self, status: str, status_info: str):
        self.status = status
        self.status_info = status_info
        super().__init__(f"JEPX業務エラー: status={status}, info={status_info}")
