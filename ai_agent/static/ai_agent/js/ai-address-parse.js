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
        _modalEl.className = 'ai-modal';
        _modalEl.innerHTML =
            '<div class="ai-modal-overlay" onclick="EzzyAIParse.close()"></div>' +
            '<div class="ai-modal-content">' +
                '<div class="ai-modal-header">' +
                    '<h5><i class="fa-solid fa-wand-magic-sparkles"></i> <span id="ezzyAiParseTitle">AI Address Parse</span></h5>' +
                    '<button type="button" class="btn-close" onclick="EzzyAIParse.close()"></button>' +
                '</div>' +
                '<div class="ai-modal-body" id="ezzyAiParseBody"></div>' +
                '<div class="ai-modal-footer" id="ezzyAiParseFooter">' +
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
        return _fetchQNASBuildings(zone, street).then(function(buildings) {
            if (!Array.isArray(buildings) || buildings.length === 0) return null;

            // Try exact building match
            if (building) {
                var bStr = String(building);
                for (var i = 0; i < buildings.length; i++) {
                    if (String(buildings[i].building_number || '') === bStr) {
                        return {
                            latitude: parseFloat(buildings[i].x),
                            longitude: parseFloat(buildings[i].y),
                            exact_match: true,
                            source: 'QNAS (exact building ' + bStr + ')'
                        };
                    }
                }
            }

            // Fallback to first building on street
            var first = buildings[0];
            if (first.x && first.y) {
                return {
                    latitude: parseFloat(first.x),
                    longitude: parseFloat(first.y),
                    exact_match: false,
                    source: 'QNAS (street level)'
                };
            }

            return null;
        }).catch(function() {
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

        return fetch(_getSaveEndpoint(orderId), {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': _getCSRFToken()
            },
            credentials: 'same-origin',
            body: JSON.stringify({
                zone_number: data.zone_number,
                street_number: data.street_number,
                building_number: data.building_number,
                latitude: coords.latitude || coords.lat || null,
                longitude: coords.longitude || coords.lng || null
            })
        }).then(function(r) {
            if (!r.ok) throw new Error('HTTP ' + r.status + ': ' + r.statusText);
            return r.json();
        }).then(function(resp) {
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
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = '<i class="fa-solid fa-save me-2"></i>Save to Order';
                btn.classList.add('btn-danger');
                setTimeout(function() { btn.classList.remove('btn-danger'); }, 2000);
            }
            alert('Error saving: ' + err.message);
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

        var html = '<div class="ai-result-card">';
        html += '<div class="ai-result-card-header">';
        html += '<i class="fa-solid fa-location-dot"></i>';
        html += '<strong>Parsed Address</strong>';
        html += '<span class="ms-auto badge bg-' + confClass + '">' + conf + '% confidence</span>';
        html += '</div>';

        html += '<div class="ai-result-grid">';
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
            html += '<div class="ai-result-item">';
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
            html += '<p class="mb-1 small" id="ezzyAiParseCoordsText">' + qc.latitude.toFixed(6) + ', ' + qc.longitude.toFixed(6) + '</p>';

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
            }
            html += '</div>';
        }

        // Regular coordinates (from AI parse, no QNAS)
        if (!opts.qnasCoords && coords.latitude && coords.longitude) {
            html += '<div class="mt-3">';
            html += '<strong class="small"><i class="fa-solid fa-map-marker-alt text-info me-1"></i>Coordinates:</strong>';
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
        if (opts.orderId && result.zone_number) {
            html += '<div class="mt-3 pt-3 border-top">';
            html += '<button type="button" class="btn btn-info w-100" id="ezzyAiParseSaveBtn">';
            html += '<i class="fa-solid fa-save me-2"></i>Save Zone ' + _escapeHtml(String(result.zone_number));
            html += (finalLat ? ' with Coordinates' : '') + ' to Order';
            html += '</button>';
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

                var statusContent = step.status === 'active' ? '<span class="ai-step-spinner"></span>' + _escapeHtml(step.activeText) :
                    step.status === 'completed' ? '<i class="fa-solid fa-check text-success me-1"></i>Complete' :
                    step.status === 'error' ? '<i class="fa-solid fa-times text-danger me-1"></i>Error' :
                    'Waiting...';

                return '<div class="ai-process-step ' + (step.status || 'pending') + '">' +
                    '<div class="ai-step-indicator">' + indicatorContent + '</div>' +
                    '<div class="ai-step-content">' +
                        '<div class="ai-step-title">' + _escapeHtml(step.title) + '</div>' +
                        '<div class="ai-step-status">' + statusContent + '</div>' +
                    '</div></div>';
            }).join('');
        },

        renderLogsHtml: function() {
            if (this.logs.length === 0) return '';
            return '<div class="ai-process-details">' +
                '<div class="ai-process-details-header"><span><i class="fa-solid fa-terminal me-1"></i>Process Log</span>' +
                '<span class="text-muted">' + this.logs.length + ' entries</span></div>' +
                '<div class="ai-process-log">' +
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
                '<div class="ai-process-container">' +
                    '<div class="ai-process-header">' +
                        '<div class="ai-process-icon' + (progress === 100 ? ' success' : '') + '">' +
                            '<i class="fa-solid ' + (progress === 100 ? 'fa-check' : 'fa-robot') + '"></i>' +
                        '</div>' +
                        '<div class="ai-process-title">' + (isProcessing ? 'AI Processing...' : progress === 100 ? 'Analysis Complete' : 'Preparing...') + '</div>' +
                        '<div class="ai-process-subtitle">' + (isProcessing ? 'Please wait while AI analyzes the data' : progress === 100 ? 'Results ready' : '') + '</div>' +
                    '</div>' +
                    '<div class="ai-progress-container">' +
                        '<div class="ai-progress-bar"><div class="ai-progress-fill" style="width:' + progress + '%"></div></div>' +
                        '<div class="ai-progress-text"><span>Step ' + (this.stepIndex + 1) + ' of ' + this.steps.length + '</span><span>' + progress + '% complete</span></div>' +
                    '</div>' +
                    '<div class="ai-process-steps">' + this.renderStepsHtml() + '</div>' +
                    this.renderLogsHtml() +
                '</div>'
            );
        },

        showResult: function(resultHtml) {
            _setBody(
                '<div class="ai-process-container">' +
                    '<div class="ai-process-header">' +
                        '<div class="ai-process-icon success"><i class="fa-solid fa-check"></i></div>' +
                        '<div class="ai-process-title">Analysis Complete</div>' +
                        '<div class="ai-process-subtitle">Results ready</div>' +
                    '</div>' +
                    '<div class="ai-progress-container">' +
                        '<div class="ai-progress-bar"><div class="ai-progress-fill" style="width:100%"></div></div>' +
                        '<div class="ai-progress-text"><span>Step ' + this.steps.length + ' of ' + this.steps.length + '</span><span>100% complete</span></div>' +
                    '</div>' +
                    '<div class="ai-process-steps">' + this.renderStepsHtml() + '</div>' +
                    '<div class="ai-result-output mt-3">' + resultHtml + '</div>' +
                '</div>'
            );
        },

        showError: function(message) {
            var progress = this.getProgress();
            _setBody(
                '<div class="ai-process-container">' +
                    '<div class="ai-process-header">' +
                        '<div class="ai-process-icon error"><i class="fa-solid fa-times"></i></div>' +
                        '<div class="ai-process-title">Analysis Failed</div>' +
                    '</div>' +
                    '<div class="ai-progress-container">' +
                        '<div class="ai-progress-bar"><div class="ai-progress-fill" style="width:' + progress + '%"></div></div>' +
                        '<div class="ai-progress-text"><span>Failed at step ' + (this.stepIndex + 1) + '</span><span>' + progress + '% complete</span></div>' +
                    '</div>' +
                    '<div class="ai-process-steps">' + this.renderStepsHtml() + '</div>' +
                    '<div class="ai-error-output mt-3"><div class="alert alert-danger mb-0"><i class="fa-solid fa-exclamation-circle me-2"></i>' + _escapeHtml(message) + '</div></div>' +
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

                qnasCoords = await _lookupQNASCoords(zone, street, building);

                if (qnasCoords) {
                    _process.addLog('QNAS coordinates found: ' + qnasCoords.latitude.toFixed(6) + ', ' + qnasCoords.longitude.toFixed(6) + ' (' + qnasCoords.source + ')', 'success');
                } else {
                    _process.addLog('QNAS lookup returned no results', 'info');
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

                    qnasCoords = await _lookupQNASCoords(result.zone_number, result.street_number, result.building_number);

                    if (qnasCoords) {
                        _process.addLog('QNAS coordinates found: ' + qnasCoords.latitude.toFixed(6) + ', ' + qnasCoords.longitude.toFixed(6) + ' (' + qnasCoords.source + ')', 'success');
                        // Override AI parse coordinates with QNAS
                        result.coordinates = { latitude: qnasCoords.latitude, longitude: qnasCoords.longitude };
                        result.parse_notes = result.parse_notes || [];
                        result.parse_notes.push('Coordinates from ' + qnasCoords.source);
                    } else {
                        _process.addLog('QNAS returned no results for AI-parsed location', 'info');
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
                result = {
                    zone_number: zone,
                    street_number: street,
                    building_number: building,
                    zone_name: null,
                    unit_number: null,
                    area_name: null,
                    landmarks: [],
                    confidence: qnasCoords ? (qnasCoords.exact_match ? 0.95 : 0.75) : 0.5,
                    parse_notes: ['Built from page data (zone/street/building)'],
                    original_address: address || ('Zone ' + zone + ', Street ' + street + (building ? ', Building ' + building : '')),
                    coordinates: qnasCoords ? { latitude: qnasCoords.latitude, longitude: qnasCoords.longitude } : {}
                };
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

                // If QNAS coords found, override AI coordinates
                if (qnasCoords) {
                    result.coordinates = { latitude: qnasCoords.latitude, longitude: qnasCoords.longitude };
                }

                var resultHtml = _renderResultCard(result, {
                    orderId: opts.orderId || '',
                    showMap: opts.showMap || false,
                    qnasCoords: qnasCoords,
                    existingLat: existingLat,
                    existingLng: existingLng
                });
                _process.showResult(resultHtml);

                // Wire save button
                if (opts.orderId && result.zone_number) {
                    var saveBtn = document.getElementById('ezzyAiParseSaveBtn');
                    if (saveBtn) {
                        saveBtn.addEventListener('click', function() {
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
            '<div class="ai-process-container">' +
                '<div class="ai-process-header">' +
                    '<div class="ai-process-icon"><i class="fa-solid fa-robot"></i></div>' +
                    '<div class="ai-process-title">Processing ' + orders.length + ' orders...</div>' +
                    '<div class="ai-process-subtitle">AI Parse + QNAS Lookup</div>' +
                '</div>' +
                '<div class="ai-progress-container">' +
                    '<div class="ai-progress-bar"><div class="ai-progress-fill" id="ezzyBulkProgressFill" style="width:0%"></div></div>' +
                    '<div class="ai-progress-text"><span id="ezzyBulkProgressLabel">0 / ' + orders.length + '</span><span id="ezzyBulkProgressPct">0%</span></div>' +
                '</div>' +
                '<div id="ezzyBulkSteps" class="ai-process-steps"></div>' +
            '</div>'
        );

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
            if (stepsEl) {
                stepsEl.innerHTML = '<div class="ai-process-step active">' +
                    '<div class="ai-step-indicator"><i class="fa-solid fa-gear fa-spin"></i></div>' +
                    '<div class="ai-step-content">' +
                        '<div class="ai-step-title">' + _escapeHtml(order.orderNumber) + '</div>' +
                        '<div class="ai-step-status"><span class="ai-step-spinner"></span>Parsing address...</div>' +
                    '</div></div>';
            }

            if (!order.address || !order.address.trim()) {
                results.push({ order: order, success: false, error: 'No address', html: '' });
                errorCount++;
                continue;
            }

            try {
                // AI Parse
                var data = await _fetchParse(order.address.trim());
                if (data.success && data.data) {
                    var r = data.data;

                    // Try QNAS for coordinates if zone+street found
                    var qc = null;
                    if (r.zone_number && r.street_number) {
                        qc = await _lookupQNASCoords(r.zone_number, r.street_number, r.building_number);
                        if (qc) {
                            r.coordinates = { latitude: qc.latitude, longitude: qc.longitude };
                        }
                    }

                    var cardHtml = '<div class="ai-result-card"><div class="ai-result-card-header">' +
                        '<i class="fa-solid fa-location-dot"></i><strong>' + _escapeHtml(order.orderNumber) + '</strong>' +
                        '<span class="ms-auto badge bg-' + (r.confidence > 0.7 ? 'success' : 'warning') + '">' + Math.round(r.confidence * 100) + '%</span></div>' +
                        '<div class="ai-result-grid">' +
                        '<div class="ai-result-item"><span class="label">Zone</span><span class="value' + (r.zone_number ? ' success' : '') + '">' + (r.zone_number || '-') + '</span></div>' +
                        '<div class="ai-result-item"><span class="label">Street</span><span class="value">' + (r.street_number || '-') + '</span></div>' +
                        '<div class="ai-result-item"><span class="label">Building</span><span class="value">' + (r.building_number || '-') + '</span></div>' +
                        '<div class="ai-result-item"><span class="label">Area</span><span class="value">' + _escapeHtml(r.area_name || '-') + '</span></div>' +
                        '</div>';

                    // Show QNAS result
                    if (qc) {
                        cardHtml += '<div class="mt-2 small text-success"><i class="fa-solid fa-map-pin me-1"></i>QNAS: ' + qc.latitude.toFixed(6) + ', ' + qc.longitude.toFixed(6) + ' (' + _escapeHtml(qc.source) + ')</div>';
                    }

                    if (r.landmarks && r.landmarks.length > 0) {
                        cardHtml += '<div class="mt-2"><strong class="small">Landmarks:</strong> <span class="text-muted small">' + _escapeHtml(r.landmarks.join(', ')) + '</span></div>';
                    }
                    cardHtml += '<div class="mt-2"><strong class="small">Original:</strong> <span class="text-muted small">' + _escapeHtml(r.original_address || order.address) + '</span></div></div>';
                    results.push({ order: order, success: true, data: r, html: cardHtml });
                    successCount++;
                } else {
                    results.push({ order: order, success: false, error: data.error || 'Failed', html: '' });
                    errorCount++;
                }
            } catch (err) {
                results.push({ order: order, success: false, error: err.message, html: '' });
                errorCount++;
            }
        }

        var elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
        var allCardsHtml = results.map(function(r) {
            if (r.success) return r.html;
            return '<div class="ai-result-card"><div class="ai-result-card-header">' +
                '<i class="fa-solid fa-triangle-exclamation text-warning"></i>' +
                '<strong>' + _escapeHtml(r.order.orderNumber) + '</strong>' +
                '<span class="ms-auto badge bg-danger">Failed</span></div>' +
                '<p class="text-danger mb-0">' + _escapeHtml(r.error) + '</p></div>';
        }).join('');

        _setBody(
            '<div class="ai-process-container">' +
                '<div class="ai-process-header">' +
                    '<div class="ai-process-icon success"><i class="fa-solid fa-check"></i></div>' +
                    '<div class="ai-process-title">Bulk Parse Complete</div>' +
                    '<div class="ai-process-subtitle">' + successCount + ' succeeded, ' + errorCount + ' failed in ' + elapsed + 's</div>' +
                '</div>' +
                '<div class="ai-progress-container">' +
                    '<div class="ai-progress-bar"><div class="ai-progress-fill" style="width:100%"></div></div>' +
                '</div>' +
                '<div class="mt-3">' + allCardsHtml + '</div>' +
            '</div>'
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
