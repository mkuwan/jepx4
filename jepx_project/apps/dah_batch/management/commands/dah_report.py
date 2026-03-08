"""dah_report: 計画値vs約定の比較レポート生成 (JP1ジョブ5)"""
import asyncio
import sys
from django.core.management.base import BaseCommand

from apps.jepx_client.client import JepxApiClient
from apps.sharepoint.client import SharePointClient
from apps.dah_batch.services import generate_report


class Command(BaseCommand):
    help = '翌日市場の比較レポート生成（計画値 vs DAH1030約定結果）'

    def add_arguments(self, parser):
        parser.add_argument('--date', required=True, help='受渡日 (YYYY-MM-DD)')

    def handle(self, *args, **options):
        delivery_date = options['date']
        self.stdout.write(f"[dah_report] 対象日: {delivery_date}")

        try:
            report_bytes = asyncio.run(self._generate_and_upload(delivery_date))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"レポート生成エラー: {e}"))
            sys.exit(1)

        self.stdout.write(self.style.SUCCESS(
            f"比較レポート生成完了 ({len(report_bytes)}B)"
        ))

    async def _generate_and_upload(self, delivery_date: str) -> bytes:
        """約定データ取得 → レポート生成 → SharePointアップロード"""
        client = JepxApiClient()
        sp = SharePointClient()

        # DAH1030 全約定照会
        result = await client.send_request('DAH1030', {
            'deliveryDate': delivery_date,
        })
        contracts = result.get('bidResults', [])

        # レポート生成
        report_bytes = await generate_report(delivery_date, contracts)

        # SharePointにアップロード
        report_path = f"output/{delivery_date}_report.csv"
        await sp.upload_file(report_path, report_bytes)

        return report_bytes
