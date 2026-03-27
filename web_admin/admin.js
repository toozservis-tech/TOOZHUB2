// ============================================
// TOOZ HUB 2 - ADMIN DASHBOARD
// Kompletní refaktoring s plně funkčním CRUD
// ============================================

const API_BASE = "";
const ADMIN_TOKEN_KEY = 'adminAccessToken';
const LEGACY_TOKEN_KEY = 'accessToken';
const ADMIN_ROLE_KEY = 'adminRole';

// Globální proměnné
let authToken = null;
let currentSection = "overview";
let currentAdminRole = null;
const LIST_FETCH_PAGE_SIZE = 50;
const USERS_RENDER_PAGE_SIZE = 24;
let usersAllCache = [];
let usersFilteredCache = [];
let usersCurrentPage = 1;
let userDetailData = null;
let userDetailActivePanel = 'vehicles';
let userDetailReturnContext = null;
const ADMIN_VIEW_SECTIONS = ['users', 'vehicles', 'services', 'records'];
const ADMIN_VIEW_MODES = ['grid', 'list', 'compact'];
const adminViewState = {};
const recordFormOptionsState = {
  users: [],
  vehicles: [],
};
let controlCenterCurrentInsight = null;
const controlCenterDataState = {
  users: [],
  health: null,
  payments: null,
  presence: null,
  security: null,
  backups: null,
  apiMonitor: null,
  webhookMonitor: null,
  storage: null,
  storageCleanupPreview: null,
  email: null,
  jobs: null,
  notifications: null,
  audit: null,
  systemLogs: null,
  insight: null,
  command: null,
};
const controlCenterPaymentsFilters = {
  env: 'all',
  state: 'all',
  query: '',
};
let systemCapabilities = {};

// ============================================
// AUTH & TOKEN MANAGEMENT
// ============================================

function getAuthToken() {
  if (authToken) return authToken;
  authToken = localStorage.getItem(ADMIN_TOKEN_KEY) || localStorage.getItem(LEGACY_TOKEN_KEY);
  if (authToken) return authToken;
  const urlParams = new URLSearchParams(window.location.search);
  authToken = urlParams.get('token');
  if (authToken) {
    localStorage.setItem(ADMIN_TOKEN_KEY, authToken);
    return authToken;
  }
  return null;
}

function setAuthToken(token) {
  authToken = token;
  localStorage.setItem(ADMIN_TOKEN_KEY, token);
}

function setAdminRole(role) {
  currentAdminRole = role || null;
  if (currentAdminRole) {
    localStorage.setItem(ADMIN_ROLE_KEY, currentAdminRole);
  } else {
    localStorage.removeItem(ADMIN_ROLE_KEY);
  }
  updateControlCenterVisibility();
}

function getStoredAdminRole() {
  if (currentAdminRole) return currentAdminRole;
  currentAdminRole = localStorage.getItem(ADMIN_ROLE_KEY) || null;
  return currentAdminRole;
}

function clearAuthToken() {
  const currentToken = authToken;
  const legacyToken = localStorage.getItem(LEGACY_TOKEN_KEY);
  authToken = null;
  localStorage.removeItem(ADMIN_TOKEN_KEY);
  if (legacyToken && currentToken && legacyToken === currentToken) {
    localStorage.removeItem(LEGACY_TOKEN_KEY);
  }
  setAdminRole(null);
}

// ============================================
// CENTRÁLNÍ API HELPER
// ============================================

function showGlobalError(message) {
  const errorEl = document.getElementById('global-error');
  if (errorEl) {
    errorEl.textContent = message;
    errorEl.classList.remove('hidden');
    setTimeout(() => {
      errorEl.classList.add('hidden');
    }, 5000);
  }
}

function hideGlobalError() {
  const errorEl = document.getElementById('global-error');
  if (errorEl) {
    errorEl.classList.add('hidden');
  }
}

function showSuccess(message) {
  const errorEl = document.getElementById('global-error');
  if (errorEl) {
    errorEl.textContent = message;
    errorEl.classList.add('success');
    errorEl.classList.remove('hidden');
    setTimeout(() => {
      errorEl.classList.add('hidden');
      errorEl.classList.remove('success');
    }, 3000);
  }
}

async function apiRequest(method, path, body = null) {
  const token = getAuthToken();
  const headers = {
    "Accept": "application/json",
  };
  
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  
  if (body && (method === "POST" || method === "PATCH" || method === "PUT")) {
    headers["Content-Type"] = "application/json";
  }
  
  try {
    const options = {
      method,
      headers,
      credentials: 'include' // Pro CORS cookies
    };
    
    if (body) {
      options.body = JSON.stringify(body);
    }
    
    const url = API_BASE + path;
    const res = await fetch(url, options);
    
    // Pokud je 401 Unauthorized, zkusit přesměrovat na login
    if (res.status === 401) {
      clearAuthToken();
      showGlobalError('Session vypršela. Prosím přihlaste se znovu.');
      setTimeout(() => {
        showLoginScreen();
      }, 2000);
      throw new Error('Unauthorized');
    }
    
    if (!res.ok) {
      let errorData;
      try {
        errorData = await res.json();
      } catch {
        errorData = { detail: res.statusText || `HTTP ${res.status}` };
      }
      throw new Error(errorData.detail || `Request failed: ${res.status} ${res.statusText}`);
    }
    
    // Pokud response je prázdný (204 No Content), vrátit null
    if (res.status === 204) {
      return null;
    }
    
    return await res.json();
  } catch (error) {
    // Pokud je to network error (Failed to fetch), zobrazit uživatelsky přívětivou zprávu
    if (error.message === 'Failed to fetch' || error.name === 'TypeError') {
      const friendlyError = 'Nelze se připojit k serveru. Zkontrolujte, zda server běží na ' + (API_BASE || window.location.origin);
      console.error(`API Error [${method} ${path}]:`, error);
      showGlobalError(friendlyError);
      throw new Error(friendlyError);
    }
    
    console.error(`API Error [${method} ${path}]:`, error);
    showGlobalError(error.message || `Chyba při ${method} ${path}`);
    throw error;
  }
}

async function loadSystemCapabilitiesAdmin() {
  try {
    const data = await apiRequest('GET', '/api/v1/system/capabilities');
    systemCapabilities = (data && data.modules) || {};
  } catch (error) {
    console.warn('Capabilities unavailable:', error?.message || error);
    systemCapabilities = {};
  }
}

function withQueryParams(path, params = {}) {
  const [base, query = ""] = path.split("?");
  const search = new URLSearchParams(query);
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null) {
      search.set(key, String(value));
    }
  });
  const serialized = search.toString();
  return serialized ? `${base}?${serialized}` : base;
}

async function fetchAllList(path, pageSize = LIST_FETCH_PAGE_SIZE, maxPages = 200) {
  const allItems = [];
  let offset = 0;

  for (let page = 0; page < maxPages; page += 1) {
    const response = await apiRequest('GET', withQueryParams(path, { limit: pageSize, offset }));
    const items = Array.isArray(response) ? response : (Array.isArray(response?.records) ? response.records : []);

    allItems.push(...items);

    if (items.length < pageSize) {
      break;
    }

    offset += items.length;
  }

  return allItems;
}

function escapeHtml(value) {
  if (value === null || value === undefined) return '';
  const div = document.createElement('div');
  div.textContent = String(value);
  return div.innerHTML;
}

function formatDateTime(value, fallback = '-') {
  if (!value) return fallback;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return fallback;
  return date.toLocaleString('cs-CZ');
}

function formatDate(value, fallback = '-') {
  if (!value) return fallback;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return fallback;
  return date.toLocaleDateString('cs-CZ');
}

function formatMoney(value, fallback = '-') {
  const num = Number(value);
  if (!Number.isFinite(num)) return fallback;
  return `${num.toLocaleString('cs-CZ')} Kč`;
}

function getAdminSectionContainer(section) {
  return document.getElementById(`${section}-cards-container`);
}

function getStoredViewMode(section) {
  const saved = localStorage.getItem(`admin:view:${section}`);
  return ADMIN_VIEW_MODES.includes(saved) ? saved : 'grid';
}

function applySectionViewMode(section) {
  const container = getAdminSectionContainer(section);
  const mode = adminViewState[section] || 'grid';
  const switchEl = document.querySelector(`.view-switch[data-section="${section}"]`);

  if (container) {
    container.classList.remove('view-grid', 'view-list', 'view-compact');
    container.classList.add(`view-${mode}`);
  }

  if (switchEl) {
    switchEl.querySelectorAll('.view-btn').forEach((btn) => {
      btn.classList.toggle('active', btn.dataset.view === mode);
    });
  }
}

function setSectionViewMode(section, mode) {
  if (!ADMIN_VIEW_SECTIONS.includes(section)) return;
  if (!ADMIN_VIEW_MODES.includes(mode)) return;
  adminViewState[section] = mode;
  localStorage.setItem(`admin:view:${section}`, mode);
  if (section === 'users') {
    renderUsersList();
    return;
  }
  applySectionViewMode(section);
}

function initSectionViewModes() {
  ADMIN_VIEW_SECTIONS.forEach((section) => {
    adminViewState[section] = getStoredViewMode(section);
    applySectionViewMode(section);
  });
}

function getOnlineState(user) {
  if (typeof user?.is_online === 'boolean') {
    return user.is_online;
  }
  if (!user?.last_seen_at) {
    return false;
  }
  const lastSeen = new Date(user.last_seen_at);
  if (Number.isNaN(lastSeen.getTime())) {
    return false;
  }
  const ageSec = (Date.now() - lastSeen.getTime()) / 1000;
  return ageSec <= 300;
}

function canAccessControlCenter() {
  const role = (getStoredAdminRole() || '').toLowerCase();
  return role === 'developer_admin';
}

function updateControlCenterVisibility() {
  const navItem = document.querySelector('.nav-item[data-section="control-center"]');
  const section = document.getElementById('section-control-center');
  const allowed = canAccessControlCenter();

  if (navItem) {
    navItem.classList.toggle('hidden', !allowed);
  }
  if (section && !allowed) {
    section.classList.remove('active');
  }
  if (!allowed && currentSection === 'control-center') {
    switchSection('overview');
  }
}

async function resolveCurrentAdminRole() {
  if (getStoredAdminRole()) {
    updateControlCenterVisibility();
    return;
  }
  try {
    const me = await apiRequest('GET', '/user/me');
    setAdminRole(me?.role || null);
  } catch (error) {
    // Role není k dispozici - neblokovat dashboard.
    updateControlCenterVisibility();
  }
}

// ============================================
// SECTION NAVIGATION
// ============================================

function initNavigation() {
  const navItems = document.querySelectorAll('.nav-item[data-section]');
  
  navItems.forEach((item) => {
    item.addEventListener('click', () => {
      const section = item.getAttribute('data-section');
      switchSection(section);
    });
  });

  initSummaryNavigation();
  
  // Načíst data pro aktivní sekci
  const activeItem = document.querySelector('.nav-item.active');
  if (activeItem) {
    const section = activeItem.getAttribute('data-section');
    if (section) {
      currentSection = section;
      loadSectionData(section);
    }
  }
}

function isAdminMobileViewport() {
  return window.matchMedia('(max-width: 1024px)').matches;
}

function openAdminMobileNav() {
  if (!isAdminMobileViewport()) return;
  const sidebar = document.getElementById('adminSidebar');
  const overlay = document.getElementById('admin-mobile-nav-overlay');
  const toggle = document.getElementById('admin-mobile-menu-toggle');

  sidebar?.classList.add('mobile-open');
  if (overlay) {
    overlay.classList.remove('hidden');
    overlay.classList.add('active');
  }
  document.body.classList.add('admin-mobile-nav-open');
  if (toggle) {
    toggle.setAttribute('aria-expanded', 'true');
  }
}

function closeAdminMobileNav() {
  const sidebar = document.getElementById('adminSidebar');
  const overlay = document.getElementById('admin-mobile-nav-overlay');
  const toggle = document.getElementById('admin-mobile-menu-toggle');

  sidebar?.classList.remove('mobile-open');
  if (overlay) {
    overlay.classList.remove('active');
    overlay.classList.add('hidden');
  }
  document.body.classList.remove('admin-mobile-nav-open');
  if (toggle) {
    toggle.setAttribute('aria-expanded', 'false');
  }
}

function toggleAdminMobileNav() {
  if (!isAdminMobileViewport()) return;
  const sidebar = document.getElementById('adminSidebar');
  const isOpen = Boolean(sidebar?.classList.contains('mobile-open'));
  if (isOpen) {
    closeAdminMobileNav();
  } else {
    openAdminMobileNav();
  }
}

function initSummaryNavigation() {
  const sectionMap = {
    'summary-users': 'users',
    'summary-vehicles': 'vehicles',
    'summary-services': 'services',
    'summary-records': 'records',
  };

  Object.entries(sectionMap).forEach(([id, section]) => {
    const el = document.getElementById(id);
    if (!el || el.dataset.bound === '1') return;

    const navigate = () => switchSection(section);
    el.setAttribute('role', 'button');
    el.setAttribute('tabindex', '0');
    el.addEventListener('click', navigate);
    el.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        navigate();
      }
    });
    el.dataset.bound = '1';
  });
}

function switchSection(section) {
  if (section !== 'control-center') {
    closeAllControlCenterDetails();
  } else {
    syncControlCenterDetailsOverlayState();
  }

  currentSection = section;
  
  // Aktualizovat aktivní stav v navigaci
  document.querySelectorAll('.nav-item').forEach(item => {
    item.classList.remove('active');
  });
  document.querySelector(`.nav-item[data-section="${section}"]`)?.classList.add('active');
  
  // Skrýt všechny sekce
  document.querySelectorAll('.content-section').forEach(sec => {
    sec.classList.remove('active');
  });
  
  // Zobrazit aktivní sekci
  const activeSection = document.getElementById(`section-${section}`);
  if (activeSection) {
    activeSection.classList.add('active');
  }
  
  // Načíst data pro sekci
  loadSectionData(section);

  // Na mobilu po kliknutí na sekci zavřít sidebar
  if (isAdminMobileViewport()) {
    closeAdminMobileNav();
  }
}

function loadSectionData(section) {
  hideGlobalError();
  
  switch(section) {
    case 'overview':
      loadOverview();
      break;
    case 'users':
      loadUsers();
      break;
    case 'vehicles':
      loadVehicles();
      break;
    case 'services':
      loadServices();
      break;
    case 'records':
      loadRecords();
      break;
    case 'audit':
      loadAuditLog();
      break;
    case 'system':
      // Systémové nástroje se načítají při kliknutí
      break;
    case 'settings':
      loadSettings();
      break;
    case 'control-center':
      refreshControlCenterOverview();
      break;
  }
}

// ============================================
// OVERVIEW SECTION
// ============================================

async function loadOverview() {
  try {
    const stats = await apiRequest('GET', '/admin-api/overview');
    
    // Aktualizovat statistiky v navbaru
    document.getElementById('summary-users').innerHTML = `👥 Uživatelé: <strong>${stats.total_users ?? 0}</strong>`;
    document.getElementById('summary-vehicles').innerHTML = `🚗 Vozidla: <strong>${stats.total_vehicles ?? 0}</strong>`;
    document.getElementById('summary-services').innerHTML = `🛠 Servisy: <strong>${stats.total_services ?? 0}</strong>`;
    document.getElementById('summary-records').innerHTML = `📋 Záznamy: <strong>${stats.total_records ?? 0}</strong>`;
    
    // Zobrazit statistiky
    const statsEl = document.getElementById('overview-stats');
    if (statsEl) {
      statsEl.innerHTML = `
        <div class="stat-card">
          <h3>${stats.total_users ?? 0}</h3>
          <p>Uživatelé</p>
        </div>
        <div class="stat-card">
          <h3>${stats.total_vehicles ?? 0}</h3>
          <p>Vozidla</p>
        </div>
        <div class="stat-card">
          <h3>${stats.total_services ?? 0}</h3>
          <p>Servisy</p>
        </div>
        <div class="stat-card">
          <h3>${stats.total_records ?? 0}</h3>
          <p>Servisní záznamy</p>
        </div>
        <div class="stat-card">
          <h3>${stats.total_assignments ?? 0}</h3>
          <p>Přiřazení</p>
        </div>
      `;
    }
    
    // Načíst poslední aktivitu
    loadRecentActivity();
    
  } catch (error) {
    console.error('Error loading overview:', error);
  }
}

async function loadRecentActivity() {
  try {
    const auditData = await apiRequest('GET', '/admin-api/audit?limit=5');
    const activityEl = document.getElementById('recent-activity');
    
    if (!activityEl) return;
    
    const logs = auditData.logs || [];
    
    if (logs.length === 0) {
      activityEl.innerHTML = '<div class="empty">Žádná nedávná aktivita</div>';
      return;
    }
    
    activityEl.innerHTML = logs.map(log => {
      const timestamp = log.timestamp ? new Date(log.timestamp).toLocaleString('cs-CZ') : '-';
      const actor = log.actor_email || `Uživatel #${log.actor_user_id || '?'}`;
      const actionText = getActionText(log.action || '');
      const entityType = log.entity_type || '?';
      const entityId = log.entity_id || '?';
      
      return `
        <div class="activity-item">
          <span class="activity-time">${timestamp}</span>
          <span class="activity-actor">${actor}</span>
          <span class="activity-action">${actionText}</span>
          <span class="activity-entity">${entityType} #${entityId}</span>
        </div>
      `;
    }).join('');
    
  } catch (error) {
    console.error('Error loading recent activity:', error);
  }
}

function getActionText(action) {
  const actionMap = {
    'CREATE_USER': 'vytvořil uživatele',
    'UPDATE_USER': 'aktualizoval uživatele',
    'DELETE_USER': 'smazal uživatele',
    'CREATE_VEHICLE': 'vytvořil vozidlo',
    'UPDATE_VEHICLE': 'aktualizoval vozidlo',
    'DELETE_VEHICLE': 'smazal vozidlo',
    'CREATE_SERVICE': 'vytvořil servis',
    'UPDATE_SERVICE': 'aktualizoval servis',
    'DELETE_SERVICE': 'smazal servis',
    'CREATE_SERVICE_RECORD': 'vytvořil servisní záznam',
    'UPDATE_SERVICE_RECORD': 'aktualizoval servisní záznam',
    'DELETE_SERVICE_RECORD': 'smazal servisní záznam',
  };
  return actionMap[action] || action;
}

// ============================================
// USERS CRUD
// ============================================

async function loadUsers() {
  const container = document.getElementById('users-cards-container');
  if (!container) return;
  const paginationEl = document.getElementById('users-pagination');

  container.innerHTML = '<div class="loading">Načítám uživatele...</div>';
  if (paginationEl) {
    paginationEl.classList.add('hidden');
    paginationEl.innerHTML = '';
  }

  try {
    const searchInput = document.getElementById('user-search');
    usersAllCache = await fetchAllList('/admin-api/users');
    usersCurrentPage = 1;

    if (searchInput && searchInput.dataset.bound !== '1') {
      searchInput.addEventListener('input', () => {
        usersCurrentPage = 1;
        renderUsersList();
      });
      searchInput.dataset.bound = '1';
    }

    renderUsersList();
  } catch (error) {
    container.innerHTML = `<div class="error">Chyba při načítání: ${error.message}</div>`;
  }
}

function renderUsersList() {
  const container = document.getElementById('users-cards-container');
  const paginationEl = document.getElementById('users-pagination');
  if (!container) return;

  const query = (document.getElementById('user-search')?.value || '').trim().toLowerCase();
  usersFilteredCache = !query
    ? [...usersAllCache]
    : usersAllCache.filter((user) => {
        const haystack = [
          user.id,
          user.email,
          user.name,
          user.role,
          user.city,
          user.phone,
          user.last_ip_address,
          user.last_location,
        ]
          .filter(Boolean)
          .join(' ')
          .toLowerCase();
        return haystack.includes(query);
      });

  if (usersFilteredCache.length === 0) {
    container.innerHTML = '<div class="empty">Žádní uživatelé</div>';
    if (paginationEl) {
      paginationEl.classList.add('hidden');
      paginationEl.innerHTML = '';
    }
    return;
  }

  const totalPages = Math.max(1, Math.ceil(usersFilteredCache.length / USERS_RENDER_PAGE_SIZE));
  usersCurrentPage = Math.min(Math.max(usersCurrentPage, 1), totalPages);

  const start = (usersCurrentPage - 1) * USERS_RENDER_PAGE_SIZE;
  const end = start + USERS_RENDER_PAGE_SIZE;
  const pageItems = usersFilteredCache.slice(start, end);

  const roleLabelMap = {
    user: 'Uživatel',
    service: 'Servis',
    admin: 'Admin',
    developer_admin: 'Developer',
  };
  const usersViewMode = adminViewState.users || getStoredViewMode('users');

  container.innerHTML = pageItems.map(user => {
    const createdDate = user.created_at ? new Date(user.created_at).toLocaleDateString('cs-CZ') : '-';
    const lastSeen = formatDateTime(user.last_seen_at);
    const lastPaidAt = formatDateTime(user.last_paid_at);
    const hasPaid = Boolean(user.has_paid);
    const paymentSummary = hasPaid
      ? `ANO${lastPaidAt !== '-' ? ` • ${lastPaidAt}` : ''}`
      : 'NE';
    const isOnline = getOnlineState(user);
    const presenceClass = isOnline ? 'presence-online' : 'presence-offline';
    const presenceLabel = isOnline ? 'Online' : 'Offline';
    const roleRaw = String(user.role || 'user').toLowerCase();
    const role = ['user', 'service', 'admin', 'developer_admin'].includes(roleRaw) ? roleRaw : 'user';
    const roleLabel = roleLabelMap[role] || 'Uživatel';
    const displayName = escapeHtml(user.name || user.email || 'Bez jména');
    const email = escapeHtml(user.email || '-');
    const city = escapeHtml(user.city || '-');
    const phone = escapeHtml(user.phone || '-');
    const ipAddress = escapeHtml(user.last_ip_address || '-');
    const location = escapeHtml(user.last_location || '-');
    const licensePlan = escapeHtml((user.license_plan || 'free').toUpperCase());
    const licenseStatus = escapeHtml(user.license_status || 'active');
    const vehiclesCount = Number(user.vehicles_count || 0).toLocaleString('cs-CZ');
    const tenantId = user.tenant_id ?? '-';
    const tenantIdValue = escapeHtml(String(tenantId));
    const contactValue = [phone !== '-' ? phone : null, city !== '-' ? city : null].filter(Boolean).join(' • ') || '-';
    const networkValue = [ipAddress !== '-' ? ipAddress : null, location !== '-' ? location : null].filter(Boolean).join(' • ') || '-';
    const encodedEmail = encodeURIComponent(String(user.email || ''));

    if (usersViewMode === 'compact') {
      return `
        <div class="card user-card-clickable" data-user-id="${user.id}" onclick="handleUserCardClick(event, ${user.id})" title="Otevřít detail uživatele">
          <div class="card-header">
            <h3 class="card-title">${user.name || user.email || 'Bez jména'}</h3>
            <span class="card-id">#${user.id}</span>
          </div>
          <div class="card-body">
            <div class="card-field">
              <span class="card-label">Email</span>
              <span class="card-value">${user.email || '-'}</span>
            </div>
            <div class="card-field">
              <span class="card-label">Jméno</span>
              <span class="card-value">${user.name || '-'}</span>
            </div>
            <div class="card-field">
              <span class="card-label">Role</span>
              <span class="card-value"><span class="role-badge role-${user.role || 'user'}">${user.role || 'user'}</span></span>
            </div>
            <div class="card-field">
              <span class="card-label">Licence</span>
              <span class="card-value">${licensePlan} (${licenseStatus})</span>
            </div>
            <div class="card-field">
              <span class="card-label">Platby</span>
              <span class="card-value">${escapeHtml(paymentSummary)}</span>
            </div>
            <div class="card-field">
              <span class="card-label">Stav</span>
              <span class="card-value"><span class="presence-pill ${presenceClass}">${presenceLabel}</span></span>
            </div>
            <div class="card-field">
              <span class="card-label">Tenant</span>
              <span class="card-value">${user.tenant_id ?? '-'}</span>
            </div>
            <div class="card-field">
              <span class="card-label">Vozidla</span>
              <span class="card-value">${user.vehicles_count || 0}</span>
            </div>
            <div class="card-field">
              <span class="card-label">Registrován</span>
              <span class="card-value">${createdDate}</span>
            </div>
            <div class="card-field">
              <span class="card-label">Poslední IP</span>
              <span class="card-value">${escapeHtml(user.last_ip_address || '-')}</span>
            </div>
            <div class="card-field">
              <span class="card-label">Lokalita</span>
              <span class="card-value">${escapeHtml(user.last_location || '-')}</span>
            </div>
            <div class="card-field">
              <span class="card-label">Naposledy aktivní</span>
              <span class="card-value">${lastSeen}</span>
            </div>
          </div>
          <div class="card-actions">
            <button class="btn-edit" onclick="editUser(event, ${user.id})">✏️ Upravit</button>
            <button class="btn-danger" onclick="deleteUser(event, ${user.id}, decodeURIComponent('${encodedEmail}'))">🗑️ Smazat</button>
          </div>
        </div>
      `;
    }

    return `
      <div class="card user-card user-card-clickable" data-user-id="${user.id}" onclick="handleUserCardClick(event, ${user.id})" title="Otevřít detail uživatele">
        <div class="card-header user-card-header">
          <div class="user-card-head-main">
            <h3 class="card-title">${displayName}</h3>
            <div class="user-card-email">${email}</div>
          </div>
          <div class="user-card-head-meta">
            <span class="role-badge role-${role}">${roleLabel}</span>
            <span class="presence-pill ${presenceClass}">${presenceLabel}</span>
            <span class="card-id">#${user.id}</span>
          </div>
        </div>
        <div class="card-body user-card-body">
          <div class="user-card-kpis">
            <span class="user-chip">Vozidla <strong>${vehiclesCount}</strong></span>
            <span class="user-chip">Tenant <strong>${tenantIdValue}</strong></span>
            <span class="user-chip">${licensePlan} • ${licenseStatus}</span>
            <span class="user-chip">Platby <strong>${hasPaid ? 'ANO' : 'NE'}</strong></span>
          </div>
          <div class="user-card-details">
            <div class="card-field">
              <span class="card-label">Kontakt</span>
              <span class="card-value">${contactValue}</span>
            </div>
            <div class="card-field">
              <span class="card-label">Registrován</span>
              <span class="card-value">${createdDate}</span>
            </div>
            <div class="card-field">
              <span class="card-label">Naposledy aktivní</span>
              <span class="card-value">${lastSeen}</span>
            </div>
            <div class="card-field">
              <span class="card-label">Poslední platba</span>
              <span class="card-value">${lastPaidAt}</span>
            </div>
            <div class="card-field user-card-field-wide">
              <span class="card-label">IP a lokalita</span>
              <span class="card-value user-card-tech">${networkValue}</span>
            </div>
          </div>
          <div class="card-field user-card-mobile-summary">
            <span class="card-label">Naposledy aktivní</span>
            <span class="card-value">${lastSeen}</span>
          </div>
        </div>
        <div class="card-actions user-card-actions">
          <button class="btn-edit" onclick="editUser(event, ${user.id})">Upravit</button>
          <button class="btn-danger" onclick="deleteUser(event, ${user.id}, decodeURIComponent('${encodedEmail}'))">Smazat</button>
        </div>
      </div>
    `;
  }).join('');

  applySectionViewMode('users');

  if (!paginationEl) {
    return;
  }

  const from = start + 1;
  const to = start + pageItems.length;
  paginationEl.classList.remove('hidden');
  paginationEl.innerHTML = `
    <div class="list-meta">Zobrazeno ${from}-${to} z ${usersFilteredCache.length} uživatelů</div>
    <div class="pagination-controls">
      <button class="pagination-btn" onclick="changeUsersPage(-1)" ${usersCurrentPage <= 1 ? 'disabled' : ''}>Předchozí</button>
      <span class="list-meta">Strana ${usersCurrentPage}/${totalPages}</span>
      <button class="pagination-btn" onclick="changeUsersPage(1)" ${usersCurrentPage >= totalPages ? 'disabled' : ''}>Další</button>
    </div>
  `;
}

