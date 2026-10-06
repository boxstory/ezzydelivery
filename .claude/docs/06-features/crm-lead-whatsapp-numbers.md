# CRM Lead WhatsApp Numbers (owner, office, accounts…)

Reference for how a CRM lead holds **several WhatsApp numbers**, and how those numbers relate to platform user accounts. Built 2026-09-29; the history is in `.claude/devlog/2026-09-29.md`. The inbox side is in [`waha-inbox.md`](../05-api-integrations/waha-inbox.md).

## The problem it solves

A company talks to us from more than one phone: the owner's mobile, the office line, an accountant. Each is a separate WhatsApp chat. Before 2026-09-29 a lead could hold only its own `phone` plus **one** manual link (`Lead.wa_chat_override`), so linking the office chat silently replaced the owner's.

Each of those people may also **sign up** for their own login (the owner manages the dashboard, the office staff work as a team). A lead must never get in the way of that.

## Data model

| | |
|---|---|
| Primary number | `Lead.phone`: free text, matched automatically to chats by its last 8 digits |
| Linked numbers | `crm.LeadWaLink`: any number of rows per lead |
| Legacy | `Lead.wa_chat_override`: the old single link. **Emptied by migration; nothing should write it.** |

`LeadWaLink` fields:

| Field | Meaning |
|---|---|
| `lead` | FK, `related_name='wa_links'`, cascade delete |
| `identifier` | Bare digits: a phone (`97455667788`) **or** a WhatsApp lid (14-15 digits) |
| `session` | WAHA session the chat was linked on. It matters for lids, which only mean something on the number that issued them |
| `label` | Who the number is: Owner, Office, Manager, Accounts, Driver, Other, or free text up to 40 characters |
| `created_by`, `created_at` | Audit |

Unique on `(lead, identifier)`, and ordered by `created_at`.

