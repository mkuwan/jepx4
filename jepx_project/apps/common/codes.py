"""コード定義ローダー (§9.3)

YAMLマスタコード定義を読み込み、lru_cacheでキャッシュする。
変更を反映するにはプロセスの再起動が必要。
"""
import yaml
from pathlib import Path
from functools import lru_cache

from django.conf import settings


@lru_cache(maxsize=1)
def load_master_codes() -> dict:
    """マスタコードYAMLを読み込み、dictとしてキャッシュする。

    Returns:
        config_data/jepx_master.yaml の内容 (dict)
    """
    path = Path(settings.BASE_DIR) / 'config_data' / 'jepx_master.yaml'
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def get_area_name(area_cd: str) -> str:
    """エリアコードからエリア名を取得する"""
    codes = load_master_codes()
    return codes['areas'].get(area_cd, f"不明({area_cd})")


def get_area_group_name(area_group_cd: str) -> str:
    """エリアグループコードからエリア名を取得する (時間前市場用)"""
    codes = load_master_codes()
    return codes['area_groups'].get(area_group_cd, f"不明({area_group_cd})")


def is_valid_bid_type(bid_type_cd: str) -> bool:
    """入札種別コードが有効か検証する"""
    codes = load_master_codes()
    return bid_type_cd in codes['bid_types']


def is_valid_area_code(area_cd: str) -> bool:
    """エリアコードが有効か検証する"""
    codes = load_master_codes()
    return area_cd in codes['areas']


def is_valid_area_group_code(area_group_cd: str) -> bool:
    """エリアグループコードが有効か検証する (時間前市場用)"""
    codes = load_master_codes()
    return area_group_cd in codes['area_groups']


def get_time_code_range() -> tuple[int, int]:
    """時間帯コードの有効範囲を取得する"""
    codes = load_master_codes()
    tc = codes['time_codes']
    return tc['min'], tc['max']


def get_limits() -> dict:
    """入札制限値を取得する"""
    codes = load_master_codes()
    return codes['limits']
