from core.state import state
import uuid
from datetime import date

def handle_itd1001(body: dict) -> dict:
    """ITD1001: 時間前市場 入札
    JEPX仕様903 2.1 準拠: status/statusInfo/bidNo を返却"""
    bid_no = state.add_bid("ITD", body)

    return {
        "status": "200",
        "statusInfo": "1",
        "bidNo": bid_no
    }

def handle_itd1002(body: dict) -> dict:
    """ITD1002: 時間前市場 入札削除要求
    JEPX仕様903 2.2 準拠: deliveryDate + timeCd + targetBidNo"""
    target_bid_no = body.get("targetBidNo", "")
    success = state.delete_bid("ITD", target_bid_no)

    return {
        "status": "200",
        "statusInfo": "1" if success else "0",
        "bidNo": state._next_bid_no() if success else ""
    }

def handle_itd1003(body: dict) -> dict:
    """ITD1003: 時間前市場 入札照会
    JEPX仕様903 2.3 準拠: bids[] 配列で返却"""
    delivery_date = body.get("deliveryDate", "")

    bids = state.get_bids("ITD", delivery_date)

    return {
        "status": "200",
        "statusInfo": "",
        "bids": bids
    }

def handle_itd1004(body: dict) -> dict:
    """ITD1004: 時間前市場 約定照会
    JEPX仕様903 2.4 準拠: bidResults[] + contractPrice/contractVolume"""
    delivery_date = body.get("deliveryDate", "")

    bids = state.get_bids("ITD", delivery_date)
    bid_results = []
    for bid in bids:
        result = dict(bid)
        result["contractPrice"] = bid.get("price", 0)
        result["contractVolume"] = bid.get("volume", 0)
        bid_results.append(result)

    if not bid_results:
        bid_results.append({
            "bidNo": f"M{uuid.uuid4().hex[:9].upper()}",
            "deliveryDate": delivery_date or date.today().isoformat(),
            "areaCd": "1",
            "timeCd": "24",
            "bidTypeCd": "SELL-LIMIT",
            "price": 10.5,
            "volume": 50.0,
            "deliveryContractCd": "MOCK01",
            "note": "",
            "contractPrice": 10.5,
            "contractVolume": 50.0
        })

    return {
        "status": "200",
        "statusInfo": "",
        "bidResults": bid_results
    }

def handle_itd9001(body: dict) -> dict:
    """ITD9001: 時間前市場 清算照会
    JEPX仕様903 3.1 準拠: settlements[] 配列で返却（ダミーデータ）"""
    from_date = body.get("fromDate", date.today().isoformat())

    return {
        "status": "200",
        "statusInfo": "",
        "settlements": [
            {
                "settlementNo": "SI000000001",
                "settlementDate": from_date,
                "title": f"時間前取引売買手数料 {from_date} 約定分",
                "totalAmount": -500000,
                "items": [
                    {"name": "売買手数料", "quantity": "5,000.00(MWh)", "unitPrice": "100(円/MWh)", "amount": -500000}
                ],
                "pdf": "TW9ja1BERkRhdGE="
            }
        ]
    }
