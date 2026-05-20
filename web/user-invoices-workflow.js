/**
 * User invoice creation workflow — STAGING localStorage adapter.
 * Backend user invoice CRUD/PDF/email/share endpoints do NOT exist yet.
 */
(function () {
  'use strict';

  const API = 'UserInvoicesWorkflow';
  const STORAGE_PREFIX = 'sv_user_invoices_staging_v1';
  const APPEARANCE_KEY = 'sv_user_invoice_appearance_v1';

  const WIZARD_STEPS = [
    { n: 1, label: 'Základní informace' },
    { n: 2, label: 'Položky faktury' },
    { n: 3, label: 'Náhled a odeslání' },
    { n: 4, label: 'Dokončeno' },
  ];

  const state = {
    mountEl: null,
    step: 1,
    draft: null,
    draftId: null,
    saving: false,
    previewModal: false,
    previewZoom: 100,
    customerSameAsSupplier: false,
    attachments: [],
  };

  function storageKey() {
    const uid = window.currentUser?.id || window.currentUser?.account_id || 'anon';
    const tid = window.lastWorkspaceMePayload?.tenant_id || 'default';
    return `${STORAGE_PREFIX}:${tid}:${uid}`;
  }

  function loadStore() {
    try {
      const raw = localStorage.getItem(storageKey());
      return raw ? JSON.parse(raw) : { invoices: [], seq: 0 };
    } catch (e) {
      return { invoices: [], seq: 0 };
    }
  }

  function saveStore(data) {
    localStorage.setItem(storageKey(), JSON.stringify(data));
  }

  function esc(v) {
    return String(v ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function money(value, currency) {
    const n = Number(value || 0);
    const cur = !currency || currency === 'CZK' ? 'Kč' : currency;
    return `${n.toLocaleString('cs-CZ', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${cur}`;
  }

  function blockerToast(feature) {
    showToast(`${feature}: Tato funkce čeká na backend API.`, 'info');
  }

  function fmtDateLong(value) {
    if (!value) return '—';
    try {
      const d = new Date(value);
      return `${d.getDate()}. ${d.getMonth() + 1}. ${d.getFullYear()}`;
    } catch (e) {
      return String(value);
    }
  }

  function showToast(msg, kind) {
    if (typeof window.showAlert === 'function') window.showAlert(msg, kind || 'info');
  }

  function lineNet(line) {
    const qty = Number(line?.quantity || 0);
    const price = Number(line?.unit_price || 0);
    const disc = Number(line?.discount_percent || 0);
    return qty * price * (1 - disc / 100);
  }

  function invoiceCalc(lines) {
    const rows = Array.isArray(lines) ? lines : [];
    let subtotal = 0;
    let discountTotal = 0;
    let tax = 0;
    rows.forEach((ln) => {
      const qty = Number(ln?.quantity || 0);
      const price = Number(ln?.unit_price || 0);
      const disc = Number(ln?.discount_percent || 0);
      const grossLine = qty * price;
      const net = lineNet(ln);
      discountTotal += grossLine - net;
      subtotal += grossLine;
      tax += net * (Number(ln?.tax_rate || ln?.vat_rate || 0) / 100);
    });
    const base = subtotal - discountTotal;
    return {
      subtotal: Math.round(subtotal * 100) / 100,
      discountTotal: Math.round(discountTotal * 100) / 100,
      base: Math.round(base * 100) / 100,
      tax: Math.round(tax * 100) / 100,
      total: Math.round((base + tax) * 100) / 100,
    };
  }

  function getAppearance() {
    try {
      const raw = localStorage.getItem(`${APPEARANCE_KEY}:${storageKey()}`);
      return raw
        ? JSON.parse(raw)
        : {
            style: 'modern',
            font: 'Inter',
            fontSize: 12,
            paper: 'A4',
            alignment: 'left',
            shadows: true,
            radius: true,
            qrPayment: true,
            signature: true,
            elements: {
              logo: true,
              supplier: true,
              customer: true,
              meta: true,
              items: true,
              payment: true,
              qr: true,
              summary: true,
              note: true,
              signature: true,
              footer: true,
            },
          };
    } catch (e) {
      return { style: 'modern', qrPayment: true, signature: true, elements: {} };
    }
  }

  function saveAppearance(cfg) {
    localStorage.setItem(`${APPEARANCE_KEY}:${storageKey()}`, JSON.stringify(cfg));
  }

  function nextInvoiceNumber() {
    const store = loadStore();
    store.seq = Number(store.seq || 0) + 1;
    const year = new Date().getFullYear();
    const num = `FV-${year}-${String(store.seq).padStart(5, '0')}`;
    saveStore(store);
    return num;
  }

  function defaultDraft() {
    const today = new Date().toISOString().slice(0, 10);
    const due = new Date();
    due.setDate(due.getDate() + 14);
    const num = nextInvoiceNumber();
    const u = window.currentUser || {};
    return {
      id: null,
      number: num,
      invoice_number: num,
      status: 'draft',
      issue_date: today,
      taxable_date: today,
      due_date: due.toISOString().slice(0, 10),
      due_at: due.toISOString().slice(0, 10),
      payment_method: 'Bankovní převod',
      variable_symbol: num.replace(/\D/g, '').slice(-9),
      constant_symbol: '0308',
      specific_symbol: '',
      currency: 'CZK',
      source: 'user_local',
      supplier: {
        name: u.name || 'AutoFuture s.r.o.',
        ico: u.ico || '12345678',
        dic: u.dic || 'CZ12345678',
        address: u.street ? [u.street, u.city, u.zip].filter(Boolean).join(', ') : 'U Trati 123, 100 00 Praha 10, Česká republika',
        email: u.email || 'info@autofuture.cz',
        phone: u.phone || '+420 777 123 456',
        bank_name: 'Fio banka, a.s.',
        bank_account: '2501234567 / 2010',
        iban: 'CZ89 2010 0000 0025 0123 4567',
        bic: 'FIOBCZPPXXX',
      },
      customer: {
        name: 'Novák Trans s.r.o.',
        ico: '87654321',
        dic: 'CZ87654321',
        address: 'Brněnská 45, 602 00 Brno, Česká republika',
        email: 'ucto@novaktrans.cz',
        phone: '+420 602 555 888',
      },
      items: [
        { id: 1, name: 'Výměna oleje a filtru', description: 'Motorový olej 5W-30, olejový filtr', quantity: 1, unit: 'ks', unit_price: 2500, discount_percent: 0, vat_rate: 21, total_without_vat: 2500 },
        { id: 2, name: 'Práce mechanika', description: 'Diagnostika vozidla', quantity: 2, unit: 'hod', unit_price: 800, discount_percent: 0, vat_rate: 21, total_without_vat: 1600 },
        { id: 3, name: 'Brzdové destičky přední', description: 'Kvalitní OEM', quantity: 1, unit: 'sada', unit_price: 3200, discount_percent: 5, vat_rate: 21, total_without_vat: 3040 },
      ],
      note: 'Děkujeme za spolupráci. Splatnost faktury je 14 dní od data vystavení.',
      attachments: [],
      extra: {},
      lines: [],
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
  }

  function draftToLegacy(draft) {
    const d = draft || {};
    const sup = d.supplier || {};
    const cust = d.customer || {};
    const items = Array.isArray(d.items) ? d.items : [];
    const lines = items.map((it) => ({
      description: it.name || it.description,
      note: it.description !== it.name ? it.description : '',
      quantity: it.quantity,
      unit: it.unit,
      unit_price: it.unit_price,
      tax_rate: it.vat_rate,
      discount_percent: it.discount_percent || 0,
    }));
    const totals = invoiceCalc(lines);
    return {
      ...d,
      invoice_number: d.number || d.invoice_number,
      due_at: d.due_date || d.due_at,
      notes: d.note || d.notes,
      total: totals.total,
      lines,
      extra: {
        issue_date: d.issue_date,
        delivery_date: d.taxable_date,
        variable_symbol: d.variable_symbol,
        constant_symbol: d.constant_symbol,
        specific_symbol: d.specific_symbol,
        supplier_name: sup.name,
        supplier_ico: sup.ico,
        supplier_dic: sup.dic,
        supplier_street: sup.address,
        supplier_email: sup.email,
        supplier_phone: sup.phone,
        supplier_bank: sup.bank_name,
        supplier_bankaccount: sup.bank_account,
        supplier_iban: sup.iban,
        supplier_swift: sup.bic,
        customer_name: cust.name,
        customer_ico: cust.ico,
        customer_dic: cust.dic,
        customer_street: cust.address,
        customer_email: cust.email,
        customer_phone: cust.phone,
      },
    };
  }

  function renderDocumentHtml(inv, opts) {
    if (typeof window.UserInvoicesDashboard?.renderDocumentHtml === 'function') {
      return window.UserInvoicesDashboard.renderDocumentHtml(inv, opts);
    }
    const doc = draftToLegacy(inv);
    const extra = doc.extra || {};
    const lines = doc.lines || [];
    const totals = invoiceCalc(lines);
    const invNo = doc.invoice_number || '(koncept)';
    return `<div class="sv-inv-doc"><div class="sv-inv-doc-header"><strong>${esc(invNo)}</strong></div><p>${esc(extra.supplier_name)} → ${esc(extra.customer_name)}</p><p>Celkem: ${esc(money(totals.total))}</p></div>`;
  }

  function readFormIntoDraft() {
    const d = state.draft || defaultDraft();
    const g = (id) => document.getElementById(id)?.value;
    const gc = (id) => document.getElementById(id)?.checked;
    d.number = g('uInvNumber') || d.number;
    d.invoice_number = d.number;
    d.issue_date = g('uInvIssueDate') || d.issue_date;
    d.taxable_date = g('uInvTaxDate') || d.taxable_date;
    d.due_date = g('uInvDueDate') || d.due_date;
    d.due_at = d.due_date;
    d.payment_method = g('uInvPayment') || d.payment_method;
    d.variable_symbol = g('uInvVs') || d.variable_symbol;
    d.constant_symbol = g('uInvKs') || d.constant_symbol;
    d.specific_symbol = g('uInvSs') || d.specific_symbol;
    d.supplier = {
      name: g('uInvSupName') || '',
      ico: g('uInvSupIco') || '',
      dic: g('uInvSupDic') || '',
      address: g('uInvSupAddr') || '',
      email: g('uInvSupEmail') || '',
      phone: g('uInvSupPhone') || '',
      bank_name: g('uInvSupBank') || '',
      bank_account: g('uInvSupAccount') || '',
      iban: g('uInvSupIban') || '',
      bic: g('uInvSupBic') || '',
    };
    state.customerSameAsSupplier = !!gc('uInvCustSame');
    if (state.customerSameAsSupplier) {
      d.customer = { ...d.supplier };
    } else {
      d.customer = {
        name: g('uInvCustName') || '',
        ico: g('uInvCustIco') || '',
        dic: g('uInvCustDic') || '',
        address: g('uInvCustAddr') || '',
        email: g('uInvCustEmail') || '',
        phone: g('uInvCustPhone') || '',
      };
    }
    d.note = g('uInvNote') || d.note;
    const lineRows = Array.from(document.querySelectorAll('[data-u-inv-line]'));
    d.items = lineRows.map((row, i) => {
      const qty = Number(row.querySelector('[data-u-line-qty]')?.value || 0);
      const price = Number(row.querySelector('[data-u-line-price]')?.value || 0);
      const disc = Number(row.querySelector('[data-u-line-disc]')?.value || 0);
      const name = String(row.querySelector('[data-u-line-name]')?.value || '').trim();
      const desc = String(row.querySelector('[data-u-line-desc]')?.value || '').trim();
      return {
        id: i + 1,
        name,
        description: desc || name,
        quantity: qty,
        unit: String(row.querySelector('[data-u-line-unit]')?.value || 'ks'),
        unit_price: price,
        discount_percent: disc,
        vat_rate: Number(row.querySelector('[data-u-line-vat]')?.value || 21),
        total_without_vat: lineNet({ quantity: qty, unit_price: price, discount_percent: disc }),
      };
    });
    d.updated_at = new Date().toISOString();
    state.draft = d;
    return d;
  }

  function validateDraft(d) {
    const errors = [];
    if (!d.supplier?.name?.trim()) errors.push('Vyplňte název dodavatele.');
    if (!d.supplier?.ico?.trim()) errors.push('Vyplňte IČO dodavatele.');
    if (!d.customer?.name?.trim()) errors.push('Vyplňte název odběratele.');
    if (!d.customer?.ico?.trim()) errors.push('Vyplňte IČO odběratele.');
    if (!Array.isArray(d.items) || !d.items.filter((it) => it.name && it.quantity > 0).length) {
      errors.push('Přidejte alespoň jednu položku faktury.');
    }
    if (d.due_date && d.issue_date && d.due_date < d.issue_date) {
      errors.push('Datum splatnosti nesmí být před datem vystavení.');
    }
    return errors;
  }

  function persistDraft(status) {
    const d = readFormIntoDraft();
    const store = loadStore();
    const totals = invoiceCalc(draftToLegacy(d).lines);
    d.totals = {
      subtotal_without_vat: totals.subtotal,
      discount_total: totals.discountTotal,
      vat_base: totals.base,
      vat_total: totals.tax,
      total_with_vat: totals.total,
    };
    d.total = totals.total;
    if (status) d.status = status;
    if (!d.id) {
      d.id = `local_${Date.now()}`;
      d.created_at = new Date().toISOString();
      store.invoices.unshift(d);
    } else {
      const idx = store.invoices.findIndex((x) => x.id === d.id);
      if (idx >= 0) store.invoices[idx] = d;
      else store.invoices.unshift(d);
    }
    state.draftId = d.id;
    state.draft = d;
    saveStore(store);
    auditLog('invoice_draft_save', d.id);
    return d;
  }

  function auditLog(action, invoiceId) {
    console.info('[USER_INVOICE_AUDIT]', action, { invoiceId, ts: new Date().toISOString(), staging: true });
  }

  function stepperHtml(step) {
    return `<ol class="sv-inv-stepper">${WIZARD_STEPS.map((s) => {
      let cls = '';
      if (s.n < step) cls = 'is-done';
      else if (s.n === step) cls = 'is-active';
      const icon = s.n < step ? '✓' : String(s.n);
      return `<li class="sv-inv-step ${cls}"><span class="sv-inv-step-ico">${icon}</span><span>${esc(s.label)}</span></li>`;
    }).join('')}</ol>`;
  }

  function lineRowHtml(it, idx) {
    const net = lineNet(it);
    const desc = it.description && it.description !== it.name ? it.description : '';
    return `
      <tr class="sv-inv-form-line" data-u-inv-line="${idx}">
        <td class="sv-inv-form-line-item">
          <input data-u-line-name class="sv-inv-inline-input sv-inv-inline-input--name" value="${esc(it.name)}" placeholder="Název položky" oninput="window.${API}.recalcSidebar()">
          <input data-u-line-desc class="sv-inv-inline-input sv-inv-inline-input--desc" value="${esc(desc)}" placeholder="Popis (volitelné)">
        </td>
        <td class="sv-inv-form-line-qty"><input data-u-line-qty type="number" min="0" step="0.1" class="sv-inv-inline-input sv-inv-inline-input--num" value="${esc(it.quantity)}" oninput="window.${API}.recalcSidebar()"></td>
        <td class="sv-inv-form-line-unit"><input data-u-line-unit class="sv-inv-inline-input sv-inv-inline-input--sm" value="${esc(it.unit)}" oninput="window.${API}.recalcSidebar()"></td>
        <td class="sv-inv-form-line-price"><input data-u-line-price type="number" min="0" step="0.01" class="sv-inv-inline-input sv-inv-inline-input--num" value="${esc(it.unit_price)}" oninput="window.${API}.recalcSidebar()"></td>
        <td class="sv-inv-form-line-disc"><input data-u-line-disc type="number" min="0" max="100" class="sv-inv-inline-input sv-inv-inline-input--num" value="${esc(it.discount_percent || 0)}" oninput="window.${API}.recalcSidebar()"></td>
        <td class="sv-inv-form-line-vat"><input data-u-line-vat type="number" class="sv-inv-inline-input sv-inv-inline-input--num" value="${esc(it.vat_rate || 21)}" oninput="window.${API}.recalcSidebar()"></td>
        <td class="sv-inv-form-line-net sv-inv-line-net">${esc(money(net))}</td>
        <td class="sv-inv-form-line-actions">
          <button type="button" class="sv-inv-icon-btn" title="Více">⋮</button>
          <button type="button" class="sv-inv-icon-btn sv-inv-icon-btn--danger" onclick="window.${API}.removeLine(${idx})" title="Odstranit">🗑</button>
        </td>
      </tr>`;
  }

  function sidebarSummaryHtml(d) {
    const legacy = draftToLegacy(d);
    const totals = invoiceCalc(legacy.lines);
    return `
      <section class="sv-inv-side-card">
        <h3>Náhled faktury</h3>
        <div class="sv-inv-side-summary">
          <div class="sv-inv-side-summary-row"><span>Mezisoučet bez DPH</span><span id="uInvSumSub">${esc(money(totals.subtotal))}</span></div>
          <div class="sv-inv-side-summary-row"><span>Sleva celkem</span><span id="uInvSumDisc" class="sv-inv-discount sv-inv-discount--pos">${esc(money(totals.discountTotal))}</span></div>
          <div class="sv-inv-side-summary-row"><span>Základ DPH</span><span id="uInvSumBase">${esc(money(totals.base))}</span></div>
          <div class="sv-inv-side-summary-row"><span>DPH (21 %)</span><span id="uInvSumVat">${esc(money(totals.tax))}</span></div>
          <div class="sv-inv-side-summary-total"><span>Celkem k úhradě</span><strong id="uInvSumTotal">${esc(money(totals.total))}</strong></div>
        </div>
        <button type="button" class="sv-inv-btn sv-inv-btn--secondary sv-inv-btn--block" onclick="window.${API}.openPreview()">Zobrazit náhled PDF</button>
      </section>
      <section class="sv-inv-side-card">
        <h3>Poznámka na faktuře</h3>
        <textarea id="uInvNote" class="sv-inv-textarea" rows="4">${esc(d.note || '')}</textarea>
      </section>
      <section class="sv-inv-side-card">
        <h3>Přílohy</h3>
        <div class="sv-inv-upload-zone" onclick="document.getElementById('uInvFileInput').click()" ondragover="event.preventDefault()" ondrop="window.${API}.onFileDrop(event)">
          <input id="uInvFileInput" type="file" accept=".pdf,.jpg,.jpeg,.png" multiple hidden onchange="window.${API}.onFileSelect(event)">
          <span class="sv-inv-upload-ico">↑</span>
          <p>Přetáhněte soubor sem nebo klikněte pro nahrání.</p>
          <p class="sv-inv-upload-hint">PDF, JPG, PNG (max. 10 MB) — staging: pouze lokálně</p>
          <div id="uInvAttachList">${(state.attachments || []).map((f) => `<div class="sv-inv-attach-item">${esc(f.name)}</div>`).join('')}</div>
        </div>
      </section>
      <div class="sv-inv-side-actions">
        <button type="button" class="sv-inv-btn sv-inv-btn--ghost sv-inv-btn--block" onclick="window.${API}.cancel()">Zrušit</button>
        <button type="button" class="sv-inv-btn sv-inv-btn--primary sv-inv-btn--block" onclick="window.${API}.createInvoice()">Vytvořit fakturu</button>
      </div>`;
  }

  function formStepHtml() {
    const d = state.draft || defaultDraft();
    const sup = d.supplier || {};
    const cust = d.customer || {};
    const items = Array.isArray(d.items) ? d.items : [];
    return `
      <div class="sv-inv-wizard-layout sv-inv-wizard-layout--form">
        <div class="sv-inv-wizard-main">
          <div class="sv-inv-form-page-head">
            <div>
              <h1 class="sv-inv-form-title">Nová faktura</h1>
              <p class="sv-inv-form-sub">Vytvořte novou fakturu. Všechna pole označená * jsou povinná.</p>
            </div>
            <button type="button" class="sv-inv-btn sv-inv-btn--secondary sv-inv-btn--with-icon" onclick="window.${API}.saveDraft()">💾 Uložit jako koncept</button>
          </div>
          <section class="sv-inv-card sv-inv-section-card">
            <div class="sv-inv-section-head"><span class="sv-inv-section-num">1</span><h2>Základní informace</h2></div>
            <div class="sv-inv-form-grid">
              <label>Číslo faktury *<input id="uInvNumber" value="${esc(d.number)}" readonly><small>Číslo se vygeneruje automaticky</small></label>
              <label>Datum vystavení *<input id="uInvIssueDate" type="date" value="${esc(String(d.issue_date || '').slice(0, 10))}"></label>
              <label>Datum zdanitelného plnění *<input id="uInvTaxDate" type="date" value="${esc(String(d.taxable_date || '').slice(0, 10))}"></label>
              <label>Datum splatnosti *<input id="uInvDueDate" type="date" value="${esc(String(d.due_date || '').slice(0, 10))}"></label>
              <label>Forma úhrady *<select id="uInvPayment"><option${d.payment_method === 'Bankovní převod' ? ' selected' : ''}>Bankovní převod</option><option${d.payment_method === 'Hotově' ? ' selected' : ''}>Hotově</option></select></label>
              <label>Variabilní symbol<input id="uInvVs" value="${esc(d.variable_symbol)}"><small>Doporučeno: číslo faktury</small></label>
              <label>Konstantní symbol<input id="uInvKs" value="${esc(d.constant_symbol)}"></label>
              <label>Specifický symbol<input id="uInvSs" value="${esc(d.specific_symbol || '')}" placeholder="Nepovinné"></label>
            </div>
          </section>
          <section class="sv-inv-card sv-inv-section-card">
            <div class="sv-inv-section-head"><span class="sv-inv-section-num">2</span><h2>Dodavatel</h2></div>
            <div class="sv-inv-form-grid">
              <label>Název firmy / jméno *<input id="uInvSupName" value="${esc(sup.name)}"></label>
              <label>IČO *<input id="uInvSupIco" value="${esc(sup.ico)}"></label>
              <label>DIČ<input id="uInvSupDic" value="${esc(sup.dic)}"></label>
              <label class="sv-inv-form-span2">Adresa *<input id="uInvSupAddr" value="${esc(sup.address)}"></label>
              <label>E-mail<input id="uInvSupEmail" type="email" value="${esc(sup.email)}"></label>
              <label>Telefon<input id="uInvSupPhone" value="${esc(sup.phone)}"></label>
              <label>Banka<input id="uInvSupBank" value="${esc(sup.bank_name)}"></label>
              <label>Číslo účtu<input id="uInvSupAccount" value="${esc(sup.bank_account)}"></label>
              <label>IBAN<input id="uInvSupIban" value="${esc(sup.iban)}"></label>
              <label>BIC/SWIFT<input id="uInvSupBic" value="${esc(sup.bic)}"></label>
              <label class="sv-inv-check-label sv-inv-form-span2"><input type="checkbox" id="uInvSupDefault"> Použít jako výchozího dodavatele (staging: localStorage)</label>
            </div>
          </section>
          <section class="sv-inv-card sv-inv-section-card">
            <div class="sv-inv-section-head"><span class="sv-inv-section-num">3</span><h2>Odběratel</h2>
              <label class="sv-inv-toggle-label"><input type="checkbox" id="uInvCustSame" ${state.customerSameAsSupplier ? 'checked' : ''} onchange="window.${API}.toggleCustSame()"> Odběratel je zároveň dodavatel</label>
            </div>
            <div class="sv-inv-form-grid" id="uInvCustFields">
              <label>Název firmy / jméno *<input id="uInvCustName" value="${esc(cust.name)}"></label>
              <label>IČO *<input id="uInvCustIco" value="${esc(cust.ico)}"></label>
              <label>DIČ<input id="uInvCustDic" value="${esc(cust.dic)}"></label>
              <label class="sv-inv-form-span2">Adresa *<input id="uInvCustAddr" value="${esc(cust.address)}"></label>
              <label>E-mail<input id="uInvCustEmail" type="email" value="${esc(cust.email)}"></label>
              <label>Telefon<input id="uInvCustPhone" value="${esc(cust.phone)}"></label>
            </div>
          </section>
          <section class="sv-inv-card sv-inv-section-card">
            <div class="sv-inv-section-head"><span class="sv-inv-section-num">4</span><h2>Položky faktury</h2></div>
            <div class="sv-inv-table-wrap sv-inv-form-lines-wrap">
              <table class="sv-inv-table sv-inv-lines-edit-table">
                <thead><tr>
                  <th>Položka / Popis</th>
                  <th>Množství</th>
                  <th>Jedn.</th>
                  <th>Cena za jedn.</th>
                  <th>Sleva (%)</th>
                  <th>DPH (%)</th>
                  <th>Celkem bez DPH</th>
                  <th>Akce</th>
                </tr></thead>
                <tbody id="uInvLinesBody">${items.map((it, i) => lineRowHtml(it, i)).join('')}</tbody>
              </table>
            </div>
            <button type="button" class="sv-inv-btn sv-inv-btn--outline sv-inv-btn--with-plus sv-inv-add-line-btn" onclick="window.${API}.addLine()">+ Přidat položku</button>
          </section>
        </div>
        <aside class="sv-inv-side">${sidebarSummaryHtml(d)}</aside>
      </div>`;
  }

  function previewStepHtml() {
    const d = state.draft || {};
    const legacy = draftToLegacy(d);
    const sup = d.supplier || {};
    const cust = d.customer || {};
    const totals = invoiceCalc(legacy.lines);
    const edit = (n) => `window.${API}.goStep(${n})`;
    return `
      <div class="sv-inv-wizard-layout sv-inv-wizard-layout--step3">
        <div class="sv-inv-wizard-main">
          <h2 class="sv-inv-review-title">Zkontrolujte a odešlete fakturu</h2>
          <div class="sv-inv-review-parties">
            <div class="sv-inv-card sv-inv-section-card">
              <div class="sv-inv-section-head"><h2>Dodavatel</h2><button type="button" class="sv-inv-edit-link" onclick="${edit(1)}">Upravit</button></div>
              <p><strong>${esc(sup.name)}</strong></p><p>${esc(sup.address)}</p><p>IČO: ${esc(sup.ico)} · DIČ: ${esc(sup.dic)}</p>
            </div>
            <div class="sv-inv-card sv-inv-section-card">
              <div class="sv-inv-section-head"><h2>Odběratel</h2><button type="button" class="sv-inv-edit-link" onclick="${edit(1)}">Upravit</button></div>
              <p><strong>${esc(cust.name)}</strong></p><p>${esc(cust.address)}</p><p>IČO: ${esc(cust.ico)} · DIČ: ${esc(cust.dic)}</p>
            </div>
          </div>
          <div class="sv-inv-card sv-inv-section-card">
            <div class="sv-inv-section-head"><h2>Údaje o faktuře</h2><button type="button" class="sv-inv-edit-link" onclick="${edit(1)}">Upravit</button></div>
            <div class="sv-inv-meta-grid sv-inv-meta-grid--review">
              <div class="sv-inv-meta-item"><label>Číslo faktury</label><strong>${esc(d.number)}</strong></div>
              <div class="sv-inv-meta-item"><label>Datum vystavení</label><strong>${esc(fmtDateLong(d.issue_date))}</strong></div>
              <div class="sv-inv-meta-item"><label>Datum zdanitelného plnění</label><strong>${esc(fmtDateLong(d.taxable_date))}</strong></div>
              <div class="sv-inv-meta-item"><label>Datum splatnosti</label><strong class="is-due">${esc(fmtDateLong(d.due_date))}</strong></div>
              <div class="sv-inv-meta-item"><label>Forma úhrady</label><strong>${esc(d.payment_method)}</strong></div>
            </div>
          </div>
          <div class="sv-inv-card sv-inv-section-card">
            <div class="sv-inv-section-head"><h2>Položky faktury</h2><button type="button" class="sv-inv-edit-link" onclick="${edit(1)}">Upravit</button></div>
            <div class="sv-inv-table-wrap"><table class="sv-inv-table"><thead><tr><th>Položka</th><th>Množství</th><th>Jedn.</th><th>Cena</th><th>Sleva</th><th>DPH</th><th>Celkem</th></tr></thead>
            <tbody>${(d.items || []).map((it) => `<tr><td><strong>${esc(it.name)}</strong>${it.description && it.description !== it.name ? `<div class="sv-inv-cell-sub">${esc(it.description)}</div>` : ''}</td><td>${esc(it.quantity)}</td><td>${esc(it.unit)}</td><td>${esc(money(it.unit_price))}</td><td>${esc(it.discount_percent || 0)} %</td><td>${esc(it.vat_rate)} %</td><td>${esc(money(lineNet(it)))}</td></tr>`).join('')}</tbody></table></div>
          </div>
          <div class="sv-inv-review-totals">
            <div class="sv-inv-side-summary">
              <div class="sv-inv-side-summary-row"><span>Mezisoučet bez DPH</span><span>${esc(money(totals.subtotal))}</span></div>
              <div class="sv-inv-side-summary-row"><span>Sleva celkem</span><span class="sv-inv-discount">-${esc(money(totals.discountTotal))}</span></div>
              <div class="sv-inv-side-summary-row"><span>Základ DPH</span><span>${esc(money(totals.base))}</span></div>
              <div class="sv-inv-side-summary-row"><span>DPH (21 %)</span><span>${esc(money(totals.tax))}</span></div>
              <div class="sv-inv-side-summary-total"><span>Celkem k úhradě</span><strong>${esc(money(totals.total))}</strong></div>
            </div>
          </div>
        </div>
        <aside class="sv-inv-side sv-inv-side--preview">
          <section class="sv-inv-side-card"><h3>Náhled faktury</h3><div class="sv-inv-mini-preview"><div class="sv-inv-a4-sheet sv-inv-a4-sheet--mini">${renderDocumentHtml(legacy, { a4: true, compact: true })}</div></div>
            <button type="button" class="sv-inv-btn sv-inv-btn--secondary sv-inv-btn--block" onclick="window.${API}.downloadPdf()">Stáhnout PDF</button></section>
          <section class="sv-inv-side-card sv-inv-alert-ready sv-inv-alert-ready--card"><span class="sv-inv-alert-ready-ico">✓</span><div><strong>Faktura je připravena k odeslání</strong><p>Po odeslání již nebude možné fakturu upravovat.</p></div></section>
          <section class="sv-inv-side-card"><h3>Další možnosti</h3>
            <button type="button" class="sv-inv-btn sv-inv-btn--outline sv-inv-btn--block" onclick="window.${API}.sendEmail()">Odeslat e-mailem</button>
            <button type="button" class="sv-inv-btn sv-inv-btn--outline sv-inv-btn--block" style="margin-top:8px;" onclick="window.${API}.scheduleSend()">Naplánovat odeslání</button>
          </section>
          <section class="sv-inv-side-card sv-inv-tip"><span>💡</span><div><strong>Tip:</strong> Fakturu můžete uložit jako koncept a pokračovat později.</div></section>
        </aside>
      </div>`;
  }

  function doneStepHtml() {
    const d = state.draft || {};
    const legacy = draftToLegacy(d);
    const totals = invoiceCalc(legacy.lines);
    return `
      <div class="sv-inv-wizard-layout sv-inv-wizard-layout--step4">
        <div class="sv-inv-wizard-step4-main">
          <div class="sv-inv-card sv-inv-section-card sv-inv-success-card">
            <div class="sv-inv-success-icon">✓</div>
            <h2>Faktura byla úspěšně vytvořena</h2>
            <p class="sv-inv-success-lead">Faktura <strong>${esc(d.number)}</strong> byla vytvořena a je připravena k odeslání odběrateli.</p>
            <h3 class="sv-inv-success-sub">Co chcete udělat dál?</h3>
            <div class="sv-inv-action-cards">
              <article class="sv-inv-action-card"><div class="sv-inv-action-card-ico">✉</div><strong>Odeslat odběrateli</strong><p>Pošlete fakturu e-mailem.</p><button type="button" class="sv-inv-btn sv-inv-btn--outline sv-inv-btn--block" onclick="window.${API}.sendEmail()">Odeslat e-mailem</button></article>
              <article class="sv-inv-action-card"><div class="sv-inv-action-card-ico">↓</div><strong>Stáhnout PDF</strong><p>Stáhněte si fakturu ve formátu PDF.</p><button type="button" class="sv-inv-btn sv-inv-btn--outline sv-inv-btn--block" onclick="window.${API}.downloadPdf()">Stáhnout PDF</button></article>
              <article class="sv-inv-action-card"><div class="sv-inv-action-card-ico">🔗</div><strong>Sdílet odkazem</strong><p>Vygenerujte odkaz na fakturu.</p><button type="button" class="sv-inv-btn sv-inv-btn--outline sv-inv-btn--block" onclick="window.${API}.shareLink()">Vygenerovat odkaz</button></article>
              <article class="sv-inv-action-card"><div class="sv-inv-action-card-ico">📅</div><strong>Naplánovat odeslání</strong><p>Naplánujte automatické odeslání.</p><button type="button" class="sv-inv-btn sv-inv-btn--outline sv-inv-btn--block" onclick="window.${API}.scheduleSend()">Naplánovat odeslání</button></article>
            </div>
            <h3 class="sv-inv-success-sub">Co bude následovat?</h3>
            <div class="sv-inv-timeline sv-inv-timeline--boxed">
              <div class="sv-inv-timeline-item"><span class="sv-inv-timeline-ico is-done">✓</span><div class="sv-inv-timeline-body"><strong>Faktura byla vytvořena jako koncept</strong><span class="sv-inv-timeline-status is-done">Hotovo</span></div></div>
              <div class="sv-inv-timeline-item"><span class="sv-inv-timeline-ico is-done">✓</span><div class="sv-inv-timeline-body"><strong>Faktura je připravena k odeslání</strong><span class="sv-inv-timeline-status is-done">Hotovo</span></div></div>
              <div class="sv-inv-timeline-item"><span class="sv-inv-timeline-ico is-next">●</span><div class="sv-inv-timeline-body"><strong>Po odeslání bude faktura evidována jako „Odesláno“</strong><span class="sv-inv-timeline-status is-next">Další krok</span><p>Odběratel obdrží fakturu na e-mail.</p></div></div>
            </div>
          </div>
        </div>
        <aside class="sv-inv-side">
          <section class="sv-inv-side-card"><h3>Stav faktury</h3><span class="sv-inv-badge sv-inv-badge--created">Vytvořena</span><p class="sv-inv-side-desc">Faktura byla úspěšně vytvořena.</p></section>
          <section class="sv-inv-side-card"><h3>Náhled faktury</h3><button type="button" class="sv-inv-btn sv-inv-btn--secondary sv-inv-btn--block" onclick="window.${API}.openPreview()">Zobrazit náhled</button></section>
          <section class="sv-inv-side-card"><h3>Souhrn</h3><div class="sv-inv-side-summary">
            <div class="sv-inv-side-summary-row"><span>Celkem k úhradě</span><strong>${esc(money(totals.total))}</strong></div>
          </div></section>
          <section class="sv-inv-side-card sv-inv-tip"><span>💡</span><div>Fakturu můžete upravit, dokud není odeslána.</div></section>
        </aside>
      </div>`;
  }

  function renderPreviewModal() {
    if (!state.previewModal) return '';
    const legacy = draftToLegacy(state.draft);
    const zoom = state.previewZoom || 100;
    const docHtml = typeof window.UserInvoicesDashboard?.renderDocumentHtml === 'function'
      ? window.UserInvoicesDashboard.renderDocumentHtml(legacy, { a4: true })
      : renderDocumentHtml(legacy, { a4: true });
    return `
      <div class="sv-inv-modal-backdrop sv-inv-modal-backdrop--dark" onclick="if(event.target===this) window.${API}.closePreview()">
        <div class="sv-inv-modal sv-inv-modal--wide sv-inv-modal--pdf" role="dialog" onclick="event.stopPropagation()">
          <div class="sv-inv-modal-head"><h2 class="sv-inv-modal-title">Náhled faktury</h2><button type="button" class="sv-inv-modal-close" onclick="window.${API}.closePreview()">×</button></div>
          <div class="sv-inv-modal-toolbar">
            <div class="sv-inv-modal-toolbar-group"><button type="button" class="sv-inv-toolbar-btn" disabled>‹</button><span class="sv-inv-toolbar-pages">1 / 1</span><button type="button" class="sv-inv-toolbar-btn" disabled>›</button></div>
            <div class="sv-inv-modal-toolbar-group"><button type="button" class="sv-inv-toolbar-btn" onclick="window.${API}.zoomOut()">−</button><span class="sv-inv-toolbar-zoom">${zoom} %</span><button type="button" class="sv-inv-toolbar-btn" onclick="window.${API}.zoomIn()">+</button></div>
            <div class="sv-inv-modal-toolbar-group sv-inv-modal-toolbar-actions"><button type="button" class="sv-inv-toolbar-btn" onclick="window.${API}.downloadPdf()" title="Stáhnout">↓</button><button type="button" class="sv-inv-toolbar-btn" onclick="window.${API}.printPreview()" title="Tisk">🖨</button></div>
          </div>
          <div class="sv-inv-modal-body sv-inv-modal-body--a4"><div class="sv-inv-a4-viewport"><div class="sv-inv-a4-sheet" style="transform:scale(${zoom / 100})">${docHtml}</div></div></div>
          <div class="sv-inv-modal-foot"><button type="button" class="sv-inv-btn sv-inv-btn--secondary" onclick="window.${API}.closePreview()">Zavřít</button></div>
        </div>
      </div>`;
  }

  function renderWizardHtml() {
    const step = state.step;
    let body = formStepHtml();
    if (step === 3) body = previewStepHtml();
    if (step === 4) body = doneStepHtml();
    let footer = '';
    if (step === 1) {
      footer = '';
    } else if (step === 3) {
      footer = `<div class="sv-inv-sticky-bar"><button type="button" class="sv-inv-btn sv-inv-btn--ghost" onclick="window.${API}.goStep(1)">Zpět: Položky faktury</button>
        <div class="sv-inv-sticky-bar-actions"><button type="button" class="sv-inv-btn sv-inv-btn--secondary" onclick="window.${API}.saveDraft()">Uložit koncept</button>
        <button type="button" class="sv-inv-btn sv-inv-btn--primary sv-inv-btn--split" onclick="window.${API}.finalize()">Odeslat fakturu</button>
        <button type="button" class="sv-inv-btn sv-inv-btn--primary sv-inv-btn-chevron" aria-label="Další možnosti">▾</button></div></div>`;
    } else if (step === 4) {
      footer = `<div class="sv-inv-sticky-bar"><button type="button" class="sv-inv-btn sv-inv-btn--ghost" onclick="window.${API}.backToList()">Zpět na přehled faktur</button>
        <button type="button" class="sv-inv-btn sv-inv-btn--primary sv-inv-btn--with-plus" onclick="window.${API}.startNew()">+ Vytvořit další fakturu</button></div>`;
    }
    const showStepper = step >= 3;
    const stepperStep = step === 4 ? 4 : step;
    const pageHead = step === 1 ? '' : `<div class="sv-inv-page-head"><div><h1>Nová faktura <span class="sv-inv-badge sv-inv-badge--draft">Koncept</span></h1></div>
          <div class="sv-inv-head-actions"><button type="button" class="sv-inv-btn sv-inv-btn--secondary" onclick="window.${API}.saveDraft()">Uložit koncept</button></div></div>`;
    return `
      <div class="sv-inv sv-inv-page sv-inv-page--wizard sv-inv-page--wizard-step-${step}" data-testid="user-invoice-wizard">
        <nav class="sv-inv-breadcrumb"><button type="button" onclick="window.UserInvoicesDashboard.goOverview()">Přehled</button><span>/</span><button type="button" onclick="window.${API}.backToList()">Faktury</button><span>/</span><span>Nová faktura</span></nav>
        ${pageHead}
        ${showStepper ? stepperHtml(stepperStep) : ''}
        ${body}${footer}${renderPreviewModal()}
      </div>`;
  }

  function paint() {
    const el = state.mountEl;
    if (!el) return;
    el.innerHTML = renderWizardHtml();
    document.body.classList.toggle('sv-inv-modal-open', !!state.previewModal);
  }

  function navigateInvoiceNew() {
    const slug = window.lastWorkspaceMePayload?.account_slug;
    if (slug && typeof buildAppWorkspacePath === 'function') {
      workspaceHistoryPush(buildAppWorkspacePath('u', slug, 'invoice-new'));
    }
  }

  const api = {
    getLocalInvoices() {
      return loadStore().invoices || [];
    },
    getLocalInvoice(id) {
      return (loadStore().invoices || []).find((x) => x.id === id) || null;
    },
    deleteLocalInvoice(id) {
      const store = loadStore();
      store.invoices = (store.invoices || []).filter((x) => x.id !== id);
      saveStore(store);
    },
    getAppearance,
    saveAppearance,
    draftToLegacy,
    renderDocumentHtml,
    invoiceCalc,
    mountWizard(el, draftId) {
      state.mountEl = el;
      state.step = 1;
      state.previewModal = false;
      state.attachments = [];
      if (draftId) {
        const found = api.getLocalInvoice(draftId);
        state.draft = found ? { ...found } : defaultDraft();
        state.draftId = draftId;
      } else {
        state.draft = defaultDraft();
        state.draftId = null;
      }
      paint();
    },
    startNew() {
      state.draft = defaultDraft();
      state.draftId = null;
      state.step = 1;
      navigateInvoiceNew();
      paint();
    },
    goStep(n) {
      if (n === 1) readFormIntoDraft();
      state.step = Number(n) || 1;
      paint();
    },
    recalcSidebar() {
      readFormIntoDraft();
      const legacy = draftToLegacy(state.draft);
      const totals = invoiceCalc(legacy.lines);
      const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
      set('uInvSumSub', money(totals.subtotal));
      set('uInvSumDisc', money(totals.discountTotal));
      set('uInvSumBase', money(totals.base));
      set('uInvSumVat', money(totals.tax));
      set('uInvSumTotal', money(totals.total));
    },
    addLine() {
      readFormIntoDraft();
      const items = state.draft.items || [];
      items.push({ id: items.length + 1, name: '', description: '', quantity: 1, unit: 'ks', unit_price: 0, discount_percent: 0, vat_rate: 21, total_without_vat: 0 });
      state.draft.items = items;
      paint();
    },
    removeLine(idx) {
      readFormIntoDraft();
      state.draft.items = (state.draft.items || []).filter((_, i) => i !== idx);
      paint();
    },
    toggleCustSame() {
      state.customerSameAsSupplier = !!document.getElementById('uInvCustSame')?.checked;
      if (state.customerSameAsSupplier) readFormIntoDraft();
      paint();
    },
    onFileSelect(e) {
      const files = Array.from(e.target?.files || []);
      files.forEach((f) => { if (f.size <= 10 * 1024 * 1024) state.attachments.push({ name: f.name, size: f.size }); });
      paint();
    },
    onFileDrop(e) {
      e.preventDefault();
      api.onFileSelect({ target: { files: e.dataTransfer?.files } });
    },
    saveDraft() {
      try {
        readFormIntoDraft();
        const errs = validateDraft(state.draft);
        if (errs.length) { showToast(errs[0], 'warning'); return; }
        persistDraft('draft');
        showToast('Koncept faktury byl uložen (staging localStorage).', 'success');
      } catch (e) {
        showToast(e?.message || 'Uložení selhalo', 'error');
      }
    },
    createInvoice() {
      readFormIntoDraft();
      const errs = validateDraft(state.draft);
      if (errs.length) { showToast(errs[0], 'warning'); return; }
      persistDraft('draft');
      state.step = 3;
      paint();
    },
    finalize() {
      persistDraft('created');
      state.step = 4;
      auditLog('invoice_created', state.draftId);
      paint();
    },
    cancel() {
      if (window.confirm('Zrušit vytváření faktury? Neuložené změny budou ztraceny.')) api.backToList();
    },
    backToList() {
      if (typeof window.UserInvoicesDashboard?.showList === 'function') {
        window.UserInvoicesDashboard.showList();
      }
    },
    openPreview() {
      readFormIntoDraft();
      state.previewModal = true;
      state.previewZoom = 100;
      auditLog('invoice_preview_open', state.draftId);
      paint();
    },
    closePreview() {
      state.previewModal = false;
      paint();
    },
    zoomIn() { state.previewZoom = Math.min(200, (state.previewZoom || 100) + 10); paint(); },
    zoomOut() { state.previewZoom = Math.max(50, (state.previewZoom || 100) - 10); paint(); },
    downloadPdf() {
      auditLog('invoice_pdf_download', state.draftId);
      showToast('Stažení PDF: Tato funkce čeká na backend API. Otevírám tisk pro uložení jako PDF.', 'info');
      api.openPreview();
      window.setTimeout(() => api.printPreview(), 500);
    },
    printPreview() {
      auditLog('invoice_pdf_print', state.draftId);
      window.print();
    },
    sendEmail() {
      const d = state.draft || {};
      const email = d.customer?.email;
      if (!email) { showToast('U odběratele chybí e-mail.', 'warning'); return; }
      auditLog('invoice_email_send', state.draftId);
      const subject = encodeURIComponent(`Faktura ${d.number || ''}`);
      const body = encodeURIComponent(`Dobrý den,\n\nzasíláme fakturu ${d.number || ''}.\n\n`);
      window.location.href = `mailto:${email}?subject=${subject}&body=${body}`;
    },
    shareLink() {
      auditLog('invoice_share_link', state.draftId);
      const token = btoa(`${state.draftId}:${Date.now()}`).replace(/[^a-zA-Z0-9]/g, '').slice(0, 24);
      const slug = window.lastWorkspaceMePayload?.account_slug || '';
      const url = `${window.location.origin}${typeof toBrowserAppPath === 'function' ? toBrowserAppPath(`/app/u/${slug}/invoices`) : ''}?local_inv=${token}`;
      try {
        localStorage.setItem(`sv_inv_share_${token}`, JSON.stringify({ id: state.draftId, created: Date.now() }));
        navigator.clipboard.writeText(url);
        showToast('Odkaz zkopírován (lokální staging token).', 'success');
      } catch (e) {
        showToast(url, 'info');
      }
    },
    scheduleSend() {
      blockerToast('Naplánované odeslání');
    },
    paint,
  };

  window.UserInvoicesWorkflow = api;

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && state.previewModal) {
      state.previewModal = false;
      paint();
    }
  });
})();
