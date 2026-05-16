window.fakturywebTestState = {
  activeTab: 'settings', // settings, create, list, remote
  settings: null,
  localInvoices: [],
  remoteInvoices: null,
  remoteRaw: null,
  loading: false,
  error: null,
};

async function fetchFakturywebSettings() {
  try {
    const res = await fetch('/api/v1/services/workspace/fakturyweb/settings', {
      headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
    });
    if (!res.ok) throw new Error('Nepodařilo se načíst nastavení');
    window.fakturywebTestState.settings = await res.json();
  } catch (err) {
    console.error(err);
  }
}

async function saveFakturywebSettings(e) {
  e.preventDefault();
  const formData = new FormData(e.target);
  const payload = Object.fromEntries(formData.entries());
  payload.default_due_days = parseInt(payload.default_due_days || '7', 10);
  payload.default_qr = parseInt(payload.default_qr || '1', 10);
  
  try {
    const res = await fetch('/api/v1/services/workspace/fakturyweb/settings', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('token')}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    });
    if (!res.ok) throw new Error('Chyba při ukládání nastavení');
    if (typeof window.showAlert === 'function') window.showAlert('Nastavení uloženo.', 'success');
    await fetchFakturywebSettings();
    renderFakturywebTest();
  } catch (err) {
    if (typeof window.showAlert === 'function') window.showAlert(err.message, 'error');
  }
}

async function testFakturywebConnection() {
  try {
    const res = await fetch('/api/v1/services/workspace/fakturyweb/test-connection', {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
    });
    const data = await res.json();
    if (data.ok) {
      if (typeof window.showAlert === 'function') window.showAlert('Spojení úspěšné.', 'success');
    } else {
      if (typeof window.showAlert === 'function') window.showAlert(`Chyba spojení: ${data.message}`, 'error');
    }
    await fetchFakturywebSettings();
    renderFakturywebTest();
  } catch (err) {
    if (typeof window.showAlert === 'function') window.showAlert('Chyba při testu spojení.', 'error');
  }
}

async function createFakturywebTestInvoice(e) {
  e.preventDefault();
  const formData = new FormData(e.target);
  
  const payload = {
    customer: {
      name: formData.get('o_name'),
      street: formData.get('o_street'),
      city: formData.get('o_city'),
      zip: formData.get('o_zip'),
      state: formData.get('o_state'),
      ico: formData.get('o_ico'),
      dic: formData.get('o_dic'),
      email: formData.get('o_email')
    },
    invoice: {
      issue_date: formData.get('f_date_issue'),
      delivery_date: formData.get('f_date_delivery'),
      due_date: formData.get('f_date_due'),
      payment: formData.get('f_payment'),
      currency: formData.get('f_currency'),
      note: formData.get('f_note'),
      internal_note: formData.get('f_internal_note'),
      qr: parseInt(formData.get('f_qr') || '1', 10),
      style: formData.get('f_style')
    },
    items: [
      {
        text: formData.get('p_text'),
        quantity: parseFloat(formData.get('p_quantity') || '1'),
        unit: formData.get('p_unit'),
        price: parseFloat(formData.get('p_price') || '0'),
        vat: formData.get('p_vat') ? parseFloat(formData.get('p_vat')) : null
      }
    ]
  };
  
  try {
    const res = await fetch('/api/v1/services/workspace/fakturyweb/invoices/test-create', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('token')}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (res.ok && data.ok) {
      if (typeof window.showAlert === 'function') window.showAlert(`Faktura vytvořena. Kód: ${data.code}`, 'success');
      window.fakturywebTestState.activeTab = 'list';
      await fetchFakturywebLocalInvoices();
      renderFakturywebTest();
    } else {
      throw new Error(data.detail || data.message || 'Chyba při vytváření faktury');
    }
  } catch (err) {
    if (typeof window.showAlert === 'function') window.showAlert(err.message, 'error');
  }
}

async function fetchFakturywebLocalInvoices() {
  try {
    const res = await fetch('/api/v1/services/workspace/fakturyweb/invoices', {
      headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
    });
    if (!res.ok) throw new Error('Nepodařilo se načíst lokální faktury');
    window.fakturywebTestState.localInvoices = await res.json();
  } catch (err) {
    console.error(err);
  }
}