function changeUsersPage(delta) {
  usersCurrentPage += delta;
  renderUsersList();
}

function handleUserCardClick(event, userId) {
  // Ochrana proti nechtěnému otevření detailu při kliku na akční tlačítka uvnitř karty.
  const target = event?.target;
  if (target && typeof target.closest === 'function') {
    if (target.closest('.card-actions, .user-card-actions, button, a, input, select, textarea, label')) {
      return;
    }
  }
  openUserDetail(userId);
}

function getCurrentUserDetailId() {
  if (userDetailData?.user?.id) return userDetailData.user.id;
  const modal = document.getElementById('user-detail-modal');
  if (!modal) return null;
  const rawId = modal.dataset.userId;
  const parsedId = Number.parseInt(rawId || '', 10);
  return Number.isFinite(parsedId) ? parsedId : null;
}

function setUserDetailLoadingState(isLoading) {
  const loadingEl = document.getElementById('user-detail-loading');
  const contentEl = document.getElementById('user-detail-content');
  const errorEl = document.getElementById('user-detail-error');
  if (loadingEl) {
    loadingEl.classList.toggle('hidden', !isLoading);
  }
  if (contentEl && isLoading) {
    contentEl.classList.add('hidden');
  }
  if (errorEl && isLoading) {
    errorEl.classList.add('hidden');
    errorEl.textContent = '';
  }
}

async function openUserDetail(userId, panel = 'vehicles') {
  const modal = document.getElementById('user-detail-modal');
  if (!modal) return;
  modal.dataset.userId = String(userId);
  userDetailActivePanel = panel;
  modal.classList.remove('hidden');
  await refreshUserDetail(panel);
}

function closeUserDetailModal() {
  const modal = document.getElementById('user-detail-modal');
  if (!modal) return;
  modal.classList.add('hidden');
  modal.dataset.userId = '';
  userDetailData = null;
}

function setUserDetailReturnContext(userId, panel) {
  userDetailReturnContext = { userId, panel };
}

async function reopenUserDetailIfNeeded() {
  if (!userDetailReturnContext) return;
  const context = userDetailReturnContext;
  userDetailReturnContext = null;
  await openUserDetail(context.userId, context.panel || 'vehicles');
}

async function refreshUserDetail(panelOverride = null) {
  const userId = getCurrentUserDetailId();
  const modal = document.getElementById('user-detail-modal');
  if (!userId || !modal) return;

  if (panelOverride) {
    userDetailActivePanel = panelOverride;
  }

  setUserDetailLoadingState(true);

  try {
    const detail = await apiRequest('GET', `/admin-api/users/${userId}/detail`);
    userDetailData = detail;
    renderUserDetailModal();
  } catch (error) {
    const errorEl = document.getElementById('user-detail-error');
    if (errorEl) {
      errorEl.textContent = `Chyba při načítání detailu uživatele: ${error.message}`;
      errorEl.classList.remove('hidden');
    }
  } finally {
    setUserDetailLoadingState(false);
  }
}

function setUserDetailPanel(panelKey) {
  userDetailActivePanel = panelKey;
  renderUserDetailModal();
}

function renderUserDetailModal() {
  const contentEl = document.getElementById('user-detail-content');
  const profileEl = document.getElementById('user-detail-profile');
  const panelsEl = document.getElementById('user-detail-panels');
  const listTitleEl = document.getElementById('user-detail-list-title');
  const listEl = document.getElementById('user-detail-list');
  const titleEl = document.getElementById('user-detail-title');
  const errorEl = document.getElementById('user-detail-error');
  if (!contentEl || !profileEl || !panelsEl || !listEl || !listTitleEl || !titleEl) return;

  const detail = userDetailData || {};
  const user = detail.user || {};
  const stats = detail.stats || {};
  const meta = detail.meta || {};
  const panels = detail.panels || {};
  const insight = detail.insight || {};
  const insightLicense = insight.license || {};
  const insightPaymentsSummary = insight.payments_summary || {};
  const insightPresence = insight.presence || {};
  const insightPayments = Array.isArray(insight.payments) ? insight.payments : [];

  titleEl.textContent = `Detail uživatele: ${user.name || user.email || '#' + (user.id ?? '?')}`;
  if (errorEl) {
    errorEl.classList.add('hidden');
    errorEl.textContent = '';
  }

  const roleClass = `role-${user.role || 'user'}`;
  const addressLine = [user.address_line, user.city_line].filter(Boolean).join(', ') || '-';
  const ipHistory = Array.isArray(meta.ip_history) ? meta.ip_history : [];
  const latestIpEntry = ipHistory.length > 0 ? ipHistory[0] : null;
  const latestIp = latestIpEntry?.ip_address || meta.last_ip_address || '-';
  const latestLocation = latestIpEntry?.location_label || meta.last_location || '-';
  const latestGeoSource = latestIpEntry?.geo_source || latestIpEntry?.source || '-';
  const latestGeoAccuracy = latestIpEntry?.geo_accuracy_m;
  const latestLatitude = latestIpEntry?.latitude;
  const latestLongitude = latestIpEntry?.longitude;
  const latestCoordinates = (
    latestLatitude !== null && latestLatitude !== undefined &&
    latestLongitude !== null && latestLongitude !== undefined
  ) ? `${Number(latestLatitude).toFixed(5)}, ${Number(latestLongitude).toFixed(5)}` : '-';
  const latestMapsUrl = latestIpEntry?.maps_url || null;
  const olderIpEntries = ipHistory.slice(1);
  const latestSeen = formatDateTime(meta.last_activity_at);
  const detailOnline = getOnlineState({ last_seen_at: insightPresence.last_seen_at || meta.last_activity_at });
  const detailOnlineClass = detailOnline ? 'presence-online' : 'presence-offline';
  const detailOnlineLabel = detailOnline ? 'Online' : 'Offline';
  const paymentPreview = insightPayments
    .slice(0, 3)
    .map((payment) => {
      const amount = Number(payment.amount_halers || 0).toLocaleString('cs-CZ');
      const stamp = formatDateTime(payment.payment_timestamp);
      const status = escapeHtml(payment.provider_status || payment.event_type || '-');
      const environment = escapeHtml(normalizePaymentEnvironment(payment));
      return `${environment} • ${amount} ${escapeHtml(payment.currency || 'CZK')} • ${status} • ${stamp}`;
    })
    .join('<br/>');

  profileEl.innerHTML = `
    <div class="user-detail-info-grid">
      <div class="user-detail-info-card">
        <h4>Základní údaje</h4>
        <div class="user-detail-row"><span>ID</span><strong>#${user.id ?? '-'}</strong></div>
        <div class="user-detail-row"><span>Email</span><strong>${escapeHtml(user.email || '-')}</strong></div>
        <div class="user-detail-row"><span>Jméno / Název</span><strong>${escapeHtml(user.name || '-')}</strong></div>
        <div class="user-detail-row"><span>Role</span><strong><span class="role-badge ${roleClass}">${escapeHtml(user.role || 'user')}</span></strong></div>
        <div class="user-detail-row"><span>Tenant</span><strong>${user.tenant_id ?? '-'}</strong></div>
        <div class="user-detail-row"><span>Licence</span><strong>${escapeHtml((user.license_plan || 'free').toUpperCase())} (${escapeHtml(user.license_status || 'active')})</strong></div>
        <div class="user-detail-row"><span>Stav účtu</span><strong>${user.is_deleted ? 'Smazaný' : (user.is_disabled ? 'Pozastavený' : 'Aktivní')}</strong></div>
        <div class="user-detail-row"><span>Session verze</span><strong>${user.session_version ?? 0}</strong></div>
        <div class="user-detail-row"><span>Registrován</span><strong>${formatDateTime(user.created_at)}</strong></div>
      </div>
      <div class="user-detail-info-card">
        <h4>Kontakt a firma</h4>
        <div class="user-detail-row"><span>Telefon</span><strong>${escapeHtml(user.phone || '-')}</strong></div>
        <div class="user-detail-row"><span>IČO</span><strong>${escapeHtml(user.ico || '-')}</strong></div>
        <div class="user-detail-row"><span>DIČ</span><strong>${escapeHtml(user.dic || '-')}</strong></div>
        <div class="user-detail-row"><span>Adresa</span><strong>${escapeHtml(addressLine)}</strong></div>
      </div>
      <div class="user-detail-info-card">
        <h4>Aktivita a IP</h4>
        <div class="user-detail-row"><span>Stav</span><strong><span class="presence-pill ${detailOnlineClass}">${detailOnlineLabel}</span></strong></div>
        <div class="user-detail-row"><span>Poslední IP</span><strong>${escapeHtml(latestIp)}</strong></div>
        <div class="user-detail-row"><span>Lokalita</span><strong>${escapeHtml(latestLocation)}</strong></div>
        <div class="user-detail-row"><span>Zdroj polohy</span><strong>${escapeHtml(latestGeoSource)}</strong></div>
        <div class="user-detail-row"><span>GPS</span><strong>${escapeHtml(latestCoordinates)}</strong></div>
        <div class="user-detail-row"><span>Přesnost</span><strong>${latestGeoAccuracy ? `±${escapeHtml(Math.round(Number(latestGeoAccuracy)).toString())} m` : '-'}</strong></div>
        <div class="user-detail-row"><span>Last login</span><strong>${escapeHtml(formatDateTime(insightPresence.last_login_at || user.last_login_at))}</strong></div>
        <div class="user-detail-row"><span>Last seen</span><strong>${escapeHtml(formatDateTime(insightPresence.last_seen_at || user.last_seen_at))}</strong></div>
        <div class="user-detail-row"><span>Aktivní relace</span><strong>${escapeHtml(String(insightPresence.active_session_count ?? 0))}</strong></div>
        <div class="user-detail-row"><span>Poslední aktivita</span><strong>${escapeHtml(latestSeen)}</strong></div>
        ${latestMapsUrl ? `<div class="user-detail-ip-map-link"><a href="${escapeHtml(latestMapsUrl)}" target="_blank" rel="noopener noreferrer">Otevřít poslední polohu na mapě</a></div>` : ''}
        <div class="user-detail-ip-list user-detail-ip-last">
          ${(latestIpEntry
            ? `
                <div class="user-detail-ip-item">
                  <strong>${escapeHtml(latestIpEntry.ip_address || '-')}</strong>
                  <span>${escapeHtml(latestIpEntry.location_label || '-')}</span>
                  <span>${escapeHtml(formatDateTime(latestIpEntry.timestamp))}</span>
                </div>
              `
            : '<div class="empty">Žádná uložená IP historie</div>')}
        </div>
        ${olderIpEntries.length > 0
          ? `
            <details class="user-detail-ip-history-details">
              <summary>Historie připojení (${olderIpEntries.length})</summary>
              <div class="user-detail-ip-list user-detail-ip-list-scroll">
                ${olderIpEntries.map((ip) => {
                  const hasCoords = ip.latitude !== null && ip.latitude !== undefined && ip.longitude !== null && ip.longitude !== undefined;
                  const coords = hasCoords ? `${Number(ip.latitude).toFixed(5)}, ${Number(ip.longitude).toFixed(5)}` : null;
                  const sourceLabel = ip.geo_source || ip.source || '-';
                  const accuracyLabel = ip.geo_accuracy_m ? ` ±${Math.round(Number(ip.geo_accuracy_m))} m` : '';
                  const mapLink = ip.maps_url
                    ? `<a href="${escapeHtml(ip.maps_url)}" target="_blank" rel="noopener noreferrer">mapa</a>`
                    : '';
                  return `
                    <div class="user-detail-ip-item">
                      <strong>${escapeHtml(ip.ip_address || '-')}</strong>
                      <span>${escapeHtml(ip.location_label || '-')}</span>
                      <span>${escapeHtml(formatDateTime(ip.timestamp))}</span>
                      <span>Zdroj: ${escapeHtml(sourceLabel)}${escapeHtml(accuracyLabel)}</span>
                      ${coords ? `<span>GPS: ${escapeHtml(coords)} ${mapLink}</span>` : ''}
                    </div>
                  `;
                }).join('')}
              </div>
            </details>
          `
          : ''}
      </div>
      <div class="user-detail-info-card">
        <h4>Licence a platby</h4>
        <div class="user-detail-row"><span>Plan</span><strong>${escapeHtml((insightLicense.current_plan || user.license_plan || 'free').toUpperCase())}</strong></div>
        <div class="user-detail-row"><span>Status</span><strong>${escapeHtml(insightLicense.status || user.license_status || 'active')}</strong></div>
        <div class="user-detail-row"><span>Zdroj aktivace</span><strong>${escapeHtml(insightLicense.source_of_activation || '-')}</strong></div>
        <div class="user-detail-row"><span>Nákup</span><strong>${escapeHtml(formatDateTime(insightLicense.purchase_date))}</strong></div>
        <div class="user-detail-row"><span>Aktivace</span><strong>${escapeHtml(formatDateTime(insightLicense.activation_date))}</strong></div>
        <div class="user-detail-row"><span>Expirace</span><strong>${escapeHtml(formatDateTime(insightLicense.expiration_date))}</strong></div>
        <div class="user-detail-row"><span>Další obnova</span><strong>${escapeHtml(formatDateTime(insightLicense.next_renewal_date))}</strong></div>
        <div class="user-detail-row"><span>LIVE paid</span><strong>${insightPaymentsSummary.has_live_paid || insightPaymentsSummary.has_paid ? 'Ano' : 'Ne'}</strong></div>
        <div class="user-detail-row"><span>LIVE/TEST tx</span><strong>${escapeHtml(String(insightPaymentsSummary.count_live ?? 0))} / ${escapeHtml(String(insightPaymentsSummary.count_test ?? 0))}</strong></div>
        <div class="user-detail-row"><span>LIVE/TEST paid</span><strong>${escapeHtml(String(insightPaymentsSummary.live_paid_count ?? 0))} / ${escapeHtml(String(insightPaymentsSummary.test_paid_count ?? 0))}</strong></div>
        <div class="user-detail-row"><span>Počet transakcí</span><strong>${escapeHtml(String(insightPaymentsSummary.count ?? insightPayments.length ?? 0))}</strong></div>
        <div class="user-detail-row"><span>Poslední platba</span><strong>${escapeHtml(formatDateTime(insightPaymentsSummary.last_paid_at))}</strong></div>
        <div class="user-detail-row"><span>Nedávné transakce</span><strong>${paymentPreview || '-'}</strong></div>
      </div>
      <div class="user-detail-info-card">
        <h4>Notifikace</h4>
        <div class="user-detail-row"><span>Email notifikace</span><strong>${user.notify_email ? 'Ano' : 'Ne'}</strong></div>
        <div class="user-detail-row"><span>SMS notifikace</span><strong>${user.notify_sms ? 'Ano' : 'Ne'}</strong></div>
        <div class="user-detail-row"><span>STK připomínky</span><strong>${user.notify_stk ? 'Ano' : 'Ne'}</strong></div>
        <div class="user-detail-row"><span>Olej připomínky</span><strong>${user.notify_oil ? 'Ano' : 'Ne'}</strong></div>
        <div class="user-detail-row"><span>Obecné připomínky</span><strong>${user.notify_general ? 'Ano' : 'Ne'}</strong></div>
      </div>
    </div>
  `;

  const panelDefs = [
    { key: 'vehicles', label: 'Vozidla', icon: '🚗', count: stats.vehicles_count ?? 0 },
    { key: 'reminders', label: 'Připomínky', icon: '⏰', count: stats.reminders_count ?? 0 },
    { key: 'reservations', label: 'Rezervace', icon: '📅', count: stats.reservations_count ?? 0 },
    { key: 'records', label: 'Záznamy', icon: '📋', count: stats.records_count ?? 0 },
  ];

  panelsEl.innerHTML = panelDefs.map((panel) => `
    <button
      class="user-detail-panel-card ${userDetailActivePanel === panel.key ? 'active' : ''}"
      onclick="setUserDetailPanel('${panel.key}')"
      type="button"
    >
      <span class="user-detail-panel-icon">${panel.icon}</span>
      <span class="user-detail-panel-label">${panel.label}</span>
      <span class="user-detail-panel-count">${panel.count}</span>
    </button>
  `).join('');

  const titleMap = {
    vehicles: 'Vozidla uživatele',
    reminders: 'Připomínky uživatele',
    reservations: 'Rezervace uživatele',
    records: 'Servisní záznamy uživatele',
  };
  listTitleEl.textContent = titleMap[userDetailActivePanel] || 'Detail položek';

  const selected = Array.isArray(panels[userDetailActivePanel]) ? panels[userDetailActivePanel] : [];
  if (selected.length === 0) {
    listEl.innerHTML = '<div class="empty">Žádné položky</div>';
    contentEl.classList.remove('hidden');
    return;
  }

  if (userDetailActivePanel === 'vehicles') {
    listEl.innerHTML = selected.map((vehicle) => {
      const label = vehicle.label || vehicle.nickname || `Vozidlo #${vehicle.id}`;
      const encodedLabel = encodeURIComponent(label || '');
      const metaText = [
        `SPZ: ${vehicle.plate || '-'}`,
        `Rok: ${vehicle.year || '-'}`,
        `Záznamů: ${vehicle.service_count || 0}`,
        `Vytvořeno: ${formatDate(vehicle.created_at)}`,
      ].join(' • ');
      return `
        <div class="user-detail-list-item">
          <div class="user-detail-list-text">
            <div class="user-detail-list-title">🚗 ${escapeHtml(label)}</div>
            <div class="user-detail-list-meta">${escapeHtml(metaText)}</div>
          </div>
          <div class="user-detail-list-actions">
            <button class="btn-edit btn-sm" onclick="stopEventSafely(event); editVehicleFromUserDetail(${vehicle.id})">Upravit</button>
            <button class="btn-danger btn-sm" onclick="stopEventSafely(event); deleteVehicleFromUserDetail(${vehicle.id}, '${encodedLabel}')">Smazat</button>
          </div>
        </div>
      `;
    }).join('');
  } else if (userDetailActivePanel === 'reminders') {
    listEl.innerHTML = selected.map((reminder) => {
      const encodedText = encodeURIComponent(reminder.text || '');
      const status = reminder.is_completed ? 'Dokončeno' : 'Aktivní';
      const statusClass = reminder.is_completed ? 'status-ok' : 'status-warn';
      const due = formatDate(reminder.due_date);
      return `
        <div class="user-detail-list-item">
          <div class="user-detail-list-text">
            <div class="user-detail-list-title">⏰ ${escapeHtml(reminder.text || '-')}</div>
            <div class="user-detail-list-meta">
              ${escapeHtml(`Typ: ${reminder.type || '-'} • Vozidlo: ${reminder.vehicle_label || '-'} • Termín: ${due}`)}
            </div>
          </div>
          <div class="user-detail-list-actions">
            <span class="status-pill ${statusClass}">${status}</span>
            <button class="btn-secondary btn-sm" onclick="stopEventSafely(event); toggleReminderCompletionFromUserDetail(${reminder.id}, ${!reminder.is_completed})">${reminder.is_completed ? 'Obnovit' : 'Dokončit'}</button>
            <button class="btn-edit btn-sm" onclick="stopEventSafely(event); quickEditReminderFromUserDetail(${reminder.id}, '${encodedText}')">Upravit</button>
            <button class="btn-danger btn-sm" onclick="stopEventSafely(event); deleteReminderFromUserDetail(${reminder.id})">Smazat</button>
          </div>
        </div>
      `;
    }).join('');
  } else if (userDetailActivePanel === 'reservations') {
    listEl.innerHTML = selected.map((reservation) => {
      const statusClass = reservation.status === 'CONFIRMED' ? 'status-ok' : (reservation.status === 'CANCELLED' ? 'status-bad' : 'status-warn');
      const status = reservation.status || '-';
      return `
        <div class="user-detail-list-item">
          <div class="user-detail-list-text">
            <div class="user-detail-list-title">📅 ${escapeHtml(reservation.service_type || 'Rezervace')}</div>
            <div class="user-detail-list-meta">
              ${escapeHtml(`Vozidlo: ${reservation.vehicle_label || '-'} • Servis: ${reservation.service_name || reservation.service_email || '-'} • Od: ${formatDateTime(reservation.start_datetime)}`)}
            </div>
            ${reservation.note ? `<div class="user-detail-list-note">${escapeHtml(reservation.note)}</div>` : ''}
          </div>
          <div class="user-detail-list-actions">
            <span class="status-pill ${statusClass}">${escapeHtml(status)}</span>
            <button class="btn-secondary btn-sm" onclick="stopEventSafely(event); updateReservationStatusFromUserDetail(${reservation.id}, 'CONFIRMED')">Potvrdit</button>
            <button class="btn-secondary btn-sm" onclick="stopEventSafely(event); updateReservationStatusFromUserDetail(${reservation.id}, 'CANCELLED')">Zrušit</button>
            <button class="btn-danger btn-sm" onclick="stopEventSafely(event); deleteReservationFromUserDetail(${reservation.id})">Smazat</button>
          </div>
        </div>
      `;
    }).join('');
  } else {
    listEl.innerHTML = selected.map((record) => {
      const metaText = [
        `Vozidlo: ${record.vehicle_label || '-'}`,
        `Datum: ${formatDateTime(record.performed_at)}`,
        `Nájezd: ${record.mileage ? `${Number(record.mileage).toLocaleString('cs-CZ')} km` : '-'}`,
        `Cena: ${formatMoney(record.price)}`,
      ].join(' • ');
      return `
        <div class="user-detail-list-item">
          <div class="user-detail-list-text">
            <div class="user-detail-list-title">📋 ${escapeHtml(record.description || '-')}</div>
            <div class="user-detail-list-meta">${escapeHtml(metaText)}</div>
            ${record.note ? `<div class="user-detail-list-note">${escapeHtml(record.note)}</div>` : ''}
          </div>
          <div class="user-detail-list-actions">
            <button class="btn-edit btn-sm" onclick="stopEventSafely(event); editRecordFromUserDetail(${record.id})">Upravit</button>
            <button class="btn-danger btn-sm" onclick="stopEventSafely(event); deleteRecordFromUserDetail(${record.id})">Smazat</button>
          </div>
        </div>
      `;
    }).join('');
  }

  contentEl.classList.remove('hidden');
}

