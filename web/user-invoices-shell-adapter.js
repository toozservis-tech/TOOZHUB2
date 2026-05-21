/**
 * Uživatelské rozhraní faktur — adapter pro ServiceInvoicesDashboard (1:1 referenční UI).
 * Poskytuje window.serviceShell pro user-app-next.js bez servisního shellu.
 */
(function () {
  'use strict';

  const API_ISSUED = '/api/v1/user/invoices';
  const API_ELIGIBILITY = '/api/v1/user/invoices/eligibility';

  const userShellState = {
    mounted: false,
    mountEl: null,
    activeSection: 'invoices',
    loading: false,
    invoices: [],
    profile: null,
    invoiceListTab: 'overview',
    invoiceSearchTerm: '',
    invoiceStatusFilter: 'all',
    invoicePage: 1,
    invoicePerPage: 10,
    invoicePreviewModalId: null,
    invoicePreviewModalData: null,
    invoiceWizard: null,
    customers: [],
    eligible: null,
  };

  function esc(v) {
    return String(v ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function showToast(msg, kind) {
    if (typeof window.showAlert === 'function') window.showAlert(msg, kind || 'info');
  }

  function invoiceMoney(value, currency = 'CZK') {
    const n = Number(value || 0);
    return `${n.toLocaleString('cs-CZ', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${currency}`;
  }

  function formatDate(value) {
    if (!value) return '—';
    try {
      return new Date(value).toLocaleDateString('cs-CZ');
    } catch (e) {
      return String(value);
    }
  }

  function paintUserShell() {
    const mount = userShellState.mountEl;
    if (!mount || !userShellState.mounted) return;

    let html = '';
    if (userShellState.loading) {
      html = '<p class="sv-inv-loading-hint">Načítám faktury…</p>';
    } else if (userShellState.activeSection === 'invoice-new' && window.ServiceInvoicesDashboard?.renderWizard) {
      html = window.ServiceInvoicesDashboard.renderWizard();
    } else if (window.ServiceInvoicesDashboard?.renderList) {
      html = window.ServiceInvoicesDashboard.renderList();
    }

    const overlay =
      window.ServiceInvoicesDashboard?.renderPreviewOverlay && userShellState.invoicePreviewModalId
        ? window.ServiceInvoicesDashboard.renderPreviewOverlay()
        : '';

    mount.innerHTML = html + overlay;
    document.body.classList.toggle('sv-inv-modal-open', !!userShellState.invoicePreviewModalId);

    if (userShellState.activeSection === 'invoice-new' && window.ServiceInvoicesDashboard?.initWizardAfterRender) {
      window.requestAnimationFrame(() => {
        try {
          window.ServiceInvoicesDashboard.initWizardAfterRender();
        } catch (e) {
          console.warn('[USER_INVOICES] initWizardAfterRender:', e);
        }
      });
    }
  }

  async function loadUserIssuedInvoices(force) {
    if (userShellState.loading && !force) return;
    if (typeof window.apiCall !== 'function') {
      showToast('API není dostupné.', 'error');
      return;
    }
    userShellState.loading = true;
    paintUserShell();
    try {
      try {
        userShellState.eligible = await window.apiCall(API_ELIGIBILITY, 'GET');
      } catch (e) {
        userShellState.eligible = { eligible: false, message: e?.message || 'Nelze ověřit oprávnění.' };
      }
      const res = await window.apiCall(API_ISSUED, 'GET');
      userShellState.invoices = Array.isArray(res?.items) ? res.items : [];
      const prof = window.userProfile || window.currentUser || {};
      userShellState.profile = prof;
    } catch (e) {
      userShellState.invoices = [];
      showToast(e?.message || 'Faktury se nepodařilo načíst.', 'error');
    } finally {
      userShellState.loading = false;
      paintUserShell();
    }
  }

  function syncUserInvoicesUrl(section) {
    if (typeof window.syncUserTabUrlHistory !== 'function') return;
    if (String(section || '') === 'invoice-new') {
      window.syncUserTabUrlHistory('invoices', { replace: true });
      return;
    }
    window.syncUserTabUrlHistory('invoices', { replace: true });
  }

  function navigate(section) {
    if (section === 'invoice-new') {
      userShellState.activeSection = 'invoice-new';
    } else {
      userShellState.activeSection = 'invoices';
    }
    syncUserInvoicesUrl(section);
    paintUserShell();
  }

  function setInvoiceSearchTerm(value) {
    userShellState.invoiceSearchTerm = String(value || '');
    userShellState.invoicePage = 1;
    paintUserShell();
  }

  function setInvoiceStatusFilter(value) {
    userShellState.invoiceStatusFilter = String(value || 'all');
    userShellState.invoicePage = 1;
    paintUserShell();
  }

  function openServiceInvoicePdf(invoiceId) {
    const id = Number(invoiceId || 0);
    if (!id) return;
    const path = `${API_ISSUED}/${id}/pdf`;
    if (typeof window.openAuthenticatedPdf === 'function') {
      window.openAuthenticatedPdf(path).catch((err) => showToast(err?.message || 'PDF se nepodařilo otevřít.', 'error'));
    } else {
      window.open(`${window.location.origin}${path}`, '_blank', 'noopener');
    }
  }

  window.serviceShell = {
    state: userShellState,
    invoiceMode: 'user',
    invoiceApiBase: API_ISSUED,
    mounted: true,
    render: paintUserShell,
    navigate,
    load: loadUserIssuedInvoices,
    showToast,
    invoiceMoney,
    formatDate,
    openServiceInvoicePdf,
    setInvoiceSearchTerm,
    setInvoiceStatusFilter,
    goProfileSettings() {
      if (typeof window.switchTab === 'function') window.switchTab('settings');
      else {
        const btn = document.querySelector('.uapp-next-nav [data-uapp-action="settings"]');
        if (btn) btn.click();
      }
    },
    onVatDetail() {
      showToast('Detailní přehled DPH připravujeme.', 'info');
    },
    onInvoiceDateRange() {
      showToast('Filtr období připravujeme.', 'info');
    },
    focusDueList() {
      userShellState.invoiceStatusFilter = 'all';
      userShellState.invoiceListTab = 'overview';
      paintUserShell();
    },
    populateCustomerVehicleSelect() {
      return Promise.resolve();
    },
  };

  window.UserInvoicesShellAdapter = {
    mountInto(el) {
      if (!el) return;
      userShellState.mountEl = el;
      userShellState.mounted = true;
      userShellState.activeSection = 'invoices';
      if (window.ServiceInvoicesDashboard?.wireShellMethods) {
        window.ServiceInvoicesDashboard.wireShellMethods();
      }
      loadUserIssuedInvoices(true);
    },
    unmount() {
      userShellState.mounted = false;
      userShellState.mountEl = null;
    },
    reload(force) {
      return loadUserIssuedInvoices(!!force);
    },
    isEligible() {
      return userShellState.eligible?.eligible === true;
    },
  };
})();
