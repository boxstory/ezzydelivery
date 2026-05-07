# WAHA WhatsApp Integration — Port Plan

**Status:** Implementation in progress
**Last updated:** 2026-05-07
**Source spec:** Paperclip / Yellowkey project (consolidated by user in conversation)

---

## 1. Scope & non-goals

**In scope**
- Self-hosted WAHA container alongside Django, talked to over HTTP.
- New `WhatsAppMessage` model — one row per inbound/outbound message; no equivalent today.
- Inbound webhook receiver, outbound send proxy, agent API endpoints.
- Ops UIs: `/waha/wa-dashboard/` (session health + QR pairing) and `/waha/wa-chats/` (agent inbox).
- Daily backfill management command + Celery beat schedule.
- WAHA wired as **optional** outbound channel for `core.order_notifications.notify_order_event`, behind a feature flag.

**Out of scope (keep as-is)**
- `business.WhatsAppNotificationTrigger` config UI — the in-flight card→table refactor on this branch is unrelated.
- The existing n8n send path in `core/whatsapp_utils.py` — leave running so we can A/B and roll back.
- `core.WhatsAppVerification` (OTP) — not migrating to WAHA in this round.
- `core.WhatsAppInstance` (Evolution API) — leave dormant; WAHA config lives in env, not DB.

## 2. Architecture & app placement

**New Django app: `whatsapp/`** at the project root (sibling to `business/`, `fleet/`, etc.).

Rationale for a dedicated app rather than extending `ezzy_api/`:
- `ezzy_api/` is for *external partners* talking to *us* (Shopify imports, ShipDay webhooks, business API). WAHA is the inverse — *we* drive a self-hosted bridge.
- A dedicated app keeps the model, ops UIs, and management command together; easy to remove if we abandon WAHA.
- `core/whatsapp_utils.py` stays the dispatch layer (already knows about n8n + Evolution API; adding WAHA there fits the pattern).

```
whatsapp/
├── __init__.py
├── apps.py
├── models.py            # WhatsAppMessage
├── auth.py              # _bearer_ok, _verify_waha_hmac
├── waha_views.py        # webhook, messages list, processed, send
├── wa_dashboard_view.py # /waha/wa-dashboard/
├── wa_chats_view.py     # /waha/wa-chats/, /send/, /resync/
├── tasks.py             # Celery wrapper for backfill
├── urls.py              # /api/integrations/waha/* (webhook + agent API)
├── dashboard_urls.py    # /waha/wa-dashboard/
├── chats_urls.py        # /waha/wa-chats/, /send/, /resync/
├── migrations/
└── management/commands/backfill_waha.py
```

## 3. Settings & env

Append a new block in `ezzydelivery/settings.py` near the existing n8n config (after line ~815):

```python
# ==========================================
# WAHA (self-hosted WhatsApp HTTP API)
# ==========================================
WAHA_ENABLED = config('WAHA_ENABLED', default=False, cast=bool)
WAHA_BASE_URL = config('WAHA_BASE_URL', default='http://127.0.0.1:3000')
WAHA_API_KEY = config('WAHA_API_KEY', default='')
WAHA_WEBHOOK_HMAC_SECRET = config('WAHA_WEBHOOK_HMAC_SECRET', default='')
WAHA_DEFAULT_SESSION = config('WAHA_DEFAULT_SESSION', default='default')
WAHA_DEFAULT_FROM = config('WAHA_DEFAULT_FROM', default='EzzyDelivery')
WAHA_AGENT_TOKEN = config('WAHA_AGENT_TOKEN', default='')
```

Mirror in `envsample`. **Default `WAHA_ENABLED=False`** so the port ships dark and existing n8n flow is unaffected.

## 4. Database — `WhatsAppMessage`

Single new table, no migrations against existing tables.

