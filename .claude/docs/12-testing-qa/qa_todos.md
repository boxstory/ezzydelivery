# QA Audit — EzzyDelivery

> **This file is generated.** Regenerate with `python scripts/qa_scan.py`
> (or `python manage.py qa_evaluate --update-todos`). Do not hand-edit the finding
> counts — they are overwritten on every run.
>
> **Your triage IS preserved.** The checkbox mark and any `— NOTE: …` you add to a
> finding line survive regeneration, keyed off the `<!-- id: … -->` marker. The scanner
> will never un-tick a decision you made.

## Marks

| Mark | Meaning |
|------|---------|
| `[ ]` | Open — not yet looked at |
| `[x]` | Done, or verified a non-issue |
| `[~]` | Won't fix / intentional — **add a `— NOTE:` saying why** |
| `[!]` | Confirmed and urgent |

Anything with a `[~]` needs a note. A bare `[~]` is indistinguishable from giving up.


Last scanned: 2026-08-02


---

## Summary

| Category | Open | `[!]` | Total | Occurrences |
|---|---:|---:|---:|---:|
| Inline `style="` attributes in templates | 52 | — | 52 | 1374 |
| Inline `onclick=` handlers | 34 | — | 34 | 494 |
| Hardcoded colours instead of Brand Kit tokens | 25 | — | 25 | 10853 |
| `!important` in project CSS | 18 | — | 18 | 992 |
| URL-routed views with no decorator (needs human triage) | 9 | 6 | 81 | 9 |
| Buttons with no accessible name | 106 | — | 106 | 240 |
| `<style>` blocks in templates | 8 | — | 8 | 8 |
| Large stylesheets with almost no breakpoints | 26 | — | 26 | 39 |
| `print()` in shipped application code | 0 | — | 1 | — |

**278 open findings (6 marked `[!]` urgent), 73 triaged and retired.**

---

## Findings

### Inline `style="` attributes in templates

_CLAUDE.md forbids inline styles. Extract to BEM classes per the `/css-fix` skill. Only files with 10+ are listed; the long tail is in the totals._

**52 open / 52 findings** · 1374 occurrences outstanding

- [ ] `fleet/templates/fleet/parts/cod_collection.html` — 153 inline `style="` attributes <!-- id: inline-style:fleet/templates/fleet/parts/cod_collection.html -->
- [ ] `fleet/templates/fleet/cod_submission_pwa.html` — 56 inline `style="` attributes <!-- id: inline-style:fleet/templates/fleet/cod_submission_pwa.html -->
- [ ] `fleet/templates/fleet/parts/task_detail_sheet.html` — 52 inline `style="` attributes <!-- id: inline-style:fleet/templates/fleet/parts/task_detail_sheet.html -->
- [ ] `fleet/templates/fleet/cod_collection_pwa.html` — 50 inline `style="` attributes <!-- id: inline-style:fleet/templates/fleet/cod_collection_pwa.html -->
- [ ] `fleet/templates/fleet/parts/driver_earnings.html` — 48 inline `style="` attributes <!-- id: inline-style:fleet/templates/fleet/parts/driver_earnings.html -->
- [ ] `workforce/templates/workforce/order_detail.html` — 47 inline `style="` attributes <!-- id: inline-style:workforce/templates/workforce/order_detail.html -->
- [ ] `workforce/templates/workforce/temp_orders.html` — 45 inline `style="` attributes <!-- id: inline-style:workforce/templates/workforce/temp_orders.html -->
- [ ] `delivery/templates/delivery/parts/tasks_all.html` — 42 inline `style="` attributes <!-- id: inline-style:delivery/templates/delivery/parts/tasks_all.html -->
- [ ] `fleet/templates/fleet/driver_settings_pwa.html` — 40 inline `style="` attributes <!-- id: inline-style:fleet/templates/fleet/driver_settings_pwa.html -->
- [ ] `workforce/templates/workforce/parts/delivery_task_edit.html` — 36 inline `style="` attributes <!-- id: inline-style:workforce/templates/workforce/parts/delivery_task_edit.html -->
- [ ] `warehouse/templates/warehouse/receive_stock.html` — 35 inline `style="` attributes <!-- id: inline-style:warehouse/templates/warehouse/receive_stock.html -->
- [ ] `webpages/templates/webpages/page_not_found.html` — 35 inline `style="` attributes <!-- id: inline-style:webpages/templates/webpages/page_not_found.html -->
- [ ] `core/templates/core/parts/join_driver_form.html` — 34 inline `style="` attributes <!-- id: inline-style:core/templates/core/parts/join_driver_form.html -->
- [ ] `workforce/templates/workforce/parts/delivery_task_detail.html` — 32 inline `style="` attributes <!-- id: inline-style:workforce/templates/workforce/parts/delivery_task_detail.html -->
- [ ] `workforce/templates/workforce/tasks_live_map.html` — 31 inline `style="` attributes <!-- id: inline-style:workforce/templates/workforce/tasks_live_map.html -->
- [ ] `fleet/templates/fleet/staff_cod_submission_edit.html` — 30 inline `style="` attributes <!-- id: inline-style:fleet/templates/fleet/staff_cod_submission_edit.html -->
- [ ] `workforce/templates/workforce/cod_settlement_report.html` — 28 inline `style="` attributes <!-- id: inline-style:workforce/templates/workforce/cod_settlement_report.html -->
- [ ] `workforce/templates/workforce/parts/components/_tasks_status_modal.html` — 28 inline `style="` attributes <!-- id: inline-style:workforce/templates/workforce/parts/components/_tasks_status_modal.html -->
- [ ] `workforce/templates/workforce/auto_triggers_list.html` — 27 inline `style="` attributes <!-- id: inline-style:workforce/templates/workforce/auto_triggers_list.html -->
- [ ] `workforce/templates/workforce/mapping_manager.html` — 24 inline `style="` attributes <!-- id: inline-style:workforce/templates/workforce/mapping_manager.html -->
- [ ] `workforce/templates/workforce/temp_orders_by_date.html` — 24 inline `style="` attributes <!-- id: inline-style:workforce/templates/workforce/temp_orders_by_date.html -->
- [ ] `fleet/templates/fleet/parts/driver_profile_mobile.html` — 23 inline `style="` attributes <!-- id: inline-style:fleet/templates/fleet/parts/driver_profile_mobile.html -->
- [ ] `fleet/templates/fleet/task_navigation_pwa.html` — 22 inline `style="` attributes <!-- id: inline-style:fleet/templates/fleet/task_navigation_pwa.html -->
- [ ] `fleet/templates/fleet/driver_notifications_pwa.html` — 21 inline `style="` attributes <!-- id: inline-style:fleet/templates/fleet/driver_notifications_pwa.html -->
- [ ] `workforce/templates/workforce/import_wizard.html` — 21 inline `style="` attributes <!-- id: inline-style:workforce/templates/workforce/import_wizard.html -->
- [ ] `workforce/templates/workforce/orders_api.html` — 21 inline `style="` attributes <!-- id: inline-style:workforce/templates/workforce/orders_api.html -->
- [ ] `fleet/templates/fleet/driver_help_pwa.html` — 20 inline `style="` attributes <!-- id: inline-style:fleet/templates/fleet/driver_help_pwa.html -->
- [ ] `fleet/templates/fleet/staff_cod_submissions.html` — 19 inline `style="` attributes <!-- id: inline-style:fleet/templates/fleet/staff_cod_submissions.html -->
- [ ] `orders/templates/orders/order_details.html` — 19 inline `style="` attributes <!-- id: inline-style:orders/templates/orders/order_details.html -->
- [ ] `workforce/templates/workforce/auto_flow_add.html` — 19 inline `style="` attributes <!-- id: inline-style:workforce/templates/workforce/auto_flow_add.html -->
- [ ] `fleet/templates/fleet/driver_profile_pwa.html` — 15 inline `style="` attributes <!-- id: inline-style:fleet/templates/fleet/driver_profile_pwa.html -->
- [ ] `orders/templates/orders/order_update.html` — 15 inline `style="` attributes <!-- id: inline-style:orders/templates/orders/order_update.html -->
- [ ] `workforce/templates/workforce/auto_flows_list.html` — 15 inline `style="` attributes <!-- id: inline-style:workforce/templates/workforce/auto_flows_list.html -->
- [ ] `workforce/templates/workforce/forms/pricing_inquiry_detail.html` — 15 inline `style="` attributes <!-- id: inline-style:workforce/templates/workforce/forms/pricing_inquiry_detail.html -->
- [ ] `workforce/templates/workforce/view_business_profile.html` — 15 inline `style="` attributes <!-- id: inline-style:workforce/templates/workforce/view_business_profile.html -->
- [ ] `fleet/templates/fleet/parts/driver_performance.html` — 14 inline `style="` attributes <!-- id: inline-style:fleet/templates/fleet/parts/driver_performance.html -->
- [ ] `fleet/templates/fleet/pickup_scanner_pwa.html` — 14 inline `style="` attributes <!-- id: inline-style:fleet/templates/fleet/pickup_scanner_pwa.html -->
- [ ] `product/templates/product/product_api_wizard.html` — 14 inline `style="` attributes <!-- id: inline-style:product/templates/product/product_api_wizard.html -->
- [ ] `workforce/templates/workforce/business_license_detail.html` — 14 inline `style="` attributes <!-- id: inline-style:workforce/templates/workforce/business_license_detail.html -->
- [ ] `workforce/templates/workforce/onedrive_sources.html` — 14 inline `style="` attributes <!-- id: inline-style:workforce/templates/workforce/onedrive_sources.html -->
- [ ] `workforce/templates/workforce/parts/status_timeline.html` — 14 inline `style="` attributes <!-- id: inline-style:workforce/templates/workforce/parts/status_timeline.html -->
- [ ] `workforce/templates/workforce/temp_orders_browse.html` — 14 inline `style="` attributes <!-- id: inline-style:workforce/templates/workforce/temp_orders_browse.html -->
- [ ] `fleet/templates/fleet/driver_earnings_pwa.html` — 13 inline `style="` attributes <!-- id: inline-style:fleet/templates/fleet/driver_earnings_pwa.html -->
- [ ] `fleet/templates/fleet/driver_tasks_pwa.html` — 13 inline `style="` attributes <!-- id: inline-style:fleet/templates/fleet/driver_tasks_pwa.html -->
- [ ] `workforce/templates/workforce/driver_detail.html` — 13 inline `style="` attributes <!-- id: inline-style:workforce/templates/workforce/driver_detail.html -->
- [ ] `core/templates/core/parts/join_business_form.html` — 12 inline `style="` attributes <!-- id: inline-style:core/templates/core/parts/join_business_form.html -->
- [ ] `ezzy_api/templates/ezzy_api/docs/authentication.html` — 12 inline `style="` attributes <!-- id: inline-style:ezzy_api/templates/ezzy_api/docs/authentication.html -->
- [ ] `workforce/templates/workforce/parts/components/_tasks_card_view.html` — 12 inline `style="` attributes <!-- id: inline-style:workforce/templates/workforce/parts/components/_tasks_card_view.html -->
- [ ] `core/templates/core/profile_complete_update.html` — 11 inline `style="` attributes <!-- id: inline-style:core/templates/core/profile_complete_update.html -->
- [ ] `workforce/templates/workforce/import_history.html` — 11 inline `style="` attributes <!-- id: inline-style:workforce/templates/workforce/import_history.html -->
- [ ] `workforce/templates/workforce/seller_detail.html` — 11 inline `style="` attributes <!-- id: inline-style:workforce/templates/workforce/seller_detail.html -->
- [ ] `workforce/templates/workforce/temp_auto_stages.html` — 11 inline `style="` attributes <!-- id: inline-style:workforce/templates/workforce/temp_auto_stages.html -->

