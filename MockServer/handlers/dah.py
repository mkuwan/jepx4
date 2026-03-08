from core.state import state
import uuid
from datetime import date

def handle_dah1001(body: dict) -> dict:
    """DAH1001: 翌日市場 入札
    JEPX仕様902 2.1 準拠: status/statusInfo を返却"""
    bids = body.get("bidOffers", [])

    for bid in bids:
        state.add_bid("DAH", bid)

    # JEPX仕様: status="200", statusInfo=入札件数(文字列)
    return {
        "status": "200",
        "statusInfo": str(len(bids))
    }

def handle_dah1002(body: dict) -> dict:
    """DAH1002: 翌日市場 入札照会
    JEPX仕様902 2.2 準拠: bids[] 配列で返却"""
    delivery_date = body.get("deliveryDate", "")

    bids = state.get_bids("DAH", delivery_date)

    return {
        "status": "200",
        "statusInfo": "",
        "bids": bids
    }

def handle_dah1003(body: dict) -> dict:
    """DAH1003: 翌日市場 入札削除
    JEPX仕様902 2.3 準拠: deliveryDate + bidDels[].bidNo"""
    delivery_date = body.get("deliveryDate", "")
    bid_dels = body.get("bidDels", [])

    deleted_count = 0
    if bid_dels:
        # 個別のbidNo指定による削除
        for bid_del in bid_dels:
            bid_no = bid_del.get("bidNo", "")
            if state.delete_bid("DAH", bid_no):
                deleted_count += 1
    else:
        # bidDels未指定の場合は該当日の全入札を削除
        deleted_count = state.delete_bids_by_date("DAH", delivery_date)

    return {
        "status": "200",
        "statusInfo": str(deleted_count)
    }

def handle_dah1004(body: dict) -> dict:
    """DAH1004: 翌日市場 約定照会
    JEPX仕様902 2.4 準拠: bidResults[] + contractPrice/contractVolume"""
    delivery_date = body.get("deliveryDate", "")

    # 入札データを取得し、約定情報を付加してダミー応答
    bids = state.get_bids("DAH", delivery_date)
    bid_results = []
    for bid in bids:
        result = dict(bid)
        result["contractPrice"] = bid.get("price", 0)
        result["contractVolume"] = bid.get("volume", 0)
        bid_results.append(result)

    # 入札がない場合でもダミーの約定データを1件返却（テスト用）
    if not bid_results:
        bid_results.append({
            "bidNo": f"M{uuid.uuid4().hex[:9].upper()}",
            "deliveryDate": delivery_date or date.today().isoformat(),
            "areaCd": "1",
            "timeCd": "48",
            "bidTypeCd": "SELL-LIMIT",
            "price": 120,
            "volume": 100.0,
            "deliveryContractCd": "MOCK01",
            "note": "",
            "contractPrice": 120,
            "contractVolume": 100.0
        })

    return {
        "status": "200",
        "statusInfo": "",
        "bidResults": bid_results
    }

def handle_dah9001(body: dict) -> dict:
    """DAH9001: 翌日市場 清算照会
    JEPX仕様902 3.1 準拠: settlements[] 配列で返却（ダミーデータ）"""
    from_date = body.get("fromDate", date.today().isoformat())

    return {
        "status": "200",
        "statusInfo": "",
        "settlements": [
            {
                "settlementNo": "SD000000001",
                "settlementDate": from_date,
                "title": f"翌日取引売買手数料 {from_date} 受渡分",
                "totalAmount": -150000,
                "items": [
                    {"name": "売買手数料", "quantity": "5,000.00(MWh)", "unitPrice": "30(円/MWh)", "amount": -150000}
                ],
                "pdf": "TW9ja1BERkRhdGE="
            }
        ]
    }
