"""ITD業務ロジック (§5)

時間前市場の入札・削除・照会・約定・清算の
JEPXリクエスト構築を担当する。
"""
import logging

from apps.jepx_client.client import JepxApiClient
from apps.common.validators import BidValidator

audit_logger = logging.getLogger('jepx.audit')


async def execute_itd_bid(data: dict) -> dict:
    """ITD入札の送信データ構築と実行を行う (ITD1001)

    Views層で受け取ったパース済みのdictから、JEPXが要求する型の
    値(文字列や小数点数)へ厳格な型変換・補正を行い、JepxApiClientへ渡します。

    Args:
        data: リクエストデータ (deliveryDate, timeCd, areaCd, ...)

    Returns:
        JEPX APIレスポンスbody
    """
    client = JepxApiClient()
    body = {
        'deliveryDate': data['deliveryDate'],
        'timeCd': str(data['timeCd']),
        'areaCd': str(data['areaCd']),
        'bidTypeCd': data['bidTypeCd'],
        'price': float(data.get('price', 0)),
        'volume': float(data.get('volume', 0)),
    }
    if data.get('deliveryContractCd'):
        body['deliveryContractCd'] = data['deliveryContractCd']
    if data.get('note'):
        body['note'] = str(data['note'])[:100]

    audit_logger.info(
        "[OPERATION] ITD入札送信: ITD1001 (date=%s, timeCd=%s, areaCd=%s)",
        body['deliveryDate'], body['timeCd'], body['areaCd'],
    )
    return await client.send_request('ITD1001', body)


async def execute_itd_delete(data: dict) -> dict:
    """指定された入札番号(bidNo)を持つITD入札を取消(削除)する (ITD1002)"""
    client = JepxApiClient()
    body = {
        'deliveryDate': data['deliveryDate'],
        'targetBidNo': data['bidNo'],  # JEPX仕様903 2.2: 削除対象入札番号フィールド名はtargetBidNo
    }
    audit_logger.info("[OPERATION] ITD削除送信: ITD1002 (bidNo=%s)", data['bidNo'])
    return await client.send_request('ITD1002', body)


async def execute_itd_inquiry(data: dict) -> dict:
    """受渡日・対象時間を指定して自社のITD入札状況を照会する (ITD1003)"""
    client = JepxApiClient()
    body = {'deliveryDate': data['deliveryDate']}
    if data.get('timeCd'):
        body['timeCd'] = str(data['timeCd'])
    audit_logger.info("[OPERATION] ITD照会: ITD1003 (date=%s)", data['deliveryDate'])
    return await client.send_request('ITD1003', body)


async def execute_itd_contract(data: dict) -> dict:
    """受渡日を指定して自社のITD約定状況を照会する (ITD1004)"""
    client = JepxApiClient()
    body = {'deliveryDate': data['deliveryDate']}
    audit_logger.info("[OPERATION] ITD約定照会: ITD1004 (date=%s)", data['deliveryDate'])
    return await client.send_request('ITD1004', body)


async def execute_itd_settlement(data: dict) -> dict:
    """ITD清算データを照会する (ITD9001)"""
    client = JepxApiClient()
    body = {'fromDate': data.get('fromDate', data.get('deliveryDate', ''))}
    if data.get('toDate'):
        body['toDate'] = data['toDate']
    audit_logger.info("[OPERATION] ITD清算照会: ITD9001")
    return await client.send_request('ITD9001', body)


async def check_duplicate_bid(data: dict) -> dict | None:
    """ITD二重送信チェック (§5.3.1 FR-40準拠)

    VBAから送信された入札データと同じ時間帯(timeCd)・エリア(areaCd)・入札種別(bidTypeCd)
    の「有効な(未取消の)」入札が既に存在しないかをITD1003を用いて事前照会します。
    ※ 存在する場合は、重複を避けるために呼び出し側のViewでエラー(409 Conflict)として弾きます。

    Returns:
        重複入札がある場合はそのbid dict、なければ None
    """
    client = JepxApiClient()
    existing = await client.send_request('ITD1003', {
        'deliveryDate': data['deliveryDate'],
        'timeCd': str(data.get('timeCd', '')),
    })

    for bid in existing.get('bids', []):
        if (bid.get('timeCd') == str(data.get('timeCd', ''))
                and bid.get('areaCd') == str(data.get('areaCd', ''))
                and bid.get('bidTypeCd') == data.get('bidTypeCd', '')
                and bid.get('deleteCd', '0') == '0'):
            return bid
    return None
