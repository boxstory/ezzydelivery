/*
 * Purpose: Bulk edit grid for order location + delivery fee — dirty tracking, fill-ticked-rows, save.
 * Used by: workforce/templates/workforce/orders_bulk_edit.html (/workforce/orders/bulk-edit/)
 * Notes: Sends only changed fields per row, in chunks of data-max-rows. Everything is scoped to the
 *        ObeBulkEdit object — no page-level function names, so dashboard-utils.js cannot shadow them.
 */
(function () {
  'use strict';

  var ObeBulkEdit = {
    page: null,
    originals: new Map(),   // order id -> {field: value} as last stored
    pickups: {},

    init: function () {
      this.page = document.getElementById('workforce_obe_page');
      if (!this.page) return;
      var data = document.getElementById('workforce_obe_data_pickups');
      this.pickups = data ? JSON.parse(data.textContent) : {};

      var self = this;
      this.rows().forEach(function (row) {
        self.originals.set(row.dataset.orderId, self.readRow(row));
      });

      var tbody = this.page.querySelector('#workforce_obe_table_orders tbody');
      tbody.addEventListener('input', function (e) {
        if (e.target.matches('[data-field]')) self.markRow(e.target.closest('.obe__row'));
      });
      tbody.addEventListener('change', function (e) {
        if (e.target.matches('[data-field]')) self.markRow(e.target.closest('.obe__row'));
        if (e.target.matches('.obe__tick')) self.onTick();
      });
      document.getElementById('workforce_obe_check_all').addEventListener('change', function (e) {
        self.rows().forEach(function (row) { row.querySelector('.obe__tick').checked = e.target.checked; });
        self.onTick();
      });
      document.getElementById('workforce_obe_btn_fill').addEventListener('click', function () { self.fillTicked(); });
      document.getElementById('workforce_obe_btn_ratecard').addEventListener('click', function () { self.feeToRateCard(); });
      document.getElementById('workforce_obe_btn_discard').addEventListener('click', function () { self.discard(); });
      document.getElementById('workforce_obe_btn_save').addEventListener('click', function () { self.save(); });

      window.addEventListener('beforeunload', function (e) {
        if (self.dirtyRows().length) { e.preventDefault(); e.returnValue = ''; }
      });
    },

    rows: function () {
      return Array.prototype.slice.call(this.page.querySelectorAll('.obe__row'));
    },

    tickedRows: function () {
      return this.rows().filter(function (row) { return row.querySelector('.obe__tick').checked; });
    },

    dirtyRows: function () {
      return this.rows().filter(function (row) { return row.classList.contains('obe__row--dirty'); });
    },

    readRow: function (row) {
      var values = {};
      row.querySelectorAll('[data-field]').forEach(function (el) {
        values[el.dataset.field] = el.value.trim();
      });
      return values;
    },

    changedFields: function (row) {
      var original = this.originals.get(row.dataset.orderId) || {};
      var current = this.readRow(row);
      var changed = {};
      Object.keys(current).forEach(function (field) {
        if (current[field] !== (original[field] || '')) changed[field] = current[field];
      });
      // A pin is one fact: send both halves together or the server sees half a move.
      if ('latitude' in changed || 'longitude' in changed) {
        changed.latitude = current.latitude;
        changed.longitude = current.longitude;
      }
      return changed;
    },

    markRow: function (row) {
      var original = this.originals.get(row.dataset.orderId) || {};
      row.querySelectorAll('[data-field]').forEach(function (el) {
        el.classList.toggle('obe__in--changed', el.value.trim() !== (original[el.dataset.field] || ''));
      });
      var dirty = Object.keys(this.changedFields(row)).length > 0;
      row.classList.toggle('obe__row--dirty', dirty);
      if (dirty) this.setResult(row, '', '');
      this.refreshSaveBar();
    },

    refreshSaveBar: function () {
      var n = this.dirtyRows().length;
      document.getElementById('workforce_obe_bar_save').hidden = n === 0;
      document.getElementById('workforce_obe_text_dirty').textContent =
        n + (n === 1 ? ' row changed' : ' rows changed');
    },

    onTick: function () {
      var ticked = this.tickedRows();
      var all = this.rows();
      var master = document.getElementById('workforce_obe_check_all');
      master.checked = ticked.length > 0 && ticked.length === all.length;
      master.indeterminate = ticked.length > 0 && ticked.length < all.length;
      document.getElementById('workforce_obe_text_ticked').textContent = ticked.length;
      document.getElementById('workforce_obe_btn_fill').disabled = ticked.length === 0;
      document.getElementById('workforce_obe_btn_ratecard').disabled = ticked.length === 0;

      // A pickup location belongs to one client, so it can only be filled
      // across rows that all share that client.
      var select = document.getElementById('workforce_obe_fill_pickup');
      var businesses = new Set(ticked.map(function (row) { return row.dataset.businessId; }));
      var keep = select.value;
      select.innerHTML = '';
      var blank = document.createElement('option');
      blank.value = '';
      if (businesses.size === 1) {
        var options = this.pickups[Array.from(businesses)[0]] || [];
        blank.textContent = options.length ? '— leave as is —' : '— no active locations —';
        select.appendChild(blank);
        options.forEach(function (loc) {
          var opt = document.createElement('option');
          opt.value = String(loc.id);
          opt.textContent = loc.label;
          select.appendChild(opt);
        });
        select.value = keep;
        if (select.value !== keep) select.value = '';
        select.disabled = options.length === 0;
      } else {
        blank.textContent = '— one client only —';
        select.appendChild(blank);
        select.disabled = true;
      }
    },

    setField: function (row, field, value) {
      var el = row.querySelector('[data-field="' + field + '"]');
      if (!el || el.disabled) return;
      if (el.tagName === 'SELECT' && !el.querySelector('option[value="' + value + '"]')) return;
      el.value = value;
    },

    fillTicked: function () {
      var fills = {
        dl_amount: document.getElementById('workforce_obe_fill_fee').value.trim(),
        dl_zone: document.getElementById('workforce_obe_fill_zone').value.trim(),
        dl_street: document.getElementById('workforce_obe_fill_street').value.trim(),
        dl_building: document.getElementById('workforce_obe_fill_building').value.trim(),
        pickup_location: document.getElementById('workforce_obe_fill_pickup').value
      };
      var self = this;
      this.tickedRows().forEach(function (row) {
        Object.keys(fills).forEach(function (field) {
          if (fills[field] !== '') self.setField(row, field, fills[field]);
        });
        self.markRow(row);
      });
    },

    feeToRateCard: function () {
      var self = this;
      this.tickedRows().forEach(function (row) {
        self.setField(row, 'dl_amount', '0');
        self.markRow(row);
      });
    },

    discard: function () {
      var self = this;
      this.dirtyRows().forEach(function (row) {
        var original = self.originals.get(row.dataset.orderId) || {};
        row.querySelectorAll('[data-field]').forEach(function (el) {
          el.value = original[el.dataset.field] || '';
        });
        self.markRow(row);
      });
    },

    setResult: function (row, kind, message) {
      var cell = row.querySelector('[data-cell="result"]');
      cell.textContent = '';
      if (!kind) return;
      var span = document.createElement('span');
      span.className = 'obe__status obe__status--' + kind;
      span.textContent = message;
      cell.appendChild(span);
    },

    sourceLabel: function (source, fee) {
      if (source === 'rate_card') return 'Rate card';
      if (source === 'manual') return 'Set by staff';
      return parseFloat(fee) > 0 ? 'Kept (imported)' : 'Not set';
    },

    // Redraw a row from what the server stored — the rate card may have
    // re-priced it, and QNAS may have moved the pin.
    applyValues: function (row, values) {
      var pin = function (v) { return v === '' || v === null ? '' : Number(v).toFixed(6); };
      var stored = {
        dl_zone: values.dl_zone === null ? '' : String(values.dl_zone),
        dl_street: values.dl_street === null ? '' : String(values.dl_street),
        dl_building: values.dl_building === null ? '' : String(values.dl_building),
        latitude: pin(values.latitude),
        longitude: pin(values.longitude),
        pickup_location: values.pickup_location === null ? '' : String(values.pickup_location),
        dl_amount: values.dl_amount
      };
      var original = {};
      row.querySelectorAll('[data-field]').forEach(function (el) {
        var field = el.dataset.field;
        if (field in stored) el.value = stored[field];
        original[field] = el.value.trim();
      });
      this.originals.set(row.dataset.orderId, original);

      row.querySelector('[data-cell="source"]').textContent = this.sourceLabel(values.dl_amount_source, values.dl_amount);
      row.querySelector('[data-cell="distance"]').textContent =
        values.route_distance_km ? values.route_distance_km + ' km' : '—';
      row.querySelector('[data-cell="area"]').textContent = values.delivery_area_name || '';
      var acc = row.querySelector('[data-cell="accuracy"]');
      if (acc) acc.textContent = values.coords_accuracy_display || '';
    },

    csrfToken: function () {
      var meta = document.querySelector('meta[name="csrf-token"]');
      if (meta && meta.content) return meta.content;
      var input = document.querySelector('[name=csrfmiddlewaretoken]');
      return input ? input.value : '';
    },

    save: async function () {
      var btn = document.getElementById('workforce_obe_btn_save');
      var dirty = this.dirtyRows();
      if (!dirty.length) return;
      var max = parseInt(this.page.dataset.maxRows, 10) || 100;
      var byId = new Map(dirty.map(function (row) { return [row.dataset.orderId, row]; }));
      var self = this;
      var totals = { saved: 0, unchanged: 0, error: 0, deferred: 0 };

      btn.disabled = true;
      btn.classList.add('obe__btn-save--busy');
      dirty.forEach(function (row) { self.setResult(row, 'idle', 'Saving…'); });

      try {
        for (var i = 0; i < dirty.length; i += max) {
          var chunk = dirty.slice(i, i + max).map(function (row) {
            var payload = self.changedFields(row);
            payload.id = parseInt(row.dataset.orderId, 10);
            return payload;
          });
          var resp = await fetch(this.page.dataset.saveUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': this.csrfToken() },
            body: JSON.stringify({ rows: chunk })
          });
          var data;
          try { data = await resp.json(); } catch (err) { data = null; }
          if (!resp.ok || !data || !data.success) {
            var msg = (data && data.error) || ('Save failed (HTTP ' + resp.status + ')');
            dirty.slice(i, i + max).forEach(function (row) { self.setResult(row, 'err', msg); });
            totals.error += chunk.length;
            continue;
          }
          data.rows.forEach(function (result) {
            var row = byId.get(String(result.id));
            if (!row) return;
            totals[result.status] = (totals[result.status] || 0) + 1;
            if (result.values && (result.status === 'saved' || result.status === 'unchanged')) {
              self.applyValues(row, result.values);
              self.markRow(row);
            }
            var kind = { saved: result.warning ? 'warn' : 'ok', unchanged: 'idle', deferred: 'warn', error: 'err' }[result.status] || 'err';
            self.setResult(row, kind, result.message);
          });
        }
      } catch (err) {
        dirty.forEach(function (row) {
          if (row.classList.contains('obe__row--dirty')) self.setResult(row, 'err', 'Network error — not saved');
        });
      } finally {
        btn.disabled = false;
        btn.classList.remove('obe__btn-save--busy');
        this.refreshSaveBar();
      }

      var summary = totals.saved + ' saved';
      if (totals.error) summary += ', ' + totals.error + ' with errors';
      if (totals.deferred) summary += ', ' + totals.deferred + ' still to save';
      if (window.showToast) window.showToast(summary, totals.error ? 'warning' : 'success');
    }
  };

  document.addEventListener('DOMContentLoaded', function () { ObeBulkEdit.init(); });
})();
