(function () {
  'use strict';

  const API_BASE = '/api/v1/user/settings';
  const PANELS = [
    { id: 'profile', label: 'Profil a účet', icon: 'user' },
    { id: 'security', label: 'Zabezpečení', icon: 'shield' },
    { id: 'license', label: 'Licence a tarif', icon: 'crown' },
    { id: 'notifications', label: 'Oznámení', icon: 'bell' },
    { id: 'garage', label: 'Vozidla a garáž', icon: 'garage' },
    { id: 'documents', label: 'Dokumenty', icon: 'folder' },
    { id: 'billing', label: 'Faktury a platby', icon: 'invoice' },
    { id: 'services-sharing', label: 'Servisy a sdílení', icon: 'building' },
    { id: 'privacy', label: 'Soukromí a data', icon: 'lock' },
    { id: 'support', label: 'Podpora', icon: 'globe' },
  ];

  const STATE = {
    panel: 'profile',
    search: '',
    loading: false,
    snapshot: null,
    security: null,
    license: null,
    billing: null,
    services: null,
    documents: null,
    modal: null,
    saveBusy: false,
    formDraft: {},
  };

  function esc(v) {
    if (typeof window.escapeHtml === 'function') return window.escapeHtml(v == null ? '' : String(v));
    return String(v == null ? '' : v).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function hasFn(n) { return typeof window[n] === 'function'; }

  function showMsg(msg, type) {
    if (hasFn('showAlert')) window.showAlert(msg, type || 'info');
    else alert(msg);
  }

  async function api(url, method, body) {
    if (!hasFn('apiCall')) throw new Error('API není dostupné');
    return apiCall(url, method || 'GET', body == null ? null : body);
  }

  function fmtDate(iso) {
    if (!iso) return '—';
    try {
      const d = new Date(iso);
      return d.toLocaleDateString('cs-CZ', { day: 'numeric', month: 'numeric', year: 'numeric' });
    } catch (_) { return '—'; }
  }

  function fmtDateTime(iso) {
    if (!iso) return '—';
    try {
      const d = new Date(iso);
      return d.toLocaleString('cs-CZ', { day: 'numeric', month: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' });
    } catch (_) { return '—'; }
  }

  function trialBadge(snapshot) {
    const lic = snapshot && snapshot.license;
    if (!lic) return '';
    if (lic.trial_active && lic.trial_days_remaining != null) {
      return `<span class="uapp-settings-trial-badge">Trial ${esc(String(lic.trial_days_remaining))} dní</span>`;
    }
    return '';
  }

  function progressBar(current, limit) {
    const cur = Number(current) || 0;
    const lim = Number(limit);
    const pct = !lim || lim <= 0 ? Math.min(cur > 0 ? 100 : 8, 100) : Math.min(100, Math.round((cur / lim) * 100));
    return `<div class="uapp-settings-progress"><div class="uapp-settings-progress-bar" style="width:${pct}%"></div></div>`;
  }

  function toggleHtml(checked, disabled) {
    return `<button type="button" class="uapp-settings-toggle${checked ? ' is-on' : ''}${disabled ? ' is-disabled' : ''}" ${disabled ? 'disabled' : ''} role="switch" aria-checked="${checked ? 'true' : 'false'}"><span class="uapp-settings-toggle-knob"></span></button>`;
  }

  function badge(text, tone) {
    return `<span class="uapp-settings-badge is-${tone || 'neutral'}">${esc(text)}</span>`;
  }

  function quickAction(label, action, opts) {
    const o = opts || {};
    return `<button type="button" class="uapp-settings-quick-action${o.danger ? ' is-danger' : ''}" data-uapp-settings-action="${esc(action)}"><span>${esc(label)}</span><span aria-hidden="true">›</span></button>`;
  }

  function filteredCategories() {
    const q = String(STATE.search || '').trim().toLowerCase();
    if (!q) return PANELS;
    return PANELS.filter((p) => p.label.toLowerCase().includes(q));
  }

  function panelMeta(id) {
    return PANELS.find((p) => p.id === id) || PANELS[0];
  }

  async function loadSnapshot(force) {
    if (STATE.snapshot && !force) return STATE.snapshot;
    STATE.loading = true;
    try {
      STATE.snapshot = await api(API_BASE);
      return STATE.snapshot;
    } finally {
      STATE.loading = false;
    }
  }

  async function loadPanelData(panel) {
    if (panel === 'security') {
      STATE.security = await api(`${API_BASE}/security`);
    } else if (panel === 'license') {
      STATE.license = await api(`${API_BASE}/license`);
    } else if (panel === 'billing') {
      STATE.billing = await api(`${API_BASE}/billing`);
    } else if (panel === 'services-sharing') {
      STATE.services = await api(`${API_BASE}/services-sharing`);
    } else if (panel === 'documents') {
      STATE.documents = await api(`${API_BASE}/documents/summary`);
    }
  }

  function renderTopbar(snapshot) {
    const u = snapshot && snapshot.profile;
    const name = (u && u.name) ? u.name.split(' ').map((p) => p[0]).join('').slice(0, 2).toUpperCase() : 'U';
    const count = '3';
    return `
      <header class="uapp-settings-topbar">
        <div class="uapp-settings-topbar-left">
          <span class="uapp-settings-topbar-icon" aria-hidden="true">⚙</span>
          <div>
            <h1 class="uapp-settings-topbar-title">Nastavení</h1>
            <p class="uapp-settings-topbar-sub">Správa účtu, zabezpečení, oznámení a předvoleb aplikace</p>
          </div>
        </div>
        <label class="uapp-settings-search">
          <span aria-hidden="true">🔍</span>
          <input type="search" placeholder="Hledat v nastavení…" value="${esc(STATE.search)}" data-uapp-settings-field="search">
        </label>
        <div class="uapp-settings-topbar-actions">
          <button type="button" class="uapp-settings-notify-btn" data-uapp-action="notifications" aria-label="Oznámení"><span>${count}</span>🔔</button>
          <button type="button" class="uapp-settings-profile-btn" data-uapp-action="profile">
            <span class="uapp-settings-avatar">${esc(name)}</span>
            <span class="uapp-settings-profile-meta">
              <strong>${esc((u && u.name) || 'Uživatel')}</strong>
              ${trialBadge(snapshot)}
            </span>
            <span aria-hidden="true">▾</span>
          </button>
        </div>
      </header>`;
  }

  function renderCategoryNav() {
    const cats = filteredCategories();
    return `
      <nav class="uapp-settings-categories" aria-label="Kategorie nastavení">
        <h2 class="uapp-settings-categories-title">Kategorie nastavení</h2>
        <div class="uapp-settings-categories-list">
          ${cats.map((c) => `
            <button type="button" class="uapp-settings-category${STATE.panel === c.id ? ' is-active' : ''}" data-uapp-settings-action="panel:${c.id}">
              <span class="uapp-settings-category-ico" data-ico="${esc(c.icon)}" aria-hidden="true"></span>
              <span>${esc(c.label)}</span>
            </button>`).join('')}
        </div>
      </nav>`;
  }

  function renderAside(panel, snapshot) {
    const usage = (snapshot && snapshot.usage) || {};
    const lic = (snapshot && snapshot.license) || {};
    if (panel === 'profile') {
      return `
        <aside class="uapp-settings-aside">
          <div class="uapp-settings-aside-card">
            <h3>Stav účtu</h3>
            <div class="uapp-settings-status-ok">Aktivní účet — Vše funguje správně</div>
            <ul class="uapp-settings-aside-list">
              <li><span>Trial verze</span><strong>${lic.trial_active ? esc(String(lic.trial_days_remaining)) + ' dní zbývá' : '—'}</strong></li>
              <li><span>Využití garáže</span><strong>${esc(String(usage.vehicles_count || 0))} / ${lic.is_unlimited ? '∞' : esc(String(lic.vehicles_limit || '—'))}</strong></li>
              <li><span>Dokumenty</span><strong>${esc(String(usage.documents_count || 0))} položek</strong></li>
              <li><span>Připomínky</span><strong>${esc(String(usage.reminders_active || 0))} aktivní</strong></li>
              <li><span>Zabezpečení</span><strong class="is-green">V pořádku</strong></li>
            </ul>
          </div>
          <div class="uapp-settings-aside-card">
            <h3>Rychlé akce</h3>
            ${quickAction('Změnit heslo', 'modal:password')}
            ${quickAction('Nastavit dvoufázové ověření', 'modal:2fa')}
            ${quickAction('Exportovat moje data', 'export-data')}
            ${quickAction('Odhlásit všechna zařízení', 'modal:logout-all')}
            ${quickAction('Smazat účet', 'modal:delete-account', { danger: true })}
          </div>
        </aside>`;
    }
    if (panel === 'security') {
      return `
        <aside class="uapp-settings-aside">
          <div class="uapp-settings-aside-card uapp-settings-aside-card--center">
            <div class="uapp-settings-shield-ok" aria-hidden="true">✓</div>
            <h3>Stav zabezpečení</h3>
            <p>Váš účet je zabezpečený. Doporučené kroky jsou splněny.</p>
            <ul class="uapp-settings-checklist">
              <li>Silné heslo</li>
              <li>Dvoufázové ověření <small>(doporučeno)</small></li>
              <li>Ověřený e-mail</li>
              <li>Aktivní zařízení zkontrolována</li>
              <li>Bezpečnostní e-maily zapnuty</li>
            </ul>
          </div>
          <div class="uapp-settings-aside-card">
            <h3>Rychlé akce</h3>
            ${quickAction('Změnit heslo', 'modal:password')}
            ${quickAction('Nastavit dvoufázové ověření', 'modal:2fa')}
            ${quickAction('Odhlásit všechna zařízení', 'modal:logout-all')}
            ${quickAction('Zobrazit historii přihlášení', 'modal:login-history')}
            ${quickAction('Zrušit účet', 'modal:delete-account', { danger: true })}
          </div>
        </aside>`;
    }
    if (panel === 'license') {
      const days = lic.trial_days_remaining != null ? lic.trial_days_remaining : '—';
      return `
        <aside class="uapp-settings-aside">
          <div class="uapp-settings-aside-card uapp-settings-aside-card--center">
            <div class="uapp-settings-gauge">${esc(String(days))}</div>
            <p>Trial verze ${badge(String(days) + ' dní zbývá', 'warn')}</p>
            <p class="uapp-settings-muted">Po skončení zkušební doby si vyberte tarif a pokračujte bez omezení.</p>
            <button type="button" class="uapp-settings-btn uapp-settings-btn-primary" data-uapp-settings-action="open-license">Vybrat tarif</button>
          </div>
          <div class="uapp-settings-aside-card">
            <h3>Co získáte s placenými tarify</h3>
            <ul class="uapp-settings-checklist">
              <li>Více vozidel v garáži</li><li>Neomezené dokumenty</li><li>Pokročilé připomínky</li>
              <li>Export dat a reporty</li><li>Sdílení se servisy</li><li>Prioritní podpora</li>
            </ul>
          </div>
          <div class="uapp-settings-aside-card">
            <h3>Fakturace a platby</h3>
            <p class="uapp-settings-row"><span>Platební metoda</span><button type="button" class="uapp-settings-link" data-uapp-settings-action="panel:billing">Přidat</button></p>
            <p class="uapp-settings-row"><span>Fakturační údaje</span><button type="button" class="uapp-settings-link" data-uapp-settings-action="panel:billing">Upravit</button></p>
            <p class="uapp-settings-row"><span>Historie plateb</span><button type="button" class="uapp-settings-link" data-uapp-settings-action="panel:billing">Zobrazit</button></p>
          </div>
        </aside>`;
    }
    if (panel === 'notifications') {
      return `
        <aside class="uapp-settings-aside">
          <div class="uapp-settings-aside-card">
            <h3>Souhrn vašeho nastavení</h3>
            <ul class="uapp-settings-aside-list">
              <li><span>E-mail</span><strong class="is-green">Aktivní</strong></li>
              <li><span>SMS</span><strong class="is-orange">Neověřeno</strong></li>
              <li><span>Push oznámení</span><strong class="is-green">Aktivní</strong></li>
            </ul>
            <button type="button" class="uapp-settings-link" data-uapp-settings-action="scroll:channels">Upravit kanály oznámení</button>
          </div>
          <div class="uapp-settings-aside-card">
            <h3>Náhled oznámení</h3>
            <div class="uapp-settings-preview-item"><strong>Připomínka servisu</strong><span>Dnes 9:00</span></div>
            <div class="uapp-settings-preview-item"><strong>Nový dokument</strong><span>Včera</span></div>
            <div class="uapp-settings-preview-item"><strong>Bezpečnost</strong><span>Před 3 dny</span></div>
          </div>
          <div class="uapp-settings-aside-card uapp-settings-tip">
            <strong>💡 Doporučení</strong>
            <p>Doporučujeme mít aktivní e-mail a push oznámení.</p>
          </div>
        </aside>`;
    }
    if (panel === 'garage') {
      const lim = lic.is_unlimited ? null : Number(lic.vehicles_limit || 0);
      const rem = lim != null ? Math.max(0, lim - Number(usage.vehicles_count || 0)) : null;
      return `
        <aside class="uapp-settings-aside">
          <div class="uapp-settings-aside-card uapp-settings-aside-card--center">
            <div class="uapp-settings-gauge">${esc(String(usage.vehicles_count || 0))}/${lim == null ? '∞' : esc(String(lim))}</div>
            <p>${rem != null ? `Máte ještě ${rem} volných míst` : 'Neomezená garáž'}</p>
            <button type="button" class="uapp-settings-link" data-uapp-settings-action="open-license">Zvýšit limit garáže</button>
          </div>
          <div class="uapp-settings-aside-card">
            <h3>Rychlé akce</h3>
            ${quickAction('Přidat vozidlo', 'add-vehicle')}
            ${quickAction('Importovat vozidlo', 'nav:vehicles')}
            ${quickAction('Skrýt vozidlo', 'nav:vehicles')}
            ${quickAction('Změnit pořadí vozidel', 'nav:vehicles')}
            ${quickAction('Smazat vozidlo', 'nav:vehicles', { danger: true })}
          </div>
        </aside>`;
    }
    if (panel === 'documents') {
      return `
        <aside class="uapp-settings-aside">
          <div class="uapp-settings-aside-card uapp-settings-aside-card--center">
            <div class="uapp-settings-gauge">${esc(String(usage.documents_count || 0))}</div>
            <p>dokumentů celkem</p>
          </div>
          <div class="uapp-settings-aside-card">
            <h3>Rychlé akce</h3>
            ${quickAction('Nahrát dokument', 'upload-document')}
            ${quickAction('Vytvořit složku', 'nav:documents')}
            ${quickAction('Spravovat kategorie', 'nav:documents')}
            ${quickAction('Vyčistit nevyužité soubory', 'nav:documents')}
            ${quickAction('Zobrazit koš', 'nav:documents')}
          </div>
        </aside>`;
    }
    if (panel === 'billing') {
      return `
        <aside class="uapp-settings-aside">
          <div class="uapp-settings-aside-card">
            <h3>Přehled fakturace</h3>
            <ul class="uapp-settings-aside-list">
              <li><span>Aktuální tarif</span><strong>${esc(String(lic.plan_public_label || lic.effective_plan || '—'))}</strong></li>
              <li><span>Další platba</span><strong>${fmtDate(lic.trial_ends_at)}</strong></li>
            </ul>
          </div>
          <div class="uapp-settings-aside-card">
            <h3>Rychlé akce</h3>
            ${quickAction('Změnit tarif', 'open-license')}
            ${quickAction('Upravit fakturační údaje', 'edit-billing-profile')}
            ${quickAction('Změnit platební metodu', 'open-license')}
            ${quickAction('Stáhnout poslední fakturu', 'download-invoice')}
            ${quickAction('Zrušit předplatné', 'modal:cancel-subscription', { danger: true })}
          </div>
        </aside>`;
    }
    if (panel === 'services-sharing') {
      const sum = (STATE.services && STATE.services.summary) || {};
      return `
        <aside class="uapp-settings-aside">
          <div class="uapp-settings-aside-card uapp-settings-aside-card--center">
            <div class="uapp-settings-gauge">${esc(String(sum.favorites_count || 0))}</div>
            <p>oblíbené servisy</p>
            <ul class="uapp-settings-aside-list">
              <li><span>Sdílená vozidla</span><strong class="is-green">${esc(String(sum.active_shares || 0))} aktivní</strong></li>
              <li><span>Žádosti o přístup</span><strong class="is-orange">${esc(String(sum.pending_requests || 0))} čeká</strong></li>
            </ul>
          </div>
          <div class="uapp-settings-aside-card">
            <h3>Rychlé akce</h3>
            ${quickAction('Přidat servis', 'nav:servicesDirectory')}
            ${quickAction('Sdílet vozidlo se servisem', 'modal:share-service')}
            ${quickAction('Zobrazit pozvánky', 'nav:servicesDirectory')}
            ${quickAction('Odebrat všechny přístupy', 'modal:revoke-all-services', { danger: true })}
          </div>
          <div class="uapp-settings-aside-card uapp-settings-tip"><p>Sdílení vozidel se servisy umožňuje rychlejší servisní péči.</p></div>
        </aside>`;
    }
    if (panel === 'privacy') {
      return `
        <aside class="uapp-settings-aside">
          <div class="uapp-settings-aside-card uapp-settings-aside-card--center">
            <div class="uapp-settings-shield-ok">✓</div>
            <h3>Vaše data jsou v bezpečí.</h3>
            <ul class="uapp-settings-checklist"><li>Vaše data neprodáváme</li><li>Šifrované přenosy</li><li>Máte kontrolu nad údaji</li></ul>
          </div>
          <div class="uapp-settings-aside-card">
            <h3>Rychlé akce</h3>
            ${quickAction('Stáhnout moje data', 'export-data')}
            ${quickAction('Odstranit účet', 'modal:delete-account', { danger: true })}
          </div>
        </aside>`;
    }
    if (panel === 'support') {
      return `
        <aside class="uapp-settings-aside">
          <div class="uapp-settings-aside-card">
            <h3>Rychlý přehled</h3>
            <p>Jsme tu, abychom vám pomohli.</p>
            <ul class="uapp-settings-aside-list">
              <li><span>Průměrná doba odpovědi</span><strong>do 4 hodin</strong></li>
              <li><span>Dostupnost</span><strong>Po–Pá 8:00–18:00</strong></li>
              <li><span>Jazyk podpory</span><strong>Čeština</strong></li>
            </ul>
          </div>
          <div class="uapp-settings-aside-card">
            <h3>Rychlé akce</h3>
            ${quickAction('Napsat e-mail', 'mailto:support')}
            ${quickAction('Spustit online chat', 'chat-disabled')}
            ${quickAction('Odeslat zpětnou vazbu', 'modal:feedback')}
          </div>
        </aside>`;
    }
    return '';
  }

  function renderPanelProfile(snapshot) {
    const p = (snapshot && snapshot.profile) || {};
    const prefs = (snapshot && snapshot.preferences) || {};
    return `
      <div class="uapp-settings-panel-head"><span class="uapp-settings-panel-ico">👤</span><div><h2>Profil a účet</h2><p>Spravujte své osobní údaje a nastavení účtu</p></div></div>
      <section class="uapp-settings-card">
        <h3>Osobní údaje</h3>
        <div class="uapp-settings-grid-2">
          <label>Jméno a příjmení<input data-uapp-settings-field="name" value="${esc(p.name || '')}"></label>
          <label>E-mail<input disabled value="${esc(p.email_masked || '')}"><small>E-mail nelze změnit bez ověření</small></label>
          <label>Telefon<input data-uapp-settings-field="phone" value="${esc(STATE.formDraft.phone || '')}" placeholder="+420 …"></label>
          <label>Preferovaný jazyk<select data-uapp-settings-field="preferred_language"><option value="cs"${prefs.preferred_language === 'cs' ? ' selected' : ''}>Čeština</option></select></label>
        </div>
        <label class="uapp-settings-full">Adresa<input data-uapp-settings-field="address_display" disabled value="${esc(p.address || '')}"></label>
        <div class="uapp-settings-card-actions"><button type="button" class="uapp-settings-btn uapp-settings-btn-primary" data-uapp-settings-action="save-profile">Uložit změny</button></div>
      </section>
      <section class="uapp-settings-card">
        <h3>Kontaktní údaje</h3>
        <div class="uapp-settings-row-line"><div><strong>Primární e-mail</strong><span>${esc(p.email_masked || '')}</span></div>${badge('Ověřeno', 'green')}</div>
        <div class="uapp-settings-row-line"><div><strong>Telefonní číslo</strong><span>${esc(p.phone_masked || '')}</span></div><button type="button" class="uapp-settings-link" data-uapp-settings-action="modal:verify-phone">Ověřit</button></div>
        <label>Preferovaný kontakt<select data-uapp-settings-field="preferred_contact"><option value="email">E-mail</option><option value="phone">Telefon</option><option value="sms">SMS</option></select></label>
      </section>
      <section class="uapp-settings-card">
        <h3>Účet</h3>
        <div class="uapp-settings-info-grid">
          <div><span>Typ účtu</span><strong>${esc(p.account_type || 'Osobní účet')}</strong></div>
          <div><span>Role</span><strong>${esc(p.role_label || 'Uživatel')}</strong></div>
          <div><span>Stav účtu</span>${badge('Aktivní', 'green')}</div>
          <div><span>Datum registrace</span><strong>${fmtDate(p.registered_at)}</strong></div>
          <div><span>Poslední přihlášení</span><strong>${fmtDateTime(p.last_login_at)}</strong></div>
        </div>
      </section>`;
  }

  function renderPanelSecurity() {
    const sec = STATE.security || {};
    const devices = sec.devices || [];
    return `
      <div class="uapp-settings-panel-head"><span class="uapp-settings-panel-ico">🛡</span><div><h2>Zabezpečení</h2><p>Spravujte zabezpečení účtu a chraňte svá data</p></div></div>
      <section class="uapp-settings-card"><h3>Heslo</h3><p>Stav hesla: <strong>${esc(sec.password_strength || 'Silné')}</strong></p><button type="button" class="uapp-settings-btn" data-uapp-settings-action="modal:password">Změnit heslo</button></section>
      <section class="uapp-settings-card"><h3>Dvoufázové ověření (2FA)</h3><p>Stav 2FA: <strong>${sec.two_factor_enabled ? 'Zapnuto' : 'Vypnuto'}</strong></p><button type="button" class="uapp-settings-btn" data-uapp-settings-action="modal:2fa">Nastavit 2FA</button></section>
      <section class="uapp-settings-card"><h3>Přihlášená zařízení</h3>
        ${devices.length ? devices.map((d) => `
          <div class="uapp-settings-device">
            <div><strong>${esc(d.os)} • ${esc(d.browser)}</strong><span>${esc(d.location)} • ${fmtDateTime(d.last_active_at)} ${d.is_current ? badge('Aktuální', 'green') : ''}</span></div>
            ${d.is_current ? '' : '<button type="button" class="uapp-settings-btn uapp-settings-btn-ghost" disabled title="Vyžaduje správu relací">Odhlásit</button>'}
          </div>`).join('') : '<p class="uapp-settings-muted">Žádná zařízení k zobrazení.</p>'}
        <button type="button" class="uapp-settings-link" data-uapp-settings-action="modal:login-history">Zobrazit všechna zařízení (${esc(String(sec.devices_total || devices.length))})</button>
      </section>
      <section class="uapp-settings-card"><h3>Bezpečnostní e-maily</h3><p>E-maily o přihlášení: <strong class="is-green">Zapnuto</strong></p><p>E-maily o změnách účtu: <strong class="is-green">Zapnuto</strong></p></section>`;
  }

  function renderPanelLicense() {
    const lic = (STATE.license && STATE.license.license) || (STATE.snapshot && STATE.snapshot.license) || {};
    const usage = (STATE.license && STATE.license.usage) || (STATE.snapshot && STATE.snapshot.usage) || {};
    const cg = (STATE.license && STATE.license.comgate) || {};
    const plans = cg.plans || {};
    const planKey = String(lic.effective_plan || lic.plan || 'free').toLowerCase();
    return `
      <div class="uapp-settings-panel-head"><span class="uapp-settings-panel-ico">👑</span><div><h2>Licence a tarif</h2><p>Spravujte svou licenci, tarif a využití funkcí aplikace</p></div></div>
      <section class="uapp-settings-card">
        <h3>Váš aktuální tarif</h3>
        <p><strong>${esc(String(lic.plan_public_label || planKey))}</strong> ${lic.trial_active ? badge(String(lic.trial_days_remaining) + ' dní zbývá', 'warn') : ''}</p>
        <p class="uapp-settings-muted">Zkušební / tarifní období dle vašeho účtu.</p>
        <button type="button" class="uapp-settings-btn uapp-settings-btn-primary" data-uapp-settings-action="open-license">${planKey === 'free' || lic.trial_active ? 'Vybrat tarif' : 'Změnit tarif'}</button>
        <div class="uapp-settings-meta-row"><span>Aktivováno: ${fmtDate(lic.trial_started_at || lic.valid_to)}</span><span>Konec trial: ${fmtDate(lic.trial_ends_at)}</span></div>
      </section>
      <section class="uapp-settings-card"><h3>Využití vašeho účtu</h3>
        <p>Vozidla v garáži: ${esc(String(usage.vehicles_count || 0))} / ${lic.is_unlimited ? '∞' : esc(String(lic.vehicles_limit || '—'))}${progressBar(usage.vehicles_count, lic.vehicles_limit)}</p>
        <p>Dokumenty: ${esc(String(usage.documents_count || 0))} položek</p>
        <p>Připomínky: ${esc(String(usage.reminders_active || 0))} aktivních</p>
      </section>
      <section class="uapp-settings-card"><h3>Dostupné tarify</h3>
        <div class="uapp-settings-plans">
          ${['free', 'basic', 'premium'].map((pk) => {
            const price = plans[pk] && plans[pk].monthly ? Math.round(plans[pk].monthly / 100) : (pk === 'free' ? 0 : pk === 'basic' ? 99 : 299);
            const active = planKey === pk || (pk === 'premium' && planKey === 'premium_trial');
            return `<div class="uapp-settings-plan${active ? ' is-active' : ''}"><h4>${pk === 'free' ? 'Free' : pk === 'basic' ? 'Basic' : 'Premium'}</h4><p>${price} Kč / měsíc</p><button type="button" class="uapp-settings-btn${active ? ' is-outline-green' : ''}" data-uapp-settings-action="open-license" ${!cg.enabled && pk !== 'free' ? 'disabled title="Platby nejsou aktivní"' : ''}>${active ? 'Aktivní tarif' : 'Zvolit ' + (pk === 'basic' ? 'Basic' : 'Premium')}</button></div>`;
          }).join('')}
        </div>
      </section>`;
  }

  function renderPanelNotifications(snapshot) {
    const prefs = (snapshot && snapshot.preferences && snapshot.preferences.notifications) || {};
    const channels = prefs.channels || {};
    const types = prefs.types || {};
    const typeRows = [
      ['service_reminders', 'Připomínky servisu a údržby'],
      ['documents', 'Dokumenty'],
      ['news', 'Novinky a aktuality'],
      ['security', 'Bezpečnost účtu'],
      ['marketing', 'Marketingové nabídky'],
    ];
    return `
      <div class="uapp-settings-panel-head"><span class="uapp-settings-panel-ico">🔔</span><div><h2>Oznámení</h2><p>Spravujte kanály a typy oznámení</p></div></div>
      <section class="uapp-settings-card"><h3>Obecná nastavení oznámení</h3>
        <div class="uapp-settings-row-line"><span>Hlavní přepínač</span>${toggleHtml(prefs.master !== false)}</div>
        <label>Tichý režim<select data-uapp-settings-field="quiet_mode"><option value="off">Vypnuto</option><option value="1h">1 hodina</option><option value="today">Dnes</option></select></label>
      </section>
      <section class="uapp-settings-card" id="uappSettingsChannels"><h3>Kanály oznámení</h3>
        <div class="uapp-settings-row-line"><div><strong>E-mail</strong><span>${esc((snapshot.profile && snapshot.profile.email_masked) || '')}</span></div>${toggleHtml(channels.email !== false)}</div>
        <div class="uapp-settings-row-line"><div><strong>SMS</strong><span>${esc((snapshot.profile && snapshot.profile.phone_masked) || '')}</span></div>${badge('Neověřeno', 'orange')}</div>
        <div class="uapp-settings-row-line"><div><strong>Push oznámení</strong></div>${toggleHtml(channels.push !== false)}</div>
      </section>
      <section class="uapp-settings-card"><h3>Typy oznámení</h3>
        <table class="uapp-settings-matrix"><thead><tr><th>Typ</th><th>E-mail</th><th>SMS</th><th>Push</th></tr></thead><tbody>
          ${typeRows.map(([key, label]) => {
            const row = types[key] || {};
            return `<tr><td>${esc(label)}</td><td><input type="checkbox" data-notify-type="${key}:email" ${row.email !== false ? 'checked' : ''}></td><td><input type="checkbox" data-notify-type="${key}:sms" ${row.sms ? 'checked' : ''}></td><td><input type="checkbox" data-notify-type="${key}:push" ${row.push !== false ? 'checked' : ''}></td></tr>`;
          }).join('')}
        </tbody></table>
        <button type="button" class="uapp-settings-btn uapp-settings-btn-primary" data-uapp-settings-action="save-notifications">Uložit nastavení</button>
      </section>`;
  }

  function renderPanelGarage(snapshot) {
    const lic = (snapshot && snapshot.license) || {};
    const usage = (snapshot && snapshot.usage) || {};
    const prefs = (snapshot && snapshot.preferences && snapshot.preferences.garage) || {};
    return `
      <div class="uapp-settings-panel-head"><span class="uapp-settings-panel-ico">🚗</span><div><h2>Vozidla a garáž</h2><p>Spravujte garáž, limity a výchozí nastavení</p></div></div>
      <div class="uapp-settings-mini-stats">
        <div><span>Vozidla</span><strong>${esc(String(usage.vehicles_count || 0))} / ${lic.is_unlimited ? '∞' : esc(String(lic.vehicles_limit || '—'))}</strong></div>
        <div><span>Dokumenty</span><strong>${esc(String(usage.documents_count || 0))}</strong></div>
        <div><span>Připomínky</span><strong>${esc(String(usage.reminders_active || 0))}</strong></div>
      </div>
      <section class="uapp-settings-card"><h3>Limity garáže</h3><p>Maximální počet vozidel dle tarifu.</p>${progressBar(usage.vehicles_count, lic.vehicles_limit)}<button type="button" class="uapp-settings-link" data-uapp-settings-action="open-license">Zvýšit limit</button></section>
      <section class="uapp-settings-card"><h3>Výchozí nastavení vozidel</h3>
        <label>Jednotky<select data-uapp-settings-field="default_units"><option value="metric">Metrické (km, °C, l)</option></select></label>
        <label>Měna<select data-uapp-settings-field="default_currency"><option value="CZK">CZK – Kč</option></select></label>
        <div class="uapp-settings-row-line"><span>Automatická aktualizace dat vozidel (MDČR)</span>${toggleHtml(prefs.mdcr_auto_update !== false)}</div>
        <button type="button" class="uapp-settings-btn" data-uapp-settings-action="save-garage">Uložit</button>
      </section>
      <section class="uapp-settings-card"><h3>Sdílení vozidel</h3><button type="button" class="uapp-settings-btn" data-uapp-settings-action="panel:services-sharing">Spravovat sdílení</button></section>
      <section class="uapp-settings-card"><h3>Odstranění vozidla</h3><button type="button" class="uapp-settings-btn is-danger-outline" data-uapp-settings-action="nav:vehicles">Spravovat vozidla</button></section>`;
  }

  function renderPanelDocuments() {
    const doc = STATE.documents || {};
    const prefs = doc.preferences || {};
    return `
      <div class="uapp-settings-panel-head"><span class="uapp-settings-panel-ico">📁</span><div><h2>Dokumenty</h2><p>Nastavení úložiště a organizace dokumentů</p></div></div>
      <section class="uapp-settings-card"><h3>Nastavení úložiště</h3><p>Maximální velikost souboru: <strong>25 MB</strong></p><p>Celkem dokumentů: <strong>${esc(String(doc.total || 0))}</strong></p><button type="button" class="uapp-settings-link" data-uapp-settings-action="nav:documents">Spravovat úložiště</button></section>
      <section class="uapp-settings-card"><h3>Organizace dokumentů</h3>
        <div class="uapp-settings-row-line"><span>Automatické řazení</span>${toggleHtml(prefs.auto_sort !== false)}</div>
        <div class="uapp-settings-row-line"><span>Pojmenování souborů</span>${toggleHtml(prefs.smart_naming !== false)}</div>
        <button type="button" class="uapp-settings-btn" data-uapp-settings-action="save-documents">Uložit</button>
      </section>
      <section class="uapp-settings-card"><h3>Zálohování a bezpečnost</h3><p>Pravidelné zálohování: <strong class="is-green">Aktivní</strong></p><p>Skenování malware: <strong class="is-green">Aktivní</strong> <small>(status)</small></p></section>`;
  }

  function renderPanelBilling() {
    const bill = STATE.billing || {};
    const lic = bill.license || {};
    const inv = bill.invoices || [];
    const pm = bill.payment_method || {};
    return `
      <div class="uapp-settings-panel-head"><span class="uapp-settings-panel-ico">💳</span><div><h2>Faktury a platby</h2><p>Fakturace licence a platební metody</p></div></div>
      <section class="uapp-settings-card"><h3>Aktuální tarif</h3><p>${esc(String(lic.plan_public_label || lic.effective_plan || 'Trial'))} ${lic.trial_active ? badge(String(lic.trial_days_remaining) + ' dní', 'warn') : ''}</p><button type="button" class="uapp-settings-btn uapp-settings-btn-primary" data-uapp-settings-action="open-license">Změnit tarif</button></section>
      <section class="uapp-settings-card"><h3>Fakturační údaje</h3><p>${esc((bill.billing_profile && bill.billing_profile.name) || '—')}</p><p>${esc((bill.billing_profile && bill.billing_profile.email) || '')}</p><button type="button" class="uapp-settings-link" data-uapp-settings-action="edit-billing-profile">Upravit</button></section>
      <section class="uapp-settings-card"><h3>Historie faktur</h3>
        ${inv.length ? `<table class="uapp-settings-table"><thead><tr><th>Číslo</th><th>Datum</th><th>Částka</th><th>Stav</th></tr></thead><tbody>${inv.slice(0, 5).map((r) => `<tr><td>${esc(r.invoice_number)}</td><td>${fmtDate(r.issued_at)}</td><td>${esc(String(r.amount_czk))} Kč</td><td>${esc(r.status)}</td></tr>`).join('')}</tbody></table>` : '<p class="uapp-settings-muted">Žádné platby zatím nejsou k dispozici.</p>'}
      </section>
      <section class="uapp-settings-card"><h3>Platební metoda</h3><p>${pm.configured ? 'Karta ' + esc(pm.masked || '****') : 'Není nastavena'}</p><button type="button" class="uapp-settings-link" data-uapp-settings-action="open-license">${pm.configured ? 'Upravit' : 'Přidat platební metodu'}</button></section>`;
  }

  function renderPanelServices() {
    const data = STATE.services || {};
    const fav = data.favorites || [];
    const sharing = data.sharing || [];
    return `
      <div class="uapp-settings-panel-head"><span class="uapp-settings-panel-ico">🔧</span><div><h2>Servisy a sdílení</h2><p>Oblíbené servisy a sdílení vozidel</p></div></div>
      <section class="uapp-settings-card"><div class="uapp-settings-card-head-row"><h3>Oblíbené servisy</h3><button type="button" class="uapp-settings-btn" data-uapp-settings-action="nav:servicesDirectory">Přidat servis</button></div>
        ${fav.length ? fav.map((s) => `<div class="uapp-settings-service-row"><div><strong>${esc(s.name)}</strong><span>${esc(s.city || '')}, ${esc(s.country || '')}</span></div><button type="button" class="uapp-settings-link" data-uapp-settings-action="nav:servicesDirectory">Nastavení</button></div>`).join('') : '<p class="uapp-settings-muted">Zatím nemáte oblíbené servisy.</p>'}
      </section>
      <section class="uapp-settings-card"><div class="uapp-settings-card-head-row"><h3>Sdílení vozidel se servisy</h3><button type="button" class="uapp-settings-btn" data-uapp-settings-action="modal:share-service">Sdílet vozidlo</button></div>
        ${sharing.length ? `<table class="uapp-settings-table"><thead><tr><th>Servis</th><th>Vozidlo</th><th>Přístup</th><th>Stav</th></tr></thead><tbody>${sharing.map((r) => `<tr><td>${esc(r.service_name)}</td><td>${esc(r.vehicle_name)}</td><td>${esc(r.access_level)}</td><td>${esc(r.status)}</td></tr>`).join('')}</tbody></table>` : '<p class="uapp-settings-muted">Žádné sdílení.</p>'}
      </section>
      <section class="uapp-settings-card"><h3>Komunikace se servisy</h3>
        <div class="uapp-settings-row-line"><span>Povolit servisům přístup k vozidlům</span>${toggleHtml((data.communication && data.communication.allow_vehicle_access) !== false)}</div>
        <div class="uapp-settings-row-line"><span>Povolit komunikaci se servisy</span>${toggleHtml((data.communication && data.communication.allow_communication) !== false)}</div>
        <button type="button" class="uapp-settings-btn" data-uapp-settings-action="save-services">Uložit</button>
      </section>`;
  }

  function renderPanelPrivacy(snapshot) {
    const priv = (snapshot && snapshot.preferences && snapshot.preferences.privacy) || {};
    return `
      <div class="uapp-settings-panel-head"><span class="uapp-settings-panel-ico">🔒</span><div><h2>Soukromí a data</h2><p>Spravujte soukromí, data a oprávnění</p></div></div>
      <section class="uapp-settings-card"><h3>Oprávnění aplikace</h3>
        <div class="uapp-settings-row-line"><span>Přístup k poloze</span>${badge('Povoleno', 'green')}</div>
        <div class="uapp-settings-row-line"><span>Přístup k fotoaparátu</span>${badge('Povoleno', 'green')}</div>
        <div class="uapp-settings-row-line"><span>Oznámení</span>${badge('Povoleno', 'green')}</div>
      </section>
      <section class="uapp-settings-card"><h3>Ochrana osobních údajů</h3>
        <div class="uapp-settings-row-line"><span>Sdílení dat s třetími stranami</span>${badge(priv.third_party ? 'Povoleno' : 'Zakázáno', priv.third_party ? 'green' : 'red')}</div>
        <div class="uapp-settings-row-line"><span>Personalizace</span>${badge(priv.personalization !== false ? 'Povoleno' : 'Zakázáno', 'green')}</div>
        <div class="uapp-settings-row-line"><span>Marketingová oznámení</span>${badge(priv.marketing ? 'Povoleno' : 'Zakázáno', priv.marketing ? 'green' : 'red')}</div>
        <button type="button" class="uapp-settings-btn" data-uapp-settings-action="save-privacy">Uložit</button>
      </section>
      <section class="uapp-settings-card"><h3>Správa a export dat</h3>
        <button type="button" class="uapp-settings-btn" data-uapp-settings-action="export-data">Exportovat data</button>
        <button type="button" class="uapp-settings-btn is-danger-outline" data-uapp-settings-action="modal:delete-account">Odstranit účet</button>
      </section>`;
  }

  function renderPanelSupport() {
    return `
      <div class="uapp-settings-panel-head"><span class="uapp-settings-panel-ico">🌐</span><div><h2>Podpora</h2><p>Získejte pomoc, nápovědu a kontaktujte tým podpory</p></div></div>
      <section class="uapp-settings-card"><h3>Časté dotazy</h3>
        ${['Začínáme se správou vozidel', 'Přidávání vozidel a dokumentů', 'Servisy, připomínky a historie', 'Fakturace a tarify', 'Účet a zabezpečení'].map((q) => `<button type="button" class="uapp-settings-faq-row">${esc(q)} <span>›</span></button>`).join('')}
      </section>
      <section class="uapp-settings-card"><h3>Kontaktujte podporu</h3>
        <div class="uapp-settings-row-line"><div><strong>Napsat e-mail</strong><span>Odpovíme co nejdříve</span></div><a class="uapp-settings-link" href="mailto:podpora@sprava-vozidel.cz">podpora@sprava-vozidel.cz</a></div>
        <div class="uapp-settings-row-line"><div><strong>Online chat</strong><span>Po–Pá 8:00–18:00</span></div><button type="button" class="uapp-settings-btn" data-uapp-settings-action="chat-disabled" disabled>Chat připravujeme</button></div>
        <div class="uapp-settings-row-line"><div><strong>Zavolat nám</strong><span>Po–Pá 8:00–18:00</span></div><strong>+420 800 123 456</strong></div>
      </section>
      <section class="uapp-settings-card"><h3>Nápověda a návody</h3><p>Uživatelská nápověda — průvodce funkcemi aplikace.</p><button type="button" class="uapp-settings-btn" data-uapp-settings-action="open-help">Otevřít nápovědu</button></section>
      <footer class="uapp-settings-footer-meta">
        <span>Novinky v aplikaci</span>
        <button type="button" class="uapp-settings-link" data-uapp-settings-action="open-changelog">Zobrazit historii změn</button>
      </footer>`;
  }

  function renderMainPanel(snapshot) {
    switch (STATE.panel) {
      case 'security': return renderPanelSecurity();
      case 'license': return renderPanelLicense();
      case 'notifications': return renderPanelNotifications(snapshot);
      case 'garage': return renderPanelGarage(snapshot);
      case 'documents': return renderPanelDocuments();
      case 'billing': return renderPanelBilling();
      case 'services-sharing': return renderPanelServices();
      case 'privacy': return renderPanelPrivacy(snapshot);
      case 'support': return renderPanelSupport();
      default: return renderPanelProfile(snapshot);
    }
  }

  function renderModals() {
    const m = STATE.modal;
    if (!m) return '';
    if (m === 'password') {
      return `<div class="uapp-settings-modal-backdrop" data-uapp-settings-action="modal:close"><div class="uapp-settings-modal" role="dialog"><h3>Změna hesla</h3><label>Staré heslo<input type="password" data-uapp-settings-field="old_password"></label><label>Nové heslo<input type="password" data-uapp-settings-field="new_password"></label><label>Potvrzení<input type="password" data-uapp-settings-field="new_password2"></label><div class="uapp-settings-modal-actions"><button type="button" data-uapp-settings-action="modal:close">Zrušit</button><button type="button" class="uapp-settings-btn-primary" data-uapp-settings-action="submit-password">Změnit heslo</button></div></div></div>`;
    }
    if (m === 'logout-all') {
      return `<div class="uapp-settings-modal-backdrop" data-uapp-settings-action="modal:close"><div class="uapp-settings-modal"><h3>Odhlásit všechna zařízení?</h3><p>Ukončí všechny aktivní relace kromě této (může být nutné se znovu přihlásit).</p><div class="uapp-settings-modal-actions"><button type="button" data-uapp-settings-action="modal:close">Zrušit</button><button type="button" class="uapp-settings-btn-primary" data-uapp-settings-action="submit-logout-all">Potvrdit</button></div></div></div>`;
    }
    if (m === 'delete-account') {
      return `<div class="uapp-settings-modal-backdrop"><div class="uapp-settings-modal"><h3>Smazat účet</h3><p>Tato akce je nevratná. Použijte existující bezpečný postup v aplikaci.</p><div class="uapp-settings-modal-actions"><button type="button" data-uapp-settings-action="modal:close">Zrušit</button><button type="button" class="is-danger" data-uapp-settings-action="legacy-delete-account">Pokračovat</button></div></div></div>`;
    }
    if (m === '2fa') {
      return `<div class="uapp-settings-modal-backdrop" data-uapp-settings-action="modal:close"><div class="uapp-settings-modal"><h3>Dvoufázové ověření</h3><p>Nastavení 2FA probíhá v zabezpečeném průvodci aplikace.</p><button type="button" class="uapp-settings-btn-primary" data-uapp-settings-action="legacy-2fa">Spustit nastavení 2FA</button></div></div>`;
    }
    if (m === 'verify-phone') {
      return `<div class="uapp-settings-modal-backdrop" data-uapp-settings-action="modal:close"><div class="uapp-settings-modal"><h3>Ověření telefonu</h3><p>SMS ověření zatím není aktivní na backendu. Uložte telefon v profilu — ověření bude dostupné brzy.</p><button type="button" data-uapp-settings-action="modal:close">Rozumím</button></div></div>`;
    }
    if (m === 'login-history') {
      return `<div class="uapp-settings-modal-backdrop" data-uapp-settings-action="modal:close"><div class="uapp-settings-modal uapp-settings-modal-wide"><h3>Historie přihlášení</h3><div id="uappSettingsLoginHistory">Načítám…</div></div></div>`;
    }
    if (m === 'feedback') {
      return `<div class="uapp-settings-modal-backdrop" data-uapp-settings-action="modal:close"><div class="uapp-settings-modal"><h3>Zpětná vazba</h3><label>Typ<select data-uapp-settings-field="feedback_type"><option value="bug">Chyba</option><option value="idea">Nápad</option><option value="other">Jiné</option></select></label><label>Zpráva<textarea data-uapp-settings-field="feedback_message" rows="4"></textarea></label><button type="button" class="uapp-settings-btn-primary" data-uapp-settings-action="submit-feedback">Odeslat</button></div></div>`;
    }
    if (m === 'cancel-subscription') {
      return `<div class="uapp-settings-modal-backdrop" data-uapp-settings-action="modal:close"><div class="uapp-settings-modal"><h3>Zrušit předplatné?</h3><p>Předplatné bude ukončeno ke konci fakturačního období.</p><div class="uapp-settings-modal-actions"><button type="button" data-uapp-settings-action="modal:close">Zpět</button><button type="button" class="is-danger" data-uapp-settings-action="submit-cancel-subscription">Zrušit předplatné</button></div></div></div>`;
    }
    if (m === 'share-service') {
      return `<div class="uapp-settings-modal-backdrop" data-uapp-settings-action="modal:close"><div class="uapp-settings-modal"><h3>Sdílet vozidlo se servisem</h3><p>Vyberte servis v adresáři a povolte přístup k vybranému vozidlu. Sdílení je dostupné od tarifu Basic.</p><div class="uapp-settings-modal-actions"><button type="button" data-uapp-settings-action="modal:close">Zrušit</button><button type="button" class="uapp-settings-btn-primary" data-uapp-settings-action="nav:servicesDirectory">Otevřít servisy</button></div></div></div>`;
    }
    return '';
  }

  function renderPageHtml(snapshot) {
    return `
      <div class="uapp-settings-page" data-testid="user-app-next-settings">
        ${renderTopbar(snapshot)}
        <div class="uapp-settings-layout">
          ${renderCategoryNav()}
          <div class="uapp-settings-main">
            ${STATE.loading ? '<div class="uapp-settings-loading">Načítám nastavení…</div>' : renderMainPanel(snapshot)}
          </div>
          ${renderAside(STATE.panel, snapshot)}
        </div>
        ${renderModals()}
      </div>`;
  }

  function collectProfileDraft(root) {
    const draft = {};
    root.querySelectorAll('[data-uapp-settings-field]').forEach((el) => {
      const key = el.getAttribute('data-uapp-settings-field');
      if (!key || key === 'search') return;
      draft[key] = el.value;
    });
    return draft;
  }

  async function saveProfile(root) {
    const draft = collectProfileDraft(root);
    await api(`${API_BASE}/profile`, 'PATCH', {
      name: draft.name,
      phone: draft.phone,
      preferred_language: draft.preferred_language,
      preferred_contact: draft.preferred_contact,
    });
    showMsg('Profil byl uložen.', 'success');
    await loadSnapshot(true);
  }

  async function saveNotifications(root) {
    const types = {};
    root.querySelectorAll('[data-notify-type]').forEach((el) => {
      const spec = el.getAttribute('data-notify-type').split(':');
      if (spec.length !== 2) return;
      types[spec[0]] = types[spec[0]] || {};
      types[spec[0]][spec[1]] = el.checked;
    });
    await api(`${API_BASE}/notifications`, 'PATCH', { types });
    showMsg('Nastavení oznámení uloženo.', 'success');
  }

  async function handleAction(action, event) {
    const root = document.querySelector('.uapp-settings-page');
    if (action === 'modal:close') { STATE.modal = null; return refresh(); }
    if (action.startsWith('panel:')) {
      const panel = action.split(':')[1];
      navigatePanel(panel);
      return;
    }
    if (action === 'save-profile' && root) { try { await saveProfile(root); refresh(); } catch (e) { showMsg(e.message || 'Uložení selhalo', 'error'); } return; }
    if (action === 'save-notifications' && root) { try { await saveNotifications(root); } catch (e) { showMsg(e.message || 'Uložení selhalo', 'error'); } return; }
    if (action === 'save-garage') { try { await api(`${API_BASE}/garage`, 'PATCH', { mdcr_auto_update: true }); showMsg('Uloženo.', 'success'); } catch (e) { showMsg(e.message, 'error'); } return; }
    if (action === 'save-privacy') { try { await api(`${API_BASE}/privacy`, 'PATCH', { marketing: false, third_party: false }); showMsg('Uloženo.', 'success'); await loadSnapshot(true); refresh(); } catch (e) { showMsg(e.message, 'error'); } return; }
    if (action === 'save-services') { try { await api(`${API_BASE}/services`, 'PATCH', { allow_vehicle_access: true, allow_communication: true }); showMsg('Uloženo.', 'success'); } catch (e) { showMsg(e.message, 'error'); } return; }
    if (action === 'save-documents') { try { await api(`${API_BASE}/documents`, 'PATCH', { auto_sort: true, smart_naming: true }); showMsg('Uloženo.', 'success'); } catch (e) { showMsg(e.message, 'error'); } return; }
    if (action === 'open-license') { if (hasFn('openLicenseModal')) window.openLicenseModal(); else showMsg('Modul licencí není dostupný.', 'warning'); return; }
    if (action === 'add-vehicle') { if (hasFn('openAddVehicleModal')) window.openAddVehicleModal(); return; }
    if (action === 'upload-document') { if (hasFn('switchTab')) { window.switchTab('documents'); } return; }
    if (action.startsWith('nav:')) { const tab = action.split(':')[1]; if (hasFn('switchTab')) window.switchTab(tab === 'servicesDirectory' ? 'servicesDirectory' : tab); return; }
    if (action === 'export-data') {
      try {
        if (!hasFn('apiCall')) throw new Error('API není dostupné');
        const blobResp = await fetch((typeof getApiBaseUrl === 'function' ? getApiBaseUrl() : '') + API_BASE + '/export-data', {
          method: 'POST',
          headers: {
            Authorization: typeof accessToken !== 'undefined' && accessToken ? `Bearer ${accessToken}` : '',
            Accept: 'application/zip',
          },
        });
        if (!blobResp.ok) throw new Error('Export selhal (' + blobResp.status + ')');
        const blob = await blobResp.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'export-dat.zip';
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
        showMsg('Export dat byl spuštěn.', 'success');
      } catch (e) { showMsg('Export selhal: ' + e.message, 'error'); }
      return;
    }
    if (action === 'legacy-delete-account') { STATE.modal = null; if (hasFn('handleDeleteAccount')) window.handleDeleteAccount(); else showMsg('Funkce smazání účtu není dostupná.', 'warning'); refresh(); return; }
    if (action === 'legacy-2fa') { STATE.modal = null; if (hasFn('setSettingsPanel')) { /* noop */ } showMsg('Použijte stávající 2FA průvodce v sekci zabezpečení.', 'info'); refresh(); return; }
    if (action === 'submit-password') {
      const oldP = root && root.querySelector('[data-uapp-settings-field="old_password"]');
      const newP = root && root.querySelector('[data-uapp-settings-field="new_password"]');
      const newP2 = root && root.querySelector('[data-uapp-settings-field="new_password2"]');
      if (!newP || newP.value !== newP2.value) { showMsg('Hesla se neshodují.', 'error'); return; }
      try {
        await api(`${API_BASE}/security/change-password`, 'POST', { current_password: oldP.value, new_password: newP.value });
        STATE.modal = null; showMsg('Heslo změněno.', 'success'); refresh();
      } catch (e) { showMsg(e.message || 'Změna hesla selhala', 'error'); }
      return;
    }
    if (action === 'submit-logout-all') {
      try {
        const res = await api(`${API_BASE}/security/logout-all`, 'POST', {});
        STATE.modal = null; showMsg(res.message || 'Odhlášeno.', 'success');
        if (res.requires_relogin && hasFn('logout')) window.logout();
      } catch (e) { showMsg(e.message, 'error'); }
      return;
    }
    if (action === 'submit-cancel-subscription') {
      try {
        await api('/api/v1/license/subscription/cancel', 'POST', {});
        STATE.modal = null; showMsg('Předplatné bude zrušeno ke konci období.', 'success');
      } catch (e) { showMsg(e.message || 'Zrušení selhalo', 'error'); }
      return;
    }
    if (action === 'submit-feedback') {
      const msgEl = root && root.querySelector('[data-uapp-settings-field="feedback_message"]');
      const typeEl = root && root.querySelector('[data-uapp-settings-field="feedback_type"]');
      try {
        await api(`${API_BASE}/support-feedback`, 'POST', { subject: 'Zpětná vazba z nastavení', message: msgEl.value, category: typeEl.value, feedback_type: typeEl.value });
        STATE.modal = null; showMsg('Děkujeme za zpětnou vazbu.', 'success'); refresh();
      } catch (e) { showMsg(e.message, 'error'); }
      return;
    }
    if (action === 'modal:password' || action === 'modal:2fa' || action === 'modal:logout-all' || action === 'modal:delete-account' || action === 'modal:verify-phone' || action === 'modal:login-history' || action === 'modal:feedback' || action === 'modal:cancel-subscription' || action === 'modal:share-service') {
      STATE.modal = action.replace('modal:', '');
      refresh();
      if (STATE.modal === 'login-history') {
        api(`${API_BASE}/security/login-history`).then((res) => {
          const box = document.getElementById('uappSettingsLoginHistory');
          if (!box) return;
          const items = (res.items || []).map((i) => `<div class="uapp-settings-history-row"><strong>${esc(i.event_type)}</strong> ${esc(i.os)} / ${esc(i.browser)} — ${fmtDateTime(i.created_at)}</div>`).join('');
          box.innerHTML = items || '<p>Žádná historie.</p>';
        }).catch(() => {});
      }
      return;
    }
    if (action === 'open-help') { showMsg('Nápověda — otevřete sekci Podpora nebo kontaktujte podporu.', 'info'); return; }
    if (action === 'open-changelog') { if (hasFn('apiCall')) apiCall('/version', 'GET').then((v) => showMsg((v && v.version) ? 'Verze ' + v.version : 'Historie změn', 'info')).catch(() => showMsg('Historie změn', 'info')); return; }
    if (action === 'chat-disabled') { showMsg('Online chat připravujeme.', 'info'); return; }
    if (action === 'mailto:support') { window.location.href = 'mailto:podpora@sprava-vozidel.cz'; return; }
    if (action === 'download-invoice') { showMsg('Stažení faktury bude dostupné po první platbě.', 'info'); return; }
    if (action === 'edit-billing-profile') { navigatePanel('profile'); return; }
  }

  function bindEvents(root) {
    if (!root) return;
    root.addEventListener('click', (ev) => {
      const btn = ev.target.closest('[data-uapp-settings-action]');
      if (!btn) return;
      ev.preventDefault();
      void handleAction(btn.getAttribute('data-uapp-settings-action'), ev);
    });
    root.addEventListener('input', (ev) => {
      const field = ev.target.closest('[data-uapp-settings-field="search"]');
      if (!field) return;
      STATE.search = field.value;
      const nav = root.querySelector('.uapp-settings-categories-list');
      if (nav) nav.innerHTML = filteredCategories().map((c) => `
        <button type="button" class="uapp-settings-category${STATE.panel === c.id ? ' is-active' : ''}" data-uapp-settings-action="panel:${c.id}"><span>${esc(c.label)}</span></button>`).join('');
    });
  }

  function getMountRoot() {
    return document.querySelector('#uappNextSettingsMount');
  }

  function getPageRoot() {
    return document.querySelector('.uapp-settings-page');
  }

  function updateCategoryNav(root) {
    const list = root.querySelector('.uapp-settings-categories-list');
    if (!list) return;
    list.innerHTML = filteredCategories().map((c) => `
      <button type="button" class="uapp-settings-category${STATE.panel === c.id ? ' is-active' : ''}" data-uapp-settings-action="panel:${c.id}">
        <span class="uapp-settings-category-ico" data-ico="${esc(c.icon)}" aria-hidden="true"></span>
        <span>${esc(c.label)}</span>
      </button>`).join('');
  }

  function updateMainAndAside(root, snapshot) {
    const main = root.querySelector('.uapp-settings-main');
    if (main) {
      main.innerHTML = STATE.loading
        ? '<div class="uapp-settings-loading">Načítám nastavení…</div>'
        : renderMainPanel(snapshot);
    }
    const layout = root.querySelector('.uapp-settings-layout');
    const oldAside = root.querySelector('.uapp-settings-aside');
    if (oldAside) oldAside.remove();
    const asideHtml = renderAside(STATE.panel, snapshot);
    if (layout && asideHtml) layout.insertAdjacentHTML('beforeend', asideHtml);
  }

  function updateModals(root) {
    root.querySelectorAll('.uapp-settings-modal-backdrop').forEach((el) => el.remove());
    const modalsHtml = renderModals();
    if (modalsHtml) root.insertAdjacentHTML('beforeend', modalsHtml);
  }

  function updateDom(snapshot) {
    const root = getPageRoot();
    if (!root) return false;
    const snap = snapshot || STATE.snapshot;
    if (!snap) return false;
    updateCategoryNav(root);
    updateMainAndAside(root, snap);
    updateModals(root);
    return true;
  }

  function refresh() {
    if (updateDom(STATE.snapshot)) return;
    if (hasFn('UserAppNext') && window.UserAppNext.render) window.UserAppNext.render();
  }

  async function switchPanel(panel) {
    const next = normalizePanel(
      panel || (hasFn('getSettingsPanelFromRoute') ? window.getSettingsPanelFromRoute() : STATE.panel)
    );
    STATE.panel = next;
    const pageRoot = getPageRoot();
    if (!pageRoot) {
      await mount(getMountRoot());
      return;
    }
    STATE.loading = true;
    updateDom(STATE.snapshot);
    try {
      await loadPanelData(next);
      if (!STATE.snapshot) await loadSnapshot();
    } finally {
      STATE.loading = false;
      updateDom(STATE.snapshot);
    }
  }

  async function navigatePanel(panel) {
    const next = normalizePanel(panel);
    if (hasFn('setSettingsPanelRoute')) window.setSettingsPanelRoute(next);
    await switchPanel(next);
  }

  async function onRoutePanel(panel) {
    const next = normalizePanel(
      panel || (hasFn('getSettingsPanelFromRoute') ? window.getSettingsPanelFromRoute() : STATE.panel)
    );
    if (!getPageRoot()) {
      await new Promise((resolve) => {
        let tries = 0;
        const waitForMount = () => {
          if (getPageRoot() || getMountRoot() || tries++ > 150) {
            resolve();
            return;
          }
          window.requestAnimationFrame(waitForMount);
        };
        waitForMount();
      });
    }
    await switchPanel(next);
  }

  function normalizePanel(p) {
    const id = String(p || 'profile').toLowerCase();
    return PANELS.some((x) => x.id === id) ? id : 'profile';
  }

  async function mount(container) {
    if (!container) return;
    STATE.panel = normalizePanel(hasFn('getSettingsPanelFromRoute') ? window.getSettingsPanelFromRoute() : STATE.panel);
    const snapshot = await loadSnapshot(true);
    STATE.formDraft.phone = '';
    await loadPanelData(STATE.panel);
    container.innerHTML = renderPageHtml(snapshot);
    bindEvents(container);
  }

  function renderInto(container) {
    void mount(container);
    return '<div class="uapp-settings-loading-wrap">Načítám nastavení…</div>';
  }

  window.UserSettings = {
    renderInto,
    mount,
    refresh,
    onRoutePanel,
    navigatePanel,
    getPanel: () => STATE.panel,
  };
})();
