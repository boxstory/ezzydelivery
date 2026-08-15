/* Purpose: Inline Leaflet map for any coordinate on the site — one point, or two compared. */
/* Used by: templates/includes/components/_map_point.html (delegated, so it works on lists rendered by htmx too). */
/* Notes: Loads Leaflet on demand so the component works on bases that do not already ship it. */
/*        Driver turn-by-turn navigation is deliberately NOT handled here — that stays a Google Maps deep link. */

(function () {
  'use strict';

  var LEAFLET_CSS = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
  var LEAFLET_JS = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
  var TILES = 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png';
  var ATTRIB = '&copy; OpenStreetMap &copy; CARTO';

  var loading = null;
  var built = {};

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

  function build(panel) {
    var lat = parseFloat(panel.dataset.lat);
    var lon = parseFloat(panel.dataset.lon);
    if (isNaN(lat) || isNaN(lon)) return null;

    var map = L.map(panel, { scrollWheelZoom: false });
    L.tileLayer(TILES, { attribution: ATTRIB, maxZoom: 19 }).addTo(map);

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
    return map;
  }

  document.addEventListener('click', function (ev) {
    var btn = ev.target.closest('[data-mappoint-toggle]');
    if (!btn) return;
    ev.preventDefault();
    // List rows are often click-through to the record; opening a map must not
    // also navigate away from the list.
    ev.stopPropagation();

    var panel = document.getElementById(btn.dataset.mappointToggle);
    if (!panel) return;

    var wrap = panel.closest('.mpt__panel') || panel;
    var showing = wrap.hasAttribute('hidden');
    if (showing) { wrap.removeAttribute('hidden'); } else { wrap.setAttribute('hidden', ''); }
    btn.classList.toggle('mpt__btn--on', showing);
    btn.setAttribute('aria-expanded', showing ? 'true' : 'false');
    if (!showing) return;

    var key = panel.id;
    if (built[key]) {
      built[key].invalidateSize();
      return;
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
