/**
 * QNAS Verification Utility
 * Verifies if zone/street/building exists in QNAS and shows coordinates
 */

/**
 * Save QNAS status to the order via the update-coords endpoint
 * @param {number} orderId - Order ID to update
 * @param {string} status - 'verified', 'not_found', or 'error'
 */
function _saveQnasStatus(orderId, status) {
    if (!orderId) return;
    try {
        var csrfToken = _getCsrfToken();
        fetch(window.location.origin + '/workforce/orders/' + orderId + '/update-coords/', {
            method: 'POST',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
            body: JSON.stringify({ qnas_status: status })
        });
        // Update any visible status badges on the page
        _updateQnasStatusBadges(orderId, status);
    } catch (e) {
        console.error('[QNAS] Failed to save qnas_status:', e);
    }
}

/**
 * Update all QNAS status badges on the page for a given order
 */
function _updateQnasStatusBadges(orderId, status) {
    var badges = document.querySelectorAll('[data-qnas-badge="' + orderId + '"]');
    var config = {
        verified:  { cls: 'qnas-verify__status--verified',   icon: 'fa-check-circle',        label: 'Verified' },
        not_found: { cls: 'qnas-verify__status--not_found',  icon: 'fa-exclamation-triangle', label: 'Not Found' },
        error:     { cls: 'qnas-verify__status--error',      icon: 'fa-times-circle',         label: 'Error' },
    };
    var c = config[status];
    if (!c) return;
    badges.forEach(function(badge) {
        badge.className = 'qnas-verify__status ' + c.cls;
        badge.innerHTML = '<i class="fa-solid ' + c.icon + ' me-1"></i>' + c.label;
        badge.style.display = '';
    });
}