| Field | Type | Notes |
|---|---|---|
| `waha_message_id` | CharField(128), unique, db_index | Dedup key from WAHA payload |
| `session` | CharField(64) | `WAHA_DEFAULT_SESSION` usually |
| `direction` | CharField(8), choices=[`inbound`,`outbound`] | List, not set (CLAUDE.md) |
| `from_number`, `to_number` | CharField(32), db_index | `@c.us` / `@s.whatsapp.net` stripped |
| `body` | TextField, blank=True | |
| `message_type` | CharField(16) | text/image/audio/video/document/location |
| `media_url`, `media_mime` | CharField(500)/CharField(80), blank=True | Same-origin rewrite at render time |
| `status` | CharField(16) | `received`→`picked_up`→`processed`→`archived`, or `failed` |
| `error_kind` | CharField(64), blank=True | e.g. `waha_send_error` |
| `business` | FK → business.Business, null=True | Optional link if number maps to a known business |
| `order` | FK → orders.Order, null=True | Optional link if message references an order |
| `raw_payload` | JSONField | Full WAHA blob, for re-parse |
| `received_at`, `picked_up_at`, `processed_at` | DateTimeField | |
| `created_at`, `updated_at` | DateTimeField, auto | Audit |

Indexes: `(status, received_at)`, `(from_number, received_at)`, `(business, received_at)`.

## 5. URL routing & nginx

### Django URLs (top-level `ezzydelivery/urls.py`)

```python
path('api/integrations/waha/', include('whatsapp.urls')),  # webhook + agent API
path('waha/wa-dashboard/', include('whatsapp.dashboard_urls')),
path('waha/wa-chats/',     include('whatsapp.chats_urls')),
```

Webhook URL given to WAHA: `https://ezzydelivery.qa/api/integrations/waha/webhook/`.

### Nginx

```nginx
# Django ops UIs — more specific, wins via ^~ prefix match
location ^~ /waha/wa-dashboard/ {
    auth_basic "EzzyDelivery ops";
    auth_basic_user_file /etc/nginx/.htpasswd;
    proxy_pass http://ezzy_app_server;
}
location ^~ /waha/wa-chats/ {
    auth_basic "EzzyDelivery ops";
    auth_basic_user_file /etc/nginx/.htpasswd;
    proxy_pass http://ezzy_app_server;
}

# Catch-all WAHA reverse proxy — runs for everything else under /waha/
location /waha/ {
    proxy_pass http://127.0.0.1:3000/;
    proxy_set_header X-Api-Key "<WAHA_API_KEY>";
    proxy_set_header Host $host;
    proxy_buffering off;     # for QR refresh
}
```

`^~` is critical — without it, longest-prefix matching could send `/waha/wa-dashboard/` to the WAHA container and you'd get 404s from WAHA's Swagger.

Webhook (`/api/integrations/waha/webhook/`) stays public — HMAC verifies it.

## 6. Auth helpers (`whatsapp/auth.py`)

- `_bearer_ok(request)` → `hmac.compare_digest` against `settings.WAHA_AGENT_TOKEN`. Used by `/messages/` and `/send/`.
- `_verify_waha_hmac(request, body)` → HMAC-SHA512 over raw body, header `X-Webhook-Hmac`, key `settings.WAHA_WEBHOOK_HMAC_SECRET`. Reject if missing in non-DEBUG.

## 7. Webhook receiver (`waha_views.py::WAHAWebhook`)

- `csrf_exempt`, POST only.
- Read raw body once → verify HMAC → parse JSON.
- Ignore events ≠ `message` / `message.any`. Ignore `fromMe` echoes.
- Strip `@c.us` / `@s.whatsapp.net` from numbers.
- Pull media from `payload.media.url` / `mimetype` for image/audio/video/document.
- Dedup on `waha_message_id` via `update_or_create`. Keep full payload in `raw_payload`.

## 8. Send proxy + agent API

