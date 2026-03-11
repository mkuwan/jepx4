"""ITD API シリアライザ — リクエスト/レスポンスJSON変換 (§5.2)"""


def serialize_bid_response(jepx_body: dict) -> dict:
    """JEPXからの入札完了レスポンスを、Excel VBA側がパースしやすいフラットなJSON形式に変換する。
    
    VBA側では 'success' フラグ(True/False)をチェックするだけで簡潔に成否判定・制御分岐が行えます。
    """
    return {
        'success': jepx_body.get('status') == '200',
        'jepx_status': jepx_body.get('status', ''),
        'bid_no': jepx_body.get('bidNo', ''),
        'message': jepx_body.get('statusInfo', ''),
    }


def serialize_delete_response(jepx_body: dict) -> dict:
    """JEPX削除レスポンスをExcel VBA向けに変換する(successフラグ付き)"""
    return {
        'success': jepx_body.get('status') == '200',
        'jepx_status': jepx_body.get('status', ''),
        'message': jepx_body.get('statusInfo', ''),
    }


def serialize_inquiry_response(jepx_body: dict) -> dict:
    """JEPX照会レスポンスを元に、Excelシートへ展開するための配列入りJSONを構築する"""
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
    """予期せぬエラーやバリデーションエラー時に、VBAへ返す統一されたエラーフォーマットを作成する。"""
    return {
        'success': False,
        'error_code': error_code,
        'message': message,
    }
