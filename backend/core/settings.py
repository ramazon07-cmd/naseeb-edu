import secrets
import sys
from datetime import timedelta
from pathlib import Path
from corsheaders.defaults import default_headers
from decouple import config, Csv
from core.environment import (
    build_cache_settings,
    build_database_settings,
    direct_database_settings,
    is_enabled,
    resolve_app_environment,
    validate_runtime_environment,
    validate_storage_environment,
)
from core.observability import init_sentry
from core.storage_config import FILESYSTEM_STORAGE, build_storages

BASE_DIR = Path(__file__).resolve().parent.parent

HOSTED_RUNTIME = config('RENDER', default=False, cast=bool)
APP_ENV = resolve_app_environment(
    config('APP_ENV', default=''),
    hosted=HOSTED_RUNTIME,
    debug_requested=config('DEBUG', default=''),
    running_tests=len(sys.argv) > 1 and sys.argv[1] == 'test',
)
IS_PRODUCTION = APP_ENV == 'production'
# No shared default: production must supply SECRET_KEY (validated below); local
# development without one gets a random per-process key, so JWTs can't be forged.
SECRET_KEY = config('SECRET_KEY', default='').strip() or (
    '' if IS_PRODUCTION else 'dev-ephemeral-' + secrets.token_urlsafe(48)
)
DEBUG = config('DEBUG', default=not IS_PRODUCTION, cast=bool)
DATABASE_URL = config('DATABASE_URL', default='').strip()
DEMO_ACCOUNTS_ENABLED = config('ENABLE_DEMO_ACCOUNTS', default=not IS_PRODUCTION, cast=bool)
DEMO_COUNSELOR_PASSWORD = config('DEMO_COUNSELOR_PASSWORD', default='admin12345')
DEMO_ORGANIZATION_PASSWORD = config('DEMO_ORGANIZATION_PASSWORD', default='school12345')
DEMO_STUDENT_PASSWORD = config('DEMO_STUDENT_PASSWORD', default='student12345')
DEMO_PARENT_PASSWORD = config('DEMO_PARENT_PASSWORD', default='parent12345')
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1', cast=Csv())
MEDIA_ROOT_VALUE = config('MEDIA_ROOT', default='').strip()
DOCUMENT_STORAGE_ROOT_VALUE = config('DOCUMENT_STORAGE_ROOT', default='').strip()

