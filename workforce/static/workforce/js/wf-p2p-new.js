/*
Purpose: The staff P2P booking form — locality name to map pin, and the live rate-card figure
Used by: workforce/forms/p2p_new.html
Notes: The price shown here is advisory. The POST recomputes it from the same p2p.pricing.quote,
       so nothing typed on this page can buy a cheaper delivery than the card says.
*/

(function () {
  'use strict';

  const form = document.getElementById('workforce_p2p_new_form_booking');
  if (!form) return;

  const dataEl = document.getElementById('workforce_p2p_new_data_localities');
  let localities = [];
  try {
    localities = JSON.parse(dataEl.textContent) || [];
  } catch (e) {
    localities = [];
  }

  // --- The area picker ------------------------------------------------------
  // A datalist rather than a custom dropdown: it searches as you type, works with the
  // keyboard, and still lets ops type a name that is not on the list when the pin is
  // going to be pasted in by hand anyway.
  const list = document.getElementById('workforce_p2p_new_list_localities');
  const byName = new Map();
  localities.forEach(function (row) {
    byName.set(row.name.toLowerCase(), row);
    const opt = document.createElement('option');
    opt.value = row.name;
    opt.label = row.zone || '';
    list.appendChild(opt);
  });

  // "25.2854, 51.5310" or a Google/Apple maps link carrying a pair. Ops paste both
  // shapes off a customer's WhatsApp message, so read a pin out of either.
  const PAIR = /(-?\d{1,3}\.\d{3,})[ ,/]+(-?\d{1,3}\.\d{3,})/;

  function coordsFrom(text) {
    const m = PAIR.exec(text || '');
    if (!m) return null;
    return { lat: parseFloat(m[1]), lng: parseFloat(m[2]) };
  }

  const LEGS = [
    { label: 'from_label', lat: 'from_lat', lng: 'from_lng' },
    { label: 'to_label', lat: 'to_lat', lng: 'to_lng' },
  ];

  function field(name) {
    return form.querySelector('[name="' + name + '"]');
  }

  LEGS.forEach(function (leg) {
    const labelInput = field(leg.label);
    const latInput = field(leg.lat);
    const lngInput = field(leg.lng);
    if (!labelInput || !latInput || !lngInput) return;

    labelInput.addEventListener('input', function () {
      const typed = labelInput.value.trim();

      // A pasted pin wins over a name match: it is a specific spot, and the name box
      // then keeps whatever it already said rather than being overwritten with digits.
      const pin = coordsFrom(typed);
      if (pin) {
        latInput.value = pin.lat;
        lngInput.value = pin.lng;
        if (byName.size && !byName.has(typed.toLowerCase())) {
          labelInput.value = 'Pinned location';
        }
        requestQuote();
        return;
      }

      const match = byName.get(typed.toLowerCase());
      if (match) {
        latInput.value = match.lat;
        lngInput.value = match.lng;
        requestQuote();
      }
    });

    [latInput, lngInput].forEach(function (el) {
      el.addEventListener('change', requestQuote);
    });
  });

  // --- The live figure ------------------------------------------------------
  const priceEl = document.getElementById('workforce_p2p_new_text_price');
  const noteEl = document.getElementById('workforce_p2p_new_text_note');
  const quoteUrl = form.dataset.quoteUrl;
  let pending = null;
  let inFlight = 0;

  function collect() {
    const params = new URLSearchParams();
    ['from_lat', 'from_lng', 'to_lat', 'to_lng', 'box_count', 'weight_kg'].forEach(function (name) {
      const el = field(name);
      if (el && el.value) params.set(name, el.value);
    });
    ['size', 'vehicle', 'speed'].forEach(function (name) {
      const el = form.querySelector('[name="' + name + '"]:checked');
      if (el && el.value) params.set(name, el.value);
    });
    // The leg back doubles the figure, so the number ops read out has to know about it.
    const back = field('return_trip');
    if (back && back.checked) params.set('return_trip', '1');
    form.querySelectorAll('[name^="count_"]').forEach(function (el) {
      if (el.value && Number(el.value) > 0) params.set(el.name, el.value);
    });
    return params;
  }

  function show(price, note) {
    priceEl.textContent = price;
    noteEl.textContent = note;
  }

  function requestQuote() {
    // Debounced: every keystroke in the weight box would otherwise be a round trip.
    window.clearTimeout(pending);
    pending = window.setTimeout(runQuote, 250);
  }

  function runQuote() {
    const params = collect();
    if (!params.get('from_lat') || !params.get('to_lat')) {
      show('—', 'Pick both ends and a size.');
      return;
    }
    const ticket = ++inFlight;
    fetch(quoteUrl + '?' + params.toString(), {
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        // A slower earlier request must not overwrite a newer answer.
        if (ticket !== inFlight) return;
        if (!data.ok) {
          show('—', data.reason || 'Cannot price this yet.');
          return;
        }
        const km = data.km_low + '–' + data.km_high + ' km';
        if (data.price === null) {
          const why = data.over_capacity
            ? 'The load will not fit that vehicle.'
            : (data.needs_vehicle
              ? 'Use a ' + data.needs_vehicle + ' for this load.'
              : 'No band covers this — enter an agreed price.');
          show('Quote', km + ' · ' + why);
          return;
        }
        const both = data.return_trip && data.leg_price
          ? km + ' · both journeys, ' + Number(data.leg_price).toFixed(0) + ' QAR each way'
          : km;
        show(Number(data.price).toFixed(0) + ' QAR', both);
      })
      .catch(function () {
        if (ticket !== inFlight) return;
        show('—', 'Could not reach the rate card.');
      });
  }

  form.querySelectorAll(
    '[name="size"], [name="vehicle"], [name="speed"], [name="box_count"], ' +
    '[name="weight_kg"], [name="return_trip"], [name^="count_"]'
  ).forEach(function (el) {
    el.addEventListener('change', requestQuote);
  });

  // A re-rendered form after a validation error already has every answer on it, so
  // price it once on load rather than waiting for ops to touch something.
  runQuote();
})();
