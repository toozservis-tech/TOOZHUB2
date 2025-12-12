// ============================================
// TOOZ HUB 2 - ADMIN DASHBOARD
// Kompletní refaktoring s plně funkčním CRUD
// ============================================

const API_BASE = "";

// Globální proměnné
let authToken = null;
let currentSection = "overview";

// ============================================
// AUTH & TOKEN MANAGEMENT
// ============================================

function getAuthToken() {
  if (authToken) return authToken;
  authToken = localStorage.getItem('accessToken');
  if (authToken) return authToken;
  const urlParams = new URLSearchParams(window.location.search);
  authToken = urlParams.get('token');
  if (authToken) {
    localStorage.setItem('accessToken', authToken);
    return authToken;
  }
  return null;
}

function setAuthToken(token) {
  authToken = token;
  localStorage.setItem('accessToken', token);
}

function clearAuthToken() {
  authToken = null;
  localStorage.removeItem('accessToken');
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

function switchSection(section) {
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
  
  container.innerHTML = '<div class="loading">Načítám uživatele...</div>';
  
  try {
    const users = await apiRequest('GET', '/admin-api/users');
    
    if (users.length === 0) {
      container.innerHTML = '<div class="empty">Žádní uživatelé</div>';
      return;
    }
    
    container.innerHTML = users.map(user => {
      const createdDate = user.created_at ? new Date(user.created_at).toLocaleDateString('cs-CZ') : '-';
      return `
        <div class="card" data-user-id="${user.id}">
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
              <span class="card-label">Vozidla</span>
              <span class="card-value">${user.vehicles_count || 0}</span>
            </div>
            <div class="card-field">
              <span class="card-label">Registrován</span>
              <span class="card-value">${createdDate}</span>
            </div>
          </div>
          <div class="card-actions">
            <button class="btn-edit" onclick="editUser(${user.id})">✏️ Upravit</button>
            <button class="btn-danger" onclick="deleteUser(${user.id}, '${user.email}')">🗑️ Smazat</button>
          </div>
        </div>
      `;
    }).join('');
    
    // Vyhledávání
    const searchInput = document.getElementById('user-search');
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
      const users = await apiRequest('GET', '/admin-api/users');
      const user = users.find(u => u.id === userId);
      if (user) {
        document.getElementById('user-id').value = user.id;
        document.getElementById('user-email').value = user.email || '';
        document.getElementById('user-name').value = user.name || '';
        document.getElementById('user-role').value = user.role || 'user';
        passwordInput.value = '';
      }
    } catch (error) {
      showGlobalError('Chyba při načítání uživatele: ' + error.message);
      return;
    }
  } else {
    title.textContent = 'Přidat uživatele';
    passwordHint.textContent = '(povinné při vytvoření)';
    form.reset();
    document.getElementById('user-id').value = '';
    passwordInput.required = true;
  }
  
  modal.classList.remove('hidden');
}

function closeUserModal() {
  document.getElementById('user-modal').classList.add('hidden');
  document.getElementById('user-form').reset();
}

async function saveUser(event) {
  event.preventDefault();
  
  const userId = document.getElementById('user-id').value;
  const userData = {
    email: document.getElementById('user-email').value,
    name: document.getElementById('user-name').value || null,
    role: document.getElementById('user-role').value,
  };
  
  const password = document.getElementById('user-password').value;
  if (password) {
    userData.password = password;
  }
  
  try {
    if (userId) {
      await apiRequest('PATCH', `/admin-api/users/${userId}`, userData);
      showSuccess('Uživatel byl upraven');
    } else {
      if (!password) {
        showGlobalError('Heslo je povinné při vytváření uživatele');
        return;
      }
      await apiRequest('POST', '/admin-api/users', userData);
      showSuccess('Uživatel byl vytvořen');
    }
    
    closeUserModal();
    loadUsers();
    loadOverview(); // Aktualizovat statistiky
  } catch (error) {
    console.error('Error saving user:', error);
  }
}

async function editUser(userId) {
  showUserModal(userId);
}