function verifyQNAS(zone, street, building, recordId, orderId) {
    var btnId = 'qnasVerifyBtn' + recordId;
    var resultId = 'qnasResult' + recordId;
    var coordsId = 'qnasCoords' + recordId;

    var btn = document.getElementById(btnId);
    var resultSpan = document.getElementById(resultId);
    var coordsSpan = document.getElementById(coordsId);

    if (!btn) return;

    // Show loading
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin me-1"></i>Checking...';
    if (resultSpan) resultSpan.innerHTML = '';
    if (coordsSpan) coordsSpan.innerHTML = '';

    try {
        // Use current domain for API calls to avoid CORS issues
        var domain = window.location.origin;
        var url = domain + '/api/qnas/location/' + zone + '/' + street + '/';
        if (building) {
            url += building + '/';
        }

        console.log('[QNAS Verify] Calling:', url);

        // Use GET endpoint with path parameters
        fetch(url, {
            method: 'GET',
            credentials: 'include'
        }).then(function(response) {
            return response.json();
        }).then(function(data) {
        console.log('[QNAS Verify] Response:', data);

        if (!response.ok || !data.success) {
            // Not found in QNAS
            btn.innerHTML = '<i class="fa-solid fa-xmark-circle me-1"></i>Not in QNAS';
            btn.className = 'btn btn-sm btn-outline-danger';
            if (resultSpan) {
                resultSpan.innerHTML = '<span class="badge bg-danger"><i class="fa-solid fa-exclamation-triangle me-1"></i>Not Found</span>';
            }
            _saveQnasStatus(orderId, 'not_found');
            return;
        }

        var lat = data.latitude;
        var lng = data.longitude;
        var isExactMatch = data.match_type === 'exact';

        if (!lat || !lng || isNaN(lat) || isNaN(lng)) {
            btn.innerHTML = '<i class="fa-solid fa-exclamation-triangle me-1"></i>No Coords';
            btn.className = 'btn btn-sm btn-outline-warning';
            if (resultSpan) {
                resultSpan.innerHTML = '<span class="badge bg-warning text-dark"><i class="fa-solid fa-map-pin me-1"></i>Found but no coordinates</span>';
            }
            _saveQnasStatus(orderId, 'not_found');
            return;
        }

        // Success - found with coordinates
        btn.innerHTML = '<i class="fa-solid fa-check-circle me-1"></i>Verified';
        btn.className = 'btn btn-sm btn-success';
        btn.disabled = false;

        if (resultSpan) {
            var matchBadge = isExactMatch
                ? '<span class="badge bg-success"><i class="fa-solid fa-check-double me-1"></i>Exact Match</span>'
                : '<span class="badge bg-info"><i class="fa-solid fa-location-dot me-1"></i>Street Level</span>';
            resultSpan.innerHTML = matchBadge;
        }

        if (coordsSpan) {
            coordsSpan.innerHTML = '<a href="https://www.google.com/maps?q=' + lat + ',' + lng + '" target="_blank" class="text-success text-decoration-none d-inline-flex align-items-center gap-1" title="View on Google Maps"><i class="fa-solid fa-map-pin"></i><span>' + lat.toFixed(6) + ', ' + lng.toFixed(6) + '</span></a>';
        }

        _saveQnasStatus(orderId, 'verified');
        console.log('[QNAS Verify] Success:', { zone: zone, street: street, building: building, lat: lat, lng: lng, isExactMatch: isExactMatch, totalBuildings: data.total_buildings });
        }).catch(function(error) {
        console.error('[QNAS Verify] Error:', error);
        btn.innerHTML = '<i class="fa-solid fa-exclamation-circle me-1"></i>Error';
        btn.className = 'btn btn-sm btn-outline-danger';
        btn.disabled = false;

        if (resultSpan) {
            resultSpan.innerHTML = '<span class="badge bg-danger"><i class="fa-solid fa-times me-1"></i>Check Failed</span>';
        }
        _saveQnasStatus(orderId, 'error');
        });
    } catch (error) {
        console.error('[QNAS Verify] Error:', error);
        btn.innerHTML = '<i class="fa-solid fa-exclamation-circle me-1"></i>Error';
        btn.className = 'btn btn-sm btn-outline-danger';
        btn.disabled = false;

        if (resultSpan) {
            resultSpan.innerHTML = '<span class="badge bg-danger"><i class="fa-solid fa-times me-1"></i>Check Failed</span>';
        }
        _saveQnasStatus(orderId, 'error');
    }
}

/**
 * Verify QNAS and save coordinates to order
 */
function verifyAndUpdateCoords(zone, street, building, orderId) {
    var container = document.getElementById('orderLatLng' + orderId);
    if (!container) return;

    container.innerHTML = '<i class="fa-solid fa-spinner fa-spin me-1"></i>Verifying...';

    try {
        var domain = window.location.origin;
        var url = domain + '/api/qnas/location/' + zone + '/' + street + '/';
        if (building) url += building + '/';

        fetch(url, { method: 'GET', credentials: 'include' }).then(function(resp) {
            return resp.json();
        }).then(function(data) {

            if (!data.success || !data.latitude || !data.longitude) {
                container.innerHTML = '<span class="badge bg-danger"><i class="fa-solid fa-times me-1"></i>Not found in QNAS</span>';
                _saveQnasStatus(orderId, 'not_found');
                return;
            }

            // Save to order - get CSRF token
            var csrfToken = _getCsrfToken();
            fetch(domain + '/workforce/orders/' + orderId + '/update-coords/', {
                method: 'POST',
                credentials: 'include',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                body: JSON.stringify({ latitude: data.latitude, longitude: data.longitude, qnas_status: 'verified' })
            }).then(function(saveResp) {
                return saveResp.json();
            }).then(function(saveData) {
                if (saveData.success) {
                    var lat = saveData.latitude.toFixed(6);
                    var lng = saveData.longitude.toFixed(6);
                    container.innerHTML = '<a href="https://www.google.com/maps?q=' + lat + ',' + lng + '" target="_blank" class="text-decoration-none"><i class="fa-solid fa-map-pin me-1 text-success"></i>' + lat + ', ' + lng + '</a> <span class="badge bg-success ms-1"><i class="fa-solid fa-check me-1"></i>Saved</span>';
                } else {
                    container.innerHTML = '<span class="text-danger"><i class="fa-solid fa-map-pin me-1"></i>' + data.latitude.toFixed(6) + ', ' + data.longitude.toFixed(6) + '</span> <span class="badge bg-warning text-dark">Save failed</span>';
                }
            }).catch(function(err) {
                console.error('[QNAS] Save error:', err);
            });
        }).catch(function(err) {
            console.error('[QNAS] Fetch error:', err);
        });
    } catch (error) {
        console.error('[QNAS] verifyAndUpdateCoords error:', error);
        container.innerHTML = '<span class="badge bg-danger"><i class="fa-solid fa-times me-1"></i>Error</span>';
        _saveQnasStatus(orderId, 'error');
    }
}

