# EzzyDelivery Deployment Skill

## Production Environment

### Server Stack
- **Web Server**: Nginx (reverse proxy)
- **App Server**: Gunicorn (gunicornezzy service)
- **Database**: PostgreSQL 15+
- **Cache/Broker**: Redis
- **Task Queue**: Celery
- **CDN**: Cloudflare

### Server Paths
```
/home/ezzyadmin/ezdlproject/
├── ezzydelivery/          # Django project root
│   ├── manage.py
│   ├── ezzydelivery/      # Settings module
│   ├── static/            # Development static files
│   └── staticfiles/       # Collected static files
└── venvezzy/              # Virtual environment
```

## Deployment Commands

### Quick Reload (No Downtime)
```bash
# Graceful Gunicorn reload - workers restart one at a time
kill -HUP $(pgrep -f "gunicorn.*ezzydelivery" | head -1)
```

### Full Service Restart
```bash
# Stop and restart Gunicorn service
sudo systemctl restart gunicornezzy

# Check service status
sudo systemctl status gunicornezzy

# View logs
sudo journalctl -u gunicornezzy -f --no-pager -n 100
```

### Database Migrations
```bash
# ALWAYS backup before migrations in production
# Run migrations
source ../venvezzy/bin/activate
python manage.py migrate

# Check migration status
python manage.py showmigrations
```

### Static Files
```bash
# Collect static files for production
python manage.py collectstatic --noinput

# If Cloudflare caching issues:
# Purge cache from Cloudflare dashboard or API
```

### Nginx Commands
```bash
# Test nginx config
sudo nginx -t

# Reload nginx
sudo systemctl reload nginx

# View nginx logs
sudo tail -f /var/log/nginx/error.log
```

## Deployment Checklist

### Pre-Deployment
- [ ] Run tests: `python manage.py test`
- [ ] Check for issues: `python manage.py check --deploy`
- [ ] Review migrations: `python manage.py showmigrations`
- [ ] Backup database if needed

### Deployment Steps
1. Pull latest code: `git pull origin master`
2. Install dependencies: `pip install -r requirements.txt`
3. Run migrations: `python manage.py migrate`
4. Collect static: `python manage.py collectstatic --noinput`
5. Reload Gunicorn: `kill -HUP $(pgrep -f "gunicorn.*ezzydelivery" | head -1)`

### Post-Deployment
- [ ] Verify site is accessible: `curl -sI https://ezzydelivery.qa/`
- [ ] Check for errors in logs: `sudo journalctl -u gunicornezzy -n 50`
- [ ] Test critical paths (login, orders, etc.)
- [ ] Monitor for 5-10 minutes

## Troubleshooting

### 502 Bad Gateway
```bash
# Check if Gunicorn is running
sudo systemctl status gunicornezzy

# Restart if needed
sudo systemctl restart gunicornezzy

# Check socket permissions
ls -la /run/gunicornezzy.sock
```

### Static Files 404
```bash
# Re-collect static files
python manage.py collectstatic --clear --noinput

# Check nginx static config
sudo nginx -t
```

### Database Connection Issues
```bash
# Check PostgreSQL status
sudo systemctl status postgresql

# Test connection
python manage.py dbshell
```

### Celery Not Processing Tasks
```bash
# Check Celery workers
sudo systemctl status celery

# Restart Celery
sudo systemctl restart celery

# Check Redis
redis-cli ping
```

## Environment Variables

Critical production settings in `/home/ezzyadmin/ezdlproject/ezzydelivery/.env`:
```
DEBUG=False
ALLOWED_HOSTS=ezzydelivery.qa,www.ezzydelivery.qa
SECRET_KEY=<production-secret>
DATABASE_URL=postgres://...
REDIS_URL=redis://localhost:6379/0
```

## Rollback Procedure

```bash
# If deployment fails, rollback to previous commit
git log --oneline -5  # Find previous working commit
git revert HEAD       # Revert last commit
# OR
git reset --hard <commit-hash>

# Then redeploy
python manage.py migrate
python manage.py collectstatic --noinput
kill -HUP $(pgrep -f "gunicorn.*ezzydelivery" | head -1)
```
