"""SharePoint ファイルクライアント (§6.2)

Graph API を使用した SharePoint ファイルのダウンロード・アップロード。
dev環境ではローカルファイルにフォールバックする。
"""
import logging
from pathlib import Path

import httpx

from django.conf import settings

from .auth import SharePointAuth

logger = logging.getLogger('jepx.api')
audit_logger = logging.getLogger('jepx.audit')

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


class SharePointClient:
    """SharePoint (OneDrive for Business) 上の共有フォルダとファイル入出力を行うクライアント。

    Microsoft Graph API (v1.0) を用いてファイルのダウンロード・アップロードを行います。
    SHAREPOINT_ENABLED=False に設定されているローカル開発環境(dev環境)では、APIをネットワーク越しに呼ばず、
    直接ローカルの設定フォルダ(INPUT_FILE_DIR等)を読み書きするフォールバック動作を提供し、開発効率を高めます。
    """

    def __init__(self):
        self.enabled = getattr(settings, 'SHAREPOINT_ENABLED', False)
        if self.enabled:
            self.auth = SharePointAuth()
            self.site_id = settings.SHAREPOINT_SITE_ID
            self.drive_id = settings.SHAREPOINT_DRIVE_ID

    async def download_file(self, remote_path: str) -> bytes:
        """SharePoint上の対象パスからファイル（計画値Excel/CSV等）をバイナリとしてダウンロードする。

        Args:
            remote_path: SharePoint上のパス (例: "input/2026-04-01.csv")

        Returns:
            ファイル内容のバイト列 (bytes)
        """
        if not self.enabled:
            # dev環境: ローカルファイルから読み込み
            local_path = Path(settings.INPUT_FILE_DIR) / Path(remote_path).name
            audit_logger.info("[SHAREPOINT] dev: ローカル読み込み %s", local_path)
            return local_path.read_bytes()

        token = await self.auth.get_token()
        url = (
            f"{GRAPH_BASE}/sites/{self.site_id}/drives/{self.drive_id}"
            f"/root:/{remote_path}:/content"
        )
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                url, headers={'Authorization': f'Bearer {token}'}, follow_redirects=True,
            )
            resp.raise_for_status()
        audit_logger.info("[SHAREPOINT] ダウンロード完了: %s (%dB)", remote_path, len(resp.content))
        return resp.content

    async def upload_file(self, remote_path: str, content: bytes) -> None:
        """生成・取得したデータ（結果レポートCSVやJEPX清算PDF等）をSharePointの指定パスへアップロードする。

        Args:
            remote_path: SharePoint上の保存先パス (例: "output/2026-04-01_report.csv")
            content: アップロードするファイル内容のバイト列 (bytes)
        """
        if not self.enabled:
            # dev環境: ローカルに出力
            local_path = Path(settings.OUTPUT_FILE_DIR) / Path(remote_path).name
            local_path.parent.mkdir(parents=True, exist_ok=True)
            local_path.write_bytes(content)
            audit_logger.info("[SHAREPOINT] dev: ローカル出力 %s (%dB)", local_path, len(content))
            return

        token = await self.auth.get_token()
        url = (
            f"{GRAPH_BASE}/sites/{self.site_id}/drives/{self.drive_id}"
            f"/root:/{remote_path}:/content"
        )
        async with httpx.AsyncClient() as client:
            resp = await client.put(
                url,
                headers={
                    'Authorization': f'Bearer {token}',
                    'Content-Type': 'application/octet-stream',
                },
                content=content,
            )
            resp.raise_for_status()
        audit_logger.info("[SHAREPOINT] アップロード完了: %s (%dB)", remote_path, len(content))

    async def upload_error_report(self, remote_path: str, content: bytes) -> None:
        """エラーレポートCSVをerrorフォルダにアップロードする。"""
        if not self.enabled:
            # dev環境: ローカルのerrorフォルダに出力
            local_path = Path(settings.ERROR_FILE_DIR) / Path(remote_path).name
            local_path.parent.mkdir(parents=True, exist_ok=True)
            local_path.write_bytes(content)
            audit_logger.info("[SHAREPOINT] dev: エラーレポート出力 %s", local_path)
            return

        error_path = f"error/{Path(remote_path).name}"
        await self.upload_file(error_path, content)

    async def file_exists(self, remote_path: str) -> bool:
        """SharePoint上にファイルが存在するか確認する。

        Args:
            remote_path: SharePoint上のパス

        Returns:
            ファイルが存在すればTrue
        """
        if not self.enabled:
            local_path = Path(settings.INPUT_FILE_DIR) / Path(remote_path).name
            return local_path.exists()

        token = await self.auth.get_token()
        url = (
            f"{GRAPH_BASE}/sites/{self.site_id}/drives/{self.drive_id}"
            f"/root:/{remote_path}"
        )
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                url, headers={'Authorization': f'Bearer {token}'},
            )
        return resp.status_code == 200
