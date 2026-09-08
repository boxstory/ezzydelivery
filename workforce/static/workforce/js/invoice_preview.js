/* Purpose: Paginate a bpi__ invoice sheet into A4 pages on screen, so staff can see the real page breaks and page count without opening the print dialog. */
/* Used by: workforce/templates/workforce/{client_charge_invoice,cod_business_payout_invoice,driver_payout_invoice}.html with invoice_preview.css */
/* Notes: Measures live DOM rather than estimating — the ledger is filled row by row until it
   overflows the page area, which is how the print engine breaks it too. The source .bpi__sheet is
   never mutated; it stays in the DOM and remains the only thing that prints. */
(function () {
  'use strict';

  var BUILT = false;

  function pxOf(root, varName) {
    // Custom props are authored in mm; resolve to px by measuring a probe.
    var probe = document.createElement('div');
    probe.style.cssText = 'position:absolute;visibility:hidden;height:var(' + varName + ')';
    root.appendChild(probe);
    var px = probe.getBoundingClientRect().height;
    probe.remove();
    return px;
  }

  function build(root) {
    var src = root.querySelector('.bpi__sheet');
    var host = root.querySelector('.bprev__pages');
    var meta = root.querySelector('.bprev__meta');
    if (!src || !host) return 0;

    var cell = src.querySelector('.bpi__page > tbody > tr > td');
    var topBand = src.querySelector('.bpi__lp-top');
    var botBand = src.querySelector('.bpi__lp-bottom');
    if (!cell) return 0;

    host.innerHTML = '';
    var sheets = [];
    var avail = 0;
    var current = null;

    function newSheet() {
      var sheet = document.createElement('div');
      sheet.className = 'bprev__sheet';
      var area = document.createElement('div');
      area.className = 'bprev__area';
      var topClone = null;
      if (topBand) {
        topClone = topBand.cloneNode(true);
        area.appendChild(topClone);
      }
      var body = document.createElement('div');
      body.className = 'bprev__body';
      area.appendChild(body);
      if (botBand) area.appendChild(botBand.cloneNode(true));
      var num = document.createElement('span');
      num.className = 'bprev__num';
      area.appendChild(num);
      sheet.appendChild(area);
      host.appendChild(sheet);

      if (!avail) {
        // Body room = page area minus the letterhead band minus the reserved
        // strip the closing band occupies on paper. Measure the CLONE: the
        // source .bpi__sheet is display:none in preview mode, so measuring the
        // original band returns 0 and every page comes out a band too tall.
        var bandH = topClone ? topClone.getBoundingClientRect().height : 0;
        avail = area.clientHeight - bandH - pxOf(root, '--bpi-band-reserve');
      }
      current = { sheet: sheet, body: body, num: num };
      sheets.push(current);
      return current;
    }

    function overflows() {
      return current.body.getBoundingClientRect().height > avail;
    }

    newSheet();

    Array.prototype.forEach.call(cell.children, function (block) {
      var table = block.querySelector ? block.querySelector('.bpi__table') : null;

      if (!table) {
        var clone = block.cloneNode(true);
        current.body.appendChild(clone);
        if (overflows() && current.body.children.length > 1) {
          clone.remove();
          newSheet();
          current.body.appendChild(clone);
        }
        return;
      }

      // Ledger: refill row by row so the break lands where the printer puts it.
      var head = table.querySelector('thead');
      var rows = Array.prototype.slice.call(table.querySelectorAll('tbody > tr'));
      var foot = table.querySelector('tfoot');

      function freshTable() {
        var wrap = block.cloneNode(false);
        var t = table.cloneNode(false);
        if (head) t.appendChild(head.cloneNode(true));
        var tb = document.createElement('tbody');
        t.appendChild(tb);
        wrap.appendChild(t);
        current.body.appendChild(wrap);
        return { table: t, body: tb };
      }

      var slice = freshTable();
      rows.forEach(function (row) {
        var r = row.cloneNode(true);
        slice.body.appendChild(r);
        if (overflows() && slice.body.children.length > 1) {
          r.remove();
          newSheet();
          slice = freshTable();
          slice.body.appendChild(r);
        }
      });

      if (foot) {
        var f = foot.cloneNode(true);
        slice.table.appendChild(f);
        if (overflows()) {
          f.remove();
          newSheet();
          slice = freshTable();
          slice.table.appendChild(f);
        }
      }
    });

    sheets.forEach(function (s, i) {
      s.num.textContent = 'Page ' + (i + 1) + ' of ' + sheets.length;
    });
    if (meta) {
      meta.textContent = sheets.length + (sheets.length === 1 ? ' page' : ' pages') + ' · A4 portrait';
    }
    return sheets.length;
  }

  document.addEventListener('DOMContentLoaded', function () {
    var root = document.querySelector('.bpi');
    var btn = document.querySelector('[data-bpi-preview-toggle]');
    if (!root || !btn) return;

    btn.addEventListener('click', function () {
      var on = root.classList.toggle('bpi--preview');
      if (on && !BUILT) { build(root); BUILT = true; }
      btn.setAttribute('aria-pressed', on ? 'true' : 'false');
      btn.textContent = on ? 'Exit preview' : 'A4 preview';
      if (on) root.querySelector('.bprev').scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  });
})();