1. `WAHASend` — POST `{to, text}`. Normalize `to` to `<digits>@c.us`. POST to `{WAHA_BASE_URL}/api/sendText` with `X-Api-Key`. Always write a `WhatsAppMessage` row (status `received`→after success, `failed` + `error_kind=waha_send_error` on non-2xx).
2. `WAHAMessagesList` — GET `?status=received&mark_picked_up=true`. Atomic select-then-update (`select_for_update`). Status flip `received`→`picked_up`.
3. `WAHAMessageProcessed` — POST `/messages/<id>/processed/` with optional `{order_id, error_kind}`. Stamp `processed_at`.

## 9. Ops UI: `/waha/wa-dashboard/` and `/waha/wa-chats/`

### Dashboard

Polls `GET /waha/api/sessions/<session>` every 5s, surfaces:

| State | Dot | Action |
|---|---|---|
| WORKING | green | Shows linked phone (`d.me`) |
| SCAN_QR_CODE / STARTING | orange | "Show QR to connect" → `/waha/api/<session>/auth/qr?format=image` (refresh every 55s) |
| STOPPED / FAILED | red | "Restart + show QR" → POST `/waha/api/sessions/start` then refetch QR |

### Chats UI

**Layout** (two panes, full viewport):
- Sidebar (21.25rem): header chip, search input, type filter (all/dm/group), label filter, scrollable chat list.
- Conversation pane: header (avatar, name, ↻ Resync), messages list, error strip, composer.

**Color tokens** (intentionally NOT Brand Kit — WhatsApp Web parity):
- Brand green `#00a884`, hover `#008f6f`, light tint `#e7f6f0`
- Out bubble `#d9fdd3` · In bubble `#ffffff` · Conv bg `#efeae2`
- Sidebar `#f0f2f5` · Borders `#e9edef` · Muted `#667781`/`#8696a0`

All sizing in `rem`. Hairlines `0.0625rem`. CSS file header should call out the WhatsApp-parity exception so a future `/css-fix` pass doesn't "correct" them.

**Filters & search**:
- Free-text search over chat name and id.
- Phone-number search auto-injects a virtual phone chat row when 8–15 digits typed and no existing match.
- Label filter cached in localStorage `wa_label_map_v1` + ts companion, 24h TTL. `?nolabels=1` kill-switch.

**Message loader (the clever bit)**:
1. Compute today-start in Asia/Qatar (UTC+3, no DST).
2. DB pull: `WhatsAppMessage` for chat with `received_at < today_start_utc`, newest-first up to limit (default 1000, max 2000).
3. WAHA live: `GET /api/{session}/chats/{chatId}/messages?limit=100&downloadMedia=false` with **20s timeout** (under gunicorn 30s).
4. Cold start case: DB empty → bump `limit=300, cutoff=0` so first open isn't empty.
5. Filter today messages by `seen_ids`, sort ascending by timestamp, return JSON.

Three robustness shims:
- `_msg_type(payload)` — read from `_data.type` first, fall back to top-level `type`.
- Media URL backfill — pull from `raw_payload.media.url` if DB column blank, then `_rewrite_waha_url` to convert `http://127.0.0.1:3000/api/files/…` → same-origin `/waha/api/files/…`.
- `_group_sender(payload)` — for `@g.us` chats, pull author from `payload.author` / `payload.participant` / `_data.author` / `notifyName`. Stub allowed for v1.

**Send (`wa_chats_send`)**: POST `{to, text}`, normalize to `<digits>@c.us`, forward to `{WAHA_BASE_URL}/api/sendText` with `{session, chatId, text}` + `X-Api-Key`. `csrf_exempt` (htpasswd-gated, JSON POST without CSRF cookie).

**Resync (`wa_chats_resync`)**: POST `?chatId=…`, GET WAHA `/api/{session}/chats/{chatId}/messages?limit=200&downloadMedia=true` with **25s timeout**. Insert missing rows as `status='archived'` with media + raw_payload. Returns `{ok, count, inserted, messages}`.

**Polling**: every 30s, active chat re-clicked + chat list reloaded.

