(function () {
  console.log('[SERVICE_SHELL] SERVICE SHELL LOADED');

  function getAppDisplayName() {
    try {
      if (typeof window !== 'undefined') {
        if (typeof window.__appDisplayName === 'string' && window.__appDisplayName.trim()) {
          return window.__appDisplayName.trim();
        }
        if (typeof window.APP_NAME === 'string' && window.APP_NAME.trim()) {
          return window.APP_NAME.trim();
        }
      }
    } catch (e) {
      /* ignore */
    }
    return 'Správa vozidel';
  }

  const rootId = 'serviceAppRoot';
  const themeKey = 'serviceShellTheme';
  const dataTtlMs = 30000;
  const autoRefreshMs = 60000;
  const defaultSection = 'dashboard';
  const serviceSections = new Set([
    'dashboard',
    'clients',
    'vehicles',
    'work-orders',
    'documents',
    'invoices',
    'reservations',
    'reminders',
    'team',
  ]);
  const legacyTargets = [
    { key: 'mainNavbar', selector: '#mainNavbar' },
    { key: 'dashboard', selector: '#dashboard' },
    { key: 'footer', selector: '.payment-legal-footer' },
  ];

  const originalShowDashboard = window.showDashboard;
  const originalShowLogin = window.showLogin;
  const originalSwitchTab = window.switchTab;
  const originalLoadHomeDashboard = window.loadHomeDashboard;
  const originalRenderServiceWorkspace = window.renderServiceWorkspace;
  const originalLoadServiceWorkspace = window.loadServiceWorkspace;
  const originalOpenServiceAddVehicleForCustomer = window.openServiceAddVehicleForCustomer;
  const originalOpenServiceDashboardCreateModal = window.openServiceDashboardCreateModal;
  const originalOpenServiceDashboardWorkOrderDetail = window.openServiceDashboardWorkOrderDetail;
  const originalSubmitServiceDashboardDetailUpdate = window.submitServiceDashboardDetailUpdate;

  const parkedLegacyNodes = new Map();

  const state = {
    mounted: false,
    loading: false,
    theme: safeStorageGet(themeKey) || 'dark',
    activeSection: defaultSection,
    kpiFilter: 'all',
    searchTerm: '',
    sortBy: 'due_asc',
    summary: null,
    workOrders: [],
    performance: [],
    technicians: [],
    queue: null,
    customers: [],
    vehicles: [],
    reservations: [],
    reminders: [],
    documents: [],
    invoices: [],
    profile: {},
    errors: [],
    lastLoadedAt: 0,
    autoRefreshHandle: 0,
    accountMenuOpen: false,
    mobileNavOpen: false,
    customerSearchQuery: '',
    customerSearchResults: [],
    customerSearchMeta: null,
    customerSearchLoading: false,
    customerSearchError: '',
    vehicleLookupQuery: '',
    vehicleLookupResults: [],
    vehicleLookupMeta: null,
    vehicleLookupLoading: false,
    vehicleLookupError: '',
    workOrderDraft: null,
    addVehicleDraft: null,
    activeVehicle: null,
    modal: null,
    quoteListPrefs: { status: 'all', sort: 'created_at', order: 'desc' },
  };

  state.modal = createEmptyModalState();

  function safeStorageGet(key) {
    try {
      return window.localStorage.getItem(key);
    } catch (error) {
      return null;
    }
  }

  function safeStorageSet(key, value) {
    try {
      window.localStorage.setItem(key, value);
    } catch (error) {
      /* noop */
    }
  }

  function getRoot() {
    let root = document.getElementById(rootId);
    if (root) return root;
    const dashboard = document.getElementById('dashboard');
    root = document.createElement('div');
    root.id = rootId;
    root.className = 'service-app-root hidden';
    root.setAttribute('data-testid', 'service-app-root');
    root.setAttribute('data-service-shell', 'root');
    if (dashboard?.parentNode) {
      dashboard.parentNode.insertBefore(root, dashboard);
    } else {
      document.body.appendChild(root);
    }
    return root;
  }

  function isServiceRole() {
    return typeof window.isServiceWorkspaceRole === 'function' && window.isServiceWorkspaceRole();
  }

  function isMobileViewport() {
    return Number(window.innerWidth || 0) <= 900;
  }

  function showToast(message, type = 'info') {
    if (typeof window.showAlert === 'function') {
      window.showAlert(message, type);
    }
  }

  function escape(value) {
    try {
      if (typeof window.escapeHtml === 'function') {
        return window.escapeHtml(value ?? '');
      }
      return String(value ?? '');
    } catch (err) {
      console.warn('[SERVICE_SHELL] escape failed:', err);
      try {
        return String(value ?? '');
      } catch (e2) {
        return '';
      }
    }
  }

  function formatDate(value) {
    if (typeof window.formatDateCZ === 'function') {
      return window.formatDateCZ(value);
    }
    return value ? String(value).slice(0, 10) : '-';
  }

  function initials(value) {
    const parts = String(value || '')
      .split(/[\s@._-]+/)
      .filter(Boolean)
      .slice(0, 2);
    if (!parts.length) return 'SA';
    return parts.map((item) => item.charAt(0).toUpperCase()).join('');
  }

  function todayKey() {
    return new Date().toISOString().slice(0, 10);
  }

  function toDateKey(value) {
    return value ? String(value).slice(0, 10) : '';
  }

  function statusMeta(status) {
    const key = String(status || '').trim().toLowerCase();
    if (key === 'awaiting_client_approval') return { label: 'Awaiting', cls: 'awaiting' };
    if (key === 'completed') return { label: 'Completed', cls: 'completed' };
    if (key === 'issue') return { label: 'Issue', cls: 'issue' };
    if (key === 'approved') return { label: 'Approved', cls: 'in_progress' };
    return { label: 'In Progress', cls: 'in_progress' };
  }

  function sourceLabel(source) {
    const key = String(source || '').trim().toLowerCase();
    if (key === 'manual') return 'Manual Entry';
    if (key === 'api') return 'API Sync';
    if (key === 'crm') return 'CRM Import';
    if (key === 'reservation') return 'Reservation';
    return source ? String(source) : '-';
  }

  function formatDateTime(value) {
    if (!value) return '-';
    try {
      return new Date(value).toLocaleString('cs-CZ');
    } catch (error) {
      return String(value);
    }
  }

  function toDateTimeInputValue(value) {
    if (!value) return '';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '';
    const offset = date.getTimezoneOffset();
    const local = new Date(date.getTime() - (offset * 60000));
    return local.toISOString().slice(0, 16);
  }

  function fromDateTimeInputValue(value) {
    const raw = String(value || '').trim();
    if (!raw) return null;
    const date = new Date(raw);
    if (Number.isNaN(date.getTime())) return null;
    return date.toISOString();
  }

  function formatMoney(value, currency = 'CZK') {
    const amount = Number(value);
    if (!Number.isFinite(amount)) return '-';
    try {
      return new Intl.NumberFormat('cs-CZ', {
        style: 'currency',
        currency: currency || 'CZK',
        maximumFractionDigits: 2,
      }).format(amount);
    } catch (error) {
      return `${amount} ${currency || 'CZK'}`;
    }
  }

  function disclosureLabel(value) {
    return String(value || '').toLowerCase() === 'full' ? 'Plné zobrazení' : 'Omezené zobrazení';
  }

  function accessStatusLabel(value) {
    const key = String(value || '').trim().toLowerCase();
    if (key === 'linked') return 'Propojeno';
    if (key === 'not_linked') return 'Nepropojeno';
    if (key === 'already_approved') return 'Přístup schválen';
    if (key === 'pending_request') return 'Žádost čeká';
    if (key === 'matched') return 'Vyžaduje přístup';
    if (key === 'owner_missing') return 'Chybí schvalovatel';
    if (key === 'processed') return 'Zpracováno';
    if (key === 'needs_review') return 'Vyžaduje kontrolu';
    if (key === 'failed') return 'Selhalo';
    if (key === 'open') return 'Aktivní';
    if (key === 'completed') return 'Dokončeno';
    if (key === 'confirmed') return 'Potvrzeno';
    if (key === 'cancelled') return 'Zrušeno';
    if (key === 'pending') return 'Čeká';
    return value ? String(value) : '-';
  }

  function renderDetailPills(detail) {
    const pills = [
      `<span class="service-shell-detail-pill">${escape(accessStatusLabel(detail?.status || detail?.access_status))}</span>`,
      `<span class="service-shell-detail-pill">${escape(disclosureLabel(detail?.disclosure))}</span>`,
    ];
    if (detail?.can_edit) pills.push('<span class="service-shell-detail-pill">Lze upravit</span>');
    if (detail?.can_request_access) pills.push('<span class="service-shell-detail-pill">Lze žádat přístup</span>');
    if (detail?.can_create_work_order) pills.push('<span class="service-shell-detail-pill">Lze založit zakázku</span>');
    return `<div class="service-shell-detail-pills">${pills.join('')}</div>`;
  }

  function renderBlockingReason(detail) {
    if (!detail?.blocking_reason) return '';
    return `<div class="service-shell-inline-error">${escape(detail.blocking_reason)}</div>`;
  }

  function openDetailModal(config = {}) {
    const entityId = Number(config.entityId || 0);
    if (!entityId) return;
    return openModal({
      key: `${config.entityType}-detail-${entityId}`,
      entityType: config.entityType,
      kicker: config.kicker,
      title: config.title,
      description: config.description,
      size: config.size || 'wide',
      load: async () => {
        if (typeof config.load === 'function') {
          return config.load();
        }
        return window.apiCall(config.endpoint, 'GET');
      },
      actions: config.actions || {},
      renderContent: (modal) => config.renderContent(modal.data || {}, modal),
      renderFooter: (modal) => config.renderFooter(modal.data || {}, modal),
    });
  }

  function currentProfile() {
    return state.profile && Object.keys(state.profile).length ? state.profile : (window.currentUser || {});
  }

  /** Sladění s backend pravidly service_records._assert_current_user_can_edit_record + immutable statusy. */
  function computeServiceRecordShellEditState(record) {
    if (!record || !record.id) {
      return { editable: true, reason: null };
    }
    const status = String(record.record_status || 'draft').toLowerCase();
    if (status === 'approved' || status === 'locked') {
      return {
        editable: false,
        reason: 'Záznam je schválený nebo uzamčený — úpravy nejsou povoleny.',
      };
    }
    const profile = currentProfile();
    const role = String(profile?.role || '').toLowerCase();
    if (role !== 'service') {
      return { editable: true, reason: null };
    }
    const me = Number(profile?.id || 0);
    const creator = Number(record.created_by_service_customer_id ?? 0);
    if (creator && creator === me) {
      return { editable: true, reason: null };
    }
    if (!creator) {
      return {
        editable: false,
        reason: 'Tento záznam nevznikl v aktuálním servisním workflow tohoto servisního účtu — zobrazení je jen pro čtení.',
      };
    }
    return {
      editable: false,
      reason: 'Servis může upravovat jen vlastní servisní záznamy vytvořené v tomto workflow.',
    };
  }

  function hasFloatingModalSupport() {
    return typeof window.mountFloatingModal === 'function' && typeof window.unmountFloatingModal === 'function';
  }

  function setActiveVehicle(detail) {
    if (!detail || !Number(detail.vehicle_id || detail.id || 0)) {
      state.activeVehicle = null;
      return;
    }
    state.activeVehicle = {
      vehicleId: Number(detail.vehicle_id || detail.id || 0),
      label: detail.nickname || [detail.brand, detail.model].filter(Boolean).join(' ') || detail.vehicle_name || 'Vozidlo',
      vin: detail.vin || detail.vin_masked || '-',
      plate: detail.plate || detail.plate_masked || detail.vehicle_plate || '-',
      accessStatus: accessStatusLabel(detail.status || detail.access_status),
      canCreateWorkOrder: Boolean(detail.can_create_work_order),
      ownerCustomerId: Number(detail.owner_customer_id || detail.customer_id || 0) || null,
      hasQrToken: Boolean(detail.has_qr_token),
      recordsCount: Number(detail.records_count || 0),
    };
  }

  function activeVehicleBanner() {
    if (!isMobileViewport() || !state.activeVehicle) return '';
    const vehicle = state.activeVehicle;
    return `
      <section class="service-shell-mobile-vehicle-card">
        <div class="service-shell-mobile-vehicle-head">
          <div>
            <p class="service-shell-mobile-kicker">Aktivní vozidlo</p>
            <h2>${escape(vehicle.label || 'Vozidlo')}</h2>
          </div>
          <span class="service-shell-badge ${vehicle.canCreateWorkOrder ? 'completed' : 'awaiting'}">${escape(vehicle.accessStatus || 'Přístup')}</span>
        </div>
        <div class="service-shell-mobile-vehicle-meta">
          <span>VIN ${escape(vehicle.vin || '-')}</span>
          <span>SPZ ${escape(vehicle.plate || '-')}</span>
          <span>Záznamy ${escape(String(vehicle.recordsCount || 0))}</span>
        </div>
        <div class="service-shell-mobile-vehicle-actions">
          <button type="button" class="service-shell-filter-chip" onclick="window.serviceShell.openServiceRecordModal(${vehicle.vehicleId})">Nový záznam</button>
          ${vehicle.canCreateWorkOrder ? `<button type="button" class="service-shell-filter-chip" onclick="window.serviceShell.openCreateWorkOrderModal({ ownerId: ${Number(vehicle.ownerCustomerId || 0)}, vehicleId: ${vehicle.vehicleId} })">Nová zakázka</button>` : ''}
          <button type="button" class="service-shell-filter-chip" onclick="window.serviceShell.openVehicleQrModal(${vehicle.vehicleId})">QR</button>
        </div>
      </section>
    `;
  }

  function closeFloatingModal() {
    if (typeof window.unmountFloatingModal === 'function') {
      window.unmountFloatingModal();
    }
  }

  function createEmptyModalState() {
    return {
      open: false,
      key: '',
      entityType: '',
      kicker: '',
      title: '',
      description: '',
      size: 'default',
      loading: false,
      saving: false,
      error: '',
      data: null,
      bodyClass: '',
      allowBackdropClose: true,
      renderContent: null,
      renderFooter: null,
      load: null,
      actions: {},
      actionKey: '',
      context: {},
    };
  }

  function isModalOpen(key = '') {
    return Boolean(state.modal?.open) && (!key || state.modal.key === key);
  }

  function closeModal() {
    state.modal = createEmptyModalState();
    closeFloatingModal();
  }

  function handleModalBackdrop(event) {
    if (event?.target !== event?.currentTarget) return;
    if (!state.modal?.allowBackdropClose || state.modal?.saving) return;
    closeModal();
  }

  function modalLoadingState() {
    return `
      <div class="service-shell-modal-state">
        <div class="service-shell-modal-spinner"></div>
        <div>
          <strong>Načítám detail</strong>
          <p>Pracuji nad produkčními servisními daty a ověřuji oprávnění.</p>
        </div>
      </div>
    `;
  }

  function modalErrorState(message) {
    return `
      <div class="service-shell-inline-error service-shell-modal-state service-shell-modal-state-error">
        <div>
          <strong>Nepodařilo se dokončit operaci</strong>
          <p>${escape(message || 'Neznámá chyba')}</p>
        </div>
      </div>
    `;
  }

  function renderModalFooter() {
    if (!state.modal?.open) return '';
    if (typeof state.modal.renderFooter === 'function') {
      try {
        return state.modal.renderFooter(state.modal) || '';
      } catch (error) {
        console.error('[SERVICE_SHELL] modal renderFooter failed:', error);
        return `
      <div class="service-shell-modal-footer">
        <p class="service-shell-inline-error" style="margin:0 0 8px;">Patka modálu selhala: ${escape(String(error?.message || error))}</p>
        <button type="button" class="btn btn-secondary" onclick="window.serviceShell.closeModal()">Zavřít</button>
      </div>
    `;
      }
    }
    return `
      <div class="service-shell-modal-footer">
        <button type="button" class="btn btn-secondary" onclick="window.serviceShell.closeModal()">Zavřít</button>
      </div>
    `;
  }

  function renderModalContent() {
    if (!state.modal?.open) return '';
    if (state.modal.loading) return modalLoadingState();
    if (state.modal.error) return modalErrorState(state.modal.error);
    if (typeof state.modal.renderContent === 'function') {
      try {
        return state.modal.renderContent(state.modal) || '';
      } catch (error) {
        console.error('[SERVICE_SHELL] modal renderContent failed:', error);
        return modalErrorState(error?.message || 'Chyba vykreslení modálu');
      }
    }
    return '';
  }

  function renderModal() {
    if (!state.modal?.open || !hasFloatingModalSupport()) return;
    const sizeClass = state.modal.size === 'wide' ? 'service-shell-modal--wide' : '';
    const bodyClass = state.modal.bodyClass ? ` ${state.modal.bodyClass}` : '';
    const mobileClass = isMobileViewport() ? ' service-shell-modal--mobile-flow' : '';
    window.mountFloatingModal(`
      <div class="service-shell-modal-overlay" onclick="window.serviceShell.handleModalBackdrop(event)">
        <div class="service-shell-modal ${sizeClass}${mobileClass}">
          <div class="service-shell-modal-header">
            <div class="service-shell-modal-heading">
              ${state.modal.kicker ? `<p class="service-shell-modal-kicker">${escape(state.modal.kicker)}</p>` : ''}
              <h2 class="service-shell-modal-title">${escape(state.modal.title || 'Detail')}</h2>
              ${state.modal.description ? `<p class="service-shell-modal-description">${escape(state.modal.description)}</p>` : ''}
            </div>
            <button type="button" class="service-shell-modal-close" aria-label="Zavřít okno" onclick="window.serviceShell.closeModal()">×</button>
          </div>
          <div class="service-shell-modal-body${bodyClass}">
            ${renderModalContent()}
          </div>
          ${renderModalFooter()}
        </div>
      </div>
    `);
  }

  function setModalState(patch = {}) {
    state.modal = {
      ...(state.modal || createEmptyModalState()),
      ...patch,
    };
    renderModal();
  }

  async function reloadModalData() {
    if (!state.modal?.open || typeof state.modal.load !== 'function') return;
    const token = Date.now();
    state.modal.loadToken = token;
    setModalState({ loading: true, error: '' });
    try {
      const data = await state.modal.load(state.modal);
      if (!isModalOpen() || state.modal.loadToken !== token) return;
      setModalState({ loading: false, error: '', data });
    } catch (error) {
      if (!isModalOpen() || state.modal.loadToken !== token) return;
      setModalState({
        loading: false,
        data: null,
        error: error?.message || 'Neznámá chyba',
      });
    }
  }

  function openModal(config = {}) {
    if (!hasFloatingModalSupport()) return false;
    state.modal = {
      ...createEmptyModalState(),
      ...config,
      open: true,
      loading: typeof config.load === 'function',
      error: '',
      data: config.data ?? null,
      actions: config.actions || {},
      context: config.context || {},
    };
    renderModal();
    if (typeof config.load === 'function') {
      reloadModalData();
    }
    return true;
  }

  function normalizeQueuePayload(payload) {
    const queue = payload && typeof payload === 'object' ? { ...payload } : {};
    const alerts = Array.isArray(queue.alerts) ? queue.alerts : [];
    const alertCount = (key) => Number(alerts.find((item) => item?.key === key)?.count || 0);
    return {
      ...queue,
      new_jobs: Number(queue.new_jobs ?? queue.new_orders ?? queue.new_work_orders ?? 0),
      new_orders: Number(queue.new_orders ?? queue.new_jobs ?? queue.new_work_orders ?? 0),
      awaiting_approval: Number(queue.awaiting_approval || 0),
      missing_documents: Number(queue.missing_documents || 0),
      conflicting_data: Number(queue.conflicting_data || 0),
      missing_client_consent: Number(queue.missing_client_consent ?? alertCount('missing_client_consent')),
      suspicious_km: Number(queue.suspicious_km ?? alertCount('suspicious_km')),
      unfinished_jobs: Number(queue.unfinished_jobs ?? alertCount('unfinished_jobs')),
      internal_warnings: Number(queue.internal_warnings || 0),
      alerts,
    };
  }

  async function refreshAfterModalAction() {
    await load(true, true);
  }

  async function runModalAction(actionKey) {
    const action = state.modal?.actions?.[actionKey];
    if (typeof action !== 'function' || state.modal?.saving) return;
    state.modal = {
      ...(state.modal || createEmptyModalState()),
      saving: true,
      error: '',
      actionKey,
    };
    try {
      const result = await action(state.modal);
      if (!isModalOpen()) return;
      if (result && Object.prototype.hasOwnProperty.call(result, 'data')) {
        state.modal.data = result.data;
      }
      if (result?.contextPatch && typeof result.contextPatch === 'object') {
        state.modal.context = {
          ...(state.modal.context || {}),
          ...result.contextPatch,
        };
      }
      if (result?.reloadDetail) {
        await reloadModalData();
      }
      if (result?.refreshParent) {
        await refreshAfterModalAction();
      }
      if (result && Object.prototype.hasOwnProperty.call(result, 'error')) {
        setModalState({
          saving: false,
          actionKey: '',
          error: result.error || '',
        });
        if (result?.message) {
          showToast(result.message, result.messageType || 'warning');
        }
        return;
      }
      if (result?.message) {
        showToast(result.message, result.messageType || 'success');
      }
      if (result?.close === false) {
        setModalState({ saving: false, actionKey: '' });
        return;
      }
      closeModal();
    } catch (error) {
      showToast(error?.message || 'Neznámá chyba', 'error');
      setModalState({
        saving: false,
        actionKey: '',
        error: error?.message || 'Neznámá chyba',
      });
    }
  }

  function parkLegacyNode(target) {
    if (parkedLegacyNodes.has(target.key)) return;
    const node = document.querySelector(target.selector);
    if (!node || !node.parentNode) return;
    const placeholder = document.createComment(`service-shell:${target.key}`);
    node.parentNode.replaceChild(placeholder, node);
    parkedLegacyNodes.set(target.key, { node, placeholder });
  }

  function restoreLegacyNode(key) {
    const parked = parkedLegacyNodes.get(key);
    if (!parked || !parked.placeholder.parentNode) return;
    parked.placeholder.parentNode.replaceChild(parked.node, parked.placeholder);
    parkedLegacyNodes.delete(key);
  }

  function parkLegacyDom() {
    legacyTargets.forEach(parkLegacyNode);
  }

  function restoreLegacyDom() {
    legacyTargets.slice().reverse().forEach((target) => restoreLegacyNode(target.key));
  }

  function applyTheme(theme) {
    state.theme = theme === 'light' ? 'light' : 'dark';
    safeStorageSet(themeKey, state.theme);
    document.body.classList.add('service-shell-app');
    document.body.classList.toggle('service-shell-theme-light', state.theme === 'light');
  }

  function unapplyTheme() {
    document.body.classList.remove('service-shell-app');
    document.body.classList.remove('service-shell-theme-light');
  }

  function stopAutoRefresh() {
    if (state.autoRefreshHandle) {
      window.clearInterval(state.autoRefreshHandle);
      state.autoRefreshHandle = 0;
    }
  }

  function ensureAutoRefresh() {
    stopAutoRefresh();
    state.autoRefreshHandle = window.setInterval(() => {
      if (!state.mounted || !isServiceRole()) return;
      load(true, true).catch((error) => {
        console.warn('[SERVICE_SHELL] auto refresh failed:', error?.message || error);
      });
    }, autoRefreshMs);
  }

  function mapSection(tab) {
    const key = String(tab || '').trim().toLowerCase();
    if (serviceSections.has(key)) return key;
    if (key === 'home') return 'dashboard';
    if (key === 'servicesdirectory' || key === 'clients') return 'clients';
    if (key === 'vehicles') return 'vehicles';
    if (key === 'serviceworkspace' || key === 'workorders') return 'work-orders';
    if (key === 'documents') return 'documents';
    if (key === 'invoices') return 'invoices';
    if (key === 'reservations') return 'reservations';
    if (key === 'reminders') return 'reminders';
    if (key === 'account' || key === 'team') return 'team';
    if (key === 'support') return 'dashboard';
    return '';
  }

  function showAppShellForService() {
    if (typeof window.setPublicPageMode === 'function') {
      window.setPublicPageMode('app');
      return;
    }
    const appShell = document.getElementById('app-shell');
    if (appShell) appShell.style.display = '';
    document.body.classList.remove('route-home-view', 'route-login-view', 'route-register-view');
    document.body.classList.add('route-app-view');
  }

  function mountShellFailsafe(error) {
    console.error('[SERVICE_SHELL] mount failsafe:', error);
    try {
      showAppShellForService();
      const root = document.getElementById(rootId);
      if (root) {
        root.classList.remove('hidden');
        root.innerHTML = `
          <div class="service-shell-root" data-service-shell="root" style="min-height:60vh;padding:24px;background:#111315;color:#f5f7fb;">
            <h1 style="font-size:1.2rem;margin:0 0 12px;">Chyba načtení aplikace</h1>
            <p style="opacity:0.85;margin:0 0 16px;">Servisní rozhraní se nepodařilo spustit. Zkuste obnovit stránku nebo kontaktujte správce.</p>
            <pre style="white-space:pre-wrap;font-size:12px;opacity:0.75;">${escape(String(error?.message || error || ''))}</pre>
            <button type="button" class="btn btn-primary" style="margin-top:16px;" onclick="window.location.reload()">Obnovit stránku</button>
          </div>`;
      }
    } catch (e2) {
      console.error('[SERVICE_SHELL] failsafe render failed:', e2);
    }
  }

  function init(options) {
    console.log('[SERVICE_SHELL] INIT START', options || {});
    return mount(options || {});
  }

  function mount(options = {}) {
    console.log('[SERVICE_SHELL] MOUNT START', {
      isServiceRole: isServiceRole(),
      hasSetPublicPageMode: typeof window.setPublicPageMode === 'function',
    });
    if (!isServiceRole()) {
      console.warn('[SERVICE_SHELL] MOUNT skipped (not service workspace role)');
      return;
    }
    try {
      showAppShellForService();
      const root = getRoot();
      if (!root) {
        throw new Error('Element #serviceAppRoot neexistuje — zkontrolujte šablonu index.html');
      }
      const authSection = document.getElementById('authSection');
      if (authSection) {
        authSection.classList.add('hidden');
        authSection.style.display = 'none';
      }
      parkLegacyDom();
      root.classList.remove('hidden');
      state.mounted = true;
      applyTheme(state.theme);
      render();
      if (!options.skipLoad) {
        load(false, false).catch((error) => {
          console.error('[SERVICE_SHELL] mount load failed:', error);
          if (typeof window.showAlert === 'function') {
            window.showAlert(`Nepodařilo se načíst servisní workspace: ${error.message || 'Neznámá chyba'}`, 'error');
          }
        });
      }
      console.log('[SERVICE_SHELL] MOUNT OK');
    } catch (error) {
      mountShellFailsafe(error);
    }
  }

  function unmount() {
    stopAutoRefresh();
    state.mounted = false;
    const root = getRoot();
    root.classList.add('hidden');
    root.innerHTML = '';
    restoreLegacyDom();
    unapplyTheme();
  }

  async function load(force = false, silent = false) {
    if (!isServiceRole()) {
      if (typeof originalLoadServiceWorkspace === 'function') {
        return originalLoadServiceWorkspace.apply(this, arguments);
      }
      return;
    }

    const now = Date.now();
    if (!force && state.lastLoadedAt && now - state.lastLoadedAt < dataTtlMs && !silent) {
      render();
      ensureAutoRefresh();
      return;
    }

    state.loading = true;
    if (!silent) render();

    try {
      if (typeof window.apiCall !== 'function') {
        throw new Error('window.apiCall není k dispozici — zkontrolujte načtení sdílených skriptů.');
      }

      const requests = {
        summary: window.apiCall('/api/service/dashboard/summary', 'GET'),
        workOrders: window.apiCall('/api/service/work-orders', 'GET'),
        performance: window.apiCall('/api/service/technicians/performance', 'GET'),
        queue: window.apiCall('/api/service/dashboard/queue', 'GET'),
        customers: window.apiCall('/api/v1/services/workspace/customers', 'GET'),
        vehicles: window.apiCall('/api/v1/services/workspace/approved-vehicles', 'GET'),
        reservations: window.apiCall('/api/v1/reservations/service', 'GET'),
        reminders: window.apiCall('/api/v1/services/workspace/reminders?include_completed=true&limit=500', 'GET'),
        documents: window.apiCall('/api/v1/services/workspace/documents?limit=50', 'GET'),
        invoices: window.apiCall('/api/service/invoices', 'GET').catch((err) => {
          console.warn('[SERVICE_SHELL] invoices endpoint:', err?.message || err);
          return { items: [] };
        }),
        profile: window.apiCall('/user/me', 'GET'),
      };

      const keys = Object.keys(requests);
      const results = await Promise.allSettled(keys.map((key) => requests[key]));
      state.errors = [];

      results.forEach((result, index) => {
        const key = keys[index];
        if (result.status !== 'fulfilled') {
          state.errors.push(`${key}: ${result.reason?.message || 'chyba načtení'}`);
          return;
        }
        const payload = result.value;
        if (key === 'summary') state.summary = payload || null;
        if (key === 'workOrders') state.workOrders = Array.isArray(payload?.items) ? payload.items : [];
        if (key === 'performance') state.performance = Array.isArray(payload?.items) ? payload.items : [];
        if (key === 'queue') state.queue = normalizeQueuePayload(payload);
        if (key === 'customers') state.customers = Array.isArray(payload) ? payload : [];
        if (key === 'vehicles') state.vehicles = Array.isArray(payload?.items) ? payload.items : [];
        if (key === 'reservations') state.reservations = Array.isArray(payload) ? payload : [];
        if (key === 'reminders') state.reminders = Array.isArray(payload) ? payload : [];
        if (key === 'documents') state.documents = Array.isArray(payload) ? payload : [];
        if (key === 'invoices') state.invoices = Array.isArray(payload?.items) ? payload.items : [];
        if (key === 'profile') state.profile = payload || {};
      });

      const perf = Array.isArray(state.performance) ? state.performance : [];
      state.technicians = perf
        .map((item) => ({
          technician_id: Number(item?.technician_id || 0),
          name: item?.name || `Technik #${Number(item?.technician_id || 0)}`,
        }))
        .filter((item) => item.technician_id > 0);

      if (!state.technicians.length && window.currentUser?.id) {
        state.technicians = [{
          technician_id: Number(window.currentUser.id),
          name: window.currentUser?.name || window.currentUser?.email || 'Hlavní technik',
        }];
      }

      window.serviceWorkspaceState = window.serviceWorkspaceState || {};
      window.serviceWorkspaceState.customerVehicles = {};

      state.lastLoadedAt = Date.now();
      if (state.errors.length && !silent && typeof window.showAlert === 'function') {
        window.showAlert(`Některé servisní sekce se načetly jen částečně: ${state.errors[0]}`, 'warning');
      }
    } catch (error) {
      console.error('[SERVICE_SHELL] load failed:', error);
      state.errors = state.errors || [];
      state.errors.push(String(error?.message || error || 'load'));
      if (!silent && typeof window.showAlert === 'function') {
        window.showAlert(`Servisní data se nepodařilo načíst: ${error?.message || 'Neznámá chyba'}`, 'error');
      }
    } finally {
      state.loading = false;
      render();
      ensureAutoRefresh();
    }
  }

  function navigate(section, options = {}) {
    const next = mapSection(section) || defaultSection;
    state.accountMenuOpen = false;
    state.mobileNavOpen = false;
    state.activeSection = next;
    if (typeof options.kpiFilter === 'string') {
      state.kpiFilter = options.kpiFilter;
      if (next !== 'dashboard') {
        state.activeSection = 'dashboard';
      }
    }
    render();
    if (typeof window.syncWorkspaceHistoryFromServiceShell === 'function') {
      window.syncWorkspaceHistoryFromServiceShell(next);
    }
    if (options.forceLoad) {
      load(true, false);
    }
  }

  function setTheme(theme) {
    applyTheme(theme);
    render();
  }

  function toggleTheme() {
    setTheme(state.theme === 'light' ? 'dark' : 'light');
  }

  function setSearchTerm(value) {
    state.searchTerm = String(value || '');
    render();
  }

  function setSortBy(value) {
    state.sortBy = String(value || 'due_asc');
    render();
  }

  function setKpiFilter(filter) {
    state.kpiFilter = String(filter || 'all');
    state.activeSection = 'dashboard';
    render();
  }

  function closeAccountMenu() {
    state.accountMenuOpen = false;
    render();
  }

  function toggleAccountMenu() {
    state.accountMenuOpen = !state.accountMenuOpen;
    render();
  }

  function toggleMobileNav() {
    state.mobileNavOpen = !state.mobileNavOpen;
    render();
  }

  function logout() {
    closeAccountMenu();
    if (typeof window.handleLogout === 'function') {
      window.handleLogout();
    } else {
      unmount();
    }
  }

  function openAccountSettings() {
    closeAccountMenu();
    const profile = currentProfile();
    openModal({
      key: 'account-settings',
      entityType: 'account',
      kicker: 'Servisní účet',
      title: 'Nastavení účtu',
      description: 'Základní identita účtu a rychlé akce bez opuštění service shellu.',
      renderContent: () => `
        <div class="service-shell-list">
          <div class="service-shell-list-row"><span class="service-shell-list-title">Název účtu</span><span class="service-shell-list-value">${escape(profile?.name || window.currentUser?.name || 'Servisní účet')}</span></div>
          <div class="service-shell-list-row"><span class="service-shell-list-title">E-mail</span><span class="service-shell-list-value">${escape(profile?.email || window.currentUser?.email || '-')}</span></div>
          <div class="service-shell-list-row"><span class="service-shell-list-title">Role</span><span class="service-shell-list-value">${escape(String(profile?.role || window.currentUser?.role || 'service_account').replace(/_/g, ' '))}</span></div>
          <div class="service-shell-list-row"><span class="service-shell-list-title">Telefon</span><span class="service-shell-list-value">${escape(profile?.phone || '-')}</span></div>
        </div>
      `,
      renderFooter: () => `
        <div class="service-shell-modal-footer">
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.closeModal()">Zavřít</button>
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.closeModal(); window.serviceShell.navigate('team');">Otevřít profil</button>
          <button type="button" class="btn btn-primary" onclick="window.serviceShell.closeModal(); window.serviceShell.logout();">Odhlásit se</button>
        </div>
      `,
    });
  }

  async function searchCustomers(queryOverride = null) {
    const query = String(queryOverride ?? state.customerSearchQuery ?? '').trim();
    state.customerSearchQuery = query;
    state.customerSearchError = '';
    state.customerSearchMeta = null;
    if (query.length < 2) {
      state.customerSearchResults = [];
      return renderServiceToolsModal();
    }
    state.customerSearchLoading = true;
    renderServiceToolsModal();
    try {
      const response = await window.apiCall(`/api/v1/services/workspace/customers/search?query=${encodeURIComponent(query)}`, 'GET');
      state.customerSearchResults = Array.isArray(response?.items) ? response.items : [];
      state.customerSearchMeta = response || null;
    } catch (error) {
      state.customerSearchError = error?.message || 'Vyhledání klienta selhalo.';
      state.customerSearchResults = [];
      state.customerSearchMeta = null;
    } finally {
      state.customerSearchLoading = false;
      renderServiceToolsModal();
    }
  }

  async function linkCustomerById(customerId) {
    try {
      const response = await window.apiCall(`/api/v1/services/workspace/customers/${Number(customerId)}/link`, 'POST');
      showToast(response?.message || 'Klient byl propojen.', 'success');
      await load(true, true);
      if (isModalOpen('service-tools')) {
        await searchCustomers(state.customerSearchQuery);
      } else if (String(state.modal?.entityType || '') === 'customer') {
        await reloadModalData();
      }
    } catch (error) {
      showToast(`Nepodařilo se propojit klienta: ${error?.message || 'Neznámá chyba'}`, 'error');
    }
  }

  async function sendInvitationFromSearch() {
    const query = String(state.customerSearchQuery || '').trim();
    if (!query || !query.includes('@')) {
      showToast('Pozvánku lze odeslat jen při hledání podle e-mailu.', 'warning');
      return;
    }
    try {
      const response = await window.apiCall('/api/v1/services/workspace/invitations/send', 'POST', {
        invite_email: query,
        invite_name: null,
        invite_message: 'Servisní účet vás zve k propojení do Správy vozidel.',
      });
      showToast(response?.message || 'Pozvánka byla připravena.', response?.email_sent ? 'success' : 'info');
      await load(true, true);
      renderServiceToolsModal();
    } catch (error) {
      showToast(`Nepodařilo se odeslat pozvánku: ${error?.message || 'Neznámá chyba'}`, 'error');
    }
  }

  async function searchVehicles(queryOverride = null) {
    const query = String(queryOverride ?? state.vehicleLookupQuery ?? '').trim();
    state.vehicleLookupQuery = query;
    state.vehicleLookupError = '';
    state.vehicleLookupMeta = null;
    if (query.length < 2) {
      state.vehicleLookupResults = [];
      return renderServiceToolsModal();
    }
    state.vehicleLookupLoading = true;
    renderServiceToolsModal();
    try {
      const response = await window.apiCall('/api/v1/services/workspace/vehicle-lookup', 'POST', { query });
      state.vehicleLookupResults = Array.isArray(response?.candidates) ? response.candidates : [];
      state.vehicleLookupMeta = response || null;
    } catch (error) {
      state.vehicleLookupError = error?.message || 'Lookup vozidla selhal.';
      state.vehicleLookupResults = [];
      state.vehicleLookupMeta = null;
    } finally {
      state.vehicleLookupLoading = false;
      renderServiceToolsModal();
    }
  }

  async function requestVehicleAccess(vehicleId, lookupQueryOverride = null) {
    const lookupQuery = String(
      lookupQueryOverride
      || state.modal?.data?.vehicle_plate_masked
      || state.modal?.data?.plate_masked
      || state.vehicleLookupQuery
      || ''
    ).trim();
    if (lookupQuery.length < 2) {
      showToast('Pro žádost o přístup chybí použitelný VIN nebo SPZ identifikátor.', 'error');
      return;
    }
    try {
      const response = await window.apiCall('/api/v1/services/workspace/access-requests', 'POST', {
        vehicle_id: Number(vehicleId),
        lookup_query: lookupQuery,
        note: 'Žádost vytvořená z nového servisního shellu.',
      });
      showToast(response?.message || 'Žádost o přístup byla vytvořena.', 'success');
      if (isModalOpen('service-tools')) {
        await searchVehicles(lookupQuery);
      } else if (String(state.modal?.entityType || '') === 'vehicle' || String(state.modal?.entityType || '') === 'document' || String(state.modal?.entityType || '') === 'reservation' || String(state.modal?.entityType || '') === 'reminder') {
        await reloadModalData();
      }
    } catch (error) {
      showToast(`Nepodařilo se vytvořit žádost o přístup: ${error?.message || 'Neznámá chyba'}`, 'error');
    }
  }

  function openVehicleFromLookup(candidate) {
    const vehicleId = Number(candidate?.vehicle_id || 0);
    if (!vehicleId) {
      showToast('Detail vozidla není k dispozici.', 'warning');
      return;
    }
    return openVehicleDetailModal(vehicleId);
  }

  function openVehicleFromLookupByIndex(index) {
    const candidate = Array.isArray(state.vehicleLookupResults) ? state.vehicleLookupResults[Number(index)] : null;
    return openVehicleFromLookup(candidate);
  }

  function openCreateWorkOrderFromLookup(candidate) {
    const ownerId = Number(candidate?.owner_customer_id || 0);
    const vehicleId = Number(candidate?.vehicle_id || 0);
    if (!ownerId || !vehicleId) {
      showToast('Chybí identita vozidla nebo vlastníka pro založení zakázky.', 'warning');
      return;
    }
    closeFloatingModal();
    openCreateWorkOrderModal({ ownerId, vehicleId });
  }

  function openCreateWorkOrderFromLookupByIndex(index) {
    const candidate = Array.isArray(state.vehicleLookupResults) ? state.vehicleLookupResults[Number(index)] : null;
    return openCreateWorkOrderFromLookup(candidate);
  }

  async function populateCreateVehicleOptions(customerId, preferredVehicleId = null) {
    const customerIdNum = Number(customerId || 0);
    const select = document.getElementById('serviceShellWorkOrderVehicle');
    if (!select) return;
    if (!customerIdNum) {
      select.innerHTML = '<option value="">Nejprve vyberte klienta</option>';
      return;
    }
    window.serviceWorkspaceState = window.serviceWorkspaceState || { customerVehicles: {} };
    if (!Array.isArray(window.serviceWorkspaceState.customerVehicles?.[customerIdNum])) {
      const vehicles = await window.apiCall(`/api/v1/services/workspace/customers/${customerIdNum}/vehicles`, 'GET');
      window.serviceWorkspaceState.customerVehicles[customerIdNum] = Array.isArray(vehicles) ? vehicles : [];
    }
    const vehicles = Array.isArray(window.serviceWorkspaceState.customerVehicles?.[customerIdNum])
      ? window.serviceWorkspaceState.customerVehicles[customerIdNum].filter((item) => Boolean(item?.is_shared))
      : [];
    const preferred = Number(preferredVehicleId || 0);
    select.innerHTML = vehicles.length
      ? vehicles.map((item) => {
          const selected = preferred > 0 && Number(item?.id || 0) === preferred ? 'selected' : '';
          return `<option value="${Number(item.id)}" ${selected}>${escape(item.nickname || item.plate || item.vin || `Vozidlo #${Number(item.id)}`)}</option>`;
        }).join('')
      : '<option value="">Klient nemá schválené vozidlo pro založení zakázky</option>';
  }

  async function populateCustomerVehicleSelect(selectId, customerId, options = {}) {
    const customerIdNum = Number(customerId || 0);
    const select = document.getElementById(selectId);
    if (!select) return;
    const {
      preferredVehicleId = null,
      includeEmpty = true,
      emptyLabel = 'Bez vozidla',
      sharedOnly = false,
      disabledLabel = 'Nejprve vyberte klienta',
    } = options || {};
    if (!customerIdNum) {
      select.innerHTML = includeEmpty
        ? `<option value="">${escape(disabledLabel)}</option>`
        : `<option value="">${escape(disabledLabel)}</option>`;
      return;
    }
    window.serviceWorkspaceState = window.serviceWorkspaceState || { customerVehicles: {} };
    if (!Array.isArray(window.serviceWorkspaceState.customerVehicles?.[customerIdNum])) {
      const vehicles = await window.apiCall(`/api/v1/services/workspace/customers/${customerIdNum}/vehicles`, 'GET');
      window.serviceWorkspaceState.customerVehicles[customerIdNum] = Array.isArray(vehicles) ? vehicles : [];
    }
    const raw = Array.isArray(window.serviceWorkspaceState.customerVehicles?.[customerIdNum])
      ? window.serviceWorkspaceState.customerVehicles[customerIdNum]
      : [];
    const vehicles = sharedOnly ? raw.filter((item) => Boolean(item?.is_shared)) : raw;
    const preferred = Number(preferredVehicleId || 0);
    const optionsHtml = vehicles.map((item) => {
      const selected = preferred > 0 && Number(item?.id || 0) === preferred ? 'selected' : '';
      return `<option value="${Number(item.id)}" ${selected}>${escape(item.nickname || item.plate || item.vin || `Vozidlo #${Number(item.id)}`)}</option>`;
    }).join('');
    if (!vehicles.length) {
      select.innerHTML = `<option value="">${escape(includeEmpty ? emptyLabel : 'Bez dostupných vozidel')}</option>`;
      return;
    }
    select.innerHTML = includeEmpty
      ? `<option value="">${escape(emptyLabel)}</option>${optionsHtml}`
      : optionsHtml;
  }

  function renderServiceToolsModal() {
    if (!hasFloatingModalSupport()) return;
    const customerMeta = state.customerSearchMeta || {};
    const vehicleMeta = state.vehicleLookupMeta || {};
    const customerRows = state.customerSearchLoading
      ? '<div class="service-shell-empty">Vyhledávám klienty…</div>'
      : state.customerSearchResults.length
        ? state.customerSearchResults.map((item) => `
          <div class="service-shell-list-row">
            <div>
              <p class="service-shell-list-title">${escape(item?.name || '-')}</p>
              <p class="service-shell-list-note">${escape(item?.email_masked || '-')} • ${escape(item?.phone_masked || '-')} • ${escape(item?.status_label || '-')}</p>
              ${item?.blocking_reason ? `<p class="service-shell-list-note">${escape(item.blocking_reason)}</p>` : ''}
            </div>
            <div class="service-shell-modal-actions">
              ${item?.already_linked
                ? `<button type="button" class="btn btn-secondary" onclick="window.serviceShell.openCustomerDetailModal(${Number(item.customer_id || 0)})">Otevřít</button>`
                : `<button type="button" class="btn btn-primary" onclick="window.serviceShell.linkCustomerById(${Number(item.customer_id || 0)})">Propojit</button>`}
            </div>
          </div>
        `).join('')
        : '<div class="service-shell-empty">Zatím žádné výsledky.</div>';

    const vehicleRows = state.vehicleLookupLoading
      ? '<div class="service-shell-empty">Vyhledávám vozidla…</div>'
      : state.vehicleLookupResults.length
        ? state.vehicleLookupResults.map((item, index) => `
          <div class="service-shell-list-row">
            <div>
              <p class="service-shell-list-title">${escape(item?.nickname || [item?.brand, item?.model].filter(Boolean).join(' ') || (item?.status === 'conflict' ? 'Konfliktní identifikace' : 'Vozidlo'))}</p>
              <p class="service-shell-list-note">${escape(item?.plate_masked || '-')} • ${escape(item?.vin_masked || '-')} • ${escape(accessStatusLabel(item?.status || '-'))}</p>
              ${item?.blocking_reason ? `<p class="service-shell-list-note">${escape(item.blocking_reason)}</p>` : ''}
              ${Array.isArray(item?.conflicting_candidates) ? `
                <div class="service-shell-list">
                  ${item.conflicting_candidates.map((conflict) => `
                    <div class="service-shell-list-row">
                      <div>
                        <p class="service-shell-list-title">${escape(conflict?.nickname || [conflict?.brand, conflict?.model].filter(Boolean).join(' ') || 'Vozidlo')}</p>
                        <p class="service-shell-list-note">${escape(conflict?.plate_masked || '-')} • ${escape(conflict?.vin_masked || '-')} • ${escape(accessStatusLabel(conflict?.status || '-'))}</p>
                      </div>
                      <div class="service-shell-modal-actions">
                        <button type="button" class="btn btn-secondary" onclick="window.serviceShell.openVehicleDetailModal(${Number(conflict?.vehicle_id || 0)})">Otevřít detail</button>
                      </div>
                    </div>
                  `).join('')}
                </div>
              ` : ''}
            </div>
            <div class="service-shell-modal-actions">
              ${item?.can_open_detail ? `<button type="button" class="btn btn-secondary" onclick="window.serviceShell.openVehicleFromLookupByIndex(${index})">Detail</button>` : ''}
              ${item?.can_create_work_order ? `<button type="button" class="btn btn-secondary" onclick="window.serviceShell.openCreateWorkOrderFromLookupByIndex(${index})">Nová zakázka</button>` : ''}
              ${item?.can_request_access ? `<button type="button" class="btn btn-primary" onclick="window.serviceShell.requestVehicleAccess(${Number(item.vehicle_id || 0)})">Požádat o přístup</button>` : ''}
            </div>
          </div>
        `).join('')
        : '<div class="service-shell-empty">Zatím žádné výsledky.</div>';

    openModal({
      key: 'service-tools',
      entityType: 'toolbox',
      kicker: 'Servisní nástroje',
      title: 'Najít nebo vytvořit',
      description: 'Vyhledávání klientů a vozidel, propojení účtů a bezpečný vstup do dalších servisních akcí.',
      size: 'wide',
      bodyClass: 'service-shell-modal-body--tools',
      renderContent: () => `
        <div class="service-shell-tools-grid">
          <section class="service-shell-side-card">
            <h3>Najít existujícího klienta</h3>
            <p>Hledání podle e-mailu, telefonu nebo jména. Nejdřív hledat, až potom zvát nebo vytvářet vazbu.</p>
            <div class="service-shell-table-tools">
              <input class="service-shell-search" type="search" placeholder="email, telefon nebo jméno" value="${escape(state.customerSearchQuery)}" oninput="window.serviceShell.setCustomerSearchQuery(this.value)">
              <button type="button" class="btn btn-primary" onclick="window.serviceShell.searchCustomers()">Hledat klienta</button>
            </div>
            ${customerMeta?.has_multiple_matches ? `<div class="service-shell-inline-alert"><span>Nalezeno více podobných klientů. Otevřete detail správného záznamu nebo proveďte přímé propojení.</span></div>` : ''}
            ${state.customerSearchError ? `<div class="service-shell-inline-error">${escape(state.customerSearchError)}</div>` : ''}
            <div class="service-shell-list">${customerRows}</div>
            ${String(state.customerSearchQuery || '').includes('@') ? '<div class="service-shell-modal-footer service-shell-modal-footer--inline"><button type="button" class="btn btn-secondary" onclick="window.serviceShell.sendInvitationFromSearch()">Klient nenalezen? Odeslat pozvánku</button></div>' : ''}
          </section>
          <section class="service-shell-side-card">
            <h3>Najít vozidlo podle VIN / SPZ</h3>
            <p>Bezpečný lookup nad existující databází. Pokud vozidlo existuje, nabídne se detail, přístup nebo nová zakázka.</p>
            <div class="service-shell-table-tools">
              <input class="service-shell-search" type="search" placeholder="VIN nebo SPZ" value="${escape(state.vehicleLookupQuery)}" oninput="window.serviceShell.setVehicleLookupQuery(this.value)">
              <button type="button" class="btn btn-primary" onclick="window.serviceShell.searchVehicles()">Hledat vozidlo</button>
            </div>
            ${vehicleMeta?.has_conflict ? `<div class="service-shell-inline-error">VIN a SPZ ukazují na rozdílné záznamy. Ověřte vstup a pokračujte přes správný detail.</div>` : ''}
            ${state.vehicleLookupError ? `<div class="service-shell-inline-error">${escape(state.vehicleLookupError)}</div>` : ''}
            <div class="service-shell-list">${vehicleRows}</div>
            <div class="service-shell-modal-footer service-shell-modal-footer--inline">
              <button type="button" class="btn btn-secondary" onclick="window.serviceShell.openAddVehicleModal(null, { vin: window.serviceShell.state.vehicleLookupQuery, plate: window.serviceShell.state.vehicleLookupQuery })">Vozidlo nenalezeno? Založit nové</button>
            </div>
          </section>
        </div>
      `,
      renderFooter: () => `
        <div class="service-shell-modal-footer">
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.closeModal()">Zavřít</button>
        </div>
      `,
    });
  }

  function openServiceToolsModal() {
    state.accountMenuOpen = false;
    renderServiceToolsModal();
  }

  function setCustomerSearchQuery(value) {
    state.customerSearchQuery = String(value || '');
  }

  function setVehicleLookupQuery(value) {
    state.vehicleLookupQuery = String(value || '');
  }

  async function openCreateWorkOrderModal(prefill = {}) {
    if (!hasFloatingModalSupport()) {
      if (typeof originalOpenServiceDashboardCreateModal === 'function') {
        return originalOpenServiceDashboardCreateModal();
      }
      return;
    }
    const customers = Array.isArray(state.customers) ? state.customers : [];
    const technicians = Array.isArray(state.technicians) && state.technicians.length
      ? state.technicians
      : [{ technician_id: Number(window.currentUser?.id || 0), name: window.currentUser?.name || window.currentUser?.email || 'Hlavní technik' }];
    const preferredOwnerId = Number(prefill.ownerId || customers[0]?.customer_id || 0);
    const ownerOptions = customers.length
      ? customers.map((item) => `<option value="${Number(item.customer_id)}" ${Number(item.customer_id) === preferredOwnerId ? 'selected' : ''}>${escape(item.name || item.email || `Klient #${Number(item.customer_id)}`)}</option>`).join('')
      : '<option value="">Nejsou dostupní propojení klienti</option>';
    openModal({
      key: 'work-order-create',
      entityType: 'work_order',
      kicker: 'Servisní zakázka',
      title: 'Nová zakázka',
      description: 'Zakázku lze založit jen nad existujícím propojeným klientem a schváleným vozidlem.',
      actions: {
        save: async () => {
          const ownerId = Number(document.getElementById('serviceShellWorkOrderOwner')?.value || 0);
          const vehicleId = Number(document.getElementById('serviceShellWorkOrderVehicle')?.value || 0);
          const technicianId = Number(document.getElementById('serviceShellWorkOrderTechnician')?.value || 0) || null;
          const title = String(document.getElementById('serviceShellWorkOrderTitle')?.value || '').trim();
          const dueDate = String(document.getElementById('serviceShellWorkOrderDueDate')?.value || '').trim() || null;
          const status = String(document.getElementById('serviceShellWorkOrderStatus')?.value || 'awaiting_client_approval').trim();
          const description = String(document.getElementById('serviceShellWorkOrderDescription')?.value || '').trim() || null;
          if (!ownerId || !vehicleId || !title) {
            throw new Error('Vyberte klienta, vozidlo a vyplňte název zakázky.');
          }
          try {
            await window.apiCall('/api/service/work-orders', 'POST', {
              owner_id: ownerId,
              vehicle_id: vehicleId,
              technician_id: technicianId,
              title,
              description,
              due_date: dueDate,
              status,
              source_type: 'manual',
            });
          } catch (error) {
            const detail = error?.payload?.detail;
            if (error?.status === 409 && detail?.code === 'duplicate_work_order') {
              return {
                close: false,
                error: detail.message || error.message || 'Duplicitní rozpracovaná zakázka.',
                message: detail.message || error.message || 'Duplicitní rozpracovaná zakázka.',
                messageType: 'warning',
                contextPatch: {
                  duplicateWorkOrderId: Number(detail.existing_work_order_id || 0),
                  duplicateWorkOrderTitle: detail.existing_work_order_title || '',
                },
              };
            }
            throw error;
          }
          return {
            close: true,
            refreshParent: true,
            message: 'Zakázka byla vytvořena.',
          };
        },
      },
      renderContent: () => `
        <div class="service-shell-modal-toolbar">
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.openServiceToolsModal()">Najít klienta nebo vozidlo</button>
        </div>
        <form class="service-dashboard-modal-form" onsubmit="event.preventDefault(); window.serviceShell.submitCreateWorkOrderModal();">
          <div class="service-dashboard-modal-grid cols-2">
            <div class="form-group">
              <label for="serviceShellWorkOrderOwner">Zákazník</label>
              <select id="serviceShellWorkOrderOwner" onchange="window.serviceShell.populateCreateVehicleOptions(this.value)">
                ${ownerOptions}
              </select>
            </div>
            <div class="form-group">
              <label for="serviceShellWorkOrderVehicle">Vozidlo</label>
              <select id="serviceShellWorkOrderVehicle"><option value="">Načítám vozidla…</option></select>
            </div>
          </div>
          <div class="service-dashboard-modal-grid cols-2">
            <div class="form-group">
              <label for="serviceShellWorkOrderTitle">Název zakázky</label>
              <input type="text" id="serviceShellWorkOrderTitle" placeholder="Např. diagnostika motoru">
            </div>
            <div class="form-group">
              <label for="serviceShellWorkOrderDueDate">Termín</label>
              <input type="date" id="serviceShellWorkOrderDueDate">
            </div>
          </div>
          <div class="service-dashboard-modal-grid cols-2">
            <div class="form-group">
              <label for="serviceShellWorkOrderTechnician">Technik</label>
              <select id="serviceShellWorkOrderTechnician">
                ${technicians.map((item) => `<option value="${Number(item.technician_id)}">${escape(item.name || `Technik #${Number(item.technician_id)}`)}</option>`).join('')}
              </select>
            </div>
            <div class="form-group">
              <label for="serviceShellWorkOrderStatus">Stav</label>
              <select id="serviceShellWorkOrderStatus">
                <option value="awaiting_client_approval">Čeká na schválení</option>
                <option value="approved">Schváleno</option>
                <option value="in_progress">Rozpracováno</option>
                <option value="issue">Problém</option>
              </select>
            </div>
          </div>
          <div class="form-group">
            <label for="serviceShellWorkOrderDescription">Popis</label>
            <textarea id="serviceShellWorkOrderDescription" rows="4" placeholder="Rozsah prací, diagnóza, poznámky pro tým nebo klienta"></textarea>
          </div>
        </form>
      `,
      renderFooter: (modal) => `
        <div class="service-shell-modal-footer">
          ${Number(modal?.context?.duplicateWorkOrderId || 0) > 0
            ? `<button type="button" class="btn btn-secondary" onclick="window.serviceShell.closeModal(); window.serviceShell.openWorkOrderDetailModal(${Number(modal.context.duplicateWorkOrderId)})">Otevřít existující zakázku</button>`
            : ''}
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.closeModal()">Zrušit</button>
          <button type="button" class="btn btn-primary" onclick="window.serviceShell.submitCreateWorkOrderModal()">${modal.saving ? 'Ukládám…' : 'Uložit zakázku'}</button>
        </div>
      `,
    });
    await populateCreateVehicleOptions(preferredOwnerId, Number(prefill.vehicleId || 0));
  }

  async function submitCreateWorkOrderModal() {
    if (isModalOpen('work-order-create')) {
      return runModalAction('save');
    }
  }

  async function openWorkOrderDetailModal(workOrderId) {
    const id = Number(workOrderId || 0);
    if (!id || !hasFloatingModalSupport()) return;
    const technicians = Array.isArray(state.technicians) && state.technicians.length
      ? state.technicians
      : [{ technician_id: Number(window.currentUser?.id || 0), name: window.currentUser?.name || window.currentUser?.email || 'Hlavní technik' }];
    openModal({
      key: `work-order-detail-${id}`,
      entityType: 'work_order',
      kicker: `Zakázka #${id}`,
      title: 'Detail zakázky',
      description: 'Úpravy detailu, auditní stopa a navázané servisní workflow v jednom modal lifecycle.',
      load: async () => window.apiCall(`/api/service/work-orders/${id}`, 'GET'),
      actions: {
        save: async () => {
          const status = String(document.getElementById('serviceShellDetailStatus')?.value || 'awaiting_client_approval').trim();
          const dueDate = String(document.getElementById('serviceShellDetailDueDate')?.value || '').trim() || null;
          const technicianId = Number(document.getElementById('serviceShellDetailTechnicianId')?.value || 0) || null;
          const description = String(document.getElementById('serviceShellDetailDescription')?.value || '').trim() || null;
          await window.apiCall(`/api/service/work-orders/${id}`, 'PUT', {
            status,
            due_date: dueDate,
            technician_id: technicianId,
            description,
          });
          return {
            close: true,
            refreshParent: true,
            message: 'Zakázka byla aktualizována.',
          };
        },
      },
      renderContent: (modal) => {
        const detail = modal.data || {};
        const quote = detail?.quote_summary || null;
        return `
          <div class="service-shell-modal-summary">
            <span>${escape(detail?.customer_name || '-')}</span>
            <span>${escape(detail?.vehicle_label || '-')}</span>
          </div>
          <form class="service-dashboard-modal-form" onsubmit="event.preventDefault(); window.serviceShell.submitWorkOrderDetailUpdate(${id});">
            <div class="service-dashboard-modal-grid cols-2">
              <div class="form-group">
                <label for="serviceShellDetailStatus">Stav</label>
                <select id="serviceShellDetailStatus">
                  <option value="awaiting_client_approval" ${detail?.status === 'awaiting_client_approval' ? 'selected' : ''}>Čeká na schválení</option>
                  <option value="approved" ${detail?.status === 'approved' ? 'selected' : ''}>Schváleno</option>
                  <option value="in_progress" ${detail?.status === 'in_progress' ? 'selected' : ''}>Rozpracováno</option>
                  <option value="issue" ${detail?.status === 'issue' ? 'selected' : ''}>Problém</option>
                  <option value="completed" ${detail?.status === 'completed' ? 'selected' : ''}>Dokončeno</option>
                </select>
              </div>
              <div class="form-group">
                <label for="serviceShellDetailDueDate">Termín</label>
                <input type="date" id="serviceShellDetailDueDate" value="${escape(String(detail?.due_date || '').slice(0, 10))}">
              </div>
            </div>
            <div class="service-dashboard-modal-grid cols-2">
              <div class="form-group">
                <label for="serviceShellDetailTechnicianId">Technik</label>
                <select id="serviceShellDetailTechnicianId">
                  ${technicians.map((item) => `<option value="${Number(item.technician_id)}" ${Number(item.technician_id) === Number(detail?.technician_id || 0) ? 'selected' : ''}>${escape(item.name || `Technik #${Number(item.technician_id)}`)}</option>`).join('')}
                </select>
              </div>
              <div class="form-group">
                <label>Zdroj</label>
                <input type="text" value="${escape(detail?.source_label || detail?.source || '-')}" disabled>
              </div>
            </div>
            <div class="service-dashboard-modal-grid cols-2">
              <div class="form-group">
                <label>Zákazník</label>
                <input type="text" value="${escape(detail?.customer_name || '-')}" disabled>
              </div>
              <div class="form-group">
                <label>VIN / SPZ</label>
                <input type="text" value="${escape(detail?.vehicle_vin || '-')}${detail?.vehicle_spz ? ` / ${escape(detail.vehicle_spz)}` : ''}" disabled>
              </div>
            </div>
            <div class="form-group">
              <label for="serviceShellDetailDescription">Popis</label>
              <textarea id="serviceShellDetailDescription" rows="4">${escape(detail?.description || '')}</textarea>
            </div>
            ${quote ? `
              <section class="service-shell-side-card">
                <h3>Nabídka</h3>
                <div class="service-shell-list">
                  <div class="service-shell-list-row"><span class="service-shell-list-title">Stav</span><span class="service-shell-list-value">${escape(quote?.status_label || quote?.status || '-')}</span></div>
                  <div class="service-shell-list-row"><span class="service-shell-list-title">Cena</span><span class="service-shell-list-value">${escape(quote?.total_price != null ? `${Number(quote.total_price).toLocaleString('cs-CZ')} Kč` : '-')}</span></div>
                  <div class="service-shell-list-row"><span class="service-shell-list-title">Schváleno</span><span class="service-shell-list-value">${escape(quote?.approved_at ? formatDateTime(quote.approved_at) : '-')}</span></div>
                  <div class="service-shell-list-row"><span class="service-shell-list-title">Odmítnuto</span><span class="service-shell-list-value">${escape(quote?.rejected_at ? formatDateTime(quote.rejected_at) : '-')}</span></div>
                  <div class="service-shell-list-row"><span class="service-shell-list-title">Veřejný odkaz</span><span class="service-shell-list-value">${escape(quote?.public_quote_url || '-')}</span></div>
                </div>
                ${quote?.consistency_note ? `<p class="service-shell-list-note">${escape(quote.consistency_note)}</p>` : ''}
                <div class="service-shell-modal-actions">
                  <button type="button" class="btn btn-secondary" onclick="window.serviceShell.openQuoteModal(${Number(quote?.quote_id || 0)})">Otevřít nabídku</button>
                  <button type="button" class="btn btn-secondary" onclick="window.serviceShell.copyQuotePublicLinkByUrl(${JSON.stringify(String(quote?.public_quote_url || ''))})">Kopírovat odkaz</button>
                </div>
              </section>
            ` : ''}
            <div class="form-group">
              <label>Audit</label>
              <div class="service-dashboard-empty service-shell-modal-audit">
                ${(Array.isArray(detail?.audit_log) && detail.audit_log.length)
                  ? detail.audit_log.map((item) => `${escape(formatDate(item.created_at))} • ${escape(item.action || 'update')}`).join('<br>')
                  : 'Bez auditních záznamů.'}
              </div>
            </div>
          </form>
        `;
      },
      renderFooter: (modal) => `
        <div class="service-shell-modal-footer">
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.closeModal()">Zavřít</button>
          <button type="button" class="btn btn-primary" onclick="window.serviceShell.submitWorkOrderDetailUpdate(${id})">${modal.saving ? 'Ukládám…' : 'Uložit změny'}</button>
        </div>
      `,
    });
  }

  async function submitWorkOrderDetailUpdate(workOrderId) {
    if (isModalOpen(`work-order-detail-${Number(workOrderId || 0)}`)) {
      return runModalAction('save');
    }
  }

  async function openAddVehicleModal(customerId = null, defaults = {}) {
    if (!hasFloatingModalSupport()) return;
    const customers = Array.isArray(state.customers) ? state.customers : [];
    const preferredCustomerId = Number(customerId || customers[0]?.customer_id || 0);
    openModal({
      key: 'vehicle-create',
      entityType: 'vehicle',
      kicker: 'Vozidlo klienta',
      title: 'Založit nové vozidlo',
      description: 'Před uložením se vozidlo ověří proti existující databázi podle VIN nebo SPZ.',
      actions: {
        save: async () => {
          const customerIdValue = Number(document.getElementById('serviceShellAddVehicleCustomer')?.value || 0);
          const nickname = String(document.getElementById('serviceShellAddVehicleNickname')?.value || '').trim();
          const plate = String(document.getElementById('serviceShellAddVehiclePlate')?.value || '').trim();
          const vin = String(document.getElementById('serviceShellAddVehicleVin')?.value || '').trim().toUpperCase();
          const brand = String(document.getElementById('serviceShellAddVehicleBrand')?.value || '').trim() || null;
          const model = String(document.getElementById('serviceShellAddVehicleModel')?.value || '').trim() || null;
          const yearRaw = Number(document.getElementById('serviceShellAddVehicleYear')?.value || 0);
          const engine = String(document.getElementById('serviceShellAddVehicleEngine')?.value || '').trim() || null;
          const stk = String(document.getElementById('serviceShellAddVehicleStk')?.value || '').trim();
          const notes = String(document.getElementById('serviceShellAddVehicleNotes')?.value || '').trim() || null;
          const duplicateState = document.getElementById('serviceShellAddVehicleDuplicateState');
          if (!customerIdValue || !nickname || !plate || !stk) {
            throw new Error('Vyberte klienta a vyplňte název, SPZ a platnost STK.');
          }
          const lookupQuery = vin || plate;
          if (lookupQuery) {
            try {
              const lookup = await window.apiCall('/api/v1/services/workspace/vehicle-lookup', 'POST', { query: lookupQuery });
              const candidates = Array.isArray(lookup?.candidates) ? lookup.candidates : [];
              if (candidates.length) {
                if (duplicateState) {
                  duplicateState.innerHTML = 'Vozidlo už v databázi existuje. Použijte existující záznam nebo požádejte o přístup, nové vozidlo se nevytvoří.';
                }
                throw new Error('Vozidlo už v databázi existuje. Nový záznam nebyl vytvořen.');
              }
            } catch (error) {
              if (String(error?.message || '').includes('Nový záznam nebyl vytvořen')) {
                throw error;
              }
              console.warn('[SERVICE_SHELL] vehicle lookup before create failed:', error);
            }
          }
          const response = await window.apiCall(`/api/v1/services/workspace/customers/${customerIdValue}/vehicles`, 'POST', {
            nickname,
            plate,
            vin: vin || null,
            brand,
            model,
            year: Number.isFinite(yearRaw) && yearRaw > 0 ? yearRaw : null,
            engine,
            notes,
            stk_valid_until: stk,
            tyres_info: null,
          });
          return {
            close: true,
            refreshParent: true,
            message: response?.message || 'Vozidlo bylo přidáno.',
          };
        },
      },
      renderContent: () => `
        <form class="service-dashboard-modal-form" onsubmit="event.preventDefault(); window.serviceShell.submitAddVehicleModal();">
          <div class="service-dashboard-modal-grid cols-2">
            <div class="form-group">
              <label for="serviceShellAddVehicleCustomer">Klient</label>
              <select id="serviceShellAddVehicleCustomer">
                ${customers.map((item) => `<option value="${Number(item.customer_id)}" ${Number(item.customer_id) === preferredCustomerId ? 'selected' : ''}>${escape(item.name || item.email || `Klient #${Number(item.customer_id)}`)}</option>`).join('')}
              </select>
            </div>
            <div class="form-group">
              <label for="serviceShellAddVehicleNickname">Název vozidla</label>
              <input type="text" id="serviceShellAddVehicleNickname" placeholder="Např. Octavia RS">
            </div>
          </div>
          <div class="service-dashboard-modal-grid cols-2">
            <div class="form-group">
              <label for="serviceShellAddVehiclePlate">SPZ</label>
              <input type="text" id="serviceShellAddVehiclePlate" value="${escape(defaults?.plate || '')}">
            </div>
            <div class="form-group">
              <label for="serviceShellAddVehicleVin">VIN</label>
              <input type="text" id="serviceShellAddVehicleVin" value="${escape(defaults?.vin || '')}">
            </div>
          </div>
          <div class="service-dashboard-modal-grid cols-2">
            <div class="form-group">
              <label for="serviceShellAddVehicleBrand">Značka</label>
              <input type="text" id="serviceShellAddVehicleBrand">
            </div>
            <div class="form-group">
              <label for="serviceShellAddVehicleModel">Model</label>
              <input type="text" id="serviceShellAddVehicleModel">
            </div>
          </div>
          <div class="service-dashboard-modal-grid cols-2">
            <div class="form-group">
              <label for="serviceShellAddVehicleYear">Rok</label>
              <input type="number" id="serviceShellAddVehicleYear" min="1900" max="2100">
            </div>
            <div class="form-group">
              <label for="serviceShellAddVehicleStk">Platnost STK</label>
              <input type="date" id="serviceShellAddVehicleStk">
            </div>
          </div>
          <div class="form-group">
            <label for="serviceShellAddVehicleEngine">Motor</label>
            <input type="text" id="serviceShellAddVehicleEngine">
          </div>
          <div class="form-group">
            <label for="serviceShellAddVehicleNotes">Poznámka</label>
            <textarea id="serviceShellAddVehicleNotes" rows="3"></textarea>
          </div>
          <div id="serviceShellAddVehicleDuplicateState" class="service-shell-empty"></div>
        </form>
      `,
      renderFooter: (modal) => `
        <div class="service-shell-modal-footer">
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.closeModal()">Zrušit</button>
          <button type="button" class="btn btn-primary" onclick="window.serviceShell.submitAddVehicleModal()">${modal.saving ? 'Ukládám…' : 'Uložit vozidlo'}</button>
        </div>
      `,
    });
  }

  async function submitAddVehicleModal() {
    if (isModalOpen('vehicle-create')) {
      return runModalAction('save');
    }
  }

  function parseJsonList(value) {
    if (!value) return [];
    try {
      const parsed = typeof value === 'string' ? JSON.parse(value) : value;
      return Array.isArray(parsed) ? parsed : [];
    } catch (error) {
      return [];
    }
  }

  function serviceRecordStatusLabel(status) {
    const normalized = String(status || 'draft').toLowerCase();
    if (normalized === 'submitted') return 'Odesláno';
    if (normalized === 'approved') return 'Schváleno';
    if (normalized === 'locked') return 'Uzamčeno';
    return 'Koncept';
  }

  function serviceRecordCards(records, vehicleId) {
    const items = Array.isArray(records) ? records : [];
    if (!items.length) {
      return '<div class="service-shell-empty">Pro toto vozidlo zatím nejsou servisní záznamy.</div>';
    }
    return items.map((record) => `
      <article ${clickableAttrs(`window.serviceShell.openServiceRecordModal(${Number(vehicleId || 0)}, ${Number(record?.id || 0)})`)}>
        <div class="service-shell-record-card">
        <div class="service-shell-record-card-head">
          <div>
            <strong>${escape(record?.category || 'Servisní záznam')}</strong>
            <p class="service-shell-list-note">${escape(record?.performed_at ? formatDateTime(record.performed_at) : 'Bez data')}</p>
          </div>
          <span class="service-shell-badge ${String(record?.record_status || '').toLowerCase() === 'approved' || String(record?.record_status || '').toLowerCase() === 'locked' ? 'completed' : 'awaiting'}">${escape(serviceRecordStatusLabel(record?.record_status))}</span>
        </div>
        <p class="service-shell-list-title">${escape(record?.description || 'Bez popisu')}</p>
        <div class="service-shell-record-card-meta">
          <span>${escape(record?.mileage != null ? `${Number(record.mileage).toLocaleString('cs-CZ')} km` : 'Bez km')}</span>
          <span>${escape(record?.total_price != null ? `${Number(record.total_price).toLocaleString('cs-CZ')} Kč` : record?.price != null ? `${Number(record.price).toLocaleString('cs-CZ')} Kč` : 'Bez ceny')}</span>
          ${record?.quote_id ? `<span>Nabídka #${escape(String(record.quote_id))}</span>` : ''}
        </div>
        </div>
      </article>
    `).join('');
  }

  function quoteStatusLabel(status) {
    const normalized = String(status || 'draft').toLowerCase();
    if (normalized === 'sent') return 'Odesláno';
    if (normalized === 'approved') return 'Schváleno';
    if (normalized === 'rejected') return 'Zamítnuto';
    return 'Koncept';
  }

  function getQuoteListPrefs() {
    return state.quoteListPrefs || { status: 'all', sort: 'created_at', order: 'desc' };
  }

  function setVehicleQuoteListPrefs(partial = {}) {
    state.quoteListPrefs = {
      ...getQuoteListPrefs(),
      ...(partial && typeof partial === 'object' ? partial : {}),
    };
    if (
      state.modal?.open
      && state.modal.entityType === 'vehicle'
      && String(state.modal.key || '').startsWith('vehicle-detail-')
    ) {
      try {
        renderModal();
      } catch (err) {
        console.error('[SERVICE_SHELL] quote list prefs renderModal failed:', err);
      }
    }
  }

  function formatQuotePriceCs(value) {
    try {
      if (value == null || value === '') return 'Bez ceny';
      const n = Number(value);
      if (!Number.isFinite(n)) return 'Bez ceny';
      return `${n.toLocaleString('cs-CZ')} Kč`;
    } catch (err) {
      console.warn('[SERVICE_SHELL] formatQuotePriceCs:', err);
      return 'Bez ceny';
    }
  }

  function quoteStatusSortRank(status) {
    const normalized = String(status || 'draft').toLowerCase();
    if (normalized === 'draft') return 0;
    if (normalized === 'sent') return 1;
    if (normalized === 'approved') return 2;
    if (normalized === 'rejected') return 3;
    return 9;
  }

  function quoteBadgeClass(status) {
    const normalized = String(status || 'draft').toLowerCase();
    if (normalized === 'approved') return 'completed';
    if (normalized === 'rejected') return 'issue';
    if (normalized === 'sent') return 'in_progress';
    return 'awaiting';
  }

  function filterSortVehicleQuotes(items, prefs) {
    const safePrefs = prefs && typeof prefs === 'object' ? prefs : getQuoteListPrefs();
    const raw = Array.isArray(items) ? items.slice() : [];
    const statusKey = String(safePrefs.status || 'all').toLowerCase();
    const filtered = statusKey === 'all'
      ? raw
      : raw.filter((quote) => String(quote?.status || '').toLowerCase() === statusKey);
    const sortKey = String(safePrefs.sort || 'created_at').toLowerCase();
    const orderKey = String(safePrefs.order || 'desc').toLowerCase();
    const direction = orderKey === 'asc' ? 1 : -1;
    filtered.sort((left, right) => {
      if (sortKey === 'total_price') {
        const pl = Number(left?.total_price ?? 0);
        const pr = Number(right?.total_price ?? 0);
        if (pl !== pr) return (pl - pr) * direction;
      } else if (sortKey === 'status') {
        const rl = quoteStatusSortRank(left?.status);
        const rr = quoteStatusSortRank(right?.status);
        if (rl !== rr) return (rl - rr) * direction;
      } else {
        const tl = new Date(left?.created_at || 0).getTime();
        const tr = new Date(right?.created_at || 0).getTime();
        if (tl !== tr) return (tl - tr) * direction;
      }
      const idl = Number(left?.quote_id || left?.id || 0);
      const idr = Number(right?.quote_id || right?.id || 0);
      return (idl - idr) * direction;
    });
    return filtered;
  }

  function vehicleQuotesToolbar() {
    const prefs = getQuoteListPrefs();
    const sel = (value, current) => (String(value) === String(current) ? ' selected' : '');
    return `
      <div class="service-shell-quote-list-toolbar" role="group" aria-label="Filtrování a řazení nabídek">
        <div class="service-shell-quote-list-toolbar-row">
          <label class="service-shell-quote-filter-label" for="serviceShellQuoteFilterStatus">Stav</label>
          <select id="serviceShellQuoteFilterStatus" class="service-shell-quote-filter" onchange="window.serviceShell.setVehicleQuoteListPrefs({ status: this.value })">
            <option value="all"${sel('all', prefs.status)}>Všechny stavy</option>
            <option value="draft"${sel('draft', prefs.status)}>Koncept</option>
            <option value="sent"${sel('sent', prefs.status)}>Odesláno</option>
            <option value="approved"${sel('approved', prefs.status)}>Schváleno</option>
            <option value="rejected"${sel('rejected', prefs.status)}>Zamítnuto</option>
          </select>
        </div>
        <div class="service-shell-quote-list-toolbar-row">
          <label class="service-shell-quote-filter-label" for="serviceShellQuoteSortField">Řazení pole</label>
          <select id="serviceShellQuoteSortField" class="service-shell-quote-filter" onchange="window.serviceShell.setVehicleQuoteListPrefs({ sort: this.value })">
            <option value="created_at"${sel('created_at', prefs.sort)}>Data vytvoření</option>
            <option value="total_price"${sel('total_price', prefs.sort)}>Ceny</option>
            <option value="status"${sel('status', prefs.sort)}>Stavu</option>
          </select>
        </div>
        <div class="service-shell-quote-list-toolbar-row">
          <label class="service-shell-quote-filter-label" for="serviceShellQuoteSortOrder">Pořadí</label>
          <select id="serviceShellQuoteSortOrder" class="service-shell-quote-filter" onchange="window.serviceShell.setVehicleQuoteListPrefs({ order: this.value })">
            <option value="desc"${sel('desc', prefs.order)}>Nejnovější / vyšší první</option>
            <option value="asc"${sel('asc', prefs.order)}>Nejstarší / nižší první</option>
          </select>
        </div>
      </div>
    `;
  }

  function vehicleQuoteCardHtml(quote) {
    const qid = Number(quote?.quote_id || quote?.id || 0);
    const pub = String(quote?.public_quote_url || '');
    const badgeClass = quoteBadgeClass(quote?.status);
    const statusText = escape(quote?.status_label || quoteStatusLabel(quote?.status));
    const priceText = escape(formatQuotePriceCs(quote?.total_price));
    const dateText = escape(quote?.created_at ? formatDateTime(quote.created_at) : 'Bez data');
    return `
      <article class="service-shell-quote-card" data-quote-id="${qid}" data-quote-status="${escape(String(quote?.status || ''))}">
        <div class="service-shell-quote-card-top">
          <div class="service-shell-quote-card-heading">
            <strong class="service-shell-quote-card-id">Nabídka #${escape(String(qid))}</strong>
            <span class="service-shell-badge service-shell-badge--quote ${badgeClass}">${statusText}</span>
          </div>
          <div class="service-shell-quote-card-stats">
            <div class="service-shell-quote-stat">
              <span class="service-shell-quote-stat-label">Vytvořeno</span>
              <span class="service-shell-quote-stat-value">${dateText}</span>
            </div>
            <div class="service-shell-quote-stat">
              <span class="service-shell-quote-stat-label">Cena</span>
              <span class="service-shell-quote-stat-value">${priceText}</span>
            </div>
          </div>
        </div>
        <div class="service-shell-quote-card-links">
          ${quote?.service_record_id ? `<span>Záznam #${escape(String(quote.service_record_id))}</span>` : '<span>Bez záznamu</span>'}
          <span class="service-shell-quote-card-links-sep">·</span>
          ${quote?.work_order_id ? `<span>Zakázka #${escape(String(quote.work_order_id))}</span>` : '<span>Bez zakázky</span>'}
        </div>
        ${quote?.approved_at ? `<p class="service-shell-list-note">Schváleno: ${escape(formatDateTime(quote.approved_at))}</p>` : ''}
        ${quote?.rejected_at ? `<p class="service-shell-list-note">Odmítnuto: ${escape(formatDateTime(quote.rejected_at))}</p>` : ''}
        ${quote?.consistency_note ? `<p class="service-shell-list-note">${escape(quote.consistency_note)}</p>` : ''}
        <div class="service-shell-quote-actions">
          <button type="button" class="btn btn-secondary service-shell-quote-action" onclick="window.serviceShell.openQuoteModal(${qid})">Otevřít</button>
          <button type="button" class="btn btn-secondary service-shell-quote-action" onclick="window.serviceShell.shareQuotePdf(${qid})">PDF</button>
          <button type="button" class="btn btn-secondary service-shell-quote-action" onclick="window.serviceShell.openQuotePublicLink(${qid})">Veřejný odkaz</button>
          <button type="button" class="btn btn-secondary service-shell-quote-action" onclick="window.serviceShell.copyQuotePublicLinkByUrl(${JSON.stringify(pub)})">Kopírovat odkaz</button>
        </div>
        <details class="service-shell-quote-debug">
          <summary>Provozní kontrola (servis)</summary>
          <dl class="service-shell-quote-debug-dl">
            <div><dt>quote_id</dt><dd><code>${escape(String(qid))}</code></dd></div>
            <div><dt>quote_status</dt><dd><code>${escape(String(quote?.status || '-'))}</code></dd></div>
            <div><dt>public_quote_url</dt><dd><code class="service-shell-quote-debug-url">${escape(pub || '-')}</code></dd></div>
            <div><dt>work_order_id</dt><dd><code>${escape(quote?.work_order_id != null ? String(quote.work_order_id) : '-')}</code></dd></div>
          </dl>
        </details>
      </article>
    `;
  }

  function vehicleQuotesSection(detail) {
    try {
      const items = Array.isArray(detail?.service_quotes) ? detail.service_quotes : [];
      if (!items.length) {
        return `
        <div class="service-shell-empty">
          Pro toto vozidlo zatím nejsou cenové nabídky.
          <div class="service-shell-modal-actions">
            <button type="button" class="btn btn-primary" onclick="window.serviceShell.openFirstRecordForQuote()">Vytvořit nabídku</button>
          </div>
        </div>
      `;
      }
      const prefs = getQuoteListPrefs();
      const filtered = filterSortVehicleQuotes(items, prefs);
      const meta = `<p class="service-shell-quote-list-count">Zobrazeno <strong>${filtered.length}</strong> z <strong>${items.length}</strong></p>`;
      const list = filtered.length
        ? filtered.map((quote) => {
          try {
            return vehicleQuoteCardHtml(quote);
          } catch (rowErr) {
            console.error('[SERVICE_SHELL] vehicleQuoteCardHtml failed:', rowErr, quote);
            return '<div class="service-shell-empty">Jednu nabídku se nepodařilo zobrazit (viz konzole).</div>';
          }
        }).join('')
        : '<div class="service-shell-empty">Žádná nabídka pro zvolený filtr. Upravte stav výše.</div>';
      return `
      ${vehicleQuotesToolbar()}
      ${meta}
      <div class="service-shell-quote-card-list">
        ${list}
      </div>
    `;
    } catch (err) {
      console.error('[SERVICE_SHELL] vehicleQuotesSection failed:', err);
      return '<div class="service-shell-empty">Sekci nabídek se nepodařilo vykreslit. Zkuste znovu načíst detail vozidla.</div>';
    }
  }

  async function fileToBase64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const result = String(reader.result || '');
        const base64 = result.includes(',') ? result.split(',').pop() : result;
        resolve(base64 || '');
      };
      reader.onerror = () => reject(reader.error || new Error('Soubor se nepodařilo načíst.'));
      reader.readAsDataURL(file);
    });
  }

  function appendWorkItemDraft() {
    const edit = state.modal?.data?.recordEditState;
    if (edit && !edit.editable) return;
    const target = document.getElementById('serviceShellRecordDescription');
    if (!target) return;
    const prefix = target.value && !/\n$/.test(target.value) ? '\n' : '';
    target.value = `${target.value || ''}${prefix}- `;
    target.focus();
  }

  async function handleServiceRecordPhotoSelection(input) {
    const edit = state.modal?.data?.recordEditState;
    if (edit && !edit.editable) return;
    const files = Array.from(input?.files || []);
    const context = state.modal?.context || {};
    const vehicleId = Number(context.vehicleId || 0);
    if (!vehicleId || !files.length) return;
    const uploaded = [];
    for (const file of files) {
      const fileContentBase64 = await fileToBase64(file);
      const payload = await window.apiCall(`/api/v1/vehicles/${vehicleId}/records/attachments/upload`, 'POST', {
        file_name: file.name || 'photo.jpg',
        file_mime_type: file.type || 'image/jpeg',
        file_content_base64: fileContentBase64,
      });
      uploaded.push({
        kind: 'user_photo',
        file_name: payload?.file_name || file.name || 'photo.jpg',
        mime_type: payload?.mime_type || file.type || 'image/jpeg',
        file_size: payload?.file_size || file.size || null,
        storage_key: payload?.storage_key || null,
        download_url: payload?.download_url || null,
      });
    }
    context.photoAttachments = [...(Array.isArray(context.photoAttachments) ? context.photoAttachments : []), ...uploaded];
    state.modal.context = context;
    renderModal();
  }

  function triggerServiceRecordPhotoPicker() {
    const edit = state.modal?.data?.recordEditState;
    if (edit && !edit.editable) return;
    const input = document.getElementById('serviceShellRecordPhotos');
    if (input) input.click();
  }

  function openServiceRecordModal(vehicleId, recordId = 0) {
    const resolvedVehicleId = Number(vehicleId || state.activeVehicle?.vehicleId || 0);
    const resolvedRecordId = Number(recordId || 0);
    if (!resolvedVehicleId) return;
    openModal({
      key: resolvedRecordId ? `service-record-${resolvedRecordId}` : `service-record-create-${resolvedVehicleId}`,
      entityType: 'service-record',
      kicker: resolvedRecordId ? `Záznam #${resolvedRecordId}` : `Vozidlo #${resolvedVehicleId}`,
      title: resolvedRecordId ? 'Servisní záznam' : 'Nový servisní záznam',
      description: 'Mobilní full-screen workflow pro bezpečný zápis servisní historie.',
      size: 'wide',
      bodyClass: 'service-shell-modal-body--record',
      context: {
        vehicleId: resolvedVehicleId,
        recordId: resolvedRecordId || null,
        photoAttachments: [],
      },
      actions: {
        save: async () => {
          await submitServiceRecordModal('save');
          return { close: false };
        },
        finish: async () => {
          await submitServiceRecordModal('finish');
          return { close: false };
        },
      },
      load: async () => {
        const [vehicleDetail, recordDetail] = await Promise.all([
          window.apiCall(`/api/v1/services/workspace/vehicles/${resolvedVehicleId}/detail`, 'GET'),
          resolvedRecordId ? window.apiCall(`/api/v1/vehicles/${resolvedVehicleId}/records/${resolvedRecordId}`, 'GET') : Promise.resolve(null),
        ]);
        setActiveVehicle(vehicleDetail);
        render();
        const attachments = parseJsonList(recordDetail?.attachments);
        const recordEditState = recordDetail ? computeServiceRecordShellEditState(recordDetail) : { editable: true, reason: null };
        state.modal.context = {
          ...(state.modal.context || {}),
          vehicleId: resolvedVehicleId,
          recordId: resolvedRecordId || null,
          photoAttachments: attachments,
          recordEditState,
        };
        return {
          vehicle: vehicleDetail,
          record: recordDetail,
          recordEditState,
        };
      },
      renderContent: (modal) => {
        const detail = modal.data?.record || {};
        const vehicle = modal.data?.vehicle || {};
        const edit = modal.data?.recordEditState || { editable: true, reason: null };
        const ro = !edit.editable;
        const attachments = Array.isArray(modal.context?.photoAttachments) ? modal.context.photoAttachments : [];
        return `
          <section class="service-shell-mobile-form-top">
            <div class="service-shell-mobile-kicker">Vozidlo</div>
            <strong>${escape(vehicle?.nickname || [vehicle?.brand, vehicle?.model].filter(Boolean).join(' ') || vehicle?.plate || 'Vozidlo')}</strong>
            <span class="service-shell-muted">${escape(vehicle?.vin || vehicle?.vin_masked || '-')} · ${escape(vehicle?.plate || vehicle?.plate_masked || '-')}</span>
          </section>
          ${ro ? `<div class="service-shell-inline-error" style="margin-bottom:12px;">${escape(edit.reason || 'Jen pro čtení.')}</div>` : ''}
          <form class="service-dashboard-modal-form service-shell-record-form" onsubmit="event.preventDefault(); window.serviceShell.submitServiceRecordModal('save');">
            <div class="form-group">
              <label for="serviceShellRecordCategory">Typ úkonu</label>
              <select id="serviceShellRecordCategory" ${ro ? 'disabled' : ''}>
                <option value="OPRAVA" ${String(detail?.category || '').toUpperCase() === 'OPRAVA' ? 'selected' : ''}>Oprava</option>
                <option value="OLEJ" ${String(detail?.category || '').toUpperCase() === 'OLEJ' ? 'selected' : ''}>Výměna oleje</option>
                <option value="PNEU" ${String(detail?.category || '').toUpperCase() === 'PNEU' ? 'selected' : ''}>Pneuservis</option>
                <option value="DIAGNOSTIKA" ${String(detail?.category || '').toUpperCase() === 'DIAGNOSTIKA' ? 'selected' : ''}>Diagnostika</option>
                <option value="STK" ${String(detail?.category || '').toUpperCase() === 'STK' ? 'selected' : ''}>STK / ME</option>
                <option value="JINE" ${!detail?.category || String(detail?.category || '').toUpperCase() === 'JINE' ? 'selected' : ''}>Ostatní</option>
              </select>
            </div>
            <div class="form-group">
              <label for="serviceShellRecordStatus">Stav záznamu</label>
              <select id="serviceShellRecordStatus" ${ro ? 'disabled' : ''}>
                <option value="draft" ${String(detail?.record_status || 'draft').toLowerCase() === 'draft' ? 'selected' : ''}>Koncept</option>
                <option value="submitted" ${String(detail?.record_status || '').toLowerCase() === 'submitted' ? 'selected' : ''}>Odesláno</option>
                <option value="approved" ${String(detail?.record_status || '').toLowerCase() === 'approved' ? 'selected' : ''}>Schváleno</option>
                <option value="locked" ${String(detail?.record_status || '').toLowerCase() === 'locked' ? 'selected' : ''}>Uzamčeno</option>
              </select>
            </div>
            <div class="form-group">
              <label for="serviceShellRecordPerformedAt">Datum a čas</label>
              <input type="datetime-local" id="serviceShellRecordPerformedAt" ${ro ? 'readonly' : ''} value="${escape(toDateTimeInputValue(detail?.performed_at || new Date().toISOString()))}">
            </div>
            <div class="form-group">
              <label for="serviceShellRecordMileage">Nájezd</label>
              <input type="number" id="serviceShellRecordMileage" inputmode="numeric" min="0" ${ro ? 'readonly' : ''} value="${escape(detail?.mileage != null ? String(detail.mileage) : '')}">
            </div>
            <div class="form-group">
              <label for="serviceShellRecordDescription">Popis</label>
              <textarea id="serviceShellRecordDescription" rows="5" ${ro ? 'readonly' : ''}>${escape(detail?.description || '')}</textarea>
            </div>
            <div class="form-group">
              <label for="serviceShellRecordNotesCustomer">Poznámka pro zákazníka</label>
              <textarea id="serviceShellRecordNotesCustomer" rows="4" ${ro ? 'readonly' : ''}>${escape(detail?.notes_customer_visible || '')}</textarea>
            </div>
            <div class="form-group">
              <label for="serviceShellRecordRecommendedText">Doporučený další servis</label>
              <textarea id="serviceShellRecordRecommendedText" rows="3" ${ro ? 'readonly' : ''}>${escape(detail?.recommended_next_service_text || '')}</textarea>
            </div>
            <div class="form-group">
              <label for="serviceShellRecordRecommendedDate">Doporučený termín</label>
              <input type="date" id="serviceShellRecordRecommendedDate" ${ro ? 'readonly' : ''} value="${escape(String(detail?.recommended_next_service_date || '').slice(0, 10))}">
            </div>
            <div class="form-group">
              <label for="serviceShellRecordPrice">Cena</label>
              <input type="number" id="serviceShellRecordPrice" inputmode="decimal" min="0" step="0.01" ${ro ? 'readonly' : ''} value="${escape(detail?.total_price != null ? String(detail.total_price) : detail?.price != null ? String(detail.price) : '')}">
            </div>
            <div class="form-group">
              <label for="serviceShellRecordInternalNote">Interní poznámka</label>
              <textarea id="serviceShellRecordInternalNote" rows="3" ${ro ? 'readonly' : ''}>${escape(detail?.note || '')}</textarea>
            </div>
            <input type="file" id="serviceShellRecordPhotos" accept="image/*" capture="environment" multiple style="display:none" ${ro ? 'disabled' : ''} onchange="window.serviceShell.handleServiceRecordPhotoSelection(this)">
            <section class="service-shell-side-card">
              <h3>Fotodokumentace</h3>
              <div class="service-shell-list">
                ${attachments.length ? attachments.map((item) => `
                  <div class="service-shell-list-row">
                    <div>
                      <p class="service-shell-list-title">${escape(item?.file_name || 'Fotografie')}</p>
                      <p class="service-shell-list-note">${escape(item?.mime_type || 'image')}</p>
                    </div>
                    <span class="service-shell-list-value">${escape(item?.file_size ? `${Math.round(Number(item.file_size) / 1024)} kB` : 'Uloženo')}</span>
                  </div>
                `).join('') : '<div class="service-shell-empty">Zatím bez nahraných fotek.</div>'}
              </div>
            </section>
          </form>
        `;
      },
      renderFooter: (modal) => {
        const edit = modal?.data?.recordEditState || { editable: true, reason: null };
        const canEdit = edit.editable;
        return `
        <div class="service-shell-modal-footer ${isMobileViewport() ? 'service-shell-mobile-action-bar' : ''}">
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.closeModal()">Zpět</button>
          ${modal?.context?.recordId && canEdit ? `<button type="button" class="btn btn-secondary" onclick="window.serviceShell.createQuoteFromRecord(${Number(modal.context.recordId)})">Vytvořit nabídku</button>` : ''}
          ${canEdit ? `<button type="button" class="btn btn-secondary" onclick="window.serviceShell.appendWorkItemDraft()">Přidat položku</button>` : ''}
          ${canEdit ? `<button type="button" class="btn btn-secondary" onclick="window.serviceShell.triggerServiceRecordPhotoPicker()">Přidat fotku</button>` : ''}
          ${canEdit ? `<button type="button" class="btn btn-primary" onclick="window.serviceShell.runModalAction('save')">${modal.saving ? 'Ukládám…' : 'Uložit'}</button>` : ''}
          ${canEdit ? `<button type="button" class="btn btn-primary" onclick="window.serviceShell.runModalAction('finish')">${modal.saving ? 'Dokončuji…' : 'Dokončit'}</button>` : ''}
        </div>
      `;
      },
    });
  }

  async function submitServiceRecordModal(mode = 'save') {
    const edit = state.modal?.data?.recordEditState;
    if (edit && !edit.editable) {
      throw new Error(edit.reason || 'Záznam není možné upravovat.');
    }
    const context = state.modal?.context || {};
    const vehicleId = Number(context.vehicleId || 0);
    const recordId = Number(context.recordId || 0);
    if (!vehicleId) return;
    const payload = {
      category: String(document.getElementById('serviceShellRecordCategory')?.value || 'JINE').trim(),
      record_status: mode === 'finish'
        ? 'approved'
        : String(document.getElementById('serviceShellRecordStatus')?.value || 'draft').trim(),
      performed_at: fromDateTimeInputValue(document.getElementById('serviceShellRecordPerformedAt')?.value),
      mileage: Number(document.getElementById('serviceShellRecordMileage')?.value || 0) || 0,
      description: String(document.getElementById('serviceShellRecordDescription')?.value || '').trim(),
      recommended_next_service_text: String(document.getElementById('serviceShellRecordRecommendedText')?.value || '').trim() || null,
      recommended_next_service_date: String(document.getElementById('serviceShellRecordRecommendedDate')?.value || '').trim() || null,
      notes_customer_visible: String(document.getElementById('serviceShellRecordNotesCustomer')?.value || '').trim() || null,
      note: String(document.getElementById('serviceShellRecordInternalNote')?.value || '').trim() || null,
      total_price: Number(document.getElementById('serviceShellRecordPrice')?.value || 0) || 0,
      price: Number(document.getElementById('serviceShellRecordPrice')?.value || 0) || 0,
      attachments: JSON.stringify(Array.isArray(context.photoAttachments) ? context.photoAttachments : []),
    };
    if (!payload.description) {
      throw new Error('Vyplňte popis servisního úkonu.');
    }
    if (recordId > 0) {
      await window.apiCall(`/api/v1/vehicles/${vehicleId}/records/${recordId}`, 'PUT', payload);
    } else {
      await window.apiCall(`/api/v1/vehicles/${vehicleId}/records`, 'POST', payload);
    }
    state.activeSection = 'vehicles';
    await load(true, true);
    closeModal();
    if (typeof window.showAlert === 'function') {
      window.showAlert(mode === 'finish' ? 'Servisní záznam byl dokončen.' : 'Servisní záznam byl uložen.', 'success');
    }
  }

  function quoteItemsFromDom() {
    const rows = Array.from(document.querySelectorAll('[data-quote-item-row]'));
    return rows.map((row) => {
      const name = String(row.querySelector('[data-quote-item-name]')?.value || '').trim() || 'Položka';
      const quantity = Number(row.querySelector('[data-quote-item-qty]')?.value || 0) || 0;
      const unitPrice = Number(row.querySelector('[data-quote-item-price]')?.value || 0) || 0;
      return {
        name,
        quantity,
        unit_price: unitPrice,
        total_price: Number((quantity * unitPrice).toFixed(2)),
      };
    });
  }

  function appendQuoteItemRow() {
    const container = document.getElementById('serviceShellQuoteItems');
    if (!container) return;
    const row = document.createElement('div');
    row.className = 'service-shell-quote-item-row';
    row.setAttribute('data-quote-item-row', '1');
    row.innerHTML = `
      <input data-quote-item-name type="text" placeholder="Položka">
      <input data-quote-item-qty type="number" inputmode="decimal" min="0" step="0.1" value="1">
      <input data-quote-item-price type="number" inputmode="decimal" min="0" step="0.01" value="0">
    `;
    container.appendChild(row);
  }

  function invoiceLinesFromDom() {
    const rows = Array.from(document.querySelectorAll('[data-invoice-line-row]'));
    return rows
      .map((row) => {
        const description = String(row.querySelector('[data-invoice-line-description]')?.value || '').trim();
        const quantity = Number(row.querySelector('[data-invoice-line-quantity]')?.value || 0) || 0;
        const unit = String(row.querySelector('[data-invoice-line-unit]')?.value || 'ks').trim() || 'ks';
        const unitPrice = Number(row.querySelector('[data-invoice-line-unit-price]')?.value || 0) || 0;
        const taxRate = Number(row.querySelector('[data-invoice-line-tax-rate]')?.value || 0) || 0;
        return { description, quantity, unit, unit_price: unitPrice, tax_rate: taxRate };
      })
      .filter((item) => item.description && item.quantity > 0);
  }

  function appendInvoiceLineRow(values = {}) {
    const container = document.getElementById('serviceShellInvoiceLines');
    if (!container) return;
    const row = document.createElement('div');
    row.className = 'service-shell-quote-item-row service-shell-invoice-line-row';
    row.setAttribute('data-invoice-line-row', '1');
    row.innerHTML = `
      <input data-invoice-line-description type="text" placeholder="Položka" value="${escape(values?.description || '')}">
      <input data-invoice-line-quantity type="number" inputmode="decimal" min="0.01" step="0.1" value="${escape(String(values?.quantity ?? 1))}">
      <input data-invoice-line-unit type="text" placeholder="ks" value="${escape(values?.unit || 'ks')}">
      <input data-invoice-line-unit-price type="number" inputmode="decimal" min="0" step="0.01" value="${escape(String(values?.unit_price ?? 0))}">
      <input data-invoice-line-tax-rate type="number" inputmode="decimal" min="0" max="100" step="0.1" value="${escape(String(values?.tax_rate ?? 21))}">
    `;
    container.appendChild(row);
  }

  function buildQuoteSmsText(detail) {
    const vehicle = String(detail?.vehicle_label || 'vozidlo').trim();
    const price = detail?.total_price != null ? `${Number(detail.total_price).toLocaleString('cs-CZ')} Kč` : 'neuvedeno';
    const url = String(detail?.public_quote_url || '').trim();
    return `Dobrý den, posíláme nabídku pro ${vehicle}. Cena: ${price}. Odkaz: ${url}`;
  }

  async function copyQuotePublicLinkByUrl(url) {
    const normalized = String(url || '').trim();
    if (!normalized) return;
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(normalized);
      if (typeof window.showAlert === 'function') window.showAlert('Veřejný odkaz na nabídku byl zkopírován.', 'success');
      return;
    }
    window.prompt('Zkopíruj veřejný odkaz na nabídku:', normalized);
  }

  async function copyQuotePublicLink(quoteId) {
    const resolvedQuoteId = Number(quoteId || state.modal?.context?.quoteId || 0);
    const detail = resolvedQuoteId && Number(state.modal?.context?.quoteId || 0) === resolvedQuoteId
      ? (state.modal?.data || {})
      : await window.apiCall(`/api/service/quotes/${resolvedQuoteId}`, 'GET');
    await copyQuotePublicLinkByUrl(detail?.public_quote_url);
  }

  async function openQuotePublicLink(quoteId) {
    const resolvedQuoteId = Number(quoteId || state.modal?.context?.quoteId || 0);
    const detail = resolvedQuoteId && Number(state.modal?.context?.quoteId || 0) === resolvedQuoteId
      ? (state.modal?.data || {})
      : await window.apiCall(`/api/service/quotes/${resolvedQuoteId}`, 'GET');
    const url = String(detail?.public_quote_url || '').trim();
    if (url) window.open(url, '_blank', 'noopener');
  }

  async function emailQuotePublicLink(quoteId) {
    const resolvedQuoteId = Number(quoteId || state.modal?.context?.quoteId || 0);
    const detail = resolvedQuoteId && Number(state.modal?.context?.quoteId || 0) === resolvedQuoteId
      ? (state.modal?.data || {})
      : await window.apiCall(`/api/service/quotes/${resolvedQuoteId}`, 'GET');
    const url = String(detail?.public_quote_url || '').trim();
    const email = String(detail?.customer_email || '').trim();
    if (!url) return;
    const subject = encodeURIComponent(`Cenová nabídka pro ${String(detail?.vehicle_label || 'vozidlo')}`);
    const body = encodeURIComponent(`Dobrý den,\n\nposíláme cenovou nabídku: ${url}\n\nS pozdravem\n${String(detail?.service_name || 'Servis')}`);
    window.open(`mailto:${encodeURIComponent(email)}?subject=${subject}&body=${body}`, '_self');
  }

  async function shareQuoteSmsTemplate(quoteId) {
    const resolvedQuoteId = Number(quoteId || state.modal?.context?.quoteId || 0);
    const detail = resolvedQuoteId && Number(state.modal?.context?.quoteId || 0) === resolvedQuoteId
      ? (state.modal?.data || {})
      : await window.apiCall(`/api/service/quotes/${resolvedQuoteId}`, 'GET');
    const text = buildQuoteSmsText(detail);
    const phone = String(detail?.customer_phone || '').trim();
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      if (typeof window.showAlert === 'function') window.showAlert('SMS šablona k nabídce byla zkopírována.', 'success');
    }
    window.open(`sms:${encodeURIComponent(phone)}?body=${encodeURIComponent(text)}`, '_self');
  }

  async function openFirstRecordForQuote() {
    const records = Array.isArray(state.modal?.data?.service_records) ? state.modal.data.service_records : [];
    const firstRecordId = Number(records[0]?.id || 0);
    if (firstRecordId) {
      await createQuoteFromRecord(firstRecordId);
      return;
    }
    const vehicleId = Number(state.modal?.context?.entityId || state.activeVehicle?.vehicleId || 0);
    if (vehicleId) {
      openServiceRecordModal(vehicleId);
    }
  }

  function openQuoteModal(quoteId) {
    const resolvedQuoteId = Number(quoteId || 0);
    if (!resolvedQuoteId) return;
    openModal({
      key: `service-quote-${resolvedQuoteId}`,
      entityType: 'service-quote',
      kicker: `Nabídka #${resolvedQuoteId}`,
      title: 'Cenová nabídka',
      description: 'Zákaznický výstup navázaný na servisní záznam a zakázku.',
      size: 'wide',
      context: { quoteId: resolvedQuoteId },
      actions: {
        save: async () => {
          const items = quoteItemsFromDom();
          const totalPrice = Number(document.getElementById('serviceShellQuoteTotal')?.value || 0) || 0;
          const laborHours = Number(document.getElementById('serviceShellQuoteLaborHours')?.value || 0) || 0;
          const laborRate = Number(document.getElementById('serviceShellQuoteLaborRate')?.value || 0) || 0;
          const status = String(document.getElementById('serviceShellQuoteStatus')?.value || 'draft').trim();
          const updated = await window.apiCall(`/api/service/quotes/${resolvedQuoteId}`, 'PUT', {
            items,
            labor_hours: laborHours,
            labor_rate: laborRate,
            total_price: totalPrice,
            status,
          });
          return { data: updated, close: false };
        },
      },
      load: async () => window.apiCall(`/api/service/quotes/${resolvedQuoteId}`, 'GET'),
      renderContent: (modal) => {
        const detail = modal.data || {};
        const items = Array.isArray(detail?.items) ? detail.items : [];
        return `
          <section class="service-shell-mobile-form-top">
            <div class="service-shell-mobile-kicker">Výstup pro zákazníka</div>
            <strong>${escape(detail?.vehicle_label || 'Vozidlo')}</strong>
            <span class="service-shell-muted">${escape(detail?.service_name || 'Servis')} · ${escape(detail?.status_label || detail?.status || 'Koncept')}</span>
          </section>
          <section class="service-shell-side-card">
            <div class="service-shell-list">
              <div class="service-shell-list-row"><span class="service-shell-list-title">Veřejný odkaz</span><span class="service-shell-list-value">${escape(detail?.public_quote_url || 'Ještě není připraven')}</span></div>
              <div class="service-shell-list-row"><span class="service-shell-list-title">Schváleno</span><span class="service-shell-list-value">${escape(detail?.approved_at ? formatDateTime(detail.approved_at) : '-')}</span></div>
              <div class="service-shell-list-row"><span class="service-shell-list-title">Odmítnuto</span><span class="service-shell-list-value">${escape(detail?.rejected_at ? formatDateTime(detail.rejected_at) : '-')}</span></div>
            </div>
          </section>
          <div class="form-group">
            <label for="serviceShellQuoteStatus">Stav nabídky</label>
            <select id="serviceShellQuoteStatus">
              <option value="draft" ${detail?.status === 'draft' ? 'selected' : ''}>Koncept</option>
              <option value="sent" ${detail?.status === 'sent' ? 'selected' : ''}>Odesláno</option>
              <option value="approved" ${detail?.status === 'approved' ? 'selected' : ''}>Schváleno</option>
              <option value="rejected" ${detail?.status === 'rejected' ? 'selected' : ''}>Zamítnuto</option>
            </select>
          </div>
          <div id="serviceShellQuoteItems" class="service-shell-quote-items">
            ${items.map((item) => `
              <div class="service-shell-quote-item-row" data-quote-item-row="1">
                <input data-quote-item-name type="text" value="${escape(item?.name || '')}" placeholder="Položka">
                <input data-quote-item-qty type="number" inputmode="decimal" min="0" step="0.1" value="${escape(String(item?.quantity ?? 1))}">
                <input data-quote-item-price type="number" inputmode="decimal" min="0" step="0.01" value="${escape(String(item?.unit_price ?? 0))}">
              </div>
            `).join('') || `
              <div class="service-shell-quote-item-row" data-quote-item-row="1">
                <input data-quote-item-name type="text" value="Servisní práce" placeholder="Položka">
                <input data-quote-item-qty type="number" inputmode="decimal" min="0" step="0.1" value="1">
                <input data-quote-item-price type="number" inputmode="decimal" min="0" step="0.01" value="${escape(String(detail?.total_price ?? 0))}">
              </div>
            `}
          </div>
          <div class="form-group">
            <label for="serviceShellQuoteLaborHours">Hodiny práce</label>
            <input id="serviceShellQuoteLaborHours" type="number" inputmode="decimal" min="0" step="0.1" value="${escape(String(detail?.labor_hours ?? 0))}">
          </div>
          <div class="form-group">
            <label for="serviceShellQuoteLaborRate">Sazba práce</label>
            <input id="serviceShellQuoteLaborRate" type="number" inputmode="decimal" min="0" step="0.01" value="${escape(String(detail?.labor_rate ?? 0))}">
          </div>
          <div class="form-group">
            <label for="serviceShellQuoteTotal">Celková cena</label>
            <input id="serviceShellQuoteTotal" type="number" inputmode="decimal" min="0" step="0.01" value="${escape(String(detail?.total_price ?? 0))}">
          </div>
        `;
      },
      renderFooter: (modal) => `
        <div class="service-shell-modal-footer ${isMobileViewport() ? 'service-shell-mobile-action-bar' : ''}">
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.closeModal()">Zpět</button>
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.appendQuoteItemRow()">Přidat položku</button>
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.shareQuotePdf(${resolvedQuoteId})">Sdílet / stáhnout PDF</button>
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.copyQuotePublicLink(${resolvedQuoteId})">Kopírovat veřejný odkaz</button>
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.openQuotePublicLink(${resolvedQuoteId})">Otevřít veřejný odkaz</button>
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.emailQuotePublicLink(${resolvedQuoteId})">Odeslat e-mailem</button>
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.shareQuoteSmsTemplate(${resolvedQuoteId})">SMS šablona</button>
          <button type="button" class="btn btn-primary" onclick="window.serviceShell.runModalAction('save')">${modal.saving ? 'Ukládám…' : 'Uložit nabídku'}</button>
        </div>
      `,
    });
  }

  async function createQuoteFromRecord(recordId) {
    const resolvedRecordId = Number(recordId || 0);
    if (!resolvedRecordId) return;
    const quote = await window.apiCall(`/api/service/quotes/from-record/${resolvedRecordId}`, 'POST');
    openQuoteModal(Number(quote?.id || 0));
  }

  function shareQuotePdf(quoteId) {
    const resolvedQuoteId = Number(quoteId || state.modal?.context?.quoteId || 0);
    if (!resolvedQuoteId) return;
    const path = `/api/service/quotes/${resolvedQuoteId}/pdf`;
    if (typeof window.openAuthenticatedPdf === 'function') {
      window.openAuthenticatedPdf(path).catch((err) => {
        const msg = err?.message || 'PDF se nepodařilo otevřít.';
        if (typeof window.showAlert === 'function') window.showAlert(msg, 'error');
      });
      return;
    }
    const url = `${window.location.origin}${path}`;
    if (navigator.share) {
      navigator.share({ title: 'Cenová nabídka', url }).catch(() => {
        window.open(url, '_blank', 'noopener');
      });
      return;
    }
    window.open(url, '_blank', 'noopener');
  }

  async function openCreateReminderModal(prefill = {}) {
    const customers = Array.isArray(state.customers) ? state.customers : [];
    const preferredCustomerId = Number(prefill.customerId || customers[0]?.customer_id || 0);
    openModal({
      key: 'reminder-create',
      entityType: 'reminder',
      kicker: 'Připomínka',
      title: 'Nová připomínka',
      description: 'Follow-up nad klientem a volitelně konkrétním vozidlem v tenant-safe servisním workflow.',
      actions: {
        save: async () => {
          const customerId = Number(document.getElementById('serviceShellCreateReminderCustomer')?.value || 0);
          const vehicleId = Number(document.getElementById('serviceShellCreateReminderVehicle')?.value || 0) || null;
          const type = String(document.getElementById('serviceShellCreateReminderType')?.value || 'SERVIS').trim();
          const text = String(document.getElementById('serviceShellCreateReminderText')?.value || '').trim();
          const dueDate = String(document.getElementById('serviceShellCreateReminderDueDate')?.value || '').trim() || null;
          const notifyAt = fromDateTimeInputValue(document.getElementById('serviceShellCreateReminderNotifyAt')?.value);
          const notificationMethod = String(document.getElementById('serviceShellCreateReminderMethod')?.value || '').trim() || null;
          if (!customerId || !text) {
            throw new Error('Vyberte klienta a vyplňte text připomínky.');
          }
          await window.apiCall('/api/v1/services/workspace/reminders', 'POST', {
            customer_id: customerId,
            vehicle_id: vehicleId,
            type,
            text,
            due_date: dueDate,
            notify_at: notifyAt,
            notification_method: notificationMethod,
          });
          return { close: true, refreshParent: true, message: 'Připomínka byla vytvořena.' };
        },
      },
      renderContent: () => `
        <form class="service-dashboard-modal-form" onsubmit="event.preventDefault(); window.serviceShell.submitCreateReminderModal();">
          <div class="service-dashboard-modal-grid cols-2">
            <div class="form-group">
              <label for="serviceShellCreateReminderCustomer">Klient</label>
              <select id="serviceShellCreateReminderCustomer" onchange="window.serviceShell.populateCustomerVehicleSelect('serviceShellCreateReminderVehicle', this.value, { includeEmpty: true, emptyLabel: 'Obecná připomínka' })">
                ${customers.map((item) => `<option value="${Number(item.customer_id)}" ${Number(item.customer_id) === preferredCustomerId ? 'selected' : ''}>${escape(item.name || item.email || `Klient #${Number(item.customer_id)}`)}</option>`).join('')}
              </select>
            </div>
            <div class="form-group">
              <label for="serviceShellCreateReminderVehicle">Vozidlo</label>
              <select id="serviceShellCreateReminderVehicle"><option value="">Načítám vozidla…</option></select>
            </div>
          </div>
          <div class="service-dashboard-modal-grid cols-2">
            <div class="form-group">
              <label for="serviceShellCreateReminderType">Typ</label>
              <input type="text" id="serviceShellCreateReminderType" value="${escape(prefill.type || 'SERVIS')}">
            </div>
            <div class="form-group">
              <label for="serviceShellCreateReminderMethod">Kanál</label>
              <select id="serviceShellCreateReminderMethod">
                <option value="">Výchozí</option>
                <option value="app">Aplikace</option>
                <option value="email">E-mail</option>
                <option value="both">Obojí</option>
              </select>
            </div>
          </div>
          <div class="service-dashboard-modal-grid cols-2">
            <div class="form-group">
              <label for="serviceShellCreateReminderDueDate">Termín</label>
              <input type="date" id="serviceShellCreateReminderDueDate" value="${escape(prefill.dueDate || '')}">
            </div>
            <div class="form-group">
              <label for="serviceShellCreateReminderNotifyAt">Notifikovat</label>
              <input type="datetime-local" id="serviceShellCreateReminderNotifyAt" value="${escape(prefill.notifyAt || '')}">
            </div>
          </div>
          <div class="form-group">
            <label for="serviceShellCreateReminderText">Text</label>
            <textarea id="serviceShellCreateReminderText" rows="4">${escape(prefill.text || '')}</textarea>
          </div>
        </form>
      `,
      renderFooter: (modal) => `
        <div class="service-shell-modal-footer">
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.closeModal()">Zrušit</button>
          <button type="button" class="btn btn-primary" onclick="window.serviceShell.submitCreateReminderModal()">${modal.saving ? 'Ukládám…' : 'Vytvořit připomínku'}</button>
        </div>
      `,
    });
    await populateCustomerVehicleSelect('serviceShellCreateReminderVehicle', preferredCustomerId, {
      includeEmpty: true,
      emptyLabel: 'Obecná připomínka',
    });
  }

  async function submitCreateReminderModal() {
    if (isModalOpen('reminder-create')) {
      return runModalAction('save');
    }
  }

  async function openCreateInvoiceModal(prefill = {}) {
    const customers = Array.isArray(state.customers) ? state.customers : [];
    const preferredCustomerId = Number(prefill.customerId || customers[0]?.customer_id || 0);
    openModal({
      key: 'invoice-create',
      entityType: 'service-invoice',
      kicker: 'Faktura',
      title: 'Nová draft faktura',
      description: 'Vytvoření draftu, který lze dál upravit, vystavit a exportovat do PDF.',
      size: 'wide',
      actions: {
        save: async () => {
          const customerId = Number(document.getElementById('serviceShellCreateInvoiceCustomer')?.value || 0);
          const vehicleId = Number(document.getElementById('serviceShellCreateInvoiceVehicle')?.value || 0) || null;
          const dueAt = fromDateTimeInputValue(document.getElementById('serviceShellCreateInvoiceDueAt')?.value);
          const notes = String(document.getElementById('serviceShellCreateInvoiceNotes')?.value || '').trim() || null;
          const currency = String(document.getElementById('serviceShellCreateInvoiceCurrency')?.value || 'CZK').trim() || 'CZK';
          const lines = invoiceLinesFromDom();
          if (!customerId) {
            throw new Error('Vyberte klienta faktury.');
          }
          if (!lines.length) {
            throw new Error('Faktura musí obsahovat alespoň jednu položku.');
          }
          await window.apiCall('/api/service/invoices', 'POST', {
            customer_id: customerId,
            vehicle_id: vehicleId,
            currency,
            due_at: dueAt,
            notes,
            lines,
          });
          return { close: true, refreshParent: true, message: 'Draft faktura byla vytvořena.' };
        },
      },
      renderContent: () => `
        <form class="service-dashboard-modal-form" onsubmit="event.preventDefault(); window.serviceShell.submitCreateInvoiceModal();">
          <div class="service-dashboard-modal-grid cols-2">
            <div class="form-group">
              <label for="serviceShellCreateInvoiceCustomer">Klient</label>
              <select id="serviceShellCreateInvoiceCustomer" onchange="window.serviceShell.populateCustomerVehicleSelect('serviceShellCreateInvoiceVehicle', this.value, { includeEmpty: true, emptyLabel: 'Bez vozidla' })">
                ${customers.map((item) => `<option value="${Number(item.customer_id)}" ${Number(item.customer_id) === preferredCustomerId ? 'selected' : ''}>${escape(item.name || item.email || `Klient #${Number(item.customer_id)}`)}</option>`).join('')}
              </select>
            </div>
            <div class="form-group">
              <label for="serviceShellCreateInvoiceVehicle">Vozidlo</label>
              <select id="serviceShellCreateInvoiceVehicle"><option value="">Načítám vozidla…</option></select>
            </div>
          </div>
          <div class="service-dashboard-modal-grid cols-2">
            <div class="form-group">
              <label for="serviceShellCreateInvoiceCurrency">Měna</label>
              <input type="text" id="serviceShellCreateInvoiceCurrency" value="${escape(prefill.currency || 'CZK')}">
            </div>
            <div class="form-group">
              <label for="serviceShellCreateInvoiceDueAt">Splatnost</label>
              <input type="datetime-local" id="serviceShellCreateInvoiceDueAt" value="${escape(prefill.dueAt || '')}">
            </div>
          </div>
          <div class="form-group">
            <label for="serviceShellCreateInvoiceNotes">Poznámka</label>
            <textarea id="serviceShellCreateInvoiceNotes" rows="3">${escape(prefill.notes || '')}</textarea>
          </div>
          <div class="form-group">
            <label>Položky</label>
            <div id="serviceShellInvoiceLines" class="service-shell-quote-items"></div>
          </div>
        </form>
      `,
      renderFooter: (modal) => `
        <div class="service-shell-modal-footer">
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.closeModal()">Zrušit</button>
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.appendInvoiceLineRow()">Přidat položku</button>
          <button type="button" class="btn btn-primary" onclick="window.serviceShell.submitCreateInvoiceModal()">${modal.saving ? 'Ukládám…' : 'Vytvořit draft'}</button>
        </div>
      `,
    });
    await populateCustomerVehicleSelect('serviceShellCreateInvoiceVehicle', preferredCustomerId, {
      includeEmpty: true,
      emptyLabel: 'Bez vozidla',
    });
    appendInvoiceLineRow(prefill.line || {});
  }

  async function submitCreateInvoiceModal() {
    if (isModalOpen('invoice-create')) {
      return runModalAction('save');
    }
  }

  function openServiceInvoicePdf(invoiceId) {
    const id = Number(invoiceId || 0);
    if (!id) return;
    const path = `/api/service/invoices/${id}/pdf`;
    if (typeof window.openAuthenticatedPdf === 'function') {
      window.openAuthenticatedPdf(path).catch((err) => {
        const msg = err?.message || 'PDF faktury se nepodařilo otevřít.';
        if (typeof window.showAlert === 'function') window.showAlert(msg, 'error');
      });
      return;
    }
    window.open(`${window.location.origin}${path}`, '_blank', 'noopener');
  }

  function openServiceInvoiceDetailModal(invoiceId) {
    const id = Number(invoiceId || 0);
    if (!id) return;
    openModal({
      key: `service-invoice-${id}`,
      entityType: 'service-invoice',
      kicker: `Faktura #${id}`,
      title: 'Servisní faktura',
      description: 'Stav dokladu, částky a PDF podle produkčního API.',
      size: 'wide',
      actions: {
        save: async () => {
          const inv = state.modal?.data || {};
          if (String(inv?.status || '').toLowerCase() !== 'draft') {
            throw new Error('Upravit lze pouze draft fakturu.');
          }
          const customerId = Number(document.getElementById('serviceShellInvoiceCustomer')?.value || inv?.customer_id || 0);
          const vehicleId = Number(document.getElementById('serviceShellInvoiceVehicle')?.value || 0) || null;
          const dueAt = fromDateTimeInputValue(document.getElementById('serviceShellInvoiceDueAt')?.value);
          const notes = String(document.getElementById('serviceShellInvoiceNotes')?.value || '').trim() || null;
          const currency = String(document.getElementById('serviceShellInvoiceCurrency')?.value || inv?.currency || 'CZK').trim() || 'CZK';
          const lines = invoiceLinesFromDom();
          if (!customerId) {
            throw new Error('Vyberte klienta faktury.');
          }
          if (!lines.length) {
            throw new Error('Faktura musí obsahovat alespoň jednu položku.');
          }
          const updated = await window.apiCall(`/api/service/invoices/${id}`, 'PUT', {
            customer_id: customerId,
            vehicle_id: vehicleId,
            currency,
            due_at: dueAt,
            notes,
            lines,
          });
          return { data: updated, close: false, refreshParent: true, message: 'Draft faktura byla uložena.' };
        },
      },
      load: async () => window.apiCall(`/api/service/invoices/${id}`, 'GET'),
      renderContent: (modal) => {
        const inv = modal.data || {};
        const isDraft = String(inv?.status || '').toLowerCase() === 'draft';
        const customers = Array.isArray(state.customers) ? state.customers : [];
        const lines = Array.isArray(inv.lines) ? inv.lines : [];
        const rows = lines.length
          ? lines.map((ln) => `
            <tr>
              <td>${escape(ln?.description || '-')}</td>
              <td>${escape(String(ln?.quantity ?? '-'))}</td>
              <td>${escape(ln?.unit || '-')}</td>
              <td>${escape(String(ln?.unit_price ?? '-'))}</td>
              <td>${escape(String(ln?.tax_rate ?? '-'))}</td>
              <td>${escape(String(ln?.line_total ?? '-'))}</td>
            </tr>`).join('')
          : '<tr><td colspan="6" class="service-shell-empty">Bez položek</td></tr>';
        return `
          <div class="service-shell-list">
            <div class="service-shell-list-row"><span class="service-shell-list-title">Stav</span><span class="service-shell-list-value">${escape(inv?.status_label || inv?.status || '-')}</span></div>
            <div class="service-shell-list-row"><span class="service-shell-list-title">Číslo</span><span class="service-shell-list-value">${escape(inv?.invoice_number || '(koncept)')}</span></div>
            <div class="service-shell-list-row"><span class="service-shell-list-title">Celkem</span><span class="service-shell-list-value">${escape(String(inv?.total ?? '-'))} ${escape(inv?.currency || 'CZK')}</span></div>
            <div class="service-shell-list-row"><span class="service-shell-list-title">Klient</span><span class="service-shell-list-value">${escape(inv?.customer_label || (inv?.customer_id != null ? `Klient #${inv.customer_id}` : '-'))}</span></div>
            <div class="service-shell-list-row"><span class="service-shell-list-title">Vozidlo</span><span class="service-shell-list-value">${escape(inv?.vehicle_label || '-')}</span></div>
          </div>
          ${isDraft ? `
            <form class="service-dashboard-modal-form" onsubmit="event.preventDefault(); window.serviceShell.runModalAction('save');">
              <div class="service-dashboard-modal-grid cols-2">
                <div class="form-group">
                  <label for="serviceShellInvoiceCustomer">Klient</label>
                  <select id="serviceShellInvoiceCustomer" onchange="window.serviceShell.populateCustomerVehicleSelect('serviceShellInvoiceVehicle', this.value, { includeEmpty: true, emptyLabel: 'Bez vozidla', preferredVehicleId: ${Number(inv?.vehicle_id || 0)} })">
                    ${customers.map((item) => `<option value="${Number(item.customer_id)}" ${Number(item.customer_id) === Number(inv?.customer_id || 0) ? 'selected' : ''}>${escape(item.name || item.email || `Klient #${Number(item.customer_id)}`)}</option>`).join('')}
                  </select>
                </div>
                <div class="form-group">
                  <label for="serviceShellInvoiceVehicle">Vozidlo</label>
                  <select id="serviceShellInvoiceVehicle"><option value="">Načítám vozidla…</option></select>
                </div>
              </div>
              <div class="service-dashboard-modal-grid cols-2">
                <div class="form-group">
                  <label for="serviceShellInvoiceCurrency">Měna</label>
                  <input type="text" id="serviceShellInvoiceCurrency" value="${escape(inv?.currency || 'CZK')}">
                </div>
                <div class="form-group">
                  <label for="serviceShellInvoiceDueAt">Splatnost</label>
                  <input type="datetime-local" id="serviceShellInvoiceDueAt" value="${escape(toDateTimeInputValue(inv?.due_at))}">
                </div>
              </div>
              <div class="form-group">
                <label for="serviceShellInvoiceNotes">Poznámka</label>
                <textarea id="serviceShellInvoiceNotes" rows="3">${escape(inv?.notes || '')}</textarea>
              </div>
              <div class="form-group">
                <label>Položky</label>
                <div id="serviceShellInvoiceLines" class="service-shell-quote-items">
                  ${lines.map((ln) => `
                    <div class="service-shell-quote-item-row service-shell-invoice-line-row" data-invoice-line-row="1">
                      <input data-invoice-line-description type="text" value="${escape(ln?.description || '')}">
                      <input data-invoice-line-quantity type="number" inputmode="decimal" min="0.01" step="0.1" value="${escape(String(ln?.quantity ?? 1))}">
                      <input data-invoice-line-unit type="text" value="${escape(ln?.unit || 'ks')}">
                      <input data-invoice-line-unit-price type="number" inputmode="decimal" min="0" step="0.01" value="${escape(String(ln?.unit_price ?? 0))}">
                      <input data-invoice-line-tax-rate type="number" inputmode="decimal" min="0" max="100" step="0.1" value="${escape(String(ln?.tax_rate ?? 21))}">
                    </div>
                  `).join('')}
                </div>
              </div>
            </form>
          ` : `
            <h3 style="margin-top:16px;">Položky</h3>
            <table class="service-shell-table"><thead><tr><th>Popis</th><th>Množství</th><th>Jed.</th><th>Cena/j.</th><th>DPH %</th><th>Řádek</th></tr></thead><tbody>${rows}</tbody></table>
          `}
        `;
      },
      renderFooter: (modal) => {
        const inv = modal.data || {};
        const st = String(inv?.status || '').toLowerCase();
        const showIssue = st === 'draft';
        const showCancel = st === 'draft' || st === 'issued';
        return `
        <div class="service-shell-modal-footer">
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.closeModal()">Zavřít</button>
          ${showIssue ? `<button type="button" class="btn btn-secondary" onclick="window.serviceShell.appendInvoiceLineRow()">Přidat položku</button>` : ''}
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.openServiceInvoicePdf(${id})">PDF</button>
          ${showIssue ? `<button type="button" class="btn btn-primary" onclick="window.serviceShell.runModalAction('save')">${modal.saving ? 'Ukládám…' : 'Uložit draft'}</button>` : ''}
          ${showIssue ? `<button type="button" class="btn btn-primary" onclick="window.serviceShell.issueServiceInvoiceFromModal(${id})">Vystavit</button>` : ''}
          ${showCancel ? `<button type="button" class="btn btn-secondary" onclick="window.serviceShell.cancelServiceInvoiceFromModal(${id})">Zrušit</button>` : ''}
        </div>`;
      },
    });
    const current = state.modal?.data || {};
    if (String(current?.status || '').toLowerCase() === 'draft' && current?.customer_id) {
      queueMicrotask(() => {
        window.serviceShell.populateCustomerVehicleSelect('serviceShellInvoiceVehicle', current.customer_id, {
          includeEmpty: true,
          emptyLabel: 'Bez vozidla',
          preferredVehicleId: Number(current?.vehicle_id || 0),
        }).catch((err) => console.warn('[SERVICE_SHELL] invoice vehicle select load failed:', err));
      });
    }
  }

  async function issueServiceInvoiceFromModal(invoiceId) {
    const id = Number(invoiceId || 0);
    if (!id) return;
    await window.apiCall(`/api/service/invoices/${id}/issue`, 'POST');
    if (typeof window.showAlert === 'function') window.showAlert('Faktura byla vystavena.', 'success');
    await load(true, true);
    closeModal();
  }

  async function cancelServiceInvoiceFromModal(invoiceId) {
    const id = Number(invoiceId || 0);
    if (!id) return;
    await window.apiCall(`/api/service/invoices/${id}/cancel`, 'POST');
    if (typeof window.showAlert === 'function') window.showAlert('Faktura byla zrušena.', 'success');
    await load(true, true);
    closeModal();
  }

  function openVehicleQrModal(vehicleId) {
    const resolvedVehicleId = Number(vehicleId || state.activeVehicle?.vehicleId || 0);
    if (!resolvedVehicleId) return;
    openModal({
      key: `vehicle-qr-${resolvedVehicleId}`,
      entityType: 'vehicle-qr',
      kicker: `Vozidlo #${resolvedVehicleId}`,
      title: 'QR historie vozidla',
      description: 'Bezpečný veřejný token s revokací, podpisem a auditní stopou.',
      size: 'wide',
      bodyClass: 'service-shell-modal-body--qr',
      context: { vehicleId: resolvedVehicleId },
      load: async () => {
        try {
          return await window.apiCall(`/api/v1/services/workspace/vehicles/${resolvedVehicleId}/qr`, 'GET');
        } catch (error) {
          if (String(error?.message || '').includes('404')) {
            return { missing: true, vehicle_id: resolvedVehicleId };
          }
          throw error;
        }
      },
      actions: {
        create: async () => {
          const data = await window.apiCall(`/api/v1/services/workspace/vehicles/${resolvedVehicleId}/qr`, 'POST', {
            public_mode: 'verified',
            explicit_full_consent: false,
          });
          return { data };
        },
        regenerate: async () => {
          const data = await window.apiCall(`/api/v1/services/workspace/vehicles/${resolvedVehicleId}/qr/regenerate`, 'POST', {
            public_mode: 'verified',
            explicit_full_consent: false,
          });
          return { data };
        },
      },
      renderContent: (modal) => {
        const detail = modal.data || {};
        if (detail?.missing) {
          return '<div class="service-shell-empty">Pro toto vozidlo zatím nebyl vygenerován veřejný QR token.</div>';
        }
        return `
          <section class="service-shell-qr-panel">
            <div class="service-shell-qr-visual">${detail?.qr_svg || ''}</div>
            <div class="service-shell-list">
              <div class="service-shell-list-row"><span class="service-shell-list-title">Režim</span><span class="service-shell-list-value">${escape(detail?.public_mode || '-')}</span></div>
              <div class="service-shell-list-row"><span class="service-shell-list-title">Vydáno</span><span class="service-shell-list-value">${escape(detail?.issued_at ? formatDateTime(detail.issued_at) : '-')}</span></div>
              <div class="service-shell-list-row"><span class="service-shell-list-title">Poslední přístup</span><span class="service-shell-list-value">${escape(detail?.last_access_at ? formatDateTime(detail.last_access_at) : 'Zatím žádný')}</span></div>
            </div>
            <div class="service-shell-qr-link">${escape(detail?.public_history_url || '')}</div>
            <div class="service-shell-qr-actions">
              <button type="button" class="btn btn-secondary" onclick="window.serviceShell.openPublicHistoryFromModal()">Otevřít historii</button>
              <button type="button" class="btn btn-secondary" onclick="window.serviceShell.copyPublicHistoryFromModal()">Kopírovat odkaz</button>
            </div>
          </section>
        `;
      },
      renderFooter: (modal) => `
        <div class="service-shell-modal-footer ${isMobileViewport() ? 'service-shell-mobile-action-bar service-shell-mobile-action-bar--stack' : ''}">
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.closeModal()">Zpět</button>
          ${modal?.data?.missing
            ? `<button type="button" class="btn btn-primary" onclick="window.serviceShell.runModalAction('create')">${modal.saving ? 'Generuji…' : 'Vygenerovat QR'}</button>`
            : `
              <button type="button" class="btn btn-secondary" onclick="window.serviceShell.sharePublicHistoryFromModal()">Sdílet</button>
              <button type="button" class="btn btn-primary" onclick="window.serviceShell.runModalAction('regenerate')">${modal.saving ? 'Obnovuji…' : 'Regenerovat QR'}</button>
            `}
        </div>
      `,
    });
  }

  function openPublicHistoryFromModal() {
    const url = String(state.modal?.data?.public_history_url || '').trim();
    if (url) {
      window.open(url, '_blank', 'noopener');
    }
  }

  async function sharePublicHistoryFromModal() {
    const url = String(state.modal?.data?.public_history_url || '').trim();
    if (!url) return;
    if (navigator.share) {
      await navigator.share({ title: 'Veřejná historie vozidla', url });
      return;
    }
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(url);
      if (typeof window.showAlert === 'function') {
        window.showAlert('Odkaz na veřejnou historii byl zkopírován.', 'success');
      }
    }
  }

  async function copyPublicHistoryFromModal() {
    const url = String(state.modal?.data?.public_history_url || '').trim();
    if (!url) return;
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(url);
      if (typeof window.showAlert === 'function') {
        window.showAlert('Odkaz na veřejnou historii byl zkopírován.', 'success');
      }
      return;
    }
    window.prompt('Zkopírujte veřejný odkaz ručně:', url);
  }

  function openCustomerDetailModal(customerId) {
    const id = Number(customerId || 0);
    if (!id) return;
    openDetailModal({
      entityType: 'customer',
      entityId: id,
      endpoint: `/api/v1/services/workspace/customers/${id}/detail`,
      kicker: `Klient #${id}`,
      title: 'Detail klienta',
      description: 'Propojení servisního účtu, stav vazby a návazná vozidla klienta.',
      actions: {
        link: async () => {
          const response = await window.apiCall(`/api/v1/services/workspace/customers/${id}/link`, 'POST');
          return {
            close: false,
            reloadDetail: true,
            refreshParent: true,
            message: response?.message || 'Klient byl propojen.',
          };
        },
      },
      renderContent: (detail) => `
        ${renderDetailPills(detail)}
        ${renderBlockingReason(detail)}
        <div class="service-shell-modal-detail-grid cols-2">
          <div class="service-shell-side-card">
            <h3>Základní informace</h3>
            <div class="service-shell-list">
              <div class="service-shell-list-row"><span class="service-shell-list-title">Jméno</span><span class="service-shell-list-value">${escape(detail?.name || '-')}</span></div>
              <div class="service-shell-list-row"><span class="service-shell-list-title">E-mail</span><span class="service-shell-list-value">${escape(detail?.email || detail?.email_masked || '-')}</span></div>
              <div class="service-shell-list-row"><span class="service-shell-list-title">Telefon</span><span class="service-shell-list-value">${escape(detail?.phone || detail?.phone_masked || '-')}</span></div>
              <div class="service-shell-list-row"><span class="service-shell-list-title">Vozidla</span><span class="service-shell-list-value">${escape(String(detail?.vehicles_count ?? '-'))}</span></div>
              <div class="service-shell-list-row"><span class="service-shell-list-title">Sdílená vozidla</span><span class="service-shell-list-value">${escape(String(detail?.shared_vehicles_count ?? 0))}</span></div>
              <div class="service-shell-list-row"><span class="service-shell-list-title">Poslední servis</span><span class="service-shell-list-value">${escape(detail?.last_service_date ? formatDate(detail.last_service_date) : '-')}</span></div>
            </div>
          </div>
          <div class="service-shell-side-card">
            <h3>Vazba a pozvánky</h3>
            <div class="service-shell-list">
              <div class="service-shell-list-row"><span class="service-shell-list-title">Status</span><span class="service-shell-list-value">${escape(accessStatusLabel(detail?.status))}</span></div>
              <div class="service-shell-list-row"><span class="service-shell-list-title">Disclosure</span><span class="service-shell-list-value">${escape(disclosureLabel(detail?.disclosure))}</span></div>
              <div class="service-shell-list-row"><span class="service-shell-list-title">Pozvánka</span><span class="service-shell-list-value">${escape(detail?.invite_status_label || 'Bez pozvánky')}</span></div>
              <div class="service-shell-list-row"><span class="service-shell-list-title">Poznámka k vazbě</span><span class="service-shell-list-value">${escape(detail?.note || '-')}</span></div>
            </div>
          </div>
        </div>
        <section class="service-shell-side-card">
          <h3>Vozidla klienta</h3>
          <div class="service-shell-list">
            ${(Array.isArray(detail?.vehicles) && detail.vehicles.length)
              ? detail.vehicles.map((item) => `
                <div class="service-shell-list-row">
                  <div>
                    <p class="service-shell-list-title">${escape(item?.label || 'Vozidlo')}</p>
                    <p class="service-shell-list-note">${escape(accessStatusLabel(item?.status || 'matched'))}</p>
                  </div>
                  <div class="service-shell-modal-actions">
                    <button type="button" class="btn btn-secondary" onclick="window.serviceShell.openVehicleDetailModal(${Number(item?.vehicle_id || 0)})">Otevřít detail</button>
                    ${item?.can_create_work_order ? `<button type="button" class="btn btn-primary" onclick="window.serviceShell.closeModal(); window.serviceShell.openCreateWorkOrderModal({ ownerId: ${id}, vehicleId: ${Number(item?.vehicle_id || 0)} })">Nová zakázka</button>` : ''}
                  </div>
                </div>
              `).join('')
              : '<div class="service-shell-empty">Klient zatím nemá v shellu dostupná vozidla.</div>'}
          </div>
        </section>
      `,
      renderFooter: (detail, modal) => `
        <div class="service-shell-modal-footer">
          ${detail?.can_link ? `<button type="button" class="btn btn-primary" onclick="window.serviceShell.runModalAction('link')">${modal.saving ? 'Propojuji…' : 'Propojit klienta'}</button>` : ''}
          ${detail?.status === 'linked' ? `<button type="button" class="btn btn-secondary" onclick="window.serviceShell.closeModal(); window.serviceShell.openAddVehicleModal(${id})">Přidat vozidlo</button>` : ''}
          ${detail?.can_create_work_order ? `<button type="button" class="btn btn-secondary" onclick="window.serviceShell.closeModal(); window.serviceShell.openCreateWorkOrderModal({ ownerId: ${id} })">Nová zakázka</button>` : ''}
          ${detail?.can_send_invite && !detail?.can_link ? `<button type="button" class="btn btn-secondary" onclick="window.serviceShell.sendInvitationFromSearch()">Odeslat pozvánku</button>` : ''}
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.closeModal()">Zavřít</button>
        </div>
      `,
    });
  }

  function openVehicleDetailModal(vehicleId) {
    const id = Number(vehicleId || 0);
    if (!id) return;
    openDetailModal({
      entityType: 'vehicle',
      entityId: id,
      load: async () => {
        const [detail, records, quotes] = await Promise.all([
          window.apiCall(`/api/v1/services/workspace/vehicles/${id}/detail`, 'GET'),
          window.apiCall(`/api/v1/vehicles/${id}/records`, 'GET').catch(() => []),
          window.apiCall(`/api/service/vehicles/${id}/quotes`, 'GET').catch(() => ({ items: [] })),
        ]);
        setActiveVehicle(detail);
        render();
        return {
          ...detail,
          service_records: Array.isArray(records) ? records : [],
          service_quotes: Array.isArray(quotes?.items) ? quotes.items : [],
        };
      },
      kicker: `Vozidlo #${id}`,
      title: 'Detail vozidla',
      description: 'Schválený přístup, omezené zobrazení bez oprávnění a navazující servisní akce.',
      renderContent: (detail) => `
        ${renderDetailPills(detail)}
        ${renderBlockingReason(detail)}
        <div class="service-shell-modal-detail-grid cols-2">
          <div class="service-shell-side-card">
            <h3>Identita vozidla</h3>
            <div class="service-shell-list">
              <div class="service-shell-list-row"><span class="service-shell-list-title">Název</span><span class="service-shell-list-value">${escape(detail?.nickname || [detail?.brand, detail?.model].filter(Boolean).join(' ') || 'Vozidlo')}</span></div>
              <div class="service-shell-list-row"><span class="service-shell-list-title">SPZ</span><span class="service-shell-list-value">${escape(detail?.plate || detail?.plate_masked || '-')}</span></div>
              <div class="service-shell-list-row"><span class="service-shell-list-title">VIN</span><span class="service-shell-list-value">${escape(detail?.vin || detail?.vin_masked || '-')}</span></div>
              <div class="service-shell-list-row"><span class="service-shell-list-title">Rok</span><span class="service-shell-list-value">${escape(String(detail?.year || '-'))}</span></div>
              <div class="service-shell-list-row"><span class="service-shell-list-title">Motor</span><span class="service-shell-list-value">${escape(detail?.engine || '-')}</span></div>
            </div>
          </div>
          <div class="service-shell-side-card">
            <h3>Přístup a vazba</h3>
            <div class="service-shell-list">
              <div class="service-shell-list-row"><span class="service-shell-list-title">Přístup</span><span class="service-shell-list-value">${escape(accessStatusLabel(detail?.status))}</span></div>
              <div class="service-shell-list-row"><span class="service-shell-list-title">Klient</span><span class="service-shell-list-value">${escape(detail?.owner_name || (detail?.linked_customer ? 'Propojený klient' : 'Skrytý bez vazby'))}</span></div>
              <div class="service-shell-list-row"><span class="service-shell-list-title">Platnost STK</span><span class="service-shell-list-value">${escape(detail?.stk_valid_until ? formatDate(detail.stk_valid_until) : '-')}</span></div>
              <div class="service-shell-list-row"><span class="service-shell-list-title">Aktuální km</span><span class="service-shell-list-value">${escape(detail?.current_mileage_km != null ? String(detail.current_mileage_km) : '-')}</span></div>
              <div class="service-shell-list-row"><span class="service-shell-list-title">Datová důvěra</span><span class="service-shell-list-value">${escape(detail?.data_trust_state || '-')}</span></div>
            </div>
          </div>
        </div>
        <section class="service-shell-side-card">
          <div class="service-shell-card-head">
            <div>
              <h3>Servisní záznamy</h3>
              <p class="service-shell-subtitle">Pouze auditovatelná historie bez tichých přepisů.</p>
            </div>
            <button type="button" class="service-shell-icon-btn" onclick="window.serviceShell.openServiceRecordModal(${id})" aria-label="Nový servisní záznam">+</button>
          </div>
          <div class="service-shell-record-card-list">
            ${serviceRecordCards(detail?.service_records, id)}
          </div>
        </section>
        <section class="service-shell-side-card">
          <div class="service-shell-card-head">
            <div>
              <h3>Nabídky</h3>
              <p class="service-shell-subtitle">Zákaznické výstupy navázané na záznamy a zakázky.</p>
            </div>
            <button type="button" class="service-shell-icon-btn" onclick="window.serviceShell.openFirstRecordForQuote()" aria-label="Vytvořit nabídku">+</button>
          </div>
          <div class="service-shell-record-card-list service-shell-vehicle-quotes-wrap">
            ${vehicleQuotesSection(detail)}
          </div>
        </section>
      `,
      renderFooter: (detail) => `
        <div class="service-shell-modal-footer">
          ${detail?.can_request_access ? `<button type="button" class="btn btn-primary" onclick="window.serviceShell.requestVehicleAccess(${id}, ${JSON.stringify(String(detail?.plate_masked || ''))})">Požádat o přístup</button>` : ''}
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.openVehicleQrModal(${id})">Zobrazit QR</button>
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.openFirstRecordForQuote()">Vytvořit nabídku</button>
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.openServiceRecordModal(${id})">Nový záznam</button>
          ${detail?.can_create_work_order ? `<button type="button" class="btn btn-secondary" onclick="window.serviceShell.closeModal(); window.serviceShell.openCreateWorkOrderModal({ ownerId: ${Number(detail?.owner_customer_id || 0)}, vehicleId: ${id} })">Nová zakázka</button>` : ''}
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.closeModal()">Zavřít</button>
        </div>
      `,
    });
  }

  function openDocumentDetailModal(documentId) {
    const id = Number(documentId || 0);
    if (!id) return;
    openDetailModal({
      entityType: 'document',
      entityId: id,
      endpoint: `/api/v1/services/workspace/documents/${id}/detail`,
      kicker: `Doklad #${id}`,
      title: 'Detail dokumentu',
      description: 'Výsledek extrakce, validace a návazné akce v jednotném servisním rozhraní.',
      renderContent: (detail) => {
        const items = Array.isArray(detail?.parsed_data?.items) ? detail.parsed_data.items : [];
        return `
          ${renderDetailPills(detail)}
          ${renderBlockingReason(detail)}
          <div class="service-shell-modal-detail-grid cols-2">
            <div class="service-shell-side-card">
              <h3>Doklad</h3>
              <div class="service-shell-list">
                <div class="service-shell-list-row"><span class="service-shell-list-title">Číslo</span><span class="service-shell-list-value">${escape(detail?.document_number || detail?.original_filename || '-')}</span></div>
                <div class="service-shell-list-row"><span class="service-shell-list-title">Dodavatel</span><span class="service-shell-list-value">${escape(detail?.supplier_name || '-')}</span></div>
                <div class="service-shell-list-row"><span class="service-shell-list-title">Klient</span><span class="service-shell-list-value">${escape(detail?.customer_name || detail?.customer_email_masked || '-')}</span></div>
                <div class="service-shell-list-row"><span class="service-shell-list-title">Vozidlo</span><span class="service-shell-list-value">${escape(detail?.vehicle_label || '-')}</span></div>
                <div class="service-shell-list-row"><span class="service-shell-list-title">Celkem</span><span class="service-shell-list-value">${escape(formatMoney(detail?.total_with_vat, detail?.currency))}</span></div>
              </div>
            </div>
            <div class="service-shell-side-card">
              <h3>Extrakce</h3>
              <div class="service-shell-list">
                <div class="service-shell-list-row"><span class="service-shell-list-title">Stav</span><span class="service-shell-list-value">${escape(accessStatusLabel(detail?.status))}</span></div>
                <div class="service-shell-list-row"><span class="service-shell-list-title">Confidence</span><span class="service-shell-list-value">${escape(detail?.parse_confidence != null ? String(detail.parse_confidence) : '-')}</span></div>
                <div class="service-shell-list-row"><span class="service-shell-list-title">Vloženo</span><span class="service-shell-list-value">${escape(detail?.created_at ? formatDateTime(detail.created_at) : '-')}</span></div>
                <div class="service-shell-list-row"><span class="service-shell-list-title">Zdroj</span><span class="service-shell-list-value">${escape(detail?.source_type || '-')}</span></div>
              </div>
            </div>
          </div>
          ${detail?.extracted_text_preview ? `<section class="service-shell-side-card"><h3>Náhled textu</h3><div class="service-shell-empty service-shell-modal-audit">${escape(detail.extracted_text_preview)}</div></section>` : ''}
          <section class="service-shell-side-card">
            <h3>Položky</h3>
            <div class="service-shell-list">
              ${items.length ? items.map((item) => `
                <div class="service-shell-list-row">
                  <div>
                    <p class="service-shell-list-title">${escape(item?.name || 'Položka')}</p>
                    <p class="service-shell-list-note">${escape(String(item?.quantity || '-'))} ${escape(item?.unit || '')}</p>
                  </div>
                  <div class="service-shell-list-value">${escape(formatMoney(item?.total_price, detail?.currency))}</div>
                </div>
              `).join('') : '<div class="service-shell-empty">Bez strukturovaných položek.</div>'}
            </div>
          </section>
        `;
      },
      renderFooter: (detail) => `
        <div class="service-shell-modal-footer">
          ${detail?.can_request_access ? `<button type="button" class="btn btn-primary" onclick="window.serviceShell.requestVehicleAccess(${Number(detail?.vehicle_id || 0)}, ${JSON.stringify(String(detail?.vehicle_plate_masked || ''))})">Požádat o přístup</button>` : ''}
          ${detail?.can_create_work_order ? `<button type="button" class="btn btn-secondary" onclick="window.serviceShell.closeModal(); window.serviceShell.openCreateWorkOrderModal({ ownerId: ${Number(detail?.customer_id || 0)}, vehicleId: ${Number(detail?.vehicle_id || 0)} })">Nová zakázka</button>` : ''}
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.closeModal()">Zavřít</button>
        </div>
      `,
    });
  }

  function openReservationDetailModal(reservationId) {
    const id = Number(reservationId || 0);
    if (!id) return;
    openDetailModal({
      entityType: 'reservation',
      entityId: id,
      endpoint: `/api/v1/services/workspace/reservations/${id}/detail`,
      kicker: `Rezervace #${id}`,
      title: 'Detail rezervace',
      description: 'Shell-native detail rezervace s možností úpravy a návaznou zakázkou.',
      actions: {
        save: async () => {
          const detail = state.modal?.data || {};
          if (!detail?.can_edit) {
            throw new Error(detail?.blocking_reason || 'Rezervaci teď nelze upravit.');
          }
          await window.apiCall(`/api/v1/reservations/${id}`, 'PUT', {
            service_type: String(document.getElementById('serviceShellReservationType')?.value || '').trim() || null,
            note: String(document.getElementById('serviceShellReservationNote')?.value || '').trim() || null,
            start_datetime: fromDateTimeInputValue(document.getElementById('serviceShellReservationStart')?.value),
            end_datetime: fromDateTimeInputValue(document.getElementById('serviceShellReservationEnd')?.value),
            status: String(document.getElementById('serviceShellReservationStatus')?.value || detail?.status || 'PENDING').trim(),
          });
          return {
            close: true,
            refreshParent: true,
            message: 'Rezervace byla aktualizována.',
          };
        },
      },
      renderContent: (detail) => `
        ${renderDetailPills(detail)}
        ${renderBlockingReason(detail)}
        <div class="service-shell-modal-summary">
          <span>${escape(detail?.customer_name || detail?.customer_email_masked || '-')}</span>
          <span>${escape(detail?.vehicle_name || detail?.vehicle_plate_masked || '-')}</span>
        </div>
        <form class="service-dashboard-modal-form" onsubmit="event.preventDefault(); window.serviceShell.runModalAction('save');">
          <div class="service-dashboard-modal-grid cols-2">
            <div class="form-group">
              <label for="serviceShellReservationType">Typ rezervace</label>
              <input type="text" id="serviceShellReservationType" value="${escape(detail?.service_type || '')}" ${detail?.can_edit ? '' : 'disabled'}>
            </div>
            <div class="form-group">
              <label for="serviceShellReservationStatus">Stav</label>
              <select id="serviceShellReservationStatus" ${detail?.can_edit ? '' : 'disabled'}>
                <option value="PENDING" ${String(detail?.status || '').toUpperCase() === 'PENDING' ? 'selected' : ''}>Čeká</option>
                <option value="CONFIRMED" ${String(detail?.status || '').toUpperCase() === 'CONFIRMED' ? 'selected' : ''}>Potvrzeno</option>
                <option value="CANCELLED" ${String(detail?.status || '').toUpperCase() === 'CANCELLED' ? 'selected' : ''}>Zrušeno</option>
              </select>
            </div>
          </div>
          <div class="service-dashboard-modal-grid cols-2">
            <div class="form-group">
              <label for="serviceShellReservationStart">Začátek</label>
              <input type="datetime-local" id="serviceShellReservationStart" value="${escape(toDateTimeInputValue(detail?.start_datetime))}" ${detail?.can_edit ? '' : 'disabled'}>
            </div>
            <div class="form-group">
              <label for="serviceShellReservationEnd">Konec</label>
              <input type="datetime-local" id="serviceShellReservationEnd" value="${escape(toDateTimeInputValue(detail?.end_datetime))}" ${detail?.can_edit ? '' : 'disabled'}>
            </div>
          </div>
          <div class="form-group">
            <label for="serviceShellReservationNote">Poznámka</label>
            <textarea id="serviceShellReservationNote" rows="4" ${detail?.can_edit ? '' : 'disabled'}>${escape(detail?.note || '')}</textarea>
          </div>
        </form>
      `,
      renderFooter: (detail, modal) => `
        <div class="service-shell-modal-footer">
          ${detail?.can_request_access ? `<button type="button" class="btn btn-primary" onclick="window.serviceShell.requestVehicleAccess(${Number(detail?.vehicle_id || 0)}, ${JSON.stringify(String(detail?.vehicle_plate_masked || ''))})">Požádat o přístup</button>` : ''}
          ${detail?.can_create_work_order ? `<button type="button" class="btn btn-secondary" onclick="window.serviceShell.closeModal(); window.serviceShell.openCreateWorkOrderModal({ ownerId: ${Number(detail?.customer_id || 0)}, vehicleId: ${Number(detail?.vehicle_id || 0)} })">Nová zakázka</button>` : ''}
          ${detail?.can_edit ? `<button type="button" class="btn btn-primary" onclick="window.serviceShell.runModalAction('save')">${modal.saving ? 'Ukládám…' : 'Uložit změny'}</button>` : ''}
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.closeModal()">Zavřít</button>
        </div>
      `,
    });
  }

  function openReminderDetailModal(reminderId) {
    const id = Number(reminderId || 0);
    if (!id) return;
    openDetailModal({
      entityType: 'reminder',
      entityId: id,
      endpoint: `/api/v1/services/workspace/reminders/${id}/detail`,
      kicker: `Připomínka #${id}`,
      title: 'Detail připomínky',
      description: 'Follow-up servisního týmu, stav dokončení a navazující akce.',
      actions: {
        save: async () => {
          const detail = state.modal?.data || {};
          if (!detail?.can_edit) {
            throw new Error(detail?.blocking_reason || 'Připomínku teď nelze upravit.');
          }
          await window.apiCall(`/api/v1/services/workspace/reminders/${id}`, 'PUT', {
            type: String(document.getElementById('serviceShellReminderType')?.value || detail?.type || 'SERVIS').trim(),
            text: String(document.getElementById('serviceShellReminderText')?.value || '').trim(),
            due_date: String(document.getElementById('serviceShellReminderDueDate')?.value || '').trim() || null,
            notify_at: fromDateTimeInputValue(document.getElementById('serviceShellReminderNotifyAt')?.value),
            notification_method: String(document.getElementById('serviceShellReminderMethod')?.value || '').trim() || null,
            is_completed: String(document.getElementById('serviceShellReminderCompleted')?.value || 'false') === 'true',
          });
          return {
            close: true,
            refreshParent: true,
            message: 'Připomínka byla aktualizována.',
          };
        },
      },
      renderContent: (detail) => `
        ${renderDetailPills(detail)}
        ${renderBlockingReason(detail)}
        <form class="service-dashboard-modal-form" onsubmit="event.preventDefault(); window.serviceShell.runModalAction('save');">
          <div class="service-dashboard-modal-grid cols-2">
            <div class="form-group">
              <label for="serviceShellReminderType">Typ</label>
              <input type="text" id="serviceShellReminderType" value="${escape(detail?.type || 'SERVIS')}" ${detail?.can_edit ? '' : 'disabled'}>
            </div>
            <div class="form-group">
              <label for="serviceShellReminderCompleted">Stav</label>
              <select id="serviceShellReminderCompleted" ${detail?.can_edit ? '' : 'disabled'}>
                <option value="false" ${detail?.is_completed ? '' : 'selected'}>Aktivní</option>
                <option value="true" ${detail?.is_completed ? 'selected' : ''}>Dokončeno</option>
              </select>
            </div>
          </div>
          <div class="service-dashboard-modal-grid cols-2">
            <div class="form-group">
              <label for="serviceShellReminderDueDate">Termín</label>
              <input type="date" id="serviceShellReminderDueDate" value="${escape(String(detail?.due_date || '').slice(0, 10))}" ${detail?.can_edit ? '' : 'disabled'}>
            </div>
            <div class="form-group">
              <label for="serviceShellReminderNotifyAt">Notifikovat</label>
              <input type="datetime-local" id="serviceShellReminderNotifyAt" value="${escape(toDateTimeInputValue(detail?.notify_at))}" ${detail?.can_edit ? '' : 'disabled'}>
            </div>
          </div>
          <div class="form-group">
            <label for="serviceShellReminderMethod">Kanál</label>
            <select id="serviceShellReminderMethod" ${detail?.can_edit ? '' : 'disabled'}>
              <option value="" ${!detail?.notification_method ? 'selected' : ''}>Výchozí</option>
              <option value="app" ${detail?.notification_method === 'app' ? 'selected' : ''}>Aplikace</option>
              <option value="email" ${detail?.notification_method === 'email' ? 'selected' : ''}>E-mail</option>
              <option value="both" ${detail?.notification_method === 'both' ? 'selected' : ''}>Obojí</option>
            </select>
          </div>
          <div class="form-group">
            <label for="serviceShellReminderText">Text</label>
            <textarea id="serviceShellReminderText" rows="4" ${detail?.can_edit ? '' : 'disabled'}>${escape(detail?.text || '')}</textarea>
          </div>
        </form>
      `,
      renderFooter: (detail, modal) => `
        <div class="service-shell-modal-footer">
          ${detail?.can_request_access ? `<button type="button" class="btn btn-primary" onclick="window.serviceShell.requestVehicleAccess(${Number(detail?.vehicle_id || 0)}, ${JSON.stringify(String(detail?.vehicle_plate_masked || ''))})">Požádat o přístup</button>` : ''}
          ${detail?.can_create_work_order ? `<button type="button" class="btn btn-secondary" onclick="window.serviceShell.closeModal(); window.serviceShell.openCreateWorkOrderModal({ ownerId: ${Number(detail?.customer_id || 0)}, vehicleId: ${Number(detail?.vehicle_id || 0)} })">Nová zakázka</button>` : ''}
          ${detail?.can_edit ? `<button type="button" class="btn btn-primary" onclick="window.serviceShell.runModalAction('save')">${modal.saving ? 'Ukládám…' : 'Uložit změny'}</button>` : ''}
          <button type="button" class="btn btn-secondary" onclick="window.serviceShell.closeModal()">Zavřít</button>
        </div>
      `,
    });
  }

  function filteredWorkOrders() {
    const query = String(state.searchTerm ?? '').trim().toLowerCase();
    const today = todayKey();
    let items = Array.isArray(state.workOrders) ? [...state.workOrders] : [];

    if (state.kpiFilter === 'active') {
      items = items.filter((item) => ['in_progress', 'approved'].includes(String(item?.status || '').toLowerCase()));
    } else if (state.kpiFilter === 'awaiting') {
      items = items.filter((item) => String(item?.status || '').toLowerCase() === 'awaiting_client_approval');
    } else if (state.kpiFilter === 'today') {
      items = items.filter((item) => toDateKey(item?.due_date) === today);
    } else if (state.kpiFilter === 'overdue') {
      items = items.filter((item) => {
        const due = toDateKey(item?.due_date);
        return due && due < today && String(item?.status || '').toLowerCase() !== 'completed';
      });
    }

    if (query) {
      items = items.filter((item) => {
        const haystack = [
          item?.customer_name,
          item?.vehicle_vin,
          item?.vehicle_spz,
          item?.source_type,
          item?.source_label,
          item?.technician_name,
          item?.title,
        ].join(' ').toLowerCase();
        return haystack.includes(query);
      });
    }

    if (state.sortBy === 'due_desc') {
      items.sort((a, b) => String(b?.due_date || '').localeCompare(String(a?.due_date || '')));
    } else if (state.sortBy === 'customer') {
      items.sort((a, b) => String(a?.customer_name || '').localeCompare(String(b?.customer_name || ''), 'cs'));
    } else if (state.sortBy === 'status') {
      items.sort((a, b) => String(a?.status || '').localeCompare(String(b?.status || ''), 'cs'));
    } else {
      items.sort((a, b) => String(a?.due_date || '').localeCompare(String(b?.due_date || '')));
    }

    return items;
  }

  function dashboardSummary() {
    const summary = state.summary || {};
    const reservations = Array.isArray(state.reservations) ? state.reservations : [];
    const reminders = Array.isArray(state.reminders) ? state.reminders : [];
    const invoices = Array.isArray(state.invoices) ? state.invoices : [];
    return {
      active_jobs: Number(summary.active_jobs || 0),
      awaiting_approval: Number(summary.awaiting_approval || 0),
      due_today: Number(summary.due_today || 0),
      overdue: Number(summary.overdue || 0),
      new_reservations: Number(summary.new_reservations || reservations.filter((item) => String(item?.status || '').toUpperCase() === 'PENDING').length),
      today_reservations: Number(summary.today_reservations || reservations.filter((item) => toDateKey(item?.scheduled_for || item?.reservation_date || item?.starts_at) === todayKey()).length),
      pending_quotes: Number(summary.pending_quotes || 0),
      draft_invoices: Number(summary.draft_invoices || invoices.filter((item) => String(item?.status || '').toLowerCase() === 'draft').length),
      invoices_total: Number(summary.invoices_total || invoices.length),
      open_reminders: Number(summary.open_reminders || reminders.filter((item) => !item?.is_completed).length),
      overdue_reminders: Number(summary.overdue_reminders || reminders.filter((item) => !item?.is_completed && toDateKey(item?.due_date) && toDateKey(item?.due_date) < todayKey()).length),
    };
  }

  function dashboardOpsStats() {
    const summary = dashboardSummary();
    return `
      <div class="service-shell-stat-grid">
        <article class="service-shell-mini-card summary-card"><h3>Nové rezervace</h3><div class="service-shell-stat-value">${summary.new_reservations}</div><p class="service-shell-muted">Čekají na reakci servisu</p></article>
        <article class="service-shell-mini-card summary-card"><h3>Čekající nabídky</h3><div class="service-shell-stat-value">${summary.pending_quotes}</div><p class="service-shell-muted">Koncepty a odeslané nabídky</p></article>
        <article class="service-shell-mini-card summary-card"><h3>Draft faktury</h3><div class="service-shell-stat-value">${summary.draft_invoices}</div><p class="service-shell-muted">Připravené k vystavení</p></article>
        <article class="service-shell-mini-card summary-card"><h3>Aktivní připomínky</h3><div class="service-shell-stat-value">${summary.open_reminders}</div><p class="service-shell-muted">Follow-upy a kritické termíny</p></article>
      </div>
    `;
  }

  function shellHeader() {
    const profile = currentProfile();
    const mobile = isMobileViewport();
    const accountMenu = state.accountMenuOpen ? `
      <div class="service-shell-account-menu">
        <div class="service-shell-account-summary">
          <strong>${escape(profile?.name || window.currentUser?.name || 'Servisní účet')}</strong>
          <span>${escape(profile?.email || window.currentUser?.email || '-')}</span>
          <span>${escape(String(profile?.role || window.currentUser?.role || 'service_account').replace(/_/g, ' '))}</span>
        </div>
        <button type="button" class="service-shell-account-action" onclick="window.serviceShell.openAccountSettings()">Otevřít nastavení účtu</button>
        <button type="button" class="service-shell-account-action" onclick="window.serviceShell.navigate('team'); window.serviceShell.closeAccountMenu();">Otevřít profil</button>
        <button type="button" class="service-shell-account-action danger" onclick="window.serviceShell.logout()">Odhlásit se</button>
      </div>
    ` : '';
    const navItems = [
      ['dashboard', 'Dashboard'],
      ['clients', 'Klienti'],
      ['vehicles', 'Vozidla'],
      ['work-orders', 'Zakázky'],
      ['documents', 'Dokumenty'],
      ['invoices', 'Faktury'],
      ['reservations', 'Rezervace'],
      ['reminders', 'Připomínky'],
      ['team', 'Tým'],
    ];

    return `
      <header class="service-shell-header">
        <div class="service-shell-brandline">
          <button type="button" class="service-shell-icon-btn service-shell-mobile-menu-btn" onclick="window.serviceShell.toggleMobileNav()" aria-expanded="${mobile && state.mobileNavOpen ? 'true' : 'false'}" aria-controls="service-shell-main-nav" aria-label="${state.mobileNavOpen ? 'Zavřít menu' : 'Otevřít menu'}">☰</button>
          <div class="service-shell-brand">
            <span class="service-shell-brand-mark" aria-hidden="true"></span>
            <span>${escape(getAppDisplayName())}</span>
          </div>
          <nav id="service-shell-main-nav" class="service-shell-nav ${mobile && state.mobileNavOpen ? 'mobile-open' : ''}" aria-label="Servisní navigace">
            ${navItems.map(([key, label]) => `
              <button
                type="button"
                class="service-shell-nav-btn ${state.activeSection === key ? 'active' : ''}"
                onclick="window.serviceShell.navigate('${key}')"
              >${label}</button>
            `).join('')}
          </nav>
        </div>
        <div class="service-shell-toolbar">
          <button type="button" class="service-shell-icon-btn" onclick="window.serviceShell.toggleTheme()" aria-label="Přepnout motiv">${state.theme === 'light' ? '☀' : '☾'}</button>
          <button type="button" class="service-shell-icon-btn" onclick="window.serviceShell.load(true)" aria-label="Obnovit data">↻</button>
          <button type="button" class="service-shell-icon-btn" onclick="window.serviceShell.openServiceToolsModal()" aria-label="Servisní nástroje">⌘</button>
          <div class="service-shell-userbox-wrap">
          <button type="button" class="service-shell-userbox" onclick="window.serviceShell.toggleAccountMenu()" aria-label="Účet servisu">
            <span class="service-shell-avatar">${escape(initials(profile?.name || profile?.email || window.currentUser?.email || 'SA'))}</span>
            <div class="service-shell-usertext">
              <strong>${escape(profile?.name || window.currentUser?.name || window.currentUser?.email || 'Servisní účet')}</strong>
              <span>${escape(String(profile?.role || window.currentUser?.role || 'service_account').replace(/_/g, ' '))}</span>
            </div>
          </button>
          ${accountMenu}
          </div>
          <button type="button" class="service-shell-primary-btn" onclick="${state.activeVehicle ? `window.serviceShell.openServiceRecordModal(${Number(state.activeVehicle.vehicleId || 0)})` : 'window.serviceShell.openCreateWorkOrderModal()'}">${mobile ? '+' : '+ Nová zakázka'}</button>
        </div>
      </header>
    `;
  }

  function pageHead(title, subtitle) {
    return `
      <div class="service-shell-page-head">
        <div>
          <h1>${escape(title)}</h1>
          <p class="service-shell-subtitle">${escape(subtitle)}</p>
        </div>
      </div>
    `;
  }

  function clickableAttrs(action) {
    const js = String(action || '').trim();
    if (!js) return '';
    const safe = js.replace(/"/g, '&quot;');
    return `class="service-shell-clickable-row" tabindex="0" role="button" onclick="${safe}" onkeydown="if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); ${safe} }"`;
  }

  function kpiCards() {
    const summary = dashboardSummary();
    const cards = [
      ['active', 'Aktivní zakázky', summary.active_jobs, 'Ve výrobě nebo schválené klientem', '✓', 'success', 'Otevřít aktivní frontu'],
      ['awaiting', 'Čeká na schválení', summary.awaiting_approval, 'Zakázky blokované souhlasem klienta', '!', 'warning', 'Otevřít čekající zakázky'],
      ['today', 'Dnes k dokončení', summary.due_today, 'Plánované odevzdání během dneška', '△', 'warning', 'Otevřít dnešní termíny'],
      ['overdue', 'Po termínu', summary.overdue, 'Rozpracované zakázky po deadlinu', '•', 'danger', 'Otevřít kritické zakázky'],
    ];
    return `
      <section class="service-shell-kpis">
        ${cards.map(([key, title, value, note, icon, iconCls, actionNote]) => `
          <article class="service-shell-kpi summary-card ${state.kpiFilter === key ? 'active' : ''}" tabindex="0" role="button" onclick="window.serviceShell.setKpiFilter('${key}')" onkeydown="if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); window.serviceShell.setKpiFilter('${key}') }">
            <div class="service-shell-kpi-head">
              <span class="service-shell-kpi-icon ${iconCls}">${icon}</span>
              <span class="service-shell-kpi-arrow">↗</span>
            </div>
            <div>
              <h3 class="service-shell-kpi-title">${title}</h3>
            </div>
            <div>
              <p class="service-shell-kpi-value">${escape(String(value))}</p>
              <p class="service-shell-muted">${note}</p>
              <p class="service-shell-action-note">${actionNote}</p>
            </div>
          </article>
        `).join('')}
      </section>
    `;
  }

  function workOrderRows(items) {
    if (!items.length) {
      return `<tr><td colspan="6"><div class="service-shell-empty">Žádné zakázky neodpovídají aktuálním filtrům.</div></td></tr>`;
    }
    return items.map((item) => {
      const meta = statusMeta(item?.status);
      const action = `openServiceDashboardWorkOrderDetail(${Number(item?.id || 0)})`;
      return `
        <tr ${clickableAttrs(action)}>
          <td>
            <div class="service-shell-row-primary">
              <strong>${escape(item?.customer_name || '-')}</strong>
              <span class="service-shell-muted">${escape(item?.title || 'Servisní zakázka')}</span>
            </div>
          </td>
          <td>${escape(item?.vehicle_vin || '-')}<br><span class="service-shell-muted">${escape(item?.vehicle_spz || '-')}</span></td>
          <td>${escape(item?.due_date ? formatDate(item.due_date) : '-')}</td>
          <td>${escape(sourceLabel(item?.source_type || item?.source || item?.source_label))}</td>
          <td>
            <span class="service-shell-tech">
              <span class="service-shell-tech-avatar">${escape(initials(item?.technician_name || 'T'))}</span>
              <span>${escape(item?.technician_name || '-')}</span>
            </span>
          </td>
          <td><span class="service-shell-badge ${meta.cls}">${meta.label}</span></td>
        </tr>
      `;
    }).join('');
  }

  function rightPanel() {
    const performance = Array.isArray(state.performance) ? state.performance.slice(0, 4) : [];
    const reservations = Array.isArray(state.reservations) ? state.reservations.slice(0, 4) : [];
    const reminders = Array.isArray(state.reminders) ? state.reminders.slice(0, 4) : [];
    const summary = dashboardSummary();
    const queue = state.queue || {};
    return `
      <aside class="service-shell-side">
        <section class="service-shell-side-card list-card">
          <div class="service-shell-card-head">
            <h3>Výkon techniků</h3>
            <button type="button" class="service-shell-icon-btn" onclick="window.serviceShell.load(true)" aria-label="Obnovit panel">↗</button>
          </div>
          <p class="service-shell-action-note">Otevřít tým a rozdělení práce</p>
          <div class="service-shell-list">
            ${performance.length ? performance.map((item) => `
              <div class="service-shell-list-row service-shell-clickable-row" tabindex="0" role="button" onclick="window.serviceShell.navigate('team')" onkeydown="if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); window.serviceShell.navigate('team') }">
                <div class="service-shell-tech">
                  <span class="service-shell-tech-avatar">${escape(initials(item?.name || 'T'))}</span>
                  <div>
                    <p class="service-shell-list-title">${escape(item?.name || '-')}</p>
                    <p class="service-shell-list-note">${escape(String(item?.jobs_total || 0))} zakázek</p>
                  </div>
                </div>
                <div class="service-shell-list-value">${escape(String(item?.awaiting_count || 0))} čeká</div>
              </div>
            `).join('') : '<div class="service-shell-empty">Bez výkonových dat techniků.</div>'}
          </div>
        </section>
        <section class="service-shell-side-card list-card">
          <h3>Fronta práce</h3>
          <p class="service-shell-action-note">Otevřít detail zakázek a filtrů</p>
          <div class="service-shell-list">
            <div class="service-shell-list-row service-shell-clickable-row" tabindex="0" role="button" onclick="window.serviceShell.navigate('work-orders')" onkeydown="if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); window.serviceShell.navigate('work-orders') }"><span class="service-shell-list-title">Nové zakázky</span><span class="service-shell-list-value">${escape(String(queue?.new_jobs || queue?.new_work_orders || 0))}</span></div>
            <div class="service-shell-list-row service-shell-clickable-row" tabindex="0" role="button" onclick="window.serviceShell.setKpiFilter('awaiting')" onkeydown="if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); window.serviceShell.setKpiFilter('awaiting') }"><span class="service-shell-list-title">Čeká na schválení</span><span class="service-shell-list-value">${escape(String(queue?.awaiting_approval || 0))}</span></div>
            <div class="service-shell-list-row service-shell-clickable-row" tabindex="0" role="button" onclick="window.serviceShell.navigate('reservations')" onkeydown="if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); window.serviceShell.navigate('reservations') }"><span class="service-shell-list-title">Nové rezervace</span><span class="service-shell-list-value">${escape(String(queue?.new_reservations || summary.new_reservations || 0))}</span></div>
            <div class="service-shell-list-row service-shell-clickable-row" tabindex="0" role="button" onclick="window.serviceShell.navigate('invoices')" onkeydown="if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); window.serviceShell.navigate('invoices') }"><span class="service-shell-list-title">Draft faktury</span><span class="service-shell-list-value">${escape(String(queue?.draft_invoices || summary.draft_invoices || 0))}</span></div>
            <div class="service-shell-list-row service-shell-clickable-row" tabindex="0" role="button" onclick="window.serviceShell.navigate('documents')" onkeydown="if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); window.serviceShell.navigate('documents') }"><span class="service-shell-list-title">Chybí dokumenty</span><span class="service-shell-list-value">${escape(String(queue?.missing_documents || 0))}</span></div>
            <div class="service-shell-list-row service-shell-clickable-row" tabindex="0" role="button" onclick="window.serviceShell.openServiceToolsModal()" onkeydown="if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); window.serviceShell.openServiceToolsModal() }"><span class="service-shell-list-title">Konfliktní data</span><span class="service-shell-list-value">${escape(String(queue?.conflicting_data || 0))}</span></div>
          </div>
        </section>
        <section class="service-shell-side-card list-card">
          <h3>Rezervace a nabídky</h3>
          <div class="service-shell-list">
            <div class="service-shell-list-row"><span class="service-shell-list-title">Čekající nabídky</span><span class="service-shell-list-value">${escape(String(queue?.pending_quotes || summary.pending_quotes || 0))}</span></div>
            ${reservations.map((item) => `
              <div class="service-shell-list-row service-shell-clickable-row" tabindex="0" role="button" onclick="window.serviceShell.openReservationDetailModal(${Number(item?.id || 0)})" onkeydown="if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); window.serviceShell.openReservationDetailModal(${Number(item?.id || 0)}) }">
                <div>
                  <p class="service-shell-list-title">${escape(item?.customer_name || item?.customer_email || '-')}</p>
                  <p class="service-shell-list-note">${escape(item?.vehicle_name || item?.vehicle_label || '-')}</p>
                </div>
                <div class="service-shell-list-value">${escape(formatDate(item?.scheduled_for || item?.reservation_date || item?.starts_at || '-'))}</div>
              </div>
            `).join('') || '<div class="service-shell-empty">Bez nových rezervací.</div>'}
          </div>
        </section>
        <section class="service-shell-side-card list-card">
          <h3>Fakturace a follow-up</h3>
          <div class="service-shell-list">
            <div class="service-shell-list-row"><span class="service-shell-list-title">Celkem faktur</span><span class="service-shell-list-value">${escape(String(summary.invoices_total || 0))}</span></div>
            <div class="service-shell-list-row"><span class="service-shell-list-title">Po termínu</span><span class="service-shell-list-value">${escape(String(summary.overdue_reminders || 0))}</span></div>
            ${reminders.map((item) => `
              <div class="service-shell-list-row service-shell-clickable-row" tabindex="0" role="button" onclick="window.serviceShell.openReminderDetailModal(${Number(item?.id || 0)})" onkeydown="if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); window.serviceShell.openReminderDetailModal(${Number(item?.id || 0)}) }">
                <div>
                  <p class="service-shell-list-title">${escape(item?.customer_name || item?.customer_email || '-')}</p>
                  <p class="service-shell-list-note">${escape(item?.text || '-')}</p>
                </div>
                <div class="service-shell-list-value">${escape(item?.due_date ? formatDate(item.due_date) : '-')}</div>
              </div>
            `).join('') || '<div class="service-shell-empty">Bez follow-upů.</div>'}
          </div>
        </section>
        <section class="service-shell-queue-card">
          <div class="service-shell-card-head">
            <h3>Upozornění</h3>
            <span class="service-shell-kpi-arrow">↗</span>
          </div>
          <div class="service-shell-queue-grid">
            <div class="service-shell-queue-tile service-shell-clickable-row" tabindex="0" role="button" onclick="window.serviceShell.setKpiFilter('awaiting')" onkeydown="if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); window.serviceShell.setKpiFilter('awaiting') }"><span class="service-shell-queue-icon">☑</span><div><strong>${escape(String(queue?.missing_client_consent || 0))}</strong><p>Chybí souhlas klienta</p></div></div>
            <div class="service-shell-queue-tile service-shell-clickable-row" tabindex="0" role="button" onclick="window.serviceShell.navigate('vehicles')" onkeydown="if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); window.serviceShell.navigate('vehicles') }"><span class="service-shell-queue-icon">⦿</span><div><strong>${escape(String(queue?.suspicious_km || 0))}</strong><p>Podezřelé km</p></div></div>
            <div class="service-shell-queue-tile service-shell-clickable-row" tabindex="0" role="button" onclick="window.serviceShell.navigate('work-orders')" onkeydown="if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); window.serviceShell.navigate('work-orders') }"><span class="service-shell-queue-icon">⌁</span><div><strong>${escape(String(queue?.unfinished_jobs || 0))}</strong><p>Nedokončené zakázky</p></div></div>
            <div class="service-shell-queue-tile service-shell-clickable-row" tabindex="0" role="button" onclick="window.serviceShell.openServiceToolsModal()" onkeydown="if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); window.serviceShell.openServiceToolsModal() }"><span class="service-shell-queue-icon">⚑</span><div><strong>${escape(String(queue?.internal_warnings || 0))}</strong><p>Interní varování</p></div></div>
          </div>
          <div class="service-shell-inline-alert">
            <span>Pravý panel se obnovuje automaticky každých 60 sekund.</span>
            <button type="button" class="service-shell-icon-btn" onclick="window.serviceShell.load(true)">×</button>
          </div>
        </section>
      </aside>
    `;
  }

  function workOrdersTableCard(title, subtitle) {
    const items = filteredWorkOrders();
    return `
      <div class="service-shell-card detail-card">
        <div class="service-shell-card-head">
          <div>
            <h3 class="service-shell-card-title">${escape(title)}</h3>
            <p class="service-shell-subtitle">${escape(subtitle)}</p>
          </div>
          <button type="button" class="service-shell-icon-btn" onclick="window.serviceShell.load(true)" aria-label="Obnovit sekci">↗</button>
        </div>
        <div class="service-shell-table-tools">
          <button type="button" class="service-shell-filter-chip ${state.kpiFilter === 'all' ? 'active' : ''}" onclick="window.serviceShell.setKpiFilter('all')">Vše</button>
          <button type="button" class="service-shell-filter-chip ${state.kpiFilter === 'active' ? 'active' : ''}" onclick="window.serviceShell.setKpiFilter('active')">Aktivní</button>
          <button type="button" class="service-shell-filter-chip ${state.kpiFilter === 'awaiting' ? 'active' : ''}" onclick="window.serviceShell.setKpiFilter('awaiting')">Čeká</button>
          <input class="service-shell-search" type="search" placeholder="Search..." value="${escape(state.searchTerm)}" oninput="window.serviceShell.setSearchTerm(this.value)">
          <select class="service-shell-sort" onchange="window.serviceShell.setSortBy(this.value)">
            <option value="due_asc" ${state.sortBy === 'due_asc' ? 'selected' : ''}>Sort by: termín ↑</option>
            <option value="due_desc" ${state.sortBy === 'due_desc' ? 'selected' : ''}>Sort by: termín ↓</option>
            <option value="customer" ${state.sortBy === 'customer' ? 'selected' : ''}>Sort by: zákazník</option>
            <option value="status" ${state.sortBy === 'status' ? 'selected' : ''}>Sort by: stav</option>
          </select>
        </div>
        <div class="service-shell-table-wrap">
          <table class="service-shell-data-table">
            <thead>
              <tr>
                <th>Zákazník</th>
                <th>VIN / SPZ</th>
                <th>Termín</th>
                <th>Zdroj</th>
                <th>Technik</th>
                <th>Stav</th>
              </tr>
            </thead>
            <tbody>${workOrderRows(items)}</tbody>
          </table>
        </div>
      </div>
    `;
  }

  function dashboardSection() {
    return `
      ${pageHead('Dashboard', 'Provozní přehled servisu, priorit a rozpracované práce.')}
      ${kpiCards()}
      ${dashboardOpsStats()}
      <div class="service-shell-layout">
        <div class="service-shell-main">
          ${workOrdersTableCard('Aktivní zakázky', 'Hlavní pracovní plocha servisu nad produkčními daty FastAPI backendu.')}
        </div>
        ${rightPanel()}
      </div>
    `;
  }

  function genericSection(config) {
    return `
      ${pageHead(config.title, config.subtitle)}
      <div class="service-shell-stat-grid">${config.stats}</div>
      <div class="service-shell-layout">
        <div class="service-shell-main">${config.main}</div>
        ${config.side || rightPanel()}
      </div>
    `;
  }

  function renderTable(headers, rows, emptyCols) {
    return `
      <div class="service-shell-card detail-card">
        ${rows.head || ''}
        <div class="service-shell-table-wrap">
          <table class="service-shell-data-table">
            <thead><tr>${headers.map((label) => `<th>${label}</th>`).join('')}</tr></thead>
            <tbody>${rows.body || `<tr><td colspan="${emptyCols}"><div class="service-shell-empty">Bez dat.</div></td></tr>`}</tbody>
          </table>
        </div>
      </div>
    `;
  }

  function clientsSection() {
    const customers = Array.isArray(state.customers) ? state.customers : [];
    const rows = customers.length ? customers.map((customer) => `
      <tr ${clickableAttrs(`window.serviceShell.openCustomerDetailModal(${Number(customer?.customer_id || 0)})`)}>
        <td><strong>${escape(customer?.name || customer?.email || '-')}</strong></td>
        <td>${escape(customer?.email || '-')}</td>
        <td>${escape(customer?.phone || '-')}</td>
        <td>${escape(String(customer?.vehicles_count || customer?.vehicle_count || 0))}</td>
        <td>${escape(customer?.last_activity ? formatDate(customer.last_activity) : '-')}</td>
      </tr>
    `).join('') : '';
    const stats = `
      <article class="service-shell-mini-card summary-card"><h3>Klienti</h3><div class="service-shell-stat-value">${customers.length}</div><p class="service-shell-muted">Aktivní servisní vazby</p></article>
      <article class="service-shell-mini-card summary-card"><h3>Vozidla</h3><div class="service-shell-stat-value">${customers.reduce((sum, item) => sum + Number(item?.vehicles_count || item?.vehicle_count || 0), 0)}</div><p class="service-shell-muted">Sdílená vozidla klientů</p></article>
    `;
    const main = renderTable(
      ['Klient', 'Email', 'Telefon', 'Vozidla', 'Aktivita'],
      {
        head: `
          <div class="service-shell-card-head">
            <div><h3 class="service-shell-card-title">Klienti</h3><p class="service-shell-subtitle">Seznam servisních klientů v jednotném pracovním rozhraní.</p></div>
            <button type="button" class="service-shell-icon-btn" onclick="window.serviceShell.load(true)">↗</button>
          </div>
        `,
        body: rows,
      },
      5
    );
    const side = `
      <aside class="service-shell-side">
        <section class="service-shell-side-card list-card">
          <h3>Poslední aktivita</h3>
          <div class="service-shell-list">
            ${customers.slice(0, 5).map((item) => `
              <div class="service-shell-list-row">
                <div>
                  <p class="service-shell-list-title">${escape(item?.name || item?.email || '-')}</p>
                  <p class="service-shell-list-note">${escape(item?.email || '-')}</p>
                </div>
                <div class="service-shell-list-value">${escape(item?.last_activity ? formatDate(item.last_activity) : '-')}</div>
              </div>
            `).join('') || '<div class="service-shell-empty">Bez aktivit.</div>'}
          </div>
        </section>
        <section class="service-shell-side-card list-card">
          <h3>Akce</h3>
          <div class="service-shell-list">
            <div class="service-shell-list-row"><span class="service-shell-list-title">Otevřít detail klienta</span><span class="service-shell-list-value">Klik na řádek</span></div>
            <div class="service-shell-list-row"><span class="service-shell-list-title">Přidat vozidlo</span><span class="service-shell-list-value">V detailu klienta</span></div>
          </div>
        </section>
      </aside>
    `;
    return genericSection({
      title: 'Klienti',
      subtitle: 'Napojené účty zákazníků, sdílená vozidla a aktivní vazby.',
      stats,
      main,
      side,
    });
  }

  function vehiclesSection() {
    const vehicles = Array.isArray(state.vehicles) ? state.vehicles : [];
    const rows = vehicles.length ? vehicles.slice(0, 80).map((vehicle) => `
      <tr ${clickableAttrs(`window.serviceShell.openVehicleDetailModal(${Number(vehicle?.id || 0)})`)}>
        <td><strong>${escape(vehicle?.vehicle_name || vehicle?.nickname || vehicle?.plate || '-')}</strong></td>
        <td>${escape(vehicle?.vehicle_plate || '-')}</td>
        <td>${escape(vehicle?.customer_name || '-')}</td>
        <td>${escape(vehicle?.last_shared_at ? formatDate(vehicle?.last_shared_at) : '-')}</td>
        <td>${escape('Schváleno')}</td>
      </tr>
    `).join('') : '';
    const stats = `
      <article class="service-shell-mini-card summary-card"><h3>Vozidla</h3><div class="service-shell-stat-value">${vehicles.length}</div><p class="service-shell-muted">Napojená vozidla servisu</p></article>
      <article class="service-shell-mini-card summary-card"><h3>Sdílení</h3><div class="service-shell-stat-value">${vehicles.filter((item) => item?.last_shared_at).length}</div><p class="service-shell-muted">Aktivně schválené přístupy</p></article>
    `;
    const main = renderTable(
      ['Vozidlo', 'SPZ', 'Klient', 'Sdíleno', 'Přístup'],
      {
        head: `
          <div class="service-shell-card-head">
            <div><h3 class="service-shell-card-title">Vozidla</h3><p class="service-shell-subtitle">Seznam vozidel pod servisní správou.</p></div>
            <button type="button" class="service-shell-icon-btn" onclick="window.serviceShell.load(true)">↗</button>
          </div>
        `,
        body: rows,
      },
      5
    );
    const side = `
      <aside class="service-shell-side">
        <section class="service-shell-side-card list-card">
          <h3>Vozidla s přístupem</h3>
          <div class="service-shell-list">
            <div class="service-shell-list-row"><span class="service-shell-list-title">Schválené vazby</span><span class="service-shell-list-value">${vehicles.length}</span></div>
            <div class="service-shell-list-row"><span class="service-shell-list-title">Otevřít detail</span><span class="service-shell-list-value">Klik na řádek</span></div>
          </div>
        </section>
      </aside>
    `;
    return genericSection({
      title: 'Vozidla',
      subtitle: 'Přehled vozidel napojených na servis v jednotném operativním zobrazení.',
      stats,
      main,
      side,
    });
  }

  function workOrdersSection() {
    const summary = dashboardSummary();
    const stats = `
      <article class="service-shell-mini-card summary-card"><h3>Aktivní</h3><div class="service-shell-stat-value">${summary.active_jobs}</div><p class="service-shell-muted">Schválené a rozpracované</p></article>
      <article class="service-shell-mini-card summary-card"><h3>Po termínu</h3><div class="service-shell-stat-value">${summary.overdue}</div><p class="service-shell-muted">Vyžaduje zásah</p></article>
    `;
    return genericSection({
      title: 'Zakázky',
      subtitle: 'Hlavní pracovní fronta servisu se stavem, termíny a odpovědností.',
      stats,
      main: workOrdersTableCard('Zakázky', 'Produkční zakázky v jednotném servisním rozhraní.'),
      side: rightPanel(),
    });
  }

  function documentsSection() {
    const documents = Array.isArray(state.documents) ? state.documents : [];
    const rows = documents.length ? documents.map((doc) => `
      <tr ${clickableAttrs(`window.serviceShell.openDocumentDetailModal(${Number(doc?.id || 0)})`)}>
        <td><strong>${escape(doc?.document_number || doc?.original_filename || '-')}</strong></td>
        <td>${escape(doc?.supplier_name || '-')}</td>
        <td>${escape(doc?.customer_name || doc?.customer_label || '-')}</td>
        <td>${escape(doc?.processing_status || '-')}</td>
        <td>${escape(doc?.created_at ? formatDate(doc.created_at) : '-')}</td>
      </tr>
    `).join('') : '';
    const processed = documents.filter((item) => String(item?.processing_status || '').toLowerCase() === 'processed').length;
    const stats = `
      <article class="service-shell-mini-card summary-card"><h3>Dokumenty</h3><div class="service-shell-stat-value">${documents.length}</div><p class="service-shell-muted">Načtené servisní doklady</p></article>
      <article class="service-shell-mini-card summary-card"><h3>Validace</h3><div class="service-shell-stat-value">${processed}</div><p class="service-shell-muted">Zpracované vstupy</p></article>
    `;
    const main = renderTable(
      ['Doklad', 'Dodavatel', 'Klient', 'Stav', 'Vloženo'],
      {
        head: `
          <div class="service-shell-card-head">
            <div><h3 class="service-shell-card-title">Dokumenty</h3><p class="service-shell-subtitle">Dokumentový modul servisu ve stejném systému karet a tabulek.</p></div>
            <button type="button" class="service-shell-icon-btn" onclick="window.serviceShell.load(true)">↗</button>
          </div>
        `,
        body: rows,
      },
      5
    );
    const side = `
      <aside class="service-shell-side">
        <section class="service-shell-side-card">
          <h3>Quick actions</h3>
          <div class="service-shell-list">
            <div class="service-shell-list-row"><span class="service-shell-list-title">Čeká na kontrolu</span><span class="service-shell-list-value">${documents.length - processed}</span></div>
            <div class="service-shell-list-row"><span class="service-shell-list-title">Se záznamem</span><span class="service-shell-list-value">${documents.filter((item) => Number(item?.auto_created_service_record_id || 0) > 0).length}</span></div>
          </div>
        </section>
        <section class="service-shell-side-card">
          <h3>Akce</h3>
          <div class="service-shell-list">
            <div class="service-shell-list-row"><span class="service-shell-list-title">Otevřít detail dokumentu</span><span class="service-shell-list-value">Klik na řádek</span></div>
            <div class="service-shell-list-row"><span class="service-shell-list-title">Vytvořit zakázku</span><span class="service-shell-list-value">V detailu dokladu</span></div>
          </div>
        </section>
      </aside>
    `;
    return genericSection({
      title: 'Dokumenty',
      subtitle: 'Doklady, extrakce, validace a návaznost na servisní evidenci.',
      stats,
      main,
      side,
    });
  }

  function invoicesSection() {
    const invoices = Array.isArray(state.invoices) ? state.invoices : [];
    const rows = invoices.length
      ? invoices.map((inv) => `
      <tr ${clickableAttrs(`window.serviceShell.openServiceInvoiceDetailModal(${Number(inv?.id || 0)})`)}>
        <td><strong>${escape(inv?.invoice_number || 'Koncept')}</strong></td>
        <td>${escape(String(inv?.status_label || inv?.status || '-'))}</td>
        <td>${escape(String(inv?.total ?? '-'))} ${escape(inv?.currency || 'CZK')}</td>
        <td>${escape(inv?.customer_label || (inv?.customer_id != null ? `Klient #${inv.customer_id}` : '-'))}</td>
        <td>
          <button type="button" class="btn btn-secondary" onclick="event.stopPropagation(); window.serviceShell.openServiceInvoicePdf(${Number(inv?.id || 0)})">PDF</button>
        </td>
      </tr>
    `).join('')
      : '';
    const stats = `
      <article class="service-shell-mini-card summary-card"><h3>Faktury</h3><div class="service-shell-stat-value">${invoices.length}</div><p class="service-shell-muted">Servisní faktury tohoto účtu</p></article>
    `;
    const main = renderTable(
      ['Číslo / stav', 'Stav', 'Celkem', 'Klient', 'Akce'],
      {
        head: `
          <div class="service-shell-card-head">
            <div><h3 class="service-shell-card-title">Servisní faktury</h3><p class="service-shell-subtitle">Draft / vystaveno / zrušeno — PDF vyžaduje přihlášení (Bearer).</p></div>
            <div class="service-shell-modal-actions">
              <button type="button" class="btn btn-primary" onclick="window.serviceShell.openCreateInvoiceModal()">Nová draft faktura</button>
              <button type="button" class="service-shell-icon-btn" onclick="window.serviceShell.load(true)">↗</button>
            </div>
          </div>
        `,
        body: rows,
      },
      5,
    );
    const side = `
      <aside class="service-shell-side">
        <section class="service-shell-side-card">
          <h3>Workflow</h3>
          <div class="service-shell-list">
            <div class="service-shell-list-row"><span class="service-shell-list-title">Vytvořit draft</span><span class="service-shell-list-value">Tlačítko v hlavičce</span></div>
            <div class="service-shell-list-row"><span class="service-shell-list-title">Upravit draft</span><span class="service-shell-list-value">Detail faktury</span></div>
            <div class="service-shell-list-row"><span class="service-shell-list-title">Vystavit / PDF</span><span class="service-shell-list-value">Detail faktury</span></div>
          </div>
        </section>
      </aside>
    `;
    return genericSection({
      title: 'Faktury',
      subtitle: 'Servisní faktury Fáze 1 — tenantová izolace a číslování při vystavení.',
      stats,
      main,
      side,
    });
  }

  function reservationsSection() {
    const reservations = Array.isArray(state.reservations) ? state.reservations : [];
    const rows = reservations.length ? reservations.map((reservation) => `
      <tr ${clickableAttrs(`window.serviceShell.openReservationDetailModal(${Number(reservation?.id || 0)})`)}>
        <td><strong>${escape(reservation?.customer_name || reservation?.customer_email || '-')}</strong></td>
        <td>${escape(reservation?.vehicle_name || reservation?.vehicle_label || reservation?.vehicle_plate || '-')}</td>
        <td>${escape(formatDate(reservation?.scheduled_for || reservation?.reservation_date || reservation?.starts_at || reservation?.created_at || '-'))}</td>
        <td>${escape(reservation?.status || '-')}</td>
        <td>${escape(reservation?.note || reservation?.service_note || '-')}</td>
      </tr>
    `).join('') : '';
    const stats = `
      <article class="service-shell-mini-card summary-card"><h3>Rezervace</h3><div class="service-shell-stat-value">${reservations.length}</div><p class="service-shell-muted">Celkový počet rezervací</p></article>
      <article class="service-shell-mini-card summary-card"><h3>Dnes</h3><div class="service-shell-stat-value">${reservations.filter((item) => toDateKey(item?.scheduled_for || item?.reservation_date || item?.starts_at) === todayKey()).length}</div><p class="service-shell-muted">Příjezdy během dneška</p></article>
    `;
    const main = renderTable(
      ['Zákazník', 'Vozidlo', 'Termín', 'Stav', 'Poznámka'],
      {
        head: `
          <div class="service-shell-card-head">
            <div><h3 class="service-shell-card-title">Rezervace</h3><p class="service-shell-subtitle">Seznam rezervací a stavů ve stejném servisním systému.</p></div>
            <button type="button" class="service-shell-icon-btn" onclick="window.serviceShell.load(true)">↗</button>
          </div>
        `,
        body: rows,
      },
      5
    );
    const side = `
      <aside class="service-shell-side">
        <section class="service-shell-side-card">
          <h3>Dnešní příjezdy</h3>
          <div class="service-shell-list">
            ${reservations.slice(0, 5).map((item) => `
              <div class="service-shell-list-row">
                <div>
                  <p class="service-shell-list-title">${escape(item?.customer_name || item?.customer_email || '-')}</p>
                  <p class="service-shell-list-note">${escape(item?.vehicle_name || item?.vehicle_label || '-')}</p>
                </div>
                <div class="service-shell-list-value">${escape(formatDate(item?.scheduled_for || item?.reservation_date || item?.starts_at || '-'))}</div>
              </div>
            `).join('') || '<div class="service-shell-empty">Bez dnešních příjezdů.</div>'}
          </div>
        </section>
        <section class="service-shell-side-card">
          <h3>Akce</h3>
          <div class="service-shell-list">
            <div class="service-shell-list-row"><span class="service-shell-list-title">Otevřít detail rezervace</span><span class="service-shell-list-value">Klik na řádek</span></div>
            <div class="service-shell-list-row"><span class="service-shell-list-title">Založit zakázku</span><span class="service-shell-list-value">Z detailu rezervace</span></div>
          </div>
        </section>
      </aside>
    `;
    return genericSection({
      title: 'Rezervace',
      subtitle: 'Příjmy vozidel, nepotvrzené rezervace a čekající požadavky.',
      stats,
      main,
      side,
    });
  }

  function remindersSection() {
    const reminders = Array.isArray(state.reminders) ? state.reminders : [];
    const rows = reminders.length ? reminders.map((item) => `
      <tr ${clickableAttrs(`window.serviceShell.openReminderDetailModal(${Number(item?.id || 0)})`)}>
        <td><strong>${escape(item?.customer_name || item?.customer_email || '-')}</strong></td>
        <td>${escape(item?.vehicle_label || 'Obecná připomínka')}</td>
        <td>${escape(item?.text || '-')}</td>
        <td>${escape(item?.due_date ? formatDate(item.due_date) : '-')}</td>
        <td>${escape(item?.is_completed ? 'Dokončeno' : 'Aktivní')}</td>
      </tr>
    `).join('') : '';
    const stats = `
      <article class="service-shell-mini-card summary-card"><h3>Připomínky</h3><div class="service-shell-stat-value">${reminders.length}</div><p class="service-shell-muted">Servisní follow-upy</p></article>
      <article class="service-shell-mini-card summary-card"><h3>Po termínu</h3><div class="service-shell-stat-value">${reminders.filter((item) => !item?.is_completed && toDateKey(item?.due_date) && toDateKey(item?.due_date) < todayKey()).length}</div><p class="service-shell-muted">Kritické termíny</p></article>
    `;
    const main = renderTable(
      ['Zákazník', 'Vozidlo', 'Text', 'Termín', 'Stav'],
      {
        head: `
          <div class="service-shell-card-head">
            <div><h3 class="service-shell-card-title">Připomínky</h3><p class="service-shell-subtitle">Tabulka připomínek ve stejném servisním systému.</p></div>
            <div class="service-shell-modal-actions">
              <button type="button" class="btn btn-primary" onclick="window.serviceShell.openCreateReminderModal()">Nová připomínka</button>
              <button type="button" class="service-shell-icon-btn" onclick="window.serviceShell.load(true)">↗</button>
            </div>
          </div>
        `,
        body: rows,
      },
      5
    );
    const side = `
      <aside class="service-shell-side">
        <section class="service-shell-side-card">
          <h3>Follow-upy</h3>
          <div class="service-shell-list">
            ${reminders.slice(0, 5).map((item) => `
              <div class="service-shell-list-row">
                <div>
                  <p class="service-shell-list-title">${escape(item?.customer_name || item?.customer_email || '-')}</p>
                  <p class="service-shell-list-note">${escape(item?.text || '-')}</p>
                </div>
                <div class="service-shell-list-value">${escape(item?.due_date ? formatDate(item.due_date) : '-')}</div>
              </div>
            `).join('') || '<div class="service-shell-empty">Bez follow-upů.</div>'}
          </div>
        </section>
        <section class="service-shell-side-card">
          <h3>Akce</h3>
          <div class="service-shell-list">
            <div class="service-shell-list-row"><span class="service-shell-list-title">Vytvořit připomínku</span><span class="service-shell-list-value">Tlačítko v hlavičce</span></div>
            <div class="service-shell-list-row"><span class="service-shell-list-title">Otevřít detail připomínky</span><span class="service-shell-list-value">Klik na řádek</span></div>
            <div class="service-shell-list-row"><span class="service-shell-list-title">Uložit změny</span><span class="service-shell-list-value">V detailu připomínky</span></div>
          </div>
        </section>
      </aside>
    `;
    return genericSection({
      title: 'Připomínky',
      subtitle: 'Tabulka reminderů, follow-upů a kritických termínů servisu.',
      stats,
      main,
      side,
    });
  }

  function teamSection() {
    const performance = Array.isArray(state.performance) ? state.performance : [];
    const rows = performance.length ? performance.map((item) => `
      <tr>
        <td><strong>${escape(item?.name || '-')}</strong></td>
        <td>${escape(String(item?.jobs_total || 0))}</td>
        <td>${escape(String(item?.awaiting_count || 0))}</td>
        <td>${escape(String(item?.overdue_count || 0))}</td>
      </tr>
    `).join('') : '';
    const profile = currentProfile();
    const stats = `
      <article class="service-shell-mini-card summary-card"><h3>Tým</h3><div class="service-shell-stat-value">${performance.length}</div><p class="service-shell-muted">Aktivní technici</p></article>
      <article class="service-shell-mini-card summary-card"><h3>Profil</h3><div class="service-shell-stat-value">${escape(initials(profile?.name || profile?.email || window.currentUser?.email || 'SA'))}</div><p class="service-shell-muted">${escape(profile?.email || window.currentUser?.email || '-')}</p></article>
    `;
    const main = renderTable(
      ['Technik', 'Zakázky', 'Čeká', 'Po termínu'],
      {
        head: `
          <div class="service-shell-card-head">
            <div><h3 class="service-shell-card-title">Tým</h3><p class="service-shell-subtitle">Výkon techniků a identita přihlášeného servisního účtu.</p></div>
            <button type="button" class="service-shell-icon-btn" onclick="window.serviceShell.load(true)">↗</button>
          </div>
        `,
        body: rows,
      },
      4
    );
    const side = `
      <aside class="service-shell-side">
        <section class="service-shell-side-card">
          <h3>Přihlášený účet</h3>
          <div class="service-shell-list">
            <div class="service-shell-list-row">
              <div>
                <p class="service-shell-list-title">${escape(profile?.name || window.currentUser?.name || 'Servisní účet')}</p>
                <p class="service-shell-list-note">${escape(profile?.email || window.currentUser?.email || '-')}</p>
              </div>
              <div class="service-shell-list-value">${escape(String(profile?.role || window.currentUser?.role || 'service_account').replace(/_/g, ' '))}</div>
            </div>
          </div>
        </section>
        <section class="service-shell-side-card">
          <h3>Rozdělení práce</h3>
          <div class="service-shell-list">
            ${performance.slice(0, 4).map((item) => `
              <div class="service-shell-list-row">
                <div>
                  <p class="service-shell-list-title">${escape(item?.name || '-')}</p>
                  <p class="service-shell-list-note">${escape(String(item?.jobs_total || 0))} zakázek</p>
                </div>
                <div class="service-shell-list-value">${escape(String(item?.awaiting_count || 0))} čeká</div>
              </div>
            `).join('') || '<div class="service-shell-empty">Bez rozdělené práce.</div>'}
          </div>
        </section>
        <section class="service-shell-side-card">
          <h3>Fronta týmu</h3>
          <div class="service-shell-list">
            <div class="service-shell-list-row"><span class="service-shell-list-title">Nové zakázky</span><span class="service-shell-list-value">${escape(String(state.queue?.new_jobs || state.queue?.new_work_orders || 0))}</span></div>
            <div class="service-shell-list-row"><span class="service-shell-list-title">Po termínu</span><span class="service-shell-list-value">${escape(String(state.summary?.overdue || 0))}</span></div>
          </div>
        </section>
      </aside>
    `;
    return genericSection({
      title: 'Tým',
      subtitle: 'Seznam techniků, výkon, rozdělení práce a fronta úkolů.',
      stats,
      main,
      side,
    });
  }

  function loadingShell() {
    return `
      ${pageHead('Dashboard', 'Načítám servisní pracovní prostor...')}
      <div class="service-shell-kpis">
        <div class="service-shell-skeleton"></div>
        <div class="service-shell-skeleton"></div>
        <div class="service-shell-skeleton"></div>
        <div class="service-shell-skeleton"></div>
      </div>
      <div class="service-shell-layout">
        <div class="service-shell-main"><div class="service-shell-skeleton" style="min-height: 520px;"></div></div>
        <div class="service-shell-side"><div class="service-shell-skeleton" style="min-height: 520px;"></div></div>
      </div>
    `;
  }

  function currentSectionHtml() {
    if (state.loading) return loadingShell();
    if (state.activeSection === 'clients') return clientsSection();
    if (state.activeSection === 'vehicles') return vehiclesSection();
    if (state.activeSection === 'work-orders') return workOrdersSection();
    if (state.activeSection === 'documents') return documentsSection();
    if (state.activeSection === 'invoices') return invoicesSection();
    if (state.activeSection === 'reservations') return reservationsSection();
    if (state.activeSection === 'reminders') return remindersSection();
    if (state.activeSection === 'team') return teamSection();
    return dashboardSection();
  }

  function currentSectionHtmlSafe() {
    try {
      return currentSectionHtml();
    } catch (error) {
      console.error('[SERVICE_SHELL] currentSectionHtml failed:', error);
      return `
        <div class="service-shell-page-head">
          <h1>Chyba zobrazení sekce</h1>
          <p class="service-shell-subtitle">Zkuste jinou záložku v menu nebo obnovte data. Detail chyby je v konzoli (F12).</p>
        </div>
        <div class="service-shell-inline-error" style="margin:16px 0;">${escape(String(error?.message || error || 'Neznámá chyba'))}</div>
        <button type="button" class="btn btn-primary" onclick="window.serviceShell.navigate('dashboard'); window.serviceShell.load(true);">Zpět na dashboard</button>
      `;
    }
  }

  function renderFatalShellFallback(error) {
    const msg = escape(String(error?.message || error || 'Neznámá chyba'));
    return `
      <div class="service-shell-root" data-service-shell="root" style="min-height:100vh;padding:24px;background:#111315;color:#f5f7fb;">
        <div class="service-shell-app-shell" style="max-width:640px;margin:0 auto;">
          <h1 style="font-size:1.25rem;margin:0 0 12px;">${escape(getAppDisplayName())} — servisní režim</h1>
          <p style="color:#fca5a5;margin:0 0 8px;">Rozhraní se nepodařilo vykreslit. Podrobnosti v konzoli prohlížeče.</p>
          <pre style="white-space:pre-wrap;font-size:12px;opacity:0.85;border:1px solid rgba(255,255,255,0.12);padding:12px;border-radius:8px;">${msg}</pre>
          <div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:16px;">
            <button type="button" class="btn btn-primary" onclick="window.location.reload()">Obnovit stránku</button>
            <button type="button" class="btn btn-secondary" onclick="window.serviceShell && window.serviceShell.load && window.serviceShell.load(true)">Znovu načíst data</button>
          </div>
        </div>
      </div>
    `;
  }

  function render() {
    if (!state.mounted) return;
    const root = getRoot();
    try {
      const header = shellHeader();
      const banner = activeVehicleBanner();
      const section = currentSectionHtmlSafe();
      root.innerHTML = `
      <div class="service-shell-root ${isMobileViewport() ? 'service-shell-root--mobile' : ''}" data-service-shell="root">
        <div class="service-shell-app-shell">
          ${header}
          ${banner}
          ${section}
        </div>
      </div>
    `;
    } catch (error) {
      console.error('[SERVICE_SHELL] render failed:', error);
      try {
        root.innerHTML = renderFatalShellFallback(error);
      } catch (e2) {
        console.error('[SERVICE_SHELL] fatal shell fallback failed:', e2);
        root.innerHTML = '';
        root.textContent = 'Servisní workspace: kritická chyba vykreslení. Obnovte stránku.';
      }
    }
  }

  window.serviceShell = {
    init,
    mount,
    unmount,
    load,
    render,
    navigate,
    toggleTheme,
    setTheme,
    setSearchTerm,
    setSortBy,
    setKpiFilter,
    toggleAccountMenu,
    toggleMobileNav,
    closeAccountMenu,
    openAccountSettings,
    openModal,
    closeModal,
    handleModalBackdrop,
    runModalAction,
    reloadModalData,
    logout,
    openServiceToolsModal,
    searchCustomers,
    linkCustomerById,
    sendInvitationFromSearch,
    searchVehicles,
    requestVehicleAccess,
    openVehicleFromLookup,
    openVehicleFromLookupByIndex,
    openCreateWorkOrderFromLookup,
    openCreateWorkOrderFromLookupByIndex,
    openCreateWorkOrderModal,
    populateCreateVehicleOptions,
    submitCreateWorkOrderModal,
    openWorkOrderDetailModal,
    submitWorkOrderDetailUpdate,
    openAddVehicleModal,
    submitAddVehicleModal,
    appendWorkItemDraft,
    appendQuoteItemRow,
    appendInvoiceLineRow,
    openFirstRecordForQuote,
    triggerServiceRecordPhotoPicker,
    handleServiceRecordPhotoSelection,
    openServiceRecordModal,
    submitServiceRecordModal,
    openQuoteModal,
    createQuoteFromRecord,
    shareQuotePdf,
    copyQuotePublicLinkByUrl,
    copyQuotePublicLink,
    openQuotePublicLink,
    emailQuotePublicLink,
    shareQuoteSmsTemplate,
    openCreateReminderModal,
    submitCreateReminderModal,
    openCustomerDetailModal,
    setVehicleQuoteListPrefs,
    openVehicleDetailModal,
    openVehicleQrModal,
    openPublicHistoryFromModal,
    sharePublicHistoryFromModal,
    copyPublicHistoryFromModal,
    openDocumentDetailModal,
    openReservationDetailModal,
    openReminderDetailModal,
    populateCustomerVehicleSelect,
    openCreateInvoiceModal,
    submitCreateInvoiceModal,
    openServiceInvoicePdf,
    openServiceInvoiceDetailModal,
    issueServiceInvoiceFromModal,
    cancelServiceInvoiceFromModal,
    setCustomerSearchQuery,
    setVehicleLookupQuery,
    state,
  };

  window.renderServiceWorkspace = function () {
    if (isServiceRole()) {
      return render();
    }
    if (typeof originalRenderServiceWorkspace === 'function') {
      return originalRenderServiceWorkspace.apply(this, arguments);
    }
  };

  window.loadServiceWorkspace = function (force = true, silent = false) {
    if (isServiceRole()) {
      return load(force, silent);
    }
    if (typeof originalLoadServiceWorkspace === 'function') {
      return originalLoadServiceWorkspace.apply(this, arguments);
    }
  };

  window.toggleServiceDashboardTheme = function () {
    if (isServiceRole()) {
      return toggleTheme();
    }
  };

  window.handleServiceDashboardNav = function (target) {
    if (isServiceRole()) {
      return navigate(target);
    }
  };

  window.loadHomeDashboard = function () {
    if (isServiceRole()) {
      state.activeSection = 'dashboard';
      return mount();
    }
    if (typeof originalLoadHomeDashboard === 'function') {
      return originalLoadHomeDashboard.apply(this, arguments);
    }
  };

  window.switchTab = function (tab, options = {}) {
    if (isServiceRole()) {
      const mapped = mapSection(tab);
      if (mapped) {
        return navigate(mapped, options);
      }
    }
    if (typeof originalSwitchTab === 'function') {
      return originalSwitchTab.call(this, tab, options);
    }
  };

  window.showDashboard = function () {
    if (isServiceRole()) {
      return mount();
    }
    if (typeof originalShowDashboard === 'function') {
      return originalShowDashboard.apply(this, arguments);
    }
  };

  window.showLogin = function () {
    unmount();
    if (typeof originalShowLogin === 'function') {
      return originalShowLogin.apply(this, arguments);
    }
  };

  window.openServiceDashboardCreateModal = function () {
    if (isServiceRole()) {
      return openCreateWorkOrderModal();
    }
    if (typeof originalOpenServiceDashboardCreateModal === 'function') {
      return originalOpenServiceDashboardCreateModal.apply(this, arguments);
    }
  };

  window.openServiceDashboardWorkOrderDetail = function () {
    if (isServiceRole()) {
      return openWorkOrderDetailModal.apply(this, arguments);
    }
    if (typeof originalOpenServiceDashboardWorkOrderDetail === 'function') {
      return originalOpenServiceDashboardWorkOrderDetail.apply(this, arguments);
    }
  };

  window.submitServiceDashboardDetailUpdate = function () {
    if (isServiceRole()) {
      return submitWorkOrderDetailUpdate.apply(this, arguments);
    }
    if (typeof originalSubmitServiceDashboardDetailUpdate === 'function') {
      return originalSubmitServiceDashboardDetailUpdate.apply(this, arguments);
    }
  };

  window.openServiceAddVehicleForCustomer = function (customerId) {
    if (isServiceRole()) {
      return openAddVehicleModal(customerId);
    }
    if (typeof originalOpenServiceAddVehicleForCustomer === 'function') {
      return originalOpenServiceAddVehicleForCustomer.apply(this, arguments);
    }
  };
})();