<details><summary>Sample line numbers (regenerated each run — do not cite these elsewhere)</summary>

- `fleet/templates/fleet/parts/cod_collection.html` → lines 39, 45, 53, 56, 57
- `fleet/templates/fleet/cod_submission_pwa.html` → lines 19, 20, 23, 24, 28
- `fleet/templates/fleet/parts/task_detail_sheet.html` → lines 17, 27, 37, 52, 83
- `fleet/templates/fleet/cod_collection_pwa.html` → lines 14, 38, 44, 46, 47
- `fleet/templates/fleet/parts/driver_earnings.html` → lines 40, 55, 60, 63, 64
- `workforce/templates/workforce/order_detail.html` → lines 161, 163, 165, 167, 169
- `workforce/templates/workforce/temp_orders.html` → lines 16, 51, 221, 223, 226
- `delivery/templates/delivery/parts/tasks_all.html` → lines 131, 220, 233, 239, 241
- `fleet/templates/fleet/driver_settings_pwa.html` → lines 11, 23, 35, 40, 45
- `workforce/templates/workforce/parts/delivery_task_edit.html` → lines 16, 19, 23, 24, 25
- `warehouse/templates/warehouse/receive_stock.html` → lines 38, 41, 44, 46, 62
- `webpages/templates/webpages/page_not_found.html` → lines 20, 23, 29, 33, 36
- `core/templates/core/parts/join_driver_form.html` → lines 35, 37, 39, 72, 136
- `workforce/templates/workforce/parts/delivery_task_detail.html` → lines 124, 217, 276, 366, 391
- `workforce/templates/workforce/tasks_live_map.html` → lines 21, 24, 35, 39, 65

</details>

### Inline `onclick=` handlers

_Inline handlers cannot be CSP-hardened, break under HTMX swaps, and hide behaviour from the JS file. Replace with `data-action` attributes + event delegation — the pattern already used in the DMS and document-list templates._

**34 open / 34 findings** · 494 occurrences outstanding

- [ ] `fleet/templates/fleet/parts/task_detail_sheet.html` — 36 inline `onclick=` handlers <!-- id: onclick:fleet/templates/fleet/parts/task_detail_sheet.html -->
- [ ] `workforce/templates/workforce/parts/components/_tasks_table_view.html` — 32 inline `onclick=` handlers <!-- id: onclick:workforce/templates/workforce/parts/components/_tasks_table_view.html -->
- [ ] `workforce/templates/workforce/fleet_transactions.html` — 25 inline `onclick=` handlers <!-- id: onclick:workforce/templates/workforce/fleet_transactions.html -->
- [ ] `fleet/templates/fleet/driver_tasks_pwa.html` — 24 inline `onclick=` handlers <!-- id: onclick:fleet/templates/fleet/driver_tasks_pwa.html -->
- [ ] `fleet/templates/fleet/driver_pickups_pwa.html` — 21 inline `onclick=` handlers <!-- id: onclick:fleet/templates/fleet/driver_pickups_pwa.html -->
- [ ] `workforce/templates/workforce/temp_orders.html` — 21 inline `onclick=` handlers <!-- id: onclick:workforce/templates/workforce/temp_orders.html -->
- [ ] `workforce/templates/workforce/onedrive_sources.html` — 20 inline `onclick=` handlers <!-- id: onclick:workforce/templates/workforce/onedrive_sources.html -->
- [ ] `warehouse/templates/warehouse/parts/wh_sidebar_mobile.html` — 19 inline `onclick=` handlers <!-- id: onclick:warehouse/templates/warehouse/parts/wh_sidebar_mobile.html -->
- [ ] `workforce/templates/workforce/parts/dashboard_sidebar_workforce_mob.html` — 19 inline `onclick=` handlers <!-- id: onclick:workforce/templates/workforce/parts/dashboard_sidebar_workforce_mob.html -->
- [ ] `workforce/templates/workforce/orders_bulk_import.html` — 16 inline `onclick=` handlers <!-- id: onclick:workforce/templates/workforce/orders_bulk_import.html -->
- [ ] `fleet/templates/fleet/driver_profile_pwa.html` — 15 inline `onclick=` handlers <!-- id: onclick:fleet/templates/fleet/driver_profile_pwa.html -->
- [ ] `workforce/templates/workforce/parts/delivery_task_detail.html` — 15 inline `onclick=` handlers <!-- id: onclick:workforce/templates/workforce/parts/delivery_task_detail.html -->
- [ ] `orders/templates/orders/bulk_import.html` — 14 inline `onclick=` handlers <!-- id: onclick:orders/templates/orders/bulk_import.html -->
- [ ] `workforce/templates/workforce/order_detail.html` — 14 inline `onclick=` handlers <!-- id: onclick:workforce/templates/workforce/order_detail.html -->
- [ ] `workforce/templates/workforce/parts/lists/orders_list_view.html` — 14 inline `onclick=` handlers <!-- id: onclick:workforce/templates/workforce/parts/lists/orders_list_view.html -->
- [ ] `workforce/templates/workforce/tasks_live_map.html` — 14 inline `onclick=` handlers <!-- id: onclick:workforce/templates/workforce/tasks_live_map.html -->
- [ ] `workforce/templates/workforce/parts/lists/dl_list_followup.html` — 13 inline `onclick=` handlers <!-- id: onclick:workforce/templates/workforce/parts/lists/dl_list_followup.html -->
- [ ] `templates/delivery/zone_map.html` — 12 inline `onclick=` handlers <!-- id: onclick:templates/delivery/zone_map.html -->
- [ ] `workforce/templates/workforce/auto_flow_add.html` — 12 inline `onclick=` handlers <!-- id: onclick:workforce/templates/workforce/auto_flow_add.html -->
- [ ] `workforce/templates/workforce/mapping_manager.html` — 12 inline `onclick=` handlers <!-- id: onclick:workforce/templates/workforce/mapping_manager.html -->
- [ ] `workforce/templates/workforce/temp_orders_by_date.html` — 12 inline `onclick=` handlers <!-- id: onclick:workforce/templates/workforce/temp_orders_by_date.html -->
- [ ] `fleet/templates/fleet/driver_earnings_pwa.html` — 10 inline `onclick=` handlers <!-- id: onclick:fleet/templates/fleet/driver_earnings_pwa.html -->
- [ ] `workforce/templates/workforce/orders_api.html` — 10 inline `onclick=` handlers <!-- id: onclick:workforce/templates/workforce/orders_api.html -->
- [ ] `workforce/templates/workforce/temp_verify_queue.html` — 10 inline `onclick=` handlers <!-- id: onclick:workforce/templates/workforce/temp_verify_queue.html -->
- [ ] `business/templates/business/parts/business_settings_api_list.html` — 9 inline `onclick=` handlers <!-- id: onclick:business/templates/business/parts/business_settings_api_list.html -->
- [ ] `fleet/templates/fleet/parts/driver_reports.html` — 9 inline `onclick=` handlers <!-- id: onclick:fleet/templates/fleet/parts/driver_reports.html -->
- [ ] `workforce/templates/workforce/auto_triggers_list.html` — 9 inline `onclick=` handlers <!-- id: onclick:workforce/templates/workforce/auto_triggers_list.html -->
- [ ] `workforce/templates/workforce/import_wizard.html` — 9 inline `onclick=` handlers <!-- id: onclick:workforce/templates/workforce/import_wizard.html -->
- [ ] `delivery/templates/delivery/parts/tasks_all.html` — 8 inline `onclick=` handlers <!-- id: onclick:delivery/templates/delivery/parts/tasks_all.html -->
- [ ] `fleet/templates/fleet/cod_collection_pwa.html` — 8 inline `onclick=` handlers <!-- id: onclick:fleet/templates/fleet/cod_collection_pwa.html -->
- [ ] `orders/templates/orders/parts/order_list_view.html` — 8 inline `onclick=` handlers <!-- id: onclick:orders/templates/orders/parts/order_list_view.html -->
- [ ] `templates/delivery/edit_polygon.html` — 8 inline `onclick=` handlers <!-- id: onclick:templates/delivery/edit_polygon.html -->
- [ ] `workforce/templates/workforce/driver_detail.html` — 8 inline `onclick=` handlers <!-- id: onclick:workforce/templates/workforce/driver_detail.html -->
- [ ] `workforce/templates/workforce/temp_orders_browse.html` — 8 inline `onclick=` handlers <!-- id: onclick:workforce/templates/workforce/temp_orders_browse.html -->

<details><summary>Sample line numbers (regenerated each run — do not cite these elsewhere)</summary>

- `fleet/templates/fleet/parts/task_detail_sheet.html` → lines 11, 19, 56, 117, 169
- `workforce/templates/workforce/parts/components/_tasks_table_view.html` → lines 18, 23, 26, 29, 32
- `workforce/templates/workforce/fleet_transactions.html` → lines 197, 200, 208, 215, 258
- `fleet/templates/fleet/driver_tasks_pwa.html` → lines 9, 32, 40, 48, 56
- `fleet/templates/fleet/driver_pickups_pwa.html` → lines 22, 27, 32, 40, 78
- `workforce/templates/workforce/temp_orders.html` → lines 88, 143, 268, 330, 358
- `workforce/templates/workforce/onedrive_sources.html` → lines 80, 83, 86, 89, 153
- `warehouse/templates/warehouse/parts/wh_sidebar_mobile.html` → lines 9, 19, 25, 34, 38
- `workforce/templates/workforce/parts/dashboard_sidebar_workforce_mob.html` → lines 9, 36, 76, 123, 148
- `workforce/templates/workforce/orders_bulk_import.html` → lines 111, 117, 157, 160, 204
- `fleet/templates/fleet/driver_profile_pwa.html` → lines 8, 33, 91, 104, 117
- `workforce/templates/workforce/parts/delivery_task_detail.html` → lines 42, 88, 94, 209, 239
- `orders/templates/orders/bulk_import.html` → lines 131, 137, 177, 180, 219
- `workforce/templates/workforce/order_detail.html` → lines 84, 91, 99, 262, 325
- `workforce/templates/workforce/parts/lists/orders_list_view.html` → lines 211, 216, 220, 221, 222