## 10. Backfill command

`whatsapp/management/commands/backfill_waha.py`:

```bash
python manage.py backfill_waha --skip-today --days=120 \
    --limit-per-chat=100 --max-chats=200 --min-sleep=3 --max-sleep=8
```

- Iterates chats from `/api/{session}/chats?limit=200`.
- Per chat: `/api/{session}/chats/{id}/messages?limit=100&downloadMedia=true`, **180s timeout**.
- 24h skip cache `waha_backfill_done:<chat_id>` (Redis already configured).
- For dup rows: backfills missing `media_url`/`media_mime`, normalizes `message_type`, refreshes `raw_payload` only if it lacked the media block. Never clobber populated fields.
- `--skip-today` keeps Qatar-today messages live-only (handled by webhook + chat UI).
- Random 3–8s sleep between chats (rate-limit defense).
- `--force` ignores the 24h skip cache.

**Schedule via Celery beat** (not host crontab) at 01:30 Asia/Qatar:
```python
'whatsapp-daily-backfill': {
    'task': 'whatsapp.tasks.run_backfill',
    'schedule': crontab(hour=1, minute=30),
    'kwargs': {'skip_today': True, 'days': 120, ...},
},
```

## 11. Integration with existing notification flow

In `core/order_notifications.py::_send_whatsapp`, add a single branch at the top:

```python
def _send_whatsapp(phone, message, event, order):
    if getattr(settings, 'WAHA_ENABLED', False):
        return _send_whatsapp_via_waha(phone, message, event, order)
    # ...existing n8n path unchanged...
```

`_send_whatsapp_via_waha` POSTs internally to our own `/api/integrations/waha/send/` endpoint (so all sends go through one auditable proxy and get a DB row for free). Cutover = `WAHA_ENABLED=True` + reload. Rollback = flip back.

Don't touch the trigger model or trigger UI — branch already has UI work in flight there.

## 12. Sidebar entry points (workforce, not business)

Add to `workforce/templates/workforce/parts/dashboard_sidebar_workforce.html` (and mobile counterpart):
- `wf-sidebar__item--wa-chats` → `/waha/wa-chats/`
- `wf-sidebar__item--wa-dashboard` → `/waha/wa-dashboard/`
- Plus `target="_blank"` variants for opening in a new tab.

`wf-sidebar__` BEM prefix already established (per memory index).

## 13. Order of operations

1. Settings + envsample (`WAHA_ENABLED=False` default).
2. App skeleton + `WhatsAppMessage` model + migration. Register in `INSTALLED_APPS`.
3. Auth helpers + webhook + send + agent API + URL routes.
4. Run WAHA container; nginx config; htpasswd.
5. Dashboard view; verify state flips to WORKING after QR scan.
6. Chats view; send a self-test message.
7. Backfill command + Celery beat entry.
8. Notification dispatcher branch.
9. Sidebar entries.
10. Cutover: flip `WAHA_ENABLED=True`. Rollback path = flip back.

## 14. Risks / open questions

- **Account ban**: Self-hosted WAHA is grey-area against WhatsApp ToS. Use a dedicated number, not the main company line.
- **n8n co-existence**: Keep n8n config warm for ~2 weeks post-cutover for fallback.
- **`WAHA_API_KEY` in nginx config**: plaintext on disk; acceptable on single-tenant VPS.
- **Bearer in chat UI page source**: behind htpasswd, but rotatable; flag for ops awareness.
- **Group chats**: v1 can stub `_group_sender`.
- **Media persistence**: WAHA serves media from container volume; if rebuilt, old URLs 404. Persist the volume properly or add a download step in v2.
- **Webhook idempotency**: `update_or_create` on `waha_message_id` handles WAHA retries; avoid side effects firing twice.
- **Agent inbox auth**: htpasswd-only currently (matches paperclip). If staff need it via Django auth, swap to allauth + permission decorator.
