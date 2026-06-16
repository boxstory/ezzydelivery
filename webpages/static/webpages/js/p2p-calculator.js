/*
Purpose: P2P delivery price calculator — category, size, zone chips, location search, map link parsing, Haversine
Used by: webpages/p2p_pricing.html
Notes: Locality data from window.P2P_LOCALITIES / window.P2P_POPULAR (injected by view from ZoneName/ZoneArea DB)
*/

const P2P_LOCALITIES = window.P2P_LOCALITIES || [];
const P2P_POPULAR    = window.P2P_POPULAR    || [];

// --- Categories ---
const P2P_CATEGORIES = [
  // Popular chips (shown at top)
  { name: 'Documents',            icon: 'fa-file-lines',         popular: true  },
  { name: 'Electronics',          icon: 'fa-plug',               popular: true  },
  { name: 'Phones & Accessories', icon: 'fa-mobile-screen',      popular: true  },
  { name: 'Fashion & Clothing',   icon: 'fa-shirt',              popular: true  },
  { name: 'Food & Grocery',       icon: 'fa-bag-shopping',       popular: true  },
  { name: 'Medical & Pharmacy',   icon: 'fa-kit-medical',        popular: true  },
  { name: 'Flowers & Gifts',      icon: 'fa-gift',               popular: true  },
  { name: 'Perfume & Fragrance',  icon: 'fa-spray-can',          popular: true  },
  { name: 'Watches & Jewelry',    icon: 'fa-clock',              popular: true  },
  { name: 'Furniture',            icon: 'fa-couch',              popular: true  },
  { name: 'Home Appliances',      icon: 'fa-blender',            popular: true  },
  { name: 'Toys & Games',         icon: 'fa-gamepad',            popular: true  },
  { name: 'General Parcel',       icon: 'fa-box',                popular: true  },
  // Home business — popular chips
  { name: 'Sweets & Chocolates',  icon: 'fa-candy-cane',         popular: true  },
  { name: 'Home Bakery',          icon: 'fa-cake-candles',       popular: true  },
  { name: 'Gift Hampers',         icon: 'fa-box-open',           popular: true  },
  { name: 'Handmade Items',       icon: 'fa-hands',              popular: true  },
  { name: 'Abayas & Thobes',      icon: 'fa-person-dress',       popular: true  },
  { name: 'Candles & Wax Melts',  icon: 'fa-fire',               popular: true  },
  // Home business — searchable only
  { name: 'Homemade Food',        icon: 'fa-utensils',           popular: false },
  { name: 'Natural Skincare',     icon: 'fa-leaf',               popular: false },
  { name: 'Islamic & Prayer Items',icon: 'fa-star-and-crescent', popular: false },
  { name: 'Party Decorations',    icon: 'fa-champagne-glasses',  popular: false },
  { name: 'Custom Merchandise',   icon: 'fa-print',              popular: false },
  { name: 'Embroidery & Tailoring',icon: 'fa-scissors',          popular: false },
  { name: 'Organic & Natural',    icon: 'fa-seedling',           popular: false },
  { name: 'Arabic Coffee & Dates',icon: 'fa-mug-hot',            popular: false },
  { name: 'Custom Stationery',    icon: 'fa-pen-nib',            popular: false },
  { name: 'Handmade Jewelry',     icon: 'fa-gem',                popular: false },
  { name: 'Baby Shower Items',    icon: 'fa-baby',               popular: false },
  { name: 'Wedding Favors',       icon: 'fa-heart',              popular: false },
  { name: 'Home Decor',           icon: 'fa-couch',              popular: false },
  { name: 'Scented Products',     icon: 'fa-spray-can',          popular: false },
  // General searchable
  { name: 'Books & Stationery',   icon: 'fa-book',               popular: false },
  { name: 'Sports & Fitness',     icon: 'fa-dumbbell',           popular: false },
  { name: 'Automotive Parts',     icon: 'fa-car',                popular: false },
  { name: 'Art & Crafts',         icon: 'fa-palette',            popular: false },
  { name: 'Computer & Laptop',    icon: 'fa-laptop',             popular: false },
  { name: 'Camera & Photography', icon: 'fa-camera',             popular: false },
  { name: 'Gaming & Consoles',    icon: 'fa-gamepad',            popular: false },
  { name: 'Kitchen & Cookware',   icon: 'fa-kitchen-set',        popular: false },
  { name: 'Office Supplies',      icon: 'fa-briefcase',          popular: false },
  { name: 'Eyewear & Glasses',    icon: 'fa-glasses',            popular: false },
  { name: 'Luggage & Bags',       icon: 'fa-suitcase',           popular: false },
  { name: 'Plants & Seeds',       icon: 'fa-leaf',               popular: false },
  { name: 'Fabric & Textiles',    icon: 'fa-scissors',           popular: false },
  { name: 'Tools & Hardware',     icon: 'fa-screwdriver-wrench', popular: false },
  { name: 'Pet Supplies',         icon: 'fa-paw',                popular: false },
  { name: 'Industrial',           icon: 'fa-industry',           popular: false },
  { name: 'Other',                icon: 'fa-ellipsis',           popular: false },
];

