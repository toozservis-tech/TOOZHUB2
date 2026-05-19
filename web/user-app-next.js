(function () {
  'use strict';

  const STATE = {
    installed: false,
    renderToken: 0,
    lastVehicles: [],
    latestData: null,
    vehiclesFilter: 'all',
    vehiclesSort: 'activity',
    vehiclesSearchQuery: '',
    detailModal: { open: false, vehicleId: null, activeTab: 'tech', vehicle: null, records: [], optionsOpen: false },
    attentionModalOpen: false,
    attentionItems: [],
    legacyDetailReadyFor: null,
    legacyMount: { tabId: null },
    originalShowVehicleDetail: null,
    modalEscBound: false,
    viewOverride: null,
    remindersTipHidden: false,
    serviceHistoryLimit: 8,
    serviceHistoryFilters: { vehicle: 'all', period: '2y', type: 'all', service: 'all', docStatus: 'all' },
  };

  const DETAIL_MODAL_ID = 'uappNextVehicleDetail';
  const ATTENTION_MODAL_ID = 'uappNextAttentionModal';

  const LOGO_SRC = '/web/assets/landing/sprava-vozidel-logo.jpeg';
  const USER_APP_SCREEN_ID = 'userAppNextScreen';

  const ICO = {
    home: '<svg class="uapp-next-svg" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z"/></svg>',
    car: '<svg class="uapp-next-svg" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M18.92 6.01C18.72 5.42 18.16 5 17.5 5h-11c-.66 0-1.21.42-1.42 1.01L3 12v8c0 .55.45 1 1 1h1c.55 0 1-.45 1-1v-1h12v1c0 .55.45 1 1 1h1c.55 0 1-.45 1-1v-8l-2.08-5.99zM6.5 16c-.83 0-1.5-.67-1.5-1.5S5.67 13 6.5 13s1.5.67 1.5 1.5S7.33 16 6.5 16zm11 0c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5zM5 11l1.5-4.5h11L19 11H5z"/></svg>',
    wrench: '<svg class="uapp-next-svg" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M22.7 19l-9.1-9.1c.9-2.3.4-5-1.5-6.9-2-2-5-2.4-7.4-1.3L9 6 6 9 1.6 4.7C.4 7.1.9 10.1 2.9 12.1c1.9 1.9 4.6 2.4 6.9 1.5l9.1 9.1c.4.4 1 .4 1.4 0l2.3-2.3c.5-.4.5-1.1.1-1.4z"/></svg>',
    bell: '<svg class="uapp-next-svg" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 22c1.1 0 2-.9 2-2h-4c0 1.1.89 2 2 2zm6-6v-5c0-3.07-1.64-5.64-4.5-6.32V4c0-.83-.67-1.5-1.5-1.5s-1.5.67-1.5 1.5v.68C7.63 5.36 6 7.92 6 11v5l-2 2v1h16v-1l-2-2z"/></svg>',
    doc: '<svg class="uapp-next-svg" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M14 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z"/></svg>',
    building: '<svg class="uapp-next-svg" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 7V3H2v18h20V7H12zM6 19H4v-2h2v2zm0-4H4v-2h2v2zm0-4H4V9h2v2zm0-4H4V5h2v2zm4 12H8v-2h2v2zm0-4H8v-2h2v2zm0-4H8V9h2v2zm0-4H8V5h2v2zm10 12h-8v-2h2v-2h-2v-2h2v-2h-2V9h8v10zm-2-8h-2v2h2v-2zm0 4h-2v2h2v-2z"/></svg>',
    invoice: '<svg class="uapp-next-svg" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z"/></svg>',
    gear: '<svg class="uapp-next-svg" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M19.14 12.94c.04-.31.06-.63.06-.94 0-.31-.02-.63-.06-.94l2.03-1.58c.18-.14.23-.41.12-.61l-1.92-3.32c-.12-.22-.37-.29-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54c-.04-.24-.24-.41-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.04.31-.06.63-.06.94s.02.63.06.94l-2.03 1.58c-.18.14-.23.41-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z"/></svg>',
    search: '<svg class="uapp-next-search-ico" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M15.5 14h-.79l-.28-.27A6.471 6.471 0 0016 9.5 6.5 6.5 0 109.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/></svg>',
    quickStk: '<svg class="uapp-next-quick-ico" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M11.99 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 11.99 2zM12 20c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8zm.5-13H11v6l5.25 3.15.75-1.23-4.5-2.67z"/></svg>',
    quickShield: '<svg class="uapp-next-quick-ico" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4zm0 10.99h7c-.53 4.12-3.28 7.79-7 8.94V12H5V6.3l7-3.11v8.8z"/></svg>',
    share: '<svg class="uapp-next-svg" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M18 16.08c-.76 0-1.44.3-1.96.77L8.91 12.7c.05-.23.09-.46.09-.7s-.04-.47-.09-.7l7.05-4.11c.54.5 1.25.81 2.04.81 1.66 0 3-1.34 3-3s-1.34-3-3-3-3 1.34-3 3c0 .24.04.47.09.7L8.04 9.81C7.5 9.31 6.79 9 6 9c-1.66 0-3 1.34-3 3s1.34 3 3 3c.79 0 1.5-.31 2.04-.81l7.12 4.16c-.05.21-.08.43-.08.65 0 1.61 1.31 2.92 2.92 2.92s2.92-1.31 2.92-2.92-1.31-2.92-2.92-2.92z"/></svg>',
    detail: '<svg class="uapp-next-svg" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z"/></svg>',
    edit: '<svg class="uapp-next-svg" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04c.39-.39.39-1.02 0-1.41l-2.34-2.34c-.39-.39-1.02-.39-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/></svg>',
    upload: '<svg class="uapp-next-svg" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M9 16h6v-6h4l-7-7-7 7h4v6zm-4 2h14v2H5v-2z"/></svg>',
    odometer: '<svg class="uapp-next-svg" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm.5-13H11v6l5.25 3.15.75-1.23-4.5-2.67V7z"/></svg>',
    pdf: '<svg class="uapp-next-svg" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M14 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z"/></svg>',
    qr: '<svg class="uapp-next-svg" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M3 3h8v8H3V3zm2 2v4h4V5H5zm8-2h8v8h-8V3zm2 2v4h4V5h-4zM3 13h8v8H3v-8zm2 2v4h4v-4H5zm13-2h3v2h-3v-2zM14 13h2v3h-2v-3zm3 3h2v2h-2v-2zm-3 0h2v2h-2v-2zm3 3h2v3h-2v-3zm-3 0h2v2h-2v-2z"/></svg>',
    checkOk: '<svg class="uapp-next-overall-ico uapp-next-overall-ico--ok" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/></svg>',
    checkWarn: '<svg class="uapp-next-overall-ico uapp-next-overall-ico--warn" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z"/></svg>',
  };

  const PLATE_EU_STARS_SVG = (function buildPlateEuStarsSvg() {
    const cx = 9;
    const cy = 9;
    const r = 5.15;
    const star = 'M0,-0.95 L0.22,-0.3 L0.95,-0.3 L0.36,0.12 L0.58,0.82 L0,0.38 L-0.58,0.82 L-0.36,0.12 L-0.95,-0.3 L-0.22,-0.3 Z';
    let paths = '';
    for (let i = 0; i < 12; i += 1) {
      const rad = ((i * 30) - 90) * (Math.PI / 180);
      const x = cx + r * Math.cos(rad);
      const y = cy + r * Math.sin(rad);
      paths += `<path d="${star}" transform="translate(${x.toFixed(2)} ${y.toFixed(2)}) scale(0.36)"/>`;
    }
    return `<svg class="uapp-plate__eu-stars" viewBox="0 0 18 18" xmlns="http://www.w3.org/2000/svg" aria-hidden="true"><g fill="#FFCC00">${paths}</g></svg>`;
  })();

  function hasFn(name) {
    return typeof window[name] === 'function';
  }

  function esc(value) {
    if (typeof window.escapeHtml === 'function') {
      return window.escapeHtml(value == null ? '' : String(value));
    }
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function user() {
    try {
      return typeof currentUser !== 'undefined' ? currentUser : null;
    } catch (_) {
      return null;
    }
  }

  function apiReady() {
    return typeof apiCall === 'function';
  }

  function isAuthed() {
    try {
      return typeof isAuthenticated === 'function' && isAuthenticated();
    } catch (_) {
      return false;
    }
  }

  function isServiceMode() {
    try {
      return typeof isServiceWorkspaceRole === 'function' && isServiceWorkspaceRole();
    } catch (_) {
      return false;
    }
  }

  const LEGACY_SECTION_META = {
    documents: { tabId: 'documentsTab', testId: 'user-app-next-documents' },
    servicesDirectory: { tabId: 'servicesDirectoryTab', testId: 'user-app-next-services' },
    account: { tabId: 'accountTab', testId: 'user-app-next-account' },
    support: { tabId: 'supportTab', testId: 'user-app-next-support' },
    reservations: { tabId: 'reservationsTab', testId: 'user-app-next-reservations' },
  };

  function getActiveView() {
    if (STATE.viewOverride) return STATE.viewOverride;
    if (!document.body.classList.contains('route-app-view') || !isAuthed() || isServiceMode()) {
      return null;
    }
    const appShell = document.getElementById('app-shell');
    if (!appShell || appShell.hidden) return null;
    const viewByTabId = {
      homeTab: 'home',
      vehiclesTab: 'vehicles',
      remindersTab: 'reminders',
      documentsTab: 'documents',
      servicesDirectoryTab: 'servicesDirectory',
      accountTab: 'account',
      supportTab: 'support',
      reservationsTab: 'reservations',
    };
    for (const [tabId, view] of Object.entries(viewByTabId)) {
      const tab = document.getElementById(tabId);
      if (tab && tab.classList.contains('active')) return view;
    }
    return null;
  }

  function shouldActivate() {
    return getActiveView() !== null;
  }

  function getStoredViewMode() {
    if (hasFn('getVehicleViewMode')) {
      try {
        const mode = window.getVehicleViewMode();
        if (mode === 'grid' || mode === 'list' || mode === 'compact') return mode;
      } catch (_) {}
    }
    return 'grid';
  }

  function stkCatalogLabel(vehicle) {
    const meta = stkFieldMeta(vehicle);
    const raw = getStkValue(vehicle);
    const diff = daysUntil(raw);
    if (diff != null && diff >= 0) {
      if (diff === 0) return { label: 'dnes', tone: meta.tone };
      if (diff === 1) return { label: 'do 1 dne', tone: meta.tone };
      return { label: `do ${diff} dnů`, tone: meta.tone };
    }
    return { label: meta.label, tone: meta.tone };
  }

  function lastServiceLabel(records) {
    const list = Array.isArray(records) ? records.slice() : [];
    if (!list.length) return { label: 'Bez záznamu', tone: 'muted' };
    list.sort((a, b) => (Date.parse(b?.performed_at || b?.created_at) || 0) - (Date.parse(a?.performed_at || a?.created_at) || 0));
    const latest = list[0];
    const status = String(latest?.record_status || '').toLowerCase();
    if (status === 'in_progress' || status === 'draft') {
      return { label: 'právě probíhá', tone: 'bad' };
    }
    const months = monthsSince(latest?.performed_at || latest?.created_at);
    if (months == null) return { label: 'Záznam k dispozici', tone: 'ok' };
    if (months <= 0) return { label: 'tento měsíc', tone: 'ok' };
    if (months === 1) return { label: 'před 1 měsícem', tone: 'ok' };
    return { label: `před ${months} měsíci`, tone: 'ok' };
  }

  function getCatalogVehicleStatus(vehicle, records) {
    if (String(vehicle?.status || '').toLowerCase() === 'archived') {
      return { key: 'archived', label: 'V archivu', tone: 'archived' };
    }
    const openService = (records || []).some((record) => {
      const st = String(record?.record_status || '').toLowerCase();
      return st === 'in_progress' || st === 'draft';
    });
    if (openService) {
      return { key: 'service', label: 'V servisu', tone: 'service' };
    }
    const stk = stkFieldMeta(vehicle);
    const ins = insuranceFieldMeta(vehicle);
    if (stk.tone === 'bad' || ins.tone === 'bad' || stk.tone === 'warn' || ins.tone === 'warn') {
      return { key: 'attention', label: 'Vyžaduje pozornost', tone: 'warn' };
    }
    return { key: 'ok', label: 'V pořádku', tone: 'ok' };
  }

  function catalogBadgeClass(tone) {
    if (tone === 'warn') return 'uapp-next-badge uapp-next-badge--warn';
    if (tone === 'service' || tone === 'bad') return 'uapp-next-badge uapp-next-badge--danger';
    if (tone === 'archived') return 'uapp-next-badge uapp-next-badge--muted';
    return 'uapp-next-badge uapp-next-badge--ok';
  }

  function getFilterCounts(data) {
    const counts = { all: 0, ok: 0, attention: 0, service: 0, archived: 0 };
    (data.vehicles || []).forEach((vehicle) => {
      counts.all += 1;
      const status = getCatalogVehicleStatus(vehicle, recordsFor(data, vehicle.id));
      if (status.key === 'ok') counts.ok += 1;
      else if (status.key === 'attention') counts.attention += 1;
      else if (status.key === 'service') counts.service += 1;
      else if (status.key === 'archived') counts.archived += 1;
    });
    return counts;
  }

  function filterCatalogVehicles(data, filter, query) {
    const q = String(query || '').trim().toLowerCase();
    let list = (data.vehicles || []).slice();
    if (q) {
      list = list.filter((vehicle) => {
        const hay = [getVehicleName(vehicle), vehicle.plate, vehicle.vin, vehicle.brand, vehicle.model].filter(Boolean).join(' ').toLowerCase();
        return hay.includes(q);
      });
    }
    if (filter === 'all') return list;
    return list.filter((vehicle) => getCatalogVehicleStatus(vehicle, recordsFor(data, vehicle.id)).key === filter);
  }

  function sortCatalogVehicles(list, data, sortKey) {
    const copy = list.slice();
    if (sortKey === 'name') {
      copy.sort((a, b) => getVehicleName(a).localeCompare(getVehicleName(b), 'cs'));
      return copy;
    }
    const rank = { service: 0, attention: 1, ok: 2, archived: 3 };
    copy.sort((a, b) => {
      const sa = getCatalogVehicleStatus(a, recordsFor(data, a.id)).key;
      const sb = getCatalogVehicleStatus(b, recordsFor(data, b.id)).key;
      const da = rank[sa] != null ? rank[sa] : 9;
      const db = rank[sb] != null ? rank[sb] : 9;
      if (da !== db) return da - db;
      const ra = (recordsFor(data, a.id)[0]?.performed_at || recordsFor(data, a.id)[0]?.created_at || '');
      const rb = (recordsFor(data, b.id)[0]?.performed_at || recordsFor(data, b.id)[0]?.created_at || '');
      return (Date.parse(rb) || 0) - (Date.parse(ra) || 0);
    });
    return copy;
  }

  function fullName() {
    const u = user() || {};
    const raw = String(u.name || u.email || '').trim();
    if (!raw) return 'uživateli';
    const visible = raw.includes('@') ? raw.split('@')[0].replace(/[._-]+/g, ' ') : raw;
    return visible.split(/\s+/).filter(Boolean)[0] || 'uživateli';
  }

  function profileName() {
    const u = user() || {};
    return String(u.name || fullName()).trim() || 'Profil';
  }

  function initials() {
    const u = user() || {};
    const source = String(u.name || u.email || 'SV').trim();
    return source
      .split(/[\s@._-]+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part.charAt(0).toUpperCase())
      .join('') || 'SV';
  }

  function formatDate(value) {
    if (!value) return '—';
    try {
      if (typeof formatDateCZ === 'function') return formatDateCZ(value);
    } catch (_) {}
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? '—' : d.toLocaleDateString('cs-CZ');
  }

  function formatDateTime(value) {
    if (!value) return '—';
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return '—';
    try {
      return d.toLocaleString('cs-CZ', { day: 'numeric', month: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' });
    } catch (_) {
      return formatDate(value);
    }
  }

  function formatTodayTimeHm() {
    try {
      return new Date().toLocaleTimeString('cs-CZ', { hour: '2-digit', minute: '2-digit' });
    } catch (_) {
      return '';
    }
  }

  function parseDate(value) {
    if (!value) return null;
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? null : d;
  }

  function daysUntil(value) {
    const d = parseDate(value);
    if (!d) return null;
    const today = new Date();
    const start = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime();
    const target = new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
    return Math.round((target - start) / 86400000);
  }

  function monthsSince(value) {
    const d = parseDate(value);
    if (!d) return null;
    const now = new Date();
    return (now.getFullYear() - d.getFullYear()) * 12 + (now.getMonth() - d.getMonth());
  }

  function getVehicleName(vehicle) {
    return String(vehicle?.nickname || vehicle?.name || [vehicle?.brand, vehicle?.model].filter(Boolean).join(' ') || vehicle?.plate || `Vozidlo #${vehicle?.id || ''}`).trim();
  }

  function shortVin(vehicle) {
    const s = String(vehicle?.vin || '').trim();
    if (!s) return '—';
    return s.length <= 14 ? s : `${s.slice(0, 12)}…`;
  }

  function normalizePlateSize(size) {
    const raw = String(size || '').toLowerCase();
    if (raw.includes('lg')) return 'lg';
    if (raw.includes('sm')) return 'sm';
    if (raw === 'lg' || raw === 'sm') return raw;
    return 'sm';
  }

  function renderPlateBadge(plate, size) {
    const raw = String(plate || '').trim();
    const isEmpty = !raw || raw === '—';
    const text = isEmpty ? 'Nezadáno' : raw;
    const sizeKey = normalizePlateSize(size);
    const titleAttr = isEmpty ? '' : ` title="${esc(text)}"`;
    return (
      `<span class="uapp-plate uapp-plate--${sizeKey}${isEmpty ? ' uapp-plate--empty' : ''}"${titleAttr}>` +
      `<span class="uapp-plate__country" aria-hidden="true">` +
      `<span class="uapp-plate__eu">${PLATE_EU_STARS_SVG}</span>` +
      `<span class="uapp-plate__cz">CZ</span>` +
      `</span>` +
      `<span class="uapp-plate__number">${esc(text)}</span>` +
      `</span>`
    );
  }

  function renderCardActionBar(vehicleId, withArrow) {
    const id = Number(vehicleId);
    const addRecordBlocked = !hasFn('openAddServiceRecordModal');
    return `
      <div class="uapp-next-card-actions">
        <button type="button" class="uapp-next-card-action" data-uapp-action="detail:${id}">
          <span class="uapp-next-card-action-ico" aria-hidden="true">${ICO.detail}</span>
          <span class="uapp-next-card-action-label">Detail</span>
        </button>
        <button type="button" class="uapp-next-card-action${addRecordBlocked ? ' is-blocked' : ''}" data-uapp-action="addRecord:${id}"${addRecordBlocked ? ' disabled title="Funkce není dostupná"' : ''}>
          <span class="uapp-next-card-action-ico" aria-hidden="true">${ICO.wrench}</span>
          <span class="uapp-next-card-action-label">Přidat záznam</span>
        </button>
        <button type="button" class="uapp-next-card-action" data-uapp-action="documentsVehicle:${id}">
          <span class="uapp-next-card-action-ico" aria-hidden="true">${ICO.doc}</span>
          <span class="uapp-next-card-action-label">Dokumenty</span>
        </button>
        <button type="button" class="uapp-next-card-action" data-uapp-action="shareVehicle:${id}">
          <span class="uapp-next-card-action-ico" aria-hidden="true">${ICO.share}</span>
          <span class="uapp-next-card-action-label">Sdílet se servisem</span>
        </button>
        ${withArrow ? `<button type="button" class="uapp-next-card-action uapp-next-card-action--arrow" data-uapp-action="detail:${id}" aria-label="Otevřít detail">›</button>` : ''}
      </div>`;
  }

  function vehicleFuelLabel(vehicle) {
    const raw = vehicle?.fuel_type;
    if (!raw) return '—';
    if (hasFn('normalizeFuelType')) {
      try { return window.normalizeFuelType(raw); } catch (_) {}
    }
    return String(raw);
  }

  function vehiclePowerLabel(vehicle) {
    if (vehicle?.engine_power_kw != null && vehicle.engine_power_kw !== '') {
      return `${vehicle.engine_power_kw} kW`;
    }
    return '—';
  }

  function vehicleVolumeLabel(vehicle) {
    if (vehicle?.engine_displacement_cc != null && vehicle.engine_displacement_cc !== '') {
      return `${Number(vehicle.engine_displacement_cc).toLocaleString('cs-CZ')} ccm`;
    }
    return '—';
  }

  function getStkValue(vehicle) {
    if (vehicle?.stk_valid_until) return vehicle.stk_valid_until;
    if (hasFn('getVehicleStkDateValueSimple')) {
      try {
        const d = window.getVehicleStkDateValueSimple(vehicle);
        return d || null;
      } catch (_) {}
    }
    return null;
  }

  function stkFieldMeta(vehicle) {
    const raw = getStkValue(vehicle);
    const dateObj = raw instanceof Date ? raw : parseDate(raw);
    if (hasFn('getVehicleStkStatusMeta') && dateObj) {
      try {
        const meta = window.getVehicleStkStatusMeta(dateObj);
        const diff = daysUntil(dateObj);
        let tone = 'ok';
        if (meta.className === 'stk-expired') tone = 'bad';
        else if (meta.className === 'stk-soon') tone = 'warn';
        else if (meta.className === 'stk-unknown') tone = 'muted';
        let label = meta.label || 'STK';
        if (diff != null && diff >= 0 && diff <= 120) {
          label = diff === 0 ? 'dnes' : (diff === 1 ? 'za 1 den' : `za ${diff} dní`);
        } else if (diff != null && diff < 0) {
          label = 'po termínu';
        }
        return { label, tone, hint: formatDate(raw), className: meta.className || 'stk-unknown' };
      } catch (_) {}
    }
    const diff = daysUntil(raw);
    if (diff == null) return { label: 'Nezadáno', tone: 'muted', hint: 'Bez data', className: 'stk-unknown' };
    if (diff < 0) return { label: 'po termínu', tone: 'bad', hint: formatDate(raw), className: 'stk-expired' };
    if (diff <= 60) return { label: `za ${diff} dní`, tone: 'warn', hint: formatDate(raw), className: 'stk-soon' };
    return { label: 'v pořádku', tone: 'ok', hint: formatDate(raw), className: 'stk-ok' };
  }

  function insuranceFieldMeta(vehicle) {
    const raw = vehicle?.insurance_valid_until;
    const diff = daysUntil(raw);
    if (diff == null) return { label: 'Nezadáno', tone: 'muted' };
    if (diff < 0) return { label: 'po termínu', tone: 'bad' };
    if (diff <= 45) return { label: formatDate(raw), tone: 'warn' };
    return { label: 'v pořádku', tone: 'ok' };
  }

  function serviceFieldMeta(records) {
    const list = Array.isArray(records) ? records.slice() : [];
    if (!list.length) return { label: 'Bez záznamu', tone: 'warn' };
    list.sort((a, b) => (Date.parse(b?.performed_at || b?.created_at) || 0) - (Date.parse(a?.performed_at || a?.created_at) || 0));
    const latest = list[0];
    const months = monthsSince(latest?.performed_at || latest?.created_at);
    if (months == null) return { label: 'Záznam k dispozici', tone: 'ok' };
    if (months <= 0) return { label: 'tento měsíc', tone: 'ok' };
    if (months === 1) return { label: 'před 1 měsícem', tone: 'ok' };
    if (months < 6) return { label: `před ${months} měsíci`, tone: 'ok' };
    if (months < 12) return { label: 'naplánovat servis', tone: 'warn' };
    return { label: 'dlouho bez servisu', tone: 'warn' };
  }

  function vehicleStatusMeta(vehicle, records) {
    const stk = stkFieldMeta(vehicle);
    const ins = insuranceFieldMeta(vehicle);
    if (stk.className === 'stk-expired' || stk.tone === 'bad' || ins.tone === 'bad') {
      return { label: 'Vyžaduje pozornost', tone: 'warn' };
    }
    if (stk.tone === 'warn' || ins.tone === 'warn') {
      return { label: 'Vyžaduje pozornost', tone: 'warn' };
    }
    const svc = serviceFieldMeta(records);
    if (svc.tone === 'warn') return { label: 'Vyžaduje pozornost', tone: 'warn' };
    return { label: 'V pořádku', tone: 'ok' };
  }

  function toneClass(tone) {
    if (tone === 'bad') return 'is-bad';
    if (tone === 'warn') return 'is-warn';
    if (tone === 'muted') return 'is-muted';
    return 'is-ok';
  }

  function badgeClass(tone) {
    if (tone === 'warn') return 'uapp-next-badge uapp-next-badge--warn';
    if (tone === 'bad') return 'uapp-next-badge uapp-next-badge--danger';
    if (tone === 'service') return 'uapp-next-badge uapp-next-badge--service';
    return 'uapp-next-badge uapp-next-badge--ok';
  }

  function quickToneClass(tone) {
    if (tone === 'warning') return 'uapp-next-quick-card--warn';
    if (tone === 'danger') return 'uapp-next-quick-card--danger';
    if (tone === 'info') return 'uapp-next-quick-card--info';
    return 'uapp-next-quick-card--ok';
  }

  function heroCarSvg() {
    return (
      '<svg class="uapp-next-hero-car-svg" viewBox="0 0 400 175" aria-hidden="true" focusable="false">' +
      '<defs><linearGradient id="uappH1" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#1e3a8a"/><stop offset="100%" stop-color="#2563eb"/></linearGradient>' +
      '<linearGradient id="uappH2" x1="0%" y1="0%" x2="0%" y2="100%"><stop offset="0%" stop-color="#93c5fd"/><stop offset="100%" stop-color="#1d4ed8"/></linearGradient>' +
      '<filter id="uappHs" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur in="SourceAlpha" stdDeviation="4"/><feOffset dy="8" result="o"/><feFlood flood-color="rgba(11,31,122,0.25)"/><feComposite in2="o" operator="in"/><feMerge><feMergeNode/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>' +
      '<ellipse cx="200" cy="138" rx="175" ry="14" fill="rgba(11,31,122,0.07)"/>' +
      '<g filter="url(#uappHs)"><path d="M48 102 L118 78 L268 74 L338 86 L368 104 L368 122 L38 122 Z" fill="url(#uappH1)"/>' +
      '<path d="M125 80 L248 78 L318 88 L328 108 L98 110 Z" fill="url(#uappH2)" opacity="0.88"/>' +
      '<rect x="142" y="86" width="52" height="24" rx="4" fill="rgba(255,255,255,0.28)"/>' +
      '<rect x="258" y="88" width="44" height="20" rx="3" fill="rgba(255,255,255,0.22)"/>' +
      '<circle cx="108" cy="122" r="16" fill="#0f172a"/><circle cx="108" cy="122" r="7" fill="#475569"/>' +
      '<circle cx="278" cy="122" r="16" fill="#0f172a"/><circle cx="278" cy="122" r="7" fill="#475569"/></g></svg>'
    );
  }

  async function safeApi(url, fallback) {
    if (!apiReady()) return fallback;
    try {
      const result = await apiCall(url, 'GET');
      return result == null ? fallback : result;
    } catch (error) {
      console.warn('[USER_APP_NEXT] API skipped:', url, error?.message || error);
      return fallback;
    }
  }

  async function loadRecordsForVehicles(vehicles) {
    const targets = vehicles.filter((vehicle) => Number(vehicle?.id) > 0);
    const entries = await Promise.all(targets.map(async (vehicle) => {
      const records = await safeApi(`/api/v1/vehicles/${Number(vehicle.id)}/records`, []);
      return { vehicle, records: Array.isArray(records) ? records : [] };
    }));
    return entries;
  }

  async function loadData() {
    const [summary, vehicles, reminders, accessPayload, contactsPayload] = await Promise.all([
      safeApi('/api/v1/analytics/dashboard', {}),
      safeApi('/api/v1/vehicles', []),
      safeApi('/api/v1/reminders', []),
      safeApi('/api/v1/services/vehicle-access', { grants: [] }),
      safeApi('/api/v1/services/my-contacts', { services: [] }),
    ]);
    const vehicleList = Array.isArray(vehicles) ? vehicles : [];
    window._lastVehiclesById = vehicleList.reduce((acc, vehicle) => {
      if (vehicle && Number(vehicle.id) > 0) acc[Number(vehicle.id)] = vehicle;
      return acc;
    }, {});
    STATE.lastVehicles = vehicleList;
    const recordEntries = await loadRecordsForVehicles(vehicleList);
    const recordMap = recordEntries.reduce((acc, entry) => {
      acc[Number(entry.vehicle.id)] = entry.records;
      return acc;
    }, {});
    const data = {
      summary: summary && typeof summary === 'object' ? summary : {},
      vehicles: vehicleList,
      reminders: Array.isArray(reminders) ? reminders : [],
      accessGrants: Array.isArray(accessPayload?.grants) ? accessPayload.grants : [],
      services: Array.isArray(contactsPayload?.services) ? contactsPayload.services : [],
      recordEntries,
      recordMap,
    };
    STATE.latestData = data;
    return data;
  }

  function recordsFor(data, vehicleId) {
    if (data.recordMap && data.recordMap[vehicleId]) return data.recordMap[vehicleId];
    const hit = (data.recordEntries || []).find((entry) => Number(entry.vehicle?.id) === Number(vehicleId));
    return hit ? hit.records : [];
  }

  function activeRemindersCount(data) {
    const fromSummary = Number(data.summary?.active_reminders);
    if (Number.isFinite(fromSummary)) return fromSummary;
    return data.reminders.filter((item) => !item?.is_completed).length;
  }

  function stkSoonCount(data) {
    const fromSummary = Number(data.summary?.stk_soon);
    if (Number.isFinite(fromSummary) && fromSummary >= 0) return fromSummary;
    return data.vehicles.filter((vehicle) => {
      const meta = stkFieldMeta(vehicle);
      return meta.tone === 'warn' || meta.tone === 'bad';
    }).length;
  }

  function serviceNotificationsCount(data) {
    const pending = data.accessGrants.filter((grant) => {
      const status = String(grant?.status || '').toLowerCase();
      return status.includes('pending') || status.includes('ček') || status.includes('wait');
    }).length;
    if (pending > 0) return pending;
    const notes = window.__systemNotificationsLastItems || [];
    return notes.filter((item) => {
      const hay = `${item?.title || ''} ${item?.body || ''} ${item?.kind || ''}`.toLowerCase();
      return hay.includes('servis') || hay.includes('service') || hay.includes('přístup');
    }).length;
  }

  function fleetNeedsAttention(data) {
    if (Array.isArray(data.summary?.attention) && data.summary.attention.length) return true;
    return data.vehicles.some((vehicle) => {
      const meta = vehicleStatusMeta(vehicle, recordsFor(data, vehicle.id));
      return meta.tone !== 'ok';
    });
  }

  function attentionPriorityRank(priority) {
    if (priority === 'high') return 3;
    if (priority === 'warning') return 2;
    return 1;
  }

  function attentionItemIcon(type) {
    const map = {
      stk: ICO.quickStk,
      insurance: ICO.quickShield,
      service: ICO.wrench,
      documents: ICO.doc,
      access: ICO.share,
      reminder: ICO.bell,
    };
    return map[type] || ICO.bell;
  }

  function reminderLooksLikeStk(text) {
    const hay = String(text || '').toLowerCase();
    return hay.includes('stk') || hay.includes('sme') || hay.includes('technick');
  }

  function reminderLooksLikeInsurance(text) {
    const hay = String(text || '').toLowerCase();
    return hay.includes('pojišt') || hay.includes('pojist');
  }

  function getVehicleAttentionItems(vehicle, data) {
    const items = [];
    const id = Number(vehicle?.id);
    if (!Number.isFinite(id) || id <= 0) return items;
    const records = recordsFor(data, id);
    const vehicleName = getVehicleName(vehicle);
    const plate = vehicle.plate || '';
    const push = (item) => items.push({ vehicleId: id, vehicleName, plate, vehicle, ...item });

    const stk = stkFieldMeta(vehicle);
    if (stk.tone === 'bad') {
      push({
        type: 'stk',
        problemText: 'STK po termínu',
        priority: 'high',
        priorityLabel: 'Po termínu',
        actionText: 'Otevřít STK',
        action: `detailTab:ops:${id}`,
      });
    } else if (stk.tone === 'warn') {
      push({
        type: 'stk',
        problemText: stk.label === 'po termínu' ? 'STK po termínu' : `STK ${stk.label}`,
        priority: 'warning',
        priorityLabel: 'Blíží se',
        actionText: 'Otevřít STK',
        action: `detailTab:ops:${id}`,
      });
    } else if (stk.tone === 'muted' && stk.label === 'Nezadáno') {
      push({
        type: 'stk',
        problemText: 'STK nezadána',
        priority: 'warning',
        priorityLabel: 'Vyžaduje doplnění',
        actionText: 'Otevřít detail',
        action: `detail:${id}`,
      });
    }

    const ins = insuranceFieldMeta(vehicle);
    if (ins.tone === 'bad') {
      push({
        type: 'insurance',
        problemText: 'Pojištění po termínu',
        priority: 'high',
        priorityLabel: 'Po termínu',
        actionText: 'Otevřít detail',
        action: `detail:${id}`,
      });
    } else if (ins.tone === 'warn') {
      push({
        type: 'insurance',
        problemText: 'Pojištění brzy končí',
        priority: 'warning',
        priorityLabel: 'Blíží se',
        actionText: 'Otevřít detail',
        action: `detail:${id}`,
      });
    } else if (ins.tone === 'muted') {
      push({
        type: 'insurance',
        problemText: 'Pojištění nezadáno',
        priority: 'warning',
        priorityLabel: 'Vyžaduje doplnění',
        actionText: 'Otevřít detail',
        action: `detail:${id}`,
      });
    }

    const openService = (records || []).filter((record) => {
      const st = String(record?.record_status || '').toLowerCase();
      return st === 'in_progress' || st === 'draft';
    });
    if (openService.length) {
      const draft = openService.some((record) => String(record?.record_status || '').toLowerCase() === 'draft');
      push({
        type: 'service',
        problemText: draft ? 'Rozepsaný servisní záznam' : 'Servis právě probíhá',
        priority: 'warning',
        priorityLabel: 'V servisu',
        actionText: 'Otevřít servis',
        action: `detailTab:service:${id}`,
      });
    }

    const hasStkItem = items.some((item) => item.type === 'stk');
    const hasInsuranceItem = items.some((item) => item.type === 'insurance');
    (data?.reminders || []).forEach((reminder) => {
      if (reminder?.is_completed || Number(reminder?.vehicle_id) !== id) return;
      const title = String(reminder.text || reminder.title || reminder.type || 'Připomínka').trim();
      if (hasStkItem && reminderLooksLikeStk(title)) return;
      if (hasInsuranceItem && reminderLooksLikeInsurance(title)) return;
      const diff = daysUntil(reminder.due_date || reminder.notify_at);
      if (diff == null || diff > 60) return;
      push({
        type: 'reminder',
        problemText: title,
        priority: diff < 0 ? 'high' : 'warning',
        priorityLabel: diff < 0 ? 'Po termínu' : 'Blíží se',
        actionText: 'Otevřít připomínky',
        action: `detailTab:ops:${id}`,
      });
    });

    (data?.accessGrants || []).forEach((grant) => {
      if (Number(grant?.vehicle_id) !== id) return;
      const badge = grantBadge(grant.status);
      if (badge.tone !== 'warn') return;
      const serviceLabel = grant.service_name || grant.service_email || 'servis';
      push({
        type: 'access',
        problemText: `Přístup servisu — ${serviceLabel}`,
        priority: 'warning',
        priorityLabel: 'Čeká na schválení',
        actionText: 'Otevřít přístupy',
        action: `detailTab:access:${id}`,
      });
    });

    return items;
  }

  function collectAllAttentionItems(data) {
    const all = [];
    (data?.vehicles || []).forEach((vehicle) => {
      getVehicleAttentionItems(vehicle, data).forEach((item) => all.push(item));
    });
    all.sort((a, b) => {
      const rankDiff = attentionPriorityRank(b.priority) - attentionPriorityRank(a.priority);
      if (rankDiff !== 0) return rankDiff;
      return String(a.vehicleName || '').localeCompare(String(b.vehicleName || ''), 'cs');
    });
    return all;
  }

  function attentionCountLabel(count) {
    if (count === 1) return '1 položka k řešení';
    if (count >= 2 && count <= 4) return `${count} položky k řešení`;
    return `${count} položek k řešení`;
  }

  function renderAttentionModalContent(data) {
    const items = collectAllAttentionItems(data);
    STATE.attentionItems = items;
    const count = items.length;
    const listHtml = count
      ? items.map((item, index) => `
        <article class="uapp-next-attention-item">
          <div class="uapp-next-attention-item-main">
            <span class="uapp-next-attention-item-ico" aria-hidden="true">${attentionItemIcon(item.type)}</span>
            <div class="uapp-next-attention-item-body">
              <div class="uapp-next-attention-item-head">
                <strong class="uapp-next-attention-vehicle">${esc(item.vehicleName)}</strong>
                ${renderPlateBadge(item.plate)}
                <span class="uapp-next-attention-badge is-${esc(item.priority)}">${esc(item.priorityLabel)}</span>
              </div>
              <p class="uapp-next-attention-problem">${esc(item.problemText)}</p>
            </div>
          </div>
          <button type="button" class="uapp-next-attention-resolve" data-uapp-action="attentionResolve:${index}">${esc(item.actionText)}</button>
        </article>`).join('')
      : `
        <div class="uapp-next-attention-empty">
          <div class="uapp-next-attention-empty-ico" aria-hidden="true">${ICO.checkOk}</div>
          <p>Všechna vozidla jsou aktuálně v pořádku.</p>
          <button type="button" class="uapp-next-btn uapp-next-btn-primary" data-uapp-action="attentionAllVehicles">Zobrazit přehled vozidel</button>
        </div>`;

    return `
      <div class="uapp-next-attention-modal" role="dialog" aria-modal="true" aria-labelledby="uappNextAttentionTitle">
        <button type="button" class="uapp-next-attention-close" data-uapp-action="attentionClose" aria-label="Zavřít">×</button>
        <header class="uapp-next-attention-head">
          <h2 id="uappNextAttentionTitle">Co je potřeba řešit</h2>
          <p class="uapp-next-attention-sub">Přehled vozidel a úkolů, které vyžadují vaši pozornost.</p>
          ${count ? `<p class="uapp-next-attention-count">${esc(attentionCountLabel(count))}</p>` : ''}
        </header>
        <div class="uapp-next-attention-list">${listHtml}</div>
        <footer class="uapp-next-attention-foot">
          <button type="button" class="uapp-next-btn uapp-next-btn-secondary" data-uapp-action="attentionAllVehicles">Zobrazit všechna vozidla</button>
          <button type="button" class="uapp-next-btn uapp-next-btn-ghost" data-uapp-action="attentionClose">Zavřít</button>
        </footer>
      </div>`;
  }

  function mountAttentionModalShell(html) {
    let backdrop = document.getElementById(ATTENTION_MODAL_ID);
    if (!backdrop) {
      backdrop = document.createElement('div');
      backdrop.id = ATTENTION_MODAL_ID;
      backdrop.className = 'uapp-next-attention-backdrop';
      backdrop.setAttribute('data-testid', 'user-app-next-attention-modal');
      document.body.appendChild(backdrop);
    }
    backdrop.innerHTML = `<div class="uapp-next-attention-backdrop-inner">${html}</div>`;
    backdrop.onclick = (event) => {
      if (event.target === backdrop || event.target.classList.contains('uapp-next-attention-backdrop-inner')) {
        closeAttentionModal();
      }
    };
  }

  function openAttentionModal() {
    bindModalEsc();
    const data = STATE.latestData;
    if (!data) return;
    STATE.attentionModalOpen = true;
    document.body.classList.add('uapp-next-attention-open');
    mountAttentionModalShell(renderAttentionModalContent(data));
  }

  function closeAttentionModal() {
    STATE.attentionModalOpen = false;
    STATE.attentionItems = [];
    document.body.classList.remove('uapp-next-attention-open');
    const root = document.getElementById(ATTENTION_MODAL_ID);
    if (root) root.remove();
  }

  function computeQuickCards(data) {
    const vehicles = data.vehicles || [];
    let stkN = 0;
    let stkSample = '';
    let insWarn = 0;
    let insBad = 0;
    vehicles.forEach((vehicle) => {
      const stk = stkFieldMeta(vehicle);
      const ins = insuranceFieldMeta(vehicle);
      if (stk.tone === 'warn' || stk.tone === 'bad') {
        stkN += 1;
        if (!stkSample) stkSample = stk.label;
      }
      if (ins.tone === 'warn') insWarn += 1;
      if (ins.tone === 'bad') insBad += 1;
    });

    let svcBlock = { tone: 'success', title: 'Bez servisního záznamu', desc: 'Doplňte první servisní záznam' };
    let latestMonths = null;
    data.recordEntries.forEach(({ records }) => {
      const meta = serviceFieldMeta(records);
      if (meta.tone === 'ok' && meta.label.includes('měs')) {
        const m = monthsSince(records[0]?.performed_at || records[0]?.created_at);
        if (m != null && (latestMonths == null || m < latestMonths)) latestMonths = m;
      }
    });
    if (latestMonths != null) {
      svcBlock = {
        tone: 'info',
        title: latestMonths <= 1 ? 'Poslední servis tento měsíc' : `Poslední servis před ${latestMonths} měsíci`,
        desc: 'Váš vůz je v pořádku',
      };
    } else if (data.recordEntries.some((entry) => entry.records.length)) {
      svcBlock = { tone: 'info', title: 'Servisní záznamy k dispozici', desc: 'Zkontrolujte historii servisu' };
    }

    const docsMissing = Number(data.summary?.missing_main_photo || 0) + Number(data.summary?.records_missing_history || 0);
    const docPending = docsMissing > 0 ? docsMissing : Number(data.summary?.documents_pending || 0);

    return {
      stk: {
        tone: stkN > 0 ? 'warning' : 'success',
        title: stkN === 0 ? 'STK / SME v pořádku' : (stkN === 1 ? `1 vozidlo — ${stkSample}` : `${stkN} vozidla — zkontrolujte STK`),
        desc: stkN > 0 ? 'Zkontrolujte včas' : 'Žádná blížící se lhůta',
        action: 'reminders',
      },
      ins: {
        tone: insWarn + insBad > 0 ? 'warning' : 'success',
        title: insWarn + insBad > 0 ? 'Zkontrolujte pojistné smlouvy' : 'Všechna vozidla v pořádku',
        desc: insWarn + insBad > 0 ? 'Zkontrolujte pojištění' : 'Platné smlouvy',
        action: 'reminders',
      },
      svc: { ...svcBlock, action: 'serviceHistory' },
      docs: {
        tone: docPending > 0 ? 'warning' : 'success',
        title: docPending > 0 ? `${docPending} dokumenty čekají na doplnění` : 'Dokumenty v pořádku',
        desc: docPending > 0 ? 'Doplňte chybějící' : 'Žádné chybějící podklady',
        action: 'documents',
      },
    };
  }

  function preserveLegacyOverlays() {
    preserveLegacyVehicleModal();
    detachedPanels();
  }

  function detachedPanels() {
    ['appNotificationsPanel', 'mobileProfileMenu'].forEach((id) => {
      const el = document.getElementById(id);
      if (el && el.parentElement !== document.body) {
        document.body.appendChild(el);
      }
    });
  }

  function preserveLegacyVehicleModal() {
    const modal = document.getElementById('addVehicleModal');
    if (modal && modal.parentElement !== document.body) {
      document.body.appendChild(modal);
    }
  }

  function ensureUserAppScreenRoot() {
    const dashboard = document.getElementById('dashboard');
    if (!dashboard) return null;
    let root = document.getElementById(USER_APP_SCREEN_ID);
    if (!root) {
      root = document.createElement('div');
      root.id = USER_APP_SCREEN_ID;
      root.className = 'user-app-next-screen';
      root.setAttribute('data-testid', 'user-app-next-screen');
      dashboard.appendChild(root);
    }
    return root;
  }

  function clearUserAppScreen() {
    restoreLegacyTabMount();
    const root = document.getElementById(USER_APP_SCREEN_ID);
    if (root) root.replaceChildren();
  }

  function restoreLegacyTabMount() {
    if (!STATE.legacyMount.tabId) return;
    const tab = document.getElementById(STATE.legacyMount.tabId);
    const mount = document.getElementById('uappNextLegacyMount');
    if (tab && mount) {
      while (mount.firstChild) {
        tab.appendChild(mount.firstChild);
      }
    }
    STATE.legacyMount = { tabId: null };
  }

  function mountLegacyTabContent(view) {
    const meta = LEGACY_SECTION_META[view];
    if (!meta) return;
    const tab = document.getElementById(meta.tabId);
    const mount = document.getElementById('uappNextLegacyMount');
    if (!tab || !mount) return;
    while (tab.firstChild) {
      mount.appendChild(tab.firstChild);
    }
    STATE.legacyMount = { tabId: meta.tabId };
  }

  function renderLegacySectionCanvas(view) {
    const meta = LEGACY_SECTION_META[view] || { testId: `user-app-next-${view}` };
    return `
      ${renderTopbar()}
      <div class="uapp-next-legacy-page" data-testid="${esc(meta.testId)}">
        <div class="uapp-next-legacy-mount" id="uappNextLegacyMount"></div>
      </div>`;
  }

  function setActiveClass(active) {
    document.body.classList.toggle('user-app-next-active', Boolean(active));
    if (!active) {
      document.body.classList.remove('user-app-next-sidebar-collapsed', 'user-app-next-view-vehicles', 'user-app-next-view-legacy');
      clearUserAppScreen();
    }
  }

  function navButton(label, iconSvg, action, active, badge) {
    const badgeHtml = badge > 0 ? `<span class="uapp-next-nav-badge">${esc(String(badge))}</span>` : '';
    return `<button type="button" class="${active ? 'is-active' : ''}" data-uapp-action="${esc(action)}"><span class="uapp-next-nav-ico" aria-hidden="true">${iconSvg}</span><span class="uapp-next-nav-label">${esc(label)}</span>${badgeHtml}</button>`;
  }

  function reminderReferenceDate(reminder) {
    const notify = parseDate(reminder?.notify_at);
    if (notify) return notify;
    return parseDate(reminder?.due_date);
  }

  function reminderColumnKey(reminder) {
    if (reminder?.is_completed === true) return 'completed';
    const ref = reminderReferenceDate(reminder);
    if (!ref) return 'planned';
    const diff = daysUntil(ref);
    if (diff == null) return 'planned';
    if (diff < 0) return 'overdue';
    if (diff <= 60) return 'upcoming';
    return 'planned';
  }

  function reminderPriorityLabel(reminder) {
    const key = String(reminder?.type || '').toUpperCase();
    if (key === 'STK') return 'STK';
    if (key === 'OLEJ') return 'Olej';
    if (key === 'GENERAL') return 'Servis';
    if (key === 'VLASTNI') return 'Vlastní';
    return key || 'Připomínka';
  }

  function reminderSummaryStats(data) {
    const buckets = bucketReminders(data);
    const now = new Date();
    const monthStart = new Date(now.getFullYear(), now.getMonth(), 1);
    let today = 0;
    let thisWeek = 0;
    (data?.reminders || []).forEach((item) => {
      if (item?.is_completed) return;
      const ref = reminderReferenceDate(item);
      const diff = ref ? daysUntil(ref) : null;
      if (diff === 0) today += 1;
      if (diff != null && diff >= 0 && diff <= 7) thisWeek += 1;
    });
    const completedMonth = (data?.reminders || []).filter((item) => {
      if (!item?.is_completed) return false;
      const ref = parseDate(item?.completed_at || item?.due_date || item?.updated_at);
      return ref && ref >= monthStart;
    }).length;
    return {
      today,
      thisWeek,
      overdue: buckets.overdue.length,
      completedMonth,
      planned: buckets.planned.length,
      upcoming: buckets.upcoming.length,
      completed: buckets.completed.length,
    };
  }

  function bucketReminders(data) {
    const buckets = { overdue: [], upcoming: [], planned: [], completed: [] };
    (data?.reminders || []).forEach((item) => {
      const col = reminderColumnKey(item);
      if (buckets[col]) buckets[col].push(item);
    });
    const sortByDate = (a, b) => {
      const da = reminderReferenceDate(a);
      const db = reminderReferenceDate(b);
      if (!da && !db) return 0;
      if (!da) return 1;
      if (!db) return -1;
      return da.getTime() - db.getTime();
    };
    buckets.overdue.sort(sortByDate);
    buckets.upcoming.sort(sortByDate);
    buckets.planned.sort(sortByDate);
    buckets.completed.sort((a, b) => {
      const da = parseDate(a?.completed_at || a?.due_date);
      const db = parseDate(b?.completed_at || b?.due_date);
      return (db?.getTime() || 0) - (da?.getTime() || 0);
    });
    return buckets;
  }

  function vehicleLabelById(data, vehicleId) {
    const id = Number(vehicleId);
    if (!id) return 'Bez vozidla';
    const vehicle = (data?.vehicles || []).find((v) => Number(v.id) === id);
    return vehicle ? getVehicleName(vehicle) : `Vozidlo #${id}`;
  }

  function reminderDueLabel(reminder) {
    const ref = reminderReferenceDate(reminder);
    if (!ref) return 'Bez termínu';
    const diff = daysUntil(ref);
    if (diff == null) return formatDate(ref);
    if (diff < 0) return `${Math.abs(diff) === 1 ? '1 den' : `${Math.abs(diff)} dní`} po termínu`;
    if (diff === 0) return 'Dnes';
    if (diff === 1) return 'Zítra';
    if (diff <= 14) return `Za ${diff} dní`;
    return formatDate(ref);
  }

  function renderReminderKanbanCard(item, data) {
    const id = Number(item.id);
    const col = reminderColumnKey(item);
    const vehicleId = Number(item?.vehicle_id) || 0;
    const vehicle = (data?.vehicles || []).find((v) => Number(v.id) === vehicleId);
    const plate = vehicle?.plate ? renderPlateBadge(vehicle.plate, 'sm') : '';
    return `
      <article class="uapp-rem-kanban-card is-${esc(col)}" data-testid="uapp-reminder-card-${id}">
        <div class="uapp-rem-kanban-card-top">
          <span class="uapp-rem-kanban-priority">${esc(reminderPriorityLabel(item))}</span>
          ${item?.is_manual === false ? '<span class="uapp-rem-kanban-auto">Auto</span>' : ''}
        </div>
        <h4 class="uapp-rem-kanban-title">${esc(String(item.text || item.title || item.type || 'Připomínka').trim())}</h4>
        <p class="uapp-rem-kanban-vehicle">${plate}<span>${esc(vehicleLabelById(data, vehicleId))}</span></p>
        <p class="uapp-rem-kanban-due ${col === 'overdue' ? 'is-overdue' : ''}">${esc(reminderDueLabel(item))}</p>
        <div class="uapp-rem-kanban-actions">
          ${col !== 'completed' ? `<button type="button" class="uapp-rem-kanban-btn" data-uapp-action="reminderComplete:${id}">✓ Splnit</button>` : ''}
          ${col !== 'completed' ? `<button type="button" class="uapp-rem-kanban-btn" data-uapp-action="reminderSnooze:${id}">◷ Odložit</button>` : ''}
          <button type="button" class="uapp-rem-kanban-btn" data-uapp-action="reminderDetail:${id}">▣ Detail</button>
        </div>
      </article>`;
  }

  function renderRemindersCalendar(data) {
    const now = new Date();
    const year = now.getFullYear();
    const month = now.getMonth();
    const first = new Date(year, month, 1);
    const startPad = (first.getDay() + 6) % 7;
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const monthLabel = first.toLocaleDateString('cs-CZ', { month: 'long', year: 'numeric' });
    const dueDays = new Set();
    (data?.reminders || []).forEach((item) => {
      if (item?.is_completed) return;
      const ref = reminderReferenceDate(item);
      if (!ref || ref.getFullYear() !== year || ref.getMonth() !== month) return;
      dueDays.add(ref.getDate());
    });
    let cells = '';
    for (let i = 0; i < startPad; i += 1) {
      cells += '<span class="uapp-rem-cal-day is-empty" aria-hidden="true"></span>';
    }
    for (let day = 1; day <= daysInMonth; day += 1) {
      const isToday = day === now.getDate();
      const hasDue = dueDays.has(day);
      cells += `<span class="uapp-rem-cal-day${isToday ? ' is-today' : ''}${hasDue ? ' has-due' : ''}">${day}</span>`;
    }
    return `
      <section class="uapp-rem-aside-card">
        <h3>Kalendář termínů</h3>
        <p class="uapp-rem-cal-month">${esc(monthLabel)}</p>
        <div class="uapp-rem-cal-weekdays" aria-hidden="true">
          <span>Po</span><span>Út</span><span>St</span><span>Čt</span><span>Pá</span><span>So</span><span>Ne</span>
        </div>
        <div class="uapp-rem-cal-grid" role="grid" aria-label="Kalendář připomínek">${cells}</div>
      </section>`;
  }

  function renderRemindersPage(data) {
    const stats = reminderSummaryStats(data);
    const buckets = bucketReminders(data);
    const columns = [
      { key: 'overdue', title: 'Po termínu', tone: 'danger' },
      { key: 'upcoming', title: 'Blíží se', tone: 'warn' },
      { key: 'planned', title: 'Naplánováno', tone: 'info' },
      { key: 'completed', title: 'Dokončeno', tone: 'ok' },
    ];
    const kanban = columns.map((col) => {
      const items = buckets[col.key] || [];
      return `
        <section class="uapp-rem-kanban-col is-${col.tone}" aria-label="${esc(col.title)}">
          <header class="uapp-rem-kanban-col-head">
            <h3>${esc(col.title)}</h3>
            <span class="uapp-rem-kanban-count">${items.length}</span>
          </header>
          <div class="uapp-rem-kanban-col-body">
            ${items.length
              ? items.map((item) => renderReminderKanbanCard(item, data)).join('')
              : '<p class="uapp-rem-kanban-empty">Žádné položky</p>'}
          </div>
        </section>`;
    }).join('');

    const tipBanner = STATE.remindersTipHidden ? '' : `
      <div class="uapp-rem-tip" role="note">
        <div>
          <strong>Tip</strong>
          <p>Tip: Připomínky se automaticky synchronizují s vozidly a jejich servisní historií.</p>
        </div>
        <button type="button" class="uapp-rem-tip-close" data-uapp-action="remindersTipClose" aria-label="Zavřít tip">×</button>
      </div>`;

    return `
      <div class="uapp-rem-page" data-testid="user-app-next-reminders">
        <header class="uapp-rem-page-head">
          <div>
            <h1 class="uapp-rem-page-title">Připomínky</h1>
            <p class="uapp-rem-page-sub">Hlídejte STK, pojištění, servis i vlastní úkoly</p>
          </div>
          <button type="button" class="uapp-next-btn uapp-next-btn-primary" data-uapp-action="newReminder">+ Nová připomínka</button>
        </header>
        <div class="uapp-rem-stats">
          <article class="uapp-rem-stat is-danger"><span class="uapp-rem-stat-ico" aria-hidden="true">📅</span><div><strong>${esc(String(stats.today))}</strong><span>Dnes</span><small>${esc(String(stats.today))} ${stats.today === 1 ? 'úkol' : 'úkoly'}</small></div></article>
          <article class="uapp-rem-stat is-warn"><span class="uapp-rem-stat-ico" aria-hidden="true">📅</span><div><strong>${esc(String(stats.thisWeek))}</strong><span>Tento týden</span><small>${esc(String(stats.thisWeek))} ${stats.thisWeek === 1 ? 'úkol' : 'úkolů'}</small></div></article>
          <article class="uapp-rem-stat is-danger-soft"><span class="uapp-rem-stat-ico" aria-hidden="true">!</span><div><strong>${esc(String(stats.overdue))}</strong><span>Po termínu</span><small>${esc(String(stats.overdue))} ${stats.overdue === 1 ? 'úkol' : 'úkoly'}</small></div></article>
          <article class="uapp-rem-stat is-ok"><span class="uapp-rem-stat-ico" aria-hidden="true">✓</span><div><strong>${esc(String(stats.completedMonth))}</strong><span>Dokončeno</span><small>tento měsíc</small></div></article>
        </div>
        <div class="uapp-rem-layout">
          <div class="uapp-rem-main">
            <div class="uapp-rem-kanban-board" role="region" aria-label="Kanban připomínek">${kanban}</div>
            ${tipBanner}
          </div>
          <aside class="uapp-rem-aside" aria-label="Nastavení připomínek">
            ${renderRemindersCalendar(data)}
            <section class="uapp-rem-aside-card">
              <h3>Automatické připomínky</h3>
              <label class="uapp-rem-toggle"><input type="checkbox" checked disabled><span>STK / SME před termínem</span></label>
              <label class="uapp-rem-toggle"><input type="checkbox" checked disabled><span>Pojištění před vypršením</span></label>
              <label class="uapp-rem-toggle"><input type="checkbox" checked disabled><span>Servisní intervaly</span></label>
              <p class="uapp-rem-aside-hint">Nastavení upravíte v sekci Nastavení účtu.</p>
            </section>
            <section class="uapp-rem-aside-card">
              <h3>Doporučení pro vozidla</h3>
              <ul class="uapp-rem-rec-list">
                ${(data?.vehicles || []).slice(0, 3).map((vehicle) => {
                  const stk = stkFieldMeta(vehicle);
                  const hint = stk.tone === 'bad' || stk.tone === 'warn'
                    ? `STK ${stk.label}`
                    : (serviceFieldMeta(recordsFor(data, vehicle.id)).tone === 'warn' ? 'Zkontrolujte servis' : 'V pořádku');
                  return `<li><button type="button" data-uapp-action="detail:${Number(vehicle.id)}"><strong>${esc(getVehicleName(vehicle))}</strong><span>${esc(hint)}</span></button></li>`;
                }).join('') || '<li class="uapp-rem-rec-empty">Zatím bez vozidel.</li>'}
              </ul>
            </section>
          </aside>
        </div>
      </div>`;
  }

  function flattenAllRecords(data) {
    const rows = [];
    (data?.recordEntries || []).forEach((entry) => {
      const vehicle = entry?.vehicle;
      const vehicleId = Number(vehicle?.id) || 0;
      (entry?.records || []).forEach((record) => {
        rows.push({ vehicle, vehicleId, record });
      });
    });
    rows.sort((a, b) => (Date.parse(b.record?.performed_at || b.record?.created_at) || 0) - (Date.parse(a.record?.performed_at || a.record?.created_at) || 0));
    return rows;
  }

  function formatMoneyCzk(value) {
    const num = Number(value);
    if (!Number.isFinite(num) || num <= 0) return '—';
    try {
      return `${num.toLocaleString('cs-CZ', { maximumFractionDigits: 0 })} Kč`;
    } catch (_) {
      return `${Math.round(num)} Kč`;
    }
  }

  function serviceRecordIconClass(record) {
    const type = String(record?.service_type || record?.category || '').toLowerCase();
    if (type.includes('stk') || type.includes('technick')) return 'stk';
    if (type.includes('olej') || type.includes('oil')) return 'oil';
    if (type.includes('brzd') || type.includes('brake')) return 'brakes';
    if (type.includes('pneu') || type.includes('tire')) return 'tires';
    return 'service';
  }

  function serviceRecordStatusMeta(record) {
    const status = String(record?.record_status || '').toLowerCase();
    if (status === 'in_progress' || status === 'draft' || status === 'pending') {
      return { label: 'Čeká na ověření', tone: 'warn' };
    }
    if (status === 'cancelled' || status === 'canceled') {
      return { label: 'Zrušeno', tone: 'muted' };
    }
    return { label: 'Ověřeno', tone: 'ok' };
  }

  function serviceRecordIconGlyph(record) {
    const cls = serviceRecordIconClass(record);
    const map = { stk: '✓', oil: '🛢', brakes: '◉', tires: '◎', service: '⚙' };
    return map[cls] || map.service;
  }

  function filterServiceHistoryRows(data) {
    const filters = STATE.serviceHistoryFilters || {};
    let rows = flattenAllRecords(data);
    if (filters.vehicle && filters.vehicle !== 'all') {
      const vid = Number(filters.vehicle);
      rows = rows.filter((entry) => Number(entry.vehicleId) === vid);
    }
    if (filters.period === '1y') {
      const cutoff = Date.now() - (365 * 86400000);
      rows = rows.filter((entry) => (Date.parse(entry.record?.performed_at || entry.record?.created_at) || 0) >= cutoff);
    } else if (filters.period === '2y') {
      const cutoff = Date.now() - (730 * 86400000);
      rows = rows.filter((entry) => (Date.parse(entry.record?.performed_at || entry.record?.created_at) || 0) >= cutoff);
    }
    if (filters.docStatus === 'with_doc') {
      rows = rows.filter((entry) => Array.isArray(entry.record?.attachments) && entry.record.attachments.length > 0);
    }
    return rows;
  }

  function serviceHistoryTopActions(data) {
    const counts = {};
    flattenAllRecords(data).forEach((entry) => {
      const title = String(entry.record?.description || entry.record?.service_type || 'Servis').trim();
      const key = title.length > 28 ? `${title.slice(0, 28)}…` : title;
      counts[key] = (counts[key] || 0) + 1;
    });
    return Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 5);
  }

  function serviceHistoryWorkshops(data) {
    const map = new Map();
    flattenAllRecords(data).forEach((entry) => {
      const name = String(entry.record?.service_name || entry.record?.workshop_name || 'TooZServis').trim() || 'TooZServis';
      const price = Number(entry.record?.total_price ?? entry.record?.price);
      const hit = map.get(name) || { name, count: 0, total: 0 };
      hit.count += 1;
      if (Number.isFinite(price) && price > 0) hit.total += price;
      map.set(name, hit);
    });
    return Array.from(map.values()).sort((a, b) => b.count - a.count).slice(0, 4);
  }

  function serviceHistoryStats(data) {
    const rows = filterServiceHistoryRows(data);
    const limit = STATE.serviceHistoryLimit || 8;
    const visible = rows.slice(0, limit);
    let totalCost = 0;
    let costCount = 0;
    rows.forEach((entry) => {
      const price = Number(entry.record?.total_price ?? entry.record?.price);
      if (Number.isFinite(price) && price > 0) {
        totalCost += price;
        costCount += 1;
      }
    });
    const mid = Math.floor(visible.length / 2);
    let firstHalf = 0;
    let secondHalf = 0;
    visible.forEach((entry, idx) => {
      const price = Number(entry.record?.total_price ?? entry.record?.price);
      if (!Number.isFinite(price) || price <= 0) return;
      if (idx < mid) firstHalf += price;
      else secondHalf += price;
    });
    let trendPct = null;
    if (firstHalf > 0 && secondHalf >= 0) {
      trendPct = Math.round(((secondHalf - firstHalf) / firstHalf) * 100);
    }
    return {
      totalRecords: rows.length,
      visibleCount: visible.length,
      totalCost,
      averageCost: costCount ? totalCost / costCount : 0,
      trendPct,
      workshops: serviceHistoryWorkshops(data),
      topActions: serviceHistoryTopActions(data),
    };
  }

  function renderServiceHistoryRecordRow(entry) {
    const { vehicle, vehicleId, record } = entry;
    const meta = serviceRecordStatusMeta(record);
    const iconClass = serviceRecordIconClass(record);
    const title = String(record?.description || record?.service_type || 'Servisní záznam').trim();
    const dateLabel = formatDate(record?.performed_at || record?.created_at);
    const cost = formatMoneyCzk(record?.total_price ?? record?.price);
    const km = record?.mileage_km != null && record.mileage_km !== ''
      ? `${Number(record.mileage_km).toLocaleString('cs-CZ')} km`
      : (vehicle?.current_mileage_km != null ? `${Number(vehicle.current_mileage_km).toLocaleString('cs-CZ')} km` : '');
    const workshop = String(record?.service_name || record?.workshop_name || 'TooZServis').trim() || 'TooZServis';
    const recordId = Number(record?.id) || 0;
    const attCount = Array.isArray(record?.attachments) ? record.attachments.length : 0;
    return `
      <article class="uapp-sh-record">
        <div class="uapp-sh-record-date">
          <strong>${esc(dateLabel)}</strong>
          ${km ? `<span>${esc(km)}</span>` : ''}
        </div>
        <div class="uapp-sh-record-icon is-${esc(iconClass)}" aria-hidden="true">${serviceRecordIconGlyph(record)}</div>
        <div class="uapp-sh-record-main">
          <h4>${esc(title)}</h4>
          <p class="uapp-sh-record-vehicle">
            <span>${esc(getVehicleName(vehicle || {}))}</span>
            ${vehicle?.plate ? renderPlateBadge(vehicle.plate, 'sm') : ''}
          </p>
          <p class="uapp-sh-record-workshop">${esc(workshop)}</p>
          <div class="uapp-sh-record-meta">
            <span class="uapp-sh-cost">${esc(cost)}</span>
            <span class="uapp-sh-status is-${meta.tone}">${esc(meta.label)}</span>
            ${attCount ? `<span class="uapp-sh-att">📎 ${attCount}</span>` : ''}
          </div>
        </div>
        <div class="uapp-sh-record-actions">
          <button type="button" data-uapp-action="serviceRecordDetail:${vehicleId}">Detail</button>
          <button type="button" data-uapp-action="detailTab:documents:${vehicleId}">Dokumenty</button>
          ${recordId && hasFn('openEditServiceRecordModal') ? `<button type="button" data-uapp-action="serviceRecordEdit:${vehicleId}:${recordId}">Upravit</button>` : ''}
        </div>
      </article>`;
  }

  function renderServiceHistoryTimeline(data) {
    const rows = filterServiceHistoryRows(data);
    const limit = STATE.serviceHistoryLimit || 8;
    const visible = rows.slice(0, limit);
    if (!visible.length) {
      return '<p class="uapp-sh-empty">Zatím nemáte žádné servisní záznamy. Přidejte první záznam tlačítkem výše nebo z detailu vozidla.</p>';
    }
    let html = '';
    let lastYear = null;
    visible.forEach((entry) => {
      const d = parseDate(entry.record?.performed_at || entry.record?.created_at);
      const year = d ? d.getFullYear() : null;
      if (year && year !== lastYear) {
        html += `<div class="uapp-sh-year" aria-hidden="true">${year}</div>`;
        lastYear = year;
      }
      html += renderServiceHistoryRecordRow(entry);
    });
    return html;
  }

  function renderServiceHistoryFilters(data) {
    const f = STATE.serviceHistoryFilters || {};
    const vehicleOptions = (data?.vehicles || []).map((v) => {
      const id = Number(v.id);
      const selected = String(f.vehicle) === String(id) ? ' selected' : '';
      return `<option value="${id}"${selected}>${esc(getVehicleName(v))}</option>`;
    }).join('');
    return `
      <div class="uapp-sh-filters" role="region" aria-label="Filtry historie">
        <label class="uapp-sh-filter-field"><span>Vozidlo</span>
          <select data-uapp-sh-filter="vehicle">
            <option value="all"${f.vehicle === 'all' ? ' selected' : ''}>Všechna vozidla</option>
            ${vehicleOptions}
          </select>
        </label>
        <label class="uapp-sh-filter-field"><span>Období</span>
          <select data-uapp-sh-filter="period">
            <option value="2y"${f.period === '2y' ? ' selected' : ''}>Poslední 2 roky</option>
            <option value="1y"${f.period === '1y' ? ' selected' : ''}>Poslední rok</option>
            <option value="all"${f.period === 'all' ? ' selected' : ''}>Celá historie</option>
          </select>
        </label>
        <label class="uapp-sh-filter-field"><span>Typ úkonu</span>
          <select data-uapp-sh-filter="type">
            <option value="all"${f.type === 'all' ? ' selected' : ''}>Všechny typy</option>
          </select>
        </label>
        <label class="uapp-sh-filter-field"><span>Servis</span>
          <select data-uapp-sh-filter="service">
            <option value="all"${f.service === 'all' ? ' selected' : ''}>Všechny servisy</option>
          </select>
        </label>
        <label class="uapp-sh-filter-field"><span>Stav dokladu</span>
          <select data-uapp-sh-filter="docStatus">
            <option value="all"${f.docStatus === 'all' ? ' selected' : ''}>Všechny stavy</option>
            <option value="with_doc"${f.docStatus === 'with_doc' ? ' selected' : ''}>S dokladem</option>
          </select>
        </label>
        <button type="button" class="uapp-sh-filter-reset" data-uapp-action="serviceHistoryResetFilters">↺ Vymazat filtry</button>
      </div>`;
  }

  function renderServiceHistoryPage(data) {
    const rows = filterServiceHistoryRows(data);
    const limit = STATE.serviceHistoryLimit || 8;
    const stats = serviceHistoryStats(data);
    const hasMore = rows.length > limit;
    const trendHtml = stats.trendPct == null
      ? ''
      : `<p class="uapp-sh-trend${stats.trendPct <= 0 ? ' is-down' : ' is-up'}">${stats.trendPct <= 0 ? '↓' : '↑'} ${esc(String(Math.abs(stats.trendPct)))} % ${stats.trendPct <= 0 ? 'méně' : 'více'} než předchozí období</p>`;

    const workshopList = stats.workshops.length
      ? stats.workshops.map((ws) => `<li><strong>${esc(ws.name)}</strong><span>${esc(String(ws.count))} zásahů · ${esc(formatMoneyCzk(ws.total))}</span></li>`).join('')
      : '<li class="uapp-sh-widget-empty">Zatím bez evidovaných servisů.</li>';

    const topActions = stats.topActions.length
      ? stats.topActions.map(([label, count]) => `<li><span>${esc(label)}</span><strong>${esc(String(count))}×</strong></li>`).join('')
      : '<li class="uapp-sh-widget-empty">Zatím bez opakovaných úkonů.</li>';

    return `
      <div class="uapp-sh-page" data-testid="user-app-next-service-history">
        <header class="uapp-sh-page-head">
          <div>
            <h1 class="uapp-sh-page-title">Servisní historie</h1>
            <p class="uapp-sh-page-sub">Kompletní přehled servisních zásahů napříč vašimi vozidly</p>
          </div>
          ${hasFn('openAddServiceRecordModal') ? '<button type="button" class="uapp-next-btn uapp-next-btn-primary" data-uapp-action="serviceHistoryAdd">+ Přidat servisní záznam</button>' : ''}
        </header>
        ${renderServiceHistoryFilters(data)}
        <div class="uapp-sh-layout">
          <div class="uapp-sh-main">
            <div class="uapp-sh-list-head">
              <h2>Servisní záznamy</h2>
              <span class="uapp-sh-list-count">${esc(String(stats.totalRecords))} záznamů</span>
            </div>
            <section class="uapp-sh-timeline" aria-label="Servisní záznamy">
              ${renderServiceHistoryTimeline(data)}
            </section>
            ${hasMore ? `<button type="button" class="uapp-sh-load-more" data-uapp-action="loadMoreServiceHistory">Načíst další záznamy ▾</button>` : ''}
          </div>
          <aside class="uapp-sh-aside" aria-label="Souhrn servisní historie">
            <section class="uapp-sh-widget">
              <div class="uapp-sh-widget-head">
                <h3>Souhrn nákladů</h3>
                <span class="uapp-sh-widget-period">Poslední 2 roky</span>
              </div>
              <p class="uapp-sh-widget-kpi">${esc(formatMoneyCzk(stats.totalCost))}</p>
              ${trendHtml}
              <div class="uapp-sh-chart-placeholder" aria-hidden="true"><svg viewBox="0 0 200 48" preserveAspectRatio="none"><polyline fill="none" stroke="currentColor" stroke-width="2.5" points="0,40 30,34 60,28 90,32 120,18 150,22 180,12 200,16"/></svg></div>
            </section>
            <section class="uapp-sh-widget">
              <h3>Nejčastější úkony</h3>
              <ul class="uapp-sh-top-actions">${topActions}</ul>
            </section>
            <section class="uapp-sh-widget">
              <h3>Servisy, které vozidla obsluhovaly</h3>
              <ul class="uapp-sh-workshops">${workshopList}</ul>
              <button type="button" class="uapp-sh-widget-link" data-uapp-action="servicesDirectory">Zobrazit všechny servisy ›</button>
            </section>
            <section class="uapp-sh-widget">
              <h3>Doporučené další kroky</h3>
              <ul class="uapp-sh-rec">
                ${(data?.vehicles || []).slice(0, 2).map((vehicle) => {
                  const svc = serviceFieldMeta(recordsFor(data, vehicle.id));
                  if (svc.tone !== 'warn') return '';
                  return `<li class="uapp-sh-rec-card is-warn"><button type="button" data-uapp-action="detail:${Number(vehicle.id)}"><strong>Vyměnit brzdovou kapalinu</strong><span>${esc(getVehicleName(vehicle))} · ${esc(svc.label)}</span></button></li>`;
                }).filter(Boolean).join('') || '<li class="uapp-sh-widget-empty">Všechna vozidla mají aktuální servis.</li>'}
              </ul>
              <button type="button" class="uapp-sh-widget-link" data-uapp-action="reminders">Zobrazit všechny doporučené kroky ›</button>
            </section>
          </aside>
        </div>
      </div>`;
  }

  function bindServiceHistoryFilters() {
    document.querySelectorAll('[data-uapp-sh-filter]').forEach((select) => {
      if (select.dataset.uappShBound === '1') return;
      select.dataset.uappShBound = '1';
      select.addEventListener('change', () => {
        const key = select.getAttribute('data-uapp-sh-filter');
        if (!key) return;
        STATE.serviceHistoryFilters = STATE.serviceHistoryFilters || {};
        STATE.serviceHistoryFilters[key] = select.value;
        STATE.serviceHistoryLimit = 8;
        render();
      });
    });
  }

  function renderSidebar(data, activeNav) {
    const reminderBadge = activeRemindersCount(data);
    const nav = activeNav || 'home';
    return `
      <aside class="uapp-next-sidebar" aria-label="Navigace uživatelského rozhraní">
        <div class="uapp-next-brand">
          <img src="${LOGO_SRC}" alt="" width="40" height="40">
          <span>Správa vozidel</span>
        </div>
        <nav class="uapp-next-nav" aria-label="Sekce aplikace">
          ${navButton('Přehled', ICO.home, 'home', nav === 'home', 0)}
          ${navButton('Moje vozidla', ICO.car, 'vehicles', nav === 'vehicles', 0)}
          ${navButton('Servisní historie', ICO.wrench, 'serviceHistory', nav === 'serviceHistory', 0)}
          ${navButton('Připomínky', ICO.bell, 'reminders', nav === 'reminders', reminderBadge)}
          ${navButton('Dokumenty', ICO.doc, 'documents', nav === 'documents', 0)}
          ${navButton('Servisy', ICO.building, 'servicesDirectory', nav === 'servicesDirectory', 0)}
          ${navButton('Faktury', ICO.invoice, 'invoices', nav === 'documents', 0)}
          ${navButton('Nastavení', ICO.gear, 'account', nav === 'account', 0)}
        </nav>
        <div class="uapp-next-sidebar-bottom">
          <p class="uapp-next-help-label">Potřebujete pomoc?</p>
          <button type="button" class="uapp-next-help-btn" data-uapp-action="help">
            <span aria-hidden="true">?</span>
            <span>Nápověda</span>
          </button>
          <button type="button" class="uapp-next-side-action" data-uapp-action="collapse"><span aria-hidden="true">⇤</span><span>Sbalit menu</span></button>
        </div>
      </aside>
    `;
  }

  function renderTopbar() {
    const badge = document.getElementById('desktopNotificationsBadge') || document.getElementById('mobileNotificationsBadge');
    const count = badge ? String(badge.getAttribute('data-count') || badge.textContent || '0').trim() : '0';
    return `
      <header class="uapp-next-topbar" aria-label="Horní lišta">
        <label class="uapp-next-search">
          <span class="uapp-next-search-icon" aria-hidden="true">${ICO.search}</span>
          <input id="uappNextSearch" type="search" autocomplete="off" placeholder="Hledejte podle SPZ, VIN, názvu vozidla…">
          <kbd class="uapp-next-search-kbd" aria-hidden="true">⌘ K</kbd>
        </label>
        <button type="button" class="uapp-next-btn uapp-next-btn-primary" data-uapp-action="addVehicle">+ Přidat vozidlo</button>
        <div class="uapp-next-top-actions">
          <button type="button" class="uapp-next-btn uapp-next-icon-btn" data-uapp-action="notifications" aria-label="Oznámení" data-count="${esc(count || '0')}">${ICO.bell}</button>
          <button type="button" class="uapp-next-profile" data-uapp-action="profile" aria-label="Profil uživatele">
            <span class="uapp-next-avatar" aria-hidden="true">${esc(initials())}</span>
            <span class="uapp-next-profile-name">${esc(profileName())}</span>
            <span class="uapp-next-profile-caret" aria-hidden="true">▾</span>
          </button>
        </div>
      </header>
    `;
  }

  function heroSummaryHtml(data) {
    const total = Number(data.summary?.vehicles_total ?? data.vehicles.length) || 0;
    const stkSoon = stkSoonCount(data);
    const reminders = activeRemindersCount(data);
    const serviceNotes = serviceNotificationsCount(data);
    const vehicleWord = total === 1 ? 'vozidlo' : (total > 1 && total < 5 ? 'vozidla' : 'vozidel');
    const stkWord = stkSoon === 1 ? 'blížící se STK' : 'blížící se STK';
    const reminderWord = reminders === 1 ? 'aktivní připomínku' : (reminders > 1 && reminders < 5 ? 'aktivní připomínky' : 'aktivních připomínek');
    const serviceWord = serviceNotes === 1 ? 'nové upozornění od servisu' : 'nových upozornění od servisu';
    return (
      `Máte <span class="uapp-next-stat-pill uapp-next-stat-pill--navy">${esc(String(total))}</span> ${vehicleWord}, ` +
      `<span class="uapp-next-stat-pill uapp-next-stat-pill--amber">${esc(String(stkSoon))}</span> ${stkWord}, ` +
      `<span class="uapp-next-stat-pill uapp-next-stat-pill--rose">${esc(String(reminders))}</span> ${reminderWord} a ` +
      `<span class="uapp-next-stat-pill uapp-next-stat-pill--blue">${esc(String(serviceNotes))}</span> ${serviceWord}.`
    );
  }

  function renderHero(data) {
    const heroVehicle = data.vehicles[0] || null;
    const needsAttention = fleetNeedsAttention(data);
    return `
      <div class="uapp-next-overview-top">
        <section class="uapp-next-hero">
          <div class="uapp-next-hero-copy">
            <h1>Dobrý den, ${esc(fullName())} 👋</h1>
            <p class="uapp-next-hero-summary">${heroSummaryHtml(data)}</p>
          </div>
          <div class="uapp-next-hero-visual" aria-hidden="true">
            <div class="uapp-next-hero-landscape"></div>
            <div class="uapp-next-hero-car-wrap" data-next-photo-wrap="${heroVehicle ? Number(heroVehicle.id) : ''}">
              ${heroVehicle
                ? '<img id="uappNextHeroPhoto" class="uapp-next-hero-photo-img" alt="" loading="eager">'
                : `<div class="uapp-next-hero-car-fallback">${heroCarSvg()}</div>`}
            </div>
          </div>
        </section>
        <button type="button" class="uapp-next-overall-status" data-uapp-action="attentionOpen" aria-label="Zobrazit, co je potřeba řešit">
          <div class="uapp-next-overall-inner">
            <div class="uapp-next-overall-text">
              <h2>Celkový stav</h2>
              <p class="uapp-next-overall-main ${needsAttention ? 'is-warn' : 'is-ok'}">${needsAttention ? 'Vyžaduje pozornost' : 'Vozidla pod kontrolou'}</p>
              <p class="uapp-next-overall-meta">Poslední aktualizace: dnes v ${esc(formatTodayTimeHm())}</p>
              <span class="uapp-next-overall-link">Zobrazit detaily <span aria-hidden="true">›</span></span>
            </div>
            <div class="uapp-next-overall-ico-wrap" aria-hidden="true">${needsAttention ? ICO.checkWarn : ICO.checkOk}</div>
          </div>
        </button>
      </div>
    `;
  }

  function quickCards(data) {
    const cards = computeQuickCards(data);
    const icoMap = { stk: ICO.quickStk, ins: ICO.quickShield, svc: ICO.wrench, docs: ICO.doc };
    const labels = { stk: 'STK / SME', ins: 'Pojištění', svc: 'Servis', docs: 'Dokumenty' };
    const accentClass = { stk: 'uapp-next-quick-card--warn', ins: 'uapp-next-quick-card--ok', svc: 'uapp-next-quick-card--info', docs: 'uapp-next-quick-card--warn' };
    return `<div class="uapp-next-quick-grid">${Object.keys(cards).map((key) => {
      const card = cards[key];
      return `
        <button type="button" class="uapp-next-quick-card ${accentClass[key] || quickToneClass(card.tone)}" data-uapp-action="${esc(card.action)}">
          <span class="uapp-next-quick-card-ico">${icoMap[key] || ICO.quickStk}</span>
          <span class="uapp-next-quick-card-body">
            <span class="uapp-next-quick-card-cat">${labels[key]}</span>
            <strong class="uapp-next-quick-card-title">${esc(card.title)}</strong>
            <span class="uapp-next-quick-card-desc">${esc(card.desc)}</span>
          </span>
          <span class="uapp-next-quick-card-arrow" aria-hidden="true">›</span>
        </button>`;
    }).join('')}</div>`;
  }

  function renderVehicleCard(vehicle, data) {
    const id = Number(vehicle.id);
    const records = recordsFor(data, id);
    const status = vehicleStatusMeta(vehicle, records);
    const stk = stkFieldMeta(vehicle);
    const ins = insuranceFieldMeta(vehicle);
    const svc = serviceFieldMeta(records);
    const km = vehicle.current_mileage_km != null && vehicle.current_mileage_km !== ''
      ? `${Number(vehicle.current_mileage_km).toLocaleString('cs-CZ')} km`
      : '—';
    return `
      <article class="uapp-next-vehicle-card" data-uapp-vehicle-card data-search-text="${esc([getVehicleName(vehicle), vehicle.plate, vehicle.vin, vehicle.brand, vehicle.model].filter(Boolean).join(' ').toLowerCase())}" data-vehicle-id="${id}">
        <div class="uapp-next-vehicle-visual">
          <div class="uapp-next-photo" data-next-photo-wrap="${id}">
            <img id="uappNextVehiclePhoto-${id}" alt="Fotka vozidla ${esc(getVehicleName(vehicle))}" loading="lazy">
            <div class="uapp-next-photo-fallback">Bez fotky</div>
          </div>
          <span class="${badgeClass(status.tone === 'warn' ? 'warn' : 'ok')}">${esc(status.label)}</span>
        </div>
        <div class="uapp-next-vehicle-body">
          <h3 class="uapp-next-vehicle-title">${esc(getVehicleName(vehicle))}</h3>
          <div class="uapp-next-vehicle-subrow">
            ${renderPlateBadge(vehicle.plate)}
          </div>
          <div class="uapp-next-vehicle-meta">
            <div class="uapp-next-meta-row"><span class="uapp-next-meta-k">VIN</span><span class="uapp-next-meta-v">${esc(shortVin(vehicle))}</span></div>
            <div class="uapp-next-meta-row"><span class="uapp-next-meta-k">Nájezd</span><span class="uapp-next-meta-v"><strong>${esc(km)}</strong></span></div>
          </div>
          <div class="uapp-next-status-lines">
            <div class="uapp-next-status-line"><span>STK</span><strong class="uapp-next-status-val ${toneClass(stk.tone)}">${esc(stk.label)}</strong></div>
            <div class="uapp-next-status-line"><span>Pojištění</span><strong class="uapp-next-status-val ${toneClass(ins.tone)}">${esc(ins.label)}</strong></div>
            <div class="uapp-next-status-line"><span>Servis</span><strong class="uapp-next-status-val ${toneClass(svc.tone)}">${esc(svc.label)}</strong></div>
          </div>
          ${renderCardActionBar(id, false)}
        </div>
      </article>
    `;
  }

  function renderVehicles(data) {
    const vehicles = data.vehicles.slice(0, 3);
    const cards = vehicles.length
      ? vehicles.map((vehicle) => renderVehicleCard(vehicle, data)).join('')
      : '';
    return `
      <section class="uapp-next-vehicles-section">
        <div class="uapp-next-section-head">
          <h2 class="uapp-next-section-title">Moje vozidla</h2>
          <button type="button" class="uapp-next-section-link" data-uapp-action="vehicles">Zobrazit všechna vozidla →</button>
        </div>
        <div class="uapp-next-vehicle-grid">
          ${cards || '<div class="uapp-next-empty uapp-next-empty--inline">Zatím nemáte žádné vozidlo. Přidejte první vozidlo a přehled se naplní reálnými daty.</div>'}
        </div>
        <button type="button" class="uapp-next-add-card" data-uapp-action="addVehicle">
          <span class="uapp-next-add-plus">+</span>
          <strong>Přidat další vozidlo</strong>
          <span>Rychle přidejte nové vozidlo do své správy</span>
        </button>
      </section>
    `;
  }

  function asideHead(title, actionLabel, action) {
    return `
      <div class="uapp-next-aside-head">
        <h3>${esc(title)}</h3>
        <button type="button" class="uapp-next-aside-link" data-uapp-action="${esc(action)}">${esc(actionLabel)}</button>
      </div>`;
  }

  function reminderAsideRows(data) {
    const rows = data.reminders
      .filter((item) => !item?.is_completed)
      .slice(0, 4)
      .map((item) => {
        const title = item.text || item.title || item.type || 'Připomínka';
        const vehicle = item.vehicle_name || item.vehicle_plate || '';
        const diff = daysUntil(item.due_date || item.notify_at);
        let value = formatDate(item.due_date || item.notify_at);
        let tone = 'neutral';
        if (diff != null && diff >= 0 && diff <= 60) {
          value = diff === 1 ? 'za 1 den' : `do ${diff} dnů`;
          tone = 'warn';
        } else if (diff != null && diff < 0) {
          value = 'po termínu';
          tone = 'bad';
        }
        return {
          icon: '□',
          title,
          detail: vehicle,
          value,
          tone,
          action: Number(item?.vehicle_id) > 0 ? `detailTab:ops:${Number(item.vehicle_id)}` : 'reminders',
        };
      });
    if (rows.length) return rows;
    return [];
  }

  function activityAsideRows(data) {
    const recent = Array.isArray(data.summary?.recent_activity) ? data.summary.recent_activity : [];
    const fromSummary = recent.slice(0, 4).map((item) => ({
      title: item.description || item.title || 'Aktivita',
      when: formatDateTime(item.performed_at || item.created_at),
      detail: item.vehicle_name || '',
      action: Number(item?.vehicle_id) > 0 ? `detail:${Number(item.vehicle_id)}` : 'serviceHistory',
    }));
    if (fromSummary.length) return fromSummary;
    const fromRecords = [];
    data.recordEntries.forEach(({ vehicle, records }) => {
      records.slice(0, 1).forEach((record) => {
        fromRecords.push({
          title: record.description || 'Servisní záznam',
          when: formatDateTime(record.performed_at || record.created_at),
          detail: getVehicleName(vehicle),
          action: `detailTab:service:${Number(vehicle.id)}`,
        });
      });
    });
    fromRecords.sort((a, b) => String(b.when).localeCompare(String(a.when), 'cs'));
    return fromRecords.slice(0, 4);
  }

  function grantBadge(statusRaw) {
    const status = String(statusRaw || '').toLowerCase();
    if (status.includes('approve') || status.includes('schv') || status.includes('active') || status.includes('granted')) {
      return { label: 'Schváleno', tone: 'ok' };
    }
    if (status.includes('pending') || status.includes('ček') || status.includes('wait')) {
      return { label: 'Čeká na schválení', tone: 'warn' };
    }
    if (status.includes('reject') || status.includes('odm')) {
      return { label: 'Odmítnuto', tone: 'bad' };
    }
    return { label: statusRaw || 'Stav přístupu', tone: 'neutral' };
  }

  function serviceAsideRows(data) {
    const grants = data.accessGrants.slice(0, 4).map((grant) => {
      const badge = grantBadge(grant.status);
      return {
        name: grant.service_name || grant.service_email || 'Servis',
        meta: [grant.vehicle_name || grant.vehicle_plate, grant.access_level || grant.role].filter(Boolean).join(' · ') || 'Servisní přístup',
        badge: badge.label,
        tone: badge.tone,
        action: Number(grant?.vehicle_id) > 0 ? `detailTab:access:${Number(grant.vehicle_id)}` : 'servicesDirectory',
      };
    });
    if (grants.length) return grants;
    return data.services.slice(0, 3).map((service) => ({
      name: service.name || service.email || 'Servis',
      meta: [service.city, service.email].filter(Boolean).join(' · ') || 'Uložený kontakt',
      badge: 'Bez přístupu',
      tone: 'neutral',
    }));
  }

  function renderSide(data) {
    const reminders = reminderAsideRows(data);
    const activity = activityAsideRows(data);
    const services = serviceAsideRows(data);

    const reminderList = reminders.length
      ? reminders.map((row) => `
          <li>
            <button type="button" class="uapp-next-aside-row" data-uapp-action="${esc(row.action || 'reminders')}">
              <span class="uapp-next-aside-row-icon" aria-hidden="true">${row.icon}</span>
              <div class="uapp-next-aside-row-main">
                <strong>${esc(row.title)}</strong>
                <span>${esc(row.detail || '')}</span>
              </div>
              <span class="uapp-next-aside-pill ${toneClass(row.tone)}">${esc(row.value)}</span>
              <span class="uapp-next-aside-row-arrow" aria-hidden="true">›</span>
            </button>
          </li>`).join('')
      : '<li class="uapp-next-aside-empty">Bez blížících se termínů.</li>';

    const activityList = activity.length
      ? activity.map((row) => `
          <li>
            <button type="button" class="uapp-next-aside-activity-item" data-uapp-action="${esc(row.action || 'serviceHistory')}">
              <span class="uapp-next-act-dot" aria-hidden="true"></span>
              <div>
                <strong>${esc(row.title)}</strong>
                <span>${esc(row.when)}${row.detail ? ` · ${esc(row.detail)}` : ''}</span>
              </div>
            </button>
          </li>`).join('')
      : '<li class="uapp-next-aside-empty">Zatím bez poslední aktivity.</li>';

    const serviceList = services.length
      ? services.map((row) => `
          <li>
            <button type="button" class="uapp-next-aside-access-item" data-uapp-action="${esc(row.action || 'servicesDirectory')}">
              <div class="uapp-next-aside-access-top">
                <strong>${esc(row.name)}</strong>
                <span class="uapp-next-aside-pill ${toneClass(row.tone)}">${esc(row.badge)}</span>
              </div>
              <span class="uapp-next-aside-access-meta">${esc(row.meta)}</span>
            </button>
          </li>`).join('')
      : '<li class="uapp-next-aside-empty">Zatím nejsou aktivní sdílené přístupy ani servisní kontakty.</li>';

    return `
      <aside class="uapp-next-overview-aside">
        <section class="uapp-next-aside-card">
          ${asideHead('Blížící se termíny', 'Zobrazit všechny →', 'reminders')}
          <ul class="uapp-next-aside-list">${reminderList}</ul>
          <button type="button" class="uapp-next-aside-foot-link" data-uapp-action="reminders">Zobrazit všechny připomínky →</button>
        </section>
        <section class="uapp-next-aside-card">
          ${asideHead('Poslední aktivita', 'Zobrazit vše →', 'serviceHistory')}
          <ul class="uapp-next-aside-activity">${activityList}</ul>
        </section>
        <section class="uapp-next-aside-card">
          ${asideHead('Servisy a přístupy', 'Spravovat přístupy →', 'servicesDirectory')}
          <ul class="uapp-next-aside-access">${serviceList}</ul>
        </section>
      </aside>
    `;
  }

  function renderGarageVehicleCard(vehicle, data, viewMode) {
    const id = Number(vehicle.id);
    const records = recordsFor(data, id);
    const status = getCatalogVehicleStatus(vehicle, records);
    const stk = stkCatalogLabel(vehicle);
    const ins = insuranceFieldMeta(vehicle);
    const svc = lastServiceLabel(records);
    const km = vehicle.current_mileage_km != null && vehicle.current_mileage_km !== ''
      ? `${Number(vehicle.current_mileage_km).toLocaleString('cs-CZ')} km`
      : '—';
    const searchText = [getVehicleName(vehicle), vehicle.plate, vehicle.vin, vehicle.brand, vehicle.model].filter(Boolean).join(' ').toLowerCase();

    if (viewMode === 'list') {
      return `
        <article class="uapp-next-garage-card uapp-next-garage-card--list" data-uapp-vehicle-card data-search-text="${esc(searchText)}" data-vehicle-id="${id}">
          <button type="button" class="uapp-next-garage-list-main" data-uapp-action="detail:${id}">
            <span class="${catalogBadgeClass(status.tone)}">${esc(status.label)}</span>
            <strong>${esc(getVehicleName(vehicle))}</strong>
            ${renderPlateBadge(vehicle.plate, 'sm')}
            <span class="uapp-next-garage-list-meta">${esc(stk.label)} · ${esc(svc.label)}</span>
          </button>
          <div class="uapp-next-garage-list-actions">
            <button type="button" data-uapp-action="detail:${id}">Detail</button>
            <button type="button" data-uapp-action="addRecord:${id}">Přidat záznam</button>
            <button type="button" data-uapp-action="documentsVehicle:${id}">Dokumenty</button>
            <button type="button" data-uapp-action="shareVehicle:${id}">Sdílet</button>
          </div>
        </article>`;
    }

    return `
      <article class="uapp-next-garage-card" data-uapp-vehicle-card data-search-text="${esc(searchText)}" data-vehicle-id="${id}">
        <div class="uapp-next-garage-photo">
          <div class="uapp-next-photo" data-next-photo-wrap="${id}">
            <img id="uappNextGaragePhoto-${id}" alt="Fotka vozidla ${esc(getVehicleName(vehicle))}" loading="lazy">
            <div class="uapp-next-photo-fallback">Bez fotky</div>
          </div>
          <span class="${catalogBadgeClass(status.tone)}">${esc(status.label)}</span>
        </div>
        <div class="uapp-next-garage-body">
          <h3 class="uapp-next-garage-title">${esc(getVehicleName(vehicle))}</h3>
          <div class="uapp-next-garage-sub">
            ${renderPlateBadge(vehicle.plate)}
            <span class="uapp-next-garage-vin">VIN ${esc(vehicle.vin || '—')}</span>
          </div>
          <div class="uapp-next-garage-km-row">
            <span class="uapp-next-garage-km-ico" aria-hidden="true">◔</span>
            <span>Nájezd</span>
            <strong>${esc(km)}</strong>
          </div>
          <div class="uapp-next-garage-lines">
            <div class="uapp-next-garage-line">
              <span class="uapp-next-garage-line-ico" aria-hidden="true">${ICO.quickStk}</span>
              <span>STK</span>
              <strong class="uapp-next-status-val ${toneClass(stk.tone)}">${esc(stk.label)}</strong>
            </div>
            <div class="uapp-next-garage-line">
              <span class="uapp-next-garage-line-ico" aria-hidden="true">${ICO.quickShield}</span>
              <span>Pojištění</span>
              <strong class="uapp-next-status-val ${toneClass(ins.tone)}">${esc(ins.label)}</strong>
            </div>
            <div class="uapp-next-garage-line">
              <span class="uapp-next-garage-line-ico" aria-hidden="true">${ICO.wrench}</span>
              <span>Poslední servis</span>
              <strong class="uapp-next-status-val ${toneClass(svc.tone)}">${esc(svc.label)}</strong>
            </div>
          </div>
          ${renderCardActionBar(id, true)}
        </div>
      </article>`;
  }

  function renderAddGarageCard() {
    return `
      <article class="uapp-next-garage-card uapp-next-garage-card--add">
        <div class="uapp-next-garage-add-inner">
          <div class="uapp-next-garage-add-ico" aria-hidden="true">${ICO.car}<span>+</span></div>
          <h3 class="uapp-next-garage-add-title">Přidat nové vozidlo</h3>
          <p class="uapp-next-garage-add-text">Přidejte vozidlo podle SPZ nebo VIN a mějte vše pohromadě.</p>
          <button type="button" class="uapp-next-btn uapp-next-btn-primary" data-uapp-action="addVehicle">+ Přidat vozidlo</button>
        </div>
      </article>`;
  }

  function renderFilterPill(id, label, count, dotClass) {
    const active = STATE.vehiclesFilter === id ? ' is-active' : '';
    const dot = dotClass ? `<span class="uapp-next-filter-dot ${dotClass}" aria-hidden="true"></span>` : '';
    return `<button type="button" class="uapp-next-filter-pill${active}" data-uapp-action="filter:${id}">${dot}${esc(label)} <span class="uapp-next-filter-count">${esc(String(count))}</span></button>`;
  }

  function renderVehiclesCatalog(data) {
    const counts = getFilterCounts(data);
    const total = counts.all;
    const viewMode = getStoredViewMode();
    const filtered = sortCatalogVehicles(filterCatalogVehicles(data, STATE.vehiclesFilter, STATE.vehiclesSearchQuery), data, STATE.vehiclesSort);
    const vehicleWord = total === 1 ? 'vozidlo' : (total > 1 && total < 5 ? 'vozidla' : 'vozidel');
    const gridClass = viewMode === 'list' ? 'uapp-next-garage-grid uapp-next-garage-grid--list' : 'uapp-next-garage-grid';

    const cards = filtered.length
      ? filtered.map((vehicle) => renderGarageVehicleCard(vehicle, data, viewMode)).join('')
      : `<div class="uapp-next-empty uapp-next-garage-empty">${STATE.vehiclesFilter === 'archived' ? 'Archivovaná vozidla nejsou v aktuálním seznamu API. Po archivaci vozidlo zmizí z běžného přehledu.' : 'Žádné vozidlo neodpovídá filtru nebo vyhledávání.'}</div>`;

    return `
      <section class="uapp-next-catalog" data-testid="user-app-next-vehicles">
        <header class="uapp-next-catalog-head">
          <div>
            <h1 class="uapp-next-catalog-title">Moje vozidla</h1>
            <p class="uapp-next-catalog-sub">Máte <strong>${esc(String(total))}</strong> ${vehicleWord} · <button type="button" class="uapp-next-link-btn" data-uapp-action="filter:archived">Zobrazit archivovaná</button></p>
          </div>
        </header>
        <div class="uapp-next-catalog-toolbar">
          <div class="uapp-next-filter-pills">
            ${renderFilterPill('all', 'Všechna', counts.all, '')}
            ${renderFilterPill('ok', 'V pořádku', counts.ok, 'is-green')}
            ${renderFilterPill('attention', 'Vyžaduje pozornost', counts.attention, 'is-orange')}
            ${renderFilterPill('service', 'V servisu', counts.service, 'is-red')}
            ${renderFilterPill('archived', 'V archivu', counts.archived, 'is-gray')}
          </div>
          <div class="uapp-next-catalog-controls">
            <label class="uapp-next-sort-label">
              <span>Řadit podle:</span>
              <select id="uappNextSortSelect" data-uapp-sort-select>
                <option value="activity"${STATE.vehiclesSort === 'activity' ? ' selected' : ''}>Poslední aktivity</option>
                <option value="name"${STATE.vehiclesSort === 'name' ? ' selected' : ''}>Název A–Z</option>
              </select>
            </label>
            <div class="uapp-next-view-toggle" role="group" aria-label="Zobrazení vozidel">
              <button type="button" class="${viewMode === 'grid' || viewMode === 'compact' ? 'is-active' : ''}" data-uapp-action="viewMode:grid" aria-label="Mřížka">▦</button>
              <button type="button" class="${viewMode === 'list' ? 'is-active' : ''}" data-uapp-action="viewMode:list" aria-label="Seznam">☰</button>
            </div>
          </div>
        </div>
        <div class="${gridClass}">
          ${cards}
          ${viewMode !== 'list' ? renderAddGarageCard() : ''}
        </div>
        <div class="uapp-next-catalog-summary">
          <div class="uapp-next-summary-stats">
            <div class="uapp-next-summary-stat is-blue"><span aria-hidden="true">▣</span><div><strong>${esc(String(counts.all))}</strong><span>Celkem vozidel</span></div></div>
            <div class="uapp-next-summary-stat is-orange"><span aria-hidden="true">◷</span><div><strong>${esc(String(counts.attention))}</strong><span>Vyžaduje pozornost</span></div></div>
            <div class="uapp-next-summary-stat is-red"><span aria-hidden="true">${ICO.wrench.replace('class="uapp-next-svg"', 'class="uapp-next-svg uapp-next-summary-ico"')}</span><div><strong>${esc(String(counts.service))}</strong><span>V servisu</span></div></div>
            <div class="uapp-next-summary-stat is-green"><span aria-hidden="true">✓</span><div><strong>${esc(String(counts.ok))}</strong><span>V pořádku</span></div></div>
          </div>
          <button type="button" class="uapp-next-summary-link-card" data-uapp-action="home">
            <span>Zobrazit všechna vozidla v přehledu</span>
            <span aria-hidden="true">›</span>
          </button>
        </div>
      </section>`;
  }

  function renderMainCanvas(view, data) {
    if (view === 'vehicles') {
      return `
        ${renderTopbar()}
        ${renderVehiclesCatalog(data)}
      `;
    }
    if (view === 'reminders') {
      return `
        ${renderTopbar()}
        ${renderRemindersPage(data)}
      `;
    }
    if (view === 'serviceHistory') {
      return `
        ${renderTopbar()}
        ${renderServiceHistoryPage(data)}
      `;
    }
    if (view === 'home') {
      return `
        ${renderTopbar()}
        <div class="uapp-next-overview-shell">
          ${renderHero(data)}
          ${quickCards(data)}
          <div class="uapp-next-overview-body">
            <div class="uapp-next-overview-main">
              ${renderVehicles(data)}
            </div>
            ${renderSide(data)}
          </div>
        </div>
      `;
    }
    return renderLegacySectionCanvas(view);
  }

  function renderUserAppScreen(view, data) {
    preserveLegacyOverlays();
    restoreLegacyTabMount();
    const root = ensureUserAppScreenRoot();
    if (!root) return;

    const activeView = view || 'home';
    const isLegacySection = Boolean(LEGACY_SECTION_META[activeView]);
    let testId = 'user-app-next-dashboard';
    if (isLegacySection) testId = LEGACY_SECTION_META[activeView].testId;
    else if (activeView === 'vehicles') testId = 'user-app-next-vehicles';
    else if (activeView === 'reminders') testId = 'user-app-next-reminders';
    else if (activeView === 'serviceHistory') testId = 'user-app-next-service-history';

    root.replaceChildren();
    root.innerHTML = `
      <div class="uapp-next-shell" data-testid="${testId}">
        ${renderSidebar(data, activeView)}
        <main class="uapp-next-main">
          <div class="uapp-next-canvas">
            ${renderMainCanvas(activeView, data)}
          </div>
        </main>
      </div>
    `;

    document.body.classList.toggle('user-app-next-view-vehicles', activeView === 'vehicles');
    document.body.classList.toggle('user-app-next-view-legacy', isLegacySection);
    document.body.classList.toggle('user-app-next-view-reminders', activeView === 'reminders');
    document.body.classList.toggle('user-app-next-view-service-history', activeView === 'serviceHistory');
    if (isLegacySection) {
      mountLegacyTabContent(activeView);
    }
    bindSearch();
    if (activeView === 'vehicles') {
      hydrateGarageImages(data);
      bindSortSelect();
    } else if (activeView === 'home') {
      hydrateImages(data);
    } else if (activeView === 'serviceHistory') {
      bindServiceHistoryFilters();
    }
  }

  function renderShell(data) {
    setActiveClass(true);
    const view = getActiveView() || 'home';
    renderUserAppScreen(view, data);
  }

  async function hydrateImageForVehicle(vehicle, img, scope) {
    if (!vehicle || !img) return;
    const wrap = img.closest('[data-next-photo-wrap]');
    const fallback = wrap?.querySelector('.uapp-next-photo-fallback');
    const heroFallback = wrap?.querySelector('.uapp-next-hero-car-fallback');
    if (fallback) fallback.style.display = 'grid';
    try {
      if (typeof vehiclePrimaryPhotoAvailable === 'function' && vehiclePrimaryPhotoAvailable(vehicle) && typeof hydrateVehiclePhotoPreview === 'function') {
        await hydrateVehiclePhotoPreview(Number(vehicle.id), img, scope);
      } else if (typeof fetchVehicleStockImageUrl === 'function') {
        const url = await fetchVehicleStockImageUrl(vehicle);
        if (!url) throw new Error('Bez katalogové fotky');
        if (typeof isProtectedCatalogImageUrl === 'function' && isProtectedCatalogImageUrl(url) && typeof hydrateAuthorizedImageUrl === 'function') {
          await hydrateAuthorizedImageUrl(url, img, scope);
        } else {
          img.src = url;
        }
      } else {
        throw new Error('Bez fotky');
      }
      img.style.display = 'block';
      if (fallback) fallback.style.display = 'none';
      if (heroFallback) heroFallback.style.display = 'none';
    } catch (_) {
      img.removeAttribute('src');
      img.style.display = 'none';
      if (fallback) fallback.style.display = 'grid';
    }
  }

  function hydrateImages(data) {
    const heroVehicle = data.vehicles[0];
    if (heroVehicle) {
      hydrateImageForVehicle(heroVehicle, document.getElementById('uappNextHeroPhoto'), `uapp-next-hero:${heroVehicle.id}`);
    }
    data.vehicles.slice(0, 3).forEach((vehicle) => {
      hydrateImageForVehicle(vehicle, document.getElementById(`uappNextVehiclePhoto-${Number(vehicle.id)}`), `uapp-next-card:${vehicle.id}`);
    });
  }

  function hydrateGarageImages(data) {
    (data.vehicles || []).forEach((vehicle) => {
      const img = document.getElementById(`uappNextGaragePhoto-${Number(vehicle.id)}`);
      if (img) {
        hydrateImageForVehicle(vehicle, img, `uapp-next-garage:${vehicle.id}`);
      }
    });
  }

  function setStoredViewMode(mode) {
    const next = mode === 'list' ? 'list' : 'grid';
    if (typeof SpravaVozidelStorage !== 'undefined') {
      SpravaVozidelStorage.setLocal('vehicleViewMode', next);
    } else {
      localStorage.setItem('sprava_vozidel_vehicle_view_mode', next);
      localStorage.removeItem('toozhub_vehicle_view_mode');
    }
  }

  function reRenderCatalog() {
    if (STATE.latestData && getActiveView() === 'vehicles') {
      renderUserAppScreen('vehicles', STATE.latestData);
    }
  }

  function bindSortSelect() {
    const select = document.getElementById('uappNextSortSelect');
    if (!select || select.dataset.uappBound === '1') return;
    select.dataset.uappBound = '1';
    select.addEventListener('change', () => {
      STATE.vehiclesSort = select.value === 'name' ? 'name' : 'activity';
      reRenderCatalog();
    });
  }

  function bindSearch() {
    const input = document.getElementById('uappNextSearch');
    if (!input || input.dataset.uappBound === '1') return;
    input.dataset.uappBound = '1';
    if (STATE.vehiclesSearchQuery) input.value = STATE.vehiclesSearchQuery;
    input.addEventListener('input', () => {
      const q = input.value.trim().toLowerCase();
      STATE.vehiclesSearchQuery = q;
      if (getActiveView() === 'vehicles') {
        reRenderCatalog();
        return;
      }
      document.querySelectorAll('[data-uapp-vehicle-card]').forEach((card) => {
        const haystack = String(card.getAttribute('data-search-text') || '');
        card.style.display = !q || haystack.includes(q) ? '' : 'none';
      });
    });
  }

  function clickOriginal(selector) {
    const target = document.querySelector(selector);
    if (target && typeof target.click === 'function') {
      target.click();
      return true;
    }
    return false;
  }

  function legacyPanelAnchor(event) {
    return (event && event.currentTarget) || document.querySelector('.uapp-next-icon-btn[data-uapp-action="notifications"]') || document.querySelector('.uapp-next-profile[data-uapp-action="profile"]');
  }

  function openNotificationsPanel(event) {
    preserveLegacyOverlays();
    if (hasFn('toggleAppNotificationsPanel')) {
      return window.toggleAppNotificationsPanel({
        currentTarget: legacyPanelAnchor(event),
        stopPropagation() {},
      });
    }
    return clickOriginal('#desktopNotificationsButton') || clickOriginal('#mobileNotificationsButton');
  }

  function openProfileMenu() {
    preserveLegacyOverlays();
    if (hasFn('toggleMobileProfileMenu')) return window.toggleMobileProfileMenu();
    return clickOriginal('#desktopProfileButton') || clickOriginal('#mobileProfileButton');
  }

  async function openVehicleDocuments(vehicleId) {
    const id = Number(vehicleId);
    if (!Number.isFinite(id) || id <= 0) return;
    await openUserVehicleDetailModal(id);
    return openDetailLegacyTab('documents', id);
  }

  async function openVehicleAccess(vehicleId) {
    const id = Number(vehicleId);
    if (!Number.isFinite(id) || id <= 0) return;
    await openUserVehicleDetailModal(id);
    return openDetailLegacyTab('access', id);
  }

  function openVehicleSection(vehicleId, section) {
    const id = Number(vehicleId);
    if (!Number.isFinite(id) || id <= 0) return;
    preserveLegacyOverlays();
    ensureLegacyDetailDom(id).then(() => {
      if (hasFn('openVehicleDetailFloatingSection')) {
        window.openVehicleDetailFloatingSection(section, id);
      }
    });
  }

  function suppressLegacyDetailModal() {
    const modal = document.getElementById('vehicleDetailModal');
    if (!modal) return;
    modal.classList.add('uapp-next-legacy-detail-suppressed');
    modal.style.display = 'none';
    modal.setAttribute('aria-hidden', 'true');
    if (typeof clearBodyScrollLocks === 'function') {
      try { clearBodyScrollLocks(); } catch (_) {}
    }
  }

  async function ensureLegacyDetailDom(vehicleId) {
    const id = Number(vehicleId);
    if (!Number.isFinite(id) || id <= 0) return;
    if (STATE.legacyDetailReadyFor === id) return;
    const loader = STATE.originalShowVehicleDetail;
    if (typeof loader !== 'function') return;
    await loader(id);
    suppressLegacyDetailModal();
    STATE.legacyDetailReadyFor = id;
  }

  function bindModalEsc() {
    if (STATE.modalEscBound) return;
    STATE.modalEscBound = true;
    document.addEventListener('keydown', (event) => {
      if (event.key !== 'Escape') return;
      const floatingRoot = document.getElementById('appFloatingModalRoot');
      if (floatingRoot && floatingRoot.innerHTML.trim()) return;
      if (STATE.detailModal.open) {
        if (STATE.detailModal.optionsOpen) {
          STATE.detailModal.optionsOpen = false;
          refreshDetailModalShell();
          return;
        }
        event.preventDefault();
        event.stopPropagation();
        closeUserVehicleDetailModal();
        return;
      }
      if (STATE.attentionModalOpen) {
        event.preventDefault();
        event.stopPropagation();
        closeAttentionModal();
      }
    }, true);
  }

  function closeUserVehicleDetailModal() {
    STATE.detailModal = { open: false, vehicleId: null, activeTab: 'tech', vehicle: null, records: [], optionsOpen: false };
    STATE.legacyDetailReadyFor = null;
    document.body.classList.remove('uapp-next-detail-open');
    const root = document.getElementById(DETAIL_MODAL_ID);
    if (root) root.remove();
    if (hasFn('closeVehicleModal')) {
      try { window.closeVehicleModal(); } catch (_) {}
    }
  }

  function detailSummaryCards(vehicle, records, data) {
    const id = Number(vehicle.id);
    const stk = stkFieldMeta(vehicle);
    const ins = insuranceFieldMeta(vehicle);
    const svc = lastServiceLabel(records);
    const km = vehicle.current_mileage_km != null && vehicle.current_mileage_km !== ''
      ? `${Number(vehicle.current_mileage_km).toLocaleString('cs-CZ')} km`
      : '—';
    const grants = (data?.accessGrants || []).filter((g) => Number(g.vehicle_id) === id);
    const pendingAccess = grants.filter((g) => {
      const st = String(g?.status || '').toLowerCase();
      return st.includes('pending') || st.includes('ček') || st.includes('wait');
    }).length;
    const stkDate = getStkValue(vehicle) ? formatDate(getStkValue(vehicle)) : 'Nezadáno';
    const insDate = vehicle.insurance_valid_until ? formatDate(vehicle.insurance_valid_until) : 'Nezadáno';
    const latestRecord = (records || []).slice().sort((a, b) => (Date.parse(b?.performed_at || b?.created_at) || 0) - (Date.parse(a?.performed_at || a?.created_at) || 0))[0];
    const svcDate = latestRecord ? formatDate(latestRecord.performed_at || latestRecord.created_at) : 'Bez záznamu';
    return [
      { key: 'stk', tone: stk.tone, icon: '◷', title: 'STK / SME', value: stk.label, sub: stkDate, action: `detailTab:ops:${id}` },
      { key: 'ins', tone: ins.tone, icon: '⛨', title: 'Pojištění', value: ins.label, sub: insDate, action: `detailTab:ops:${id}` },
      { key: 'km', tone: 'ok', icon: '◔', title: 'Nájezd', value: km, sub: 'Aktuální stav tachometru', action: `detailTab:ops:${id}` },
      { key: 'svc', tone: svc.tone, icon: '⚙', title: 'Poslední servis', value: svc.label, sub: svcDate, action: `detailTab:service:${id}` },
      { key: 'docs', tone: records.length ? 'ok' : 'warn', icon: '▣', title: 'Dokumenty', value: String(records.length || '0'), sub: records.length ? 'Servisní záznamy a přílohy' : 'Bez příloh', action: `detailTab:documents:${id}` },
      { key: 'access', tone: pendingAccess ? 'warn' : 'ok', icon: '👥', title: 'Přístupy servisů', value: String(grants.length), sub: pendingAccess ? `${pendingAccess} čeká na schválení` : 'Aktivní servisní přístupy', action: `detailTab:access:${id}` },
    ];
  }

  function detailTimelineRows(records) {
    const sorted = (records || []).slice().sort((a, b) => (Date.parse(b?.performed_at || b?.created_at) || 0) - (Date.parse(a?.performed_at || a?.created_at) || 0));
    return sorted.slice(0, 6).map((record) => {
      const meta = serviceRecordStatusMeta(record);
      const iconClass = serviceRecordIconClass(record);
      return {
        title: record.description || record.service_type || 'Servisní záznam',
        when: formatDateTime(record.performed_at || record.created_at),
        detail: formatMoneyCzk(record?.total_price ?? record?.price),
        tone: meta.tone,
        iconClass,
        statusLabel: meta.label,
      };
    });
  }

  function vehicleIdentificationVerified(vehicle) {
    return Boolean(String(vehicle?.vin || '').trim() && String(vehicle?.plate || '').trim());
  }

  function detailReminderRows(data, vehicleId) {
    return (data?.reminders || [])
      .filter((item) => !item?.is_completed && Number(item?.vehicle_id) === Number(vehicleId))
      .slice(0, 4)
      .map((item) => {
        const diff = daysUntil(item.due_date || item.notify_at);
        let value = formatDate(item.due_date || item.notify_at);
        if (diff != null && diff >= 0 && diff <= 120) {
          value = diff === 0 ? 'dnes' : (diff === 1 ? 'zítra' : `za ${diff} dnů`);
        }
        return { title: item.text || item.title || item.type || 'Připomínka', value };
      });
  }

  function renderDetailTechTab(vehicle) {
    const rows = [
      ['Značka', vehicle.brand || '—'],
      ['Typ / model', [vehicle.brand, vehicle.model].filter(Boolean).join(' ') || '—'],
      ['VIN', vehicle.vin || '—'],
      ['SPZ', vehicle.plate || '—'],
      ['Barva', vehicle.color || '—'],
      ['Emisní norma', vehicle.emission_norm || vehicle.emission_class || '—'],
      ['Palivo', vehicleFuelLabel(vehicle)],
      ['Objem', vehicleVolumeLabel(vehicle)],
      ['Výkon', vehiclePowerLabel(vehicle)],
      ['Převodovka', vehicle.transmission || '—'],
      ['Rok výroby', vehicle.year || '—'],
      ['Motor', vehicle.engine || '—'],
    ];
    const notes = String(vehicle.notes || '').trim();
    return `
      <div class="uapp-next-detail-tab-grid">
        <section class="uapp-next-detail-panel">
          <h3 class="uapp-next-detail-panel-title">Základní informace</h3>
          <dl class="uapp-next-detail-spec">
            ${rows.map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${esc(String(v))}</dd></div>`).join('')}
          </dl>
        </section>
        <section class="uapp-next-detail-panel">
          <h3 class="uapp-next-detail-panel-title">Identifikace vozidla</h3>
          <div class="uapp-next-detail-id-box">
            <ul class="uapp-next-detail-id-list">
              <li class="${vehicle.vin ? 'is-ok' : 'is-muted'}">${vehicle.vin ? '✓' : '○'} VIN ${vehicle.vin ? 'evidován' : 'neuveden'}</li>
              <li class="${vehicle.plate ? 'is-ok' : 'is-muted'}">${vehicle.plate ? '✓' : '○'} SPZ ${vehicle.plate ? 'evidována' : 'neuvedena'}</li>
              <li class="${vehicle.stk_valid_until ? 'is-ok' : 'is-muted'}">${vehicle.stk_valid_until ? '✓' : '○'} STK ${vehicle.stk_valid_until ? 'evidována' : 'neuvedena'}</li>
            </ul>
            ${hasFn('downloadVehicleVerifiedReportFromHub') ? `<button type="button" class="uapp-next-btn uapp-next-btn-secondary uapp-next-detail-id-btn" data-uapp-action="detailVerifiedPdf:${Number(vehicle.id)}">Zobrazit protokol kontroly</button>` : ''}
          </div>
        </section>
      </div>
      <section class="uapp-next-detail-note">
        <div class="uapp-next-detail-note-head">
          <h3 class="uapp-next-detail-panel-title">Poznámka k vozidlu</h3>
        </div>
        <p>${esc(notes || '—')}</p>
      </section>`;
  }

  function renderDetailOptionsMenu(vehicleId) {
    const id = Number(vehicleId);
    const items = [];
    if (hasFn('openAddServiceRecordModal')) items.push([`addRecord:${id}`, 'Přidat servisní záznam']);
    items.push([`detailTab:documents:${id}`, 'Nahrát dokument']);
    items.push([`detailTab:access:${id}`, 'Sdílet se servisem']);
    items.push([`detailTab:ops:${id}`, 'Připomínky a STK']);
    items.push([`detailTab:gallery:${id}`, 'Fotogalerie a QR']);
    if (hasFn('downloadVehicleReportFromHub')) items.push([`detailPdf:${id}`, 'Exportovat PDF report']);
    if (hasFn('refreshExistingVehicleFromVin')) items.push([`detailVinRefresh:${id}`, 'Obnovit údaje z VIN']);
    return items.map(([action, label]) => (
      `<button type="button" class="uapp-next-detail-options-item" data-uapp-action="${esc(action)}">${esc(label)}</button>`
    )).join('');
  }

  function refreshDetailModalShell() {
    if (!STATE.detailModal.open || !STATE.detailModal.vehicle) return;
    mountDetailModalShell(renderDetailModalContent(
      STATE.detailModal.vehicle,
      STATE.detailModal.records,
      STATE.latestData || {},
    ));
    const img = document.getElementById(`uappNextDetailPhoto-${Number(STATE.detailModal.vehicleId)}`);
    if (img) hydrateImageForVehicle(STATE.detailModal.vehicle, img, `uapp-next-detail:${STATE.detailModal.vehicleId}`);
  }

  function closeDetailOptionsMenu() {
    if (!STATE.detailModal.optionsOpen) return;
    STATE.detailModal.optionsOpen = false;
    refreshDetailModalShell();
  }

  function renderDetailModalContent(vehicle, records, data) {
    const id = Number(vehicle.id);
    const status = getCatalogVehicleStatus(vehicle, records);
    const tabs = [
      ['tech', 'Technické údaje'],
      ['service', 'Servisní historie'],
      ['documents', 'Dokumenty'],
      ['gallery', 'Fotogalerie'],
      ['reminders', 'Připomínky'],
      ['access', 'Přístupy a sdílení'],
    ];
    const summary = detailSummaryCards(vehicle, records, data);
    const timeline = detailTimelineRows(records);
    const upcoming = detailReminderRows(data, id);
    const activeTab = STATE.detailModal.activeTab || 'tech';
    const optionsOpen = Boolean(STATE.detailModal.optionsOpen);

    return `
      <div class="uapp-next-detail-modal" role="dialog" aria-modal="true" aria-labelledby="uappNextDetailTitle">
        <button type="button" class="uapp-next-detail-close" data-uapp-action="detailClose" aria-label="Zavřít detail">×</button>
        <div class="uapp-next-detail-scroll">
          <nav class="uapp-next-detail-crumb" aria-label="Drobečková navigace">
            <button type="button" class="uapp-next-link-btn" data-uapp-action="vehicles">Moje vozidla</button>
            <span aria-hidden="true">/</span>
            <span>Detail vozidla</span>
          </nav>
          <section class="uapp-next-detail-hero">
            <div class="uapp-next-detail-photo">
              <div class="uapp-next-photo" data-next-photo-wrap="detail-${id}">
                <img id="uappNextDetailPhoto-${id}" alt="Fotka vozidla ${esc(getVehicleName(vehicle))}" loading="lazy">
                <div class="uapp-next-photo-fallback">Bez fotky</div>
              </div>
            </div>
            <div class="uapp-next-detail-hero-body">
              <div class="uapp-next-detail-hero-top">
                <h2 id="uappNextDetailTitle" class="uapp-next-detail-title">${esc(getVehicleName(vehicle))}</h2>
                <div class="uapp-next-detail-menu-wrap">
                  <button type="button" class="uapp-next-detail-menu${optionsOpen ? ' is-open' : ''}" data-uapp-action="detailOptionsToggle:${id}" aria-label="Možnosti vozidla" aria-expanded="${optionsOpen}" aria-haspopup="menu">⋯</button>
                  ${optionsOpen ? `<div class="uapp-next-detail-options" role="menu">${renderDetailOptionsMenu(id)}</div>` : ''}
                </div>
              </div>
              <div class="uapp-next-detail-hero-meta">
                ${renderPlateBadge(vehicle.plate, 'lg')}
                <span class="${catalogBadgeClass(status.tone)}">${esc(status.label)}</span>
              </div>
              <dl class="uapp-next-detail-metrics-inline">
                <div><dt>VIN</dt><dd>${esc(vehicle.vin || '—')}</dd></div>
                <div><dt>Rok výroby</dt><dd>${esc(vehicle.year || '—')}</dd></div>
                <div><dt>Palivo</dt><dd>${esc(vehicleFuelLabel(vehicle))}</dd></div>
                <div><dt>Výkon</dt><dd>${esc(vehiclePowerLabel(vehicle))}</dd></div>
                <div><dt>Objem</dt><dd>${esc(vehicleVolumeLabel(vehicle))}</dd></div>
              </dl>
              <div class="uapp-next-detail-hero-actions">
                ${hasFn('openAddServiceRecordModal') ? `<button type="button" class="uapp-next-btn uapp-next-btn-primary" data-uapp-action="addRecord:${id}">+ <span>Přidat záznam</span></button>` : ''}
                <button type="button" class="uapp-next-btn uapp-next-btn-secondary" data-uapp-action="detailTab:documents:${id}">${ICO.upload}<span>Nahrát dokument</span></button>
                <button type="button" class="uapp-next-btn uapp-next-btn-secondary" data-uapp-action="detailTab:access:${id}">${ICO.share}<span>Sdílet se servisem</span></button>
              </div>
            </div>
          </section>
          <div class="uapp-next-detail-summary-grid">
            ${summary.map((card) => `
              <article class="uapp-next-detail-summary-card is-${esc(card.tone)}">
                <div class="uapp-next-detail-summary-ico" aria-hidden="true">${card.icon}</div>
                <div>
                  <span class="uapp-next-detail-summary-k">${esc(card.title)}</span>
                  <strong>${esc(card.value)}</strong>
                  <span class="uapp-next-detail-summary-sub">${esc(card.sub)}</span>
                  ${card.action ? `<button type="button" class="uapp-next-detail-summary-link" data-uapp-action="${esc(card.action)}">Zobrazit ›</button>` : ''}
                </div>
              </article>`).join('')}
          </div>
          <div class="uapp-next-detail-body">
            <div class="uapp-next-detail-main">
              <div class="uapp-next-detail-tabs" role="tablist" aria-label="Sekce detailu vozidla">
                ${tabs.map(([key, label]) => `<button type="button" role="tab" class="uapp-next-detail-tab${activeTab === key ? ' is-active' : ''}" data-uapp-action="detailTab:${key}:${id}" aria-selected="${activeTab === key}">${esc(label)}</button>`).join('')}
              </div>
              <div class="uapp-next-detail-tab-content">
                ${activeTab === 'tech' ? renderDetailTechTab(vehicle) : `<div class="uapp-next-detail-tab-placeholder"><p>Obsah sekce se otevře v plné verzi detailu.</p><button type="button" class="uapp-next-btn uapp-next-btn-primary" data-uapp-action="detailTab:${activeTab}:${id}">Otevřít ${esc(tabs.find((t) => t[0] === activeTab)?.[1] || 'sekci')}</button></div>`}
              </div>
            </div>
            <aside class="uapp-next-detail-aside">
              <section class="uapp-next-detail-aside-card">
                <h3>Časová osa vozidla</h3>
                ${timeline.length ? timeline.map((row) => `
                  <div class="uapp-next-detail-timeline-item is-${row.tone}">
                    <strong>${esc(row.title)}</strong>
                    <span>${esc(row.when)}</span>
                  </div>`).join('') : '<p class="uapp-next-detail-empty">Zatím bez záznamů.</p>'}
              </section>
              <section class="uapp-next-detail-aside-card">
                <h3>Nejbližší termíny</h3>
                ${upcoming.length ? upcoming.map((row) => `
                  <div class="uapp-next-detail-upcoming-item">
                    <strong>${esc(row.title)}</strong>
                    <span>${esc(row.value)}</span>
                  </div>`).join('') : '<p class="uapp-next-detail-empty">Žádné blížící se termíny.</p>'}
              </section>
              <section class="uapp-next-detail-aside-card">
                <h3>Rychlé akce</h3>
                <div class="uapp-next-detail-quick">
                  ${hasFn('openAddServiceRecordModal') ? `<button type="button" data-uapp-action="addRecord:${id}">+ Přidat servisní úkon</button>` : ''}
                  <button type="button" data-uapp-action="detailTab:ops:${id}">+ Přidat záznam tachometru</button>
                  <button type="button" data-uapp-action="detailTab:documents:${id}">Nahrát dokument</button>
                  ${hasFn('downloadVehicleReportFromHub') ? `<button type="button" data-uapp-action="detailPdf:${id}">Exportovat PDF report</button>` : ''}
                  ${hasFn('openVehicleDetailFloatingSection') ? `<button type="button" data-uapp-action="detailTab:gallery:${id}">Generovat QR historii</button>` : ''}
                </div>
              </section>
            </aside>
          </div>
        </div>
      </div>`;
  }

  function mountDetailModalShell(html) {
    let backdrop = document.getElementById(DETAIL_MODAL_ID);
    if (!backdrop) {
      backdrop = document.createElement('div');
      backdrop.id = DETAIL_MODAL_ID;
      backdrop.className = 'uapp-next-detail-backdrop';
      backdrop.setAttribute('data-testid', 'user-app-next-vehicle-detail');
      document.body.appendChild(backdrop);
    }
    backdrop.innerHTML = `<div class="uapp-next-detail-backdrop-inner">${html}</div>`;
    backdrop.onclick = (event) => {
      if (event.target === backdrop || event.target.classList.contains('uapp-next-detail-backdrop-inner')) {
        closeUserVehicleDetailModal();
      }
    };
  }

  async function openUserVehicleDetailModal(vehicleId) {
    const id = Number(vehicleId);
    if (!Number.isFinite(id) || id <= 0) return;
    bindModalEsc();
    STATE.detailModal = { open: true, vehicleId: id, activeTab: 'tech', vehicle: null, records: [], optionsOpen: false };
    document.body.classList.add('uapp-next-detail-open');
    mountDetailModalShell('<div class="uapp-next-loading">Načítám detail vozidla…</div>');

    let vehicle = (STATE.latestData?.vehicles || []).find((v) => Number(v.id) === id) || null;
    let records = recordsFor(STATE.latestData || {}, id);
    if (apiReady()) {
      vehicle = await safeApi(`/api/v1/vehicles/${id}`, vehicle);
      records = await safeApi(`/api/v1/vehicles/${id}/records`, records);
    }

    if (!vehicle) {
      mountDetailModalShell('<div class="uapp-next-empty">Vozidlo se nepodařilo načíst.</div>');
      return;
    }

    STATE.detailModal.vehicle = vehicle;
    STATE.detailModal.records = Array.isArray(records) ? records : [];
    const data = STATE.latestData || { vehicles: [vehicle], reminders: [], accessGrants: [], recordEntries: [{ vehicle, records: STATE.detailModal.records }] };
    mountDetailModalShell(renderDetailModalContent(vehicle, STATE.detailModal.records, data));
    void ensureLegacyDetailDom(id);
    const img = document.getElementById(`uappNextDetailPhoto-${id}`);
    if (img) hydrateImageForVehicle(vehicle, img, `uapp-next-detail:${id}`);
  }

  function openDetailLegacyTab(tabKey, vehicleId) {
    const id = Number(vehicleId);
    const map = { tech: 'basic', service: 'service', documents: 'documents', gallery: 'gallery', reminders: 'ops', access: 'access', ops: 'ops' };
    const section = map[String(tabKey || '').toLowerCase()] || 'basic';
    if (section === 'basic') {
      STATE.detailModal.activeTab = 'tech';
      if (STATE.detailModal.vehicle) {
        mountDetailModalShell(renderDetailModalContent(STATE.detailModal.vehicle, STATE.detailModal.records, STATE.latestData || {}));
        const img = document.getElementById(`uappNextDetailPhoto-${id}`);
        if (img) hydrateImageForVehicle(STATE.detailModal.vehicle, img, `uapp-next-detail:${id}`);
      }
      return;
    }
    ensureLegacyDetailDom(id).then(() => {
      if (hasFn('openVehicleDetailFloatingSection')) {
        window.openVehicleDetailFloatingSection(section, id);
      }
    });
  }

  function runAction(action, event) {
    const [name, rawId] = String(action || '').split(':');
    const id = Number(rawId || 0);
    if (name === 'detailOptionsToggle' && id) {
      STATE.detailModal.optionsOpen = !STATE.detailModal.optionsOpen;
      refreshDetailModalShell();
      return;
    }
    if (STATE.detailModal.open && STATE.detailModal.optionsOpen) {
      STATE.detailModal.optionsOpen = false;
      refreshDetailModalShell();
    }
    if (name === 'home' && hasFn('switchTab')) { STATE.viewOverride = null; return window.switchTab('home'); }
    if (name === 'vehicles' && hasFn('switchTab')) { STATE.viewOverride = null; return window.switchTab('vehicles'); }
    if (name === 'reminders' && hasFn('switchTab')) { STATE.viewOverride = null; return window.switchTab('reminders'); }
    if (name === 'documents' && hasFn('switchTab')) { STATE.viewOverride = null; return window.switchTab('documents'); }
    if (name === 'servicesDirectory' && hasFn('switchTab')) { STATE.viewOverride = null; return window.switchTab('servicesDirectory'); }
    if (name === 'account' && hasFn('switchTab')) { STATE.viewOverride = null; return window.switchTab('account'); }
    if (name === 'invoices' && hasFn('switchTab')) { STATE.viewOverride = null; return window.switchTab('documents'); }
    if (name === 'serviceHistory') { STATE.viewOverride = 'serviceHistory'; return render(); }
    if (name === 'serviceHistoryAdd') {
      if (hasFn('openAddServiceRecordModal')) return window.openAddServiceRecordModal();
      return;
    }
    if (name === 'loadMoreServiceHistory') {
      STATE.serviceHistoryLimit = (STATE.serviceHistoryLimit || 8) + 8;
      return render();
    }
    if (name === 'serviceHistoryResetFilters') {
      STATE.serviceHistoryFilters = { vehicle: 'all', period: '2y', type: 'all', service: 'all', docStatus: 'all' };
      STATE.serviceHistoryLimit = 8;
      return render();
    }
    if (name === 'serviceRecordDetail' && id) return openUserVehicleDetailModal(id);
    if (name === 'serviceRecordEdit') {
      const parts = String(action || '').split(':');
      const vehicleId = Number(parts[1] || 0);
      const recordId = Number(parts[2] || 0);
      if (vehicleId && recordId && hasFn('openEditServiceRecordModal')) {
        return window.openEditServiceRecordModal(recordId, vehicleId);
      }
      return;
    }
    if (name === 'newReminder') {
      if (hasFn('showCreateReminderForm')) return window.showCreateReminderForm();
      return;
    }
    if (name === 'reminderComplete' && id && apiReady()) {
      return apiCall(`/api/v1/reminders/${id}`, 'PUT', { is_completed: true })
        .then(() => render())
        .catch((err) => console.warn('[USER_APP_NEXT] reminder complete failed', err));
    }
    if (name === 'reminderDetail' && id && hasFn('editReminder')) return window.editReminder(id);
    if (name === 'reminderSnooze' && id && hasFn('editReminder')) return window.editReminder(id);
    if (name === 'remindersTipClose') { STATE.remindersTipHidden = true; return render(); }
    if (name === 'help') {
      if (hasFn('openHowToHubModal')) return window.openHowToHubModal();
      if (hasFn('switchTab')) return window.switchTab('support');
    }
    if (name === 'collapse') return document.body.classList.toggle('user-app-next-sidebar-collapsed');
    if (name === 'addVehicle') {
      if (hasFn('openAddVehicleModal')) return window.openAddVehicleModal();
      return clickOriginal('#btnOpenAddVehicleModal');
    }
    if (name === 'notifications') return openNotificationsPanel(event);
    if (name === 'profile') return openProfileMenu();
    if (name === 'detail' && id) return openUserVehicleDetailModal(id);
    if (name === 'addRecord' && id) {
      if (hasFn('openAddServiceRecordModal')) return window.openAddServiceRecordModal(id);
      console.warn('[USER_APP_NEXT] BLOCKER: openAddServiceRecordModal missing');
      return;
    }
    if (name === 'documentsVehicle' && id) return openVehicleDocuments(id);
    if (name === 'shareVehicle' && id) return openVehicleAccess(id);
    if (name === 'attentionOpen') return openAttentionModal();
    if (name === 'attentionClose') return closeAttentionModal();
    if (name === 'attentionAllVehicles') {
      closeAttentionModal();
      if (hasFn('switchTab')) return window.switchTab('vehicles');
    }
    if (name === 'attentionResolve') {
      const idx = Number(rawId);
      const item = STATE.attentionItems[idx];
      if (!item?.action) return;
      closeAttentionModal();
      return runAction(item.action, event);
    }
    if (name === 'detailClose') return closeUserVehicleDetailModal();
    if (name === 'detailEdit' && id) {
      if (STATE.detailModal.open) {
        STATE.detailModal.activeTab = 'tech';
        refreshDetailModalShell();
        return;
      }
      return ensureLegacyDetailDom(id).then(() => {
        if (hasFn('openVehicleDetailFloatingSection')) window.openVehicleDetailFloatingSection('basic', id);
        else if (hasFn('startEditModal')) window.startEditModal('nickname', id);
      });
    }
    if (name === 'detailVinRefresh' && id && hasFn('refreshExistingVehicleFromVin')) {
      return window.refreshExistingVehicleFromVin(id);
    }
    if (name === 'detailTab') {
      const parts = String(action || '').split(':');
      const tabKey = parts[1];
      const vid = Number(parts[2] || 0);
      if (tabKey && vid) {
        if (tabKey === 'tech') {
          STATE.detailModal.activeTab = 'tech';
          if (STATE.detailModal.vehicle) {
            mountDetailModalShell(renderDetailModalContent(STATE.detailModal.vehicle, STATE.detailModal.records, STATE.latestData || {}));
          }
          return;
        }
        STATE.detailModal.activeTab = tabKey;
        return openDetailLegacyTab(tabKey, vid);
      }
    }
    if (name === 'detailPdf' && id && hasFn('downloadVehicleReportFromHub')) return window.downloadVehicleReportFromHub(id);
    if (name === 'detailVerifiedPdf' && id && hasFn('downloadVehicleVerifiedReportFromHub')) return window.downloadVehicleVerifiedReportFromHub(id);
    if (name === 'detailQrOpen' && id) return openDetailLegacyTab('gallery', id);
    if (name === 'filter') {
      const key = String(rawId || 'all');
      if (['all', 'ok', 'attention', 'service', 'archived'].includes(key)) {
        STATE.vehiclesFilter = key;
        reRenderCatalog();
      }
      return;
    }
    if (name === 'viewMode') {
      setStoredViewMode(rawId === 'list' ? 'list' : 'grid');
      reRenderCatalog();
      return;
    }
    console.warn('[USER_APP_NEXT] BLOCKER: handler not found for action', action);
  }

  async function render() {
    if (!shouldActivate()) {
      setActiveClass(false);
      return;
    }
    const token = ++STATE.renderToken;
    setActiveClass(true);
    preserveLegacyOverlays();
    const view = getActiveView() || 'home';
    const root = ensureUserAppScreenRoot();
    if (root && !root.querySelector('.uapp-next-shell')) {
      root.replaceChildren();
      const loading = document.createElement('div');
      loading.className = 'uapp-next-loading';
      loading.textContent = 'Načítám...';
      root.appendChild(loading);
    }
    const data = await loadData();
    if (token !== STATE.renderToken || !shouldActivate()) return;
    renderShell(data);
  }

  function installHooks() {
    if (STATE.installed) return;
    STATE.installed = true;

    const originalLoadHomeDashboard = window.loadHomeDashboard;
    if (typeof originalLoadHomeDashboard === 'function') {
      window.loadHomeDashboard = async function () {
        const result = await originalLoadHomeDashboard.apply(this, arguments);
        if (shouldActivate()) {
          await render();
        } else {
          setActiveClass(false);
        }
        return result;
      };
    }

    const originalLoadVehicles = window.loadVehicles;
    if (typeof originalLoadVehicles === 'function') {
      window.loadVehicles = async function () {
        if (shouldActivate()) {
          if (getActiveView() === 'vehicles') {
            await render();
          }
          return;
        }
        return originalLoadVehicles.apply(this, arguments);
      };
    }

    const originalSwitchTab = window.switchTab;
    if (typeof originalSwitchTab === 'function') {
      window.switchTab = function () {
        const tabName = arguments[0];
        if (tabName !== 'serviceHistory') STATE.viewOverride = null;
        const result = originalSwitchTab.apply(this, arguments);
        window.setTimeout(() => {
          if (shouldActivate()) {
            render();
          } else {
            setActiveClass(false);
          }
        }, 0);
        return result;
      };
    }

    if (typeof window.showVehicleDetail === 'function') {
      STATE.originalShowVehicleDetail = window.showVehicleDetail;
      window.showVehicleDetail = async function (vehicleId) {
        if (shouldActivate()) {
          return openUserVehicleDetailModal(vehicleId);
        }
        return STATE.originalShowVehicleDetail.apply(this, arguments);
      };
    }

    document.addEventListener('click', (event) => {
      const trigger = event.target && event.target.closest && event.target.closest('[data-uapp-action]');
      if (!trigger || trigger.disabled || trigger.getAttribute('aria-disabled') === 'true') return;
      event.preventDefault();
      event.stopPropagation();
      if (typeof event.stopImmediatePropagation === 'function') {
        event.stopImmediatePropagation();
      }
      runAction(trigger.getAttribute('data-uapp-action'), event);
    });

    window.UserAppNext = {
      render,
      runAction,
      openVehicleSection,
      openUserVehicleDetailModal,
      closeUserVehicleDetailModal,
      get audit() {
        return {
          loadHomeDashboard: hasFn('loadHomeDashboard'),
          loadVehicles: hasFn('loadVehicles'),
          showVehicleDetail: hasFn('showVehicleDetail'),
          openAddVehicleModal: hasFn('openAddVehicleModal'),
          openAddServiceRecordModal: hasFn('openAddServiceRecordModal'),
          notifications: hasFn('toggleAppNotificationsPanel'),
          profileMenu: hasFn('toggleMobileProfileMenu'),
        };
      },
    };
  }

  function boot() {
    preserveLegacyOverlays();
    installHooks();
    window.setTimeout(() => {
      if (shouldActivate()) render();
    }, 0);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot, { once: true });
  } else {
    boot();
  }
})();
