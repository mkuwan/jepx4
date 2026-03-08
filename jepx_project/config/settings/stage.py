"""検証環境 — JEPX検証環境接続 (§2.2.4)"""
import os
from .base import *  # noqa: F401,F403

DEBUG = False
ALLOWED_HOSTS = [os.environ.get('ALLOWED_HOST', '*')]

# JEPX検証環境接続
JEPX_HOST = os.environ.get('JEPX_HOST')         # JEPX検証環境IP
JEPX_PORT = int(os.environ.get('JEPX_PORT', 0))  # JEPX検証環境Port
JEPX_MEMBER_ID = '9999'                           # 試験用会員ID
JEPX_TLS_VERIFY = True
JEPX_TLS_CA_CERT = str(BASE_DIR / 'certs' / 'jepx_root_ca.pem')
JEPX_ENVIRONMENT = 'stage'

# SharePoint有効
SHAREPOINT_ENABLED = True
