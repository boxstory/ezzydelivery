
import os
import sys
from pathlib import Path
from decouple import config


# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config("SECRET_KEY")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config("DEBUG", cast=bool)

ALLOWED_HOSTS = config('ALLOWED_HOSTS', cast=lambda v: [s.strip() for s in v.split(',')])

# ==========================================
# SECURITY SETTINGS
# ==========================================
# These settings should be properly configured for production deployment

# HTTPS/SSL Settings (enable in production with HTTPS)
SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=False, cast=bool)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# HSTS (HTTP Strict Transport Security) - enable in production
SECURE_HSTS_SECONDS = config('SECURE_HSTS_SECONDS', default=0, cast=int)  # Set to 31536000 (1 year) in production
SECURE_HSTS_INCLUDE_SUBDOMAINS = config('SECURE_HSTS_INCLUDE_SUBDOMAINS', default=False, cast=bool)
SECURE_HSTS_PRELOAD = config('SECURE_HSTS_PRELOAD', default=False, cast=bool)

# Content Security
SECURE_CONTENT_TYPE_NOSNIFF = True
# SECURE_BROWSER_XSS_FILTER removed — deprecated since Django 4.0, has no effect
X_FRAME_OPTIONS = 'SAMEORIGIN'  # Allow framing from same origin (for dev tools)

# Cookie Security
CSRF_COOKIE_SECURE = config('CSRF_COOKIE_SECURE', default=False, cast=bool)  # True in production with HTTPS
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = 'Lax'
CSRF_TRUSTED_ORIGINS = config(
    'CSRF_TRUSTED_ORIGINS',
    default='http://localhost,http://127.0.0.1',
    cast=lambda v: [s.strip() for s in v.split(',')]
)

# Referrer Policy
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'

# Permissions Policy (formerly Feature-Policy)
PERMISSIONS_POLICY = {
    'geolocation': ['self'],
    'camera': [],
    'microphone': [],
    'payment': ['self'],
}
# ==========================================
# END SECURITY SETTINGS
# ==========================================


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.postgres',
    'django.contrib.sites',
    'django.contrib.sitemaps',
    
    
    # 3rdparty apps
    


    'allauth',
    'allauth.account',
    'allauth.socialaccount',

    # Social Auth Providers
    'allauth.socialaccount.providers.google',
    'allauth.socialaccount.providers.facebook',

    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'crispy_forms',
    'crispy_bootstrap5',
    'django_recaptcha',
    'fontawesomefree',
    'rest_framework',
    'rest_framework.authtoken',
    'drf_spectacular',
    'import_export',
    'geocoder',
    'django_initials_avatar', 

    # local apps
    'core',
    'webpages',
    'blog',
    'business',
    'product',
    'fleet',
    'delivery',
    'orders',
    'workforce',
    'ezzy_api',
    'warehouse',
    'dispatch',
    'ai_agent',
    'whatsapp',

]


CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"

CRISPY_TEMPLATE_PACK = "bootstrap5"

# SOCIALACCOUNT_PROVIDERS specific settings
SITE_ID = config('SITE_ID', default=1, cast=int)

SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'SCOPE': [
            'profile',
            'email',
        ],
        'AUTH_PARAMS': {
            'access_type': 'online',
        }
    },
    'facebook': {
        'METHOD': 'oauth2',
        # 'SDK_URL': '//connect.facebook.net/{locale}/sdk.js',
        'SCOPE': ['email', 'public_profile'],
        'AUTH_PARAMS': {'auth_type': 'reauthenticate'},
        'INIT_PARAMS': {'cookie': True},
        'FIELDS': [
            'id',
            'first_name',
            'last_name',
            'middle_name',
            'name',
            'name_format',
            'picture',
            'short_name'
        ],
        'EXCHANGE_TOKEN': True,
        # 'LOCALE_FUNC': 'path.to.callable',
        'VERIFIED_EMAIL': False,
        'VERSION': 'v7.0',
    }
}

# Authentication backends required for django-allauth
AUTHENTICATION_BACKENDS = [
    # Needed to login by username in Django admin, regardless of `allauth`
    'django.contrib.auth.backends.ModelBackend',
    # `allauth` specific authentication methods, such as login by email
    'allauth.account.auth_backends.AuthenticationBackend',
]

LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/'
LOGIN_URL = '/accounts/login/'