/**
 * Validate address via QNAS and fill lat/long form fields
 * Used on order add/update forms where lat/long are editable inputs
 *
 * @param {object} opts - { zoneId, streetId, buildingId, latId, lngId, resultId, btnId }
 *   All are element IDs. Zone/street are read from inputs, lat/lng are filled on success.
 */
function qnasValidateAndFill(opts) {
    var zoneEl = document.getElementById(opts.zoneId);
    var streetEl = document.getElementById(opts.streetId);
    var zone = zoneEl ? zoneEl.value : null;
    var street = streetEl ? streetEl.value : null;
    var buildingEl = document.getElementById(opts.buildingId);
    var building = buildingEl ? buildingEl.value : '';
    var latInput = document.getElementById(opts.latId);
    var lngInput = document.getElementById(opts.lngId);
    var resultDiv = document.getElementById(opts.resultId);
    var btn = document.getElementById(opts.btnId);

    if (!zone || !street) {
        if (resultDiv) resultDiv.innerHTML = '<span class="text-danger small">Enter Zone and Street first</span>';
        return;
    }

    if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin me-1"></i>Checking...'; }
    if (resultDiv) resultDiv.innerHTML = '';

    try {
        var url = window.location.origin + '/api/qnas/location/' + zone + '/' + street + '/';
        if (building) url += building + '/';

        fetch(url, { method: 'GET', credentials: 'include' }).then(function(resp) {
            return resp.json();
        }).then(function(data) {
            var mapLink = opts.mapId ? document.getElementById(opts.mapId) : null;
            var accuracyInput = opts.accuracyId ? document.getElementById(opts.accuracyId) : null;
            var accuracyBadge = opts.accuracyBadgeId ? document.getElementById(opts.accuracyBadgeId) : null;
            if (data.success && data.latitude && data.longitude) {
                if (latInput) latInput.value = data.latitude;
                if (lngInput) lngInput.value = data.longitude;
                var lat = data.latitude.toFixed(6);
                var lng = data.longitude.toFixed(6);
                var isExact = data.match_type === 'exact';
                var accuracy = isExact ? 'exact' : 'street';
                var zoneName = data.zone_name || '';
                if (accuracyInput) accuracyInput.value = accuracy;
                // Fill zone name display field if provided
                var zoneNameId = opts.zoneNameId;
                if (zoneNameId && zoneName) {
                    var znEl = document.getElementById(zoneNameId);
                    if (znEl) znEl.value = zoneName;
                }
                if (mapLink) {
                    mapLink.href = 'https://www.google.com/maps?q=' + lat + ',' + lng;
                    mapLink.classList.remove('disabled', 'btn-outline-secondary', 'btn-success', 'btn-warning');
                    mapLink.classList.add(isExact ? 'btn-success' : 'btn-warning');
                }
                if (accuracyBadge) {
                    accuracyBadge.innerHTML = isExact
                        ? '<span class="badge bg-success" style="font-size:.7rem">Exact</span>'
                        : '<span class="badge bg-warning text-dark" style="font-size:.7rem">Street</span>';
                }
                if (resultDiv) {
                    var zoneNameHtml = zoneName ? '<span class="text-muted small ms-1">' + zoneName + '</span>' : '';
                    resultDiv.innerHTML = '<div class="d-flex align-items-center gap-2 flex-wrap"><span class="badge ' + (isExact ? 'bg-success' : 'bg-warning text-dark') + '"><i class="fa-solid fa-check me-1"></i>' + (isExact ? 'Exact Match' : 'Street Level') + '</span><span class="text-muted small">(' + data.total_buildings + ' buildings)</span>' + zoneNameHtml + '</div>';
                }
                if (btn) { btn.innerHTML = '<i class="fa-solid fa-check me-1"></i>Verified'; btn.className = btn.className.replace('btn-outline-warning', 'btn-success'); }
            } else {
                if (accuracyInput) accuracyInput.value = '';
                if (accuracyBadge) accuracyBadge.innerHTML = '';
                if (mapLink) { mapLink.href = '#'; mapLink.classList.add('disabled', 'btn-outline-secondary'); mapLink.classList.remove('btn-success', 'btn-warning'); }
                if (resultDiv) resultDiv.innerHTML = '<span class="badge bg-danger"><i class="fa-solid fa-times me-1"></i>Not found in QNAS</span>';
                if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fa-solid fa-satellite-dish me-1"></i>Validate'; }
            }
        });
    } catch (error) {
        console.error('[QNAS] qnasValidateAndFill error:', error);
        if (resultDiv) resultDiv.innerHTML = '<span class="badge bg-danger"><i class="fa-solid fa-times me-1"></i>Connection error</span>';
        if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fa-solid fa-satellite-dish me-1"></i>Validate'; }
    }
}


