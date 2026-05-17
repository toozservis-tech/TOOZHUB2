/* Správa vozidel — Fáze 1 demo prototyp (bez závislostí, bez globálního znečištění). */
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
      emoji: '🚐',
      name: 'Volkswagen Transporter T5.1',
      plate: '2P4 3391',
      vin: 'WV2ZZZ7HZ9H123456',
      km: 245680,
      status: 'ok',
      statusLabel: 'V pořádku',
      stk: 'STK za 120 dní',
      insurance: 'Pojištění v pořádku',
      service: 'Servis v pořádku',
      lastService: 'Výměna oleje — před 8 měsíci',
    },
    {
      id: 'demo-sk',
      emoji: '🚙',
      name: 'Škoda Kodiaq 2.0 TDI 4x4',
      plate: '9A2 5518',
      vin: 'TMBLE9NSXKH789012',
      km: 128400,
      status: 'attention',
      statusLabel: 'Vyžaduje pozornost',
      stk: 'STK za 42 dní',
      insurance: 'Kontrola pojistky',
      service: 'Rozvody — naplánovat',
      lastService: 'Brzdy — před 5 měsíci',
    },
    {
      id: 'demo-bmw',
      emoji: '🚘',
      name: 'BMW 320d xDrive',
      plate: '5M2 1234',
      vin: 'WBA3B5C50EK345678',
      km: 198200,
      status: 'service',
      statusLabel: 'V servisu',
      stk: 'Po servisu ověřit STK',
      insurance: 'V pořádku',
      service: 'Servis — rozpracováno',
      lastService: 'Diagnostika — aktivní',
    },
  ];

  var DEMO_TIMELINE = [
    { title: 'Výměna brzd', when: '2026 · plán' },
    { title: 'STK / měření emisí', when: '2025 · za 42 dní' },
    { title: 'Olejový servis', when: '2025 · proběhlo' },
  ];

  var DEMO_UPCOMING = [
    { label: 'STK', value: 'za 42 dní' },
    { label: 'Pojištění', value: 'za 320 dní' },
    { label: 'Olej + filtr', value: 'za 5 600 km / 4 měsíce' },
  ];

  var DEMO_DOCS = [
    { name: 'Velký technický průkaz', state: 'Platný' },
    { name: 'Malý technický průkaz', state: 'Platný' },
    { name: 'Osmdová karta / ORV', state: 'Platný' },
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

  var NAV_ITEMS = [
    { key: 'overview', icon: '🏠', label: 'Přehled' },
    { key: 'vehicles', icon: '🚗', label: 'Moje vozidla' },
    { key: 'history', icon: '🔧', label: 'Servisní historie' },
    { key: 'reminders', icon: '⏰', label: 'Připomínky' },
    { key: 'documents', icon: '📄', label: 'Dokumenty' },
    { key: 'services', icon: '🏢', label: 'Servisy' },
    { key: 'invoices', icon: '🧾', label: 'Faktury' },
    { key: 'settings', icon: '⚙️', label: 'Nastavení' },
  ];

  var TAB_LABELS =
    'Přehled | Servisní historie | STK / tachometr | Dokumenty | Připomínky | Sdílení se servisy | Faktury'.split(
      ' | ',
    );

  var state = {
    activeNav: 'overview',
    view: 'dashboard',
    vehicleId: null,
    activeTabIdx: 0,
    toastTimer: null,
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
      return (
        '<button type="button" class="sv-prototype-nav-item' +
        active +
        '" data-sv-nav-key="' +
        escapeHtml(item.key) +
        '">' +
        '<span class="sv-prototype-nav-ico" aria-hidden="true">' +
        item.icon +
        '</span>' +
        escapeHtml(item.label) +
        '</button>'
      );
    }).join('');
  }

  function renderBottomNav(root) {
    var bot = root.querySelector('[data-sv-bottom-nav]');
    if (!bot) return;
    var keys = ['overview', 'vehicles', 'reminders', 'documents', 'settings'];
    var icons = ['🏠', '🚗', '⏰', '📄', '☰'];
    var labels = ['Přehled', 'Vozidla', 'Připomínky', 'Doklady', 'Menu'];
    bot.innerHTML = keys
      .map(function (key, idx) {
        var active = state.view === 'dashboard' && state.activeNav === key ? ' is-active' : '';
        return (
          '<button type="button" class="sv-prototype-bottom-item' +
          active +
          '" data-sv-bottom-key="' +
          key +
          '">' +
          '<span class="sv-prototype-bottom-ico" aria-hidden="true">' +
          icons[idx] +
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
        '<div class="sv-prototype-vehicle-photo" aria-hidden="true">' +
        v.emoji +
        '</div>' +
        '<div class="sv-prototype-vehicle-body">' +
        '<div class="sv-prototype-vehicle-head">' +
        '<h3>' +
        escapeHtml(v.name) +
        '</h3>' +
        '<span class="' +
        badgeClass(v.status) +
        '">' +
        escapeHtml(v.statusLabel) +
        '</span>' +
        '</div>' +
        '<div class="sv-prototype-vehicle-meta">' +
        '<div>SPZ: <strong>' +
        escapeHtml(v.plate) +
        '</strong></div>' +
        '<div>VIN: ' +
        escapeHtml(v.vin) +
        '</div>' +
        '<div>Nájezd: <strong>' +
        v.km.toLocaleString('cs-CZ') +
        ' km</strong></div>' +
        '</div>' +
        '<div class="sv-prototype-mini-status">' +
        '<span class="sv-prototype-mini-pill">STK · ' +
        escapeHtml(v.stk) +
        '</span>' +
        '<span class="sv-prototype-mini-pill">Pojištění</span>' +
        '<span class="sv-prototype-mini-pill">Servis</span>' +
        '</div>' +
        '<div class="sv-prototype-vehicle-actions">' +
        '<button type="button" class="sv-prototype-btn-small sv-prototype-btn-small--primary" data-sv-stop="1" data-sv-open-vehicle="' +
        escapeHtml(v.id) +
        '">Detail</button>' +
        '<button type="button" class="sv-prototype-btn-small" data-sv-stop="1" data-sv-mock-action="1">Přidat záznam</button>' +
        '<button type="button" class="sv-prototype-btn-small" data-sv-stop="1" data-sv-mock-action="1">Dokumenty</button>' +
        '<button type="button" class="sv-prototype-btn-small" data-sv-stop="1" data-sv-mock-action="1">Sdílet</button>' +
        '</div>' +
        '</div></article>'
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
      imgEl.innerHTML = '<span aria-hidden="true">' + v.emoji + '</span>';
    }
    if (titleEl) titleEl.textContent = v.name;
    if (metaEl) {
      metaEl.innerHTML =
        '<span>SPZ <strong>' +
        escapeHtml(v.plate) +
        '</strong></span>' +
        '<span>VIN ' +
        escapeHtml(v.vin) +
        '</span>' +
        '<span><strong>' +
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
        '<div class="sv-prototype-panel">' +
        '<h3>Časová osa vozidla</h3>' +
        '<div class="sv-prototype-timeline">' +
        DEMO_TIMELINE.map(function (t) {
          return (
            '<div class="sv-prototype-timeline-item">' +
            '<strong>' +
            escapeHtml(t.title) +
            '</strong>' +
            '<span>' +
            escapeHtml(t.when) +
            '</span></div>'
          );
        }).join('') +
        '</div></div>' +
        '<div class="sv-prototype-panel">' +
        '<h3>Poslední servisní úkon</h3>' +
        '<p style="margin:0;font-size:0.9rem;color:var(--sv-muted);">' +
        escapeHtml(v.lastService) +
        '</p>' +
        '<button type="button" class="sv-prototype-btn-primary" style="margin-top:0.75rem;" data-sv-mock-action="1">Zobrazit detail</button>' +
        '</div>' +
        '<div class="sv-prototype-panel">' +
        '<h3>Blížící se termíny</h3>' +
        '<ul class="sv-prototype-list-compact">' +
        DEMO_UPCOMING.map(function (u) {
          return (
            '<li><span>' +
            escapeHtml(u.label) +
            '</span><strong>' +
            escapeHtml(u.value) +
            '</strong></li>'
          );
        }).join('') +
        '</ul></div>' +
        '<div class="sv-prototype-panel">' +
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
        '</div>';
    }

    var access = root.querySelector('[data-sv-detail-access]');
    if (access) {
      access.innerHTML =
        '<div class="sv-prototype-access-panel">' +
        '<h3>Kdo má přístup k tomuto vozidlu</h3>' +
        DEMO_ACCESS.map(function (a) {
          return (
            '<div class="sv-prototype-access-service">' +
            '<h4>' +
            escapeHtml(a.name) +
            '</h4>' +
            '<div class="sv-prototype-access-row">' +
            '<span>' +
            escapeHtml(a.accessType) +
            '</span>' +
            '<span class="' +
            accessBadgeClass(a.badgeKind) +
            '">' +
            escapeHtml(a.badge) +
            '</span></div>' +
            '<div class="sv-prototype-access-actions">' +
            '<button type="button" class="sv-prototype-btn-small" data-sv-mock-action="1">Akce</button>' +
            '</div></div>'
          );
        }).join('') +
        '<button type="button" class="sv-prototype-btn-primary" style="width:100%;margin-top:0.35rem;" data-sv-mock-action="1">+ Přidat servis</button>' +
        '<div class="sv-prototype-toggle-row">' +
        '<span>Povolit detailní historii</span>' +
        '<button type="button" class="sv-prototype-switch is-on" aria-pressed="true" data-sv-toggle-demo="1"></button>' +
        '</div></div>';
    }
  }

  function syncViews(root) {
    var dash = root.querySelector('[data-sv-view-dashboard]');
    var det = root.querySelector('[data-sv-view-detail]');
    if (dash) dash.hidden = state.view !== 'dashboard';
    if (det) det.hidden = state.view !== 'detail';
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
        state.vehicleId = openV.getAttribute('data-sv-open-vehicle');
        state.view = 'detail';
        state.activeTabIdx = 0;
        syncViews(root);
        renderDetail(root);
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
        state.vehicleId = card.getAttribute('data-sv-open-vehicle');
        state.view = 'detail';
        state.activeTabIdx = 0;
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
      '<div class="sv-prototype-brand">Správa vozidel</div>' +
      '<nav class="sv-prototype-nav" data-sv-nav></nav>' +
      '<div class="sv-prototype-sidebar-foot">' +
      '<button type="button" class="sv-prototype-btn-ghost" data-sv-mock-action="1">Sbalit</button>' +
      '</div></aside>' +
      '<div class="sv-prototype-main">' +
      '<header class="sv-prototype-topbar">' +
      '<div class="sv-prototype-search">' +
      '<label class="sr-only" for="sv-proto-search">Hledat vozidlo</label>' +
      '<input id="sv-proto-search" type="search" autocomplete="off" placeholder="Hledat podle SPZ, VIN nebo názvu vozidla…" data-sv-mock-action="1" />' +
      '</div>' +
      '<button type="button" class="sv-prototype-btn-primary" data-sv-mock-action="1">+ Přidat vozidlo</button>' +
      '<div class="sv-prototype-top-actions">' +
      '<button type="button" class="sv-prototype-icon-btn" aria-label="Oznámení" data-sv-mock-action="1">🔔' +
      '<span class="sv-prototype-badge-count">3</span></button>' +
      '<button type="button" class="sv-prototype-profile" data-sv-mock-action="1">' +
      '<span class="sv-prototype-avatar">TN</span>' +
      '<span>' +
      escapeHtml(DEMO_USER.firstName + ' ' + DEMO_USER.lastName) +
      ' ▾</span></button></div></header>' +
      '<div class="sv-prototype-scroll">' +
      '<div class="sv-prototype-view" data-sv-view-dashboard>' +
      '<div class="sv-prototype-hero">' +
      '<div class="sv-prototype-hero-copy">' +
      '<h1>Dobrý den, ' +
      escapeHtml(DEMO_USER.firstName) +
      ' 👋</h1>' +
      '<p>Máte ' +
      DEMO_SUMMARY.vehicles +
      ' vozidla, ' +
      DEMO_SUMMARY.stkSoon +
      ' blížící se STK a ' +
      DEMO_SUMMARY.reminders +
      ' aktivní připomínky.</p>' +
      '</div>' +
      '<div class="sv-prototype-hero-visual">' +
      '<div class="sv-prototype-hero-car"><span class="sv-prototype-hero-car-placeholder" aria-hidden="true">🚙</span></div>' +
      '<div class="sv-prototype-quick-cards">' +
      '<div class="sv-prototype-quick-card"><strong>STK do 42 dnů</strong><span>Nejbližší lhůta u Kodiaqu</span></div>' +
      '<div class="sv-prototype-quick-card"><strong>Pojištění v pořádku</strong><span>Všechna vozidla krytá</span></div>' +
      '<div class="sv-prototype-quick-card"><strong>Poslední servis před 3 měsíci</strong><span>Olej u Transporteru</span></div>' +
      '</div></div></div>' +
      '<h2 class="sv-prototype-section-title">Moje vozidla</h2>' +
      '<div class="sv-prototype-vehicle-grid" data-sv-vehicle-grid></div></div>' +
      '<div class="sv-prototype-view" data-sv-view-detail hidden>' +
      '<button type="button" class="sv-prototype-back" data-sv-back>← Zpět na přehled</button>' +
      '<div class="sv-prototype-detail-header">' +
      '<div class="sv-prototype-detail-photo" data-sv-detail-photo></div>' +
      '<div><div style="display:flex;align-items:center;gap:0.65rem;flex-wrap:wrap;margin-bottom:0.35rem;">' +
      '<h2 data-sv-detail-title></h2>' +
      '<span data-sv-detail-badge class="sv-prototype-badge"></span></div>' +
      '<div class="sv-prototype-detail-meta" data-sv-detail-meta></div>' +
      '<div class="sv-prototype-tabs" data-sv-detail-tabs></div></div></div>' +
      '<div class="sv-prototype-detail-grid">' +
      '<div data-sv-detail-overview></div>' +
      '<div data-sv-detail-access></div></div></div></div></div>' +
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
