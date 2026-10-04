#!/usr/bin/env bash
# Purpose: One-off root fix — stop nginx exposing WAHA's chat API, and give gunicorn threads so slow WAHA calls stop queueing sends.
# Used by: run once by hand: sudo bash scripts/waha_lockdown_and_threads.sh
# Notes: Backs up both files with a timestamp, validates, health-checks, and restores the backup if anything fails.
set -euo pipefail

NGINX_SITE=/etc/nginx/sites-available/ezzydelivery
UNIT=/etc/systemd/system/gunicornezzy.service
STAMP=$(date +%Y%m%d-%H%M%S)

[ "$(id -u)" = 0 ] || { echo "Run with sudo."; exit 1; }

health() { curl -s -o /dev/null -w '%{http_code}' --max-time 15 https://ezzydelivery.qa/ ; }

# ---- 1. nginx: only session status / QR / media files pass through to WAHA ----
cp -a "$NGINX_SITE" "$NGINX_SITE.bak.$STAMP"
python3 - "$NGINX_SITE" <<'PY'
import re, sys
path = sys.argv[1]
s = open(path).read()
if 'api/sessions(/.*)?' in s:
    print('nginx: already locked down, skipping')
    sys.exit(0)
m = re.search(r'\n([ \t]*)location /waha/ \{\n(?:(?!\n[ \t]*\}).)*?proxy_pass\s+http://127\.0\.0\.1:3000/;.*?\n[ \t]*\}\n', s, re.S)
if not m:
    sys.exit('nginx: could not find the catch-all "location /waha/" WAHA proxy block')
block = m.group(0)
key = re.search(r'proxy_set_header\s+X-Api-Key\s+"([^"]+)"', block)
if not key:
    sys.exit('nginx: no X-Api-Key in the /waha/ block')
ind = m.group(1)
new = f'''
{ind}# WAHA pass-through, narrowed 2026-10-01: only what /waha/wa-dashboard/ and the
{ind}# inbox header need (session status/start/stop/logout, QR) plus media files.
{ind}# Chat data goes through Django (/waha/wa-chats/), which hides marketing-only chats.
{ind}location ~ ^/waha/(api/sessions(/.*)?|api/[A-Za-z0-9_-]+/auth/qr|api/files/.*)$ {{
{ind}    auth_basic           "EzzyDelivery ops";
{ind}    auth_basic_user_file /etc/nginx/.htpasswd;
{ind}    rewrite              ^/waha/(.*)$ /$1 break;
{ind}    proxy_pass           http://127.0.0.1:3000;
{ind}    proxy_set_header     X-Api-Key         "{key.group(1)}";
{ind}    proxy_set_header     Host              $host;
{ind}    proxy_set_header     X-Real-IP         $remote_addr;
{ind}    proxy_buffering      off;
{ind}    proxy_read_timeout   300s;
{ind}}}

{ind}location /waha/ {{
{ind}    return 403;
{ind}}}
'''
open(path, 'w').write(s.replace(block, new, 1))
print('nginx: catch-all replaced')
PY
if ! nginx -t; then
  echo "nginx -t failed — restoring backup"; cp -a "$NGINX_SITE.bak.$STAMP" "$NGINX_SITE"; exit 1
fi
systemctl reload nginx
echo "nginx reloaded (backup: $NGINX_SITE.bak.$STAMP)"

# ---- 2. gunicorn: 4 threads per worker ----
cp -a "$UNIT" "$UNIT.bak.$STAMP"
if grep -q -- '--threads' "$UNIT"; then
  echo "gunicorn: --threads already set, skipping"
else
  sed -i 's/^\([[:space:]]*\)--workers 3 \\$/&\n\1--threads 4 \\/' "$UNIT"
  grep -q -- '--threads 4' "$UNIT" || { echo "gunicorn: could not add --threads"; cp -a "$UNIT.bak.$STAMP" "$UNIT"; exit 1; }
  systemctl daemon-reload
  systemctl restart gunicornezzy
  sleep 5
  code=$(health || true)
  if [ "$code" != "200" ]; then
    echo "site returned $code after restart — restoring the old unit"
    cp -a "$UNIT.bak.$STAMP" "$UNIT"; systemctl daemon-reload; systemctl restart gunicornezzy
    exit 1
  fi
  echo "gunicorn restarted with --threads 4 (backup: $UNIT.bak.$STAMP)"
fi

echo
echo "Checks:"
echo "  site:                      $(health)"
echo "  /waha/api/default/chats -> $(curl -s -o /dev/null -w '%{http_code}' https://ezzydelivery.qa/waha/api/default/chats)  (expect 401 without the password, 403 with it)"
