# EzzyDelivery Configuration Guide

This comprehensive guide covers all configuration aspects of the EzzyDelivery Django application, including settings, environment variables, third-party integrations, and environment-specific configurations.

## Table of Contents

1. [Settings.py Configuration Guide](#settingspy-configuration-guide)
2. [Environment-Specific Settings](#environment-specific-settings)
3. [Database Configuration](#database-configuration)
4. [Email Configuration](#email-configuration)
5. [API Keys and Secrets Management](#api-keys-and-secrets-management)
6. [Third-Party Service Configuration](#third-party-service-configuration)
7. [Caching Configuration](#caching-configuration)
8. [Logging Configuration](#logging-configuration)
9. [Static and Media Files Configuration](#static-and-media-files-configuration)
10. [Security Settings](#security-settings)

---

## Settings.py Configuration Guide

### Core Settings

#### Base Configuration

```python
# ezzydelivery/settings.py

import os
from pathlib import Path
from decouple import config

# Build paths
BASE_DIR = Path(__file__).resolve().parent.parent

# Security settings
SECRET_KEY = config('SECRET_KEY')
DEBUG = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', cast=lambda v: [s.strip() for s in v.split(',')])

# Site Configuration
SITE_ID = 1
```

#### Installed Applications

```python
INSTALLED_APPS = [
    # Django Core Apps
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.sites',
    'django.contrib.sitemaps',
    'django.contrib.staticfiles',

    # Third-Party Apps
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    # Social providers (uncomment as needed)
    # 'allauth.socialaccount.providers.google',
    # 'allauth.socialaccount.providers.facebook',

    'crispy_forms',
    'crispy_bootstrap5',
    'fontawesomefree',
    'rest_framework',
    'rest_framework.authtoken',
    'import_export',
    'geocoder',

    # Development Tools (remove in production)
    'debug_toolbar',

    # Local Apps
    'core',
    'webpages',
    'business',
    'product',
    'fleet',
    'delivery',
    'orders',
    'workforce',
    'ezzy_api',
]
```

#### Middleware Configuration

```python
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',

    # Debug toolbar (development only)
    'debug_toolbar.middleware.DebugToolbarMiddleware',
]
```

#### Template Configuration

```python
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
                # Custom context processors
                'core.context_processors.seo_defaults',
                'core.context_processors.site_info',
            ],
        },
    },
]
```

---

## Environment-Specific Settings

### Development Settings

Create `ezzydelivery/settings_dev.py`:

```python
from .settings import *

# Development-specific settings
DEBUG = True
ALLOWED_HOSTS = ['127.0.0.1', 'localhost', '0.0.0.0']

# Database - SQLite for quick development (optional)
# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.sqlite3',
#         'NAME': BASE_DIR / 'db.sqlite3',
#     }
# }

# Email backend for development (prints to console)
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Debug Toolbar Settings
INTERNAL_IPS = [
    '127.0.0.1',
    'localhost',
]

DEBUG_TOOLBAR_CONFIG = {
    'SHOW_TOOLBAR_CALLBACK': lambda request: DEBUG,
    'INTERCEPT_REDIRECTS': False,
    'INSERT_BEFORE': '</head>',
    'RENDER_PANELS': True,
}

# Disable HTTPS redirects in development
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# CORS settings for API development
CORS_ALLOW_ALL_ORIGINS = True  # Only for development
```

**Usage:**
```bash
python manage.py runserver --settings=ezzydelivery.settings_dev
```

### Staging Settings

Create `ezzydelivery/settings_staging.py`:

```python
from .settings import *

# Staging-specific settings
DEBUG = False
ALLOWED_HOSTS = config('STAGING_ALLOWED_HOSTS', cast=lambda v: [s.strip() for s in v.split(',')])

# Use staging database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('STAGING_DB_NAME'),
        'USER': config('STAGING_DB_USER'),
        'PASSWORD': config('STAGING_DB_PASSWORD'),
        'HOST': config('STAGING_DB_HOST'),
        'PORT': config('STAGING_DB_PORT', default='5432'),
    }
}

# Email - use real SMTP but with staging domain
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = config('EMAIL_HOST')
EMAIL_PORT = config('EMAIL_PORT', cast=int)
EMAIL_USE_TLS = True
EMAIL_HOST_USER = config('STAGING_EMAIL_USER')
EMAIL_HOST_PASSWORD = config('STAGING_EMAIL_PASSWORD')

# Moderate security settings
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': os.path.join(BASE_DIR, 'logs', 'staging.log'),
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file'],
            'level': 'INFO',
            'propagate': True,
        },
    },
}
```

### Production Settings

Create `ezzydelivery/settings_prod.py`:

```python
from .settings import *

# Production settings
DEBUG = False
ALLOWED_HOSTS = config('ALLOWED_HOSTS', cast=lambda v: [s.strip() for s in v.split(',')])

# Remove debug toolbar
if 'debug_toolbar' in INSTALLED_APPS:
    INSTALLED_APPS.remove('debug_toolbar')
if 'debug_toolbar.middleware.DebugToolbarMiddleware' in MIDDLEWARE:
    MIDDLEWARE.remove('debug_toolbar.middleware.DebugToolbarMiddleware')

# Security settings
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# CSRF settings
CSRF_COOKIE_HTTPONLY = True
CSRF_USE_SESSIONS = True
CSRF_COOKIE_SAMESITE = 'Strict'
SESSION_COOKIE_SAMESITE = 'Strict'

# Production database with connection pooling
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME'),
        'USER': config('DB_USER'),
        'PASSWORD': config('DB_PASSWORD'),
        'HOST': config('DB_HOST', default='localhost'),
        'PORT': config('DB_PORT', default='5432'),
        'CONN_MAX_AGE': 600,
        'OPTIONS': {
            'connect_timeout': 10,
            'sslmode': 'require',  # If using SSL
        },
    }
}

# Production logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': 'ERROR',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.path.join(BASE_DIR, 'logs', 'production.log'),
            'maxBytes': 1024 * 1024 * 15,  # 15MB
            'backupCount': 10,
            'formatter': 'verbose',
        },
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console', 'file'],
        'level': 'WARNING',
    },
    'loggers': {
        'django': {
            'handlers': ['file'],
            'level': 'ERROR',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['file'],
            'level': 'ERROR',
            'propagate': False,
        },
    },
}

# Sentry integration (error tracking)
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration

sentry_sdk.init(
    dsn=config('SENTRY_DSN', default=''),
    integrations=[DjangoIntegration()],
    traces_sample_rate=0.1,
    send_default_pii=False,
    environment='production',
)
```

---

## Database Configuration

### PostgreSQL Configuration

#### Development Database

```python
# settings.py or settings_dev.py
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME', default='ezzy_dl_db'),
        'USER': config('DB_USER', default='zyadmin'),
        'PASSWORD': config('DB_PASSWORD'),
        'HOST': config('DB_HOST', default='localhost'),
        'PORT': config('DB_PORT', default='5432'),
    }
}
```

#### Production Database with Connection Pooling

```python
# settings_prod.py
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME'),
        'USER': config('DB_USER'),
        'PASSWORD': config('DB_PASSWORD'),
        'HOST': config('DB_HOST'),
        'PORT': config('DB_PORT', default='5432'),
        'CONN_MAX_AGE': 600,  # Keep connections alive for 10 minutes
        'OPTIONS': {
            'connect_timeout': 10,
            'keepalives': 1,
            'keepalives_idle': 30,
            'keepalives_interval': 10,
            'keepalives_count': 5,
        },
    }
}
```

#### Multiple Database Configuration

```python
# For read replicas or separate databases
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME'),
        'USER': config('DB_USER'),
        'PASSWORD': config('DB_PASSWORD'),
        'HOST': config('DB_HOST'),
        'PORT': '5432',
    },
    'read_replica': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME'),
        'USER': config('DB_READ_USER'),
        'PASSWORD': config('DB_READ_PASSWORD'),
        'HOST': config('DB_READ_HOST'),
        'PORT': '5432',
    }
}

# Database router for read/write splitting
DATABASE_ROUTERS = ['core.db_routers.ReadWriteRouter']
```

### Database Backup Configuration

```python
# settings.py
DBBACKUP_STORAGE = 'django.core.files.storage.FileSystemStorage'
DBBACKUP_STORAGE_OPTIONS = {'location': os.path.join(BASE_DIR, 'backups')}

# For S3 backups
# DBBACKUP_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
# DBBACKUP_STORAGE_OPTIONS = {
#     'access_key': config('AWS_ACCESS_KEY_ID'),
#     'secret_key': config('AWS_SECRET_ACCESS_KEY'),
#     'bucket_name': config('AWS_BACKUP_BUCKET_NAME'),
# }
```

---

## Email Configuration

### Development Email (Console Backend)

```python
# settings_dev.py
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
```

### SMTP Configuration (Gmail)

```python
# settings.py or settings_prod.py
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = config('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = True
EMAIL_HOST_USER = config('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD')  # Use App Password for Gmail
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='noreply@ezzydelivery.qa')
SERVER_EMAIL = config('SERVER_EMAIL', default='admin@ezzydelivery.qa')

# Additional email settings
EMAIL_TIMEOUT = 10
EMAIL_USE_LOCALTIME = True
```

### SendGrid Configuration

```python
# settings.py
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.sendgrid.net'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'apikey'  # Literal string 'apikey'
EMAIL_HOST_PASSWORD = config('SENDGRID_API_KEY')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL')
```

### Amazon SES Configuration

```python
# settings.py
EMAIL_BACKEND = 'django_ses.SESBackend'
AWS_ACCESS_KEY_ID = config('AWS_SES_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = config('AWS_SES_SECRET_ACCESS_KEY')
AWS_SES_REGION_NAME = config('AWS_SES_REGION_NAME', default='us-east-1')
AWS_SES_REGION_ENDPOINT = f'email.{AWS_SES_REGION_NAME}.amazonaws.com'
```

### Email Templates Configuration

```python
# settings.py
EMAIL_SUBJECT_PREFIX = '[EzzyDelivery] '

# Custom email templates directory
EMAIL_TEMPLATES_DIR = os.path.join(BASE_DIR, 'templates', 'emails')
```

---

## API Keys and Secrets Management

### Environment Variables (.env)

```bash
# .env file structure

# Core Settings
SECRET_KEY=your-secret-key-50-chars-minimum
DEBUG=False
ALLOWED_HOSTS=ezzydelivery.qa,www.ezzydelivery.qa

# Database
DB_NAME=ezzy_dl_db
DB_USER=zyadmin
DB_PASSWORD=secure_password_here
DB_HOST=localhost
DB_PORT=5432

# Email
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=noreply@ezzydelivery.qa
EMAIL_HOST_PASSWORD=your_email_app_password

# Delivery Management APIs
TOOKAN_API_KEY=your_tookan_api_key
SHIPDAY_API_KEY=your_shipday_api_key

# Mapping Services
MAPBOX_API_KEY=your_mapbox_api_key
HERE_MAP_API_KEY=your_here_map_api_key

# E-commerce Integrations
SHOPIFY_API_KEY=your_shopify_api_key
SHOPIFY_API_SECRET=your_shopify_secret
SHOPIFY_SHOP_NAME=your_shop_name
SHOPIFY_ACCESS_TOKEN=your_shopify_access_token

WOOCOMMERCE_URL=https://your-store.com
WOOCOMMERCE_CONSUMER_KEY=your_consumer_key
WOOCOMMERCE_CONSUMER_SECRET=your_consumer_secret

# Social Media
INSTAGRAM_TOKEN_FEEDS_KEY=your_instagram_token

# Payment Gateways (if applicable)
STRIPE_PUBLIC_KEY=your_stripe_public_key
STRIPE_SECRET_KEY=your_stripe_secret_key

# AWS (if using S3 or other services)
AWS_ACCESS_KEY_ID=your_aws_access_key
AWS_SECRET_ACCESS_KEY=your_aws_secret_key
AWS_STORAGE_BUCKET_NAME=ezzydelivery-media
AWS_S3_REGION_NAME=us-east-1

# Redis
REDIS_URL=redis://127.0.0.1:6379/1

# Sentry
SENTRY_DSN=your_sentry_dsn_url
```

### Loading Environment Variables

```python
# settings.py
from decouple import config, Csv

# String values
SECRET_KEY = config('SECRET_KEY')

# Boolean values
DEBUG = config('DEBUG', default=False, cast=bool)

# Integer values
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)

# List values
ALLOWED_HOSTS = config('ALLOWED_HOSTS', cast=Csv())
# Or custom parsing
ALLOWED_HOSTS = config('ALLOWED_HOSTS', cast=lambda v: [s.strip() for s in v.split(',')])

# Optional values with defaults
REDIS_URL = config('REDIS_URL', default='redis://127.0.0.1:6379/1')
```

### Secrets Management Best Practices

1. **Never commit .env to version control**
   ```bash
   # .gitignore
   .env
   .env.*
   !.env.example
   ```

2. **Use different .env files per environment**
   ```
   .env.development
   .env.staging
   .env.production
   ```

3. **Document required variables**
   ```bash
   # Create .env.example
   SECRET_KEY=
   DEBUG=True
   ALLOWED_HOSTS=localhost,127.0.0.1
   DB_NAME=ezzy_dl_db
   DB_USER=
   DB_PASSWORD=
   ```

4. **Use secrets management services for production**
   - AWS Secrets Manager
   - Azure Key Vault
   - HashiCorp Vault
   - Google Cloud Secret Manager

---

## Third-Party Service Configuration

### Shopify Integration

```python
# settings.py
SHOPIFY_CONFIG = {
    'API_KEY': config('SHOPIFY_API_KEY'),
    'API_SECRET': config('SHOPIFY_API_SECRET'),
    'SHOP_NAME': config('SHOPIFY_SHOP_NAME'),
    'ACCESS_TOKEN': config('SHOPIFY_ACCESS_TOKEN'),
    'API_VERSION': '2024-01',
    'WEBHOOK_SECRET': config('SHOPIFY_WEBHOOK_SECRET'),
}

# Webhook endpoints
SHOPIFY_WEBHOOK_TOPICS = [
    'orders/create',
    'orders/updated',
    'orders/cancelled',
    'orders/fulfilled',
]
```

**Usage in code:**
```python
# In views or services
from django.conf import settings
import shopify

shopify.ShopifyResource.set_site(
    f"https://{settings.SHOPIFY_CONFIG['SHOP_NAME']}.myshopify.com/admin/api/{settings.SHOPIFY_CONFIG['API_VERSION']}"
)
shopify.ShopifyResource.set_access_token(settings.SHOPIFY_CONFIG['ACCESS_TOKEN'])
```

### WooCommerce Integration

```python
# settings.py
WOOCOMMERCE_CONFIG = {
    'URL': config('WOOCOMMERCE_URL'),
    'CONSUMER_KEY': config('WOOCOMMERCE_CONSUMER_KEY'),
    'CONSUMER_SECRET': config('WOOCOMMERCE_CONSUMER_SECRET'),
    'VERSION': 'wc/v3',
    'TIMEOUT': 30,
}
```

**Usage in code:**
```python
from woocommerce import API
from django.conf import settings

wcapi = API(
    url=settings.WOOCOMMERCE_CONFIG['URL'],
    consumer_key=settings.WOOCOMMERCE_CONFIG['CONSUMER_KEY'],
    consumer_secret=settings.WOOCOMMERCE_CONFIG['CONSUMER_SECRET'],
    version=settings.WOOCOMMERCE_CONFIG['VERSION'],
    timeout=settings.WOOCOMMERCE_CONFIG['TIMEOUT']
)
```

### Shipday DMS Integration

```python
# settings.py
SHIPDAY_CONFIG = {
    'API_KEY': config('SHIPDAY_API_KEY'),
    'BASE_URL': 'https://api.shipday.com',
    'TIMEOUT': 30,
}
```

### Mapbox Configuration

```python
# settings.py
MAPBOX_CONFIG = {
    'ACCESS_TOKEN': config('MAPBOX_API_KEY'),
    'STYLE': 'mapbox://styles/mapbox/streets-v11',
    'DEFAULT_CENTER': [51.5074, 25.2769],  # Qatar coordinates
    'DEFAULT_ZOOM': 12,
}
```

### HERE Maps Configuration

```python
# settings.py
HERE_MAPS_CONFIG = {
    'API_KEY': config('HERE_MAP_API_KEY'),
    'BASE_URL': 'https://geocode.search.hereapi.com',
}
```

### Tookan Configuration

```python
# settings.py
TOOKAN_CONFIG = {
    'API_KEY': config('TOOKAN_API_KEY'),
    'BASE_URL': 'https://api.tookanapp.com',
}
```

---

## Caching Configuration

### Redis Cache (Recommended for Production)

```python
# settings.py
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': config('REDIS_URL', default='redis://127.0.0.1:6379/1'),
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'CONNECTION_POOL_KWARGS': {
                'max_connections': 50,
                'retry_on_timeout': True,
            },
            'SOCKET_CONNECT_TIMEOUT': 5,
            'SOCKET_TIMEOUT': 5,
        },
        'KEY_PREFIX': 'ezzydelivery',
        'TIMEOUT': 300,  # 5 minutes default
    }
}

# Session cache
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'default'
```

### Memcached Configuration

```python
# settings.py
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.memcached.PyMemcacheCache',
        'LOCATION': '127.0.0.1:11211',
        'OPTIONS': {
            'no_delay': True,
            'ignore_exc': True,
            'max_pool_size': 4,
            'use_pooling': True,
        }
    }
}
```

### File-Based Cache (Development)

```python
# settings_dev.py
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache',
        'LOCATION': os.path.join(BASE_DIR, 'cache'),
    }
}
```

### Cache Configuration for Different Use Cases

```python
# settings.py
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': config('REDIS_URL'),
        'KEY_PREFIX': 'ezzydelivery',
        'TIMEOUT': 300,
    },
    'sessions': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': config('REDIS_URL'),
        'KEY_PREFIX': 'session',
        'TIMEOUT': 86400,  # 24 hours
    },
    'api': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': config('REDIS_URL'),
        'KEY_PREFIX': 'api',
        'TIMEOUT': 600,  # 10 minutes
    }
}
```

---

## Logging Configuration

### Development Logging

```python
# settings_dev.py
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.db.backends': {
            'handlers': ['console'],
            'level': 'DEBUG',  # Log SQL queries
            'propagate': False,
        },
    },
}
```

### Production Logging

```python
# settings_prod.py
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'json': {
            '()': 'pythonjsonlogger.jsonlogger.JsonFormatter',
            'format': '%(asctime)s %(levelname)s %(name)s %(message)s'
        },
    },
    'handlers': {
        'file_error': {
            'level': 'ERROR',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.path.join(BASE_DIR, 'logs', 'error.log'),
            'maxBytes': 1024 * 1024 * 15,  # 15MB
            'backupCount': 10,
            'formatter': 'verbose',
        },
        'file_info': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.path.join(BASE_DIR, 'logs', 'info.log'),
            'maxBytes': 1024 * 1024 * 15,
            'backupCount': 5,
            'formatter': 'verbose',
        },
        'file_api': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.path.join(BASE_DIR, 'logs', 'api.log'),
            'maxBytes': 1024 * 1024 * 10,
            'backupCount': 5,
            'formatter': 'json',
        },
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console', 'file_error'],
        'level': 'WARNING',
    },
    'loggers': {
        'django': {
            'handlers': ['file_error'],
            'level': 'ERROR',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['file_error'],
            'level': 'ERROR',
            'propagate': False,
        },
        'ezzy_api': {
            'handlers': ['file_api', 'file_info'],
            'level': 'INFO',
            'propagate': False,
        },
        'orders': {
            'handlers': ['file_info'],
            'level': 'INFO',
            'propagate': False,
        },
        'delivery': {
            'handlers': ['file_info'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}
```

---

## Static and Media Files Configuration

### Development Configuration

```python
# settings_dev.py
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'static/')
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'assets'),  # Additional static files
]

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media/')
```

### Production with Nginx

```python
# settings_prod.py
STATIC_URL = '/static/'
STATIC_ROOT = '/var/www/ezzydelivery/static/'

MEDIA_URL = '/media/'
MEDIA_ROOT = '/var/www/ezzydelivery/media/'
```

### Production with WhiteNoise

```python
# settings_prod.py
MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')

STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
WHITENOISE_MAX_AGE = 31536000  # 1 year
```

### AWS S3 Configuration

```python
# settings_prod.py
# pip install django-storages boto3

DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
STATICFILES_STORAGE = 'storages.backends.s3boto3.S3StaticStorage'

AWS_ACCESS_KEY_ID = config('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = config('AWS_SECRET_ACCESS_KEY')
AWS_STORAGE_BUCKET_NAME = config('AWS_STORAGE_BUCKET_NAME')
AWS_S3_REGION_NAME = config('AWS_S3_REGION_NAME', default='us-east-1')
AWS_S3_CUSTOM_DOMAIN = f'{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com'
AWS_DEFAULT_ACL = 'public-read'
AWS_S3_OBJECT_PARAMETERS = {
    'CacheControl': 'max-age=86400',  # 1 day
}
AWS_LOCATION = 'static'
AWS_MEDIA_LOCATION = 'media'

STATIC_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/{AWS_LOCATION}/'
MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/{AWS_MEDIA_LOCATION}/'
```

---

## Security Settings

### Production Security Configuration

```python
# settings_prod.py

# HTTPS and SSL
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Cookies
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'

# HSTS
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Content Security
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = 'DENY'

# Additional security headers
SECURE_REFERRER_POLICY = 'same-origin'

# Password validators
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {
            'min_length': 12,
        }
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Session security
SESSION_COOKIE_AGE = 86400  # 24 hours
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
```

---

## REST Framework Configuration

```python
# settings.py
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
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
        'rest_framework.parsers.FormParser',
        'rest_framework.parsers.MultiPartParser',
    ],
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',
        'user': '1000/hour',
    },
    'DEFAULT_VERSIONING_CLASS': 'rest_framework.versioning.AcceptHeaderVersioning',
    'DEFAULT_VERSION': 'v1',
    'ALLOWED_VERSIONS': ['v1'],
}
```

---

## Configuration Checklist

### Development
- [ ] DEBUG = True
- [ ] Local database configuration
- [ ] Console email backend
- [ ] Debug toolbar enabled
- [ ] Permissive CORS settings
- [ ] File-based caching

### Staging
- [ ] DEBUG = False
- [ ] Staging database
- [ ] Real SMTP configuration
- [ ] Moderate security settings
- [ ] Test API keys
- [ ] File or Redis caching

### Production
- [ ] DEBUG = False
- [ ] Production database with connection pooling
- [ ] SMTP/SendGrid/SES configuration
- [ ] All security headers enabled
- [ ] Production API keys
- [ ] Redis caching
- [ ] Sentry integration
- [ ] Comprehensive logging
- [ ] HTTPS enforced
- [ ] Static files on CDN/S3

---

**Document Version:** 1.0
**Last Updated:** 2025-11-13
**Maintained by:** EzzyDelivery Development Team
