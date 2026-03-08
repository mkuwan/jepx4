"""SharePoint OAuth2 認証 (§6.1)

Microsoft Graph API (Client Credentials Flow) でアクセストークンを取得する。
"""
import time
import logging

import httpx

from django.conf import settings

logger = logging.getLogger('jepx.api')


class SharePointAuth:
    """Azure AD Client Credentials でトークンを取得・キャッシュする"""

    _token: str | None = None
    _expires_at: float = 0

    def __init__(self):
        self.tenant_id = settings.GRAPH_API_TENANT_ID
        self.client_id = settings.GRAPH_API_CLIENT_ID
        self.client_secret = settings.GRAPH_API_CLIENT_SECRET
        self.token_url = (
            f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        )

    async def get_token(self) -> str:
        """アクセストークンを取得する (キャッシュあり)。

        トークンの有効期限が切れている場合は自動的に再取得する。
        """
        if self._token and time.time() < self._expires_at - 60:
            return self._token

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.token_url,
                data={
                    'grant_type': 'client_credentials',
                    'client_id': self.client_id,
                    'client_secret': self.client_secret,
                    'scope': 'https://graph.microsoft.com/.default',
                },
            )
            response.raise_for_status()
            data = response.json()

        self._token = data['access_token']
        self._expires_at = time.time() + data.get('expires_in', 3600)
        logger.info("[SHAREPOINT] トークン取得成功 (expires_in=%s)", data.get('expires_in'))
        return self._token
