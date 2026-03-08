"""DAH業務ロジック (§4)

翌日市場の入札・照会・レポート生成のコアロジック。
management commandsからはこのモジュールの関数を呼び出す。
"""
import asyncio
import csv
import io
import base64
import logging
import tempfile
from pathlib import Path

from django.conf import settings

from apps.jepx_client.client import JepxApiClient
from apps.sharepoint.client import SharePointClient
from apps.sharepoint.file_parser import parse_csv, parse_excel
from apps.common.validators import BidValidator, ValidationError as VError

logger = logging.getLogger('jepx.api')
audit_logger = logging.getLogger('jepx.audit')
error_logger = logging.getLogger('jepx.error')


async def check_input_file(delivery_date: str) -> bool:
    """計画値ファイルの存在確認 (dah_check_file コマンド用)

    Args:
        delivery_date: 対象受渡日 (YYYY-MM-DD)

    Returns:
        ファイルが存在する場合True
    """
    sp = SharePointClient()
    file_path = f"input/{delivery_date}.csv"
    exists = await sp.file_exists(file_path)
    audit_logger.info(
        "[OPERATION] ファイル存在確認: %s → %s",
        file_path, "存在" if exists else "不在",
    )
    return exists


async def execute_bid(delivery_date: str) -> dict:
    """入札実行 (dah_bid コマンド用)

    §4.3 処理フロー:
    1. SharePointから計画値ファイル取込
    2. バリデーション
    3. 冪等性チェック (DAH1002照会)
    4. 入札送信 (DAH1001)

    Returns:
        {'status': 'success'|'skipped'|'error', 'message': str, 'count': int}
    """
    client = JepxApiClient()
    sp = SharePointClient()

    # 1. ファイル取込
    file_path = f"input/{delivery_date}.csv"
    audit_logger.info("[OPERATION] 計画値ファイル取込開始: %s", file_path)
    content = await sp.download_file(file_path)

    # CSV/Excel判定
    if file_path.endswith('.xlsx'):
        rows = parse_excel(content)
    else:
        rows = parse_csv(content)
    audit_logger.info("[OPERATION] ファイル件数: %d行", len(rows))

    # 2. バリデーション
    validator = BidValidator()
    errors = validator.validate(rows, market='DAH')
    if errors:
        error_logger.error("[VALIDATION] バリデーションエラー %d件", len(errors))
        # エラーレポートCSV出力 (§4.8)
        await _output_error_report(sp, delivery_date, errors)

        if settings.VALIDATION_FAIL_FAST:
            return {
                'status': 'error',
                'message': f'バリデーションエラー {len(errors)}件',
                'count': 0,
            }

    # 3. 冪等性チェック (§4.6)
    audit_logger.info("[OPERATION] 冪等性チェック: DAH1002 (deliveryDate=%s)", delivery_date)
    existing = await client.send_request('DAH1002', {
        'deliveryDate': delivery_date,
    })
    existing_bids = existing.get('bids', [])

    if existing_bids:
        audit_logger.info(
            "[OPERATION] 入札済み→スキップ (既存%d件)", len(existing_bids)
        )
        return {
            'status': 'skipped',
            'message': f'入札済み ({len(existing_bids)}件)',
            'count': len(existing_bids),
        }

    # 4. 入札送信 (DAH1001)
    bid_offers = _build_bid_offers(rows)
    audit_logger.info("[OPERATION] 入札送信: DAH1001 (%d件)", len(bid_offers))
    result = await client.send_request('DAH1001', {
        'deliveryDate': delivery_date,
        'bidOffers': bid_offers,
    })

    audit_logger.info(
        "[API_COMM] 入札結果: status=%s, statusInfo=%s",
        result.get('status'), result.get('statusInfo'),
    )
    return {
        'status': 'success',
        'message': result.get('statusInfo', ''),
        'count': len(bid_offers),
    }


