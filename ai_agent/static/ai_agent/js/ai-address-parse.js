/**
 * EzzyAIParse — Global AI Address Parse Utility
 *
 * Smart flow:
 *   1. Gather existing data from page (zone, street, building, address, lat/lng)
 *   2. If zone+street+building known → QNAS API for precise coordinates
 *   3. Otherwise → AI parse to extract zone/street/building from address text
 *   4. After AI parse, call QNAS with extracted zone/street/building for coords
 *   5. If lat/lng already exists → compare with QNAS result, show both
 *
 * Usage:
 *   // Auto-detect from page context (reads data-* attributes)
 *   EzzyAIParse.parse({ address: '...', zone: 51, street: 203, building: 26, lat: 25.36, lng: 51.42 });
 *
 *   // With order save capability
 *   EzzyAIParse.parse({ address: '...', orderId: '123', orderNumber: 'ORD-001', showMap: true });
 *
 *   // Bulk parse
 *   EzzyAIParse.parseBulk([{ id: '1', orderNumber: 'ORD-001', address: '...' }]);
 *
 *   // Close modal
 *   EzzyAIParse.close();
 */
(function() {
    'use strict';

    var PARSE_ENDPOINT = '/api/ai-agent/tools/parse-address/';
    var QNAS_BUILDINGS_ENDPOINT = '/api/qnas/get-buildings/';
    var ZONE_NAME_ENDPOINT = '/workforce/ajax/zone-name/';
    var MODAL_ID = 'ezzyAiParseModal';

    // ─── Helpers ───────────────────────────────────────────────

    function _getCSRFToken() {
        var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
        if (match && match[1] && match[1].length === 64) return match[1];

        var meta = document.querySelector('meta[name="csrf-token"]');
        if (meta) {
            var token = meta.getAttribute('content');
            if (token && token.length === 64) return token;
        }

        var input = document.querySelector('[name=csrfmiddlewaretoken]');
        if (input) return input.value;

        if (typeof htmx !== 'undefined' && htmx.config && htmx.config.csrfToken) {
            return htmx.config.csrfToken;
        }

        return '';
    }

    function _escapeHtml(text) {
        if (!text) return '';
        var div = document.createElement('div');
        div.appendChild(document.createTextNode(String(text)));
        return div.innerHTML;
    }

    function _delay(ms) {
        return new Promise(function(resolve) { setTimeout(resolve, ms); });
    }

    function _toInt(v) {
        var n = parseInt(v, 10);
        return isNaN(n) ? null : n;
    }

    function _toFloat(v) {
        var n = parseFloat(v);
        return isNaN(n) ? null : n;
    }

    // ─── Modal Management ──────────────────────────────────────

    var _modalEl = null;

    function _ensureModal() {
        if (_modalEl && document.body.contains(_modalEl)) return _modalEl;

        _modalEl = document.createElement('div');
        _modalEl.id = MODAL_ID;
        _modalEl.className = 'aim__modal';
        _modalEl.innerHTML =
            '<div class="aim__modal-overlay" onclick="EzzyAIParse.close()"></div>' +
            '<div class="aim__modal-content">' +
                '<div class="aim__modal-header">' +
                    '<h5><i class="fa-solid fa-wand-magic-sparkles"></i> <span id="ezzyAiParseTitle">AI Address Parse</span></h5>' +
                    '<button type="button" class="btn-close" onclick="EzzyAIParse.close()"></button>' +
                '</div>' +
                '<div class="aim__modal-body" id="ezzyAiParseBody"></div>' +
                '<div class="aim__modal-footer" id="ezzyAiParseFooter">' +
                    '<button class="btn btn-secondary" onclick="EzzyAIParse.close()">Close</button>' +
                '</div>' +
            '</div>';
        document.body.appendChild(_modalEl);
        return _modalEl;
    }

    function _openModal(title) {
        var modal = _ensureModal();
        document.getElementById('ezzyAiParseTitle').textContent = title || 'AI Address Parse';
        modal.classList.add('show');
        document.body.style.overflow = 'hidden';
    }

    function _closeModal() {
        var modal = document.getElementById(MODAL_ID);
        if (modal) {
            modal.classList.remove('show');
            document.body.style.overflow = '';
        }
    }

    function _setBody(html) {
        var el = document.getElementById('ezzyAiParseBody');
        if (el) el.innerHTML = html;
    }

    function _setFooter(html) {
        var el = document.getElementById('ezzyAiParseFooter');
        if (el) el.innerHTML = html;
    }

    // ─── API Calls ─────────────────────────────────────────────

    function _fetchParse(address) {
        return fetch(PARSE_ENDPOINT, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': _getCSRFToken()
            },
            credentials: 'same-origin',
            body: JSON.stringify({ address: address })
        }).then(function(r) {
            if (!r.ok) throw new Error('Server returned ' + r.status + ' ' + r.statusText);
            return r.json();
        });
    }

    function _fetchQNASBuildings(zone, street) {
        return fetch(QNAS_BUILDINGS_ENDPOINT + '?zone=' + zone + '&street=' + street, {
            method: 'GET',
            credentials: 'include'
        }).then(function(r) {
            if (!r.ok) throw new Error('QNAS returned ' + r.status);
            return r.json();
        });
    }

    function _lookupQNASCoords(zone, street, building) {
        console.log('[QNAS] Looking up Zone', zone, 'Street', street, 'Building', building);

        return _fetchQNASBuildings(zone, street).then(function(buildings) {
            console.log('[QNAS] Response:', buildings);

            if (!Array.isArray(buildings) || buildings.length === 0) {
                console.log('[QNAS] No buildings found or invalid response');
                return null;
            }

            console.log('[QNAS] Found', buildings.length, 'buildings');

            // Try exact building match
            if (building) {
                var bStr = String(building);
                for (var i = 0; i < buildings.length; i++) {
                    console.log('[QNAS] Checking building:', buildings[i].building_number, 'vs', bStr);
                    if (String(buildings[i].building_number || '') === bStr) {
                        console.log('[QNAS] Exact match found!', buildings[i]);
                        return {
                            latitude: parseFloat(buildings[i].x),
                            longitude: parseFloat(buildings[i].y),
                            exact_match: true,
                            source: 'QNAS (exact building ' + bStr + ')'
                        };
                    }
                }
                console.log('[QNAS] No exact building match, using first building');
            }

            // Fallback to first building on street
            var first = buildings[0];
            console.log('[QNAS] First building:', first);
            if (first.x && first.y) {
                console.log('[QNAS] Returning street-level coords:', first.x, first.y);
                return {
                    latitude: parseFloat(first.x),
                    longitude: parseFloat(first.y),
                    exact_match: false,
                    source: 'QNAS (street level)'
                };
            }

            console.log('[QNAS] First building has no coordinates');
            return null;
        }).catch(function(err) {
            console.error('[QNAS] Error:', err);
            return null;
        });
    }

    // ─── Save to Order ─────────────────────────────────────────

    function _getSaveEndpoint(orderId) {
        // Use workforce endpoint for staff, orders endpoint for business users
        if (window.location.pathname.indexOf('/workforce/') === 0) {
            return '/workforce/order/' + orderId + '/update-zone/';
        }
        return '/orders/order/' + orderId + '/update-zone/';
    }

    function _saveToOrder(orderId, data) {
        var btn = document.getElementById('ezzyAiParseSaveBtn');
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin me-2"></i>Saving...';
        }

        var coords = _adjustedCoords.lat !== null ? _adjustedCoords : (data.coordinates || {});
        var lat = coords.latitude || coords.lat || null;
        var lng = coords.longitude || coords.lng || null;

        // Determine accuracy: exact if building known + exact QNAS match, else street, else ai_estimate
        var accuracy = null;
        if (lat && lng) {
            if (data.building_number && data._qnasExactMatch) {
                accuracy = 'exact';
            } else if (data.building_number || data._qnasMatch) {
                accuracy = 'street';
            } else {
                accuracy = 'ai_estimate';
            }
        }

        var csrfToken = _getCSRFToken();
        var endpoint = _getSaveEndpoint(orderId);
        var payload = {
            zone_number: data.zone_number,
            street_number: data.street_number,
            building_number: data.building_number,
            latitude: lat,
            longitude: lng,
            coords_accuracy: accuracy
        };
        console.log('[AIParse Save] endpoint:', endpoint, 'payload:', payload, 'csrf:', csrfToken ? 'present' : 'MISSING');

        return fetch(endpoint, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            credentials: 'same-origin',
            redirect: 'error',
            body: JSON.stringify(payload)
        }).then(function(r) {
            console.log('[AIParse Save] response status:', r.status, 'type:', r.type, 'url:', r.url);
            if (!r.ok) {
                return r.text().then(function(text) {
                    console.log('[AIParse Save] error body:', text.substring(0, 200));
                    try {
                        var json = JSON.parse(text);
                        throw new Error(json.error || ('Server error: HTTP ' + r.status));
                    } catch(e) {
                        if (e.message && e.message.indexOf('Server error') === 0) throw e;
                        throw new Error('Server error: HTTP ' + r.status);
                    }
                });
            }
            return r.json();
        }).then(function(resp) {
            console.log('[AIParse Save] response:', resp);
            if (resp.success) {
                if (btn) {
                    btn.innerHTML = '<i class="fa-solid fa-check me-2"></i>Saved!';
                    btn.classList.remove('btn-info');
                    btn.classList.add('btn-success');
                }
                setTimeout(function() { window.location.reload(); }, 1500);
            } else {
                throw new Error(resp.error || 'Failed to save');
            }
        }).catch(function(err) {
            console.error('[AIParse Save] error:', err);
            var msg = err.message || 'Unknown error';
            // Detect redirect block (login redirect)
            if (err instanceof TypeError && err.message.indexOf('redirect') !== -1) {
                msg = 'Session expired — please refresh and try again';
            }
            if (btn) {
                btn.disabled = false;
                btn.classList.remove('btn-info');
                btn.classList.add('btn-danger');
                btn.innerHTML = '<i class="fa-solid fa-triangle-exclamation me-2"></i>' + msg;
            }
        });
    }

    // ─── Silent Save (for bulk operations) ────────────────────

    function _saveToOrderSilent(orderId, data) {
        var coords = data.coordinates || {};
        var lat = coords.latitude || null;
        var lng = coords.longitude || null;

        var accuracy = null;
        if (lat && lng) {
            if (data.building_number && data._qnasExactMatch) {
                accuracy = 'exact';
            } else if (data.building_number || data._qnasMatch) {
                accuracy = 'street';
            } else {
                accuracy = 'ai_estimate';
            }
        }

        var csrfToken = _getCSRFToken();
        var endpoint = _getSaveEndpoint(orderId);
        var payload = {
            zone_number: data.zone_number,
            street_number: data.street_number,
            building_number: data.building_number,
            latitude: lat,
            longitude: lng,
            coords_accuracy: accuracy
        };

        return fetch(endpoint, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            credentials: 'same-origin',
            body: JSON.stringify(payload)
        }).then(function(r) {
            if (!r.ok) throw new Error('HTTP ' + r.status);
            return r.json();
        }).then(function(resp) {
            if (!resp.success) throw new Error(resp.error || 'Save failed');
            return resp;
        });
    }

    // ─── Leaflet Map ───────────────────────────────────────────

    var _adjustedCoords = { lat: null, lng: null };

    function _initMap(lat, lng, title) {
        var mapEl = document.getElementById('ezzyAiParseMap');
        if (!mapEl) return;

        if (typeof L === 'undefined') {
            var css = document.createElement('link');
            css.rel = 'stylesheet';
            css.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
            document.head.appendChild(css);

            var js = document.createElement('script');
            js.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
            js.onload = function() { _createMap(lat, lng, title); };
            document.body.appendChild(js);
        } else {
            _createMap(lat, lng, title);
        }
    }

    function _createMap(lat, lng, title) {
        var mapEl = document.getElementById('ezzyAiParseMap');
        if (!mapEl || mapEl._leaflet_id) return;

        _adjustedCoords.lat = lat;
        _adjustedCoords.lng = lng;

        var map = L.map('ezzyAiParseMap').setView([lat, lng], 14);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; OpenStreetMap',
            maxZoom: 19
        }).addTo(map);

        var icon = L.divIcon({
            className: 'custom-marker',
            html: '<div style="background:#17a2b8;width:28px;height:28px;border-radius:50% 50% 50% 0;transform:rotate(-45deg);border:3px solid white;box-shadow:0 2px 8px rgba(23,162,184,0.5);cursor:grab;">' +
                  '<div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%) rotate(45deg);color:white;font-size:12px;"><i class="fa-solid fa-location-dot"></i></div></div>',
            iconSize: [28, 28],
            iconAnchor: [14, 28],
            popupAnchor: [0, -28]
        });

        var marker = L.marker([lat, lng], { icon: icon, draggable: true }).addTo(map);
        marker.bindPopup(
            '<strong>' + _escapeHtml(title) + '</strong><br>' +
            '<span class="text-info"><i class="fa-solid fa-arrows-up-down-left-right me-1"></i>Drag to adjust</span><br>' +
            'Lat: ' + lat.toFixed(6) + '<br>Lng: ' + lng.toFixed(6)
        ).openPopup();

        marker.on('dragend', function() {
            var pos = marker.getLatLng();
            _adjustedCoords.lat = pos.lat;
            _adjustedCoords.lng = pos.lng;

            marker.setPopupContent(
                '<strong>' + _escapeHtml(title) + '</strong><br>' +
                '<span class="text-info"><i class="fa-solid fa-arrows-up-down-left-right me-1"></i>Drag to adjust</span><br>' +
                'Lat: ' + pos.lat.toFixed(6) + '<br>Lng: ' + pos.lng.toFixed(6)
            ).openPopup();

            var coordsEl = document.getElementById('ezzyAiParseCoordsText');
            if (coordsEl) {
                coordsEl.innerHTML = pos.lat.toFixed(6) + ', ' + pos.lng.toFixed(6) +
                    ' <span class="badge bg-warning text-dark ms-1">Adjusted</span>';
            }

            var saveBtn = document.getElementById('ezzyAiParseSaveBtn');
            if (saveBtn && !saveBtn.textContent.includes('Adjusted')) {
                saveBtn.innerHTML = saveBtn.innerHTML.replace('Save Zone', 'Save Zone (Adjusted)');
            }
        });

        setTimeout(function() { map.invalidateSize(); }, 200);
    }

    // ─── Result Rendering ──────────────────────────────────────

    function _renderResultCard(result, opts) {
        opts = opts || {};
        var coords = result.coordinates || {};
        var conf = Math.round((result.confidence || 0) * 100);
        var confClass = conf > 70 ? 'success' : conf > 40 ? 'warning' : 'secondary';

        var html = '<div class="aim__result-card">';
        html += '<div class="aim__result-card-header">';
        html += '<i class="fa-solid fa-location-dot"></i>';
        html += '<strong>Parsed Address</strong>';
        html += '<span class="ms-auto badge bg-' + confClass + '">' + conf + '% confidence</span>';
        html += '</div>';

        html += '<div class="aim__result-grid">';
        var fields = [
            ['Zone', result.zone_number],
            ['Zone Name', result.zone_name],
            ['Street', result.street_number],
            ['Building', result.building_number],
            ['Unit', result.unit_number],
            ['Area', result.area_name]
        ];
        for (var i = 0; i < fields.length; i++) {
            var val = fields[i][1];
            html += '<div class="aim__result-item">';
            html += '<span class="label">' + fields[i][0] + '</span>';
            html += '<span class="value' + (fields[i][0] === 'Zone' && val ? ' success' : '') + '">' + (val != null && val !== '' ? _escapeHtml(String(val)) : '-') + '</span>';
            html += '</div>';
        }
        html += '</div>';

        // QNAS coordinates section
        if (opts.qnasCoords) {
            var qc = opts.qnasCoords;
            html += '<div class="mt-3 p-2 rounded" style="background:rgba(16,185,129,0.08);border:1px solid rgba(16,185,129,0.2);">';
            html += '<strong class="small text-success"><i class="fa-solid fa-map-pin me-1"></i>QNAS Coordinates (' + _escapeHtml(qc.source) + '):</strong>';
            html += '<p class="mb-1 small" id="ezzyAiParseCoordsText"><strong>' + qc.latitude.toFixed(6) + ', ' + qc.longitude.toFixed(6) + '</strong></p>';

            // Show comparison with existing coordinates
            if (opts.existingLat && opts.existingLng) {
                var dist = _haversineDistance(opts.existingLat, opts.existingLng, qc.latitude, qc.longitude);
                var distStr = dist < 1000 ? Math.round(dist) + 'm' : (dist / 1000).toFixed(1) + 'km';
                var distClass = dist < 100 ? 'success' : dist < 500 ? 'warning' : 'danger';
                html += '<div class="small mt-1">';
                html += '<i class="fa-solid fa-arrows-left-right me-1"></i>';
                html += 'Existing: ' + opts.existingLat.toFixed(6) + ', ' + opts.existingLng.toFixed(6);
                html += ' <span class="badge bg-' + distClass + '">' + distStr + ' diff</span>';
                if (dist > 100) {
                    html += ' <span class="text-warning"><i class="fa-solid fa-triangle-exclamation me-1"></i>QNAS result differs from current</span>';
                }
                html += '</div>';
            } else {
                // No existing coordinates - show that QNAS found new ones
                html += '<div class="small mt-1 text-success">';
                html += '<i class="fa-solid fa-check-circle me-1"></i>New coordinates found from QNAS';
                html += '</div>';
            }
            html += '</div>';
        }

        // Google Maps link found in text
        if (result.location_link) {
            html += '<div class="mt-2 p-2 rounded" style="background:rgba(66,133,244,0.08);border:1px solid rgba(66,133,244,0.2);">';
            html += '<strong class="small text-primary"><i class="fa-solid fa-link me-1"></i>Google Maps Link:</strong> ';
            html += '<a href="' + _escapeHtml(result.location_link) + '" target="_blank" class="small">' + _escapeHtml(result.location_link.substring(0, 80)) + (result.location_link.length > 80 ? '...' : '') + '</a>';
            html += '</div>';
        }

        // Regular coordinates (from AI parse, no QNAS)
        if (!opts.qnasCoords && coords.latitude && coords.longitude) {
            var srcLabel = result.geocode_source === 'google_maps' ? 'From Google Maps link'
                : result.geocode_source === 'raw_coordinates' ? 'From text coordinates'
                : result.geocode_source === 'zone_center' ? 'Zone center (approximate)'
                : 'Estimated';
            html += '<div class="mt-3">';
            html += '<strong class="small"><i class="fa-solid fa-map-marker-alt text-info me-1"></i>Coordinates (' + srcLabel + '):</strong>';
            html += '<p class="text-muted small mb-2" id="ezzyAiParseCoordsText">' + coords.latitude.toFixed(6) + ', ' + coords.longitude.toFixed(6) + '</p>';

            if (opts.existingLat && opts.existingLng) {
                var dist2 = _haversineDistance(opts.existingLat, opts.existingLng, coords.latitude, coords.longitude);
                var distStr2 = dist2 < 1000 ? Math.round(dist2) + 'm' : (dist2 / 1000).toFixed(1) + 'km';
                html += '<div class="small text-muted mb-2"><i class="fa-solid fa-arrows-left-right me-1"></i>Existing: ' + opts.existingLat.toFixed(6) + ', ' + opts.existingLng.toFixed(6) + ' <span class="badge bg-secondary">' + distStr2 + ' diff</span></div>';
            }

            html += '</div>';
        }

        // Map
        var finalLat = opts.qnasCoords ? opts.qnasCoords.latitude : (coords.latitude || null);
        var finalLng = opts.qnasCoords ? opts.qnasCoords.longitude : (coords.longitude || null);
        if (finalLat && finalLng) {
            if (opts.showMap) {
                html += '<div class="mt-2"><div id="ezzyAiParseMap" style="height:200px;border-radius:8px;border:2px solid #17a2b8;"></div></div>';
            } else {
                html += '<div class="mt-2"><a href="https://www.google.com/maps?q=' + finalLat + ',' + finalLng + '" target="_blank" class="btn btn-sm btn-outline-dark"><i class="fa-solid fa-map-location-dot me-1"></i>View on Google Maps</a></div>';
            }
        }

        // Landmarks
        if (result.landmarks && result.landmarks.length > 0) {
            html += '<div class="mt-3"><strong class="small">Landmarks:</strong>';
            html += '<p class="text-muted small mb-0">' + _escapeHtml(result.landmarks.join(', ')) + '</p></div>';
        }

        // Original address
        if (result.original_address) {
            html += '<div class="mt-3"><strong class="small">Original Address:</strong>';
            html += '<p class="text-muted small mb-0">' + _escapeHtml(result.original_address) + '</p></div>';
        }

        // Parse notes
        if (result.parse_notes && result.parse_notes.length > 0) {
            html += '<div class="mt-2"><strong class="small">Parse Notes:</strong>';
            html += '<p class="text-muted small mb-0">' + _escapeHtml(result.parse_notes.join(' | ')) + '</p></div>';
        }

        // Save button
        if (opts.orderId) {
            html += '<div class="mt-3 pt-3 border-top">';

            // Determine what we're saving
            var saveLabel = '';
            if (result.zone_number && finalLat) {
                saveLabel = 'Save Zone ' + _escapeHtml(String(result.zone_number)) + ' + Coordinates';
            } else if (result.zone_number) {
                saveLabel = 'Save Zone ' + _escapeHtml(String(result.zone_number));
            } else if (finalLat) {
                saveLabel = 'Update Coordinates Only';
            } else {
                saveLabel = 'Save to Order';
            }

            if (result.zone_number || finalLat) {
                html += '<button type="button" class="btn btn-info w-100" id="ezzyAiParseSaveBtn">';
                html += '<i class="fa-solid fa-save me-2"></i>' + saveLabel;
                html += '</button>';

                // Show what will be saved
                html += '<div class="small text-muted mt-2 text-center">';
                var saveItems = [];
                if (result.zone_number) saveItems.push('Zone ' + result.zone_number);
                if (result.street_number) saveItems.push('Street ' + result.street_number);
                if (result.building_number) saveItems.push('Building ' + result.building_number);
                if (finalLat) saveItems.push('Lat/Lng: ' + finalLat.toFixed(6) + ', ' + finalLng.toFixed(6));
                html += 'Will save: ' + saveItems.join(', ');
                html += '</div>';
            }

            html += '</div>';
        }

        html += '</div>';
        return html;
    }

    // Distance calculation for comparing coordinates
    function _haversineDistance(lat1, lon1, lat2, lon2) {
        var R = 6371000; // meters
        var dLat = (lat2 - lat1) * Math.PI / 180;
        var dLon = (lon2 - lon1) * Math.PI / 180;
        var a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
                Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
                Math.sin(dLon / 2) * Math.sin(dLon / 2);
        return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    }

    // ─── Process State Manager ────────────────────────────────

    var _process = {
        steps: [],
        stepIndex: 0,
        logs: [],

        init: function(steps) {
            this.steps = steps.map(function(s) { return { title: s.title, activeText: s.activeText || 'Processing...', status: 'pending' }; });
            this.stepIndex = 0;
            this.logs = [];
        },

        updateStep: function(index, status) {
            if (index < this.steps.length) {
                this.steps[index].status = status;
                if (status === 'active') this.stepIndex = index;
            }
        },

        addLog: function(message, type) {
            var now = new Date();
            this.logs.push({ time: now.toLocaleTimeString('en-US', { hour12: false }), message: message, type: type || 'info' });
        },

        getProgress: function() {
            var completed = this.steps.filter(function(s) { return s.status === 'completed'; }).length;
            return Math.round((completed / this.steps.length) * 100);
        },

        renderStepsHtml: function() {
            return this.steps.map(function(step, i) {
                var indicatorContent = step.status === 'completed' ? '<i class="fa-solid fa-check"></i>' :
                    step.status === 'error' ? '<i class="fa-solid fa-times"></i>' :
                    step.status === 'active' ? '<i class="fa-solid fa-gear fa-spin"></i>' :
                    String(i + 1);

                var statusContent = step.status === 'active' ? '<span class="aim__step-spinner"></span>' + _escapeHtml(step.activeText) :
                    step.status === 'completed' ? '<i class="fa-solid fa-check text-success me-1"></i>Complete' :
                    step.status === 'error' ? '<i class="fa-solid fa-times text-danger me-1"></i>Error' :
                    'Waiting...';

                return '<div class="aim__process-step ' + (step.status || 'pending') + '">' +
                    '<div class="aim__step-indicator">' + indicatorContent + '</div>' +
                    '<div class="aim__step-content">' +
                        '<div class="aim__step-title">' + _escapeHtml(step.title) + '</div>' +
                        '<div class="aim__step-status">' + statusContent + '</div>' +
                    '</div></div>';
            }).join('');
        },

        renderLogsHtml: function() {
            if (this.logs.length === 0) return '';
            return '<div class="aim__process-details">' +
                '<div class="aim__process-details-header"><span><i class="fa-solid fa-terminal me-1"></i>Process Log</span>' +
                '<span class="text-muted">' + this.logs.length + ' entries</span></div>' +
                '<div class="aim__process-log">' +
                this.logs.map(function(log) {
                    return '<div class="log-entry ' + (log.type || '') + '">' +
                        '<span class="log-time">[' + _escapeHtml(log.time) + ']</span>' +
                        '<span class="log-message">' + _escapeHtml(log.message) + '</span></div>';
                }).join('') +
                '</div></div>';
        },

        render: function() {
            var progress = this.getProgress();
            var isProcessing = this.steps.some(function(s) { return s.status === 'active'; });

            _setBody(
                '<div class="aim__process-container">' +
                    '<div class="aim__process-header">' +
                        '<div class="aim__process-icon' + (progress === 100 ? ' success' : '') + '">' +
                            '<i class="fa-solid ' + (progress === 100 ? 'fa-check' : 'fa-robot') + '"></i>' +
                        '</div>' +
                        '<div class="aim__process-title">' + (isProcessing ? 'AI Processing...' : progress === 100 ? 'Analysis Complete' : 'Preparing...') + '</div>' +
                        '<div class="aim__process-subtitle">' + (isProcessing ? 'Please wait while AI analyzes the data' : progress === 100 ? 'Results ready' : '') + '</div>' +
                    '</div>' +
                    '<div class="aim__progress-container">' +
                        '<div class="aim__progress-bar"><div class="aim__progress-fill" style="width:' + progress + '%"></div></div>' +
                        '<div class="aim__progress-text"><span>Step ' + (this.stepIndex + 1) + ' of ' + this.steps.length + '</span><span>' + progress + '% complete</span></div>' +
                    '</div>' +
                    '<div class="aim__process-steps">' + this.renderStepsHtml() + '</div>' +
                    this.renderLogsHtml() +
                '</div>'
            );
        },

        showResult: function(resultHtml) {
            _setBody(
                '<div class="aim__process-container">' +
                    '<div class="aim__process-header">' +
                        '<div class="aim__process-icon success"><i class="fa-solid fa-check"></i></div>' +
                        '<div class="aim__process-title">Analysis Complete</div>' +
                        '<div class="aim__process-subtitle">Results ready</div>' +
                    '</div>' +
                    '<div class="aim__progress-container">' +
                        '<div class="aim__progress-bar"><div class="aim__progress-fill" style="width:100%"></div></div>' +
                        '<div class="aim__progress-text"><span>Step ' + this.steps.length + ' of ' + this.steps.length + '</span><span>100% complete</span></div>' +
                    '</div>' +
                    '<div class="aim__process-steps">' + this.renderStepsHtml() + '</div>' +
                    this.renderLogsHtml() +
                    '<div class="aim__result-output mt-3">' + resultHtml + '</div>' +
                '</div>'
            );
        },

        showError: function(message) {
            var progress = this.getProgress();
            _setBody(
                '<div class="aim__process-container">' +
                    '<div class="aim__process-header">' +
                        '<div class="aim__process-icon error"><i class="fa-solid fa-times"></i></div>' +
                        '<div class="aim__process-title">Analysis Failed</div>' +
                    '</div>' +
                    '<div class="aim__progress-container">' +
                        '<div class="aim__progress-bar"><div class="aim__progress-fill" style="width:' + progress + '%"></div></div>' +
                        '<div class="aim__progress-text"><span>Failed at step ' + (this.stepIndex + 1) + '</span><span>' + progress + '% complete</span></div>' +
                    '</div>' +
                    '<div class="aim__process-steps">' + this.renderStepsHtml() + '</div>' +
                    '<div class="aim__error-output mt-3"><div class="alert alert-danger mb-0"><i class="fa-solid fa-exclamation-circle me-2"></i>' + _escapeHtml(message) + '</div></div>' +
                '</div>'
            );
        }
    };

    // ─── Smart Single Parse ────────────────────────────────────
    //
    // opts: { address, zone, street, building, lat, lng,
    //         orderId, orderNumber, showMap, title, onResult, onSave }

    async function parse(opts) {
        opts = opts || {};
        var address = (opts.address || '').trim();
        var zone = _toInt(opts.zone);
        var street = _toInt(opts.street);
        var building = _toInt(opts.building);
        var existingLat = _toFloat(opts.lat);
        var existingLng = _toFloat(opts.lng);
        var hasStructured = zone && street;  // Have enough for QNAS lookup
        var hasAddress = address.length > 0;

        if (!hasStructured && !hasAddress) {
            alert('No address data to parse');
            return;
        }

        var title = opts.title || ('Address Parse' + (opts.orderNumber ? ' - ' + opts.orderNumber : ''));

        // Build steps based on what data we have
        var steps = [];
        steps.push({ title: 'Collect Page Data', activeText: 'Gathering existing details...' });

        if (hasStructured) {
            steps.push({ title: 'QNAS Lookup', activeText: 'Looking up Zone ' + zone + ', Street ' + street + (building ? ', Building ' + building : '') + '...' });
        }

        if (hasAddress) {
            steps.push({ title: 'AI Address Parse', activeText: 'Parsing address with AI...' });
        }

        if (!hasStructured && hasAddress) {
            // After AI parse extracts zone/street, do QNAS lookup
            steps.push({ title: 'QNAS Coordinate Lookup', activeText: 'Looking up QNAS coordinates...' });
        }

        if (existingLat && existingLng) {
            steps.push({ title: 'Compare Coordinates', activeText: 'Comparing with existing location...' });
        }

        steps.push({ title: 'Generate Results', activeText: 'Finalizing...' });

        _process.init(steps);
        _openModal(title);
        _setFooter('<button class="btn btn-secondary" onclick="EzzyAIParse.close()">Close</button>');
        _adjustedCoords = { lat: null, lng: null };

        var stepIdx = 0;
        var result = null;
        var qnasCoords = null;

        try {
            // ── Step: Collect Page Data ──
            _process.updateStep(stepIdx, 'active');
            _process.addLog('Collecting existing data from page...');
            _process.render();
            await _delay(250);

            if (zone) _process.addLog('Zone: ' + zone, 'success');
            if (street) _process.addLog('Street: ' + street, 'success');
            if (building) _process.addLog('Building: ' + building, 'success');
            if (hasAddress) _process.addLog('Address: "' + address.substring(0, 60) + (address.length > 60 ? '...' : '') + '"');
            if (existingLat && existingLng) _process.addLog('Existing coords: ' + existingLat.toFixed(6) + ', ' + existingLng.toFixed(6));
            if (!zone && !street) _process.addLog('No zone/street found, will use AI parse', 'info');

            _process.updateStep(stepIdx, 'completed');
            stepIdx++;

            // ── Step: Direct QNAS Lookup (if zone+street known) ──
            if (hasStructured) {
                _process.updateStep(stepIdx, 'active');
                _process.addLog('Querying QNAS for Zone ' + zone + ', Street ' + street + (building ? ', Building ' + building : '') + '...');
                _process.render();

                try {
                    qnasCoords = await _lookupQNASCoords(zone, street, building);
                    console.log('[Parse] QNAS result:', qnasCoords);

                    if (qnasCoords) {
                        _process.addLog('✓ QNAS coordinates found: ' + qnasCoords.latitude.toFixed(6) + ', ' + qnasCoords.longitude.toFixed(6) + ' (' + qnasCoords.source + ')', 'success');
                    } else {
                        _process.addLog('⚠ QNAS lookup returned no results (check console for details)', 'info');
                    }
                } catch (err) {
                    console.error('[Parse] QNAS error:', err);
                    _process.addLog('✗ QNAS lookup failed: ' + err.message, 'error');
                    qnasCoords = null;
                }

                _process.updateStep(stepIdx, 'completed');
                stepIdx++;
            }

            // ── Step: AI Address Parse (if address text available) ──
            if (hasAddress) {
                _process.updateStep(stepIdx, 'active');
                _process.addLog('Sending address to AI parser...');
                _process.render();

                var data = await _fetchParse(address);

                if (data.success && data.data) {
                    result = data.data;
                    _process.addLog('AI parsed zone: ' + (result.zone_number || 'Not detected'), result.zone_number ? 'success' : 'info');
                    _process.addLog('AI parsed street: ' + (result.street_number || 'Not detected'), result.street_number ? 'success' : 'info');
                    _process.addLog('AI confidence: ' + Math.round(result.confidence * 100) + '%', result.confidence > 0.7 ? 'success' : 'info');

                    // Merge existing page values for any fields AI couldn't extract
                    if (!result.zone_number && zone) {
                        result.zone_number = zone;
                        _process.addLog('Using existing Zone ' + zone + ' (AI did not detect zone)', 'info');
                    }
                    if (!result.street_number && street) {
                        result.street_number = street;
                        _process.addLog('Using existing Street ' + street + ' (AI did not detect street)', 'info');
                    }
                    if (!result.building_number && building) {
                        result.building_number = building;
                        _process.addLog('Using existing Building ' + building + ' (AI did not detect building)', 'info');
                    }
                } else {
                    _process.addLog('AI parse failed: ' + (data.error || 'Unknown error'), 'error');
                }

                _process.updateStep(stepIdx, 'completed');
                stepIdx++;

                // ── Step: QNAS after AI parse (if didn't have structured data) ──
                if (!hasStructured && result && result.zone_number && result.street_number) {
                    _process.updateStep(stepIdx, 'active');
                    _process.addLog('Using AI-parsed Zone ' + result.zone_number + ', Street ' + result.street_number + ' for QNAS lookup...');
                    _process.render();

                    try {
                        qnasCoords = await _lookupQNASCoords(result.zone_number, result.street_number, result.building_number);
                        console.log('[Parse] QNAS after AI result:', qnasCoords);

                        if (qnasCoords) {
                            _process.addLog('✓ QNAS coordinates found: ' + qnasCoords.latitude.toFixed(6) + ', ' + qnasCoords.longitude.toFixed(6) + ' (' + qnasCoords.source + ')', 'success');
                            // Override AI parse coordinates with QNAS
                            result.coordinates = { latitude: qnasCoords.latitude, longitude: qnasCoords.longitude };
                            result.parse_notes = result.parse_notes || [];
                            result.parse_notes.push('Coordinates from ' + qnasCoords.source);
                        } else {
                            _process.addLog('⚠ QNAS returned no results for AI-parsed location (check console)', 'info');
                        }
                    } catch (err) {
                        console.error('[Parse] QNAS after AI error:', err);
                        _process.addLog('✗ QNAS lookup failed: ' + err.message, 'error');
                    }

                    _process.updateStep(stepIdx, 'completed');
                    stepIdx++;
                } else if (!hasStructured) {
                    // Skip the QNAS step if AI didn't find zone/street
                    _process.updateStep(stepIdx, 'completed');
                    _process.addLog('Skipping QNAS lookup - AI could not extract zone/street');
                    stepIdx++;
                }
            }

            // Build final result object
            if (!result && hasStructured) {
                // No AI parse was done, build a minimal result from structured data
                // Look up zone name from server
                var zoneName = null;
                try {
                    var znResp = await fetch(ZONE_NAME_ENDPOINT + '?zone=' + zone);
                    var znData = await znResp.json();
                    zoneName = znData.zone_name || null;
                } catch (e) { /* ignore */ }

                result = {
                    zone_number: zone,
                    street_number: street,
                    building_number: building,
                    zone_name: zoneName,
                    unit_number: null,
                    area_name: zoneName,
                    landmarks: [],
                    confidence: qnasCoords ? (qnasCoords.exact_match ? 0.95 : 0.75) : 0.5,
                    parse_notes: ['Built from page data (zone/street/building)'],
                    original_address: address || ('Zone ' + zone + (zoneName ? ' (' + zoneName + ')' : '') + ', Street ' + street + (building ? ', Building ' + building : '')),
                    coordinates: qnasCoords ? { latitude: qnasCoords.latitude, longitude: qnasCoords.longitude } : {}
                };
            }

            // Ensure zone_name is populated when we have a zone number but no name
            if (result && result.zone_number && !result.zone_name) {
                try {
                    var znResp2 = await fetch(ZONE_NAME_ENDPOINT + '?zone=' + result.zone_number);
                    var znData2 = await znResp2.json();
                    if (znData2.zone_name) {
                        result.zone_name = znData2.zone_name;
                        if (!result.area_name) result.area_name = znData2.zone_name;
                    }
                } catch (e) { /* ignore */ }
            }

            // ── Step: Compare Coordinates ──
            if (existingLat && existingLng && stepIdx < steps.length - 1) {
                _process.updateStep(stepIdx, 'active');
                _process.render();
                await _delay(200);

                var compareCoords = qnasCoords || (result && result.coordinates) || {};
                if (compareCoords.latitude && compareCoords.longitude) {
                    var dist = _haversineDistance(existingLat, existingLng, compareCoords.latitude, compareCoords.longitude);
                    var distStr = dist < 1000 ? Math.round(dist) + 'm' : (dist / 1000).toFixed(1) + 'km';

                    if (dist < 100) {
                        _process.addLog('Existing coordinates match QNAS result (' + distStr + ' difference)', 'success');
                    } else if (dist < 500) {
                        _process.addLog('Minor difference from existing coords: ' + distStr + ' — QNAS result preferred', 'info');
                    } else {
                        _process.addLog('Significant difference from existing coords: ' + distStr + ' — review recommended', 'error');
                    }
                } else {
                    _process.addLog('No new coordinates to compare with existing', 'info');
                }

                _process.updateStep(stepIdx, 'completed');
                stepIdx++;
            }

            // ── Step: Generate Results ──
            _process.updateStep(stepIdx, 'active');
            _process.render();
            await _delay(200);

            if (result) {
                _process.updateStep(stepIdx, 'completed');
                await _delay(200);

                // If QNAS coords found, override AI coordinates and tag match type
                if (qnasCoords) {
                    result.coordinates = { latitude: qnasCoords.latitude, longitude: qnasCoords.longitude };
                    result._qnasMatch = true;
                    result._qnasExactMatch = qnasCoords.exact_match || false;
                }

                var resultHtml = _renderResultCard(result, {
                    orderId: opts.orderId || '',
                    showMap: opts.showMap || false,
                    qnasCoords: qnasCoords,
                    existingLat: existingLat,
                    existingLng: existingLng
                });
                _process.showResult(resultHtml);

                // Wire save button (zone or coordinates available)
                if (opts.orderId && (result.zone_number || (result.coordinates && result.coordinates.latitude))) {
                    var saveBtn = document.getElementById('ezzyAiParseSaveBtn');
                    if (saveBtn) {
                        saveBtn.addEventListener('click', function() {
                            // Reset error state if retrying
                            saveBtn.classList.remove('btn-danger');
                            saveBtn.classList.add('btn-info');
                            _saveToOrder(opts.orderId, result);
                        });
                    }
                }

                // Initialize map
                var mapLat = qnasCoords ? qnasCoords.latitude : ((result.coordinates || {}).latitude || null);
                var mapLng = qnasCoords ? qnasCoords.longitude : ((result.coordinates || {}).longitude || null);
                if (opts.showMap && mapLat && mapLng) {
                    setTimeout(function() {
                        _initMap(mapLat, mapLng, result.zone_name || 'Zone ' + result.zone_number);
                    }, 100);
                }

                if (typeof opts.onResult === 'function') {
                    opts.onResult(result);
                }
            } else {
                _process.updateStep(stepIdx, 'error');
                _process.showError('No results could be generated. Please provide an address or zone/street details.');
            }

        } catch (err) {
            _process.addLog('Error: ' + err.message, 'error');
            _process.showError(err.message);
        }
    }

    // ─── Bulk Parse ────────────────────────────────────────────

    async function parseBulk(orders, opts) {
        opts = opts || {};
        if (!orders || orders.length === 0) {
            alert('No orders selected');
            return;
        }

        _openModal('Bulk Address Parsing (' + orders.length + ' orders)');
        _setFooter('<button class="btn btn-secondary" onclick="EzzyAIParse.close()">Close</button>');

        var results = [];
        var successCount = 0;
        var errorCount = 0;
        var startTime = Date.now();

        _setBody(
            '<div class="aim__process-container">' +
                '<div class="aim__process-header">' +
                    '<div class="aim__process-icon"><i class="fa-solid fa-robot"></i></div>' +
                    '<div class="aim__process-title">Processing ' + orders.length + ' orders...</div>' +
                    '<div class="aim__process-subtitle">AI Parse + QNAS Lookup</div>' +
                '</div>' +
                '<div class="aim__progress-container">' +
                    '<div class="aim__progress-bar"><div class="aim__progress-fill" id="ezzyBulkProgressFill" style="width:0%"></div></div>' +
                    '<div class="aim__progress-text"><span id="ezzyBulkProgressLabel">0 / ' + orders.length + '</span><span id="ezzyBulkProgressPct">0%</span></div>' +
                '</div>' +
                '<div id="ezzyBulkSteps" class="aim__process-steps"></div>' +
            '</div>'
        );

        // Helper to render a single bulk step row
        function _bulkStepHtml(title, status, statusText) {
            var indicator = status === 'completed' ? '<i class="fa-solid fa-check"></i>' :
                status === 'error' ? '<i class="fa-solid fa-times"></i>' :
                status === 'active' ? '<i class="fa-solid fa-gear fa-spin"></i>' :
                '<i class="fa-solid fa-hourglass text-muted"></i>';
            var stText = status === 'active' ? '<span class="aim__step-spinner"></span>' + _escapeHtml(statusText || 'Processing...') :
                status === 'completed' ? '<i class="fa-solid fa-check text-success me-1"></i>' + _escapeHtml(statusText || 'Done') :
                status === 'error' ? '<i class="fa-solid fa-times text-danger me-1"></i>' + _escapeHtml(statusText || 'Error') :
                _escapeHtml(statusText || 'Waiting...');
            return '<div class="aim__process-step ' + status + '">' +
                '<div class="aim__step-indicator">' + indicator + '</div>' +
                '<div class="aim__step-content">' +
                    '<div class="aim__step-title">' + _escapeHtml(title) + '</div>' +
                    '<div class="aim__step-status">' + stText + '</div>' +
                '</div></div>';
        }

        // Track completed order steps to show history
        var completedStepsHtml = '';

        for (var i = 0; i < orders.length; i++) {
            var order = orders[i];
            var pct = Math.round(((i + 1) / orders.length) * 100);

            var fillEl = document.getElementById('ezzyBulkProgressFill');
            var labelEl = document.getElementById('ezzyBulkProgressLabel');
            var pctEl = document.getElementById('ezzyBulkProgressPct');
            if (fillEl) fillEl.style.width = pct + '%';
            if (labelEl) labelEl.textContent = (i + 1) + ' / ' + orders.length;
            if (pctEl) pctEl.textContent = pct + '%';

            var stepsEl = document.getElementById('ezzyBulkSteps');

            // Sub-steps for current order
            var subSteps = [
                { key: 'parse', title: 'AI Parse', status: 'pending', text: 'Waiting...' },
                { key: 'qnas', title: 'QNAS Lookup', status: 'pending', text: 'Waiting...' },
                { key: 'save', title: 'Save to Order', status: 'pending', text: 'Waiting...' }
            ];

            function _renderBulkSteps() {
                if (!stepsEl) return;
                var currentHtml = '<div class="aim__process-step active" style="border-left-width:4px">' +
                    '<div class="aim__step-indicator"><i class="fa-solid fa-gear fa-spin"></i></div>' +
                    '<div class="aim__step-content">' +
                        '<div class="aim__step-title fw-semibold">' + _escapeHtml(order.orderNumber) + '</div>' +
                        '<div class="aim__step-status small">' +
                            subSteps.map(function(ss) {
                                var icon = ss.status === 'completed' ? '<i class="fa-solid fa-check text-success me-1"></i>' :
                                    ss.status === 'error' ? '<i class="fa-solid fa-times text-danger me-1"></i>' :
                                    ss.status === 'active' ? '<i class="fa-solid fa-gear fa-spin me-1" style="font-size:0.7rem"></i>' :
                                    '<i class="fa-solid fa-circle text-muted me-1" style="font-size:0.4rem;vertical-align:middle"></i>';
                                var cls = ss.status === 'completed' ? 'text-success' :
                                    ss.status === 'error' ? 'text-danger' :
                                    ss.status === 'active' ? '' : 'text-muted';
                                return '<span class="me-3 ' + cls + '">' + icon + _escapeHtml(ss.title) +
                                    (ss.status === 'active' ? ' <span class="text-muted">(' + _escapeHtml(ss.text) + ')</span>' : '') +
                                    '</span>';
                            }).join('') +
                        '</div>' +
                    '</div></div>';
                stepsEl.innerHTML = completedStepsHtml + currentHtml;
                // Auto-scroll to bottom of steps
                stepsEl.scrollTop = stepsEl.scrollHeight;
            }

            // Show initial state
            _renderBulkSteps();

            if (!order.address || !order.address.trim()) {
                subSteps[0].status = 'error'; subSteps[0].text = 'No address';
                subSteps[1].status = 'error'; subSteps[1].text = 'Skipped';
                subSteps[2].status = 'error'; subSteps[2].text = 'Skipped';
                _renderBulkSteps();
                await _delay(200);
                completedStepsHtml += _bulkStepHtml(order.orderNumber, 'error', 'No address');
                results.push({ order: order, success: false, error: 'No address', html: '' });
                errorCount++;
                continue;
            }

            try {
                // Sub-step 1: AI Parse
                subSteps[0].status = 'active'; subSteps[0].text = 'Parsing...';
                _renderBulkSteps();

                var data = await _fetchParse(order.address.trim());
                if (data.success && data.data) {
                    var r = data.data;
                    subSteps[0].status = 'completed';
                    subSteps[0].text = 'Zone ' + (r.zone_number || '?') + ', St ' + (r.street_number || '?') + ' (' + Math.round(r.confidence * 100) + '%)';
                    _renderBulkSteps();

                    // Sub-step 2: QNAS Lookup
                    var qc = null;
                    if (r.zone_number && r.street_number) {
                        subSteps[1].status = 'active'; subSteps[1].text = 'Z' + r.zone_number + ' St' + r.street_number;
                        _renderBulkSteps();

                        qc = await _lookupQNASCoords(r.zone_number, r.street_number, r.building_number);
                        if (qc) {
                            r.coordinates = { latitude: qc.latitude, longitude: qc.longitude };
                            r._qnasMatch = true;
                            r._qnasExactMatch = qc.exact_match || false;
                            subSteps[1].status = 'completed'; subSteps[1].text = 'Coords found';
                        } else {
                            subSteps[1].status = 'completed'; subSteps[1].text = 'No coords';
                        }
                    } else {
                        subSteps[1].status = 'completed'; subSteps[1].text = 'Skipped (no zone/street)';
                    }
                    _renderBulkSteps();

                    // Compute accuracy (same logic as _saveToOrderSilent)
                    var _rLat = (r.coordinates || {}).latitude;
                    var _rLng = (r.coordinates || {}).longitude;
                    var _accuracy = null;
                    if (_rLat && _rLng) {
                        if (r.building_number && r._qnasExactMatch) _accuracy = 'exact';
                        else if (r.building_number || r._qnasMatch)  _accuracy = 'street';
                        else                                          _accuracy = 'ai_estimate';
                    }
                    var _accLabels = { exact: 'Exact', street: 'Street Level', ai_estimate: 'AI Est. 10%' };
                    var _accLabel  = _accuracy ? (_accLabels[_accuracy] || _accuracy) : null;

                    // Sub-step 3: Save to Order
                    var saved = false;
                    if (order.id && r.zone_number) {
                        subSteps[2].status = 'active'; subSteps[2].text = 'Saving...';
                        _renderBulkSteps();

                        try {
                            await _saveToOrderSilent(order.id, r);
                            saved = true;
                            subSteps[2].status = 'completed';
                            subSteps[2].text = 'Saved' + (_accLabel ? ' · ' + _accLabel : '');
                        } catch (saveErr) {
                            console.error('[BulkParse] Save error for ' + order.orderNumber + ':', saveErr);
                            subSteps[2].status = 'error'; subSteps[2].text = 'Save failed';
                        }
                    } else {
                        subSteps[2].status = 'completed'; subSteps[2].text = r.zone_number ? 'No order ID' : 'No zone data';
                    }
                    _renderBulkSteps();
                    await _delay(150);

                    // Mark order completed and add to history
                    var summaryText = 'Z' + (r.zone_number || '?') + ' St' + (r.street_number || '?') +
                        (saved ? ' — Saved' : '') +
                        (_accLabel ? ' · ' + _accLabel : '') +
                        ' (' + Math.round(r.confidence * 100) + '%)';
                    completedStepsHtml += _bulkStepHtml(order.orderNumber, 'completed', summaryText);

                    var _accBadge = _accuracy
                        ? '<span class="task-card__acc-badge task-card__acc-badge--' + _accuracy + ' ms-1">' + _accLabel + '</span>'
                        : '';
                    var cardHtml = '<div class="aim__result-card"><div class="aim__result-card-header">' +
                        '<i class="fa-solid fa-location-dot"></i><strong>' + _escapeHtml(order.orderNumber) + '</strong>' +
                        '<span class="ms-auto">' +
                        (saved ? '<span class="badge bg-success me-1"><i class="fa-solid fa-check me-1"></i>Saved</span>' : '<span class="badge bg-secondary me-1">Not saved</span>') +
                        '<span class="badge bg-' + (r.confidence > 0.7 ? 'success' : 'warning') + '">' + Math.round(r.confidence * 100) + '%</span>' +
                        '</span></div>' +
                        '<div class="aim__result-grid">' +
                        '<div class="aim__result-item"><span class="label">Zone</span><span class="value' + (r.zone_number ? ' success' : '') + '">' + (r.zone_number || '-') + (r.zone_name ? ' (' + _escapeHtml(r.zone_name) + ')' : '') + '</span></div>' +
                        '<div class="aim__result-item"><span class="label">Street</span><span class="value">' + (r.street_number || '-') + '</span></div>' +
                        '<div class="aim__result-item"><span class="label">Building</span><span class="value">' + (r.building_number || '-') + '</span></div>' +
                        '<div class="aim__result-item"><span class="label">Area</span><span class="value">' + _escapeHtml(r.area_name || '-') + '</span></div>' +
                        (_accuracy ? '<div class="aim__result-item"><span class="label">Accuracy</span><span class="value">' + _accBadge + '</span></div>' : '') +
                        '</div>';

                    if (qc) {
                        cardHtml += '<div class="mt-2 small text-success"><i class="fa-solid fa-map-pin me-1"></i>QNAS: ' + qc.latitude.toFixed(6) + ', ' + qc.longitude.toFixed(6) + ' (' + _escapeHtml(qc.source) + ')</div>';
                    }
                    if (r.landmarks && r.landmarks.length > 0) {
                        cardHtml += '<div class="mt-2"><strong class="small">Landmarks:</strong> <span class="text-muted small">' + _escapeHtml(r.landmarks.join(', ')) + '</span></div>';
                    }
                    cardHtml += '<div class="mt-2"><strong class="small">Original:</strong> <span class="text-muted small">' + _escapeHtml(r.original_address || order.address) + '</span></div></div>';
                    results.push({ order: order, success: true, data: r, saved: saved, html: cardHtml });
                    successCount++;
                } else {
                    subSteps[0].status = 'error'; subSteps[0].text = data.error || 'Failed';
                    subSteps[1].status = 'error'; subSteps[1].text = 'Skipped';
                    subSteps[2].status = 'error'; subSteps[2].text = 'Skipped';
                    _renderBulkSteps();
                    await _delay(200);
                    completedStepsHtml += _bulkStepHtml(order.orderNumber, 'error', data.error || 'Parse failed');
                    results.push({ order: order, success: false, error: data.error || 'Failed', html: '' });
                    errorCount++;
                }
            } catch (err) {
                subSteps[0].status = 'error'; subSteps[0].text = err.message;
                _renderBulkSteps();
                await _delay(200);
                completedStepsHtml += _bulkStepHtml(order.orderNumber, 'error', err.message);
                results.push({ order: order, success: false, error: err.message, html: '' });
                errorCount++;
            }
        }

        var elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
        var savedCount = results.filter(function(r) { return r.saved; }).length;
        var allCardsHtml = results.map(function(r) {
            if (r.success) return r.html;
            return '<div class="aim__result-card"><div class="aim__result-card-header">' +
                '<i class="fa-solid fa-triangle-exclamation text-warning"></i>' +
                '<strong>' + _escapeHtml(r.order.orderNumber) + '</strong>' +
                '<span class="ms-auto badge bg-danger">Failed</span></div>' +
                '<p class="text-danger mb-0">' + _escapeHtml(r.error) + '</p></div>';
        }).join('');

        _setBody(
            '<div class="aim__process-container">' +
                '<div class="aim__process-header">' +
                    '<div class="aim__process-icon success"><i class="fa-solid fa-check"></i></div>' +
                    '<div class="aim__process-title">Bulk Parse Complete</div>' +
                    '<div class="aim__process-subtitle">' +
                        successCount + ' parsed, ' + savedCount + ' saved, ' + errorCount + ' failed in ' + elapsed + 's' +
                    '</div>' +
                '</div>' +
                '<div class="aim__progress-container">' +
                    '<div class="aim__progress-bar"><div class="aim__progress-fill" style="width:100%"></div></div>' +
                '</div>' +
                '<div class="mt-3">' + allCardsHtml + '</div>' +
            '</div>'
        );

        _setFooter(
            '<button class="btn btn-secondary" onclick="EzzyAIParse.close()">Close</button>' +
            (savedCount > 0 ? ' <button class="btn btn-primary" onclick="window.location.reload()"><i class="fa-solid fa-refresh me-1"></i>Refresh Page</button>' : '')
        );

        if (typeof opts.onComplete === 'function') {
            opts.onComplete(results);
        }
    }

    // ─── Keyboard ──────────────────────────────────────────────

    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') _closeModal();
    });

    // ─── Public API ────────────────────────────────────────────

    window.EzzyAIParse = {
        parse: parse,
        parseBulk: parseBulk,
        close: _closeModal
    };

})();
