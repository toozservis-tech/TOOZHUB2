(function () {
    'use strict';

    const RESTYLE_BRANCH = 'feature/user-dashboard-restyle-from-prod-20260517';
    const RESTYLE_SEARCH_STATE = {
        vehicleQuery: '',
        vehicleFilter: 'all',
        vehicleSort: 'name',
        vehicleView: 'grid',
    };
    const SIDEBAR_COMPACT_KEY = 'userDashboardRestyleCompactSectionsV2';

    function isRestyleEnabled() {
        try {
            return String(window.location.hostname || '').includes('staging.');
        } catch (error) {
            return false;
        }
    }

    if (!isRestyleEnabled()) {
        return;
    }

    function icon(name) {
        const icons = {
            home: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M3 10.5 12 3l9 7.5"></path><path d="M5 9.5V21h14V9.5"></path><path d="M9 21v-7h6v7"></path></svg>',
            car: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="m4 13 2-5h12l2 5"></path><path d="M5 13h14v6H5z"></path><circle cx="8" cy="17" r="1.5"></circle><circle cx="16" cy="17" r="1.5"></circle></svg>',
            wrench: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M14.7 6.3a5 5 0 0 0-6.4 6.4L3 18l3 3 5.3-5.3a5 5 0 0 0 6.4-6.4l-3.2 3.2-3-3z"></path></svg>',
            bell: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M18 16v-5a6 6 0 1 0-12 0v5l-2 2h16z"></path><path d="M10 21h4"></path></svg>',
            folder: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M3 6h7l2 2h9v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path></svg>',
            building: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M4 21V8l8-5 8 5v13"></path><path d="M9 21v-6h6v6"></path><path d="M8 10h.01M12 10h.01M16 10h.01"></path></svg>',
            file: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M6 3h9l3 3v15H6z"></path><path d="M15 3v4h4"></path><path d="M9 12h6M9 16h6"></path></svg>',
            settings: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.8 1.8 0 0 0 .36 2l.04.04-2 3.46-.06-.02a1.8 1.8 0 0 0-2.1.55l-.02.03h-4l-.02-.03a1.8 1.8 0 0 0-2.1-.55l-.06.02-2-3.46.04-.04a1.8 1.8 0 0 0 .36-2 1.8 1.8 0 0 0-1.7-1.1H6v-4h.14a1.8 1.8 0 0 0 1.7-1.1 1.8 1.8 0 0 0-.36-2l-.04-.04 2-3.46.06.02a1.8 1.8 0 0 0 2.1-.55l.02-.03h4l.02.03a1.8 1.8 0 0 0 2.1.55l.06-.02 2 3.46-.04.04a1.8 1.8 0 0 0-.36 2 1.8 1.8 0 0 0 1.7 1.1H21v4h-.14a1.8 1.8 0 0 0-1.46 1.1z"></path></svg>',
            help: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><circle cx="12" cy="12" r="9"></circle><path d="M9.8 9.4a2.4 2.4 0 1 1 3.6 2.1c-.9.5-1.4 1.1-1.4 2.2"></path><path d="M12 17h.01"></path></svg>',
            collapse: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="m15 18-6-6 6-6"></path><path d="M20 4v16"></path></svg>',
            search: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><circle cx="11" cy="11" r="7"></circle><path d="m20 20-3.4-3.4"></path></svg>',
            plus: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M12 5v14M5 12h14"></path></svg>',
            check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="m5 13 4 4L19 7"></path></svg>',
            calendar: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><rect x="4" y="5" width="16" height="15" rx="2"></rect><path d="M8 3v4M16 3v4M4 10h16"></path></svg>',
            shield: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M12 3 20 6v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"></path><path d="m8.5 12 2.3 2.3 4.7-5"></path></svg>',
            arrow: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="m9 18 6-6-6-6"></path></svg>',
            grid: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><rect x="4" y="4" width="6" height="6"></rect><rect x="14" y="4" width="6" height="6"></rect><rect x="4" y="14" width="6" height="6"></rect><rect x="14" y="14" width="6" height="6"></rect></svg>',
            list: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M8 6h13M8 12h13M8 18h13"></path><path d="M3 6h.01M3 12h.01M3 18h.01"></path></svg>',
            share: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><circle cx="18" cy="5" r="3"></circle><circle cx="6" cy="12" r="3"></circle><circle cx="18" cy="19" r="3"></circle><path d="m8.6 10.6 6.8-4.2M8.6 13.4l6.8 4.2"></path></svg>',
        };
        return icons[name] || icons.car;
    }

    function escape(value) {
        if (typeof window.escapeHtml === 'function') {
            return window.escapeHtml(String(value ?? ''));
        }
        return String(value ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function formatDate(value) {
        if (!value) return '—';
        if (typeof window.formatDateCZ === 'function') {
            return window.formatDateCZ(value);
        }
        const d = value instanceof Date ? value : new Date(value);
        return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleDateString('cs-CZ');
    }

    function formatKm(value) {
        const n = Number(value);
        return Number.isFinite(n) && n > 0 ? `${Math.round(n).toLocaleString('cs-CZ')} km` : '—';
    }

    function getVehicleName(vehicle) {
        return String(vehicle?.nickname || [vehicle?.brand, vehicle?.model].filter(Boolean).join(' ') || vehicle?.plate || 'Vozidlo').trim();
    }

    function getVehicleStkDate(vehicle) {
        if (typeof window.getVehicleStkDateValueSimple === 'function') {
            return window.getVehicleStkDateValueSimple(vehicle);
        }
        if (!vehicle?.stk_valid_until) return null;
        const d = new Date(vehicle.stk_valid_until);
        return Number.isNaN(d.getTime()) ? null : d;
    }

    function getVehicleStatus(vehicle) {
        const d = getVehicleStkDate(vehicle);
        const meta = typeof window.getVehicleStkStatusMeta === 'function'
            ? window.getVehicleStkStatusMeta(d)
            : { className: 'stk-unknown', label: d ? 'STK evidována' : 'Bez STK', daysRemaining: null };
        const key = String(meta.className || 'stk-unknown');
        if (key === 'stk-expired') return { key: 'danger', className: 'is-danger', label: 'Vyžaduje pozornost', meta };
        if (key === 'stk-soon') return { key: 'warning', className: 'is-warning', label: 'Vyžaduje pozornost', meta };
        if (key === 'stk-ok') return { key: 'ok', className: '', label: 'V pořádku', meta };
        return { key: 'unknown', className: 'is-warning', label: 'Doplnit údaje', meta };
    }

    function getVinShort(vehicle) {
        const vin = String(vehicle?.vin || '').trim();
        if (!vin) return 'VIN neuvedeno';
        if (vin.length <= 12) return vin;
        return `${vin.slice(0, 8)}…${vin.slice(-4)}`;
    }

    function getServiceText(record) {
        const forbidden = /dekódováno z|mdcr|local_vin|pneumatiky|emisní norma|euro|technická data vozidla/i;
        const raw = String(record?.description || record?.summary || record?.note || '').trim();
        if (!raw || forbidden.test(raw)) return '';
        return raw.length > 74 ? `${raw.slice(0, 74)}…` : raw;
    }

    function isServiceAccount() {
        if (typeof window.isServiceWorkspaceRole === 'function' && window.isServiceWorkspaceRole()) return true;
        const role = String(window.currentUser?.role || window.currentUser?.account_type || '').toLowerCase();
        return role.includes('service');
    }

    function disableRestyleChromeForService() {
        const chrome = document.getElementById('userRestyleChrome');
        if (chrome) chrome.remove();
        const style = document.getElementById('userRestyleRuntimeLayout');
        if (style) style.remove();
        document.body.classList.remove('user-dashboard-restyle', 'user-dashboard-restyle-compact');
    }

    function injectRuntimeLayoutStyles() {
        if (document.getElementById('userRestyleRuntimeLayout')) return;
        const style = document.createElement('style');
        style.id = 'userRestyleRuntimeLayout';
        style.textContent = `
body.user-dashboard-restyle.route-app-view #dashboard.dashboard {
    margin: 0 0 0 var(--ud-sidebar-w) !important;
    width: calc(100vw - var(--ud-sidebar-w)) !important;
    max-width: none !important;
    min-width: 0 !important;
    padding: calc(var(--ud-topbar-h) + 18px) 28px 36px !important;
    box-sizing: border-box !important;
    overflow-x: hidden !important;
}
body.user-dashboard-restyle.route-app-view .user-restyle-topbar {
    left: var(--ud-sidebar-w) !important;
    width: calc(100vw - var(--ud-sidebar-w)) !important;
    box-sizing: border-box !important;
}
body.user-dashboard-restyle.route-app-view .user-restyle-sidebar {
    width: var(--ud-sidebar-w) !important;
    box-sizing: border-box !important;
}
@media (max-width: 820px) {
    body.user-dashboard-restyle.route-app-view #dashboard.dashboard {
        margin-left: 0 !important;
        width: 100vw !important;
        padding: calc(var(--ud-topbar-h) + 14px) 14px 88px !important;
    }
    body.user-dashboard-restyle.route-app-view .user-restyle-topbar {
        left: 0 !important;
        width: 100vw !important;
    }
}
        `;
        document.head.appendChild(style);
    }

    function injectChrome() {
        if (isServiceAccount()) {
            disableRestyleChromeForService();
            return;
        }
        document.body.classList.add('user-dashboard-restyle');
        injectRuntimeLayoutStyles();
        const appShell = document.getElementById('app-shell');
        if (!appShell || document.getElementById('userRestyleChrome')) return;
        const chrome = document.createElement('div');
        chrome.id = 'userRestyleChrome';
        chrome.className = 'user-restyle-chrome';
        chrome.innerHTML = `
            <aside class="user-restyle-sidebar" aria-label="Hlavní menu Správa vozidel">
                <div class="user-restyle-brand">
                    <span class="user-restyle-brand-mark" aria-hidden="true"><svg viewBox="0 0 44 52" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 2 40 10v15c0 12-8 20-18 25C12 45 4 37 4 25V10z"></path><path d="M13 27h18v7H13z"></path><path d="m15 27 2.2-6h9.6L29 27"></path><circle cx="17" cy="34" r="1.5"></circle><circle cx="27" cy="34" r="1.5"></circle></svg></span>
                    <span>Správa<br>vozidel</span>
                </div>
                <nav class="user-restyle-nav">
                    ${[
                        ['home', 'Přehled', 'home', 'home'],
                        ['vehicles', 'Moje vozidla', 'car', 'vehicles'],
                        ['serviceHistory', 'Servisní historie', 'wrench', 'serviceHistory'],
                        ['reminders', 'Připomínky', 'bell', 'reminders'],
                        ['documents', 'Dokumenty', 'folder', 'documents'],
                        ['servicesDirectory', 'Servisy', 'building', 'servicesDirectory'],
                        ['invoices', 'Faktury', 'file', 'documents'],
                        ['account', 'Nastavení', 'settings', 'account'],
                    ].map(([key, label, glyph, target]) => `
                        <button type="button" class="user-restyle-nav-btn" data-restyle-nav="${key}" data-restyle-target="${target}" onclick="switchTab('${target}')">
                            ${icon(glyph)}<span>${escape(label)}</span>${key === 'reminders' ? '<span class="user-restyle-nav-badge" id="userRestyleReminderBadge" data-count="0">0</span>' : '<span></span>'}
                        </button>
                    `).join('')}
                </nav>
                <div class="user-restyle-sidebar-foot">
                    <span>Potřebujete pomoc?</span>
                    <button type="button" class="user-restyle-help-btn" onclick="switchTab('support')" title="Nápověda">${icon('help')}<span>Nápověda</span></button>
                    <button type="button" class="user-restyle-collapse-btn" onclick="window.toggleUserRestyleSidebar()" title="Sbalit menu">${icon('collapse')}<span>Sbalit menu</span></button>
                </div>
            </aside>
            <header class="user-restyle-topbar" aria-label="Horní lišta">
                <label class="user-restyle-search">
                    ${icon('search')}
                    <input id="userRestyleSearchInput" type="search" placeholder="Hledejte podle SPZ, VIN, názvu vozidla..." oninput="window.setUserRestyleVehicleSearch(this.value)" onkeydown="if(event.key === 'Enter') switchTab('vehicles')">
                    <span class="user-restyle-kbd">⌘ K</span>
                </label>
                <button type="button" class="user-restyle-add-btn" onclick="openAddVehicleModal()">${icon('plus')}<span>Přidat vozidlo</span></button>
                <button type="button" class="user-restyle-icon-btn app-notifications-button" onclick="toggleAppNotificationsPanel(event)" aria-label="Oznámení" aria-expanded="false" aria-controls="appNotificationsPanel">
                    ${icon('bell')}<span class="app-notifications-badge" id="userRestyleNotificationsBadge" data-count="0" aria-hidden="true"></span>
                </button>
                <button type="button" class="user-restyle-profile" onclick="switchTab('account')" aria-label="Profil">
                    <span class="user-restyle-avatar" id="userRestyleAvatar">U</span>
                    <span id="userRestyleProfileName">Uživatel</span>
                    <span>⌄</span>
                </button>
            </header>
        `;
        appShell.prepend(chrome);
        updateChromeIdentity();
        updateActiveChromeNav('home');
    }

    window.toggleUserRestyleSidebar = function () {
        const compact = !document.body.classList.contains('user-dashboard-restyle-compact');
        document.body.classList.toggle('user-dashboard-restyle-compact', compact);
        try {
            window.localStorage?.setItem(SIDEBAR_COMPACT_KEY, compact ? '1' : '0');
        } catch (error) {}
    };

    function restoreSidebarState() {
        try {
            document.body.classList.toggle(
                'user-dashboard-restyle-compact',
                window.localStorage?.getItem(SIDEBAR_COMPACT_KEY) === '1'
            );
        } catch (error) {}
    }

    function updateChromeIdentity() {
        const name = String(window.currentUser?.name || window.currentUser?.email || '').trim();
        const shown = name ? name.split('@')[0] : 'Uživatel';
        const profile = document.getElementById('userRestyleProfileName');
        const avatar = document.getElementById('userRestyleAvatar');
        if (profile) profile.textContent = shown;
        if (avatar) avatar.textContent = shown.trim().slice(0, 1).toUpperCase() || 'U';
    }

    function updateActiveChromeNav(tab) {
        const normalized = String(tab || 'home');
        document.querySelectorAll('[data-restyle-nav]').forEach((button) => {
            const target = button.getAttribute('data-restyle-target');
            const key = button.getAttribute('data-restyle-nav');
            const active = target === normalized || key === normalized;
            button.classList.toggle('is-active', active);
        });
    }

    function renderHeroVehicleMedia(vehicle) {
        if (vehicle && typeof window.vehiclePrimaryPhotoAvailable === 'function' && window.vehiclePrimaryPhotoAvailable(vehicle)) {
            return `<div class="user-restyle-hero-media"><img id="userRestyleHeroVehiclePhoto" alt="Fotka vozidla ${escape(getVehicleName(vehicle))}"></div>`;
        }
        return `
            <div class="user-restyle-hero-media" aria-hidden="true">
                <svg class="user-restyle-car-fallback" viewBox="0 0 520 220" fill="none">
                    <path d="M78 144h352l-26-54c-10-20-27-31-49-31H183c-23 0-41 11-52 31l-53 54Z" fill="#dfe9f7"/>
                    <path d="M114 148h306c21 0 38 17 38 38v4H76v-4c0-21 17-38 38-38Z" fill="#16468f"/>
                    <path d="M182 77h169c17 0 31 10 38 25l12 27H135l18-34c6-12 17-18 29-18Z" fill="#2e6db8"/>
                    <path d="M202 88h66v38h-93l15-29c3-6 7-9 12-9Zm81 0h62c9 0 17 5 21 13l11 25h-94V88Z" fill="#ecf5ff"/>
                    <circle cx="155" cy="188" r="34" fill="#0f172a"/><circle cx="155" cy="188" r="16" fill="#dbeafe"/>
                    <circle cx="374" cy="188" r="34" fill="#0f172a"/><circle cx="374" cy="188" r="16" fill="#dbeafe"/>
                    <path d="M88 158h54M396 158h46" stroke="#ff7a1a" stroke-width="8" stroke-linecap="round"/>
                </svg>
            </div>
        `;
    }

    function renderVehicleCard(vehicle, compact = false) {
        const id = Number(vehicle?.id || 0);
        const name = getVehicleName(vehicle);
        const status = getVehicleStatus(vehicle);
        const stk = getVehicleStkDate(vehicle);
        const hasPhoto = typeof window.vehiclePrimaryPhotoAvailable === 'function' && window.vehiclePrimaryPhotoAvailable(vehicle);
        const serviceText = String(vehicle.__restyleLatestServiceText || '').trim() || 'Bez servisního záznamu';
        return `
            <article class="user-restyle-vehicle-card" data-vehicle-id="${id}">
                <div class="user-restyle-vehicle-media ${hasPhoto ? 'is-loading' : 'is-empty'}" id="vehicle-card-media-${id}">
                    ${hasPhoto ? `<img id="vehicle-photo-preview-card-${id}" alt="Hlavní fotka vozidla ${escape(name)}" loading="lazy">` : ''}
                    <div class="user-restyle-vehicle-fallback">${icon('car')}<span>Bez fotky</span></div>
                    <span class="user-restyle-status-badge ${status.className}">${escape(status.label)}</span>
                </div>
                <div class="user-restyle-vehicle-body">
                    <div class="user-restyle-vehicle-title-row">
                        <h3>${escape(name)}</h3>
                        <span class="user-restyle-plate-pill">${escape(vehicle?.plate || 'SPZ —')}</span>
                    </div>
                    <p class="user-restyle-vehicle-sub">VIN: ${escape(getVinShort(vehicle))}</p>
                    <p class="user-restyle-vehicle-sub">${escape([vehicle?.brand, vehicle?.model].filter(Boolean).join(' ') || 'Model není doplněn')}</p>
                    <div class="user-restyle-vehicle-facts">
                        <div class="user-restyle-vehicle-fact"><span>Nájezd</span><strong>${escape(formatKm(vehicle?.current_mileage_km))}</strong></div>
                        <div class="user-restyle-vehicle-fact"><span>STK</span><strong>${escape(stk ? formatDate(stk) : '—')}</strong></div>
                        <div class="user-restyle-vehicle-fact"><span>Servis</span><strong>${escape(serviceText)}</strong></div>
                    </div>
                </div>
                <div class="user-restyle-vehicle-actions">
                    <button type="button" onclick="event.stopPropagation(); showVehicleDetail(${id})">${icon('search')}<span>Detail</span></button>
                    <button type="button" onclick="event.stopPropagation(); openAddServiceRecordModal(${id})">${icon('plus')}<span>Přidat záznam</span></button>
                    <button type="button" onclick="event.stopPropagation(); window.openUserRestyleVehicleSection(${id}, 'documents')">${icon('file')}<span>Dokumenty</span></button>
                    <button type="button" onclick="event.stopPropagation(); window.openUserRestyleVehicleSection(${id}, 'access')">${icon('share')}<span>Sdílet</span></button>
                </div>
            </article>
        `;
    }

    async function loadVehicleRecordsForPreview(vehicles) {
        const list = Array.isArray(vehicles) ? vehicles.slice(0, 8) : [];
        const batches = await Promise.allSettled(list.map(async (vehicle) => {
            const id = Number(vehicle?.id || 0);
            if (!id || typeof window.apiCall !== 'function') return { vehicle, records: [] };
            const records = await window.apiCall(`/api/v1/vehicles/${id}/records`, 'GET');
            return { vehicle, records: Array.isArray(records) ? records : [] };
        }));
        const flat = [];
        batches.forEach((result) => {
            if (result.status !== 'fulfilled') return;
            const { vehicle, records } = result.value;
            const latest = records
                .slice()
                .sort((a, b) => (Date.parse(b?.performed_at) || 0) - (Date.parse(a?.performed_at) || 0))[0] || null;
            if (latest) {
                vehicle.__restyleLatestServiceText = getServiceText(latest);
            }
            records.forEach((record) => {
                const text = getServiceText(record);
                if (!text) return;
                flat.push({ vehicle, record, text, ts: Date.parse(record?.performed_at) || 0 });
            });
        });
        flat.sort((a, b) => b.ts - a.ts);
        return flat;
    }

    function renderQuickCards({ vehicles, reminders, latestService }) {
        const total = vehicles.length;
        const stkSoon = vehicles.filter((vehicle) => {
            const status = getVehicleStatus(vehicle);
            return status.key === 'warning' || status.key === 'danger';
        }).length;
        const serviceTitle = latestService?.text || 'Bez servisního záznamu';
        const serviceHint = latestService?.record?.performed_at ? formatDate(latestService.record.performed_at) : 'Doplňte servisní historii';
        return `
            <div class="user-restyle-quick-grid">
                <button type="button" class="user-restyle-card user-restyle-quick-card" style="--tone: var(--ud-orange)" onclick="switchTab('vehicles')">
                    <span class="user-restyle-quick-icon">${icon('calendar')}</span><span><h3>STK / SME</h3><strong>${stkSoon ? `${stkSoon} vozidlo vyžaduje kontrolu` : 'Vše pod kontrolou'}</strong><p>Zkontrolujte včas</p></span>${icon('arrow')}
                </button>
                <button type="button" class="user-restyle-card user-restyle-quick-card" style="--tone: var(--ud-green)" onclick="switchTab('vehicles')">
                    <span class="user-restyle-quick-icon">${icon('shield')}</span><span><h3>Pojištění</h3><strong>${total ? 'Evidence u vozidel' : 'Bez vozidel'}</strong><p>Platné smlouvy</p></span>${icon('arrow')}
                </button>
                <button type="button" class="user-restyle-card user-restyle-quick-card" style="--tone: var(--ud-blue)" onclick="switchTab('vehicles')">
                    <span class="user-restyle-quick-icon">${icon('wrench')}</span><span><h3>Servis</h3><strong>${escape(serviceTitle)}</strong><p>${escape(serviceHint)}</p></span>${icon('arrow')}
                </button>
                <button type="button" class="user-restyle-card user-restyle-quick-card" style="--tone: var(--ud-orange)" onclick="switchTab('documents')">
                    <span class="user-restyle-quick-icon">${icon('folder')}</span><span><h3>Dokumenty</h3><strong>Dokumenty vozidel</strong><p>Výpisy a přílohy</p></span>${icon('arrow')}
                </button>
            </div>
        `;
    }

    function buildDeadlineRows(vehicles, reminders) {
        const rows = [];
        vehicles.forEach((vehicle) => {
            const status = getVehicleStatus(vehicle);
            if (status.key !== 'warning' && status.key !== 'danger') return;
            rows.push({
                icon: 'calendar',
                title: 'STK',
                text: getVehicleName(vehicle),
                pill: status.meta?.daysRemaining != null ? `za ${status.meta.daysRemaining} dní` : status.label,
                onclick: `showVehicleDetail(${Number(vehicle.id)})`,
            });
        });
        reminders.filter((r) => !r?.is_completed).slice(0, 4).forEach((reminder) => {
            rows.push({
                icon: 'bell',
                title: String(reminder?.type || 'Připomínka'),
                text: String(reminder?.vehicle_name || reminder?.vehicle_plate || reminder?.text || 'Připomínka'),
                pill: reminder?.due_date || reminder?.notify_at ? formatDate(reminder.due_date || reminder.notify_at) : 'aktivní',
                onclick: "switchTab('reminders')",
            });
        });
        return rows.slice(0, 5);
    }

    function renderRows(rows, emptyText) {
        if (!rows.length) {
            return `<div class="user-restyle-empty">${escape(emptyText)}</div>`;
        }
        return `<div class="user-restyle-list">${rows.map((row) => `
            <button type="button" class="user-restyle-list-row" onclick="${row.onclick || "switchTab('vehicles')"}">
                <span class="user-restyle-list-icon">${icon(row.icon || 'car')}</span>
                <span><strong>${escape(row.title)}</strong><p>${escape(row.text)}</p></span>
                <span class="user-restyle-due-pill">${escape(row.pill || '')}</span>
                ${icon('arrow')}
            </button>
        `).join('')}</div>`;
    }

    async function hydrateOverview() {
        if (typeof window.apiCall !== 'function' || !document.getElementById('userRestyleOverviewRoot')) return;
        let vehicles = [];
        let reminders = [];
        let docs = null;
        let services = null;
        try {
            const [vehicleResult, reminderResult, docsResult, servicesResult] = await Promise.allSettled([
                window.apiCall('/api/v1/vehicles', 'GET'),
                window.apiCall('/api/v1/reminders', 'GET'),
                window.apiCall('/api/v1/vehicles/documents/hub', 'GET'),
                window.apiCall('/api/v1/services/discovery', 'GET'),
            ]);
            vehicles = vehicleResult.status === 'fulfilled' && Array.isArray(vehicleResult.value) ? vehicleResult.value : [];
            reminders = reminderResult.status === 'fulfilled' && Array.isArray(reminderResult.value) ? reminderResult.value : [];
            docs = docsResult.status === 'fulfilled' ? docsResult.value : null;
            services = servicesResult.status === 'fulfilled' ? servicesResult.value : null;
        } catch (error) {
            return;
        }
        const records = await loadVehicleRecordsForPreview(vehicles);
        window.__userRestyleAllVehicles = vehicles;
        const byId = {};
        vehicles.forEach((vehicle) => { byId[Number(vehicle.id)] = vehicle; });
        window._lastVehiclesById = byId;

        const firstVehicle = vehicles.find((vehicle) => typeof window.vehiclePrimaryPhotoAvailable === 'function' && window.vehiclePrimaryPhotoAvailable(vehicle)) || vehicles[0] || null;
        const heroMedia = document.getElementById('userRestyleHeroMediaMount');
        if (heroMedia) {
            heroMedia.innerHTML = renderHeroVehicleMedia(firstVehicle);
            if (firstVehicle && document.getElementById('userRestyleHeroVehiclePhoto') && typeof window.hydrateVehiclePhotoPreview === 'function') {
                window.hydrateVehiclePhotoPreview(Number(firstVehicle.id), document.getElementById('userRestyleHeroVehiclePhoto'), 'restyle-hero').catch(() => {});
            }
        }

        const preview = document.getElementById('userRestyleVehiclePreview');
        if (preview) {
            preview.innerHTML = vehicles.slice(0, 3).map((vehicle) => renderVehicleCard(vehicle, true)).join('')
                || '<div class="user-restyle-empty">Zatím nemáte žádná vozidla.</div>';
            if (typeof window.hydrateVehicleCardPhotos === 'function') {
                window.hydrateVehicleCardPhotos(vehicles.slice(0, 3));
            }
        }

        const quick = document.getElementById('userRestyleQuickCards');
        if (quick) quick.innerHTML = renderQuickCards({ vehicles, reminders, latestService: records[0] || null, docs });

        const deadlineRows = buildDeadlineRows(vehicles, reminders);
        const deadlines = document.getElementById('userRestyleDeadlines');
        if (deadlines) deadlines.innerHTML = renderRows(deadlineRows, 'Žádné blížící se termíny.');

        const activityRows = records.slice(0, 4).map((item) => ({
            icon: 'wrench',
            title: `${formatDate(item.record?.performed_at)} · ${getVehicleName(item.vehicle)}`,
            text: item.text,
            pill: 'servis',
            onclick: `showVehicleDetail(${Number(item.vehicle?.id || 0)})`,
        }));
        const activity = document.getElementById('userRestyleActivity');
        if (activity) activity.innerHTML = renderRows(activityRows, 'Zatím bez čerstvé servisní aktivity.');

        const servicesRows = Array.isArray(services?.services)
            ? services.services.slice(0, 3).map((service) => ({
                icon: 'building',
                title: String(service?.name || service?.email || 'Servis'),
                text: service?.city || service?.email || 'Servisní partner',
                pill: service?.is_linked ? 'Schváleno' : 'Bez přístupu',
                onclick: "switchTab('servicesDirectory')",
            }))
            : [];
        const servicesBox = document.getElementById('userRestyleServices');
        if (servicesBox) servicesBox.innerHTML = renderRows(servicesRows, 'Servisní přístupy otevřete v sekci Servisy.');

        const badge = document.getElementById('userRestyleReminderBadge');
        if (badge) {
            const active = reminders.filter((item) => !item?.is_completed).length;
            badge.dataset.count = String(active);
            badge.textContent = String(active);
        }
    }

    function renderRestyleDashboard(model) {
        injectChrome();
        updateChromeIdentity();
        updateActiveChromeNav('home');
        const homeTab = document.getElementById('homeTab');
        if (!homeTab) return;
        const vehiclesTotal = Number(model?.vehiclesTotal || 0);
        const activeReminders = Number(model?.activeReminders || 0);
        const stkSoon = Number(model?.stkSoon || 0) + Number(model?.stkExpired || 0);
        const name = String(window.currentUser?.name || window.currentUser?.email || '').trim();
        const firstName = name ? name.split(/[ @._-]+/).filter(Boolean)[0] : 'uživateli';
        const health = (stkSoon || activeReminders) ? 'Vozidla vyžadují pozornost' : 'Vozidla pod kontrolou';
        homeTab.innerHTML = `
            <section class="user-restyle-home" id="userRestyleOverviewRoot" data-restyle-branch="${RESTYLE_BRANCH}">
                <div class="user-restyle-hero-row">
                    <article class="user-restyle-card user-restyle-hero">
                        <div class="user-restyle-hero-copy">
                            <h1 id="homeDashboardGreeting">Dobrý den, ${escape(firstName)} 👋</h1>
                            <p class="user-restyle-hero-lead">Máte <strong>${vehiclesTotal}</strong> ${vehiclesTotal === 1 ? 'vozidlo' : 'vozidel'}, <span class="${stkSoon ? 'is-hot' : ''}"><strong>${stkSoon}</strong></span> blížící se STK a <span class="${activeReminders ? 'is-hot' : ''}"><strong>${activeReminders}</strong></span> aktivních připomínek.</p>
                        </div>
                        <div id="userRestyleHeroMediaMount">${renderHeroVehicleMedia(null)}</div>
                    </article>
                    <article class="user-restyle-card user-restyle-health-card" id="homeDashboardLicensePanel">
                        <div>
                            <p class="eyebrow">Celkový stav</p>
                            <div class="user-restyle-health-title">${escape(health)}</div>
                            <p class="user-restyle-health-note">Poslední aktualizace: právě teď</p>
                        </div>
                        <span class="user-restyle-check">${icon('check')}</span>
                    </article>
                </div>
                <div id="homeDashboardStats" hidden></div>
                <div id="userRestyleQuickCards">${renderQuickCards({ vehicles: [], reminders: [], latestService: null })}</div>
                <div class="user-restyle-main-grid">
                    <section class="user-restyle-card user-restyle-panel" id="homeDashboardWorkspace">
                        <header class="user-restyle-panel-head">
                            <h2>Moje vozidla</h2>
                            <button type="button" class="user-restyle-panel-link" onclick="switchTab('vehicles')">Zobrazit všechna vozidla ${icon('arrow')}</button>
                        </header>
                        <div class="user-restyle-vehicle-preview-grid" id="userRestyleVehiclePreview"><div class="user-restyle-empty">Načítám vozidla...</div></div>
                        <button type="button" class="user-restyle-add-vehicle-card" onclick="openAddVehicleModal()">${icon('plus')} Přidat další vozidlo<span>Rychle přidejte nové vozidlo do své správy</span></button>
                    </section>
                    <aside class="user-restyle-side-stack">
                        <section class="user-restyle-card user-restyle-panel" id="homeDashboardAttention">
                            <header class="user-restyle-panel-head"><h3>Blížící se termíny</h3><button type="button" class="user-restyle-panel-link" onclick="switchTab('reminders')">Zobrazit všechny ${icon('arrow')}</button></header>
                            <div id="userRestyleDeadlines"><div class="user-restyle-empty">Načítám termíny...</div></div>
                        </section>
                        <section class="user-restyle-card user-restyle-panel" id="homeDashboardActivityPanel">
                            <header class="user-restyle-panel-head"><h3>Poslední aktivita</h3><button type="button" class="user-restyle-panel-link" onclick="switchTab('vehicles')">Zobrazit vše ${icon('arrow')}</button></header>
                            <div id="homeDashboardRecentFeed"><div id="userRestyleActivity"><div class="user-restyle-empty">Načítám aktivitu...</div></div></div>
                        </section>
                        <section class="user-restyle-card user-restyle-panel">
                            <header class="user-restyle-panel-head"><h3>Servisy a přístupy</h3><button type="button" class="user-restyle-panel-link" onclick="switchTab('servicesDirectory')">Spravovat přístupy ${icon('arrow')}</button></header>
                            <div id="userRestyleServices"><div class="user-restyle-empty">Načítám servisy...</div></div>
                        </section>
                    </aside>
                </div>
                <div id="homeDashboardActivityExtras" hidden></div>
                <div id="homeDashboardMileageHint" hidden></div>
                <div id="homeDashboardPrimaryActions" hidden></div>
                <div id="homeDashboardHeroStatus" hidden></div>
                <div id="homeDashboardHeroInsights" hidden></div>
                <div id="homeDashboardNotifications" hidden></div>
            </section>
        `;
        hydrateOverview();
    }

    function filterVehicles(vehicles) {
        const query = RESTYLE_SEARCH_STATE.vehicleQuery.trim().toLowerCase();
        let list = Array.isArray(vehicles) ? vehicles.slice() : [];
        if (query) {
            list = list.filter((vehicle) => [
                getVehicleName(vehicle),
                vehicle?.plate,
                vehicle?.vin,
                vehicle?.brand,
                vehicle?.model,
            ].some((part) => String(part || '').toLowerCase().includes(query)));
        }
        const filter = RESTYLE_SEARCH_STATE.vehicleFilter;
        if (filter !== 'all') {
            list = list.filter((vehicle) => {
                const status = getVehicleStatus(vehicle);
                if (filter === 'ok') return status.key === 'ok';
                if (filter === 'attention') return status.key === 'warning' || status.key === 'danger' || status.key === 'unknown';
                if (filter === 'service') return String(vehicle?.service_status || vehicle?.status || '').toLowerCase().includes('servis');
                if (filter === 'archive') return Boolean(vehicle?.archived || vehicle?.is_archived);
                return true;
            });
        }
        const sort = RESTYLE_SEARCH_STATE.vehicleSort;
        list.sort((a, b) => {
            if (sort === 'stk') {
                return (getVehicleStkDate(a)?.getTime() || Infinity) - (getVehicleStkDate(b)?.getTime() || Infinity);
            }
            if (sort === 'mileage') {
                return Number(b?.current_mileage_km || 0) - Number(a?.current_mileage_km || 0);
            }
            return getVehicleName(a).localeCompare(getVehicleName(b), 'cs');
        });
        return list;
    }

    function renderRestyleVehicles(container, vehicles) {
        injectChrome();
        updateActiveChromeNav('vehicles');
        const list = Array.isArray(vehicles) ? vehicles : [];
        window.__userRestyleAllVehicles = list;
        const byId = {};
        list.forEach((vehicle) => { byId[Number(vehicle.id)] = vehicle; });
        window._lastVehiclesById = byId;
        const filtered = filterVehicles(list);
        const viewClass = RESTYLE_SEARCH_STATE.vehicleView === 'list' ? 'is-list' : '';
        container.classList.remove('loading');
        container.innerHTML = `
            <section class="user-restyle-garage">
                <header class="user-restyle-garage-head">
                    <div class="user-restyle-garage-titlebar">
                        <div>
                            <h2>Moje vozidla</h2>
                            <p>Máte ${list.length} ${list.length === 1 ? 'vozidlo' : 'vozidel'}</p>
                        </div>
                        <button type="button" class="user-restyle-panel-link" onclick="window.setUserRestyleVehicleFilter('archive')">Zobrazit archivovaná</button>
                    </div>
                    <div class="user-restyle-garage-tools">
                        <div class="user-restyle-filter-pills">
                            ${[
                                ['all', 'Všechna'],
                                ['ok', 'V pořádku'],
                                ['attention', 'Vyžaduje pozornost'],
                                ['service', 'V servisu'],
                                ['archive', 'V archivu'],
                            ].map(([key, label]) => `<button type="button" class="${RESTYLE_SEARCH_STATE.vehicleFilter === key ? 'is-active' : ''}" onclick="window.setUserRestyleVehicleFilter('${key}')">${escape(label)}</button>`).join('')}
                        </div>
                        <div>
                            <select class="user-restyle-sort-select" onchange="window.setUserRestyleVehicleSort(this.value)" aria-label="Řazení vozidel">
                                <option value="name" ${RESTYLE_SEARCH_STATE.vehicleSort === 'name' ? 'selected' : ''}>Název A-Z</option>
                                <option value="stk" ${RESTYLE_SEARCH_STATE.vehicleSort === 'stk' ? 'selected' : ''}>Nejbližší STK</option>
                                <option value="mileage" ${RESTYLE_SEARCH_STATE.vehicleSort === 'mileage' ? 'selected' : ''}>Nejvyšší nájezd</option>
                            </select>
                            <span class="user-restyle-view-toggle">
                                <button type="button" class="${RESTYLE_SEARCH_STATE.vehicleView === 'grid' ? 'is-active' : ''}" onclick="window.setUserRestyleVehicleView('grid')" aria-label="Grid">${icon('grid')}</button>
                                <button type="button" class="${RESTYLE_SEARCH_STATE.vehicleView === 'list' ? 'is-active' : ''}" onclick="window.setUserRestyleVehicleView('list')" aria-label="List">${icon('list')}</button>
                            </span>
                        </div>
                    </div>
                </header>
                <div class="user-restyle-vehicle-grid ${viewClass}">
                    ${filtered.map((vehicle) => renderVehicleCard(vehicle)).join('') || '<div class="user-restyle-empty">Žádná vozidla neodpovídají filtru.</div>'}
                </div>
                <button type="button" class="user-restyle-add-vehicle-card" onclick="openAddVehicleModal()">${icon('plus')} Přidat nové vozidlo<span>Otevře původní produkční formulář přidání vozidla</span></button>
            </section>
        `;
        if (typeof window.hydrateVehicleCardPhotos === 'function') {
            window.hydrateVehicleCardPhotos(filtered);
        }
    }

    window.setUserRestyleVehicleSearch = function (value) {
        RESTYLE_SEARCH_STATE.vehicleQuery = String(value || '');
        const vehiclesTab = document.getElementById('vehiclesTab');
        if (vehiclesTab?.classList.contains('active') && Array.isArray(window.__userRestyleAllVehicles)) {
            const container = document.getElementById('vehiclesContainer');
            if (container) renderRestyleVehicles(container, window.__userRestyleAllVehicles);
        }
    };

    window.setUserRestyleVehicleFilter = function (filter) {
        RESTYLE_SEARCH_STATE.vehicleFilter = String(filter || 'all');
        const container = document.getElementById('vehiclesContainer');
        if (container && Array.isArray(window.__userRestyleAllVehicles)) renderRestyleVehicles(container, window.__userRestyleAllVehicles);
    };

    window.setUserRestyleVehicleSort = function (sort) {
        RESTYLE_SEARCH_STATE.vehicleSort = String(sort || 'name');
        const container = document.getElementById('vehiclesContainer');
        if (container && Array.isArray(window.__userRestyleAllVehicles)) renderRestyleVehicles(container, window.__userRestyleAllVehicles);
    };

    window.setUserRestyleVehicleView = function (view) {
        RESTYLE_SEARCH_STATE.vehicleView = view === 'list' ? 'list' : 'grid';
        const container = document.getElementById('vehiclesContainer');
        if (container && Array.isArray(window.__userRestyleAllVehicles)) renderRestyleVehicles(container, window.__userRestyleAllVehicles);
    };

    window.openUserRestyleVehicleSection = async function (vehicleId, section) {
        const id = Number(vehicleId || 0);
        if (!id) return;
        await window.showVehicleDetail(id);
        window.setTimeout(() => {
            if (typeof window.openVehicleDetailFloatingSection === 'function') {
                window.openVehicleDetailFloatingSection(section, id);
            }
        }, 180);
    };

    function formatMoney(value) {
        const n = Number(value);
        return Number.isFinite(n) && n > 0 ? `${Math.round(n).toLocaleString('cs-CZ')} Kč` : '—';
    }

    function formatRecordTitle(record) {
        return String(record?.description || record?.summary || record?.category || 'Servisní záznam').trim();
    }

    function getRecordDate(record) {
        const value = record?.performed_at || record?.created_at || record?.date;
        const d = value ? new Date(value) : null;
        return d && Number.isFinite(d.getTime()) ? d : null;
    }

    async function fetchVehiclesWithRecords(limitVehicles = 24) {
        if (typeof window.apiCall !== 'function') return { vehicles: [], records: [] };
        const vehiclesRaw = await window.apiCall('/api/v1/vehicles', 'GET');
        const vehicles = Array.isArray(vehiclesRaw) ? vehiclesRaw : [];
        const batches = await Promise.allSettled(vehicles.slice(0, limitVehicles).map(async (vehicle) => {
            const id = Number(vehicle?.id || 0);
            if (!id) return [];
            const recordsRaw = await window.apiCall(`/api/v1/vehicles/${id}/records`, 'GET');
            const records = Array.isArray(recordsRaw) ? recordsRaw : [];
            return records.map((record) => ({ ...record, __vehicle: vehicle }));
        }));
        const records = [];
        batches.forEach((result) => {
            if (result.status === 'fulfilled' && Array.isArray(result.value)) records.push(...result.value);
        });
        records.sort((a, b) => (getRecordDate(b)?.getTime() || 0) - (getRecordDate(a)?.getTime() || 0));
        return { vehicles, records };
    }

    function activateSyntheticTab(tabKey, contentId) {
        document.querySelectorAll('.tab').forEach((item) => item.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach((item) => item.classList.remove('active'));
        const target = document.getElementById(contentId);
        if (target) target.classList.add('active');
        updateActiveChromeNav(tabKey);
        updateChromeIdentity();
    }

    async function renderServiceHistoryRestyle() {
        injectChrome();
        activateSyntheticTab('serviceHistory', 'vehiclesTab');
        const vehiclesTab = document.getElementById('vehiclesTab');
        if (!vehiclesTab) return;
        vehiclesTab.innerHTML = '<section class="user-restyle-service-history"><div class="user-restyle-empty">Načítám servisní historii...</div></section>';
        try {
            const { vehicles, records } = await fetchVehiclesWithRecords();
            const total = records.length;
            const totalCost = records.reduce((sum, record) => {
                const price = Number(record?.price || record?.total_price || 0);
                return Number.isFinite(price) ? sum + price : sum;
            }, 0);
            const serviceMap = new Map();
            records.forEach((record) => {
                const service = String(record?.service_name || record?.supplier_name || record?.created_by_service_name || 'Vlastní záznam').trim();
                const prev = serviceMap.get(service) || { count: 0, cost: 0 };
                prev.count += 1;
                const price = Number(record?.price || record?.total_price || 0);
                if (Number.isFinite(price)) prev.cost += price;
                serviceMap.set(service, prev);
            });
            const serviceRows = Array.from(serviceMap.entries()).slice(0, 5);
            const rowsHtml = records.map((record, index) => {
                const vehicle = record.__vehicle || {};
                const id = Number(record?.id || 0);
                const vehicleId = Number(vehicle?.id || record?.vehicle_id || 0);
                const date = getRecordDate(record);
                const title = formatRecordTitle(record);
                const category = String(record?.category || '').replace(/_/g, ' ') || 'Servis';
                const service = String(record?.service_name || record?.supplier_name || record?.created_by_service_name || 'Servisní záznam');
                return `
                    <article class="user-restyle-history-row">
                        <div class="user-restyle-history-date"><strong>${escape(date ? formatDate(date) : '—')}</strong><span>${escape(formatKm(record?.mileage || vehicle?.current_mileage_km))}</span></div>
                        <div class="user-restyle-history-icon">${icon(index % 3 === 0 ? 'wrench' : index % 3 === 1 ? 'file' : 'settings')}</div>
                        <div class="user-restyle-history-main">
                            <h3>${escape(title)}</h3>
                            <p>${escape(getVehicleName(vehicle))} <span>${escape(vehicle?.plate || '')}</span></p>
                            <strong>${escape(service)}</strong>
                        </div>
                        <div class="user-restyle-history-price">${escape(formatMoney(record?.price || record?.total_price))}</div>
                        <div class="user-restyle-history-state">${escape(record?.verified_at || record?.is_verified ? 'Ověřeno' : category)}</div>
                        <div class="user-restyle-history-actions">
                            <button type="button" onclick="showServiceRecordDetail(${id}, ${vehicleId})">${icon('search')} Detail</button>
                            <button type="button" onclick="showServiceRecordDetail(${id}, ${vehicleId})">${icon('file')} Dokumenty</button>
                            <button type="button" onclick="openAddServiceRecordModal(${vehicleId})">${icon('plus')} Upravit</button>
                        </div>
                    </article>
                `;
            }).join('');
            vehiclesTab.innerHTML = `
                <section class="user-restyle-service-history">
                    <header class="user-restyle-section-head">
                        <div>
                            <h1>Servisní historie</h1>
                            <p>Kompletní přehled servisních zásahů napříč vašimi vozidly</p>
                        </div>
                        <button type="button" class="user-restyle-add-btn" onclick="openAddServiceRecordModal()">${icon('plus')}<span>Přidat servisní záznam</span></button>
                    </header>
                    <div class="user-restyle-filter-row">
                        <button type="button">${icon('car')}<span>Vozidlo<strong>${vehicles.length ? 'Všechna vozidla' : 'Bez vozidel'}</strong></span></button>
                        <button type="button">${icon('calendar')}<span>Období<strong>Poslední 2 roky</strong></span></button>
                        <button type="button">${icon('wrench')}<span>Typ úkonu<strong>Všechny typy</strong></span></button>
                        <button type="button">${icon('building')}<span>Servis<strong>Všechny servisy</strong></span></button>
                        <button type="button" onclick="window.loadUserRestyleServiceHistory()">${icon('settings')} Vymazat filtry</button>
                    </div>
                    <div class="user-restyle-history-layout">
                        <section class="user-restyle-card user-restyle-history-list">
                            <header class="user-restyle-panel-head"><h2>Servisní záznamy</h2><span>${total} záznamů</span></header>
                            ${rowsHtml || '<div class="user-restyle-empty">Zatím nemáte žádné servisní záznamy.</div>'}
                        </section>
                        <aside class="user-restyle-side-stack">
                            <section class="user-restyle-card user-restyle-panel">
                                <header class="user-restyle-panel-head"><h3>Souhrn nákladů</h3><button type="button" class="user-restyle-panel-link">Poslední 2 roky</button></header>
                                <div class="user-restyle-big-number">${escape(formatMoney(totalCost))}</div>
                                <p class="user-restyle-muted">Celkové náklady za servis</p>
                                <div class="user-restyle-mini-chart" aria-hidden="true"><span></span><span></span><span></span><span></span><span></span><span></span></div>
                            </section>
                            <section class="user-restyle-card user-restyle-panel">
                                <header class="user-restyle-panel-head"><h3>Servisy, které vozidla obsluhovaly</h3></header>
                                ${serviceRows.map(([name, item]) => `<div class="user-restyle-side-line"><strong>${escape(name)}</strong><span>${item.count} zásahů</span><em>${escape(formatMoney(item.cost))}</em></div>`).join('') || '<div class="user-restyle-empty">Bez servisních partnerů.</div>'}
                            </section>
                            <section class="user-restyle-card user-restyle-panel">
                                <header class="user-restyle-panel-head"><h3>Doporučené další kroky</h3></header>
                                <button type="button" class="user-restyle-action-line" onclick="openAddServiceRecordModal()">${icon('plus')} Přidat další servisní úkon</button>
                                <button type="button" class="user-restyle-action-line" onclick="switchTab('reminders')">${icon('bell')} Zkontrolovat připomínky</button>
                            </section>
                        </aside>
                    </div>
                </section>
            `;
        } catch (error) {
            vehiclesTab.innerHTML = `<section class="user-restyle-service-history"><div class="user-restyle-empty">Servisní historii se nepodařilo načíst: ${escape(error?.message || error)}</div></section>`;
        }
    }

    window.loadUserRestyleServiceHistory = renderServiceHistoryRestyle;

    function reminderDate(reminder) {
        return reminder?.due_date || reminder?.notify_at || reminder?.created_at || '';
    }

    function reminderStatus(reminder) {
        if (reminder?.is_completed) return 'done';
        const d = reminderDate(reminder) ? new Date(reminderDate(reminder)) : null;
        if (d && Number.isFinite(d.getTime())) {
            const today = new Date();
            today.setHours(0, 0, 0, 0);
            d.setHours(0, 0, 0, 0);
            if (d < today) return 'late';
            const days = Math.round((d.getTime() - today.getTime()) / 86400000);
            if (days <= 14) return 'soon';
        }
        return 'planned';
    }

    function renderReminderCard(reminder) {
        const id = Number(reminder?.id || 0);
        const status = reminderStatus(reminder);
        const labels = { late: 'Vysoká', soon: 'Střední', planned: 'Nízká', done: 'Dokončeno' };
        const vehicleName = reminder?.vehicle_name || reminder?.vehicle_plate || 'Obecná připomínka';
        return `
            <article class="user-restyle-reminder-card is-${status}">
                <header><span>${icon(status === 'done' ? 'check' : status === 'late' ? 'bell' : 'calendar')}</span><strong>${escape(reminder?.type || 'Připomínka')}</strong><em>${escape(labels[status])}</em></header>
                <h3>${escape(vehicleName)}</h3>
                <p>${escape(reminder?.vehicle_plate || '')}</p>
                <div class="user-restyle-reminder-date">${escape(status === 'late' ? 'Termín byl' : status === 'soon' ? 'do' : '')} ${escape(formatDate(reminderDate(reminder)))}</div>
                <small>${escape(reminder?.text || 'Bez popisu')}</small>
                <footer>
                    ${id && status !== 'done' ? `<button type="button" onclick="window.completeUserRestyleReminder(${id})">${icon('check')} Splnit</button>` : ''}
                    ${id && status !== 'done' ? `<button type="button" onclick="window.editReminder ? editReminder(${id}) : window.openUserRestyleReminderDetail(${id})">${icon('settings')} Odložit</button>` : ''}
                    <button type="button" onclick="window.openUserRestyleReminderDetail(${id})">${icon('file')} Detail</button>
                </footer>
            </article>
        `;
    }

    async function renderRemindersRestyle(remindersOverride = null) {
        injectChrome();
        updateActiveChromeNav('reminders');
        const container = document.getElementById('remindersContainer');
        if (!container || typeof window.apiCall !== 'function') return;
        const reminders = Array.isArray(remindersOverride)
            ? remindersOverride
            : await window.apiCall('/api/v1/reminders?include_completed=true', 'GET');
        const list = Array.isArray(reminders) ? reminders : [];
        window.__userRestyleReminders = list;
        const buckets = {
            late: list.filter((item) => reminderStatus(item) === 'late'),
            soon: list.filter((item) => reminderStatus(item) === 'soon'),
            planned: list.filter((item) => reminderStatus(item) === 'planned'),
            done: list.filter((item) => reminderStatus(item) === 'done'),
        };
        const stats = [
            ['Dnes', buckets.soon.filter((item) => {
                const d = new Date(reminderDate(item));
                const t = new Date();
                return Number.isFinite(d.getTime()) && d.toDateString() === t.toDateString();
            }).length, 'calendar'],
            ['Tento týden', buckets.soon.length, 'calendar'],
            ['Po termínu', buckets.late.length, 'bell'],
            ['Dokončeno', buckets.done.length, 'check'],
        ];
        container.innerHTML = `
            <section class="user-restyle-reminders">
                <header class="user-restyle-section-head">
                    <div><h1>Připomínky</h1><p>Hlídejte STK, pojištění, servis i vlastní úkoly</p></div>
                    <button type="button" class="user-restyle-add-btn" onclick="showCreateReminderForm()">${icon('plus')}<span>Nová připomínka</span></button>
                </header>
                <div class="user-restyle-reminder-stats">
                    ${stats.map(([label, count, glyph]) => `<button type="button" class="user-restyle-card">${icon(glyph)}<strong>${count}</strong><span>${escape(label)}</span><em>${count === 1 ? '1 úkol' : `${count} úkolů`}</em></button>`).join('')}
                </div>
                <div class="user-restyle-reminder-layout">
                    <div class="user-restyle-reminder-board">
                        ${[
                            ['late', 'Po termínu', '#ef3b2d'],
                            ['soon', 'Blíží se', '#ff7a1a'],
                            ['planned', 'Naplánováno', '#0f49c9'],
                            ['done', 'Dokončeno', '#18a54a'],
                        ].map(([key, title, color]) => `
                            <section class="user-restyle-reminder-column" style="--tone:${color}">
                                <header><h2>${escape(title)}</h2><span>${buckets[key].length}</span></header>
                                <div>${buckets[key].map(renderReminderCard).join('') || '<div class="user-restyle-empty">Žádné položky.</div>'}</div>
                                <button type="button" onclick="showCreateReminderForm()">${icon('plus')} Nová připomínka</button>
                            </section>
                        `).join('')}
                    </div>
                    <aside class="user-restyle-side-stack">
                        <section class="user-restyle-card user-restyle-panel">
                            <header class="user-restyle-panel-head"><h3>Kalendář</h3><button type="button" class="user-restyle-panel-link" onclick="showCreateReminderForm()">+</button></header>
                            <div class="user-restyle-calendar-mini">${Array.from({ length: 35 }, (_, i) => `<span class="${i === 18 ? 'is-hot' : i === 20 ? 'is-plan' : ''}">${(i % 31) + 1}</span>`).join('')}</div>
                        </section>
                        <section class="user-restyle-card user-restyle-panel">
                            <header class="user-restyle-panel-head"><h3>Automatické připomínky</h3><button type="button" class="user-restyle-panel-link" onclick="showCreateReminderForm()">Nastavit</button></header>
                            ${['STK / SME', 'Pojištění', 'Servisní intervaly', 'Olej / kapaliny', 'Pneumatiky'].map((item) => `<div class="user-restyle-toggle-line"><span>${escape(item)}</span><strong>Zapnuto</strong></div>`).join('')}
                        </section>
                        <section class="user-restyle-card user-restyle-panel">
                            <header class="user-restyle-panel-head"><h3>Doporučení podle vozidel</h3><button type="button" class="user-restyle-panel-link" onclick="switchTab('vehicles')">Zobrazit vše</button></header>
                            ${list.slice(0, 2).map((item) => `<button type="button" class="user-restyle-action-line" onclick="${item?.vehicle_id ? `showVehicleDetail(${Number(item.vehicle_id)})` : "switchTab('vehicles')"}">${icon('car')} ${escape(item?.vehicle_name || item?.text || 'Vozidlo')}</button>`).join('') || '<div class="user-restyle-empty">Bez doporučení.</div>'}
                        </section>
                    </aside>
                </div>
            </section>
        `;
    }

    window.openUserRestyleReminderDetail = function (id) {
        const reminder = (window.__userRestyleReminders || []).find((item) => Number(item?.id) === Number(id));
        if (!reminder) {
            if (typeof window.showAlert === 'function') window.showAlert('Detail připomínky není dostupný.', 'error');
            return;
        }
        const modal = document.createElement('div');
        modal.className = 'user-restyle-lightbox';
        modal.innerHTML = `
            <div class="user-restyle-lightbox-card">
                <button type="button" class="user-restyle-lightbox-close" onclick="this.closest('.user-restyle-lightbox').remove()">×</button>
                <p class="user-restyle-kicker">Připomínka</p>
                <h2>${escape(reminder?.type || 'Připomínka')}</h2>
                <div class="user-restyle-detail-fields">
                    <span>Vozidlo<strong>${escape(reminder?.vehicle_name || 'Obecná připomínka')}</strong></span>
                    <span>Termín<strong>${escape(formatDate(reminderDate(reminder)))}</strong></span>
                    <span>Stav<strong>${escape(reminderStatus(reminder))}</strong></span>
                    <span>Popis<strong>${escape(reminder?.text || '—')}</strong></span>
                </div>
                <div class="user-restyle-lightbox-actions">
                    ${reminder?.vehicle_id ? `<button type="button" onclick="this.closest('.user-restyle-lightbox').remove(); showVehicleDetail(${Number(reminder.vehicle_id)})">Otevřít vozidlo</button>` : ''}
                    ${reminder?.id ? `<button type="button" onclick="this.closest('.user-restyle-lightbox').remove(); editReminder(${Number(reminder.id)})">Upravit</button>` : ''}
                    <button type="button" onclick="this.closest('.user-restyle-lightbox').remove()">Zavřít</button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
    };

    window.completeUserRestyleReminder = async function (id) {
        const reminder = (window.__userRestyleReminders || []).find((item) => Number(item?.id) === Number(id));
        if (!reminder || typeof window.apiCall !== 'function') return;
        try {
            await window.apiCall(`/api/v1/reminders/${Number(id)}`, 'PUT', { ...reminder, is_completed: true });
            if (typeof window.showAlert === 'function') window.showAlert('Připomínka označena jako splněná.', 'success');
            await renderRemindersRestyle();
        } catch (error) {
            if (typeof window.showAlert === 'function') window.showAlert(`Připomínku se nepodařilo splnit: ${error?.message || error}`, 'error');
        }
    };

    async function enhanceVehicleDetailRestyle(vehicleId) {
        const modal = document.getElementById('vehicleDetailModal');
        const body = document.getElementById('vehicleModalBody');
        const vehicle = window.currentVehicle;
        if (!modal || !body || !vehicle) return;
        modal.classList.add('user-restyle-detail-modal');
        body.querySelector('.user-restyle-detail-overview')?.remove();
        let records = [];
        try {
            const raw = await window.apiCall(`/api/v1/vehicles/${Number(vehicleId)}/records`, 'GET');
            records = Array.isArray(raw) ? raw : [];
        } catch (error) {}
        const latest = records.slice().sort((a, b) => (getRecordDate(b)?.getTime() || 0) - (getRecordDate(a)?.getTime() || 0))[0] || null;
        const stk = getVehicleStkDate(vehicle);
        const status = getVehicleStatus(vehicle);
        const timelineRows = records.slice(0, 5).map((record) => {
            const d = getRecordDate(record);
            return `
                <button type="button" class="user-restyle-detail-timeline-row" onclick="showServiceRecordDetail(${Number(record?.id || 0)}, ${Number(vehicleId)})">
                    <span></span>
                    <strong>${escape(d ? formatDate(d) : '—')}</strong>
                    <em>${escape(formatRecordTitle(record))}</em>
                </button>
            `;
        }).join('');
        body.insertAdjacentHTML('afterbegin', `
            <section class="user-restyle-detail-overview">
                <div class="user-restyle-detail-hero-card">
                    <div class="user-restyle-detail-photo" id="user-restyle-detail-photo-${Number(vehicleId)}">
                        ${typeof window.vehiclePrimaryPhotoAvailable === 'function' && window.vehiclePrimaryPhotoAvailable(vehicle) ? `<img id="user-restyle-detail-img-${Number(vehicleId)}" alt="${escape(getVehicleName(vehicle))}">` : renderHeroVehicleMedia(null)}
                    </div>
                    <div class="user-restyle-detail-copy">
                        <h1>${escape(getVehicleName(vehicle))}</h1>
                        <div class="user-restyle-detail-badges"><span>${escape(vehicle?.plate || 'SPZ —')}</span><span class="${status.className}">${escape(status.label)}</span></div>
                        <div class="user-restyle-detail-meta">
                            <span>VIN<strong>${escape(vehicle?.vin || '—')}</strong></span>
                            <span>Rok výroby<strong>${escape(vehicle?.year || '—')}</strong></span>
                            <span>Palivo<strong>${escape(vehicle?.fuel_type || vehicle?.fuel || '—')}</strong></span>
                            <span>Výkon<strong>${escape(vehicle?.power_kw ? `${vehicle.power_kw} kW` : '—')}</strong></span>
                        </div>
                        <div class="user-restyle-detail-actions">
                            <button type="button" onclick="openVehicleDetailFloatingSection('basic', ${Number(vehicleId)})">${icon('settings')} Upravit</button>
                            <button type="button" onclick="openAddServiceRecordModal(${Number(vehicleId)})">${icon('plus')} Přidat záznam</button>
                            <button type="button" onclick="openVehicleDetailFloatingSection('documents', ${Number(vehicleId)})">${icon('file')} Nahrát dokument</button>
                            <button type="button" onclick="openVehicleDetailFloatingSection('access', ${Number(vehicleId)})">${icon('share')} Sdílet se servisem</button>
                        </div>
                    </div>
                </div>
                <div class="user-restyle-detail-stat-grid">
                    ${[
                        ['STK / SME', stk ? formatDate(stk) : '—', status.label, 'calendar'],
                        ['Pojištění', vehicle?.insurance_valid_until ? formatDate(vehicle.insurance_valid_until) : '—', 'V pořádku', 'shield'],
                        ['Nájezd', formatKm(vehicle?.current_mileage_km), latest?.performed_at ? `Poslední záznam ${formatDate(latest.performed_at)}` : 'Bez záznamu', 'grid'],
                        ['Poslední servis', latest ? formatRecordTitle(latest) : 'Bez servisního záznamu', latest?.performed_at ? formatDate(latest.performed_at) : 'Doplňte historii', 'wrench'],
                        ['Dokumenty', 'Dokumenty vozidla', 'Zobrazit', 'folder'],
                        ['Přístupy servisů', 'Spravovat sdílení', 'Přístupy', 'building'],
                    ].map(([title, value, hint, glyph]) => `<button type="button" class="user-restyle-detail-stat" onclick="${title === 'Dokumenty' ? `openVehicleDetailFloatingSection('documents', ${Number(vehicleId)})` : title === 'Přístupy servisů' ? `openVehicleDetailFloatingSection('access', ${Number(vehicleId)})` : `openVehicleDetailFloatingSection('basic', ${Number(vehicleId)})`}">${icon(glyph)}<span>${escape(title)}</span><strong>${escape(value)}</strong><em>${escape(hint)}</em></button>`).join('')}
                </div>
                <div class="user-restyle-detail-tabs">
                    ${[
                        ['Technické údaje', 'basic', 'car'],
                        ['Servisní historie', 'service', 'wrench'],
                        ['Dokumenty', 'documents', 'file'],
                        ['Fotogalerie', 'gallery', 'folder'],
                        ['Připomínky', 'ops', 'bell'],
                        ['Přístupy a sdílení', 'access', 'building'],
                    ].map(([label, section, glyph], index) => `<button type="button" class="${index === 0 ? 'is-active' : ''}" onclick="openVehicleDetailFloatingSection('${section}', ${Number(vehicleId)})">${icon(glyph)} ${escape(label)}</button>`).join('')}
                </div>
                <div class="user-restyle-detail-lower-grid">
                    <section class="user-restyle-card user-restyle-panel">
                        <header class="user-restyle-panel-head"><h2>Základní informace</h2><button type="button" class="user-restyle-panel-link" onclick="openVehicleDetailFloatingSection('basic', ${Number(vehicleId)})">Upravit</button></header>
                        <div class="user-restyle-detail-info-grid">
                            ${[
                                ['Značka / model', [vehicle?.brand, vehicle?.model].filter(Boolean).join(' ') || getVehicleName(vehicle)],
                                ['Typ', vehicle?.type || vehicle?.body_type || '—'],
                                ['VIN', vehicle?.vin || '—'],
                                ['SPZ', vehicle?.plate || '—'],
                                ['Datum první registrace', vehicle?.first_registration_date ? formatDate(vehicle.first_registration_date) : '—'],
                                ['Palivo', vehicle?.fuel_type || vehicle?.fuel || '—'],
                                ['Objem motoru', vehicle?.engine_volume_cc ? `${vehicle.engine_volume_cc} ccm` : '—'],
                                ['Výkon', vehicle?.power_kw ? `${vehicle.power_kw} kW` : '—'],
                                ['Nájezd', formatKm(vehicle?.current_mileage_km)],
                                ['STK', stk ? formatDate(stk) : '—'],
                            ].map(([label, value]) => `<span>${escape(label)}<strong>${escape(value)}</strong></span>`).join('')}
                        </div>
                    </section>
                    <aside class="user-restyle-side-stack">
                        <section class="user-restyle-card user-restyle-panel">
                            <header class="user-restyle-panel-head"><h3>Časová osa vozidla</h3><button type="button" class="user-restyle-panel-link" onclick="openVehicleDetailFloatingSection('service', ${Number(vehicleId)})">Zobrazit vše</button></header>
                            <div class="user-restyle-detail-timeline">${timelineRows || '<div class="user-restyle-empty">Bez servisní aktivity.</div>'}</div>
                        </section>
                        <section class="user-restyle-card user-restyle-panel">
                            <header class="user-restyle-panel-head"><h3>Rychlé akce</h3></header>
                            <button type="button" class="user-restyle-action-line" onclick="openAddServiceRecordModal(${Number(vehicleId)})">${icon('plus')} Přidat servisní úkon</button>
                            <button type="button" class="user-restyle-action-line" onclick="openVehicleDetailFloatingSection('ops', ${Number(vehicleId)})">${icon('grid')} Přidat záznam tachometru</button>
                            <button type="button" class="user-restyle-action-line" onclick="openVehicleDetailFloatingSection('documents', ${Number(vehicleId)})">${icon('file')} Nahrát dokument</button>
                            <button type="button" class="user-restyle-action-line" onclick="generateServiceRecordsPDF(${Number(vehicleId)})">${icon('file')} Exportovat PDF report</button>
                        </section>
                    </aside>
                </div>
            </section>
        `);
        const img = document.getElementById(`user-restyle-detail-img-${Number(vehicleId)}`);
        if (img && typeof window.hydrateVehiclePhotoPreview === 'function') {
            try { await window.hydrateVehiclePhotoPreview(Number(vehicleId), img, 'user-restyle-detail'); } catch (error) {}
        }
    }

    function patchRuntime() {
        if (isServiceAccount()) {
            disableRestyleChromeForService();
            return;
        }
        injectChrome();
        restoreSidebarState();
        const originalSwitchTab = window.switchTab;
        if (typeof originalSwitchTab === 'function' && !originalSwitchTab.__userRestyleWrapped) {
            const wrappedSwitchTab = function (tab, options) {
                if (isServiceAccount()) {
                    disableRestyleChromeForService();
                    return originalSwitchTab.call(this, tab, options || {});
                }
                if (String(tab || '') === 'serviceHistory') {
                    void renderServiceHistoryRestyle();
                    return undefined;
                }
                const result = originalSwitchTab.call(this, tab, options || {});
                updateActiveChromeNav(tab);
                updateChromeIdentity();
                return result;
            };
            wrappedSwitchTab.__userRestyleWrapped = true;
            window.switchTab = wrappedSwitchTab;
        }

        const originalRenderDashboard = window.renderHomeDashboardState;
        if (typeof originalRenderDashboard === 'function' && !originalRenderDashboard.__userRestyleWrapped) {
            const wrappedRenderDashboard = function (model) {
                if (window.isServiceWorkspaceRole && window.isServiceWorkspaceRole()) {
                    return originalRenderDashboard.call(this, model);
                }
                renderRestyleDashboard(model || {});
                return undefined;
            };
            wrappedRenderDashboard.__userRestyleWrapped = true;
            window.renderHomeDashboardState = wrappedRenderDashboard;
        }

        const originalLoadVehicles = window.loadVehicles;
        if (typeof originalLoadVehicles === 'function' && !originalLoadVehicles.__userRestyleWrapped) {
            const wrappedLoadVehicles = async function (force) {
                if (window.isServiceWorkspaceRole && window.isServiceWorkspaceRole()) {
                    return originalLoadVehicles.call(this, force);
                }
                const container = document.getElementById('vehiclesContainer');
                if (!container || typeof window.apiCall !== 'function') {
                    return originalLoadVehicles.call(this, force);
                }
                if (window.isAuthenticated && !window.isAuthenticated()) return undefined;
                container.classList.add('loading');
                container.innerHTML = '<div class="loading">Načítám vozidla...</div>';
                try {
                    const vehicles = await window.apiCall('/api/v1/vehicles', 'GET');
                    const list = Array.isArray(vehicles) ? vehicles : [];
                    await loadVehicleRecordsForPreview(list);
                    renderRestyleVehicles(container, list);
                    return undefined;
                } catch (error) {
                    return originalLoadVehicles.call(this, force);
                }
            };
            wrappedLoadVehicles.__userRestyleWrapped = true;
            window.loadVehicles = wrappedLoadVehicles;
        }

        const originalLoadReminders = window.loadReminders;
        if (typeof originalLoadReminders === 'function' && !originalLoadReminders.__userRestyleWrapped) {
            const wrappedLoadReminders = async function (force) {
                if (window.isServiceWorkspaceRole && window.isServiceWorkspaceRole()) {
                    return originalLoadReminders.call(this, force);
                }
                try {
                    const result = await originalLoadReminders.call(this, force);
                    if (window.__licenseFlags && window.__licenseFlags.remindersEnabled === false) return result;
                    await renderRemindersRestyle();
                    return result;
                } catch (error) {
                    return originalLoadReminders.call(this, force);
                }
            };
            wrappedLoadReminders.__userRestyleWrapped = true;
            window.loadReminders = wrappedLoadReminders;
        }

        const originalShowVehicleDetail = window.showVehicleDetail;
        if (typeof originalShowVehicleDetail === 'function' && !originalShowVehicleDetail.__userRestyleWrapped) {
            const wrappedShowVehicleDetail = async function (vehicleId) {
                const result = await originalShowVehicleDetail.call(this, vehicleId);
                if (!(window.isServiceWorkspaceRole && window.isServiceWorkspaceRole())) {
                    await enhanceVehicleDetailRestyle(vehicleId);
                }
                return result;
            };
            wrappedShowVehicleDetail.__userRestyleWrapped = true;
            window.showVehicleDetail = wrappedShowVehicleDetail;
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', patchRuntime, { once: true });
    } else {
        patchRuntime();
    }
    window.addEventListener('load', patchRuntime, { once: true });
})();