async def execute_inquiry(delivery_date: str) -> dict:
    """照会実行 (dah_inquiry コマンド用)

    §4.5: DAH1004(約定照会) + DAH1030(全約定照会) + DAH1050(市場結果) + DAH9001(清算)
    """
    client = JepxApiClient()
    sp = SharePointClient()
    results = {}

    # DAH1030 全約定照会 (通常+ブロック — 比較レポート用)
    audit_logger.info("[OPERATION] 全約定照会: DAH1030")
    contract_data = await client.send_request('DAH1030', {
        'deliveryDate': delivery_date,
    })
    results['contracts'] = contract_data.get('bidResults', [])

    # DAH1050 市場結果照会
    audit_logger.info("[OPERATION] 市場結果照会: DAH1050")
    market_data = await client.send_request('DAH1050', {
        'deliveryDate': delivery_date,
    })
    results['market_results'] = market_data.get('marketResults', [])

    # DAH9001 清算照会
    audit_logger.info("[OPERATION] 清算照会: DAH9001")
    settlement_data = await client.send_request('DAH9001', {
        'fromDate': delivery_date,
    })
    settlements = settlement_data.get('settlements', [])
    results['settlements'] = settlements

    # PDF保存 (§5 PDFハンドリング手順)
    for s in settlements:
        pdf_b64 = s.get('pdf')
        if pdf_b64:
            pdf_bytes = base64.b64decode(pdf_b64)
            filename = f"output/{s['settlementDate']}_{s['settlementNo']}.pdf"
            await sp.upload_file(filename, pdf_bytes)
            audit_logger.info("[OPERATION] PDF出力: %s", filename)

    return results


async def generate_report(delivery_date: str, contract_data: list[dict]) -> bytes:
    """比較レポート生成 (dah_report コマンド用) (§4.7)

    計画値ファイル vs DAH1030約定結果の比較CSV
    """
    sp = SharePointClient()

    # 計画値を再取得
    content = await sp.download_file(f"input/{delivery_date}.csv")
    plan_rows = parse_csv(content)

    # 約定データを (deliveryDate, timeCd, areaCd) でインデックス化
    contract_map = {}
    for c in contract_data:
        key = (c.get('deliveryDate'), c.get('timeCd'), c.get('areaCd'))
        contract_map[key] = c

    # CSV生成
    output = io.StringIO()
    writer = csv.writer(output)
    # ヘッダ
    writer.writerow([
        'deliveryDate', 'timeCd', 'areaCd',
        'plan_price', 'plan_volume',
        'contract_price', 'contract_volume',
        'diff_volume', 'match',
    ])

    for row in plan_rows:
        key = (row.get('deliveryDate'), row.get('timeCd'), row.get('areaCd'))
        c = contract_map.get(key, {})

        plan_vol = float(row.get('volume', 0) or 0)
        contract_vol = float(c.get('contractVolume', 0) or 0)
        diff = contract_vol - plan_vol
        match = 'OK' if abs(diff) < 0.01 else 'MISMATCH'

        writer.writerow([
            row.get('deliveryDate', ''),
            row.get('timeCd', ''),
            row.get('areaCd', ''),
            row.get('price', ''),
            row.get('volume', ''),
            c.get('contractPrice', ''),
            c.get('contractVolume', ''),
            f'{diff:.1f}',
            match,
        ])

    csv_bytes = ('\ufeff' + output.getvalue()).encode('utf-8')  # BOM付きUTF-8
    return csv_bytes


def _build_bid_offers(rows: list[dict]) -> list[dict]:
    """入力行リストからDAH1001のbidOffers配列を構築する"""
    offers = []
    for row in rows:
        offer = {
            'areaCd': str(row.get('areaCd', '')),
            'timeCd': str(row.get('timeCd', '')),
            'bidTypeCd': str(row.get('bidTypeCd', '')),
            'price': float(row.get('price', 0) or 0),
            'volume': float(row.get('volume', 0) or 0),
        }
        if row.get('deliveryContractCd'):
            offer['deliveryContractCd'] = str(row['deliveryContractCd'])
        if row.get('note'):
            offer['note'] = str(row['note'])[:100]
        offers.append(offer)
    return offers


async def _output_error_report(
    sp: SharePointClient, delivery_date: str, errors: list[VError]
) -> None:
    """エラーレポートCSVを出力する (§4.8)"""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['row', 'field', 'rule_id', 'error_code', 'message', 'original_value'])
    for err in errors:
        writer.writerow([
            err.row, err.field, err.rule_id,
            err.error_code, err.message, err.original_value,
        ])
    csv_bytes = ('\ufeff' + output.getvalue()).encode('utf-8')
    await sp.upload_error_report(f"{delivery_date}_error.csv", csv_bytes)
    audit_logger.info("[OPERATION] エラーレポート出力: %s_error.csv (%d件)", delivery_date, len(errors))