/* ============================================================
 * AI Parse helpers
 * ============================================================ */

/** Get CSRF token from cookie, meta tag, or hidden input */
function _getCsrfToken() {
    // Hidden input
    var input = document.querySelector('input[name="csrfmiddlewaretoken"]');
    if (input) return input.value;
    // Cookie
    var cookies = document.cookie.split(';');
    for (var i = 0; i < cookies.length; i++) {
        var c = cookies[i].trim();
        if (c.indexOf('csrftoken=') === 0) return c.substring('csrftoken='.length);
    }
    // Meta tag
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) return meta.getAttribute('content');
    return '';
}

/**
 * Show step progress with maroon spinner badge
 * @param {HTMLElement} btn
 * @param {HTMLElement} resultDiv
 * @param {number} step - current step (1-5)
 * @param {string} message
 */
function _setProgress(btn, resultDiv, step, message) {
    var pct = Math.min(Math.round((step / 5) * 100), 95);
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin me-1"></i>' + pct + '%';
        btn.className = 'btn-outline-info';
        btn.style.color = '#8b1a3a';
        btn.style.borderColor = '#8b1a3a';
    }
    if (resultDiv) {
        resultDiv.innerHTML = '<span class="badge text-white" style="font-size:.72rem;background:#8b1a3a"><i class="fa-solid fa-spinner fa-spin me-1"></i>' + message + '</span>';
    }
}

/**
 * Map geocode_source to badge color, label, accuracy value, and map icon class
 * @param {string} geocodeSource - qnas_exact|qnas_street|landmark|zone_center|ai_estimate
 * @param {number} confidence - 0.0-1.0
 * @returns {{ badgeClass:string, badgeStyle:string, label:string, accuracy:string, mapBtnClass:string }}
 */
