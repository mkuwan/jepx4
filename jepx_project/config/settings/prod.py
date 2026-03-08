"""本番環境 — JEPX本番接続 (§2.2.5)"""
import os
from .base import *  # noqa: F401,F403

DEBUG = False
ALLOWED_HOSTS = [os.environ['ALLOWED_HOST']]

# JEPX本番接続
JEPX_HOST = os.environ['JEPX_HOST']
JEPX_PORT = int(os.environ['JEPX_PORT'])
JEPX_MEMBER_ID = os.environ['JEPX_MEMBER_ID']    # 実会員ID
JEPX_TLS_VERIFY = True
JEPX_TLS_CA_CERT = str(BASE_DIR / 'certs' / 'jepx_root_ca.pem')
JEPX_ENVIRONMENT = 'prod'

JEPX_RETRY_MAX = 5  # 本番は再試行回数を増やす

# SharePoint有効
SHAREPOINT_ENABLED = True

# 本番ではコンソールログを出さない
LOGGING['loggers']['jepx.api']['handlers'] = ['api_comm']