async function editUserFromDetail() {
  if (!userDetailData?.user?.id) return;
  const userId = userDetailData.user.id;
  const panel = userDetailActivePanel;
  const opened = await showUserModal(userId);
  if (!opened) return;
  setUserDetailReturnContext(userId, panel);
  closeUserDetailModal();
}

async function deleteCurrentUserFromDetail() {
  const userId = getCurrentUserDetailId();
  if (!userId) return;
  const userEmail = userDetailData?.user?.email || `#${userId}`;
  await deleteUser(userId, userEmail);
}

async function disableCurrentUserFromDetail() {
  const userId = getCurrentUserDetailId();
  if (!userId) return;
  if (!confirm(`Pozastavit účet uživatele #${userId}?`)) return;
  try {
    const data = await apiRequest('POST', `/admin-api/control-center/users/${userId}/disable`, { reason: 'detail_modal' });
    showSuccess(data?.message || 'Účet byl pozastaven');
    await Promise.all([loadUsers(), refreshUserDetail()]);
  } catch (error) {
    console.error('Error disabling user from detail:', error);
  }
}

async function enableCurrentUserFromDetail() {
  const userId = getCurrentUserDetailId();
  if (!userId) return;
  if (!confirm(`Aktivovat účet uživatele #${userId}?`)) return;
  try {
    const data = await apiRequest('POST', `/admin-api/control-center/users/${userId}/enable`, { reason: 'detail_modal' });
    showSuccess(data?.message || 'Účet byl aktivován');
    await Promise.all([loadUsers(), refreshUserDetail()]);
  } catch (error) {
    console.error('Error enabling user from detail:', error);
  }
}

async function forceLogoutCurrentUserFromDetail() {
  const userId = getCurrentUserDetailId();
  if (!userId) return;
  if (!confirm(`Ukončit všechny relace uživatele #${userId}?`)) return;
  try {
    const data = await apiRequest('POST', `/admin-api/control-center/users/${userId}/force-logout`, { reason: 'detail_modal' });
    showSuccess(data?.message || 'Relace byly ukončeny');
    await refreshUserDetail();
  } catch (error) {
    console.error('Error forcing logout from detail:', error);
  }
}

async function resetPasswordCurrentUserFromDetail() {
  const userId = getCurrentUserDetailId();
  if (!userId) return;
  const password = prompt('Nové heslo (prázdné = vygenerovat dočasné):', '');
  try {
    const data = await apiRequest('POST', `/admin-api/control-center/users/${userId}/reset-password`, {
      new_password: password || null,
      generate_random: !password,
      reason: 'detail_modal',
    });
    if (data?.temporary_password) {
      showSuccess(`Dočasné heslo: ${data.temporary_password}`);
    } else {
      showSuccess(data?.message || 'Heslo bylo resetováno');
    }
    await refreshUserDetail();
  } catch (error) {
    console.error('Error resetting password from detail:', error);
  }
}

function editVehicleFromUserDetail(vehicleId) {
  if (!userDetailData?.user?.id) return;
  setUserDetailReturnContext(userDetailData.user.id, 'vehicles');
  closeUserDetailModal();
  showVehicleModal(vehicleId);
}

function editRecordFromUserDetail(recordId) {
  if (!userDetailData?.user?.id) return;
  setUserDetailReturnContext(userDetailData.user.id, 'records');
  closeUserDetailModal();
  showRecordModal(recordId);
}

async function deleteVehicleFromUserDetail(vehicleId, encodedVehicleLabel) {
  const vehicleLabel = decodeURIComponent(encodedVehicleLabel || '');
  if (!confirm(`Opravdu chcete smazat vozidlo ${vehicleLabel || '#'+vehicleId}?`)) return;
  try {
    await apiRequest('DELETE', `/admin-api/vehicles/${vehicleId}`);
    showSuccess('Údaj byl upraven adminem: vozidlo smazáno');
    await Promise.all([loadVehicles(), loadUsers(), loadOverview()]);
    await refreshUserDetail('vehicles');
  } catch (error) {
    console.error('Error deleting vehicle from detail:', error);
  }
}

async function deleteRecordFromUserDetail(recordId) {
  if (!confirm('Opravdu chcete smazat tento servisní záznam?')) return;
  try {
    await apiRequest('DELETE', `/admin-api/records/${recordId}`);
    showSuccess('Údaj byl upraven adminem: záznam smazán');
    await Promise.all([loadRecords(), loadOverview()]);
    await refreshUserDetail('records');
  } catch (error) {
    console.error('Error deleting record from detail:', error);
  }
}

async function quickEditReminderFromUserDetail(reminderId, encodedCurrentText) {
  const currentText = decodeURIComponent(encodedCurrentText || '');
  const nextText = prompt('Upravte text připomínky:', currentText || '');
  if (nextText === null) return;
  try {
    await apiRequest('PATCH', `/admin-api/reminders/${reminderId}`, { text: nextText });
    showSuccess('Údaj byl upraven adminem: připomínka aktualizována');
    await Promise.all([loadOverview()]);
    await refreshUserDetail('reminders');
  } catch (error) {
    console.error('Error updating reminder from detail:', error);
  }
}

async function toggleReminderCompletionFromUserDetail(reminderId, nextCompletedState) {
  try {
    await apiRequest('PATCH', `/admin-api/reminders/${reminderId}`, { is_completed: nextCompletedState });
    showSuccess('Údaj byl upraven adminem: stav připomínky změněn');
    await Promise.all([loadOverview()]);
    await refreshUserDetail('reminders');
  } catch (error) {
    console.error('Error toggling reminder state from detail:', error);
  }
}

async function deleteReminderFromUserDetail(reminderId) {
  if (!confirm('Opravdu chcete smazat tuto připomínku?')) return;
  try {
    await apiRequest('DELETE', `/admin-api/reminders/${reminderId}`);
    showSuccess('Údaj byl upraven adminem: připomínka smazána');
    await Promise.all([loadOverview()]);
    await refreshUserDetail('reminders');
  } catch (error) {
    console.error('Error deleting reminder from detail:', error);
  }
}

async function updateReservationStatusFromUserDetail(reservationId, status) {
  try {
    await apiRequest('PATCH', `/admin-api/reservations/${reservationId}`, { status });
    showSuccess(`Údaj byl upraven adminem: rezervace nastavena na ${status}`);
    await Promise.all([loadOverview()]);
    await refreshUserDetail('reservations');
  } catch (error) {
    console.error('Error updating reservation status from detail:', error);
  }
}

async function deleteReservationFromUserDetail(reservationId) {
  if (!confirm('Opravdu chcete smazat tuto rezervaci?')) return;
  try {
    await apiRequest('DELETE', `/admin-api/reservations/${reservationId}`);
    showSuccess('Údaj byl upraven adminem: rezervace smazána');
    await Promise.all([loadOverview()]);
    await refreshUserDetail('reservations');
  } catch (error) {
    console.error('Error deleting reservation from detail:', error);
  }
}

async function showUserModal(userId = null) {
  const modal = document.getElementById('user-modal');
  const form = document.getElementById('user-form');
  const title = document.getElementById('user-modal-title');
  const passwordHint = document.getElementById('user-password-hint');
  const passwordInput = document.getElementById('user-password');
  
  if (userId) {
    title.textContent = 'Upravit uživatele';
    passwordHint.textContent = '(nechte prázdné, pokud neměníte)';
    passwordInput.required = false;
    
    try {
      let user = null;
      try {
        const detail = await apiRequest('GET', `/admin-api/users/${userId}/detail`);
        user = detail?.user || null;
      } catch (detailError) {
        console.warn('Detail uživatele se nepodařilo načíst, použije se fallback seznam.', detailError);
      }

      if (!user) {
        const users = usersAllCache.length > 0 ? usersAllCache : await fetchAllList('/admin-api/users');
        user = users.find(u => u.id === userId) || null;
      }

      if (user) {
        document.getElementById('user-id').value = user.id;
        document.getElementById('user-email').value = user.email || '';
        document.getElementById('user-name').value = user.name || '';
        document.getElementById('user-role').value = user.role || 'user';
        document.getElementById('user-phone').value = user.phone || '';
        document.getElementById('user-ico').value = user.ico || '';
        document.getElementById('user-dic').value = user.dic || '';
        document.getElementById('user-street').value = user.street || '';
        document.getElementById('user-street-number').value = user.street_number || '';
        document.getElementById('user-city').value = user.city || '';
        document.getElementById('user-zip').value = user.zip || '';
        document.getElementById('user-license-plan').value = (user.license_plan || 'free').toLowerCase();
        passwordInput.value = '';
      }
    } catch (error) {
      showGlobalError('Chyba při načítání uživatele: ' + error.message);
      return false;
    }
  } else {
    title.textContent = 'Přidat uživatele';
    passwordHint.textContent = '(povinné při vytvoření)';
    form.reset();
    document.getElementById('user-id').value = '';
    passwordInput.required = true;
    document.getElementById('user-license-plan').value = 'free';
  }
  
  modal.classList.remove('hidden');
  return true;
}

function closeUserModal(preserveReturnContext = false) {
  document.getElementById('user-modal').classList.add('hidden');
  document.getElementById('user-form').reset();
  if (!preserveReturnContext) {
    userDetailReturnContext = null;
  }
}

async function saveUser(event) {
  event.preventDefault();
  
  const userId = document.getElementById('user-id').value;
  const userData = {
    email: document.getElementById('user-email').value,
    name: document.getElementById('user-name').value || null,
    role: document.getElementById('user-role').value,
    phone: document.getElementById('user-phone').value || null,
    ico: document.getElementById('user-ico').value || null,
    dic: document.getElementById('user-dic').value || null,
    street: document.getElementById('user-street').value || null,
    street_number: document.getElementById('user-street-number').value || null,
    city: document.getElementById('user-city').value || null,
    zip: document.getElementById('user-zip').value || null,
    license_plan: document.getElementById('user-license-plan').value || 'free',
  };
  
  const password = document.getElementById('user-password').value;
  if (password) {
    userData.password = password;
  }
  
  try {
    let responseData = null;
    if (userId) {
      responseData = await apiRequest('PATCH', `/admin-api/users/${userId}`, userData);
      const planLabel = (responseData?.license_plan || userData.license_plan || 'free').toUpperCase();
      showSuccess(`Údaj byl upraven adminem: uživatel (licence: ${planLabel})`);
    } else {
      if (!password) {
        showGlobalError('Heslo je povinné při vytváření uživatele');
        return;
      }
      responseData = await apiRequest('POST', '/admin-api/users', userData);
      const planLabel = (responseData?.license_plan || userData.license_plan || 'free').toUpperCase();
      showSuccess(`Uživatel byl vytvořen (licence: ${planLabel})`);
    }
    
    closeUserModal(true);
    await Promise.all([loadUsers(), loadOverview()]);
    await reopenUserDetailIfNeeded();
  } catch (error) {
    console.error('Error saving user:', error);
  }
}

function stopEventSafely(evt) {
  if (!evt || typeof evt !== 'object') return;
  if (typeof evt.preventDefault === 'function') evt.preventDefault();
  if (typeof evt.stopPropagation === 'function') evt.stopPropagation();
}

async function editUser(eventOrUserId, maybeUserId = null) {
  const hasEvent = eventOrUserId && typeof eventOrUserId === 'object' && typeof eventOrUserId.stopPropagation === 'function';
  const userId = hasEvent ? maybeUserId : eventOrUserId;
  if (hasEvent) {
    stopEventSafely(eventOrUserId);
  }
  showUserModal(userId);
}

async function deleteUser(eventOrUserId, maybeUserId = null, maybeUserEmail = null) {
  const hasEvent = eventOrUserId && typeof eventOrUserId === 'object' && typeof eventOrUserId.stopPropagation === 'function';
  const userId = hasEvent ? maybeUserId : eventOrUserId;
  const userEmail = hasEvent ? maybeUserEmail : maybeUserId;
  if (hasEvent) {
    stopEventSafely(eventOrUserId);
  }
  if (!confirm(`Opravdu chcete smazat uživatele ${userEmail}?`)) {
    return;
  }
  
  try {
    await apiRequest('DELETE', `/admin-api/users/${userId}`);
    showSuccess('Uživatel byl smazán');
    const currentDetailId = getCurrentUserDetailId();
    if (Number(currentDetailId) === Number(userId)) {
      closeUserDetailModal();
    }
    await Promise.all([loadUsers(), loadOverview()]);
  } catch (error) {
    console.error('Error deleting user:', error);
  }
}

// ============================================
// VEHICLES CRUD
// ============================================

async function loadVehicles() {
  const container = document.getElementById('vehicles-cards-container');
  if (!container) return;
  
  container.innerHTML = '<div class="loading">Načítám vozidla...</div>';
  
  try {
    const vehicles = await fetchAllList('/admin-api/vehicles');
    
    if (vehicles.length === 0) {
      container.innerHTML = '<div class="empty">Žádná vozidla</div>';
      applySectionViewMode('vehicles');
      return;
    }
    
    container.innerHTML = vehicles.map(vehicle => {
      const createdDate = vehicle.created_at ? new Date(vehicle.created_at).toLocaleDateString('cs-CZ') : '-';
      const vehicleName = vehicle.nickname || `${vehicle.brand || ''} ${vehicle.model || ''}`.trim() || 'Bez názvu';
      return `
        <div class="card" data-vehicle-id="${vehicle.id}">
          <div class="card-header">
            <h3 class="card-title">🚗 ${vehicleName}</h3>
            <span class="card-id">#${vehicle.id}</span>
          </div>
          <div class="card-body">
            <div class="card-field">
              <span class="card-label">Vlastník</span>
              <span class="card-value">${vehicle.owner_name || vehicle.user_email || '-'}</span>
            </div>
            <div class="card-field">
              <span class="card-label">Značka / Model</span>
              <span class="card-value">${vehicle.brand || '-'} ${vehicle.model || ''}</span>
            </div>
            <div class="card-field">
              <span class="card-label">Rok</span>
              <span class="card-value">${vehicle.year || '-'}</span>
            </div>
            <div class="card-field">
              <span class="card-label">SPZ</span>
              <span class="card-value">${vehicle.plate || '-'}</span>
            </div>
            ${vehicle.vin ? `
            <div class="card-field">
              <span class="card-label">VIN</span>
              <span class="card-value" style="font-family: monospace; font-size: 13px;">${vehicle.vin}</span>
            </div>
            ` : ''}
            <div class="card-field">
              <span class="card-label">Přidáno</span>
              <span class="card-value">${createdDate}</span>
            </div>
          </div>
          <div class="card-actions">
            <button class="btn-edit" onclick="editVehicle(${vehicle.id})">✏️ Upravit</button>
            <button class="btn-danger" onclick="deleteVehicle(${vehicle.id}, '${vehicleName.replace(/'/g, "\\'")}')">🗑️ Smazat</button>
          </div>
        </div>
      `;
    }).join('');
    applySectionViewMode('vehicles');
    
    // Vyhledávání
    const searchInput = document.getElementById('vehicle-search');
    if (searchInput) {
      searchInput.oninput = (e) => {
        const query = e.target.value.toLowerCase();
        const cards = container.querySelectorAll('.card');
        cards.forEach(card => {
          const text = card.textContent.toLowerCase();
          card.style.display = text.includes(query) ? '' : 'none';
        });
      };
    }
    
  } catch (error) {
    container.innerHTML = `<div class="error">Chyba při načítání: ${error.message}</div>`;
  }
}

async function showVehicleModal(vehicleId = null) {
  const modal = document.getElementById('vehicle-modal');
  const title = document.getElementById('vehicle-modal-title');
  
  if (vehicleId) {
    title.textContent = 'Upravit vozidlo';
    try {
      const vehicles = await fetchAllList('/admin-api/vehicles');
      const vehicle = vehicles.find(v => v.id === vehicleId);
      if (vehicle) {
        document.getElementById('vehicle-id').value = vehicle.id;
        document.getElementById('vehicle-user-email').value = vehicle.user_email || '';
        document.getElementById('vehicle-nickname').value = vehicle.nickname || '';
        document.getElementById('vehicle-brand').value = vehicle.brand || '';
        document.getElementById('vehicle-model').value = vehicle.model || '';
        document.getElementById('vehicle-year').value = vehicle.year || '';
        document.getElementById('vehicle-plate').value = vehicle.plate || '';
        document.getElementById('vehicle-vin').value = vehicle.vin || '';
      }
    } catch (error) {
      showGlobalError('Chyba při načítání vozidla: ' + error.message);
      return;
    }
  } else {
    title.textContent = 'Přidat vozidlo';
    document.getElementById('vehicle-form').reset();
    document.getElementById('vehicle-id').value = '';
  }
  
  modal.classList.remove('hidden');
}

function closeVehicleModal(preserveReturnContext = false) {
  document.getElementById('vehicle-modal').classList.add('hidden');
  document.getElementById('vehicle-form').reset();
  if (!preserveReturnContext) {
    userDetailReturnContext = null;
  }
}

async function saveVehicle(event) {
  event.preventDefault();
  
  const vehicleId = document.getElementById('vehicle-id').value;
  const vehicleData = {
    user_email: document.getElementById('vehicle-user-email').value,
    nickname: document.getElementById('vehicle-nickname').value || null,
    brand: document.getElementById('vehicle-brand').value || null,
    model: document.getElementById('vehicle-model').value || null,
    year: parseInt(document.getElementById('vehicle-year').value) || null,
    plate: document.getElementById('vehicle-plate').value || null,
    vin: document.getElementById('vehicle-vin').value || null,
  };
  
  try {
    if (vehicleId) {
      await apiRequest('PATCH', `/admin-api/vehicles/${vehicleId}`, vehicleData);
      showSuccess('Údaj byl upraven adminem: vozidlo');
    } else {
      await apiRequest('POST', '/admin-api/vehicles', vehicleData);
      showSuccess('Vozidlo bylo vytvořeno');
    }
    
    closeVehicleModal(true);
    await Promise.all([loadVehicles(), loadOverview(), loadUsers()]);
    await reopenUserDetailIfNeeded();
  } catch (error) {
    console.error('Error saving vehicle:', error);
  }
}

async function editVehicle(vehicleId) {
  showVehicleModal(vehicleId);
}

async function deleteVehicle(vehicleId, vehicleName) {
  if (!confirm(`Opravdu chcete smazat vozidlo ${vehicleName}?`)) {
    return;
  }
  
  try {
    await apiRequest('DELETE', `/admin-api/vehicles/${vehicleId}`);
    showSuccess('Vozidlo bylo smazáno');
    loadVehicles();
    loadOverview();
  } catch (error) {
    console.error('Error deleting vehicle:', error);
  }
}

// ============================================
// SERVICES CRUD
// ============================================

async function loadServices() {
  const container = document.getElementById('services-cards-container');
  if (!container) return;
  
  container.innerHTML = '<div class="loading">Načítám servisy...</div>';
  loadServiceRegistrationRequests();
  
  try {
    const services = await fetchAllList('/admin-api/services');
    
    if (services.length === 0) {
      container.innerHTML = '<div class="empty">Žádné servisy</div>';
      applySectionViewMode('services');
      return;
    }
    
    container.innerHTML = services.map(service => {
      const createdDate = service.created_at ? new Date(service.created_at).toLocaleDateString('cs-CZ') : '-';
      return `
        <div class="card" data-service-id="${service.id}">
          <div class="card-header">
            <h3 class="card-title">🛠️ ${service.name || service.email || 'Bez názvu'}</h3>
            <span class="card-id">#${service.id}</span>
          </div>
          <div class="card-body">
            <div class="card-field">
              <span class="card-label">Email</span>
              <span class="card-value">${service.email || '-'}</span>
            </div>
            <div class="card-field">
              <span class="card-label">Město</span>
              <span class="card-value">${service.city || '-'}</span>
            </div>
            <div class="card-field">
              <span class="card-label">Telefon</span>
              <span class="card-value">${service.phone || '-'}</span>
            </div>
            ${service.ico ? `
            <div class="card-field">
              <span class="card-label">IČO</span>
              <span class="card-value">${service.ico}</span>
            </div>
            ` : ''}
            <div class="card-field">
              <span class="card-label">Registrován</span>
              <span class="card-value">${createdDate}</span>
            </div>
          </div>
          <div class="card-actions">
            <button class="btn-edit" onclick="editService(${service.id})">✏️ Upravit</button>
            <button class="btn-danger" onclick="deleteService(${service.id}, '${(service.name || service.email || '').replace(/'/g, "\\'")}')">🗑️ Smazat</button>
          </div>
        </div>
      `;
    }).join('');
    applySectionViewMode('services');
    
    // Vyhledávání
    const searchInput = document.getElementById('service-search');
    if (searchInput) {
      searchInput.oninput = (e) => {
        const query = e.target.value.toLowerCase();
        const cards = container.querySelectorAll('.card');
        cards.forEach(card => {
          const text = card.textContent.toLowerCase();
          card.style.display = text.includes(query) ? '' : 'none';
        });
      };
    }
    
  } catch (error) {
    container.innerHTML = `<div class="error">Chyba při načítání: ${error.message}</div>`;
  }
}