# H8 assistant configuration. Provider credentials are backend-only secrets and
# must never be mirrored into a VITE_* build variable.
AI_ASSISTANT_ENABLED = config('AI_ASSISTANT_ENABLED', default=True, cast=bool)
AI_GATEWAY_API_KEY = config('AI_GATEWAY_API_KEY', default='').strip()
AI_GATEWAY_URL = config(
    'AI_GATEWAY_URL',
    default='https://ai-gateway.vercel.sh/v1/chat/completions',
).strip()
AI_ASSISTANT_MODEL = config('AI_ASSISTANT_MODEL', default='openai/gpt-5.4-mini').strip()
AI_ASSISTANT_FALLBACK_MODEL = config('AI_ASSISTANT_FALLBACK_MODEL', default='openai/gpt-5.4-nano').strip()
AI_ASSISTANT_MAX_MESSAGES = config('AI_ASSISTANT_MAX_MESSAGES', default=12, cast=int)
AI_ASSISTANT_MAX_INPUT_CHARS = config('AI_ASSISTANT_MAX_INPUT_CHARS', default=6000, cast=int)
AI_ASSISTANT_MAX_OUTPUT_TOKENS = config('AI_ASSISTANT_MAX_OUTPUT_TOKENS', default=450, cast=int)
AI_ASSISTANT_TIMEOUT_SECONDS = config('AI_ASSISTANT_TIMEOUT_SECONDS', default=35, cast=int)
# Long-lived assistant streams: a total time limit per reply (on top of the
# per-read timeout above), streams per gunicorn process (keep it below
# GUNICORN_THREADS so ordinary requests always find a thread) and per user.
AI_STREAM_MAX_SECONDS = config('AI_STREAM_MAX_SECONDS', default=60, cast=int)
AI_MAX_STREAMS_PER_PROCESS = config('AI_MAX_STREAMS_PER_PROCESS', default=4, cast=int)
AI_USER_MAX_CONCURRENT_STREAMS = config('AI_USER_MAX_CONCURRENT_STREAMS', default=2, cast=int)
# Daily cost caps for paid provider calls (0 = no cap): platform-wide, per school
# and per user. They need REDIS_URL to be shared by processes.
AI_ASSISTANT_DAILY_BUDGET = config('AI_ASSISTANT_DAILY_BUDGET', default=5000, cast=int)
AI_ASSISTANT_SCHOOL_DAILY_BUDGET = config('AI_ASSISTANT_SCHOOL_DAILY_BUDGET', default=1000, cast=int)
AI_ASSISTANT_USER_DAILY_LIMIT = config('AI_ASSISTANT_USER_DAILY_LIMIT', default=60, cast=int)
# Paid calls each process may still make per day while Redis is unreachable.
AI_FALLBACK_PROCESS_DAILY_BUDGET = config('AI_FALLBACK_PROCESS_DAILY_BUDGET', default=20, cast=int)
GROQ_API_KEY = config('GROQ_API_KEY', default='').strip()
GROQ_API_URL = config('GROQ_API_URL', default='https://api.groq.com/openai/v1/chat/completions').strip()
GROQ_RECOMMENDATION_MODEL = config('GROQ_RECOMMENDATION_MODEL', default='openai/gpt-oss-20b').strip()
AI_RECOMMENDATION_TIMEOUT_SECONDS = config('AI_RECOMMENDATION_TIMEOUT_SECONDS', default=30, cast=int)
# Essay Lab. The coach reuses the AI gateway credentials above.
ESSAY_COACH_MODEL = config('ESSAY_COACH_MODEL', default=AI_ASSISTANT_MODEL).strip()
ESSAY_COACH_TIMEOUT_SECONDS = config('ESSAY_COACH_TIMEOUT_SECONDS', default=40, cast=int)
ESSAY_COACH_MAX_OUTPUT_TOKENS = config('ESSAY_COACH_MAX_OUTPUT_TOKENS', default=1800, cast=int)
ESSAY_COACH_MAX_INPUT_CHARS = config('ESSAY_COACH_MAX_INPUT_CHARS', default=24000, cast=int)
# The platform-wide coach budget is required (0 = AI checks off); school and
# user caps use 0 = no cap.
ESSAY_COACH_DAILY_BUDGET = config('ESSAY_COACH_DAILY_BUDGET', default=5000, cast=int)
ESSAY_COACH_SCHOOL_DAILY_BUDGET = config('ESSAY_COACH_SCHOOL_DAILY_BUDGET', default=1000, cast=int)
ESSAY_COACH_USER_DAILY_LIMIT = config('ESSAY_COACH_USER_DAILY_LIMIT', default=40, cast=int)
ESSAY_COACH_MIN_INTERVAL_SECONDS = config('ESSAY_COACH_MIN_INTERVAL_SECONDS', default=15, cast=int)
ESSAY_COACH_HOURLY_LIMIT = config('ESSAY_COACH_HOURLY_LIMIT', default=120, cast=int)
ESSAY_AUTOSAVE_LIMIT = config('ESSAY_AUTOSAVE_LIMIT', default=1200, cast=int)
ESSAY_AUTOSAVE_WINDOW_SECONDS = config('ESSAY_AUTOSAVE_WINDOW_SECONDS', default=600, cast=int)
SCREEN_TIME_RETENTION_DAYS = config('SCREEN_TIME_RETENTION_DAYS', default=365, cast=int)
PUBLIC_REACH_MIN_CELL = config('PUBLIC_REACH_MIN_CELL', default=5, cast=int)
TEMPORARY_CREDENTIAL_TTL_HOURS = config('TEMPORARY_CREDENTIAL_TTL_HOURS', default=72, cast=int)
# Domain for students created without an email (.invalid never routes mail).
PLACEHOLDER_EMAIL_DOMAIN = config('PLACEHOLDER_EMAIL_DOMAIN', default='students.naseeb.invalid')

