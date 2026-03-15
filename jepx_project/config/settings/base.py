"""基本設定 — 全環境共通 (§2.2.2)"""
import os
import yaml
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# --- SSO Configuration Load ---
# プロジェクトルート直下の .settings/sso_config.yml から認証情報を取得する
SSO_CONFIG_PATH = BASE_DIR / '.settings' / 'sso_config.yml'
sso_config = {}
if SSO_CONFIG_PATH.exists():
    with open(SSO_CONFIG_PATH, 'r', encoding='utf-8') as f:
        sso_config = yaml.safe_load(f) or {}

ENTRA_TENANT_ID = sso_config.get('ENTRA_TENANT_ID', os.environ.get('ENTRA_TENANT_ID', ''))
ENTRA_CLIENT_ID = sso_config.get('ENTRA_CLIENT_ID', os.environ.get('ENTRA_CLIENT_ID', ''))
ENTRA_CLIENT_SECRET = sso_config.get('ENTRA_CLIENT_SECRET', os.environ.get('ENTRA_CLIENT_SECRET', ''))

SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-insecure-key-change-in-production')

INSTALLED_APPS = [
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'apps.jepx_client',
    'apps.dah_batch',
    'apps.itd_api',
    'apps.itn_stream',
    'apps.sharepoint',
    'apps.common',
    'apps.web_ui', # Django Web GUI
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # 静的ファイル配信 (uvicorn/本番共通)
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

LANGUAGE_CODE = 'ja'
TIME_ZONE = 'Asia/Tokyo'
USE_I18N = True
USE_L10N = True
USE_TZ = True


# セッション管理（DBレス用: 暗号化署名Cookie）
SESSION_ENGINE = 'django.contrib.sessions.backends.signed_cookies'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
# collectstatic の出力先 (本番・検証環境での Nginx 配信ディレクトリ)
STATIC_ROOT = BASE_DIR / 'staticfiles'

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

# ---- ビジネスロジック・バリデーション制御 ----
# 取込ファイル内に1件でもエラーがあれば、正常な他レコードの処理も含めて処理全体を中断する Fail-Fast モード
VALIDATION_FAIL_FAST = True
