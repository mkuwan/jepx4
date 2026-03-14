from core.state import state, BidStatus
from datetime import date


# --------------------------------------------------------------------------
# バリデーション
# --------------------------------------------------------------------------
_VALID_BID_TYPES_DAH = {
    'SELL-LIMIT', 'BUY-LIMIT', 'SELL-MARKET', 'BUY-MARKET',
    'SELL-FIT', 'SELL-FIT-MARKET', 'BUY-APPROVED', 'BUY-APPROVED-MARKET',
}

def _validate_dah_bid(bid: dict) -> str | None:
    """単一DAH入札のバリデーション。エラーコードまたは None を返す。"""
    for field in ('deliveryDate', 'areaCd', 'timeCd', 'bidTypeCd', 'volume', 'deliveryContractCd'):
        if bid.get(field) is None:
            return "E001"  # 必須項目不足

    time_cd = bid.get('timeCd', '')
    try:
        tc = int(time_cd)
        if not (1 <= tc <= 48):
            return "E002"
    except (ValueError, TypeError):
        return "E002"

    bid_type = bid.get('bidTypeCd', '')
    if bid_type not in _VALID_BID_TYPES_DAH:
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
                return "E003"  # 10の倍数でない
        except (ValueError, TypeError):
            return "E002"

    return None


# --------------------------------------------------------------------------
# 翌日市場 API ハンドラ
# --------------------------------------------------------------------------

def handle_dah1001(body: dict) -> dict:
    """DAH1001: 翌日市場 入札
    JEPX仕様902 §2.1: status/statusInfo(入札件数) を返却"""
    bids = body.get("bidOffers", [])
    if not bids:
        return {"status": "400", "statusInfo": "E001"}

    for bid in bids:
        err = _validate_dah_bid(bid)
        if err:
            return {"status": "400", "statusInfo": err}

    for bid in bids:
        state.add_bid("DAH", bid)

    return {"status": "200", "statusInfo": str(len(bids))}


def handle_dah1002(body: dict) -> dict:
    """DAH1002: 翌日市場 入札照会
    JEPX仕様902 §2.2: bids[] 配列で返却"""
    delivery_date = body.get("deliveryDate", "")
    raw_bids = state.get_bids("DAH", delivery_date)

    bids = []
    for b in raw_bids:
        if b.get('bidTypeCd') == 'DEL':
            continue
        bids.append({
            "bidNo":              b.get("bidNo", ""),
            "deliveryDate":       b.get("deliveryDate", ""),
            "areaCd":             b.get("areaCd", ""),
            "timeCd":             b.get("timeCd", ""),
            "bidTypeCd":          b.get("bidTypeCd", ""),
            "price":              b.get("price"),
            "volume":             b.get("volume", 0),
            "deliveryContractCd": b.get("deliveryContractCd", ""),
            "note":               b.get("note", ""),
        })

    return {"status": "200", "statusInfo": "", "bids": bids}


def handle_dah1003(body: dict) -> dict:
    """DAH1003: 翌日市場 入札削除
    JEPX仕様902 §2.3: statusInfo(削除件数) を返却"""
    delivery_date = body.get("deliveryDate", "")
    bid_dels      = body.get("bidDels", [])

    deleted_count = 0
    if bid_dels:
        for bid_del in bid_dels:
            bid_no = bid_del.get("bidNo", "")
            if state.delete_bid("DAH", bid_no):
                deleted_count += 1
    else:
        deleted_count = state.delete_bids_by_date("DAH", delivery_date)

    return {"status": "200", "statusInfo": str(deleted_count)}


def handle_dah1004(body: dict) -> dict:
    """DAH1004: 翌日市場 約定照会
    JEPX仕様902 §2.4: bidResults[] に contractPrice/contractVolume を付加して返却。
    未登録の入札に対しても SMP(システム清算価格)で約定シミュレーションを実行する。"""
    delivery_date = body.get("deliveryDate", "") or date.today().isoformat()

    # PENDING 入札を約定シミュレーション（すでに処理済みのものはスキップ）
    state.simulate_dah_contracts(delivery_date)

    bid_results = state.get_dah_bid_results(delivery_date)

    # 入札が一件もない場合はサンプルデータを返却
    if not bid_results:
        market_price = state.get_or_create_market_price("DAH", delivery_date, "24")
        bid_results = [{
            "bidNo":              "1500000001",
            "deliveryDate":       delivery_date,
            "areaCd":             "1",
            "timeCd":             "24",
            "bidTypeCd":          "SELL-LIMIT",
            "price":              round(market_price * 0.9 / 10) * 10,
            "volume":             100.0,
            "deliveryContractCd": "SMPL01",
            "note":               "MockServer sample bid",
            "contractPrice":      market_price,
            "contractVolume":     100.0,
        }]

    return {"status": "200", "statusInfo": "", "bidResults": bid_results}


def handle_dah9001(body: dict) -> dict:
    """DAH9001: 翌日市場 清算照会
    JEPX仕様902 §3.1: 約定データから売買代金・手数料・消費税を算出して返却"""
    from_date = body.get("fromDate", date.today().isoformat())

    dah_contracts   = state.get_dah_contracts(from_date)
    total_volume    = sum(c.get('contractVolume', 0) for c in dah_contracts)
    buy_contracts   = [c for c in dah_contracts if 'BUY' in c.get('bidTypeCd', '')]
    sell_contracts  = [c for c in dah_contracts if 'SELL' in c.get('bidTypeCd', '')]
    buy_amount      = sum(float(c.get('contractPrice', 0)) * float(c.get('contractVolume', 0))
                          for c in buy_contracts)
    sell_amount     = sum(float(c.get('contractPrice', 0)) * float(c.get('contractVolume', 0))
                          for c in sell_contracts)

    # 入札がない場合はサンプル数値
    if not dah_contracts:
        total_volume = 5000.0
        buy_amount   = 0.0
        sell_amount  = 500000.0

    trading_fee_per_mwh = 30  # 翌日市場: 30 円/MWh
    fee = round(total_volume * trading_fee_per_mwh)
    tax = round(fee * 0.1)
    vol_str = f"{total_volume:,.2f}(MWh)"

    settlements = [
        {
            "settlementNo":   f"SD{abs(hash(from_date)) % 1000000000:09d}",
            "settlementDate": from_date,
            "title":          f"翌日取引売買手数料 {from_date} 受渡分",
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
            "settlementNo":   f"SD{(abs(hash(from_date)) + 1) % 1000000000:09d}",
            "settlementDate": from_date,
            "title":          f"翌日取引売買代金 {from_date} 受渡分",
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