environment_errors = validate_runtime_environment(
    app_env=APP_ENV,
    debug=DEBUG,
    secret_key=SECRET_KEY,
    database_url=DATABASE_URL,
    demo_accounts_enabled=DEMO_ACCOUNTS_ENABLED,
    hosted=HOSTED_RUNTIME,
)
if environment_errors:
    message = 'Invalid runtime environment: ' + ' '.join(environment_errors)
    if not str(config('APP_ENV', default='')).strip() and not HOSTED_RUNTIME:
        message += (
            ' APP_ENV is not set, so the backend defaulted to production (fail-closed).'
            ' For local development run `cp backend/.env.example backend/.env`'
            ' (it sets APP_ENV=development) or export APP_ENV=development.'
        )
    raise RuntimeError(message)

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders',
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'drf_spectacular',
    'apps.users',
    'apps.admissions',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    # Before every middleware that rewrites the body, so compression runs last.
    'core.middleware.ApiGZipMiddleware',
    'apps.users.security.AdminIPAllowlistMiddleware',
    'apps.users.uploads.RequestSizeLimitMiddleware',
    'apps.users.middleware.StripNulQueryParamsMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'apps.users.middleware.ApiErrorLocalizationMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'

# Gunicorn runs gthread workers (see Procfile/Dockerfile); size the per-process
# PostgreSQL pool to the thread count so every request thread can hold a
# connection without waiting. Total connections per instance =
# WEB_CONCURRENCY x DB_POOL_MAX_SIZE; keep that under the database's limit.
GUNICORN_THREADS = config('GUNICORN_THREADS', default=8, cast=int)
DB_POOL_MIN_SIZE = config('DB_POOL_MIN_SIZE', default=2, cast=int)
DB_POOL_MAX_SIZE = config('DB_POOL_MAX_SIZE', default=8, cast=int)
DB_POOL_TIMEOUT = config('DB_POOL_TIMEOUT', default=10, cast=int)

# Set PGBOUNCER=1 (or DB_POOLER=pgbouncer) when DATABASE_URL points at PgBouncer
# in transaction mode. DIRECT_DATABASE_URL (the database itself, bypassing the
# pooler) is then used for migrations and scheduled-job locks.
DB_BEHIND_POOLER = is_enabled(config('PGBOUNCER', default='')) or is_enabled(config('DB_POOLER', default=''))
DIRECT_DATABASE_URL = config('DIRECT_DATABASE_URL', default='').strip()

if DATABASE_URL:
    DATABASES = {
        'default': build_database_settings(
            DATABASE_URL,
            pool_min=DB_POOL_MIN_SIZE,
            pool_max=DB_POOL_MAX_SIZE,
            pool_timeout=DB_POOL_TIMEOUT,
            conn_max_age=config('CONN_MAX_AGE', default=60, cast=int),
            behind_pooler=DB_BEHIND_POOLER,
        )
    }
    if DIRECT_DATABASE_URL:
        DATABASES['direct'] = direct_database_settings(DIRECT_DATABASE_URL)
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

AUTH_USER_MODEL = 'users.User'

# A shared cache is required for correct rate limits, login lockouts and the AI
# budget once more than one process serves traffic. Without REDIS_URL each
# process counts separately (fine for development and tests only).
REDIS_URL = config('REDIS_URL', default='').strip()
CACHES = build_cache_settings(
    REDIS_URL,
    key_prefix=config('CACHE_KEY_PREFIX', default='naseeb'),
    connect_timeout=config('REDIS_CONNECT_TIMEOUT', default=0.25, cast=float),
    socket_timeout=config('REDIS_SOCKET_TIMEOUT', default=0.25, cast=float),
    health_check_interval=config('REDIS_HEALTH_CHECK_INTERVAL', default=30, cast=int),
)

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'uz'
LANGUAGES = [
    ('uz', 'O‘zbekcha'),
    ('ru', 'Русский'),
    ('en', 'English'),
]
TIME_ZONE = 'Asia/Tashkent'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# ---------------------------------------------------------------------------
# File storage. STORAGE_BACKEND=filesystem (default) keeps uploads on the local
# disk, which only works for a single instance. STORAGE_BACKEND=s3 stores them
# in a private S3-compatible bucket (AWS S3 or Cloudflare R2), see
# docs/scaling.md "File storage".
# ---------------------------------------------------------------------------
STORAGE_BACKEND = config('STORAGE_BACKEND', default=FILESYSTEM_STORAGE).strip().lower()
# Production refuses local-disk storage unless this acknowledges one instance.
FILE_STORAGE_SINGLE_INSTANCE = config('FILE_STORAGE_SINGLE_INSTANCE', default=False, cast=bool)
AWS_STORAGE_BUCKET_NAME = config('AWS_STORAGE_BUCKET_NAME', default='').strip()
AWS_PRIVATE_STORAGE_BUCKET_NAME = config('AWS_PRIVATE_STORAGE_BUCKET_NAME', default='').strip()
AWS_S3_ENDPOINT_URL = config('AWS_S3_ENDPOINT_URL', default='').strip() or None
AWS_S3_REGION_NAME = config('AWS_S3_REGION_NAME', default='').strip() or None
AWS_ACCESS_KEY_ID = config('AWS_ACCESS_KEY_ID', default='').strip()
AWS_SECRET_ACCESS_KEY = config('AWS_SECRET_ACCESS_KEY', default='').strip()
AWS_S3_SIGNATURE_VERSION = 's3v4'
AWS_S3_ADDRESSING_STYLE = config('AWS_S3_ADDRESSING_STYLE', default='').strip() or None
# Empty = objects inherit the bucket's (private) policy; R2 and AWS buckets with
# ACLs disabled reject explicit ACL headers.
AWS_DEFAULT_ACL = config('AWS_DEFAULT_ACL', default='').strip() or None
AWS_MEDIA_LOCATION = config('AWS_MEDIA_LOCATION', default='media').strip('/ ')
AWS_PRIVATE_LOCATION = config('AWS_PRIVATE_LOCATION', default='private').strip('/ ')
# Lifetime of the presigned GET URLs handed out after authorisation.
PRIVATE_FILE_URL_EXPIRE_SECONDS = config('PRIVATE_FILE_URL_EXPIRE_SECONDS', default=60, cast=int)