async function loadServiceRegistrationRequests() {
  const container = document.getElementById('service-requests-container');
  if (!container) return;

  container.innerHTML = '<div class="loading">Načítám čekající žádosti...</div>';

  try {
    const requests = await fetchAllList('/admin-api/service-registration-requests?status=pending');
    if (!requests.length) {
      container.innerHTML = '<div class="empty">Žádné čekající žádosti o servisní registraci.</div>';
      return;
    }

    container.innerHTML = requests.map((item) => {
      const createdAt = formatDateTime(item.created_at, '-');
      const address = [item.street, item.street_number, item.city, item.zip]
        .filter(Boolean)
        .join(', ');
      return `
        <article class="service-request-item">
          <div class="service-request-main">
            <div>
              <p class="service-request-title">🛠️ ${escapeHtml(item.service_name || '-')}</p>
              <p class="service-request-meta">
                Email: <strong>${escapeHtml(item.email || '-')}</strong><br>
                IČO: <strong>${escapeHtml(item.ico || '-')}</strong> ${item.dic ? `• DIČ: <strong>${escapeHtml(item.dic)}</strong>` : ''}<br>
                Zodpovědná osoba: <strong>${escapeHtml(item.responsible_person || '-')}</strong><br>
                Telefon: <strong>${escapeHtml(item.phone || '-')}</strong><br>
                Adresa: <strong>${escapeHtml(address || '-')}</strong><br>
                Podáno: <strong>${escapeHtml(createdAt)}</strong>
              </p>
            </div>
            <span class="status-pill status-warn">Čeká na schválení</span>
          </div>
          <div class="service-request-purpose"><strong>Účel registrace:</strong><br>${escapeHtml(item.registration_purpose || '-')}</div>
          <div class="service-request-actions">
            <button class="btn-primary btn-sm" onclick="approveServiceRegistrationRequest(${item.id})">✅ Schválit</button>
            <button class="btn-danger btn-sm" onclick="rejectServiceRegistrationRequest(${item.id})">❌ Zamítnout</button>
          </div>
        </article>
      `;
    }).join('');
  } catch (error) {
    container.innerHTML = `<div class="error">Chyba při načítání žádostí: ${escapeHtml(error.message || 'Neznámá chyba')}</div>`;
  }
}

async function approveServiceRegistrationRequest(requestId) {
  if (!confirm('Opravdu chcete schválit tuto servisní registraci a vytvořit aktivní servisní účet?')) {
    return;
  }

  const reviewNoteRaw = prompt('Poznámka ke schválení (volitelné):', 'Schváleno po kontrole údajů.');
  if (reviewNoteRaw === null) {
    return;
  }

  try {
    await apiRequest('POST', `/admin-api/service-registration-requests/${requestId}/approve`, {
      review_note: reviewNoteRaw || null
    });
    showSuccess('Žádost byla schválena a servisní účet vytvořen.');
    await Promise.all([loadServices(), loadOverview()]);
  } catch (error) {
    console.error('Error approving service registration request:', error);
  }
}

async function rejectServiceRegistrationRequest(requestId) {
  if (!confirm('Opravdu chcete zamítnout tuto servisní registraci?')) {
    return;
  }

  const reviewNoteRaw = prompt('Důvod zamítnutí (doporučeno):', 'Žádost byla zamítnuta po kontrole údajů.');
  if (reviewNoteRaw === null) {
    return;
  }

  try {
    await apiRequest('POST', `/admin-api/service-registration-requests/${requestId}/reject`, {
      review_note: reviewNoteRaw || null
    });
    showSuccess('Žádost byla zamítnuta.');
    await Promise.all([loadServiceRegistrationRequests(), loadOverview()]);
  } catch (error) {
    console.error('Error rejecting service registration request:', error);
  }
}

async function showServiceModal(serviceId = null) {
  const modal = document.getElementById('service-modal');
  const title = document.getElementById('service-modal-title');
  const passwordHint = document.getElementById('service-password-hint');
  const passwordInput = document.getElementById('service-password');
  
  if (serviceId) {
    title.textContent = 'Upravit servis';
    passwordHint.textContent = '(nechte prázdné, pokud neměníte)';
    passwordInput.required = false;
    
    try {
      const services = await fetchAllList('/admin-api/services');
      const service = services.find(s => s.id === serviceId);
      if (service) {
        document.getElementById('service-id').value = service.id;
        document.getElementById('service-email').value = service.email || '';
        document.getElementById('service-name').value = service.name || '';
        document.getElementById('service-city').value = service.city || '';
        document.getElementById('service-phone').value = service.phone || '';
        document.getElementById('service-ico').value = service.ico || '';
        passwordInput.value = '';
      }
    } catch (error) {
      showGlobalError('Chyba při načítání servisu: ' + error.message);
      return;
    }
  } else {
    title.textContent = 'Přidat servis';
    passwordHint.textContent = '(povinné při vytvoření)';
    document.getElementById('service-form').reset();
    document.getElementById('service-id').value = '';
    passwordInput.required = true;
  }
  
  modal.classList.remove('hidden');
}

function closeServiceModal() {
  document.getElementById('service-modal').classList.add('hidden');
  document.getElementById('service-form').reset();
}

async function saveService(event) {
  event.preventDefault();
  
  const serviceId = document.getElementById('service-id').value;
  const serviceData = {
    email: document.getElementById('service-email').value,
    name: document.getElementById('service-name').value,
    city: document.getElementById('service-city').value || null,
    phone: document.getElementById('service-phone').value || null,
    ico: document.getElementById('service-ico').value || null,
  };
  
  const password = document.getElementById('service-password').value;
  if (password) {
    serviceData.password = password;
  }
  
  try {
    if (serviceId) {
      await apiRequest('PATCH', `/admin-api/services/${serviceId}`, serviceData);
      showSuccess('Servis byl upraven');
    } else {
      if (!password) {
        showGlobalError('Heslo je povinné při vytváření servisu');
        return;
      }
      await apiRequest('POST', '/admin-api/services', serviceData);
      showSuccess('Servis byl vytvořen');
    }
    
    closeServiceModal();
    loadServices();
    loadOverview();
  } catch (error) {
    console.error('Error saving service:', error);
  }
}

async function editService(serviceId) {
  showServiceModal(serviceId);
}

async function deleteService(serviceId, serviceName) {
  if (!confirm(`Opravdu chcete smazat servis ${serviceName}?`)) {
    return;
  }
  
  try {
    await apiRequest('DELETE', `/admin-api/services/${serviceId}`);
    showSuccess('Servis byl smazán');
    loadServices();
    loadOverview();
  } catch (error) {
    console.error('Error deleting service:', error);
  }
}

// ============================================
// RECORDS CRUD
// ============================================

async function loadRecords() {
  const container = document.getElementById('records-cards-container');
  if (!container) return;
  
  container.innerHTML = '<div class="loading">Načítám záznamy...</div>';
  
  try {
    const response = await apiRequest('GET', withQueryParams('/admin-api/records', { limit: 500, offset: 0 }));
    const records = Array.isArray(response) ? response : (response.records || []);
    
    if (records.length === 0) {
      container.innerHTML = '<div class="empty">Žádné záznamy</div>';
      applySectionViewMode('records');
      return;
    }
    
    container.innerHTML = records.map(record => {
      const performedDate = record.performed_at ? new Date(record.performed_at).toLocaleDateString('cs-CZ') : '-';
      const serviceLabel = record.user_name || record.user_email || (record.user_id ? `#${record.user_id}` : '-');
      const vehicleLabel = record.vehicle_nickname
        || `${record.vehicle_brand || ''} ${record.vehicle_model || ''}`.trim()
        || record.vehicle_plate
        || (record.vehicle_id ? `#${record.vehicle_id}` : '-');
      return `
        <div class="card" data-record-id="${record.id}">
          <div class="card-header">
            <h3 class="card-title">📋 ${record.description || 'Bez popisu'}</h3>
            <span class="card-id">#${record.id}</span>
          </div>
          <div class="card-body">
            <div class="card-field">
              <span class="card-label">Servis</span>
              <span class="card-value">${serviceLabel}</span>
            </div>
            <div class="card-field">
              <span class="card-label">Vozidlo</span>
              <span class="card-value">${vehicleLabel}</span>
            </div>
            <div class="card-field">
              <span class="card-label">Datum provedení</span>
              <span class="card-value">${performedDate}</span>
            </div>
            ${record.mileage ? `
            <div class="card-field">
              <span class="card-label">Nájezd</span>
              <span class="card-value">${record.mileage.toLocaleString('cs-CZ')} km</span>
            </div>
            ` : ''}
            ${record.price ? `
            <div class="card-field">
              <span class="card-label">Cena</span>
              <span class="card-value" style="color: #059669; font-weight: 700;">${record.price.toLocaleString('cs-CZ')} Kč</span>
            </div>
            ` : ''}
            ${record.category ? `
            <div class="card-field">
              <span class="card-label">Kategorie</span>
              <span class="card-value">${record.category}</span>
            </div>
            ` : ''}
          </div>
          <div class="card-actions">
            <button class="btn-edit" onclick="editRecord(${record.id})">✏️ Upravit</button>
            <button class="btn-danger" onclick="deleteRecord(${record.id})">🗑️ Smazat</button>
          </div>
        </div>
      `;
    }).join('');
    applySectionViewMode('records');
    
    // Vyhledávání
    const searchInput = document.getElementById('record-search');
    if (searchInput) {
      searchInput.oninput = (e) => {
        const query = e.target.value.toLowerCase();
        const cards = container.querySelectorAll('.card');
        cards.forEach(card => {
          const text = card.textContent.toLowerCase();
          card.style.display = text.includes(query) ? '' : 'none';
        });
      };
    }
    
  } catch (error) {
    container.innerHTML = `<div class="error">Chyba při načítání: ${error.message}</div>`;
  }
}

function buildRecordActorLabel(user) {
  if (!user) return '-';
  const roleLabel = ({
    service: 'servis',
    user: 'uživatel',
    admin: 'admin',
    developer_admin: 'developer admin',
  })[user.role] || user.role || 'uživatel';
  return `${user.name || user.email || `ID ${user.id}`} (${roleLabel})`;
}

function renderRecordServiceSelect(selectedVehicleId = null, selectedUserId = null) {
  const serviceSelect = document.getElementById('record-service-id');
  if (!serviceSelect) return;

  const selectedVehicle = recordFormOptionsState.vehicles.find(
    (vehicle) => Number(vehicle.id) === Number(selectedVehicleId),
  );
  const selectedVehicleTenantId = selectedVehicle?.tenant_id ?? null;

  let users = recordFormOptionsState.users;
  if (selectedVehicleTenantId !== null && selectedVehicleTenantId !== undefined) {
    users = users.filter((user) => Number(user.tenant_id) === Number(selectedVehicleTenantId));
  }

  users = [...users].sort((a, b) => {
    const aRole = String(a.role || '');
    const bRole = String(b.role || '');
    if (aRole === bRole) {
      return String(a.name || a.email || '').localeCompare(String(b.name || b.email || ''));
    }
    if (aRole === 'service') return -1;
    if (bRole === 'service') return 1;
    return aRole.localeCompare(bRole);
  });

  let html = '<option value="">Bez přiřazení</option>';
  if (!selectedVehicleId) {
    html += '<option value="" disabled>Nejprve vyberte vozidlo</option>';
    serviceSelect.innerHTML = html;
    serviceSelect.disabled = true;
    return;
  }

  html += users.map((user) => {
    const label = buildRecordActorLabel(user);
    return `<option value="${user.id}">${escapeHtml(label)}</option>`;
  }).join('');

  // Pokud je u editace historicky přiřazen uživatel mimo tenant, zobrazíme ho explicitně.
  if (
    selectedUserId
    && !users.some((user) => Number(user.id) === Number(selectedUserId))
  ) {
    const foreignUser = recordFormOptionsState.users.find((user) => Number(user.id) === Number(selectedUserId));
    if (foreignUser) {
      html += `<option value="${foreignUser.id}">${escapeHtml(`${buildRecordActorLabel(foreignUser)} (mimo tenant)`)}`
        + '</option>';
    }
  }

  serviceSelect.innerHTML = html;
  serviceSelect.disabled = false;
  if (selectedUserId !== null && selectedUserId !== undefined && String(selectedUserId) !== '') {
    serviceSelect.value = String(selectedUserId);
  } else {
    serviceSelect.value = '';
  }
}

async function loadRecordFormData(selectedVehicleId = null, selectedUserId = null) {
  try {
    const [users, vehicles] = await Promise.all([
      fetchAllList('/admin-api/users'),
      fetchAllList('/admin-api/vehicles'),
    ]);

    recordFormOptionsState.users = Array.isArray(users) ? users : [];
    recordFormOptionsState.vehicles = Array.isArray(vehicles) ? vehicles : [];

    const vehicleSelect = document.getElementById('record-vehicle-id');
    if (vehicleSelect) {
      vehicleSelect.innerHTML = '<option value="">Vyberte vozidlo</option>' +
        recordFormOptionsState.vehicles.map((vehicle) => {
          const label = vehicle.nickname
            || `${vehicle.brand || ''} ${vehicle.model || ''}`.trim()
            || `ID ${vehicle.id}`;
          return `<option value="${vehicle.id}">${escapeHtml(`${label} (${vehicle.user_email || '-'})`)}</option>`;
        }).join('');

      if (selectedVehicleId !== null && selectedVehicleId !== undefined && String(selectedVehicleId) !== '') {
        vehicleSelect.value = String(selectedVehicleId);
      }

      vehicleSelect.onchange = (event) => {
        const vehicleId = parseInt(event.target.value, 10);
        renderRecordServiceSelect(Number.isFinite(vehicleId) ? vehicleId : null, null);
      };
    }

    renderRecordServiceSelect(selectedVehicleId, selectedUserId);
  } catch (error) {
    console.error('Error loading form data:', error);
  }
}

async function showRecordModal(recordId = null) {
  const modal = document.getElementById('record-modal');
  const title = document.getElementById('record-modal-title');

  if (recordId) {
    title.textContent = 'Upravit záznam';
    try {
      const response = await apiRequest('GET', withQueryParams('/admin-api/records', { limit: 500, offset: 0 }));
      const records = Array.isArray(response) ? response : (response.records || []);
      const record = records.find(r => r.id === recordId);
      if (record) {
        await loadRecordFormData(record.vehicle_id, record.user_id);
        document.getElementById('record-id').value = record.id;
        document.getElementById('record-vehicle-id').value = record.vehicle_id || '';
        renderRecordServiceSelect(record.vehicle_id || null, record.user_id || null);
        document.getElementById('record-service-id').value = record.user_id || '';
        document.getElementById('record-description').value = record.description || '';
        
        if (record.performed_at) {
          const date = new Date(record.performed_at);
          const localDate = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
          document.getElementById('record-performed-at').value = localDate.toISOString().slice(0, 16);
        }
        
        document.getElementById('record-mileage').value = record.mileage || '';
        document.getElementById('record-price').value = record.price || '';
        document.getElementById('record-category').value = record.category || '';
        document.getElementById('record-note').value = record.note || '';
      }
    } catch (error) {
      showGlobalError('Chyba při načítání záznamu: ' + error.message);
      return;
    }
  } else {
    title.textContent = 'Přidat záznam';
    document.getElementById('record-form').reset();
    document.getElementById('record-id').value = '';
    await loadRecordFormData(null, null);
    
    // Nastavit výchozí datum na teď
    const now = new Date();
    const localNow = new Date(now.getTime() - now.getTimezoneOffset() * 60000);
    document.getElementById('record-performed-at').value = localNow.toISOString().slice(0, 16);
  }
  
  modal.classList.remove('hidden');
}

function closeRecordModal(preserveReturnContext = false) {
  document.getElementById('record-modal').classList.add('hidden');
  document.getElementById('record-form').reset();
  if (!preserveReturnContext) {
    userDetailReturnContext = null;
  }
}

async function saveRecord(event) {
  event.preventDefault();
  
  const recordId = document.getElementById('record-id').value;
  const performedAtStr = document.getElementById('record-performed-at').value;
  const performedAt = performedAtStr ? new Date(performedAtStr) : new Date();
  
  const selectedUserId = parseInt(document.getElementById('record-service-id').value, 10);
  const selectedVehicleId = parseInt(document.getElementById('record-vehicle-id').value, 10);
  if (!Number.isFinite(selectedVehicleId)) {
    showGlobalError('Vyberte prosím vozidlo.');
    return;
  }

  const recordData = {
    user_id: Number.isFinite(selectedUserId) ? selectedUserId : null,
    vehicle_id: selectedVehicleId,
    performed_at: performedAt.toISOString(),
    description: document.getElementById('record-description').value,
    mileage: parseInt(document.getElementById('record-mileage').value) || null,
    price: parseFloat(document.getElementById('record-price').value) || null,
    category: document.getElementById('record-category').value || null,
    note: document.getElementById('record-note').value || null,
  };
  
  try {
    if (recordId) {
      await apiRequest('PATCH', `/admin-api/records/${recordId}`, recordData);
      showSuccess('Údaj byl upraven adminem: servisní záznam');
    } else {
      await apiRequest('POST', '/admin-api/records', recordData);
      showSuccess('Záznam byl vytvořen');
    }
    
    closeRecordModal(true);
    await Promise.all([loadRecords(), loadOverview()]);
    await reopenUserDetailIfNeeded();
  } catch (error) {
    console.error('Error saving record:', error);
  }
}

async function editRecord(recordId) {
  showRecordModal(recordId);
}

async function deleteRecord(recordId) {
  if (!confirm('Opravdu chcete smazat tento záznam?')) {
    return;
  }
  
  try {
    await apiRequest('DELETE', `/admin-api/records/${recordId}`);
    showSuccess('Záznam byl smazán');
    loadRecords();
    loadOverview();
  } catch (error) {
    console.error('Error deleting record:', error);
  }
}

// ============================================
// AUDIT LOG
// ============================================