function _getAccuracyInfo(geocodeSource, confidence) {
    var pct = Math.round((confidence || 0) * 100);
    var result;
    switch (geocodeSource) {
        case 'qnas_exact':
            result = { badgeClass: 'bg-success', badgeStyle: '', label: 'Exact', accuracy: 'exact', mapBtnClass: 'btn-success' };
            break;
        case 'qnas_street':
            result = { badgeClass: 'bg-warning text-dark', badgeStyle: '', label: 'Street', accuracy: 'street', mapBtnClass: 'btn-warning' };
            break;
        case 'landmark':
            result = { badgeClass: 'text-white', badgeStyle: 'background:#8b1a3a', label: 'Area ' + pct + '%', accuracy: 'landmark', mapBtnClass: 'btn-outline-danger' };
            break;
        case 'zone_center':
            result = { badgeClass: 'text-white', badgeStyle: 'background:#8b1a3a', label: 'Zone ~' + pct + '%', accuracy: 'zone_center', mapBtnClass: 'btn-outline-danger' };
            break;
        case 'ai_estimate':
            result = { badgeClass: 'text-white', badgeStyle: 'background:#8b1a3a', label: 'AI ' + pct + '%', accuracy: 'ai_estimate', mapBtnClass: 'btn-outline-danger' };
            break;
        default:
            result = { badgeClass: 'bg-secondary', badgeStyle: '', label: pct + '%', accuracy: '', mapBtnClass: 'btn-outline-secondary' };
    }
    return result;
}

/** Show done state on AI parse button */
function _setDone(btn, label) {
    if (!btn) return;
    btn.disabled = false;
    btn.style.color = '';
    btn.style.borderColor = '';
    btn.innerHTML = '<i class="fa-solid fa-check me-1"></i>' + label;
    btn.className = 'btn-success';
}

/** Show error state */
function _setError(btn, resultDiv, message) {
    if (resultDiv) resultDiv.innerHTML = '<span class="badge bg-warning text-dark"><i class="fa-solid fa-exclamation-triangle me-1"></i>' + message + '</span>';
    if (btn) {
        btn.disabled = false;
        btn.style.color = '';
        btn.style.borderColor = '';
        btn.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles me-1"></i>AI Parse';
        btn.className = 'btn-outline-info';
    }
}

/** Reset AI parse button to initial state after delay */
function _resetBtnAfterDelay(btn, ms) {
    ms = ms || 4000;
    setTimeout(function() {
        if (btn) {
            btn.disabled = false;
            btn.style.color = '';
            btn.style.borderColor = '';
            btn.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles me-1"></i>AI Parse';
            btn.className = 'btn-outline-info';
        }
    }, ms);
}

/**
 * Apply coordinate result to form fields (lat, lng, map link, accuracy)
 * @param {object} opts - qnasOpts from extra param
 * @param {number} lat
 * @param {number} lng
 * @param {object} info - from _getAccuracyInfo
 */
function _applyCoords(opts, lat, lng, info) {
    if (!opts) return;
    var latInput = opts.latId ? document.getElementById(opts.latId) : null;
    var lngInput = opts.lngId ? document.getElementById(opts.lngId) : null;
    var mapLink = opts.mapId ? document.getElementById(opts.mapId) : null;
    var accInput = opts.accuracyId ? document.getElementById(opts.accuracyId) : null;
    var accBadge = opts.accuracyBadgeId ? document.getElementById(opts.accuracyBadgeId) : null;

    if (latInput) latInput.value = lat;
    if (lngInput) lngInput.value = lng;
    if (accInput) accInput.value = info.accuracy;
    if (mapLink) {
        mapLink.href = 'https://www.google.com/maps?q=' + lat + ',' + lng;
        mapLink.classList.remove('disabled', 'btn-outline-secondary', 'btn-success', 'btn-warning', 'btn-outline-danger');
        mapLink.classList.add(info.mapBtnClass);
    }
    if (accBadge) {
        var style = info.badgeStyle ? ' style="font-size:.7rem;' + info.badgeStyle + '"' : ' style="font-size:.7rem"';
        accBadge.innerHTML = '<span class="badge ' + info.badgeClass + '"' + style + '>' + info.label + '</span>';
    }
}


