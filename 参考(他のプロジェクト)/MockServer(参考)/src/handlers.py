import random
from datetime import datetime, timedelta

def handle_request(api, body, **kwargs):
    if api == "DAH1001":
        return handle_dah1001(body)
    elif api == "DAH1002":
        return handle_dah1002(body)
    elif api == "DAH1003":  # Bid Deletion
        return handle_dah1003(body)
    elif api == "DAH1004":  # Contract Inquiry
        return handle_dah1004(body)
    elif api == "DAH1011":  # Block Bid Submission
        return handle_dah1011(body)
    elif api == "DAH1030":  # DAH All Contracts
        return handle_dah1030(body)
    elif api == "DAH9001":  # DAH Settlement
        return handle_dah9001(body)
    elif api == "ITD1001":  # Intraday Bid
        return handle_itd1001(body)
    elif api == "ITD1002":  # Intraday Bid Del
        return handle_itd1002(body)
    elif api == "ITD1003":  # Intraday Bid Inquiry
        return handle_itd1003(body)
    elif api == "ITD1004":  # Intraday Contract Inquiry
        return handle_itd1004(body)
    elif api == "ITN1001":  # Market info
        return handle_itn1001(body, is_initial=kwargs.get("is_initial", True))
    elif api == "SYS1001":  # Keep Alive
        return {"status": "200", "statusInfo": "Socket Expiration Time Extension"}
    else:
        return {"status": "500", "statusInfo": f"Unknown API: {api}"}

def _generate_bids(delivery_date, count):
    bids = []
    base_bid_no = 1000000000
    for i in range(count):
        bids.append({
            "bidNo": str(base_bid_no + i),
            "deliveryDate": delivery_date,
            "areaCd": str(random.randint(1, 9)),
            "timeCd": f"{random.randint(1, 48):02d}",
            "bidTypeCd": random.choice(["SELL-LIMIT", "BUY-LIMIT", "SELL-MARKET", "BUY-MARKET"]),
            "price": random.choice([0, 5, 10, 15, 20]) * 10,
            "volume": round(random.uniform(50.0, 5000.0), 1),
            "deliveryContractCd": f"CT{random.randint(1000, 9999)}",
            "note": f"Demo Data {i+1}"
        })
    return bids

def handle_dah1001(body):
    # Bid Submission
    bids = body.get("bidOffers", [])
    for b in bids:
        if b.get("volume", 0) <= 0:
            return {
                "status": "400",
                "statusInfo": "format",
                "errorDetails": [{"index": 0, "field": "volume", "errorCode": "range", "message": "Volume must be > 0"}]
            }
    count = len(bids)
    return {"status": "200", "statusInfo": str(count)}

