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
// Deliberately not a table here. The size cards are rendered server-side from
// p2p.models.P2P_SIZE_CARDS and carry their slug and label in data attributes, so this
// file reads the choice off the card the customer clicked instead of keeping a second
// copy of the five sizes to fall out of step with the booking form.

// --- Pricing ---
// The rate card is served from the database (window.P2P_PRICE_LADDER, injected by
// webpages.views.p2p_pricing) rather than hardcoded here, so an ops price change lands
// on this page without a deploy and the two can no longer drift. The resolution order
// below MUST match p2p/pricing.py resolve_band(): priority, then specificity, then the
// tightest distance ceiling. If they disagree, the customer is shown one number and
// charged another.
function rateBands() {
  return Array.isArray(window.P2P_PRICE_LADDER) ? window.P2P_PRICE_LADDER : [];
}

function bandMatches(band, { boxes, size, weightKg, vehicle, speed, km }) {
  if (boxes < band.min_boxes) return false;
  if (band.max_boxes !== null && boxes > band.max_boxes) return false;
  if (band.size && band.size !== size) return false;
  if (band.vehicle && band.vehicle !== vehicle) return false;
  if (band.speed && band.speed !== speed) return false;
  if (band.up_to_kg !== null) {
    if (weightKg === null || weightKg === undefined || weightKg > band.up_to_kg) return false;
  }
  if (band.up_to_km !== null && km > band.up_to_km) return false;
  return true;
}

function resolveBand(req) {
  const matches = rateBands().filter(b => bandMatches(b, req));
  if (!matches.length) return null;
  return matches.sort((a, b) => {
    if (a.priority !== b.priority) return b.priority - a.priority;
    if (a.specificity !== b.specificity) return b.specificity - a.specificity;
    const aKm = a.up_to_km === null ? Infinity : a.up_to_km;
    const bKm = b.up_to_km === null ? Infinity : b.up_to_km;
    return aKm - bKm;
  })[0];
}

// The box tiers, injected the same way as the ladder. The uplift is added on top of
// the resolved band, and a tier flagged needs_quote takes the whole job to a quote —
// exactly what p2p/pricing.py quote() does. Same reason as the ladder: the page must
// be able to reach the number the server is going to charge.
function boxTiers() {
  return Array.isArray(window.P2P_BOX_TIERS) ? window.P2P_BOX_TIERS : [];
}

// The most boxes of this size the vehicle takes, across both ceilings and the booking
// limit — the mirror of p2p.pricing.max_boxes_for. null when nothing can be said.
// bookingCap is P2P_MAX_BOXES, and it is optional for the same reason as in Python: as
// the denominator of a fill fraction it belongs, as a test of what a van can physically
// carry it does not. 0 means "cannot take even one", null means "nothing to say".
function maxBoxesFor(vehicle, size, bookingCap) {
  if (bookingCap === undefined) bookingCap = true;
  if (!vehicle) return null;
  let ceiling = boxLimit(vehicle, size);
  if (bookingCap) {
    ceiling = ceiling === null ? P2P_BOXES_MAX : Math.min(ceiling, P2P_BOXES_MAX);
  }
  const row = capacity().vehicles[vehicle];
  const per = capacity().sizes[size];
  if (per === undefined) return null;
  if (row !== undefined) {
    const fromVolume = Math.floor(row.capacity / per);
    ceiling = ceiling === null ? fromVolume : Math.min(ceiling, fromVolume);
  }
  return ceiling;
}

// How full the load leaves the vehicle, 0-1. Six medium boxes fill a car and a fifth of
// a van, which is why the slabs are fractions: one row means the same in both.
// A mixed load is the sum of its parts: three medium boxes and three small ones are half
// a car each, so together they are one full car. Infinity when the vehicle cannot take
// one of something in the load; null when there is no ceiling to be a fraction of.
function loadFill(vehicle, load, bookingCap) {
  let total = 0;
  for (const [size, n] of Object.entries(asLoad('', 1, load))) {
    const ceiling = maxBoxesFor(vehicle, size, bookingCap);
    if (ceiling === null) return null;
    if (ceiling === 0) return Infinity;
    total += n / ceiling;
  }
  return total || null;
}