# Django-allauth settings (using latest allauth 0.50+ syntax)
ACCOUNT_LOGIN_METHODS = {'username', 'email'}  # Allow login with username or email
ACCOUNT_SIGNUP_FIELDS = ['email', 'username*', 'password1*', 'password2*']
ACCOUNT_EMAIL_VERIFICATION = "none"
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = True
ACCOUNT_LOGOUT_ON_GET = False  # Require POST for logout (security)
ACCOUNT_SESSION_REMEMBER = True  # Remember session
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_FORMS = {
    'signup': 'core.forms.CustomSignupForm',
}

# Session Configuration - Auto logout after 1 day of inactivity
SESSION_COOKIE_AGE = 86400  # 1 day in seconds (86400 seconds = 24 hours)
SESSION_SAVE_EVERY_REQUEST = True  # Refresh session on every request (updates last activity)
SESSION_EXPIRE_AT_BROWSER_CLOSE = False  # Keep session even after browser close
SESSION_COOKIE_SECURE = config('SESSION_COOKIE_SECURE', default=False, cast=bool)  # True in production with HTTPS
SESSION_COOKIE_HTTPONLY = True  # Prevent JavaScript access to session cookie
SESSION_COOKIE_SAMESITE = 'Lax'  # CSRF protection
SESSION_COOKIE_NAME = 'ezzy_sessionid'  # Custom session cookie name for added security

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'core.middleware.CloudflareIPMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',
    # Custom middleware for session timeout and auto-logout
    'core.middleware.SessionTimeoutMiddleware',
    'core.middleware.SessionWarningMiddleware',
    'core.middleware.NoCacheAuthMiddleware',
    # Fix 18: Force logout deactivated drivers accessing fleet pages
    'core.middleware.DriverStatusCheckMiddleware',
    # SQL query inspector - disabled (high CPU overhead per request in DEBUG mode)
    # 'core.middleware.QueryInspectorMiddleware',
    # Security headers for SEO (CSP + Permissions-Policy)
    'core.middleware.SecurityHeadersMiddleware',
]

# Add debug toolbar only in DEBUG mode (skip during tests as Django forces DEBUG=False)
TESTING = 'test' in sys.argv
if DEBUG and not TESTING:
    INSTALLED_APPS += ['debug_toolbar']
    MIDDLEWARE.insert(2, 'debug_toolbar.middleware.DebugToolbarMiddleware')

# The test client speaks plain HTTP; production .env flags would otherwise
# 301-redirect every test request and reject its cookies.
if TESTING:
    SECURE_SSL_REDIRECT = False
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False

ROOT_URLCONF = 'ezzydelivery.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.i18n',
                # SEO context processors for Qatar delivery keywords
                'core.context_processors.seo_defaults',
                'core.context_processors.site_info',
                # Social media and contact links
                'core.context_processors.social_media_links',
                # HTMX request detection
                'core.context_processors.htmx_request',
                # User profile to avoid duplicate queries
                'core.context_processors.user_profile',
                # User driver record for fleet profile links
                'core.context_processors.user_driver',
                # User business to avoid duplicate queries in sidebar
                'core.context_processors.user_business',
                # Business team permissions context
                'business.decorators.business_permissions_context',
                # Workforce dashboard sidebar counts
                'workforce.context_processors.workforce_sidebar_counts',
                # Fleet driver wallet status for COD warnings
                'fleet.context_processors.driver_wallet_status',
                # Fleet PWA bottom nav: pending tasks badge count
                'core.context_processors.driver_pending_tasks',
                'core.context_processors.dl_task_status_choices',
                # Google One Tap: exposes client_id to public templates
                'core.context_processors.google_one_tap',
            ],
        },
    },
]

WSGI_APPLICATION = 'ezzydelivery.wsgi.application'


 


# Database
# https://docs.djangoproject.com/en/3.2/ref/settings/#databases
DATABASES = {

    'default': {

        'ENGINE': 'django.db.backends.postgresql',

        'NAME': config('DB_NAME'),

        'USER': config('DB_USER'),

        'PASSWORD': config('DB_PASSWORD'),

        'HOST': 'localhost',

        'PORT': '',

    }

}


# Password validation
# https://docs.djangoproject.com/en/3.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/3.2/topics/i18n/

LANGUAGE_CODE = 'en'

