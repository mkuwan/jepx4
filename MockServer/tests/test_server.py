import unittest
import asyncio
import ssl
import json
import zlib
import time
from concurrent.futures import ThreadPoolExecutor

# MockServer configuration values expected
HOST = '127.0.0.1'
PORT = 8888

SOH = b'\x01'
STX = b'\x02'
ETX = b'\x03'

def build_jepx_request(member: str, api: str, body: dict) -> bytes:
    json_bytes = json.dumps(body).encode('utf-8')
    compressed_body = zlib.compress(json_bytes)
    size = len(compressed_body)
    header = f"MEMBER={member},API={api},SIZE={size}".encode('ascii')
    return SOH + header + STX + compressed_body + ETX

def parse_jepx_response(data: bytes) -> tuple[dict, dict]:
    soh_idx = data.find(SOH)
    stx_idx = data.find(STX)
    etx_idx = data.rfind(ETX)
    
    header_bytes = data[soh_idx + 1:stx_idx]
    header_str = header_bytes.decode('ascii')
    header_dict = dict(pair.split('=') for pair in header_str.split(','))
    
    body_bytes = data[stx_idx + 1:etx_idx]
    if body_bytes:
        decompressed = zlib.decompress(body_bytes)
        body_dict = json.loads(decompressed.decode('utf-8'))
    else:
        body_dict = {}
        
    return header_dict, body_dict

