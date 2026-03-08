import asyncio
import random
from datetime import datetime, date, timedelta
from typing import List, Dict

from config import ITN_PUSH_INTERVAL_SEC

class ITNMarketEngine:
    def __init__(self):
        self.subscribers: List[asyncio.Queue] = []
        
        # Internal state grouped by (deliveryDate, timeCd)
        # Format: {(deliveryDate, timeCd): [list of bid/ask items]}
        self.board_state: Dict[tuple[str, str], List[dict]] = {}
        
        self._initialize_board()

    def _initialize_board(self):
        """Initializes the board with dummy data for Today and Tomorrow."""
        today = date.today()
        tomorrow = today + timedelta(days=1)
        
        for d in [today, tomorrow]:
            date_str = d.isoformat()
            for t in range(1, 49):
                time_cd = str(t).zfill(2)
                # Generate 1-3 dummy bids per timeslot
                bids = []
                for _ in range(random.randint(1, 3)):
                    bids.append({
                        "noticeTypeCd": "BID-BOARD",
                        "timestamp": datetime.now().isoformat(),
                        "deliveryDate": date_str,
                        "timeCd": time_cd,
                        "areaGroupCd": str(random.randint(1, 9)),
                        "buySellCd": random.choice(["BUY", "SELL"]),
                        "price": round(random.uniform(5.0, 25.0), 1),
                        "volume": round(random.uniform(10.0, 50.0), 1)
                    })
                self.board_state[(date_str, time_cd)] = bids

    def _is_expired(self, delivery_date: str, time_cd: str, now: datetime) -> bool:
        """Determines if a timeslot has passed."""
        try:
            d = datetime.strptime(delivery_date, "%Y-%m-%d").date()
            t_idx = int(time_cd) # 1-48
            # timeCd 1 = 00:00~00:30, timeCd 48 = 23:30~24:00
            # A slot expires when its end time passes.
            hours = t_idx // 2
            minutes = 30 if t_idx % 2 != 0 else 0
            if t_idx == 48:
                end_time = datetime.combine(d + timedelta(days=1), datetime.min.time())
            else:
                end_time = datetime.combine(d, datetime.min.time().replace(hour=hours, minute=minutes))
            
            return now >= end_time
        except Exception:
            return True # If parsing fails, consider it expired to purge

    def _purge_expired_data(self):
        """Removes data for time slots that have already passed."""
        now = datetime.now()
        expired_keys = []
        for (d_date, t_cd) in self.board_state.keys():
            if self._is_expired(d_date, t_cd, now):
                expired_keys.append((d_date, t_cd))
                
        for key in expired_keys:
            del self.board_state[key]
            
        if expired_keys:
            print(f"[ITN Engine] Purged {len(expired_keys)} expired time slots. Remaining active slots: {len(self.board_state)}")
            
        # Also ensure tomorrow's slots exist if we crossed midnight
        tomorrow = (now.date() + timedelta(days=1)).isoformat()
        if (tomorrow, "24") not in self.board_state:
             self._initialize_board() # Re-init will overwrite/append missing future slots smoothly in a real app; for mock, we just broadly ensure data exists.

    def get_full_state(self) -> dict:
        """Returns the current full market state formatted according to JEPX specifications."""
        self._purge_expired_data() # Guarantee clean state before sending
        
        all_notices = []
        for bids in self.board_state.values():
            all_notices.extend(bids)
            
        return {
            "status": "200",
            "statusInfo": "",
            "memo": "Mock: Current Full Market State",
            "notices": all_notices
        }

    def subscribe(self) -> asyncio.Queue:
        queue = asyncio.Queue()
        self.subscribers.append(queue)
        print(f"[ITN Engine] New subscriber added. Total: {len(self.subscribers)}")
        return queue

    def unsubscribe(self, queue: asyncio.Queue):
        if queue in self.subscribers:
            self.subscribers.remove(queue)
            print(f"[ITN Engine] Subscriber removed. Total: {len(self.subscribers)}")

    async def run_engine(self):
        print(f"[ITN Engine] Background engine started. Pushing every {ITN_PUSH_INTERVAL_SEC} seconds.")
        diff_count = 1
        
        while True:
            await asyncio.sleep(ITN_PUSH_INTERVAL_SEC)
            self._purge_expired_data() # Purge old data
            
            now = datetime.now()
            today_str = now.date().isoformat()
            
            # Find a valid future timecode to generate a diff for
            active_keys = list(self.board_state.keys())
            if not active_keys:
                 self._initialize_board()
                 active_keys = list(self.board_state.keys())
                 
            target_date, target_time = random.choice(active_keys)
            
            msg_type = random.choice(["CONTRACT", "BID-BOARD"])
            
            diff_item = {
                "noticeTypeCd": msg_type,
                "timestamp": now.isoformat(),
                "deliveryDate": target_date,
                "timeCd": target_time,
                "memo": f"Mock: Differential Delivery #{diff_count} from Engine"
            }
            if msg_type == "CONTRACT":
                diff_item["contractPrice"] = round(random.uniform(5.0, 25.0), 1)
                diff_item["contractVolume"] = round(random.uniform(1.0, 20.0), 1)
            else:
                diff_item["areaGroupCd"] = str(random.randint(1, 9))
                diff_item["buySellCd"] = random.choice(["BUY", "SELL"])
                diff_item["price"] = round(random.uniform(5.0, 25.0), 1)
                diff_item["volume"] = round(random.uniform(-10.0, 10.0), 1) # Differential can be negative

            diff_packet = {
                 "status": "200",
                 "statusInfo": "",
                 "memo": f"Mock: Differential Delivery #{diff_count} from Engine",
                 "notices": [diff_item]
            }

            # Update our internal state
            if msg_type == "BID-BOARD":
                 self.board_state[(target_date, target_time)].append(diff_item)

            if self.subscribers:
                print(f"[ITN Engine] Broadcasting Differential #{diff_count} ({msg_type}) to {len(self.subscribers)} subscribers.")
                for queue in self.subscribers:
                    try:
                        queue.put_nowait(diff_packet)
                    except asyncio.QueueFull:
                        pass
            else:
                 print(f"[ITN Engine] Market Updated #{diff_count} (No subscribers). Active slots: {len(self.board_state)}")
                
            diff_count += 1

itn_engine = ITNMarketEngine()
