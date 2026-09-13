/*
Purpose: The per-size box counters — stepper buttons, the whole-job cap, and the running total
Used by: p2p/book.html, p2p/delivery_edit.html, workforce/forms/p2p_new.html
Notes: These counters ARE the box count; there is no separate total field to keep in step. The
       server adds them up the same way (BookingDetailsForm.clean) and the cap here is the same
       one it validates, so nothing typed on the page can post a load it will reject silently.
       Every counter at zero means the size card describes the job, which is one box — and picking
       a different card then moves a single-size count onto it rather than stranding it.
*/
(function () {
    'use strict';

    var block = document.getElementById('p2p_load_block');
    if (!block) { return; }

    var form = block.closest('form');
    var counters = Array.prototype.slice.call(block.querySelectorAll('[name^="count_"]'));
    if (!form || !counters.length) { return; }

    var totalEl = document.getElementById('p2p_load_total');
    /* p2p.models.P2P_MAX_BOXES, off the field the server rendered rather than restated. */
    var maxBoxes = parseInt(counters[0].getAttribute('max'), 10) || 20;

    function countOf(input) {
        var n = parseInt(input.value, 10);
        return isNaN(n) || n < 0 ? 0 : n;
    }

    function total() {
        return counters.reduce(function (sum, input) { return sum + countOf(input); }, 0);
    }

    /* What the load measures, in cubic metres. Each size carries its own figure on the
     * stepper (data-size-cbm, straight off P2P_SIZE_CARDS), because that is the number a
     * vehicle is measured in — a motorcycle box is 0.027 — and it is what decides whether
     * the load fits the vehicle chosen above. */
    function cbm() {
        return counters.reduce(function (sum, input) {
            var group = input.closest('.p2pb__step');
            var per = group ? parseFloat(group.dataset.sizeCbm) : NaN;
            return isNaN(per) ? sum : sum + per * countOf(input);
        }, 0);
    }

    function render() {
        var sum = total();
        if (totalEl) {
            var parts = [];
            if (sum) {
                parts.push(sum + ' box' + (sum === 1 ? '' : 'es'));
                var volume = cbm();
                if (volume > 0) { parts.push(volume.toFixed(3) + ' cbm'); }
                if (sum >= maxBoxes) { parts.push('the most one job can be'); }
            }
            totalEl.textContent = parts.length ? parts.join(' · ') : 'Nothing added yet';
        }
        counters.forEach(function (input) {
            var minus = input.previousElementSibling;
            if (minus) { minus.disabled = countOf(input) <= 0; }
        });
    }

    function set(input, n) {
        var wanted = Math.max(0, Math.min(maxBoxes, n));
        /* The whole job is capped, not each size: eleven small plus eleven medium is not
         * two bookable jobs. Trim the size just raised rather than rewriting the others. */
        var others = total() - countOf(input);
        input.value = Math.max(0, Math.min(wanted, maxBoxes - others)) || '';
        render();
        input.dispatchEvent(new Event('change', { bubbles: true }));
    }

    block.querySelectorAll('[data-load-step]').forEach(function (button) {
        button.addEventListener('click', function () {
            var input = button.parentElement.querySelector('[name^="count_"]');
            if (input) { set(input, countOf(input) + parseInt(button.dataset.loadStep, 10)); }
        });
    });

    counters.forEach(function (input) { input.addEventListener('input', render); });

    /* Picking a different size card with one size counted moves that count onto the new
     * card, so the two controls cannot describe different jobs. A mix is left alone: no
     * single card describes it, and the server prices it off the counters anyway. */
    form.querySelectorAll('[name="size"]').forEach(function (radio) {
        radio.addEventListener('change', function () {
            var filled = counters.filter(function (input) { return countOf(input) > 0; });
            if (filled.length !== 1) { return; }
            var moving = filled[0];
            var target = block.querySelector('[name="count_' + radio.value + '"]');
            if (!target || target === moving) { return; }
            var n = countOf(moving);
            moving.value = '';
            set(target, n);
        });
    });

    render();
})();