</details>

### Hardcoded colours instead of Brand Kit tokens

_CLAUDE.md requires all styling to use Brand Kit variables. A hardcoded hex will not follow a palette change, so every one is a future inconsistency._

**25 open / 25 findings** · 10853 occurrences outstanding

- [ ] `workforce/static/workforce/css/workforce.css` — 3499 hardcoded hex vs 1875 `var(--…)` — 35% tokenised <!-- id: hex:workforce/static/workforce/css/workforce.css -->
- [ ] `orders/static/orders/css/orders.css` — 1357 hardcoded hex vs 942 `var(--…)` — 41% tokenised <!-- id: hex:orders/static/orders/css/orders.css -->
- [ ] `business/static/business/css/business.css` — 944 hardcoded hex vs 585 `var(--…)` — 38% tokenised <!-- id: hex:business/static/business/css/business.css -->
- [ ] `delivery/static/delivery/css/delivery.css` — 603 hardcoded hex vs 432 `var(--…)` — 42% tokenised <!-- id: hex:delivery/static/delivery/css/delivery.css -->
- [ ] `product/static/product/css/product.css` — 478 hardcoded hex vs 190 `var(--…)` — 28% tokenised <!-- id: hex:product/static/product/css/product.css -->
- [ ] `fleet/static/fleet/css/fleet.css` — 454 hardcoded hex vs 493 `var(--…)` — 52% tokenised <!-- id: hex:fleet/static/fleet/css/fleet.css -->
- [ ] `fleet/static/fleet/css/fleet-bem.css` — 383 hardcoded hex vs 484 `var(--…)` — 56% tokenised <!-- id: hex:fleet/static/fleet/css/fleet-bem.css -->
- [ ] `fleet/static/fleet/css/fleet-pwa-modern.css` — 366 hardcoded hex vs 1259 `var(--…)` — 77% tokenised <!-- id: hex:fleet/static/fleet/css/fleet-pwa-modern.css -->
- [ ] `warehouse/static/warehouse/css/warehouse.css` — 314 hardcoded hex vs 633 `var(--…)` — 67% tokenised <!-- id: hex:warehouse/static/warehouse/css/warehouse.css -->
- [ ] `workforce/static/workforce/css/fleet_transactions.css` — 311 hardcoded hex vs 212 `var(--…)` — 41% tokenised <!-- id: hex:workforce/static/workforce/css/fleet_transactions.css -->
- [ ] `business/static/business/css/business-mobile.css` — 300 hardcoded hex vs 162 `var(--…)` — 35% tokenised <!-- id: hex:business/static/business/css/business-mobile.css -->
- [ ] `workforce/static/workforce/css/verify_queue.css` — 204 hardcoded hex vs 132 `var(--…)` — 39% tokenised <!-- id: hex:workforce/static/workforce/css/verify_queue.css -->
- [ ] `fleet/static/fleet/css/fleet-mobile.css` — 201 hardcoded hex vs 187 `var(--…)` — 48% tokenised <!-- id: hex:fleet/static/fleet/css/fleet-mobile.css -->
- [ ] `workforce/static/workforce/css/pricing_inquiry_detail.css` — 188 hardcoded hex vs 115 `var(--…)` — 38% tokenised <!-- id: hex:workforce/static/workforce/css/pricing_inquiry_detail.css -->
- [ ] `workforce/static/workforce/css/verification.css` — 136 hardcoded hex vs 65 `var(--…)` — 32% tokenised <!-- id: hex:workforce/static/workforce/css/verification.css -->
- [ ] `webpages/static/webpages/css/p2p-pricing.css` — 130 hardcoded hex vs 91 `var(--…)` — 41% tokenised <!-- id: hex:webpages/static/webpages/css/p2p-pricing.css -->
- [ ] `workforce/static/workforce/css/live-map.css` — 123 hardcoded hex vs 4 `var(--…)` — 3% tokenised <!-- id: hex:workforce/static/workforce/css/live-map.css -->
- [ ] `workforce/static/workforce/css/delivery_task_detail.css` — 120 hardcoded hex vs 240 `var(--…)` — 67% tokenised <!-- id: hex:workforce/static/workforce/css/delivery_task_detail.css -->
- [ ] `webpages/static/webpages/css/delivery_pricing_inquiry.css` — 115 hardcoded hex vs 105 `var(--…)` — 48% tokenised <!-- id: hex:webpages/static/webpages/css/delivery_pricing_inquiry.css -->
- [ ] `orders/static/orders/css/order_api_get.css` — 110 hardcoded hex vs 0 `var(--…)` — 0% tokenised <!-- id: hex:orders/static/orders/css/order_api_get.css -->
- [ ] `workforce/static/workforce/css/ai-config.css` — 106 hardcoded hex vs 170 `var(--…)` — 62% tokenised <!-- id: hex:workforce/static/workforce/css/ai-config.css -->
- [ ] `templates/static/mobile-app.css` — 104 hardcoded hex vs 108 `var(--…)` — 51% tokenised <!-- id: hex:templates/static/mobile-app.css -->
- [ ] `workforce/static/workforce/css/fleet_cod_in_hand.css` — 104 hardcoded hex vs 84 `var(--…)` — 45% tokenised <!-- id: hex:workforce/static/workforce/css/fleet_cod_in_hand.css -->
- [ ] `webpages/static/webpages/css/pricing.css` — 102 hardcoded hex vs 58 `var(--…)` — 36% tokenised <!-- id: hex:webpages/static/webpages/css/pricing.css -->
- [ ] `templates/static/base-forms.css` — 101 hardcoded hex vs 133 `var(--…)` — 57% tokenised <!-- id: hex:templates/static/base-forms.css -->

### `!important` in project CSS

_Each one raises the specificity floor for every later rule in that file. Vendor CSS and the Brand Kit override layer are excluded — theirs is intentional._

**18 open / 18 findings** · 992 occurrences outstanding

- [ ] `workforce/static/workforce/css/workforce.css` — 144 `!important` declarations <!-- id: important:workforce/static/workforce/css/workforce.css -->
- [ ] `core/static/core/css/profile-mobile.css` — 103 `!important` declarations <!-- id: important:core/static/core/css/profile-mobile.css -->
- [ ] `core/static/core/css/account-forms.css` — 93 `!important` declarations <!-- id: important:core/static/core/css/account-forms.css -->
- [ ] `webpages/static/webpages/css/seo-landing.css` — 80 `!important` declarations <!-- id: important:webpages/static/webpages/css/seo-landing.css -->
- [ ] `business/static/business/css/business.css` — 69 `!important` declarations <!-- id: important:business/static/business/css/business.css -->
- [ ] `core/static/core/css/core_dashboard.css` — 60 `!important` declarations <!-- id: important:core/static/core/css/core_dashboard.css -->
- [ ] `orders/static/orders/css/orders.css` — 57 `!important` declarations <!-- id: important:orders/static/orders/css/orders.css -->
- [ ] `webpages/static/webpages/css/sidebar-common.css` — 55 `!important` declarations <!-- id: important:webpages/static/webpages/css/sidebar-common.css -->
- [ ] `fleet/static/fleet/css/fleet-mobile.css` — 49 `!important` declarations <!-- id: important:fleet/static/fleet/css/fleet-mobile.css -->
- [ ] `warehouse/static/warehouse/css/warehouse.css` — 48 `!important` declarations <!-- id: important:warehouse/static/warehouse/css/warehouse.css -->
- [ ] `workforce/static/workforce/css/fleet_transactions.css` — 42 `!important` declarations <!-- id: important:workforce/static/workforce/css/fleet_transactions.css -->
- [ ] `core/static/core/css/core.css` — 39 `!important` declarations <!-- id: important:core/static/core/css/core.css -->
- [ ] `orders/static/orders/css/order_api_get.css` — 34 `!important` declarations <!-- id: important:orders/static/orders/css/order_api_get.css -->
- [ ] `webpages/static/webpages/css/brandkit-components.css` — 30 `!important` declarations <!-- id: important:webpages/static/webpages/css/brandkit-components.css -->
- [ ] `fleet/static/fleet/css/fleet-bem.css` — 23 `!important` declarations <!-- id: important:fleet/static/fleet/css/fleet-bem.css -->
- [ ] `workforce/static/workforce/css/ai-config.css` — 23 `!important` declarations <!-- id: important:workforce/static/workforce/css/ai-config.css -->
- [ ] `business/static/business/css/business-mobile.css` — 22 `!important` declarations <!-- id: important:business/static/business/css/business-mobile.css -->
- [ ] `workforce/static/workforce/css/auto-triggers.css` — 21 `!important` declarations <!-- id: important:workforce/static/workforce/css/auto-triggers.css -->

<details><summary>Sample line numbers (regenerated each run — do not cite these elsewhere)</summary>

- `workforce/static/workforce/css/workforce.css` → lines 52, 952, 1380, 2045, 2047
- `core/static/core/css/profile-mobile.css` → lines 86, 135, 168, 169, 170
- `core/static/core/css/account-forms.css` → lines 182, 190, 216, 221, 270
- `webpages/static/webpages/css/seo-landing.css` → lines 144, 145, 146, 151, 152
- `business/static/business/css/business.css` → lines 27, 66, 67, 68, 69
- `core/static/core/css/core_dashboard.css` → lines 47, 48, 49, 50, 65
- `orders/static/orders/css/orders.css` → lines 8, 57, 59, 60, 61
- `webpages/static/webpages/css/sidebar-common.css` → lines 21, 44, 45, 46, 52
- `fleet/static/fleet/css/fleet-mobile.css` → lines 2210, 2211, 2222, 2226, 2227
- `warehouse/static/warehouse/css/warehouse.css` → lines 60, 61, 62, 63, 66
- `workforce/static/workforce/css/fleet_transactions.css` → lines 426, 1742, 1743, 1747, 1748
- `core/static/core/css/core.css` → lines 334, 335, 339, 340, 396
- `orders/static/orders/css/order_api_get.css` → lines 269, 270, 274, 275, 277
- `webpages/static/webpages/css/brandkit-components.css` → lines 119, 126, 257, 258, 259
- `fleet/static/fleet/css/fleet-bem.css` → lines 28, 29, 30, 64, 67