function resolveBoxTier(boxes, weightKg, vehicle, size, load) {
  const spec = asLoad(size, boxes, load);
  boxes = loadBoxes(spec) || boxes;
  let fill = vehicle ? loadFill(vehicle, spec) : null;
  if (fill !== null && !Number.isFinite(fill)) fill = null;
  const covering = boxTiers().filter(t => {
    if (boxes < t.min_boxes) return false;
    if (t.max_boxes !== null && boxes > t.max_boxes) return false;
    // A fill-bounded row is skipped when there is no ceiling to be a fraction of.
    if (t.from_fill !== null || t.to_fill !== null) {
      if (fill === null) return false;
      if (t.from_fill !== null && fill <= t.from_fill) return false;
      if (t.to_fill !== null && fill > t.to_fill) return false;
    }
    // An unstated weight does not rule a weight-limited tier out — this page has no
    // weight field, and refusing them would zero the uplift on every quote it gives.
    if (t.up_to_kg !== null && weightKg !== null && weightKg !== undefined) {
      return weightKg <= t.up_to_kg;
    }
    return true;
  });
  if (!covering.length) return null;

  // needs_quote beats everything covering: a cheaper slab must not hand the customer an
  // automatic price for a job the card says a human prices.
  const quoting = covering.filter(t => t.needs_quote);
  const pool = quoting.length ? quoting : covering;

  // Narrowest across BOTH bounds, each as a fraction of all it could have covered and
  // the two multiplied — the same key, in the same order, as resolve_box_tier().
  const fillSpan = t => (t.from_fill === null && t.to_fill === null)
    ? 1
    : ((t.to_fill === null ? 1 : t.to_fill) - (t.from_fill === null ? 0 : t.from_fill));
  const countSpan = t => t.max_boxes === null
    ? 1
    : (t.max_boxes - t.min_boxes + 1) / P2P_BOXES_MAX;

  return pool.sort((a, b) => {
    const aN = fillSpan(a) * countSpan(a);
    const bN = fillSpan(b) * countSpan(b);
    if (aN !== bN) return aN - bN;
    if (fillSpan(a) !== fillSpan(b)) return fillSpan(a) - fillSpan(b);
    const aKg = a.up_to_kg === null ? 1e12 : a.up_to_kg;
    const bKg = b.up_to_kg === null ? 1e12 : b.up_to_kg;
    if (aKg !== bKg) return aKg - bKg;
    return b.min_boxes - a.min_boxes;
  })[0];
}

// --- Capacity ---
// What each vehicle holds and what each box takes up, injected by webpages.views. Three
// small boxes are 0.045 cbm and a motorcycle box is 0.027, so the page greys the bike out
// rather than showing a price p2p/pricing.py would refuse to honour.
function capacity() {
  return window.P2P_CAPACITY || { vehicles: {}, sizes: {} };
}

function loadCbm(size, boxes) {
  const per = capacity().sizes[size];
  return per === undefined ? null : per * Math.max(1, boxes);
}

// --- The load -----------------------------------------------------------------
// A job may be several sizes at once. One canonical shape, {size: count}, so nothing
// below needs a second code path — the mirror of p2p.pricing.as_load.
function asLoad(size, boxes, load) {
  if (load && Object.keys(load).length) {
    const out = {};
    for (const [s, n] of Object.entries(load)) { if (n > 0) out[s] = n; }
    return out;
  }
  return size ? { [size]: Math.max(1, boxes || 1) } : {};
}

function loadBoxes(load) {
  return Object.values(asLoad('', 1, load)).reduce((a, b) => a + b, 0);
}

// The biggest size present — the band a mixed job is priced on. Mirrors primary_size().
function primarySize(load) {
  const order = (capacity().order || ['xs', 's', 'm', 'l', 'xl']);
  const present = order.filter(s => asLoad('', 1, load)[s]);
  return present.length ? present[present.length - 1] : '';
}

