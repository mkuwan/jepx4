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

    同一受渡日の `dah_bid` などのバッチが、複数同時に起動・並行実行されてしまうのを防ぐ仕組みです。
    OSのファイルロック機構（Windowsならmsvcrt、Linuxならfcntl）を利用し、
    既にロックファイルが他プロセスによって掴まれている場合は即座に例外をスローして実行を中止します。
    """

    def __init__(self, command: str, delivery_date: str):
        lock_dir = Path(settings.BASE_DIR) / 'locks'
        lock_dir.mkdir(exist_ok=True)
        self.lock_path = lock_dir / f'{command}_{delivery_date}.lock'
        self._fd = None

    def __enter__(self):
        """with構文に入った瞬間に呼ばれるロック取得処理。
        
        対象日付専用のロックファイルを「排他・非ブロッキングモード(LK_NBLCK / LOCK_NB)」で開き、
        他プロセスが使用中なら即 RuntimeError を発生させます。
        """
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
