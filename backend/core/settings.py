from datetime import timedelta
from pathlib import Path
from decouple import config, Csv
import dj_database_url
from core.environment import validate_runtime_environment

BASE_DIR = Path(__file__).resolve().parent.parent

APP_ENV = config('APP_ENV', default='development').strip().lower()
IS_PRODUCTION = APP_ENV == 'production'
SECRET_KEY = config('SECRET_KEY', default='dev-only-naseeb-secret-key-change-in-production')
DEBUG = config('DEBUG', default=not IS_PRODUCTION, cast=bool)
DATABASE_URL = config('DATABASE_URL', default='').strip()
DEMO_ACCOUNTS_ENABLED = config('ENABLE_DEMO_ACCOUNTS', default=not IS_PRODUCTION, cast=bool)
DEMO_COUNSELOR_PASSWORD = config('DEMO_COUNSELOR_PASSWORD', default='admin12345')
DEMO_ORGANIZATION_PASSWORD = config('DEMO_ORGANIZATION_PASSWORD', default='school12345')
DEMO_STUDENT_PASSWORD = config('DEMO_STUDENT_PASSWORD', default='student12345')
DEMO_PARENT_PASSWORD = config('DEMO_PARENT_PASSWORD', default='parent12345')
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1', cast=Csv())

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
SCREEN_TIME_RETENTION_DAYS = config('SCREEN_TIME_RETENTION_DAYS', default=365, cast=int)
TEMPORARY_CREDENTIAL_TTL_HOURS = config('TEMPORARY_CREDENTIAL_TTL_HOURS', default=72, cast=int)

environment_errors = validate_runtime_environment(
    app_env=APP_ENV,
    debug=DEBUG,
    secret_key=SECRET_KEY,
    database_url=DATABASE_URL,
    demo_accounts_enabled=DEMO_ACCOUNTS_ENABLED,
)
if environment_errors:
    raise RuntimeError('Invalid runtime environment: ' + ' '.join(environment_errors))

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

if DATABASE_URL:
    DATABASES = {
        'default': dj_database_url.parse(DATABASE_URL, conn_max_age=600, ssl_require='sslmode=require' in DATABASE_URL)
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

AUTH_USER_MODEL = 'users.User'

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
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'},
}

MEDIA_URL = '/media/'
MEDIA_ROOT_VALUE = config('MEDIA_ROOT', default='').strip()
MEDIA_ROOT = Path(MEDIA_ROOT_VALUE).expanduser() if MEDIA_ROOT_VALUE else BASE_DIR / 'media'
DOCUMENT_STORAGE_ROOT_VALUE = config('DOCUMENT_STORAGE_ROOT', default='').strip()
DOCUMENT_STORAGE_ROOT = (
    Path(DOCUMENT_STORAGE_ROOT_VALUE).expanduser()
    if DOCUMENT_STORAGE_ROOT_VALUE
    else BASE_DIR / 'private_documents'
)
DOCUMENT_MAX_UPLOAD_SIZE = config('DOCUMENT_MAX_UPLOAD_SIZE', default=25 * 1024 * 1024, cast=int)
DOCUMENT_ALLOWED_EXTENSIONS = tuple(config(
    'DOCUMENT_ALLOWED_EXTENSIONS',
    default='.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.csv,.rtf,.odt,.ods,.odp,.png,.jpg,.jpeg,.webp,.heic',
    cast=Csv(),
))

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

CORS_ALLOWED_ORIGINS = config(
    'CORS_ALLOWED_ORIGINS',
    default='http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173',
    cast=Csv(),
)
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = [origin for origin in config('CSRF_TRUSTED_ORIGINS', default='', cast=Csv()) if origin]

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'apps.users.authentication.VersionedJWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 25,
    'DEFAULT_THROTTLE_CLASSES': (
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ),
    'DEFAULT_THROTTLE_RATES': {
        'anon': config('API_ANON_RATE', default='60/hour'),
        'user': config('API_USER_RATE', default='1200/hour'),
        'assistant': config('AI_ASSISTANT_RATE', default='20/hour'),
        'login': config('AUTH_LOGIN_RATE', default='10/minute'),
        'password_change': config('AUTH_PASSWORD_CHANGE_RATE', default='5/hour'),
        'credential_issue': config('AUTH_CREDENTIAL_ISSUE_RATE', default='20/hour'),
    },
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=8),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=14),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'Naseeb Edu API',
    'DESCRIPTION': 'Education counseling platform for international university applications.',
    'VERSION': '1.0.0',
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