</details>

### URL-routed views with no decorator (needs human triage)

_Restricted to functions wired into a `urls.py`; private helpers are filtered out. Some entries are correctly public (marketing pages, customer tracking, driver signup); others are a missing `@login_required` / `@staff_required`. Triage each, then tick or `[~]`._

**9 open / 81 findings** · **6 marked `[!]` urgent** · 9 occurrences outstanding

- [~] `blog/views.py` → `blog_category()` — no decorator <!-- id: undecorated-view:blog/views.py::blog_category --> — NOTE: Public blog post/index — indexed by search engines.
- [~] `blog/views.py` → `blog_index()` — no decorator <!-- id: undecorated-view:blog/views.py::blog_index --> — NOTE: Public blog post/index — indexed by search engines.
- [~] `blog/views.py` → `blog_post_detail()` — no decorator <!-- id: undecorated-view:blog/views.py::blog_post_detail --> — NOTE: Public blog post/index — indexed by search engines.
- [~] `business/views.py` → `business_profile_display()` — no decorator <!-- id: undecorated-view:business/views.py::business_profile_display --> — NOTE: Deliberately public so crawlers can index the profile + Store structured data (rationale documented inline at business/views.py:650).
- [!] `core/views.py` → `check_phone_availability()` — no decorator <!-- id: undecorated-view:core/views.py::check_phone_availability --> — NOTE: Unauthenticated account-enumeration oracle — confirms whether any given phone number is already registered. Needs throttling, or a response that does not distinguish "taken" from "invalid".
- [!] `core/views.py` → `check_whatsapp_availability()` — no decorator <!-- id: undecorated-view:core/views.py::check_whatsapp_availability --> — NOTE: Same enumeration oracle as check_phone_availability, over WhatsApp numbers.
- [~] `core/views.py` → `join_driver()` — no decorator <!-- id: undecorated-view:core/views.py::join_driver --> — NOTE: Public driver application funnel (/join_us/driver/).
- [~] `core/views.py` → `join_driver_start()` — no decorator <!-- id: undecorated-view:core/views.py::join_driver_start --> — NOTE: Public driver application funnel (/join_us/driver/).
- [~] `core/views.py` → `join_driver_start_ar()` — no decorator <!-- id: undecorated-view:core/views.py::join_driver_start_ar --> — NOTE: Public driver application funnel, Arabic.
- [~] `core/views.py` → `rate_limit_exceeded()` — no decorator <!-- id: undecorated-view:core/views.py::rate_limit_exceeded --> — NOTE: Django error handler, not a user-facing route.
- [ ] `delivery/views.py` → `dl_address_link()` — no decorator <!-- id: undecorated-view:delivery/views.py::dl_address_link --> — NOTE: Unauthenticated read that geocodes and discloses a customer address for any known `dl_task_code`. Same token-strength dependency as the writes above.
- [!] `delivery/views.py` → `dl_address_update()` — no decorator <!-- id: undecorated-view:delivery/views.py::dl_address_update --> — NOTE: Unauthenticated WRITE of a customer delivery address, addressed by `dl_task_number` + `mobile_no`.
- [!] `delivery/views.py` → `get_street_polygon()` — no decorator <!-- id: undecorated-view:delivery/views.py::get_street_polygon --> — NOTE: Unauthenticated, and with `?update_zone=true` it WRITES `zone.polygon` (delivery/views.py — `zone.save(update_fields=[...])`). Also proxies QNAS, so it is an outbound-request and quota surface.
- [ ] `delivery/views.py` → `get_zone_name()` — no decorator <!-- id: undecorated-view:delivery/views.py::get_zone_name --> — NOTE: Unauthenticated, but returns zone-name reference data only. Low impact; no rate limit.
- [!] `delivery/views.py` → `save_location_data()` — no decorator <!-- id: undecorated-view:delivery/views.py::save_location_data --> — NOTE: Unauthenticated WRITE of customer lat/long, addressed only by `dl_task_code`. Token strength is the sole access control.
- [~] `ezzy_api/views.py` → `docs_api_reference()` — no decorator <!-- id: undecorated-view:ezzy_api/views.py::docs_api_reference --> — NOTE: Public API documentation page.
- [~] `ezzy_api/views.py` → `docs_authentication()` — no decorator <!-- id: undecorated-view:ezzy_api/views.py::docs_authentication --> — NOTE: Public API documentation page.
- [~] `ezzy_api/views.py` → `docs_errors()` — no decorator <!-- id: undecorated-view:ezzy_api/views.py::docs_errors --> — NOTE: Public API documentation page.
- [~] `ezzy_api/views.py` → `docs_examples()` — no decorator <!-- id: undecorated-view:ezzy_api/views.py::docs_examples --> — NOTE: Public API documentation page.
- [~] `ezzy_api/views.py` → `docs_faq()` — no decorator <!-- id: undecorated-view:ezzy_api/views.py::docs_faq --> — NOTE: Public API documentation page.
- [~] `ezzy_api/views.py` → `docs_getting_started()` — no decorator <!-- id: undecorated-view:ezzy_api/views.py::docs_getting_started --> — NOTE: Public API documentation page.
- [~] `ezzy_api/views.py` → `docs_index()` — no decorator <!-- id: undecorated-view:ezzy_api/views.py::docs_index --> — NOTE: Public API documentation page.
- [~] `ezzy_api/views.py` → `docs_shopify()` — no decorator <!-- id: undecorated-view:ezzy_api/views.py::docs_shopify --> — NOTE: Public API documentation page.
- [~] `ezzy_api/views.py` → `docs_tiktok()` — no decorator <!-- id: undecorated-view:ezzy_api/views.py::docs_tiktok --> — NOTE: Public API documentation page.
- [~] `ezzy_api/views.py` → `docs_webhooks()` — no decorator <!-- id: undecorated-view:ezzy_api/views.py::docs_webhooks --> — NOTE: Public API documentation page.
- [~] `ezzy_api/views.py` → `docs_woocommerce()` — no decorator <!-- id: undecorated-view:ezzy_api/views.py::docs_woocommerce --> — NOTE: Public API documentation page.
- [~] `orders/views.py` → `customer_tracking()` — no decorator <!-- id: undecorated-view:orders/views.py::customer_tracking --> — NOTE: Token-addressed public customer flow — login is deliberately not required. The URL token is the only control, so this inherits the open finding on predictable `dl_task_number` tokens.
- [~] `orders/views.py` → `customer_tracking_data()` — no decorator <!-- id: undecorated-view:orders/views.py::customer_tracking_data --> — NOTE: Token-addressed public customer flow — login is deliberately not required. The URL token is the only control, so this inherits the open finding on predictable `dl_task_number` tokens.
- [~] `orders/views.py` → `update_location()` — no decorator <!-- id: undecorated-view:orders/views.py::update_location --> — NOTE: Token-addressed public customer flow — login is deliberately not required. The URL token is the only control, so this inherits the open finding on predictable `dl_task_number` tokens.
- [~] `orders/views.py` → `verify_location()` — no decorator <!-- id: undecorated-view:orders/views.py::verify_location --> — NOTE: Token-addressed public customer flow — login is deliberately not required. The URL token is the only control, so this inherits the open finding on predictable `dl_task_number` tokens.
- [~] `orders/views.py` → `verify_location_short()` — no decorator <!-- id: undecorated-view:orders/views.py::verify_location_short --> — NOTE: Token-addressed public customer flow — login is deliberately not required. The URL token is the only control, so this inherits the open finding on predictable `dl_task_number` tokens.
- [ ] `product/views.py` → `product_categories()` — no decorator <!-- id: undecorated-view:product/views.py::product_categories --> — NOTE: Renders an empty context dict — confirm the page is still needed before decorating it.
- [!] `product/views.py` → `test_images()` — no decorator <!-- id: undecorated-view:product/views.py::test_images --> — NOTE: Diagnostic page routed in production at /product/test-images/ (product/urls.py:51) with no auth. Delete the route or gate it behind staff.
- [~] `webpages/views.py` → `about()` — no decorator <!-- id: undecorated-view:webpages/views.py::about --> — NOTE: Public marketing/SEO page — must stay unauthenticated (listed in sitemap.xml).
- [~] `webpages/views.py` → `affiliate()` — no decorator <!-- id: undecorated-view:webpages/views.py::affiliate --> — NOTE: Public marketing/SEO page — must stay unauthenticated (listed in sitemap.xml).
- [~] `webpages/views.py` → `al_wakrah_delivery()` — no decorator <!-- id: undecorated-view:webpages/views.py::al_wakrah_delivery --> — NOTE: Public marketing/SEO page — must stay unauthenticated (listed in sitemap.xml).
- [~] `webpages/views.py` → `business_delivery_qatar()` — no decorator <!-- id: undecorated-view:webpages/views.py::business_delivery_qatar --> — NOTE: Public marketing/SEO page — must stay unauthenticated (listed in sitemap.xml).
- [~] `webpages/views.py` → `careers()` — no decorator <!-- id: undecorated-view:webpages/views.py::careers --> — NOTE: Public marketing/SEO page — must stay unauthenticated (listed in sitemap.xml).
- [~] `webpages/views.py` → `client_faq()` — no decorator <!-- id: undecorated-view:webpages/views.py::client_faq --> — NOTE: Public marketing/SEO page — must stay unauthenticated (listed in sitemap.xml).
- [~] `webpages/views.py` → `client_faq_100()` — no decorator <!-- id: undecorated-view:webpages/views.py::client_faq_100 --> — NOTE: Public marketing/SEO page — must stay unauthenticated (listed in sitemap.xml).
- [~] `webpages/views.py` → `client_guide()` — no decorator <!-- id: undecorated-view:webpages/views.py::client_guide --> — NOTE: Public marketing/SEO page — must stay unauthenticated (listed in sitemap.xml).
- [~] `webpages/views.py` → `cod_delivery_qatar()` — no decorator <!-- id: undecorated-view:webpages/views.py::cod_delivery_qatar --> — NOTE: Public marketing/SEO page — must stay unauthenticated (listed in sitemap.xml).
- [~] `webpages/views.py` → `contactus()` — no decorator <!-- id: undecorated-view:webpages/views.py::contactus --> — NOTE: Public marketing/SEO page — must stay unauthenticated (listed in sitemap.xml).
- [~] `webpages/views.py` → `courier_doha_arabic()` — no decorator <!-- id: undecorated-view:webpages/views.py::courier_doha_arabic --> — NOTE: Public marketing/SEO page — must stay unauthenticated (listed in sitemap.xml).
- [~] `webpages/views.py` → `courier_service_qatar()` — no decorator <!-- id: undecorated-view:webpages/views.py::courier_service_qatar --> — NOTE: Public marketing/SEO page — must stay unauthenticated (listed in sitemap.xml).
- [~] `webpages/views.py` → `delivery_companies_qatar()` — no decorator <!-- id: undecorated-view:webpages/views.py::delivery_companies_qatar --> — NOTE: Public marketing/SEO page — must stay unauthenticated (listed in sitemap.xml).
- [~] `webpages/views.py` → `delivery_doha()` — no decorator <!-- id: undecorated-view:webpages/views.py::delivery_doha --> — NOTE: Public marketing/SEO page — must stay unauthenticated (listed in sitemap.xml).
- [~] `webpages/views.py` → `delivery_inquiry()` — no decorator <!-- id: undecorated-view:webpages/views.py::delivery_inquiry --> — NOTE: Public marketing/SEO page — must stay unauthenticated (listed in sitemap.xml).
- [~] `webpages/views.py` → `delivery_pricing()` — no decorator <!-- id: undecorated-view:webpages/views.py::delivery_pricing --> — NOTE: Public marketing/SEO page — must stay unauthenticated (listed in sitemap.xml).
- [~] `webpages/views.py` → `delivery_qatar_arabic()` — no decorator <!-- id: undecorated-view:webpages/views.py::delivery_qatar_arabic --> — NOTE: Public marketing/SEO page — must stay unauthenticated (listed in sitemap.xml).
- [~] `webpages/views.py` → `delivery_request()` — no decorator <!-- id: undecorated-view:webpages/views.py::delivery_request --> — NOTE: Public marketing/SEO page — must stay unauthenticated (listed in sitemap.xml).
- [~] `webpages/views.py` → `delivery_service_qatar()` — no decorator <!-- id: undecorated-view:webpages/views.py::delivery_service_qatar --> — NOTE: Public marketing/SEO page — must stay unauthenticated (listed in sitemap.xml).
- [~] `webpages/views.py` → `driver_faq()` — no decorator <!-- id: undecorated-view:webpages/views.py::driver_faq --> — NOTE: Public marketing/SEO page — must stay unauthenticated (listed in sitemap.xml).
- [~] `webpages/views.py` → `driver_guide()` — no decorator <!-- id: undecorated-view:webpages/views.py::driver_guide --> — NOTE: Public marketing/SEO page — must stay unauthenticated (listed in sitemap.xml).
- [~] `webpages/views.py` → `ecommerce_delivery_qatar()` — no decorator <!-- id: undecorated-view:webpages/views.py::ecommerce_delivery_qatar --> — NOTE: Public marketing/SEO page — must stay unauthenticated (listed in sitemap.xml).
- [~] `webpages/views.py` → `express_delivery_qatar()` — no decorator <!-- id: undecorated-view:webpages/views.py::express_delivery_qatar --> — NOTE: Public marketing/SEO page — must stay unauthenticated (listed in sitemap.xml).
- [~] `webpages/views.py` → `fleets()` — no decorator <!-- id: undecorated-view:webpages/views.py::fleets --> — NOTE: Public marketing/SEO page — must stay unauthenticated (listed in sitemap.xml).
- [~] `webpages/views.py` → `food_delivery_partner_qatar()` — no decorator <!-- id: undecorated-view:webpages/views.py::food_delivery_partner_qatar --> — NOTE: Public marketing/SEO page — must stay unauthenticated (listed in sitemap.xml).
- [~] `webpages/views.py` → `fulfillment()` — no decorator <!-- id: undecorated-view:webpages/views.py::fulfillment --> — NOTE: Public marketing/SEO page — must stay unauthenticated (listed in sitemap.xml).
- [~] `webpages/views.py` → `handler404()` — no decorator <!-- id: undecorated-view:webpages/views.py::handler404 --> — NOTE: Django error handler, not a user-facing route.
- [~] `webpages/views.py` → `handler500()` — no decorator <!-- id: undecorated-view:webpages/views.py::handler500 --> — NOTE: Django error handler, not a user-facing route.
- [~] `webpages/views.py` → `help_center()` — no decorator <!-- id: undecorated-view:webpages/views.py::help_center --> — NOTE: Public marketing/SEO page — must stay unauthenticated (listed in sitemap.xml).
- [~] `webpages/views.py` → `help_guides()` — no decorator <!-- id: undecorated-view:webpages/views.py::help_guides --> — NOTE: Public marketing/SEO page — must stay unauthenticated (listed in sitemap.xml).
- [~] `webpages/views.py` → `index()` — no decorator <!-- id: undecorated-view:webpages/views.py::index --> — NOTE: Public marketing/SEO page — must stay unauthenticated (listed in sitemap.xml).
- [~] `webpages/views.py` → `inquiry_success()` — no decorator <!-- id: undecorated-view:webpages/views.py::inquiry_success --> — NOTE: Public marketing/SEO page — must stay unauthenticated (listed in sitemap.xml).
- [~] `webpages/views.py` → `instagram_sellers_delivery()` — no decorator <!-- id: undecorated-view:webpages/views.py::instagram_sellers_delivery --> — NOTE: Public marketing/SEO page — must stay unauthenticated (listed in sitemap.xml).
- [~] `webpages/views.py` → `last_mile_delivery_qatar()` — no decorator <!-- id: undecorated-view:webpages/views.py::last_mile_delivery_qatar --> — NOTE: Public marketing/SEO page — must stay unauthenticated (listed in sitemap.xml).
- [~] `webpages/views.py` → `llm_knowledge_panel()` — no decorator <!-- id: undecorated-view:webpages/views.py::llm_knowledge_panel --> — NOTE: Public marketing/SEO page — must stay unauthenticated (listed in sitemap.xml).
- [~] `webpages/views.py` → `logistics_services_qatar()` — no decorator <!-- id: undecorated-view:webpages/views.py::logistics_services_qatar --> — NOTE: Public marketing/SEO page — must stay unauthenticated (listed in sitemap.xml).
- [~] `webpages/views.py` → `lusail_delivery()` — no decorator <!-- id: undecorated-view:webpages/views.py::lusail_delivery --> — NOTE: Public marketing/SEO page — must stay unauthenticated (listed in sitemap.xml).
- [~] `webpages/views.py` → `online_store_delivery_qatar()` — no decorator <!-- id: undecorated-view:webpages/views.py::online_store_delivery_qatar --> — NOTE: Public marketing/SEO page — must stay unauthenticated (listed in sitemap.xml).
- [~] `webpages/views.py` → `p2p_pricing()` — no decorator <!-- id: undecorated-view:webpages/views.py::p2p_pricing --> — NOTE: Public marketing/SEO page — must stay unauthenticated (listed in sitemap.xml).
- [~] `webpages/views.py` → `package_delivery_qatar()` — no decorator <!-- id: undecorated-view:webpages/views.py::package_delivery_qatar --> — NOTE: Public marketing/SEO page — must stay unauthenticated (listed in sitemap.xml).
- [~] `webpages/views.py` → `privacy()` — no decorator <!-- id: undecorated-view:webpages/views.py::privacy --> — NOTE: Public marketing/SEO page — must stay unauthenticated (listed in sitemap.xml).
- [~] `webpages/views.py` → `qcommerce()` — no decorator <!-- id: undecorated-view:webpages/views.py::qcommerce --> — NOTE: Public marketing/SEO page — must stay unauthenticated (listed in sitemap.xml).
- [~] `webpages/views.py` → `same_day_delivery_qatar()` — no decorator <!-- id: undecorated-view:webpages/views.py::same_day_delivery_qatar --> — NOTE: Public marketing/SEO page — must stay unauthenticated (listed in sitemap.xml).
- [~] `webpages/views.py` → `services()` — no decorator <!-- id: undecorated-view:webpages/views.py::services --> — NOTE: Public marketing/SEO page — must stay unauthenticated (listed in sitemap.xml).
- [~] `webpages/views.py` → `shopify_delivery_qatar()` — no decorator <!-- id: undecorated-view:webpages/views.py::shopify_delivery_qatar --> — NOTE: Public marketing/SEO page — must stay unauthenticated (listed in sitemap.xml).
- [~] `webpages/views.py` → `terms()` — no decorator <!-- id: undecorated-view:webpages/views.py::terms --> — NOTE: Public marketing/SEO page — must stay unauthenticated (listed in sitemap.xml).
- [~] `webpages/views.py` → `testimonials()` — no decorator <!-- id: undecorated-view:webpages/views.py::testimonials --> — NOTE: Public marketing/SEO page — must stay unauthenticated (listed in sitemap.xml).
- [~] `webpages/views.py` → `three_pl_qatar()` — no decorator <!-- id: undecorated-view:webpages/views.py::three_pl_qatar --> — NOTE: Public marketing/SEO page — must stay unauthenticated (listed in sitemap.xml).

