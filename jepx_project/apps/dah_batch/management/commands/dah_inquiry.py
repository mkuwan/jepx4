"""dah_inquiry: 約定照会・市場結果照会・清算照会→ファイル出力 (JP1ジョブ4)"""
import asyncio
import json
import sys
from django.core.management.base import BaseCommand

from apps.dah_batch.services import execute_inquiry


class Command(BaseCommand):
    help = '翌日市場の照会バッチ（約定・市場結果・清算 → ファイル出力）'

    def add_arguments(self, parser):
        parser.add_argument('--date', required=True, help='受渡日 (YYYY-MM-DD)')

    def handle(self, *args, **options):
        delivery_date = options['date']
        self.stdout.write(f"[dah_inquiry] 対象日: {delivery_date}")

        try:
            results = asyncio.run(execute_inquiry(delivery_date))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"照会エラー: {e}"))
            sys.exit(1)

        contracts = results.get('contracts', [])
        market = results.get('market_results', [])
        settlements = results.get('settlements', [])

        self.stdout.write(self.style.SUCCESS(
            f"照会完了: 約定={len(contracts)}件, "
            f"市場結果={len(market)}件, 清算={len(settlements)}件"
        ))