from django.utils.translation import gettext_lazy as _
LANGUAGES = [
    ('en', _('English')),
    ('ar', _('العربية')),
]

LOCALE_PATHS = [
    os.path.join(BASE_DIR, 'locale'),
]

TIME_ZONE = 'Asia/Qatar'

USE_I18N = True

USE_L10N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/3.2/howto/static-files/

STATIC_URL = '/static/'

# Additional locations of static files (for development)
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'templates', 'static/'),
]

# For production: collectstatic will copy files here
STATIC_ROOT = os.path.join(BASE_DIR, 'staticroot/')

MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
MEDIA_URL = '/media/'


# Default primary key field type
# https://docs.djangoproject.com/en/3.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# ==========================================
# CACHE CONFIGURATION
# ==========================================
# Configure cache backend for sessions, rate limiting, and general caching
# For production, use Redis or Memcached

# Cache configuration - supports both local memory and Redis
_CACHE_BACKEND = config(
    'CACHE_BACKEND',
    default='django.core.cache.backends.locmem.LocMemCache'
)
_CACHE_OPTIONS = {}
# MAX_ENTRIES only applies to LocMemCache, not Redis
if 'locmem' in _CACHE_BACKEND.lower():
    _CACHE_OPTIONS['MAX_ENTRIES'] = 1000

CACHES = {
    'default': {
        'BACKEND': _CACHE_BACKEND,
        'LOCATION': config('CACHE_LOCATION', default='unique-snowflake'),
        'TIMEOUT': 300,  # 5 minutes default
        'OPTIONS': _CACHE_OPTIONS,
    }
}

# For Redis cache in production, add to .env:
# CACHE_BACKEND=django.core.cache.backends.redis.RedisCache
# CACHE_LOCATION=redis://127.0.0.1:6379/1
# ==========================================
# END CACHE CONFIGURATION
# ==========================================


# ==========================================
# GOOGLE reCAPTCHA CONFIGURATION
# ==========================================
RECAPTCHA_PUBLIC_KEY = config('RECAPTCHA_PUBLIC_KEY', default='')
RECAPTCHA_PRIVATE_KEY = config('RECAPTCHA_PRIVATE_KEY', default='')
NOCAPTCHA = True  # Use reCAPTCHA v2 checkbox ("I'm not a robot")
# ==========================================
# END reCAPTCHA CONFIGURATION
# ==========================================


# ==========================================
# RATE LIMITING CONFIGURATION
# ==========================================
# CloudflareIPMiddleware extracts IP from Cloudflare headers and sets REMOTE_ADDR.
# django-ratelimit will use the standard 'ip' key which reads REMOTE_ADDR.
# No need to set RATELIMIT_IP_META_KEY since REMOTE_ADDR is properly set by middleware.
# ==========================================
# END RATE LIMITING CONFIGURATION
# ==========================================


# ==========================================
# CELERY CONFIGURATION
# ==========================================
# Added: December 2024
# Purpose: Async task processing for batch timer engine
# ==========================================