### Buttons with no accessible name

_An icon-only or `btn-close` button with no `aria-label` is announced as just "button"._

**106 open / 106 findings** · 240 occurrences outstanding

- [ ] `workforce/templates/workforce/temp_orders.html` — 10 button(s) without `aria-label` (7 icon-only, 3 `btn-close`) <!-- id: aria-button:workforce/templates/workforce/temp_orders.html -->
- [ ] `workforce/templates/workforce/seller_detail.html` — 8 button(s) without `aria-label` (8 icon-only) <!-- id: aria-button:workforce/templates/workforce/seller_detail.html -->
- [ ] `orders/templates/orders/parts/order_all_list_content.html` — 6 button(s) without `aria-label` (5 icon-only, 1 `btn-close`) <!-- id: aria-button:orders/templates/orders/parts/order_all_list_content.html -->
- [ ] `workforce/templates/workforce/auto_triggers_list.html` — 6 button(s) without `aria-label` (4 icon-only, 2 `btn-close`) <!-- id: aria-button:workforce/templates/workforce/auto_triggers_list.html -->
- [ ] `workforce/templates/workforce/onedrive_sources.html` — 6 button(s) without `aria-label` (4 icon-only, 2 `btn-close`) <!-- id: aria-button:workforce/templates/workforce/onedrive_sources.html -->
- [ ] `workforce/templates/workforce/parts/delivery_task_detail.html` — 6 button(s) without `aria-label` (6 icon-only) <!-- id: aria-button:workforce/templates/workforce/parts/delivery_task_detail.html -->
- [ ] `workforce/templates/workforce/parts/lists/orders_list_view.html` — 6 button(s) without `aria-label` (6 icon-only) <!-- id: aria-button:workforce/templates/workforce/parts/lists/orders_list_view.html -->
- [ ] `fleet/templates/fleet/parts/task_detail_sheet.html` — 5 button(s) without `aria-label` (5 icon-only) <!-- id: aria-button:fleet/templates/fleet/parts/task_detail_sheet.html -->
- [ ] `orders/templates/orders/order_pending_list.html` — 5 button(s) without `aria-label` (4 icon-only, 1 `btn-close`) <!-- id: aria-button:orders/templates/orders/order_pending_list.html -->
- [ ] `orders/templates/orders/order_update.html` — 5 button(s) without `aria-label` (5 icon-only) <!-- id: aria-button:orders/templates/orders/order_update.html -->
- [ ] `workforce/templates/workforce/business_license_detail.html` — 5 button(s) without `aria-label` (5 icon-only) <!-- id: aria-button:workforce/templates/workforce/business_license_detail.html -->
- [ ] `workforce/templates/workforce/google_sheet_sources.html` — 5 button(s) without `aria-label` (3 icon-only, 2 `btn-close`) <!-- id: aria-button:workforce/templates/workforce/google_sheet_sources.html -->
- [ ] `workforce/templates/workforce/temp_orders_by_date.html` — 5 button(s) without `aria-label` (2 icon-only, 3 `btn-close`) <!-- id: aria-button:workforce/templates/workforce/temp_orders_by_date.html -->
- [ ] `workforce/templates/workforce/business_verification_list.html` — 4 button(s) without `aria-label` (4 icon-only) <!-- id: aria-button:workforce/templates/workforce/business_verification_list.html -->
- [ ] `workforce/templates/workforce/driver_detail.html` — 4 button(s) without `aria-label` (2 icon-only, 2 `btn-close`) <!-- id: aria-button:workforce/templates/workforce/driver_detail.html -->
- [ ] `workforce/templates/workforce/order_edit.html` — 4 button(s) without `aria-label` (4 icon-only) <!-- id: aria-button:workforce/templates/workforce/order_edit.html -->
- [ ] `workforce/templates/workforce/orders_api.html` — 4 button(s) without `aria-label` (2 icon-only, 2 `btn-close`) <!-- id: aria-button:workforce/templates/workforce/orders_api.html -->
- [ ] `workforce/templates/workforce/parts/components/_tasks_table_view.html` — 4 button(s) without `aria-label` (4 icon-only) <!-- id: aria-button:workforce/templates/workforce/parts/components/_tasks_table_view.html -->
- [ ] `workforce/templates/workforce/whatsapp_instances_list.html` — 4 button(s) without `aria-label` (2 icon-only, 2 `btn-close`) <!-- id: aria-button:workforce/templates/workforce/whatsapp_instances_list.html -->
- [ ] `fleet/templates/fleet/driver_tasks_pwa.html` — 3 button(s) without `aria-label` (3 icon-only) <!-- id: aria-button:fleet/templates/fleet/driver_tasks_pwa.html -->
- [ ] `fleet/templates/fleet/pickup_scanner_pwa.html` — 3 button(s) without `aria-label` (3 icon-only) <!-- id: aria-button:fleet/templates/fleet/pickup_scanner_pwa.html -->
- [ ] `orders/templates/orders/order_add.html` — 3 button(s) without `aria-label` (3 icon-only) <!-- id: aria-button:orders/templates/orders/order_add.html -->
- [ ] `orders/templates/orders/order_product_add.html` — 3 button(s) without `aria-label` (3 icon-only) <!-- id: aria-button:orders/templates/orders/order_product_add.html -->
- [ ] `orders/templates/orders/parts/order_row.html` — 3 button(s) without `aria-label` (3 icon-only) <!-- id: aria-button:orders/templates/orders/parts/order_row.html -->
- [ ] `product/templates/product/parts/product_card.html` — 3 button(s) without `aria-label` (3 icon-only) <!-- id: aria-button:product/templates/product/parts/product_card.html -->
- [ ] `workforce/templates/workforce/auto_flows_list.html` — 3 button(s) without `aria-label` (1 icon-only, 2 `btn-close`) <!-- id: aria-button:workforce/templates/workforce/auto_flows_list.html -->
- [ ] `workforce/templates/workforce/driver_verification_list.html` — 3 button(s) without `aria-label` (3 icon-only) <!-- id: aria-button:workforce/templates/workforce/driver_verification_list.html -->
- [ ] `workforce/templates/workforce/mapping_manager.html` — 3 button(s) without `aria-label` (3 icon-only) <!-- id: aria-button:workforce/templates/workforce/mapping_manager.html -->
- [ ] `workforce/templates/workforce/parts/components/_tasks_view_toggle.html` — 3 button(s) without `aria-label` (3 icon-only) <!-- id: aria-button:workforce/templates/workforce/parts/components/_tasks_view_toggle.html -->
- [ ] `workforce/templates/workforce/parts/lists/dl_list_followup.html` — 3 button(s) without `aria-label` (3 icon-only) <!-- id: aria-button:workforce/templates/workforce/parts/lists/dl_list_followup.html -->
- [ ] `workforce/templates/workforce/user_verification_list.html` — 3 button(s) without `aria-label` (3 icon-only) <!-- id: aria-button:workforce/templates/workforce/user_verification_list.html -->
- [ ] `fleet/templates/fleet/cod_collection_pwa.html` — 2 button(s) without `aria-label` (2 icon-only) <!-- id: aria-button:fleet/templates/fleet/cod_collection_pwa.html -->
- [ ] `fleet/templates/fleet/driver_earnings_pwa.html` — 2 button(s) without `aria-label` (2 icon-only) <!-- id: aria-button:fleet/templates/fleet/driver_earnings_pwa.html -->
- [ ] `fleet/templates/fleet/driver_notifications_pwa.html` — 2 button(s) without `aria-label` (2 icon-only) <!-- id: aria-button:fleet/templates/fleet/driver_notifications_pwa.html -->
- [ ] `fleet/templates/fleet/driver_pickups_pwa.html` — 2 button(s) without `aria-label` (2 icon-only) <!-- id: aria-button:fleet/templates/fleet/driver_pickups_pwa.html -->
- [ ] `fleet/templates/fleet/driver_profile_pwa.html` — 2 button(s) without `aria-label` (2 icon-only) <!-- id: aria-button:fleet/templates/fleet/driver_profile_pwa.html -->
- [ ] `fleet/templates/fleet/parts/document_all.html` — 2 button(s) without `aria-label` (2 icon-only) <!-- id: aria-button:fleet/templates/fleet/parts/document_all.html -->
- [ ] `fleet/templates/fleet/parts/pwa_header.html` — 2 button(s) without `aria-label` (2 icon-only) <!-- id: aria-button:fleet/templates/fleet/parts/pwa_header.html -->
- [ ] `fleet/templates/fleet/pwa_base.html` — 2 button(s) without `aria-label` (2 icon-only) <!-- id: aria-button:fleet/templates/fleet/pwa_base.html -->
- [ ] `fleet/templates/fleet/staff_cod_submission_edit.html` — 2 button(s) without `aria-label` (2 icon-only) <!-- id: aria-button:fleet/templates/fleet/staff_cod_submission_edit.html -->
- [ ] `fleet/templates/fleet/task_navigation_pwa.html` — 2 button(s) without `aria-label` (2 icon-only) <!-- id: aria-button:fleet/templates/fleet/task_navigation_pwa.html -->
- [ ] `orders/templates/orders/bulk_import.html` — 2 button(s) without `aria-label` (2 icon-only) <!-- id: aria-button:orders/templates/orders/bulk_import.html -->
- [ ] `orders/templates/orders/parts/order_list_review.html` — 2 button(s) without `aria-label` (2 icon-only) <!-- id: aria-button:orders/templates/orders/parts/order_list_review.html -->
- [ ] `orders/templates/orders/parts/order_list_table_view.html` — 2 button(s) without `aria-label` (2 icon-only) <!-- id: aria-button:orders/templates/orders/parts/order_list_table_view.html -->
- [ ] `product/templates/product/combo_form.html` — 2 button(s) without `aria-label` (2 icon-only) <!-- id: aria-button:product/templates/product/combo_form.html -->
- [ ] `templates/delivery/zone_map.html` — 2 button(s) without `aria-label` (2 icon-only) <!-- id: aria-button:templates/delivery/zone_map.html -->
- [ ] `workforce/templates/workforce/business_licenses_list.html` — 2 button(s) without `aria-label` (2 icon-only) <!-- id: aria-button:workforce/templates/workforce/business_licenses_list.html -->
- [ ] `workforce/templates/workforce/dispatch/batch_list.html` — 2 button(s) without `aria-label` (2 icon-only) <!-- id: aria-button:workforce/templates/workforce/dispatch/batch_list.html -->
- [ ] `workforce/templates/workforce/fleet_cod_in_hand.html` — 2 button(s) without `aria-label` (2 icon-only) <!-- id: aria-button:workforce/templates/workforce/fleet_cod_in_hand.html -->
- [ ] `workforce/templates/workforce/order_detail.html` — 2 button(s) without `aria-label` (1 icon-only, 1 `btn-close`) <!-- id: aria-button:workforce/templates/workforce/order_detail.html -->
- [ ] `workforce/templates/workforce/orders_add.html` — 2 button(s) without `aria-label` (2 icon-only) <!-- id: aria-button:workforce/templates/workforce/orders_add.html -->
- [ ] `workforce/templates/workforce/orders_bulk_import.html` — 2 button(s) without `aria-label` (2 icon-only) <!-- id: aria-button:workforce/templates/workforce/orders_bulk_import.html -->
- [ ] `workforce/templates/workforce/product_requests_list.html` — 2 button(s) without `aria-label` (2 icon-only) <!-- id: aria-button:workforce/templates/workforce/product_requests_list.html -->
- [ ] `workforce/templates/workforce/seller_transactions.html` — 2 button(s) without `aria-label` (1 icon-only, 1 `btn-close`) <!-- id: aria-button:workforce/templates/workforce/seller_transactions.html -->
- [ ] `workforce/templates/workforce/temp_orders_browse.html` — 2 button(s) without `aria-label` (1 icon-only, 1 `btn-close`) <!-- id: aria-button:workforce/templates/workforce/temp_orders_browse.html -->
- [ ] `workforce/templates/workforce/warehouses_list.html` — 2 button(s) without `aria-label` (2 icon-only) <!-- id: aria-button:workforce/templates/workforce/warehouses_list.html -->
- [ ] `workforce/templates/workforce/warehouses_list_enhanced.html` — 2 button(s) without `aria-label` (1 icon-only, 1 `btn-close`) <!-- id: aria-button:workforce/templates/workforce/warehouses_list_enhanced.html -->
- [ ] `workforce/templates/workforce/workforce_pickup_location_add.html` — 2 button(s) without `aria-label` (2 icon-only) <!-- id: aria-button:workforce/templates/workforce/workforce_pickup_location_add.html -->
- [ ] `business/templates/business/branded_tracking_settings.html` — 1 button(s) without `aria-label` (1 `btn-close`) <!-- id: aria-button:business/templates/business/branded_tracking_settings.html -->
- [ ] `business/templates/business/live_tracking_map.html` — 1 button(s) without `aria-label` (1 icon-only) <!-- id: aria-button:business/templates/business/live_tracking_map.html -->
- [ ] `business/templates/business/parts/business_transactions.html` — 1 button(s) without `aria-label` (1 icon-only) <!-- id: aria-button:business/templates/business/parts/business_transactions.html -->
- [ ] `business/templates/business/parts/dashboard_sidebar_business.html` — 1 button(s) without `aria-label` (1 icon-only) <!-- id: aria-button:business/templates/business/parts/dashboard_sidebar_business.html -->
- [ ] `business/templates/business/parts/driver_directory_add.html` — 1 button(s) without `aria-label` (1 `btn-close`) <!-- id: aria-button:business/templates/business/parts/driver_directory_add.html -->
- [ ] `core/templates/core/driverjobform.html` — 1 button(s) without `aria-label` (1 `btn-close`) <!-- id: aria-button:core/templates/core/driverjobform.html -->
- [ ] `core/templates/core/join_team.html` — 1 button(s) without `aria-label` (1 icon-only) <!-- id: aria-button:core/templates/core/join_team.html -->
- [ ] `core/templates/core/join_us.html` — 1 button(s) without `aria-label` (1 icon-only) <!-- id: aria-button:core/templates/core/join_us.html -->
- [ ] `core/templates/core/join_us_team.html` — 1 button(s) without `aria-label` (1 icon-only) <!-- id: aria-button:core/templates/core/join_us_team.html -->
- [ ] `core/templates/core/profile_add.html` — 1 button(s) without `aria-label` (1 `btn-close`) <!-- id: aria-button:core/templates/core/profile_add.html -->
- [ ] `core/templates/core/profile_role_update.html` — 1 button(s) without `aria-label` (1 `btn-close`) <!-- id: aria-button:core/templates/core/profile_role_update.html -->
- [ ] `delivery/templates/delivery/all_delivery_tasks.html` — 1 button(s) without `aria-label` (1 icon-only) <!-- id: aria-button:delivery/templates/delivery/all_delivery_tasks.html -->
- [ ] `delivery/templates/delivery/parts/tasks_all.html` — 1 button(s) without `aria-label` (1 icon-only) <!-- id: aria-button:delivery/templates/delivery/parts/tasks_all.html -->
- [ ] `fleet/templates/fleet/cod_submission_pwa.html` — 1 button(s) without `aria-label` (1 icon-only) <!-- id: aria-button:fleet/templates/fleet/cod_submission_pwa.html -->
- [ ] `fleet/templates/fleet/driver_help_pwa.html` — 1 button(s) without `aria-label` (1 icon-only) <!-- id: aria-button:fleet/templates/fleet/driver_help_pwa.html -->
- [ ] `fleet/templates/fleet/driver_settings_pwa.html` — 1 button(s) without `aria-label` (1 icon-only) <!-- id: aria-button:fleet/templates/fleet/driver_settings_pwa.html -->
- [ ] `fleet/templates/fleet/parts/cod_collection.html` — 1 button(s) without `aria-label` (1 icon-only) <!-- id: aria-button:fleet/templates/fleet/parts/cod_collection.html -->
- [ ] `fleet/templates/fleet/parts/driver_performance.html` — 1 button(s) without `aria-label` (1 icon-only) <!-- id: aria-button:fleet/templates/fleet/parts/driver_performance.html -->
- [ ] `fleet/templates/fleet/parts/fleet_finance_summary.html` — 1 button(s) without `aria-label` (1 icon-only) <!-- id: aria-button:fleet/templates/fleet/parts/fleet_finance_summary.html -->
- [ ] `fleet/templates/fleet/parts/transaction_detail_page.html` — 1 button(s) without `aria-label` (1 icon-only) <!-- id: aria-button:fleet/templates/fleet/parts/transaction_detail_page.html -->
- [ ] `fleet/templates/fleet/parts/transaction_history.html` — 1 button(s) without `aria-label` (1 icon-only) <!-- id: aria-button:fleet/templates/fleet/parts/transaction_history.html -->
- [ ] `fleet/templates/fleet/parts/vehicle_own.html` — 1 button(s) without `aria-label` (1 icon-only) <!-- id: aria-button:fleet/templates/fleet/parts/vehicle_own.html -->
- [ ] `fleet/templates/fleet/pickup_scanner.html` — 1 button(s) without `aria-label` (1 icon-only) <!-- id: aria-button:fleet/templates/fleet/pickup_scanner.html -->
- [ ] `fleet/templates/fleet/tasks_map_pwa.html` — 1 button(s) without `aria-label` (1 icon-only) <!-- id: aria-button:fleet/templates/fleet/tasks_map_pwa.html -->
- [ ] `orders/templates/orders/parts/_mobile_product_row.html` — 1 button(s) without `aria-label` (1 icon-only) <!-- id: aria-button:orders/templates/orders/parts/_mobile_product_row.html -->
- [ ] `orders/templates/orders/parts/order_comments_list.html` — 1 button(s) without `aria-label` (1 icon-only) <!-- id: aria-button:orders/templates/orders/parts/order_comments_list.html -->
- [ ] `orders/templates/orders/parts/order_list_view.html` — 1 button(s) without `aria-label` (1 icon-only) <!-- id: aria-button:orders/templates/orders/parts/order_list_view.html -->
- [ ] `product/templates/product/product_all_list_table.html` — 1 button(s) without `aria-label` (1 icon-only) <!-- id: aria-button:product/templates/product/product_all_list_table.html -->
- [ ] `templates/fleet_dashboard_base.html` — 1 button(s) without `aria-label` (1 icon-only) <!-- id: aria-button:templates/fleet_dashboard_base.html -->
- [ ] `warehouse/templates/warehouse/cycle_count_detail.html` — 1 button(s) without `aria-label` (1 icon-only) <!-- id: aria-button:warehouse/templates/warehouse/cycle_count_detail.html -->
- [ ] `warehouse/templates/warehouse/low_stock_alerts.html` — 1 button(s) without `aria-label` (1 icon-only) <!-- id: aria-button:warehouse/templates/warehouse/low_stock_alerts.html -->
- [ ] `warehouse/templates/warehouse/parts/qr_scanner.html` — 1 button(s) without `aria-label` (1 icon-only) <!-- id: aria-button:warehouse/templates/warehouse/parts/qr_scanner.html -->
- [ ] `workforce/templates/workforce/crm/lead_detail.html` — 1 button(s) without `aria-label` (1 icon-only) <!-- id: aria-button:workforce/templates/workforce/crm/lead_detail.html -->
- [ ] `workforce/templates/workforce/dispatch/dashboard.html` — 1 button(s) without `aria-label` (1 icon-only) <!-- id: aria-button:workforce/templates/workforce/dispatch/dashboard.html -->
- [ ] `workforce/templates/workforce/drivers_list.html` — 1 button(s) without `aria-label` (1 icon-only) <!-- id: aria-button:workforce/templates/workforce/drivers_list.html -->
- [ ] `workforce/templates/workforce/fleet_transactions.html` — 1 button(s) without `aria-label` (1 icon-only) <!-- id: aria-button:workforce/templates/workforce/fleet_transactions.html -->
- [ ] `workforce/templates/workforce/forms/pricing_inquiry_detail.html` — 1 button(s) without `aria-label` (1 icon-only) <!-- id: aria-button:workforce/templates/workforce/forms/pricing_inquiry_detail.html -->
- [ ] `workforce/templates/workforce/import_history.html` — 1 button(s) without `aria-label` (1 icon-only) <!-- id: aria-button:workforce/templates/workforce/import_history.html -->
- [ ] `workforce/templates/workforce/import_wizard.html` — 1 button(s) without `aria-label` (1 icon-only) <!-- id: aria-button:workforce/templates/workforce/import_wizard.html -->
- [ ] `workforce/templates/workforce/parts/components/_tasks_view_scripts.html` — 1 button(s) without `aria-label` (1 `btn-close`) <!-- id: aria-button:workforce/templates/workforce/parts/components/_tasks_view_scripts.html -->
- [ ] `workforce/templates/workforce/parts/delivery_task_edit.html` — 1 button(s) without `aria-label` (1 icon-only) <!-- id: aria-button:workforce/templates/workforce/parts/delivery_task_edit.html -->
- [ ] `workforce/templates/workforce/parts/temp_order_detail_modal.html` — 1 button(s) without `aria-label` (1 `btn-close`) <!-- id: aria-button:workforce/templates/workforce/parts/temp_order_detail_modal.html -->
- [ ] `workforce/templates/workforce/public_link_sources.html` — 1 button(s) without `aria-label` (1 icon-only) <!-- id: aria-button:workforce/templates/workforce/public_link_sources.html -->
- [ ] `workforce/templates/workforce/staff_pages.html` — 1 button(s) without `aria-label` (1 icon-only) <!-- id: aria-button:workforce/templates/workforce/staff_pages.html -->
- [ ] `workforce/templates/workforce/staff_roles.html` — 1 button(s) without `aria-label` (1 icon-only) <!-- id: aria-button:workforce/templates/workforce/staff_roles.html -->
- [ ] `workforce/templates/workforce/tasks_live_map.html` — 1 button(s) without `aria-label` (1 icon-only) <!-- id: aria-button:workforce/templates/workforce/tasks_live_map.html -->
- [ ] `workforce/templates/workforce/warehouses_list_backup.html` — 1 button(s) without `aria-label` (1 icon-only) <!-- id: aria-button:workforce/templates/workforce/warehouses_list_backup.html -->
- [ ] `workforce/templates/workforce/wf_orders_by_seller.html` — 1 button(s) without `aria-label` (1 icon-only) <!-- id: aria-button:workforce/templates/workforce/wf_orders_by_seller.html -->