async function loadAuditLog() {
  const listEl = document.getElementById('audit-log-list');
  if (!listEl) return;
  
  listEl.innerHTML = '<div class="loading">Načítám audit log...</div>';
  
  try {
    const entityType = document.getElementById('audit-entity-type')?.value || '';
    const action = document.getElementById('audit-action')?.value || '';
    
    let url = '/admin-api/audit?limit=100';
    if (entityType) url += `&entity_type=${entityType}`;
    if (action) url += `&action=${action}`;
    
    const auditData = await apiRequest('GET', url);
    const logs = auditData.logs || [];
    
    if (logs.length === 0) {
      listEl.innerHTML = '<div class="empty">Žádné záznamy v audit logu</div>';
      return;
    }
    
    listEl.innerHTML = logs.map(log => {
      const timestamp = log.timestamp ? new Date(log.timestamp).toLocaleString('cs-CZ') : '-';
      const actor = log.actor_email || `Uživatel #${log.actor_user_id || '?'}`;
      const actionText = getActionText(log.action || '');
      const entityType = log.entity_type || '?';
      const entityId = log.entity_id || '';
      
      return `
        <div class="audit-log-item">
          <div class="audit-log-header">
            <span class="audit-log-time">${timestamp}</span>
            <span class="audit-log-project">${log.source_project || '?'}</span>
          </div>
          <div class="audit-log-content">
            <strong>${actor}</strong> ${actionText} <strong>${entityType}</strong>
            ${entityId ? `#${entityId}` : ''}
          </div>
          ${log.details ? `<div class="audit-log-details">${log.details}</div>` : ''}
        </div>
      `;
    }).join('');
    
  } catch (error) {
    listEl.innerHTML = `<div class="error">Chyba při načítání: ${error.message}</div>`;
  }
}

// ============================================
// SYSTEM TOOLS
// ============================================

async function runReindex() {
  const resultEl = document.getElementById('reindex-result');
  if (!resultEl) return;
  
  resultEl.innerHTML = '<div class="loading">Probíhá reindexace...</div>';
  
  try {
    const result = await apiRequest('POST', '/admin-api/reindex');
    const results = Array.isArray(result?.results) ? result.results : [];
    resultEl.innerHTML = `
      <div style="color: #28a745;">
        <strong>✓ ${result?.message || 'Reindexace dokončena'}</strong>
        ${results.length > 0 ? `
        <ul style="margin-top: 8px; padding-left: 20px;">
          ${results.map(r => `<li>${r}</li>`).join('')}
        </ul>
        ` : ''}
      </div>
    `;
    loadOverview(); // Aktualizovat statistiky
  } catch (error) {
    resultEl.innerHTML = `<div style="color: #dc3545;">Chyba: ${error.message}</div>`;
  }
}

async function runRepair() {
  const resultEl = document.getElementById('repair-result');
  if (!resultEl) return;
  
  resultEl.innerHTML = '<div class="loading">Probíhá oprava...</div>';
  
  try {
    const result = await apiRequest('POST', '/admin-api/repair');
    const results = Array.isArray(result?.results) ? result.results : [];
    resultEl.innerHTML = `
      <div style="color: #28a745;">
        <strong>✓ ${result?.message || 'Oprava dokončena'}</strong>
        ${results.length > 0 ? `
        <ul style="margin-top: 8px; padding-left: 20px;">
          ${results.map(r => `<li>${r}</li>`).join('')}
        </ul>
        ` : ''}
      </div>
    `;
  } catch (error) {
    resultEl.innerHTML = `<div style="color: #dc3545;">Chyba: ${error.message}</div>`;
  }
}

async function loadDbInfo() {
  const resultEl = document.getElementById('db-info-result');
  if (!resultEl) return;
  
  resultEl.innerHTML = '<div class="loading">Načítám informace...</div>';
  
  try {
    const info = await apiRequest('GET', '/admin-api/db-info');
    resultEl.innerHTML = `
      <div>
        <p><strong>Cesta k databázi:</strong><br>${info.db_path}</p>
        <p><strong>Počet tabulek:</strong> ${info.table_count}</p>
        ${info.total_size_kb ? `<p><strong>Velikost:</strong> ${info.total_size_kb.toFixed(2)} KB</p>` : ''}
        <p><strong>Tabulky:</strong><br>${info.tables.join(', ')}</p>
      </div>
    `;
  } catch (error) {
    resultEl.innerHTML = `<div style="color: #dc3545;">Chyba: ${error.message}</div>`;
  }
}

// ============================================
// SETTINGS
// ============================================

let allSettings = {};
let currentSettingsCategory = 'general';

async function loadSettings() {
  const loadingEl = document.getElementById('settings-loading');
  const errorEl = document.getElementById('settings-error');
  const contentEl = document.getElementById('settings-content');
  
  loadingEl.classList.remove('hidden');
  errorEl.classList.add('hidden');
  contentEl.classList.add('hidden');
  
  try {
    const response = await apiRequest('GET', '/admin-api/settings');
    allSettings = response.settings || {};
    
    // Zobrazit první kategorii
    showSettingsCategory('general');
    
    loadingEl.classList.add('hidden');
    contentEl.classList.remove('hidden');
  } catch (error) {
    loadingEl.classList.add('hidden');
    errorEl.textContent = `Chyba při načítání nastavení: ${error.message}`;
    errorEl.classList.remove('hidden');
    console.error('Error loading settings:', error);
  }
}

function showSettingsCategory(category) {
  currentSettingsCategory = category;
  
  // Aktualizovat aktivní tab
  document.querySelectorAll('.settings-tab').forEach(tab => {
    if (tab.dataset.category === category) {
      tab.classList.add('active');
    } else {
      tab.classList.remove('active');
    }
  });
  
  // Zobrazit obsah kategorie
  renderSettingsCategory(category);
}

function renderSettingsCategory(category) {
  const container = document.getElementById('settings-categories');
  const categorySettings = allSettings[category] || {};
  
  const categoryConfigs = {
    general: {
      title: 'Obecná nastavení',
      groups: [
        {
          title: 'Aplikace',
          settings: [
            { key: 'app_name', label: 'Název aplikace', type: 'text', desc: 'Název aplikace' },
            { key: 'app_version', label: 'Verze', type: 'text', desc: 'Verze aplikace' },
            { key: 'app_description', label: 'Popis', type: 'textarea', desc: 'Popis aplikace' },
            { key: 'maintenance_mode', label: 'Režim údržby', type: 'checkbox', desc: 'Zapnout režim údržby' }
          ]
        }
      ]
    },
    security: {
      title: 'Bezpečnost',
      groups: [
        {
          title: 'Autentizace',
          settings: [
            { key: 'jwt_expiration_hours', label: 'Platnost JWT tokenu (hodiny)', type: 'number', desc: 'Jak dlouho je token platný' },
            { key: 'session_timeout_minutes', label: 'Timeout session (minuty)', type: 'number', desc: 'Automatické odhlášení po nečinnosti' },
            { key: 'max_login_attempts', label: 'Max. pokusů o přihlášení', type: 'number', desc: 'Počet pokusů před zablokováním' }
          ]
        },
        {
          title: 'Hesla',
          settings: [
            { key: 'password_min_length', label: 'Minimální délka hesla', type: 'number', desc: 'Minimální počet znaků' },
            { key: 'password_require_uppercase', label: 'Vyžadovat velká písmena', type: 'checkbox', desc: 'Heslo musí obsahovat velká písmena' },
            { key: 'password_require_numbers', label: 'Vyžadovat čísla', type: 'checkbox', desc: 'Heslo musí obsahovat čísla' }
          ]
        }
      ]
    },
    database: {
      title: 'Databáze',
      groups: [
        {
          title: 'Zálohování',
          settings: [
            { key: 'backup_enabled', label: 'Automatické zálohování', type: 'checkbox', desc: 'Povolit automatické zálohování' },
            { key: 'backup_frequency_hours', label: 'Frekvence zálohování (hodiny)', type: 'number', desc: 'Jak často se má zálohovat' },
            { key: 'backup_retention_days', label: 'Uchování záloh (dny)', type: 'number', desc: 'Kolik dní uchovávat zálohy' },
            { key: 'backup_path', label: 'Cesta k zálohám', type: 'text', desc: 'Složka pro ukládání záloh' }
          ]
        }
      ]
    },
    server: {
      title: 'Server',
      groups: [
        {
          title: 'Síť',
          settings: [
            { key: 'host', label: 'Host', type: 'text', desc: 'IP adresa nebo hostname' },
            { key: 'port', label: 'Port', type: 'number', desc: 'Port serveru' }
          ]
        },
        {
          title: 'CORS',
          settings: [
            { key: 'cors_enabled', label: 'Povolit CORS', type: 'checkbox', desc: 'Povolit Cross-Origin Resource Sharing' },
            { key: 'cors_origins', label: 'Povolené origins', type: 'textarea', desc: 'JSON pole povolených originů' }
          ]
        },
        {
          title: 'Rate Limiting',
          settings: [
            { key: 'rate_limit_enabled', label: 'Povolit rate limiting', type: 'checkbox', desc: 'Omezit počet požadavků' },
            { key: 'rate_limit_per_minute', label: 'Požadavků za minutu', type: 'number', desc: 'Maximální počet požadavků za minutu' }
          ]
        }
      ]
    },
    email: {
      title: 'E-maily',
      groups: [
        {
          title: 'SMTP',
          settings: [
            { key: 'smtp_enabled', label: 'Povolit SMTP', type: 'checkbox', desc: 'Zapnout odesílání e-mailů' },
            { key: 'smtp_host', label: 'SMTP host', type: 'text', desc: 'Adresa SMTP serveru' },
            { key: 'smtp_port', label: 'SMTP port', type: 'number', desc: 'Port SMTP serveru' },
            { key: 'smtp_user', label: 'SMTP uživatel', type: 'text', desc: 'Uživatelské jméno' },
            { key: 'smtp_from', label: 'Odesílatel', type: 'email', desc: 'E-mailová adresa odesílatele' }
          ]
        }
      ]
    },
    logging: {
      title: 'Logování',
      groups: [
        {
          title: 'Konfigurace',
          settings: [
            { key: 'log_level', label: 'Úroveň logování', type: 'select', desc: 'Minimální úroveň logů', options: ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'] },
            { key: 'log_file_enabled', label: 'Ukládat do souboru', type: 'checkbox', desc: 'Ukládat logy do souboru' },
            { key: 'log_file_path', label: 'Cesta k logům', type: 'text', desc: 'Složka pro ukládání logů' },
            { key: 'log_rotation_days', label: 'Rotace logů (dny)', type: 'number', desc: 'Po kolika dnech rotovat logy' }
          ]
        }
      ]
    },
    ui: {
      title: 'Vzhled',
      groups: [
        {
          title: 'Téma',
          settings: [
            { key: 'theme', label: 'Téma', type: 'select', desc: 'Vzhled aplikace', options: ['light', 'dark', 'auto'] },
            { key: 'primary_color', label: 'Primární barva', type: 'text', desc: 'Hex kód primární barvy' },
            { key: 'items_per_page', label: 'Položek na stránku', type: 'number', desc: 'Výchozí počet položek v seznamech' }
          ]
        }
      ]
    },
    api: {
      title: 'API',
      groups: [
        {
          title: 'Konfigurace',
          settings: [
            { key: 'api_docs_enabled', label: 'Povolit API dokumentaci', type: 'checkbox', desc: 'Zobrazit Swagger dokumentaci' },
            { key: 'api_rate_limit', label: 'API rate limit', type: 'number', desc: 'Maximální počet API požadavků za minutu' }
          ]
        }
      ]
    },
    comgate: {
      title: 'Comgate',
      groups: [
        {
          title: 'Základní nastavení',
          settings: [
            { key: 'enabled', label: 'Aktivovat Comgate', type: 'checkbox', desc: 'Globálně zapnout platební bránu v aplikaci' },
            { key: 'merchant', label: 'Merchant ID', type: 'text', desc: 'Merchant identifikátor z Comgate portálu' },
            { key: 'secret', label: 'Secret', type: 'text', desc: 'Heslo/secret pro serverovou komunikaci' },
            { key: 'test_mode', label: 'Testovací režim', type: 'checkbox', desc: 'Používat test mód Comgate' },
            { key: 'currency', label: 'Měna', type: 'select', desc: 'Měna plateb', options: ['CZK', 'EUR', 'USD'] },
            { key: 'lang', label: 'Jazyk brány', type: 'select', desc: 'Jazyk platební stránky', options: ['cs', 'en', 'sk', 'de'] },
            { key: 'country', label: 'Země', type: 'text', desc: 'Kód země (např. CZ)' }
          ]
        },
        {
          title: 'Platební režim',
          settings: [
            { key: 'method', label: 'Výchozí metoda', type: 'select', desc: 'ALL/CARD/BANK', options: ['ALL', 'CARD', 'BANK'] },
            { key: 'subscription_method', label: 'Metoda předplatného', type: 'select', desc: 'Pro recurring doporučeno CARD', options: ['CARD', 'ALL'] },
            { key: 'test_one_time_fallback', label: 'Test fallback bez recurring', type: 'checkbox', desc: 'Použít jednorázový fallback při testu' }
          ]
        },
        {
          title: 'Comgate endpointy',
          settings: [
            { key: 'create_url', label: 'Create URL', type: 'text', desc: 'Endpoint pro založení platby' },
            { key: 'status_url', label: 'Status URL', type: 'text', desc: 'Endpoint pro kontrolu statusu' },
            { key: 'recurring_url', label: 'Recurring URL', type: 'text', desc: 'Endpoint pro opakované stržení' }
          ]
        },
        {
          title: 'Ceník (haléře)',
          settings: [
            { key: 'price_basic_monthly_halers', label: 'BASIC měsíčně', type: 'number', desc: 'Např. 9900 = 99 Kč' },
            { key: 'price_basic_yearly_halers', label: 'BASIC ročně', type: 'number', desc: 'Roční cena v haléřích' },
            { key: 'price_premium_monthly_halers', label: 'PREMIUM měsíčně', type: 'number', desc: 'Např. 29900 = 299 Kč' },
            { key: 'price_premium_yearly_halers', label: 'PREMIUM ročně', type: 'number', desc: 'Roční cena v haléřích' }
          ]
        },
        {
          title: 'Předplatné lifecycle',
          settings: [
            { key: 'subscription_grace_days', label: 'Grace period (dny)', type: 'number', desc: 'Počet dní po neúspěšné obnově' },
            { key: 'subscription_notify_days', label: 'Dny upozornění (CSV)', type: 'text', desc: 'Např. 14,7,1' }
          ]
        }
      ]
    },
    system: {
      title: 'Systémové',
      groups: [
        {
          title: 'Desktop aplikace',
          settings: [
            { key: 'autostart_enabled', label: 'Automatický start při bootu', type: 'checkbox', desc: 'Spustit aplikaci při startu PC' },
          ]
        }
      ]
    }
  };
  
  const config = categoryConfigs[category] || { title: category, groups: [] };
  
  let html = `<div class="settings-category active" data-category="${category}">`;
  html += `<h2 style="margin-bottom: 24px; font-size: 24px; color: #1e293b;">${config.title}</h2>`;
  html += `<div class="settings-category-grid">`;
  
  config.groups.forEach(group => {
    html += `<div class="settings-group">`;
    html += `<h4>${group.title}</h4>`;
    
    // Escape HTML pro bezpečnost
    const escapeHtml = (text) => {
      if (text === null || text === undefined) return '';
      const div = document.createElement('div');
      div.textContent = String(text);
      return div.innerHTML;
    };
    
    group.settings.forEach(setting => {
      const settingData = categorySettings[setting.key] || {};
      const value = settingData.value !== undefined ? settingData.value : '';
      const desc = settingData.description || setting.desc;
      
      html += `<div class="setting-item">`;
      html += `<label for="setting-${escapeHtml(category)}-${escapeHtml(setting.key)}">${escapeHtml(setting.label)}</label>`;
      if (desc) {
        html += `<div class="setting-description">${escapeHtml(desc)}</div>`;
      }
      
      if (setting.type === 'checkbox') {
        const checked = value === true || value === 'true' || value === 1 || value === '1';
        const idAttr = `setting-${escapeHtml(category)}-${escapeHtml(setting.key)}`;
        html += `<div class="checkbox-wrapper">`;
        html += `<input type="checkbox" id="${idAttr}" data-category="${escapeHtml(category)}" data-key="${escapeHtml(setting.key)}" ${checked ? 'checked' : ''}>`;
        html += `<label for="${idAttr}" style="margin: 0;">${checked ? 'Zapnuto' : 'Vypnuto'}</label>`;
        html += `</div>`;
      } else if (setting.type === 'select') {
        const idAttr = `setting-${escapeHtml(category)}-${escapeHtml(setting.key)}`;
        html += `<select id="${idAttr}" data-category="${escapeHtml(category)}" data-key="${escapeHtml(setting.key)}">`;
        setting.options.forEach(opt => {
          const selected = value === opt ? 'selected' : '';
          html += `<option value="${escapeHtml(opt)}" ${selected}>${escapeHtml(opt)}</option>`;
        });
        html += `</select>`;
      } else if (setting.type === 'textarea') {
        const idAttr = `setting-${escapeHtml(category)}-${escapeHtml(setting.key)}`;
        html += `<textarea id="${idAttr}" data-category="${escapeHtml(category)}" data-key="${escapeHtml(setting.key)}" rows="3">${escapeHtml(String(value))}</textarea>`;
      } else {
        const inputType = setting.type === 'email' ? 'email' : setting.type === 'number' ? 'number' : 'text';
        const idAttr = `setting-${escapeHtml(category)}-${escapeHtml(setting.key)}`;
        html += `<input type="${inputType}" id="${idAttr}" data-category="${escapeHtml(category)}" data-key="${escapeHtml(setting.key)}" value="${escapeHtml(String(value))}">`;
      }
      
      html += `</div>`;
    });
    
    html += `</div>`;
  });
  
  html += `</div></div>`;
  
  container.innerHTML = html;
  
  // Přidat event listenery pro checkboxy
  container.querySelectorAll('input[type="checkbox"]').forEach(cb => {
    cb.addEventListener('change', function() {
      const label = this.nextElementSibling;
      label.textContent = this.checked ? 'Zapnuto' : 'Vypnuto';
    });
  });
}

async function saveAllSettings() {
  try {
    const settingsToSave = [];
    
    // Projít všechny inputy, selecty a textarey
    document.querySelectorAll('[data-category][data-key]').forEach(el => {
      const category = el.dataset.category;
      const key = el.dataset.key;
      let value = el.value;
      
      if (el.type === 'checkbox') {
        value = el.checked;
      } else if (el.type === 'number') {
        value = parseFloat(value) || 0;
      }
      
      // Zjistit typ hodnoty
      const settingData = allSettings[category]?.[key] || {};
      let valueType = settingData.value_type || 'string';
      
      if (typeof value === 'boolean') {
        valueType = 'boolean';
      } else if (typeof value === 'number') {
        valueType = 'number';
      } else if (el.tagName === 'TEXTAREA' && (key.includes('origins') || key.includes('json'))) {
        valueType = 'json';
      }
      
      settingsToSave.push({
        category,
        key,
        value,
        value_type: valueType,
        description: settingData.description || null
      });
    });
    
    await apiRequest('PUT', '/admin-api/settings', { settings: settingsToSave });
    showSuccess('Nastavení byla úspěšně uložena');
    
    // Znovu načíst nastavení
    await loadSettings();
  } catch (error) {
    showGlobalError(`Chyba při ukládání nastavení: ${error.message}`);
  }
}

function resetSettingsCategory() {
  if (confirm('Opravdu chcete obnovit všechna nastavení v této kategorii na výchozí hodnoty?')) {
    showSettingsCategory(currentSettingsCategory);
  }
}

async function initDefaultSettings() {
  if (!confirm('Tato akce vytvoří výchozí nastavení aplikace. Pokračovat?')) {
    return;
  }
  
  try {
    await apiRequest('POST', '/admin-api/settings/init-defaults');
    showSuccess('Výchozí nastavení byla úspěšně vytvořena');
    await loadSettings();
  } catch (error) {
    showGlobalError(`Chyba při inicializaci nastavení: ${error.message}`);
  }
}

// ============================================
// DEVELOPER CONTROL CENTER
// ============================================

const CONTROL_CENTER_TECHNICAL_RESULT_IDS = {
  'cc-health-result': 'cc-health-technical',
  'cc-payments-result': 'cc-payments-technical',
  'cc-presence-result': 'cc-presence-technical',
  'cc-security-result': 'cc-security-technical',
  'cc-backup-result': 'cc-backup-technical',
  'cc-infra-result': 'cc-infra-technical',
  'cc-ops-result': 'cc-ops-technical',
  'cc-logs-result': 'cc-logs-technical',
  'cc-notifications-result': 'cc-notifications-technical',
};

const CONTROL_CENTER_RAW_RESULT_IDS = new Set(['cc-insight-result', 'cc-command-result']);

function setControlCenterState(key, value) {
  controlCenterDataState[key] = value;
  controlCenterDataState.lastUpdatedAt = new Date().toISOString();
  renderControlCenterDashboard();
}

function setControlCenterText(id, value) {
  const el = document.getElementById(id);
  if (el) {
    el.textContent = String(value ?? '-');
  }
}

function setControlCenterKpi(id, value, tone = '') {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = String(value ?? '-');
  el.classList.remove('is-ok', 'is-warn', 'is-alert');
  if (tone) {
    el.classList.add(`is-${tone}`);
  }
}

function setControlCenterStatusChip(id, tone, text) {
  const el = document.getElementById(id);
  if (!el) return;
  el.classList.remove('is-ok', 'is-warn', 'is-alert');
  if (tone) {
    el.classList.add(`is-${tone}`);
  }
  el.textContent = text;
}

function setControlCenterHealthChip(id, label, status) {
  const el = document.getElementById(id);
  if (!el) return;
  const normalized = String(status || 'unknown').toLowerCase();
  el.classList.remove('is-ok', 'is-warn', 'is-alert');
  if (normalized === 'ok') {
    el.classList.add('is-ok');
  } else if (normalized === 'warning') {
    el.classList.add('is-warn');
  } else if (normalized === 'error') {
    el.classList.add('is-alert');
  }
  el.textContent = `${label}: ${String(status || '-').toUpperCase()}`;
}

function parseIsoDate(value) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function isDateOlderThan(value, hours) {
  const date = parseIsoDate(value);
  if (!date) return true;
  return (Date.now() - date.getTime()) > (hours * 3600 * 1000);
}

function formatNumber(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return '0';
  return num.toLocaleString('cs-CZ');
}

function formatHalersToCzk(value) {
  const halers = Number(value);
  if (!Number.isFinite(halers)) return '-';
  const czk = halers / 100;
  return `${czk.toLocaleString('cs-CZ', { minimumFractionDigits: 0, maximumFractionDigits: 2 })} Kč`;
}

function formatShortDateTime(value) {
  return formatDateTime(value, '-');
}

function normalizeLicenseStatus(value) {
  return String(value || 'active').trim().toLowerCase();
}

function isPaidLicenseUser(user) {
  const plan = String(user?.license_plan || 'free').toLowerCase();
  const status = normalizeLicenseStatus(user?.license_status);
  const hasPaid = Boolean(user?.has_paid);
  if (['expired', 'inactive', 'suspended'].includes(status)) {
    return false;
  }
  return hasPaid || plan !== 'free';
}

function isUnpaidProblemUser(user) {
  const plan = String(user?.license_plan || 'free').toLowerCase();
  const status = normalizeLicenseStatus(user?.license_status);
  if (['expired', 'inactive', 'suspended'].includes(status)) {
    return true;
  }
  return plan !== 'free' && !Boolean(user?.has_paid);
}

function normalizePaymentEnvironment(item) {
  const explicit = String(item?.payment_environment || '').trim().toUpperCase();
  if (explicit === 'LIVE' || explicit === 'TEST') {
    return explicit;
  }
  const status = String(item?.provider_status || '').trim().toLowerCase();
  const eventType = String(item?.event_type || '').trim().toLowerCase();
  if (status.includes('test') || status.includes('sandbox') || eventType.includes('test') || eventType.includes('sandbox')) {
    return 'TEST';
  }
  return 'LIVE';
}

function isPaymentSuccessful(item) {
  const status = String(item?.provider_status || '').trim().toUpperCase();
  const eventType = String(item?.event_type || '').trim().toLowerCase();
  return status === 'PAID' || status === 'CONFIRMED'
    || eventType === 'payment_paid'
    || eventType === 'payment_confirmed'
    || eventType === 'subscription_renewal_paid'
    || eventType === 'paid_confirmed'
    || eventType === 'renewal_paid';
}

function isPaymentFailed(item) {
  const status = String(item?.provider_status || '').trim().toLowerCase();
  const eventType = String(item?.event_type || '').trim().toLowerCase();
  return status.includes('fail')
    || status.includes('error')
    || status.includes('declin')
    || status.includes('cancel')
    || status.includes('denied')
    || status.includes('timeout')
    || eventType.includes('fail')
    || eventType.includes('error')
    || eventType.includes('cancel')
    || eventType.includes('declin');
}

function isPaymentNeedsAttention(item) {
  const status = String(item?.provider_status || '').trim().toLowerCase();
  const refunded = String(item?.refund_status || '').trim().toLowerCase() === 'refunded';
  return refunded || isPaymentFailed(item) || status.includes('pending') || status.includes('created');
}

function isRecentlyActive(value, minutes = 15) {
  const date = parseIsoDate(value);
  if (!date) return false;
  return (Date.now() - date.getTime()) <= (minutes * 60 * 1000);
}

function buildControlCenterHealthDetail(component = {}) {
  if (component.error) return String(component.error);
  if (Object.prototype.hasOwnProperty.call(component, 'merchant_configured')) {
    return component.merchant_configured ? 'Merchant configured' : 'Merchant missing';
  }
  if (Object.prototype.hasOwnProperty.call(component, 'smtp_host_configured')) {
    return component.smtp_host_configured ? 'SMTP configured' : 'SMTP missing';
  }
  if (Object.prototype.hasOwnProperty.call(component, 'recent_api_activity_15m')) {
    return `Events 15m: ${formatNumber(component.recent_api_activity_15m)}`;
  }
  if (Object.prototype.hasOwnProperty.call(component, 'recent_events_tail_count')) {
    return `Webhook events: ${formatNumber(component.recent_events_tail_count)}`;
  }
  if (Object.prototype.hasOwnProperty.call(component, 'license_worker_paused')) {
    const paused = component.license_worker_paused || component.reminders_worker_paused;
    return paused ? 'Některé workers jsou pozastavené' : 'Workers aktivní';
  }
  return 'OK';
}

function renderControlCenterStatusLabel(status) {
  const normalized = String(status || 'unknown').toLowerCase();
  let klass = 'status-pill';
  if (normalized === 'ok') klass += ' status-ok';
  else if (normalized === 'warning') klass += ' status-warn';
  else if (normalized === 'error') klass += ' status-bad';
  return `<span class="${klass}">${escapeHtml(String(status || '-').toUpperCase())}</span>`;
}

function renderControlCenterPriorities(metrics) {
  const listEl = document.getElementById('cc-priority-list');
  if (!listEl) return;

  const priorities = [];
  if (metrics.healthTone === 'alert') {
    priorities.push({
      tone: 'alert',
      text: 'System health hlásí chybu. Zkontrolujte komponenty.',
      moduleId: 'cc-module-health',
      detailsId: 'cc-health-details',
    });
  } else if (metrics.healthTone === 'warn') {
    priorities.push({
      tone: 'warn',
      text: 'System health má varování. Ověřte konfiguraci a workers.',
      moduleId: 'cc-module-health',
      detailsId: 'cc-health-details',
    });
  }

  if (metrics.failedPayments > 0) {
    priorities.push({
      tone: metrics.failedPayments >= 5 ? 'alert' : 'warn',
      text: `Neúspěšné platby: ${formatNumber(metrics.failedPayments)}.`,
      moduleId: 'cc-module-payments',
      detailsId: 'cc-payments-details',
    });
  }

  if (metrics.securityAlerts > 0) {
    priorities.push({
      tone: 'alert',
      text: `Security alerty: ${formatNumber(metrics.securityAlerts)} (brute-force / blokace).`,
      moduleId: 'cc-module-security',
      detailsId: 'cc-security-details',
    });
  }

  if (metrics.expiredLicenses > 0) {
    priorities.push({
      tone: 'warn',
      text: `Expirované licence: ${formatNumber(metrics.expiredLicenses)}.`,
      moduleId: 'cc-module-users',
      detailsId: 'cc-users-details',
    });
  }

  if (metrics.backupTone !== 'ok') {
    priorities.push({
      tone: metrics.backupTone === 'alert' ? 'alert' : 'warn',
      text: metrics.backupTone === 'alert'
        ? 'Backup není dostupný nebo je nevalidní.'
        : 'Backup je starší než doporučené okno.',
      moduleId: 'cc-module-backups',
      detailsId: 'cc-backups-details',
    });
  }

  if (metrics.pausedJobs > 0) {
    priorities.push({
      tone: 'warn',
      text: `Pozastavené joby: ${formatNumber(metrics.pausedJobs)}.`,
      moduleId: 'cc-module-jobs',
      detailsId: 'cc-jobs-details',
    });
  }

  if (priorities.length === 0) {
    priorities.push({
      tone: 'ok',
      text: 'Žádné kritické problémy. Sledujte moduly pro průběžný dohled.',
    });
  }

  listEl.innerHTML = priorities.map((item) => `
    <li class="cc-priority-item is-${item.tone}">
      <span class="cc-priority-text">${escapeHtml(item.text)}</span>
      ${item.moduleId ? `<button class="cc-priority-action" type="button" onclick="focusControlCenterModule('${item.moduleId}', '${item.detailsId || ''}')">Otevřít</button>` : ''}
    </li>
  `).join('');
}

function renderControlCenterDashboard() {
  const users = Array.isArray(controlCenterDataState.users) ? controlCenterDataState.users : [];
  const presenceItems = Array.isArray(controlCenterDataState?.presence?.items) ? controlCenterDataState.presence.items : [];
  const paymentItems = Array.isArray(controlCenterDataState?.payments?.items) ? controlCenterDataState.payments.items : [];
  const security = controlCenterDataState.security || {};
  const securitySummary = security.summary || {};
  const topFailedIps = Array.isArray(security.top_failed_ips) ? security.top_failed_ips : [];
  const latestSecurityEvents = Array.isArray(security.latest_events) ? security.latest_events : [];
  const backupItems = Array.isArray(controlCenterDataState?.backups?.items) ? controlCenterDataState.backups.items : [];
  const jobs = Array.isArray(controlCenterDataState?.jobs?.jobs) ? controlCenterDataState.jobs.jobs : [];
  const emailSummary = controlCenterDataState?.email?.summary || {};
  const notifications = Array.isArray(controlCenterDataState?.notifications?.items) ? controlCenterDataState.notifications.items : [];
  const subscriptionsCapability = systemCapabilities.subscriptions || null;
  const notificationsCapability = systemCapabilities.system_notifications || null;
  const adminAuditCapability = systemCapabilities.admin_audit || null;
  const auditItems = Array.isArray(controlCenterDataState?.audit?.items) ? controlCenterDataState.audit.items : [];
  const apiItems = Array.isArray(controlCenterDataState?.apiMonitor?.items) ? controlCenterDataState.apiMonitor.items : [];
  const storagePayload = controlCenterDataState.storage || {};
  const webhookPayload = controlCenterDataState.webhookMonitor || {};
  const health = controlCenterDataState.health || {};
  const healthComponents = health.components || {};

  const onlineUsers = presenceItems.filter((item) => String(item.online_status || '').toUpperCase() === 'ONLINE').length;
  const offlineUsers = Math.max(0, presenceItems.length - onlineUsers);
  const recentlyActive = presenceItems.filter((item) => isRecentlyActive(item.last_seen_at, 30)).length;
  const suspiciousPresence = presenceItems.filter((item) => {
    const sessions = Number(item.active_session_count || 0);
    const online = String(item.online_status || '').toUpperCase() === 'ONLINE';
    return sessions >= 4 || (!online && sessions > 0 && isRecentlyActive(item.last_seen_at, 5));
  }).length;

  const paidLicenses = users.filter((user) => isPaidLicenseUser(user)).length;
  const expiredLicenses = users.filter((user) => normalizeLicenseStatus(user?.license_status) === 'expired').length;
  const disabledUsers = users.filter((user) => Boolean(user?.is_disabled)).length;
  const unpaidUsers = users.filter((user) => isUnpaidProblemUser(user)).length;

  const livePaymentItems = paymentItems.filter((item) => normalizePaymentEnvironment(item) === 'LIVE');
  const testPaymentItems = paymentItems.filter((item) => normalizePaymentEnvironment(item) === 'TEST');
  const livePaidCount = livePaymentItems.filter((item) => isPaymentSuccessful(item)).length;
  const testPaidCount = testPaymentItems.filter((item) => isPaymentSuccessful(item)).length;
  const paidTodayHalers = livePaymentItems
    .filter((item) => isPaymentSuccessful(item))
    .filter((item) => {
      const created = parseIsoDate(item.created_at);
      if (!created) return false;
      const now = new Date();
      return created.getFullYear() === now.getFullYear()
        && created.getMonth() === now.getMonth()
        && created.getDate() === now.getDate();
    })
    .reduce((acc, item) => acc + Number(item.amount_halers || 0), 0);
  const latestLivePaymentAt = livePaymentItems
    .filter((item) => isPaymentSuccessful(item))
    .map((item) => parseIsoDate(item.created_at))
    .filter(Boolean)
    .sort((a, b) => b.getTime() - a.getTime())[0] || null;
  const failedPayments = livePaymentItems.filter((item) => isPaymentFailed(item)).length;
  const refundedPayments = livePaymentItems.filter((item) => String(item.refund_status || '').toLowerCase() === 'refunded').length;
  const paymentsAttention = livePaymentItems.filter((item) => isPaymentNeedsAttention(item)).length;

  const blockedActive = Number(securitySummary.blocked_ips_active || 0);
  const bruteForceAlerts = topFailedIps.filter((item) => Number(item.failed_count || 0) >= 5).length;
  const rateLimited24h = Number(securitySummary.rate_limited_24h || 0);
  const suspiciousAuthEvents = latestSecurityEvents
    .filter((item) => {
      const type = String(item.event_type || '').toLowerCase();
      return type.includes('login_failed') || type.includes('rate_limited');
    })
    .length;
  const securityAlerts = bruteForceAlerts + blockedActive;

  const latestBackup = backupItems[0] || null;
  const latestBackupTime = latestBackup?.created_at || null;
  const backupCount = backupItems.length;
  const backupHealthy = Boolean(latestBackup && latestBackup.db_exists);
  const backupStale = latestBackup ? isDateOlderThan(latestBackup.created_at, 72) : true;

  const runningJobs = jobs.filter((job) => String(job.state || '').toLowerCase() === 'running').length;
  const pausedJobs = jobs.filter((job) => String(job.state || '').toLowerCase() === 'paused').length;
  const emailSent24h = Number(emailSummary.sent_24h || 0);
  const emailFailed24h = Number(emailSummary.failed_24h || 0);

  const activeNotifications = notifications.filter((item) => Boolean(item.is_active)).length;
  const lastCriticalAudit = auditItems.find((item) => {
    const result = String(item.result || '').toLowerCase();
    const code = Number(item.status_code || 0);
    return result === 'failed' || result === 'partial' || code >= 400;
  });

  const apiTop = apiItems[0] || null;
  const webhookFailed = Number(webhookPayload.failed_count || 0);
  const dbBytes = Number(storagePayload?.database?.size_bytes || 0);
  const dirs = storagePayload?.directories || {};
  const storageTotalBytes = dbBytes
    + Number(dirs?.data?.total_bytes || 0)
    + Number(dirs?.logs?.total_bytes || 0)
    + Number(dirs?.backups?.total_bytes || 0);

  let healthTone = 'ok';
  const healthStatuses = Object.values(healthComponents)
    .map((item) => String(item?.status || '').toLowerCase())
    .filter(Boolean);
  if (healthStatuses.some((status) => status === 'error')) {
    healthTone = 'alert';
  } else if (healthStatuses.some((status) => status === 'warning')) {
    healthTone = 'warn';
  }

  const paymentsTone = subscriptionsCapability && subscriptionsCapability.available === false
    ? 'warn'
    : (failedPayments > 0 ? (failedPayments >= 5 ? 'alert' : 'warn') : 'ok');
  const usersTone = expiredLicenses > 0 ? 'warn' : 'ok';
  const presenceTone = suspiciousPresence > 0 ? 'warn' : (onlineUsers > 0 ? 'ok' : 'warn');
  const securityTone = securityAlerts > 0 ? 'alert' : (rateLimited24h > 0 ? 'warn' : 'ok');
  const backupTone = !backupHealthy ? 'alert' : (backupStale ? 'warn' : 'ok');
  const jobsTone = (pausedJobs > 0 || emailFailed24h > 0) ? 'warn' : 'ok';
  const notificationsTone = notificationsCapability && notificationsCapability.available === false
    ? 'warn'
    : (notifications.length === 0 ? 'warn' : 'ok');
  const auditTone = lastCriticalAudit ? 'warn' : 'ok';
  const infraTone = webhookFailed > 0 ? 'warn' : 'ok';

  setControlCenterKpi('cc-kpi-active-users', formatNumber(onlineUsers), onlineUsers > 0 ? 'ok' : 'warn');
  setControlCenterKpi('cc-kpi-paid-licenses', formatNumber(paidLicenses), paidLicenses > 0 ? 'ok' : 'warn');
  setControlCenterKpi('cc-kpi-expired-licenses', formatNumber(expiredLicenses), expiredLicenses > 0 ? 'warn' : 'ok');
  setControlCenterKpi('cc-kpi-failed-payments', formatNumber(failedPayments), failedPayments > 0 ? 'alert' : 'ok');
  setControlCenterKpi('cc-kpi-security-alerts', formatNumber(securityAlerts), securityAlerts > 0 ? 'alert' : 'ok');
  setControlCenterKpi('cc-kpi-backup-status', backupHealthy ? 'OK' : 'NONE', backupTone);
  setControlCenterText('cc-kpi-backup-time', latestBackupTime ? formatShortDateTime(latestBackupTime) : 'Bez backupu');
  setControlCenterText('cc-kpi-last-updated', `Naposledy: ${formatShortDateTime(controlCenterDataState.lastUpdatedAt)}`);

  setControlCenterText('cc-users-total', formatNumber(users.length));
  setControlCenterText('cc-users-disabled', formatNumber(disabledUsers));
  setControlCenterText('cc-users-expired', formatNumber(expiredLicenses));
  setControlCenterText('cc-users-unpaid', formatNumber(unpaidUsers));

  setControlCenterText('cc-payments-paid-today', formatHalersToCzk(paidTodayHalers));
  setControlCenterText('cc-payments-live-paid-count', formatNumber(livePaidCount));
  setControlCenterText('cc-payments-failed', formatNumber(failedPayments));
  setControlCenterText('cc-payments-refunds', formatNumber(refundedPayments));
  setControlCenterText('cc-payments-attention', formatNumber(paymentsAttention));
  setControlCenterText('cc-payments-live-test-ratio', `${formatNumber(livePaymentItems.length)} / ${formatNumber(testPaymentItems.length)}`);
  setControlCenterText('cc-payments-live-last', latestLivePaymentAt ? formatShortDateTime(latestLivePaymentAt.toISOString()) : 'Žádná');

  setControlCenterText('cc-presence-online', formatNumber(onlineUsers));
  setControlCenterText('cc-presence-offline', formatNumber(offlineUsers));
  setControlCenterText('cc-presence-recent', formatNumber(recentlyActive));
  setControlCenterText('cc-presence-suspicious', formatNumber(suspiciousPresence));

  setControlCenterText('cc-security-blocked-active', formatNumber(blockedActive));
  setControlCenterText('cc-security-bruteforce', formatNumber(bruteForceAlerts));
  setControlCenterText('cc-security-rate-limited', formatNumber(rateLimited24h));
  setControlCenterText('cc-security-suspicious', formatNumber(suspiciousAuthEvents));

  setControlCenterText('cc-backup-latest-status', backupHealthy ? 'OK' : 'Nedostupný');
  setControlCenterText('cc-backup-latest-time', latestBackupTime ? formatShortDateTime(latestBackupTime) : '-');
  setControlCenterText('cc-backup-count', formatNumber(backupCount));
  setControlCenterText('cc-backup-restore-warning', 'Dangerous');

  setControlCenterText('cc-jobs-running', formatNumber(runningJobs));
  setControlCenterText('cc-jobs-paused', formatNumber(pausedJobs));
  setControlCenterText('cc-email-sent', formatNumber(emailSent24h));
  setControlCenterText('cc-email-failed', formatNumber(emailFailed24h));

  setControlCenterText('cc-notifications-active', formatNumber(activeNotifications));
  setControlCenterText('cc-notifications-total', formatNumber(notifications.length));
  setControlCenterText('cc-notifications-severity-preview', 'info');
  setControlCenterText('cc-notifications-target-preview', (document.getElementById('cc-broadcast-target-type')?.value || 'all'));

  setControlCenterText('cc-audit-count', formatNumber(auditItems.length));
  setControlCenterText('cc-audit-last-critical', lastCriticalAudit
    ? `${lastCriticalAudit.action_type || '-'} (${formatShortDateTime(lastCriticalAudit.created_at)})`
    : 'Žádná');

  setControlCenterText('cc-infra-api-hits', apiTop ? `${apiTop.endpoint || '-'}: ${formatNumber(apiTop.hits || 0)}` : '-');
  setControlCenterText('cc-infra-webhooks-failed', formatNumber(webhookFailed));
  setControlCenterText('cc-infra-storage', storageTotalBytes > 0 ? `${(storageTotalBytes / (1024 * 1024)).toFixed(1)} MB` : '-');
  setControlCenterText('cc-infra-cleanup-preview', controlCenterDataState?.storageCleanupPreview?.reclaimed_human || '-');

  setControlCenterStatusChip('cc-module-health-status', healthTone, healthTone === 'ok' ? 'Healthy' : (healthTone === 'warn' ? 'Warning' : 'Error'));
  setControlCenterStatusChip(
    'cc-module-payments-status',
    paymentsTone,
    subscriptionsCapability && subscriptionsCapability.available === false
      ? 'Disabled until migration'
      : (paymentsTone === 'ok' ? 'Stable' : (paymentsTone === 'warn' ? 'Attention' : 'Critical'))
  );
  setControlCenterStatusChip('cc-module-users-status', usersTone, usersTone === 'ok' ? 'Stable' : 'Attention');
  setControlCenterStatusChip('cc-module-presence-status', presenceTone, presenceTone === 'ok' ? 'Normal' : 'Attention');
  setControlCenterStatusChip('cc-module-security-status', securityTone, securityTone === 'ok' ? 'Normal' : (securityTone === 'warn' ? 'Warning' : 'Alert'));
  setControlCenterStatusChip('cc-module-backups-status', backupTone, backupTone === 'ok' ? 'Safe' : (backupTone === 'warn' ? 'Stale' : 'No backup'));
  setControlCenterStatusChip('cc-module-jobs-status', jobsTone, jobsTone === 'ok' ? 'Running' : 'Attention');
  setControlCenterStatusChip(
    'cc-module-notifications-status',
    notificationsTone,
    notificationsCapability && notificationsCapability.available === false
      ? 'Disabled until migration'
      : (notificationsTone === 'ok' ? 'Active' : 'Empty')
  );
  if (adminAuditCapability && adminAuditCapability.available === false) {
    setControlCenterText('cc-audit-preview', 'Audit actions disabled until migration');
  }
  setControlCenterStatusChip('cc-module-audit-status', auditTone, auditTone === 'ok' ? 'Clean' : 'Review');
  setControlCenterStatusChip('cc-module-infra-status', infraTone, infraTone === 'ok' ? 'Stable' : 'Warning');

  setControlCenterHealthChip('cc-health-chip-api', 'API', healthComponents?.api?.status);
  setControlCenterHealthChip('cc-health-chip-database', 'DB', healthComponents?.database?.status);
  setControlCenterHealthChip('cc-health-chip-email', 'Email', healthComponents?.email_service?.status);
  setControlCenterHealthChip('cc-health-chip-payments', 'Payments', healthComponents?.payment_gateway?.status);
  setControlCenterHealthChip('cc-health-chip-workers', 'Workers', healthComponents?.background_jobs?.status);
  setControlCenterHealthChip('cc-health-chip-storage', 'Storage', backupHealthy ? 'ok' : 'warning');

  renderControlCenterPriorities({
    healthTone,
    failedPayments,
    securityAlerts,
    expiredLicenses,
    backupTone,
    pausedJobs,
  });
}

function summarizeControlCenterPayload(elementId, payload) {
  if (typeof payload === 'string') return payload;
  if (!payload || typeof payload !== 'object') return String(payload ?? '-');
  if (payload.error) return `Chyba: ${payload.error}`;

  switch (elementId) {
    case 'cc-health-result': {
      const components = payload.components || {};
      const statuses = Object.values(components).map((item) => String(item?.status || 'unknown').toLowerCase());
      if (statuses.length === 0) return 'Health data načtena.';
      if (statuses.some((status) => status === 'error')) return 'Health obsahuje chybu. Otevřete detail.';
      if (statuses.some((status) => status === 'warning')) return 'Health obsahuje varování. Ověřte detail.';
      return 'System health je v pořádku.';
    }
    case 'cc-payments-result': {
      const summary = payload.summary || {};
      const liveCount = Number(summary?.live?.count || 0);
      const testCount = Number(summary?.test?.count || 0);
      const livePaid = Number(summary?.live?.paid_count || 0);
      return `Načteno plateb: ${formatNumber(payload.count ?? payload.items?.length ?? 0)}. LIVE ${formatNumber(liveCount)} (paid ${formatNumber(livePaid)}), TEST ${formatNumber(testCount)}.`;
    }
    case 'cc-presence-result':
      return `Načteno presence záznamů: ${formatNumber(payload.count ?? payload.items?.length ?? 0)}.`;
    case 'cc-security-result':
      return `Aktivní blokace: ${formatNumber(payload?.summary?.blocked_ips_active || 0)}, failed 24h: ${formatNumber(payload?.summary?.failed_logins_24h || 0)}.`;
    case 'cc-backup-result':
      return payload.message || `Načteno backupů: ${formatNumber(payload.items?.length ?? 0)}.`;
    case 'cc-infra-result':
      return payload.message || 'Infrastrukturní data načtena.';
    case 'cc-ops-result':
      return payload.message || 'Jobs/email data načtena.';
    case 'cc-logs-result':
      return payload.message || 'Audit/log data načtena.';
    case 'cc-notifications-result':
      return payload.message || `Načteno notifikací: ${formatNumber(payload.count ?? payload.items?.length ?? 0)}.`;
    default:
      return payload.message || 'Operace dokončena.';
  }
}

function setControlCenterResult(elementId, payload) {
  const el = document.getElementById(elementId);
  if (!el) return;

  const serialized = typeof payload === 'string' ? payload : JSON.stringify(payload, null, 2);
  const technicalId = CONTROL_CENTER_TECHNICAL_RESULT_IDS[elementId];
  if (technicalId) {
    const technicalEl = document.getElementById(technicalId);
    if (technicalEl) {
      technicalEl.textContent = serialized;
    }
  }

  if (CONTROL_CENTER_RAW_RESULT_IDS.has(elementId)) {
    el.textContent = serialized;
    return;
  }
  el.textContent = summarizeControlCenterPayload(elementId, payload);
}

function getNumberValue(id) {
  const raw = document.getElementById(id)?.value;
  if (!raw) return null;
  const num = Number(raw);
  if (!Number.isFinite(num) || num <= 0) return null;
  return Math.floor(num);
}

function renderControlCenterTable(containerId, columns, rows) {
  const el = document.getElementById(containerId);
  if (!el) return;
  const safeRows = Array.isArray(rows) ? rows : [];
  if (safeRows.length === 0) {
    el.innerHTML = '<div class="empty">Žádná data</div>';
    return;
  }
  const head = columns.map((col) => `<th>${escapeHtml(col.label)}</th>`).join('');
  const body = safeRows.map((row) => {
    const cells = columns.map((col) => {
      const rawValue = typeof col.render === 'function' ? col.render(row) : row[col.key];
      return `<td>${rawValue === undefined || rawValue === null || rawValue === '' ? '-' : rawValue}</td>`;
    }).join('');
    return `<tr>${cells}</tr>`;
  }).join('');
  el.innerHTML = `
    <table class="cc-mini-table">
      <thead><tr>${head}</tr></thead>
      <tbody>${body}</tbody>
    </table>
  `;
}

function clearControlCenterTable(containerId) {
  const el = document.getElementById(containerId);
  if (el) {
    el.innerHTML = '';
  }
}

function setControlCenterTableLoading(containerId, message = 'Načítám...') {
  const el = document.getElementById(containerId);
  if (!el) return;
  el.innerHTML = `<div class="loading">${escapeHtml(message)}</div>`;
}

function setControlCenterLoading(resultId, tableIds = []) {
  const loadingPayload = { loading: true, timestamp: new Date().toISOString() };
  if (resultId) {
    if (CONTROL_CENTER_RAW_RESULT_IDS.has(resultId)) {
      setControlCenterResult(resultId, loadingPayload);
    } else {
      const target = document.getElementById(resultId);
      if (target) {
        target.textContent = 'Načítám...';
      }
      const technicalId = CONTROL_CENTER_TECHNICAL_RESULT_IDS[resultId];
      const technicalEl = technicalId ? document.getElementById(technicalId) : null;
      if (technicalEl) {
        technicalEl.textContent = JSON.stringify(loadingPayload, null, 2);
      }
    }
  }
  for (const tableId of tableIds) {
    setControlCenterTableLoading(tableId);
  }
}

function syncControlCenterDetailsOverlayState() {
  const anyOpen = Boolean(document.querySelector('#section-control-center .cc-module-details[open]'));
  document.body.classList.toggle('cc-details-open', anyOpen);
  if (anyOpen) {
    const scrollbarWidth = Math.max(0, window.innerWidth - document.documentElement.clientWidth);
    document.body.style.setProperty('--cc-overlay-scrollbar', `${scrollbarWidth}px`);
  } else {
    document.body.style.removeProperty('--cc-overlay-scrollbar');
  }
}

function closeAllControlCenterDetails(exceptId = '') {
  const detailsNodes = Array.from(document.querySelectorAll('#section-control-center .cc-module-details'));
  detailsNodes.forEach((node) => {
    if (!exceptId || node.id !== exceptId) {
      node.open = false;
    }
  });
  syncControlCenterDetailsOverlayState();
}

function initControlCenterDetailsBehavior() {
  const detailsNodes = Array.from(document.querySelectorAll('#section-control-center .cc-module-details'));
  detailsNodes.forEach((node) => {
    const summary = node.querySelector(':scope > summary');
    if (summary && summary.dataset.closeBound !== '1') {
      const closeBtn = document.createElement('button');
      closeBtn.type = 'button';
      closeBtn.className = 'cc-details-close-btn';
      closeBtn.textContent = 'Zavřít';
      closeBtn.addEventListener('click', (event) => {
        event.preventDefault();
        event.stopPropagation();
        node.open = false;
        syncControlCenterDetailsOverlayState();
      });
      summary.appendChild(closeBtn);
      summary.dataset.closeBound = '1';
    }

    if (node.dataset.bound === '1') return;
    node.addEventListener('toggle', () => {
      if (node.open) {
        closeAllControlCenterDetails(node.id);
      }
      syncControlCenterDetailsOverlayState();
    });
    node.dataset.bound = '1';
  });
}

function focusControlCenterDetailPrimaryField(detailsEl) {
  if (!detailsEl) return;
  const target = detailsEl.querySelector(
    '[data-cc-primary-focus], input:not([type="hidden"]):not([disabled]), select:not([disabled]), textarea:not([disabled])',
  );
  if (target && typeof target.focus === 'function') {
    target.focus({ preventScroll: true });
  }
}

function openControlCenterModuleDetails(detailsId) {
  const detailsEl = document.getElementById(detailsId);
  if (!detailsEl || detailsEl.tagName.toLowerCase() !== 'details') return;
  if (detailsEl.open) {
    detailsEl.open = false;
    syncControlCenterDetailsOverlayState();
    return;
  }
  closeAllControlCenterDetails(detailsId);
  detailsEl.open = true;
  syncControlCenterDetailsOverlayState();
  requestAnimationFrame(() => {
    detailsEl.scrollTop = 0;
    focusControlCenterDetailPrimaryField(detailsEl);
  });
}

function focusControlCenterModule(moduleId, detailsId = '') {
  const moduleEl = document.getElementById(moduleId);
  if (moduleEl) {
    moduleEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
  if (detailsId) {
    openControlCenterModuleDetails(detailsId);
  }
}

async function loadControlCenterUsersSnapshot() {
  try {
    const users = await fetchAllList('/admin-api/users');
    setControlCenterState('users', users);
  } catch (error) {
    console.error('Error loading control center users snapshot:', error);
    setControlCenterState('users', []);
  }
}

function initControlCenterDraftPreviewBindings() {
  const targetType = document.getElementById('cc-broadcast-target-type');
  const targetValue = document.getElementById('cc-broadcast-target-value');
  if (targetType && targetType.dataset.bound !== '1') {
    targetType.addEventListener('change', renderControlCenterDashboard);
    targetType.dataset.bound = '1';
  }
  if (targetValue && targetValue.dataset.bound !== '1') {
    targetValue.addEventListener('input', () => {
      const value = (targetValue.value || '').trim();
      setControlCenterText('cc-notifications-target-preview', value || (targetType?.value || 'all'));
    });
    targetValue.dataset.bound = '1';
  }
}

function initControlCenterModuleColumns() {
  const grid = document.querySelector('#section-control-center .cc-module-grid');
  if (!grid) return;
  if (grid.dataset.columnsReady === '1') return;
  if (Array.from(grid.children).some((el) => el.classList && el.classList.contains('cc-module-column'))) {
    grid.dataset.columnsReady = '1';
    return;
  }

  const cards = Array.from(grid.children).filter(
    (el) => el.classList && el.classList.contains('cc-module-card'),
  );
  if (cards.length === 0) return;

  const leftColumn = document.createElement('div');
  leftColumn.className = 'cc-module-column cc-module-column-left';
  const rightColumn = document.createElement('div');
  rightColumn.className = 'cc-module-column cc-module-column-right';

  cards.forEach((card, index) => {
    if (index % 2 === 0) {
      leftColumn.appendChild(card);
    } else {
      rightColumn.appendChild(card);
    }
  });

  grid.appendChild(leftColumn);
  grid.appendChild(rightColumn);
  grid.dataset.columnsReady = '1';
}

async function refreshControlCenterOverview() {
  if (!canAccessControlCenter()) {
    setControlCenterResult('cc-health-result', { detail: 'Sekce je dostupná pouze pro roli developer_admin.' });
    return;
  }

  initControlCenterModuleColumns();
  initControlCenterDetailsBehavior();
  initControlCenterDraftPreviewBindings();

  await Promise.all([
    loadControlCenterUsersSnapshot(),
    loadControlCenterHealth(),
    loadControlCenterPayments(),
    loadControlCenterPresence(),
    loadControlCenterSecurityMonitor(),
    loadControlCenterBackups(),
    loadControlCenterApiMonitor(),
    loadControlCenterWebhookMonitor(),
    loadControlCenterStorage(),
    loadControlCenterEmailMonitor(),
    loadControlCenterJobs(),
    loadControlCenterNotifications(),
    loadControlCenterAuditActions(),
  ]);
}

async function loadControlCenterHealth() {
  setControlCenterLoading('cc-health-result', ['cc-health-table']);
  try {
    const data = await apiRequest('GET', '/admin-api/control-center/health');
    setControlCenterState('health', data);
    const components = data?.components || {};
    const rows = Object.entries(components).map(([name, component]) => ({
      component: name,
      status: component?.status || 'unknown',
      detail: buildControlCenterHealthDetail(component),
    }));
    renderControlCenterTable(
      'cc-health-table',
      [
        { key: 'component', label: 'Komponenta', render: (row) => escapeHtml(row.component) },
        { key: 'status', label: 'Stav', render: (row) => renderControlCenterStatusLabel(row.status) },
        { key: 'detail', label: 'Poznámka', render: (row) => escapeHtml(row.detail) },
      ],
      rows,
    );
    setControlCenterResult('cc-health-result', data);
  } catch (error) {
    clearControlCenterTable('cc-health-table');
    setControlCenterResult('cc-health-result', { error: error.message });
  }
}

function getSortedControlCenterPaymentItems(items) {
  return items
    .slice()
    .sort((a, b) => {
      const envA = normalizePaymentEnvironment(a);
      const envB = normalizePaymentEnvironment(b);
      if (envA !== envB) return envA === 'LIVE' ? -1 : 1;
      return new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime();
    });
}

function getControlCenterPaymentsFilterState() {
  const env = (document.getElementById('cc-payments-filter-env')?.value || 'all').toLowerCase();
  const state = (document.getElementById('cc-payments-filter-state')?.value || 'all').toLowerCase();
  const query = (document.getElementById('cc-payments-filter-query')?.value || '').trim().toLowerCase();
  controlCenterPaymentsFilters.env = env;
  controlCenterPaymentsFilters.state = state;
  controlCenterPaymentsFilters.query = query;
  return { ...controlCenterPaymentsFilters };
}

function paymentMatchesControlCenterFilters(item, filters) {
  const env = normalizePaymentEnvironment(item).toLowerCase();
  if (filters.env !== 'all' && filters.env !== env) return false;

  if (filters.state === 'success' && !isPaymentSuccessful(item)) return false;
  if (filters.state === 'failed' && !isPaymentFailed(item)) return false;
  if (filters.state === 'attention' && !isPaymentNeedsAttention(item)) return false;
  if (filters.state === 'refunded' && String(item?.refund_status || '').trim().toLowerCase() !== 'refunded') return false;

  if (filters.query) {
    const haystack = [
      String(item?.account_email || ''),
      String(item?.trans_id || ''),
      String(item?.ref_id || ''),
      String(item?.plan || ''),
      String(item?.provider_status || ''),
    ].join(' ').toLowerCase();
    if (!haystack.includes(filters.query)) return false;
  }

  return true;
}

function renderControlCenterPaymentsLiveFeed(items) {
  const liveFeedEl = document.getElementById('cc-payments-live-feed');
  const liveLastEl = document.getElementById('cc-payments-live-last');
  if (!liveFeedEl || !liveLastEl) return;

  const livePaid = items
    .filter((item) => normalizePaymentEnvironment(item) === 'LIVE' && isPaymentSuccessful(item))
    .sort((a, b) => new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime());

  const latestLive = livePaid[0] || null;
  liveLastEl.textContent = latestLive ? formatDateTime(latestLive.created_at) : 'Žádná';

  if (livePaid.length === 0) {
    liveFeedEl.innerHTML = '<div class="empty">Žádné LIVE platby v aktuálním feedu.</div>';
    return;
  }

  liveFeedEl.innerHTML = livePaid.slice(0, 4).map((item) => {
    const amount = Number(item.amount_halers || 0).toLocaleString('cs-CZ');
    const email = escapeHtml(item.account_email || '-');
    const transId = escapeHtml(item.trans_id || '-');
    return `
      <div class="cc-live-feed-item">
        <div class="cc-live-feed-main">${email}</div>
        <div class="cc-live-feed-meta">${amount} hal. • ${escapeHtml(item.currency || 'CZK')} • ${formatDateTime(item.created_at)}</div>
        <div class="cc-live-feed-meta">transId: ${transId}</div>
      </div>
    `;
  }).join('');
}

function renderControlCenterPaymentsModule(data) {
  const items = Array.isArray(data?.items) ? data.items : [];
  const summary = data?.summary || {};
  const liveSummary = summary?.live || {};
  const testSummary = summary?.test || {};
  const allSummary = summary?.all || {};
  const sortedItems = getSortedControlCenterPaymentItems(items);
  const liveItems = sortedItems.filter((item) => normalizePaymentEnvironment(item) === 'LIVE');
  const filters = getControlCenterPaymentsFilterState();
  const filteredItems = sortedItems.filter((item) => paymentMatchesControlCenterFilters(item, filters));

  renderControlCenterTable(
    'cc-payments-summary',
    [
      { key: 'metric', label: 'Metrika', render: (row) => escapeHtml(row.metric) },
      { key: 'value', label: 'Hodnota', render: (row) => escapeHtml(row.value) },
    ],
    [
      { metric: 'Transakce celkem', value: formatNumber(allSummary.count ?? items.length) },
      { metric: 'LIVE transakce', value: formatNumber(liveSummary.count ?? liveItems.length) },
      { metric: 'TEST transakce', value: formatNumber(testSummary.count ?? (items.length - liveItems.length)) },
      { metric: 'LIVE paid', value: formatNumber(liveSummary.paid_count ?? liveItems.filter((item) => isPaymentSuccessful(item)).length) },
      { metric: 'LIVE paid today', value: formatHalersToCzk(liveSummary.paid_today_halers ?? 0) },
      { metric: 'LIVE failed', value: formatNumber(liveSummary.failed_count ?? liveItems.filter((item) => isPaymentFailed(item)).length) },
      { metric: 'LIVE refundy', value: formatNumber(liveSummary.refund_count ?? liveItems.filter((item) => String(item.refund_status || '').toLowerCase() === 'refunded').length) },
      { metric: 'LIVE vyžaduje akci', value: formatNumber(liveSummary.attention_count ?? liveItems.filter((item) => isPaymentNeedsAttention(item)).length) },
      { metric: 'Filtrované položky', value: formatNumber(filteredItems.length) },
    ],
  );

  renderControlCenterTable(
    'cc-payments-table',
    [
      { key: 'id', label: '#' },
      { key: 'payment_environment', label: 'Env', render: (row) => escapeHtml(normalizePaymentEnvironment(row)) },
      { key: 'account_email', label: 'Účet', render: (row) => escapeHtml(row.account_email || '-') },
      { key: 'trans_id', label: 'Trans ID', render: (row) => escapeHtml(row.trans_id || '-') },
      { key: 'plan', label: 'Plan', render: (row) => escapeHtml((row.plan || '-').toUpperCase()) },
      { key: 'amount_halers', label: 'Částka', render: (row) => Number(row.amount_halers || 0).toLocaleString('cs-CZ') + ' hal.' },
      { key: 'provider_status', label: 'Stav', render: (row) => escapeHtml(row.provider_status || '-') },
      { key: 'refund_status', label: 'Refund', render: (row) => escapeHtml(row.refund_status || 'none') },
      { key: 'created_at', label: 'Čas', render: (row) => formatDateTime(row.created_at) },
    ],
    filteredItems.slice(0, 40),
  );

  renderControlCenterPaymentsLiveFeed(sortedItems);
}

function bindControlCenterPaymentsFilters() {
  const envEl = document.getElementById('cc-payments-filter-env');
  const stateEl = document.getElementById('cc-payments-filter-state');
  const queryEl = document.getElementById('cc-payments-filter-query');
  if (!envEl || !stateEl || !queryEl) return;

  if (envEl.dataset.bound !== '1') {
    envEl.addEventListener('change', () => {
      renderControlCenterPaymentsModule(controlCenterDataState.payments || {});
    });
    envEl.dataset.bound = '1';
  }
  if (stateEl.dataset.bound !== '1') {
    stateEl.addEventListener('change', () => {
      renderControlCenterPaymentsModule(controlCenterDataState.payments || {});
    });
    stateEl.dataset.bound = '1';
  }
  if (queryEl.dataset.bound !== '1') {
    queryEl.addEventListener('input', () => {
      renderControlCenterPaymentsModule(controlCenterDataState.payments || {});
    });
    queryEl.dataset.bound = '1';
  }
}

async function loadControlCenterPayments() {
  setControlCenterLoading('cc-payments-result', ['cc-payments-summary', 'cc-payments-table']);
  try {
    bindControlCenterPaymentsFilters();
    const data = await apiRequest('GET', '/admin-api/control-center/payments?limit=60');
    setControlCenterState('payments', data);
    renderControlCenterPaymentsModule(data);
    setControlCenterResult('cc-payments-result', data);
  } catch (error) {
    clearControlCenterTable('cc-payments-table');
    clearControlCenterTable('cc-payments-summary');
    const liveFeedEl = document.getElementById('cc-payments-live-feed');
    if (liveFeedEl) {
      liveFeedEl.innerHTML = '<div class="empty">Nepodařilo se načíst LIVE feed plateb.</div>';
    }
    setControlCenterResult('cc-payments-result', { error: error.message });
  }
}

async function runControlCenterPaymentResync() {
  if (!confirm('Spustit resync plateb a subscription stavu?')) return;
  setControlCenterLoading('cc-payments-result');
  try {
    const data = await apiRequest('POST', '/admin-api/control-center/payments/resync', {});
    setControlCenterResult('cc-payments-result', data);
    showSuccess('Payment resync dokončen');
    await Promise.all([loadControlCenterPayments(), loadControlCenterUsersSnapshot()]);
  } catch (error) {
    setControlCenterResult('cc-payments-result', { error: error.message });
  }
}

async function loadControlCenterPresence() {
  setControlCenterLoading('cc-presence-result', ['cc-presence-table']);
  try {
    const data = await apiRequest('GET', '/admin-api/control-center/presence?limit=120');
    const items = Array.isArray(data?.items) ? data.items : [];
    setControlCenterState('presence', data);
    renderControlCenterTable(
      'cc-presence-table',
      [
        { key: 'user_id', label: 'User ID' },
        { key: 'email', label: 'Email', render: (row) => escapeHtml(row.email || '-') },
        {
          key: 'online_status',
          label: 'Stav',
          render: (row) => {
            const isOnline = String(row.online_status || '').toUpperCase() === 'ONLINE';
            const klass = isOnline ? 'cc-status-online' : 'cc-status-offline';
            return `<span class="${klass}">${escapeHtml(row.online_status || '-')}</span>`;
          },
        },
        { key: 'last_seen_at', label: 'Last seen', render: (row) => formatDateTime(row.last_seen_at) },
        { key: 'last_login_at', label: 'Last login', render: (row) => formatDateTime(row.last_login_at) },
        { key: 'active_session_count', label: 'Relace' },
      ],
      items.slice(0, 30),
    );
    setControlCenterResult('cc-presence-result', data);
  } catch (error) {
    clearControlCenterTable('cc-presence-table');
    setControlCenterResult('cc-presence-result', { error: error.message });
  }
}

async function loadControlCenterSecurityMonitor() {
  setControlCenterLoading('cc-security-result', ['cc-security-failed-ips-table', 'cc-security-table', 'cc-security-events-table']);
  try {
    const data = await apiRequest('GET', '/admin-api/control-center/security-monitor');
    setControlCenterState('security', data);
    const topFailedIps = Array.isArray(data?.top_failed_ips) ? data.top_failed_ips : [];
    renderControlCenterTable(
      'cc-security-failed-ips-table',
      [
        { key: 'ip_address', label: 'Top failed IP', render: (row) => escapeHtml(row.ip_address || '-') },
        { key: 'failed_count', label: 'Failed count', render: (row) => formatNumber(row.failed_count || 0) },
      ],
      topFailedIps.slice(0, 15),
    );
    const blocked = Array.isArray(data?.blocked_ips) ? data.blocked_ips : [];
    renderControlCenterTable(
      'cc-security-table',
      [
        { key: 'ip_address', label: 'IP' },
        { key: 'is_active', label: 'Aktivní', render: (row) => row.is_active ? 'ANO' : 'NE' },
        { key: 'reason', label: 'Důvod', render: (row) => escapeHtml(row.reason || '-') },
        { key: 'blocked_at', label: 'Blocked at', render: (row) => formatDateTime(row.blocked_at) },
        { key: 'expires_at', label: 'Expires', render: (row) => formatDateTime(row.expires_at) },
      ],
      blocked.slice(0, 20),
    );
    const latestEvents = Array.isArray(data?.latest_events) ? data.latest_events : [];
    renderControlCenterTable(
      'cc-security-events-table',
      [
        { key: 'created_at', label: 'Čas', render: (row) => formatDateTime(row.created_at) },
        { key: 'event_type', label: 'Událost', render: (row) => escapeHtml(row.event_type || '-') },
        { key: 'user_email', label: 'Uživatel', render: (row) => escapeHtml(row.user_email || '-') },
        { key: 'ip_address', label: 'IP', render: (row) => escapeHtml(row.ip_address || '-') },
        { key: 'endpoint', label: 'Endpoint', render: (row) => escapeHtml(row.endpoint || '-') },
      ],
      latestEvents.slice(0, 40),
    );
    setControlCenterResult('cc-security-result', data);
  } catch (error) {
    clearControlCenterTable('cc-security-failed-ips-table');
    clearControlCenterTable('cc-security-table');
    clearControlCenterTable('cc-security-events-table');
    setControlCenterResult('cc-security-result', { error: error.message });
  }
}

async function blockIpFromControlCenter() {
  const ipAddress = (document.getElementById('cc-block-ip')?.value || '').trim();
  const reason = (document.getElementById('cc-block-reason')?.value || '').trim();
  if (!ipAddress) {
    showGlobalError('Vyplňte IP adresu pro blokaci.');
    return;
  }
  try {
    const data = await apiRequest('POST', '/admin-api/control-center/security/block-ip', {
      ip_address: ipAddress,
      reason: reason || null,
    });
    setControlCenterResult('cc-security-result', data);
    await loadControlCenterSecurityMonitor();
    showSuccess('IP adresa byla zablokována');
  } catch (error) {
    setControlCenterResult('cc-security-result', { error: error.message });
  }
}

async function unblockIpFromControlCenter() {
  const ipAddress = (document.getElementById('cc-block-ip')?.value || '').trim();
  const reason = (document.getElementById('cc-block-reason')?.value || '').trim();
  if (!ipAddress) {
    showGlobalError('Vyplňte IP adresu pro odblokování.');
    return;
  }
  try {
    const data = await apiRequest('POST', '/admin-api/control-center/security/unblock-ip', {
      ip_address: ipAddress,
      reason: reason || null,
    });
    setControlCenterResult('cc-security-result', data);
    await loadControlCenterSecurityMonitor();
    showSuccess('IP adresa byla odblokována');
  } catch (error) {
    setControlCenterResult('cc-security-result', { error: error.message });
  }
}

async function loadControlCenterBackups() {
  setControlCenterLoading('cc-backup-result', ['cc-backups-table']);
  try {
    const data = await apiRequest('GET', '/admin-api/control-center/backups');
    setControlCenterState('backups', data);
    const items = Array.isArray(data?.items) ? data.items : [];
    renderControlCenterTable(
      'cc-backups-table',
      [
        { key: 'backup_id', label: 'Backup ID', render: (row) => escapeHtml(row.backup_id || '-') },
        { key: 'created_at', label: 'Vytvořeno', render: (row) => formatDateTime(row.created_at) },
        { key: 'created_by', label: 'Vytvořil', render: (row) => escapeHtml(row.created_by || '-') },
        { key: 'db_size_bytes', label: 'DB size', render: (row) => Number(row.db_size_bytes || 0).toLocaleString('cs-CZ') + ' B' },
        { key: 'include_data_dir', label: 'Data', render: (row) => row.include_data_dir ? 'ANO' : 'NE' },
      ],
      items.slice(0, 20),
    );
    setControlCenterResult('cc-backup-result', data);
  } catch (error) {
    clearControlCenterTable('cc-backups-table');
    setControlCenterResult('cc-backup-result', { error: error.message });
  }
}

async function createControlCenterBackup() {
  setControlCenterLoading('cc-backup-result');
  try {
    const data = await apiRequest('POST', '/admin-api/control-center/backups/create', { include_data_dir: true });
    setControlCenterResult('cc-backup-result', data);
    await Promise.all([loadControlCenterBackups(), loadControlCenterStorage()]);
    showSuccess('Backup byl vytvořen');
  } catch (error) {
    setControlCenterResult('cc-backup-result', { error: error.message });
  }
}

async function restoreControlCenterBackup() {
  const backupId = (document.getElementById('cc-restore-backup-id')?.value || '').trim();
  const scope = (document.getElementById('cc-restore-scope')?.value || 'full').trim();
  const confirmText = (document.getElementById('cc-restore-confirm')?.value || '').trim();
  const userId = getNumberValue('cc-restore-user-id');
  const vehicleId = getNumberValue('cc-restore-vehicle-id');

  if (!backupId) {
    showGlobalError('Vyplňte backup ID.');
    return;
  }

  if (!confirm('Restore může přepsat data. Pokračovat?')) return;
  setControlCenterLoading('cc-backup-result');

  try {
    const data = await apiRequest('POST', '/admin-api/control-center/backups/restore', {
      backup_id: backupId,
      scope,
      user_id: userId,
      vehicle_id: vehicleId,
      confirm_text: confirmText,
    });
    setControlCenterResult('cc-backup-result', data);
    showSuccess('Restore dokončen');
    await Promise.all([
      loadOverview(),
      loadUsers(),
      loadVehicles(),
      loadRecords(),
      loadControlCenterBackups(),
      loadControlCenterUsersSnapshot(),
      loadControlCenterPresence(),
    ]);
  } catch (error) {
    setControlCenterResult('cc-backup-result', { error: error.message });
  }
}

async function loadControlCenterApiMonitor() {
  setControlCenterLoading('cc-infra-result', ['cc-api-monitor-table']);
  try {
    const data = await apiRequest('GET', '/admin-api/control-center/api-monitor');
    setControlCenterState('apiMonitor', data);
    const rows = Array.isArray(data?.items) ? data.items : [];
    renderControlCenterTable(
      'cc-api-monitor-table',
      [
        { key: 'endpoint', label: 'Endpoint', render: (row) => escapeHtml(row.endpoint || '-') },
        { key: 'hits', label: 'Hits 24h', render: (row) => formatNumber(row.hits || 0) },
      ],
      rows.slice(0, 30),
    );
    setControlCenterResult('cc-infra-result', data);
  } catch (error) {
    clearControlCenterTable('cc-api-monitor-table');
    setControlCenterResult('cc-infra-result', { error: error.message });
  }
}

async function loadControlCenterWebhookMonitor() {
  setControlCenterLoading('cc-infra-result', ['cc-webhooks-table']);
  try {
    const data = await apiRequest('GET', '/admin-api/control-center/webhook-monitor');
    setControlCenterState('webhookMonitor', data);
    const rows = Array.isArray(data?.tail) ? data.tail : [];
    renderControlCenterTable(
      'cc-webhooks-table',
      [
        { key: 'idx', label: '#', render: (row) => String(row.idx) },
        { key: 'line', label: 'Webhook log řádek', render: (row) => escapeHtml(row.line || '-') },
      ],
      rows.slice(0, 20).map((line, index) => ({ idx: index + 1, line })),
    );
    setControlCenterResult('cc-infra-result', data);
  } catch (error) {
    clearControlCenterTable('cc-webhooks-table');
    setControlCenterResult('cc-infra-result', { error: error.message });
  }
}

async function loadControlCenterStorage() {
  setControlCenterLoading('cc-infra-result', ['cc-storage-summary-table']);
  try {
    const data = await apiRequest('GET', '/admin-api/control-center/storage');
    setControlCenterState('storage', data);
    const dbSize = data?.database?.size_human || '-';
    const dataDir = data?.directories?.data?.total_human || '-';
    const logsDir = data?.directories?.logs?.total_human || '-';
    const backupsDir = data?.directories?.backups?.total_human || '-';
    renderControlCenterTable(
      'cc-storage-summary-table',
      [
        { key: 'label', label: 'Storage položka', render: (row) => escapeHtml(row.label) },
        { key: 'value', label: 'Využití', render: (row) => escapeHtml(row.value) },
      ],
      [
        { label: 'Database', value: dbSize },
        { label: 'Data dir', value: dataDir },
        { label: 'Logs dir', value: logsDir },
        { label: 'Backups dir', value: backupsDir },
      ],
    );
    setControlCenterResult('cc-infra-result', data);
  } catch (error) {
    clearControlCenterTable('cc-storage-summary-table');
    setControlCenterResult('cc-infra-result', { error: error.message });
  }
}

async function loadControlCenterEmailMonitor() {
  setControlCenterLoading('cc-ops-result', ['cc-email-table']);
  try {
    const data = await apiRequest('GET', '/admin-api/control-center/email-monitor');
    setControlCenterState('email', data);
    const items = Array.isArray(data?.items) ? data.items : [];
    renderControlCenterTable(
      'cc-email-table',
      [
        { key: 'id', label: '#' },
        { key: 'email', label: 'Email', render: (row) => escapeHtml(row.email || '-') },
        { key: 'subject', label: 'Předmět', render: (row) => escapeHtml(row.subject || '-') },
        { key: 'status', label: 'Stav', render: (row) => escapeHtml(row.status || '-') },
        { key: 'sent_at', label: 'Čas', render: (row) => formatDateTime(row.sent_at) },
      ],
      items.slice(0, 20),
    );
    setControlCenterResult('cc-ops-result', data);
  } catch (error) {
    clearControlCenterTable('cc-email-table');
    setControlCenterResult('cc-ops-result', { error: error.message });
  }
}

async function loadControlCenterJobs() {
  setControlCenterLoading('cc-ops-result', ['cc-jobs-table']);
  try {
    const data = await apiRequest('GET', '/admin-api/control-center/jobs');
    setControlCenterState('jobs', data);
    const jobs = Array.isArray(data?.jobs) ? data.jobs : [];
    renderControlCenterTable(
      'cc-jobs-table',
      [
        { key: 'name', label: 'Job', render: (row) => escapeHtml(row.name || '-') },
        { key: 'state', label: 'Stav', render: (row) => escapeHtml(row.state || '-') },
        { key: 'interval_seconds', label: 'Interval (s)' },
        { key: 'paused_by', label: 'Paused by', render: (row) => escapeHtml(row.paused_by || '-') },
        { key: 'pause_reason', label: 'Důvod', render: (row) => escapeHtml(row.pause_reason || '-') },
      ],
      jobs,
    );
    setControlCenterResult('cc-ops-result', data);
  } catch (error) {
    clearControlCenterTable('cc-jobs-table');
    setControlCenterResult('cc-ops-result', { error: error.message });
  }
}

async function runControlCenterJobPrompt() {
  const jobName = prompt('Zadejte job_name (např. license.subscription.cycle, reminders.notification.check):', 'license.subscription.cycle');
  if (!jobName) return;
  try {
    setControlCenterLoading('cc-ops-result');
    const data = await apiRequest('POST', '/admin-api/control-center/jobs/run', { job_name: jobName.trim() });
    setControlCenterResult('cc-ops-result', data);
    showSuccess(`Job ${jobName.trim()} dokončen`);
    await loadControlCenterJobs();
  } catch (error) {
    setControlCenterResult('cc-ops-result', { error: error.message });
  }
}

async function pauseControlCenterJobPrompt() {
  const jobName = prompt('Zadejte job_name pro pozastavení:', 'license.subscription.cycle');
  if (!jobName) return;
  const reason = prompt('Důvod pozastavení (volitelné):', 'maintenance') || null;
  try {
    setControlCenterLoading('cc-ops-result');
    const data = await apiRequest('POST', '/admin-api/control-center/jobs/pause', {
      job_name: jobName.trim(),
      reason,
    });
    setControlCenterResult('cc-ops-result', data);
    showSuccess(`Job ${jobName.trim()} byl pozastaven`);
    await loadControlCenterJobs();
  } catch (error) {
    setControlCenterResult('cc-ops-result', { error: error.message });
  }
}

async function resumeControlCenterJobPrompt() {
  const jobName = prompt('Zadejte job_name pro obnovení:', 'license.subscription.cycle');
  if (!jobName) return;
  const reason = prompt('Důvod obnovení (volitelné):', '') || null;
  try {
    setControlCenterLoading('cc-ops-result');
    const data = await apiRequest('POST', '/admin-api/control-center/jobs/resume', {
      job_name: jobName.trim(),
      reason,
    });
    setControlCenterResult('cc-ops-result', data);
    showSuccess(`Job ${jobName.trim()} byl obnoven`);
    await loadControlCenterJobs();
  } catch (error) {
    setControlCenterResult('cc-ops-result', { error: error.message });
  }
}

async function loadControlCenterSystemLogs() {
  setControlCenterLoading('cc-logs-result', ['cc-system-logs-table']);
  try {
    const data = await apiRequest('GET', '/admin-api/control-center/system-logs');
    setControlCenterState('systemLogs', data);
    const logs = Array.isArray(data?.logs) ? data.logs : [];
    renderControlCenterTable(
      'cc-system-logs-table',
      [
        { key: 'file', label: 'Soubor', render: (row) => escapeHtml(row.file || '-') },
        { key: 'exists', label: 'Existuje', render: (row) => row.exists ? 'ANO' : 'NE' },
        { key: 'tail_count', label: 'Tail řádků', render: (row) => formatNumber(Array.isArray(row.tail) ? row.tail.length : 0) },
        {
          key: 'last_line',
          label: 'Poslední řádek',
          render: (row) => {
            const tail = Array.isArray(row.tail) ? row.tail : [];
            const lastLine = tail.length > 0 ? tail[tail.length - 1] : '-';
            return escapeHtml(lastLine || '-');
          },
        },
      ],
      logs.slice(0, 20),
    );
    setControlCenterResult('cc-logs-result', data);
  } catch (error) {
    clearControlCenterTable('cc-system-logs-table');
    setControlCenterResult('cc-logs-result', { error: error.message });
  }
}

async function loadControlCenterAuditActions() {
  setControlCenterLoading('cc-logs-result', ['cc-audit-actions-table']);
  try {
    const data = await apiRequest('GET', '/admin-api/control-center/audit-actions?limit=200');
    setControlCenterState('audit', data);
    const items = Array.isArray(data?.items) ? data.items : [];
    renderControlCenterTable(
      'cc-audit-actions-table',
      [
        { key: 'id', label: '#' },
        { key: 'developer_email', label: 'Developer', render: (row) => escapeHtml(row.developer_email || '-') },
        { key: 'action_type', label: 'Akce', render: (row) => escapeHtml(row.action_type || '-') },
        { key: 'target_resource', label: 'Target', render: (row) => escapeHtml(row.target_resource || '-') },
        { key: 'result', label: 'Výsledek', render: (row) => escapeHtml(row.result || '-') },
        { key: 'created_at', label: 'Čas', render: (row) => formatDateTime(row.created_at) },
      ],
      items.slice(0, 40),
    );
    setControlCenterResult('cc-logs-result', data);
  } catch (error) {
    clearControlCenterTable('cc-audit-actions-table');
    setControlCenterResult('cc-logs-result', { error: error.message });
  }
}

async function executeControlCenterCommand() {
  const command = (document.getElementById('cc-command')?.value || '').trim();
  if (!command) {
    showGlobalError('Vyplňte příkaz.');
    return;
  }
  setControlCenterLoading('cc-command-result');
  try {
    const data = await apiRequest('POST', '/admin-api/control-center/commands/execute', { command });
    setControlCenterState('command', data);
    setControlCenterResult('cc-command-result', data);
    setControlCenterText('cc-command-summary', data?.ok ? 'Příkaz byl úspěšně dokončen.' : 'Příkaz dokončen.');
    setControlCenterStatusChip('cc-module-command-status', data?.ok ? 'ok' : 'warn', data?.ok ? 'Done' : 'Review');
  } catch (error) {
    setControlCenterResult('cc-command-result', { error: error.message });
    setControlCenterText('cc-command-summary', `Chyba příkazu: ${error.message}`);
    setControlCenterStatusChip('cc-module-command-status', 'alert', 'Error');
  }
}

async function loadControlCenterUserInsight() {
  const userId = getNumberValue('cc-insight-user-id');
  if (!userId) {
    showGlobalError('Vyplňte validní User ID.');
    return;
  }
  setControlCenterLoading('cc-insight-result', ['cc-insight-summary', 'cc-insight-payments-table']);
  try {
    const data = await apiRequest('GET', `/admin-api/control-center/user-insight/${userId}`);
    controlCenterCurrentInsight = data;
    setControlCenterState('insight', data);
    const license = data?.license || {};
    const presence = data?.presence || {};
    const paymentsSummary = data?.payments_summary || {};
    const summaryRows = [
      { key: 'plan', label: 'Plan', value: escapeHtml((license.current_plan || '-').toUpperCase()) },
      { key: 'status', label: 'Status', value: escapeHtml(license.status || '-') },
      { key: 'source', label: 'Zdroj', value: escapeHtml(license.source_of_activation || '-') },
      { key: 'purchase', label: 'Purchase', value: formatDateTime(license.purchase_date) },
      { key: 'activation', label: 'Activation', value: formatDateTime(license.activation_date) },
      { key: 'expiration', label: 'Expiration', value: formatDateTime(license.expiration_date) },
      { key: 'next_renewal', label: 'Next renewal', value: formatDateTime(license.next_renewal_date) },
      { key: 'has_paid', label: 'LIVE paid', value: paymentsSummary.has_live_paid ? 'Ano' : 'Ne' },
      { key: 'paid_live_count', label: 'LIVE paid count', value: String(paymentsSummary.live_paid_count ?? 0) },
      { key: 'paid_test_count', label: 'TEST paid count', value: String(paymentsSummary.test_paid_count ?? 0) },
      { key: 'payments_live_count', label: 'LIVE tx', value: String(paymentsSummary.count_live ?? 0) },
      { key: 'payments_test_count', label: 'TEST tx', value: String(paymentsSummary.count_test ?? 0) },
      { key: 'last_paid', label: 'Last paid', value: formatDateTime(paymentsSummary.last_paid_at) },
      { key: 'online', label: 'Online', value: escapeHtml(presence.online_status || '-') },
      { key: 'last_seen', label: 'Last seen', value: formatDateTime(presence.last_seen_at) },
      { key: 'sessions', label: 'Aktivní relace', value: String(presence.active_session_count ?? 0) },
    ];
    renderControlCenterTable(
      'cc-insight-summary',
      [
        { key: 'label', label: 'Položka', render: (row) => escapeHtml(row.label) },
        { key: 'value', label: 'Hodnota', render: (row) => row.value },
      ],
      summaryRows,
    );
    const paymentItems = Array.isArray(data?.payments) ? data.payments : [];
    renderControlCenterTable(
      'cc-insight-payments-table',
      [
        { key: 'id', label: '#' },
        { key: 'payment_environment', label: 'Env', render: (row) => escapeHtml(normalizePaymentEnvironment(row)) },
        { key: 'trans_id', label: 'Trans ID', render: (row) => escapeHtml(row.trans_id || '-') },
        { key: 'provider', label: 'Provider', render: (row) => escapeHtml(row.provider || '-') },
        { key: 'amount_halers', label: 'Částka', render: (row) => Number(row.amount_halers || 0).toLocaleString('cs-CZ') + ' hal.' },
        { key: 'currency', label: 'Měna', render: (row) => escapeHtml(row.currency || '-') },
        { key: 'provider_status', label: 'Status', render: (row) => escapeHtml(row.provider_status || '-') },
        { key: 'refund_status', label: 'Refund', render: (row) => escapeHtml(row.refund_status || 'none') },
        { key: 'payment_timestamp', label: 'Čas', render: (row) => formatDateTime(row.payment_timestamp) },
      ],
      paymentItems
        .slice()
        .sort((a, b) => {
          const envA = normalizePaymentEnvironment(a);
          const envB = normalizePaymentEnvironment(b);
          if (envA !== envB) return envA === 'LIVE' ? -1 : 1;
          return new Date(b.payment_timestamp || 0).getTime() - new Date(a.payment_timestamp || 0).getTime();
        })
        .slice(0, 20),
    );
    setControlCenterResult('cc-insight-result', data);
    setControlCenterStatusChip('cc-module-users-status', data?.user?.is_disabled ? 'warn' : 'ok', data?.user?.is_disabled ? 'Disabled' : 'Ready');
  } catch (error) {
    controlCenterCurrentInsight = null;
    setControlCenterState('insight', null);
    clearControlCenterTable('cc-insight-summary');
    clearControlCenterTable('cc-insight-payments-table');
    setControlCenterResult('cc-insight-result', { error: error.message });
  }
}

function getControlCenterSelectedUserId() {
  return getNumberValue('cc-insight-user-id');
}

async function disableUserFromControlCenter() {
  const userId = getControlCenterSelectedUserId();
  if (!userId) {
    showGlobalError('Nejprve vyberte user ID.');
    return;
  }
  if (!confirm(`Pozastavit účet uživatele #${userId}?`)) return;
  setControlCenterLoading('cc-insight-result');
  try {
    const data = await apiRequest('POST', `/admin-api/control-center/users/${userId}/disable`, { reason: 'admin_control_center' });
    setControlCenterResult('cc-insight-result', data);
    showSuccess('Účet byl pozastaven');
    await Promise.all([loadUsers(), loadControlCenterUsersSnapshot(), loadControlCenterUserInsight()]);
  } catch (error) {
    setControlCenterResult('cc-insight-result', { error: error.message });
  }
}

async function enableUserFromControlCenter() {
  const userId = getControlCenterSelectedUserId();
  if (!userId) {
    showGlobalError('Nejprve vyberte user ID.');
    return;
  }
  if (!confirm(`Aktivovat účet uživatele #${userId}?`)) return;
  setControlCenterLoading('cc-insight-result');
  try {
    const data = await apiRequest('POST', `/admin-api/control-center/users/${userId}/enable`, { reason: 'admin_control_center' });
    setControlCenterResult('cc-insight-result', data);
    showSuccess('Účet byl aktivován');
    await Promise.all([loadUsers(), loadControlCenterUsersSnapshot(), loadControlCenterUserInsight()]);
  } catch (error) {
    setControlCenterResult('cc-insight-result', { error: error.message });
  }
}

async function forceLogoutFromControlCenter() {
  const userId = getControlCenterSelectedUserId();
  if (!userId) {
    showGlobalError('Nejprve vyberte user ID.');
    return;
  }
  if (!confirm(`Ukončit všechny relace uživatele #${userId}?`)) return;
  setControlCenterLoading('cc-insight-result');
  try {
    const data = await apiRequest('POST', `/admin-api/control-center/users/${userId}/force-logout`, { reason: 'admin_control_center' });
    setControlCenterResult('cc-insight-result', data);
    showSuccess('Relace uživatele byly ukončeny');
    await loadControlCenterUserInsight();
  } catch (error) {
    setControlCenterResult('cc-insight-result', { error: error.message });
  }
}

async function resetUserPasswordFromControlCenter() {
  const userId = getControlCenterSelectedUserId();
  if (!userId) {
    showGlobalError('Nejprve vyberte user ID.');
    return;
  }
  const customPassword = prompt('Nové heslo (nechte prázdné pro náhodné dočasné heslo):', '');
  setControlCenterLoading('cc-insight-result');
  try {
    const data = await apiRequest('POST', `/admin-api/control-center/users/${userId}/reset-password`, {
      new_password: customPassword || null,
      generate_random: !customPassword,
      reason: 'admin_control_center',
    });
    setControlCenterResult('cc-insight-result', data);
    if (data?.temporary_password) {
      showSuccess(`Heslo resetováno. Dočasné heslo: ${data.temporary_password}`);
    } else {
      showSuccess('Heslo bylo resetováno');
    }
    await loadControlCenterUserInsight();
  } catch (error) {
    setControlCenterResult('cc-insight-result', { error: error.message });
  }
}

async function updateUserLicenseFromControlCenter() {
  const userId = getControlCenterSelectedUserId();
  if (!userId) {
    showGlobalError('Nejprve vyberte user ID.');
    return;
  }
  const plan = (document.getElementById('cc-license-plan')?.value || '').trim();
  const status = (document.getElementById('cc-license-status')?.value || '').trim();
  if (!plan && !status) {
    showGlobalError('Vyberte alespoň jednu změnu licence (plan/status).');
    return;
  }
  setControlCenterLoading('cc-insight-result');
  try {
    const data = await apiRequest('POST', `/admin-api/control-center/users/${userId}/license`, {
      plan: plan || null,
      status: status || null,
      source: 'developer_override',
      reason: 'admin_control_center',
    });
    setControlCenterResult('cc-insight-result', data);
    showSuccess('Licence byla aktualizována');
    await Promise.all([loadUsers(), loadControlCenterUsersSnapshot(), loadControlCenterUserInsight()]);
  } catch (error) {
    setControlCenterResult('cc-insight-result', { error: error.message });
  }
}

async function broadcastControlCenterNotification() {
  const message = (document.getElementById('cc-broadcast-message')?.value || '').trim();
  const title = (document.getElementById('cc-broadcast-title')?.value || '').trim();
  const targetType = (document.getElementById('cc-broadcast-target-type')?.value || 'all').trim();
  const targetValueRaw = (document.getElementById('cc-broadcast-target-value')?.value || '').trim();
  if (!message || message.length < 3) {
    showGlobalError('Zpráva musí mít alespoň 3 znaky.');
    return;
  }
  let targetValue = targetValueRaw || null;
  if (targetType === 'all') {
    targetValue = null;
  }
  setControlCenterLoading('cc-notifications-result');
  try {
    const data = await apiRequest('POST', '/admin-api/control-center/notifications/broadcast', {
      message,
      title: title || null,
      target_type: targetType,
      target_value: targetValue,
      severity: 'info',
    });
    setControlCenterResult('cc-notifications-result', data);
    showSuccess('Broadcast byl odeslán');
    setControlCenterText('cc-notifications-target-preview', targetValue ? `${targetType}:${targetValue}` : targetType);
    await loadControlCenterNotifications();
  } catch (error) {
    setControlCenterResult('cc-notifications-result', { error: error.message });
  }
}

async function loadControlCenterNotifications() {
  setControlCenterLoading('cc-notifications-result', ['cc-notifications-table']);
  try {
    const data = await apiRequest('GET', '/admin-api/control-center/notifications?limit=50');
    setControlCenterState('notifications', data);
    const items = Array.isArray(data?.items) ? data.items : [];
    renderControlCenterTable(
      'cc-notifications-table',
      [
        { key: 'id', label: '#' },
        { key: 'target_type', label: 'Target', render: (row) => `${escapeHtml(row.target_type || '-')}${row.target_value ? `:${escapeHtml(row.target_value)}` : ''}` },
        { key: 'severity', label: 'Severity', render: (row) => escapeHtml(row.severity || 'info') },
        { key: 'title', label: 'Titulek', render: (row) => escapeHtml(row.title || '-') },
        { key: 'message', label: 'Zpráva', render: (row) => escapeHtml(row.message || '-') },
        { key: 'created_at', label: 'Vytvořeno', render: (row) => formatDateTime(row.created_at) },
      ],
      items,
    );
    setControlCenterResult('cc-notifications-result', data);
  } catch (error) {
    clearControlCenterTable('cc-notifications-table');
    setControlCenterResult('cc-notifications-result', { error: error.message });
  }
}

async function previewControlCenterStorageCleanup() {
  setControlCenterLoading('cc-infra-result', ['cc-storage-preview-table']);
  try {
    const data = await apiRequest('GET', '/admin-api/control-center/storage/cleanup-preview?logs_days=30&backups_days=30');
    setControlCenterState('storageCleanupPreview', data);
    renderControlCenterTable(
      'cc-storage-preview-table',
      [
        { key: 'label', label: 'Cleanup preview', render: (row) => escapeHtml(row.label) },
        { key: 'value', label: 'Hodnota', render: (row) => escapeHtml(row.value) },
      ],
      [
        { label: 'Confirm text', value: String(data.confirm_text_required || '-') },
        { label: 'Old logs', value: `${formatNumber(data.old_logs_count || 0)} (${data.old_logs_human || '-'})` },
        { label: 'Old backups', value: `${formatNumber(data.old_backups_count || 0)} (${data.old_backups_human || '-'})` },
      ],
    );
    setControlCenterResult('cc-infra-result', data);
  } catch (error) {
    clearControlCenterTable('cc-storage-preview-table');
    setControlCenterResult('cc-infra-result', { error: error.message });
  }
}

async function runControlCenterStorageCleanup() {
  const confirmText = (document.getElementById('cc-storage-cleanup-confirm')?.value || '').trim();
  if (!confirm('Storage cleanup smaže staré logy a backupy. Pokračovat?')) return;
  setControlCenterLoading('cc-infra-result');
  try {
    const data = await apiRequest('POST', '/admin-api/control-center/storage/cleanup', {
      confirm_text: confirmText,
      delete_old_logs_days: 30,
      delete_old_backups_days: 30,
    });
    setControlCenterResult('cc-infra-result', data);
    showSuccess('Storage cleanup dokončen');
    await Promise.all([loadControlCenterStorage(), previewControlCenterStorageCleanup()]);
  } catch (error) {
    setControlCenterResult('cc-infra-result', { error: error.message });
  }
}

async function openControlCenterProblemUsers() {
  let users = Array.isArray(controlCenterDataState.users) ? controlCenterDataState.users : [];
  if (users.length === 0) {
    try {
      users = await fetchAllList('/admin-api/users');
      setControlCenterState('users', users);
    } catch (error) {
      showGlobalError(`Nelze načíst problémové uživatele: ${error.message}`);
      return;
    }
  }

  const problemUsers = users.filter((user) => isUnpaidProblemUser(user));
  renderControlCenterTable(
    'cc-problem-users-table',
    [
      { key: 'id', label: 'User ID', render: (row) => formatNumber(row.id || 0) },
      { key: 'email', label: 'Email', render: (row) => escapeHtml(row.email || '-') },
      { key: 'license_plan', label: 'Plan', render: (row) => escapeHtml(String(row.license_plan || 'free').toUpperCase()) },
      { key: 'license_status', label: 'Licence status', render: (row) => escapeHtml(String(row.license_status || 'active')) },
      { key: 'has_paid', label: 'Has paid', render: (row) => row.has_paid ? 'ANO' : 'NE' },
      { key: 'last_paid_at', label: 'Poslední platba', render: (row) => formatDateTime(row.last_paid_at) },
    ],
    problemUsers.slice(0, 120),
  );
  openControlCenterModuleDetails('cc-payments-details');
  setControlCenterResult('cc-payments-result', {
    message: `Filtrovaní problémoví uživatelé: ${problemUsers.length}`,
    count: problemUsers.length,
  });
}

// ============================================
// LOGIN & AUTH
// ============================================

async function handleAdminLogin(event) {
  event.preventDefault();
  hideGlobalError();
  
  const email = document.getElementById('admin-email').value.trim();
  const password = document.getElementById('admin-password').value;
  const errorEl = document.getElementById('login-error');
  
  errorEl.style.display = 'none';
  
  if (!email || !password) {
    errorEl.textContent = 'Vyplňte prosím email a heslo';
    errorEl.classList.remove('hidden');
    return;
  }
  
  try {
    const data = await apiRequest('POST', '/user/login', { email, password });
    
    const role = data?.user?.role;
    if (!role || !['developer_admin', 'admin'].includes(role)) {
      throw new Error('Přístup odepřen. Vyžadována role developer_admin nebo admin.');
    }
    
    setAuthToken(data.access_token);
    setAdminRole(role);
    showDashboard();
    
  } catch (error) {
    errorEl.textContent = error.message || 'Chyba při přihlášení';
    errorEl.classList.remove('hidden');
  }
}

function handleAdminLogout() {
  clearAuthToken();
  showLoginScreen();
}

function showLoginScreen() {
  closeAllControlCenterDetails();
  closeAdminMobileNav();
  document.getElementById('login-screen').classList.remove('hidden');
  document.getElementById('dashboard-screen').classList.add('hidden');
  document.getElementById('admin-email').value = '';
  document.getElementById('admin-password').value = '';
  document.getElementById('login-error').classList.add('hidden');
}

function showDashboard() {
  closeAllControlCenterDetails();
  document.getElementById('login-screen').classList.add('hidden');
  document.getElementById('dashboard-screen').classList.remove('hidden');
  hideGlobalError();
  closeAdminMobileNav();

  initSectionViewModes();
  
  // Inicializovat navigaci
  initNavigation();

  updateControlCenterVisibility();
  resolveCurrentAdminRole();
  loadSystemCapabilitiesAdmin();
  
  // Načíst přehled jako výchozí
  switchSection('overview');
}

// ============================================
// INITIALIZATION
// ============================================

window.addEventListener('DOMContentLoaded', () => {
  const token = getAuthToken();

  window.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      closeAdminMobileNav();
      closeAllControlCenterDetails();
    }
  });

  window.addEventListener('resize', () => {
    if (!isAdminMobileViewport()) {
      closeAdminMobileNav();
    }
    if (!window.matchMedia('(min-width: 1101px)').matches) {
      closeAllControlCenterDetails();
      return;
    }
    syncControlCenterDetailsOverlayState();
  });
  
  if (token) {
    // Zkusit načíst uživatele - pokud selže (token neplatný), zobrazit přihlášení
    apiRequest('GET', '/admin-api/users')
      .then(() => {
        showDashboard();
      })
      .catch(() => {
        clearAuthToken();
        showLoginScreen();
      });
  } else {
    showLoginScreen();
  }
});
