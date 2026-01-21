---
description: Deploy changes to production server
---

# Deploy to Production

You are now in deployment mode for the EzzyDelivery project. Reference `.claude/skills/deployment.md` for detailed patterns.

## Quick Reference

### Server Info
| Component | Details |
|-----------|---------|
| Server | Production (ezzydelivery.qa) |
| App Server | Gunicorn (gunicornezzy service) |
| Web Server | Nginx |
| CDN | Cloudflare |

### Deployment Commands

**Standard Deploy (No Downtime)**
```bash
# 1. Pull latest code
git pull origin master

# 2. Install any new dependencies
source ../venvezzy/bin/activate
pip install -r requirements.txt

# 3. Run migrations (if any)
python manage.py migrate

# 4. Collect static files
python manage.py collectstatic --noinput

# 5. Graceful reload
kill -HUP $(pgrep -f "gunicorn.*ezzydelivery" | head -1)
```

**Full Service Restart**
```bash
sudo systemctl restart gunicornezzy
```

### Verification
```bash
# Check service status
sudo systemctl status gunicornezzy

# Check site is accessible
curl -sI https://ezzydelivery.qa/

# Check recent logs
sudo journalctl -u gunicornezzy -n 50 --no-pager
```

### Rollback
```bash
# Find previous working commit
git log --oneline -5

# Revert to previous commit
git revert HEAD
# OR reset to specific commit
git reset --hard <commit-hash>

# Redeploy
python manage.py migrate
python manage.py collectstatic --noinput
kill -HUP $(pgrep -f "gunicorn.*ezzydelivery" | head -1)
```

## Checklist

### Pre-Deploy
- [ ] Tests passing locally
- [ ] `python manage.py check --deploy` shows no critical issues
- [ ] Reviewed changes with `git diff`

### Post-Deploy
- [ ] Site loads correctly
- [ ] No errors in logs
- [ ] Critical paths work (login, orders)

What would you like to deploy?
