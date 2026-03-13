"""結合テスト (IT) スイート — 22.結合テスト仕様書.md 準拠

本テストスイートは、事前に MockServer (localhost:8888) が起動していることを前提とする。
dev環境 (JEPX_TLS_VERIFY=True, MockServer証明書) で動作させる。
"""
import asyncio
import os
import socket
import sys
import time
import unittest
from pathlib import Path

# WindowsのProactorEventLoopでEvent loop is closedエラーが出るのを回避するためのワークアラウンド
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from django.conf import settings
from django.core.management import call_command
from django.test import SimpleTestCase, AsyncClient

# MockServerが起動しているか確認するデコレータ
def is_mockserver_running(host='127.0.0.1', port=8888) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError:
        return False

skip_if_no_mockserver = unittest.skipUnless(
    is_mockserver_running(),
    "MockServer (localhost:8888) が起動していないためスキップします"
)


@skip_if_no_mockserver
class JepxIntegrationTests(SimpleTestCase):
    """MockServer環境と通信し、JEPX連動と業務ロジックを一気通貫で検証するシステム結合テスト。"""
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.async_client = AsyncClient()
        
        # テストデータのディレクトリ準備 (DAH連携用)
        cls.input_dir = settings.BASE_DIR / 'test_data' / 'input'
        cls.output_dir = settings.BASE_DIR / 'test_data' / 'output'
        cls.input_dir.mkdir(parents=True, exist_ok=True)
        cls.output_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        # バッチ出力フォルダをクリーンアップ
        for file in self.output_dir.glob('*.csv'):
            file.unlink(missing_ok=True)
            
        # イベントループがテストごとに切り替わるため、再利用されるグローバルプールをリセットする
        from apps.jepx_client.client import JepxApiClient
        JepxApiClient._pool = None
        super().tearDown()

    # -------------------------------------------------------------
    # 4.1 通信・接続検証 (IT-CON-01〜03)
    # -------------------------------------------------------------
    async def test_it_con_01_health_check(self):
        """IT-CON-01: healthチェックAPIによるTLSコンパクション確認"""
        response = await self.async_client.get('/health')
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertEqual(data['status'], 'ok')
        self.assertIn('itn_connected', data)
        self.assertIn('itn_version', data)
        self.assertIn('timestamp', data)
        # MockServerが動いていれば内部的にハンドシェイク成功

    # -------------------------------------------------------------
    # 4.2 ITD API 連携 (IT-ITD-01〜05)
    # -------------------------------------------------------------
    async def test_it_itd_01_valid_bid(self):
        """IT-ITD-01: ExcelからのITD新規入札 (正常系)"""
        payload = {
            "deliveryDate": "2026-05-01",  # バッチテストと分ける
            "areaCd": "1",
            "timeCd": "25",
            "bidTypeCd": "SELL-LIMIT",
            "price": 100.0,
            "volume": 50.0,
            "deliveryContractCd": "AAA",
            "note": "統合テスト入札"
        }
        # 前回実行で残留している入札を先に削除してクリーンな状態にする
        inq_res = await self.async_client.get(
            f'/api/v1/itd/inquiry?deliveryDate={payload["deliveryDate"]}&timeCd={payload["timeCd"]}'
        )
        if inq_res.status_code == 200:
            for bid in inq_res.json().get('bids', []):
                bid_no = bid.get('bidNo') or bid.get('bid_no')
                if bid_no:
                    await self.async_client.post('/api/v1/itd/delete', {
                        "deliveryDate": payload["deliveryDate"],
                        "timeCd": payload["timeCd"],
                        "bidNo": bid_no
                    }, content_type='application/json')

        res = await self.async_client.post('/api/v1/itd/bid', payload, content_type='application/json')
        bid_no = res.json().get('bid_no') if res.status_code == 200 else None
        try:
            self.assertEqual(res.status_code, 200, f"Response: {res.json()}")
            data = res.json()
            self.assertTrue(data['success'])
            self.assertIn('bid_no', data)  # 受付番号が付与されていること
        finally:
            # 必ずクリーンアップ実行 (MockServerのメモリに残るため)
            if bid_no:
                await self.async_client.post('/api/v1/itd/delete', {
                    "deliveryDate": payload["deliveryDate"],
                    "timeCd": payload["timeCd"],
                    "bidNo": bid_no
                }, content_type='application/json')

    async def test_it_itd_02_validation_error(self):
        """IT-ITD-02: バリデーションエラー"""
        payload = {
            "deliveryDate": "2026-04-01",
            "areaCd": "99",  # 存在しないエリア
            "timeCd": "24",
            "bidTypeCd": "SELL-LIMIT",
            "price": 100.0,
            "volume": 50.0,
            "deliveryContractCd": "AAA"  # 必須項目追記
        }
        res = await self.async_client.post('/api/v1/itd/bid', payload, content_type='application/json')
        self.assertEqual(res.status_code, 400)
        
        data = res.json()
        self.assertFalse(data['success'])
        self.assertEqual(data['error_code'], 'VALIDATION_ERROR')
        self.assertIn('無効なエリアコード', data['message'])  # メッセージ検証

    async def test_it_itd_04_delete_bid(self):
        """IT-ITD-04: 注文取消"""
        payload = {
            "deliveryDate": "2026-04-01",
            "timeCd": "24",
            "bidNo": "1234567890"  # MockServerでは適当な桁数でOK
        }
        res = await self.async_client.post('/api/v1/itd/delete', payload, content_type='application/json')
        self.assertEqual(res.status_code, 200)
        
        data = res.json()
        self.assertTrue(data['success'])

    # -------------------------------------------------------------
    # 4.3 ITN ストリーム配信 (IT-ITN-01)
    # -------------------------------------------------------------
    async def test_it_itn_01_stream_polling(self):
        """IT-ITN-01: ITN初期スナップショットのポーリング取得"""
        # ITNタスクはASGI上で動くため、TestCase(=WSGI/同期)の環境ではバックグラウンドタスクが動かない。
        # 代わりに、意図的にReceiverを1回だけ手動起動してストアを更新し、Viewを叩く。
        from apps.itn_stream.store import ItnMemoryStore
        from apps.jepx_client.client import JepxApiClient

        async def fetch_itn_once():
            client = JepxApiClient()
            store = ItnMemoryStore()
            store.set_connection_status(True)
            try:
                # 1秒だけ受信して切断
                async def consume():
                    async for header, body in client.start_stream('ITN1001', {}):
                        notices = body.get('notices', [])
                        if notices:
                            await store.update_notices(notices)
                            break
                await asyncio.wait_for(consume(), timeout=2.0)
            except Exception:
                pass
            return store

        # イベントループで1回受信
        store = await fetch_itn_once()
        
        # クライアント(View)経由でポーリングAPIを叩く
        # ※ ASGIアプリ経由の結合テストとしては、本来は `AsyncClient` が適している。
        # ここではポーリング用のURLを叩いてみる
        res = await self.async_client.get('/api/v1/itn/stream?mode=poll&version=0')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        
        self.assertIn('changed', data)

    # -------------------------------------------------------------
    # 4.4 DAH バッチ連携 (IT-DAH-01〜03)
    # -------------------------------------------------------------
    def test_it_dah_01_bid_batch(self):
        """IT-DAH-01: 入札バッチ (dah_bid) 正常系"""
        csv_file = self.input_dir / '2026-04-01.csv'
        csv_content = (
            "deliveryDate,areaCd,timeCd,subCd,bidTypeCd,price,volume,deliveryContractCd,note\n"
            "2026-04-01,1,24,1,SELL-LIMIT,100.0,50.0,BG01,バッチテスト\n"
        )
        csv_file.write_text(csv_content, encoding='utf-8')

        try:
            # バッチコマンド実行 (引数に--date)
            call_command('dah_bid', '--date=2026-04-01')
        finally:
            csv_file.unlink(missing_ok=True)
            
        # 結果確認 (dah_bidは成功時にはファイル出力しないため0件であること)
        out_files = list(self.output_dir.glob('*.csv'))
        self.assertEqual(len(out_files), 0)

    def test_it_dah_04_inquiry_batch(self):
        """IT-DAH-04: 照会バッチ (dah_inquiry)"""
        # バッチコマンド実行 (引数に--date)
        call_command('dah_inquiry', '--date=2026-04-01')
        
        # outputフォルダに結果(清算PDF)が出力されること
        out_files = list(self.output_dir.glob('*.pdf'))
        self.assertGreaterEqual(len(out_files), 1)
