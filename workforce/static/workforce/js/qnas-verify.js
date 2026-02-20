/**
 * QNAS Verification Utility
 * Verifies if zone/street/building exists in QNAS and shows coordinates
 */

async function verifyQNAS(zone, street, building, recordId) {
    const btnId = `qnasVerifyBtn${recordId}`;
    const resultId = `qnasResult${recordId}`;
    const coordsId = `qnasCoords${recordId}`;

    const btn = document.getElementById(btnId);
    const resultSpan = document.getElementById(resultId);
    const coordsSpan = document.getElementById(coordsId);

    if (!btn) return;

    // Show loading
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin me-1"></i>Checking...';
    if (resultSpan) resultSpan.innerHTML = '';
    if (coordsSpan) coordsSpan.innerHTML = '';

    try {
        // Use current domain for API calls to avoid CORS issues
        const domain = window.location.origin;
        let url = `${domain}/api/qnas/location/${zone}/${street}/`;
        if (building) {
            url += `${building}/`;
        }

        console.log('[QNAS Verify] Calling:', url);

        // Use GET endpoint with path parameters
        const response = await fetch(url, {
            method: 'GET',
            credentials: 'include'
        });

        const data = await response.json();
        console.log('[QNAS Verify] Response:', data);

        if (!response.ok || !data.success) {
            // Not found in QNAS
            btn.innerHTML = '<i class="fa-solid fa-xmark-circle me-1"></i>Not in QNAS';
            btn.className = 'btn btn-sm btn-outline-danger';
            if (resultSpan) {
                resultSpan.innerHTML = '<span class="badge bg-danger"><i class="fa-solid fa-exclamation-triangle me-1"></i>Not Found</span>';
            }
            return;
        }

        const lat = data.latitude;
        const lng = data.longitude;
        const isExactMatch = data.match_type === 'exact';

        if (!lat || !lng || isNaN(lat) || isNaN(lng)) {
            btn.innerHTML = '<i class="fa-solid fa-exclamation-triangle me-1"></i>No Coords';
            btn.className = 'btn btn-sm btn-outline-warning';
            if (resultSpan) {
                resultSpan.innerHTML = '<span class="badge bg-warning text-dark"><i class="fa-solid fa-map-pin me-1"></i>Found but no coordinates</span>';
            }
            return;
        }

        // Success - found with coordinates
        btn.innerHTML = '<i class="fa-solid fa-check-circle me-1"></i>Verified';
        btn.className = 'btn btn-sm btn-success';
        btn.disabled = false;

        if (resultSpan) {
            const matchBadge = isExactMatch
                ? '<span class="badge bg-success"><i class="fa-solid fa-check-double me-1"></i>Exact Match</span>'
                : '<span class="badge bg-info"><i class="fa-solid fa-location-dot me-1"></i>Street Level</span>';
            resultSpan.innerHTML = matchBadge;
        }

        if (coordsSpan) {
            coordsSpan.innerHTML = `
                <a href="https://www.google.com/maps?q=${lat},${lng}"
                   target="_blank"
                   class="text-success text-decoration-none d-inline-flex align-items-center gap-1"
                   title="View on Google Maps">
                    <i class="fa-solid fa-map-pin"></i>
                    <span>${lat.toFixed(6)}, ${lng.toFixed(6)}</span>
                </a>
            `;
        }

        console.log('[QNAS Verify] Success:', { zone, street, building, lat, lng, isExactMatch, totalBuildings: data.total_buildings });

    } catch (error) {
        console.error('[QNAS Verify] Error:', error);
        btn.innerHTML = '<i class="fa-solid fa-exclamation-circle me-1"></i>Error';
        btn.className = 'btn btn-sm btn-outline-danger';
        btn.disabled = false;

        if (resultSpan) {
            resultSpan.innerHTML = '<span class="badge bg-danger"><i class="fa-solid fa-times me-1"></i>Check Failed</span>';
        }
    }
}

// Auto-verify on page load if data-auto-verify attribute is present
document.addEventListener('DOMContentLoaded', function() {
    const autoVerifyButtons = document.querySelectorAll('[data-auto-verify="true"]');
    autoVerifyButtons.forEach(btn => {
        const zone = btn.dataset.zone;
        const street = btn.dataset.street;
        const building = btn.dataset.building || '';
        const recordId = btn.dataset.recordId;

        if (zone && street && recordId) {
            verifyQNAS(zone, street, building, recordId);
        }
    });
});
