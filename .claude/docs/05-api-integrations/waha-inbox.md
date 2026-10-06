# WAHA Agent Inbox (`/waha/wa-chats/`)

Reference for the ops WhatsApp inbox: a WhatsApp-Web-style three-pane page (chat list · conversation · contact panel) over WAHA and the `WhatsAppMessage` table. Built out on 2026-09-29; see `.claude/devlog/2026-09-29.md` for the change history.

## Files

| File | What lives there |
|---|---|
| `whatsapp/wa_chats_view.py` | The whole page (HTML, CSS and JS inline in `_CHATS_HTML`) plus every JSON endpoint |
| `whatsapp/chat_panel.py` | Data for the contact panel: identity, WhatsApp names, CRM leads, media by kind, link/unlink |
| `whatsapp/profile_photos.py` | Load a profile photo from WAHA, save it, refresh it weekly |
| `whatsapp/wa_chats_actions.py` | Write actions beyond plain text: attachments, voice notes, reactions, forward, edit/delete, number check, archive/unread (added 2026-10-03) |
| `whatsapp/chats_urls.py` | Routes under `/waha/wa-chats/` |
| `whatsapp/sessions.py` | `render_tabs()` for the session picker, `list_sessions()`, `from_request()` / `normalize()` |
| `whatsapp/models.py` | `WhatsAppMessage`, `WhatsAppContact`, `WhatsAppProfilePhoto`, `RestrictedChatLabel`, `WhatsAppReaction` |
| `whatsapp/label_access.py` | Marketing-only labels: who may see which chat (inbox + CRM) |
| `workforce/wa_label_access_views.py` | Super-admin settings page `/workforce/whatsapp/label-access/` |
| `crm/models.py` · `crm/services.py` | `LeadWaLink` (a lead's many labelled numbers), `add_wa_link` / `remove_wa_link`, `lead_wa_numbers`, `accounts_for_numbers`. See [`crm-lead-whatsapp-numbers.md`](../06-features/crm-lead-whatsapp-numbers.md) |

The page uses a WhatsApp-Web palette on purpose, not the Brand Kit (see the comment at the top of its `<style>`).

## Access

| Layer | Gate |
|---|---|
| Every endpoint (page, list, labels, messages, media, photos, send) | nginx basic auth **and** a Django staff login (`_staff_only`, since 2026-10-01). Page → login redirect; JSON → 401 |
| nginx basic auth for `/waha/wa-chats/` (since 2026-10-06) | Per-staff logins in `settings.WAHA_INBOX_HTPASSWD` (`/home/ezzyadmin/ezzy-private/waha-inbox.htpasswd`), managed by super admins in the **WAHA Inbox** group (Login column) on `/workforce/staff-roles/` (`whatsapp/inbox_access.py`). Login name = Django username; password generated, shown once. The raw `/waha/` API proxy (injects `X-Api-Key`) and `/waha/wa-dashboard/` keep the root-owned `/etc/nginx/.htpasswd` — never hand that one to staff |
| Which WhatsApp numbers (since 2026-10-06) | `whatsapp/session_access.py`: super admins open every number; everyone else only the numbers switched on in the **Numbers** dropdown (WAHA Inbox group) on Staff Roles (`InboxSessionAccess` rows — no row = closed). Enforced in `_staff_only` on every endpoint from `?session=`, else the POST form/JSON `session`, else the default number; `media/<id>/` is marked `_session_from_row` and checks the message's own number. A page on a closed number redirects to the first open one (403 if none); JSON → 403 `This WhatsApp number is not open to you.` The tab strip lists only open numbers (`render_tabs(only=…)`). Label mirroring to other numbers still runs; its note names only open numbers |
| Chats under a marketing-only label | Hidden from staff without the Marketing department (super admins see all). See below |
| CRM lead details in the panel | Also needs `can_access(user, 'crm_lead_detail')` |
| Linking or unlinking a lead, lead search | Needs `can_access(user, 'crm_lead_link_chat')` |
| Filing a chat photo onto a driver's documents (`save-doc/`) | Needs `crm_lead_link_chat` **and** `can_access(user, 'driver_document_edit')` (`chat_panel.can_save_driver_docs`) |
| Editing / verifying a driver document from the media viewer | Same edit right for Submit (`can_save_docs`); Mark verified needs `driver_document_verify` (`chat_panel.can_verify_driver_docs` → `can_verify_docs`). Both are Ops + Marketing since 2026-10-06 |
| Editing a lead (stage, assignee, follow-up, note) | Posts to the CRM's own `/workforce/crm/...` endpoints, so their department rules apply (driver write-back stages need Operations) |

Every POST is CSRF-protected (`send/` and `resync/` lost `csrf_exempt` on 2026-10-01). The token is rendered as `%CSRF%`.

### Marketing-only labels

- Super admin ticks labels per number at `/workforce/whatsapp/label-access/` → `RestrictedChatLabel(session, label_id)`.
- `label_access.restricted_identifiers(session)` reads each restricted label's chats from WAHA (cached 120 s per gunicorn worker, last good copy kept 24 h) and adds the phone↔lid twin from `WhatsAppContact`.
- **Fails closed:** if a restricted label's chats cannot be read and nothing is cached, non-marketing staff get 503 on the list and 403 on chat calls.
- Inbox: list (`chats=1`), labels (`labels=1`, `chat_labels=1`), `chat_latest`, `names` filter the chats out; every chat-scoped call (messages, info, who, media, send, resync, read, set-labels, link-lead, save-doc, avatar, `media/<id>/`) refuses them. Restricted labels themselves are not shown or settable outside marketing.
- CRM: `crm_services.wa_read_blocked(identifiers, user)` adds the same rule; lead detail (conversation, number picker, AI summary), chat refresh, chat preview, media, and `driver_wa_thread` pass `request.user`.
- **The browser never calls WAHA directly.** Every fetch is `/waha/wa-chats/…` or `/workforce/…`; stored media is `/waha/wa-chats/media/<id>/`, live media `media-live/` (listed with `downloadMedia=false`, so WAHA hands back no `/api/files/` URL). That is what lets the inbox run on its own password file. Anyone holding the *admin* htpasswd can still read chats straight through the raw `/waha/api/…` proxy.

### nginx wiring for the per-staff file (one-time, needs sudo)

In `/etc/nginx/sites-enabled/ezzydelivery`, inside `location ^~ /waha/wa-chats/` only:

```nginx
auth_basic           "EzzyDelivery inbox";
auth_basic_user_file /home/ezzyadmin/ezzy-private/waha-inbox.htpasswd;
```

then `sudo nginx -t && sudo systemctl reload nginx`. The separate realm name stops browsers re-sending inbox credentials to the admin-only locations. Until this is done, Staff Roles shows a "not live yet" warning (`inbox_access.nginx_wired()` looks for the path in the site config). The file was seeded from `/etc/nginx/.htpasswd` (`ezzyadmin`, `test`) so nobody loses access at the switch; `test` has no Django user, so it never shows in the column — remove it by hand if unwanted. nginx re-reads the file per request: adding/removing a login needs no reload.

## Endpoints

All are `GET /waha/wa-chats/?…` unless stated. Every call carries `session=` (added by the JS `wq()` helper).

| Query / path | Returns | Notes |
|---|---|---|
| *(none)* | The page | `%SESSION%`, `%SESSION_LABEL%`, `%SESSION_TABS%`, `%CSRF%`, `%LABEL_RULES%` are substituted in `_render_page` |
| `chats=1&limit=&offset=` | `{chats, fetched}` — WAHA chat list minus hidden chats | Page on by `fetched` (WAHA's count), not `len(chats)` |
| `labels=1` | `{labels, map: {labelId: [chatId]}, complete}` | Replaces the browser's direct WAHA label calls; cached in localStorage for a day under a key that includes `%LABEL_RULES%` |
| `chat_labels=1&chatId=` | `{labels}` for one chat, live | |
| `POST read/` | `{session, chatId}` → marks the chat read in WhatsApp | |
| `messages=1&chatId=&limit=&before_ts=` | Messages, DB and live WAHA merged | Existing behaviour |
| `chat_latest=1` | Latest timestamp per number | Existing behaviour |
| `info=1&chatId=&name=` | Contact identity, media counts, leads, suggestions, staff list, `accounts` | Leads and accounts are only included when the user may see leads |
| `media=1&chatId=&kind=&offset=` | 60 items a page | `kind` is one of photos / videos / files / links / voice / audio |
| `lead_search=1&q=` | Leads by name, company, phone or #id | Needs CRM link rights |
| `who=1&chatId=` | `{phone, lid, saved_name, push_name}` | Used for the conversation header title |
| `names=1&ids=a,b,c` | `{names: {chatId: WhatsApp name}, leads: {chatId: lead name}}` | Chat-list labels; **makes no WhatsApp API calls**. `leads` only for a CRM-visible login (`chat_panel.lead_names`, batched) |
| `POST link-lead/` | `{lead_id, chatId, session[, action:'unlink']}` | Never creates a lead |
| `POST save-doc/` | `{session, chatId, lead_id, msg_id, doc_type, side}` → `{ok, docs}` | The photo must be one of this chat's messages and the lead must be connected to this chat and a driver lead with a `Lead.driver` |
| `avatar/?chatId=` | The saved profile photo | 404 means no photo; the browser caches that for an hour |
| `media/<msg_id>/` | One message attachment | Existing; shares `_stream_wa_media` with the CRM |
| `POST send/` | `{to, text, session[, reply_to]}` | `reply_to` = the quoted message's full serialized id (`waha_id`), checked by `_REPLY_ID_RE` |
| `POST send-media/` | multipart `file, to, session[, caption, reply_to, voice=1]` | jpeg/png ≤16 MB → `sendImage`; video ≤16 MB → `sendVideo` (convert unless mp4); `voice=1` → `sendVoice` convert; else `sendFile`. 30 MB cap |
| `POST react/` | `{session, messageId, emoji}` | Empty emoji removes. Stored in `WhatsAppReaction(sender='me')` |
| `POST forward/` | `{session, messageId, chatIds: [1..5]}` | Source and every target must pass the label gate |
| `POST edit/` · `POST delete/` | `{session, chatId, messageId[, text]}` | Only `true_…` (our own) ids. Updates the stored row too, because the DB copy wins over WAHA's in the merge |
| `check-number/?phone=` | `{exists, chatId}` | WAHA `contacts/check-exists`. Only called for a typed number with no chat (search / new chat) |
| `POST chat-action/` | `{session, chatId, action: archive\|unarchive\|unread}` | |

All writes need a strict session name (`sessions.is_valid`), not `normalize()`.

## UI features

### Sidebar header and sessions
- The green chip shows the active number's WhatsApp display name (`push_name` of the session), or the raw session name if it has none.
- The gear button opens a `<dialog>` listing every linked number (`render_tabs(..., always=True)`) with a "Session health & QR" link. It closes on ×, a backdrop click or Esc.

### Chat list
- The type filter defaults to **Persons** (`autocomplete="off"` stops the browser restoring an old choice).
- **Persons = any chat that isn't `@g.us`, `@newsletter` or `@broadcast`.** Since WhatsApp's privacy change almost every one-to-one chat is an `@lid` id, not `@c.us`, so the old `@c.us`-only "Direct" filter showed nothing.
- A chat connected to a CRM lead is titled with the **lead's name, like a saved contact** (no `~`) — list, header (`?who=1` → `lead_name`) and panel. Order: saved WhatsApp contact name → lead name → `~ <WhatsApp name>` → `+number`. Only for a staff login that may see leads; others still see `~ name`. The name carries the CRM's category tag (" ZyDrv" / " ZyBuz") because `Lead.save()` stores it that way.
- Otherwise unsaved contacts are titled `~ <WhatsApp name>`, as WhatsApp Web does. Search still matches the number (`c.number`).
- Profile photos are lazy-loaded over the coloured initials.

### Conversation header
- The title is the saved name, else `~ <WhatsApp name>`, else `+<real phone>`, via `nameFromWhatsApp()` → `?who=1`.
- The **Info** button toggles the contact panel.

### Contact panel (right column)
- Full height beside the chat. Below 75rem (about 1200px) it slides over the chat instead. Open/closed is remembered per browser in `localStorage` key `waInfoOpen`.
- **Top summary**: one compact `<details>` row with avatar, name, phone and the connected lead's stage label. Expanding it shows On number, Phone, WhatsApp name, Saved as, LID, Messages, First and Last message. Rows are always listed and left blank when a value is unknown.
- **EzzyDelivery account** (2026-10-05, `chat_panel.chat_accounts()`): the platform login(s) behind the chat, one card per person, up to 8. Shown to the same CRM login that may see leads. Each card is a `<details>` closed to one line (name, roles, the driver's or first business's status, "Login disabled") since 2026-10-06; the facts and seller/driver records open underneath. Since 2026-10-06 the section has no heading and the card is no longer a `<details>`. **Line 1** is the person: user icon, name (a toggle button that opens the facts), roles, then a green **Verified** flag when `verification_key == 'verified'`, otherwise a **Verify** button (`verify_url`: one profile status, so one queue: business `?search=<business_id>` for a client, else driver `?search=<driver_code or username>`, else user `?q=<username>`; staff-only and verified get none). **Line 2+** is one indented row per business / team / driver record with its status and **Open business** / **Open driver**. Each link only appears when the viewer `can_access` that route.
  - Matched by the chat's **real phone** (last 8 digits, `\D*` regex) against `Profile.phone/whatsapp`, `Business.business_phone/business_whatsapp`, `Driver.driver_phone/driver_whatsapp` and `BusinessTeamProfile.team_phone`, **or through a connected lead**: its `converted_business` (owner) and its `driver`. "Matched by" lists every route (Phone · Business number · Lead #239…).
  - A lid chat with no known phone matches through its leads only; a lid is never phone-matched (it would invent a 974 number).
  - Card: name, @username, roles (Staff / Client / Team member / Driver or Driver applicant / Customer), login disabled, user no., email, phone, WhatsApp, verification, joined, last login, P2P bookings. Below it each owned business (status, code, order count + last order, business number), team memberships, and the driver row (status, availability, code).
  - A business found by its number with no owner login gets its own card ("Business · no login").
  - "Open seller" / "Open driver" links only appear when the viewer may open `seller_detail` / `driver_detail` (Operations), so a marketing login sees the facts without dead links.
- **CRM leads**:
  - A **connected** lead shows a working card: stage select, assignee, follow-up date, add note, recent activity, notes and AI summary, flags (overdue, no follow-up, unassigned, days in stage, pinned, closed), facts, Open in CRM, and Unlink for manual links.
  - A connected **driver lead** with a `Lead.driver` also shows **Required documents**: the driver profile's Selfie, QID, Passport, Driving License and Istimara (`chat_panel.driver_documents`), with front/back thumbnails, number, expiry, and a "Complete"/"Incomplete" flag against the application rule (Selfie + any 2 IDs, same as `core.views.join_driver`). A row holding only the placeholder image counts as missing. Each tile has **+ Add from chat** (or **Replace from chat**) which opens a picker `<dialog id="wa-pick">` of this chat's photos (`?media=1&kind=photos`), with a Front/Back choice for IDs; tapping a photo confirms and posts to `save-doc/`.
  - **Send reminder · N missing** (2026-10-06) sits in that card's footer whenever the applicant still owes something: the lead dict's `reminder` comes from `chat_panel.driver_reminder()` → the CRM composer's `_lead_reminder()` (the driver page's `_build_driver_reminder` body: every unfinished application section + the form link). Closed/converted cards and complete applications get none, so no button. The button opens `<dialog id="wa-remind">` with the text editable; Send posts it to this chat through `postText()`, the composer's own send path (`send/`, this chat's session), never the driver-onboarding route.
  - With **nothing connected**, the panel shows name-based suggestions and a lead search, each result with "Link this chat".
  - It **never creates a lead** (the 2026-09-22 rule: leads come only from the driver or pricing form).
