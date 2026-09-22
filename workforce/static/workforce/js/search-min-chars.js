/* Purpose: Hold an htmx staff search box until the typed term is long enough to be worth a query.
   Used by: templates/wf_dashboard_base.html — every input carrying data-search-min (CRM boards,
            lists, contacts, WhatsApp inbox, drivers list, pricing inquiries).
   Notes: The CSP has no 'unsafe-eval', so htmx's own `hx-trigger="keyup[expr]"` filters — which it
          compiles with new Function — are blocked here; the gate runs on htmx:beforeRequest instead.
          An empty box always passes, otherwise clearing the field could never reset the list. */
(function () {
  'use strict';

  var SELECTOR = '[data-search-min]';
  var DEFAULT_MIN = 3;

  function minFor(input) {
    var n = parseInt(input.getAttribute('data-search-min'), 10);
    return (isNaN(n) || n < 1) ? DEFAULT_MIN : n;
  }

  function tooShort(input) {
    var term = (input.value || '').trim();
    return term.length > 0 && term.length < minFor(input);
  }

  // The hint is built in JS rather than repeated in six templates; it floats under the
  // field (absolute, see workforce.css) so showing it never re-flows the filter bar.
  function paint(input) {
    var host = input.parentNode;
    if (!host) return;
    var hint = host.querySelector(':scope > .search-min');
    if (!hint) {
      host.classList.add('search-min-host');
      hint = document.createElement('span');
      hint.className = 'search-min';
      hint.setAttribute('role', 'status');
      hint.textContent = 'Type ' + minFor(input) + ' or more characters to search';
      host.insertBefore(hint, input.nextSibling);
    }
    hint.classList.toggle('search-min--on', tooShort(input));
  }

  document.addEventListener('input', function (evt) {
    var input = evt.target;
    if (input && input.matches && input.matches(SELECTOR)) paint(input);
  });

  // The request htmx was about to fire for the search box itself.
  document.body.addEventListener('htmx:beforeRequest', function (evt) {
    var elt = evt.detail && evt.detail.elt;
    if (elt && elt.matches && elt.matches(SELECTOR) && tooShort(elt)) evt.preventDefault();
  });

  // A half-typed term must not ride along on someone else's request either — changing a
  // facet uses hx-include, which would otherwise apply the two letters we just refused.
  document.body.addEventListener('htmx:configRequest', function (evt) {
    var params = evt.detail && evt.detail.parameters;
    if (!params) return;
    var inputs = document.querySelectorAll(SELECTOR);
    for (var i = 0; i < inputs.length; i++) {
      var input = inputs[i];
      if (!input.name || !tooShort(input)) continue;
      if (typeof params.delete === 'function') {          // htmx 2 hands over a FormData
        if (params.get(input.name) === input.value) params.delete(input.name);
      } else if (params[input.name] === input.value) {    // htmx 1 handed over a plain object
        delete params[input.name];
      }
    }
  });
})();
