# In-memory storage for MockServer
# JEPX仕様書に準拠: 入札番号(bidNo)は10桁の数字文字列
import random

class MockState:
    def __init__(self):
        # bids[market] = [bid_dict, ...]
        self.bids = {
            "DAH": [],
            "ITD": []
        }
        self._bid_counter = random.randint(1000000000, 1999999999)

    def _next_bid_no(self) -> str:
        """JEPX仕様に準拠した10桁の入札番号を生成"""
        self._bid_counter += 1
        return str(self._bid_counter)

    def add_bid(self, market: str, bid_data: dict) -> str:
        """入札を追加し、JEPX仕様準拠の入札番号(bidNo)を返却"""
        bid_no = self._next_bid_no()
        bid_data['bidNo'] = bid_no
        self.bids[market].append(bid_data)
        return bid_no

    def get_bids(self, market: str, delivery_date: str = "") -> list:
        """指定された市場・受渡日の入札を取得"""
        market_bids = self.bids.get(market, [])
        if delivery_date:
            return [b for b in market_bids if b.get('deliveryDate') == delivery_date]
        return list(market_bids)

    def delete_bid(self, market: str, bid_no: str) -> bool:
        """入札番号(bidNo)で入札を削除"""
        market_bids = self.bids.get(market, [])
        original_len = len(market_bids)
        self.bids[market] = [b for b in market_bids if b.get('bidNo') != bid_no]
        return len(self.bids[market]) < original_len

    def delete_bids_by_date(self, market: str, delivery_date: str) -> int:
        """受渡日に該当する全入札を削除し、削除件数を返却"""
        market_bids = self.bids.get(market, [])
        original_len = len(market_bids)
        self.bids[market] = [b for b in market_bids if b.get('deliveryDate') != delivery_date]
        return original_len - len(self.bids[market])

# Global state instance
state = MockState()
