"""ITN InMemoryStore — 3層構造 (§5.4)

JEPX ITN1001 配信データをメモリ上に保持し、SSE/ポーリングで配信する。

3層構造:
  - contracts: 約定情報 (CONTRACT) — bidNoベースでマージ
  - boards: 板情報 (BID-BOARD) — (areaCd, timeCd)ベースでマージ
  - connection_status: 接続状態
"""
import time
import logging
from threading import Lock

logger = logging.getLogger('jepx.api')


class ItnMemoryStore:
    """ITN InMemoryStore (スレッドセーフ)"""

    def __init__(self):
        self._contracts: dict[str, dict] = {}     # key: bidNo
        self._boards: dict[str, dict] = {}         # key: "{areaCd}:{timeCd}"
        self._connection_status: dict = {
            'connected': False,
            'last_received': None,
            'error': None,
        }
        self._lock = Lock()
        self._version = 0     # 更新バージョン (ポーリング用)

    def update_notices(self, notices: list[dict]) -> None:
        """ITN1001配信データを反映する。

        Args:
            notices: ITN通知リスト
                - noticeType="CONTRACT": 約定情報
                - noticeType="BID-BOARD": 板情報
        """
        with self._lock:
            for notice in notices:
                ntype = notice.get('noticeType', '')
                if ntype == 'CONTRACT':
                    bid_no = notice.get('bidNo', '')
                    if bid_no:
                        self._contracts[bid_no] = notice
                elif ntype == 'BID-BOARD':
                    area = notice.get('areaCd', '')
                    time_cd = notice.get('timeCd', '')
                    key = f"{area}:{time_cd}"
                    self._boards[key] = notice
            self._version += 1
            self._connection_status['last_received'] = time.time()

    def set_full_state(self, notices: list[dict]) -> None:
        """全量配信データで状態をリセットする。"""
        with self._lock:
            self._contracts.clear()
            self._boards.clear()
        self.update_notices(notices)

    def set_connection_status(self, connected: bool, error: str | None = None) -> None:
        """接続状態を更新する。"""
        with self._lock:
            self._connection_status['connected'] = connected
            self._connection_status['error'] = error
            self._version += 1

    def get_snapshot(self) -> dict:
        """現在の状態をスナップショットとして返す。"""
        with self._lock:
            return {
                'version': self._version,
                'connection': dict(self._connection_status),
                'contracts': list(self._contracts.values()),
                'boards': list(self._boards.values()),
            }

    def get_version(self) -> int:
        """現在のバージョン番号を返す。"""
        return self._version
