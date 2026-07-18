/* Purpose: HTML5 drag-and-drop for the CRM leads board — moves cards between stage columns and persists via fetch POST.
   Used by: workforce/templates/workforce/crm/leads_board.html (reads window.CRMB_CONFIG for the CSRF token).
   Notes: Optimistic move with revert on failure; delegated listeners bound once so HTMX swaps of #main-content stay safe. */

(function () {
  'use strict';

  if (window.__crmbInit) return;
  window.__crmbInit = true;

  var draggedCard = null;

  document.addEventListener('dragstart', function (e) {
    var card = e.target.closest && e.target.closest('.crmb__card');
    if (!card) return;
    draggedCard = card;
    card.classList.add('is-dragging');
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', card.getAttribute('data-lead-id'));
  });

  document.addEventListener('dragend', function () {
    if (draggedCard) draggedCard.classList.remove('is-dragging');
    draggedCard = null;
    document.querySelectorAll('.crmb__col-body.is-dragover').forEach(function (el) {
      el.classList.remove('is-dragover');
    });
  });

  document.addEventListener('dragover', function (e) {
    var body = e.target.closest && e.target.closest('[data-stage-body]');
    if (!body || !draggedCard) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    body.classList.add('is-dragover');
  });

  document.addEventListener('dragleave', function (e) {
    var body = e.target.closest && e.target.closest('[data-stage-body]');
    if (body && !body.contains(e.relatedTarget)) body.classList.remove('is-dragover');
  });

  document.addEventListener('drop', function (e) {
    var body = e.target.closest && e.target.closest('[data-stage-body]');
    if (!body || !draggedCard) return;
    e.preventDefault();
    body.classList.remove('is-dragover');

    var card = draggedCard;
    var newStage = body.getAttribute('data-stage-body');
    var sourceBody = card.parentElement;
    if (sourceBody === body) return;

    // Optimistic move; revert if the server rejects it
    var emptyHint = body.querySelector('.crmb__col-empty');
    if (emptyHint) emptyHint.remove();
    body.prepend(card);
    updateCounts();

    var fd = new FormData();
    fd.append('stage', newStage);
    fd.append('csrfmiddlewaretoken', (window.CRMB_CONFIG || {}).csrfToken || '');

    fetch(card.getAttribute('data-stage-url'), { method: 'POST', body: fd })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data.success) revert(card, sourceBody, data.error);
      })
      .catch(function (err) { revert(card, sourceBody, err.message); });
  });

  // Open detail on click (but not while dragging)
  document.addEventListener('click', function (e) {
    var card = e.target.closest && e.target.closest('.crmb__card');
    if (!card) return;
    var url = card.getAttribute('data-detail-url');
    if (url) window.location.href = url;
  });

  function revert(card, sourceBody, message) {
    sourceBody.prepend(card);
    updateCounts();
    alert('Could not move lead: ' + (message || 'unknown error'));
  }

  function updateCounts() {
    document.querySelectorAll('.crmb__column').forEach(function (col) {
      var count = col.querySelectorAll('.crmb__card').length;
      var badge = col.querySelector('.crmb__col-count');
      if (badge) badge.textContent = count;
    });
  }
})();