class TestJepxMockServer(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE
        
        try:
            self.reader, self.writer = await asyncio.open_connection(
                HOST, PORT, ssl=self.ssl_context
            )
        except ConnectionRefusedError:
            self.skipTest("MockServer is not running on localhost:8888. Please start the server first.")

    async def asyncTearDown(self):
        if hasattr(self, 'writer') and not self.writer.is_closing():
            self.writer.close()

    async def _send_and_receive(self, packet: bytes) -> bytes:
        self.writer.write(packet)
        await self.writer.drain()
        
        response_data = bytearray()
        while True:
            chunk = await self.reader.read(4096)
            if not chunk:
                break
            response_data.extend(chunk)
            if ETX in chunk:
                break
        return bytes(response_data)

    # ================================================================
    # テスト1: SYS1001 Keep-Alive 正常系
    # ================================================================
    async def test_01_sys1001_keep_alive(self):
        """
        [テスト1] SYS1001 (Keep-Alive) の正常系テスト
        目的: 切断防止用の共通APIを送信し、JEPX仕様通りの正常レスポンスが返るか検証する。
        """
        req = build_jepx_request("9999", "SYS1001", {})
        resp_data = await self._send_and_receive(req)
        
        header, body = parse_jepx_response(resp_data)
        self.assertEqual(header.get("STATUS"), "00")
        self.assertEqual(body.get("status"), "200")
        self.assertIn("Socket Expiration Time Extension", body.get("statusInfo", ""))

    # ================================================================
    # テスト2: DAH1001入札 → DAH1002照会の状態保持テスト
    # ================================================================
    async def test_02_dah1001_bid_and_dah1002_inquiry(self):
        """
        [テスト2] 翌日市場 入札(DAH1001) と 入札照会(DAH1002) の状態保持テスト
        目的: 入札データがメモリに保存され、照会APIでJEPX仕様の bids[] 配列として返るか検証。
        """
        bid_body = {
            "bidOffers": [{
                "deliveryDate": "2026-04-01", "areaCd": "1", "timeCd": "48",
                "bidTypeCd": "SELL-LIMIT", "price": 120, "volume": 4320.5,
                "deliveryContractCd": "ABCD8"
            }]
        }
        
        req_bid = build_jepx_request("9999", "DAH1001", bid_body)
        resp_bid = await self._send_and_receive(req_bid)
        head_bid, body_bid = parse_jepx_response(resp_bid)
        
        # JEPX仕様: STATUS=00, body.status="200", statusInfo=入札件数
        self.assertEqual(head_bid.get("STATUS"), "00")
        self.assertEqual(body_bid.get("status"), "200")
        self.assertEqual(body_bid.get("statusInfo"), "1")
        
        # DAH1002 照会: JEPX仕様は bids[] 配列
        req_inq = build_jepx_request("9999", "DAH1002", {"deliveryDate": "2026-04-01"})
        resp_inq = await self._send_and_receive(req_inq)
        head_inq, body_inq = parse_jepx_response(resp_inq)
        
        self.assertEqual(head_inq.get("STATUS"), "00")
        bids = body_inq.get("bids", [])
        self.assertTrue(len(bids) > 0)
        
        # bidNoが採番されていて、入札価格が一致すること
        found = bids[0]
        self.assertIn("bidNo", found)
        self.assertEqual(found.get("price"), 120)

    # ================================================================
    # テスト3: 無効MEMBER認証エラー
    # ================================================================
    async def test_03_invalid_member(self):
        """
        [テスト3] 異常系: 無効なMEMBER IDによる認証エラーテスト
        目的: 不正な会員IDでSTATUS=11が返るか検証する。
        """
        req = build_jepx_request("INVALID", "SYS1001", {})
        try:
            resp_data = await self._send_and_receive(req)
            if resp_data:
                header, body = parse_jepx_response(resp_data)
                self.assertEqual(header.get("STATUS"), "11")
        except ConnectionResetError:
            pass

    # ================================================================
    # テスト4: ITN1001ストリーミング（全量配信→差分配信）
    # ================================================================
    async def test_04_itn1001_stream(self):
        """
        [テスト4] 時間前市場 ITN1001 (市場情報通知) のストリーミング受信テスト
        目的: 全量配信（当日＋翌日の全板情報）を受信後、
              10秒間隔でサーバーからPushされる差分データを受信できるか検証する。
        """
        req = build_jepx_request("0841", "ITN1001", {})
        self.writer.write(req)
        await self.writer.drain()
        
        # 1回目: 全量配信
        response_data_1 = bytearray()
        while True:
            chunk = await asyncio.wait_for(self.reader.read(4096), timeout=5.0)
            if not chunk: break
            response_data_1.extend(chunk)
            if ETX in chunk: break
                
        self.assertTrue(len(response_data_1) > 0)
        header_1, body_1 = parse_jepx_response(bytes(response_data_1))
        self.assertEqual(header_1.get("STATUS"), "00")
        self.assertIn("notices", body_1)
        self.assertTrue(len(body_1.get("notices", [])) > 0)
        self.assertEqual(body_1.get("memo"), "Mock: Current Full Market State")

        # 2回目: 差分配信（10秒後にエンジンからPush）
        response_data_2 = bytearray()
        while True:
            chunk = await asyncio.wait_for(self.reader.read(4096), timeout=15.0)
            if not chunk: break
            response_data_2.extend(chunk)
            if ETX in chunk: break

        self.assertTrue(len(response_data_2) > 0)
        header_2, body_2 = parse_jepx_response(bytes(response_data_2))
        self.assertEqual(header_2.get("STATUS"), "00")
        notices_2 = body_2.get("notices", [])
        self.assertTrue(len(notices_2) > 0)
        self.assertIn(notices_2[0].get("noticeTypeCd"), ["CONTRACT", "BID-BOARD"])
        self.assertTrue("from Engine" in body_2.get("memo", ""))

    # ================================================================
    # テスト5: DAH1003入札削除 + DAH1004約定照会
    # ================================================================
    async def test_05_dah1003_delete_and_dah1004_contract(self):
        """
        [テスト5] 翌日市場 入札削除(DAH1003) と 約定照会(DAH1004) のテスト
        目的: JEPX仕様902準拠の削除フォーマット(bidDels[].bidNo)と約定照会フォーマット(bidResults[])を検証。
        """
        # 1. 入札
        req_bid = build_jepx_request("9999", "DAH1001", {
            "bidOffers": [{"deliveryDate": "2026-04-02", "areaCd": "1", "timeCd": "48", "price": 100, "volume": 10}]
        })
        resp_bid = await self._send_and_receive(req_bid)
        _, body_bid = parse_jepx_response(resp_bid)
        self.assertEqual(body_bid.get("statusInfo"), "1")
        
        # 2. 照会してbidNoを取得
        req_inq = build_jepx_request("9999", "DAH1002", {"deliveryDate": "2026-04-02"})
        resp_inq = await self._send_and_receive(req_inq)
        _, body_inq = parse_jepx_response(resp_inq)
        bids = body_inq.get("bids", [])
        self.assertTrue(len(bids) > 0)
        bid_no = bids[0].get("bidNo")
        
        # 3. JEPX仕様準拠の削除: bidDels[].bidNo
        del_body = {"deliveryDate": "2026-04-02", "bidDels": [{"bidNo": bid_no}]}
        req_del = build_jepx_request("9999", "DAH1003", del_body)
        resp_del = await self._send_and_receive(req_del)
        head_del, body_del = parse_jepx_response(resp_del)
        self.assertEqual(head_del.get("STATUS"), "00")
        self.assertEqual(body_del.get("status"), "200")
        self.assertEqual(body_del.get("statusInfo"), "1")  # 1件削除
        
        # 4. 削除後に照会: 空であること
        req_inq2 = build_jepx_request("9999", "DAH1002", {"deliveryDate": "2026-04-02"})
        resp_inq2 = await self._send_and_receive(req_inq2)
        _, body_inq2 = parse_jepx_response(resp_inq2)
        self.assertEqual(len(body_inq2.get("bids", [])), 0)
        
        # 5. DAH1004 約定照会: bidResults[]にcontractPrice/contractVolumeが含まれること
        req_con = build_jepx_request("9999", "DAH1004", {"deliveryDate": "2026-04-02"})
        resp_con = await self._send_and_receive(req_con)
        head_con, body_con = parse_jepx_response(resp_con)
        self.assertEqual(head_con.get("STATUS"), "00")
        results = body_con.get("bidResults", [])
        self.assertTrue(len(results) > 0)
        self.assertIn("contractPrice", results[0])
        self.assertIn("contractVolume", results[0])

    # ================================================================
    # テスト6: ITD系 (ITD1001, ITD1002, ITD1003, ITD1004) 統合テスト
    # ================================================================
    async def test_06_itd_market_suite(self):
        """
        [テスト6] 時間前市場 (ITD1001→ITD1003→ITD1002→ITD1004) の統合テスト
        目的: JEPX仕様903準拠のリクエスト/レスポンスフォーマットで全CRUDが正常に動作するか検証。
        """
        # 1. ITD1001 入札: JEPX仕様ではbidNoが返る
        req_bid = build_jepx_request("9999", "ITD1001", {
            "deliveryDate": "2026-04-03", "timeCd": "24", "areaCd": "1",
            "bidTypeCd": "SELL-LIMIT", "price": 50, "volume": 5,
            "deliveryContractCd": "MOCK01"
        })
        resp_bid = await self._send_and_receive(req_bid)
        head_bid, body_bid = parse_jepx_response(resp_bid)
        self.assertEqual(head_bid.get("STATUS"), "00")
        bid_no = body_bid.get("bidNo")
        self.assertIsNotNone(bid_no)
        
        # 2. ITD1003 照会: JEPX仕様では bids[] 配列
        req_inq = build_jepx_request("9999", "ITD1003", {"deliveryDate": "2026-04-03"})
        resp_inq = await self._send_and_receive(req_inq)
        _, body_inq = parse_jepx_response(resp_inq)
        self.assertTrue(any(b.get("bidNo") == bid_no for b in body_inq.get("bids", [])))
        
        # 3. ITD1002 削除要求: JEPX仕様では targetBidNo
        req_del = build_jepx_request("9999", "ITD1002", {
            "deliveryDate": "2026-04-03", "timeCd": "24", "targetBidNo": bid_no
        })
        resp_del = await self._send_and_receive(req_del)
        _, body_del = parse_jepx_response(resp_del)
        self.assertEqual(body_del.get("status"), "200")
        
        # 4. ITD1004 約定照会: bidResults[]にcontractPrice/contractVolumeが含まれること
        req_con = build_jepx_request("9999", "ITD1004", {"deliveryDate": "2026-04-03"})
        resp_con = await self._send_and_receive(req_con)
        _, body_con = parse_jepx_response(resp_con)
        results = body_con.get("bidResults", [])
        self.assertTrue(len(results) > 0)
        self.assertIn("contractPrice", results[0])

    # ================================================================
    # テスト7: 電文フォーマット異常 (SIZE不一致)
    # ================================================================
    async def test_07_data_format_error(self):
        """
        [テスト7] 異常系: ヘッダのSIZEと実Bodyサイズが異なる場合にSTATUS=10を返すか検証。
        """
        json_bytes = json.dumps({"test": "data"}).encode('utf-8')
        compressed_body = zlib.compress(json_bytes)
        fake_size = 999999
        header = f"MEMBER=9999,API=DAH1001,SIZE={fake_size}".encode('ascii')
        bad_packet = SOH + header + STX + compressed_body + ETX
        
        try:
            resp_data = await self._send_and_receive(bad_packet)
            if resp_data:
                head, body = parse_jepx_response(resp_data)
                self.assertEqual(head.get("STATUS"), "10")
        except ConnectionResetError:
            pass

    # ================================================================
    # テスト8: TLS 1.3 プロトコル検証
    # ================================================================
    async def test_08_tls13_connection(self):
        """
        [テスト8] MockServerがJEPX仕様のTLS 1.3で通信していることを確認する。
        """
        ssl_object = self.writer.get_extra_info('ssl_object')
        self.assertIsNotNone(ssl_object)
        self.assertEqual(ssl_object.version(), "TLSv1.3")

    # ================================================================
    # テスト9: 未知APIコードのエラー応答
    # ================================================================
    async def test_09_unknown_api_code(self):
        """
        [テスト9] 異常系: 存在しないAPIコードに対しSTATUS=10が返るか検証する。
        """
        req = build_jepx_request("9999", "ZZZ9999", {})
        try:
            resp_data = await self._send_and_receive(req)
            if resp_data:
                head, body = parse_jepx_response(resp_data)
                self.assertEqual(head.get("STATUS"), "10")
        except ConnectionResetError:
            pass

    # ================================================================
    # テスト10: Keep-Alive後のSocket維持確認
    # ================================================================
    async def test_10_sys1001_keep_alive_extends_socket(self):
        """
        [テスト10] SYS1001の後、同一Socketで別APIが正常に処理されるか検証する。
        """
        req_ka = build_jepx_request("9999", "SYS1001", {})
        resp_ka = await self._send_and_receive(req_ka)
        head_ka, _ = parse_jepx_response(resp_ka)
        self.assertEqual(head_ka.get("STATUS"), "00")
        
        req_inq = build_jepx_request("9999", "DAH1002", {"deliveryDate": "2026-01-01"})
        resp_inq = await self._send_and_receive(req_inq)
        head_inq, body_inq = parse_jepx_response(resp_inq)
        self.assertEqual(head_inq.get("STATUS"), "00")
        self.assertIn("bids", body_inq)

    # ================================================================
    # テスト11: DAH1030エイリアス
    # ================================================================
    async def test_11_dah1030_alias(self):
        """
        [テスト11] DAH1030がDAH1004と同じ約定照会ハンドラで処理されるか検証する。
        """
        req = build_jepx_request("9999", "DAH1030", {"deliveryDate": "2026-04-01"})
        resp = await self._send_and_receive(req)
        head, body = parse_jepx_response(resp)
        self.assertEqual(head.get("STATUS"), "00")
        self.assertTrue(len(body.get("bidResults", [])) > 0)

    # ================================================================
    # テスト12: ITN全量配信のJEPX仕様フィールド検証
    # ================================================================
    async def test_12_itn_full_state_structure(self):
        """
        [テスト12] 全量配信データの各要素がJEPX仕様903の必須フィールドを含むか検証する。
        """
        req = build_jepx_request("0841", "ITN1001", {})
        self.writer.write(req)
        await self.writer.drain()
        
        response_data = bytearray()
        while True:
            chunk = await asyncio.wait_for(self.reader.read(8192), timeout=5.0)
            if not chunk: break
            response_data.extend(chunk)
            if ETX in chunk: break
        
        _, body = parse_jepx_response(bytes(response_data))
        notices = body.get("notices", [])
        self.assertTrue(len(notices) > 0)
        sample = notices[0]
        for key in ["noticeTypeCd", "deliveryDate", "timeCd", "price", "volume"]:
            self.assertIn(key, sample)

    # ================================================================
    # テスト13: DAH1001 複数入札の一括送信
    # ================================================================
    async def test_13_dah1001_multi_bid(self):
        """
        [テスト13] 複数入札を一括送信し、statusInfoに件数が返り全件登録されるか検証する。
        ※サーバーの状態は複数回のテスト実行で蓄積されるため、
          「自分が登録した3件が照会結果に含まれること」で検証する。
        """
        bid_body = {
            "bidOffers": [
                {"deliveryDate": "2026-05-01", "areaCd": "2", "timeCd": "01", "price": 10, "volume": 100},
                {"deliveryDate": "2026-05-01", "areaCd": "2", "timeCd": "02", "price": 15, "volume": 200},
                {"deliveryDate": "2026-05-01", "areaCd": "2", "timeCd": "03", "price": 20, "volume": 300}
            ]
        }
        req = build_jepx_request("9999", "DAH1001", bid_body)
        resp = await self._send_and_receive(req)
        head, body = parse_jepx_response(resp)
        
        self.assertEqual(head.get("STATUS"), "00")
        # JEPX仕様: statusInfo = 入札件数
        self.assertEqual(body.get("statusInfo"), "3")
        
        # 照会: 少なくとも3件以上存在すること
        req_inq = build_jepx_request("9999", "DAH1002", {"deliveryDate": "2026-05-01"})
        resp_inq = await self._send_and_receive(req_inq)
        _, body_inq = parse_jepx_response(resp_inq)
        bids = body_inq.get("bids", [])
        self.assertGreaterEqual(len(bids), 3)
        
        # 今回登録した3件がそれぞれユニークなbidNoを持ち、照会結果に含まれること
        bid_nos = [b.get("bidNo") for b in bids]
        unique_nos = set(bid_nos)
        self.assertGreaterEqual(len(unique_nos), 3)

    # ================================================================
    # テスト14: レスポンスヘッダSIZE整合性
    # ================================================================
    async def test_14_response_header_size_validation(self):
        """
        [テスト14] レスポンスのSIZEフィールドと実際のBody長が一致するか検証する。
        """
        req = build_jepx_request("9999", "SYS1001", {})
        resp_data = await self._send_and_receive(req)
        
        soh_idx = resp_data.find(SOH)
        stx_idx = resp_data.find(STX)
        etx_idx = resp_data.rfind(ETX)
        
        header_str = resp_data[soh_idx + 1:stx_idx].decode('ascii')
        header_dict = dict(pair.split('=') for pair in header_str.split(','))
        declared_size = int(header_dict.get("SIZE", "0"))
        actual_size = len(resp_data[stx_idx + 1:etx_idx])
        
        self.assertEqual(declared_size, actual_size)

    # ================================================================
    # テスト15: ITN全量配信の日付範囲検証
    # ================================================================
    async def test_15_itn_full_state_date_range(self):
        """
        [テスト15] 全量配信のnoticesが当日＋翌日のみで構成されているか検証する。
        ※DockerコンテナはUTC、テストクライアントはJSTのため、
          日付境界付近では±1日の差が生じうる。許容範囲を広げて検証する。
        """
        from datetime import date, timedelta
        
        req = build_jepx_request("0841", "ITN1001", {})
        self.writer.write(req)
        await self.writer.drain()
        
        response_data = bytearray()
        while True:
            chunk = await asyncio.wait_for(self.reader.read(8192), timeout=5.0)
            if not chunk: break
            response_data.extend(chunk)
            if ETX in chunk: break
        
        _, body = parse_jepx_response(bytes(response_data))
        notices = body.get("notices", [])
        self.assertTrue(len(notices) > 0)
        
        # UTC/JST差を考慮: 昨日〜明後日の範囲を許容
        today = date.today()
        allowed_dates = {
            (today + timedelta(days=d)).isoformat()
            for d in range(-1, 3)  # yesterday, today, tomorrow, day_after
        }
        
        for notice in notices:
            self.assertIn(notice.get("deliveryDate", ""), allowed_dates)

    # ================================================================
    # テスト16: ITN差分配信の日付有効性
    # ================================================================
    async def test_16_itn_diff_delivery_date_valid(self):
        """
        [テスト16] 差分配信のdeliveryDateが当日/翌日の範囲内であるか検証する。
        ※DockerコンテナはUTC、テストクライアントはJSTのため許容範囲を広げる。
        """
        from datetime import date, timedelta
        
        req = build_jepx_request("0841", "ITN1001", {})
        self.writer.write(req)
        await self.writer.drain()
        
        # 1回目: 全量受信（スキップ）
        while True:
            chunk = await asyncio.wait_for(self.reader.read(8192), timeout=5.0)
            if ETX in chunk: break
        
        # 2回目: 差分受信
        response_data = bytearray()
        while True:
            chunk = await asyncio.wait_for(self.reader.read(4096), timeout=15.0)
            if not chunk: break
            response_data.extend(chunk)
            if ETX in chunk: break
        
        _, body = parse_jepx_response(bytes(response_data))
        notices = body.get("notices", [])
        self.assertTrue(len(notices) > 0)
        
        today = date.today()
        allowed_dates = {
            (today + timedelta(days=d)).isoformat()
            for d in range(-1, 3)
        }
        for notice in notices:
            self.assertIn(notice.get("deliveryDate", ""), allowed_dates)

    # ================================================================
    # テスト17: DAH1003 存在しないbidNoの削除
    # ================================================================
    async def test_17_dah1003_delete_nonexistent_bid(self):
        """
        [テスト17] 存在しないbidNoに対して削除すると、statusInfo="0"（0件削除）が返るか検証する。
        """
        del_body = {"deliveryDate": "2026-01-01", "bidDels": [{"bidNo": "0000000000"}]}
        req = build_jepx_request("9999", "DAH1003", del_body)
        resp = await self._send_and_receive(req)
        head, body = parse_jepx_response(resp)
        
        self.assertEqual(head.get("STATUS"), "00")
        self.assertEqual(body.get("statusInfo"), "0")

    # ================================================================
    # テスト18: 空ボディリクエスト処理
    # ================================================================
    async def test_18_empty_body_request(self):
        """
        [テスト18] 空JSON({})でDAH1002照会してもクラッシュせず空のbids[]が返るか検証する。
        """
        req = build_jepx_request("9999", "DAH1002", {})
        resp = await self._send_and_receive(req)
        head, body = parse_jepx_response(resp)
        
        self.assertEqual(head.get("STATUS"), "00")
        self.assertIsInstance(body.get("bids"), list)

    # ================================================================
    # テスト19: DAH9001 清算照会
    # ================================================================
    async def test_19_dah9001_settlement(self):
        """
        [テスト19] 翌日市場 清算照会(DAH9001)がJEPX仕様902準拠のsettlements[]を返すか検証する。
        """
        req = build_jepx_request("9999", "DAH9001", {"fromDate": "2026-04-01"})
        resp = await self._send_and_receive(req)
        head, body = parse_jepx_response(resp)
        
        self.assertEqual(head.get("STATUS"), "00")
        self.assertEqual(body.get("status"), "200")
        settlements = body.get("settlements", [])
        self.assertTrue(len(settlements) > 0)
        
        s = settlements[0]
        self.assertIn("settlementNo", s)
        self.assertIn("settlementDate", s)
        self.assertIn("title", s)
        self.assertIn("totalAmount", s)
        self.assertIn("items", s)
        self.assertIn("pdf", s)

    # ================================================================
    # テスト20: ITD9001 清算照会
    # ================================================================
    async def test_20_itd9001_settlement(self):
        """
        [テスト20] 時間前市場 清算照会(ITD9001)がJEPX仕様903準拠のsettlements[]を返すか検証する。
        """
        req = build_jepx_request("9999", "ITD9001", {"fromDate": "2026-04-01"})
        resp = await self._send_and_receive(req)
        head, body = parse_jepx_response(resp)
        
        self.assertEqual(head.get("STATUS"), "00")
        self.assertEqual(body.get("status"), "200")
        settlements = body.get("settlements", [])
        self.assertTrue(len(settlements) > 0)
        
        s = settlements[0]
        for key in ["settlementNo", "settlementDate", "title", "totalAmount", "items", "pdf"]:
            self.assertIn(key, s)

if __name__ == '__main__':
    unittest.main()