**Migrations**
- `crm/0013_lead_wa_links`: creates the table.
- `crm/0014_move_wa_chat_override_to_links`: copies every non-empty `wa_chat_override` into a link (session = the lead's `wa_session`, unless that is `__all__`), then clears the field. 189 links were moved on 2026-09-29. The reverse step copies each lead's first link back.

## Reading and writing: the only entry points

| Purpose | Use |
|---|---|
| All linked identifiers of a lead | `lead.wa_link_values`, a list in link order that also honours a stray legacy `wa_chat_override`. For many leads, `prefetch_related('wa_links')` first (`_annotate_wa_chats` does this). |
| Add a number | `crm.services.add_wa_link(lead, identifier, session='', label='', user=None)`. Returns `(link, created)`. **Adds, never replaces**; on a repeat it only fills a missing label or session. |
| Remove a number | `crm.services.remove_wa_link(lead, identifier)`. Also clears the legacy field if it held that value. |
| A linked phone turned out to be a lid | `crm.services.repoint_wa_link(lead, old, new)` |
| Numbers plus accounts for display | `crm.services.lead_wa_numbers(lead)`: primary phone (label "Primary") plus each link, with `accounts`, `blocked`, and `phone`: a lid's real number from `lid_phones()` (contact directory, then the cached WAHA lids map; never a live call), or '' when unknown |
| Who registered on these numbers | `crm.services.accounts_for_numbers(identifiers)` |

Readers already switched to `wa_link_values`:
- `wa_identifiers_for(phone, overrides)` (accepts a str or a list) and `_lead_wa_identifiers()`, which build a lead's conversation;
- `_annotate_wa_chats()` (board "has chat" pills);
- `_search_term_q()` (search by any linked number);
- the guards in `_lead_wa_conversation` and `crm_lead_wa_media`;
- the `_lead_wa_chat_targets()` send fallback (first link, when the phone is blank);
- driver matching (`_driver_match_keys(lead.phone, *lead.wa_link_values)`);
- `backfill_lead_wa_chats`, `wa_triage.promote`;
- the inbox's `chat_panel.connected_leads()`.

**Adding a new feature that reads a lead's WhatsApp identity?** Go through `wa_link_values` / `_lead_wa_identifiers`, and never read `wa_chat_override`.

## Lid safety

A lid is not a phone. Running it through `_phone_variants()` invents `974` + its last 8 digits, a real-looking number that belongs to a stranger. Always check `crm.services.is_lid_value()` before treating an identifier as a phone (digits only, more than 13 digits long). `wa_identifiers_for` and `accounts_for_numbers` already do. A lid resolves to a phone only through `WhatsAppContact` (or the cached WAHA lids map).

## User accounts vs leads

- **Leads never block signup.** The duplicate checks in `core/forms.py` (≈ lines 268-278) and `core/views.py` (≈ 2137-2246) compare a number against **other user accounts** only. The owner and the office each have their own number, so each can register even when both are linked to the same lead. Only the same number registering twice is refused.
- `accounts_for_numbers()` **reports** who registered each number: it matches `Profile.phone` or `Profile.whatsapp` on the last 8 digits (regex, so formatted numbers match) and resolves lids through `WhatsAppContact`. The role is one of:
  - `Staff`: `user.is_staff` or `Profile.is_staff`;
  - `Client · <business name>`: owns a `Business`;
  - `Driver`: has an approved `fleet.Driver`;
  - `Driver applicant`: has any other `Driver` row;
  - `Client team`: `Profile.is_business`;
  - `Customer`: anything else.
- **Once a number has an account, the CRM hides its chat.** `crm_services.wa_read_blocked()` refuses to open conversations with platform-account numbers because they carry login and verification codes (see the memory note `whatsapp-stored-secrets`). `lead_wa_numbers()` sets `blocked=True`, and the UI shows "chat hidden — this number has an account". The WAHA inbox (htpasswd ops page) deliberately does not apply that gate.

## UI

**CRM lead page** (`/workforce/crm/leads/<id>/`, conversation panel):
- A **Numbers** list (`#workforce_crm_detail_list_wa_numbers`) is always visible. Each row shows the label, the number (a lid shows its known phone with the id on hover; "Private WhatsApp id …" only when no phone is known), the session, the account(s) on it and the blocked note. Every non-primary row has **Unlink**.
- The "Link chat / Link another number" linker has a **"Who is this number?"** field (datalist of suggestions) posted as `label` with the pick. The page reloads after any successful link, even when no messages exist yet.
- Styles are the `.crmd__numbers` / `.crmd__number*` rules in `workforce/css/crm.css`, whose `?v=` was bumped in all 15 templates that link it. JS is in `crm_lead_detail.js` (`[data-unlink-number]` handler, label read on link).

**WAHA inbox** (`/waha/wa-chats/`, contact panel):
- "Link this chat" has a "Who is this?" input (`#wa-label-options` datalist). The confirm says the number is **added alongside** any existing ones.
- The lead card header shows this chat's role: the link's label, or "Primary number".
- The working card lists all numbers (`.wa-nums`), marks "this chat", and shows the account on each.
- "Unlink" in the inbox only removes a *linked* number, never the lead's own phone.

**Admin**: `LeadWaLinkInline` on the Lead admin, and search by `wa_links__identifier`.

## Endpoints

| Route | Name | Desk | Body |
|---|---|---|---|
| `POST /workforce/crm/leads/<id>/link-chat/` | `crm_lead_link_chat` | Marketing (+ admin) | `identifier`, `session`, optional `label`. Adds a link, then pulls that chat's history from WAHA |
| `POST /workforce/crm/leads/<id>/unlink-chat/` | `crm_lead_unlink_chat` | Marketing (+ admin) | `identifier` |
| `POST /waha/wa-chats/link-lead/` | `wa_chats_link_lead` | htpasswd + Django CRM link rights + CSRF | `{lead_id, chatId, session, label}` or `{action:'unlink', …}` |

New workforce routes must be classified in `core/departments.py` or they fail closed; `crm_lead_unlink_chat` sits next to `crm_lead_link_chat` in `_MKT`.

## Tests

- `crm.tests.LeadWaLinkTests` (6 tests):
  - linking adds instead of replacing;
  - every number feeds the conversation, and a lid is never expanded;
  - remove also clears the legacy field;
  - the inbox finds the lead through its second number (with its label);
  - inbox link/unlink keeps the other numbers and can't unlink the primary;
  - the account on a number is reported.
- `crm.tests.WaTriageTests.test_promote_pins_the_conversation_it_came_from` now asserts the sender's lid became a link.
- `workforce.tests_views.LeadWaLidIdentifierTests` still set `wa_chat_override` directly. They pass because `wa_link_values` honours the legacy field.
- **Known unrelated failure**: `crm.tests.ConvertTests.test_convert_creates_pending_business_and_is_idempotent` (2 businesses instead of 1) fails identically at HEAD, before this work.
- **Run on a fresh test DB** (`--noinput`, not `--keepdb`) when the stage-seed tests fail en masse. The shared `test_ezzy_dl_db` goes stale when other sessions' runs wipe the seeded `LeadStage` rows. Check `pgrep -af "[m]anage.py test"` first.

## Automatic owner link: office number on the form, owner on WhatsApp (2026-10-04)

A business usually fills the pricing form with the office line while the owner chats from their own phone, often as a lid with no phone at all. Phone matching can never join those, so a short reference does (`crm/chat_links.py`):

- **Website first.** The WhatsApp buttons on the quote page and the thank-you page prefill `… (Ref P243-b7ad4a)`; the WhatsApp quick inquiry's message ends `(Ref W<id>-…)`. The six characters are an HMAC of the id keyed on `SECRET_KEY`, so an id cannot be guessed into someone else's lead. `waha_webhook` passes every new inbound 1:1 message to `link_from_message`: a valid reference links that chat to the lead as **Owner** (a lid is stored with its session).
- **WhatsApp first.** "Send Pricing Link" in the inbox (`crm_wa_send_link`) rewrites `https://ezzydelivery.qa/3pl/pricing/` in the message to `…/3pl/pricing/?wa=<8-char code>` and records a `crm.PricingLinkRef` (chat number, session, who sent it). `/3pl/pricing/` and `/3pl/inquiry/` keep the code in the visitor's session; when the form (or the quick inquiry) creates its lead, `link_from_pricing_ref` links that chat as Owner and stamps the ref `used_at` / `lead`.
- Either way, `attach_chat_to_lead` also folds any separate open card for that chat into one, with the **older card staying primary** like `auto_merge_duplicate`. It is reversible with Unmerge and logged on the timeline. It never creates a lead.

**Wider duplicate check** (`crm/services.py`): a number counts as the card's phone, 2nd mobile or any phone-shaped linked number (`_cards_with_numbers`). "Add Business Lead" on a chat (`create_lead_from_wa_number`) opens that card instead of creating a second one, linking the chat when it matched on the 2nd mobile. The pricing form's **operation-team number** is matched by its last 8 digits, but only for the lead page's merge **suggestions** (`duplicate_candidates(include_ops=True)`), never for an automatic merge. One owner can run two shops and type the same number into both forms; on production that was #62 "rowad altaqah" vs #69/#70 "Laloshcandy".

Tests: `crm.tests_chat_links` (14).

## Not built (yet)

- Chats that arrived before the reference existed (16 thank-you-page hand-offs up to 2026-10-04) carried only the generic text. Matching them by time is ambiguous (2–3 enquiries in the same 3 h), so they are left to staff and the merge suggestions.

- No "default send number" per lead. Sending goes to the conversation you pick, or the lead's own phone / first link.
- No stored FK from a link to the user account. Accounts are looked up live from `Profile`, so they are always current.
