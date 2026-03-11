"""dah_inquiry: 約定照会・市場結果照会・清算照会→ファイル出力 (JP1ジョブ4)"""
import asyncio
import json
import sys
from django.core.management.base import BaseCommand

from apps.dah_batch.services import execute_inquiry


class Command(BaseCommand):
    """翌日市場の照会系処理（約定・市場結果・清算）を取りまとめて実行するバッチ。
    
    JP1の夕方以降のジョブとして起動され、JEPXからの結果取得と
    自社SharePoint上の共有フォルダ（PDFやCSVの格納）への書き出しを一手に担います。
    """
    help = '翌日市場の照会バッチ（約定・市場結果・清算 → ファイル出力）'

    def add_arguments(self, parser):
        parser.add_argument('--date', required=True, help='受渡日 (YYYY-MM-DD)')

    def handle(self, *args, **options):
        """照会実行のエントリポイント。
        内部で execute_inquiry サービスロジックを非同期実行します。
        """
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