function loadCbmOf(load) {
  let total = 0;
  for (const [size, n] of Object.entries(asLoad('', 1, load))) {
    const per = capacity().sizes[size];
    if (per === undefined) return null;
    total += per * n;
  }
  return total;
}

// The count ceiling, which the volume rule cannot express: a car takes six small boxes
// and three medium ones, and no single cbm figure refuses one without refusing the
// other. null = this pairing has no count rule and the volume decides alone.
function boxLimit(vehicle, size) {
  const forVehicle = (capacity().limits || {})[vehicle];
  if (!forVehicle) return null;
  const cap = forVehicle[size];
  return (cap === undefined || cap === null) ? null : cap;
}

function vehicleCanCarry(vehicle, size, boxes, load) {
  if (!vehicle) return true;
  const spec = asLoad(size, boxes, load);
  const fill = loadFill(vehicle, spec, false);
  if (fill !== null && fill > 1) return false;
  const row = capacity().vehicles[vehicle];
  const volume = loadCbmOf(spec);
  if (row === undefined || volume === null) return true;
  // Rounded to the millilitre: 3 × 0.015 must not fail a 0.045 vehicle on a float.
  return Math.round(volume * 1e6) <= Math.round(row.capacity * 1e6);
}

// The mirror of p2p.pricing.vehicle_verdict, and it answers in the same three parts:
// {ok, reason, needed}. It used to return the vehicle to use instead and null for "this
// one is right" — but "nothing can take this load" also has no vehicle to name, so a
// bulky item came back as null from the too-big branch and read as a clean bill for
// every vehicle on the page, motorcycle included. An objection and an approval must not
// be the same value.
function vehicleVerdict(vehicle, size, boxes, load) {
  const fine = () => ({ ok: true, reason: null, needed: null });
  if (!vehicle) return fine();
  const spec = asLoad(size, boxes, load);
  // needed stays null when nothing fits — that is a fact about the load, not an approval.
  const wrong = (reason) => ({ ok: false, reason, needed: smallestVehicleFor('', 1, spec) });

  // Count first, carried inside the fill fraction — mirrors vehicle_verdict().
  const fill = loadFill(vehicle, spec, false);
  if (fill !== null && fill > 1) return wrong('too_big');

  const row = capacity().vehicles[vehicle];
  const volume = loadCbmOf(spec);
  if (row === undefined || volume === null) return fine();

  if (Math.round(volume * 1e6) > Math.round(row.capacity * 1e6)) return wrong('too_big');

  if (row.minimum && Math.round(volume * 1e6) < Math.round(row.minimum * 1e6)) {
    const smaller = smallestVehicleFor('', 1, spec);
    const ladder = capacity().ladder || [];
    if (smaller && ladder.indexOf(smaller) < ladder.indexOf(vehicle)) {
      return { ok: false, reason: 'oversized', needed: smaller };
    }
  }
  return fine();
}

// The cheapest vehicle that can actually take this load — the mirror of
// p2p.pricing.smallest_vehicle_for, walking the same ladder and honouring the same
// size policy. "Any vehicle" is priced as whatever this returns.
function smallestVehicleFor(size, boxes, load) {
  const cap = capacity();
  const spec = asLoad(size, boxes, load);
  if (!Object.keys(spec).length) return null;
  const ladder = cap.ladder || [];

  // Allowed for EVERY size in the mix: one medium box keeps the whole job off a bike,
  // however many envelopes ride with it.
  let allowed = ladder.slice();
  for (const one of Object.keys(spec)) {
    const fits = (cap.fits && cap.fits[one]) || [];
    allowed = allowed.filter(v => fits.indexOf(v) !== -1);
  }
  for (const vehicle of ladder) {
    if (allowed.indexOf(vehicle) !== -1 && vehicleCanCarry(vehicle, '', 1, spec)) {
      return vehicle;
    }
  }
  return null;
}