storage_errors = validate_storage_environment(
    app_env=APP_ENV,
    backend=STORAGE_BACKEND,
    bucket=AWS_STORAGE_BUCKET_NAME,
    access_key=AWS_ACCESS_KEY_ID,
    secret_key=AWS_SECRET_ACCESS_KEY,
    media_root=MEDIA_ROOT_VALUE,
    document_storage_root=DOCUMENT_STORAGE_ROOT_VALUE,
    single_instance=FILE_STORAGE_SINGLE_INSTANCE,
)
if storage_errors:
    raise RuntimeError('Invalid runtime environment: ' + ' '.join(storage_errors))

STORAGES = build_storages(
    backend=STORAGE_BACKEND,
    s3_options={
        'bucket_name': AWS_STORAGE_BUCKET_NAME,
        'endpoint_url': AWS_S3_ENDPOINT_URL,
        'region_name': AWS_S3_REGION_NAME,
        'access_key': AWS_ACCESS_KEY_ID,
        'secret_key': AWS_SECRET_ACCESS_KEY,
        'signature_version': AWS_S3_SIGNATURE_VERSION,
        'addressing_style': AWS_S3_ADDRESSING_STYLE,
        'default_acl': AWS_DEFAULT_ACL,
        'querystring_expire': PRIVATE_FILE_URL_EXPIRE_SECONDS,
    },
    media_location=AWS_MEDIA_LOCATION,
    private_location=AWS_PRIVATE_LOCATION,
    private_bucket=AWS_PRIVATE_STORAGE_BUCKET_NAME,
)

MEDIA_URL = '/media/'
MEDIA_ROOT = Path(MEDIA_ROOT_VALUE).expanduser() if MEDIA_ROOT_VALUE else BASE_DIR / 'media'
DOCUMENT_STORAGE_ROOT = (
    Path(DOCUMENT_STORAGE_ROOT_VALUE).expanduser()
    if DOCUMENT_STORAGE_ROOT_VALUE
    else BASE_DIR / 'private_documents'
)
# Per-file cap checked while the upload streams in, before any file handler
# buffers it; larger files then spool to a temporary file and are streamed to
# the storage backend in chunks.
FILE_UPLOAD_HANDLERS = [
    'apps.users.uploads.FileSizeLimitUploadHandler',
    'django.core.files.uploadhandler.MemoryFileUploadHandler',
    'django.core.files.uploadhandler.TemporaryFileUploadHandler',
]
# --- end of file storage ---------------------------------------------------
DOCUMENT_MAX_UPLOAD_SIZE = config('DOCUMENT_MAX_UPLOAD_SIZE', default=25 * 1024 * 1024, cast=int)
DOCUMENT_ALLOWED_EXTENSIONS = tuple(config(
    'DOCUMENT_ALLOWED_EXTENSIONS',
    default='.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.csv,.rtf,.odt,.ods,.odp,.png,.jpg,.jpeg,.webp,.heic',
    cast=Csv(),
))

