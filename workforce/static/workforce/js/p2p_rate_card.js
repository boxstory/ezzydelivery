// Purpose: Filter the P2P rate card's band editor, and fold the matrix's rare pairings away.
// Used by: workforce/templates/workforce/p2p_rate_card.html
// Notes: Hides rows with the `hidden` attribute only — never removes them and never disables a
//        field, because every row still has to POST or the formset loses the edits it did not show.

(function () {
  'use strict';

  // --- The effective price matrix: fold away the pairings nobody books ---------
  // Server-rendered hidden, so the folded rows never flash on load. The button only
  // reverses that; the rows are in the DOM either way, and Ctrl+F still finds them
  // once they are open.
  var rareBtn = document.getElementById('workforce_ratecard_btn_rare');
  if (rareBtn) {
    var rareRows = document.querySelectorAll('#workforce_ratecard_table_matrix tr[data-rare="1"]');
    rareBtn.addEventListener('click', function () {
      var opening = rareBtn.getAttribute('aria-expanded') !== 'true';
      Array.prototype.forEach.call(rareRows, function (row) { row.hidden = !opening; });
      rareBtn.setAttribute('aria-expanded', opening ? 'true' : 'false');
      rareBtn.textContent = (opening ? 'Hide ' : 'Show ') + rareRows.length + ' rare combinations';
    });
  }

  // --- Edit: swap the read-only chart for the rows behind it -------------------
  // Server-rendered state, so a failed save comes back with the editor already open on
  // its own errors and this only has to keep the button's label honest afterwards.
  var editBtn = document.getElementById('workforce_ratecard_btn_edit');
  var editor = document.getElementById('workforce_ratecard_editor');
  if (editBtn && editor) {
    editBtn.addEventListener('click', function () {
      var opening = editor.hidden;
      editor.hidden = !opening;
      editBtn.setAttribute('aria-expanded', opening ? 'true' : 'false');
      editBtn.textContent = opening ? 'Close editor' : 'Edit rate card';
      if (opening) { editor.scrollIntoView({ behavior: 'smooth', block: 'start' }); }
    });
  }

  // --- Add a row ---------------------------------------------------------------
  // Django's formset renders one spare row. Adding a row is cloning that spare, giving
  // the clone the next index, and telling the management form the count went up — which
  // is the whole contract: a POST with a TOTAL_FORMS that disagrees with the rows on the
  // page is rejected wholesale, taking every other edit with it.
  function addRow(btn) {
    var table = document.getElementById(btn.dataset.table);
    var prefix = btn.dataset.prefix;
    var total = document.getElementById('id_' + prefix + '-TOTAL_FORMS');
    if (!table || !total) { return; }

    var body = table.tBodies[0];
    var last = body.rows[body.rows.length - 1];
    var index = parseInt(total.value, 10);
    var clone = last.cloneNode(true);

    // Re-index every name/id/for on the clone, then empty it: a clone still carrying the
    // spare row's id would post as an edit to whatever row that id belongs to.
    var pattern = new RegExp(prefix + '-(\\d+)-', 'g');
    ['name', 'id', 'for'].forEach(function (attr) {
      clone.querySelectorAll('[' + attr + ']').forEach(function (el) {
        el.setAttribute(attr, el.getAttribute(attr).replace(pattern, prefix + '-' + index + '-'));
      });
    });
    clone.querySelectorAll('input, select').forEach(function (el) {
      if (el.type === 'checkbox') {
        // is_active is the one box a new row wants ticked; DELETE and needs_quote are not.
        el.checked = /-is_active$/.test(el.name);
      } else if (el.type === 'hidden' && /-id$/.test(el.name)) {
        el.value = '';
      } else if (el.tagName === 'SELECT') {
        el.selectedIndex = 0;
      } else if (!/-min_boxes$/.test(el.name) && !/-priority$/.test(el.name)) {
        el.value = '';
      }
    });
    clone.removeAttribute('hidden');
    clone.dataset.new = '1';
    body.appendChild(clone);
    total.value = index + 1;

    var first = clone.querySelector('input:not([type=hidden])');
    if (first) { first.focus(); }
  }

  Array.prototype.forEach.call(
    document.querySelectorAll('.p2prc__addrow-btn'),
    function (btn) { btn.addEventListener('click', function () { addRow(btn); }); }
  );

  // --- The band editor's filter bar -------------------------------------------
  var table = document.getElementById('workforce_ratecard_table_bands');
  if (!table) { return; }

  // Re-read on every pass rather than caching: rows added by the button after load must
  // be filtered (and counted) like the ones that came with the page.
  function bandRows() { return Array.prototype.slice.call(table.tBodies[0].rows); }
  var countEl = document.getElementById('workforce_ratecard_count_shown');
  var filters = {
    size: document.getElementById('workforce_ratecard_filter_size'),
    vehicle: document.getElementById('workforce_ratecard_filter_vehicle'),
    speed: document.getElementById('workforce_ratecard_filter_speed'),
    mode: document.getElementById('workforce_ratecard_filter_mode'),
  };
  var resetBtn = document.getElementById('workforce_ratecard_btn_filter_reset');

  function matches(row) {
    // The trailing blank "add a row" line has no data, and hiding it would take the
    // only way to add a band off the page.
    if (row.dataset.new === '1') { return true; }
    for (var key of ['size', 'vehicle', 'speed']) {
      var want = filters[key] && filters[key].value;
      // '__any' is the rate card's own blank cell, which is a real value to filter on;
      // an empty select value means the filter is off.
      if (want && (row.dataset[key] || '__any') !== want) { return false; }
    }
    var mode = filters.mode && filters.mode.value;
    if (mode === 'quote' && row.dataset.quote !== '1') { return false; }
    if (mode === 'priced' && row.dataset.quote === '1') { return false; }
    if (mode === 'inactive' && row.dataset.active !== '0') { return false; }
    return true;
  }

  function apply() {
    var rows = bandRows();
    var shown = 0;
    var addable = 0;
    rows.forEach(function (row) {
      var ok = matches(row);
      row.hidden = !ok;
      if (row.dataset.new === '1') { addable += 1; } else if (ok) { shown += 1; }
    });
    if (countEl) {
      countEl.textContent = 'Showing ' + shown + ' of ' + (rows.length - addable) + ' band(s)';
    }
  }

  Object.keys(filters).forEach(function (key) {
    if (filters[key]) { filters[key].addEventListener('change', apply); }
  });
  if (resetBtn) {
    resetBtn.addEventListener('click', function () {
      Object.keys(filters).forEach(function (key) {
        if (filters[key]) { filters[key].value = ''; }
      });
      apply();
    });
  }

  apply();
}());
