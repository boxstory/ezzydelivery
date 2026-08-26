/* Purpose: Inline Leaflet map for any coordinate on the site — one point, or two compared. */
/* Used by: templates/includes/components/_map_point.html (delegated, so it works on lists rendered by htmx too). */
/* Notes: Loads Leaflet on demand so the component works on bases that do not already ship it. */
/*        The map opens in a modal: a table cell is too narrow to judge a location in. */
/*        The tile attribution box is replaced by an "Open in Google Maps" link in the same corner. */

(function () {
  'use strict';

  var LEAFLET_CSS = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
  var LEAFLET_JS = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
  var TILES = 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png';

  var loading = null;
  var built = {};

  // The panel is moved into the modal and put back on close, so the markup a
  // page emits stays exactly where it was declared.
  var modal = null;
  var openPanel = null;
  var openPlaceholder = null;
  var openBtn = null;

  function loadLeaflet() {
    if (window.L) return Promise.resolve();
    if (loading) return loading;
    loading = new Promise(function (resolve, reject) {
      if (!document.querySelector('link[href*="leaflet"]')) {
        var css = document.createElement('link');
        css.rel = 'stylesheet';
        css.href = LEAFLET_CSS;
        document.head.appendChild(css);
      }
      var js = document.createElement('script');
      js.src = LEAFLET_JS;
      js.onload = resolve;
      js.onerror = reject;
      document.head.appendChild(js);
    });
    return loading;
  }

  function marker(colour, tooltip) {
    var icon = L.divIcon({
      className: '',
      iconSize: [16, 16],
      iconAnchor: [8, 8],
      html: '<span class="mpt__marker" style="background:' + colour + '"></span>'
    });
    var m = L.marker([0, 0], { icon: icon });
    if (tooltip) m.bindTooltip(tooltip);
    return m;
  }

  // One point opens Google Maps at that pin; two points open the drive between
  // them, which is what staff actually want when they are comparing.
  function gmapsUrl(lat, lon, lat2, lon2) {
    if (!isNaN(lat2) && !isNaN(lon2)) {
      return 'https://www.google.com/maps/dir/?api=1&origin=' + lat + ',' + lon +
             '&destination=' + lat2 + ',' + lon2;
    }
    return 'https://www.google.com/maps/search/?api=1&query=' + lat + ',' + lon;
  }

  function gmapsControl(url, compare) {
    var ctl = L.control({ position: 'bottomright' });
    ctl.onAdd = function () {
      var a = L.DomUtil.create('a', 'mpt__gmaps');
      a.href = url;
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
      a.title = compare ? 'Open this route in Google Maps' : 'Open this point in Google Maps';
      a.innerHTML = '<i class="fa-solid fa-arrow-up-right-from-square"></i> ' +
                    (compare ? 'Route in Google Maps' : 'Open in Google Maps');
      // The link sits on the map, so a click must not also pan or zoom it.
      L.DomEvent.disableClickPropagation(a);
      L.DomEvent.disableScrollPropagation(a);
      return a;
    };
    return ctl;
  }

  function build(panel) {
    var lat = parseFloat(panel.dataset.lat);
    var lon = parseFloat(panel.dataset.lon);
    if (isNaN(lat) || isNaN(lon)) return null;

    // Wheel zoom is safe here: the map only ever renders in the modal, and the
    // page behind it is scroll-locked, so the wheel has nothing else to do.
    var map = L.map(panel, { attributionControl: false });
    L.tileLayer(TILES, { maxZoom: 19 }).addTo(map);

    var points = [[lat, lon]];
    marker(panel.dataset.colour || '#1F2A44', panel.dataset.label || '')
      .setLatLng([lat, lon]).addTo(map);

    var lat2 = parseFloat(panel.dataset.lat2);
    var lon2 = parseFloat(panel.dataset.lon2);
    if (!isNaN(lat2) && !isNaN(lon2)) {
      // Compare mode: the line between the two points IS the thing being
      // judged, so it is drawn rather than left to be imagined.
      points.push([lat2, lon2]);
      marker(panel.dataset.colour2 || '#b4532a', panel.dataset.label2 || '')
        .setLatLng([lat2, lon2]).addTo(map);
      L.polyline(points, {
        color: '#1F2A44', weight: 2, dashArray: '5,5', opacity: 0.7
      }).addTo(map);
    }

    if (points.length > 1) {
      map.fitBounds(L.latLngBounds(points), { padding: [36, 36] });
    } else {
      map.setView(points[0], parseInt(panel.dataset.zoom || '15', 10));
    }

    gmapsControl(gmapsUrl(lat, lon, lat2, lon2), points.length > 1).addTo(map);
    return map;
  }

  /* ── Modal shell ─────────────────────────────────────────────────────── */

  function ensureModal() {
    if (modal) return modal;
    modal = document.createElement('div');
    modal.className = 'mpt__modal';
    modal.setAttribute('hidden', '');
    modal.innerHTML =
      '<div class="mpt__modal-backdrop" data-mpt-close></div>' +
      '<div class="mpt__modal-card" role="dialog" aria-modal="true" aria-labelledby="mpt_modal_title">' +
        '<div class="mpt__modal-head">' +
          '<h3 class="mpt__modal-title" id="mpt_modal_title"></h3>' +
          '<button type="button" class="mpt__modal-close" data-mpt-close aria-label="Close map">' +
            '<i class="fa-solid fa-xmark"></i></button>' +
        '</div>' +
        '<div class="mpt__modal-body"></div>' +
      '</div>';
    document.body.appendChild(modal);
    modal.addEventListener('click', function (ev) {
      if (ev.target.closest('[data-mpt-close]')) closeModal();
    });
    return modal;
  }

  function closeModal() {
    if (!modal || modal.hasAttribute('hidden')) return;
    modal.setAttribute('hidden', '');
    document.body.classList.remove('mpt-modal-open');

    if (openPanel) {
      openPanel.setAttribute('hidden', '');
      // htmx may have swapped the row away while the map was open — only put
      // the panel back if its original spot still exists.
      if (openPlaceholder && openPlaceholder.parentNode) {
        openPlaceholder.parentNode.insertBefore(openPanel, openPlaceholder);
      } else {
        openPanel.remove();
      }
    }
    if (openPlaceholder) openPlaceholder.remove();
    if (openBtn) {
      openBtn.classList.remove('mpt__btn--on');
      openBtn.setAttribute('aria-expanded', 'false');
      if (document.body.contains(openBtn)) openBtn.focus();
    }
    openPanel = openPlaceholder = openBtn = null;
  }

  function openModal(btn, panel, wrap) {
    ensureModal();
    if (openPanel) closeModal();

    openBtn = btn;
    openPanel = wrap;
    openPlaceholder = document.createComment('mpt-panel');
    wrap.parentNode.insertBefore(openPlaceholder, wrap);

    // In compare mode both labels belong in the title — which two things are
    // being held against each other is the whole point of the panel.
    var title = panel.dataset.label || btn.getAttribute('title') || 'Location';
    if (panel.dataset.lat2 && panel.dataset.label2) {
      title = (panel.dataset.label || 'Point A') + ' vs ' + panel.dataset.label2;
    }
    modal.querySelector('.mpt__modal-title').textContent = title;
    modal.querySelector('.mpt__modal-body').appendChild(wrap);
    wrap.removeAttribute('hidden');
    modal.removeAttribute('hidden');
    document.body.classList.add('mpt-modal-open');
    modal.querySelector('.mpt__modal-close').focus();

    btn.classList.add('mpt__btn--on');
    btn.setAttribute('aria-expanded', 'true');
  }

  document.addEventListener('keydown', function (ev) {
    if (ev.key === 'Escape') closeModal();
  });

  document.addEventListener('click', function (ev) {
    var btn = ev.target.closest('[data-mappoint-toggle]');
    if (!btn) return;
    ev.preventDefault();
    // List rows are often click-through to the record; opening a map must not
    // also navigate away from the list.
    ev.stopPropagation();

    var panel = document.getElementById(btn.dataset.mappointToggle);
    if (!panel) return;

    // Clicking the same button again closes the map.
    if (openBtn === btn) { closeModal(); return; }

    openModal(btn, panel, panel.closest('.mpt__panel') || panel);

    var key = panel.id;
    if (built[key]) {
      // An htmx swap can replace the row and hand us a fresh element under the
      // same id, which would leave the cached map bound to a detached node.
      if (built[key].getContainer() === panel) {
        setTimeout(function () { built[key].invalidateSize(); }, 60);
        return;
      }
      built[key].remove();
      delete built[key];
    }
    loadLeaflet().then(function () {
      var map = build(panel);
      if (map) {
        built[key] = map;
        // Leaflet sizes to a visible container, so measure after the reveal.
        setTimeout(function () { map.invalidateSize(); }, 60);
      }
    }).catch(function () {
      panel.innerHTML = '<p class="mpt__error">Map could not be loaded.</p>';
    });
  });
})();
