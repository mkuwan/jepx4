"""§3.2 JepxProtocol — 電文組立・解析のユニットテスト

テスト観点:
- build_packet: SOH/STX/ETX フレーミング、ヘッダ形式、gzip圧縮
- parse_response: 正常解析、SIZE不一致、フレーム異常、gzip破損
- validate_status: STATUS=00/10/11/19/未知
"""
import json
import zlib
import unittest
import os
import sys

# Django設定
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django
django.setup()

from apps.jepx_client.protocol import JepxProtocol, SOH, STX, ETX
from apps.jepx_client.exceptions import (
    JepxProtocolError, JepxFormatError, JepxAuthError, JepxSystemError,
)


class TestBuildPacket(unittest.TestCase):
    """§3.2 JEPX電文仕様に準拠した送信用特殊パケット構築(SOH/STX制御文字付与・gzip圧縮)の検証"""

    def test_packet_structure(self):
        """SOH + Header + STX + gzip(JSON) + ETX の構造を検証"""
        packet = JepxProtocol.build_packet('9999', 'DAH1001', {'key': 'val'})
        self.assertTrue(packet.startswith(SOH))
        self.assertTrue(packet.endswith(ETX))
        self.assertIn(STX, packet)

    def test_header_format(self):
        """ヘッダが MEMBER=xxxx,API=xxxxxxx,SIZE=nnn 形式であること"""
        packet = JepxProtocol.build_packet('9999', 'DAH1001', {})
        header = packet[1:packet.index(STX)].decode('ascii')
        parts = dict(p.split('=') for p in header.split(','))
        self.assertEqual(parts['MEMBER'], '9999')
        self.assertEqual(parts['API'], 'DAH1001')
        self.assertTrue(parts['SIZE'].isdigit())

    def test_body_is_gzipped_json(self):
        """ボディ部がgzip圧縮されたJSONであること"""
        body = {'deliveryDate': '2026-04-01', 'bidOffers': []}
        packet = JepxProtocol.build_packet('0841', 'DAH1001', body)
        compressed = packet[packet.index(STX) + 1:packet.rindex(ETX)]
        decompressed = zlib.decompress(compressed)
        parsed = json.loads(decompressed)
        self.assertEqual(parsed, body)

    def test_size_matches_compressed_body(self):
        """ヘッダのSIZEがgzip圧縮後のバイト数と一致すること"""
        body = {'test': 'data' * 100}
        packet = JepxProtocol.build_packet('9999', 'SYS1001', body)
        header = packet[1:packet.index(STX)].decode('ascii')
        declared_size = int(dict(p.split('=') for p in header.split(','))['SIZE'])
        actual_body = packet[packet.index(STX) + 1:packet.rindex(ETX)]
        self.assertEqual(declared_size, len(actual_body))

    def test_empty_body(self):
        """SYS1001: 空ボディでも正しくパケットを生成すること"""
        packet = JepxProtocol.build_packet('9999', 'SYS1001', {})
        self.assertTrue(len(packet) > 3)  # SOH + header + STX + body + ETX

    def test_member_4_digits(self):
        """会員IDが4桁でヘッダに含まれること"""
        packet = JepxProtocol.build_packet('0841', 'DAH1002', {})
        header = packet[1:packet.index(STX)].decode('ascii')
        self.assertIn('MEMBER=0841', header)


class TestParseResponse(unittest.TestCase):
    """§3.2 parse_response のテスト"""

    def _build_response(self, status='00', body=None):
        """テスト用レスポンス電文を構築する"""
        if body is None:
            body = {'status': '200', 'statusInfo': 'OK'}
        json_bytes = json.dumps(body).encode('utf-8')
        compressed = zlib.compress(json_bytes)
        header = f"STATUS={status},SIZE={len(compressed)}".encode('ascii')
        return SOH + header + STX + compressed + ETX

    def test_normal_parse(self):
        """正常レスポンスの解析"""
        raw = self._build_response('00', {'status': '200', 'statusInfo': 'Success'})
        header, body = JepxProtocol.parse_response(raw)
        self.assertEqual(header['STATUS'], '00')
        self.assertEqual(body['status'], '200')
        self.assertEqual(body['statusInfo'], 'Success')

    def test_size_mismatch(self):
        """SIZE不一致で JepxProtocolError が発生すること"""
        body = json.dumps({'status': '200'}).encode('utf-8')
        compressed = zlib.compress(body)
        # SIZEを意図的に不正値にする
        header = f"STATUS=00,SIZE={len(compressed) + 10}".encode('ascii')
        raw = SOH + header + STX + compressed + ETX
        with self.assertRaises(JepxProtocolError):
            JepxProtocol.parse_response(raw)

    def test_missing_soh(self):
        """SOH欠落で JepxProtocolError が発生すること"""
        with self.assertRaises(JepxProtocolError):
            JepxProtocol.parse_response(b'STATUS=00,SIZE=0' + STX + ETX)

    def test_corrupted_gzip(self):
        """gzip破損で JepxProtocolError が発生すること"""
        header = b"STATUS=00,SIZE=5"
        raw = SOH + header + STX + b'\x00\x01\x02\x03\x04' + ETX
        with self.assertRaises(JepxProtocolError):
            JepxProtocol.parse_response(raw)

    def test_roundtrip(self):
        """build → parse のラウンドトリップテスト"""
        orig_body = {'deliveryDate': '2026-04-01', 'areaCd': '1'}
        packet = JepxProtocol.build_packet('9999', 'DAH1001', orig_body)
        # パケットからレスポンスを模擬構築
        compressed = packet[packet.index(STX) + 1:packet.rindex(ETX)]
        resp = SOH + f"STATUS=00,SIZE={len(compressed)}".encode('ascii') + STX + compressed + ETX
        header, body = JepxProtocol.parse_response(resp)
        self.assertEqual(body, orig_body)


class TestValidateStatus(unittest.TestCase):
    """§3.2 validate_status のテスト"""

    def test_status_00(self):
        """STATUS=00: 正常 (例外なし)"""
        JepxProtocol.validate_status({'STATUS': '00'})

    def test_status_10(self):
        """STATUS=10: JepxFormatError"""
        with self.assertRaises(JepxFormatError):
            JepxProtocol.validate_status({'STATUS': '10'})

    def test_status_11(self):
        """STATUS=11: JepxAuthError"""
        with self.assertRaises(JepxAuthError):
            JepxProtocol.validate_status({'STATUS': '11'})

    def test_status_19(self):
        """STATUS=19: JepxSystemError"""
        with self.assertRaises(JepxSystemError):
            JepxProtocol.validate_status({'STATUS': '19'})

    def test_unknown_status(self):
        """未知のSTATUS: JepxProtocolError"""
        with self.assertRaises(JepxProtocolError):
            JepxProtocol.validate_status({'STATUS': '99'})


if __name__ == '__main__':
    unittest.main()