// Hand the accepted quote to the booking form. Never includes a price: the only
// number that counts is the one p2p/pricing.py computes on the server.
function fillBookingForm(prefix) {
  const set = (suffix, value) => {
    const el = document.getElementById(prefix + suffix);
    if (el) el.value = value === null || value === undefined ? '' : value;
  };
  if (!state.from || !state.to) return;
  set('from_lat', state.from.lat);
  set('from_lng', state.from.lng);
  set('to_lat', state.to.lat);
  set('to_lng', state.to.lng);
  set('from_label', state.from.label);
  set('to_label', state.to.label);
  set('size', state.size ? state.size.size : '');
  set('vehicle', state.vehicle ? state.vehicle.vehicle : '');
  set('box_count', state.boxes);
  // The mix itself, so a job of two sizes arrives at the booking form as two sizes and
  // not as whichever one happened to be biggest. Every size is written, blank included:
  // a count left over from a load the customer has since cleared would otherwise ride
  // along and re-add the boxes they just removed.
  for (const size of SIZE_SLUGS) { set('load_' + size, state.load[size] || ''); }
  set('speed', state.speed ? state.speed.speed : 'express');
  set('return_trip', state.returnTrip ? '1' : '');
  set('category', state.category || '');
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
// speed is the one selection that starts made: express is what a customer wants unless
// they say otherwise, and a rate band can price the two differently.
// `load` is the job: {size: count}, so it can be two small and one medium. `size` and
// `boxes` are derived off it (largest size present, total count) and kept filled, so the
// band lookup and the summary line read the same way they always did.
const state = { from: null, to: null, category: null, size: null, vehicle: null,
                speed: { speed: 'express', label: 'Express' }, boxes: 1, load: {},
                // The leg back. Off by default, and a full second journey when it is on
                // — the same rule p2p.pricing.quote applies, or the two disagree.
                returnTrip: false };

// The rate card can carry a per-box band (min_boxes / max_boxes), so the count is a
// pricing input and not a note — it goes through resolveBand like every other choice.
// Injected from p2p.models.P2P_MAX_BOXES — the same ceiling the booking form validates
// and the accept view clamps to, rather than a third copy of the number.
const P2P_BOXES_MAX = window.P2P_MAX_BOXES || 20;

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

// state.load is the source of truth — {size: count}, so a job can be two small and one
// medium. state.size and state.boxes stay filled off it (largest size, total count),
// because the band is chosen on one size and the summary reads one number.
function syncLoadState() {
  const total = loadBoxes(state.load);
  const primary = primarySize(state.load);
  state.boxes = total || 1;
  state.size = primary
    ? { size: primary, label: SIZE_LABELS[primary] || primary }
    : null;
}

const SIZE_LABELS = {};

// Every size the page offers, in card order. Read off the DOM rather than restated here,
// so the list cannot drift from p2p.models.P2P_SIZE_CHOICES, which is what rendered them.
const SIZE_SLUGS = Array.from(document.querySelectorAll('.p2p__size-card'))
  .map(card => card.dataset.size);

function setSizeCount(size, n) {
  const clamped = Math.max(0, Math.min(P2P_BOXES_MAX, Math.round(n) || 0));
  if (clamped > 0) { state.load[size] = clamped; } else { delete state.load[size]; }

  // The whole job is capped, not each size: eleven small plus eleven medium is not two
  // bookable jobs. Trim the size just raised rather than silently rewriting the others.
  let total = loadBoxes(state.load);
  if (total > P2P_BOXES_MAX && state.load[size]) {
    state.load[size] = Math.max(0, state.load[size] - (total - P2P_BOXES_MAX));
    if (!state.load[size]) delete state.load[size];
  }

  syncLoadState();
  renderSizeCounts();
  refreshVehicleCapacity();
  refreshResult();
}

function renderSizeCounts() {
  document.querySelectorAll('.p2p__size-card').forEach(card => {
    const size = card.dataset.size;
    const n = state.load[size] || 0;
    card.classList.toggle('p2p__size-card--active', n > 0);
    const out = card.querySelector('.p2p__size-count');
    if (out) out.textContent = n;
    const minus = card.querySelector('.p2p__size-minus');
    if (minus) minus.disabled = n <= 0;
  });
  const total = loadBoxes(state.load);
  const totalEl = document.getElementById('p2p_load_total');
  if (totalEl) {
    const parts = [];
    if (total) {
      parts.push(`${total} box${total === 1 ? '' : 'es'}`);
      // The volume that load actually takes up. Worth printing because it is the number
      // the vehicles are measured in — a bike's box is 0.027 cbm — so the figure here is
      // the one deciding which cards grey out in step 4, off the same size table.
      const cbm = loadCbmOf(state.load);
      if (cbm !== null && cbm > 0) { parts.push(`${cbm.toFixed(3)} cbm`); }
      if (total >= P2P_BOXES_MAX) { parts.push('the most one job can be'); }
    }
    totalEl.textContent = parts.length ? parts.join(' · ') : 'Nothing added yet';
  }
}

function renderSizeCards() {
  document.querySelectorAll('.p2p__size-card').forEach(card => {
    SIZE_LABELS[card.dataset.size] = card.dataset.label;
    const size = card.dataset.size;

    // The card itself still works as a one-tap "this size, one box", which is what the
    // overwhelming majority of jobs are. The steppers are for the ones that are not.
    card.addEventListener('click', (e) => {
      if (e.target.closest('.p2p__size-step')) return;
      setSizeCount(size, (state.load[size] || 0) > 0 ? 0 : 1);
    });
    const minus = card.querySelector('.p2p__size-minus');
    const plus = card.querySelector('.p2p__size-plus');
    if (minus) minus.addEventListener('click', (e) => {
      e.stopPropagation(); setSizeCount(size, (state.load[size] || 0) - 1);
    });
    if (plus) plus.addEventListener('click', (e) => {
      e.stopPropagation(); setSizeCount(size, (state.load[size] || 0) + 1);
    });
  });
  renderSizeCounts();
}

// There is no separate box-count control any more. One field can hold one number, so a
// job counted on three cards left it stating a fourth — five small plus a medium plus a
// large read as "2" while the total underneath read 7. The count on each card IS the
// count, state.load is the whole of it, and state.boxes is derived (syncLoadState).

// Which vehicle cards the current size and box count rule out. Called whenever either
// changes: a bike selected for one box has to stop being selected at two, or the page
// would ask the server for a price it will not give.
function refreshVehicleCapacity() {
  const size = state.size ? state.size.size : null;
  const spec = state.load;
  if (!size) { return; }
  let cleared = false;
  document.querySelectorAll('.p2p__vehicle-card').forEach(card => {
    const slug = card.dataset.vehicle;
    const verdict = vehicleVerdict(slug, '', 1, spec);
    const ok = verdict.ok;
    card.classList.toggle('p2p__vehicle-card--over', !ok);
    card.disabled = !ok;
    card.title = ok ? ''
      : (verdict.reason === 'too_big'
        ? `Too small for ${state.boxes} × ${state.size.label}`
        : `More vehicle than ${state.boxes} × ${state.size.label} needs`)
        + (verdict.needed ? ` — use a ${verdict.needed}.` : '.');
    if (!ok && state.vehicle && state.vehicle.vehicle === slug) {
      card.classList.remove('p2p__vehicle-card--active');
      state.vehicle = null;
      cleared = true;
    }
  });
  const note = document.getElementById('p2p_vehicle_note');
  if (note) {
    const blocked = document.querySelectorAll('.p2p__vehicle-card--over').length;
    // Some loads have no vehicle the card prices automatically — a bulky item is the
    // whole of that case. Saying so beats a row of cards that all look equally right,
    // and beats greying every one of them: a van really can take it, we just agree the
    // price by hand, which is exactly what the result panel goes on to offer.
    const byHand = smallestVehicleFor('', 1, spec) === null;
    const load = `${state.boxes} × ${state.size.label.toLowerCase()}`;
    note.textContent = byHand
      ? `We match a vehicle to ${load} by hand — pick the one you think it needs, `
        + `or leave it to us, and we'll confirm the price.`
      : blocked ? `Greyed vehicles are not the right size for ${load}.` : '';
  }
  if (cleared) { refreshResult(); }
}

function renderVehicleCards() {
  document.querySelectorAll('.p2p__vehicle-card').forEach(card => {
    card.addEventListener('click', () => {
      if (card.classList.contains('p2p__vehicle-card--over')) { return; }
      document.querySelectorAll('.p2p__vehicle-card').forEach(c => c.classList.remove('p2p__vehicle-card--active'));
      card.classList.add('p2p__vehicle-card--active');
      // Slug for logic, label for display. Reading dataset.label into the pricing
      // rules is what made a copy edit a pricing change — rename "SUV / Pickup" and
      // that vehicle silently stopped needing a quote.
      state.vehicle = { vehicle: card.dataset.vehicle, label: card.dataset.label };
      refreshResult();
    });
  });
}

function renderSpeedCards() {
  document.querySelectorAll('.p2p__speed-card').forEach(card => {
    card.addEventListener('click', () => {
      document.querySelectorAll('.p2p__speed-card').forEach(c => c.classList.remove('p2p__speed-card--active'));
      card.classList.add('p2p__speed-card--active');
      // Slug for the rate card, label for display — the same split as the vehicle
      // cards, and for the same reason: a copy edit must not move a price.
      state.speed = { speed: card.dataset.speed, label: card.dataset.label };
      refreshResult();
    });
  });
}

// A second journey, not a preference: ticking it doubles the figure because the driver
// drives the route twice. The server prices it the same way (p2p.pricing.quote), and
// writes a second order for it.
function renderReturnCards() {
  document.querySelectorAll('.p2p__return-card').forEach(card => {
    card.addEventListener('click', () => {
      document.querySelectorAll('.p2p__return-card')
        .forEach(c => c.classList.remove('p2p__return-card--active'));
      card.classList.add('p2p__return-card--active');
      state.returnTrip = card.dataset.return === '1';
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
  // Quote mode now comes from the rate card, not from literals: a row flagged
  // needs_quote wins and there is no automatic price. Falling back to true when no
  // row matches is deliberate — an unpriceable request goes to a human rather than
  // silently taking whatever the ladder would have said.
  const chosen = state.vehicle ? state.vehicle.vehicle : '';
  // The load may simply not fit what they picked — the server refuses that outright,
  // so the page must not print a number for it either.
  const overCapacity = !vehicleVerdict(chosen, '', 1, state.load).ok;

  // "Any vehicle" is charged as the smallest that can carry the load: for one box that
  // is the card's blank-vehicle row, and when the count outgrows it the price moves to
  // the vehicle that has to do the job. Same rule as quote(), or the two disagree.
  let pricedAs = chosen;
  if (!chosen) {
    const needed = smallestVehicleFor('', 1, state.load);
    if (needed && needed !== smallestVehicleFor(state.size.size, 1)) { pricedAs = needed; }
  }

  const band = resolveBand({
    boxes: state.boxes,
    size: state.size.size,
    weightKg: null,
    vehicle: pricedAs,
    speed: state.speed ? state.speed.speed : 'express',
    km: kmHigh,
  });
  // The fill slabs are a fraction of the vehicle the job actually goes in, so the tier
  // needs a real one. pricedAs is not enough: it stays blank whenever the blank-vehicle
  // row already covers the load, and a blank vehicle has no ceiling to be a fraction of
  // — the uplift would vanish from every "any vehicle" quote. Mirrors quote()'s
  // tier_vehicle exactly, or the page and the server disagree on the price.
  const tierVehicle = pricedAs || smallestVehicleFor('', 1, state.load) || '';
  const tier = resolveBoxTier(state.boxes, null, tierVehicle, state.size.size, state.load);
  const needsQuote = overCapacity || !band || band.needs_quote
    || (tier !== null && tier.needs_quote);
  const uplift = tier && !tier.needs_quote ? tier.uplift : 0;

  // Route display
  document.getElementById('p2p_result_from').textContent    = state.from.label;
  document.getElementById('p2p_result_to').textContent      = state.to.label;
  document.getElementById('p2p_result_km_low').textContent  = kmLow;
  document.getElementById('p2p_result_km_high').textContent = kmHigh;

  // Toggle price vs quote sections
  document.getElementById('p2p_price_section').classList.toggle('d-none', needsQuote);
  document.getElementById('p2p_quote_section').classList.toggle('d-none', !needsQuote);

  // One leg, then the whole job. The leg back is the same route reversed carrying the
  // same load, so it resolves to the same band — quote() charges it twice and so does
  // this, or the page and the server print different numbers for the same booking.
  const legPrice = needsQuote ? null : band.price + uplift;
  const total = legPrice === null ? null : legPrice * (state.returnTrip ? 2 : 1);

  if (!needsQuote) {
    document.getElementById('p2p_result_price').textContent = total;
  }

  const returnEl = document.getElementById('p2p_result_return');
  const noteEl = document.getElementById('p2p_result_price_note');
  returnEl.classList.toggle('d-none', !state.returnTrip);
  if (state.returnTrip) {
    returnEl.textContent = legPrice === null
      ? `Plus the leg back to ${state.from.label}`
      : `Plus the leg back to ${state.from.label} — ${legPrice} QR of the total`;
  }
  if (noteEl) {
    noteEl.textContent = state.returnTrip
      ? 'two journeys, there and back · Qatar'
      : 'one-time delivery · Qatar';
  }

  // Meta row
  const catEl  = document.getElementById('p2p_result_category');
  const sizeEl = document.getElementById('p2p_result_size');
  catEl.textContent  = state.category ? `📦 ${state.category}` : '';
  sizeEl.textContent = [state.size ? state.size.label : '',
                        state.boxes > 1 ? `× ${state.boxes}` : '',
                        state.vehicle ? `· ${state.vehicle.label}` : '',
                        state.speed ? `· ${state.speed.label}` : '',
                        state.returnTrip ? '· Return trip' : ''].filter(Boolean).join(' ');
  catEl.classList.toggle('d-none', !state.category);
  sizeEl.classList.toggle('d-none', !state.size && !state.vehicle);
  resultMetaEl.classList.toggle('d-none', !state.category && !state.size && !state.vehicle);

  // WhatsApp message
  let msg = needsQuote
    ? `Hi EzzyDelivery! I'd like to get a price for a P2P delivery.\n`
    : `Hi EzzyDelivery! I'd like to book a P2P delivery.\n`;
  if (state.category) msg += `Category: ${state.category}\n`;
  if (state.size)     msg += `Package size: ${state.size.label}\n`;
  if (state.boxes > 1) msg += `Boxes: ${state.boxes}\n`;
  if (state.vehicle)  msg += `Vehicle: ${state.vehicle.label}\n`;
  if (state.speed)    msg += `When: ${state.speed.label}\n`;
  msg += `From: ${state.from.label}\nTo: ${state.to.label}\nDistance: ${kmLow}–${kmHigh} km\n`;
  if (state.returnTrip) msg += `Return trip: yes, bring something back to ${state.from.label}\n`;
  msg += needsQuote ? `Please send me the price.` : `Price estimate: ${total} QR`;

  const waUrl = `https://wa.me/97466451589?text=${encodeURIComponent(msg)}`;
  document.getElementById(needsQuote ? 'p2p_wa_quote_btn' : 'p2p_wa_btn').href = waUrl;

  // Carry the selection into the booking form. Coordinates and slugs only — the price
  // is deliberately absent, because the server recomputes it and would ignore ours.
  fillBookingForm(needsQuote ? 'p2p_qbook_' : 'p2p_book_');

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
renderSpeedCards();
renderReturnCards();
renderZoneChips();