/* ============================================================
 * AI Parse Address — Step-by-step flow
 * ============================================================ */

/**
 * AI Parse address text into zone/street/building and auto-validate via QNAS
 *
 * @param {string} addressId  - ID of the address input
 * @param {string} zoneId     - ID of the zone input to fill
 * @param {string} streetId   - ID of the street input to fill
 * @param {string} buildingId - ID of the building input to fill
 * @param {string} btnId      - ID of the AI Parse button
 * @param {string} resultId   - ID of the result container
 * @param {object} extra      - { qnasOpts: opts to pass to qnasValidateAndFill }
 */
function aiParseAddress(addressId, zoneId, streetId, buildingId, btnId, resultId, extra) {
    var addressInput = document.getElementById(addressId);
    var btn = document.getElementById(btnId);
    var resultDiv = document.getElementById(resultId);
    var address = addressInput ? addressInput.value.trim() : '';

    if (!address) {
        if (resultDiv) resultDiv.innerHTML = '<span class="text-danger small">Enter an address first</span>';
        return;
    }

    /* ── Step 1: Call AI parse-address API ── */
    _setProgress(btn, resultDiv, 1, 'Extracting address...');

    var csrfToken = _getCsrfToken();
    try {
        fetch(window.location.origin + '/api/ai-agent/tools/parse-address/', {
            method: 'POST',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
            body: JSON.stringify({ address: address })
        }).then(function(resp) {
            return resp.json();
        }).then(function(data) {
            var d = data.data || data;

            var zone = d.zone_number;
            var street = d.street_number;
            var building = d.building_number;
            var areaName = d.zone_name || d.area_name || '';
            var confidence = d.confidence || 0;
            var aiLat = d.coordinates ? d.coordinates.latitude : null;
            var aiLng = d.coordinates ? d.coordinates.longitude : null;
            var geocodeSource = d.geocode_source || null;

            /* ── Step 2: Fill form fields ── */
            _setProgress(btn, resultDiv, 2, 'Filling fields...');

            var filled = [];
            if (zone) { document.getElementById(zoneId).value = zone; filled.push('Zone ' + zone); }
            if (street) { document.getElementById(streetId).value = street; filled.push('St ' + street); }
            if (building) { document.getElementById(buildingId).value = building; filled.push('Bldg ' + building); }

            var parsedStreet = parseInt(street);
            var hasValidStreet = street && !isNaN(parsedStreet) && parsedStreet > 0;
            var qOpts = extra ? extra.qnasOpts : null;

            /* ── Step 3: Zone + Street + Building → QNAS exact (green) ── */
            if (zone && hasValidStreet && building) {
                _setProgress(btn, resultDiv, 3, 'QNAS verifying building...');
                if (qOpts) {
                    // Call QNAS to finish filling coords
                    _qnasAndFinish(qOpts, btn, resultDiv, filled, areaName, geocodeSource, confidence);
                } else {
                    _showFilledResult(btn, resultDiv, filled, areaName);
                }
                _resetBtnAfterDelay(btn, 4000);
                return;
            }

            /* ── Step 4: Zone + Street (no building) → QNAS street-level (yellow) ── */
            if (zone && hasValidStreet) {
                _setProgress(btn, resultDiv, 4, 'QNAS verifying street...');
                if (qOpts) {
                    _qnasAndFinish(qOpts, btn, resultDiv, filled, areaName, geocodeSource, confidence);
                } else {
                    _showFilledResult(btn, resultDiv, filled, areaName);
                }
                _resetBtnAfterDelay(btn, 4000);
                return;
            }

            /* ── Step 5: Zone only (or no zone) with coords → maroon badge ── */
            if (aiLat && aiLng) {
                var stepMsg = zone ? 'Geocoding area...' : 'Locating address...';
                _setProgress(btn, resultDiv, 5, stepMsg);

                var info = _getAccuracyInfo(geocodeSource, confidence);
                if (qOpts) {
                    _applyCoords(qOpts, aiLat, aiLng, info);
                }

                // Build result HTML
                var html = '';
                if (filled.length > 0) {
                    html += '<span class="badge bg-info"><i class="fa-solid fa-wand-magic-sparkles me-1"></i>' + filled.join(', ') + '</span> ';
                }
                if (areaName) {
                    html += '<span class="text-muted small">' + areaName + '</span> ';
                }
                // Maroon confidence badge
                var pct = Math.round(confidence * 100);
                html += '<span class="badge text-white" style="font-size:.72rem;background:#8b1a3a">' + info.label + '</span>';

                if (resultDiv) resultDiv.innerHTML = html;
                _setDone(btn, filled.length > 0 ? 'Parsed' : 'Located');
                _resetBtnAfterDelay(btn, 4000);
                return;
            }

            /* ── Step 5b: Fields filled but no coords ── */
            if (filled.length > 0) {
                _showFilledResult(btn, resultDiv, filled, areaName);
                _resetBtnAfterDelay(btn, 4000);
                return;
            }

            /* ── Fallback: Nothing found ── */
            _setError(btn, resultDiv, 'Could not parse address');
        }).catch(function(error) {
            console.error('[AI Parse] Error:', error);
            _setError(btn, resultDiv, 'Parse failed');
        });
    } catch (error) {
        console.error('[AI Parse] Error:', error);
        _setError(btn, resultDiv, 'Parse failed');
    }
}

