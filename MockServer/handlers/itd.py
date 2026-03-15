from core.state import state, BidStatus
from datetime import date, datetime, timedelta
import random


# --------------------------------------------------------------------------
# バリデーション
# --------------------------------------------------------------------------
_VALID_BID_TYPES_ITD = {'SELL-LIMIT', 'BUY-LIMIT', 'SELL-MARKET', 'BUY-MARKET'}

def _validate_itd_bid(bid: dict) -> str | None:
    """ITD入札のバリデーション。エラーコードまたは None を返す。"""
    for field in ('deliveryDate', 'timeCd', 'areaCd', 'bidTypeCd', 'volume', 'deliveryContractCd'):
        if bid.get(field) is None:
            return "E001"

    time_cd = bid.get('timeCd', '')
    try:
        tc = int(time_cd)
        if not (1 <= tc <= 48):
            return "E002"
    except (ValueError, TypeError):
        return "E002"

    bid_type = bid.get('bidTypeCd', '')
    if bid_type not in _VALID_BID_TYPES_ITD:
        return "E002"

    try:
        vol = float(bid.get('volume'))
        if vol <= 0:
            return "E002"
    except (ValueError, TypeError):
        return "E002"

    if 'LIMIT' in bid_type:
        price = bid.get('price')
        if price is None:
            return "E001"
        try:
            p = float(price)
            if p <= 0 or p > 9990:
                return "E002"
            if int(p) % 10 != 0:
                return "E003"
        except (ValueError, TypeError):
            return "E002"

    return None


# --------------------------------------------------------------------------
# 時間前市場 API ハンドラ
# --------------------------------------------------------------------------

def handle_itd1001(body: dict) -> dict:
    """ITD1001: 時間前市場 入札
    JEPX仕様903 §2.1: 入板後に即時マッチングを試み, 約定時は ITN へ通知する"""
    err = _validate_itd_bid(body)
    if err:
        return {"status": "400", "statusInfo": err, "bidNo": ""}

    bid_no = state.add_bid("ITD", body)

    # 即時マッチングを試みる
    contract = state.try_itd_matching(bid_no)

    # 約定した場合は ITN 配信エンジンへ通知
    if contract:
        try:
            from core.itn_engine import itn_engine
            itn_engine.push_contract_notice(
                delivery_date=contract['deliveryDate'],
                time_cd=contract['timeCd'],
                contract_price=contract['contractPrice'],
                contract_volume=contract['contractVolume'],
            )
            # 約定後の板状態をBID-BOARDとして通知 → 取引ボードが即時更新される
            itn_engine.push_board_update_for_contract(
                delivery_date=contract['deliveryDate'],
                time_cd=contract['timeCd'],
            )
        except Exception:
            pass  # ITN 通知失敗は入札レスポンスに影響させない

    return {"status": "200", "statusInfo": "1", "bidNo": bid_no}


def handle_itd1002(body: dict) -> dict:
    """ITD1002: 時間前市場 入札削除要求
    JEPX仕様903 §2.2: 削除要求自体が新たな入札(bidTypeCd=DEL)として登録される"""
    delivery_date = body.get("deliveryDate", "")
    time_cd       = body.get("timeCd", "")
    target_bid_no = body.get("targetBidNo", "")

    if not target_bid_no:
        return {"status": "400", "statusInfo": "E001", "bidNo": ""}

    # 対象入札の存在確認
    target_bid = next(
        (b for b in state.bids.get("ITD", []) if b.get('bidNo') == target_bid_no), None)
    if not target_bid:
        return {"status": "400", "statusInfo": "E004", "bidNo": ""}  # 入札番号不存在
    if target_bid.get('_status') == BidStatus.CONTRACTED:
        return {"status": "400", "statusInfo": "E005", "bidNo": ""}  # 約定済みは削除不可

    delete_bid_no = state.add_delete_request("ITD", delivery_date, time_cd, target_bid_no)
    return {"status": "200", "statusInfo": "1", "bidNo": delete_bid_no}


def handle_itd1003(body: dict) -> dict:
    """ITD1003: 時間前市場 入札照会
    JEPX仕様903 §2.3: 削除要求入札を含む全入札を返却。
    timestamp / contractVolume / targetBidNo / deleteCd フィールドを含む。"""
    delivery_date = body.get("deliveryDate", "")
    time_cd       = body.get("timeCd", "")

    raw_bids = state.get_bids("ITD", delivery_date)
    if time_cd:
        raw_bids = [b for b in raw_bids if b.get('timeCd') == time_cd]

    bids = []
    for b in raw_bids:
        bids.append({
            "bidNo":              b.get("bidNo", ""),
            "timestamp":          b.get("timestamp", ""),
            "deliveryDate":       b.get("deliveryDate", ""),
            "timeCd":             b.get("timeCd", ""),
            "areaCd":             b.get("areaCd"),
            "bidTypeCd":          b.get("bidTypeCd", ""),
            "price":              b.get("price"),
            "volume":             b.get("volume"),
            "deliveryContractCd": b.get("deliveryContractCd"),
            "note":               b.get("note"),
            "contractVolume":     b.get("_contractVolume"),
            "targetBidNo":        b.get("_targetBidNo"),
            "deleteCd":           b.get("_deleteCd", "0"),
        })

    return {"status": "200", "statusInfo": "", "bids": bids}


