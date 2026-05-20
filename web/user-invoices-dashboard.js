/**
 * Správa vozidel — modul Faktury pro uživatele (/app/u/).
 * Samostatný modul (bez InvoicesUiShared / service-shell-invoices-dashboard.js).
 */
(function () {
  'use strict';

  const API_OVERVIEW = '/api/v1/vehicles/invoices/overview';
  const API = 'UserInvoicesDashboard';

  const state = {
    mountEl: null,
    view: 'list',
    invoices: [],
    localInvoices: [],
    loading: false,
    listTab: 'overview',
    searchTerm: '',
    statusFilter: 'all',
    dateFrom: '',
    dateTo: '',
    filtersOpen: false,
    page: 1,
    perPage: 10,
    detailLoading: false,
    detailData: null,
    previewModal: false,
    previewData: null,
    previewZoom: 100,
  };

  function esc(v) {
    return String(v ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function money(value, currency) {
    const n = Number(value || 0);
    return `${n.toLocaleString('cs-CZ', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${currency || 'CZK'}`;
  }

  function fmtDate(value) {
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

  function getMount() {
    if (state.mountEl) return state.mountEl;
    const uapp = document.getElementById('userInvoicesMount');
    if (uapp) return uapp;
    return document.getElementById('invoicesTabMount');
  }

  function showToast(msg, kind) {
    if (typeof window.showAlert === 'function') window.showAlert(msg, kind || 'info');
  }

  function statusKey(inv) {
    return String(inv?.status || '').trim().toLowerCase();
  }

  function displayStatus(inv) {
    const key = statusKey(inv);
    if (key === 'draft') return { label: 'Koncept', cls: 'draft' };
    if (key === 'created') return { label: 'Vytvořena', cls: 'pending' };
    if (key === 'sent') return { label: 'Odesláno', cls: 'pending' };
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

  function invoiceIssueDate(inv) {
    const extra = inv?.extra || {};
    const raw = extra.issue_date || inv?.issue_date || inv?.issued_at || inv?.created_at;
    return raw ? String(raw).slice(0, 10) : '';
  }

  function mergeAllInvoices() {
    const apiRows = Array.isArray(state.invoices) ? state.invoices : [];
    const localRows = (Array.isArray(state.localInvoices) ? state.localInvoices : []).map((inv) => {
      const wf = window.UserInvoicesWorkflow;
      const legacy = wf?.draftToLegacy ? wf.draftToLegacy(inv) : inv;
      return {
        ...legacy,
        id: inv.id,
        source: 'user_local',
        invoice_number: inv.number || inv.invoice_number,
        customer_label: inv.customer?.name || legacy?.extra?.customer_name,
        service_label: inv.supplier?.name || legacy?.extra?.supplier_name,
        vehicle_label: inv.vehicle_label || '',
        status: inv.status || 'draft',
        total: inv.total || inv.totals?.total_with_vat || 0,
        due_at: inv.due_date || inv.due_at,
        vehicle_id: inv.vehicle_id || null,
      };
    });
    return [...localRows, ...apiRows];
  }

  function filterInvoices(list) {
    const tab = String(state.listTab || 'overview');
    const q = String(state.searchTerm || '').trim().toLowerCase();
    const statusF = String(state.statusFilter || 'all').toLowerCase();
    const from = String(state.dateFrom || '').trim();
    const to = String(state.dateTo || '').trim();
    let rows = Array.isArray(list) ? [...list] : [];

    if (tab === 'drafts') {
      return rows.filter((inv) => {
        const key = statusKey(inv);
        return key === 'draft' || inv.source === 'user_local' && ['draft', 'created'].includes(key);
      });
    }

    rows = rows.filter((inv) => {
      const key = statusKey(inv);
      if (inv.source === 'user_local') return key !== 'draft' || tab === 'drafts';
      return key !== 'draft';
    });

    if (statusF === 'paid') rows = rows.filter((inv) => displayStatus(inv).cls === 'paid');
    else if (statusF === 'pending') rows = rows.filter((inv) => displayStatus(inv).cls === 'pending');
    else if (statusF === 'overdue') rows = rows.filter((inv) => displayStatus(inv).cls === 'overdue');

    if (from) {
      rows = rows.filter((inv) => {
        const d = invoiceIssueDate(inv);
        return d && d >= from;
      });
    }
    if (to) {
      rows = rows.filter((inv) => {
        const d = invoiceIssueDate(inv);
        return d && d <= to;
      });
    }

    if (q) {
      rows = rows.filter((inv) => {
        const extra = inv?.extra || {};
        const hay = [
          inv?.invoice_number,
          inv?.service_label,
          inv?.vehicle_label,
          inv?.variable_symbol,
          extra.variable_symbol,
          extra.supplier_name,
        ]
          .join(' ')
          .toLowerCase();
        return hay.includes(q);
      });
    }

    return rows;
  }

  function paginateList(list) {
    const per = Math.max(1, Number(state.perPage || 10));
    const total = list.length;
    const pages = Math.max(1, Math.ceil(total / per));
    const p = Math.min(Math.max(1, Number(state.page || 1)), pages);
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

  function invoiceForDocument(inv) {
    const extra = { ...(inv?.extra || {}) };
    if (!extra.supplier_name && inv?.service_label) {
      extra.supplier_name = inv.service_label;
    }
    return { ...inv, extra, lines: Array.isArray(inv?.lines) ? inv.lines : [] };
  }

  function renderDocumentHtml(inv, opts) {
    const doc = invoiceForDocument(inv);
    const extra = doc.extra || {};
    const lines = Array.isArray(doc.lines) ? doc.lines : [];
    const totals = invoiceCalc(lines.length ? lines : []);
    const spayd = spaydString(doc, totals);
    const invNo = doc.invoice_number || '(koncept)';
    const appName = 'Správa vozidel';
    const compact = opts?.compact;
    const supplierAddr = [extra.supplier_street, extra.supplier_zip, extra.supplier_city].filter(Boolean).join(', ');
    const customerAddr = [extra.customer_street, extra.customer_zip, extra.customer_city].filter(Boolean).join(', ');
    const noteText =
      doc.notes ||
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
            <p class="sv-inv-doc-party-name">${esc(extra.customer_name || doc.customer_label || '—')}</p>
            <p>${esc(customerAddr || '—')}</p>
            <p>IČO: ${esc(extra.customer_ico || '—')}</p>
            <p>DIČ: ${esc(extra.customer_dic || '—')}</p>
            <p class="sv-inv-doc-contact">✉ ${esc(extra.customer_email || '—')}</p>
            <p class="sv-inv-doc-contact">☎ ${esc(extra.customer_phone || '—')}</p>
          </div>
          <div class="sv-inv-doc-meta-panel">
            <div class="sv-inv-doc-meta-line"><span>📅</span><div><em>Datum vystavení</em><strong>${esc(fmtDateLong(extra.issue_date || doc.issued_at))}</strong></div></div>
            <div class="sv-inv-doc-meta-line"><span>📅</span><div><em>Datum zdanitelného plnění</em><strong>${esc(fmtDateLong(extra.delivery_date || extra.issue_date))}</strong></div></div>
            <div class="sv-inv-doc-meta-line"><span>📅</span><div><em>Datum splatnosti</em><strong class="is-due">${esc(fmtDateLong(doc.due_at))}</strong></div></div>
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
                    <td>${esc(money(ln.unit_price, doc.currency))}</td>
                    <td>${disc ? `<span class="sv-inv-discount">${disc} %</span>` : '—'}</td>
                    <td>${esc(ln.tax_rate)} %</td>
                    <td>${esc(money(net, doc.currency))}</td>
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
                <tr><td>Mezisoučet bez DPH</td><td>${esc(money(totals.subtotal, doc.currency))}</td></tr>
                <tr><td>Sleva celkem</td><td class="sv-inv-discount">-${esc(money(totals.discountTotal, doc.currency))}</td></tr>
                <tr><td>Základ DPH</td><td>${esc(money(totals.base, doc.currency))}</td></tr>
                <tr><td>DPH (21 %)</td><td>${esc(money(totals.tax, doc.currency))}</td></tr>
              </tbody>
            </table>
            <div class="sv-inv-totals-box">
              <div class="sv-inv-totals-label">CELKEM K ÚHRADĚ</div>
              <div class="grand">${esc(money(totals.total, doc.currency))}</div>
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
  function icoFilter() {
    return '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M10 18h4v-2h-4v2zM3 6v2h18V6H3zm3 7h12v-2H6v2z"/></svg>';
  }
  function icoCalendar() {
    return '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/></svg>';
  }
  function icoLink() {
    return '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>';
  }
  function icoMail() {
    return '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><path d="M22 6l-10 7L2 6"/></svg>';
  }

  function statusBadgeHtml(inv) {
    const ds = displayStatus(inv);
    return `<span class="sv-inv-badge sv-inv-badge--${ds.cls}"><span class="sv-inv-badge-ico" aria-hidden="true"></span>${esc(ds.label)}</span>`;
  }

  function goOverviewNav() {
    if (typeof switchTab === 'function') switchTab('overview');
    else clickUappNav('overview');
  }

  function renderFiltersPanel() {
    if (!state.filtersOpen) return '';
    return `
      <div class="sv-inv-toolbar" style="border-top:0;padding-top:0;background:#f9fafb;">
        <label style="font-size:0.875rem;display:flex;align-items:center;gap:8px;">
          <span>Datum od</span>
          <input type="date" class="sv-inv-select" value="${esc(state.dateFrom)}" onchange="window.${API}.setDateFrom(this.value)">
        </label>
        <label style="font-size:0.875rem;display:flex;align-items:center;gap:8px;">
          <span>Datum do</span>
          <input type="date" class="sv-inv-select" value="${esc(state.dateTo)}" onchange="window.${API}.setDateTo(this.value)">
        </label>
        <button type="button" class="sv-inv-btn sv-inv-btn--ghost" onclick="window.${API}.clearDateFilter()">Vymazat období</button>
      </div>`;
  }

  function renderListHtml() {
    const all = mergeAllInvoices();
    const listTab = state.listTab;
    const searchTerm = state.searchTerm;
    const statusFilter = state.statusFilter;
    const loading = state.loading;
    const stats = computeStats(all);
    const filtered = filterInvoices(all);
    const { slice, page, pages, total, per } = paginateList(filtered);

    const statusOptions = `
          <option value="all"${statusFilter === 'all' ? ' selected' : ''}>Všechny stavy</option>
          <option value="paid"${statusFilter === 'paid' ? ' selected' : ''}>Zaplaceno</option>
          <option value="pending"${statusFilter === 'pending' ? ' selected' : ''}>Čeká na úhradu</option>
          <option value="overdue"${statusFilter === 'overdue' ? ' selected' : ''}>Po splatnosti</option>`;

    const tableBody = slice
            .map((inv) => {
              const isLocal = inv.source === 'user_local';
              const id = isLocal ? JSON.stringify(String(inv?.id || '')) : Number(inv?.id || 0);
              const vid = Number(inv?.vehicle_id || 0);
              const extra = inv?.extra || {};
              const partyPrimary = esc(inv?.customer_label || inv?.service_label || '—');
              const partySub = isLocal ? esc(`IČO: ${inv?.extra?.customer_ico || inv?.customer?.ico || '—'}`) : esc(inv?.vehicle_label || '—');
              const detailClick = isLocal
                ? `window.${API}.openLocalDetail(${JSON.stringify(String(inv.id))})`
                : `window.${API}.openDetail(${id}, ${vid})`;
              const pdfClick = isLocal
                ? `window.${API}.openLocalPdf(${JSON.stringify(String(inv.id))})`
                : `window.${API}.openPdf(${id}, ${vid})`;
              return `<tr>
          <td>
            <div class="sv-inv-cell-primary">${esc(inv?.invoice_number || '—')}</div>
            <div class="sv-inv-cell-sub">VS ${esc(extra.variable_symbol || inv?.variable_symbol || '—')}</div>
          </td>
          <td>
            <div class="sv-inv-cell-primary">${partyPrimary}</div>
            <div class="sv-inv-cell-sub">${partySub}</div>
          </td>
          <td>${esc(fmtDate(extra.issue_date || inv?.issue_date || inv?.issued_at))}</td>
          <td>${esc(fmtDate(inv?.due_at))}</td>
          <td>
            <div class="sv-inv-cell-primary"><strong>${esc(money(inv?.total, inv?.currency))}</strong></div>
            <div class="sv-inv-cell-sub">s DPH</div>
          </td>
          <td>${statusBadgeHtml(inv)}</td>
          <td>
            <div class="sv-inv-row-actions">
              <button type="button" class="sv-inv-icon-btn" title="Detail" onclick="${detailClick}">${icoEye()}</button>
              <button type="button" class="sv-inv-icon-btn" title="Stáhnout PDF" onclick="${pdfClick}">${icoDownload()}</button>
              <button type="button" class="sv-inv-icon-btn" title="Detail" onclick="${detailClick}">${icoMore()}</button>
            </div>
          </td>
        </tr>`;
            })
            .join('') ||
          '<tr><td colspan="7"><div class="sv-inv-table-empty">Žádné faktury neodpovídají aktuálnímu filtru.</div></td></tr>';

    const pagerNums = Array.from({ length: Math.min(pages, 5) }, (_, i) => {
      const n = i + 1;
      return `<button type="button" class="${n === page ? 'is-active' : ''}" onclick="window.${API}.setPage(${n})">${n}</button>`;
    }).join('');

    const vatMonth = new Date().toLocaleDateString('cs-CZ', { month: 'long', year: 'numeric' });
    const vatBase = stats.issuedTotal > 0 ? Math.round((stats.issuedTotal / 1.21) * 100) / 100 : 0;
    const vat21 = Math.round((stats.issuedTotal - vatBase) * 100) / 100;

    const dueItems = all
      .filter((inv) => statusKey(inv) === 'issued' && inv?.due_at && displayStatus(inv).cls !== 'paid')
      .sort((a, b) => new Date(a.due_at) - new Date(b.due_at))
      .slice(0, 2)
      .map((inv) => {
        const id = Number(inv.id);
        const vid = Number(inv.vehicle_id || 0);
        const click = `window.${API}.openDetail(${id}, ${vid})`;
        return `<button type="button" class="sv-inv-link-item" onclick="${click}">
          <span>${esc(inv.invoice_number || '—')}</span>
          <span class="sv-inv-link-item-meta">${esc(fmtDate(inv.due_at))} · ${esc(money(inv.total, inv.currency))}</span>
        </button>`;
      })
      .join('');

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
      <div class="sv-inv sv-inv-page sv-inv-page--user" data-testid="user-invoices-dashboard">
        <nav class="sv-inv-breadcrumb" aria-label="Drobečková navigace">
          <button type="button" onclick="window.${API}.goOverview()">Přehled</button>
          <span aria-hidden="true">/</span>
          <span>Faktury</span>
        </nav>
        <div class="sv-inv-page-head">
          <div>
            <h1>Faktury</h1>
            <p>Vytvářejte, spravujte a sledujte přehled všech faktur. Rychle vystavte fakturu a mějte své finance pod kontrolou.</p>
          </div>
        </div>
        ${loading ? '<p class="sv-inv-loading-hint">Načítám faktury…</p>' : ''}
        ${kpi}
        <div class="sv-inv-layout">
          <div class="sv-inv-main">
            <div class="sv-inv-card">
              <div class="sv-inv-tabs">
                <button type="button" class="sv-inv-tab ${listTab === 'overview' ? 'is-active' : ''}" onclick="window.${API}.setListTab('overview')">Přehled faktur</button>
                <button type="button" class="sv-inv-tab ${listTab === 'drafts' ? 'is-active' : ''}" onclick="window.${API}.setListTab('drafts')">Návrhy / Koncepty</button>
              </div>
              <div class="sv-inv-toolbar">
                <input class="sv-inv-search" type="search" placeholder="Hledat fakturu, servis, číslo…" value="${esc(searchTerm)}" oninput="window.${API}.setSearch(this.value)">
                <select class="sv-inv-select" onchange="window.${API}.setStatusFilter(this.value)">${statusOptions}</select>
                <button type="button" class="sv-inv-date-range" onclick="window.${API}.toggleFilters()">${icoCalendar()}<span>Datum od – do</span></button>
                <button type="button" class="sv-inv-btn sv-inv-btn--ghost sv-inv-btn--filter" onclick="window.${API}.toggleFilters()">${icoFilter()} Filtry</button>
              </div>
              ${renderFiltersPanel()}
              <div class="sv-inv-table-wrap">
                <table class="sv-inv-table">
                  <thead><tr>
                    <th>Číslo faktury</th><th>Zákazník</th><th>Datum vystavení</th><th>Splatnost</th>
                    <th>Částka</th><th>Stav</th><th>Akce</th>
                  </tr></thead>
                  <tbody>${tableBody}</tbody>
                </table>
              </div>
              <div class="sv-inv-pagination">
                <span>Zobrazeno ${total ? (page - 1) * per + 1 : 0}–${Math.min(page * per, total)} z ${total} faktur</span>
                <div class="sv-inv-pager">
                  <button type="button" ${page <= 1 ? 'disabled' : ''} onclick="window.${API}.setPage(${page - 1})">‹</button>
                  ${pagerNums}
                  <button type="button" ${page >= pages ? 'disabled' : ''} onclick="window.${API}.setPage(${page + 1})">›</button>
                </div>
                <select class="sv-inv-select" onchange="window.${API}.setPerPage(Number(this.value))">
                  <option value="10"${per === 10 ? ' selected' : ''}>10 na stránku</option>
                  <option value="25"${per === 25 ? ' selected' : ''}>25 na stránku</option>
                </select>
              </div>
            </div>
          </div>
          <aside class="sv-inv-side">
            <section class="sv-inv-side-card">
              <h3>Vytvořit fakturu</h3>
              <p class="sv-inv-side-desc">Vystavte novou fakturu během pár sekund.</p>
              <button type="button" class="sv-inv-btn sv-inv-btn--primary sv-inv-btn--block sv-inv-btn--with-plus" onclick="window.${API}.startNewInvoice()">+ Nová faktura</button>
              <button type="button" class="sv-inv-btn sv-inv-btn--secondary sv-inv-btn--block sv-inv-btn--with-plus" onclick="window.${API}.openDrafts()">+ Z návrhu / konceptu</button>
            </section>
            <section class="sv-inv-side-card">
              <h3>Přehled DPH</h3>
              <p class="sv-inv-vat-month">${esc(vatMonth)}</p>
              <div class="sv-inv-vat-rows">
                <div class="sv-inv-vat-row"><span>Základ 21 %</span><strong>${esc(money(vatBase))}</strong></div>
                <div class="sv-inv-vat-row"><span>DPH 21 %</span><strong>${esc(money(vat21))}</strong></div>
                <div class="sv-inv-vat-row sv-inv-vat-row--total"><span>Celkem s DPH</span><strong>${esc(money(stats.issuedTotal))}</strong></div>
              </div>
              <button type="button" class="sv-inv-edit-link" onclick="window.${API}.onVatDetail()">Zobrazit detailní přehled DPH →</button>
            </section>
            <section class="sv-inv-side-card">
              <h3>Nejbližší splatnosti</h3>
              <div class="sv-inv-link-list">${dueItems || '<p class="sv-inv-side-empty">Žádné blízké splatnosti</p>'}</div>
              <button type="button" class="sv-inv-edit-link" onclick="window.${API}.focusDueList()">Zobrazit všechny →</button>
            </section>
            <section class="sv-inv-side-card">
              <h3>Rychlé akce</h3>
              <div class="sv-inv-link-list">
                <button type="button" class="sv-inv-link-item" onclick="window.${API}.openNumberingSettings()">Nastavení číslování faktur</button>
                <button type="button" class="sv-inv-link-item" onclick="window.${API}.openTemplates()">Šablony faktur</button>
                <button type="button" class="sv-inv-link-item" onclick="window.${API}.openPriceList()">Ceník služeb a položek</button>
                <button type="button" class="sv-inv-link-item" onclick="window.${API}.exportList()">Export faktur</button>
              </div>
            </section>
          </aside>
        </div>
      </div>`;
  }

  function renderDetailHtml() {
    const inv = state.detailData || {};
    const loading = state.detailLoading;
    const id = Number(inv.id || 0);
    const vid = Number(inv.vehicle_id || 0);
    const invNo = inv.invoice_number || '—';
    const ds = displayStatus(inv);
    const totals = invoiceCalc(inv.lines || []);
    const extra = inv.extra || {};
    const paid = ds.cls === 'paid';
    const overdue = ds.cls === 'overdue';

    const checklist = `
      <div class="sv-inv-checklist">
        <div class="sv-inv-check-item is-done"><span class="sv-inv-check-ico" aria-hidden="true">✓</span><span>Faktura vystavena autoservisem</span></div>
        <div class="sv-inv-check-item is-done"><span class="sv-inv-check-ico" aria-hidden="true">✓</span><span>Zkontrolovat údaje a položky</span></div>
        <div class="sv-inv-check-item ${paid ? 'is-done' : overdue ? 'is-warn' : ''}">
          <span class="sv-inv-check-ico" aria-hidden="true">${paid ? '✓' : '○'}</span>
          <span>${paid ? 'Faktura uhrazena' : overdue ? 'Uhradit — po splatnosti' : 'Uhradit do data splatnosti'}</span>
        </div>
        <div class="sv-inv-check-item"><span class="sv-inv-check-ico" aria-hidden="true">○</span><span>Archivovat PDF u sebe</span></div>
      </div>`;

    const docHtml = loading
      ? '<p class="sv-inv-table-empty" style="padding:48px;">Načítám fakturu…</p>'
      : renderDocumentHtml(inv);

    return `
      <div class="sv-inv sv-inv-page sv-inv-page--user sv-inv-page--detail" data-testid="user-invoice-detail">
        <nav class="sv-inv-breadcrumb" aria-label="Drobečková navigace">
          <button type="button" onclick="window.${API}.goOverview()">Přehled</button>
          <span aria-hidden="true">/</span>
          <button type="button" onclick="window.${API}.backToList()">Faktury</button>
          <span aria-hidden="true">/</span>
          <span>${esc(invNo)}</span>
        </nav>
        <div class="sv-inv-page-head">
          <div>
            <h1>${esc(invNo)} ${statusBadgeHtml(inv)}</h1>
            <p>${esc(inv.service_label || 'Autoservis')} · ${esc(inv.vehicle_label || 'Vozidlo')}</p>
          </div>
        </div>
        <div class="sv-inv-layout sv-inv-user-invoice-view">
          <div class="sv-inv-main">
            <div class="sv-inv-card sv-inv-preview-card">
              <div class="sv-inv-preview-card-head">
                <div>
                  <h2>Náhled faktury</h2>
                  <p class="sv-inv-preview-card-sub">Kompletní dokument faktury od autoservisu — pouze pro čtení</p>
                </div>
                <button type="button" class="sv-inv-btn sv-inv-btn--secondary" ${loading || !id ? 'disabled' : ''} onclick="window.${API}.openPreview(${id}, ${vid})">Zobrazit na celou obrazovku</button>
              </div>
              <div class="sv-inv-preview-embed">${docHtml}</div>
            </div>
            <div class="sv-inv-sticky-bar sv-inv-sticky-bar--user">
              <button type="button" class="sv-inv-btn sv-inv-btn--ghost" onclick="window.${API}.backToList()">Zpět na přehled</button>
              <div style="display:flex;gap:8px;flex-wrap:wrap;">
                <button type="button" class="sv-inv-btn sv-inv-btn--secondary sv-inv-btn--with-icon" ${loading || !id ? 'disabled' : ''} onclick="window.${API}.openPdf(${id}, ${vid})">${icoDownload()} Stáhnout PDF</button>
                <button type="button" class="sv-inv-btn sv-inv-btn--outline sv-inv-btn--with-icon" ${loading || !id ? 'disabled' : ''} onclick="window.${API}.sharePdfLink(${id}, ${vid})">${icoLink()} Sdílet odkazem</button>
              </div>
            </div>
          </div>
          <aside class="sv-inv-side">
            <section class="sv-inv-side-card">
              <h3>Stav faktury</h3>
              ${statusBadgeHtml(inv)}
              <p class="sv-inv-side-desc">${paid ? 'Faktura je označena jako zaplacená.' : overdue ? 'Faktura je po splatnosti — uhraďte co nejdříve.' : 'Faktura čeká na úhradu do data splatnosti.'}</p>
            </section>
            <section class="sv-inv-side-card">
              <h3>Další kroky</h3>
              ${checklist}
            </section>
            <section class="sv-inv-side-card">
              <h3>Možnosti</h3>
              <div class="sv-inv-send-options-list">
                <button type="button" class="sv-inv-option-row" ${loading || !id ? 'disabled' : ''} onclick="window.${API}.openPdf(${id}, ${vid})"><span class="sv-inv-option-ico">${icoDownload()}</span> Stáhnout PDF</button>
                <button type="button" class="sv-inv-option-row" ${loading || !id ? 'disabled' : ''} onclick="window.${API}.sharePdfLink(${id}, ${vid})"><span class="sv-inv-option-ico">${icoLink()}</span> Sdílet odkazem</button>
                <button type="button" class="sv-inv-option-row" onclick="window.${API}.contactService()"><span class="sv-inv-option-ico">${icoMail()}</span> Kontaktovat autoservis</button>
              </div>
            </section>
            <section class="sv-inv-side-card">
              <h3>Souhrn</h3>
              <div class="sv-inv-side-summary">
                <div class="sv-inv-side-summary-row"><span>Mezisoučet bez DPH</span><span>${esc(money(totals.subtotal, inv.currency))}</span></div>
                <div class="sv-inv-side-summary-row"><span>Sleva celkem</span><span class="sv-inv-discount">-${esc(money(totals.discountTotal, inv.currency))}</span></div>
                <div class="sv-inv-side-summary-row"><span>Základ DPH</span><span>${esc(money(totals.base, inv.currency))}</span></div>
                <div class="sv-inv-side-summary-row"><span>DPH (21 %)</span><span>${esc(money(totals.tax, inv.currency))}</span></div>
                <div class="sv-inv-side-summary-total"><span>Celkem k úhradě</span><strong>${esc(money(totals.total || inv.total, inv.currency))}</strong></div>
              </div>
            </section>
            <section class="sv-inv-side-card">
              <h3>Informace o faktuře</h3>
              <dl class="sv-inv-info-list">
                <div><dt>Číslo faktury</dt><dd>${esc(invNo)}</dd></div>
                <div><dt>Variabilní symbol</dt><dd>${esc(extra.variable_symbol || '—')}</dd></div>
                <div><dt>Datum vystavení</dt><dd>${esc(fmtDateLong(extra.issue_date || inv.issued_at))}</dd></div>
                <div><dt>Datum splatnosti</dt><dd>${esc(fmtDateLong(inv.due_at))}</dd></div>
                <div><dt>Forma úhrady</dt><dd>Bankovní převod</dd></div>
                <div><dt>Servis</dt><dd>${esc(inv.service_label || '—')}</dd></div>
                <div><dt>Vozidlo</dt><dd>${esc(inv.vehicle_label || '—')}</dd></div>
              </dl>
            </section>
            <section class="sv-inv-side-card sv-inv-tip">
              <span>💡</span>
              <div><strong>Tip</strong> PDF si stáhněte pro archivaci. Při dotazu využijte kontakt na autoservis uvedený na faktuře.</div>
            </section>
          </aside>
        </div>
      </div>`;
  }

  function renderPreviewOverlay() {
    if (!state.previewModal) return '';
    const inv = state.previewData;
    if (!inv) {
      return `
        <div class="sv-inv-modal-backdrop" onclick="if(event.target===this) window.${API}.closePreview()">
          <div class="sv-inv-modal sv-inv-modal--wide"><p style="padding:40px;">Načítám náhled…</p></div>
        </div>`;
    }
    const id = inv.id;
    const vid = Number(inv.vehicle_id || 0);
    const isLocal = inv.source === 'user_local';
    const zoom = state.previewZoom || 100;
    const pdfClick = isLocal
      ? `window.${API}.openLocalPdf(${JSON.stringify(String(id))})`
      : `window.${API}.openPdf(${Number(id)}, ${vid})`;
    return `
      <div class="sv-inv-modal-backdrop" onclick="if(event.target===this) window.${API}.closePreview()">
        <div class="sv-inv-modal sv-inv-modal--wide" role="dialog" aria-labelledby="userInvModalTitle">
          <div class="sv-inv-modal-head">
            <h2 id="userInvModalTitle" style="margin:0;font-size:1.125rem;">Náhled faktury</h2>
            <button type="button" class="sv-inv-icon-btn" onclick="window.${API}.closePreview()" aria-label="Zavřít">×</button>
          </div>
          <div class="sv-inv-modal-toolbar">
            <span>‹ 1 / 1 ›</span>
            <button type="button" class="sv-inv-icon-btn" onclick="window.${API}.zoomOut()">−</button>
            <span>${zoom} %</span>
            <button type="button" class="sv-inv-icon-btn" onclick="window.${API}.zoomIn()">+</button>
            <button type="button" class="sv-inv-icon-btn" onclick="${pdfClick}" title="Stáhnout">${icoDownload()}</button>
            <button type="button" class="sv-inv-icon-btn" onclick="window.print()" title="Tisk">🖨</button>
          </div>
          <div class="sv-inv-modal-body sv-inv-modal-body--a4"><div class="sv-inv-a4-sheet" style="transform:scale(${zoom / 100})">${renderDocumentHtml(inv)}</div></div>
          <div class="sv-inv-modal-foot">
            <button type="button" class="sv-inv-btn sv-inv-btn--secondary" onclick="window.${API}.closePreview()">Zavřít</button>
          </div>
        </div>
      </div>`;
  }

  function paint() {
    const mount = getMount();
    if (!mount) return;
    if (state.view === 'wizard' && window.UserInvoicesWorkflow) {
      window.UserInvoicesWorkflow.mountWizard(mount, state.wizardDraftId || null);
      return;
    }
    if (state.view === 'settings' && window.UserInvoiceSettings) {
      window.UserInvoiceSettings.mount(mount);
      return;
    }
    const main = state.view === 'detail' ? renderDetailHtml() : renderListHtml();
    mount.innerHTML = main + renderPreviewOverlay();
    document.body.classList.toggle('sv-inv-modal-open', !!state.previewModal);
    document.body.classList.toggle('user-invoices-view-detail', state.view === 'detail');
  }

  async function load(force) {
    if (state.loading && !force) return;
    if (window.UserInvoicesWorkflow?.getLocalInvoices) {
      state.localInvoices = window.UserInvoicesWorkflow.getLocalInvoices();
    }
    if (typeof window.apiCall !== 'function') {
      showToast('API není dostupné — zobrazuji lokální koncepty.', 'info');
      state.invoices = [];
      paint();
      return;
    }
    state.loading = true;
    paint();
    try {
      const res = await window.apiCall(API_OVERVIEW, 'GET');
      state.invoices = Array.isArray(res?.items) ? res.items : [];
    } catch (e) {
      state.invoices = [];
      showToast(e?.message || 'Servisní faktury se nepodařilo načíst.', 'error');
    } finally {
      state.loading = false;
      if (window.UserInvoicesWorkflow?.getLocalInvoices) {
        state.localInvoices = window.UserInvoicesWorkflow.getLocalInvoices();
      }
      paint();
    }
  }

  async function loadDetail(invoiceId, vehicleId) {
    const id = Number(invoiceId);
    const vid = Number(vehicleId);
    if (!id || !vid) return;
    state.detailLoading = true;
    state.detailData = null;
    paint();
    try {
      const full = await window.apiCall(`/api/v1/vehicles/${vid}/invoices/${id}`, 'GET');
      state.detailData = { ...full, already_paid: !!(full?.extra?.already_paid) };
    } catch (e) {
      showToast(e?.message || 'Fakturu se nepodařilo načíst.', 'error');
      state.view = 'list';
    } finally {
      state.detailLoading = false;
      paint();
    }
  }

  function clickUappNav(action) {
    const btn = document.querySelector(`.uapp-next-nav [data-uapp-action="${action}"]`);
    if (btn) btn.click();
  }

  const api = {
    load,
    paint,
    goOverview: goOverviewNav,
    backToList() {
      state.view = 'list';
      state.detailData = null;
      state.detailLoading = false;
      state.previewModal = false;
      state.previewData = null;
      paint();
    },
    setListTab(tab) {
      state.listTab = tab;
      state.page = 1;
      paint();
    },
    setSearch(v) {
      state.searchTerm = v;
      state.page = 1;
      paint();
    },
    setStatusFilter(v) {
      state.statusFilter = v;
      state.page = 1;
      paint();
    },
    setDateFrom(v) {
      state.dateFrom = v || '';
      state.page = 1;
      paint();
    },
    setDateTo(v) {
      state.dateTo = v || '';
      state.page = 1;
      paint();
    },
    clearDateFilter() {
      state.dateFrom = '';
      state.dateTo = '';
      state.page = 1;
      paint();
    },
    toggleFilters() {
      state.filtersOpen = !state.filtersOpen;
      paint();
    },
    setPage(p) {
      const filtered = filterInvoices(state.invoices);
      const per = Math.max(1, state.perPage);
      const pages = Math.max(1, Math.ceil(filtered.length / per));
      state.page = Math.min(Math.max(1, Number(p) || 1), pages);
      paint();
    },
    setPerPage(n) {
      state.perPage = Number(n) || 10;
      state.page = 1;
      paint();
    },
    onCreatePrimary() {
      api.startNewInvoice();
    },
    startNewInvoice() {
      state.view = 'wizard';
      state.wizardDraftId = null;
      state.previewModal = false;
      if (typeof syncUserTabUrlHistory === 'function') {
        try { syncUserTabUrlHistory('invoiceNew', {}); } catch (_) {}
      }
      paint();
    },
    showList() {
      state.view = 'list';
      state.wizardDraftId = null;
      state.detailData = null;
      state.previewModal = false;
      if (typeof syncUserTabUrlHistory === 'function') {
        try { syncUserTabUrlHistory('invoices', {}); } catch (_) {}
      }
      load(true);
    },
    openDrafts() {
      state.listTab = 'drafts';
      state.view = 'list';
      state.page = 1;
      paint();
    },
    openLocalDetail(id) {
      const inv = window.UserInvoicesWorkflow?.getLocalInvoice?.(id);
      if (!inv) { showToast('Koncept nenalezen.', 'error'); return; }
      if (inv.status === 'draft' || inv.status === 'created') {
        state.view = 'wizard';
        state.wizardDraftId = id;
        paint();
        return;
      }
      const legacy = window.UserInvoicesWorkflow?.draftToLegacy?.(inv) || inv;
      state.detailData = { ...legacy, source: 'user_local', id };
      state.view = 'detail';
      paint();
    },
    openLocalPdf(id) {
      const inv = window.UserInvoicesWorkflow?.getLocalInvoice?.(id);
      if (!inv) return;
      auditLogLocal('invoice_pdf_download', id);
      const legacy = window.UserInvoicesWorkflow?.draftToLegacy?.(inv);
      state.previewData = { ...legacy, source: 'user_local', id };
      state.previewModal = true;
      state.previewZoom = 100;
      paint();
    },
    openInvoiceSettings() {
      state.view = 'settings';
      paint();
    },
    openNumberingSettings() {
      showToast('Číslování faktur: staging localStorage sekvence FV-YYYY-NNNNN.', 'info');
    },
    openTemplates() {
      api.openInvoiceSettings();
    },
    openPriceList() {
      showToast('BLOCKER: Ceník služeb vyžaduje backend API.', 'info');
    },
    openAccount() {
      if (typeof switchTab === 'function') switchTab('account');
    },
    zoomIn() { state.previewZoom = Math.min(200, (state.previewZoom || 100) + 10); paint(); },
    zoomOut() { state.previewZoom = Math.max(50, (state.previewZoom || 100) - 10); paint(); },
    renderDocumentHtml,
    invoiceCalc,
    onVatDetail() {
      showToast('Detailní přehled DPH z vašich faktur připravujeme.', 'info');
    },
    focusDueList() {
      state.statusFilter = 'pending';
      state.listTab = 'overview';
      state.page = 1;
      if (state.view !== 'list') {
        state.view = 'list';
        state.detailData = null;
      }
      paint();
    },
    goDocuments() {
      if (typeof switchTab === 'function') switchTab('documents');
      else clickUappNav('documents');
    },
    goServices() {
      if (typeof switchTab === 'function') switchTab('servicesDirectory');
      else clickUappNav('servicesDirectory');
    },
    goServiceHistory() {
      clickUappNav('serviceHistory');
    },
    exportList() {
      const list = filterInvoices(mergeAllInvoices());
      if (!list.length) {
        showToast('Není co exportovat.', 'info');
        return;
      }
      const header = ['Číslo', 'Servis', 'Vozidlo', 'Vystaveno', 'Splatnost', 'Částka', 'Měna', 'Stav'];
      const lines = list.map((inv) => {
        const ds = displayStatus(inv);
        return [
          inv.invoice_number,
          inv.service_label,
          inv.vehicle_label,
          fmtDate(invoiceIssueDate(inv)),
          fmtDate(inv.due_at),
          inv.total,
          inv.currency || 'CZK',
          ds.label,
        ]
          .map((c) => `"${String(c ?? '').replace(/"/g, '""')}"`)
          .join(';');
      });
      const blob = new Blob(['\ufeff' + [header.join(';'), ...lines].join('\n')], { type: 'text/csv;charset=utf-8' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = 'faktury-export.csv';
      a.click();
      URL.revokeObjectURL(a.href);
      showToast('Export CSV byl stažen.', 'success');
    },
    async openDetail(invoiceId, vehicleId) {
      state.view = 'detail';
      state.previewModal = false;
      state.previewData = null;
      await loadDetail(invoiceId, vehicleId);
    },
    async openPreview(invoiceId, vehicleId) {
      const id = Number(invoiceId);
      const vid = Number(vehicleId);
      if (!id || !vid) return;
      if (state.detailData && Number(state.detailData.id) === id) {
        state.previewData = invoiceForDocument(state.detailData);
        state.previewModal = true;
        paint();
        return;
      }
      try {
        const full = await window.apiCall(`/api/v1/vehicles/${vid}/invoices/${id}`, 'GET');
        state.previewData = invoiceForDocument({ ...full, already_paid: !!(full?.extra?.already_paid) });
        state.previewModal = true;
        paint();
      } catch (e) {
        showToast(e?.message || 'Náhled nelze načíst.', 'error');
      }
    },
    closePreview() {
      state.previewModal = false;
      paint();
    },
    openPdf(invoiceId, vehicleId) {
      const id = Number(invoiceId);
      const vid = Number(vehicleId);
      if (!id || !vid) return;
      const path = `/api/v1/vehicles/${vid}/invoices/${id}/pdf`;
      if (typeof window.openAuthenticatedPdf === 'function') {
        window.openAuthenticatedPdf(path).catch((err) => showToast(err?.message || 'PDF se nepodařilo otevřít.', 'error'));
      } else {
        window.open(`${window.location.origin}${path}`, '_blank', 'noopener');
      }
    },
    sharePdfLink(invoiceId, vehicleId) {
      const id = Number(invoiceId);
      const vid = Number(vehicleId);
      if (!id || !vid) return;
      const url = `${window.location.origin}/api/v1/vehicles/${vid}/invoices/${id}/pdf`;
      if (navigator.clipboard?.writeText) {
        navigator.clipboard.writeText(url).then(() => showToast('Odkaz na PDF zkopírován.', 'success'));
      } else {
        showToast(url, 'info');
      }
    },
    contactService() {
      const inv = state.detailData;
      const email = inv?.extra?.supplier_email;
      if (email) {
        const subject = encodeURIComponent(`Dotaz k faktuře ${inv.invoice_number || ''}`);
        window.location.href = `mailto:${email}?subject=${subject}`;
        return;
      }
      showToast('Kontakt na autoservis není uveden — využijte záložku Servisy.', 'info');
      api.goServices();
    },
    openServiceRecord(vehicleId, recordId) {
      if (typeof switchTab !== 'function') return;
      switchTab('vehicles');
      window.setTimeout(() => {
        if (typeof window.openVehicleDetail === 'function') {
          window.openVehicleDetail(Number(vehicleId), { serviceRecordId: Number(recordId) });
        } else if (typeof window.viewVehicle === 'function') {
          window.viewVehicle(Number(vehicleId));
        }
      }, 200);
    },
    mountInto(el) {
      if (!el) return;
      state.mountEl = el;
      const sub = el.dataset?.invSubRoute || '';
      const path = String(window.location.pathname || '');
      if (sub === 'new' || path.includes('invoice-new')) {
        state.view = 'wizard';
      } else if (sub === 'settings' || path.includes('invoice-settings')) {
        state.view = 'settings';
      } else {
        state.view = 'list';
      }
      load(true);
    },
  };

  function auditLogLocal(action, id) {
    console.info('[USER_INVOICE_AUDIT]', action, { id, staging: true });
  }

  window.UserInvoicesDashboard = api;
  window.loadUserInvoices = function (force) {
    const tabMount = getMount();
    if (tabMount) state.mountEl = tabMount;
    if (!state.mountEl) {
      const legacy = document.getElementById('invoicesTabMount');
      if (legacy && legacy.closest('#invoicesTab')) state.mountEl = legacy;
    }
    return api.load(force);
  };

  function bootPrototypeInvoices(root) {
    if (!root || root._svInvoicesBound) return;
    const scroll = root.querySelector('.sv-prototype-scroll');
    if (!scroll) return;
    let page = root.querySelector('[data-sv-invoices-page]');
    if (!page) {
      page = document.createElement('div');
      page.setAttribute('data-sv-invoices-page', '1');
      page.hidden = true;
      page.className = 'sv-prototype-invoices-mount';
      scroll.appendChild(page);
    }
    root._svInvoicesBound = true;
    root._svInvoicesPage = page;
    if (!root._svInvoicesSync) {
      root._svInvoicesSync = function () {
        const isInv = root.__svProtoActiveNav === 'invoices';
        const dash = root.querySelector('[data-sv-view-dashboard]');
        const det = root.querySelector('[data-sv-view-detail]');
        const ov = root.querySelector('[data-sv-overview-page]');
        const veh = root.querySelector('[data-sv-vehicles-page]');
        if (page) page.hidden = !isInv;
        if (dash) dash.hidden = isInv || root.__svProtoView === 'detail';
        if (ov) ov.hidden = isInv || root.__svProtoView !== 'overview' || root.__svProtoActiveNav !== 'overview';
        if (veh) veh.hidden = isInv || root.__svProtoView !== 'overview' || root.__svProtoActiveNav !== 'vehicles';
        if (det) det.hidden = root.__svProtoView !== 'detail';
        if (isInv) api.mountInto(page);
      };
    }
  }

  window.UserInvoicesDashboard.bootPrototype = bootPrototypeInvoices;
})();
