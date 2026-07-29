/* Purpose: Seller roster cards — draw the COD rail and filter the grid by name or code. */
/* Used by: workforce/templates/workforce/seller_transactions.html (landing state). */
/* Notes: Rail widths arrive as data-seg percentages because templates may not carry inline styles. */

(function () {
    'use strict';

    function drawRails(root) {
        root.querySelectorAll('.sro__rail-seg').forEach(function (seg) {
            var pct = parseFloat(seg.dataset.seg);
            seg.style.setProperty('--seg', (isNaN(pct) ? 0 : pct) + '%');
        });
    }

    function initFilter(root) {
        var input = root.querySelector('#workforce_seller_roster_input_search');
        var list = root.querySelector('#workforce_seller_roster_list');
        var none = root.querySelector('#workforce_seller_roster_no_match');
        if (!input || !list) return;

        var items = Array.prototype.slice.call(list.querySelectorAll('.sro__item'));

        input.addEventListener('input', function () {
            var q = input.value.trim().toLowerCase();
            var shown = 0;

            items.forEach(function (item) {
                var match = !q || (item.dataset.seller || '').indexOf(q) !== -1;
                item.hidden = !match;
                if (match) shown++;
            });

            if (none) none.hidden = shown !== 0;
        });
    }

    function init(root) {
        if (!root || !root.querySelector('.sro')) return;
        drawRails(root);
        initFilter(root);
    }

    document.addEventListener('DOMContentLoaded', function () { init(document); });
    // The staff console swaps #main-content via HTMX, which drops these handlers.
    document.body.addEventListener('htmx:afterSwap', function (evt) {
        init(evt.detail.target);
    });
})();
