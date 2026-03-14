# In-memory storage for MockServer
# JEPX仕様書に準拠: 入札番号(bidNo)は10桁の数字文字列
import random
from datetime import datetime


class BidStatus:
    """入札ステータス定数"""
    PENDING    = "PENDING"     # 受付済み（約定待ち）
    CONTRACTED = "CONTRACTED"  # 約定済み
    CANCELLED  = "CANCELLED"   # 取消済み


class MockState:
    def __init__(self):
        # bids[market] = [bid_dict, ...]  ※削除要求入札も同リストに保管
        self.bids = {"DAH": [], "ITD": []}
        # contracts[market][delivery_date] = [contract_dict, ...]
        self.contracts = {"DAH": {}, "ITD": {}}

        self._bid_counter      = random.randint(1000000000, 1999999999)
        self._contract_counter = random.randint(2000000000, 2999999999)
        # 市場清算価格キャッシュ: (market, deliveryDate, timeCd) -> price
        self._market_prices: dict = {}

    # ------------------------------------------------------------------
    # 採番
    # ------------------------------------------------------------------
    def _next_bid_no(self) -> str:
        """JEPX仕様に準拠した10桁の入札番号を生成"""
        self._bid_counter += 1
        return str(self._bid_counter)

    def _next_contract_no(self) -> str:
        """約定番号(contractNo)を生成"""
        self._contract_counter += 1
        return str(self._contract_counter)

    # ------------------------------------------------------------------
    # 市場価格シミュレーション
    # ------------------------------------------------------------------
    def get_or_create_market_price(self, market: str, delivery_date: str, time_cd: str) -> float:
        """指定スロットのシミュレーション市場清算価格を返す（ない場合は生成）。
        価格単位は 円/MWh、10の倍数。
        """
        key = (market, delivery_date, time_cd)
        if key not in self._market_prices:
            try:
                tc = int(time_cd)
            except (ValueError, TypeError):
                tc = 24
            # 時間帯別基準価格（JEPXの一般的な価格帯: 50-300 円/MWh、10の倍数）
            base = random.uniform(80.0, 200.0)
            if 14 <= tc <= 18:    # 朝ピーク (7:00–9:00)
                base *= random.uniform(1.3, 2.5)
            elif 36 <= tc <= 42:  # 夕方ピーク (18:00–21:00)
                base *= random.uniform(1.2, 2.0)
            elif 1 <= tc <= 6:    # 深夜帯 (0:00–3:00)
                base *= random.uniform(0.4, 0.7)
            self._market_prices[key] = round(base / 10) * 10
        return self._market_prices[key]

    # ------------------------------------------------------------------
    # 入札追加・照会・削除
    # ------------------------------------------------------------------
    def add_bid(self, market: str, bid_data: dict) -> str:
        """入札を追加し、JEPX仕様準拠の入札番号(bidNo)を返却"""
        bid_no = self._next_bid_no()
        now    = datetime.now()
        entry  = dict(bid_data)
        entry['bidNo']            = bid_no
        entry['_status']          = BidStatus.PENDING
        entry['timestamp']        = now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}"
        entry['_contractVolume']  = 0.0
        entry['_deleteCd']        = "0"
        entry['_targetBidNo']     = None
        self.bids[market].append(entry)
        return bid_no

    def add_delete_request(self, market: str, delivery_date: str, time_cd: str,
                           target_bid_no: str) -> str:
        """ITD削除要求入札を新規登録し、対象入札をCANCELLED状態にする。
        JEPX仕様903 §2.2: 削除要求自体が入札番号を持つ入札(bidTypeCd=DEL)として登録される。
        """
        delete_bid_no = self._next_bid_no()
        now = datetime.now()
        delete_entry = {
            'bidNo':              delete_bid_no,
            'timestamp':          now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}",
            'deliveryDate':       delivery_date,
            'timeCd':             time_cd,
            'areaCd':             None,
            'bidTypeCd':          'DEL',
            'price':              None,
            'volume':             None,
            'deliveryContractCd': None,
            'note':               None,
            '_status':            'DELETE',
            '_contractVolume':    None,
            '_deleteCd':          '1',
            '_targetBidNo':       target_bid_no,
        }
        self.bids[market].append(delete_entry)
        # 対象入札をキャンセル状態に更新
        self.delete_bid(market, target_bid_no)
        return delete_bid_no

    def get_bids(self, market: str, delivery_date: str = "") -> list:
        """指定された市場・受渡日の入札を取得"""
        market_bids = self.bids.get(market, [])
        if delivery_date:
            return [b for b in market_bids if b.get('deliveryDate') == delivery_date]
        return list(market_bids)

    def delete_bid(self, market: str, bid_no: str) -> bool:
        """入札番号(bidNo)で入札をCANCELLED状態に更新（約定済みは不可）"""
        for bid in self.bids.get(market, []):
            if bid.get('bidNo') == bid_no:
                if bid.get('_status') == BidStatus.CONTRACTED:
                    return False  # 約定済みはキャンセル不可
                bid['_status']    = BidStatus.CANCELLED
                bid['_deleteCd']  = '1'
                return True
        return False  # 入札が見つからない

    def delete_bids_by_date(self, market: str, delivery_date: str) -> int:
        """受渡日に該当する全PENDING入札をキャンセルし、件数を返却"""
        count = 0
        for bid in self.bids.get(market, []):
            if (bid.get('deliveryDate') == delivery_date
                    and bid.get('_status') == BidStatus.PENDING
                    and bid.get('bidTypeCd') != 'DEL'):
                bid['_status']   = BidStatus.CANCELLED
                bid['_deleteCd'] = '1'
                count += 1
        return count

    # ------------------------------------------------------------------
    # DAH オークション約定シミュレーション
    # ------------------------------------------------------------------
    def simulate_dah_contracts(self, delivery_date: str) -> list:
        """DAH統一価格オークションをシミュレート。
        SELL-LIMIT:  入札価格 ≦ SMP → 約定
        BUY-LIMIT:   入札価格 ≧ SMP → 約定
        *-MARKET:    常に約定
        """
        bids = [b for b in self.bids.get("DAH", [])
                if b.get('deliveryDate') == delivery_date
                and b.get('_status') == BidStatus.PENDING
                and b.get('bidTypeCd') != 'DEL']

        new_contracts = []
        for bid in bids:
            time_cd      = bid.get('timeCd', '01')
            market_price = self.get_or_create_market_price("DAH", delivery_date, time_cd)
            bid_type     = bid.get('bidTypeCd', '')
            bid_price    = float(bid.get('price') or 0)
            volume       = float(bid.get('volume') or 0)

            contract_volume = 0.0
            if 'MARKET' in bid_type:
                contract_volume = volume               # 成行: 必ず全量約定
            elif 'SELL-LIMIT' in bid_type:
                if bid_price <= market_price:
                    contract_volume = volume           # 売り指値: 清算価格以下 → 約定
            elif 'BUY-LIMIT' in bid_type:
                if bid_price >= market_price:
                    contract_volume = volume           # 買い指値: 清算価格以上 → 約定

            bid['_contractVolume'] = contract_volume
            if contract_volume > 0:
                bid['_status'] = BidStatus.CONTRACTED
                now = datetime.now()
                contract = {
                    'contractNo':         self._next_contract_no(),
                    'timestamp':          now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}",
                    'bidNo':              bid['bidNo'],
                    'deliveryDate':       delivery_date,
                    'areaCd':             bid.get('areaCd', ''),
                    'timeCd':             time_cd,
                    'bidTypeCd':          bid_type,
                    'price':              bid.get('price'),
                    'volume':             volume,
                    'deliveryContractCd': bid.get('deliveryContractCd', ''),
                    'note':               bid.get('note', ''),
                    'contractPrice':      market_price,
                    'contractVolume':     contract_volume,
                }
                if delivery_date not in self.contracts["DAH"]:
                    self.contracts["DAH"][delivery_date] = []
                self.contracts["DAH"][delivery_date].append(contract)
                new_contracts.append(contract)

        return new_contracts

    def get_dah_contracts(self, delivery_date: str) -> list:
        """指定受渡日のDAH約定リストを返却"""
        return self.contracts.get("DAH", {}).get(delivery_date, [])

    def get_dah_bid_results(self, delivery_date: str) -> list:
        """DAH1004用: 全入札の約定結果（contractVolume=0 を含む）を返却"""
        results = []
        for b in self.get_bids("DAH", delivery_date):
            if b.get('bidTypeCd') == 'DEL':
                continue
            contract_volume = float(b.get('_contractVolume') or 0)
            contract_price  = None
            if contract_volume > 0:
                contract_price = self.get_or_create_market_price(
                    "DAH", delivery_date, b.get('timeCd', '01'))
            results.append({
                'bidNo':              b.get('bidNo', ''),
                'deliveryDate':       b.get('deliveryDate', ''),
                'areaCd':             b.get('areaCd', ''),
                'timeCd':             b.get('timeCd', ''),
                'bidTypeCd':          b.get('bidTypeCd', ''),
                'price':              b.get('price'),
                'volume':             b.get('volume', 0),
                'deliveryContractCd': b.get('deliveryContractCd', ''),
                'note':               b.get('note', ''),
                'contractPrice':      contract_price,
                'contractVolume':     contract_volume,
            })
        return results

    # ------------------------------------------------------------------
    # ITD 連続オークション約定シミュレーション
    # ------------------------------------------------------------------
    def try_itd_matching(self, new_bid_no: str) -> dict | None:
        """ITD連続オークション: 新規入札の即時マッチングを試みる。
        マッチ成功時は約定レコードを返す。失敗時は None。
        """
        new_bid = next(
            (b for b in self.bids.get("ITD", []) if b.get('bidNo') == new_bid_no), None)
        if not new_bid or new_bid.get('bidTypeCd') == 'DEL':
            return None

        delivery_date = new_bid.get('deliveryDate', '')
        time_cd       = new_bid.get('timeCd', '')
        bid_type      = new_bid.get('bidTypeCd', '')
        bid_price     = float(new_bid.get('price') or 0)
        bid_volume    = float(new_bid.get('volume') or 0)

        # ---- 対向入札を検索 ----
        opposing: list = []
        if 'SELL' in bid_type:
            candidates = [b for b in self.bids.get("ITD", [])
                          if b.get('deliveryDate') == delivery_date
                          and b.get('timeCd') == time_cd
                          and 'BUY' in b.get('bidTypeCd', '')
                          and b.get('_status') == BidStatus.PENDING
                          and b.get('bidNo') != new_bid_no]
            opposing = candidates if 'MARKET' in bid_type else \
                [b for b in candidates if float(b.get('price') or 0) >= bid_price]
        elif 'BUY' in bid_type:
            candidates = [b for b in self.bids.get("ITD", [])
                          if b.get('deliveryDate') == delivery_date
                          and b.get('timeCd') == time_cd
                          and 'SELL' in b.get('bidTypeCd', '')
                          and b.get('_status') == BidStatus.PENDING
                          and b.get('bidNo') != new_bid_no]
            opposing = candidates if 'MARKET' in bid_type else \
                [b for b in candidates if float(b.get('price') or 0) <= bid_price]

        contract_price: float  = 0.0
        contract_volume: float = 0.0

        if opposing:
            # 価格・時間優先: 売り→最高買値、買い→最低売値
            best = (max(opposing, key=lambda b: float(b.get('price') or 0))
                    if 'SELL' in bid_type
                    else min(opposing, key=lambda b: float(b.get('price') or 0)))
            contract_price  = float(best.get('price') or bid_price)
            contract_volume = round(min(bid_volume, float(best.get('volume') or 0)), 1)
            # 双方を約定状態へ
            new_bid['_status']         = BidStatus.CONTRACTED
            new_bid['_contractVolume'] = contract_volume
            best['_status']            = BidStatus.CONTRACTED
            best['_contractVolume']    = contract_volume
        else:
            # 対向注文なし: 外部参加者との約定を35%確率でシミュレート
            if random.random() >= 0.35:
                return None
            contract_price = bid_price if bid_price > 0 else \
                self.get_or_create_market_price("ITD", delivery_date, time_cd)
            contract_volume = round(random.uniform(bid_volume * 0.3, bid_volume), 1)
            new_bid['_status']         = BidStatus.CONTRACTED
            new_bid['_contractVolume'] = contract_volume

        now = datetime.now()
        contract = {
            'contractNo':         self._next_contract_no(),
            'timestamp':          now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}",
            'bidNo':              new_bid_no,
            'deliveryDate':       delivery_date,
            'timeCd':             time_cd,
            'areaCd':             new_bid.get('areaCd', ''),
            'bidTypeCd':          bid_type,
            'deliveryContractCd': new_bid.get('deliveryContractCd', ''),
            'note':               new_bid.get('note', ''),
            'contractPrice':      contract_price,
            'contractVolume':     contract_volume,
        }
        if delivery_date not in self.contracts["ITD"]:
            self.contracts["ITD"][delivery_date] = []
        self.contracts["ITD"][delivery_date].append(contract)
        return contract

    def get_itd_contracts(self, delivery_date: str, time_cd: str = "") -> list:
        """指定受渡日・時間帯コードのITD約定リストを返却"""
        date_contracts = self.contracts.get("ITD", {}).get(delivery_date, [])
        if time_cd:
            return [c for c in date_contracts if c.get('timeCd') == time_cd]
        return date_contracts


# グローバルステートインスタンス
state = MockState()
