
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
SECURE_BROWSER_XSS_FILTER = True  # Legacy, but still useful for older browsers
X_FRAME_OPTIONS = 'DENY'  # Prevent clickjacking

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
    'crispy_forms',
    'crispy_bootstrap5',
    'fontawesomefree',
    'rest_framework',
    'rest_framework.authtoken',
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

# Session Configuration - Auto logout after 1 hour of inactivity
SESSION_COOKIE_AGE = 3600  # 1 hour in seconds (3600 seconds = 60 minutes)
SESSION_SAVE_EVERY_REQUEST = True  # Refresh session on every request (updates last activity)
SESSION_EXPIRE_AT_BROWSER_CLOSE = False  # Keep session even after browser close
SESSION_COOKIE_SECURE = config('SESSION_COOKIE_SECURE', default=False, cast=bool)  # True in production with HTTPS
SESSION_COOKIE_HTTPONLY = True  # Prevent JavaScript access to session cookie
SESSION_COOKIE_SAMESITE = 'Lax'  # CSRF protection
SESSION_COOKIE_NAME = 'ezzy_sessionid'  # Custom session cookie name for added security

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',
    # Custom middleware for session timeout and auto-logout
    'core.middleware.SessionTimeoutMiddleware',
    'core.middleware.SessionWarningMiddleware',
    # SQL query inspector - logs duplicate queries in DEBUG mode
    'core.middleware.QueryInspectorMiddleware',
]

# Add debug toolbar only in DEBUG mode (skip during tests as Django forces DEBUG=False)
TESTING = 'test' in sys.argv
if DEBUG and not TESTING:
    INSTALLED_APPS += ['debug_toolbar']
    MIDDLEWARE.insert(2, 'debug_toolbar.middleware.DebugToolbarMiddleware')

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
                # SEO context processors for Qatar delivery keywords
                'core.context_processors.seo_defaults',
                'core.context_processors.site_info',
                # Social media and contact links
                'core.context_processors.social_media_links',
                # HTMX request detection
                'core.context_processors.htmx_request',
                # User profile to avoid duplicate queries
                'core.context_processors.user_profile',
                # User business to avoid duplicate queries in sidebar
                'core.context_processors.user_business',
                # Business team permissions context
                'business.decorators.business_permissions_context',
                # Workforce dashboard sidebar counts
                'workforce.context_processors.workforce_sidebar_counts',
                # Fleet driver wallet status for COD warnings
                'fleet.context_processors.driver_wallet_status',
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

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

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

CACHES = {
    'default': {
        'BACKEND': config(
            'CACHE_BACKEND',
            default='django.core.cache.backends.locmem.LocMemCache'
        ),
        'LOCATION': config('CACHE_LOCATION', default='unique-snowflake'),
        'TIMEOUT': 300,  # 5 minutes default
        'OPTIONS': {
            'MAX_ENTRIES': 1000,
        }
    }
}

# For Redis cache in production, add to .env:
# CACHE_BACKEND=django.core.cache.backends.redis.RedisCache
# CACHE_LOCATION=redis://127.0.0.1:6379/1
# ==========================================
# END CACHE CONFIGURATION
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
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'

# Task result expiration
CELERY_RESULT_EXPIRES = 3600  # 1 hour

# Worker settings
CELERY_WORKER_PREFETCH_MULTIPLIER = 1  # Fair task distribution
CELERY_WORKER_MAX_TASKS_PER_CHILD = 1000  # Restart worker after 1000 tasks

# ==========================================
# END CELERY CONFIGURATION
# ==========================================


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
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 10,
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
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

import mimetypes
mimetypes.add_type("application/javascript", ".js", True)

DEBUG_TOOLBAR_PATCH_SETTINGS = False

INTERNAL_IPS = [
    "127.0.0.1",
]

def show_toolbar(request):
    if DEBUG:
        return True
    
