/**
 * Purpose: Open/close the mobile account drawer in the business PWA header.
 * Used by: templates/business_dashboard_base.html with business/parts/pwa_menu_drawer.html.
 * Notes: Locks body scroll while open and restores focus to the trigger on close.
 */
(function () {
  'use strict';

  function init() {
    var trigger = document.getElementById('business_pwa_menu_btn');
    var menu = document.getElementById('business_pwa_menu');
    if (!trigger || !menu || menu.dataset.bmnuReady === '1') return;
    menu.dataset.bmnuReady = '1';

    var panel = menu.querySelector('.bmnu__panel');

    function open() {
      menu.hidden = false;
      // Next frame so the transition runs from the closed state.
      requestAnimationFrame(function () {
        menu.classList.add('bmnu--open');
      });
      document.body.classList.add('bmnu-locked');
      trigger.setAttribute('aria-expanded', 'true');
      if (panel) panel.focus();
    }

    function close() {
      menu.classList.remove('bmnu--open');
      document.body.classList.remove('bmnu-locked');
      trigger.setAttribute('aria-expanded', 'false');
      window.setTimeout(function () {
        if (!menu.classList.contains('bmnu--open')) menu.hidden = true;
      }, 220);
      trigger.focus();
    }

    trigger.addEventListener('click', function () {
      if (menu.classList.contains('bmnu--open')) {
        close();
      } else {
        open();
      }
    });

    menu.addEventListener('click', function (e) {
      if (e.target.closest('[data-bmnu-close]')) close();
    });

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && menu.classList.contains('bmnu--open')) close();
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