/**
 * Run qnasValidateAndFill then show final result
 * (wraps the QNAS call so aiParseAddress can call it)
 */
function _qnasAndFinish(qOpts, btn, resultDiv, filled, areaName, geocodeSource, confidence) {
    try {
        qnasValidateAndFill(qOpts);
        // After QNAS finishes, check if it actually set coords
        var latInput = qOpts.latId ? document.getElementById(qOpts.latId) : null;
        var latVal = latInput ? parseFloat(latInput.value) : 0;
        if (latVal) {
            // QNAS succeeded — show filled fields + the QNAS result already shown by qnasValidateAndFill
            var filledHtml = '<span class="badge bg-info me-1"><i class="fa-solid fa-wand-magic-sparkles me-1"></i>' + filled.join(', ') + '</span>';
            if (areaName) filledHtml += '<span class="text-muted small me-1">' + areaName + '</span>';
            // Prepend to existing QNAS result
            if (resultDiv) {
                var existing = resultDiv.innerHTML;
                resultDiv.innerHTML = filledHtml + existing;
            }
            _setDone(btn, 'Verified');
        } else {
            // QNAS failed — show filled fields only
            _showFilledResult(btn, resultDiv, filled, areaName);
        }
    } catch (e) {
        console.error('[AI Parse] QNAS follow-up error:', e);
        _showFilledResult(btn, resultDiv, filled, areaName);
    }
}

/** Show simple "filled" result badge */
function _showFilledResult(btn, resultDiv, filled, areaName) {
    var html = '<span class="badge bg-info"><i class="fa-solid fa-wand-magic-sparkles me-1"></i>' + filled.join(', ') + '</span>';
    if (areaName) html += ' <span class="text-muted small">' + areaName + '</span>';
    if (resultDiv) resultDiv.innerHTML = html;
    _setDone(btn, 'Parsed');
}


// Auto-verify on page load if data-auto-verify attribute is present
document.addEventListener('DOMContentLoaded', function() {
    var autoVerifyButtons = document.querySelectorAll('[data-auto-verify="true"]');
    autoVerifyButtons.forEach(function(btn) {
        var zone = btn.dataset.zone;
        var street = btn.dataset.street;
        var building = btn.dataset.building || '';
        var recordId = btn.dataset.recordId;
        var orderId = btn.dataset.orderId || '';

        if (zone && street && recordId) {
            verifyQNAS(zone, street, building, recordId, orderId);
        }
    });
});
