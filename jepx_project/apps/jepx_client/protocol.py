"""JEPX電文プロトコル — 電文組立・解析 (§3.2)

901.接続技術書 §3 準拠:
- 通信フォーマット: SOH + ヘッダ部 + STX + ボディ部(gzip) + ETX
- ヘッダ部: ASCII, MEMBER=xxxx,API=xxxxxxx,SIZE=nnn
- ボディ部: gzip圧縮されたJSON
"""
import json
import zlib

from .exceptions import (
    JepxProtocolError,
    JepxFormatError,
    JepxAuthError,
    JepxSystemError,
)

SOH = b'\x01'
STX = b'\x02'
ETX = b'\x03'


class JepxProtocol:
    """JEPX電文の組立・解析ユーティリティ (staticメソッド群)"""

    @staticmethod
    def build_packet(member: str, api_code: str, body: dict) -> bytes:
        """送信用のリクエスト電文（パケット）を要求仕様に従い組み立てる。

        1. 業務用のJSONディクショナリを文字列化してUTF-8バイトに変換。
        2. ZLIBを用いてGZIP圧縮（JEPX仕様による通信量削減）。
        3. MEMBER, APIコード, 圧縮データの長さを記載したASCIIヘッダーを作成。
        4. SOH(0x01) + Header + STX(0x02) + 圧縮実体 + ETX(0x03) で連結。

        Args:
            member: 会員ID (4桁英数字)
            api_code: API機能番号 (例: "DAH1001")
            body: リクエストボディ (dict)

        Returns:
            SOH + Header + STX + gzip(JSON) + ETX のbytes
        """
        json_bytes = json.dumps(body, ensure_ascii=False).encode('utf-8')
        compressed = zlib.compress(json_bytes)
        size = len(compressed)
        header = f"MEMBER={member},API={api_code},SIZE={size}".encode('ascii')
        return SOH + header + STX + compressed + ETX

    @staticmethod
    def parse_response(data: bytes) -> tuple[dict, dict]:
        """JEPXから受信したバイナリ電文を解体し、ヘッダ情報と業務JSONに変換する。

        1. SOH, STX, ETX の制御文字を検索し、パケット境界を特定。
        2. STXとETXで挟まれたgzip部分を zlib.decompress で解凍。
        3. ヘッダ部のSIZE宣言と実際のバイト数が一致しているかを検証。
        4. パース結果を dict として返却。

        Returns:
            (header_dict, body_dict)
            header_dict: {"STATUS": "00", "SIZE": "254"}
            body_dict: JSONパース済みのdict

        Raises:
            JepxProtocolError: SOH/STX/ETX不正、SIZE不一致、gzip破損
        """
        soh_idx = data.find(SOH)
        stx_idx = data.find(STX)
        etx_idx = data.rfind(ETX)

        if soh_idx < 0 or stx_idx < 0 or etx_idx < 0:
            raise JepxProtocolError("電文フレーム異常: SOH/STX/ETX不正")

        header_str = data[soh_idx + 1:stx_idx].decode('ascii')
        header = dict(p.split('=') for p in header_str.split(','))

        body_bytes = data[stx_idx + 1:etx_idx]
        declared_size = int(header.get('SIZE', 0))
        if len(body_bytes) != declared_size:
            raise JepxProtocolError(
                f"SIZE不一致: 宣言={declared_size}, 実体={len(body_bytes)}"
            )

        try:
            decompressed = zlib.decompress(body_bytes)
        except zlib.error as e:
            raise JepxProtocolError(f"gzip解凍失敗: {e}") from e

        body = json.loads(decompressed.decode('utf-8'))
        return header, body

    @staticmethod
    def validate_status(header: dict) -> None:
        """解体したレスポンスのヘッダーに記載されたシステムステータス(STATUS)を検証。

        正常(00)以外の場合は、エラー種別に応じた固有のJepxError子クラスを発生させる。

        Raises:
            JepxFormatError: STATUS=10 (電文フォーマット異常)
            JepxAuthError: STATUS=11 (権限なし)
            JepxSystemError: STATUS=19 (JEPXシステム異常、リトライ対象)
        """
        status = header.get('STATUS', '')
        if status == '00':
            return
        elif status == '10':
            raise JepxFormatError("電文フォーマット異常 (STATUS=10)")
        elif status == '11':
            raise JepxAuthError("会員ID権限なし (STATUS=11)")
        elif status == '19':
            raise JepxSystemError("JEPXシステム異常 (STATUS=19)")
        else:
            raise JepxProtocolError(f"未知のSTATUS: {status}")
