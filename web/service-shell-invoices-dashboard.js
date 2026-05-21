/**
 * Správa vozidel — modul Faktury (1:1 referenční UI, servisní shell).
 * Napojení: window.ServiceInvoicesDashboard + window.serviceShell.*
 */
(function () {
  'use strict';

  const WIZARD_STEPS = [
    { n: 1, key: 'basic', label: 'Základní informace' },
    { n: 2, key: 'items', label: 'Položky faktury' },
    { n: 3, key: 'preview', label: 'Náhled a odeslání' },
    { n: 4, key: 'done', label: 'Dokončeno' },
  ];

  function shell() {
    return window.serviceShell;
  }

  function isUserInvoiceMode() {
    return String(shell()?.invoiceMode || '').toLowerCase() === 'user';
  }

  function invoiceApiBase() {
    return String(shell()?.invoiceApiBase || '/api/service/invoices').replace(/\/$/, '');
  }

  function invoiceApiUrl(suffix = '') {
    const base = invoiceApiBase();
    const tail = String(suffix || '').replace(/^\//, '');
    return tail ? `${base}/${tail}` : base;
  }

  function st() {
    return shell()?.state || {};
  }

  function esc(v) {
    return String(v ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function money(value, currency) {
    if (shell()?.invoiceMoney) return shell().invoiceMoney(value, currency);
    const n = Number(value || 0);
    return `${n.toLocaleString('cs-CZ', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${currency || 'CZK'}`;
  }

  function fmtDate(value) {
    if (shell()?.formatDate) return shell().formatDate(value);
    if (!value) return '—';
    try {
      return new Date(value).toLocaleDateString('cs-CZ');
    } catch (e) {
      return String(value);
    }
  }

  function fmtDateLong(value) {
    if (!value) return '—';
    try {
      const d = new Date(value);
      return `${d.getDate()}. ${d.getMonth() + 1}. ${d.getFullYear()}`;
    } catch (e) {
      return fmtDate(value);
    }
  }

  function showToast(msg, kind) {
    if (typeof window.showAlert === 'function') window.showAlert(msg, kind || 'info');
    else if (shell()?.showToast) shell().showToast(msg, kind);
  }

  function navigate(section, opts) {
    if (shell()?.navigate) shell().navigate(section, opts || {});
  }

  function render() {
    if (shell()?.render) shell().render();
  }

  function ensureWizardState() {
    const s = st();
    if (!s.invoiceWizard) {
      s.invoiceWizard = {
        step: 1,
        draftId: null,
        draft: null,
        saving: false,
      };
    }
    if (!s.invoiceListTab) s.invoiceListTab = 'overview';
    if (!s.invoicePage) s.invoicePage = 1;
    if (!s.invoicePerPage) s.invoicePerPage = 10;
    if (!s.invoicePreviewModalId) s.invoicePreviewModalId = null;
    return s.invoiceWizard;
  }

  function statusKey(inv) {
    return String(inv?.status || '').trim().toLowerCase();
  }

  function displayStatus(inv) {
    const key = statusKey(inv);
    if (key === 'draft') return { label: 'Koncept', cls: 'draft' };
    if (key === 'cancelled') return { label: 'Zrušeno', cls: 'overdue' };
    const extra = inv?.extra || {};
    if (inv?.already_paid || extra.already_paid) return { label: 'Zaplaceno', cls: 'paid' };
    const due = inv?.due_at ? new Date(inv.due_at) : null;
    if (due && due < new Date(new Date().toDateString())) {
      return { label: 'Po splatnosti', cls: 'overdue' };
    }
    return { label: 'Čeká na úhradu', cls: 'pending' };
  }

  function computeStats(invoices) {
    const list = Array.isArray(invoices) ? invoices : [];
    let issuedTotal = 0;
    let issuedCount = 0;
    let paidTotal = 0;
    let paidCount = 0;
    let pendingTotal = 0;
    let pendingCount = 0;
    let overdueTotal = 0;
    let overdueCount = 0;
    list.forEach((inv) => {
      const key = statusKey(inv);
      if (key !== 'issued') return;
      const total = Number(inv?.total || 0);
      issuedTotal += total;
      issuedCount += 1;
      const ds = displayStatus(inv);
      if (ds.cls === 'paid') {
        paidTotal += total;
        paidCount += 1;
      } else if (ds.cls === 'overdue') {
        overdueTotal += total;
        overdueCount += 1;
      } else if (ds.cls === 'pending') {
        pendingTotal += total;
        pendingCount += 1;
      }
    });
    return { issuedTotal, issuedCount, paidTotal, paidCount, pendingTotal, pendingCount, overdueTotal, overdueCount };
  }

  function filteredListInvoices() {
    const s = st();
    const tab = String(s.invoiceListTab || 'overview');
    const q = String(s.invoiceSearchTerm || '').trim().toLowerCase();
    const statusF = String(s.invoiceStatusFilter || 'all').toLowerCase();
    let list = Array.isArray(s.invoices) ? [...s.invoices] : [];
    if (tab === 'drafts') {
      list = list.filter((inv) => statusKey(inv) === 'draft');
    } else {
      list = list.filter((inv) => statusKey(inv) !== 'draft');
    }
    if (statusF === 'draft') list = list.filter((inv) => statusKey(inv) === 'draft');
    if (statusF === 'issued') list = list.filter((inv) => statusKey(inv) === 'issued');
    if (statusF === 'cancelled') list = list.filter((inv) => statusKey(inv) === 'cancelled');
    if (q) {
      list = list.filter((inv) => {
        const hay = [
          inv?.invoice_number,
          inv?.customer_label,
          inv?.vehicle_label,
          inv?.extra?.variable_symbol,
        ]
          .join(' ')
          .toLowerCase();
        return hay.includes(q);
      });
    }
    return list;
  }

  function paginate(list) {
    const s = st();
    const per = Math.max(1, Number(s.invoicePerPage || 10));
    const page = Math.max(1, Number(s.invoicePage || 1));
    const total = list.length;
    const pages = Math.max(1, Math.ceil(total / per));
    const p = Math.min(page, pages);
    const start = (p - 1) * per;
    return { slice: list.slice(start, start + per), page: p, pages, total, per };
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
      tax += net * (Number(ln?.tax_rate || 0) / 100);
    });
    const base = subtotal - discountTotal;
    const total = base + tax;
    return {
      subtotal: Math.round(subtotal * 100) / 100,
      discountTotal: Math.round(discountTotal * 100) / 100,
      base: Math.round(base * 100) / 100,
      tax: Math.round(tax * 100) / 100,
      total: Math.round(total * 100) / 100,
    };
  }

  function defaultDraftFromProfile() {
    const prof = isUserInvoiceMode()
      ? (window.userProfile || window.currentUser || st().profile || {})
      : (st().profile || {});
    const profileStreet = [prof?.street, prof?.street_number].filter(Boolean).join(' ').trim();
    const today = new Date().toISOString().slice(0, 10);
    const due = new Date();
    due.setDate(due.getDate() + 14);
    return {
      customer_id: isUserInvoiceMode() ? null : null,
      vehicle_id: null,
      currency: 'CZK',
      due_at: due.toISOString().slice(0, 10),
      notes: '',
      status: 'draft',
      status_label: 'Koncept',
      lines: [],
      extra: {
        invoice_type: '1',
        payment_method: 'prevod',
        issue_date: today,
        delivery_date: today,
        variable_symbol: '',
        constant_symbol: '0308',
        specific_symbol: '',
        language: 'CS',
        qr: true,
        supplier_name: prof?.name || window.currentUser?.name || '',
        supplier_email: prof?.email || window.currentUser?.email || '',
        supplier_ico: prof?.ico || window.currentUser?.ico || '',
        supplier_dic: prof?.dic || window.currentUser?.dic || '',
        supplier_street: profileStreet || '',
        supplier_city: prof?.city || '',
        supplier_zip: prof?.zip || '',
        supplier_phone: prof?.phone || '',
        supplier_bank: 'Fio banka',
        supplier_bankaccount: '',
        supplier_iban: '',
        supplier_swift: '',
        customer_name: '',
        customer_ico: '',
        customer_dic: '',
        customer_street: '',
        customer_city: '',
        customer_zip: '',
        customer_email: '',
        customer_phone: '',
      },
    };
  }

  function customerById(id) {
    const cid = Number(id || 0);
    return (Array.isArray(st().customers) ? st().customers : []).find((c) => Number(c?.customer_id) === cid);
  }

  function fillCustomerFromLink(draft) {
    const c = customerById(draft.customer_id);
    if (!c) return draft;
    const extra = { ...(draft.extra || {}) };
    if (!extra.customer_name) extra.customer_name = c?.name || c?.company_name || '';
    if (!extra.customer_email) extra.customer_email = c?.email || '';
    if (!extra.customer_phone) extra.customer_phone = c?.phone || '';
    if (!extra.customer_ico) extra.customer_ico = c?.ico || '';
    if (!extra.customer_dic) extra.customer_dic = c?.dic || '';
    return { ...draft, extra };
  }

  function payloadFromWizardDraft(draft) {
    const d = isUserInvoiceMode() ? draft : fillCustomerFromLink(draft);
    const lines = (Array.isArray(d.lines) ? d.lines : [])
      .filter((ln) => String(ln?.description || '').trim() && Number(ln?.quantity) > 0)
      .map((ln) => {
        const disc = Number(ln?.discount_percent || 0);
        const effPrice = Number(ln?.unit_price || 0) * (1 - disc / 100);
        return {
          description: String(ln.description).trim(),
          quantity: Number(ln.quantity),
          unit: String(ln.unit || 'ks').trim() || 'ks',
          unit_price: Math.round(effPrice * 100) / 100,
          tax_rate: Number(ln.tax_rate || 21),
        };
      });
    if (isUserInvoiceMode()) {
      return {
        non_vehicle_invoice: true,
        vehicle_id: null,
        currency: d.currency || 'CZK',
        due_at: d.due_at || null,
        notes: d.notes || null,
        extra: d.extra || {},
        lines,
      };
    }
    return {
      customer_id: Number(d.customer_id || 0),
      vehicle_id: d.vehicle_id ? Number(d.vehicle_id) : null,
      non_vehicle_invoice: !d.vehicle_id,
      currency: d.currency || 'CZK',
      due_at: d.due_at || null,
      notes: d.notes || null,
      extra: d.extra || {},
      lines,
    };
  }

  function spaydString(inv, totals) {
    const extra = inv?.extra || {};
    const iban = String(extra.supplier_iban || '').replace(/\s/g, '');
    const acc = String(extra.supplier_bankaccount || '').replace(/\s/g, '');
    const amount = (totals?.total ?? inv?.total ?? 0).toFixed(2);
    const vs = String(extra.variable_symbol || inv?.invoice_number || '').replace(/\D/g, '').slice(-10);
    if (!iban && !acc) return '';
    const accPart = iban ? `ACC:${iban}` : `ACC:${acc}`;
    return `SPD*1.0*${accPart}*AM:${amount}*CC:CZK*X-VS:${vs || '0'}`;
  }

  function qrImgUrl(spayd) {
    if (!spayd) return '';
    return `https://api.qrserver.com/v1/create-qr-code/?size=100x100&data=${encodeURIComponent(spayd)}`;
  }

  function lineIconHtml(description) {
    const d = String(description || '').toLowerCase();
    if (d.includes('olej') || d.includes('filtr')) {
      return '<span class="sv-inv-line-ico sv-inv-line-ico--oil" aria-hidden="true">💧</span>';
    }
    if (d.includes('brzd') || d.includes('destič')) {
      return '<span class="sv-inv-line-ico sv-inv-line-ico--brake" aria-hidden="true">◎</span>';
    }
    if (d.includes('práce') || d.includes('mechanik') || d.includes('servis')) {
      return '<span class="sv-inv-line-ico sv-inv-line-ico--work" aria-hidden="true">⚙</span>';
    }
    return '<span class="sv-inv-line-ico" aria-hidden="true">▣</span>';
  }

  function renderDocumentHtml(inv, opts) {
    const extra = inv?.extra || {};
    const lines = Array.isArray(inv?.lines) ? inv.lines : [];
    const totals = invoiceCalc(lines.length ? lines : inv?.lines || []);
    const spayd = spaydString(inv, totals);
    const invNo = inv?.invoice_number || '(koncept)';
    const appName = 'Správa vozidel';
    const compact = opts?.compact;
    const supplierAddr = [extra.supplier_street, extra.supplier_zip, extra.supplier_city].filter(Boolean).join(', ');
    const customerAddr = [extra.customer_street, extra.customer_zip, extra.customer_city].filter(Boolean).join(', ');
    const noteText =
      inv?.notes ||
      'Děkujeme za spolupráci. Uhraďte prosím na účet uvedený níže s variabilním symbolem do data splatnosti.';

    return `
      <div class="sv-inv-doc ${compact ? 'sv-inv-doc--compact' : ''}">
        <div class="sv-inv-doc-header">
          <div class="sv-inv-doc-brand">
            <span class="sv-inv-doc-brand-mark" aria-hidden="true">🛡</span>
            <div>
              <strong class="sv-inv-doc-brand-name">${esc(appName)}</strong>
              <div class="sv-inv-doc-brand-sub">Faktura vystavená v aplikaci</div>
            </div>
          </div>
          <div class="sv-inv-doc-head-right">
            <div class="sv-inv-doc-title">FAKTURA</div>
            <span class="sv-inv-doc-number">${esc(invNo)}</span>
          </div>
        </div>
        <div class="sv-inv-doc-parties-row">
          <div class="sv-inv-doc-party-block">
            <h4 class="sv-inv-doc-party-label"><span aria-hidden="true">👤</span> DODAVATEL</h4>
            <p class="sv-inv-doc-party-name">${esc(extra.supplier_name || '—')}</p>
            <p>${esc(supplierAddr || '—')}</p>
            <p>IČO: ${esc(extra.supplier_ico || '—')}</p>
            <p>DIČ: ${esc(extra.supplier_dic || '—')}</p>
            <p class="sv-inv-doc-contact">✉ ${esc(extra.supplier_email || '—')}</p>
            <p class="sv-inv-doc-contact">☎ ${esc(extra.supplier_phone || '—')}</p>
          </div>
          <div class="sv-inv-doc-party-block">
            <h4 class="sv-inv-doc-party-label"><span aria-hidden="true">👤</span> ODBĚRATEL</h4>
            <p class="sv-inv-doc-party-name">${esc(extra.customer_name || inv?.customer_label || '—')}</p>
            <p>${esc(customerAddr || '—')}</p>
            <p>IČO: ${esc(extra.customer_ico || '—')}</p>
            <p>DIČ: ${esc(extra.customer_dic || '—')}</p>
            <p class="sv-inv-doc-contact">✉ ${esc(extra.customer_email || '—')}</p>
            <p class="sv-inv-doc-contact">☎ ${esc(extra.customer_phone || '—')}</p>
          </div>
          <div class="sv-inv-doc-meta-panel">
            <div class="sv-inv-doc-meta-line"><span>📅</span><div><em>Datum vystavení</em><strong>${esc(fmtDateLong(extra.issue_date || inv?.issued_at))}</strong></div></div>
            <div class="sv-inv-doc-meta-line"><span>📅</span><div><em>Datum zdanitelného plnění</em><strong>${esc(fmtDateLong(extra.delivery_date || extra.issue_date))}</strong></div></div>
            <div class="sv-inv-doc-meta-line"><span>📅</span><div><em>Datum splatnosti</em><strong class="is-due">${esc(fmtDateLong(inv?.due_at))}</strong></div></div>
            <div class="sv-inv-doc-meta-line"><span>📄</span><div><em>Forma úhrady</em><strong>Bankovní převod</strong></div></div>
            <div class="sv-inv-doc-meta-line"><span>#</span><div><em>Variabilní symbol</em><strong>${esc(extra.variable_symbol || '—')}</strong></div></div>
            <div class="sv-inv-doc-meta-line"><span>#</span><div><em>Konstantní symbol</em><strong>${esc(extra.constant_symbol || '—')}</strong></div></div>
            <div class="sv-inv-doc-meta-line"><span>#</span><div><em>Specifický symbol</em><strong>${esc(extra.specific_symbol || '—')}</strong></div></div>
          </div>
        </div>
        <h3 class="sv-inv-doc-section-title">Položky faktury</h3>
        <div class="sv-inv-table-wrap">
          <table class="sv-inv-table sv-inv-lines-table">
            <thead><tr>
              <th>#</th><th>Položka / Popis</th><th>Množství</th><th>Jedn.</th>
              <th>Cena za jedn.</th><th>Sleva</th><th>DPH</th><th>Celkem bez DPH</th>
            </tr></thead>
            <tbody>
              ${lines
                .map((ln, i) => {
                  const net = lineNet(ln);
                  const disc = Number(ln?.discount_percent || 0);
                  return `<tr>
                    <td>${i + 1}</td>
                    <td>
                      <div class="sv-inv-line-desc-cell">${lineIconHtml(ln.description)}
                        <div><div class="sv-inv-cell-primary">${esc(ln.description)}</div>${ln.note ? `<div class="sv-inv-cell-sub">${esc(ln.note)}</div>` : ''}</div>
                      </div>
                    </td>
                    <td>${esc(ln.quantity)}</td>
                    <td>${esc(ln.unit)}</td>
                    <td>${esc(money(ln.unit_price, inv.currency))}</td>
                    <td>${disc ? `<span class="sv-inv-discount">${disc} %</span>` : '—'}</td>
                    <td>${esc(ln.tax_rate)} %</td>
                    <td>${esc(money(net, inv.currency))}</td>
                  </tr>`;
                })
                .join('') || '<tr><td colspan="8">Bez položek</td></tr>'}
            </tbody>
          </table>
        </div>
        <div class="sv-inv-doc-footer-pay">
          <div class="sv-inv-pay-box">
            <strong class="sv-inv-pay-title">Platební údaje</strong>
            <p><span class="sv-inv-pay-lbl">Banka</span> ${esc(extra.supplier_bank || 'Fio banka')}</p>
            <p><span class="sv-inv-pay-lbl">Číslo účtu</span> ${esc(extra.supplier_bankaccount || '—')}</p>
            <p><span class="sv-inv-pay-lbl">IBAN</span> ${esc(extra.supplier_iban || '—')}</p>
            <p><span class="sv-inv-pay-lbl">BIC/SWIFT</span> ${esc(extra.supplier_swift || '—')}</p>
            ${spayd ? `<div class="sv-inv-pay-qr-row"><div class="sv-inv-qr"><img src="${esc(qrImgUrl(spayd))}" alt="QR Platba" width="100" height="100"></div><span class="sv-inv-pay-qr-label">QR Platba</span></div>` : ''}
          </div>
          <div class="sv-inv-doc-totals-wrap">
            <table class="sv-inv-totals-table">
              <tbody>
                <tr><td>Mezisoučet bez DPH</td><td>${esc(money(totals.subtotal, inv.currency))}</td></tr>
                <tr><td>Sleva celkem</td><td class="sv-inv-discount">-${esc(money(totals.discountTotal, inv.currency))}</td></tr>
                <tr><td>Základ DPH</td><td>${esc(money(totals.base, inv.currency))}</td></tr>
                <tr><td>DPH (21 %)</td><td>${esc(money(totals.tax, inv.currency))}</td></tr>
              </tbody>
            </table>
            <div class="sv-inv-totals-box">
              <div class="sv-inv-totals-label">CELKEM K ÚHRADĚ</div>
              <div class="grand">${esc(money(totals.total, inv.currency))}</div>
            </div>
          </div>
        </div>
        <div class="sv-inv-doc-footer-notes">
          <div class="sv-inv-thanks">
            <span class="sv-inv-thanks-ico" aria-hidden="true">🛡</span>
            <div><strong>Děkujeme za spolupráci!</strong> Faktura byla vytvořena v aplikaci ${esc(appName)}.</div>
          </div>
          <div class="sv-inv-doc-note-box">
            <strong>Poznámka</strong>
            <p>${esc(noteText)}</p>
          </div>
          <div class="sv-inv-doc-signature">
            <div class="sv-inv-doc-signature-line"></div>
            <div class="sv-inv-doc-signature-name">${esc(extra.supplier_name || appName)}</div>
          </div>
        </div>
        <div class="sv-inv-doc-bar">
          <span>✓ Vytvořeno v aplikaci ${esc(appName)}</span>
          <span>›</span><span>🔒 Bezpečně a online</span>
          <span>›</span><span>☁ Rychle a přehledně</span>
          <span>›</span><span>🌿 Šetříme čas i přírodu</span>
        </div>
      </div>`;
  }

  function wizardReviewPartyCard(title, data, editStep) {
    return `
      <div class="sv-inv-review-party">
        <div class="sv-inv-review-party-head">
          <h3>${esc(title)}</h3>
          <button type="button" class="sv-inv-edit-link" onclick="window.serviceShell.setInvoiceWizardStep(${editStep})">✎ Upravit</button>
        </div>
        ${data}
      </div>`;
  }

  function wizardLinesTableHtml(draft) {
    const lines = Array.isArray(draft.lines) ? draft.lines : [];
    const currency = draft.currency || 'CZK';
    return `
      <div class="sv-inv-card sv-inv-section-card">
        <div class="sv-inv-section-head">
          <h2>Položky faktury</h2>
          <button type="button" class="sv-inv-edit-link" onclick="window.serviceShell.setInvoiceWizardStep(2)">✎ Upravit</button>
        </div>
        <div class="sv-inv-table-wrap">
          <table class="sv-inv-table">
            <thead><tr>
              <th>Položka / Popis</th><th>Množství</th><th>Jedn.</th><th>Cena za jedn.</th><th>Sleva</th><th>DPH</th><th>Celkem bez DPH</th>
            </tr></thead>
            <tbody>
              ${lines
                .map((ln) => {
                  const net = lineNet(ln);
                  const disc = Number(ln?.discount_percent || 0);
                  return `<tr>
                    <td><div class="sv-inv-line-desc-cell">${lineIconHtml(ln.description)}<div><strong>${esc(ln.description)}</strong>${ln.note ? `<div class="sv-inv-cell-sub">${esc(ln.note)}</div>` : ''}</div></div></td>
                    <td>${esc(ln.quantity)}</td><td>${esc(ln.unit)}</td>
                    <td>${esc(money(ln.unit_price, currency))}</td>
                    <td>${disc ? `${disc} %` : '—'}</td><td>${esc(ln.tax_rate)} %</td>
                    <td><strong>${esc(money(net, currency))}</strong></td>
                  </tr>`;
                })
                .join('') || '<tr><td colspan="7" class="sv-inv-table-empty">Bez položek</td></tr>'}
            </tbody>
          </table>
        </div>
        <button type="button" class="sv-inv-btn sv-inv-btn--ghost" style="margin-top:12px;" onclick="window.serviceShell.setInvoiceWizardStep(2)">+ Přidat položku</button>
      </div>`;
  }

  function wizardSummaryHtml(draft) {
    const totals = invoiceCalc(draft.lines || []);
    const currency = draft.currency || 'CZK';
    return `
      <div class="sv-inv-card sv-inv-section-card sv-inv-summary-card">
        <h2>Souhrn</h2>
        <div class="sv-inv-summary-rows">
          <div class="sv-inv-summary-row"><span>Mezisoučet bez DPH</span><strong>${esc(money(totals.subtotal, currency))}</strong></div>
          <div class="sv-inv-summary-row"><span>Sleva celkem</span><strong class="sv-inv-discount">-${esc(money(totals.discountTotal, currency))}</strong></div>
          <div class="sv-inv-summary-row"><span>Základ DPH</span><strong>${esc(money(totals.base, currency))}</strong></div>
          <div class="sv-inv-summary-row"><span>DPH (21 %)</span><strong>${esc(money(totals.tax, currency))}</strong></div>
        </div>
        <div class="sv-inv-summary-total">
          <span>Celkem k úhradě</span>
          <strong>${esc(money(totals.total, currency))}</strong>
        </div>
      </div>`;
  }

  function stepperHtml(currentStep) {
    const parts = [];
    WIZARD_STEPS.forEach((step, idx) => {
      const done = currentStep > step.n;
      const active = currentStep === step.n;
      parts.push(`
        <div class="sv-inv-step ${done ? 'is-done' : ''} ${active ? 'is-active' : ''}">
          <div class="sv-inv-step-dot">${done ? '✓' : step.n}</div>
          <span class="sv-inv-step-label">${esc(step.label)}</span>
        </div>`);
      if (idx < WIZARD_STEPS.length - 1) {
        parts.push(`<div class="sv-inv-step-line ${currentStep > step.n ? 'is-done' : ''}"></div>`);
      }
    });
    return `<div class="sv-inv-stepper">${parts.join('')}</div>`;
  }

  function wizardBreadcrumb(extra) {
    return `
      <nav class="sv-inv-breadcrumb" aria-label="Drobečková navigace">
        <button type="button" onclick="window.serviceShell.navigate('dashboard')">Přehled</button>
        <span>/</span>
        <button type="button" onclick="window.serviceShell.navigate('invoices')">Faktury</button>
        <span>/</span>
        <span>${esc(extra || 'Nová faktura')}</span>
      </nav>`;
  }

  function readWizardFormIntoDraft() {
    const w = ensureWizardState();
    const draft = { ...(w.draft || defaultDraftFromProfile()) };
    const extra = { ...(draft.extra || {}) };
    const get = (id) => document.getElementById(id)?.value;
    draft.customer_id = isUserInvoiceMode() ? null : (Number(get('svInvCustomer') || draft.customer_id || 0) || null);
    draft.vehicle_id = isUserInvoiceMode() ? null : (Number(get('svInvVehicle') || 0) || null);
    draft.due_at = get('svInvDueAt') || draft.due_at;
    draft.notes = get('svInvNotes') || '';
    draft.currency = get('svInvCurrency') || 'CZK';
    extra.issue_date = get('svInvIssueDate') || extra.issue_date;
    extra.delivery_date = get('svInvDeliveryDate') || extra.delivery_date;
    extra.payment_method = get('svInvPayment') || extra.payment_method;
    extra.variable_symbol = get('svInvVs') || extra.variable_symbol;
    extra.constant_symbol = get('svInvKs') || extra.constant_symbol;
    extra.supplier_name = get('svInvSupName') || extra.supplier_name;
    extra.supplier_ico = get('svInvSupIco') || extra.supplier_ico;
    extra.supplier_dic = get('svInvSupDic') || extra.supplier_dic;
    extra.supplier_street = get('svInvSupStreet') || extra.supplier_street;
    extra.supplier_city = get('svInvSupCity') || extra.supplier_city;
    extra.supplier_zip = get('svInvSupZip') || extra.supplier_zip;
    extra.supplier_email = get('svInvSupEmail') || extra.supplier_email;
    extra.supplier_phone = get('svInvSupPhone') || extra.supplier_phone;
    extra.supplier_bank = get('svInvSupBank') || extra.supplier_bank;
    extra.supplier_bankaccount = get('svInvSupAccount') || extra.supplier_bankaccount;
    extra.supplier_iban = get('svInvSupIban') || extra.supplier_iban;
    extra.supplier_swift = get('svInvSupSwift') || extra.supplier_swift;
    extra.customer_name = get('svInvCustName') || extra.customer_name;
    extra.customer_ico = get('svInvCustIco') || extra.customer_ico;
    extra.customer_dic = get('svInvCustDic') || extra.customer_dic;
    extra.customer_street = get('svInvCustStreet') || extra.customer_street;
    extra.customer_city = get('svInvCustCity') || extra.customer_city;
    extra.customer_zip = get('svInvCustZip') || extra.customer_zip;
    extra.customer_email = get('svInvCustEmail') || extra.customer_email;
    extra.customer_phone = get('svInvCustPhone') || extra.customer_phone;
    draft.extra = extra;

    const lineRows = Array.from(document.querySelectorAll('[data-sv-inv-line]'));
    if (lineRows.length) {
      draft.lines = lineRows.map((row) => ({
        description: String(row.querySelector('[data-sv-line-desc]')?.value || '').trim(),
        note: String(row.querySelector('[data-sv-line-note]')?.value || '').trim(),
        quantity: Number(row.querySelector('[data-sv-line-qty]')?.value || 0) || 0,
        unit: String(row.querySelector('[data-sv-line-unit]')?.value || 'ks').trim() || 'ks',
        unit_price: Number(row.querySelector('[data-sv-line-price]')?.value || 0) || 0,
        tax_rate: Number(row.querySelector('[data-sv-line-vat]')?.value || 21) || 21,
        discount_percent: Number(row.querySelector('[data-sv-line-disc]')?.value || 0) || 0,
      }));
    }
    w.draft = draft;
    return draft;
  }

  async function saveWizardDraft(options = {}) {
    const requireLines = options.requireLines !== false;
    const w = ensureWizardState();
    w.saving = true;
    render();
    try {
      const draft = readWizardFormIntoDraft();
      if (isUserInvoiceMode()) {
        if (!String(draft.extra?.customer_name || '').trim()) {
          throw new Error('Vyplňte název odběratele.');
        }
      } else if (!draft.customer_id) {
        throw new Error('Vyberte odběratele (klienta).');
      }
      const payload = payloadFromWizardDraft(draft);
      if (requireLines && !payload.lines.length) throw new Error('Přidejte alespoň jednu položku faktury.');
      let saved;
      if (w.draftId) {
        saved = await window.apiCall(invoiceApiUrl(String(w.draftId)), 'PUT', payload);
      } else {
        saved = await window.apiCall(invoiceApiBase(), 'POST', payload);
        w.draftId = Number(saved?.id || 0);
      }
      const full = await window.apiCall(invoiceApiUrl(String(w.draftId)), 'GET');
      w.draft = {
        ...full,
        lines: (full.lines || []).map((ln) => ({
          ...ln,
          discount_percent: 0,
          note: '',
        })),
      };
      if (shell()?.load) await shell().load(true, true);
      return full;
    } finally {
      w.saving = false;
    }
  }

  function customerOptions(selectedId) {
    const customers = Array.isArray(st().customers) ? st().customers : [];
    return customers
      .map((c) => {
        const id = Number(c?.customer_id || 0);
        const label = c?.name || maskContact(c?.email) || `Zákazník #${id}`;
        return `<option value="${id}" ${id === Number(selectedId) ? 'selected' : ''}>${esc(label)}</option>`;
      })
      .join('');
  }

  function maskContact(v) {
    if (shell()?.maskCardContact) return shell().maskCardContact(v);
    return v ? String(v).replace(/(.{2}).+(@.+)/, '$1***$2') : '—';
  }

  function icoFilter() {
    return '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M10 18h4v-2h-4v2zM3 6v2h18V6H3zm3 7h12v-2H6v2z"/></svg>';
  }

  function icoCalendar() {
    return '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/></svg>';
  }

  function statusBadgeHtml(inv) {
    const ds = displayStatus(inv);
    return `<span class="sv-inv-badge sv-inv-badge--${ds.cls}"><span class="sv-inv-badge-ico" aria-hidden="true"></span>${esc(ds.label)}</span>`;
  }

  function filterInvoicesForList(opts) {
    const listTab = String(opts.listTab || 'overview');
    const q = String(opts.searchTerm || '').trim().toLowerCase();
    const statusF = String(opts.statusFilter || 'all').toLowerCase();
    let list = Array.isArray(opts.invoices) ? [...opts.invoices] : [];

    if (listTab === 'drafts') {
      list = list.filter((inv) => statusKey(inv) === 'draft');
    } else {
      list = list.filter((inv) => statusKey(inv) !== 'draft');
    }
    if (statusF === 'draft') list = list.filter((inv) => statusKey(inv) === 'draft');
    if (statusF === 'issued') list = list.filter((inv) => statusKey(inv) === 'issued');
    if (statusF === 'cancelled') list = list.filter((inv) => statusKey(inv) === 'cancelled');
    if (isUserInvoiceMode()) {
      if (statusF === 'paid') list = list.filter((inv) => displayStatus(inv).cls === 'paid');
      else if (statusF === 'pending') list = list.filter((inv) => displayStatus(inv).cls === 'pending');
      else if (statusF === 'overdue') list = list.filter((inv) => displayStatus(inv).cls === 'overdue');
    }
    if (q) {
      list = list.filter((inv) => {
        const hay = [inv?.invoice_number, inv?.customer_label, inv?.vehicle_label, inv?.extra?.variable_symbol]
          .join(' ')
          .toLowerCase();
        return hay.includes(q);
      });
    }
    return list;
  }

  function paginateList(list, page, perPage) {
    const per = Math.max(1, Number(perPage || 10));
    const total = list.length;
    const pages = Math.max(1, Math.ceil(total / per));
    const p = Math.min(Math.max(1, Number(page || 1)), pages);
    const start = (p - 1) * per;
    return { slice: list.slice(start, start + per), page: p, pages, total, per };
  }

  /** HTML přehledu faktur — pouze servisní shell (/app/s/). */
  function renderInvoicesListPage(opts) {
    const api = 'serviceShell';
    const all = Array.isArray(opts.invoices) ? opts.invoices : [];
    const listTab = String(opts.listTab || 'overview');
    const searchTerm = String(opts.searchTerm || '');
    const statusFilter = String(opts.statusFilter || 'all');
    const loading = !!opts.loading;
    const stats = computeStats(all);
    const filtered = filterInvoicesForList({ invoices: all, listTab, searchTerm, statusFilter });
    const { slice, page, pages, total, per } = paginateList(filtered, opts.page, opts.perPage);

    const homeClick = isUserInvoiceMode()
      ? "window.UserInvoicesDashboard && window.UserInvoicesDashboard.goOverview()"
      : "window.serviceShell.navigate('dashboard')";
    const userMode = isUserInvoiceMode();
    const pageClass = userMode ? 'sv-inv sv-inv-page sv-inv-page--user' : 'sv-inv sv-inv-page';
    const testId = userMode ? 'user-invoices-dashboard' : 'service-invoices-dashboard';
    const pageSubtitle = userMode
      ? 'Přehled vystavených faktur, konceptů a stavu úhrad vaší firmy.'
      : 'Přehled vystavených faktur, konceptů a stavu úhrad.';
    const quickActions = userMode
      ? `<button type="button" class="sv-inv-link-item" onclick="window.serviceShell.goProfileSettings()">Nastavení číslování faktur</button>
          <button type="button" class="sv-inv-link-item" onclick="window.serviceShell.onInvoiceDateRange()">Šablony faktur</button>
          <button type="button" class="sv-inv-link-item" onclick="window.serviceShell.onInvoiceDateRange()">Ceník služeb a položek</button>
          <button type="button" class="sv-inv-link-item" onclick="window.serviceShell.exportInvoicesCsv()">Export faktur</button>
          <button type="button" class="sv-inv-link-item" onclick="window.UserInvoicesDashboard && window.UserInvoicesDashboard.showReceived()">Přijaté faktury od servisu</button>`
      : `<button type="button" class="sv-inv-link-item" onclick="window.serviceShell.navigate('team')">Číslování faktur</button>
          <button type="button" class="sv-inv-link-item" onclick="window.serviceShell.navigate('documents')">Šablony faktur</button>
          <button type="button" class="sv-inv-link-item" onclick="window.serviceShell.navigate('team')">Ceník</button>
          <button type="button" class="sv-inv-link-item" onclick="window.serviceShell.exportInvoicesCsv()">Export faktur</button>`;
    const vatDetailClick = userMode
      ? 'window.serviceShell.onVatDetail()'
      : `window.serviceShell.navigate('vat-overview')`;

    const statusOptions = userMode
      ? `<option value="all"${statusFilter === 'all' ? ' selected' : ''}>Všechny stavy</option>
          <option value="paid"${statusFilter === 'paid' ? ' selected' : ''}>Zaplaceno</option>
          <option value="pending"${statusFilter === 'pending' ? ' selected' : ''}>Čeká na úhradu</option>
          <option value="overdue"${statusFilter === 'overdue' ? ' selected' : ''}>Po splatnosti</option>`
      : `<option value="all"${statusFilter === 'all' ? ' selected' : ''}>Všechny stavy</option>
          <option value="draft"${statusFilter === 'draft' ? ' selected' : ''}>Koncept</option>
          <option value="issued"${statusFilter === 'issued' ? ' selected' : ''}>Vystavené</option>
          <option value="cancelled"${statusFilter === 'cancelled' ? ' selected' : ''}>Zrušené</option>`;

    const eligible = userMode ? st().eligible : null;
    const canIssue = eligible?.eligible === true;
    const eligibilityBanner =
      userMode && eligible && !canIssue
        ? `<div class="sv-inv-card" style="margin-bottom:16px;padding:16px;background:#fff7ed;border:1px solid #fed7aa;">
          <strong>Fakturaci je potřeba nejdříve aktivovat</strong>
          <p style="margin:8px 0 12px;color:#9a3412;">${esc(eligible.message || 'Doplňte IČO a název firmy v profilu.')}</p>
          <button type="button" class="sv-inv-btn sv-inv-btn--secondary" onclick="window.serviceShell.goProfileSettings()">Otevřít profil účtu</button>
        </div>`
        : '';

    const tableRows = slice
      .map((inv) => {
        const id = Number(inv?.id || 0);
        const vid = Number(inv?.vehicle_id || 0);
        const extra = inv?.extra || {};
        const partyPrimary = esc(inv?.customer_label || '—');
        const previewClick = `window.serviceShell.openInvoicePreviewModal(${id})`;
        const pdfClick = `window.serviceShell.openServiceInvoicePdf(${id})`;
        const moreClick = `window.serviceShell.openInvoiceFromList(${id})`;
        return `<tr>
          <td>
            <div class="sv-inv-cell-primary">${esc(inv?.invoice_number || '—')}</div>
            <div class="sv-inv-cell-sub">VS ${esc(extra.variable_symbol || inv?.variable_symbol || '—')}</div>
          </td>
          <td>
            <div class="sv-inv-cell-primary">${partyPrimary}</div>
            <div class="sv-inv-cell-sub">IČO ${esc(extra.customer_ico || '—')}</div>
          </td>
          <td>${esc(fmtDate(extra.issue_date || inv?.issue_date || inv?.issued_at || inv?.created_at))}</td>
          <td>${esc(fmtDate(inv?.due_at))}</td>
          <td>
            <div class="sv-inv-cell-primary"><strong>${esc(money(inv?.total, inv?.currency))}</strong></div>
            <div class="sv-inv-cell-sub">s DPH</div>
          </td>
          <td>${statusBadgeHtml(inv)}</td>
          <td>
            <div class="sv-inv-row-actions">
              <button type="button" class="sv-inv-icon-btn" title="Náhled" onclick="${previewClick}">${icoEye()}</button>
              <button type="button" class="sv-inv-icon-btn" title="PDF" onclick="${pdfClick}">${icoDownload()}</button>
              <button type="button" class="sv-inv-icon-btn" title="Detail" onclick="${moreClick}">${icoMore()}</button>
            </div>
          </td>
        </tr>`;
      })
      .join('');

    const emptyRow =
      '<tr><td colspan="7"><div class="sv-inv-table-empty">Žádné faktury neodpovídají aktuálnímu filtru.</div></td></tr>';

    const pagerNums = Array.from({ length: Math.min(pages, 5) }, (_, i) => {
      const n = i + 1;
      const setPage = `window.serviceShell.setInvoicePage(${n})`;
      return `<button type="button" class="${n === page ? 'is-active' : ''}" onclick="${setPage}">${n}</button>`;
    }).join('');

    const prevPage = `window.serviceShell.setInvoicePage(${page - 1})`;
    const nextPage = `window.serviceShell.setInvoicePage(${page + 1})`;

    const vatMonth = new Date().toLocaleDateString('cs-CZ', { month: 'long', year: 'numeric' });
    const vatBase = stats.issuedTotal > 0 ? Math.round((stats.issuedTotal / 1.21) * 100) / 100 : 0;
    const vat21 = Math.round((stats.issuedTotal - vatBase) * 100) / 100;

    const dueItems = all
      .filter((inv) => (mode === 'service' ? statusKey(inv) === 'issued' : true) && inv?.due_at)
      .sort((a, b) => new Date(a.due_at) - new Date(b.due_at))
      .slice(0, 2)
      .map((inv) => {
        const id = Number(inv.id);
        const vid = Number(inv.vehicle_id || 0);
        const click = `window.serviceShell.openInvoiceFromList(${id})`;
        const label = inv?.invoice_number || 'Koncept';
        return `<button type="button" class="sv-inv-link-item" onclick="${click}">
          <span>${esc(label)}</span>
          <span class="sv-inv-link-item-meta">${esc(fmtDate(inv.due_at))} · ${esc(money(inv.total, inv.currency))}</span>
        </button>`;
      })
      .join('');

    const sidebarCreatePrimary = `window.serviceShell.startInvoiceWizard()`;
    const sidebarCreateSecondary = userMode
      ? `window.serviceShell.setInvoiceListTab('drafts'); window.serviceShell.navigate('invoices')`
      : `window.serviceShell.setInvoiceListTab('drafts'); window.serviceShell.navigate('invoices')`;

    const kpi = `
      <div class="sv-inv-kpi-grid">
        <article class="sv-inv-kpi">
          <div class="sv-inv-kpi-icon sv-inv-kpi-icon--blue">${icoDoc()}</div>
          <div class="sv-inv-kpi-label">Celkem vystaveno</div>
          <div class="sv-inv-kpi-value">${esc(money(stats.issuedTotal))}</div>
          <div class="sv-inv-kpi-meta">${stats.issuedCount} faktur</div>
        </article>
        <article class="sv-inv-kpi">
          <div class="sv-inv-kpi-icon sv-inv-kpi-icon--green">${icoCheck()}</div>
          <div class="sv-inv-kpi-label">Zaplaceno</div>
          <div class="sv-inv-kpi-value">${esc(money(stats.paidTotal))}</div>
          <div class="sv-inv-kpi-meta">${stats.paidCount} faktur</div>
        </article>
        <article class="sv-inv-kpi">
          <div class="sv-inv-kpi-icon sv-inv-kpi-icon--orange">${icoClock()}</div>
          <div class="sv-inv-kpi-label">Čeká na úhradu</div>
          <div class="sv-inv-kpi-value">${esc(money(stats.pendingTotal))}</div>
          <div class="sv-inv-kpi-meta">${stats.pendingCount} faktur</div>
        </article>
        <article class="sv-inv-kpi">
          <div class="sv-inv-kpi-icon sv-inv-kpi-icon--red">${icoAlert()}</div>
          <div class="sv-inv-kpi-label">Po splatnosti</div>
          <div class="sv-inv-kpi-value">${esc(money(stats.overdueTotal))}</div>
          <div class="sv-inv-kpi-meta">${stats.overdueCount} faktur</div>
        </article>
      </div>`;

    return `
      <div class="${pageClass}" data-testid="${testId}">
        <nav class="sv-inv-breadcrumb">
          <button type="button" onclick="${homeClick}">Přehled</button>
          <span aria-hidden="true">/</span>
          <span>Faktury</span>
        </nav>
        <div class="sv-inv-page-head">
          <div>
            <h1>Faktury</h1>
            <p>${pageSubtitle}</p>
          </div>
          ${userMode && canIssue ? `<button type="button" class="sv-inv-btn sv-inv-btn--primary" onclick="window.serviceShell.startInvoiceWizard()">+ Nová faktura</button>` : ''}
        </div>
        ${eligibilityBanner}
        ${loading ? '<p class="sv-inv-loading-hint">Načítám faktury…</p>' : ''}
        ${kpi}
        <div class="sv-inv-layout">
          <div class="sv-inv-main">
            <div class="sv-inv-card">
              <div class="sv-inv-tabs">
                <button type="button" class="sv-inv-tab ${listTab === 'overview' ? 'is-active' : ''}" onclick="window.serviceShell.setInvoiceListTab('overview')">Přehled faktur</button>
                <button type="button" class="sv-inv-tab ${listTab === 'drafts' ? 'is-active' : ''}" onclick="window.serviceShell.setInvoiceListTab('drafts')">Návrhy / Koncepty</button>
              </div>
              <div class="sv-inv-toolbar">
                <input class="sv-inv-search" type="search" placeholder="Hledat fakturu, zákazníka, číslo…" value="${esc(searchTerm)}" oninput="window.serviceShell.setInvoiceSearchTerm(this.value)">
                <select class="sv-inv-select" onchange="window.serviceShell.setInvoiceStatusFilter(this.value)">${statusOptions}</select>
                <button type="button" class="sv-inv-date-range" onclick="window.serviceShell.onInvoiceDateRange()">${icoCalendar()}<span>Datum od – do</span></button>
                <button type="button" class="sv-inv-btn sv-inv-btn--ghost sv-inv-btn--filter">${icoFilter()} Filtry</button>
              </div>
              <div class="sv-inv-table-wrap">
                <table class="sv-inv-table">
                  <thead><tr>
                    <th>Číslo faktury</th><th>Zákazník</th><th>Datum vystavení</th><th>Splatnost</th>
                    <th>Částka</th><th>Stav</th><th>Akce</th>
                  </tr></thead>
                  <tbody>${tableRows || emptyRow}</tbody>
                </table>
              </div>
              <div class="sv-inv-pagination">
                <span>Zobrazeno ${total ? (page - 1) * per + 1 : 0}–${Math.min(page * per, total)} z ${total} faktur</span>
                <div class="sv-inv-pager">
                  <button type="button" ${page <= 1 ? 'disabled' : ''} onclick="${prevPage}">‹</button>
                  ${pagerNums}
                  <button type="button" ${page >= pages ? 'disabled' : ''} onclick="${nextPage}">›</button>
                </div>
                <select class="sv-inv-select" onchange="window.serviceShell.setInvoicePerPage(Number(this.value))">
                  <option value="10"${per === 10 ? ' selected' : ''}>10 na stránku</option>
                  <option value="25"${per === 25 ? ' selected' : ''}>25 na stránku</option>
                </select>
              </div>
            </div>
          </div>
          <aside class="sv-inv-side">
            <section class="sv-inv-side-card">
              <h3>Vytvořit fakturu</h3>
              <button type="button" class="sv-inv-btn sv-inv-btn--primary sv-inv-btn--block sv-inv-btn--with-plus" onclick="${sidebarCreatePrimary}">+ Nová faktura</button>
              <button type="button" class="sv-inv-btn sv-inv-btn--secondary sv-inv-btn--block sv-inv-btn--with-plus" onclick="${sidebarCreateSecondary}">+ Z návrhu / konceptu</button>
            </section>
            <section class="sv-inv-side-card">
              <h3>Přehled DPH</h3>
              <p class="sv-inv-vat-month">${esc(vatMonth)}</p>
              <div class="sv-inv-vat-rows">
                <div class="sv-inv-vat-row"><span>Základ 21 %</span><strong>${esc(money(vatBase))}</strong></div>
                <div class="sv-inv-vat-row"><span>DPH 21 %</span><strong>${esc(money(vat21))}</strong></div>
                <div class="sv-inv-vat-row sv-inv-vat-row--total"><span>Celkem s DPH</span><strong>${esc(money(stats.issuedTotal))}</strong></div>
              </div>
              <button type="button" class="sv-inv-edit-link" onclick="${vatDetailClick}">Zobrazit detailní přehled DPH →</button>
            </section>
            <section class="sv-inv-side-card">
              <h3>Nejbližší splatnosti</h3>
              <div class="sv-inv-link-list">${dueItems || '<p class="sv-inv-side-empty">Žádné blízké splatnosti</p>'}</div>
              <button type="button" class="sv-inv-edit-link" onclick="window.serviceShell.focusDueList()">Zobrazit všechny →</button>
            </section>
            <section class="sv-inv-side-card">
              <h3>Rychlé akce</h3>
              <div class="sv-inv-link-list">${quickActions}</div>
            </section>
          </aside>
        </div>
      </div>`;
  }

  function renderListSection() {
    const s = st();
    return renderInvoicesListPage({
      invoices: s.invoices,
      listTab: s.invoiceListTab,
      searchTerm: s.invoiceSearchTerm,
      statusFilter: s.invoiceStatusFilter,
      page: s.invoicePage,
      perPage: s.invoicePerPage,
      loading: !!s.loading,
    });
  }

  function wizardStep1Html(draft) {
    const extra = draft.extra || {};
    const customers = Array.isArray(st().customers) ? st().customers : [];
    const userMode = isUserInvoiceMode();
    const partySelect = userMode
      ? ''
      : `<div class="sv-inv-form-grid">
          <label>Klient (odběratel) *<select id="svInvCustomer" onchange="window.serviceShell.onInvoiceCustomerChange()">${'<option value="">— vyberte —</option>'}${customerOptions(draft.customer_id)}</select></label>
          <label>Vozidlo<select id="svInvVehicle"><option value="">Bez vozidla</option></select></label>
        </div>`;
    const supplierHeading = userMode ? 'Dodavatel (vy)' : 'Dodavatel';
    return `
      <div class="sv-inv-card sv-inv-section-card">
        <div class="sv-inv-section-head"><h2>Dodavatel a odběratel</h2></div>
        ${partySelect}
        <h3 style="margin:18px 0 10px;font-size:0.75rem;color:#1d4ed8;text-transform:uppercase;">${supplierHeading}</h3>
        <div class="sv-inv-form-grid">
          <label>Název<input id="svInvSupName" value="${esc(extra.supplier_name)}"></label>
          <label>IČO<input id="svInvSupIco" value="${esc(extra.supplier_ico)}"></label>
          <label>DIČ<input id="svInvSupDic" value="${esc(extra.supplier_dic)}"></label>
          <label>Ulice<input id="svInvSupStreet" value="${esc(extra.supplier_street)}"></label>
          <label>Město<input id="svInvSupCity" value="${esc(extra.supplier_city)}"></label>
          <label>PSČ<input id="svInvSupZip" value="${esc(extra.supplier_zip)}"></label>
          <label>E-mail<input id="svInvSupEmail" type="email" value="${esc(extra.supplier_email)}"></label>
          <label>Telefon<input id="svInvSupPhone" value="${esc(extra.supplier_phone)}"></label>
        </div>
        <h3 style="margin:18px 0 10px;font-size:0.75rem;color:#1d4ed8;text-transform:uppercase;">Odběratel</h3>
        <div class="sv-inv-form-grid">
          <label>Název${userMode ? ' odběratele *' : ''}<input id="svInvCustName" value="${esc(extra.customer_name)}"></label>
          <label>IČO<input id="svInvCustIco" value="${esc(extra.customer_ico)}"></label>
          <label>DIČ<input id="svInvCustDic" value="${esc(extra.customer_dic)}"></label>
          <label>Ulice<input id="svInvCustStreet" value="${esc(extra.customer_street)}"></label>
          <label>Město<input id="svInvCustCity" value="${esc(extra.customer_city)}"></label>
          <label>PSČ<input id="svInvCustZip" value="${esc(extra.customer_zip)}"></label>
          <label>E-mail<input id="svInvCustEmail" type="email" value="${esc(extra.customer_email)}"></label>
          <label>Telefon<input id="svInvCustPhone" value="${esc(extra.customer_phone)}"></label>
        </div>
        <h3 style="margin:18px 0 10px;font-size:0.75rem;color:#1d4ed8;text-transform:uppercase;">Údaje faktury</h3>
        <div class="sv-inv-form-grid">
          <label>Datum vystavení<input id="svInvIssueDate" type="date" value="${esc(String(extra.issue_date || '').slice(0, 10))}"></label>
          <label>Datum zdan. plnění<input id="svInvDeliveryDate" type="date" value="${esc(String(extra.delivery_date || '').slice(0, 10))}"></label>
          <label>Datum splatnosti<input id="svInvDueAt" type="date" value="${esc(String(draft.due_at || '').slice(0, 10))}"></label>
          <label>Forma úhrady<select id="svInvPayment"><option value="prevod" selected>Bankovní převod</option><option value="hotovost">Hotově</option></select></label>
          <label>Variabilní symbol<input id="svInvVs" value="${esc(extra.variable_symbol)}"></label>
          <label>Konstantní symbol<input id="svInvKs" value="${esc(extra.constant_symbol)}"></label>
          <label>Banka<input id="svInvSupBank" value="${esc(extra.supplier_bank)}"></label>
          <label>Číslo účtu<input id="svInvSupAccount" value="${esc(extra.supplier_bankaccount)}"></label>
          <label>IBAN<input id="svInvSupIban" value="${esc(extra.supplier_iban)}"></label>
          <label>BIC/SWIFT<input id="svInvSupSwift" value="${esc(extra.supplier_swift)}"></label>
          <label>Měna<input id="svInvCurrency" value="${esc(draft.currency || 'CZK')}"></label>
          <label>Poznámka<textarea id="svInvNotes" rows="2">${esc(draft.notes || '')}</textarea></label>
        </div>
      </div>`;
  }

  function lineRowHtml(ln, idx) {
    return `
      <div class="sv-inv-line-row" data-sv-inv-line="${idx}">
        <label><span>Popis</span><input data-sv-line-desc value="${esc(ln.description)}"></label>
        <label><span>Množ.</span><input data-sv-line-qty type="number" min="0" step="0.1" value="${esc(ln.quantity)}"></label>
        <label><span>Jedn.</span><input data-sv-line-unit value="${esc(ln.unit)}"></label>
        <label><span>Cena</span><input data-sv-line-price type="number" min="0" step="0.01" value="${esc(ln.unit_price)}"></label>
        <label><span>Sleva %</span><input data-sv-line-disc type="number" min="0" max="100" value="${esc(ln.discount_percent || 0)}"></label>
        <label><span>DPH</span><input data-sv-line-vat type="number" value="${esc(ln.tax_rate)}"></label>
        <button type="button" class="sv-inv-icon-btn" onclick="this.closest('[data-sv-inv-line]').remove()">×</button>
      </div>
      <input data-sv-line-note type="text" placeholder="Podpopis (volitelné)" value="${esc(ln.note || '')}" style="width:100%;margin-bottom:8px;padding:8px;border:1px solid #e5e7eb;border-radius:8px;">`;
  }

  function wizardStep2Html(draft) {
    const lines = Array.isArray(draft.lines) ? draft.lines : [];
    return `
      <div class="sv-inv-card sv-inv-section-card">
        <div class="sv-inv-section-head">
          <h2>Položky faktury</h2>
          <button type="button" class="sv-inv-btn sv-inv-btn--secondary" onclick="window.serviceShell.appendWizardInvoiceLine()">+ Přidat položku</button>
        </div>
        <div class="sv-inv-line-editor" id="svInvLinesEditor">
          ${lines.map((ln, i) => lineRowHtml(ln, i)).join('')}
        </div>
      </div>`;
  }

  function wizardStep3Html(draft) {
    const extra = draft.extra || {};
    const draftId = Number(draft?.id || ensureWizardState().draftId || 0);
    const supplierAddr = [extra.supplier_street, extra.supplier_zip, extra.supplier_city].filter(Boolean).join(', ');
    const customerAddr = [extra.customer_street, extra.customer_zip, extra.customer_city].filter(Boolean).join(', ');
    const supplierParty = `
      <p><strong>${esc(extra.supplier_name || '—')}</strong></p>
      <p>${esc(supplierAddr || '—')}</p>
      <p>IČO: ${esc(extra.supplier_ico || '—')} · DIČ: ${esc(extra.supplier_dic || '—')}</p>
      <p>${esc(extra.supplier_email || '')}${extra.supplier_phone ? ` · ${esc(extra.supplier_phone)}` : ''}</p>`;
    const customerParty = `
      <p><strong>${esc(extra.customer_name || draft.customer_label || '—')}</strong></p>
      <p>${esc(customerAddr || '—')}</p>
      <p>IČO: ${esc(extra.customer_ico || '—')} · DIČ: ${esc(extra.customer_dic || '—')}</p>
      <p>${esc(extra.customer_email || '')}${extra.customer_phone ? ` · ${esc(extra.customer_phone)}` : ''}</p>`;

    return `
      <div class="sv-inv-wizard-layout sv-inv-wizard-layout--step3">
        <div class="sv-inv-wizard-main">
          <h2 class="sv-inv-review-title">Zkontrolujte a odešlete fakturu</h2>
          <div class="sv-inv-review-parties">
            ${wizardReviewPartyCard(userMode ? 'Dodavatel (vy)' : 'Dodavatel', supplierParty, 1)}
            ${wizardReviewPartyCard('Odběratel', customerParty, 1)}
          </div>
          <div class="sv-inv-card sv-inv-section-card">
            <div class="sv-inv-section-head">
              <h2>Údaje faktury</h2>
              <button type="button" class="sv-inv-edit-link" onclick="window.serviceShell.setInvoiceWizardStep(1)">✎ Upravit</button>
            </div>
            <div class="sv-inv-meta-grid sv-inv-meta-grid--review">
              <div class="sv-inv-meta-item"><label>Číslo faktury</label><strong>${esc(draft.invoice_number || '(koncept)')}</strong></div>
              <div class="sv-inv-meta-item"><label>Datum vystavení</label><strong>${esc(fmtDateLong(extra.issue_date))}</strong></div>
              <div class="sv-inv-meta-item"><label>Datum zdanitelného plnění</label><strong>${esc(fmtDateLong(extra.delivery_date || extra.issue_date))}</strong></div>
              <div class="sv-inv-meta-item"><label>Datum splatnosti</label><strong class="is-due">${esc(fmtDateLong(draft.due_at))}</strong></div>
              <div class="sv-inv-meta-item"><label>Forma úhrady</label><strong>Bankovní převod</strong></div>
            </div>
          </div>
          ${wizardLinesTableHtml(draft)}
          ${wizardSummaryHtml(draft)}
        </div>
        <aside class="sv-inv-side sv-inv-side--preview">
          <section class="sv-inv-side-card">
            <h3>Náhled faktury</h3>
            <div class="sv-inv-mini-preview">${renderDocumentHtml(draft, { compact: true })}</div>
            <button type="button" class="sv-inv-btn sv-inv-btn--secondary sv-inv-btn--block sv-inv-btn--with-icon" onclick="window.serviceShell.downloadWizardInvoicePdf()">${icoDownload()} Stáhnout PDF</button>
          </section>
          <section class="sv-inv-side-card sv-inv-alert-ready sv-inv-alert-ready--card">
            <span class="sv-inv-alert-ready-ico" aria-hidden="true">✓</span>
            <div><strong>Faktura je připravena k odeslání</strong><p>Po odeslání již nebude možné fakturu upravovat.</p></div>
          </section>
          <section class="sv-inv-side-card">
            <h3>Další možnosti</h3>
            <div class="sv-inv-send-options">
              <button type="button" class="sv-inv-btn sv-inv-btn--outline" onclick="window.serviceShell.sendInvoiceEmail()">Odeslat e-mailem</button>
              <button type="button" class="sv-inv-btn sv-inv-btn--outline" onclick="window.serviceShell.scheduleInvoiceSend()">Naplánovat odeslání</button>
            </div>
          </section>
          <section class="sv-inv-side-card sv-inv-tip">
            <span>💡</span>
            <div><strong>Tip</strong> Koncept můžete kdykoliv uložit a dokončit později. Náhled otevřete tlačítkem níže.</div>
            <button type="button" class="sv-inv-btn sv-inv-btn--ghost sv-inv-btn--block" style="margin-top:10px;" onclick="window.serviceShell.openWizardInvoicePreview()">Zobrazit náhled na celou obrazovku</button>
          </section>
        </aside>
      </div>`;
  }

  function wizardStep4Html(draft) {
    const invNo = draft?.invoice_number || '(koncept)';
    const totals = invoiceCalc(draft.lines || []);
    const extra = draft.extra || {};
    const id = Number(draft?.id || 0);
    return `
      <div class="sv-inv-wizard-layout sv-inv-wizard-layout--step4">
        <div class="sv-inv-wizard-step4-main">
          <div class="sv-inv-card sv-inv-section-card sv-inv-success-card">
            <div class="sv-inv-success-icon">✓</div>
            <h2>Faktura byla úspěšně vytvořena</h2>
            <p class="sv-inv-success-lead">Faktura <strong>${esc(invNo)}</strong> byla vytvořena a je připravena k odeslání odběrateli.</p>
            <h3 class="sv-inv-success-sub">Co chcete udělat dál?</h3>
            <div class="sv-inv-action-cards">
              <article class="sv-inv-action-card">
                <div class="sv-inv-action-card-ico">✉</div>
                <strong>Odeslat odběrateli</strong>
                <p>E-mail s odkazem na PDF faktury.</p>
                <button type="button" class="sv-inv-btn sv-inv-btn--outline sv-inv-btn--block" onclick="window.serviceShell.sendInvoiceEmail()">Odeslat e-mailem</button>
              </article>
              <article class="sv-inv-action-card">
                <div class="sv-inv-action-card-ico">↓</div>
                <strong>Stáhnout PDF</strong>
                <p>Archivujte nebo tiskněte fakturu.</p>
                <button type="button" class="sv-inv-btn sv-inv-btn--outline sv-inv-btn--block" onclick="window.serviceShell.downloadWizardInvoicePdf()">Stáhnout PDF</button>
              </article>
              <article class="sv-inv-action-card">
                <div class="sv-inv-action-card-ico">🔗</div>
                <strong>Sdílet odkazem</strong>
                <p>Zkopírujte odkaz na PDF.</p>
                <button type="button" class="sv-inv-btn sv-inv-btn--outline sv-inv-btn--block" onclick="window.serviceShell.shareInvoiceLink()">Vygenerovat odkaz</button>
              </article>
              <article class="sv-inv-action-card">
                <div class="sv-inv-action-card-ico">📅</div>
                <strong>Naplánovat odeslání</strong>
                <p>Odešlete fakturu v zvolený čas.</p>
                <button type="button" class="sv-inv-btn sv-inv-btn--outline sv-inv-btn--block" onclick="window.serviceShell.scheduleInvoiceSend()">Naplánovat odeslání</button>
              </article>
            </div>
            <h3 class="sv-inv-success-sub">Co bude následovat?</h3>
            <div class="sv-inv-timeline sv-inv-timeline--boxed">
              <div class="sv-inv-timeline-item">
                <span class="sv-inv-timeline-ico is-done">✓</span>
                <div class="sv-inv-timeline-body">
                  <strong>Faktura byla vytvořena jako koncept</strong>
                  <span class="sv-inv-timeline-status is-done">Hotovo</span>
                </div>
              </div>
              <div class="sv-inv-timeline-item">
                <span class="sv-inv-timeline-ico is-done">✓</span>
                <div class="sv-inv-timeline-body">
                  <strong>Faktura je připravena k odeslání</strong>
                  <span class="sv-inv-timeline-status is-done">Hotovo</span>
                </div>
              </div>
              <div class="sv-inv-timeline-item">
                <span class="sv-inv-timeline-ico is-next">●</span>
                <div class="sv-inv-timeline-body">
                  <strong>Po odeslání bude faktura evidována jako „Odesláno“</strong>
                  <span class="sv-inv-timeline-status is-next">Další krok</span>
                  <p>Odběratel obdrží PDF a variabilní symbol pro úhradu.</p>
                </div>
              </div>
            </div>
          </div>
        </div>
        <aside class="sv-inv-side">
          <section class="sv-inv-side-card">
            <h3>Stav faktury</h3>
            <span class="sv-inv-badge sv-inv-badge--created">Vytvořena</span>
            <p class="sv-inv-side-desc">Faktura byla úspěšně vytvořena a je připravena k odeslání.</p>
            <button type="button" class="sv-inv-btn sv-inv-btn--ghost sv-inv-btn--block sv-inv-status-change">Změnit stav ▾</button>
          </section>
          <section class="sv-inv-side-card">
            <h3>Náhled faktury</h3>
            <button type="button" class="sv-inv-btn sv-inv-btn--secondary sv-inv-btn--block sv-inv-btn--with-icon" onclick="window.serviceShell.openInvoicePreviewModal(${id})">${icoEye()} Zobrazit náhled</button>
          </section>
          <section class="sv-inv-side-card">
            <h3>Souhrn</h3>
            <div class="sv-inv-side-summary">
              <div class="sv-inv-side-summary-row"><span>Mezisoučet bez DPH</span><span>${esc(money(totals.subtotal, draft.currency))}</span></div>
              <div class="sv-inv-side-summary-row"><span>Sleva celkem</span><span class="sv-inv-discount">-${esc(money(totals.discountTotal, draft.currency))}</span></div>
              <div class="sv-inv-side-summary-row"><span>Základ DPH</span><span>${esc(money(totals.base, draft.currency))}</span></div>
              <div class="sv-inv-side-summary-row"><span>DPH (21 %)</span><span>${esc(money(totals.tax, draft.currency))}</span></div>
              <div class="sv-inv-side-summary-total"><span>Celkem k úhradě</span><strong>${esc(money(totals.total, draft.currency))}</strong></div>
            </div>
          </section>
          <section class="sv-inv-side-card">
            <h3>Informace o faktuře</h3>
            <dl class="sv-inv-info-list">
              <div><dt>Číslo faktury</dt><dd>${esc(invNo)}</dd></div>
              <div><dt>Variabilní symbol</dt><dd>${esc(extra.variable_symbol || '—')}</dd></div>
              <div><dt>Datum vystavení</dt><dd>${esc(fmtDateLong(extra.issue_date))}</dd></div>
              <div><dt>Datum splatnosti</dt><dd>${esc(fmtDateLong(draft.due_at))}</dd></div>
              <div><dt>Forma úhrady</dt><dd>Bankovní převod</dd></div>
            </dl>
          </section>
          <section class="sv-inv-side-card sv-inv-tip">
            <span>💡</span>
            <div>Fakturu můžete kdykoliv upravit nebo zrušit, dokud není odeslána odběrateli.</div>
          </section>
        </aside>
      </div>`;
  }

  function renderWizardSection() {
    const w = ensureWizardState();
    const draft = w.draft || defaultDraftFromProfile();
    const step = Number(w.step || 1);
    let body = '';
    if (step === 1) body = wizardStep1Html(draft);
    else if (step === 2) body = wizardStep2Html(draft);
    else if (step === 3) body = wizardStep3Html(draft);
    else body = wizardStep4Html(draft);

    const saving = w.saving ? ' disabled' : '';
    let footerLeft = '';
    let footerRight = '';
    if (step === 1) {
      footerLeft = '';
      footerRight = `<button type="button" class="sv-inv-btn sv-inv-btn--primary" onclick="window.serviceShell.wizardNextStep()"${saving}>Pokračovat: Položky faktury</button>`;
    } else if (step === 2) {
      footerLeft = `<button type="button" class="sv-inv-btn sv-inv-btn--ghost" onclick="window.serviceShell.setInvoiceWizardStep(1)">Zpět: Základní informace</button>`;
      footerRight = `<button type="button" class="sv-inv-btn sv-inv-btn--primary" onclick="window.serviceShell.wizardNextStep()"${saving}>Pokračovat: Náhled</button>`;
    } else if (step === 3) {
      footerLeft = `<button type="button" class="sv-inv-btn sv-inv-btn--ghost" onclick="window.serviceShell.setInvoiceWizardStep(2)">Zpět: Položky faktury</button>`;
      footerRight = `
        <button type="button" class="sv-inv-btn sv-inv-btn--secondary" onclick="window.serviceShell.saveInvoiceWizardDraft()"${saving}>Uložit koncept</button>
        <button type="button" class="sv-inv-btn sv-inv-btn--primary sv-inv-btn--split" onclick="window.serviceShell.issueInvoiceFromWizard()"${saving}>Odeslat fakturu</button>
        <button type="button" class="sv-inv-btn sv-inv-btn--primary sv-inv-btn-chevron" aria-label="Další možnosti" onclick="window.serviceShell.toggleInvoiceSendMenu(event)"${saving}>▾</button>`;
    } else {
      footerLeft = `<button type="button" class="sv-inv-btn sv-inv-btn--ghost" onclick="window.serviceShell.navigate('invoices')">Zpět na přehled faktur</button>`;
      footerRight = `<button type="button" class="sv-inv-btn sv-inv-btn--primary" onclick="window.serviceShell.startInvoiceWizard()">+ Vytvořit další fakturu</button>`;
    }

    return `
      <div class="sv-inv sv-inv-page">
        ${wizardBreadcrumb('Nová faktura')}
        <div class="sv-inv-page-head">
          <div>
            <h1>Nová faktura <span class="sv-inv-badge sv-inv-badge--draft">Koncept</span></h1>
          </div>
          <div class="sv-inv-head-actions">
            ${step < 4 ? `<button type="button" class="sv-inv-btn sv-inv-btn--secondary" onclick="window.serviceShell.saveInvoiceWizardDraft()"${saving}>Uložit koncept</button>` : ''}
            <button type="button" class="sv-inv-btn sv-inv-btn--ghost">Více akcí</button>
          </div>
        </div>
        ${stepperHtml(step)}
        ${body}
        <div class="sv-inv-sticky-bar">
          <div>${footerLeft}</div>
          <div style="display:flex;gap:8px;flex-wrap:wrap;">${footerRight}</div>
        </div>
      </div>`;
  }

  function renderPreviewModal() {
    const id = Number(st().invoicePreviewModalId || 0);
    if (!id) return '';
    const inv = (Array.isArray(st().invoices) ? st().invoices : []).find((i) => Number(i.id) === id);
    const w = st().invoiceWizard;
    const draft = w?.draft?.id === id ? w.draft : null;
    const data = draft || inv;
    if (!data) {
      window.apiCall(invoiceApiUrl(String(id)), 'GET').then((full) => {
        st().invoicePreviewModalData = full;
        render();
      }).catch(() => closePreviewModal());
      return `<div class="sv-inv-modal-backdrop" onclick="window.serviceShell.closeInvoicePreviewModal()"><div class="sv-inv-modal"><p style="padding:40px;">Načítám náhled…</p></div></div>`;
    }
    const doc = st().invoicePreviewModalData || data;
    const lines = doc.lines || [];
    const withLines = { ...doc, lines: lines.length ? lines : (w?.draft?.lines || []) };

    return `
      <div class="sv-inv-modal-backdrop" onclick="if(event.target===this) window.serviceShell.closeInvoicePreviewModal()">
        <div class="sv-inv-modal sv-inv-modal--wide" role="dialog" aria-labelledby="svInvModalTitle">
          <div class="sv-inv-modal-head">
            <h2 id="svInvModalTitle" style="margin:0;font-size:1.125rem;">Náhled faktury</h2>
            <button type="button" class="sv-inv-icon-btn" onclick="window.serviceShell.closeInvoicePreviewModal()" aria-label="Zavřít">×</button>
          </div>
          <div class="sv-inv-modal-toolbar">
            <span>‹ 1 / 1 ›</span>
            <span>− 100% +</span>
            <button type="button" class="sv-inv-icon-btn" onclick="window.serviceShell.openServiceInvoicePdf(${id})" title="Stáhnout">${icoDownload()}</button>
            <button type="button" class="sv-inv-icon-btn" onclick="window.print()" title="Tisk">🖨</button>
          </div>
          <div class="sv-inv-modal-body">${renderDocumentHtml(withLines)}</div>
          <div class="sv-inv-modal-foot">
            <button type="button" class="sv-inv-btn sv-inv-btn--secondary" onclick="window.serviceShell.closeInvoicePreviewModal()">Zavřít</button>
            ${String(doc?.status || '').toLowerCase() === 'issued' ? `<button type="button" class="sv-inv-btn sv-inv-btn--ghost" onclick="window.serviceShell.cancelServiceInvoiceFromPreview(${id})">Zrušit fakturu</button>` : ''}
          </div>
        </div>
      </div>`;
  }

  function icoDoc() {
    return '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M16 13H8M16 17H8M10 9H8"/></svg>';
  }
  function icoCheck() {
    return '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 6L9 17l-5-5"/></svg>';
  }
  function icoClock() {
    return '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>';
  }
  function icoAlert() {
    return '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><path d="M12 9v4M12 17h.01"/></svg>';
  }
  function icoEye() {
    return '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>';
  }
  function icoDownload() {
    return '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>';
  }
  function icoMore() {
    return '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="5" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="12" cy="19" r="1.5"/></svg>';
  }

  const api = {
    renderList: renderListSection,
    renderWizard: renderWizardSection,
    renderPreviewOverlay: renderPreviewModal,
    wireShellMethods,
    initWizardAfterRender() {
      const w = ensureWizardState();
      const step = Number(w.step || 1);
      if (step === 2 && (!Array.isArray(w.draft?.lines) || !w.draft.lines.length)) {
        w.draft = { ...(w.draft || defaultDraftFromProfile()), lines: [{ description: '', quantity: 1, unit: 'ks', unit_price: 0, tax_rate: 21, discount_percent: 0, note: '' }] };
      }
      if (step === 1 && shell()?.populateCustomerVehicleSelect) {
        const cid = Number(w.draft?.customer_id || 0);
        shell().populateCustomerVehicleSelect('svInvVehicle', cid, {
          includeEmpty: true,
          emptyLabel: 'Bez vozidla',
          preferredVehicleId: Number(w.draft?.vehicle_id || 0),
        });
      }
    },
  };

  window.ServiceInvoicesDashboard = api;
  window.InvoicesUiShared = null;

  function wireShellMethods() {
    const sh = shell();
    if (!sh) return;

    sh.startInvoiceWizard = function (prefill) {
      if (isUserInvoiceMode()) {
        const eligible = st().eligible;
        if (eligible && !eligible.eligible) {
          showToast(eligible.message || 'Doplňte IČO a název firmy v profilu.', 'warning');
          return;
        }
      }
      const s = st();
      s.invoiceWizard = {
        step: 1,
        draftId: prefill?.invoiceId ? Number(prefill.invoiceId) : null,
        draft: prefill?.draft || defaultDraftFromProfile(),
        saving: false,
      };
      if (prefill?.customerId) s.invoiceWizard.draft.customer_id = Number(prefill.customerId);
      if (prefill?.vehicleId) s.invoiceWizard.draft.vehicle_id = Number(prefill.vehicleId);
      navigate('invoice-new');
    };

    sh.setInvoiceWizardStep = function (step) {
      const w = ensureWizardState();
      if (step < w.step) {
        readWizardFormIntoDraft();
      }
      w.step = Number(step);
      render();
      api.initWizardAfterRender();
    };

    sh.wizardNextStep = async function () {
      const w = ensureWizardState();
      try {
        readWizardFormIntoDraft();
        if (w.step === 1) {
          if (isUserInvoiceMode()) {
            if (!String(w.draft?.extra?.customer_name || '').trim()) {
              showToast('Vyplňte název odběratele.', 'warning');
              return;
            }
          } else if (!w.draft?.customer_id) {
            showToast('Vyberte odběratele.', 'warning');
            return;
          }
          w.step = 2;
          render();
          api.initWizardAfterRender();
          return;
        }
        if (w.step === 2) {
          await saveWizardDraft({ requireLines: true });
        }
        w.step = Math.min(4, w.step + 1);
        render();
        api.initWizardAfterRender();
      } catch (e) {
        showToast(e?.message || 'Uložení selhalo', 'error');
        render();
      }
    };

    sh.saveInvoiceWizardDraft = async function () {
      try {
        const w = ensureWizardState();
        const requireLines = Number(w.step || 1) >= 2;
        await saveWizardDraft({ requireLines });
        showToast('Koncept faktury byl uložen.', 'success');
        render();
      } catch (e) {
        showToast(e?.message || 'Uložení selhalo', 'error');
        render();
      }
    };

    sh.issueInvoiceFromWizard = async function () {
      const w = ensureWizardState();
      try {
        readWizardFormIntoDraft();
        await saveWizardDraft();
        const id = Number(w.draftId || 0);
        if (!id) throw new Error('Chybí ID faktury.');
        const issued = await window.apiCall(invoiceApiUrl(`${id}/issue`), 'POST');
        w.draft = { ...issued, lines: issued.lines || w.draft?.lines || [] };
        w.step = 4;
        if (shell()?.load) await shell().load(true, true);
        showToast('Faktura byla vystavena a je připravena k odeslání.', 'success');
        render();
      } catch (e) {
        showToast(e?.message || 'Vystavení selhalo', 'error');
        render();
      }
    };

    sh.setInvoiceListTab = function (tab) {
      st().invoiceListTab = tab;
      st().invoicePage = 1;
      render();
    };

    sh.setInvoicePage = function (p) {
      st().invoicePage = Number(p);
      render();
    };

    sh.setInvoicePerPage = function (n) {
      st().invoicePerPage = Number(n);
      st().invoicePage = 1;
      render();
    };

    sh.openWizardInvoicePreview = function () {
      const w = ensureWizardState();
      const id = Number(w.draftId || w.draft?.id || 0);
      if (!id) {
        showToast('Nejdříve uložte koncept faktury.', 'warning');
        return;
      }
      sh.openInvoicePreviewModal(id);
    };

    sh.openInvoicePreviewModal = async function (invoiceId) {
      const id = Number(invoiceId || 0);
      if (!id) return;
      st().invoicePreviewModalId = id;
      st().invoicePreviewModalData = null;
      try {
        st().invoicePreviewModalData = await window.apiCall(invoiceApiUrl(String(id)), 'GET');
      } catch (e) {
        showToast(e?.message || 'Náhled nelze načíst', 'error');
        return;
      }
      render();
      document.body.classList.add('sv-inv-modal-open');
    };

    sh.closeInvoicePreviewModal = function () {
      st().invoicePreviewModalId = null;
      st().invoicePreviewModalData = null;
      document.body.classList.remove('sv-inv-modal-open');
      render();
    };

    sh.openInvoiceFromList = async function (invoiceId) {
      const id = Number(invoiceId || 0);
      const inv = (Array.isArray(st().invoices) ? st().invoices : []).find((i) => Number(i.id) === id);
      if (statusKey(inv) === 'draft') {
        try {
          const full = await window.apiCall(invoiceApiUrl(String(id)), 'GET');
          sh.startInvoiceWizard({ invoiceId: id, draft: { ...full, lines: full.lines || [] } });
          sh.setInvoiceWizardStep(3);
        } catch (e) {
          showToast(e?.message || 'Načtení selhalo', 'error');
        }
        return;
      }
      sh.openInvoicePreviewModal(id);
    };

    sh.onInvoiceCustomerChange = function () {
      const cid = Number(document.getElementById('svInvCustomer')?.value || 0);
      const w = ensureWizardState();
      w.draft = fillCustomerFromLink({ ...w.draft, customer_id: cid });
      if (shell()?.populateCustomerVehicleSelect) {
        shell().populateCustomerVehicleSelect('svInvVehicle', cid, { includeEmpty: true, emptyLabel: 'Bez vozidla' });
      }
      const extra = w.draft.extra || {};
      ['svInvCustName', 'svInvCustEmail', 'svInvCustPhone', 'svInvCustIco', 'svInvCustDic'].forEach((id, i) => {
        const el = document.getElementById(id);
        if (!el) return;
        const keys = ['customer_name', 'customer_email', 'customer_phone', 'customer_ico', 'customer_dic'];
        el.value = extra[keys[i]] || '';
      });
    };

    sh.appendWizardInvoiceLine = function () {
      const ed = document.getElementById('svInvLinesEditor');
      if (!ed) return;
      const idx = ed.querySelectorAll('[data-sv-inv-line]').length;
      const div = document.createElement('div');
      div.innerHTML = lineRowHtml({ description: '', quantity: 1, unit: 'ks', unit_price: 0, tax_rate: 21, discount_percent: 0 }, idx);
      ed.appendChild(div.firstElementChild);
      ed.appendChild(div.children[1]);
    };

    sh.sendInvoiceEmail = function () {
      const w = ensureWizardState();
      const email = w.draft?.extra?.customer_email || '';
      const id = Number(w.draftId || w.draft?.id || 0);
      if (!email) {
        showToast('U odběratele chybí e-mail.', 'warning');
        return;
      }
      const subject = encodeURIComponent(`Faktura ${w.draft?.invoice_number || ''}`);
      const body = encodeURIComponent(`Dobrý den,\n\nv příloze zasíláme fakturu. PDF stáhněte v aplikaci Správa vozidel.\n\n`);
      window.location.href = `mailto:${email}?subject=${subject}&body=${body}`;
      if (id) sh.openServiceInvoicePdf(id);
    };

    sh.downloadWizardInvoicePdf = function () {
      const id = Number(st().invoiceWizard?.draftId || st().invoiceWizard?.draft?.id || 0);
      if (id) sh.openServiceInvoicePdf(id);
      else showToast('Nejdříve uložte koncept faktury.', 'warning');
    };

    sh.shareInvoiceLink = function () {
      const id = Number(st().invoiceWizard?.draftId || 0);
      if (!id) {
        showToast('Nejdříve uložte fakturu.', 'warning');
        return;
      }
      const url = `${window.location.origin}${invoiceApiUrl(`${id}/pdf`)}`;
      if (navigator.clipboard?.writeText) {
        navigator.clipboard.writeText(url).then(() => showToast('Odkaz na PDF zkopírován.', 'success'));
      } else {
        showToast(url, 'info');
      }
    };

    sh.scheduleInvoiceSend = function () {
      showToast('Plánované odeslání připravíme v další verzi. Prozatím použijte e-mail nebo PDF.', 'info');
    };

    sh.toggleInvoiceSendMenu = function (ev) {
      ev?.stopPropagation?.();
      const menu = document.getElementById('svInvSendMenu');
      if (menu) {
        menu.remove();
        return;
      }
      const el = document.createElement('div');
      el.id = 'svInvSendMenu';
      el.style.cssText = 'position:fixed;z-index:13000;background:#fff;border:1px solid #e5e7eb;border-radius:8px;box-shadow:0 8px 24px rgba(0,0,0,.12);padding:6px;min-width:200px;';
      el.innerHTML = `
        <button type="button" class="sv-inv-link-item" style="border:none;" onclick="window.serviceShell.sendInvoiceEmail();document.getElementById('svInvSendMenu')?.remove()">Odeslat e-mailem</button>
        <button type="button" class="sv-inv-link-item" style="border:none;" onclick="window.serviceShell.downloadWizardInvoicePdf();document.getElementById('svInvSendMenu')?.remove()">Stáhnout PDF</button>
        <button type="button" class="sv-inv-link-item" style="border:none;" onclick="window.serviceShell.issueInvoiceFromWizard();document.getElementById('svInvSendMenu')?.remove()">Vystavit bez e-mailu</button>`;
      const rect = ev?.target?.getBoundingClientRect?.();
      el.style.top = `${(rect?.bottom || 80) + 4}px`;
      el.style.left = `${(rect?.right || 200) - 200}px`;
      document.body.appendChild(el);
      setTimeout(() => {
        document.addEventListener('click', function rm() {
          el.remove();
          document.removeEventListener('click', rm);
        }, { once: true });
      }, 0);
    };

    sh.focusDueList = function () {
      navigate('invoices');
    };

    sh.cancelServiceInvoiceFromPreview = async function (invoiceId) {
      const id = Number(invoiceId || 0);
      if (!id) return;
      if (!window.confirm('Opravdu zrušit tuto fakturu?')) return;
      try {
        await window.apiCall(invoiceApiUrl(`${id}/cancel`), 'POST');
        st().invoicePreviewModalId = null;
        st().invoicePreviewModalData = null;
        document.body.classList.remove('sv-inv-modal-open');
        if (shell()?.load) await shell().load(true, true);
        showToast('Faktura byla zrušena.', 'success');
        render();
      } catch (e) {
        showToast(e?.message || 'Zrušení faktury selhalo', 'error');
      }
    };

    sh.onInvoiceDateRange = function () {
      showToast('Filtr období připravujeme.', 'info');
    };

    sh.exportInvoicesCsv = function () {
      const list = Array.isArray(st().invoices) ? st().invoices : [];
      if (!list.length) {
        showToast('Žádná data k exportu.', 'warning');
        return;
      }
      const header = ['cislo', 'zakaznik', 'vystaveno', 'splatnost', 'castka', 'mena', 'stav'];
      const rows = list.map((inv) => [
        inv.invoice_number || '',
        inv.customer_label || '',
        inv.issued_at || inv.extra?.issue_date || '',
        inv.due_at || '',
        inv.total || 0,
        inv.currency || 'CZK',
        inv.status || '',
      ]);
      const csv = [header, ...rows].map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(',')).join('\n');
      const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `faktury-${new Date().toISOString().slice(0, 10)}.csv`;
      a.click();
      URL.revokeObjectURL(a.href);
      showToast('Export CSV byl stažen.', 'success');
    };
  }

  function boot() {
    wireShellMethods();
    const tryInit = () => {
      if (shell()) {
        wireShellMethods();
        return;
      }
      setTimeout(tryInit, 40);
    };
    tryInit();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
