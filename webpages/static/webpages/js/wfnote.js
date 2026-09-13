/*
Purpose: Slides a page's "about this page" notes drawer in from the right, fetching its content on first click
Used by: every dashboard base (staff, warehouse) via includes/main_dashboard_scripts.html
Notes: Delegated on document so it survives HTMX swaps; content comes from workforce:page_notes.
*/
/**
 * Every staff page carries a "what this page does" panel, closed on load and
 * opened by the round help button in the hero. It slides in from the right over
 * a scrim rather than expanding under the hero, so reading the notes no longer
 * pushes the table you were looking at down the page.
 * Contract: button has [data-wfnote-toggle] + aria-controls="<panel id>". The
 * drawer's head and body are built here, so no template carries them.
 *
 * The panel ships EMPTY: its prose (~13 KB per page) lives in a partial served
 * by workforce:page_notes and is fetched the first time the button is clicked,
 * so a normal page load carries none of it. Panels that still hold their own
 * markup (no data-wfnote-src) just open as before.
 */
(function () {
    'use strict';

    var FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), ' +
        'select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

    var openPanel = null;   // the drawer currently on screen
    var opener = null;      // the hero button that opened it, to hand focus back
    var scrim = null;

    function setLabel(btn, hidden) {
        if (!btn) return;
        btn.setAttribute('aria-expanded', hidden ? 'false' : 'true');
        var sr = btn.querySelector('.visually-hidden');
        if (sr) sr.textContent = hidden ? 'Show notes' : 'Hide notes';
    }

    function getScrim() {
        if (scrim && document.body.contains(scrim)) return scrim;
        scrim = document.createElement('div');
        scrim.className = 'wfnote__scrim';
        scrim.hidden = true;
        scrim.addEventListener('click', close);
        document.body.appendChild(scrim);
        return scrim;
    }

    /** Build the drawer chrome once, moving whatever the panel already holds
     *  into the scrolling body — the two CRM boards ship their notes inline. */
    function upgrade(panel) {
        if (panel.querySelector('.wfnote__body')) return;

        var body = document.createElement('div');
        body.className = 'wfnote__body';
        while (panel.firstChild) body.appendChild(panel.firstChild);

        var head = document.createElement('div');
        head.className = 'wfnote__head';
        var title = document.createElement('h2');
        title.className = 'wfnote__title';
        title.textContent = 'About this page';
        var closeBtn = document.createElement('button');
        closeBtn.type = 'button';
        closeBtn.className = 'wfnote__close';
        closeBtn.setAttribute('data-wfnote-close', '');
        closeBtn.innerHTML = '<i class="fa-solid fa-xmark" aria-hidden="true"></i>' +
            '<span class="visually-hidden">Close notes</span>';
        head.appendChild(title);
        head.appendChild(closeBtn);

        panel.appendChild(head);
        panel.appendChild(body);
        panel.setAttribute('role', 'dialog');
        panel.setAttribute('aria-modal', 'true');
        panel.setAttribute('aria-label', 'About this page');
    }

    /** Move the drawer onto <body> before it opens. A fixed element inside a
     *  transformed or filtered ancestor is positioned against that ancestor
     *  instead of the viewport, and page layouts vary too much across 180 pages
     *  to rely on none of them having one. Any panel left parked by an earlier
     *  page (HTMX swaps #main-content out from under it) goes at the same time,
     *  so ids stay unique. */
    function park(panel) {
        Array.prototype.slice.call(document.body.children).forEach(function (el) {
            if (el !== panel && el.classList && el.classList.contains('wfnote')) {
                el.parentNode.removeChild(el);
            }
        });
        if (panel.parentNode !== document.body) document.body.appendChild(panel);
    }

    function load(panel, btn) {
        var url = panel.getAttribute('data-wfnote-src');
        var body = panel.querySelector('.wfnote__body');
        panel.setAttribute('data-wfnote-state', 'loading');
        btn.classList.add('wfnote__btn--loading');
        fetch(url, {credentials: 'same-origin', headers: {'X-Requested-With': 'XMLHttpRequest'}})
            .then(function (r) {
                if (!r.ok) throw new Error('HTTP ' + r.status);
                return r.text();
            })
            .then(function (html) {
                body.innerHTML = html;
                panel.setAttribute('data-wfnote-state', 'loaded');
            })
            .catch(function (err) {
                panel.setAttribute('data-wfnote-state', '');
                body.innerHTML = '<p class="wfnote__lede">Notes could not be loaded (' +
                    (err && err.message ? err.message : 'network error') + '). Try again.</p>';
            })
            .finally(function () {
                btn.classList.remove('wfnote__btn--loading');
            });
    }

    function open(panel, btn) {
        if (openPanel && openPanel !== panel) close();
        upgrade(panel);
        park(panel);

        panel.hidden = false;
        getScrim().hidden = false;
        // Read a layout value so the browser has a start position to animate
        // from; without it the class lands in the same frame as display and the
        // drawer simply appears.
        void panel.offsetWidth;
        panel.classList.add('wfnote--open');
        scrim.classList.add('wfnote__scrim--open');
        document.body.classList.add('wfnote-lock');

        openPanel = panel;
        opener = btn;
        setLabel(btn, false);

        var closeBtn = panel.querySelector('[data-wfnote-close]');
        if (closeBtn) closeBtn.focus();
    }

    function close() {
        if (!openPanel) return;
        var panel = openPanel;
        var btn = opener;
        openPanel = null;
        opener = null;

        panel.classList.remove('wfnote--open');
        if (scrim) scrim.classList.remove('wfnote__scrim--open');
        document.body.classList.remove('wfnote-lock');
        setLabel(btn, true);
        if (btn && document.body.contains(btn)) btn.focus();

        // hidden goes back on only once it has slid out, or the drawer would
        // vanish mid-animation. The timer covers the case where the transition
        // never fires — reduced motion, or a background tab.
        var settled = false;
        function done() {
            if (settled) return;
            settled = true;
            panel.hidden = true;
            if (scrim && !openPanel) scrim.hidden = true;
        }
        var timer = setTimeout(done, 400);
        panel.addEventListener('transitionend', function handler(e) {
            if (e.target !== panel || e.propertyName !== 'transform') return;
            panel.removeEventListener('transitionend', handler);
            clearTimeout(timer);
            done();
        });
    }

    document.addEventListener('click', function (e) {
        if (!e.target.closest) return;

        if (e.target.closest('[data-wfnote-close]')) {
            close();
            return;
        }

        var btn = e.target.closest('[data-wfnote-toggle]');
        if (!btn) return;
        var panel = document.getElementById(btn.getAttribute('aria-controls'));
        if (!panel) return;

        if (openPanel === panel) {
            close();
            return;
        }

        open(panel, btn);

        if (panel.getAttribute('data-wfnote-src') &&
            panel.getAttribute('data-wfnote-state') !== 'loaded' &&
            panel.getAttribute('data-wfnote-state') !== 'loading') {
            load(panel, btn);
        }
    });

    document.addEventListener('keydown', function (e) {
        if (!openPanel) return;

        if (e.key === 'Escape' || e.key === 'Esc') {
            e.preventDefault();
            close();
            return;
        }
        if (e.key !== 'Tab') return;

        // Keep tabbing inside the drawer while it covers the page.
        var items = openPanel.querySelectorAll(FOCUSABLE);
        if (!items.length) return;
        var first = items[0];
        var last = items[items.length - 1];
        if (e.shiftKey && document.activeElement === first) {
            e.preventDefault();
            last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
            e.preventDefault();
            first.focus();
        }
    });

    // An HTMX swap can replace the page the open drawer describes. The drawer
    // itself survives (it is parked on <body>), so close it when the button it
    // came from is gone rather than leaving another page's notes on screen.
    document.addEventListener('htmx:afterSwap', function () {
        if (openPanel && (!opener || !document.body.contains(opener))) close();
    });
})();
