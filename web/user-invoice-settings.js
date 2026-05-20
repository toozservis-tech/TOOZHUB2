/**
 * Nastavení vzhledu faktury — user UI (staging localStorage).
 */
(function () {
  'use strict';

  const API = 'UserInvoiceSettings';
  const STYLES = [
    { id: 'modern', label: 'Moderní' },
    { id: 'classic', label: 'Klasický' },
    { id: 'minimal', label: 'Minimal' },
    { id: 'comfort', label: 'Komfort' },
  ];

  const ELEMENTS = [
    { key: 'logo', label: 'Logo a název firmy' },
    { key: 'supplier', label: 'Dodavatel' },
    { key: 'customer', label: 'Odběratel' },
    { key: 'meta', label: 'Informace o faktuře' },
    { key: 'items', label: 'Položky faktury' },
    { key: 'payment', label: 'Platební údaje' },
    { key: 'qr', label: 'QR platba' },
    { key: 'summary', label: 'Souhrn' },
    { key: 'note', label: 'Poznámka' },
    { key: 'signature', label: 'Podpis' },
    { key: 'footer', label: 'Patička' },
  ];

  const state = { mountEl: null, cfg: null, a4Preview: true };

  function esc(v) {
    return String(v ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function getCfg() {
    if (window.UserInvoicesWorkflow?.getAppearance) return window.UserInvoicesWorkflow.getAppearance();
    return { style: 'modern', font: 'Inter', fontSize: 12, paper: 'A4', elements: {} };
  }

  function saveCfg() {
    if (window.UserInvoicesWorkflow?.saveAppearance) window.UserInvoicesWorkflow.saveAppearance(state.cfg);
  }

  function sampleInvoice() {
    if (window.UserInvoicesWorkflow?.draftToLegacy && window.UserInvoicesWorkflow?.defaultDraft) {
      return window.UserInvoicesWorkflow.draftToLegacy(window.UserInvoicesWorkflow.defaultDraft?.() || {});
    }
    return { invoice_number: 'FV-2024-00001', lines: [], extra: { supplier_name: 'Ukázka s.r.o.' } };
  }

  function renderPreview() {
    const inv = sampleInvoice();
    if (typeof window.UserInvoicesWorkflow?.renderDocumentHtml === 'function') {
      return window.UserInvoicesWorkflow.renderDocumentHtml(inv);
    }
    return '<div class="sv-inv-doc"><p>Náhled faktury</p></div>';
  }

  function renderHtml() {
    const c = state.cfg || getCfg();
    const els = c.elements || {};
    const styleOpts = STYLES.map((s) => `<option value="${s.id}"${c.style === s.id ? ' selected' : ''}>${esc(s.label)}</option>`).join('');
    const elementRows = ELEMENTS.map((el, i) => {
      const on = els[el.key] !== false;
      return `<div class="sv-inv-settings-element" data-el-key="${el.key}" draggable="true">
        <span class="sv-inv-settings-drag" aria-hidden="true">⋮⋮</span>
        <span>${esc(el.label)}</span>
        <label class="sv-inv-toggle-sm"><input type="checkbox" ${on ? 'checked' : ''} onchange="window.${API}.toggleEl('${el.key}', this.checked)"><span></span></label>
      </div>`;
    }).join('');

    return `
      <div class="sv-inv sv-inv-page sv-inv-settings-page" data-testid="user-invoice-settings">
        <nav class="sv-inv-breadcrumb">
          <button type="button" onclick="window.UserInvoicesDashboard.goOverview()">Přehled</button><span>/</span>
          <button type="button" onclick="window.UserInvoicesDashboard.showList()">Faktury</button><span>/</span>
          <button type="button" onclick="window.UserInvoicesDashboard.openAccount()">Nastavení</button><span>/</span>
          <span>Vzhled faktury</span>
        </nav>
        <div class="sv-inv-page-head"><div><h1>Vzhled faktury</h1><p>Přizpůsobte vzhled PDF faktury podle vaší značky. Nastavení se ukládá lokálně (staging).</p></div></div>
        <div class="sv-inv-settings-layout">
          <div class="sv-inv-settings-main">
            <div class="sv-inv-settings-toolbar">
              <label class="sv-inv-check-label"><input type="checkbox" ${state.a4Preview ? 'checked' : ''} onchange="window.${API}.toggleA4(this.checked)"> Náhled na formát A4</label>
              <button type="button" class="sv-inv-btn sv-inv-btn--secondary" onclick="window.${API}.pdfPreview()">PDF náhled</button>
            </div>
            <div class="sv-inv-settings-preview-wrap ${state.a4Preview ? 'is-a4' : ''}">
              <div class="sv-inv-a4-frame" style="font-family:${esc(c.font || 'Inter')};font-size:${Number(c.fontSize || 12)}px">
                ${renderPreview()}
              </div>
            </div>
            <div class="sv-inv-card sv-inv-section-card">
              <h2>Parametry vzhledu</h2>
              <div class="sv-inv-form-grid">
                <label>Styl faktury<select onchange="window.${API}.set('style', this.value)">${styleOpts}</select></label>
                <label>Písmo<select onchange="window.${API}.set('font', this.value)">
                  <option${c.font === 'Inter' ? ' selected' : ''}>Inter</option>
                  <option${c.font === 'Roboto' ? ' selected' : ''}>Roboto</option>
                  <option${c.font === 'Georgia' ? ' selected' : ''}>Georgia</option>
                </select></label>
                <label>Velikost písma<input type="number" min="9" max="16" value="${Number(c.fontSize || 12)}" onchange="window.${API}.set('fontSize', Number(this.value))"></label>
                <label>Formát papíru<select onchange="window.${API}.set('paper', this.value)"><option value="A4"${c.paper === 'A4' ? ' selected' : ''}>A4 (210 × 297 mm)</option></select></label>
                <label>Zarovnání<select onchange="window.${API}.set('alignment', this.value)"><option value="left"${c.alignment === 'left' ? ' selected' : ''}>Vlevo</option><option value="center"${c.alignment === 'center' ? ' selected' : ''}>Na střed</option></select></label>
                <label class="sv-inv-check-label"><input type="checkbox" ${c.shadows !== false ? 'checked' : ''} onchange="window.${API}.set('shadows', this.checked)"> Stíny</label>
                <label class="sv-inv-check-label"><input type="checkbox" ${c.radius !== false ? 'checked' : ''} onchange="window.${API}.set('radius', this.checked)"> Zaoblení rohů</label>
                <label class="sv-inv-check-label"><input type="checkbox" ${c.qrPayment !== false ? 'checked' : ''} onchange="window.${API}.set('qrPayment', this.checked)"> QR platba</label>
                <label class="sv-inv-check-label"><input type="checkbox" ${c.signature !== false ? 'checked' : ''} onchange="window.${API}.set('signature', this.checked)"> Podpis</label>
              </div>
            </div>
          </div>
          <aside class="sv-inv-side">
            <section class="sv-inv-side-card">
              <h3>Prvky faktury</h3>
              <p class="sv-inv-side-desc">Zapněte/vypněte prvky. Pořadí bude podporovat drag &amp; drop.</p>
              <div class="sv-inv-settings-elements" id="uInvSettingsElements">${elementRows}</div>
            </section>
            <section class="sv-inv-side-card sv-inv-tip"><span>💡</span><div>Nastavení se synchronizuje s náhledem faktury při vytváření.</div></section>
            <button type="button" class="sv-inv-btn sv-inv-btn--primary sv-inv-btn--block" onclick="window.${API}.save()">Uložit nastavení</button>
          </aside>
        </div>
      </div>`;
  }

  function paint() {
    if (!state.mountEl) return;
    state.mountEl.innerHTML = renderHtml();
  }

  const api = {
    mount(el) {
      state.mountEl = el;
      state.cfg = getCfg();
      if (!state.cfg.elements) state.cfg.elements = {};
      paint();
    },
    set(key, val) {
      state.cfg = state.cfg || getCfg();
      state.cfg[key] = val;
      saveCfg();
      paint();
    },
    toggleEl(key, on) {
      state.cfg = state.cfg || getCfg();
      if (!state.cfg.elements) state.cfg.elements = {};
      state.cfg.elements[key] = !!on;
      saveCfg();
      paint();
    },
    toggleA4(on) {
      state.a4Preview = !!on;
      paint();
    },
    pdfPreview() {
      if (window.UserInvoicesWorkflow?.openPreview) {
        window.UserInvoicesWorkflow.openPreview();
      } else {
        window.print();
      }
    },
    save() {
      saveCfg();
      if (typeof window.showAlert === 'function') window.showAlert('Nastavení vzhledu faktury bylo uloženo (staging localStorage).', 'success');
    },
  };

  window.UserInvoiceSettings = api;
})();