- **Media** tabs: Photos, Videos, Files, Links, Voice, Audio, each with a count and "Load more".

### Media viewer
- Photos and videos, in the panel grid and in chat bubbles (a video in a bubble is a still preview with a ▶ mark, `.wa-vthumb`), open in a full-screen `<dialog id="wa-lb">` instead of a new tab.
- It shows the date and Sent/Received, an `n / total` counter, previous/next (buttons or ←/→) through the other media in the **same container** (that grid, or `#wa-msgs`), a Download link, and closes on ×, backdrop or Esc.
- **Save to driver file**: for a photo from this chat, when the chat has a connected driver lead and the account may edit driver documents, the viewer bar offers a document + side picker. Saving (`chat_panel.save_chat_photo_to_driver`) replaces only that side's image: number, expiry and the other side are kept, a crop's parked original is dropped, and a note goes on the lead. The image is Pillow-verified, JPEG/PNG/WebP only, 8 MB max. Replacing asks for confirmation.
- To make something open in it, give the element `data-lb-url` (plus optional `data-lb-kind="video"`, `data-lb-meta`, `data-lb-caption`). One delegated document click handler does the rest, including items added later. Documents are not wired to it; they still open as files.
- **Document panel (2026-10-06)**: a thumbnail from the Required documents card (`data-lb-doc`) opens with the same panel as the CRM document popup beside the photo (stacked under it at phone width): Number / Expiry fields, **Use values from image** (copies `ai_no` / `ai_expiry_iso` into the fields, saves nothing), the image-check facts (Image check, Why, Number / Expiry on image), and **Mark verified** / **Undo verification**, **Submit**, **Submit & verify**. It posts to the workforce endpoints (`docs.doc_edit_base` + `<id>/edit/` and `/verify/`, with `X-CSRFToken` + `X-Requested-With`), never a second write path, then reloads the panel (`loadPanel()` returns its fetch) and repaints. The facts come from `chat_panel._doc_check()`. Arrow keys inside a field no longer flip the photo.

