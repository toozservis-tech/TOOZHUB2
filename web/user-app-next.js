(function () {
  'use strict';

  const STATE = {
    installed: false,
    renderToken: 0,
    lastVehicles: [],
    latestData: null,
  };

  const LOGO_SRC = '/web/assets/landing/sprava-vozidel-logo.jpeg';

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

  function shouldActivate() {
    const homeTab = document.getElementById('homeTab');
    const appShell = document.getElementById('app-shell');
    return Boolean(
      document.body.classList.contains('route-app-view')
      && appShell
      && !appShell.hidden
      && homeTab
      && homeTab.classList.contains('active')
      && !isServiceMode()
      && isAuthed()
    );
  }

  function fullName() {
    const u = user() || {};
    const raw = String(u.name || u.email || '').trim();
    if (!raw) return 'uživateli';
    const visible = raw.includes('@') ? raw.split('@')[0].replace(/[._-]+/g, ' ') : raw;
    return visible.split(/\s+/).filter(Boolean)[0] || 'uživateli';
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
    if (!value) return 'Bez termínu';
    try {
      if (typeof formatDateCZ === 'function') return formatDateCZ(value);
    } catch (_) {}
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? 'Bez termínu' : d.toLocaleDateString('cs-CZ');
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

  function getVehicleName(vehicle) {
    return String(vehicle?.nickname || vehicle?.name || [vehicle?.brand, vehicle?.model].filter(Boolean).join(' ') || vehicle?.plate || `Vozidlo #${vehicle?.id || ''}`).trim();
  }

  function getVehicleSubtitle(vehicle) {
    return [vehicle?.brand, vehicle?.model, vehicle?.year].filter(Boolean).join(' · ') || vehicle?.plate || 'Vozidlo';
  }

  function getStkValue(vehicle) {
    if (vehicle?.stk_valid_until) return vehicle.stk_valid_until;
    if (typeof getVehicleStkDateValueSimple === 'function') {
      try {
        return getVehicleStkDateValueSimple(vehicle);
      } catch (_) {}
    }
    return null;
  }

  function stkMeta(vehicle) {
    const value = getStkValue(vehicle);
    const diff = daysUntil(value);
    if (diff == null) return { label: 'STK neznámá', className: 'is-muted', hint: 'Bez data' };
    if (diff < 0) return { label: 'STK po termínu', className: 'is-warn', hint: formatDate(value) };
    if (diff <= 30) return { label: `STK za ${diff} dní`, className: 'is-warn', hint: formatDate(value) };
    return { label: 'V pořádku', className: '', hint: formatDate(value) };
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
    const targets = vehicles.slice(0, 3).filter((vehicle) => Number(vehicle?.id) > 0);
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
    const data = {
      summary: summary && typeof summary === 'object' ? summary : {},
      vehicles: vehicleList,
      reminders: Array.isArray(reminders) ? reminders : [],
      accessGrants: Array.isArray(accessPayload?.grants) ? accessPayload.grants : [],
      services: Array.isArray(contactsPayload?.services) ? contactsPayload.services : [],
      recordEntries,
    };
    STATE.latestData = data;
    return data;
  }

  function detachedPanels() {
    ['appNotificationsPanel', 'mobileProfileMenu'].forEach((id) => {
      const el = document.getElementById(id);
      if (el && el.parentElement !== document.body) {
        document.body.appendChild(el);
      }
    });
  }

  function setActiveClass(active) {
    document.body.classList.toggle('user-app-next-active', Boolean(active));
    if (!active) {
      document.body.classList.remove('user-app-next-sidebar-collapsed');
    }
  }

  function navButton(label, icon, action, active) {
    return `<button type="button" class="${active ? 'is-active' : ''}" data-uapp-action="${esc(action)}"><span class="uapp-next-ico" aria-hidden="true">${esc(icon)}</span><span class="uapp-next-nav-label">${esc(label)}</span></button>`;
  }

  function renderSidebar() {
    return `
      <aside class="uapp-next-sidebar" aria-label="Navigace uživatelského rozhraní">
        <div class="uapp-next-brand">
          <img src="${LOGO_SRC}" alt="" width="84" height="84">
          <span>Správa vozidel</span>
        </div>
        <nav class="uapp-next-nav" aria-label="Sekce aplikace">
          ${navButton('Přehled', '⌂', 'home', true)}
          ${navButton('Moje vozidla', '▤', 'vehicles', false)}
          ${navButton('Servisní historie', '◷', 'serviceHistory', false)}
          ${navButton('Připomínky', '□', 'reminders', false)}
          ${navButton('Dokumenty', '▣', 'documents', false)}
          ${navButton('Servisy', '◇', 'servicesDirectory', false)}
          ${navButton('Faktury', 'Kč', 'invoices', false)}
          ${navButton('Nastavení', '⚙', 'account', false)}
        </nav>
        <div class="uapp-next-sidebar-bottom">
          <button type="button" class="uapp-next-help" data-uapp-action="help">
            <strong>Potřebujete pomoc?</strong>
            <span>Otevřít průvodce a podporu.</span>
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
          <span aria-hidden="true">⌕</span>
          <input id="uappNextSearch" type="search" autocomplete="off" placeholder="Hledat podle SPZ, VIN, značky...">
        </label>
        <div class="uapp-next-top-actions">
          <button type="button" class="uapp-next-btn uapp-next-btn-primary" data-uapp-action="addVehicle">+ Přidat vozidlo</button>
          <button type="button" class="uapp-next-btn uapp-next-icon-btn" data-uapp-action="notifications" aria-label="Oznámení" data-count="${esc(count || '0')}">🔔</button>
        </div>
        <button type="button" class="uapp-next-profile" data-uapp-action="profile" aria-label="Profil uživatele">
          <span class="uapp-next-avatar" aria-hidden="true">${esc(initials())}</span>
          <div><span>${esc(user()?.name || fullName())}</span><small>Profil a účet</small></div>
        </button>
      </header>
    `;
  }

  function heroSummary(data) {
    const summary = data.summary || {};
    const total = Number(summary.vehicles_total ?? data.vehicles.length) || 0;
    const stkSoon = Number(summary.stk_soon || 0);
    const activeReminders = Number(summary.active_reminders || data.reminders.filter((r) => !r?.is_completed).length || 0);
    const notifications = (window.__systemNotificationsLastItems || []).length || 0;
    return `Máte ${total} ${total === 1 ? 'vozidlo' : (total > 1 && total < 5 ? 'vozidla' : 'vozidel')}, ${stkSoon} blížící se STK, ${activeReminders} aktivních připomínek a ${notifications} upozornění.`;
  }

  function renderHero(data) {
    const vehicle = data.vehicles[0] || null;
    const total = data.vehicles.length;
    const okCount = data.vehicles.filter((item) => !stkMeta(item).className).length;
    const progress = total > 0 ? Math.round((okCount / total) * 100) : 0;
    return `
      <div class="uapp-next-hero-row">
        <section class="uapp-next-hero">
          <div>
            <p class="uapp-next-kicker">Přehled garáže</p>
            <h1>Dobrý den, ${esc(fullName())} 👋</h1>
            <p>${esc(heroSummary(data))}</p>
          </div>
          <div class="uapp-next-hero-media">
            <div class="uapp-next-hero-photo" data-next-photo-wrap="${vehicle ? Number(vehicle.id) : ''}">
              ${vehicle ? `<img id="uappNextHeroPhoto" alt="Hlavní vozidlo ${esc(getVehicleName(vehicle))}" loading="eager">` : '<div class="uapp-next-photo-fallback">Zatím bez vozidla</div>'}
            </div>
          </div>
        </section>
        <aside class="uapp-next-status">
          <h2>Celkový stav</h2>
          <div class="uapp-next-ring" style="--progress:${progress}%">${esc(String(progress))}%</div>
          <div class="uapp-next-status-list">
            <div><span>Vozidla</span><strong>${esc(String(total))}</strong></div>
            <div><span>STK v pořádku</span><strong>${esc(String(okCount))}</strong></div>
            <div><span>Aktivní připomínky</span><strong>${esc(String(Number(data.summary?.active_reminders || 0)))}</strong></div>
          </div>
        </aside>
      </div>
    `;
  }

  function quickCards(data) {
    const first = data.vehicles[0] || null;
    const firstMeta = first ? stkMeta(first) : null;
    const docsCount = Number(data.summary?.documents_total || data.summary?.documents_count || 0);
    const activeReminders = Number(data.summary?.active_reminders || data.reminders.filter((r) => !r?.is_completed).length || 0);
    const serviceRecords = data.recordEntries.reduce((sum, entry) => sum + entry.records.length, 0);
    const cards = [
      ['STK / SME', firstMeta ? firstMeta.label : 'Bez vozidla', '□', '#f97316', 'reminders'],
      ['Pojištění', 'Termíny a připomínky', '✓', '#16a34a', 'reminders'],
      ['Servis', serviceRecords ? `${serviceRecords} záznamů` : 'Přidat servisní záznam', '⌁', '#0b4bf2', first ? `addRecord:${first.id}` : 'vehicles'],
      ['Dokumenty', docsCount ? `${docsCount} položek` : 'Otevřít dokumenty', '▣', '#7c3aed', 'documents'],
    ];
    return `<div class="uapp-next-quick-grid">${cards.map(([title, text, icon, color, action]) => `
      <button type="button" class="uapp-next-card" style="--accent:${color}" data-uapp-action="${esc(action)}">
        <span aria-hidden="true">${esc(icon)}</span>
        <strong>${esc(title)}</strong>
        <small>${esc(text)}${activeReminders && title === 'STK / SME' ? ` · ${activeReminders} úkolů` : ''}</small>
      </button>
    `).join('')}</div>`;
  }

  function renderVehicleCard(vehicle) {
    const id = Number(vehicle.id);
    const meta = stkMeta(vehicle);
    const km = vehicle.current_mileage_km != null && vehicle.current_mileage_km !== ''
      ? `${Number(vehicle.current_mileage_km).toLocaleString('cs-CZ')} km`
      : '—';
    return `
      <article class="uapp-next-vehicle-card" data-uapp-vehicle-card data-search-text="${esc([getVehicleName(vehicle), vehicle.plate, vehicle.vin, vehicle.brand, vehicle.model].filter(Boolean).join(' ').toLowerCase())}" data-vehicle-id="${id}">
        <div class="uapp-next-photo" data-next-photo-wrap="${id}">
          <img id="uappNextVehiclePhoto-${id}" alt="Fotka vozidla ${esc(getVehicleName(vehicle))}" loading="lazy">
          <div class="uapp-next-photo-fallback">Bez fotky</div>
        </div>
        <div class="uapp-next-vehicle-title">
          <div>
            <h3>${esc(getVehicleName(vehicle))}</h3>
            <p>${esc(getVehicleSubtitle(vehicle))}</p>
          </div>
          <span class="uapp-next-pill ${esc(meta.className)}">${esc(meta.label)}</span>
        </div>
        <div class="uapp-next-vehicle-meta">
          <span>SPZ<strong>${esc(vehicle.plate || 'Nezadáno')}</strong></span>
          <span>STK<strong>${esc(meta.hint)}</strong></span>
          <span>VIN<strong>${esc(vehicle.vin || 'Nezadáno')}</strong></span>
          <span>Nájezd<strong>${esc(km)}</strong></span>
        </div>
        <div class="uapp-next-vehicle-actions">
          <button type="button" data-uapp-action="detail:${id}">Detail</button>
          <button type="button" data-uapp-action="addRecord:${id}">Přidat záznam</button>
          <button type="button" data-uapp-action="documentsVehicle:${id}">Dokumenty</button>
          <button type="button" data-uapp-action="shareVehicle:${id}">Sdílet</button>
        </div>
      </article>
    `;
  }

  function renderVehicles(data) {
    const vehicles = data.vehicles.slice(0, 3);
    const cards = vehicles.length
      ? vehicles.map(renderVehicleCard).join('')
      : '<div class="uapp-next-empty">Zatím nemáte žádné vozidlo. Přidejte první vozidlo a přehled se naplní reálnými daty.</div>';
    return `
      <section class="uapp-next-stack">
        <div class="uapp-next-section-head">
          <div><h2>Moje vozidla</h2><p>Reálná vozidla z vaší digitální garáže.</p></div>
          <button type="button" class="uapp-next-btn" data-uapp-action="vehicles">Zobrazit všechna</button>
        </div>
        <div class="uapp-next-vehicles-grid">
          ${cards}
          <button type="button" class="uapp-next-add-card" data-uapp-action="addVehicle">
            <span class="uapp-next-add-plus">+</span>
            <strong>Přidat další vozidlo</strong>
            <span>VIN, SPZ, fotka a technické údaje.</span>
          </button>
        </div>
      </section>
    `;
  }

  function reminderRows(data) {
    const rows = data.reminders
      .filter((item) => !item?.is_completed)
      .slice(0, 4)
      .map((item) => {
        const title = item.text || item.title || item.type || 'Připomínka';
        const vehicle = item.vehicle_name || item.vehicle_plate || '';
        const due = item.due_date || item.notify_at || item.created_at;
        return listRow('□', title, `${vehicle ? `${vehicle} · ` : ''}${formatDate(due)}`, '#f97316');
      });
    return rows.length ? rows.join('') : '<div class="uapp-next-empty">Bez blížících se termínů.</div>';
  }

  function activityRows(data) {
    const recent = Array.isArray(data.summary?.recent_activity) ? data.summary.recent_activity : [];
    const fromSummary = recent.slice(0, 4).map((item) => {
      const title = item.description || item.title || item.vehicle_name || 'Aktivita';
      const detail = [item.vehicle_name, formatDate(item.performed_at || item.created_at)].filter(Boolean).join(' · ');
      return listRow('◷', title, detail, '#0b4bf2');
    });
    if (fromSummary.length) return fromSummary.join('');
    const fromRecords = [];
    data.recordEntries.forEach(({ vehicle, records }) => {
      records.slice(0, 2).forEach((record) => {
        fromRecords.push({
          title: record.description || 'Servisní záznam',
          detail: `${getVehicleName(vehicle)} · ${formatDate(record.performed_at || record.created_at)}`,
        });
      });
    });
    return fromRecords.slice(0, 4).map((item) => listRow('◷', item.title, item.detail, '#0b4bf2')).join('')
      || '<div class="uapp-next-empty">Zatím bez poslední aktivity.</div>';
  }

  function serviceRows(data) {
    const grants = data.accessGrants.slice(0, 3).map((grant) => {
      const title = grant.service_name || grant.service_email || 'Servisní přístup';
      const detail = [grant.vehicle_name || grant.vehicle_plate, grant.status || 'stav přístupu'].filter(Boolean).join(' · ');
      return listRow('◇', title, detail, '#16a34a');
    });
    if (grants.length) return grants.join('');
    const services = data.services.slice(0, 3).map((service) => {
      const title = service.name || service.email || 'Servis';
      const detail = [service.city, service.email].filter(Boolean).join(' · ') || 'Uložený kontakt';
      return listRow('◇', title, detail, '#16a34a');
    });
    return services.join('') || '<div class="uapp-next-empty">Zatím nejsou aktivní sdílené přístupy ani servisní kontakty.</div>';
  }

  function listRow(icon, title, detail, color) {
    return `
      <div class="uapp-next-list-row">
        <span class="uapp-next-list-icon" style="--accent:${esc(color)}" aria-hidden="true">${esc(icon)}</span>
        <div><strong>${esc(title)}</strong><span>${esc(detail || '')}</span></div>
      </div>
    `;
  }

  function renderSide(data) {
    return `
      <aside class="uapp-next-side">
        <section class="uapp-next-side-card"><h3>Blížící se termíny</h3><div class="uapp-next-list">${reminderRows(data)}</div></section>
        <section class="uapp-next-side-card"><h3>Poslední aktivita</h3><div class="uapp-next-list">${activityRows(data)}</div></section>
        <section class="uapp-next-side-card"><h3>Servisy a přístupy</h3><div class="uapp-next-list">${serviceRows(data)}</div></section>
      </aside>
    `;
  }

  function renderShell(data) {
    detachedPanels();
    setActiveClass(true);
    const homeTab = document.getElementById('homeTab');
    if (!homeTab) return;
    homeTab.innerHTML = `
      <div class="uapp-next-shell" data-testid="user-app-next-dashboard">
        ${renderSidebar()}
        <main class="uapp-next-main">
          <div class="uapp-next-canvas">
            ${renderTopbar()}
            <div class="uapp-next-content-grid">
              <div class="uapp-next-stack">
                ${renderHero(data)}
                ${quickCards(data)}
                ${renderVehicles(data)}
              </div>
              ${renderSide(data)}
            </div>
          </div>
        </main>
      </div>
    `;
    bindSearch();
    hydrateImages(data);
  }

  async function hydrateImageForVehicle(vehicle, img, scope) {
    if (!vehicle || !img) return;
    const wrap = img.closest('[data-next-photo-wrap]');
    const fallback = wrap?.querySelector('.uapp-next-photo-fallback');
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

  function bindSearch() {
    const input = document.getElementById('uappNextSearch');
    if (!input) return;
    input.addEventListener('input', () => {
      const q = input.value.trim().toLowerCase();
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

  function openVehicleSection(vehicleId, section) {
    const id = Number(vehicleId);
    if (!Number.isFinite(id) || id <= 0) return;
    if (!hasFn('showVehicleDetail')) {
      console.warn('[USER_APP_NEXT] BLOCKER: showVehicleDetail handler missing');
      return;
    }
    Promise.resolve(window.showVehicleDetail(id)).then(() => {
      window.setTimeout(() => {
        if (hasFn('openVehicleDetailFloatingSection')) {
          window.openVehicleDetailFloatingSection(section, id);
        }
      }, 220);
    });
  }

  function runAction(action, event) {
    const [name, rawId] = String(action || '').split(':');
    const id = Number(rawId || 0);
    if (name === 'home' && hasFn('switchTab')) return window.switchTab('home');
    if (name === 'vehicles' && hasFn('switchTab')) return window.switchTab('vehicles');
    if (name === 'reminders' && hasFn('switchTab')) return window.switchTab('reminders');
    if (name === 'documents' && hasFn('switchTab')) return window.switchTab('documents');
    if (name === 'servicesDirectory' && hasFn('switchTab')) return window.switchTab('servicesDirectory');
    if (name === 'account' && hasFn('switchTab')) return window.switchTab('account');
    if (name === 'invoices' && hasFn('switchTab')) return window.switchTab('documents');
    if (name === 'serviceHistory' && hasFn('switchTab')) return window.switchTab('vehicles');
    if (name === 'help') {
      if (hasFn('openHowToHubModal')) return window.openHowToHubModal();
      if (hasFn('switchTab')) return window.switchTab('support');
    }
    if (name === 'collapse') return document.body.classList.toggle('user-app-next-sidebar-collapsed');
    if (name === 'addVehicle') {
      if (hasFn('openAddVehicleModal')) return window.openAddVehicleModal();
      return clickOriginal('#btnOpenAddVehicleModal');
    }
    if (name === 'notifications') {
      if (clickOriginal('#desktopNotificationsButton') || clickOriginal('#mobileNotificationsButton')) return;
      if (hasFn('toggleAppNotificationsPanel')) return window.toggleAppNotificationsPanel(event || window.event);
    }
    if (name === 'profile') {
      if (clickOriginal('#desktopProfileButton') || clickOriginal('#mobileProfileButton')) return;
      if (hasFn('toggleMobileProfileMenu')) return window.toggleMobileProfileMenu();
    }
    if (name === 'detail' && id && hasFn('showVehicleDetail')) return window.showVehicleDetail(id);
    if (name === 'addRecord' && id && hasFn('openAddServiceRecordModal')) return window.openAddServiceRecordModal(id);
    if (name === 'documentsVehicle' && id) return openVehicleSection(id, 'documents');
    if (name === 'shareVehicle' && id) return openVehicleSection(id, 'access');
    console.warn('[USER_APP_NEXT] BLOCKER: handler not found for action', action);
  }

  async function render() {
    if (!shouldActivate()) {
      setActiveClass(false);
      return;
    }
    const token = ++STATE.renderToken;
    detachedPanels();
    setActiveClass(true);
    const homeTab = document.getElementById('homeTab');
    if (homeTab && !homeTab.querySelector('[data-testid="user-app-next-dashboard"]')) {
      homeTab.innerHTML = '<div class="uapp-next-loading">Načítám přehled...</div>';
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

    const originalSwitchTab = window.switchTab;
    if (typeof originalSwitchTab === 'function') {
      window.switchTab = function () {
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

    document.addEventListener('click', (event) => {
      const trigger = event.target && event.target.closest && event.target.closest('[data-uapp-action]');
      if (!trigger) return;
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