// --- Sizes ---
const P2P_SIZES = [
  { size: 'xs', label: 'Envelope / Docs',    weight: '≤ 0.5 kg' },
  { size: 's',  label: 'Small Box',          weight: '≤ 3 kg'   },
  { size: 'm',  label: 'Medium Box',         weight: '≤ 10 kg'  },
  { size: 'l',  label: 'Large Box',          weight: '≤ 25 kg'  },
  { size: 'xl', label: 'Bulky / Extra Large',weight: '25 kg+'   },
];

// --- Pricing ---
function getPrice(km) {
  if (km <= 10) return 25;
  if (km <= 20) return 35;
  if (km <= 30) return 40;
  return 55;
}

// --- Haversine ---
function haversine(lat1, lng1, lat2, lng2) {
  const R = 6371;
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLng = (lng2 - lng1) * Math.PI / 180;
  const a = Math.sin(dLat / 2) ** 2
    + Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180)
    * Math.sin(dLng / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function nearestLocality(lat, lng) {
  return P2P_LOCALITIES.reduce((best, loc) => {
    const d = haversine(lat, lng, loc.lat, loc.lng);
    return d < best.d ? { d, loc } : best;
  }, { d: Infinity, loc: null }).loc;
}

// --- URL parsing ---
function parseMapUrl(url) {
  let m = url.match(/@(-?\d{1,3}\.\d+),(-?\d{1,3}\.\d+)/);
  if (m) return { lat: parseFloat(m[1]), lng: parseFloat(m[2]) };
  m = url.match(/[?&]q=(-?\d{1,3}\.\d+),(-?\d{1,3}\.\d+)/);
  if (m) return { lat: parseFloat(m[1]), lng: parseFloat(m[2]) };
  m = url.match(/[?&]ll=(-?\d{1,3}\.\d+),(-?\d{1,3}\.\d+)/);
  if (m) return { lat: parseFloat(m[1]), lng: parseFloat(m[2]) };
  m = url.match(/(-?\d{1,3}\.\d{4,}),(-?\d{1,3}\.\d{4,})/);
  if (m) return { lat: parseFloat(m[1]), lng: parseFloat(m[2]) };
  return null;
}

function parseRawCoords(text) {
  const m = text.trim().match(/^(-?\d{1,3}\.\d+)\s*,\s*(-?\d{1,3}\.\d+)$/);
  if (!m) return null;
  const lat = parseFloat(m[1]), lng = parseFloat(m[2]);
  if (lat < 24.4 || lat > 26.3 || lng < 50.7 || lng > 51.8) return null;
  return { lat, lng };
}

function isShortUrl(url) {
  return /goo\.gl|maps\.app\.goo\.gl/.test(url);
}

function getCsrf() {
  const el = document.querySelector('[name=csrfmiddlewaretoken]');
  return el ? el.value : '';
}

// --- State ---
const state = { from: null, to: null, category: null, size: null, vehicle: null };

// --- DOM refs ---
const fromInput     = document.getElementById('p2p_from_input');
const fromClear     = document.getElementById('p2p_from_clear');
const fromDropdown  = document.getElementById('p2p_from_dropdown');
const fromResolved  = document.getElementById('p2p_from_resolved');
const toInput       = document.getElementById('p2p_to_input');
const toClear       = document.getElementById('p2p_to_clear');
const toDropdown    = document.getElementById('p2p_to_dropdown');
const toResolved    = document.getElementById('p2p_to_resolved');
const swapBtn       = document.getElementById('p2p_swap');
const resultEl      = document.getElementById('p2p_result');
const resultMetaEl  = document.getElementById('p2p_result_meta');
const chipsEl       = document.getElementById('p2p_popular_chips');
const catChipsEl    = document.getElementById('p2p_cat_chips');
const catSearch     = document.getElementById('p2p_cat_search');
const catClear      = document.getElementById('p2p_cat_clear');
const catDropdown   = document.getElementById('p2p_cat_dropdown');

// ==========================================================================
// CATEGORY
// ==========================================================================

function renderCategoryChips() {
  const popular = P2P_CATEGORIES.filter(c => c.popular);
  catChipsEl.innerHTML = popular.map(c =>
    `<button type="button" class="p2p__cat-chip" data-name="${c.name}">
       <i class="fa-solid ${c.icon}"></i> ${c.name}
     </button>`
  ).join('');

  catChipsEl.addEventListener('click', (e) => {
    const chip = e.target.closest('.p2p__cat-chip');
    if (!chip) return;
    selectCategory(chip.dataset.name);
  });
}

function selectCategory(name) {
  state.category = name;
  // Sync search input
  catSearch.value = name;
  catClear.classList.remove('d-none');
  closeCatDropdown();
  // Highlight chip
  catChipsEl.querySelectorAll('.p2p__cat-chip').forEach(ch => {
    ch.classList.toggle('p2p__cat-chip--active', ch.dataset.name === name);
  });
  refreshResult();
}

function clearCategory() {
  state.category = null;
  catSearch.value = '';
  catClear.classList.add('d-none');
  catChipsEl.querySelectorAll('.p2p__cat-chip').forEach(ch => ch.classList.remove('p2p__cat-chip--active'));
  refreshResult();
}

function openCatDropdown(items) {
  if (!items.length) { closeCatDropdown(); return; }
  catDropdown.innerHTML = items.map(c =>
    `<div class="p2p__cat-dropdown-item" data-name="${c.name}">
       <i class="fa-solid ${c.icon} p2p__cat-dropdown-icon"></i>
       <span>${c.name}</span>
     </div>`
  ).join('');
  catDropdown.classList.remove('d-none');
}

function closeCatDropdown() {
  catDropdown.classList.add('d-none');
  catDropdown.innerHTML = '';
}

catSearch.addEventListener('input', () => {
  const q = catSearch.value.trim().toLowerCase();
  if (!q) { closeCatDropdown(); return; }
  const matches = P2P_CATEGORIES.filter(c => c.name.toLowerCase().includes(q));
  openCatDropdown(matches);
});

catSearch.addEventListener('focus', () => {
  const q = catSearch.value.trim().toLowerCase();
  if (!q) openCatDropdown(P2P_CATEGORIES.filter(c => !c.popular));
});

catClear.addEventListener('click', () => clearCategory());

catDropdown.addEventListener('click', (e) => {
  const item = e.target.closest('.p2p__cat-dropdown-item');
  if (item) selectCategory(item.dataset.name);
});

// ==========================================================================
// SIZE
// ==========================================================================

function renderSizeCards() {
  document.querySelectorAll('.p2p__size-card').forEach(card => {
    card.addEventListener('click', () => {
      document.querySelectorAll('.p2p__size-card').forEach(c => c.classList.remove('p2p__size-card--active'));
      card.classList.add('p2p__size-card--active');
      state.size = { size: card.dataset.size, label: card.dataset.label };
      refreshResult();
    });
  });
}

function renderVehicleCards() {
  document.querySelectorAll('.p2p__vehicle-card').forEach(card => {
    card.addEventListener('click', () => {
      document.querySelectorAll('.p2p__vehicle-card').forEach(c => c.classList.remove('p2p__vehicle-card--active'));
      card.classList.add('p2p__vehicle-card--active');
      state.vehicle = card.dataset.label;
      refreshResult();
    });
  });
}

// ==========================================================================
// ZONE CHIPS
// ==========================================================================

function refreshZoneChips() {
  chipsEl.querySelectorAll('.p2p__chip').forEach(chip => {
    chip.classList.remove('p2p__chip--from', 'p2p__chip--to');
    const name = chip.dataset.name;
    if (state.from && state.from.label === name) chip.classList.add('p2p__chip--from');
    if (state.to   && state.to.label   === name) chip.classList.add('p2p__chip--to');
  });
}

function renderZoneChips() {
  chipsEl.innerHTML = P2P_POPULAR.map(loc =>
    `<button type="button" class="p2p__chip" data-name="${loc.name}" data-zone="${loc.zone}" data-lat="${loc.lat}" data-lng="${loc.lng}">
       ${loc.name}
     </button>`
  ).join('');

  chipsEl.addEventListener('click', (e) => {
    const chip = e.target.closest('.p2p__chip');
    if (!chip) return;
    const loc = { lat: parseFloat(chip.dataset.lat), lng: parseFloat(chip.dataset.lng), label: chip.dataset.name, sublabel: chip.dataset.zone };
    if (!state.from)      setLocation('from', loc);
    else if (!state.to)   setLocation('to',   loc);
    else                  setLocation('to',   loc);
  });
}

// ==========================================================================
// LOCATION
// ==========================================================================

function setLocation(field, loc) {
  state[field] = loc;
  const input    = field === 'from' ? fromInput    : toInput;
  const clearBtn = field === 'from' ? fromClear    : toClear;
  const dropdown = field === 'from' ? fromDropdown : toDropdown;
  const resolved = field === 'from' ? fromResolved : toResolved;

  input.value = loc.label;
  input.classList.add('p2p__loc-input--set');
  clearBtn.classList.remove('d-none');
  closeDropdown(dropdown);

  if (loc.sublabel) { resolved.textContent = loc.sublabel; resolved.classList.remove('d-none'); }
  else              { resolved.classList.add('d-none'); }

  refreshZoneChips();
  tryShowResult();
}

function clearLocation(field) {
  state[field] = null;
  const input    = field === 'from' ? fromInput    : toInput;
  const clearBtn = field === 'from' ? fromClear    : toClear;
  const resolved = field === 'from' ? fromResolved : toResolved;

  input.value = '';
  input.classList.remove('p2p__loc-input--set');
  clearBtn.classList.add('d-none');
  resolved.classList.add('d-none');
  resultEl.classList.add('d-none');
  refreshZoneChips();
}

// ==========================================================================
// RESULT
// ==========================================================================

function tryShowResult() {
  if (!state.from || !state.to || !state.size) {
    resultEl.classList.add('d-none');
    return;
  }

  // +20% over straight-line to approximate road distance
  const km = haversine(state.from.lat, state.from.lng, state.to.lat, state.to.lng) * 1.2;
  // Distance range buffer: +2 km short, +4 km medium, +8 km long
  const kmBuf  = km < 15 ? 2 : km < 25 ? 4 : 8;
  const kmLow  = Math.round(km);
  const kmHigh = kmLow + kmBuf;
  // Quote mode: medium/large/XL sizes or SUV/Van/Truck vehicles
  const needsQuote = ['m', 'l', 'xl'].includes(state.size.size) ||
                     (state.vehicle && ['SUV / Pickup', 'Van', 'Truck'].includes(state.vehicle));

  // Route display
  document.getElementById('p2p_result_from').textContent    = state.from.label;
  document.getElementById('p2p_result_to').textContent      = state.to.label;
  document.getElementById('p2p_result_km_low').textContent  = kmLow;
  document.getElementById('p2p_result_km_high').textContent = kmHigh;

  // Toggle price vs quote sections
  document.getElementById('p2p_price_section').classList.toggle('d-none', needsQuote);
  document.getElementById('p2p_quote_section').classList.toggle('d-none', !needsQuote);

  if (!needsQuote) {
    document.getElementById('p2p_result_price').textContent = getPrice(kmHigh);
  }

  // Meta row
  const catEl  = document.getElementById('p2p_result_category');
  const sizeEl = document.getElementById('p2p_result_size');
  catEl.textContent  = state.category ? `📦 ${state.category}` : '';
  sizeEl.textContent = [state.size ? state.size.label : '', state.vehicle ? `· ${state.vehicle}` : ''].filter(Boolean).join(' ');
  catEl.classList.toggle('d-none', !state.category);
  sizeEl.classList.toggle('d-none', !state.size && !state.vehicle);
  resultMetaEl.classList.toggle('d-none', !state.category && !state.size && !state.vehicle);

  // WhatsApp message
  let msg = needsQuote
    ? `Hi EzzyDelivery! I'd like to get a price for a P2P delivery.\n`
    : `Hi EzzyDelivery! I'd like to book a P2P delivery.\n`;
  if (state.category) msg += `Category: ${state.category}\n`;
  if (state.size)     msg += `Package size: ${state.size.label}\n`;
  if (state.vehicle)  msg += `Vehicle: ${state.vehicle}\n`;
  msg += `From: ${state.from.label}\nTo: ${state.to.label}\nDistance: ${kmLow}–${kmHigh} km\n`;
  msg += needsQuote ? `Please send me the price.` : `Price estimate: ${getPrice(kmHigh)} QR`;

  const waUrl = `https://wa.me/97466451589?text=${encodeURIComponent(msg)}`;
  document.getElementById(needsQuote ? 'p2p_wa_quote_btn' : 'p2p_wa_btn').href = waUrl;

  const wasHidden = resultEl.classList.contains('d-none');
  resultEl.classList.remove('d-none');
  if (wasHidden) resultEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function refreshResult() {
  tryShowResult();
}

// ==========================================================================
// DROPDOWN (locations)
// ==========================================================================

function openDropdown(dropdown, items, field, label) {
  if (!items.length) { closeDropdown(dropdown); return; }
  const header = label ? `<div class="p2p__dropdown-header">${label}</div>` : '';
  dropdown.innerHTML = header + items.slice(0, 8).map(loc =>
    `<div class="p2p__dropdown-item" data-field="${field}" data-name="${loc.name}" data-zone="${loc.zone}" data-lat="${loc.lat}" data-lng="${loc.lng}">
       <i class="fa-solid fa-location-dot p2p__dropdown-icon"></i>
       <span class="p2p__dropdown-name">${loc.name}</span>
       <span class="p2p__dropdown-zone">${loc.zone}</span>
     </div>`
  ).join('');
  dropdown.classList.remove('d-none');
}

function closeDropdown(dropdown) {
  dropdown.classList.add('d-none');
  dropdown.innerHTML = '';
}

function searchLocalities(q) {
  if (!q) return [];
  const lower = q.toLowerCase();
  return P2P_LOCALITIES.filter(loc =>
    loc.name.toLowerCase().includes(lower) || loc.zone.toLowerCase().includes(lower)
  );
}

// ==========================================================================
// INPUT WIRING
// ==========================================================================

async function handlePaste(field, text) {
  text = text.trim();
  const dropdown = field === 'from' ? fromDropdown : toDropdown;
  const input    = field === 'from' ? fromInput    : toInput;
  closeDropdown(dropdown);

  const coords = parseRawCoords(text);
  if (coords) {
    const loc = nearestLocality(coords.lat, coords.lng);
    setLocation(field, { lat: coords.lat, lng: coords.lng, label: loc ? loc.name : `${coords.lat}, ${coords.lng}`, sublabel: loc ? `Near ${loc.name} · ${loc.zone}` : '' });
    return;
  }
  if (!text.startsWith('http')) return;

  let url = text;
  if (isShortUrl(text)) {
    input.classList.add('p2p__loc-input--loading');
    try {
      const resp = await fetch('/p2p/pricing/resolve-url/', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() }, body: JSON.stringify({ url: text }) });
      const data = await resp.json();
      if (data.resolved_url) url = data.resolved_url;
    } catch (_) {}
    input.classList.remove('p2p__loc-input--loading');
  }

  const parsed = parseMapUrl(url);
  if (!parsed || parsed.lat < 24.4 || parsed.lat > 26.3 || parsed.lng < 50.7 || parsed.lng > 51.8) return;
  const loc = nearestLocality(parsed.lat, parsed.lng);
  setLocation(field, { lat: parsed.lat, lng: parsed.lng, label: loc ? loc.name : `${parsed.lat.toFixed(4)}, ${parsed.lng.toFixed(4)}`, sublabel: loc ? `Near ${loc.name} · ${loc.zone}` : 'Location from link' });
}