### Message actions (2026-10-03)
- Hovering a bubble shows ↩ Reply, ☺ React and ⋮ More (Reply · Forward, plus Edit within 15 min and Delete for everyone within ~2 days on our own messages). Touch screens show them faintly all the time.
- **Reply** opens a "Replying to" bar above the composer; Esc or × cancels. A received reply shows the quoted text (from WAHA's `replyTo`); clicking it scrolls to the original if loaded. A media quote shows its kind ("Photo") because a media `body` can be the base64 thumbnail.
- **Reactions** show as a chip on the bubble. WAHA's message list only says `hasReaction`, never which emoji, so they come from `WhatsAppReaction` (`_attach_reactions`). Other people's reactions arrive through the `message.reaction` webhook event (`_store_reaction`), enabled in `WHATSAPP_HOOK_EVENTS` on 2026-10-03. Media sending and forward need WAHA ≥ 2026.9.2 on WEBJS; 2026.7.1 failed every media send with "Data passed to getter must include an id property".
- **Attachments**: 📎, paste an image, or drop a file on the conversation. The bar says how it will send (photo / video / document). The text box becomes the caption.
- **Voice notes**: 🎤 records in the browser (MediaRecorder), up to 10 minutes; WAHA converts to opus. The page sends its own `Permissions-Policy` with `microphone=(self)` because the site-wide header blocks the microphone.
- **⋮ Chat** in the header: Mark as unread (WhatsApp's dot, `unreadCount = -1`) and Archive / Unarchive. Archived chats leave the list as on the phone; the type filter has an **Archived** view and a search still finds them (tagged "Archived"). Marking unread or archiving closes the chat so it is not read again straight away.
- **Number check**: typing a number with no chat shows "Checking WhatsApp…", then "On WhatsApp" / "Not on WhatsApp" on the "New chat" row (700 ms after typing stops, once per number). A number that is not on WhatsApp will not open.

### Background refresh (every 30 seconds)
- `poll()` → `loadChats()` + `refreshMessages()` + session status.
- `refreshMessages()` appends only messages not already on screen (keyed by `waha_id`). It never blanks the pane, and only scrolls to the bottom if the reader was already there. A locally drawn just-sent bubble (`.wa-msg--local`) is swapped for its real copy when that arrives.
- Rebuilt list rows reuse the already-loaded photo `<img>` (`listPics`, `addPhoto(..., reuse=true)`). Creating fresh ones made every avatar flicker on each poll.

## How a lead is "connected" to a chat

A lead can talk from **several WhatsApp numbers**: the owner, the office, accounts and so on. Since 2026-09-29 they live in `crm.LeadWaLink(lead, identifier, session, label, created_by)`, unique per `(lead, identifier)`.

- **Primary number**: the lead's own `phone`. It is matched automatically: the free-text phone ends in the chat phone's last 8 digits (Postgres regex, `\D*` between digits).
- **Linked numbers**: `LeadWaLink` rows. `identifier` is bare digits, either a phone or a lid (lids only mean something on their `session`). `label` says who it is ("Owner", "Office"…).
- `Lead.wa_link_values` is the single read path. It returns every linked identifier and still honours the legacy `wa_chat_override` if anything sets it. Migration `crm/0014` moved all 189 old values into the table and cleared the field.
- **Writes**: `crm.services.add_wa_link()`, `remove_wa_link()`, `repoint_wa_link()`. Linking **adds and never replaces**. The inbox's `link-lead/` and the CRM's `crm_lead_link_chat` both take an optional `label`. `crm_lead_unlink_chat` (Marketing desk, in `core/departments.py`) removes one number.
- `chat_panel.connected_leads()` returns `(lead, how, label)`, where `how` is `phone` (primary) or `linked`. Merged child leads are swapped for their parent.
- `crm.services.lead_wa_numbers(lead)` lists primary plus linked numbers with the **platform account registered on each** (`accounts_for_numbers()`: Staff, Client · business, Driver / Driver applicant, Client team, Customer). It is shown on the CRM lead page ("Numbers") and on the inbox lead card. On the inbox card, every number that is not the open chat has **Open chat** (`openNumberChat()`): a chat already in the loaded list opens directly, a lid on this session opens as `<lid>@lid`, a lid from another session reloads the inbox with `?session=<s>&open=<lid>@lid`, and a phone with no listed chat goes through `check-number/` (its thread may be stored under a lid). `?open=<chatId>` works on any inbox URL. The card's activity list uses `.wa-actlog`, not `.wa-acts`: `.wa-acts` is the message hover toolbar (opacity 0 until hover), and sharing that name hid every activity entry.
- **Accounts vs leads**: a lead's numbers never block anyone from signing up. Signup (`core/forms.py`, `core/views.py`) only checks *other accounts*, so the owner and the office can each register their own login. Once a number has an account, the CRM hides that number's chat (`wa_read_blocked`, because it carries login codes) and the Numbers list says so.

Lid rules from [`wa-lid-vs-phone-expansion`]: never run a lid through `_phone_variants`, because it invents a real-looking 974 number.

## WhatsApp names (push names)

**Rule: do not hit the WhatsApp API for names. Save them on `WhatsAppContact` and load from there.**

| Path | Sources, in order | WhatsApp calls |
|---|---|---|
| Chat list: `push_names()` | 1. `WhatsAppContact.push_name` 2. `notifyName` on the chat's newest inbound message | **None** |
| One chat (panel or header): `chat_identity()` → `_push_name()` | 1. Contact row 2. Newest inbound `notifyName` 3. One WAHA `GET /api/contacts?contactId=` | At most one, then saved |

- `remember_push_name()` writes a found name into `WhatsAppContact`. It never overwrites an existing name (the daily `sync_wa_contacts` owns those) and fills in a missing `lid`.
- The directory is keyed by `(session, phone)`, so a lid chat gets a new row only once its phone is known. Stored messages never carry a lid's phone. It comes from the WAHA lids map (`_lid_map`: one bulk call, cached 6 hours per worker, read cache-only in the batch path) or the daily contact sync.
- WAHA sets an unsaved chat's `name` to the formatted number (`"+974 7402 4778"`), so a digits-only name is **not** a name (`hasRealName` in the JS).

## Profile photos

- `WhatsAppProfilePhoto(session, chat_id, photo, has_photo, fetched_at)`, unique per `(session, chat_id)`. Migration `whatsapp/0013_profile_photo`.
- Files live in `private_media/whatsapp/avatars/` (the private storage, not public `/media/`).
- `get_photo()`: a fresh row (under 7 days) is served as-is. Otherwise it asks WAHA `/api/contacts/profile-picture`, downloads and saves. `has_photo=False` records "no photo". A failed download is retried after an hour and keeps any older copy.
- **SSRF guard**: only `https` URLs on `*.whatsapp.net` are downloaded, with no redirects, at most 2 MB, and verified with Pillow (JPEG, PNG or WebP only).
- WhatsApp's own photo URLs expire within days, which is why we keep a copy.

## Media tabs

- These read only the chat's stored `WhatsAppMessage` rows (same match as the message pane: `session` + `from_number`/`to_number` = chat digits).
- Voice and audio are both stored as `message_type='audio'`. **WhatsApp's raw type `ptt` marks a voice note** (`raw_payload._data.type` or `raw_payload.payload._data.type`).
- A media message's `body` is often a base64 thumbnail, so the caption is dropped when it contains no spaces.
- Files are served by `wa_chats_media` → `_stream_wa_media` (archive first, WAHA fallback). Some old photos show "unavailable" because WAHA purged them before they were archived.

## Gotchas

- `Business` has `business_name`, not `name`. Reading `.name` 500'd the panel for converted leads.
- `LeadActivity.created_by` is nullable, so panel writes pass `request.user`.
- The CRM endpoints answer a user without that department with a redirect or HTML page. `postForm()` treats non-JSON as "your account cannot do this here".
- A stage move fires `lead_stage_changed` AutoFlows. None were configured as of 2026-09-29, so test moves sent nothing. Re-check before testing on real leads.
- `CACHES['default']` is LocMem, so every "cached a day" is per gunicorn worker.
- A lead's extra numbers are `LeadWaLink` rows read through `lead.wa_link_values`. `Lead.wa_chat_override` is legacy and was emptied on 2026-09-29; never read or write it directly.
- The CRM leads list searches with `?search=`, not `?q=`.
- `crm.tests.ConvertTests` (2 businesses instead of 1) fails at HEAD too, so it is not caused by inbox or lead-number work.

## Testing recipe

The live URL is behind htpasswd, so drive it in headless Chromium and answer requests in-process. See `page-sweep-recipe` / `server-environment` in memory:
- Use `DJANGO_ALLOW_ASYNC_UNSAFE=true` (Playwright's sync API runs inside an event loop) and `LD_LIBRARY_PATH=~/chrome-libs/extract/usr/lib/x86_64-linux-gnu`.
- `page.route('**/*')`: send `/waha/wa-chats/…` to a `django.test.Client` (with `force_login`, `secure=True`) and `/waha/api/…` to `WAHA_BASE_URL` with the API key.
- **In the route handler, call `django.db.connections.close_all()` after building the response and BEFORE `route.fulfill()`.** Otherwise every request leaks a Postgres connection and a photo-heavy page drains the 100-slot server that production and the Zella app share.
- Headless Chromium here has no H.264, so `.mp4` videos show the "can't play here" fallback. Check the file with `fetch()` (it should be 200 `video/mp4`) instead.
- Test writes inside `transaction.atomic()` + `set_rollback(True)`, with `Client(enforce_csrf_checks=True)` and a `Referer` header.
- Fake every write in the route handler (`send/`, `send-media/`, `react/`, `forward/`, `edit/`, `delete/`, `chat-action/`, `read/`, …) and record the body from `request.post_data_buffer` (`post_data` dies on a binary upload). A streamed response (`media/`, `avatar/`) needs `b''.join(resp.streaming_content)`. For the voice recorder launch Chromium with `--use-fake-ui-for-media-stream --use-fake-device-for-media-stream` and grant `microphone`.
- `python manage.py test whatsapp` has 153 tests (`whatsapp.tests_inbox_actions` covers the write actions with WAHA mocked). Check `pgrep -af "[m]anage.py test"` first, because the test DB is shared.
