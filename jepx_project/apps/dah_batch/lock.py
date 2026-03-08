"""DAH バッチ排他制御 (§4.2)

ファイルロックによる同一受渡日のバッチ重複実行防止。
JP1排他ジョブグループとの二重防止を行う。

注意: Windowsでは fcntl が使えないため、msvcrt を使う。
"""
import os
import sys
import logging
from pathlib import Path

from django.conf import settings

logger = logging.getLogger('jepx.audit')


class BatchLock:
    """ファイルロックによる排他制御。

    同一受渡日のdah_bidが並列実行されることを防止する。
    Linux (fcntl) / Windows (msvcrt) の両方に対応。
    """

    def __init__(self, command: str, delivery_date: str):
        lock_dir = Path(settings.BASE_DIR) / 'locks'
        lock_dir.mkdir(exist_ok=True)
        self.lock_path = lock_dir / f'{command}_{delivery_date}.lock'
        self._fd = None

    def __enter__(self):
        self._fd = open(self.lock_path, 'w')
        try:
            if sys.platform == 'win32':
                import msvcrt
                msvcrt.locking(self._fd.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, IOError):
            self._fd.close()
            raise RuntimeError(
                f'同一受渡日のバッチが実行中です: {self.lock_path.name}'
            )
        logger.info("[LOCK] 排他ロック取得: %s", self.lock_path.name)
        return self

    def __exit__(self, *args):
        if self._fd:
            try:
                if sys.platform == 'win32':
                    import msvcrt
                    msvcrt.locking(self._fd.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self._fd, fcntl.LOCK_UN)
            except (OSError, IOError):
                pass
            self._fd.close()
            try:
                self.lock_path.unlink(missing_ok=True)
            except OSError:
                pass
            logger.info("[LOCK] 排他ロック解放: %s", self.lock_path.name)