function wireField(field, input, clearBtn, dropdown) {
  input.addEventListener('focus', () => {
    if (!state[field] && !input.value) openDropdown(dropdown, P2P_POPULAR, field, 'Popular areas');
  });
  input.addEventListener('input', () => {
    if (state[field]) clearLocation(field);
    const q = input.value;
    if (!q.trim()) { openDropdown(dropdown, P2P_POPULAR, field, 'Popular areas'); return; }
    openDropdown(dropdown, searchLocalities(q), field);
  });
  input.addEventListener('paste', (e) => {
    const text = (e.clipboardData || window.clipboardData).getData('text');
    if (!text.trim().startsWith('http') && !parseRawCoords(text)) return;
    e.preventDefault();
    input.value = text.trim();
    handlePaste(field, text);
  });
  clearBtn.addEventListener('click', () => clearLocation(field));
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { closeDropdown(dropdown); input.blur(); }
  });
}

wireField('from', fromInput, fromClear, fromDropdown);
wireField('to',   toInput,   toClear,   toDropdown);

// Dropdown item click
document.addEventListener('click', (e) => {
  const item = e.target.closest('.p2p__dropdown-item');
  if (item) {
    setLocation(item.dataset.field, { lat: parseFloat(item.dataset.lat), lng: parseFloat(item.dataset.lng), label: item.dataset.name, sublabel: item.dataset.zone });
    return;
  }
  if (!e.target.closest('.p2p__loc-card')) { closeDropdown(fromDropdown); closeDropdown(toDropdown); }
  if (!e.target.closest('.p2p__cat-search-wrap')) closeCatDropdown();
});

// Swap
swapBtn.addEventListener('click', () => {
  const tmp = state.from;
  if (state.to) setLocation('from', state.to); else clearLocation('from');
  if (tmp)      setLocation('to',   tmp);       else clearLocation('to');
});

// ==========================================================================
// INIT
// ==========================================================================
renderCategoryChips();
renderSizeCards();
renderVehicleCards();
renderZoneChips();
