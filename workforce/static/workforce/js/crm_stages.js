/* Purpose: Board-column configuration page — reorder columns with the ▲▼ nudges and confirm a column delete.
   Used by: workforce/templates/workforce/crm/stages_manage.html (reads window.CRMS_CONFIG for the CSRF token and reorder URL).
   Notes: Reorder posts the full row order and reloads so the numbering, first/last disabled states and the board all agree. */

(function () {
  'use strict';

  if (window.__crmsInit) return;
  window.__crmsInit = true;

  // The row's Edit button opens that column's drawer. Without this the href="#id"
  // alone only jumps to a <details> that stays shut in most browsers.
  document.addEventListener('click', function (e) {
    var link = e.target.closest && e.target.closest('[data-open-editor]');
    if (!link) return;
    e.preventDefault();
    var drawer = document.getElementById(link.getAttribute('data-open-editor'));
    if (!drawer) return;
    drawer.open = true;
    drawer.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    var first = drawer.querySelector('input[name="label"]');
    if (first) first.focus();
  });

  document.addEventListener('click', function (e) {
    var btn = e.target.closest && e.target.closest('.crms__move');
    if (!btn || btn.disabled) return;
    e.preventDefault();

    var row = btn.closest('.crms__row');
    var tbody = row && row.parentElement;
    if (!tbody) return;

    var rows = Array.prototype.slice.call(tbody.querySelectorAll('.crms__row'));
    var index = rows.indexOf(row);
    var target = btn.getAttribute('data-move') === 'up' ? index - 1 : index + 1;
    if (target < 0 || target >= rows.length) return;

    rows.splice(target, 0, rows.splice(index, 1)[0]);
    var order = rows.map(function (r) { return r.getAttribute('data-stage-id'); }).join(',');

    var cfg = window.CRMS_CONFIG || {};
    var fd = new FormData();
    fd.append('order', order);
    fd.append('board', cfg.board || '');
    fd.append('csrfmiddlewaretoken', cfg.csrfToken || '');

    btn.disabled = true;
    fetch(cfg.reorderUrl, { method: 'POST', body: fd })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.success) {
          window.location.reload();
        } else {
          btn.disabled = false;
          alert('Could not reorder columns: ' + (data.error || 'unknown error'));
        }
      })
      .catch(function (err) {
        btn.disabled = false;
        alert('Could not reorder columns: ' + err.message);
      });
  });

  // Deleting a column is destructive for its configuration — make staff confirm.
  document.addEventListener('submit', function (e) {
    var form = e.target;
    if (!form.classList || !form.classList.contains('crms__delete')) return;
    var label = form.getAttribute('data-confirm-label') || 'this column';
    if (!confirm('Delete the "' + label + '" column? Its rules and settings are gone for good.')) {
      e.preventDefault();
    }
  });
})();
