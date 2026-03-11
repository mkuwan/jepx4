"""dah_bid: 計画値取込→検証→冪等性チェック→入札 (JP1ジョブ2-3)"""
import asyncio
import sys
from django.core.management.base import BaseCommand

from apps.dah_batch.lock import BatchLock
from apps.dah_batch.services import execute_bid


class Command(BaseCommand):
    """翌日市場の入札バッチ（取込→検証→冪等性チェック→入札送信）
    
    このクラスは `python manage.py dah_bid --date 2026-03-12` といった形でOSから直接実行可能な
    CLIコマンドのエントリポイントとなります。（JP1等のジョブからキックされます）
    
    BaseCommandを継承しているため、Djangoのコンテキストが自動で読み込まれた状態から起動します。
    """
    
    help = '翌日市場の入札バッチ（取込→検証→冪等性チェック→入札送信）'

    def add_arguments(self, parser):
        parser.add_argument('--date', required=True, help='受渡日 (YYYY-MM-DD)')

    def handle(self, *args, **options):
        """コマンドのメイン処理。オプション引数から日付を受け取り、サービス層へ渡す。
        
        BatchLockで複数起動を防止し、各種エラー(RuntimeError, システムエラー)が発生した場合は
        OSの終了コードとして 1 (エラー) または 2 (ロック競合) を返して異常を伝達します。
        """
        delivery_date = options['date']
        self.stdout.write(f"[dah_bid] 対象日: {delivery_date}")

        try:
            with BatchLock('dah_bid', delivery_date):
                result = asyncio.run(execute_bid(delivery_date))
        except RuntimeError as e:
            self.stderr.write(self.style.ERROR(str(e)))
            sys.exit(2)

        status = result.get('status')
        message = result.get('message', '')
        count = result.get('count', 0)

        if status == 'success':
            self.stdout.write(self.style.SUCCESS(
                f"入札完了: {count}件 ({message})"
            ))
        elif status == 'skipped':
            self.stdout.write(self.style.WARNING(
                f"入札スキップ: {message}"
            ))
        elif status == 'error':
            self.stderr.write(self.style.ERROR(
                f"入札エラー: {message}"
            ))
            sys.exit(1)
