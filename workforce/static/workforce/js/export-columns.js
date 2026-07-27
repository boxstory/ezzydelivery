// Purpose: Drive the reusable "choose columns" CSV export modal (_export_columns_modal.html).
// Used by: staff list pages that include the modal + an [data-export-open] trigger button.
// Notes: Remembers the last selection per page in localStorage (keyed by data-export-storage).

(function () {
    var modalEl = document.getElementById('wfExportModal');
    if (!modalEl) return;
    var content = modalEl.querySelector('.wfx');
    var storageKey = content.getAttribute('data-export-storage') || 'wf_export_cols';
    var exportUrl = content.getAttribute('data-export-url') || '';

    function boxes() {
        return Array.prototype.slice.call(modalEl.querySelectorAll('.wfx__col input[type=checkbox]'));
    }

    // Restore a saved selection (if any) whenever the modal opens.
    function restore() {
        var saved;
        try { saved = JSON.parse(localStorage.getItem(storageKey) || 'null'); } catch (e) { saved = null; }
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
        var u = new URL(exportUrl, window.location.origin);
        new URLSearchParams(window.location.search).forEach(function (v, k) {
            if (['page', 'per_page', 'export', 'columns'].indexOf(k) === -1) u.searchParams.set(k, v);
        });
        u.searchParams.set('columns', selected.join(','));

        var bsModal = window.bootstrap && window.bootstrap.Modal.getInstance(modalEl);
        if (bsModal) bsModal.hide();
        window.location.href = u.pathname + '?' + u.searchParams.toString();
    }
})();
