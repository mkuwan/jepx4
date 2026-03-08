"""本番環境 — JEPX本番接続 (§2.2.5)

TLS証明書:
  推奨: OSストアにJEPXルートCA証明書をインストールし、JEPX_TLS_CA_CERT は指定しない (Mode A)
  代替: JEPX_TLS_CA_CERT 環境変数でファイルパスを指定 (Mode B)
"""
import os
from .base import *  # noqa: F401,F403

DEBUG = False
ALLOWED_HOSTS = [os.environ['ALLOWED_HOST']]

# JEPX本番接続
JEPX_HOST = os.environ['JEPX_HOST']
JEPX_PORT = int(os.environ['JEPX_PORT'])
JEPX_MEMBER_ID = os.environ['JEPX_MEMBER_ID']    # 実会員ID
JEPX_TLS_VERIFY = True
# Mode A (OSストア): JEPX_TLS_CA_CERT 環境変数を未設定 → load_default_certs()
# Mode B (ファイル指定): JEPX_TLS_CA_CERT=/path/to/jepx_root_ca.pem を設定
JEPX_TLS_CA_CERT = os.environ.get('JEPX_TLS_CA_CERT', None)
JEPX_ENVIRONMENT = 'prod'

JEPX_RETRY_MAX = 5  # 本番は再試行回数を増やす

# SharePoint有効
SHAREPOINT_ENABLED = True

# 本番ではコンソールログを出さない
LOGGING['loggers']['jepx.api']['handlers'] = ['api_comm']