def handle_itd1004(body: dict) -> dict:
    """ITD1004: 時間前市場 約定照会
    JEPX仕様903 §2.4: contractResults[] に contractNo/timestamp/contractPrice/contractVolume を返却"""
    delivery_date = body.get("deliveryDate", "") or date.today().isoformat()
    time_cd       = body.get("timeCd", "")

    contract_results = state.get_itd_contracts(delivery_date, time_cd)

    # 約定がない場合はサンプルデータを返却
    if not contract_results:
        market_price = state.get_or_create_market_price(
            "ITD", delivery_date, time_cd or "24")
        now = datetime.now()
        contract_results = [{
            "contractNo":         "2500000001",
            "timestamp":          now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}",
            "bidNo":              "1500000001",
            "deliveryDate":       delivery_date,
            "timeCd":             time_cd or "24",
            "areaCd":             "1",
            "bidTypeCd":          "SELL-LIMIT",
            "deliveryContractCd": "SMPL01",
            "note":               "MockServer sample contract",
            "contractPrice":      market_price,
            "contractVolume":     50.0,
        }]

    return {"status": "200", "statusInfo": "", "contractResults": contract_results}


def handle_itd1005(body: dict) -> dict:
    """ITD1005: 商品照会
    JEPX仕様903 §2.5: 当日・翌日の全商品の取引中断コードを返却"""
    today   = date.today()
    tomorrow = today + timedelta(days=1)
    now     = datetime.now()
    # 現在の時間帯コード (1-48)
    current_tc = now.hour * 2 + (1 if now.minute >= 30 else 0) + 1

    products = []
    for d in [today, tomorrow]:
        date_str = d.isoformat()
        for tc in range(1, 49):
            tc_str = f"{tc:02d}"
            if d == today:
                if tc < current_tc:
                    suspend_cd = "3"   # 取引終了
                else:
                    # 5% の確率で取引中断（リアリティ演出）
                    suspend_cd = "1" if random.random() < 0.05 else "0"
            else:
                suspend_cd = "1" if random.random() < 0.03 else "0"

            products.append({
                "deliveryDate": date_str,
                "timeCd":       tc_str,
                "suspendCd":    suspend_cd,
            })

    return {"status": "200", "statusInfo": "", "products": products}


def handle_itd9001(body: dict) -> dict:
    """ITD9001: 時間前市場 清算照会
    JEPX仕様903 §3.1: 約定から売買代金・手数料・消費税を算出して返却"""
    from_date = body.get("fromDate", date.today().isoformat())

    itd_contracts  = state.get_itd_contracts(from_date)
    total_volume   = sum(float(c.get('contractVolume', 0)) for c in itd_contracts)
    buy_contracts  = [c for c in itd_contracts if 'BUY'  in c.get('bidTypeCd', '')]
    sell_contracts = [c for c in itd_contracts if 'SELL' in c.get('bidTypeCd', '')]
    buy_amount     = sum(float(c.get('contractPrice', 0)) * float(c.get('contractVolume', 0))
                         for c in buy_contracts)
    sell_amount    = sum(float(c.get('contractPrice', 0)) * float(c.get('contractVolume', 0))
                         for c in sell_contracts)

    # 入札がない場合はサンプル数値
    if not itd_contracts:
        total_volume = 51422.45
        buy_amount   = 25171390.0
        sell_amount  = 0.0

    trading_fee_per_mwh = 100  # 時間前市場: 100 円/MWh
    fee     = round(total_volume * trading_fee_per_mwh)
    tax     = round(fee * 0.1)
    vol_str = f"{total_volume:,.2f}(MWh)"

    settlements = [
        {
            "settlementNo":   f"SI{abs(hash(from_date)) % 1000000000:09d}",
            "settlementDate": from_date,
            "title":          f"時間前取引売買手数料 {from_date} 約定分",
            "totalAmount":    -(fee + tax),
            "items": [
                {"name": "売買手数料",
                 "quantity": vol_str,
                 "unitPrice": f"{trading_fee_per_mwh}(円/MWh)",
                 "amount": -fee},
                {"name": f"消費税（10％対象 {fee:,} 円）",
                 "quantity": "", "unitPrice": "",
                 "amount": -tax},
            ],
            "pdf": "TW9ja1BERkRhdGE=",
        }
    ]

    if buy_amount > 0 or sell_amount > 0:
        buy_tax  = round(buy_amount  * 0.1)
        sell_tax = round(sell_amount * 0.1)
        settlements.append({
            "settlementNo":   f"SI{(abs(hash(from_date)) + 1) % 1000000000:09d}",
            "settlementDate": from_date,
            "title":          f"時間前取引売買代金 {from_date} 約定分",
            "totalAmount":    int(sell_amount + sell_tax - buy_amount - buy_tax),
            "items": [
                {"name": "売り代金（課税対象額）",
                 "quantity": "", "unitPrice": "", "amount": int(sell_amount)},
                {"name": f"売り代金消費税（10％対象 {int(sell_amount):,} 円）",
                 "quantity": "", "unitPrice": "", "amount": int(sell_tax)},
                {"name": "買い代金（課税対象額）",
                 "quantity": "", "unitPrice": "", "amount": -int(buy_amount)},
                {"name": f"買い代金消費税（10％対象 {int(buy_amount):,} 円）",
                 "quantity": "", "unitPrice": "", "amount": -int(buy_tax)},
            ],
            "pdf": "TW9ja1BERkRhdGE=",
        })

    return {"status": "200", "statusInfo": "", "settlements": settlements}