### `<style>` blocks in templates

_CLAUDE.md forbids `<style>` tags in templates — CSS belongs in a linked file loaded from `{% block extra_css %}`._

**8 open / 8 findings** · 8 occurrences outstanding

- [ ] `fleet/templates/fleet/pwa_base.html` — 1 `<style>` block(s) <!-- id: style-tag:fleet/templates/fleet/pwa_base.html -->
- [ ] `orders/templates/orders/customer_tracking.html` — 1 `<style>` block(s) <!-- id: style-tag:orders/templates/orders/customer_tracking.html -->
- [ ] `product/templates/product/test_images.html` — 1 `<style>` block(s) <!-- id: style-tag:product/templates/product/test_images.html -->
- [ ] `templates/includes/head-dashboard.html` — 1 `<style>` block(s) <!-- id: style-tag:templates/includes/head-dashboard.html -->
- [ ] `templates/includes/head.html` — 1 `<style>` block(s) <!-- id: style-tag:templates/includes/head.html -->
- [ ] `webpages/templates/webpages/inquiry_preview.html` — 1 `<style>` block(s) <!-- id: style-tag:webpages/templates/webpages/inquiry_preview.html -->
- [ ] `workforce/templates/workforce/receipt_template_preview.html` — 1 `<style>` block(s) <!-- id: style-tag:workforce/templates/workforce/receipt_template_preview.html -->
- [ ] `workforce/templates/workforce/settlement_receipt.html` — 1 `<style>` block(s) <!-- id: style-tag:workforce/templates/workforce/settlement_receipt.html -->

