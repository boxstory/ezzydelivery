/* Purpose: Add an English-labelled basemap to a Leaflet map (Qatar OSM raster tiles are Arabic-only).
   Used by: workforce/templates/workforce/tasks_live_map.html
   Notes: Loads MapLibre GL + the Leaflet bridge on demand, rewrites every label in the OpenFreeMap
          "liberty" style to name:latin, and falls back to the plain OSM raster layer if anything
          (no WebGL, CDN down, style fetch failed) stops the vector basemap from rendering. */

(function (window) {
    'use strict';

    var MAPLIBRE_JS = 'https://unpkg.com/maplibre-gl@5.24.0/dist/maplibre-gl.js';
    var MAPLIBRE_CSS = 'https://unpkg.com/maplibre-gl@5.24.0/dist/maplibre-gl.css';
    var BRIDGE_JS = 'https://unpkg.com/@maplibre/maplibre-gl-leaflet@0.1.4/leaflet-maplibre-gl.js';
    var STYLE_URL = 'https://tiles.openfreemap.org/styles/liberty';
    var RASTER_URL = 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png';
    var MAX_ZOOM = 19;

    // One shared promise per page load: two maps on the same page must not fetch the
    // 1 MB MapLibre bundle twice.
    var libsPromise = null;
    var stylePromise = null;

    function loadCss(href) {
        if (document.querySelector('link[href="' + href + '"]')) return;
        var link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = href;
        document.head.appendChild(link);
    }

    function loadScript(src) {
        return new Promise(function (resolve, reject) {
            var existing = document.querySelector('script[data-basemap-src="' + src + '"]');
            if (existing) {
                if (existing.dataset.loaded === '1') { resolve(); return; }
                existing.addEventListener('load', function () { resolve(); });
                existing.addEventListener('error', function () { reject(new Error(src)); });
                return;
            }
            var el = document.createElement('script');
            el.src = src;
            el.dataset.basemapSrc = src;
            el.onload = function () { el.dataset.loaded = '1'; resolve(); };
            el.onerror = function () { reject(new Error(src)); };
            document.head.appendChild(el);
        });
    }

    function hasWebgl() {
        try {
            var canvas = document.createElement('canvas');
            return !!(window.WebGLRenderingContext &&
                (canvas.getContext('webgl') || canvas.getContext('experimental-webgl')));
        } catch (e) {
            return false;
        }
    }

    function loadLibs() {
        if (!libsPromise) {
            loadCss(MAPLIBRE_CSS);
            // The bridge registers L.maplibreGL, so MapLibre and Leaflet must both exist first.
            libsPromise = loadScript(MAPLIBRE_JS).then(function () {
                return loadScript(BRIDGE_JS);
            });
        }
        return libsPromise;
    }

    /* The Liberty style prints "Latin newline Arabic" for every named feature. Every text-field that
       reads a name is collapsed to the Latin form so the map is English-only; shield layers read
       `ref`, not `name`, and are left alone. */
    function toEnglish(style) {
        (style.layers || []).forEach(function (layer) {
            var field = layer.layout && layer.layout['text-field'];
            if (!field) return;
            if (JSON.stringify(field).indexOf('name') === -1) return;
            layer.layout['text-field'] = [
                'coalesce',
                ['get', 'name:en'],
                ['get', 'name:latin'],
                ['get', 'name']
            ];
        });
        return style;
    }

    function loadStyle() {
        if (!stylePromise) {
            stylePromise = fetch(STYLE_URL)
                .then(function (r) {
                    if (!r.ok) throw new Error('style ' + r.status);
                    return r.json();
                })
                .then(toEnglish);
        }
        return stylePromise;
    }

    function addRaster(map) {
        return L.tileLayer(RASTER_URL, { maxZoom: MAX_ZOOM }).addTo(map);
    }

    /**
     * Add the English vector basemap to `map`, falling back to the OSM raster layer.
     * Returns a promise resolving to the layer that ended up on the map.
     */
    function englishBasemap(map) {
        if (!hasWebgl()) return Promise.resolve(addRaster(map));

        return loadLibs()
            .then(loadStyle)
            .then(function (style) {
                if (!L.maplibreGL) throw new Error('bridge missing');
                var layer = L.maplibreGL({ style: style, attribution: '' });
                layer.addTo(map);
                // A GL layer advertises no maxZoom, so without this the map zooms past what
                // MapLibre will render and the canvas goes blank.
                if (map.getMaxZoom() === Infinity) map.setMaxZoom(MAX_ZOOM);
                return layer;
            })
            .catch(function (err) {
                if (window.console) console.warn('English basemap unavailable, using OSM tiles:', err);
                return addRaster(map);
            });
    }

    window.wfEnglishBasemap = englishBasemap;
})(window);
