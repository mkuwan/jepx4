"""検証環境 — JEPX検証環境接続 (§2.2.4)

TLS証明書: ファイル指定 (Mode B) — JEPX検証環境CA証明書を certs/ に配置
"""
import os
from .base import *  # noqa: F401,F403

DEBUG = False
ALLOWED_HOSTS = [os.environ.get('ALLOWED_HOST', '*')]

# JEPX検証環境接続
JEPX_HOST = os.environ.get('JEPX_HOST')         # JEPX検証環境IP
JEPX_PORT = int(os.environ.get('JEPX_PORT', 0))  # JEPX検証環境Port
JEPX_MEMBER_ID = '9999'                           # 試験用会員ID
JEPX_TLS_VERIFY = True
# Mode B: JEPXルートCA証明書をファイルで指定
JEPX_TLS_CA_CERT = os.environ.get(
    'JEPX_TLS_CA_CERT',
    str(BASE_DIR / 'certs' / 'jepx_root_ca.pem'),
)
JEPX_ENVIRONMENT = 'stage'

# SSO バイパス設定 — True にすると Azure 認証をスキップし自動ログイン
DEV_SSO_BYPASS = False  # 検証環境では必ずAzure認証を行うため False に設定

# SharePoint有効
SHAREPOINT_ENABLED = True
