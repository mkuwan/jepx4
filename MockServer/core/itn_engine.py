import asyncio
import random
from datetime import datetime, date, timedelta
from typing import List, Dict

from config import ITN_PUSH_INTERVAL_SEC


def _random_price(base_min: float = 80.0, base_max: float = 200.0,
                  time_cd: int = 24) -> float:
    """JEPX互換の市場価格を生成（10の倍数、円/MWh）"""
    base = random.uniform(base_min, base_max)
    if 14 <= time_cd <= 18:    # 朝ピーク
        base *= random.uniform(1.3, 2.5)
    elif 36 <= time_cd <= 42:  # 夕方ピーク
        base *= random.uniform(1.2, 2.0)
    elif 1 <= time_cd <= 6:    # 深夜帯
        base *= random.uniform(0.4, 0.7)
    return round(base / 10) * 10  # 10の倍数に丸め


class ITNMarketEngine:
    def __init__(self):
        self.subscribers: List[asyncio.Queue] = []

        # 板情報の内部状態: {(deliveryDate, timeCd): [bid/ask items]}
        self.board_state: Dict[tuple, List[dict]] = {}

        self._initialize_board()

    def _initialize_board(self):
        """当日・翌日のボードを初期化"""
        today    = date.today()
        tomorrow = today + timedelta(days=1)

        for d in [today, tomorrow]:
            date_str = d.isoformat()
            for t in range(1, 49):
                time_cd = f"{t:02d}"
                tc_int  = t
                bids = []
                for _ in range(random.randint(1, 3)):
                    buy_sell = random.choice(["BUY", "SELL"])
                    price    = _random_price(time_cd=tc_int)
                    # 売買によって少し価格をずらし、スプレッドを模擬
                    if buy_sell == "BUY":
                        price = max(10, price - random.randint(0, 20))
                    bids.append({
                        "noticeTypeCd": "BID-BOARD",
                        "timestamp":    datetime.now().isoformat(),
                        "deliveryDate": date_str,
                        "timeCd":       time_cd,
                        "areaGroupCd":  str(random.randint(1, 9)),
                        "buySellCd":    buy_sell,
                        "price":        price,
                        "volume":       round(random.uniform(10.0, 100.0), 1),
                    })
                self.board_state[(date_str, time_cd)] = bids

    def _is_expired(self, delivery_date: str, time_cd: str, now: datetime) -> bool:
        """スロットの期限切れ判定"""
        try:
            d     = datetime.strptime(delivery_date, "%Y-%m-%d").date()
            t_idx = int(time_cd)
            hours   = (t_idx - 1) // 2
            minutes = 30 if (t_idx - 1) % 2 == 0 else 0
            slot_end = datetime.combine(d, datetime.min.time()).replace(
                hour=hours, minute=minutes + 30 if minutes == 0 else 0)
            if minutes == 30:
                slot_end = datetime.combine(d, datetime.min.time()).replace(
                    hour=hours + 1, minute=0)
            if t_idx == 48:
                slot_end = datetime.combine(d + timedelta(days=1), datetime.min.time())
            return now >= slot_end
        except Exception:
            return True

    def _purge_expired_data(self):
        """期限切れスロットを削除"""
        now         = datetime.now()
        expired     = [k for k in self.board_state if self._is_expired(k[0], k[1], now)]
        for key in expired:
            del self.board_state[key]
        if expired:
            print(f"[ITN Engine] Purged {len(expired)} expired slots. Remaining: {len(self.board_state)}")
        # 翌日データがなければ再初期化
        tomorrow = (now.date() + timedelta(days=1)).isoformat()
        if not any(k[0] == tomorrow for k in self.board_state):
            self._initialize_board()

    def get_full_state(self) -> dict:
        """全量配信用のフルステートを返す"""
        self._purge_expired_data()
        all_notices = []
        for bids in self.board_state.values():
            all_notices.extend(bids)
        return {
            "status":     "200",
            "statusInfo": "",
            "notices":    all_notices,
        }

    def subscribe(self) -> asyncio.Queue:
        queue = asyncio.Queue()
        self.subscribers.append(queue)
        print(f"[ITN Engine] New subscriber. Total: {len(self.subscribers)}")
        return queue

    def unsubscribe(self, queue: asyncio.Queue):
        if queue in self.subscribers:
            self.subscribers.remove(queue)
            print(f"[ITN Engine] Subscriber removed. Total: {len(self.subscribers)}")

    def push_contract_notice(self, delivery_date: str, time_cd: str,
                             contract_price: float, contract_volume: float):
        """ITD約定発生時に CONTRACT 通知を全購読者へプッシュ（同期的に呼び出し可能）"""
        now = datetime.now()
        notice = {
            "noticeTypeCd":   "CONTRACT",
            "bidNo":          f"CN{now.strftime('%Y%m%d%H%M%S%f')}",
            "timestamp":      now.strftime("%Y-%m-%dT%H:%M:%S.") +
                              f"{now.microsecond // 1000:03d}",
            "deliveryDate":   delivery_date,
            "timeCd":         time_cd,
            "contractPrice":  contract_price,
            "contractVolume": contract_volume,
        }
        packet = {
            "status":     "200",
            "statusInfo": "",
            "notices":    [notice],
        }
        if self.subscribers:
            print(f"[ITN Engine] Broadcasting CONTRACT notice for {delivery_date} tc={time_cd} "
                  f"price={contract_price} vol={contract_volume} "
                  f"to {len(self.subscribers)} subscribers.")
            for queue in self.subscribers:
                try:
                    queue.put_nowait(packet)
                except asyncio.QueueFull:
                    pass

    async def run_engine(self):
        """バックグラウンドエンジン: 定期的に差分配信を生成してプッシュ"""
        print(f"[ITN Engine] Started. Push interval: {ITN_PUSH_INTERVAL_SEC}s")
        diff_count = 1

        while True:
            await asyncio.sleep(ITN_PUSH_INTERVAL_SEC)
            self._purge_expired_data()

            active_keys = list(self.board_state.keys())
            if not active_keys:
                self._initialize_board()
                active_keys = list(self.board_state.keys())

            target_date, target_time = random.choice(active_keys)
            tc_int   = int(target_time)
            now      = datetime.now()
            msg_type = random.choice(["CONTRACT", "BID-BOARD"])

            diff_item: dict = {
                "noticeTypeCd": msg_type,
                "timestamp":    now.strftime("%Y-%m-%dT%H:%M:%S.") +
                                f"{now.microsecond // 1000:03d}",
                "deliveryDate": target_date,
                "timeCd":       target_time,
            }

            if msg_type == "CONTRACT":
                # 直近の板情報から合理的な価格帯を参照
                board_items = self.board_state.get((target_date, target_time), [])
                if board_items:
                    ref_price = float(board_items[-1].get('price', 0))
                    # 約定価格は板価格付近 (±10%)
                    diff_item["contractPrice"]  = max(10, round(
                        ref_price * random.uniform(0.9, 1.1) / 10) * 10)
                else:
                    diff_item["contractPrice"]  = _random_price(time_cd=tc_int)
                diff_item["contractVolume"] = round(random.uniform(5.0, 50.0), 1)
                diff_item["bidNo"] = f"CN{now.strftime('%Y%m%d%H%M%S%f')}"
            else:
                # 板情報更新: 前回価格からランダムウォーク
                board_items = self.board_state.get((target_date, target_time), [])
                if board_items:
                    ref_price = float(board_items[-1].get('price', 100))
                    # 価格は ±20 円/MWh 変動（10の倍数）
                    delta = random.choice([-20, -10, 0, 10, 20])
                    new_price = max(10, ref_price + delta)
                else:
                    new_price = _random_price(time_cd=tc_int)
                buy_sell = random.choice(["BUY", "SELL"])
                # 売買スプレッドを模擬
                if buy_sell == "BUY":
                    new_price = max(10, new_price - random.randint(0, 20))
                diff_item["areaGroupCd"] = str(random.randint(1, 9))
                diff_item["buySellCd"]   = buy_sell
                diff_item["price"]       = new_price
                diff_item["volume"]      = round(random.uniform(-30.0, 30.0), 1)  # 差分量(負=減少)
                # 内部板情報を更新
                self.board_state[(target_date, target_time)].append(diff_item)

            diff_packet = {
                "status":     "200",
                "statusInfo": "",
                "notices":    [diff_item],
            }

            if self.subscribers:
                print(f"[ITN Engine] Diff #{diff_count} ({msg_type}) "
                      f"→ {len(self.subscribers)} subscribers.")
                for queue in self.subscribers:
                    try:
                        queue.put_nowait(diff_packet)
                    except asyncio.QueueFull:
                        pass
            else:
                print(f"[ITN Engine] Market tick #{diff_count} ({msg_type}). "
                      f"Active slots: {len(self.board_state)}")

            diff_count += 1


itn_engine = ITNMarketEngine()

