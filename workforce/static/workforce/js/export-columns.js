// Purpose: Drive the reusable "choose columns" CSV export modal (_export_columns_modal.html)
//          and the optional per-row selection checkboxes on the list behind it.
// Used by: staff list pages that include the modal + an [data-export-open] trigger button.
// Notes: Remembers the column selection per page in localStorage (keyed by data-export-storage).
//        Row selection is opt-in: render [data-export-row] boxes (value = row id) and,
//        optionally, a [data-export-row-all] master box and a [data-export-count] readout.

(function () {
    var modalEl = document.getElementById('wfExportModal');
    if (!modalEl) return;
    var content = modalEl.querySelector('.wfx');
    var storageKey = content.getAttribute('data-export-storage') || 'wf_export_cols';
    var exportUrl = content.getAttribute('data-export-url') || '';

    function boxes() {
        return Array.prototype.slice.call(modalEl.querySelectorAll('.wfx__col input[type=checkbox]'));
    }

    // --- Row selection -------------------------------------------------------
    // Queried live rather than cached: HTMX re-renders the table on every filter,
    // so any node captured up front would be a detached one after the first swap.
    function rowBoxes() {
        return Array.prototype.slice.call(document.querySelectorAll('[data-export-row]'));
    }
    function checkedRowIds() {
        return rowBoxes().filter(function (b) { return b.checked; })
                         .map(function (b) { return b.value; });
    }

    // Ticking the header box only covers the rows on screen. allMatching is the
    // opt-in past that — "export the whole filter set, not just this page".
    // It is EXPORT-only on purpose: the orders list shares these checkboxes with
    // bulk status changes, which must never silently widen to 1,400 rows.
    var allMatching = false;

    function fmt(n) {
        try { return Number(n).toLocaleString(); } catch (e) { return String(n); }
    }

    // Keep the master box, the "N selected" readout and the all-matching toggle
    // in step with the rows.
    function syncRowUI() {
        var all = rowBoxes(), n = checkedRowIds().length;
        var master = document.querySelector('[data-export-row-all]');
        if (master) {
            master.checked = all.length > 0 && n === all.length;
            master.indeterminate = n > 0 && n < all.length;
        }
        var count = document.querySelector('[data-export-count]');
        if (count) {
            count.textContent = n + ' selected';
            count.hidden = n === 0;
        }

        var bar = document.querySelector('[data-export-selectall]');
        if (!bar) return;
        var total = parseInt(bar.getAttribute('data-export-total'), 10) || 0;
        var noun = bar.getAttribute('data-export-noun') || 'rows';
        var limit = parseInt(bar.getAttribute('data-export-limit'), 10) || 0;
        var pageFull = all.length > 0 && n === all.length;
        // Only worth offering when the page really is a subset of the filter set.
        bar.hidden = !(allMatching || (pageFull && total > all.length));

        var btn = bar.querySelector('[data-export-selectall-btn]');
        var on = bar.querySelector('[data-export-selectall-on]');
        var msg = bar.querySelector('[data-export-selectall-msg]');
        // The cap is the export's, not the page's — say so rather than quietly truncating.
        var capped = limit && total > limit ? ' (first ' + fmt(limit) + ')' : '';
        if (btn) {
            btn.hidden = allMatching;
            btn.textContent = 'Export all ' + fmt(total) + ' matching' + capped;
        }
        if (on) on.hidden = !allMatching;
        if (msg) msg.textContent = 'Exporting all ' + fmt(total) + ' ' + noun + capped;
    }

    // One delegated set of listeners for the life of the page — the table itself
    // is replaced on each HTMX swap, and this script re-runs with it.
    if (!document.body.hasAttribute('data-export-rows-bound')) {
        document.body.setAttribute('data-export-rows-bound', '1');
        document.addEventListener('change', function (e) {
            var t = e.target;
            if (t.hasAttribute && t.hasAttribute('data-export-row-all')) {
                rowBoxes().forEach(function (b) { b.checked = t.checked; });
                allMatching = false;      // re-opt-in each time, never sticky
                syncRowUI();
            } else if (t.hasAttribute && t.hasAttribute('data-export-row')) {
                allMatching = false;      // any manual tick means "just these"
                syncRowUI();
            }
        });
        document.addEventListener('click', function (e) {
            var t = e.target.closest && e.target.closest('[data-export-selectall-btn],[data-export-selectall-clear]');
            if (!t) return;
            allMatching = t.hasAttribute('data-export-selectall-btn');
            syncRowUI();
        });
        // A swap wipes the ticks and changes the filter, so both reset with it.
        document.body.addEventListener('htmx:afterSwap', function () {
            allMatching = false;
            syncRowUI();
        });
    }
    syncRowUI();

    // Restore a saved column selection (if any) whenever the modal opens, and
    // say up front how many rows the export will actually cover.
    function restore() {
        var saved;
        try { saved = JSON.parse(localStorage.getItem(storageKey) || 'null'); } catch (e) { saved = null; }
        var scope = modalEl.querySelector('[data-export-scope]');
        if (scope) {
            var n = checkedRowIds().length;
            scope.textContent = (allMatching || !n)
                ? 'Exporting every row matching the current filters.'
                : 'Exporting the ' + n + ' selected row' + (n === 1 ? '' : 's') + '.';
        }
        if (!saved || !saved.length) return;          // nothing saved -> keep defaults (all checked)
        boxes().forEach(function (b) { b.checked = saved.indexOf(b.value) !== -1; });
    }
    modalEl.addEventListener('show.bs.modal', restore);

    modalEl.addEventListener('click', function (e) {
        var t = e.target.closest('[data-export-all],[data-export-none],[data-export-run]');
        if (!t) return;
        if (t.hasAttribute('data-export-all')) {
            boxes().forEach(function (b) { b.checked = true; });
        } else if (t.hasAttribute('data-export-none')) {
            boxes().forEach(function (b) { b.checked = false; });
        } else if (t.hasAttribute('data-export-run')) {
            runExport();
        }
    });

    function runExport() {
        var selected = boxes().filter(function (b) { return b.checked; }).map(function (b) { return b.value; });
        if (!selected.length) {
            alert('Pick at least one column to export.');
            return;
        }
        // Persist for next time when "Remember" is on; otherwise forget.
        var remember = modalEl.querySelector('[data-export-remember]');
        try {
            if (remember && remember.checked) localStorage.setItem(storageKey, JSON.stringify(selected));
            else localStorage.removeItem(storageKey);
        } catch (e) { /* storage may be unavailable */ }

        // Build the target: keep any params already on exportUrl (e.g. export=csv),
        // merge the current page filters (minus paging), then set the chosen columns.
        //
        // Multi-select filters repeat a key (?status=pending&status=processing).
        // set() keeps only the last value, which silently narrowed every export to
        // one tick of each filter — so clear the key once, then append all values.
        var u = new URL(exportUrl, window.location.origin);
        var skip = ['page', 'per_page', 'export', 'columns', 'ids'];
        var cleared = {};
        new URLSearchParams(window.location.search).forEach(function (v, k) {
            if (skip.indexOf(k) !== -1) return;
            if (!cleared[k]) { u.searchParams.delete(k); cleared[k] = true; }
            u.searchParams.append(k, v);
        });
        u.searchParams.set('columns', selected.join(','));

        // Ticked rows win over the filter set; none ticked — or "all matching"
        // chosen — sends no ids at all, which the server reads as "whole filter".
        var ids = checkedRowIds();
        if (ids.length && !allMatching) u.searchParams.set('ids', ids.join(','));
        else u.searchParams.delete('ids');

        var bsModal = window.bootstrap && window.bootstrap.Modal.getInstance(modalEl);
        if (bsModal) bsModal.hide();
        window.location.href = u.pathname + '?' + u.searchParams.toString();
    }
})();
