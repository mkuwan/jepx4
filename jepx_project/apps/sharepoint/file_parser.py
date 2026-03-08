"""CSV/Excel ファイルパーサー (§6.3)

SharePointからダウンロードしたファイル(bytes)をパースし、
dict list として返す。
"""
import csv
import io
from openpyxl import load_workbook


def parse_csv(content: bytes) -> list[dict]:
    """CSVファイル(bytes)を dict list にパースする。

    BOM付きUTF-8を自動処理。ヘッダ行をキーとして使用。

    Args:
        content: CSVファイルの内容 (bytes)

    Returns:
        list of dict (1行=1dict, ヘッダをキーとして使用)
    """
    text = content.decode('utf-8-sig')
    reader = csv.DictReader(io.StringIO(text))
    return list(reader)


def parse_excel(content: bytes, sheet_name: str | None = None) -> list[dict]:
    """Excelファイル(bytes)を dict list にパースする。

    1行目をヘッダとして使用。

    Args:
        content: Excelファイルの内容 (bytes)
        sheet_name: 対象シート名 (Noneなら最初のシート)

    Returns:
        list of dict (1行=1dict, ヘッダをキーとして使用)
    """
    wb = load_workbook(filename=io.BytesIO(content), read_only=True)
    ws = wb[sheet_name] if sheet_name else wb.active

    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []

    headers = [str(h).strip() if h else f'col_{i}' for i, h in enumerate(rows[0])]
    result = []
    for row in rows[1:]:
        if all(cell is None for cell in row):
            continue  # 空行スキップ
        result.append({
            headers[i]: cell for i, cell in enumerate(row)
        })

    wb.close()
    return result