<details><summary>Sample line numbers (regenerated each run — do not cite these elsewhere)</summary>

- `fleet/templates/fleet/pwa_base.html` → lines 37
- `orders/templates/orders/customer_tracking.html` → lines 15
- `product/templates/product/test_images.html` → lines 7
- `templates/includes/head-dashboard.html` → lines 25
- `templates/includes/head.html` → lines 90
- `webpages/templates/webpages/inquiry_preview.html` → lines 8
- `workforce/templates/workforce/receipt_template_preview.html` → lines 8
- `workforce/templates/workforce/settlement_receipt.html` → lines 8

</details>

### Large stylesheets with almost no breakpoints

_A 400+ line stylesheet with 0-2 media queries is very likely desktop-only._

**26 open / 26 findings** · 39 occurrences outstanding

- [ ] `workforce/static/workforce/css/live-map.css` — 456 lines but only 0 `@media` block(s) <!-- id: media-query:workforce/static/workforce/css/live-map.css -->
- [ ] `ai_agent/static/ai_agent/css/ai-tools.css` — 901 lines but only 1 `@media` block(s) <!-- id: media-query:ai_agent/static/ai_agent/css/ai-tools.css -->
- [ ] `business/static/business/css/business-settings-pro.css` — 460 lines but only 1 `@media` block(s) <!-- id: media-query:business/static/business/css/business-settings-pro.css -->
- [ ] `business/static/business/css/business-waybill.css` — 429 lines but only 1 `@media` block(s) <!-- id: media-query:business/static/business/css/business-waybill.css -->
- [ ] `fleet/static/fleet/css/fleet-pickup.css` — 438 lines but only 1 `@media` block(s) <!-- id: media-query:fleet/static/fleet/css/fleet-pickup.css -->
- [ ] `orders/static/orders/css/bulk-entry.css` — 509 lines but only 1 `@media` block(s) <!-- id: media-query:orders/static/orders/css/bulk-entry.css -->
- [ ] `webpages/static/webpages/css/brandkit-components.css` — 935 lines but only 1 `@media` block(s) <!-- id: media-query:webpages/static/webpages/css/brandkit-components.css -->
- [ ] `webpages/static/webpages/css/seo-landing.css` — 850 lines but only 1 `@media` block(s) <!-- id: media-query:webpages/static/webpages/css/seo-landing.css -->
- [ ] `workforce/static/workforce/css/mapping_manager.css` — 884 lines but only 1 `@media` block(s) <!-- id: media-query:workforce/static/workforce/css/mapping_manager.css -->
- [ ] `workforce/static/workforce/css/verification.css` — 654 lines but only 1 `@media` block(s) <!-- id: media-query:workforce/static/workforce/css/verification.css -->
- [ ] `workforce/static/workforce/css/workforce-warehouse-compact.css` — 481 lines but only 1 `@media` block(s) <!-- id: media-query:workforce/static/workforce/css/workforce-warehouse-compact.css -->
- [ ] `workforce/static/workforce/css/workforce_finance_dashboard.css` — 455 lines but only 1 `@media` block(s) <!-- id: media-query:workforce/static/workforce/css/workforce_finance_dashboard.css -->
- [ ] `business/static/business/css/business-all.css` — 420 lines but only 2 `@media` block(s) <!-- id: media-query:business/static/business/css/business-all.css -->
- [ ] `business/static/business/css/business-dashboard-pro.css` — 669 lines but only 2 `@media` block(s) <!-- id: media-query:business/static/business/css/business-dashboard-pro.css -->
- [ ] `delivery/static/delivery/css/delivery-tasks-mobile.css` — 803 lines but only 2 `@media` block(s) <!-- id: media-query:delivery/static/delivery/css/delivery-tasks-mobile.css -->
- [ ] `orders/static/orders/css/order_api_get.css` — 568 lines but only 2 `@media` block(s) <!-- id: media-query:orders/static/orders/css/order_api_get.css -->
- [ ] `templates/static/ezzy_api/docs-premium.css` — 892 lines but only 2 `@media` block(s) <!-- id: media-query:templates/static/ezzy_api/docs-premium.css -->
- [ ] `templates/static/ezzy_api/docs.css` — 858 lines but only 2 `@media` block(s) <!-- id: media-query:templates/static/ezzy_api/docs.css -->
- [ ] `webpages/static/webpages/css/base.css` — 622 lines but only 2 `@media` block(s) <!-- id: media-query:webpages/static/webpages/css/base.css -->
- [ ] `webpages/static/webpages/css/p2p-pricing.css` — 917 lines but only 2 `@media` block(s) <!-- id: media-query:webpages/static/webpages/css/p2p-pricing.css -->
- [ ] `workforce/static/workforce/css/business_licenses_list.css` — 468 lines but only 2 `@media` block(s) <!-- id: media-query:workforce/static/workforce/css/business_licenses_list.css -->
- [ ] `workforce/static/workforce/css/earnings_verification.css` — 652 lines but only 2 `@media` block(s) <!-- id: media-query:workforce/static/workforce/css/earnings_verification.css -->
- [ ] `workforce/static/workforce/css/fleet_driver_tasks.css` — 594 lines but only 2 `@media` block(s) <!-- id: media-query:workforce/static/workforce/css/fleet_driver_tasks.css -->
- [ ] `workforce/static/workforce/css/pricing_inquiries_list.css` — 458 lines but only 2 `@media` block(s) <!-- id: media-query:workforce/static/workforce/css/pricing_inquiries_list.css -->
- [ ] `workforce/static/workforce/css/store-document-detail.css` — 537 lines but only 2 `@media` block(s) <!-- id: media-query:workforce/static/workforce/css/store-document-detail.css -->
- [ ] `workforce/static/workforce/css/verify_queue.css` — 1201 lines but only 2 `@media` block(s) <!-- id: media-query:workforce/static/workforce/css/verify_queue.css -->

