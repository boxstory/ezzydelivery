/* Purpose: HTML5 drag-and-drop for the CRM leads board — moves cards between stage columns and persists via fetch POST.
   Used by: workforce/templates/workforce/crm/leads_board.html (reads window.CRMB_CONFIG for the CSRF token).
   Notes: Optimistic move with revert on failure; delegated listeners bound once so HTMX swaps of #main-content stay safe. */

(function () {
  'use strict';

  if (window.__crmbInit) return;
  window.__crmbInit = true;

  var draggedCard = null;

  /* ── Lane strip panning ───────────────────────────────────────────────────
     The strip is wider than the console and lives inside <main style="overflow:hidden">,
     so the browser's horizontal scrollbar sat below the fold and the right-hand
     columns could not be reached at all. Three ways out, all on the same scroller:
     the pan buttons, the mouse wheel, and auto-pan while dragging a card. */

  function lanes() { return document.getElementById('workforce_crm_board_div_lanes'); }

  // Height is measured, not guessed: whatever chrome sits above the strip on this
  // page (header, tabs, toolbar, notes card) decides how much viewport is left.
  function sizeLanes() {
    var el = lanes();
    if (!el) return;
    if (window.matchMedia('(max-width: 575px)').matches) {
      el.style.removeProperty('--crmb-lanes-h');
      return;
    }
    var avail = window.innerHeight - el.getBoundingClientRect().top - 16;  // 16px breathing room
    if (avail < 320) avail = 320;
    el.style.setProperty('--crmb-lanes-h', Math.round(avail) + 'px');
    syncPan();
  }

  function step() {
    var el = lanes();
    if (!el) return 280;
    var col = el.querySelector('.crmb__column');
    return col ? col.getBoundingClientRect().width + 14 : Math.round(el.clientWidth * 0.8);
  }

  // Buttons only exist when there is somewhere to go, and each end disables itself.
  function syncPan() {
    var el = lanes();
    if (!el) return;
    var overflow = el.scrollWidth - el.clientWidth;
    var prev = document.querySelector('.crmb__pan--prev');
    var next = document.querySelector('.crmb__pan--next');
    if (!prev || !next) return;
    var show = overflow > 4;
    prev.hidden = !show;
    next.hidden = !show;
    if (!show) return;
    prev.disabled = el.scrollLeft <= 1;
    next.disabled = el.scrollLeft >= overflow - 1;
  }

  document.addEventListener('click', function (e) {
    var btn = e.target.closest && e.target.closest('[data-crmb-pan]');
    if (!btn) return;
    var el = lanes();
    if (!el) return;
    el.scrollBy({ left: parseInt(btn.getAttribute('data-crmb-pan'), 10) * step(), behavior: 'smooth' });
  });

  // Vertical wheel over the strip pans sideways — but not when the pointer is over a
  // column body that still has its own rows to scroll, or the cards become unreachable.
  document.addEventListener('wheel', function (e) {
    var el = lanes();
    if (!el || !el.contains(e.target)) return;
    if (Math.abs(e.deltaX) > Math.abs(e.deltaY)) return;   // real trackpad h-scroll: leave it
    var body = e.target.closest && e.target.closest('.crmb__col-body');
    if (body && body.scrollHeight > body.clientHeight + 1) {
      var atTop = body.scrollTop <= 0;
      var atEnd = body.scrollTop >= body.scrollHeight - body.clientHeight - 1;
      if (!((e.deltaY < 0 && atTop) || (e.deltaY > 0 && atEnd))) return;   // still room in the column
    }
    if (el.scrollWidth <= el.clientWidth) return;
    e.preventDefault();
    el.scrollLeft += e.deltaY;
  }, { passive: false });

  document.addEventListener('scroll', function (e) {
    if (e.target && e.target.id === 'workforce_crm_board_div_lanes') syncPan();
  }, true);

  window.addEventListener('resize', sizeLanes);
  document.addEventListener('DOMContentLoaded', sizeLanes);
  document.addEventListener('htmx:afterSwap', sizeLanes);   // filters re-render the strip
  sizeLanes();

  document.addEventListener('dragstart', function (e) {
    var card = e.target.closest && e.target.closest('.crmb__card');
    if (!card) return;
    draggedCard = card;
    card.classList.add('is-dragging');
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', card.getAttribute('data-lead-id'));
  });

  document.addEventListener('dragend', function () {
    stopAutoPan();
    if (draggedCard) draggedCard.classList.remove('is-dragging');
    draggedCard = null;
    document.querySelectorAll('.crmb__col-body.is-dragover').forEach(function (el) {
      el.classList.remove('is-dragover');
    });
  });

  // Dragging towards either edge pans the strip, so a card can reach a column that
  // is off screen — without this the drop target has to already be visible.
  var autoPan = 0;
  var autoPanTimer = null;

  function stopAutoPan() {
    autoPan = 0;
    if (autoPanTimer) { clearInterval(autoPanTimer); autoPanTimer = null; }
  }

  function edgePan(clientX) {
    var el = lanes();
    if (!el) return;
    var box = el.getBoundingClientRect();
    var zone = 90;
    var dir = 0;
    if (clientX > box.left && clientX < box.left + zone) dir = -1;
    else if (clientX < box.right && clientX > box.right - zone) dir = 1;
    if (dir === autoPan) return;
    autoPan = dir;
    if (autoPanTimer) { clearInterval(autoPanTimer); autoPanTimer = null; }
    if (!dir) return;
    autoPanTimer = setInterval(function () {
      var strip = lanes();
      if (!strip || !draggedCard) { stopAutoPan(); return; }
      strip.scrollLeft += autoPan * 24;
      syncPan();
    }, 16);
  }

  document.addEventListener('dragover', function (e) {
    if (!draggedCard) return;
    edgePan(e.clientX);
    var body = e.target.closest && e.target.closest('[data-stage-body]');
    if (!body) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    body.classList.add('is-dragover');
  });

  document.addEventListener('dragleave', function (e) {
    var body = e.target.closest && e.target.closest('[data-stage-body]');
    if (body && !body.contains(e.relatedTarget)) body.classList.remove('is-dragover');
  });

  document.addEventListener('drop', function (e) {
    stopAutoPan();
    var body = e.target.closest && e.target.closest('[data-stage-body]');
    if (!body || !draggedCard) return;
    e.preventDefault();
    body.classList.remove('is-dragover');

    var card = draggedCard;
    var newStage = body.getAttribute('data-stage-body');
    var sourceBody = card.parentElement;
    if (sourceBody === body) return;

    var cfg = window.CRMB_CONFIG || {};

    // Whether a column confirms before accepting a card — and whether it asks for
    // a reason — is configured per column at /workforce/crm/stages/ and arrives as
    // data attributes, so a staff-created decision column prompts too.
    var confirmText = body.getAttribute('data-confirm') || '';
    var needsReason = body.getAttribute('data-needs-reason') === '1';
    var rejectionReason = '';
    var name = ((card.querySelector('.crmb__card-name') || {}).textContent || 'this lead').trim();
    // needsReason is evaluated independently of confirmText: nesting it inside the
    // confirm branch meant a column with a blank confirm text skipped BOTH prompts.
    if (needsReason) {
      var reason = prompt('This will ' + (confirmText || 'change this driver\'s status') +
        ' (' + name + ') and update their real application status.\n\nReason (optional):', '');
      if (reason === null) return;   // cancelled
      rejectionReason = reason;
    } else if (confirmText) {
      if (!confirm('This will ' + confirmText + ' (' + name + ') and update their real application status. Continue?')) {
        return;
      }
    }

    // Optimistic move; revert if the server rejects it
    var emptyHint = body.querySelector('.crmb__col-empty');
    if (emptyHint) emptyHint.remove();
    body.prepend(card);
    updateCounts();

    var fd = new FormData();
    fd.append('stage', newStage);
    fd.append('rejection_reason', rejectionReason);
    fd.append('csrfmiddlewaretoken', cfg.csrfToken || '');

    fetch(card.getAttribute('data-stage-url'), { method: 'POST', body: fd })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data.success) { revert(card, sourceBody, data.error); return; }
        // Accepted but pinned: the card no longer tracks the driver's application, so
        // say so and mark it, rather than letting staff assume it is still in sync.
        if (data.pinned && !card.querySelector('.crmb__card-pin')) {
          var pin = document.createElement('span');
          pin.className = 'crmb__card-pin';
          pin.title = 'Pinned here by staff — this card does not follow the driver\'s application status';
          pin.innerHTML = '<i class="fa-solid fa-thumbtack"></i>';
          var top = card.querySelector('.crmb__card-top');
          var id = top && top.querySelector('.crmb__card-id');
          if (top) { id ? top.insertBefore(pin, id) : top.appendChild(pin); }
        }
        if (!data.pinned) {
          var existing = card.querySelector('.crmb__card-pin');
          if (existing) existing.remove();
        }
        if (data.warning) alert(data.warning);
      })
      .catch(function (err) { revert(card, sourceBody, err.message); });
  });

  // Open detail on click (but not while dragging, and not on inner links
  // like the WhatsApp chat chip — those navigate on their own)
  document.addEventListener('click', function (e) {
    var card = e.target.closest && e.target.closest('.crmb__card');
    if (!card) return;
    if (e.target.closest('a')) return;
    var url = card.getAttribute('data-detail-url');
    if (url) window.location.href = url;
  });

  // Keyboard: Enter/Space opens the focused card
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    var card = e.target.closest && e.target.closest('.crmb__card');
    if (!card) return;
    e.preventDefault();
    var url = card.getAttribute('data-detail-url');
    if (url) window.location.href = url;
  });

  function revert(card, sourceBody, message) {
    var hint = sourceBody.querySelector('.crmb__col-empty');
    if (hint) hint.remove();
    sourceBody.prepend(card);
    updateCounts();
    alert('Could not move lead: ' + (message || 'unknown error'));
  }

  function updateCounts() {
    document.querySelectorAll('.crmb__column').forEach(function (col) {
      var count = col.querySelectorAll('.crmb__card').length;
      var badge = col.querySelector('.crmb__col-count');
      if (badge) badge.textContent = count;
      // A column emptied by dragging gets its hint back, instead of sitting blank
      // until the next page load.
      var body = col.querySelector('.crmb__col-body');
      if (!body) return;
      var hint = body.querySelector('.crmb__col-empty');
      if (count === 0 && !hint) {
        var el = document.createElement('div');
        el.className = 'crmb__col-empty';
        el.textContent = body.hasAttribute('data-stage-body') ? 'Drop leads here' : 'Empty';
        body.appendChild(el);
      } else if (count > 0 && hint) {
        hint.remove();
      }
    });
  }
})();
