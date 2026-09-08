/*
Purpose: Opens a page's "about this page" notes card and fetches its content on first click
Used by: every dashboard base (staff, warehouse) via includes/main_dashboard_scripts.html
Notes: Delegated on document so it survives HTMX swaps; content comes from workforce:page_notes.
*/
/**
 * Every staff page carries a "what this page does" card under its hero, closed
 * on load, opened by the round help button in the hero. Delegated on document
 * so it keeps working after an HTMX swap and no page needs its own script.
 * Contract: button has [data-wfnote-toggle] + aria-controls="<panel id>".
 *
 * The panel ships EMPTY: its prose (~13 KB per page) lives in a partial served
 * by workforce:page_notes and is fetched the first time the button is clicked,
 * so a normal page load carries none of it. Panels that still hold their own
 * markup (no data-wfnote-src) just toggle as before.
 */
(function () {
    'use strict';

    function setLabel(btn, hidden) {
        btn.setAttribute('aria-expanded', hidden ? 'false' : 'true');
        var sr = btn.querySelector('.visually-hidden');
        if (sr) sr.textContent = hidden ? 'Show notes' : 'Hide notes';
    }

    function load(panel, btn) {
        var url = panel.getAttribute('data-wfnote-src');
        panel.setAttribute('data-wfnote-state', 'loading');
        btn.classList.add('wfnote__btn--loading');
        fetch(url, {credentials: 'same-origin', headers: {'X-Requested-With': 'XMLHttpRequest'}})
            .then(function (r) {
                if (!r.ok) throw new Error('HTTP ' + r.status);
                return r.text();
            })
            .then(function (html) {
                panel.innerHTML = html;
                panel.setAttribute('data-wfnote-state', 'loaded');
            })
            .catch(function (err) {
                panel.setAttribute('data-wfnote-state', '');
                panel.innerHTML = '<p class="wfnote__lede">Notes could not be loaded (' +
                    (err && err.message ? err.message : 'network error') + '). Try again.</p>';
            })
            .finally(function () {
                btn.classList.remove('wfnote__btn--loading');
            });
    }

    document.addEventListener('click', function (e) {
        var btn = e.target.closest ? e.target.closest('[data-wfnote-toggle]') : null;
        if (!btn) return;
        var panel = document.getElementById(btn.getAttribute('aria-controls'));
        if (!panel) return;

        panel.hidden = !panel.hidden;
        setLabel(btn, panel.hidden);

        if (!panel.hidden && panel.getAttribute('data-wfnote-src') &&
            panel.getAttribute('data-wfnote-state') !== 'loaded' &&
            panel.getAttribute('data-wfnote-state') !== 'loading') {
            load(panel, btn);
        }
    });
})();
