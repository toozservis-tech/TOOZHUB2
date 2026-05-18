(function () {
    'use strict';

    const RESTYLE_BRANCH = 'feature/user-dashboard-restyle-from-prod-20260517';
    const RESTYLE_SEARCH_STATE = {
        vehicleQuery: '',
        vehicleFilter: 'all',
        vehicleSort: 'name',
        vehicleView: 'grid',
    };

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
        document.body.classList.remove('user-dashboard-restyle', 'user-dashboard-restyle-compact');
    }

    function injectChrome() {
        if (isServiceAccount()) {
            disableRestyleChromeForService();
            return;
        }
        document.body.classList.add('user-dashboard-restyle');
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
                        ['serviceHistory', 'Servisní historie', 'wrench', 'vehicles'],
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
            window.localStorage?.setItem('userDashboardRestyleCompact', compact ? '1' : '0');
        } catch (error) {}
    };

    function restoreSidebarState() {
        try {
            document.body.classList.toggle(
                'user-dashboard-restyle-compact',
                window.localStorage?.getItem('userDashboardRestyleCompact') === '1'
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
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', patchRuntime, { once: true });
    } else {
        patchRuntime();
    }
    window.addEventListener('load', patchRuntime, { once: true });
})();
