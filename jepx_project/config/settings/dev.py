"""開発環境 — MockServer接続 (§2.2.3)

TLS証明書設定の2つの選択肢:
  選択肢1 (推奨): MockServer CA証明書を使用 → 全環境で同一TLSコードパスを通る
  選択肢2 (従来): 証明書検証を無効化 → 手軽だが本番との差異あり

切替方法: USE_MOCKSERVER_CERT を True / False に変更する
"""
from .base import *  # noqa: F401,F403

DEBUG = True
ALLOWED_HOSTS = ['*']

# -------------------------------------------------------
# ★ MockServer TLS設定 — 以下の切替で証明書利用を選択
# -------------------------------------------------------
USE_MOCKSERVER_CERT = True  # True: MockServer CA証明書で検証 / False: 検証なし

# MockServer接続
JEPX_HOST = '127.0.0.1'
JEPX_PORT = 8888
JEPX_MEMBER_ID = '9999'
JEPX_ENVIRONMENT = 'dev'

if USE_MOCKSERVER_CERT:
    # 選択肢1: MockServer CA証明書で検証 (推奨)
    # MockServer/certs/server.crt を jepx_project/certs/ にコピーして使用
    JEPX_TLS_VERIFY = True
    JEPX_TLS_CA_CERT = str(BASE_DIR / 'certs' / 'mockserver_ca.pem')
else:
    # 選択肢2: 証明書検証なし (レガシー互換)
    JEPX_TLS_VERIFY = False
    JEPX_TLS_CA_CERT = None

# dev環境ではSharePoint不要（ローカルファイル利用可）
SHAREPOINT_ENABLED = False
INPUT_FILE_DIR = BASE_DIR / 'test_data' / 'input'
OUTPUT_FILE_DIR = BASE_DIR / 'test_data' / 'output'
ERROR_FILE_DIR = BASE_DIR / 'test_data' / 'error'

# コンソールログ追加
LOGGING['loggers']['jepx.api']['handlers'].append('console')
LOGGING['loggers']['jepx.audit']['handlers'].append('console')
LOGGING['root'] = {'handlers': ['console'], 'level': 'DEBUG'}
