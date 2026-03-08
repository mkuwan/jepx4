"""開発環境 — MockServer接続 (§2.2.3)"""
from .base import *  # noqa: F401,F403

DEBUG = True
ALLOWED_HOSTS = ['*']

# MockServer接続
JEPX_HOST = '127.0.0.1'
JEPX_PORT = 8888
JEPX_MEMBER_ID = '9999'
JEPX_TLS_VERIFY = False          # 自己署名証明書許容
JEPX_TLS_CA_CERT = None
JEPX_ENVIRONMENT = 'dev'

# dev環境ではSharePoint不要（ローカルファイル利用可）
SHAREPOINT_ENABLED = False
INPUT_FILE_DIR = BASE_DIR / 'test_data' / 'input'
OUTPUT_FILE_DIR = BASE_DIR / 'test_data' / 'output'
ERROR_FILE_DIR = BASE_DIR / 'test_data' / 'error'

# コンソールログ追加
LOGGING['loggers']['jepx.api']['handlers'].append('console')
LOGGING['loggers']['jepx.audit']['handlers'].append('console')
LOGGING['root'] = {'handlers': ['console'], 'level': 'DEBUG'}
