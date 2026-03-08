import unittest
import socket
import gzip
import json
import time

HOST = '127.0.0.1'
PORT = 8888

SOH = b'\x01'
STX = b'\x02'
ETX = b'\x03'

class TestJepxMockServer(unittest.TestCase):

    def send_request(self, api_code, body_dict):
        """Helper to send a request to the Mock Server and return the response body as a dict."""
        body_json = json.dumps(body_dict).encode('utf-8')
        compressed_body = gzip.compress(body_json)
        size = len(compressed_body)
        
        header_str = f"MEMBER=9999,API={api_code},SIZE={size}"
        header_bytes = header_str.encode('ascii')
        
        packet = SOH + header_bytes + STX + compressed_body + ETX
        
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(5.0)  # Add a timeout
            try:
                s.connect((HOST, PORT))
            except ConnectionRefusedError:
                self.fail(f"Could not connect to {HOST}:{PORT}. Is the Mock Server running?")

            s.sendall(packet)
            
            # Read response
            # 1. Read SOH
            soh = s.recv(1)
            if not soh:
                return {} # Connection closed prematurely or empty
            self.assertEqual(soh, SOH, f"Expected SOH (0x01), got {soh}")

            # 2. Read Header until STX
            header_bytes = bytearray()
            while True:
                b = s.recv(1)
                if not b: break
                if b == STX: break
                header_bytes.extend(b)
            
            header_str = header_bytes.decode('ascii')
            header_dict = {}
            for part in header_str.split(','):
                if '=' in part:
                     k, v = part.split('=', 1)
                     header_dict[k.strip()] = v.strip()
            
            # 3. Read Body based on SIZE
            try:
                size = int(header_dict.get("SIZE", 0))
            except ValueError:
                self.fail("Invalid SIZE in response header")

            body_data = bytearray()
            while len(body_data) < size:
                chunk = s.recv(size - len(body_data))
                if not chunk: break
                body_data.extend(chunk)
                
            # 4. Read ETX
            etx = s.recv(1)
            self.assertEqual(etx, ETX, f"Expected ETX (0x03), got {etx}")

            # 5. Decompress
            try:
                resp_json = gzip.decompress(body_data)
                return json.loads(resp_json)
            except Exception as e:
                self.fail(f"Failed to decompress/parse response: {e}")
                return {}

    def test_dah1001_submit_bid(self):
        """Test DAH1001: Day Ahead Bid Submission"""
        body = {
            "bidOffers": [
                {"deliveryDate": "2023-04-01", "areaCd": "1", "timeCd": "01", "price": 10.0, "volume": 100.0}
            ]
        }
        response = self.send_request("DAH1001", body)
        
        self.assertEqual(response.get("status"), "200")
        # According to logic in handlers.py, statusInfo should be the count of bids = "1"
        self.assertEqual(response.get("statusInfo"), "1")

    def test_dah1002_bid_inquiry(self):
        """Test DAH1002: Day Ahead Bid Inquiry"""
        test_delivery_date = "2023-05-01"
        body = {
            "deliveryDate": test_delivery_date
        }
        response = self.send_request("DAH1002", body)
        
        self.assertEqual(response.get("status"), "200")
        bids = response.get("bids", [])
        self.assertTrue(len(bids) > 0, "Should return at least one bid")
        # Check if the mock returns the requested delivery date
        self.assertEqual(bids[0].get("deliveryDate"), test_delivery_date)

    def test_dah1003_delete_bid(self):
        """Test DAH1003: Day Ahead Bid Deletion"""
        body = {
            "bidDels": [
                {"bidNo": "1234567890"}
            ]
        }
        response = self.send_request("DAH1003", body)
        
        self.assertEqual(response.get("status"), "200")
        self.assertEqual(response.get("statusInfo"), "1")

    def test_itd1001_intraday_submit(self):
        """Test ITD1001: Intraday Bid Submission"""
        body = {
             "deliveryDate": "2023-04-01",
             "timeCd": "48",
             "areaCd": "1",
             "bidTypeCd": "SELL-LIMIT",
             "price": 120,
             "volume": 4320.5,
             "deliveryContractCd": "ABCDE"
        }
        response = self.send_request("ITD1001", body)
        
        self.assertEqual(response.get("status"), "200")
        self.assertIn("bidNo", response)

    def test_sys1001_keep_alive(self):
        """Test SYS1001: Keep Alive (Socket extension)"""
        response = self.send_request("SYS1001", {})
        
        self.assertEqual(response.get("status"), "200")
        self.assertEqual(response.get("statusInfo"), "Socket Expiration Time Extension")

    def test_unknown_api(self):
        """Test handling of an unknown API code"""
        response = self.send_request("UNKNOWN123", {})
        self.assertEqual(response.get("status"), "500")
        self.assertTrue("Unknown API" in response.get("statusInfo", ""))

if __name__ == "__main__":
    unittest.main()