### `print()` in shipped application code

_Writes to the Gunicorn stdout with no level or context. Use `logger.debug()`._

**0 open / 1 findings**

- [~] `ezzydelivery/celery.py` — 1 `print()` call(s) <!-- id: print:ezzydelivery/celery.py --> — NOTE: Stock Celery `debug_task` scaffold — `print` is what the Celery docs generate and the task exists only to prove the worker is alive. Not application logging.

<details><summary>Sample line numbers (regenerated each run — do not cite these elsewhere)</summary>

- `ezzydelivery/celery.py` → lines 110

</details>

---

## Closed categories

_Zero findings. The note records **why**, so these do not get re-opened by a future audit._

- **`<img>` missing `alt`** — Every `<img>` in the project carries an `alt`. The last one — a decorative brand logo in the warehouse inventory modal — was given `alt=""` on 2026-08-02.
- **Float-based layout** — No float-based layout left in project CSS. The bulk went with the BEM restructure and the deletion of `volte.css` (a 26-instance vendor bundle); the last two — `zone-group-card` in fleet-mobile.css and the FAQ `summary::after` marker in llm-knowledge-panel.css — were converted to flex on 2026-08-02.

---

<!-- QA-SCAN:MANUAL-START -->
## Workflow reference (hand-written — preserved across scans)

_Carried over from the January 2026 audit. Everything between the MANUAL markers is never
overwritten by `qa_scan.py`, so put durable notes here rather than in the findings list._

### Business onboarding
```
User Registration → Create Business Profile → Add Pickup Locations → Configure API → Add Team → Ready
```

### Order creation
```
Create Order (AddOrderForm) → Add Products → Status "to_review" → Workforce Verify → Status "verified" → Delivery Task Created
```

### Team management
```
Add Team Member → Assign Role → Set Permissions → Activate/Suspend → Revoke/Grant Permissions
```

### Audit history

- **2026-01-13 → 01-14** — first comprehensive audit. Landed the `print()`→`logger` sweep, the
  onclick→event-delegation refactor across fleet/DMS/document templates, and a large inline-style
  extraction. Then the file was abandoned.
- **2026-01-14 → 2026-08-02** — no updates, while ~336 commits landed. The BEM restructure rewrote
  most of the referenced files, so every line number in the old list went stale and much of the
  remaining work was silently completed by that other track. This is the rot the generated format
  now prevents.
- **2026-08-02** — re-audited from scratch and replaced with generated output.
<!-- QA-SCAN:MANUAL-END -->

---

## How to work this list

1. **Triage before fixing.** Several categories are raw counts a scanner cannot judge —
   `undecorated-view` especially. Mark the false positives `[~]` with a note first, so the
   next run reports a real number instead of a scary one.
2. **Use the existing skills.** `/css-fix` (`.claude/skills/css-fix.md`) already encodes the
   Bootstrap-first BEM pattern for the inline-style and `!important` work. `.claude/skills/brandkit.md`
   is the token table for the hardcoded-colour work.
3. **Re-run the scanner after a batch** so the counts move and the progress is visible.
