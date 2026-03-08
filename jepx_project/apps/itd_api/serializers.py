"""ITD API シリアライザ — リクエスト/レスポンスJSON変換 (§5.2)"""


def serialize_bid_response(jepx_body: dict) -> dict:
    """JEPX入札レスポンスをExcel向けレスポンスに変換する"""
    return {
        'success': jepx_body.get('status') == '200',
        'jepx_status': jepx_body.get('status', ''),
        'bid_no': jepx_body.get('bidNo', ''),
        'message': jepx_body.get('statusInfo', ''),
    }


def serialize_delete_response(jepx_body: dict) -> dict:
    """JEPX削除レスポンスをExcel向けレスポンスに変換する"""
    return {
        'success': jepx_body.get('status') == '200',
        'jepx_status': jepx_body.get('status', ''),
        'message': jepx_body.get('statusInfo', ''),
    }


def serialize_inquiry_response(jepx_body: dict) -> dict:
    """JEPX照会レスポンスをExcel向けレスポンスに変換する"""
    bids = jepx_body.get('bids', [])
    return {
        'success': True,
        'count': len(bids),
        'bids': bids,
    }


def serialize_contract_response(jepx_body: dict) -> dict:
    """JEPX約定照会レスポンスをExcel向けレスポンスに変換する"""
    results = jepx_body.get('contractResults', [])
    return {
        'success': True,
        'count': len(results),
        'contracts': results,
    }


def serialize_settlement_response(jepx_body: dict) -> dict:
    """JEPX清算照会レスポンスをExcel向けレスポンスに変換する"""
    settlements = jepx_body.get('settlements', [])
    return {
        'success': True,
        'count': len(settlements),
        'settlements': settlements,
    }


def serialize_error(error_code: str, message: str) -> dict:
    """エラーレスポンスを構築する"""
    return {
        'success': False,
        'error_code': error_code,
        'message': message,
    }