AVATAR_MAX_UPLOAD_SIZE = config('AVATAR_MAX_UPLOAD_SIZE', default=2 * 1024 * 1024, cast=int)
# Hard cap on any request body, enforced from Content-Length before it is read.
MAX_REQUEST_BODY_SIZE = config('MAX_REQUEST_BODY_SIZE', default=DOCUMENT_MAX_UPLOAD_SIZE + 1024 * 1024, cast=int)

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

CORS_ALLOWED_ORIGINS = config(
    'CORS_ALLOWED_ORIGINS',
    default='http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173',
    cast=Csv(),
)
CORS_ALLOW_CREDENTIALS = True
# Message polling revalidates with If-None-Match and reads the ETag back.
CORS_ALLOW_HEADERS = (*default_headers, 'if-none-match')
CORS_EXPOSE_HEADERS = ['ETag', 'X-Assistant-Source']
CSRF_TRUSTED_ORIGINS = [origin for origin in config('CSRF_TRUSTED_ORIGINS', default='', cast=Csv()) if origin]

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'apps.users.authentication.VersionedJWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_PAGINATION_CLASS': 'core.pagination.ListPagination',
    'PAGE_SIZE': 25,
    'DEFAULT_THROTTLE_CLASSES': (
        # O(1) window counters that fail open: a Redis outage must not 500 every request.
        'apps.users.throttles.AnonRateThrottle',
        'apps.users.throttles.UserRateThrottle',
    ),
    'DEFAULT_THROTTLE_RATES': {
        'anon': config('API_ANON_RATE', default='60/hour'),
        'user': config('API_USER_RATE', default='1200/hour'),
        'assistant': config('AI_ASSISTANT_RATE', default='20/hour'),
        # Sign-in is limited per (account, IP) and token refresh per token, with
        # only a generous per-IP ceiling (schools and carriers share IPs). The
        # account-wide ceiling slows distributed guessing; addresses that already
        # signed in to the account are exempt from it.
        'login': config('AUTH_LOGIN_RATE', default='10/minute'),
        'login_account': config('AUTH_LOGIN_ACCOUNT_RATE', default='60/minute'),
        'login_ip': config('AUTH_LOGIN_IP_RATE', default='300/minute'),
        'refresh': config('AUTH_REFRESH_RATE', default='30/hour'),
        'refresh_ip': config('AUTH_REFRESH_IP_RATE', default='600/minute'),
        'password_change': config('AUTH_PASSWORD_CHANGE_RATE', default='5/hour'),
        'credential_issue': config('AUTH_CREDENTIAL_ISSUE_RATE', default='20/hour'),
        'public_reach': config('PUBLIC_REACH_RATE', default='60/minute'),
    },
    # Number of trusted reverse proxies in front of Django (Render's edge = 1).
    # With 0, X-Forwarded-For is ignored and REMOTE_ADDR is used; never leave it
    # unset, or a client-chosen X-Forwarded-For becomes the throttle identity.
    'NUM_PROXIES': config('NUM_PROXIES', default=1 if IS_PRODUCTION else 0, cast=int),
}

# Per-account login lockout shared by /api/auth/token/ and /admin/login/.
LOGIN_LOCKOUT_THRESHOLD = config('LOGIN_LOCKOUT_THRESHOLD', default=10, cast=int)
LOGIN_LOCKOUT_WINDOW_SECONDS = config('LOGIN_LOCKOUT_WINDOW_SECONDS', default=900, cast=int)
# Failures for one account across all IPs that trigger a security warning in the logs.
LOGIN_ACCOUNT_ALERT_THRESHOLD = config('LOGIN_ACCOUNT_ALERT_THRESHOLD', default=50, cast=int)
# How long an address that signed in stays exempt from the account-wide login ceiling.
LOGIN_KNOWN_DEVICE_SECONDS = config('LOGIN_KNOWN_DEVICE_SECONDS', default=30 * 86400, cast=int)
# Optional comma-separated allowlist for the Django admin; empty = no IP restriction.
ADMIN_ALLOWED_IPS = [ip for ip in config('ADMIN_ALLOWED_IPS', default='', cast=Csv()) if ip]

