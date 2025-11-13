# EzzyDelivery Deployment Guide

This guide provides comprehensive instructions for deploying the EzzyDelivery Django application to production environments.

## Table of Contents

1. [Pre-Deployment Checklist](#pre-deployment-checklist)
2. [Production Settings Configuration](#production-settings-configuration)
3. [Database Setup and Migrations](#database-setup-and-migrations)
4. [Static Files and Media Configuration](#static-files-and-media-configuration)
5. [Environment Variables Setup](#environment-variables-setup)
6. [SSL/HTTPS Configuration](#sslhttps-configuration)
7. [Deployment Platforms](#deployment-platforms)
   - [AWS EC2 Deployment](#aws-ec2-deployment)
   - [DigitalOcean Deployment](#digitalocean-deployment)
   - [Heroku Deployment](#heroku-deployment)
8. [Post-Deployment Verification](#post-deployment-verification)
9. [Rollback Procedures](#rollback-procedures)
10. [Monitoring and Logging Setup](#monitoring-and-logging-setup)

---

## Pre-Deployment Checklist

Before deploying to production, ensure you have completed the following:

### Code Readiness
- [ ] All tests pass successfully
- [ ] Code has been reviewed and approved
- [ ] Database migrations are up to date
- [ ] Static files are collected and tested
- [ ] All environment variables are documented
- [ ] Security vulnerabilities have been addressed
- [ ] API integrations tested (Shopify, WooCommerce, Shipday, Mapbox)

### Infrastructure Readiness
- [ ] Production server is provisioned and accessible
- [ ] Database server is set up (PostgreSQL recommended)
- [ ] SSL certificate is obtained
- [ ] Domain name is configured
- [ ] Backup system is in place
- [ ] Monitoring tools are ready
- [ ] Log aggregation is configured

### Security Readiness
- [ ] SECRET_KEY is unique and secure
- [ ] DEBUG is set to False
- [ ] ALLOWED_HOSTS is properly configured
- [ ] Database credentials are secure
- [ ] All API keys are environment variables
- [ ] HTTPS is enforced
- [ ] Security headers are configured

---

## Production Settings Configuration

### 1. Create Production Settings File

Create a separate settings file for production or use environment-based configuration:

```python
# ezzydelivery/settings_prod.py or update settings.py

import os
from pathlib import Path
from decouple import config

BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY SETTINGS
SECRET_KEY = config('SECRET_KEY')
DEBUG = False  # CRITICAL: Always False in production
ALLOWED_HOSTS = config('ALLOWED_HOSTS', cast=lambda v: [s.strip() for s in v.split(',')])

# Security Middleware
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Remove debug toolbar in production
if 'debug_toolbar' in INSTALLED_APPS:
    INSTALLED_APPS.remove('debug_toolbar')
if 'debug_toolbar.middleware.DebugToolbarMiddleware' in MIDDLEWARE:
    MIDDLEWARE.remove('debug_toolbar.middleware.DebugToolbarMiddleware')
```

### 2. Database Configuration

```python
# Production Database Settings
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME'),
        'USER': config('DB_USER'),
        'PASSWORD': config('DB_PASSWORD'),
        'HOST': config('DB_HOST', default='localhost'),
        'PORT': config('DB_PORT', default='5432'),
        'CONN_MAX_AGE': 600,  # Connection pooling
        'OPTIONS': {
            'connect_timeout': 10,
        },
    }
}
```

### 3. Email Configuration

```python
# Email Settings for Production
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = config('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = True
EMAIL_HOST_USER = config('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL')
SERVER_EMAIL = config('SERVER_EMAIL')
```

### 4. Logging Configuration

```python
# Logging Configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': 'ERROR',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.path.join(BASE_DIR, 'logs', 'django.log'),
            'maxBytes': 1024*1024*15,  # 15MB
            'backupCount': 10,
            'formatter': 'verbose',
        },
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose'
        },
    },
    'root': {
        'handlers': ['console', 'file'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}
```

### 5. Cache Configuration

```python
# Redis Cache (recommended for production)
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': config('REDIS_URL', default='redis://127.0.0.1:6379/1'),
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        },
        'KEY_PREFIX': 'ezzydelivery',
        'TIMEOUT': 300,
    }
}

# Session Cache
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'default'
```

---

## Database Setup and Migrations

### 1. PostgreSQL Database Setup

```bash
# On the production server
sudo apt-get update
sudo apt-get install postgresql postgresql-contrib

# Create database and user
sudo -u postgres psql
```

```sql
CREATE DATABASE ezzy_dl_db;
CREATE USER ezzydelivery_user WITH PASSWORD 'your_secure_password';
ALTER ROLE ezzydelivery_user SET client_encoding TO 'utf8';
ALTER ROLE ezzydelivery_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE ezzydelivery_user SET timezone TO 'UTC';
GRANT ALL PRIVILEGES ON DATABASE ezzy_dl_db TO ezzydelivery_user;
\q
```

### 2. Run Migrations

```bash
# Activate virtual environment
source venv/bin/activate

# Run migrations
python manage.py makemigrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser
```

### 3. Load Initial Data (if applicable)

```bash
# Load fixtures
python manage.py loaddata initial_data.json

# Or use custom management commands
python manage.py setup_initial_data
```

---

## Static Files and Media Configuration

### 1. Collect Static Files

```bash
# Collect all static files
python manage.py collectstatic --noinput
```

### 2. Configure Static Files Serving

#### Option A: Using Nginx (Recommended)

```nginx
# /etc/nginx/sites-available/ezzydelivery

server {
    listen 80;
    server_name ezzydelivery.qa www.ezzydelivery.qa;

    # Redirect HTTP to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name ezzydelivery.qa www.ezzydelivery.qa;

    ssl_certificate /etc/letsencrypt/live/ezzydelivery.qa/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/ezzydelivery.qa/privkey.pem;

    client_max_body_size 20M;

    location /static/ {
        alias /var/www/ezzydelivery/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    location /media/ {
        alias /var/www/ezzydelivery/media/;
        expires 7d;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

#### Option B: Using WhiteNoise (Alternative)

```python
# settings.py
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # Add this
    # ... other middleware
]

STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
```

### 3. Media Files Storage

For production, consider using cloud storage:

```python
# AWS S3 Configuration (optional)
DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
AWS_ACCESS_KEY_ID = config('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = config('AWS_SECRET_ACCESS_KEY')
AWS_STORAGE_BUCKET_NAME = config('AWS_STORAGE_BUCKET_NAME')
AWS_S3_REGION_NAME = config('AWS_S3_REGION_NAME', default='us-east-1')
AWS_S3_CUSTOM_DOMAIN = f'{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com'
AWS_DEFAULT_ACL = 'public-read'
```

---

## Environment Variables Setup

### Production .env File Template

```bash
# Security
SECRET_KEY=your-super-secret-key-here-minimum-50-characters-long
DEBUG=False
ALLOWED_HOSTS=ezzydelivery.qa,www.ezzydelivery.qa,your-server-ip

# Database
DB_NAME=ezzy_dl_db
DB_USER=ezzydelivery_user
DB_PASSWORD=your-secure-database-password
DB_HOST=localhost
DB_PORT=5432

# Email Configuration
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=noreply@ezzydelivery.qa
EMAIL_HOST_PASSWORD=your-email-password
DEFAULT_FROM_EMAIL=EzzyDelivery <noreply@ezzydelivery.qa>
SERVER_EMAIL=admin@ezzydelivery.qa

# API Keys
TOOKAN_API_KEY=your-tookan-api-key
MAPBOX_API_KEY=your-mapbox-api-key
SHIPDAY_API_KEY=your-shipday-api-key
HERE_MAP_API_KEY=your-here-map-api-key

# Social Media
INSTAGRAM_TOKEN_FEEDS_KEY=your-instagram-token

# Redis (if using)
REDIS_URL=redis://127.0.0.1:6379/1

# AWS S3 (if using)
AWS_ACCESS_KEY_ID=your-aws-access-key
AWS_SECRET_ACCESS_KEY=your-aws-secret-key
AWS_STORAGE_BUCKET_NAME=ezzydelivery-media
AWS_S3_REGION_NAME=us-east-1

# Sentry (Error Tracking)
SENTRY_DSN=your-sentry-dsn-url
```

### Securing Environment Variables

```bash
# Set proper permissions
chmod 600 .env

# Add to .gitignore (already should be there)
echo ".env" >> .gitignore
```

---

## SSL/HTTPS Configuration

### Using Let's Encrypt (Recommended - Free)

```bash
# Install Certbot
sudo apt-get update
sudo apt-get install certbot python3-certbot-nginx

# Obtain SSL certificate
sudo certbot --nginx -d ezzydelivery.qa -d www.ezzydelivery.qa

# Auto-renewal (certbot sets this up automatically)
sudo certbot renew --dry-run
```

### SSL Settings in Django

Already covered in [Production Settings Configuration](#production-settings-configuration).

---

## Deployment Platforms

### AWS EC2 Deployment

#### 1. Launch EC2 Instance

```bash
# Choose Ubuntu Server 22.04 LTS
# Instance type: t3.medium or larger (recommended)
# Configure security group:
# - Port 22 (SSH)
# - Port 80 (HTTP)
# - Port 443 (HTTPS)
# - Port 5432 (PostgreSQL) - only if database on separate server
```

#### 2. Connect and Setup Server

```bash
# Connect to instance
ssh -i "your-key.pem" ubuntu@your-ec2-public-ip

# Update system
sudo apt-get update && sudo apt-get upgrade -y

# Install dependencies
sudo apt-get install -y python3-pip python3-dev python3-venv \
    libpq-dev postgresql postgresql-contrib nginx git
```

#### 3. Deploy Application

```bash
# Create application directory
sudo mkdir -p /var/www/ezzydelivery
sudo chown -R $USER:$USER /var/www/ezzydelivery

# Clone repository
cd /var/www/ezzydelivery
git clone https://github.com/your-repo/ezzydelivery.git .

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install gunicorn

# Setup environment variables
cp envsample .env
nano .env  # Edit with production values

# Run migrations
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser
```

#### 4. Configure Gunicorn

```bash
# Create gunicorn socket
sudo nano /etc/systemd/system/gunicorn.socket
```

```ini
[Unit]
Description=gunicorn socket

[Socket]
ListenStream=/run/gunicorn.sock

[Install]
WantedBy=sockets.target
```

```bash
# Create gunicorn service
sudo nano /etc/systemd/system/gunicorn.service
```

```ini
[Unit]
Description=gunicorn daemon
Requires=gunicorn.socket
After=network.target

[Service]
User=ubuntu
Group=www-data
WorkingDirectory=/var/www/ezzydelivery
Environment="PATH=/var/www/ezzydelivery/venv/bin"
ExecStart=/var/www/ezzydelivery/venv/bin/gunicorn \
          --access-logfile - \
          --workers 3 \
          --bind unix:/run/gunicorn.sock \
          ezzydelivery.wsgi:application

[Install]
WantedBy=multi-user.target
```

```bash
# Start and enable Gunicorn
sudo systemctl start gunicorn.socket
sudo systemctl enable gunicorn.socket
sudo systemctl status gunicorn.socket
```

#### 5. Configure Nginx

Use the Nginx configuration from [Static Files Configuration](#static-files-and-media-configuration).

```bash
# Create Nginx config
sudo nano /etc/nginx/sites-available/ezzydelivery

# Enable site
sudo ln -s /etc/nginx/sites-available/ezzydelivery /etc/nginx/sites-enabled/

# Test configuration
sudo nginx -t

# Restart Nginx
sudo systemctl restart nginx
```

#### 6. Setup SSL

```bash
# Install Certbot
sudo apt-get install certbot python3-certbot-nginx

# Obtain certificate
sudo certbot --nginx -d ezzydelivery.qa -d www.ezzydelivery.qa
```

---

### DigitalOcean Deployment

#### 1. Create Droplet

```bash
# Choose Ubuntu 22.04
# Recommended: 2GB RAM, 2 vCPUs
# Enable backups
# Add SSH key
```

#### 2. Initial Server Setup

```bash
# Connect to droplet
ssh root@your-droplet-ip

# Create new user
adduser ezzydelivery
usermod -aG sudo ezzydelivery
su - ezzydelivery

# Setup SSH key for new user
mkdir ~/.ssh
chmod 700 ~/.ssh
nano ~/.ssh/authorized_keys  # Paste your public key
chmod 600 ~/.ssh/authorized_keys
```

#### 3. Follow AWS Deployment Steps

The deployment process is similar to AWS EC2. Follow steps 2-6 from the [AWS EC2 Deployment](#aws-ec2-deployment) section.

#### 4. DigitalOcean Specific: Managed Database

```bash
# If using DigitalOcean Managed Database
# Get connection details from DigitalOcean dashboard

# Update .env
DB_HOST=your-db-host.db.ondigitalocean.com
DB_PORT=25060
DB_NAME=ezzy_dl_db
DB_USER=doadmin
DB_PASSWORD=your-managed-db-password
```

---

### Heroku Deployment

#### 1. Install Heroku CLI

```bash
# Install Heroku CLI
curl https://cli-assets.heroku.com/install.sh | sh

# Login
heroku login
```

#### 2. Prepare Application

```bash
# Create Procfile
echo "web: gunicorn ezzydelivery.wsgi --log-file -" > Procfile

# Create runtime.txt
python --version  # Check your version
echo "python-3.11.5" > runtime.txt  # Use your version

# Install additional dependencies
pip install gunicorn dj-database-url psycopg2-binary whitenoise
pip freeze > requirements.txt
```

#### 3. Update Settings for Heroku

```python
# Add to settings.py
import dj_database_url

# Heroku database configuration
if 'DATABASE_URL' in os.environ:
    DATABASES['default'] = dj_database_url.config(
        conn_max_age=600,
        ssl_require=True
    )

# WhiteNoise for static files
MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
```

#### 4. Deploy to Heroku

```bash
# Create Heroku app
heroku create ezzydelivery-app

# Add PostgreSQL addon
heroku addons:create heroku-postgresql:hobby-dev

# Set environment variables
heroku config:set SECRET_KEY="your-secret-key"
heroku config:set DEBUG=False
heroku config:set ALLOWED_HOSTS="ezzydelivery-app.herokuapp.com"
heroku config:set TOOKAN_API_KEY="your-tookan-key"
heroku config:set MAPBOX_API_KEY="your-mapbox-key"
heroku config:set SHIPDAY_API_KEY="your-shipday-key"
heroku config:set HERE_MAP_API_KEY="your-here-map-key"

# Deploy
git push heroku master

# Run migrations
heroku run python manage.py migrate

# Create superuser
heroku run python manage.py createsuperuser

# Open app
heroku open
```

---

## Post-Deployment Verification

### 1. Health Checks

```bash
# Test HTTP -> HTTPS redirect
curl -I http://ezzydelivery.qa

# Test HTTPS
curl -I https://ezzydelivery.qa

# Check application response
curl https://ezzydelivery.qa

# Test admin panel
curl -I https://ezzydelivery.qa/admin/
```

### 2. Verify Database Connectivity

```bash
# SSH into server
python manage.py dbshell

# Run a simple query
SELECT COUNT(*) FROM django_migrations;
\q
```

### 3. Check Static Files

```bash
# Verify static files are loading
curl -I https://ezzydelivery.qa/static/css/styles.css
```

### 4. Test API Endpoints

```bash
# Test API authentication
curl -X POST https://ezzydelivery.qa/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"username": "testuser", "password": "testpass"}'

# Test API endpoints
curl -H "Authorization: Token your-token" \
  https://ezzydelivery.qa/api/orders/
```

### 5. Verify Third-Party Integrations

- Test Shopify webhook endpoints
- Test WooCommerce integration
- Verify Mapbox map rendering
- Test Shipday API connectivity
- Check delivery management system integration

### 6. Performance Testing

```bash
# Install Apache Bench
sudo apt-get install apache2-utils

# Run load test
ab -n 1000 -c 10 https://ezzydelivery.qa/
```

---

## Rollback Procedures

### 1. Quick Rollback (Code)

```bash
# SSH into server
cd /var/www/ezzydelivery

# View git history
git log --oneline -10

# Rollback to previous version
git reset --hard <previous-commit-hash>

# Restart services
sudo systemctl restart gunicorn
sudo systemctl restart nginx
```

### 2. Database Rollback

```bash
# List migrations
python manage.py showmigrations

# Rollback specific migration
python manage.py migrate app_name migration_name

# Example: Rollback orders app to migration 0005
python manage.py migrate orders 0005
```

### 3. Complete Rollback with Backup

```bash
# Stop services
sudo systemctl stop gunicorn
sudo systemctl stop nginx

# Restore database from backup
sudo -u postgres psql
DROP DATABASE ezzy_dl_db;
CREATE DATABASE ezzy_dl_db;
\q

sudo -u postgres psql ezzy_dl_db < /backups/ezzy_dl_db_backup_YYYYMMDD.sql

# Restore code from backup
cd /var/www
mv ezzydelivery ezzydelivery_failed
tar -xzf /backups/ezzydelivery_backup_YYYYMMDD.tar.gz

# Start services
sudo systemctl start gunicorn
sudo systemctl start nginx
```

### 4. Deployment Checklist for Rollback

Create a pre-deployment backup:

```bash
#!/bin/bash
# backup.sh

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backups/$DATE"

mkdir -p $BACKUP_DIR

# Backup database
sudo -u postgres pg_dump ezzy_dl_db > $BACKUP_DIR/database.sql

# Backup code
tar -czf $BACKUP_DIR/code.tar.gz /var/www/ezzydelivery

# Backup media files
tar -czf $BACKUP_DIR/media.tar.gz /var/www/ezzydelivery/media

echo "Backup completed: $BACKUP_DIR"
```

---

## Monitoring and Logging Setup

### 1. Application Logging

```python
# Ensure logging is configured in settings.py (see Production Settings)

# Create logs directory
mkdir -p /var/www/ezzydelivery/logs
```

### 2. Nginx Logs

```bash
# Access logs
tail -f /var/log/nginx/access.log

# Error logs
tail -f /var/log/nginx/error.log

# Setup log rotation
sudo nano /etc/logrotate.d/nginx
```

### 3. Gunicorn Logs

```bash
# View Gunicorn logs
sudo journalctl -u gunicorn -f

# Save logs to file
sudo journalctl -u gunicorn > /var/log/gunicorn.log
```

### 4. Sentry Error Tracking (Recommended)

```bash
# Install Sentry SDK
pip install sentry-sdk
```

```python
# Add to settings.py
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration

if not DEBUG:
    sentry_sdk.init(
        dsn=config('SENTRY_DSN'),
        integrations=[DjangoIntegration()],
        traces_sample_rate=1.0,
        send_default_pii=True,
        environment='production',
    )
```

### 5. System Monitoring

```bash
# Install monitoring tools
sudo apt-get install htop iotop nethogs

# Monitor resources
htop  # CPU and memory
iotop  # Disk I/O
nethogs  # Network usage
```

### 6. Uptime Monitoring

Set up external monitoring:

- **UptimeRobot** (https://uptimerobot.com) - Free tier available
- **Pingdom** (https://www.pingdom.com)
- **StatusCake** (https://www.statuscake.com)

Configure alerts for:
- Application downtime
- Response time > 5 seconds
- SSL certificate expiration
- Disk space > 80%
- Memory usage > 90%

### 7. Database Monitoring

```bash
# Install pgAdmin or use command line

# Monitor active connections
sudo -u postgres psql
SELECT * FROM pg_stat_activity;

# Monitor database size
SELECT pg_size_pretty(pg_database_size('ezzy_dl_db'));
```

### 8. Automated Health Checks

```python
# Create management command: management/commands/health_check.py
from django.core.management.base import BaseCommand
from django.db import connection

class Command(BaseCommand):
    help = 'Check application health'

    def handle(self, *args, **options):
        try:
            # Check database
            connection.ensure_connection()
            self.stdout.write(self.style.SUCCESS('Database: OK'))

            # Add more checks
            # Check Redis, API connectivity, etc.

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Health check failed: {e}'))
            exit(1)
```

```bash
# Add to crontab
*/5 * * * * cd /var/www/ezzydelivery && venv/bin/python manage.py health_check >> /var/log/health_check.log 2>&1
```

---

## Continuous Deployment (Optional)

### Using GitHub Actions

Create `.github/workflows/deploy.yml`:

```yaml
name: Deploy to Production

on:
  push:
    branches: [ master ]

jobs:
  deploy:
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v2

    - name: Deploy to Server
      uses: appleboy/ssh-action@master
      with:
        host: ${{ secrets.SERVER_HOST }}
        username: ${{ secrets.SERVER_USER }}
        key: ${{ secrets.SSH_PRIVATE_KEY }}
        script: |
          cd /var/www/ezzydelivery
          git pull origin master
          source venv/bin/activate
          pip install -r requirements.txt
          python manage.py migrate
          python manage.py collectstatic --noinput
          sudo systemctl restart gunicorn
```

---

## Troubleshooting

### Common Issues

1. **502 Bad Gateway**
   - Check Gunicorn is running: `sudo systemctl status gunicorn`
   - Check socket permissions: `ls -l /run/gunicorn.sock`
   - View Gunicorn logs: `sudo journalctl -u gunicorn -n 50`

2. **Static Files Not Loading**
   - Run `python manage.py collectstatic --noinput`
   - Check Nginx configuration
   - Verify file permissions: `ls -l /var/www/ezzydelivery/static`

3. **Database Connection Errors**
   - Check PostgreSQL is running: `sudo systemctl status postgresql`
   - Verify credentials in .env
   - Check database exists: `sudo -u postgres psql -l`

4. **SSL Certificate Issues**
   - Renew certificate: `sudo certbot renew`
   - Check certificate status: `sudo certbot certificates`

---

## Support and Resources

- Django Deployment Documentation: https://docs.djangoproject.com/en/stable/howto/deployment/
- Gunicorn Documentation: https://docs.gunicorn.org/
- Nginx Documentation: https://nginx.org/en/docs/
- Let's Encrypt: https://letsencrypt.org/docs/

For project-specific issues, contact the development team.

---

**Document Version:** 1.0
**Last Updated:** 2025-11-13
**Maintained by:** EzzyDelivery Development Team
