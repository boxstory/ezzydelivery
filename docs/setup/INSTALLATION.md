# EzzyDelivery Installation Guide

This guide provides step-by-step instructions for installing and setting up the EzzyDelivery Django application on your local development environment.

## Table of Contents

1. [System Requirements](#system-requirements)
2. [Python Installation](#python-installation)
3. [Dependencies Installation](#dependencies-installation)
4. [Virtual Environment Setup](#virtual-environment-setup)
5. [Database Setup](#database-setup)
6. [Configuration File Setup](#configuration-file-setup)
7. [Initial Data Migration](#initial-data-migration)
8. [Creating Superuser](#creating-superuser)
9. [Running Development Server](#running-development-server)
10. [Common Installation Issues](#common-installation-issues)

---

## System Requirements

### Minimum Requirements

- **Operating System:** Windows 10/11, macOS 10.14+, Ubuntu 20.04+, or similar Linux distribution
- **Python:** 3.9 or higher (3.11.x recommended)
- **RAM:** 4GB minimum (8GB recommended)
- **Disk Space:** 2GB free space
- **PostgreSQL:** 12 or higher (14+ recommended)
- **Git:** Latest version

### Recommended Development Tools

- **IDE/Editor:**
  - VS Code (with Python extension)
  - PyCharm Professional
  - Sublime Text with Python plugins
- **Browser:** Chrome, Firefox, or Edge (latest version)
- **API Testing:** Postman or Insomnia
- **Database Client:** pgAdmin 4, DBeaver, or TablePlus

---

## Python Installation

### Windows

1. **Download Python:**
   - Visit https://www.python.org/downloads/
   - Download Python 3.11.x (latest stable version)

2. **Install Python:**
   ```cmd
   # Run the installer
   # IMPORTANT: Check "Add Python to PATH" during installation
   # Select "Install Now"
   ```

3. **Verify Installation:**
   ```cmd
   python --version
   # Should output: Python 3.11.x

   pip --version
   # Should output: pip 23.x.x
   ```

### macOS

1. **Using Homebrew (Recommended):**
   ```bash
   # Install Homebrew if not already installed
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

   # Install Python
   brew install python@3.11

   # Add to PATH (add to ~/.zshrc or ~/.bash_profile)
   export PATH="/usr/local/opt/python@3.11/bin:$PATH"
   ```

2. **Verify Installation:**
   ```bash
   python3 --version
   pip3 --version
   ```

### Linux (Ubuntu/Debian)

1. **Install Python:**
   ```bash
   sudo apt update
   sudo apt install python3.11 python3.11-venv python3.11-dev python3-pip
   ```

2. **Verify Installation:**
   ```bash
   python3 --version
   pip3 --version
   ```

---

## Dependencies Installation

### Install PostgreSQL

#### Windows

1. **Download PostgreSQL:**
   - Visit https://www.postgresql.org/download/windows/
   - Download the installer for latest version (14.x or 15.x)

2. **Install PostgreSQL:**
   - Run installer
   - Remember the password you set for the `postgres` user
   - Default port: 5432

3. **Add to PATH:**
   ```cmd
   # Add PostgreSQL bin directory to PATH
   C:\Program Files\PostgreSQL\15\bin
   ```

#### macOS

```bash
# Using Homebrew
brew install postgresql@15

# Start PostgreSQL service
brew services start postgresql@15

# Verify installation
psql --version
```

#### Linux (Ubuntu/Debian)

```bash
# Install PostgreSQL
sudo apt update
sudo apt install postgresql postgresql-contrib

# Start PostgreSQL service
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Verify installation
psql --version
```

### Install Git

#### Windows
- Download from https://git-scm.com/download/win
- Run installer with default options

#### macOS
```bash
brew install git
```

#### Linux
```bash
sudo apt install git
```

### Install Additional System Dependencies

#### Linux (Ubuntu/Debian)
```bash
# Install development tools
sudo apt install build-essential libpq-dev libssl-dev libffi-dev python3-dev

# Install image processing libraries (for Pillow)
sudo apt install libjpeg-dev zlib1g-dev

# Install geocoding dependencies
sudo apt install libgdal-dev
```

#### macOS
```bash
# Install development tools
brew install postgresql openssl libffi

# Install image processing libraries
brew install jpeg zlib
```

---

## Virtual Environment Setup

Virtual environments isolate your project dependencies from system-wide Python packages.

### Create Virtual Environment

#### Windows

```cmd
# Navigate to project directory
cd C:\path\to\django-ezzydelivery\ezzydelivery

# Create virtual environment
python -m venv venv

# Activate virtual environment
venv\Scripts\activate

# Your prompt should now show (venv)
```

#### macOS/Linux

```bash
# Navigate to project directory
cd /path/to/django-ezzydelivery/ezzydelivery

# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Your prompt should now show (venv)
```

### Install Project Dependencies

```bash
# Ensure virtual environment is activated (you should see (venv) in prompt)

# Upgrade pip
pip install --upgrade pip

# Install all project dependencies
pip install -r requirements.txt

# Verify installation
pip list
```

### Key Dependencies Installed

The project includes the following major dependencies:

- **Django 5.1.7** - Web framework
- **djangorestframework 3.15.2** - REST API framework
- **psycopg2 2.9.10** - PostgreSQL adapter
- **django-allauth 65.5.0** - Authentication and social login
- **celery 5.4.0** - Asynchronous task queue
- **geocoder 1.38.1** - Geocoding services
- **geopy 2.4.1** - Geolocation services
- **ShopifyAPI 12.7.0** - Shopify integration
- **WooCommerce 3.0.0** - WooCommerce integration
- **shipday 1.4.4** - Shipday delivery integration
- **pillow 11.1.0** - Image processing
- **pandas 2.2.3** - Data analysis
- **django-import-export 4.3.7** - Data import/export

---

## Database Setup

### PostgreSQL Database Creation

#### Windows

```cmd
# Open Command Prompt or PowerShell

# Connect to PostgreSQL (enter password when prompted)
psql -U postgres

# Create database
CREATE DATABASE ezzy_dl_db;

# Create user
CREATE USER zyadmin WITH PASSWORD 'your_secure_password';

# Grant privileges
ALTER ROLE zyadmin SET client_encoding TO 'utf8';
ALTER ROLE zyadmin SET default_transaction_isolation TO 'read committed';
ALTER ROLE zyadmin SET timezone TO 'UTC';
GRANT ALL PRIVILEGES ON DATABASE ezzy_dl_db TO zyadmin;

# For PostgreSQL 15+, grant schema privileges
\c ezzy_dl_db
GRANT ALL ON SCHEMA public TO zyadmin;

# Exit psql
\q
```

#### macOS/Linux

```bash
# Connect to PostgreSQL
sudo -u postgres psql

# Or if you're the postgres user
psql postgres

# Create database
CREATE DATABASE ezzy_dl_db;

# Create user
CREATE USER zyadmin WITH PASSWORD 'your_secure_password';

# Grant privileges
ALTER ROLE zyadmin SET client_encoding TO 'utf8';
ALTER ROLE zyadmin SET default_transaction_isolation TO 'read committed';
ALTER ROLE zyadmin SET timezone TO 'UTC';
GRANT ALL PRIVILEGES ON DATABASE ezzy_dl_db TO zyadmin;

# For PostgreSQL 15+, grant schema privileges
\c ezzy_dl_db
GRANT ALL ON SCHEMA public TO zyadmin;

# Exit psql
\q
```

### Verify Database Connection

```bash
# Test connection
psql -U zyadmin -d ezzy_dl_db -h localhost

# If successful, you'll see the PostgreSQL prompt
ezzy_dl_db=>

# List databases
\l

# Exit
\q
```

---

## Configuration File Setup

### Create Environment Variables File

1. **Copy the sample environment file:**

```bash
# Navigate to project root
cd C:\00-web-dev\django-ezzydelivery\ezzydelivery  # Windows
# OR
cd /path/to/django-ezzydelivery/ezzydelivery  # macOS/Linux

# Copy the sample file
cp envsample .env  # macOS/Linux
copy envsample .env  # Windows
```

2. **Edit the .env file:**

```bash
# Open .env in your text editor
# VS Code
code .env

# Or any text editor
nano .env  # Linux/macOS
notepad .env  # Windows
```

3. **Configure the following variables:**

```bash
# Security Settings
SECRET_KEY=your-secret-key-min-50-chars-long-random-string
DEBUG=True
ALLOWED_HOSTS=127.0.0.1,localhost

# Database Configuration
DB_NAME=ezzy_dl_db
DB_USER=zyadmin
DB_PASSWORD=your_secure_password
DB_HOST=localhost
DB_PORT=5432

# API Keys (Development - use test keys)
TOOKAN_API_KEY=your-tookan-test-api-key
MAPBOX_API_KEY=your-mapbox-test-api-key
SHIPDAY_API_KEY=your-shipday-test-api-key
HERE_MAP_API_KEY=your-here-map-test-api-key

# Social Media (Optional for development)
INSTAGRAM_TOKEN_FEEDS_KEY=your-instagram-token

# Email Configuration (Optional for development)
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
```

### Generate Secret Key

```bash
# Activate virtual environment
source venv/bin/activate  # macOS/Linux
venv\Scripts\activate  # Windows

# Generate a secure secret key
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

# Copy the output and paste it as SECRET_KEY in .env
```

### Obtaining API Keys

#### Mapbox API Key
1. Visit https://www.mapbox.com/
2. Create a free account
3. Go to Account > Tokens
4. Create a new token or use the default public token
5. Copy the token to your .env file

#### Shipday API Key
1. Visit https://www.shipday.com/
2. Sign up for an account
3. Navigate to Settings > API
4. Generate an API key
5. Copy to your .env file

#### Tookan API Key
1. Visit https://jungleworks.com/tookan/
2. Sign up for an account
3. Go to Settings > API Keys
4. Copy your API key

#### HERE Maps API Key
1. Visit https://developer.here.com/
2. Create a free account
3. Create a new project
4. Generate API credentials
5. Copy the API key

---

## Initial Data Migration

### Run Database Migrations

```bash
# Ensure virtual environment is activated
# Ensure you're in the project root directory

# Check for any migration issues
python manage.py check

# Create migration files (if any new models)
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# You should see output like:
# Running migrations:
#   Applying contenttypes.0001_initial... OK
#   Applying auth.0001_initial... OK
#   Applying admin.0001_initial... OK
#   ...
```

### Verify Migrations

```bash
# List all migrations
python manage.py showmigrations

# Connect to database and verify tables
psql -U zyadmin -d ezzy_dl_db

# List all tables
\dt

# You should see Django tables and your app tables
# Exit
\q
```

### Load Initial Data (Optional)

If your project has initial data fixtures:

```bash
# Load fixtures
python manage.py loaddata initial_data.json

# Or load specific app fixtures
python manage.py loaddata core/fixtures/initial_data.json
python manage.py loaddata product/fixtures/categories.json
```

---

## Creating Superuser

Create an admin account to access the Django admin panel:

```bash
# Create superuser
python manage.py createsuperuser

# Follow the prompts:
# Username: admin
# Email address: admin@ezzydelivery.qa
# Password: [enter secure password]
# Password (again): [confirm password]

# Superuser created successfully.
```

### Test Admin Access

1. Start the development server (see next section)
2. Navigate to http://127.0.0.1:8000/admin/
3. Login with your superuser credentials
4. You should see the Django admin dashboard

---

## Running Development Server

### Start the Server

```bash
# Ensure virtual environment is activated
# Ensure you're in the project root directory

# Run the development server
python manage.py runserver

# Server will start on http://127.0.0.1:8000/
# Output:
# Watching for file changes with StatReloader
# Performing system checks...
#
# System check identified no issues (0 silenced).
# November 13, 2025 - 10:00:00
# Django version 5.1.7, using settings 'ezzydelivery.settings'
# Starting development server at http://127.0.0.1:8000/
# Quit the server with CONTROL-C.
```

### Run on Different Port

```bash
# Run on custom port
python manage.py runserver 8080

# Run on all network interfaces
python manage.py runserver 0.0.0.0:8000
```

### Access the Application

1. **Homepage:** http://127.0.0.1:8000/
2. **Admin Panel:** http://127.0.0.1:8000/admin/
3. **API Root:** http://127.0.0.1:8000/api/
4. **API Documentation:** http://127.0.0.1:8000/api/docs/ (if configured)

### Verify Installation

```bash
# Open a new terminal (keep the server running in the other terminal)

# Test the homepage
curl http://127.0.0.1:8000/

# Test the admin panel
curl -I http://127.0.0.1:8000/admin/

# Test API endpoint
curl http://127.0.0.1:8000/api/
```

---

## Common Installation Issues

### Issue 1: PostgreSQL Connection Error

**Error:**
```
django.db.utils.OperationalError: could not connect to server: Connection refused
```

**Solution:**
```bash
# Check if PostgreSQL is running
# Windows
# Open Services and start PostgreSQL service

# macOS
brew services start postgresql@15

# Linux
sudo systemctl start postgresql
sudo systemctl status postgresql

# Verify PostgreSQL port
sudo netstat -plnt | grep postgres  # Linux
lsof -i :5432  # macOS
netstat -an | findstr 5432  # Windows
```

### Issue 2: psycopg2 Installation Error

**Error:**
```
Error: pg_config executable not found.
```

**Solution:**

**Windows:**
```cmd
# Install PostgreSQL development files
# Download and install PostgreSQL from official website
# Make sure to include command line tools
```

**macOS:**
```bash
brew install postgresql
```

**Linux:**
```bash
sudo apt-get install libpq-dev python3-dev
pip install psycopg2-binary
```

### Issue 3: Pillow Installation Error

**Error:**
```
ValueError: jpeg is required unless explicitly disabled using --disable-jpeg
```

**Solution:**

**Windows:**
```cmd
# Install Pillow with pre-built binaries
pip install Pillow --upgrade
```

**macOS:**
```bash
brew install libjpeg zlib
pip install Pillow
```

**Linux:**
```bash
sudo apt-get install libjpeg-dev zlib1g-dev
pip install Pillow
```

### Issue 4: Permission Denied (Static/Media Directories)

**Error:**
```
PermissionError: [Errno 13] Permission denied: '/path/to/media'
```

**Solution:**
```bash
# Windows
# Right-click folder > Properties > Security > Edit permissions

# macOS/Linux
sudo chown -R $USER:$USER media/
sudo chown -R $USER:$USER static/
chmod -R 755 media/
chmod -R 755 static/
```

### Issue 5: Secret Key Error

**Error:**
```
django.core.exceptions.ImproperlyConfigured: The SECRET_KEY setting must not be empty.
```

**Solution:**
```bash
# Make sure .env file exists
ls -la .env

# Generate a new secret key
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

# Add to .env file
echo "SECRET_KEY=your-generated-key" >> .env
```

### Issue 6: ModuleNotFoundError

**Error:**
```
ModuleNotFoundError: No module named 'django'
```

**Solution:**
```bash
# Ensure virtual environment is activated
# Look for (venv) in your prompt

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate

# Reinstall requirements
pip install -r requirements.txt
```

### Issue 7: Migration Conflicts

**Error:**
```
django.db.migrations.exceptions.InconsistentMigrationHistory
```

**Solution:**
```bash
# Option 1: Reset migrations (DEVELOPMENT ONLY)
# Delete all migration files except __init__.py
find . -path "*/migrations/*.py" -not -name "__init__.py" -delete
find . -path "*/migrations/*.pyc" -delete

# Recreate migrations
python manage.py makemigrations
python manage.py migrate

# Option 2: Fake migrations (if database already has tables)
python manage.py migrate --fake
```

### Issue 8: Port Already in Use

**Error:**
```
Error: That port is already in use.
```

**Solution:**
```bash
# Find process using port 8000
# Windows
netstat -ano | findstr :8000
taskkill /PID <process_id> /F

# macOS/Linux
lsof -i :8000
kill -9 <process_id>

# Or run on different port
python manage.py runserver 8080
```

### Issue 9: ALLOWED_HOSTS Error

**Error:**
```
DisallowedHost at /
Invalid HTTP_HOST header: '192.168.1.100:8000'
```

**Solution:**
```bash
# Update .env file
ALLOWED_HOSTS=127.0.0.1,localhost,192.168.1.100

# Or temporarily in settings.py for development
ALLOWED_HOSTS = ['*']  # WARNING: Only for development
```

### Issue 10: Geocoder API Errors

**Error:**
```
GeocoderServiceError: HTTP Error 403: Forbidden
```

**Solution:**
```bash
# Verify API keys in .env file
# Check API key quotas and limits
# For development, consider using mock geocoding data

# Install required geocoding libraries
pip install geocoder geopy
```

---

## Next Steps

After successful installation:

1. **Configure the Application:**
   - Review `docs/setup/CONFIGURATION.md` for detailed configuration options
   - Set up API integrations (Shopify, WooCommerce, Shipday, etc.)
   - Configure email settings
   - Set up caching (Redis recommended)

2. **Explore the Application:**
   - Create test data through admin panel
   - Test order creation workflow
   - Test delivery management features
   - Explore API endpoints

3. **Development Tools:**
   - Install Django Debug Toolbar (already included)
   - Set up pre-commit hooks
   - Configure your IDE for Django development
   - Review `docs/VSCODE_SETUP_AND_WORKFLOW.md` for VS Code setup

4. **Read Documentation:**
   - API Documentation: `docs/api/`
   - Security Guidelines: `docs/security/`
   - Deployment Guide: `docs/setup/DEPLOYMENT_GUIDE.md`

---

## Useful Commands Reference

```bash
# Virtual Environment
source venv/bin/activate  # macOS/Linux
venv\Scripts\activate  # Windows
deactivate  # Exit virtual environment

# Django Management
python manage.py runserver  # Start development server
python manage.py shell  # Interactive Python shell
python manage.py dbshell  # Database shell
python manage.py test  # Run tests
python manage.py collectstatic  # Collect static files

# Database
python manage.py makemigrations  # Create migrations
python manage.py migrate  # Apply migrations
python manage.py showmigrations  # List migrations
python manage.py sqlmigrate app_name 0001  # Show SQL for migration

# Users
python manage.py createsuperuser  # Create admin user
python manage.py changepassword username  # Change password

# Data Management
python manage.py dumpdata > backup.json  # Backup data
python manage.py loaddata backup.json  # Restore data
python manage.py flush  # Clear database

# Custom Commands (if available)
python manage.py import_products  # Import products
python manage.py sync_shopify  # Sync Shopify data
python manage.py cleanup_old_deliveries  # Cleanup old data
```

---

## Support

If you encounter issues not covered in this guide:

1. Check the Django documentation: https://docs.djangoproject.com/
2. Review project-specific documentation in `docs/` directory
3. Search for similar issues in the project repository
4. Contact the development team
5. Check Django community resources:
   - Django Forum: https://forum.djangoproject.com/
   - Django Discord: https://discord.gg/xcRH6mN4fa
   - Stack Overflow: https://stackoverflow.com/questions/tagged/django

---

## Environment Verification Checklist

Use this checklist to verify your installation:

- [ ] Python 3.9+ installed
- [ ] PostgreSQL installed and running
- [ ] Virtual environment created and activated
- [ ] All dependencies installed (`pip list` shows Django and other packages)
- [ ] .env file created with all required variables
- [ ] Database created and accessible
- [ ] Migrations applied successfully
- [ ] Superuser created
- [ ] Development server starts without errors
- [ ] Admin panel accessible at http://127.0.0.1:8000/admin/
- [ ] Homepage loads without errors
- [ ] Static files loading correctly (CSS, JS, images)
- [ ] No console errors in browser developer tools

---

**Document Version:** 1.0
**Last Updated:** 2025-11-13
**Maintained by:** EzzyDelivery Development Team
