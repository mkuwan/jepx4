"""コード定義ローダー (§9.3)

データベースを持たない本システムにおいて、変更頻度は低いものの再ビルドなしで
外部から変更したい値（エリアコード、入札上限値など）を、設定ファイル（YAML）から
読み込んでプログラム内に提供する役割を担います。
パフォーマンスを担保するため、lru_cache を利用してパース結果をメモリに保持します。
"""
import yaml
from pathlib import Path
from functools import lru_cache

from django.conf import settings


@lru_cache(maxsize=1)
def load_master_codes() -> dict:
    """マスタコードYAMLを初回のみファイルI/Oから読み込み、dictとしてメモリに完全キャッシュする関数。

    この関数はシステム内で何度も呼び出されますが、デコレータ @lru_cache の効果で
    ２回目以降は即座にキャッシュされた辞書オブジェクトを返却します。
    (運用中に設定ファイルを変えた場合、反映にはDjangoプロセスの再起動が必要です。)

    Returns:
        解析済みの config_data/jepx_master.yaml の内容 (dict)
    """
    path = Path(settings.BASE_DIR) / 'config_data' / 'jepx_master.yaml'
    with open(path, 'r', encoding='utf-8') as f:
        # YAMLファイルを安全にPythonのデータ構造（Dict）に変換して返す
        return yaml.safe_load(f)


def get_area_name(area_cd: str) -> str:
    """エリアコード(1等)を渡し、対応するエリア名(北海道等)を取得する。翌日市場等の汎用向け。"""
    codes = load_master_codes()
    return codes['areas'].get(area_cd, f"不明({area_cd})")


def get_area_group_name(area_group_cd: str) -> str:
    """時間前市場(ITN/ITD)で特殊に使われる「エリアグループコード(A1等)」を元にエリア名を取得する。"""
    codes = load_master_codes()
    return codes['area_groups'].get(area_group_cd, f"不明({area_group_cd})")


def is_valid_bid_type(bid_type_cd: str) -> bool:
    """入札種別コード（SELL-LIMIT等）がJEPX仕様上の有効な文字列であるかを検証する。"""
    codes = load_master_codes()
    return bid_type_cd in codes['bid_types']


def is_valid_area_code(area_cd: str) -> bool:
    """指定されたエリアコードがマスターに定義されている有効な値か検証する。"""
    codes = load_master_codes()
    return area_cd in codes['areas']


def is_valid_area_group_code(area_group_cd: str) -> bool:
    """指定されたエリアグループコード(ITD用)が有効な値か検証する。"""
    codes = load_master_codes()
    return area_group_cd in codes['area_groups']


def get_time_code_range() -> tuple[int, int]:
    """1日の時間帯コード（コマ）の最小値・最大値を取得する。標準は1〜48コマ。"""
    codes = load_master_codes()
    tc = codes['time_codes']
    return tc['min'], tc['max']


def get_limits() -> dict:
    """運用上の安全装置として働かせる「入札価格上限」「入札量上限」の辞書を取得する。"""
    codes = load_master_codes()
    return codes['limits']