def handle_dah1002(body):
    delivery_date = body.get("deliveryDate", (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"))
    return {"status": "200", "statusInfo": "", "bids": _generate_bids(delivery_date, 35)}

def handle_dah1003(body):
    bids = body.get("bidDels", [])
    count = len(bids) if bids else 1 
    return {"status": "200", "statusInfo": str(count)}

def handle_dah1004(body):
    delivery_date = body.get("deliveryDate", (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"))
    bids = _generate_bids(delivery_date, 35)
    for b in bids:
        if random.random() > 0.3:
            b["contractPrice"] = b.get("price", 100)
            b["contractVolume"] = round(b["volume"] * random.uniform(0.5, 1.0), 1)
        else:
            b["contractPrice"] = 0
            b["contractVolume"] = 0.0
    return {"status": "200", "statusInfo": "", "bidResults": bids}

def handle_dah1011(body):
    count = len(body.get("blockOffers", []))
    return {"status": "200", "statusInfo": str(count)}

def handle_dah1030(body):
    delivery_date = body.get("deliveryDate", (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"))
    results = []
    base_no = 2000000000
    for i in range(50):
        results.append({
            "deliveryDate": delivery_date,
            "areaCd": str(random.randint(1, 9)),
            "timeCd": f"{random.randint(1, 48):02d}",
            "price": random.choice([5, 10, 15, 20]) * 10,
            "volume": round(random.uniform(10.0, 1000.0), 1),
            "contractPrice": random.choice([5, 10, 15, 20]) * 10,
            "contractVolume": round(random.uniform(10.0, 1000.0), 1),
            "contractStatus": "ACCEPT",
        })
    return {"status": "200", "statusInfo": "", "contractResults": results}

def handle_dah9001(body):
    return {
        "status": "200",
        "statusInfo": "",
        "settlements": [
            {
                "settlementNo": f"S{datetime.now().strftime('%Y%m%d')}001",
                "settlementDate": datetime.now().strftime("%Y-%m-%d"),
                "marketType": "DAH",
                "totalAmount": 1500000.50,
                "details": [
                    {"deliveryDate": (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"), "amount": 1500000.50}
                ]
            }
        ]
    }

def handle_itd1001(body):
    return {"status": "200", "statusInfo": "1", "bidNo": str(random.randint(90000000, 99999999))}

def handle_itd1002(body):
    return {"status": "200", "statusInfo": "1", "bidNo": body.get("targetBidNo", "unknown")}

def handle_itd1003(body):
    delivery_date = body.get("deliveryDate", datetime.now().strftime("%Y-%m-%d"))
    bids = _generate_bids(delivery_date, 20)
    for b in bids:
        b["timestamp"] = datetime.now().isoformat()
        b["contractVolume"] = round(b["volume"] * 0.5, 1) if random.random() > 0.5 else 0.0
        b["deleteCd"] = "1" if random.random() > 0.8 else "0"
    return {"status": "200", "statusInfo": "", "bids": bids}

def handle_itd1004(body):
    delivery_date = body.get("deliveryDate", datetime.now().strftime("%Y-%m-%d"))
    results = []
    base_no = 3000000000
    for i in range(15):
        results.append({
            "contractNo": f"C{random.randint(100000, 999999)}",
            "timestamp": datetime.now().isoformat(),
            "bidNo": str(base_no + i),
            "deliveryDate": delivery_date,
            "timeCd": f"{random.randint(1, 48):02d}",
            "areaCd": str(random.randint(1, 9)),
            "bidTypeCd": random.choice(["SELL-LIMIT", "BUY-LIMIT"]),
            "deliveryContractCd": f"CT{random.randint(1000, 9999)}",
            "note": f"ITD Mock {i}",
            "contractPrice": random.choice([5, 10, 15, 20]) * 10,
            "contractVolume": round(random.uniform(10.0, 500.0), 1)
        })
    return {"status": "200", "statusInfo": "", "contractResults": results}

_mock_board_state = None

def _initialize_board():
    global _mock_board_state
    if _mock_board_state is None:
        _mock_board_state = []
        # Pre-seed items with valid noticeTypeCd
        for i in range(5):
            _mock_board_state.append({
                "noticeTypeCd": "CONTRACT",
                "deliveryDate": datetime.now().strftime("%Y-%m-%d"),
                "timeCd": f"{random.randint(1, 48):02d}",
                "areaCd": str(random.randint(1, 9)),
                "contractPrice": random.choice([10, 15, 20]) * 10,
                "contractVolume": round(random.uniform(50.0, 1000.0), 1),
                "noticeTime": datetime.now().isoformat() + "Z"
            })
        for i in range(5):
            _mock_board_state.append({
                "noticeTypeCd": "BID-BOARD",
                "areaGroupCd": f"A{random.choice([2, 4, 7, 9])}",
                "timeCd": f"{random.randint(1, 48):02d}",
                "areaCd": str(random.randint(1, 9)),
                "bidType": random.choice(["SELL", "BUY"]),
                "price": random.choice([10, 15, 20]) * 10,
                "volume": round(random.uniform(50.0, 1000.0), 1),
                "noticeTime": datetime.now().isoformat() + "Z"
            })

def handle_itn1001(body, is_initial=True):
    _initialize_board()
    
    if is_initial:
        # Full sync: send all 10 items
        return {"status": "200", "statusInfo": "", "notices": list(_mock_board_state)}
    else:
        # Delta sync: generate new events to simulate live market
        count = random.randint(1, 3)
        diffs = []
        for _ in range(count):
            if random.random() > 0.5:
                item = {
                    "noticeTypeCd": "CONTRACT",
                    "deliveryDate": datetime.now().strftime("%Y-%m-%d"),
                    "timeCd": f"{random.randint(1, 48):02d}",
                    "areaCd": str(random.randint(1, 9)),
                    "contractPrice": random.choice([10, 15, 20]) * 10,
                    "contractVolume": round(random.uniform(50.0, 1000.0), 1),
                    "noticeTime": datetime.now().isoformat() + "Z"
                }
            else:
                item = {
                    "noticeTypeCd": "BID-BOARD",
                    "areaGroupCd": f"A{random.choice([2, 4, 7, 9])}",
                    "timeCd": f"{random.randint(1, 48):02d}",
                    "areaCd": str(random.randint(1, 9)),
                    "bidType": random.choice(["SELL", "BUY"]),
                    "price": random.choice([10, 15, 20]) * 10,
                    "volume": round(random.uniform(50.0, 1000.0), 1),
                    "noticeTime": datetime.now().isoformat() + "Z"
                }
            diffs.append(item)
            
        return {"status": "200", "statusInfo": "", "notices": diffs}
