"""dah_check_file: 計画値ファイル存在確認 (JP1ジョブ1)"""
import asyncio
from django.core.management.base import BaseCommand

from apps.dah_batch.services import check_input_file


class Command(BaseCommand):
    help = 'SharePointに計画値ファイルが存在するか確認する'

    def add_arguments(self, parser):
        parser.add_argument('--date', required=True, help='受渡日 (YYYY-MM-DD)')

    def handle(self, *args, **options):
        delivery_date = options['date']
        self.stdout.write(f"[dah_check_file] 対象日: {delivery_date}")

        exists = asyncio.run(check_input_file(delivery_date))

        if exists:
            self.stdout.write(self.style.SUCCESS("ファイルが存在します"))
        else:
            self.stderr.write(self.style.ERROR("ファイルが存在しません"))
            raise SystemExit(1)