CELERY_BROKER_URL = config('CELERY_BROKER_URL', default='redis://localhost:6379/0')
CELERY_RESULT_BACKEND = config('CELERY_RESULT_BACKEND', default='redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'Asia/Qatar'
CELERY_ENABLE_UTC = True
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 minutes max per task
CELERY_TASK_SOFT_TIME_LIMIT = 25 * 60  # Soft limit 25 minutes

# Celery Beat settings
CELERY_BEAT_SCHEDULER = 'celery.beat:PersistentScheduler'

from celery.schedules import crontab  # noqa: E402
CELERY_BEAT_SCHEDULE = {
    # Pull new orders from WooCommerce/Shopify/Google Sheets/OneDrive every 30 min
    'sync-all-temp-orders-every-30min': {
        'task': 'orders.tasks.sync_all_temp_orders',
        'schedule': crontab(minute='*/30'),
    },
}

# Task result expiration
CELERY_RESULT_EXPIRES = 3600  # 1 hour

# Worker settings
CELERY_WORKER_PREFETCH_MULTIPLIER = 1  # Fair task distribution
CELERY_WORKER_MAX_TASKS_PER_CHILD = 1000  # Restart worker after 1000 tasks

# ==========================================
# END CELERY CONFIGURATION
# ==========================================

# ==========================================
# GOOGLE SHEETS OAUTH2
# ==========================================
# Run scripts/google_sheets_auth.py once to generate the token file.
# After that the server auto-refreshes it — no browser needed again.
GOOGLE_SHEETS_CLIENT_ID     = config('GOOGLE_SHEETS_CLIENT_ID', default='')
GOOGLE_SHEETS_CLIENT_SECRET = config('GOOGLE_SHEETS_CLIENT_SECRET', default='')
GOOGLE_SHEETS_TOKEN_FILE    = config('GOOGLE_SHEETS_TOKEN_FILE', default='google_sheets_token.json')


# ==========================================
# DISPATCH & BATCHING CONFIGURATION
# ==========================================
# Added: December 2024
# Purpose: Order batching and dispatch optimization
# ==========================================

# Feature flag - set to True to enable batching system
DISPATCH_BATCHING_ENABLED = config('DISPATCH_BATCHING_ENABLED', default=False, cast=bool)

# Default batching parameters (can be overridden per pickup location)
DISPATCH_DEFAULT_HOLD_SECONDS = config('DISPATCH_DEFAULT_HOLD_SECONDS', default=180, cast=int)
DISPATCH_DEFAULT_SLA_MINUTES = config('DISPATCH_DEFAULT_SLA_MINUTES', default=60, cast=int)
DISPATCH_MAX_BATCH_SIZE = config('DISPATCH_MAX_BATCH_SIZE', default=2, cast=int)
DISPATCH_MAX_ORDERS_PER_RIDER = config('DISPATCH_MAX_ORDERS_PER_RIDER', default=2, cast=int)

# ==========================================
# END DISPATCH CONFIGURATION
# ==========================================


REST_FRAMEWORK = {
    'DEFAULT_SCHEMA_CLASS': 'ezzy_api.schema.UserTypeFilteredSchema',
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 10,
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'ezzy_api.authentication.ClientApiKeyAuthentication',
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
        'ezzy_api.permissions.ApiKeyScopePermission',
    ],
    # API Rate Limiting / Throttling
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',      # Anonymous users: 100 requests per hour
        'user': '1000/hour',     # Authenticated users: 1000 requests per hour
        'burst': '60/minute',    # Burst rate for specific endpoints
        'login': '10/min',       # Login attempts per (IP, username)
    },
    # API Versioning
    'DEFAULT_VERSIONING_CLASS': 'rest_framework.versioning.URLPathVersioning',
    'DEFAULT_VERSION': 'v1',
    'ALLOWED_VERSIONS': ['v1'],
    'VERSION_PARAM': 'version',
    # Exception handling
    'EXCEPTION_HANDLER': 'rest_framework.views.exception_handler',
    # Date/time format
    'DATETIME_FORMAT': '%Y-%m-%dT%H:%M:%S%z',
    'DATE_FORMAT': '%Y-%m-%d',
}

# ==========================================
# DRF SPECTACULAR CONFIGURATION (OpenAPI/Swagger)
# ==========================================
SPECTACULAR_SETTINGS = {
    'TITLE': 'EzzyDelivery API',
    'DESCRIPTION': 'API documentation for EzzyDelivery integrations with Shopify, WooCommerce, and TikTok Shop',
    'VERSION': '1.0.0',
    'SCHEMA_CLASS': 'ezzy_api.schema.UserTypeFilteredSchema',
    'SCHEMA_GENERATOR_CLASS': 'ezzy_api.schema.UserTypeFilteredSchemaGenerator',
    'SERVE_PERMISSIONS': ['rest_framework.permissions.IsAuthenticated'],
    'SCHEMA_PATH_PREFIX': '/api/v1/',
    'AUTHENTICATION_SCHEMES': [
        {
            'type': 'http',
            'scheme': 'bearer',
            'bearerFormat': 'Token',
            'description': 'Token-based authentication. Include "Token <your_api_key>" in Authorization header.',
        },
    ],
    'CONTACT': {
        'name': 'Support',
        'email': 'support@ezzydelivery.qa',
    },
}

import mimetypes
mimetypes.add_type("application/javascript", ".js", True)

INTERNAL_IPS = [
    "127.0.0.1",
]

def show_toolbar(request):
    return False

DEBUG_TOOLBAR_CONFIG = {
    'SHOW_TOOLBAR_CALLBACK': show_toolbar,
    'RENDER_PANELS': False,
    'DISABLE_PANELS': {
        'debug_toolbar.panels.redirects.RedirectsPanel',
        'debug_toolbar.panels.profiling.ProfilingPanel',
    },
}