async function deleteUser(userId, userEmail) {
  if (!confirm(`Opravdu chcete smazat uživatele ${userEmail}?`)) {
    return;
  }
  
  try {
    await apiRequest('DELETE', `/admin-api/users/${userId}`);
    showSuccess('Uživatel byl smazán');
    loadUsers();
    loadOverview();
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
    const vehicles = await apiRequest('GET', '/admin-api/vehicles');
    
    if (vehicles.length === 0) {
      container.innerHTML = '<div class="empty">Žádná vozidla</div>';
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
      const vehicles = await apiRequest('GET', '/admin-api/vehicles');
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

function closeVehicleModal() {
  document.getElementById('vehicle-modal').classList.add('hidden');
  document.getElementById('vehicle-form').reset();
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
      showSuccess('Vozidlo bylo upraveno');
    } else {
      await apiRequest('POST', '/admin-api/vehicles', vehicleData);
      showSuccess('Vozidlo bylo vytvořeno');
    }
    
    closeVehicleModal();
    loadVehicles();
    loadOverview();
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
  
  try {
    const services = await apiRequest('GET', '/admin-api/services');
    
    if (services.length === 0) {
      container.innerHTML = '<div class="empty">Žádné servisy</div>';
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
      const services = await apiRequest('GET', '/admin-api/services');
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
    const records = await apiRequest('GET', '/admin-api/records');
    
    if (records.length === 0) {
      container.innerHTML = '<div class="empty">Žádné záznamy</div>';
      return;
    }
    
    container.innerHTML = records.map(record => {
      const performedDate = record.performed_at ? new Date(record.performed_at).toLocaleDateString('cs-CZ') : '-';
      return `
        <div class="card" data-record-id="${record.id}">
          <div class="card-header">
            <h3 class="card-title">📋 ${record.description || 'Bez popisu'}</h3>
            <span class="card-id">#${record.id}</span>
          </div>
          <div class="card-body">
            <div class="card-field">
              <span class="card-label">Servis</span>
              <span class="card-value">${record.service_name || record.service_id || '-'}</span>
            </div>
            <div class="card-field">
              <span class="card-label">Vozidlo</span>
              <span class="card-value">${record.vehicle_name || record.vehicle_id || '-'}</span>
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

async function loadRecordFormData() {
  // Načíst servisy a vozidla pro selecty
  try {
    const [services, vehicles] = await Promise.all([
      apiRequest('GET', '/admin-api/services'),
      apiRequest('GET', '/admin-api/vehicles')
    ]);
    
    const serviceSelect = document.getElementById('record-service-id');
    const vehicleSelect = document.getElementById('record-vehicle-id');
    
    if (serviceSelect) {
      serviceSelect.innerHTML = '<option value="">Vyberte servis</option>' +
        services.map(s => `<option value="${s.id}">${s.name || s.email}</option>`).join('');
    }
    
    if (vehicleSelect) {
      vehicleSelect.innerHTML = '<option value="">Vyberte vozidlo</option>' +
        vehicles.map(v => {
          const name = v.nickname || `${v.brand || ''} ${v.model || ''}`.trim() || `ID ${v.id}`;
          return `<option value="${v.id}">${name} (${v.user_email})</option>`;
        }).join('');
    }
  } catch (error) {
    console.error('Error loading form data:', error);
  }
}

async function showRecordModal(recordId = null) {
  const modal = document.getElementById('record-modal');
  const title = document.getElementById('record-modal-title');
  
  await loadRecordFormData();
  
  if (recordId) {
    title.textContent = 'Upravit záznam';
    try {
      const records = await apiRequest('GET', '/admin-api/records');
      const record = records.find(r => r.id === recordId);
      if (record) {
        document.getElementById('record-id').value = record.id;
        document.getElementById('record-service-id').value = record.service_id || '';
        document.getElementById('record-vehicle-id').value = record.vehicle_id || '';
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
    
    // Nastavit výchozí datum na teď
    const now = new Date();
    const localNow = new Date(now.getTime() - now.getTimezoneOffset() * 60000);
    document.getElementById('record-performed-at').value = localNow.toISOString().slice(0, 16);
  }
  
  modal.classList.remove('hidden');
}

function closeRecordModal() {
  document.getElementById('record-modal').classList.add('hidden');
  document.getElementById('record-form').reset();
}

async function saveRecord(event) {
  event.preventDefault();
  
  const recordId = document.getElementById('record-id').value;
  const performedAtStr = document.getElementById('record-performed-at').value;
  const performedAt = performedAtStr ? new Date(performedAtStr) : new Date();
  
  const recordData = {
    service_id: parseInt(document.getElementById('record-service-id').value),
    vehicle_id: parseInt(document.getElementById('record-vehicle-id').value),
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
      showSuccess('Záznam byl upraven');
    } else {
      await apiRequest('POST', '/admin-api/records', recordData);
      showSuccess('Záznam byl vytvořen');
    }
    
    closeRecordModal();
    loadRecords();
    loadOverview();
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
    resultEl.innerHTML = `
      <div style="color: #28a745;">
        <strong>✓ ${result.message}</strong>
        <ul style="margin-top: 8px; padding-left: 20px;">
          ${result.results.map(r => `<li>${r}</li>`).join('')}
        </ul>
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
    resultEl.innerHTML = `
      <div style="color: #28a745;">
        <strong>✓ ${result.message}</strong>
        <ul style="margin-top: 8px; padding-left: 20px;">
          ${result.results.map(r => `<li>${r}</li>`).join('')}
        </ul>
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
    
    if (!data.user || data.user.role !== 'developer_admin') {
      throw new Error('Přístup odepřen. Vyžadována role developer_admin.');
    }
    
    setAuthToken(data.access_token);
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
  document.getElementById('login-screen').classList.remove('hidden');
  document.getElementById('dashboard-screen').classList.add('hidden');
  document.getElementById('admin-email').value = '';
  document.getElementById('admin-password').value = '';
  document.getElementById('login-error').classList.add('hidden');
}

function showDashboard() {
  document.getElementById('login-screen').classList.add('hidden');
  document.getElementById('dashboard-screen').classList.remove('hidden');
  hideGlobalError();
  
  // Inicializovat navigaci
  initNavigation();
  
  // Načíst přehled jako výchozí
  switchSection('overview');
}

// ============================================
// INITIALIZATION
// ============================================

window.addEventListener('DOMContentLoaded', () => {
  const token = getAuthToken();
  
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



// Kompletní refaktoring s plně funkčním CRUD
// ============================================

const API_BASE = "";

// Globální proměnné
let authToken = null;
let currentSection = "overview";

// ============================================
// AUTH & TOKEN MANAGEMENT
// ============================================

function getAuthToken() {
  if (authToken) return authToken;
  authToken = localStorage.getItem('accessToken');
  if (authToken) return authToken;
  const urlParams = new URLSearchParams(window.location.search);
  authToken = urlParams.get('token');
  if (authToken) {
    localStorage.setItem('accessToken', authToken);
    return authToken;
  }
  return null;
}

function setAuthToken(token) {
  authToken = token;
  localStorage.setItem('accessToken', token);
}

function clearAuthToken() {
  authToken = null;
  localStorage.removeItem('accessToken');
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

function switchSection(section) {
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
  
  container.innerHTML = '<div class="loading">Načítám uživatele...</div>';
  
  try {
    const users = await apiRequest('GET', '/admin-api/users');
    
    if (users.length === 0) {
      container.innerHTML = '<div class="empty">Žádní uživatelé</div>';
      return;
    }
    
    container.innerHTML = users.map(user => {
      const createdDate = user.created_at ? new Date(user.created_at).toLocaleDateString('cs-CZ') : '-';
      return `
        <div class="card" data-user-id="${user.id}">
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
              <span class="card-label">Vozidla</span>
              <span class="card-value">${user.vehicles_count || 0}</span>
            </div>
            <div class="card-field">
              <span class="card-label">Registrován</span>
              <span class="card-value">${createdDate}</span>
            </div>
          </div>
          <div class="card-actions">
            <button class="btn-edit" onclick="editUser(${user.id})">✏️ Upravit</button>
            <button class="btn-danger" onclick="deleteUser(${user.id}, '${user.email}')">🗑️ Smazat</button>
          </div>
        </div>
      `;
    }).join('');
    
    // Vyhledávání
    const searchInput = document.getElementById('user-search');
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
      const users = await apiRequest('GET', '/admin-api/users');
      const user = users.find(u => u.id === userId);
      if (user) {
        document.getElementById('user-id').value = user.id;
        document.getElementById('user-email').value = user.email || '';
        document.getElementById('user-name').value = user.name || '';
        document.getElementById('user-role').value = user.role || 'user';
        passwordInput.value = '';
      }
    } catch (error) {
      showGlobalError('Chyba při načítání uživatele: ' + error.message);
      return;
    }
  } else {
    title.textContent = 'Přidat uživatele';
    passwordHint.textContent = '(povinné při vytvoření)';
    form.reset();
    document.getElementById('user-id').value = '';
    passwordInput.required = true;
  }
  
  modal.classList.remove('hidden');
}

function closeUserModal() {
  document.getElementById('user-modal').classList.add('hidden');
  document.getElementById('user-form').reset();
}

async function saveUser(event) {
  event.preventDefault();
  
  const userId = document.getElementById('user-id').value;
  const userData = {
    email: document.getElementById('user-email').value,
    name: document.getElementById('user-name').value || null,
    role: document.getElementById('user-role').value,
  };
  
  const password = document.getElementById('user-password').value;
  if (password) {
    userData.password = password;
  }
  
  try {
    if (userId) {
      await apiRequest('PATCH', `/admin-api/users/${userId}`, userData);
      showSuccess('Uživatel byl upraven');
    } else {
      if (!password) {
        showGlobalError('Heslo je povinné při vytváření uživatele');
        return;
      }
      await apiRequest('POST', '/admin-api/users', userData);
      showSuccess('Uživatel byl vytvořen');
    }
    
    closeUserModal();
    loadUsers();
    loadOverview(); // Aktualizovat statistiky
  } catch (error) {
    console.error('Error saving user:', error);
  }
}

async function editUser(userId) {
  showUserModal(userId);
}

async function deleteUser(userId, userEmail) {
  if (!confirm(`Opravdu chcete smazat uživatele ${userEmail}?`)) {
    return;
  }
  
  try {
    await apiRequest('DELETE', `/admin-api/users/${userId}`);
    showSuccess('Uživatel byl smazán');
    loadUsers();
    loadOverview();
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
    const vehicles = await apiRequest('GET', '/admin-api/vehicles');
    
    if (vehicles.length === 0) {
      container.innerHTML = '<div class="empty">Žádná vozidla</div>';
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
      const vehicles = await apiRequest('GET', '/admin-api/vehicles');
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

function closeVehicleModal() {
  document.getElementById('vehicle-modal').classList.add('hidden');
  document.getElementById('vehicle-form').reset();
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
      showSuccess('Vozidlo bylo upraveno');
    } else {
      await apiRequest('POST', '/admin-api/vehicles', vehicleData);
      showSuccess('Vozidlo bylo vytvořeno');
    }
    
    closeVehicleModal();
    loadVehicles();
    loadOverview();
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
  
  try {
    const services = await apiRequest('GET', '/admin-api/services');
    
    if (services.length === 0) {
      container.innerHTML = '<div class="empty">Žádné servisy</div>';
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
      const services = await apiRequest('GET', '/admin-api/services');
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
    const records = await apiRequest('GET', '/admin-api/records');
    
    if (records.length === 0) {
      container.innerHTML = '<div class="empty">Žádné záznamy</div>';
      return;
    }
    
    container.innerHTML = records.map(record => {
      const performedDate = record.performed_at ? new Date(record.performed_at).toLocaleDateString('cs-CZ') : '-';
      return `
        <div class="card" data-record-id="${record.id}">
          <div class="card-header">
            <h3 class="card-title">📋 ${record.description || 'Bez popisu'}</h3>
            <span class="card-id">#${record.id}</span>
          </div>
          <div class="card-body">
            <div class="card-field">
              <span class="card-label">Servis</span>
              <span class="card-value">${record.service_name || record.service_id || '-'}</span>
            </div>
            <div class="card-field">
              <span class="card-label">Vozidlo</span>
              <span class="card-value">${record.vehicle_name || record.vehicle_id || '-'}</span>
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

async function loadRecordFormData() {
  // Načíst servisy a vozidla pro selecty
  try {
    const [services, vehicles] = await Promise.all([
      apiRequest('GET', '/admin-api/services'),
      apiRequest('GET', '/admin-api/vehicles')
    ]);
    
    const serviceSelect = document.getElementById('record-service-id');
    const vehicleSelect = document.getElementById('record-vehicle-id');
    
    if (serviceSelect) {
      serviceSelect.innerHTML = '<option value="">Vyberte servis</option>' +
        services.map(s => `<option value="${s.id}">${s.name || s.email}</option>`).join('');
    }
    
    if (vehicleSelect) {
      vehicleSelect.innerHTML = '<option value="">Vyberte vozidlo</option>' +
        vehicles.map(v => {
          const name = v.nickname || `${v.brand || ''} ${v.model || ''}`.trim() || `ID ${v.id}`;
          return `<option value="${v.id}">${name} (${v.user_email})</option>`;
        }).join('');
    }
  } catch (error) {
    console.error('Error loading form data:', error);
  }
}

async function showRecordModal(recordId = null) {
  const modal = document.getElementById('record-modal');
  const title = document.getElementById('record-modal-title');
  
  await loadRecordFormData();
  
  if (recordId) {
    title.textContent = 'Upravit záznam';
    try {
      const records = await apiRequest('GET', '/admin-api/records');
      const record = records.find(r => r.id === recordId);
      if (record) {
        document.getElementById('record-id').value = record.id;
        document.getElementById('record-service-id').value = record.service_id || '';
        document.getElementById('record-vehicle-id').value = record.vehicle_id || '';
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
    
    // Nastavit výchozí datum na teď
    const now = new Date();
    const localNow = new Date(now.getTime() - now.getTimezoneOffset() * 60000);
    document.getElementById('record-performed-at').value = localNow.toISOString().slice(0, 16);
  }
  
  modal.classList.remove('hidden');
}

function closeRecordModal() {
  document.getElementById('record-modal').classList.add('hidden');
  document.getElementById('record-form').reset();
}

async function saveRecord(event) {
  event.preventDefault();
  
  const recordId = document.getElementById('record-id').value;
  const performedAtStr = document.getElementById('record-performed-at').value;
  const performedAt = performedAtStr ? new Date(performedAtStr) : new Date();
  
  const recordData = {
    service_id: parseInt(document.getElementById('record-service-id').value),
    vehicle_id: parseInt(document.getElementById('record-vehicle-id').value),
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
      showSuccess('Záznam byl upraven');
    } else {
      await apiRequest('POST', '/admin-api/records', recordData);
      showSuccess('Záznam byl vytvořen');
    }
    
    closeRecordModal();
    loadRecords();
    loadOverview();
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
    resultEl.innerHTML = `
      <div style="color: #28a745;">
        <strong>✓ ${result.message}</strong>
        <ul style="margin-top: 8px; padding-left: 20px;">
          ${result.results.map(r => `<li>${r}</li>`).join('')}
        </ul>
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
    resultEl.innerHTML = `
      <div style="color: #28a745;">
        <strong>✓ ${result.message}</strong>
        <ul style="margin-top: 8px; padding-left: 20px;">
          ${result.results.map(r => `<li>${r}</li>`).join('')}
        </ul>
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
    
    if (!data.user || data.user.role !== 'developer_admin') {
      throw new Error('Přístup odepřen. Vyžadována role developer_admin.');
    }
    
    setAuthToken(data.access_token);
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
  document.getElementById('login-screen').classList.remove('hidden');
  document.getElementById('dashboard-screen').classList.add('hidden');
  document.getElementById('admin-email').value = '';
  document.getElementById('admin-password').value = '';
  document.getElementById('login-error').classList.add('hidden');
}

function showDashboard() {
  document.getElementById('login-screen').classList.add('hidden');
  document.getElementById('dashboard-screen').classList.remove('hidden');
  hideGlobalError();
  
  // Inicializovat navigaci
  initNavigation();
  
  // Načíst přehled jako výchozí
  switchSection('overview');
}

// ============================================
// INITIALIZATION
// ============================================

window.addEventListener('DOMContentLoaded', () => {
  const token = getAuthToken();
  
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