SIMPLE_JWT = {
    # Short-lived access tokens limit the damage of a token stolen from
    # localStorage; the SPA renews them through the rotating refresh token.
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=config('JWT_ACCESS_TOKEN_MINUTES', default=30, cast=int)),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=config('JWT_REFRESH_TOKEN_DAYS', default=14, cast=int)),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'Naseeb Edu API',
    'DESCRIPTION': 'Education counseling platform for international university applications.',
    'VERSION': '1.0.0',
    'SERVE_PERMISSIONS': ['rest_framework.permissions.IsAuthenticated'],
    'ENUM_NAME_OVERRIDES': {
        'ApplicationStatusEnum': [
            ('researching', 'Researching'), ('shortlisted', 'Shortlisted'),
            ('applying', 'Applying'), ('submitted', 'Submitted'),
            ('accepted', 'Accepted'), ('rejected', 'Rejected'), ('waitlisted', 'Waitlisted'),
        ],
        'TaskStatusEnum': [
            ('todo', 'To Do'), ('in_progress', 'In Progress'), ('submitted', 'Submitted'),
            ('approved', 'Approved'), ('late', 'Late'),
        ],
        'DocumentStatusEnum': [
            ('required', 'Required'), ('uploaded', 'Uploaded'), ('reviewing', 'Reviewing'),
            ('approved', 'Approved'), ('rejected', 'Rejected'),
        ],
        'EssayStatusEnum': [
            ('draft', 'Draft'), ('needs_revision', 'Needs Revision'),
            ('reviewing', 'Reviewing'), ('approved', 'Approved'),
        ],
        'RecommendationStatusEnum': [
            ('requested', 'Requested'), ('drafting', 'Drafting'),
            ('submitted', 'Submitted'), ('approved', 'Approved'),
        ],
        'SchoolRegionEnum': [
            ('karakalpakstan', 'Republic of Karakalpakstan'), ('andijan', 'Andijan'),
            ('bukhara', 'Bukhara'), ('fergana', 'Fergana'), ('jizzakh', 'Jizzakh'),
            ('kashkadarya', 'Kashkadarya'), ('khorezm', 'Khorezm'), ('namangan', 'Namangan'),
            ('navoiy', 'Navoiy'), ('samarkand', 'Samarkand'), ('sirdaryo', 'Sirdaryo'),
            ('surkhandarya', 'Surkhandarya'), ('tashkent_region', 'Tashkent Region'),
            ('tashkent_city', 'Tashkent City'),
        ],
    },
}

FILE_UPLOAD_MAX_MEMORY_SIZE = config('FILE_UPLOAD_MAX_MEMORY_SIZE', default=5 * 1024 * 1024, cast=int)
DATA_UPLOAD_MAX_MEMORY_SIZE = config('DATA_UPLOAD_MAX_MEMORY_SIZE', default=10 * 1024 * 1024, cast=int)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'

if not DEBUG:
    SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=True, cast=bool)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = config('SECURE_HSTS_SECONDS', default=31536000, cast=int)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'

# Structured-enough logs for Render's log stream: one line per record on stdout.
LOG_LEVEL = config('LOG_LEVEL', default='INFO').upper()
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'line': {
            'format': '%(asctime)s %(levelname)s %(name)s [%(process)d:%(threadName)s] %(message)s',
        },
    },
    'handlers': {
        'console': {'class': 'logging.StreamHandler', 'formatter': 'line'},
    },
    'root': {'handlers': ['console'], 'level': LOG_LEVEL},
    'loggers': {
        'django': {'handlers': ['console'], 'level': LOG_LEVEL, 'propagate': False},
        # 4xx/5xx with tracebacks; keep even when LOG_LEVEL is raised.
        'django.request': {'handlers': ['console'], 'level': 'WARNING', 'propagate': False},
        'django.security': {'handlers': ['console'], 'level': 'WARNING', 'propagate': False},
        'django.db.backends': {'handlers': ['console'], 'level': 'WARNING', 'propagate': False},
        'apps': {'handlers': ['console'], 'level': LOG_LEVEL, 'propagate': False},
        'naseeb': {'handlers': ['console'], 'level': LOG_LEVEL, 'propagate': False},
    },
}

# Error reporting is off unless SENTRY_DSN is set.
SENTRY_ENABLED = init_sentry(
    config('SENTRY_DSN', default='').strip(),
    environment=config('SENTRY_ENVIRONMENT', default=APP_ENV),
    release=config('SENTRY_RELEASE', default=config('RENDER_GIT_COMMIT', default='')),
    traces_sample_rate=config('SENTRY_TRACES_SAMPLE_RATE', default=0.0, cast=float),
)
