"""基本設定 — 全環境共通 (§2.2.2)"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-insecure-key-change-in-production')

INSTALLED_APPS = [
    'django.contrib.contenttypes',
    'apps.jepx_client',
    'apps.dah_batch',
    'apps.itd_api',
    'apps.itn_stream',
    'apps.sharepoint',
    'apps.common',
]

MIDDLEWARE = []

ROOT_URLCONF = 'config.urls'

# ---- JEPX通信 共通設定 ----
JEPX_SOCKET_TIMEOUT_SEC = int(os.environ.get('JEPX_SOCKET_TIMEOUT_SEC', 30))
JEPX_KEEPALIVE_INTERVAL_SEC = int(os.environ.get('JEPX_KEEPALIVE_INTERVAL_SEC', 150))
JEPX_MAX_CONNECTIONS = 5           # 一般通信上限
JEPX_ITN_CONNECTIONS = 1           # 配信通信上限
JEPX_RETRY_MAX = 3
JEPX_RETRY_BACKOFF_BASE = 1       # 指数バックオフ基底(秒)

# ---- SharePoint連携 ----
GRAPH_API_TENANT_ID = os.environ.get('GRAPH_API_TENANT_ID', '')
GRAPH_API_CLIENT_ID = os.environ.get('GRAPH_API_CLIENT_ID', '')
GRAPH_API_CLIENT_SECRET = os.environ.get('GRAPH_API_CLIENT_SECRET', '')
SHAREPOINT_SITE_ID = os.environ.get('SHAREPOINT_SITE_ID', '')
SHAREPOINT_DRIVE_ID = os.environ.get('SHAREPOINT_DRIVE_ID', '')

# ---- ログ設定 ----
LOG_DIR = BASE_DIR / 'logs'
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'filters': {
        'masking': {
            '()': 'apps.common.logging.MaskingFilter',
        },
    },
    'formatters': {
        'audit': {
            'format': '{asctime} [{levelname}] [{name}] {message}',
            'style': '{',
        },
    },
    'handlers': {
        'api_comm': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(LOG_DIR / 'api_comm.log'),
            'maxBytes': 50 * 1024 * 1024,  # 50MB
            'backupCount': 30,
            'formatter': 'audit',
            'filters': ['masking'],
            'encoding': 'utf-8',
        },
        'audit': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(LOG_DIR / 'audit.log'),
            'maxBytes': 50 * 1024 * 1024,
            'backupCount': 30,
            'formatter': 'audit',
            'encoding': 'utf-8',
        },
        'error': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(LOG_DIR / 'error.log'),
            'maxBytes': 50 * 1024 * 1024,
            'backupCount': 30,
            'formatter': 'audit',
            'encoding': 'utf-8',
        },
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'audit',
        },
    },
    'loggers': {
        'jepx.api': {
            'handlers': ['api_comm'],
            'level': 'DEBUG',
        },
        'jepx.audit': {
            'handlers': ['audit'],
            'level': 'INFO',
        },
        'jepx.error': {
            'handlers': ['error'],
            'level': 'ERROR',
        },
    },
}

# ---- バリデーション ----
VALIDATION_FAIL_FAST = True  # 1件でもエラーならファイル全体を中断