async function viewFakturywebInvoicePdf(id) {
  try {
    const res = await fetch(`/api/v1/services/workspace/fakturyweb/invoices/${id}/view`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
    });
    const data = await res.json();
    if (res.ok && data.ok && data.pdf_url) {
      window.open(data.pdf_url, '_blank');
      await fetchFakturywebLocalInvoices();
      renderFakturywebTest();
    } else {
      throw new Error(data.detail || data.message || 'Nepodařilo se získat PDF');
    }
  } catch (err) {
    if (typeof window.showAlert === 'function') window.showAlert(err.message, 'error');
  }
}

async function checkFakturywebInvoiceStatus(id) {
  try {
    const res = await fetch(`/api/v1/services/workspace/fakturyweb/invoices/${id}/status`, {
      headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
    });
    const data = await res.json();
    if (res.ok && data.ok) {
      if (typeof window.showAlert === 'function') window.showAlert(`Stav: ${data.status}`, 'success');
      await fetchFakturywebLocalInvoices();
      renderFakturywebTest();
    } else {
      throw new Error(data.detail || data.message || 'Nepodařilo se načíst status');
    }
  } catch (err) {
    if (typeof window.showAlert === 'function') window.showAlert(err.message, 'error');
  }
}

async function markFakturywebInvoicePaid(id) {
  const date = prompt('Zadejte datum úhrady (YYYY-MM-DD):', new Date().toISOString().split('T')[0]);
  if (!date) return;
  
  try {
    const res = await fetch(`/api/v1/services/workspace/fakturyweb/invoices/${id}/mark-paid`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('token')}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ date })
    });
    const data = await res.json();
    if (res.ok && data.ok) {
      if (typeof window.showAlert === 'function') window.showAlert('Faktura označena jako uhrazená', 'success');
      await fetchFakturywebLocalInvoices();
      renderFakturywebTest();
    } else {
      throw new Error(data.detail || data.message || 'Nepodařilo se označit jako uhrazenou');
    }
  } catch (err) {
    if (typeof window.showAlert === 'function') window.showAlert(err.message, 'error');
  }
}

async function fetchFakturywebRemoteInvoices(e) {
  e.preventDefault();
  const formData = new FormData(e.target);
  const payload = Object.fromEntries(formData.entries());
  
  try {
    const res = await fetch('/api/v1/services/workspace/fakturyweb/invoices/list-remote', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('token')}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (res.ok && data.ok) {
      window.fakturywebTestState.remoteRaw = data.data;
      window.fakturywebTestState.remoteInvoices = data.data.list || [];
      renderFakturywebTest();
    } else {
      throw new Error(data.detail || data.message || 'Nepodařilo se načíst vzdálený seznam');
    }
  } catch (err) {
    if (typeof window.showAlert === 'function') window.showAlert(err.message, 'error');
  }
}

function switchFakturywebTab(tab) {
  window.fakturywebTestState.activeTab = tab;
  if (tab === 'settings') fetchFakturywebSettings().then(renderFakturywebTest);
  if (tab === 'list') fetchFakturywebLocalInvoices().then(renderFakturywebTest);
  renderFakturywebTest();
}

