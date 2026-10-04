// Purpose: Bulk stage move on the CRM leads list — tick rows, pick a column, apply.
// Used by: workforce/templates/workforce/crm/leads_list.html (the [data-bulk-stage] bar).
// Notes: Reads the SAME row ticks as export-columns.js ([data-export-row]), so load after it.
//        Never acts on "all matching" — that is an export-scope idea; a bulk write stays
//        on what the desk can actually see it ticked. Posts JSON to crm_leads_bulk_stage.

(function () {
    'use strict';

    function bar() { return document.querySelector('[data-bulk-stage]'); }

    function tickedIds() {
        return Array.prototype.slice
            .call(document.querySelectorAll('[data-export-row]'))
            .filter(function (b) { return b.checked; })
            .map(function (b) { return b.value; });
    }

    function csrf() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    }

    // The bar lives inside #main-content, so an HTMX swap replaces it — the readout
    // is rebuilt from the DOM each time rather than held in a variable.
    function sync() {
        var el = bar();
        if (!el) return;
        var n = tickedIds().length;
        el.hidden = n === 0;
        var count = el.querySelector('[data-bulk-count]');
        if (count) count.textContent = n;
        var apply = el.querySelector('[data-bulk-apply]');
        var select = el.querySelector('[data-bulk-select]');
        if (apply) apply.disabled = !(n > 0 && select && select.value);
    }

    // A toast, not an alert: it has to survive the table refresh that follows, so it
    // is appended to the body rather than to the bar being swapped out.
    function toast(message, isError) {
        var el = document.createElement('div');
        el.className = 'crm__toast' + (isError ? ' crm__toast--err' : '');
        el.setAttribute('role', 'status');
        el.textContent = message;
        document.body.appendChild(el);
        requestAnimationFrame(function () { el.classList.add('is-on'); });
        setTimeout(function () {
            el.classList.remove('is-on');
            setTimeout(function () { el.remove(); }, 300);
        }, isError ? 9000 : 5000);
    }

    // Re-fetch the list with the filters and sort that are already in the URL, so the
    // moved rows show their new column (and drop out if a stage filter excludes them).
    function refreshList() {
        var target = document.getElementById('main-content');
        if (window.htmx && target) {
            window.htmx.ajax('GET', window.location.pathname + window.location.search, {
                target: '#main-content', select: '#main-content', swap: 'outerHTML'
            });
        } else {
            window.location.reload();
        }
    }

    function clearTicks() {
        // Routed through the master box so export-columns.js updates its own readout
        // and its all-matching toggle with us — two scripts, one selection.
        var master = document.querySelector('[data-export-row-all]');
        if (master) {
            master.checked = false;
            master.dispatchEvent(new Event('change', { bubbles: true }));
            return;
        }
        var boxes = document.querySelectorAll('[data-export-row]');
        boxes.forEach(function (b) { b.checked = false; });
        if (boxes.length) boxes[0].dispatchEvent(new Event('change', { bubbles: true }));
    }

    function apply() {
        var el = bar();
        if (!el) return;
        var select = el.querySelector('[data-bulk-select]');
        var stage = select ? select.value : '';
        var ids = tickedIds();
        if (!stage || !ids.length) return;

        var cap = parseInt(el.getAttribute('data-bulk-max'), 10) || 0;
        if (cap && ids.length > cap) {
            toast('That is ' + ids.length + ' leads — a bulk move carries at most ' + cap +
                  '. Untick some rows, or narrow the filter and do it in batches.', true);
            return;
        }

        var option = select.options[select.selectedIndex];
        var label = (option.textContent || stage).trim();
        var confirmText = option.getAttribute('data-confirm') || '';
        var needsReason = option.getAttribute('data-needs-reason') === '1';
        var writesBack = option.getAttribute('data-write-back') === '1';
        var many = ids.length + (ids.length === 1 ? ' lead' : ' leads');

        // A write-back column rewrites each matched driver's real application status
        // and WhatsApps them, so the count goes in the prompt: "20 leads" reads very
        // differently once it says 20 people are about to be messaged.
        var head = 'Move ' + many + ' to "' + label + '"?';
        if (writesBack) {
            head += '\n\nThis will ' + (confirmText || 'change each matched driver\'s status') +
                    ' and update their real application status — every applicant with a ' +
                    'driver record is notified.';
        }

        var reason = '';
        if (needsReason) {
            var answer = prompt(head + '\n\nReason (optional) — the same one is recorded for all of them:', '');
            if (answer === null) return;
            reason = answer;
        } else if (!confirm(head)) {
            return;
        }

        var button = el.querySelector('[data-bulk-apply]');
        if (button) button.disabled = true;

        fetch(el.getAttribute('data-bulk-url'), {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
            body: JSON.stringify({
                ids: ids,
                stage: stage,
                category: el.getAttribute('data-bulk-category') || '',
                rejection_reason: reason
            })
        }).then(function (resp) {
            // A session that timed out answers with the login page, not JSON — reading
            // it as JSON would throw "Unexpected token '<'" and say nothing useful.
            var type = resp.headers.get('content-type') || '';
            if (type.indexOf('application/json') === -1) {
                toast('Your session has expired — the page will reload so you can sign in again.', true);
                setTimeout(function () { window.location.reload(); }, 1500);
                return null;
            }
            return resp.json();
        }).then(function (data) {
            if (!data) return;
            if (!data.success) {
                toast(data.error || 'The move failed.', true);
                sync();
                return;
            }
            var message = data.message;
            if (data.errors && data.errors.length) message += ' ' + data.errors.join(' ');
            if (data.warnings && data.warnings.length) {
                message += ' ' + data.warnings.join(' ');
                if (data.warning_count > data.warnings.length) {
                    message += ' (+' + (data.warning_count - data.warnings.length) + ' more)';
                }
            }
            toast(message, !!(data.errors && data.errors.length));
            clearTicks();
            refreshList();
        }).catch(function (err) {
            toast('The move could not be sent: ' + err.message, true);
            sync();
        });
    }

    // One delegated set of listeners for the life of the page — the bar and the table
    // are both replaced on every HTMX filter swap, and this script re-runs with them.
    if (!document.body.hasAttribute('data-bulk-stage-bound')) {
        document.body.setAttribute('data-bulk-stage-bound', '1');

        // Deferred by a tick: the master-box handler in export-columns.js ticks the
        // rows, and reading them in the same turn would count the state before it.
        document.addEventListener('change', function (e) {
            var t = e.target;
            if (!t.hasAttribute) return;
            if (t.hasAttribute('data-export-row') || t.hasAttribute('data-export-row-all')
                || t.hasAttribute('data-bulk-select')) {
                setTimeout(sync, 0);
            }
        });
        document.addEventListener('click', function (e) {
            if (!e.target.closest) return;
            if (e.target.closest('[data-bulk-apply]')) { apply(); return; }
            if (e.target.closest('[data-bulk-clear]')) { clearTicks(); setTimeout(sync, 0); }
        });
        // A swap wipes the ticks along with the rows, so the bar folds away with them.
        document.body.addEventListener('htmx:afterSwap', function () { setTimeout(sync, 0); });
    }

    sync();
})();
