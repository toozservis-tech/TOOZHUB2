/* Správa vozidel — izolovaný vizuální prototyp (bez API, bez emoji v hlavních plochách). */
(function () {
  'use strict';

  var DEMO_USER = { firstName: 'Tomáš', lastName: 'Novák' };
  var DEMO_SUMMARY = {
    vehicles: 3,
    stkSoon: 1,
    reminders: 2,
  };

  var DEMO_VEHICLES = [
    {
      id: 'demo-vw',
      kind: 'van',
      name: 'Volkswagen Transporter T5.1',
      plate: '5M2 1234',
      vin: 'WV2ZZZ7HZ9H123456',
      km: 245680,
      status: 'ok',
      statusLabel: 'V pořádku',
      stk: 'za 42 dní',
      insurance: 'Platné',
      service: 'v pořádku',
      lastService: 'Výměna brzdových destiček — před 3 měsíci',
    },
    {
      id: 'demo-sk',
      kind: 'suv',
      name: 'Škoda Kodiaq 2.0 TDI 4x4',
      plate: '9A2 5518',
      vin: 'TMBLE9NSXKH789012',
      km: 128400,
      status: 'attention',
      statusLabel: 'Vyžaduje pozornost',
      stk: 'za 98 dní',
      insurance: 'Kontrola smlouvy',
      service: 'naplánovat rozvody',
      lastService: 'Brzdy — před 5 měsíci',
    },
    {
      id: 'demo-bmw',
      kind: 'sedan',
      name: 'BMW 320d xDrive',
      plate: '2P4 3391',
      vin: 'WBA3B5C50EK345678',
      km: 198200,
      status: 'service',
      statusLabel: 'V servisu',
      stk: 'po servisu',
      insurance: 'v pořádku',
      service: 'rozpracováno',
      lastService: 'Diagnostika — probíhá',
    },
  ];

  var DEMO_TIMELINE = [
    { title: 'Výměna brzd', when: '2026 · plán', kind: 'planned' },
    { title: 'STK / měření emisí', when: '2025 · za 42 dní', kind: 'upcoming' },
    { title: 'Olejový servis', when: '2025 · proběhlo', kind: 'done' },
  ];

  var DEMO_UPCOMING = [
    { label: 'STK', value: 'za 42 dní', tone: 'warn' },
    { label: 'Pojištění', value: 'za 320 dní', tone: 'ok' },
    { label: 'Olejový servis', value: 'za 5 600 km / 4 měs.', tone: 'neutral' },
  ];

  var DEMO_DOCS = [
    { name: 'Velký technický průkaz', state: 'Platný' },
    { name: 'Malý technický průkaz', state: 'Platný' },
    { name: 'Prot. STK a emisí', state: 'Platný' },
    { name: 'Pojistka / ORV', state: 'Platný' },
  ];

  var DEMO_ACCESS = [
    {
      name: 'TooZServis',
      accessType: 'Plný přístup k vozidlu',
      badge: 'Schváleno',
      badgeKind: 'ok',
    },
    {
      name: 'AutoPoint Praha',
      accessType: 'Základní přístup',
      badge: 'Čeká na schválení',
      badgeKind: 'warn',
    },
    {
      name: 'Pneu Expert',
      accessType: 'Bez přístupu',
      badge: 'Odmítnuto',
      badgeKind: 'danger',
    },
  ];

  var DEMO_ACTIVE_SERVICES = [
    { name: 'TooZServis', detail: 'Plný přístup · schváleno' },
    { name: 'AutoPoint Praha', detail: 'Žádost o rozšíření' },
  ];

  var NAV_ITEMS = [
    { key: 'overview', label: 'Přehled', ico: 'home' },
    { key: 'vehicles', label: 'Moje vozidla', ico: 'car' },
    { key: 'history', label: 'Servisní historie', ico: 'wrench' },
    { key: 'reminders', label: 'Připomínky', ico: 'bell' },
    { key: 'documents', label: 'Dokumenty', ico: 'doc' },
    { key: 'services', label: 'Servisy', ico: 'building' },
    { key: 'invoices', label: 'Faktury', ico: 'invoice' },
    { key: 'settings', label: 'Nastavení', ico: 'gear' },
  ];

  var TAB_LABELS =
    'Přehled | Servisní historie | STK / tachometr | Dokumenty | Připomínky | Sdílení se servisy | Faktury'.split(
      ' | ',
    );

  var ICO = {
    home: '<svg class="sv-prototype-svg-ico" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z"/></svg>',
    car: '<svg class="sv-prototype-svg-ico" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M18.92 6.01C18.72 5.42 18.16 5 17.5 5h-11c-.66 0-1.21.42-1.42 1.01L3 12v8c0 .55.45 1 1 1h1c.55 0 1-.45 1-1v-1h12v1c0 .55.45 1 1 1h1c.55 0 1-.45 1-1v-8l-2.08-5.99zM6.5 16c-.83 0-1.5-.67-1.5-1.5S5.67 13 6.5 13s1.5.67 1.5 1.5S7.33 16 6.5 16zm11 0c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5zM5 11l1.5-4.5h11L19 11H5z"/></svg>',
    wrench:
      '<svg class="sv-prototype-svg-ico" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M22.7 19l-9.1-9.1c.9-2.3.4-5-1.5-6.9-2-2-5-2.4-7.4-1.3L9 6 6 9 1.6 4.7C.4 7.1.9 10.1 2.9 12.1c1.9 1.9 4.6 2.4 6.9 1.5l9.1 9.1c.4.4 1 .4 1.4 0l2.3-2.3c.5-.4.5-1.1.1-1.4z"/></svg>',
    bell: '<svg class="sv-prototype-svg-ico" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 22c1.1 0 2-.9 2-2h-4c0 1.1.89 2 2 2zm6-6v-5c0-3.07-1.64-5.64-4.5-6.32V4c0-.83-.67-1.5-1.5-1.5s-1.5.67-1.5 1.5v.68C7.63 5.36 6 7.92 6 11v5l-2 2v1h16v-1l-2-2z"/></svg>',
    doc: '<svg class="sv-prototype-svg-ico" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M14 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z"/></svg>',
    building:
      '<svg class="sv-prototype-svg-ico" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 7V3H2v18h20V7H12zM6 19H4v-2h2v2zm0-4H4v-2h2v2zm0-4H4V9h2v2zm0-4H4V5h2v2zm4 12H8v-2h2v2zm0-4H8v-2h2v2zm0-4H8V9h2v2zm0-4H8V5h2v2zm10 12h-8v-2h2v-2h-2v-2h2v-2h-2V9h8v10zm-2-8h-2v2h2v-2zm0 4h-2v2h2v-2z"/></svg>',
    invoice:
      '<svg class="sv-prototype-svg-ico" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z"/></svg>',
    gear: '<svg class="sv-prototype-svg-ico" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M19.14 12.94c.04-.31.06-.63.06-.94 0-.31-.02-.63-.06-.94l2.03-1.58c.18-.14.23-.41.12-.61l-1.92-3.32c-.12-.22-.37-.29-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54c-.04-.24-.24-.41-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.04.31-.06.63-.06.94s.02.63.06.94l-2.03 1.58c-.18.14-.23.41-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z"/></svg>',
    search:
      '<svg class="sv-prototype-search-ico" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M15.5 14h-.79l-.28-.27A6.471 6.471 0 0016 9.5 6.5 6.5 0 109.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/></svg>',
    quickStk:
      '<svg class="sv-prototype-quick-ico" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M11.99 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 11.99 2zM12 20c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8zm.5-13H11v6l5.25 3.15.75-1.23-4.5-2.67z"/></svg>',
    quickShield:
      '<svg class="sv-prototype-quick-ico" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4zm0 10.99h7c-.53 4.12-3.28 7.79-7 8.94V12H5V6.3l7-3.11v8.8z"/></svg>',
    quickSvc:
      '<svg class="sv-prototype-quick-ico" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M22.7 19l-9.1-9.1c.9-2.3.4-5-1.5-6.9-2-2-5-2.4-7.4-1.3L9 6 6 9 1.6 4.7C.4 7.1.9 10.1 2.9 12.1c1.9 1.9 4.6 2.4 6.9 1.5l9.1 9.1c.4.4 1 .4 1.4 0l2.3-2.3c.5-.4.5-1.1.1-1.4z"/></svg>',
    bellRing:
      '<svg class="sv-prototype-svg-ico" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 22c1.1 0 2-.9 2-2h-4c0 1.1.89 2 2 2zm6-6v-5c0-3.07-1.64-5.64-4.5-6.32V4c0-.83-.67-1.5-1.5-1.5s-1.5.67-1.5 1.5v.68C7.63 5.36 6 7.92 6 11v5l-2 2v1h16v-1l-2-2z"/></svg>',
    menu: '<svg class="sv-prototype-svg-ico" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M3 18h18v-2H3v2zm0-5h18v-2H3v2zm0-7v2h18V6H3z"/></svg>',
  };

  function heroCarSvg() {
    return (
      '<svg class="sv-prototype-hero-car-svg" viewBox="0 0 400 160" aria-hidden="true" focusable="false">' +
      '<defs><linearGradient id="svH1" x1="0%" y1="0%" x2="100%" y2="100%">' +
      '<stop offset="0%" stop-color="#1e3a8a"/><stop offset="100%" stop-color="#2563eb"/></linearGradient>' +
      '<linearGradient id="svH2" x1="0%" y1="0%" x2="0%" y2="100%">' +
      '<stop offset="0%" stop-color="#93c5fd"/><stop offset="100%" stop-color="#1d4ed8"/></linearGradient></defs>' +
      '<ellipse cx="200" cy="125" rx="170" ry="12" fill="rgba(11,31,122,0.08)"/>' +
      '<path d="M55 95 L115 75 L260 72 L335 82 L360 98 L360 112 L45 112 Z" fill="url(#svH1)"/>' +
      '<path d="M120 78 L240 76 L310 84 L318 98 L105 100 Z" fill="url(#svH2)" opacity="0.85"/>' +
      '<rect x="135" y="82" width="48" height="22" rx="4" fill="rgba(255,255,255,0.25)"/>' +
      '<rect x="245" y="84" width="40" height="18" rx="3" fill="rgba(255,255,255,0.2)"/>' +
      '<circle cx="115" cy="112" r="14" fill="#1e293b"/><circle cx="115" cy="112" r="6" fill="#64748b"/>' +
      '<circle cx="285" cy="112" r="14" fill="#1e293b"/><circle cx="285" cy="112" r="6" fill="#64748b"/>' +
      '<circle cx="340" cy="108" r="10" fill="#1e293b"/><circle cx="340" cy="108" r="4" fill="#64748b"/>' +
      '</svg>'
    );
  }

  function vehicleSilhouette(kind, uid) {
    var u = (uid || 'x').replace(/[^a-z0-9]/gi, '');
    var gVan = 'svGv' + u;
    var gSuv = 'svGs' + u;
    var gSed = 'svGd' + u;
    if (kind === 'van') {
      return (
        '<svg class="sv-prototype-card-car" viewBox="0 0 280 100" aria-hidden="true">' +
        '<defs><linearGradient id="' +
        gVan +
        '" x1="0" y1="0" x2="1" y2="1">' +
        '<stop offset="0%" stop-color="#1e40af"/><stop offset="100%" stop-color="#3b82f6"/></linearGradient></defs>' +
        '<path fill="url(#' +
        gVan +
        ')" d="M20 58 L70 40 L210 38 L248 48 L262 62 L262 72 L18 72 Z"/>' +
        '<rect x="95" y="44" width="36" height="18" rx="2" fill="rgba(255,255,255,0.35)"/>' +
        '<circle cx="65" cy="72" r="11" fill="#1e293b"/><circle cx="210" cy="72" r="11" fill="#1e293b"/></svg>'
      );
    }
    if (kind === 'suv') {
      return (
        '<svg class="sv-prototype-card-car" viewBox="0 0 280 100" aria-hidden="true">' +
        '<defs><linearGradient id="' +
        gSuv +
        '" x1="0" y1="0" x2="1" y2="1">' +
        '<stop offset="0%" stop-color="#0f172a"/><stop offset="100%" stop-color="#475569"/></linearGradient></defs>' +
        '<path fill="url(#' +
        gSuv +
        ')" d="M28 62 L95 45 L188 42 L245 52 L258 64 L258 74 L22 74 Z"/>' +
        '<path fill="rgba(255,255,255,0.2)" d="M105 48 L175 46 L220 54 L225 64 L100 66 Z"/>' +
        '<circle cx="85" cy="74" r="10" fill="#1e293b"/><circle cx="215" cy="74" r="10" fill="#1e293b"/></svg>'
      );
    }
    return (
      '<svg class="sv-prototype-card-car" viewBox="0 0 280 100" aria-hidden="true">' +
      '<defs><linearGradient id="' +
      gSed +
      '" x1="0" y1="0" x2="1" y2="1">' +
      '<stop offset="0%" stop-color="#111827"/><stop offset="100%" stop-color="#6b7280"/></linearGradient></defs>' +
      '<path fill="url(#' +
      gSed +
      ')" d="M22 60 L88 48 L200 46 L252 56 L262 68 L262 76 L20 76 Z"/>' +
      '<path fill="rgba(255,255,255,0.22)" d="M110 50 L195 48 L235 58 L238 68 L108 70 Z"/>' +
      '<circle cx="75" cy="76" r="9" fill="#1e293b"/><circle cx="210" cy="76" r="9" fill="#1e293b"/></svg>'
    );
  }

  function detailVehicleSvg(kind, uid) {
    return vehicleSilhouette(kind || 'sedan', uid);
  }

  var state = {
    activeNav: 'overview',
    view: 'dashboard',
    vehicleId: null,
    activeTabIdx: 0,
    toastTimer: null,
    cardFlashTimer: null,
  };

  function escapeHtml(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function showToast(message) {
    var host = document.querySelector('.sv-prototype-toast-host');
    if (!host) return;
    host.textContent = message;
    host.classList.add('is-visible');
    clearTimeout(state.toastTimer);
    state.toastTimer = setTimeout(function () {
      host.classList.remove('is-visible');
    }, 3200);
  }

  function badgeClass(status) {
    if (status === 'ok') return 'sv-prototype-badge sv-prototype-badge--ok';
    if (status === 'attention') return 'sv-prototype-badge sv-prototype-badge--warn';
    return 'sv-prototype-badge sv-prototype-badge--danger';
  }

  function accessBadgeClass(kind) {
    if (kind === 'ok') return 'sv-prototype-badge sv-prototype-badge--ok';
    if (kind === 'warn') return 'sv-prototype-badge sv-prototype-badge--warn';
    return 'sv-prototype-badge sv-prototype-badge--danger';
  }

  function vehicleVisualClass(kind) {
    var k = kind === 'van' || kind === 'suv' || kind === 'sedan' ? kind : 'sedan';
    return 'sv-prototype-vehicle-visual sv-vehicle-visual sv-vehicle-' + k;
  }

  function onProtoAction(ev) {
    if (ev) ev.preventDefault();
    showToast('Tato akce je v prototypu pouze vizuální.');
  }

  function getVehicle(id) {
    for (var i = 0; i < DEMO_VEHICLES.length; i++) {
      if (DEMO_VEHICLES[i].id === id) return DEMO_VEHICLES[i];
    }
    return null;
  }

  function renderNav(root) {
    var nav = root.querySelector('[data-sv-nav]');
    if (!nav) return;
    nav.innerHTML = NAV_ITEMS.map(function (item) {
      var active = state.activeNav === item.key ? ' is-active' : '';
      var svg = ICO[item.ico] || ICO.home;
      return (
        '<button type="button" class="sv-prototype-nav-item' +
        active +
        '" data-sv-nav-key="' +
        escapeHtml(item.key) +
        '">' +
        '<span class="sv-prototype-nav-ico-wrap" aria-hidden="true">' +
        svg +
        '</span>' +
        '<span class="sv-prototype-nav-label">' +
        escapeHtml(item.label) +
        '</span></button>'
      );
    }).join('');
  }

  function renderBottomNav(root) {
    var bot = root.querySelector('[data-sv-bottom-nav]');
    if (!bot) return;
    var keys = ['overview', 'vehicles', 'reminders', 'documents', 'settings'];
    var mapIco = { overview: 'home', vehicles: 'car', reminders: 'bell', documents: 'doc', settings: 'menu' };
    var labels = ['Přehled', 'Vozidla', 'Připomínky', 'Dokumenty', 'Menu'];
    bot.innerHTML = keys
      .map(function (key, idx) {
        var active = state.view === 'dashboard' && state.activeNav === key ? ' is-active' : '';
        var svg = ICO[mapIco[key]] || ICO.home;
        return (
          '<button type="button" class="sv-prototype-bottom-item' +
          active +
          '" data-sv-bottom-key="' +
          key +
          '">' +
          '<span class="sv-prototype-bottom-ico-wrap" aria-hidden="true">' +
          svg +
          '</span>' +
          escapeHtml(labels[idx]) +
          '</button>'
        );
      })
      .join('');
  }

  function renderVehicleCards(root) {
    var grid = root.querySelector('[data-sv-vehicle-grid]');
    if (!grid) return;
    grid.innerHTML = DEMO_VEHICLES.map(function (v) {
      return (
        '<article class="sv-prototype-vehicle-card" data-sv-open-vehicle="' +
        escapeHtml(v.id) +
        '" tabindex="0" role="button">' +
        '<div class="' +
        vehicleVisualClass(v.kind) +
        '" aria-hidden="true">' +
        '<div class="sv-prototype-vehicle-visual-sky"></div>' +
        '<div class="sv-prototype-vehicle-visual-ground"></div>' +
        '<div class="sv-prototype-vehicle-visual-car">' +
        vehicleSilhouette(v.kind, v.id) +
        '</div></div>' +
        '<div class="sv-prototype-vehicle-body">' +
        '<div class="sv-prototype-vehicle-head">' +
        '<h3 class="sv-prototype-vehicle-title">' +
        escapeHtml(v.name) +
        '</h3>' +
        '<span class="' +
        badgeClass(v.status) +
        '">' +
        escapeHtml(v.statusLabel) +
        '</span></div>' +
        '<div class="sv-prototype-vehicle-subrow">' +
        '<span class="sv-prototype-plate-badge">' +
        escapeHtml(v.plate) +
        '</span></div>' +
        '<div class="sv-prototype-vehicle-meta">' +
        '<div class="sv-prototype-meta-row"><span class="sv-prototype-meta-k">VIN</span><span class="sv-prototype-meta-v">' +
        escapeHtml(v.vin) +
        '</span></div>' +
        '<div class="sv-prototype-meta-row"><span class="sv-prototype-meta-k">Nájezd</span><span class="sv-prototype-meta-v"><strong>' +
        v.km.toLocaleString('cs-CZ') +
        ' km</strong></span></div></div>' +
        '<div class="sv-prototype-status-lines">' +
        '<div class="sv-prototype-status-line"><span>STK</span><strong>' +
        escapeHtml(v.stk) +
        '</strong></div>' +
        '<div class="sv-prototype-status-line"><span>Pojištění</span><strong>' +
        escapeHtml(v.insurance) +
        '</strong></div>' +
        '<div class="sv-prototype-status-line"><span>Servis</span><strong>' +
        escapeHtml(v.service) +
        '</strong></div></div>' +
        '<div class="sv-prototype-vehicle-actions">' +
        '<button type="button" class="sv-prototype-veh-ico" title="Detail" data-sv-stop="1" data-sv-open-vehicle="' +
        escapeHtml(v.id) +
        '">' +
        ICO.doc +
        '<span class="sv-prototype-veh-ico-label">Detail</span></button>' +
        '<button type="button" class="sv-prototype-veh-ico" title="Přidat záznam" data-sv-stop="1" data-sv-mock-action="1">' +
        ICO.quickSvc +
        '<span class="sv-prototype-veh-ico-label">Přidat záznam</span></button>' +
        '<button type="button" class="sv-prototype-veh-ico" title="Dokumenty" data-sv-stop="1" data-sv-mock-action="1">' +
        ICO.invoice +
        '<span class="sv-prototype-veh-ico-label">Dokumenty</span></button>' +
        '<button type="button" class="sv-prototype-veh-ico" title="Sdílet" data-sv-stop="1" data-sv-mock-action="1">' +
        '<svg class="sv-prototype-svg-ico" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M18 16.08c-.76 0-1.44.3-1.96.77L8.91 12.7c.05-.23.09-.46.09-.7s-.04-.47-.09-.7l7.05-4.11c.54.5 1.25.81 2.04.81 1.66 0 3-1.34 3-3s-1.34-3-3-3-3 1.34-3 3c0 .24.04.47.09.7L8.04 9.81C7.5 9.31 6.79 9 6 9c-1.66 0-3 1.34-3 3s1.34 3 3 3c.79 0 1.5-.31 2.04-.81l7.12 4.16c-.05.21-.08.43-.08.65 0 1.61 1.31 2.92 2.92 2.92s2.92-1.31 2.92-2.92-1.31-2.92-2.92-2.92z"/></svg>' +
        '<span class="sv-prototype-veh-ico-label">Sdílet</span></button>' +
        '</div></div></article>'
      );
    }).join('');
  }

  function renderDetail(root) {
    var v = getVehicle(state.vehicleId);
    if (!v) return;
    var imgEl = root.querySelector('[data-sv-detail-photo]');
    var titleEl = root.querySelector('[data-sv-detail-title]');
    var metaEl = root.querySelector('[data-sv-detail-meta]');
    var badgeEl = root.querySelector('[data-sv-detail-badge]');
    if (imgEl) {
      imgEl.className = 'sv-prototype-detail-photo ' + vehicleVisualClass(v.kind);
      imgEl.innerHTML =
        '<div class="sv-prototype-vehicle-visual-sky"></div>' +
        '<div class="sv-prototype-vehicle-visual-ground"></div>' +
        '<div class="sv-prototype-detail-car-wrap">' +
        detailVehicleSvg(v.kind, v.id) +
        '</div>';
    }
    if (titleEl) titleEl.textContent = v.name;
    if (metaEl) {
      metaEl.innerHTML =
        '<span class="sv-prototype-detail-plate">' +
        escapeHtml(v.plate) +
        '</span>' +
        '<span class="sv-prototype-detail-vin">VIN ' +
        escapeHtml(v.vin) +
        '</span>' +
        '<span class="sv-prototype-detail-km"><strong>' +
        v.km.toLocaleString('cs-CZ') +
        ' km</strong></span>';
    }
    if (badgeEl) {
      badgeEl.className = badgeClass(v.status);
      badgeEl.textContent = v.statusLabel;
    }

    var tabs = root.querySelector('[data-sv-detail-tabs]');
    if (tabs) {
      tabs.innerHTML = TAB_LABELS.map(function (label, idx) {
        var ac = idx === state.activeTabIdx ? ' is-active' : '';
        return (
          '<button type="button" class="sv-prototype-tab' +
          ac +
          '" data-sv-tab="' +
          idx +
          '">' +
          escapeHtml(label) +
          '</button>'
        );
      }).join('');
    }

    var overview = root.querySelector('[data-sv-detail-overview]');
    if (overview) {
      overview.innerHTML =
        '<div class="sv-prototype-panel sv-prototype-panel--elevated sv-prototype-panel--timeline">' +
        '<h3>Časová osa vozidla</h3>' +
        '<div class="sv-prototype-timeline">' +
        DEMO_TIMELINE.map(function (t) {
          var dot =
            t.kind === 'done'
              ? ' sv-prototype-timeline-dot--done'
              : t.kind === 'upcoming'
                ? ' sv-prototype-timeline-dot--soon'
                : ' sv-prototype-timeline-dot--planned';
          return (
            '<div class="sv-prototype-timeline-item">' +
            '<span class="sv-prototype-timeline-dot' +
            dot +
            '" aria-hidden="true"></span>' +
            '<div class="sv-prototype-timeline-body">' +
            '<strong>' +
            escapeHtml(t.title) +
            '</strong>' +
            '<span>' +
            escapeHtml(t.when) +
            '</span></div></div>'
          );
        }).join('') +
        '</div></div>';
    }

    var col2 = root.querySelector('[data-sv-detail-col2]');
    if (col2) {
      col2.innerHTML =
        '<div class="sv-prototype-panel sv-prototype-panel--elevated">' +
        '<h3>Poslední servisní úkon</h3>' +
        '<div class="sv-prototype-last-svc">' +
        '<div class="sv-prototype-last-svc-thumb" aria-hidden="true">' +
        '<svg class="sv-prototype-thumb-ico" viewBox="0 0 24 24"><path fill="currentColor" d="M22.7 19l-9.1-9.1c.9-2.3.4-5-1.5-6.9-2-2-5-2.4-7.4-1.3L9 6 6 9 1.6 4.7C.4 7.1.9 10.1 2.9 12.1c1.9 1.9 4.6 2.4 6.9 1.5l9.1 9.1c.4.4 1 .4 1.4 0l2.3-2.3c.5-.4.5-1.1.1-1.4z"/></svg></div>' +
        '<div class="sv-prototype-last-svc-body">' +
        '<p class="sv-prototype-last-svc-text">' +
        escapeHtml(v.lastService) +
        '</p>' +
        '<button type="button" class="sv-prototype-btn-primary sv-prototype-btn-compact" data-sv-mock-action="1">Zobrazit detail</button>' +
        '</div></div></div>' +
        '<div class="sv-prototype-panel sv-prototype-panel--elevated">' +
        '<h3>Blížící se termíny</h3>' +
        '<ul class="sv-prototype-list-compact">' +
        DEMO_UPCOMING.map(function (u) {
          var cls =
            u.tone === 'warn'
              ? ' class="sv-prototype-upcoming-val--warn"'
              : u.tone === 'ok'
                ? ' class="sv-prototype-upcoming-val--ok"'
                : '';
          return (
            '<li><span>' +
            escapeHtml(u.label) +
            '</span><strong' +
            cls +
            '>' +
            escapeHtml(u.value) +
            '</strong></li>'
          );
        }).join('') +
        '</ul></div>' +
        '<div class="sv-prototype-panel sv-prototype-panel--elevated">' +
        '<h3>Stav dokumentů</h3>' +
        DEMO_DOCS.map(function (d) {
          return (
            '<div class="sv-prototype-doc-row">' +
            '<span>' +
            escapeHtml(d.name) +
            '</span>' +
            '<span class="sv-prototype-badge sv-prototype-badge--ok">' +
            escapeHtml(d.state) +
            '</span></div>'
          );
        }).join('') +
        '</div>' +
        '<div class="sv-prototype-panel sv-prototype-panel--elevated">' +
        '<h3>Aktivní servisy s přístupem</h3>' +
        '<ul class="sv-prototype-active-svc-list">' +
        DEMO_ACTIVE_SERVICES.map(function (s) {
          return (
            '<li><strong>' +
            escapeHtml(s.name) +
            '</strong><span>' +
            escapeHtml(s.detail) +
            '</span></li>'
          );
        }).join('') +
        '</ul></div>';
    }

    var col3 = root.querySelector('[data-sv-detail-col3]');
    if (col3) {
      col3.innerHTML =
        '<div class="sv-prototype-access-panel sv-prototype-panel--elevated">' +
        '<h3>Kdo má přístup k tomuto vozidlu</h3>' +
        DEMO_ACCESS.map(function (a) {
          return (
            '<div class="sv-prototype-access-service">' +
            '<div class="sv-prototype-access-service-top">' +
            '<h4>' +
            escapeHtml(a.name) +
            '</h4>' +
            '<button type="button" class="sv-prototype-access-menu" aria-label="Menu" data-sv-mock-action="1">' +
            '<span></span><span></span><span></span></button></div>' +
            '<div class="sv-prototype-access-row">' +
            '<span class="sv-prototype-access-type">' +
            escapeHtml(a.accessType) +
            '</span>' +
            '<span class="' +
            accessBadgeClass(a.badgeKind) +
            '">' +
            escapeHtml(a.badge) +
            '</span></div></div>'
          );
        }).join('') +
        '<button type="button" class="sv-prototype-btn-primary sv-prototype-btn-add-svc" data-sv-mock-action="1">+ Přidat servis</button>' +
        '<div class="sv-prototype-toggle-row">' +
        '<div class="sv-prototype-toggle-copy"><strong>Povolit detailní historii</strong>' +
        '<span class="sv-prototype-toggle-hint">Servisy uvidí plnou historii vč. faktur</span></div>' +
        '<button type="button" class="sv-prototype-switch is-on" aria-pressed="true" data-sv-toggle-demo="1"></button>' +
        '</div></div>';
    }
  }

  function syncViews(root) {
    var dash = root.querySelector('[data-sv-view-dashboard]');
    var det = root.querySelector('[data-sv-view-detail]');
    if (dash) {
      dash.hidden = state.view !== 'dashboard';
      dash.classList.toggle('sv-prototype-view--entering', state.view === 'dashboard');
    }
    if (det) {
      det.hidden = state.view !== 'detail';
      det.classList.toggle('sv-prototype-view--entering', state.view === 'detail');
    }
    window.requestAnimationFrame(function () {
      if (dash) dash.classList.remove('sv-prototype-view--entering');
      if (det) det.classList.remove('sv-prototype-view--entering');
    });
  }

  function flashCard(root, id) {
    var cards = root.querySelectorAll('.sv-prototype-vehicle-card');
    for (var i = 0; i < cards.length; i++) {
      cards[i].classList.remove('is-focused');
    }
    var el = root.querySelector('[data-sv-open-vehicle="' + id + '"]');
    if (!el) return;
    el.classList.add('is-focused');
    clearTimeout(state.cardFlashTimer);
    state.cardFlashTimer = setTimeout(function () {
      el.classList.remove('is-focused');
    }, 420);
  }

  function bind(root) {
    root.addEventListener('click', function (ev) {
      var t = ev.target;
      if (!t || !t.closest) return;
      var stopBtn = t.closest('[data-sv-stop]');
      var navItem = t.closest('[data-sv-nav-key]');
      var bottom = t.closest('[data-sv-bottom-key]');
      var openV = t.closest('[data-sv-open-vehicle]');
      var back = t.closest('[data-sv-back]');
      var mock = t.closest('[data-sv-mock-action]');
      var tab = t.closest('[data-sv-tab]');
      var toggle = t.closest('[data-sv-toggle-demo]');
      var fab = t.closest('[data-sv-fab]');
      var quick = t.closest('[data-sv-quick-mock]');

      if (navItem) {
        state.activeNav = navItem.getAttribute('data-sv-nav-key') || 'overview';
        renderNav(root);
        renderBottomNav(root);
        if (state.activeNav !== 'overview' && state.activeNav !== 'vehicles') onProtoAction();
        return;
      }
      if (bottom) {
        state.activeNav = bottom.getAttribute('data-sv-bottom-key') || 'overview';
        state.view = 'dashboard';
        renderNav(root);
        renderBottomNav(root);
        syncViews(root);
        if (state.activeNav !== 'overview' && state.activeNav !== 'vehicles') onProtoAction();
        return;
      }
      if (openV) {
        if (stopBtn) ev.stopPropagation();
        var vid = openV.getAttribute('data-sv-open-vehicle');
        state.vehicleId = vid;
        state.view = 'detail';
        state.activeTabIdx = 0;
        flashCard(root, vid);
        syncViews(root);
        renderDetail(root);
        var sc = root.querySelector('.sv-prototype-scroll');
        if (sc) sc.scrollTop = 0;
        return;
      }
      if (back) {
        state.view = 'dashboard';
        state.vehicleId = null;
        syncViews(root);
        return;
      }
      if (tab) {
        state.activeTabIdx = parseInt(tab.getAttribute('data-sv-tab'), 10) || 0;
        renderDetail(root);
        if (state.activeTabIdx > 0) showToast('Záložka „' + TAB_LABELS[state.activeTabIdx] + '“ — pouze vizuální prototyp.');
        return;
      }
      if (quick) {
        onProtoAction(ev);
        return;
      }
      if (mock) {
        onProtoAction(ev);
        return;
      }
      if (toggle) {
        toggle.classList.toggle('is-on');
        toggle.setAttribute('aria-pressed', toggle.classList.contains('is-on') ? 'true' : 'false');
        showToast('Přepínač je v prototypu pouze vizuální.');
        return;
      }
      if (fab) {
        onProtoAction(ev);
        return;
      }
    });

    root.addEventListener(
      'keydown',
      function (ev) {
        if (ev.key !== 'Enter' && ev.key !== ' ') return;
        var card = ev.target && ev.target.closest ? ev.target.closest('[data-sv-open-vehicle]') : null;
        if (!card || ev.target.closest('.sv-prototype-vehicle-actions')) return;
        ev.preventDefault();
        var vid = card.getAttribute('data-sv-open-vehicle');
        state.vehicleId = vid;
        state.view = 'detail';
        state.activeTabIdx = 0;
        flashCard(root, vid);
        syncViews(root);
        renderDetail(root);
      },
      true,
    );
  }

  function mount(container) {
    container.className = 'sv-prototype';
    container.innerHTML =
      '<div class="sv-prototype-inner">' +
      '<div class="sv-prototype-shell">' +
      '<aside class="sv-prototype-sidebar" aria-label="Hlavní navigace">' +
      '<div class="sv-prototype-brand">' +
      '<span class="sv-prototype-brand-mark" aria-hidden="true">' +
      ICO.car +
      '</span>' +
      '<span class="sv-prototype-brand-text"><span class="sv-prototype-brand-line1">Správa</span> <span class="sv-prototype-brand-line2">vozidel</span></span></div>' +
      '<nav class="sv-prototype-nav" data-sv-nav></nav>' +
      '<div class="sv-prototype-sidebar-foot">' +
      '<button type="button" class="sv-prototype-btn-ghost" data-sv-mock-action="1">Sbalit</button>' +
      '</div></aside>' +
      '<div class="sv-prototype-main">' +
      '<header class="sv-prototype-topbar">' +
      '<div class="sv-prototype-search">' +
      '<span class="sv-prototype-search-icon" aria-hidden="true">' +
      ICO.search +
      '</span>' +
      '<label class="sr-only" for="sv-proto-search">Hledat vozidlo</label>' +
      '<input id="sv-proto-search" type="search" autocomplete="off" placeholder="Hledat podle SPZ, VIN…" data-sv-mock-action="1" />' +
      '</div>' +
      '<button type="button" class="sv-prototype-btn-primary sv-prototype-btn-add-vehicle" data-sv-mock-action="1">' +
      '<span class="sv-prototype-btn-label-full">+ Přidat vozidlo</span>' +
      '<span class="sv-prototype-btn-label-short">+ Přidat</span></button>' +
      '<div class="sv-prototype-top-actions">' +
      '<button type="button" class="sv-prototype-icon-btn" aria-label="Oznámení" data-sv-mock-action="1">' +
      ICO.bellRing +
      '<span class="sv-prototype-badge-count">3</span></button>' +
      '<button type="button" class="sv-prototype-profile" data-sv-mock-action="1">' +
      '<span class="sv-prototype-avatar">TN</span>' +
      '<span class="sv-prototype-profile-name">' +
      escapeHtml(DEMO_USER.firstName + ' ' + DEMO_USER.lastName) +
      '</span><span class="sv-prototype-profile-caret" aria-hidden="true">▾</span></button></div></header>' +
      '<div class="sv-prototype-scroll">' +
      '<div class="sv-prototype-view" data-sv-view-dashboard>' +
      '<div class="sv-prototype-hero-bundle">' +
      '<div class="sv-prototype-hero-panel">' +
      '<div class="sv-prototype-hero-copy">' +
      '<h1>Dobrý den, ' +
      escapeHtml(DEMO_USER.firstName) +
      'i 👋</h1>' +
      '<p class="sv-prototype-hero-summary">Máte <span class="sv-prototype-stat sv-prototype-stat--navy">' +
      DEMO_SUMMARY.vehicles +
      '</span> vozidla, ' +
      '<span class="sv-prototype-stat sv-prototype-stat--amber">' +
      DEMO_SUMMARY.stkSoon +
      '</span> blížící se STK a ' +
      '<span class="sv-prototype-stat sv-prototype-stat--blue">' +
      DEMO_SUMMARY.reminders +
      '</span> aktivní připomínky.</p>' +
      '</div>' +
      '<div class="sv-prototype-hero-art" aria-hidden="true">' +
      '<div class="sv-prototype-hero-landscape"></div>' +
      '<div class="sv-prototype-hero-car-wrap">' +
      heroCarSvg() +
      '</div></div></div>' +
      '<div class="sv-prototype-quick-cards">' +
      '<button type="button" class="sv-prototype-quick-tile sv-prototype-quick-tile--stk" data-sv-quick-mock="1">' +
      '<span class="sv-prototype-quick-ico-wrap">' +
      ICO.quickStk +
      '</span>' +
      '<span class="sv-prototype-quick-body"><strong>STK do 42 dnů</strong>' +
      '<span class="sv-prototype-quick-desc">VW Transporter · zbývá lhůta</span></span>' +
      '<span class="sv-prototype-quick-arrow" aria-hidden="true">→</span></button>' +
      '<button type="button" class="sv-prototype-quick-tile sv-prototype-quick-tile--ok" data-sv-quick-mock="1">' +
      '<span class="sv-prototype-quick-ico-wrap">' +
      ICO.quickShield +
      '</span>' +
      '<span class="sv-prototype-quick-body"><strong>Pojištění v pořádku</strong>' +
      '<span class="sv-prototype-quick-desc">Všechna vozidla krytá</span></span>' +
      '<span class="sv-prototype-quick-arrow" aria-hidden="true">→</span></button>' +
      '<button type="button" class="sv-prototype-quick-tile" data-sv-quick-mock="1">' +
      '<span class="sv-prototype-quick-ico-wrap">' +
      ICO.quickSvc +
      '</span>' +
      '<span class="sv-prototype-quick-body"><strong>Poslední servis před 3 měsíci</strong>' +
      '<span class="sv-prototype-quick-desc">VW Transporter T5.1</span></span>' +
      '<span class="sv-prototype-quick-arrow" aria-hidden="true">→</span></button>' +
      '</div></div>' +
      '<h2 class="sv-prototype-section-title">Moje vozidla</h2>' +
      '<div class="sv-prototype-vehicle-grid" data-sv-vehicle-grid></div></div>' +
      '<div class="sv-prototype-view" data-sv-view-detail hidden>' +
      '<button type="button" class="sv-prototype-back" data-sv-back>← Zpět na přehled</button>' +
      '<div class="sv-prototype-detail-header">' +
      '<div class="sv-prototype-detail-photo" data-sv-detail-photo></div>' +
      '<div class="sv-prototype-detail-head-copy">' +
      '<div class="sv-prototype-detail-title-row">' +
      '<h2 data-sv-detail-title></h2>' +
      '<span data-sv-detail-badge class="sv-prototype-badge"></span></div>' +
      '<div class="sv-prototype-detail-meta" data-sv-detail-meta></div>' +
      '<div class="sv-prototype-tabs" data-sv-detail-tabs></div></div></div>' +
      '<div class="sv-prototype-detail-grid">' +
      '<div class="sv-prototype-detail-col sv-prototype-detail-col--timeline" data-sv-detail-overview></div>' +
      '<div class="sv-prototype-detail-col sv-prototype-detail-col--main" data-sv-detail-col2></div>' +
      '<div class="sv-prototype-detail-col sv-prototype-detail-col--aside" data-sv-detail-col3></div></div></div></div></div>' +
      '<nav class="sv-prototype-bottom-nav" data-sv-bottom-nav aria-label="Mobilní navigace"></nav>' +
      '<button type="button" class="sv-prototype-fab" data-sv-fab aria-label="Přidat">+</button>' +
      '<div class="sv-prototype-toast-host" role="status" aria-live="polite"></div></div>';

    state.activeNav = 'overview';
    state.view = 'dashboard';
    renderNav(container);
    renderBottomNav(container);
    renderVehicleCards(container);
    syncViews(container);
    bind(container);
  }

  function ready(fn) {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fn);
    else fn();
  }

  ready(function () {
    var el = document.getElementById('sv-prototype-root');
    if (el) mount(el);
  });
})();
