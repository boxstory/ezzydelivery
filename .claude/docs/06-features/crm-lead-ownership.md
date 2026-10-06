# CRM lead ownership — managers, the pool, Take / Release, idle flag

Since 2026-10-06. All rules live in `crm/ownership.py`; views only call it.

## Who sees what

| Person | Sees | Can assign |
|---|---|---|
| **Lead manager**: `Profile.lead_manager`, or any super admin | Every lead | Anyone on the Operations or Marketing desk, or nobody |
| **Operations / Marketing staff** | Their own leads + the **unassigned pool** | Only themselves (Take) or nobody (Release) |
| **Finance only** | Their own leads + the pool, if they can reach the CRM at all | Nothing: they can't take leads |

Once a lead is taken, it disappears for everyone except its owner and the managers. This applies to the
board, the list, both CSV exports and the Google export, the driver map, the reports, the
marketing overview, the sidebar overdue badges, lead search and suggestions in the WhatsApp inbox,
and the merge candidates.
Opening a hidden lead's URL redirects to the list with "Lead #N belongs to X". Every per-lead
endpoint (`update`, `update-stage`, notes, merge, chat link, AI summary, media) returns a
**JSON 403**, because its callers are `fetch()` calls that read `error`.

The lead manager role is toggled on **Staff Roles** (`/workforce/staff-roles/`), in the "Lead Manager"
column. ezzyadmin holds it; super admins always count as managers.

## Take / Release / Take next

- **Take**: `POST crm/leads/<id>/claim/`. A conditional UPDATE (`assigned_to IS NULL`), so when
  two people press Take at once, one wins and the other is told who got it.
- **Release**: `POST crm/leads/<id>/release/`. Only the owner can release; a manager clears the
  owner with the assignee picker instead.
- **Take next**: `POST crm/leads/claim-next/` with `category`. Takes the **newest** open,
  unassigned lead on that board and opens it. It takes the newest, not the oldest, because the pool
  still holds months of history and a fresh enquiry is the one to call first.
- Each endpoint answers a form post with a flash message and a redirect to `next` (same host only).
  It answers an `X-Requested-With: XMLHttpRequest` call with JSON.
- Every owner change, wherever it comes from, goes through `ownership.set_owner()`: the lead
  page's picker, the WhatsApp inbox panel and `crm_lead_update`. It logs an `assignment` entry
  on the timeline.

Buttons: a **Take** button on unassigned board cards and list rows. On the lead page, **Assign to
me** or **Release to pool**, with the picker for managers only. On `/workforce/marketing/`, the
**My Leads** card holds two **Take next** buttons.

## `assigned_at` and the idle flag

`Lead.assigned_at` is stamped by `Lead.save()` whenever `assigned_to` changes, and by the
ownership UPDATEs. A lead is **idle** when all of these hold:

1. It has an owner.
2. It is open.
3. It was taken at least `IDLE_DAYS` (7) days ago.
4. **The owner** has logged no timeline activity on it in the last 7 days.

A manager's note does not count, and neither does a WhatsApp sent from the composer, because the
composer writes no timeline entry.

It shows up as:

- an **Idle 7d+** label on board cards and list rows
- an **Idle 7+ days** badge on the lead page
- the team-wide "Idle Business Leads / Driver Applicants" rows on the overview, for managers only
- the idle count in each person's My Leads row
- the `?idle=1` filter on the list, board and exports, which shows as a removable chip.

Nothing is auto-released. The flag tells a manager whom to chase.

## Gotchas

- **The lead page's Save button only posts `assigned_to` when the picker exists.** Before this
  change it always posted it. Without the picker, that blank would clear the owner on every save.
- `sync_lead_from_pricing_status` (legacy pricing-inquiry page) now only fills an **empty** owner.
  The legacy page re-posts its own, often stale, assignee on every status save. Before this
  change it silently overwrote or cleared a claim.
- `crm_lead_link_business` (the business verification page) is **not** ownership-gated. It is an
  Operations verification action, and its lead picker lists every open business lead.
- The WhatsApp inbox still shows the **connected** lead for a chat even when someone else owns
  it: name, stage and owner, so nobody starts a duplicate card. It shows that card read-only,
  without the working-card controls.

Tests: `crm/tests_ownership.py`.