DEBUG_TOOLBAR_CONFIG = {
'INTERCEPT_REDIRECTS': False,
"SHOW_TOOLBAR_CALLBACK": show_toolbar,
'INSERT_BEFORE': '</head>',
'INTERCEPT_REDIRECTS': False,
'RENDER_PANELS': True,
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
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'debug.log',
            'maxBytes': 10 * 1024 * 1024,  # 10 MB
            'backupCount': 5,
            'formatter': 'verbose',
            'filters': ['require_debug_true'],
        },

        # Error log (all errors)
        'file_error': {
            'level': 'ERROR',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'error.log',
            'maxBytes': 10 * 1024 * 1024,  # 10 MB
            'backupCount': 10,
            'formatter': 'verbose',
        },

        # Orders-specific log
        'file_orders': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'orders.log',
            'maxBytes': 10 * 1024 * 1024,  # 10 MB
            'backupCount': 5,
            'formatter': 'verbose',
        },

        # Delivery-specific log
        'file_delivery': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'delivery.log',
            'maxBytes': 10 * 1024 * 1024,  # 10 MB
            'backupCount': 5,
            'formatter': 'verbose',
        },

        # API-specific log (Shopify, WooCommerce, DMS)
        'file_api': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'api.log',
            'maxBytes': 10 * 1024 * 1024,  # 10 MB
            'backupCount': 5,
            'formatter': 'verbose',
        },

        # Security log (authorization, authentication)
        'file_security': {
            'level': 'WARNING',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'security.log',
            'maxBytes': 10 * 1024 * 1024,  # 10 MB
            'backupCount': 10,
            'formatter': 'verbose',
        },

        # Query log (SQL queries and duplicates)
        'file_queries': {
            'level': 'DEBUG',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'queries.log',
            'maxBytes': 10 * 1024 * 1024,  # 10 MB
            'backupCount': 3,
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


# ==========================================
# AI AGENT CONFIGURATION
# ==========================================
# Added: January 2025
# Purpose: AI Operations Agent using Claude API
# ==========================================

# Anthropic API Configuration
ANTHROPIC_API_KEY = config('ANTHROPIC_API_KEY', default='')
AI_AGENT_MODEL = config('AI_AGENT_MODEL', default='claude-sonnet-4-20250514')
AI_AGENT_MAX_TOKENS = config('AI_AGENT_MAX_TOKENS', default=4096, cast=int)

# Rate Limits (requests per minute)
AI_AGENT_RATE_LIMIT_USER = config('AI_AGENT_RATE_LIMIT_USER', default=50, cast=int)
AI_AGENT_RATE_LIMIT_BUSINESS = config('AI_AGENT_RATE_LIMIT_BUSINESS', default=200, cast=int)
AI_AGENT_RATE_LIMIT_GLOBAL = config('AI_AGENT_RATE_LIMIT_GLOBAL', default=1000, cast=int)

# Budget Limits (in USD)
AI_AGENT_DAILY_BUDGET = config('AI_AGENT_DAILY_BUDGET', default=50.0, cast=float)
AI_AGENT_MONTHLY_BUDGET = config('AI_AGENT_MONTHLY_BUDGET', default=1000.0, cast=float)

# Feature Flags
AI_AGENT_ENABLED = config('AI_AGENT_ENABLED', default=True, cast=bool)
AI_AGENT_WHATSAPP_ENABLED = config('AI_AGENT_WHATSAPP_ENABLED', default=True, cast=bool)

# WhatsApp/n8n Integration
N8N_AI_AGENT_WEBHOOK_URL = config('N8N_AI_AGENT_WEBHOOK_URL', default='')
N8N_WHATSAPP_WEBHOOK_URL = config('N8N_WHATSAPP_WEBHOOK_URL', default='')
N8N_WEBHOOK_SECRET_KEY = config('N8N_WEBHOOK_SECRET_KEY', default='')

# ==========================================
# END AI AGENT CONFIGURATION
# ==========================================

