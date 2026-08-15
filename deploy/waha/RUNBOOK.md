# WAHA Bridge — Install Runbook

All commands assume CWD = `/home/ezzyadmin/ezdlproject/ezzydelivery`.

## 1. Install Docker (one-time, requires sudo)

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
  sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin

sudo systemctl enable --now docker
sudo usermod -aG docker ezzyadmin     # log out / back in for group to apply
```

Verify: `docker --version && docker compose version`.

## 2. Start WAHA Core

```bash
cd /home/ezzyadmin/ezdlproject/ezzydelivery/deploy/waha
# .env is already in place with WAHA_API_KEY + WAHA_WEBHOOK_HMAC_SECRET.
docker compose pull
docker compose up -d
docker compose logs -f waha     # ctrl-c when "Application is running" appears
```

Smoke check:

```bash
curl -sH "X-Api-Key: $(grep WAHA_API_KEY .env | cut -d= -f2)" \
     http://127.0.0.1:3000/api/sessions | head
```

## 3. Create htpasswd for ops UIs (one-time, requires sudo)

```bash
sudo apt-get install -y apache2-utils
sudo htpasswd -c /etc/nginx/.htpasswd ezzyops    # prompts for password
sudo chown root:www-data /etc/nginx/.htpasswd
sudo chmod 640 /etc/nginx/.htpasswd
```

## 4. Wire nginx (requires sudo)

1. Open `/etc/nginx/sites-enabled/ezzydelivery` and paste the contents of
   `deploy/waha/nginx-waha.conf.snippet` inside the existing `server { }`
   block that listens on 443 for `ezzydelivery.qa`.
2. Replace `REPLACE_WITH_WAHA_API_KEY` with the value from
   `/home/ezzyadmin/ezdlproject/ezzydelivery/.env`.
3. Test + reload:

```bash
sudo nginx -t && sudo systemctl reload nginx
```

## 5. Pair the WhatsApp number

1. Browse to `https://ezzydelivery.qa/waha/wa-dashboard/` (htpasswd prompts).
2. Click "Show QR to connect" → scan with the dedicated business WhatsApp.
3. State should flip to **WORKING** within ~10s.

## 5b. Add a second number (extra WAHA session)

WAHA Core has been multi-session since `2026.6.1` — the old "Core = one
session" limit is gone, so both numbers run in this one container. Django is
session-aware throughout (`whatsapp/sessions.py` is the single resolver), and
`WhatsAppMessage`/`WhatsAppContact` are uniquely keyed per session.

**Apply migrations first.** `whatsapp/migrations/0009_*` swaps the global
unique on `waha_message_id` for `(session, waha_message_id)`. WAHA message ids
are unique per chat, not per session, so if inbound traffic from a second
number arrives before that migration lands, the webhook's `update_or_create`
silently overwrites the first number's rows instead of failing.

```bash
cd /home/ezzyadmin/ezdlproject/ezzydelivery
source ../venvezzy/bin/activate && python manage.py migrate whatsapp

# Then create + start the session (name: a-z A-Z 0-9 - _ only)
K=$(grep -m1 '^WAHA_API_KEY=' .env | cut -d= -f2-)
curl -s -X POST http://127.0.0.1:3000/api/sessions \
  -H "X-Api-Key: $K" -H 'Content-Type: application/json' \
  -d '{"name":"fleet","start":true}'
```

Then browse to `https://ezzydelivery.qa/waha/wa-dashboard/?session=fleet` and
scan the QR with that number. A tab strip appears on wa-dashboard, wa-chats and
the CRM inbox as soon as a second session exists.

Finally, point the routing at it — set **WAHA session** to `fleet` on the
matching row at `/workforce/auto-triggers/whatsapp-instances/`. Sends resolve
section → `WhatsAppSenderRoute` → `WhatsAppInstance.waha_session`, so nothing
changes hands until that field is filled in.

Notes:
- Pairing a number that is already on Evolution does **not** disturb Evolution;
  it links as an additional WhatsApp Web device. Evolution stays as a fallback.
- The engine is container-wide (`WHATSAPP_DEFAULT_ENGINE`) — WAHA has no
  per-session engine option. Every session here runs WEBJS, one Chromium each.
  A number needing a browserless engine would need its own container.
- After **any** container restart every session comes back STOPPED and needs an
  explicit `POST /api/sessions/start` per session.

## 6. Cutover

Only after the dashboard shows WORKING and a manual test send succeeds via
`https://ezzydelivery.qa/waha/wa-chats/`:

```bash
sed -i 's/^WAHA_ENABLED=False$/WAHA_ENABLED=True/' \
  /home/ezzyadmin/ezdlproject/ezzydelivery/.env
kill -HUP $(pgrep -f "gunicorn.*ezzydelivery" | head -1)
```

Rollback = flip the flag back + HUP. n8n path is unchanged and ready to take
over instantly.

## 7. Backfill (after cutover)

```bash
source /home/ezzyadmin/ezdlproject/venvezzy/bin/activate
python manage.py backfill_waha --skip-today --days=30 --max-chats=50
```

Daily run is already scheduled via Celery beat
(`whatsapp-daily-backfill`, 01:30 Asia/Qatar).
