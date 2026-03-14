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
    """ITN(時間前市場)の板情報・約定情報のリアルタイム配信データを保持する、スレッドセーフなインメモリストア。

    JEPXからの膨大な配信差分データを毎回RDB(PostgreSQL等)に書き込んでいてはパフォーマンスが追いつかないため、
    Django(ASGI)サーバーの単一プロセス内メモリ上にdict形式で最新状態（スナップショット）を構築・保持します。
    """

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
        """JEPXからPushされたITNの差分配信イベント(お知らせ)により、インメモリ状態を上書き更新(UPSERT)する。
        
        同一キーのものがくれば上書きし、新規なら追加されます。更新後はバージョン番号をインクリメントします。

        Args:
            notices: ITN通知リスト
                - noticeTypeCd="CONTRACT": 約定情報
                - noticeTypeCd="BID-BOARD": 板情報
        """
        with self._lock:
            for notice in notices:
                ntype = notice.get('noticeTypeCd', '')
                if ntype == 'CONTRACT':
                    # bidNo がない場合は deliveryDate+timeCd+timestamp で代替キーを作る
                    bid_no = (notice.get('bidNo')
                              or f"{notice.get('deliveryDate','')}:{notice.get('timeCd','')}:{notice.get('timestamp','')}")
                    self._contracts[bid_no] = notice
                elif ntype == 'BID-BOARD':
                    # MockServer は areaGroupCd を使用する場合がある
                    # 売Buy・買Buyは同一スロットでも別エントリとして保持する
                    area      = notice.get('areaCd') or notice.get('areaGroupCd', '')
                    date_cd   = notice.get('deliveryDate', '')
                    time_cd   = notice.get('timeCd', '')
                    buy_sell  = notice.get('buySellCd', '')
                    key = f"{area}:{date_cd}:{time_cd}:{buy_sell}"
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
        """接続中の社内クライアント(ブラウザのダッシュボードやExcel)へ現在状態をまとめて返却するためのスナップショットを作成する。"""
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