function renderFakturywebTest() {
  const container = document.getElementById('fakturyweb-test-container');
  if (!container) return;
  
  const state = window.fakturywebTestState;
  
  let content = '';
  
  if (state.activeTab === 'settings') {
    const s = state.settings || {};
    content = `
      <form onsubmit="saveFakturywebSettings(event)" class="service-shell-form">
        <div class="service-shell-form-group">
          <label>FakturyWeb e-mail / login</label>
          <input type="email" name="fakturyweb_email" class="service-shell-input" value="${s.email || ''}" required>
        </div>
        <div class="service-shell-form-group">
          <label>API klíč</label>
          <input type="password" name="fakturyweb_api_key" class="service-shell-input" value="${s.configured ? '********' : ''}" required>
        </div>
        <div class="service-shell-form-group">
          <label>Režim dodavatele</label>
          <select name="supplier_mode" class="service-shell-input">
            <option value="manual" ${s.supplier_mode === 'manual' ? 'selected' : ''}>Posílat dodavatele ručně z profilu servisu</option>
            <option value="saved_company" ${s.supplier_mode === 'saved_company' ? 'selected' : ''}>Použít uloženou společnost ve FakturyWeb (d_id)</option>
          </select>
        </div>
        <div class="service-shell-form-group">
          <label>d_id dodavatele (pokud je režim uložená společnost)</label>
          <input type="text" name="fakturyweb_d_id" class="service-shell-input" value="${s.d_id || ''}">
        </div>
        <div class="service-shell-form-group">
          <label>Výchozí splatnost (dny)</label>
          <input type="number" name="default_due_days" class="service-shell-input" value="7" required>
        </div>
        <div class="service-shell-form-group">
          <label>Výchozí typ platby</label>
          <select name="default_payment" class="service-shell-input">
            <option value="prevod">Převod</option>
            <option value="hotovost">Hotovost</option>
            <option value="karta">Karta</option>
          </select>
        </div>
        <div class="service-shell-form-group">
          <label>Měna</label>
          <input type="text" name="default_currency" class="service-shell-input" value="Kč" required>
        </div>
        <div class="service-shell-form-group">
          <label>Šablona</label>
          <input type="text" name="default_style" class="service-shell-input" value="styl_7" required>
        </div>
        <div class="service-shell-form-group">
          <label>QR platba</label>
          <select name="default_qr" class="service-shell-input">
            <option value="1" ${s.default_qr === 1 ? 'selected' : ''}>Ano</option>
            <option value="0" ${s.default_qr === 0 ? 'selected' : ''}>Ne</option>
          </select>
        </div>

        <h3 style="margin-top: 30px; margin-bottom: 15px; border-bottom: 1px solid #eee; padding-bottom: 5px;">Hlavička dodavatele (pro manuální režim)</h3>
        <p style="font-size: 0.9em; color: #666; margin-bottom: 15px;">
          Pokud nevyplníte, použijí se údaje z vašeho profilu servisu. Pokud používáte "uloženou společnost", tyto údaje se ignorují.
        </p>
        
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px;">
          <div class="service-shell-form-group"><label>Název firmy</label><input type="text" name="custom_d_name" class="service-shell-input" value="${s.custom_d_name || ''}"></div>
          <div class="service-shell-form-group"><label>IČO</label><input type="text" name="custom_d_ico" class="service-shell-input" value="${s.custom_d_ico || ''}"></div>
          <div class="service-shell-form-group"><label>DIČ</label><input type="text" name="custom_d_dic" class="service-shell-input" value="${s.custom_d_dic || ''}"></div>
          <div class="service-shell-form-group"><label>Číslo účtu</label><input type="text" name="custom_d_bankaccount" class="service-shell-input" value="${s.custom_d_bankaccount || ''}" placeholder="např. 123456789/0100"></div>
          <div class="service-shell-form-group"><label>Ulice</label><input type="text" name="custom_d_street" class="service-shell-input" value="${s.custom_d_street || ''}"></div>
          <div class="service-shell-form-group"><label>Město</label><input type="text" name="custom_d_city" class="service-shell-input" value="${s.custom_d_city || ''}"></div>
          <div class="service-shell-form-group"><label>PSČ</label><input type="text" name="custom_d_zip" class="service-shell-input" value="${s.custom_d_zip || ''}"></div>
          <div class="service-shell-form-group"><label>Stát</label><input type="text" name="custom_d_state" class="service-shell-input" value="${s.custom_d_state || ''}" placeholder="CZ"></div>
          <div class="service-shell-form-group"><label>E-mail</label><input type="email" name="custom_d_email" class="service-shell-input" value="${s.custom_d_email || ''}"></div>
          <div class="service-shell-form-group"><label>Telefon</label><input type="text" name="custom_d_phone" class="service-shell-input" value="${s.custom_d_phone || ''}"></div>
          <div class="service-shell-form-group"><label>Web</label><input type="text" name="custom_d_web" class="service-shell-input" value="${s.custom_d_web || ''}"></div>
        </div>

        <div style="margin-top: 20px; display: flex; gap: 10px;">
          <button type="submit" class="btn btn-primary">Uložit nastavení</button>
          <button type="button" class="btn btn-secondary" onclick="testFakturywebConnection()">Otestovat spojení</button>
        </div>
        ${s.last_test_at ? `<p style="margin-top: 10px; font-size: 0.9em; color: #666;">Poslední test: ${new Date(s.last_test_at).toLocaleString()}</p>` : ''}
        ${s.last_error ? `<p style="margin-top: 10px; font-size: 0.9em; color: red;">Poslední chyba: ${s.last_error}</p>` : ''}
      </form>
    `;
  } else if (state.activeTab === 'create') {
    const today = new Date().toISOString().split('T')[0];
    const due = new Date(Date.now() + 7 * 86400000).toISOString().split('T')[0];
    content = `
      <form onsubmit="createFakturywebTestInvoice(event)" class="service-shell-form">
        <h3>Odběratel</h3>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px;">
          <div class="service-shell-form-group"><label>Název/Jméno</label><input type="text" name="o_name" class="service-shell-input" required></div>
          <div class="service-shell-form-group"><label>E-mail</label><input type="email" name="o_email" class="service-shell-input"></div>
          <div class="service-shell-form-group"><label>Ulice</label><input type="text" name="o_street" class="service-shell-input"></div>
          <div class="service-shell-form-group"><label>Město</label><input type="text" name="o_city" class="service-shell-input"></div>
          <div class="service-shell-form-group"><label>PSČ</label><input type="text" name="o_zip" class="service-shell-input"></div>
          <div class="service-shell-form-group"><label>Stát</label><input type="text" name="o_state" class="service-shell-input" value="CZ"></div>
          <div class="service-shell-form-group"><label>IČO</label><input type="text" name="o_ico" class="service-shell-input"></div>
          <div class="service-shell-form-group"><label>DIČ</label><input type="text" name="o_dic" class="service-shell-input"></div>
        </div>
        
        <h3 style="margin-top: 20px;">Faktura</h3>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px;">
          <div class="service-shell-form-group"><label>Datum vystavení</label><input type="date" name="f_date_issue" class="service-shell-input" value="${today}" required></div>
          <div class="service-shell-form-group"><label>Datum dodání</label><input type="date" name="f_date_delivery" class="service-shell-input" value="${today}" required></div>
          <div class="service-shell-form-group"><label>Datum splatnosti</label><input type="date" name="f_date_due" class="service-shell-input" value="${due}" required></div>
          <div class="service-shell-form-group"><label>Typ platby</label><select name="f_payment" class="service-shell-input"><option value="prevod">Převod</option><option value="hotovost">Hotovost</option></select></div>
          <div class="service-shell-form-group"><label>Měna</label><input type="text" name="f_currency" class="service-shell-input" value="Kč" required></div>
          <div class="service-shell-form-group"><label>Šablona</label><input type="text" name="f_style" class="service-shell-input" value="styl_7" required></div>
          <div class="service-shell-form-group"><label>QR kód</label><select name="f_qr" class="service-shell-input"><option value="1">Ano</option><option value="0">Ne</option></select></div>
        </div>
        <div class="service-shell-form-group" style="margin-top: 15px;"><label>Poznámka</label><textarea name="f_note" class="service-shell-input"></textarea></div>
        <div class="service-shell-form-group"><label>Interní poznámka</label><textarea name="f_internal_note" class="service-shell-input"></textarea></div>
        
        <h3 style="margin-top: 20px;">Položky (zatím jen jedna pro test)</h3>
        <div style="display: grid; grid-template-columns: 2fr 1fr 1fr 1fr 1fr; gap: 15px;">
          <div class="service-shell-form-group"><label>Text</label><input type="text" name="p_text" class="service-shell-input" required></div>
          <div class="service-shell-form-group"><label>Množství</label><input type="number" step="0.01" name="p_quantity" class="service-shell-input" value="1" required></div>
          <div class="service-shell-form-group"><label>Jednotka</label><input type="text" name="p_unit" class="service-shell-input" value="ks"></div>
          <div class="service-shell-form-group"><label>Cena za jedn.</label><input type="number" step="0.01" name="p_price" class="service-shell-input" value="1000" required></div>
          <div class="service-shell-form-group"><label>DPH (%)</label><input type="number" step="1" name="p_vat" class="service-shell-input" placeholder="např. 21"></div>
        </div>
        
        <div style="margin-top: 20px;">
          <button type="submit" class="btn btn-primary">Vytvořit testovací fakturu</button>
        </div>
      </form>
    `;
  } else if (state.activeTab === 'list') {
    if (!state.localInvoices.length) {
      content = '<p>Zatím nebyly vytvořeny žádné testovací faktury.</p>';
    } else {
      content = `
        <table class="service-shell-table">
          <thead>
            <tr>
              <th>Datum</th>
              <th>Číslo / Kód</th>
              <th>Zákazník</th>
              <th>Částka</th>
              <th>Stav</th>
              <th>Akce</th>
            </tr>
          </thead>
          <tbody>
            ${state.localInvoices.map(inv => `
              <tr>
                <td>${inv.issue_date || '-'}</td>
                <td>${inv.fakturyweb_number || '-'}<br><small style="color:#666">${inv.fakturyweb_code}</small></td>
                <td>${inv.customer_name || '-'}</td>
                <td>${inv.amount_estimated || '-'}</td>
                <td><span class="service-shell-badge status-${inv.local_status}">${inv.local_status}</span></td>
                <td>
                  <button type="button" class="btn btn-sm btn-secondary" onclick="viewFakturywebInvoicePdf(${inv.id})">PDF</button>
                  <button type="button" class="btn btn-sm btn-secondary" onclick="checkFakturywebInvoiceStatus(${inv.id})">Status</button>
                  ${inv.local_status !== 'paid' ? `<button type="button" class="btn btn-sm btn-secondary" onclick="markFakturywebInvoicePaid(${inv.id})">Uhradit</button>` : ''}
                </td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      `;
    }
  } else if (state.activeTab === 'remote') {
    content = `
      <form onsubmit="fetchFakturywebRemoteInvoices(event)" class="service-shell-form" style="display: flex; gap: 15px; align-items: flex-end; margin-bottom: 20px;">
        <div class="service-shell-form-group">
          <label>Typ seznamu</label>
          <select name="type" class="service-shell-input">
            <option value="created">Vytvořené</option>
            <option value="issued">Vystavené</option>
            <option value="delivered">Doručené</option>
            <option value="paid">Uhrazené</option>
          </select>
        </div>
        <div class="service-shell-form-group">
          <label>Datum od</label>
          <input type="date" name="date_from" class="service-shell-input">
        </div>
        <div class="service-shell-form-group">
          <label>Datum do</label>
          <input type="date" name="date_to" class="service-shell-input">
        </div>
        <button type="submit" class="btn btn-primary">Načíst z FakturyWeb</button>
      </form>
      
      ${state.remoteInvoices ? `
        <table class="service-shell-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Číslo</th>
              <th>Zákazník</th>
              <th>Částka</th>
              <th>Stav</th>
            </tr>
          </thead>
          <tbody>
            ${state.remoteInvoices.map(inv => `
              <tr>
                <td>${inv.id}</td>
                <td>${inv.number || '-'}</td>
                <td>${inv.customer_name || '-'}</td>
                <td>${inv.total || '-'}</td>
                <td>${inv.status || '-'}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
        
        <details style="margin-top: 20px; padding: 10px; background: #f5f5f5; border-radius: 4px;">
          <summary>Zobrazit raw JSON odpověď</summary>
          <pre style="font-size: 11px; overflow-x: auto; margin-top: 10px;">${JSON.stringify(state.remoteRaw, null, 2)}</pre>
        </details>
      ` : '<p>Zatím nebyl načten žádný seznam.</p>'}
    `;
  }
  
  container.innerHTML = `
    <div style="background: #fff3cd; color: #856404; padding: 15px; border-radius: 4px; margin-bottom: 20px; border: 1px solid #ffeeba;">
      <strong>UPOZORNĚNÍ:</strong> Toto je testovací integrace FakturyWeb. Faktury se odesílají s <code>apitest=1</code> a nejsou určeny jako ostré účetní doklady.
    </div>
    
    <div class="service-shell-tabs" style="display: flex; gap: 10px; margin-bottom: 20px; border-bottom: 1px solid #ddd; padding-bottom: 10px;">
      <button type="button" class="btn ${state.activeTab === 'settings' ? 'btn-primary' : 'btn-secondary'}" onclick="switchFakturywebTab('settings')">Nastavení API</button>
      <button type="button" class="btn ${state.activeTab === 'create' ? 'btn-primary' : 'btn-secondary'}" onclick="switchFakturywebTab('create')">Vytvořit testovací fakturu</button>
      <button type="button" class="btn ${state.activeTab === 'list' ? 'btn-primary' : 'btn-secondary'}" onclick="switchFakturywebTab('list')">Lokální testovací faktury</button>
      <button type="button" class="btn ${state.activeTab === 'remote' ? 'btn-primary' : 'btn-secondary'}" onclick="switchFakturywebTab('remote')">Vzdálený seznam</button>
    </div>
    
    <div class="fakturyweb-test-content">
      ${content}
    </div>
  `;
}

window.fakturywebTestSection = function() {
  // Initialize on first render
  if (!window.fakturywebTestState.settings) {
    setTimeout(() => {
      fetchFakturywebSettings().then(renderFakturywebTest);
    }, 0);
  }
  
  return `
    <div class="service-shell-section">
      <header class="service-shell-section-header">
        <h1 class="service-shell-section-title">FakturyWeb test</h1>
      </header>
      <div id="fakturyweb-test-container" class="service-shell-section-body">
        Načítám...
      </div>
    </div>
  `;
};