# ==========================================
# LOGGING CONFIGURATION
# ==========================================
# Added: November 13, 2025
# Purpose: Replace print statements with proper logging
# Documentation: docs/critical-fixes/PRINT_STATEMENT_REMOVAL_PLAN.md
# ==========================================

# Create logs directory if it doesn't exist
LOGS_DIR = BASE_DIR / 'logs'
LOGS_DIR.mkdir(exist_ok=True)

# Windows doesn't support RotatingFileHandler with multithreaded dev server
# (can't rename open files). Use plain FileHandler on Windows.
import sys as _sys
_LOG_HANDLER_CLASS = (
    'logging.FileHandler' if _sys.platform == 'win32'
    else 'logging.handlers.RotatingFileHandler'
)
_LOG_HANDLER_EXTRA = {} if _sys.platform == 'win32' else {
    'maxBytes': 10 * 1024 * 1024,
    'backupCount': 5,
}

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,

    # ===== FORMATTERS =====
    'formatters': {
        'verbose': {
            'format': '[{levelname}] {asctime} {name} {module}.{funcName}:{lineno} - {message}',
            'style': '{',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
        'simple': {
            'format': '[{levelname}] {asctime} - {message}',
            'style': '{',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
    },

    # ===== FILTERS =====
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse',
        },
        'require_debug_true': {
            '()': 'django.utils.log.RequireDebugTrue',
        },
    },

    # ===== HANDLERS =====
    'handlers': {
        # Console output (for development)
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },

        # Debug log (only in DEBUG mode)
        'file_debug': {
            'level': 'DEBUG',
            'class': _LOG_HANDLER_CLASS,
            'filename': LOGS_DIR / 'debug.log',
            **_LOG_HANDLER_EXTRA,
            'formatter': 'verbose',
            'filters': ['require_debug_true'],
        },

        # Error log (all errors)
        'file_error': {
            'level': 'ERROR',
            'class': _LOG_HANDLER_CLASS,
            'filename': LOGS_DIR / 'error.log',
            **_LOG_HANDLER_EXTRA,
            'formatter': 'verbose',
        },

        # Orders-specific log
        'file_orders': {
            'level': 'INFO',
            'class': _LOG_HANDLER_CLASS,
            'filename': LOGS_DIR / 'orders.log',
            **_LOG_HANDLER_EXTRA,
            'formatter': 'verbose',
        },

        # Delivery-specific log
        'file_delivery': {
            'level': 'INFO',
            'class': _LOG_HANDLER_CLASS,
            'filename': LOGS_DIR / 'delivery.log',
            **_LOG_HANDLER_EXTRA,
            'formatter': 'verbose',
        },

        # API-specific log (Shopify, WooCommerce, DMS)
        'file_api': {
            'level': 'INFO',
            'class': _LOG_HANDLER_CLASS,
            'filename': LOGS_DIR / 'api.log',
            **_LOG_HANDLER_EXTRA,
            'formatter': 'verbose',
        },

        # Security log (authorization, authentication)
        'file_security': {
            'level': 'WARNING',
            'class': _LOG_HANDLER_CLASS,
            'filename': LOGS_DIR / 'security.log',
            **_LOG_HANDLER_EXTRA,
            'formatter': 'verbose',
        },

        # Query log (SQL queries and duplicates)
        'file_queries': {
            'level': 'DEBUG',
            'class': _LOG_HANDLER_CLASS,
            'filename': LOGS_DIR / 'queries.log',
            **_LOG_HANDLER_EXTRA,
            'formatter': 'verbose',
            'filters': ['require_debug_true'],
        },
    },

    # ===== LOGGERS =====
    'loggers': {
        # Django framework loggers
        'django': {
            'handlers': ['console', 'file_error'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['file_error'],
            'level': 'ERROR',
            'propagate': False,
        },
        'django.security.DisallowedHost': {
            'handlers': [],
            'propagate': False,
        },
        'django.db.backends': {
            # Log SQL queries in DEBUG mode (for N+1 query debugging)
            'handlers': ['file_queries'] if DEBUG else [],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        'queries': {
            # Custom query logger for duplicate detection
            'handlers': ['console', 'file_queries'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },

        # Application-specific loggers
        'orders': {
            'handlers': ['console', 'file_orders', 'file_error'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        'delivery': {
            'handlers': ['console', 'file_delivery', 'file_error'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        'business': {
            'handlers': ['console', 'file_error'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        'fleet': {
            'handlers': ['console', 'file_error'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        'ezzy_api': {
            'handlers': ['console', 'file_api', 'file_error'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        'core': {
            'handlers': ['console', 'file_error'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        'product': {
            'handlers': ['console', 'file_error'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        'webpages': {
            'handlers': ['console', 'file_error'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        'dispatch': {
            'handlers': ['console', 'file_delivery', 'file_error'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },

        # Security logger
        'security': {
            'handlers': ['file_security', 'file_error'],
            'level': 'WARNING',
            'propagate': False,
        },
    },

    # Root logger (catch-all)
    'root': {
        'handlers': ['console', 'file_error'],
        'level': 'INFO',
    },
}

# ==========================================
# END LOGGING CONFIGURATION
# ==========================================

# Shopify/WooCommerce product import forms embed 11 hidden fields per variant.
# 250 products × ~10 variants × 11 = ~27,500 fields — raise limit accordingly.
DATA_UPLOAD_MAX_NUMBER_FIELDS = 30000

# ==========================================
# AI AGENT CONFIGURATION
# ==========================================
# Added: January 2025
# Purpose: AI Operations Agent using Claude API
# ==========================================

# AI Provider API Keys
try:
    ANTHROPIC_API_KEY = config('ANTHROPIC_API_KEY') or ''
except Exception:
    ANTHROPIC_API_KEY = ''
try:
    OPENAI_API_KEY = config('OPENAI_API_KEY') or ''
except Exception:
    OPENAI_API_KEY = ''
try:
    GOOGLE_AI_API_KEY = config('GOOGLE_AI_API_KEY') or ''
except Exception:
    GOOGLE_AI_API_KEY = ''
try:
    XAI_API_KEY = config('XAI_API_KEY') or ''
except Exception:
    XAI_API_KEY = ''
try:
    GROQ_API_KEY = config('GROQ_API_KEY') or ''
except Exception:
    GROQ_API_KEY = ''
try:
    GLM_API_KEY = config('GLM_API_KEY') or ''
except Exception:
    GLM_API_KEY = ''

# Provider selection per use-case
AI_CHAT_PROVIDER          = config('AI_CHAT_PROVIDER', default='anthropic')
AI_CHAT_MODEL             = config('AI_CHAT_MODEL',    default='claude-sonnet-4-6')
AI_WA_PROVIDER            = config('AI_WA_PROVIDER',   default='anthropic')
AI_WA_MODEL               = config('AI_WA_MODEL',      default='claude-sonnet-4-6')
try:
    AI_CHAT_FALLBACK_PROVIDER = config('AI_CHAT_FALLBACK_PROVIDER', default='') or ''
except Exception:
    AI_CHAT_FALLBACK_PROVIDER = ''
try:
    AI_CHAT_FALLBACK_MODEL = config('AI_CHAT_FALLBACK_MODEL', default='') or ''
except Exception:
    AI_CHAT_FALLBACK_MODEL = ''
try:
    AI_WA_FALLBACK_PROVIDER = config('AI_WA_FALLBACK_PROVIDER', default='') or ''
except Exception:
    AI_WA_FALLBACK_PROVIDER = ''
try:
    AI_WA_FALLBACK_MODEL = config('AI_WA_FALLBACK_MODEL', default='') or ''
except Exception:
    AI_WA_FALLBACK_MODEL = ''

AI_AGENT_MODEL = config('AI_AGENT_MODEL', default='claude-sonnet-4-6')
AI_AGENT_MAX_TOKENS = config('AI_AGENT_MAX_TOKENS', default=4096, cast=int)

# Rate Limits (requests per minute)
AI_AGENT_RATE_LIMIT_USER = config('AI_AGENT_RATE_LIMIT_USER', default=50, cast=int)
AI_AGENT_RATE_LIMIT_BUSINESS = config('AI_AGENT_RATE_LIMIT_BUSINESS', default=200, cast=int)
AI_AGENT_RATE_LIMIT_GLOBAL = config('AI_AGENT_RATE_LIMIT_GLOBAL', default=1000, cast=int)

# Budget Limits (in USD)
AI_AGENT_DAILY_BUDGET = config('AI_AGENT_DAILY_BUDGET', default=50.0, cast=float)
AI_AGENT_MONTHLY_BUDGET = config('AI_AGENT_MONTHLY_BUDGET', default=1000.0, cast=float)
AI_AGENT_ALERT_PHONES = config('AI_AGENT_ALERT_PHONES', default='')  # Comma-separated WhatsApp alert recipients

# Feature Flags
AI_AGENT_ENABLED = config('AI_AGENT_ENABLED', default=True, cast=bool)
AI_AGENT_WHATSAPP_ENABLED = config('AI_AGENT_WHATSAPP_ENABLED', default=True, cast=bool)

# WhatsApp/n8n Integration
N8N_AI_AGENT_WEBHOOK_URL = config('N8N_AI_AGENT_WEBHOOK_URL', default='')
N8N_WHATSAPP_WEBHOOK_URL = config('N8N_WHATSAPP_WEBHOOK_URL', default='')
N8N_WEBHOOK_SECRET_KEY = config('N8N_WEBHOOK_SECRET_KEY', default='')

# Evolution API (WhatsApp)
EVOLUTION_URL = config('EVOLUTION_URL', default='')
EVOLUTION_API_KEY = config('EVOLUTION_API_KEY', default='')
EVOLUTION_INSTANCE = config('EVOLUTION_INSTANCE', default='')

# ==========================================
# END AI AGENT CONFIGURATION
# ==========================================


# ==========================================
# WAHA (self-hosted WhatsApp HTTP API)
# ==========================================
# Feature flag — when True, core/order_notifications.py routes outbound
# WhatsApp through WAHA instead of the legacy n8n webhook.
WAHA_ENABLED = config('WAHA_ENABLED', default=False, cast=bool)

# WAHA container endpoints + credentials
WAHA_BASE_URL = config('WAHA_BASE_URL', default='http://127.0.0.1:3000')
WAHA_API_KEY = config('WAHA_API_KEY', default='')
WAHA_WEBHOOK_HMAC_SECRET = config('WAHA_WEBHOOK_HMAC_SECRET', default='')
WAHA_DEFAULT_SESSION = config('WAHA_DEFAULT_SESSION', default='default')
WAHA_DEFAULT_FROM = config('WAHA_DEFAULT_FROM', default='EzzyDelivery')

# Bearer token used by internal callers of /api/integrations/waha/messages/
# and /api/integrations/waha/send/ (agent API + send proxy).
WAHA_AGENT_TOKEN = config('WAHA_AGENT_TOKEN', default='')

# Address verification queue (auto-import → WhatsApp link → customer location pin)
# - USE_WAHA: when True the verify-queue drain worker sends via WAHA so inbound
#   replies land on the WAHA webhook (independent of WAHA_ENABLED, which gates
#   order-notification routing platform-wide).
# - SEND_RATE: max verify-link messages per drain tick (per minute via beat).
# - PER_BUSINESS_MAX_PER_HOUR: rolling cap to spread sends across merchants.
# - MAX_ATTEMPTS: jobs flipped to status='failed' after this many failed sends.
# - MATCH_WINDOW_HOURS: inbound location pin auto-applies if within this many
#   hours of `sent_at`; older pins land in 'manual_review' for agent confirm.
WAHA_VERIFY_USE_WAHA = config('WAHA_VERIFY_USE_WAHA', default=False, cast=bool)
WAHA_VERIFY_SEND_RATE = config('WAHA_VERIFY_SEND_RATE', default=20, cast=int)
WAHA_VERIFY_PER_BUSINESS_MAX_PER_HOUR = config('WAHA_VERIFY_PER_BUSINESS_MAX_PER_HOUR', default=50, cast=int)
WAHA_VERIFY_MAX_ATTEMPTS = config('WAHA_VERIFY_MAX_ATTEMPTS', default=3, cast=int)
WAHA_VERIFY_MATCH_WINDOW_HOURS = config('WAHA_VERIFY_MATCH_WINDOW_HOURS', default=24, cast=int)
# Grace window after a driver marks a delivery failed before the recovery
# WhatsApp goes out. The driver (or staff) can undo the failed status during
# this window to auto-cancel the pending recovery job.
WAHA_DELIVERY_RECOVERY_DELAY_MINUTES = config('WAHA_DELIVERY_RECOVERY_DELAY_MINUTES', default=10, cast=int)
# ==========================================

