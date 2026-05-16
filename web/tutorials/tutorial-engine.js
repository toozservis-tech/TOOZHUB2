/** TutorialEngine — průvodce nad živým UI (globálně: apiCall, switchTab, __TUTORIAL_REGISTRY). */
(function () {
  'use strict';

  /** Návod nikdy neodvíjí krok od input/change; pouze od validního stavu (waitForValid). */
  var AUTO_NEXT_ON_INPUT = false;

  var FC = {
    SEL: 'TUTORIAL_SELECTOR_MISSING',
    VIS: 'UI_TARGET_NOT_VISIBLE',
    DIS: 'UI_TARGET_DISABLED',
    ROUTE: 'ROUTE_MISMATCH',
    MODAL: 'MODAL_NOT_OPENED',
    VAL: 'VALIDATION_BLOCKED',
    API: 'API_ERROR',
    PERM: 'PERMISSION_DENIED',
    CFG: 'TUTORIAL_CONFIG_ERROR',
    UK: 'UNKNOWN_TUTORIAL_FAILURE',
    DESYNC: 'STATE_DESYNC',
  };

  var st = {
    running: false,
    tid: null,
    idx: 0,
    timers: [],
    dispose: [],
    root: null,
    bkT: null,
    bkL: null,
    bkR: null,
    bkB: null,
    bubble: null,
    routeAttempts: 0,
    routeTabOnceDone: false,
    serviceSectionOnceDone: false,
    watchdogId: null,
    waitRafId: 0,
  };

  /** Coalescence reflowů (scroll/resize/popstate → jeden RAF). */
  var tutorialLayoutRefreshRaf = 0;

  function isCurrentServiceShell() {
    try {
      return typeof window.isServiceWorkspaceRole === 'function' && window.isServiceWorkspaceRole();
    } catch (_) {
      return false;
    }
  }

  /** @param {*} pack záznam z __TUTORIAL_REGISTRY */
  function tutorialRolesAllowPack(pack) {
    var roles = pack && pack.roles;
    var svc = isCurrentServiceShell();
    if (!roles || !roles.length) return !svc;
    for (var i = 0; i < roles.length; i++) {
      var x = String(roles[i] || '').trim().toLowerCase();
      if (x === 'both' || x === 'all' || x === '*') return true;
      if ((x === 'service' || x === 'servis' || x === 'staff') && svc) return true;
      if ((x === 'user' || x === 'consumer') && !svc) return true;
    }
    return false;
  }

  function tutorialPackModalGuardId() {
    var pack = def();
    if (!pack) return '';
    if (pack.modalGuardId === null || pack.modalGuardId === false) return '';
    if (typeof pack.modalGuardId === 'string') {
      var gs = pack.modalGuardId.replace(/^#/, '').trim();
      if (gs) return gs;
    }
    var tid = String(pack.id || '');
    if (tid === 'add-vehicle') return 'addVehicleModal';
    return '';
  }

  /** @returns {HTMLElement|null} */
  function modalElByTutorialPack() {
    var id = tutorialPackModalGuardId();
    if (!id) return null;
    return document.getElementById(id);
  }

  function tutorialModalGuardOpen() {
    var m = modalElByTutorialPack();
    if (!m) return true;
    return modalOk(m);
  }

  /** Sloupek #addVehicleModalBody — scroll uvnitř modalu ladí díru. */
  var tutorialVehicleModalScrollHookAttached = false;
  function tutorialEnsureModalBodyScrollHook() {
    var gid = tutorialPackModalGuardId();
    if (!gid || gid !== 'addVehicleModal' || tutorialVehicleModalScrollHookAttached) return;
    var el = document.getElementById('addVehicleModalBody');
    if (!el) return;
    tutorialVehicleModalScrollHookAttached = true;
    el.addEventListener(
      'scroll',
      function () {
        scheduleTutorialLayoutRefresh();
      },
      { passive: true },
    );
  }

  function dbg() {
    window.__tutorialEngineDebug = window.__tutorialEngineDebug || {};
    return window.__tutorialEngineDebug;
  }

  function cat(code) {
    if (!code) return 'none';
    if (code === FC.SEL || code === FC.CFG) return 'tutorial_config_selector';
    if (code === FC.VAL) return 'validation';
    if (code === FC.PERM) return 'permission';
    if (code === FC.API) return 'backend';
    if (
      code === FC.ROUTE ||
      code === FC.MODAL ||
      code === FC.VIS ||
      code === FC.DIS ||
      code === FC.DESYNC
    )
      return 'tutorial_flow_ui';
    return 'unknown_or_app';
  }

  function setFail(code, ctx) {
    var d = dbg();
    d.lastFailureCode = code || '';
    d.lastFailureCategory = cat(code);
    d.lastContext = ctx || {};
    if (document.body) document.body.dataset.tutorialLastFailure = code || '';
    try {
      console.warn('[tutorial]', code, ctx);
    } catch (_) {}
  }

  function tutorialLegacyUserTabSelector(dtKey) {
    /** Fallback pro SPA kde nejsou všechny záložky označeny `data-tutorial`. */
    switch (dtKey) {
      case 'user-tab-home':
        return '.tabs .tab[data-tab-key="home"]';
      case 'user-tab-vehicles':
        return '.tabs .tab[data-tab-key="vehicles"]';
      case 'user-tab-reminders':
        return '.tabs .tab[data-tab-key="reminders"]';
      case 'user-tab-reservations':
        return '.tabs .tab[data-tab-key="reservations"]';
      case 'user-tab-documents':
        return '.tabs .tab[data-tab-key="documents"]';
      case 'user-tab-support':
        return '.tabs .tab[data-tab-key="support"]';
      case 'user-tab-account':
        return '.tabs .tab[data-tab-key="account"]';
      default:
        return '';
    }
  }

  function q(key) {
    if (!key) return null;
    var escKey = String(key).replace(/"/g, '');
    var direct = escKey ? document.querySelector('[data-tutorial="' + escKey + '"]') : null;
    if (direct instanceof Element) return direct;
    var alt = tutorialLegacyUserTabSelector(escKey);
    return alt ? document.querySelector(alt) : null;
  }

  /** Spodní okraj viditelné oblasti (visualViewport; po přepnutí karty / mobilní liště nesedí innerHeight samotný). */
  function viewportBottomY() {
    var vv = window.visualViewport;
    if (vv && typeof vv.height === 'number') {
      var topOff = typeof vv.offsetTop === 'number' ? vv.offsetTop : 0;
      return Math.min(window.innerHeight, topOff + vv.height);
    }
    return window.innerHeight;
  }

  function authOk() {
    try {
      if (typeof window.isAuthenticated === 'function' && window.isAuthenticated()) return true;
      if (window.accessToken) return true;
    } catch (_) {}
    return false;
  }

  function apiPost(kind, payload) {
    if (!authOk() || typeof window.apiCall !== 'function') return Promise.resolve(null);
    var u =
      kind === 'start'
        ? '/api/v1/tutorials/progress/start'
        : kind === 'step'
          ? '/api/v1/tutorials/progress/step'
          : kind === 'done'
            ? '/api/v1/tutorials/progress/complete'
            : kind === 'skip'
              ? '/api/v1/tutorials/progress/skip'
              : '';
    return u ? window.apiCall(u, 'POST', payload).catch(function () { return null; }) : Promise.resolve(null);
  }

  function reportTutorialFailure(code, ctx) {
    setFail(code, ctx || {});
    if (st.running && st.tid && ctx && ctx.stepId) {
      apiPost('step', { tutorial_id: st.tid, step_id: ctx.stepId, failure_code: code });
    }
    updateDiagBanner();
  }

  function tabKey() {
    var b = document.querySelector('.tab.active[data-tab-key]');
    return b ? b.getAttribute('data-tab-key') || '' : '';
  }

  function modalOk(el) {
    return !!(el && el.classList.contains('active') && window.getComputedStyle(el).display !== 'none');
  }

  function visible(el) {
    if (!(el instanceof Element)) return false;
    var r = el.getBoundingClientRect();
    var cs = window.getComputedStyle(el);
    if (r.width < 2 || r.height < 2) return false;
    if (cs.visibility === 'hidden' || cs.display === 'none' || Number(cs.opacity) === 0) return false;
    return true;
  }

  function enabled(el) {
    if (!(el instanceof Element)) return true;
    return !el.matches(':disabled,[aria-disabled="true"]');
  }

  function inputTrimLen(dataTutorialKey) {
    var el = q(dataTutorialKey);
    if (!(el instanceof HTMLInputElement) && !(el instanceof HTMLTextAreaElement)) return -1;
    return String(el.value || '').trim().length;
  }

  var WAIT_PREDICATES = {
    vinLen17: function () {
      return inputTrimLen('vehicle-vin-input') >= 17;
    },
    nameMin2: function () {
      return inputTrimLen('vehicle-name-input') >= 2;
    },
    plateNonEmpty: function () {
      return inputTrimLen('vehicle-plate-input') >= 1;
    },
    stkDateNonEmpty: function () {
      return inputTrimLen('vehicle-stk-input') >= 8;
    },
  };

  function tutorialStepRequiresModalGuard(step) {
    if (!tutorialPackModalGuardId()) return false;
    if (!step || !step.id) return false;
    var id = step.id;
    if (
      id === 'go-vehicles-tab' ||
      id === 'highlight-add-open' ||
      id === 'wait-add-modal' ||
      id === 'done-celebrate'
    )
      return false;
    return true;
  }

  function cancelTutorialWaitRaf() {
    if (st.waitRafId) {
      try {
        window.cancelAnimationFrame(st.waitRafId);
      } catch (_) {}
      st.waitRafId = 0;
    }
  }

  var overlayReflowListenersAttached = false;
  function tutorialAttachOverlayReflowListeners() {
    if (overlayReflowListenersAttached) return;
    overlayReflowListenersAttached = true;
    window.addEventListener('resize', scheduleTutorialLayoutRefresh);
    window.addEventListener('scroll', scheduleTutorialLayoutRefresh, true);
    if (window.visualViewport) {
      window.visualViewport.addEventListener('resize', scheduleTutorialLayoutRefresh);
      window.visualViewport.addEventListener('scroll', scheduleTutorialLayoutRefresh, { passive: true });
    }
  }

  function ensureTutorialWatchdog() {
    if (st.watchdogId != null) return;
    st.watchdogId = window.setInterval(function () {
      if (!st.running) return;
      var csWatch = currentStep();
      if (
        csWatch &&
        tutorialStepRequiresModalGuard(csWatch) &&
        !tutorialModalGuardOpen()
      ) {
        reportTutorialFailure(FC.MODAL, { stepId: csWatch.id, reason: 'state_desync' });
        dbg().tutorialStopReason = 'state_desync';
        hardResetTutorialUI();
        return;
      }

      var attr = currentTargetAttr();
      if (!attr) return;
      var target = q(attr);
      if (!target) {
        reportTutorialFailure(FC.VIS, {
          stepId: csWatch ? csWatch.id : null,
          reason: 'lost_target',
        });
        dbg().tutorialStopReason = 'lost_target';
        hardResetTutorialUI();
      }
    }, 500);
  }

  function forceRecalculatePosition() {
    scheduleTutorialLayoutRefresh();
    tutorialLayoutRefresh();
  }

  function revalidateCurrentStep() {
    if (!st.running) return;
    var step = currentStep();
    if (!step) {
      reportTutorialFailure(FC.DESYNC, { stepId: null, reason: 'no_current_step' });
      dbg().tutorialStopReason = 'state_desync';
      hardResetTutorialUI();
      return;
    }
    /** Při přepisu focusu pole (datum, klávesnice) může být chvíli falešně „modal zavřený“ — watchdog modal stále hlídá periodicky. */
    var loosenModalGuard = step.actionType === 'observeFormValidation';
    if (
      !loosenModalGuard &&
      tutorialStepRequiresModalGuard(step) &&
      !tutorialModalGuardOpen()
    ) {
      reportTutorialFailure(FC.MODAL, { stepId: step.id, reason: 'state_desync' });
      dbg().tutorialStopReason = 'state_desync';
      hardResetTutorialUI();
      return;
    }
    forceRecalculatePosition();
  }

  function hardResetTutorialUI() {
    try {
      if (window.TutorialEngine && typeof window.TutorialEngine.unlockClicks === 'function')
        window.TutorialEngine.unlockClicks();
    } catch (_) {}
    teardownLayerOnly();
  }

  function escHtml(s) {
    return String(s || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function addTimer(fn, ms) {
    var id = window.setTimeout(fn, ms);
    st.timers.push(id);
    return id;
  }

  function clearTimers() {
    st.timers.forEach(window.clearTimeout);
    st.timers.length = 0;
  }

  function clearDispose() {
    st.dispose.forEach(function (f) {
      try {
        f();
      } catch (_) {}
    });
    st.dispose.length = 0;
  }

  function def() {
    var r = window.__TUTORIAL_REGISTRY || {};
    return st.tid ? r[st.tid] : null;
  }

  function currentStep() {
    var d = def();
    return d && d.steps ? d.steps[st.idx] : null;
  }

  function currentTargetAttr() {
    var s = currentStep();
    return s && s.target ? s.target : '';
  }

  function updateDiagBanner() {
    if (!st.bubble) return;
    var nx = st.bubble.querySelector('[data-role=d]');
    if (!nx) return;
    var code = dbg().lastFailureCode;
    if (!code) {
      nx.style.display = 'none';
      return;
    }
    nx.style.display = 'block';
    nx.textContent = 'Diagnostika: ' + code + ' · ' + cat(code);
  }

  function scheduleTutorialLayoutRefresh() {
    if (!st.running) return;
    if (tutorialLayoutRefreshRaf) return;
    tutorialLayoutRefreshRaf = window.requestAnimationFrame(function () {
      tutorialLayoutRefreshRaf = 0;
      tutorialLayoutRefresh();
    });
  }

  function tutorialLayoutRefresh() {
    if (!st.running) return;
    tutorialEnsureModalBodyScrollHook();
    try {
      positionHole(q(currentTargetAttr()));
    } catch (_) {}
  }

  var tutorialLifecycleHooksAttached = false;
  function tutorialEnsureLifecycleHooks() {
    if (tutorialLifecycleHooksAttached) return;
    tutorialLifecycleHooksAttached = true;

    document.addEventListener(
      'visibilitychange',
      function () {
        if (document.hidden || !st.running) return;
        revalidateCurrentStep();
        scheduleTutorialLayoutRefresh();
        requestAnimationFrame(function () {
          requestAnimationFrame(function () {
            if (!st.running) return;
            revalidateCurrentStep();
            scheduleTutorialLayoutRefresh();
          });
        });
      },
      false,
    );

    var tutorialsFocusDeb;
    window.addEventListener(
      'focus',
      function () {
        if (!st.running) return;
        window.clearTimeout(tutorialsFocusDeb);
        tutorialsFocusDeb = window.setTimeout(function () {
          revalidateCurrentStep();
          scheduleTutorialLayoutRefresh();
        }, 50);
      },
      false,
    );

    window.addEventListener(
      'pageshow',
      function () {
        if (!st.running) return;
        revalidateCurrentStep();
        scheduleTutorialLayoutRefresh();
      },
      false,
    );

    window.addEventListener(
      'popstate',
      function () {
        if (!st.running) return;
        revalidateCurrentStep();
        scheduleTutorialLayoutRefresh();
      },
      false,
    );
  }

  function ensureLayer() {
    if (st.root) return;

    function mkBlocker() {
      var el = document.createElement('div');
      el.style.cssText =
        'position:fixed;background:rgba(6,13,29,.62);backdrop-filter:blur(2px);pointer-events:auto';
      el.addEventListener(
        'pointerdown',
        function (e) {
          e.preventDefault();
          e.stopPropagation();
        },
        true,
      );
      return el;
    }

    st.root = document.createElement('div');
    st.root.id = 'app-tutorial-overlay-root';
    st.root.style.cssText = 'position:fixed;inset:0;z-index:2147483000;pointer-events:none';

    st.bkT = mkBlocker();
    st.bkL = mkBlocker();
    st.bkR = mkBlocker();
    st.bkB = mkBlocker();
    [st.bkT, st.bkL, st.bkR, st.bkB].forEach(function (x) {
      st.root.appendChild(x);
    });

    st.bubble = document.createElement('div');
    st.bubble.dataset.testid = 'tutorial-bubble';
    st.bubble.style.cssText =
      'position:fixed;z-index:2147483200;pointer-events:auto;' +
      'max-width:min(440px,calc(100vw - 32px));padding:14px 16px;border-radius:14px;' +
      'background:rgba(14,21,41,.96);color:#e2e8f0;' +
      'font:0.93rem/1.45 ui-sans-serif,system-ui,sans-serif;box-shadow:0 20px 64px rgba(0,0,0,.5)';
    st.bubble.innerHTML =
      '<div data-role=t style="font-weight:700;margin-bottom:6px"></div>' +
      '<div data-role=x></div>' +
      '<div data-role=d style="display:none;margin-top:8px;color:#fca5a5;font-size:.8rem"></div>' +
      '<div data-role=c style="margin-top:12px;display:flex;flex-wrap:wrap;gap:8px;justify-content:flex-end"></div>';

    st.root.appendChild(st.bubble);
    document.body.appendChild(st.root);
  }

  function clrHighlight() {
    document.querySelectorAll('.tutorial-highlight-target').forEach(function (n) {
      try {
        if (n.dataset.tutorialZPrior !== undefined) {
          n.style.zIndex = n.dataset.tutorialZPrior;
          delete n.dataset.tutorialZPrior;
        } else {
          n.style.zIndex = '';
        }
        if (n.dataset.tutorialPosPrior !== undefined) {
          n.style.position = n.dataset.tutorialPosPrior;
          delete n.dataset.tutorialPosPrior;
        } else {
          n.style.position = '';
        }
      } catch (_) {}
      n.classList.remove('tutorial-highlight-target');
      n.style.boxShadow = '';
    });
  }

  /** Psací cíle (bez reliance na `matches` kvůli WebView / některým embedded prohlížečům). */
  function isTypingTarget(el) {
    if (!(el instanceof HTMLElement)) return false;
    var t = String(el.tagName || '').toUpperCase();
    if (t === 'TEXTAREA') return true;
    if (t === 'SELECT') return true;
    if (t === 'INPUT') {
      var tp = String(el.type || 'text').toLowerCase();
      if (tp === 'button' || tp === 'submit' || tp === 'reset' || tp === 'checkbox' || tp === 'radio' || tp === 'file')
        return false;
      return true;
    }
    return false;
  }

  /** Pozná krok/VIN jen z DOM/step id (bez `visible`, aby ho top=12 fallback chytil v jedné snímku). */
  function isVinTutorialInput(el, stepSnap) {
    if (!(el instanceof Element)) return false;
    try {
      if (String(el.getAttribute('data-tutorial') || '') === 'vehicle-vin-input') return true;
      if (stepSnap && typeof stepSnap === 'object' && stepSnap.id === 'field-vin') return true;
    } catch (_) {}
    return false;
  }

  /** Vždy pod spodní hranici zvýrazněného řádku (`top ≠ 12` fallback přes vstupní pole). */
  function applyPinnedBubbleBelow(el, vw0) {
    var gPin = 16;
    var edgePin = vw0 < 640 ? 8 : 12;
    var bottomY = viewportBottomY();
    var brP = el.getBoundingClientRect();
    var topPx = brP.bottom + gPin;
    if (topPx > bottomY - edgePin - 52) {
      try {
        el.scrollIntoView({ block: 'center', inline: 'nearest', behavior: 'instant' });
      } catch (_) {}
      brP = el.getBoundingClientRect();
      bottomY = viewportBottomY();
      topPx = brP.bottom + gPin;
    }
    void st.bubble.offsetWidth;
    void st.bubble.offsetHeight;
    var availH = Math.max(96, bottomY - topPx - edgePin);
    st.bubble.style.top = topPx + 'px';
    st.bubble.style.maxHeight = availH + 'px';
    st.bubble.style.overflow = 'auto';
    st.bubble.style.bottom = '';
    st.bubble.style.transform = '';
    if (vw0 < 640) {
      st.bubble.style.left = edgePin + 'px';
      st.bubble.style.right = edgePin + 'px';
    } else {
      st.bubble.style.right = '';
      var bwP = Math.max(1, st.bubble.offsetWidth);
      var lP = Math.min(Math.max(edgePin, brP.left), vw0 - bwP - edgePin);
      st.bubble.style.left = lP + 'px';
    }
  }

  function bubbleOverlapsAvoidBox(lt, bx, bw, bh) {
    return (
      lt.l <
        bx.l +
          bx.w &&
      lt.l +
        bw >
        bx.l &&
      lt.t <
        bx.t +
          bx.h &&
      lt.t +
        bh >
        bx.t
    );
  }

  /** Plánování pozice bubliny (desktop) — respektuje `placement` kroku a nedojíždí do výřezu cíle. */
  function planBubbleDesktop(el, br, vw, vh) {
    var gap = 16;
    var edge = 12;
    void st.bubble.offsetWidth;
    void st.bubble.offsetHeight;
    var bw = Math.max(1, st.bubble.offsetWidth);
    var bh = Math.max(1, st.bubble.offsetHeight);

    var avoid = {
      l: br.left - gap,
      t: br.top - gap,
      w: br.width + 2 * gap,
      h: br.height + 2 * gap,
    };

    var step = currentStep();
    var pref = step && step.placement ? String(step.placement).toLowerCase().trim() : '';
    var order =
      pref === 'bottom'
        ? ['below', 'above', 'right', 'left']
        : pref === 'top'
          ? ['above', 'below', 'right', 'left']
          : isTypingTarget(el)
            ? ['below', 'above', 'right', 'left']
            : ['above', 'below', 'right', 'left'];

    function clampLt(lt) {
      var l = lt.l;
      var t = lt.t;
      l = Math.min(Math.max(edge, l), vw - bw - edge);
      t = Math.min(Math.max(edge, t), vh - bh - edge);
      return { l: l, t: t };
    }

    function hzAlignField() {
      return Math.min(Math.max(edge, br.left), vw - bw - edge);
    }

    var candidates = {
      below: function () {
        var l = hzAlignField();
        var t = br.bottom + gap;
        return { l: l, t: t };
      },
      above: function () {
        var l = hzAlignField();
        var t = br.top - bh - gap;
        return { l: l, t: t };
      },
      right: function () {
        var l = br.right + gap;
        var t = br.top + br.height / 2 - bh / 2;
        return { l: l, t: t };
      },
      left: function () {
        var l = br.left - bw - gap;
        var t = br.top + br.height / 2 - bh / 2;
        return { l: l, t: t };
      },
    };

    for (var oi = 0; oi < order.length; oi++) {
      var cand = clampLt(candidates[order[oi]]());
      if (!bubbleOverlapsAvoidBox(cand, avoid, bw, bh)) return cand;
    }

    if (!(pref === 'bottom' && isTypingTarget(el))) {
      var center = clampLt({ l: (vw - bw) / 2, t: edge });
      if (!bubbleOverlapsAvoidBox(center, avoid, bw, bh)) return center;
    }

    /** Poslední únik: co nejnižší v okně, kde se ještě neřeže s cílem. */
    var bottomTry = clampLt({ l: hzAlignField(), t: vh - bh - edge });
    if (!bubbleOverlapsAvoidBox(bottomTry, avoid, bw, bh)) return bottomTry;

    return clampLt({
      l: hzAlignField(),
      t: Math.min(br.bottom + gap, vh - bh - edge),
    });
  }

  function positionHole(el) {
    if (!st.root) return;

    if (el instanceof HTMLElement) {
      var avModalEarly = modalElByTutorialPack();
      if (
        avModalEarly &&
        avModalEarly.classList.contains('active') &&
        avModalEarly.contains(el)
      ) {
        try {
          el.scrollIntoView({ block: 'center', inline: 'nearest', behavior: 'instant' });
        } catch (_) {}
      }
    }

    clrHighlight();

    var pad = 10;
    var vw =
      window.visualViewport && window.visualViewport.width ? window.visualViewport.width : window.innerWidth;

    if (el instanceof Element && visible(el)) {
      try {
        el.classList.add('tutorial-highlight-target');
        el.style.boxShadow = '0 0 0 3px #60a5fa, 0 12px 40px rgba(37,99,235,.52)';
        if (el.dataset.tutorialZPrior === undefined) el.dataset.tutorialZPrior = el.style.zIndex || '';
        if (el.dataset.tutorialPosPrior === undefined) el.dataset.tutorialPosPrior = el.style.position || '';
        if (window.getComputedStyle(el).position === 'static') el.style.position = 'relative';
        el.style.zIndex = '2147483050';
      } catch (_) {}

      var r = el.getBoundingClientRect(),
        x0 = Math.max(0, r.left - pad),
        y0 = Math.max(0, r.top - pad),
        x1 = Math.min(window.innerWidth, r.right + pad),
        y1 = Math.min(window.innerHeight, r.bottom + pad);

      st.bkT.style.left = '0';
      st.bkT.style.top = '0';
      st.bkT.style.width = '100%';
      st.bkT.style.height = y0 + 'px';

      st.bkB.style.left = '0';
      st.bkB.style.top = y1 + 'px';
      st.bkB.style.width = '100%';
      st.bkB.style.height = Math.max(0, window.innerHeight - y1) + 'px';

      st.bkL.style.left = '0';
      st.bkL.style.top = y0 + 'px';
      st.bkL.style.width = x0 + 'px';
      st.bkL.style.height = Math.max(0, y1 - y0) + 'px';

      st.bkR.style.left = x1 + 'px';
      st.bkR.style.top = y0 + 'px';
      st.bkR.style.width = Math.max(0, window.innerWidth - x1) + 'px';
      st.bkR.style.height = Math.max(0, y1 - y0) + 'px';

      try {
        var modalAdd = modalElByTutorialPack();
        var skipInnerScroll =
          modalAdd &&
          modalAdd.classList.contains('active') &&
          modalAdd.contains(el);
        if (!skipInnerScroll) {
          var vh =
            window.visualViewport && window.visualViewport.height
              ? window.visualViewport.height
              : window.innerHeight;
          var br = el.getBoundingClientRect();
          if (br.bottom > vh - 112 || br.top < 76) {
            el.scrollIntoView({
              block: isTypingTarget(el) ? 'nearest' : 'center',
              behavior: 'instant',
            });
          }
        }
      } catch (_) {}
    } else {
      st.bkT.style.left = '0';
      st.bkT.style.top = '0';
      st.bkT.style.width = '100%';
      st.bkT.style.height = '100%';
      st.bkL.style.width =
        '0';
      st.bkL.style.height = '0';
      st.bkR.style.width =
        '0';
      st.bkR.style.height =
        '0';
      st.bkB.style.height = '0';
    }

    st.bubble.style.transform = '';

    void st.bubble.offsetWidth;
    void st.bubble.offsetHeight;

    var snapStep = currentStep();

    if (el instanceof Element && isVinTutorialInput(el, snapStep)) {
      st.bubble.style.left = '';
      st.bubble.style.right = '';
      st.bubble.style.bottom = '';
      applyPinnedBubbleBelow(el, vw);
    } else if (vw < 640) {
      st.bubble.style.overflow = 'auto';
      var placM = snapStep && snapStep.placement ? String(snapStep.placement).toLowerCase().trim() : '';
      var bottomTypingMob =
        el instanceof Element &&
        visible(el) &&
        isTypingTarget(el) &&
        placM === 'bottom';
      if (bottomTypingMob) {
        st.bubble.style.left = '';
        st.bubble.style.right = '';
        st.bubble.style.bottom = '';
        applyPinnedBubbleBelow(el, vw);
      } else if (el instanceof Element && visible(el) && isTypingTarget(el)) {
        st.bubble.style.left = '8px';
        st.bubble.style.right = '8px';
        st.bubble.style.top = 'calc(10px + env(safe-area-inset-top,0px))';
        st.bubble.style.bottom = '';
        st.bubble.style.maxHeight = 'min(38vh, 300px)';
      } else {
        st.bubble.style.left = '8px';
        st.bubble.style.right = '8px';
        st.bubble.style.bottom = 'calc(14px + env(safe-area-inset-bottom,0px))';
        st.bubble.style.top = '';
        st.bubble.style.maxHeight = '44vh';
      }
    } else if (el instanceof Element && visible(el)) {
      st.bubble.style.left = '';
      st.bubble.style.right = '';
      st.bubble.style.bottom = '';
      var placD =
        snapStep && snapStep.placement ? String(snapStep.placement).toLowerCase().trim() : '';
      var anchorBelowFieldDesk = isTypingTarget(el) && placD === 'bottom';
      if (anchorBelowFieldDesk) {
        applyPinnedBubbleBelow(el, vw);
      } else {
        st.bubble.style.maxHeight = '';
        var br2 = el.getBoundingClientRect();
        var vhBox = viewportBottomY();
        var lt = planBubbleDesktop(el, br2, vw, vhBox);
        st.bubble.style.left = lt.l + 'px';
        st.bubble.style.top = lt.t + 'px';
      }
    } else {
      st.bubble.style.left = '50%';
      st.bubble.style.top = '11%';
      st.bubble.style.transform = 'translateX(-50%)';
      st.bubble.style.bottom = '';
      st.bubble.style.right = '';
      st.bubble.style.maxHeight = '';
    }

    if (st.bubble) {
      st.bubble.style.background = 'rgba(14,21,41,.96)';
      st.bubble.style.color = '#e2e8f0';
    }

    updateDiagBanner();
  }

  function mandatoryAddVehicleFields() {
    var nm = q('vehicle-name-input'),
      pl = q('vehicle-plate-input'),
      sk = q('vehicle-stk-input'),
      nv = nm && nm.value ? nm.value.trim() : '',
      pv = pl && pl.value ? pl.value.trim() : '',
      sv = sk && sk.value ? sk.value.trim() : '';
    var miss = [];
    if (nv.length < 2) miss.push('název vozidla');
    if (!pv) miss.push('SPZ');
    if (!sv) miss.push('platnost STK');
    return { ok: !miss.length, missing: miss };
  }

  function paint(stepObj, extras) {
    ensureLayer();
    extras = extras || {};
    var packSnap = def();
    var tot = packSnap && packSnap.steps ? packSnap.steps.length : 0;
    var prog = tot ? 'Krok ' + (st.idx + 1) + '/' + tot + ': ' : '';
    st.bubble.querySelector('[data-role=t]').textContent = prog + (stepObj.title || '');
    st.bubble.querySelector('[data-role=x]').innerHTML =
      escHtml(stepObj.text || '') + (extras.htmlAppend || '');
    var ct = st.bubble.querySelector('[data-role=c]');
    ct.innerHTML = '';

    var cssBase =
      'padding:9px 12px;border-radius:11px;font:inherit;cursor:pointer;border:1px solid rgba(148,163,184,.45)';

    function addBtn(label, style, fn) {
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.textContent = label;
      btn.style.cssText = style;
      btn.onclick = fn;
      ct.appendChild(btn);
    }

    if (
      st.idx > 0 &&
      (stepObj.actionType === 'next' ||
        stepObj.actionType === 'review' ||
        stepObj.actionType === 'waitForValid') &&
      extras.allowBack !== false
    ) {
      addBtn('Zpět', cssBase + ';background:#0f172a;color:#e2e8f0', function () {
        clearDispose();
        clearTimers();
        cancelTutorialWaitRaf();
        st.idx -= 1;
        execMain();
      });
    }

    addBtn('Přeskočit', cssBase + ';background:#0f172a;color:#e2e8f0', function () {
      skipTutorial('user_skip');
    });

    if (
      packSnap &&
      packSnap.id &&
      st.idx > 0
    )
      addBtn(
        'Znovu od začátku',
        cssBase + ';background:#0f172a;color:#e2e8f0;font-size:0.86rem;',
        function () {
          window.TutorialEngine.startTutorial(packSnap.id);
        },

      );


    var advanceByButton =
      stepObj.actionType === 'next' ||
      stepObj.actionType === 'review' ||
      (extras.plainAdvance === true && stepObj.actionType !== 'waitForValid');
    if (advanceByButton) {
      addBtn(
        extras.advanceLabel || 'Další',
        cssBase + ';background:#2563eb;border-color:#2563eb;color:#fff',
        extras.onAdvance ||
          function () {
            /** Pro `review` s `waitPredicate` neposouváme jen podle hodnot (autofill po VIN — uživatelský vstup bez kliknutí „Další“). */
            var k = stepObj.waitPredicate ? String(stepObj.waitPredicate) : '';
            var pchk = k ? WAIT_PREDICATES[k] : null;
            if (typeof pchk === 'function') {
              if (!pchk()) {
                reportTutorialFailure(FC.VAL, { stepId: stepObj.id });
                return;
              }
            }
            execAdvance();
          },
      );
    }

    positionHole(stepObj.target ? q(stepObj.target) : null);
    updateDiagBanner();
  }

  function execAdvance() {
    clearDispose();
    clearTimers();
    cancelTutorialWaitRaf();
    st.idx += 1;
    execMain();
  }

  function execModal(s) {
    var dl = Date.now() + (Number(s.timeoutMs) || 60000);
    /** Neukončovat hned při display:none (modal často startuje jako skrytý, než dorazí aktivní stav z předchozího UI). */
    var openedGraceUntil = Date.now() + 2000;

    var tick = function () {
      var m = q(s.target);

      if (!(m instanceof Element)) {
        if (Date.now() > dl) {
          reportTutorialFailure(FC.SEL, {
            stepId: s.id,
          });

          teardown(false);
        } else addTimer(tick, 200);

        return;
      }

      var okModal = modalOk(m);

      if (!okModal && Date.now() > openedGraceUntil) {
        var dspNm = '';
        try {
          dspNm = window.getComputedStyle(m).display;
        } catch (_) {}

        /** Prvek existuje, ale formulář je zavřený — nekousat se celý dlouhý timeout. */
        if (!m.classList.contains('active') && dspNm === 'none') {
          reportTutorialFailure(FC.MODAL, {
            stepId: s.id,
            reason: 'modal_not_visible_after_grace',
          });
          teardown(false);
          return;
        }
      }

      if (okModal) execAdvance();
      else if (Date.now() > dl) {
        reportTutorialFailure(FC.MODAL, { stepId: s.id });

        teardown(false);
      } else {
        positionHole(m);

        addTimer(tick, 220);
      }
    };

    tick();
  }

  function execClick(s) {

    var dl = Date.now() + (Number(s.timeoutMs) || 120000),

      done =
        false;

    var tick = function () {

      var el =
        q(s.target);

      function fail(code) {

        if (done) return;

        done =
          true;

        reportTutorialFailure(code, { stepId: s.id });

        teardown(false);

      }

      if (!(el instanceof Element)) {

        if (
          Date.now() > dl)

          return fail(FC.SEL);

        return addTimer(tick, 220);

      }

      if (!visible(el)) {

        if (Date.now() > dl) return fail(FC.VIS);

        return addTimer(tick, 200);

      }

      if (!enabled(el)) {

        if (Date.now() > dl) return fail(FC.DIS);

        return addTimer(tick, 200);

      }

      positionHole(el);

      if (
        el.dataset.tutorialArmedClick ===
        '1')
        {

        /** wait for handler */

        return;

      }

      el.dataset.tutorialArmedClick =
        '1';

      el.addEventListener(
        'click',
        function once() {

          el.removeEventListener('click', once, true);

          if (done) return;

          done =
            true;

          delete el.dataset.tutorialArmedClick;

          execAdvance();

        },
        true,
      );

    };

    tick();

  }

  function execWaitForValid(sObj) {
    var predKey = sObj && sObj.waitPredicate ? String(sObj.waitPredicate) : '';
    var predFn = WAIT_PREDICATES[predKey];
    if (!predFn) {
      reportTutorialFailure(FC.CFG, { stepId: sObj.id, waitPredicate: predKey });
      teardown(false);
      return;
    }

    var deadline = Date.now() + (+sObj.timeoutMs || 120000);
    var stepSnapshotId = sObj.id;
    st.dispose.push(cancelTutorialWaitRaf);

    function tickWait() {
      st.waitRafId = 0;
      if (!st.running) return;

      var liveStep = currentStep();
      if (!liveStep || liveStep.id !== stepSnapshotId) return;

      if (tutorialStepRequiresModalGuard(sObj) && !tutorialModalGuardOpen()) {
        reportTutorialFailure(FC.MODAL, { stepId: sObj.id, reason: 'state_desync' });
        dbg().tutorialStopReason = 'state_desync';
        hardResetTutorialUI();
        return;
      }

      var inp = q(sObj.target);
      if (!(inp instanceof Element)) {
        if (Date.now() > deadline) {
          reportTutorialFailure(FC.SEL, { stepId: sObj.id });
          teardown(false);
          return;
        }
        st.waitRafId = window.requestAnimationFrame(tickWait);
        return;
      }
      if (!visible(inp)) {
        if (Date.now() > deadline) {
          reportTutorialFailure(FC.VIS, { stepId: sObj.id });
          teardown(false);
          return;
        }
        st.waitRafId = window.requestAnimationFrame(tickWait);
        return;
      }
      if (!enabled(inp)) {
        if (Date.now() > deadline) {
          reportTutorialFailure(FC.DIS, { stepId: sObj.id });
          teardown(false);
          return;
        }
        st.waitRafId = window.requestAnimationFrame(tickWait);
        return;
      }

      positionHole(inp);

      var okPred = false;
      try {
        okPred = !!predFn();
      } catch (e) {
        reportTutorialFailure(FC.UK, {
          stepId: sObj.id,
          message: String(e && e.message ? e.message : e),
        });
        teardown(false);
        return;
      }

      if (okPred) {
        cancelTutorialWaitRaf();
        execAdvance();
        return;
      }

      if (Date.now() > deadline) {
        reportTutorialFailure(FC.VAL, { stepId: sObj.id, waitPredicate: predKey });
        teardown(false);
        return;
      }

      st.waitRafId = window.requestAnimationFrame(tickWait);
    }

    st.waitRafId = window.requestAnimationFrame(tickWait);
  }

  function execValidate(sObj) {

    var iv = null,

      tick = function () {

        var m =
          mandatoryAddVehicleFields();

        var line =
          m.ok
            ? '<p style="margin-top:.65rem;line-height:1.45;color:#bbf7d0"><strong>V pořádku:</strong> povinná pole pro uložení vypadají vyplněná.</p>'
            : '<p style="margin-top:.65rem;line-height:1.45;color:#fde68a"><strong>Ještě doplňte:</strong> ' +
              escHtml(m.missing.join(', ')) +
              '.</p>';

        paint(sObj, {

          plainAdvance:

            true,

          htmlAppend:

            line,

          allowBack:

            true,

          onAdvance:

            function () {

              var chk = mandatoryAddVehicleFields();

              if (!chk.ok)

                {

                reportTutorialFailure(FC.VAL, { stepId: sObj.id });

                return;

              }

              if (
                iv)
                window.clearInterval(iv);

              execAdvance();

            },

        });

      };

    tick();

    iv =
      window.setInterval(tick, 440);

    st.dispose.push(function () {

      if (
        iv)
        window.clearInterval(iv);

    });

  }

  function execApi(sObj) {
    paint(sObj, { plainAdvance: false, allowBack: false });

    var deadline = Date.now() + (+sObj.timeoutMs || 120000),
      finished = false;

    function detach() {

      document.removeEventListener('tutorial:vehicle-saved', onSaved);
      document.removeEventListener(
        'tutorial:vehicle-save-failed',
        onFailed,

      );
    }

    function onSaved() {

      if (
        finished)

        return;

      finished =
        true;

      detach();

      execAdvance();

    }

    function onFailed(ev) {

      if (finished) return;

      finished =
        true;

      detach();

      var txt =
          (ev && ev.detail && ev.detail.message ? String(ev.detail.message) : '').toLowerCase(),

        pick =
          txt.indexOf('403') !== -1 || txt.indexOf('oprávn') !== -1 ? FC.PERM : FC.API;

      reportTutorialFailure(pick, { stepId: sObj.id });

      teardown(false);

    }

    document.addEventListener('tutorial:vehicle-saved', onSaved);
    document.addEventListener('tutorial:vehicle-save-failed', onFailed);

    st.dispose.push(detach);

    addTimer(function () {
      if (finished || !st.running) return;
      finished = true;
      detach();
      reportTutorialFailure(FC.API, { stepId: sObj.id });
      teardown(false);
    }, Math.max(1000, deadline - Date.now()));

  }

  function execMain() {

    if (!st.running) return;

    ensureTutorialWatchdog();

    var pack =
      def(),

      total =
        pack && pack.steps ? pack.steps.length : 0;

    if (!pack || total === 0 || st.idx >= total) {
      apiPost('done', { tutorial_id: st.tid });
      teardown(true);
      return;
    }

    var sObj = pack.steps[st.idx];

    if (!tutorialRolesAllowPack(pack)) {
      reportTutorialFailure(FC.PERM, {
        stepId: sObj.id,
        reason: 'tutorial_shell_roles',
      });

      teardown(false);

      return;
    }

    var svcShell = isCurrentServiceShell();
    var ss = String(pack.startServiceSection || '').trim();
    var serviceSectionOnce = !!pack.serviceSectionOnce;

    if (svcShell && ss && window.serviceShell && typeof window.serviceShell.navigate === 'function') {
      var enforceSs = !(serviceSectionOnce && st.serviceSectionOnceDone);

      var curS = '';
      try {
        var srvRootNode = document.querySelector('[data-service-shell="root"]');
        curS = srvRootNode ? String(srvRootNode.getAttribute('data-service-active-section') || '').trim() : '';
      } catch (_) {}

      if (enforceSs && curS !== ss) {
        st.routeAttempts += 1;
        if (st.routeAttempts > 50) {
          reportTutorialFailure(FC.ROUTE, {

            stepId: sObj.id,

            actual: curS || '(empty)',

            expected: ss,

            reason: 'service_section',

          });

          paint(sObj,

            {});
          positionHole(null);
          return;
        }

        window.serviceShell.navigate(ss);
        addTimer(execMain, 100);
        return;
      }

      if (
        serviceSectionOnce &&
        !st.serviceSectionOnceDone &&
        curS === ss
      )
        st.serviceSectionOnceDone = true;

      st.routeAttempts = 0;

    }

    var rt =
      String(pack.startRouteTab || '').trim();
    var routeOnce = !!pack.routeTabOnce;

    if (!svcShell && rt && typeof window.switchTab === 'function') {

      var enforceRouteTab = !(routeOnce && st.routeTabOnceDone);

      if (
        enforceRouteTab &&
        tabKey() !== rt) {

        st.routeAttempts += 1;

        if (st.routeAttempts > 50) {
          reportTutorialFailure(FC.ROUTE, {

            stepId: sObj.id,

            actual: tabKey(),
            expected: rt,
          });

          paint(sObj,

            {});
          positionHole(null);

          return;
        }

        window.switchTab(rt,

          {
            skipUnsavedGuard:

              true,

          },

        );

        addTimer(execMain, 66);

        return;
      }

      if (routeOnce && !st.routeTabOnceDone && tabKey() === rt) {

        st.routeTabOnceDone = true;
      }

      st.routeAttempts = 0;

    }



    if (tutorialStepRequiresModalGuard(sObj) && !tutorialModalGuardOpen()) {
      reportTutorialFailure(FC.MODAL, { stepId: sObj.id });
      dbg().tutorialStopReason = 'state_desync';
      hardResetTutorialUI();
      return;
    }

    apiPost(
      'step',

      {

        tutorial_id:

          st.tid,

        step_id: sObj.id,

        failure_code: null,

      },

    );

    clrHighlight();

    paint(sObj,

      {});

    if (
      sObj.actionType ===
      'waitForModal')

      execModal(sObj);

    else if (
      sObj.actionType === 'click')

      execClick(sObj);

    else if (
      sObj.actionType === 'waitForValid')
      execWaitForValid(sObj);

    else if (
      sObj.actionType === 'input')

      {

      reportTutorialFailure(FC.CFG, {

        stepId: sObj.id,

        legacy: 'input_action_deprecated_use_waitForValid',

      });

      teardown(false);

      return;

      }
    else if (
      sObj.actionType === 'observeFormValidation')

      execValidate(sObj);

    else if (
      sObj.actionType === 'waitForApiSuccess')

      execApi(sObj);

    else if (
      sObj.actionType === 'next' || sObj.actionType === 'review')
      ;

    else

      {

      reportTutorialFailure(FC.CFG, { stepId: sObj.id });

      paint(sObj,

        {});

    }

  }

  function teardownLayerOnly() {

    if (st.watchdogId != null) {
      window.clearInterval(st.watchdogId);
      st.watchdogId = null;
    }

    clearTimers();

    clearDispose();

    cancelTutorialWaitRaf();

    if (tutorialLayoutRefreshRaf) {
      try {
        window.cancelAnimationFrame(tutorialLayoutRefreshRaf);
      } catch (_) {}
      tutorialLayoutRefreshRaf = 0;
    }

    tutorialVehicleModalScrollHookAttached = false;

    clrHighlight();

    document.querySelectorAll('[data-tutorial]').forEach(function (n) {
      delete n.dataset.tutorialArmedClick;
    });

    if (
      st.root && st.root.parentNode) {

      try {

        st.root.parentNode.removeChild(st.root);

      } catch (_) {}
    }

    st.root =
      st.bubble =
      st.bkT =
      st.bkL =
      st.bkR =
      st.bkB =
        null;

    st.running = false;

    st.idx =

      0;

    st.routeAttempts =
      0;

  }

  function teardown(okToast) {

    teardownLayerOnly();

    if (
      okToast)

      try {

        if (
          typeof window.showAlert === 'function')

          window.showAlert('Návod je dokončený.', 'success');

      } catch (_) {}
  }

  function skipTutorial(reason) {

    apiPost(
      'skip',

      {

        tutorial_id:

          st.tid,

      },

    );

    dbg().tutorialSkipReason = reason ||
      '';

    teardownLayerOnly();

    try {

      if (
        typeof window.showAlert === 'function')

        window.showAlert('Návod byl přeskočen.', 'info');

    } catch (_) {}
  }

  /** Ukončení bez zápisu skipped (uživatel/skript) — nevolá POST /skip */
  function stopTutorial(reason) {
    dbg().tutorialStopReason = typeof reason === 'string' ? reason : '';
    teardownLayerOnly();
    dbg().tutorialStopped = true;
  }

  /** startTutorial must run after SPA auth bootstrap */
  window.TutorialEngine = {

    FAILURE_CODES: FC,

    AUTO_NEXT_ON_INPUT: AUTO_NEXT_ON_INPUT,

    categorizeFailure:

      cat,

    rolesAllowTutorial: tutorialRolesAllowPack,

    boot: function () {

      window.addEventListener(
        'keydown',

        function (e) {

          if (
            !st.running ||

            e.key !==

              'Escape')
            return;

          try {

            e.preventDefault();

            e.stopPropagation();

          } catch (_) {}

          skipTutorial(
            'escape',

          );

        },

        true,

      );

      /** Prefetch rozpracovaného stavu návodu (bez závazných akcí) */
      try {
        if (
          authOk() && typeof window.apiCall === 'function')
          void window.apiCall('/api/v1/tutorials/progress', 'GET');

      } catch (_) {}

      var svcRow = document.getElementById(
        'mobileProfileTutorialRow',

      );

      if (
        svcRow && typeof window.isServiceWorkspaceRole === 'function')

        svcRow.hidden = !!window.isServiceWorkspaceRole();

      tutorialAttachOverlayReflowListeners();
      tutorialEnsureLifecycleHooks();

    },

    startTutorial: function (tutorialId) {

      tutorialId = String(
        tutorialId ||

          '',

      ).trim();

      var catalog = window.__TUTORIAL_REGISTRY || {};

      if (!catalog[tutorialId]) {

        reportTutorialFailure(FC.CFG, { stepId: null });

        return;

      }

      var starterPack = catalog[tutorialId];
      if (!tutorialRolesAllowPack(starterPack)) {
        reportTutorialFailure(FC.PERM, { stepId: null, reason: 'tutorial_start_roles' });
        try {
          if (typeof window.showAlert === 'function')
            window.showAlert('Tento návod není v aktuálním režimu účtu k dispozici.', 'info');
        } catch (_) {}
        return;
      }

      if (
        typeof window.closeHowToHubModal === 'function')

        try {

          window.closeHowToHubModal();

        } catch (_) {}

      teardownLayerOnly();

      st.running = true;

      st.tid = tutorialId;

      st.idx =

        0;

      st.routeAttempts =
        0;

      st.routeTabOnceDone =
        false;

      st.serviceSectionOnceDone =
        false;

      dbg().lastFailureCode = '';

      if (
        document.body) delete document.body.dataset.tutorialLastFailure;

      var firstStep =

        catalog[tutorialId].steps && catalog[tutorialId].steps[0]
          ? catalog[tutorialId].steps[0].id
          : null;

      apiPost(
        'start',

        {

          tutorial_id: tutorialId,

          step_id: firstStep,

        },

      );

      execMain();

    },

    stopTutorial:

      stopTutorial,

    skipTutorial:

      skipTutorial,

    finishTutorial:

      function () {

        teardown(true);

      },

    previousStep: function () {

      if (!st.running || st.idx <= 0) return;

      st.idx -= 1;

      execMain();

    },

    nextStep: execAdvance,

    lockNonTargetClicks: function () {},

    unlockClicks: function () {},

    waitForTarget: function () {},

    waitForVisible: function () {},

    waitForEnabled:

      function () {},

    highlightTarget: function (el) {

      positionHole(el ||

        null);

    },

    positionBubble: positionHole,

    observeRouteChange: function () {},

    observeModalOpen:

      function () {},

    observeFormValidation: function () {},

    observeApiSuccess: function () {},

    hardResetTutorialUI: hardResetTutorialUI,

    reportTutorialFailure: reportTutorialFailure,

    __e2e: {

      reportSelectorMissing:

        function () {

          reportTutorialFailure(FC.SEL, {

            stepId: '__e2e__',

          });

        },

      reportDisabled: function () {

        reportTutorialFailure(FC.DIS, { stepId: '__e2e__' });

      },

      reportRoute: function () {

        reportTutorialFailure(FC.ROUTE, {

          stepId:

            '__e2e__',

        });

      },

    },

  };

  /** hub panel */
  window.openHowToHubModal = function () {

    var modal =
      document.getElementById(
        'howToHubModal',

      );

    if (!(modal instanceof Element)) return;

    var svcShellHub = isCurrentServiceShell();
    var layout =
      svcShellHub &&
      window.__TUTORIAL_HUB_LAYOUT_SERVICE &&
      Array.isArray(window.__TUTORIAL_HUB_LAYOUT_SERVICE)
        ? window.__TUTORIAL_HUB_LAYOUT_SERVICE
        : window.__TUTORIAL_HUB_LAYOUT_USER ||
          window.__TUTORIAL_HUB_LAYOUT ||
          [];

    /** categories */
    var host =
      document.getElementById(
        'howToHubCategories',

      );

    var catalogLookup = window.__TUTORIAL_REGISTRY || {};

    if (
      host &&
      layout &&
      layout.length)

       {

      var html =
        '';

      layout.forEach(function (catObj) {

        html +=
          '<section class=\"how-to-cat\"><h4>' +
          escHtml(catObj.title) +
          '</h4><ul style=\"margin:8px 0 0;padding:0;list-style:none\">';

        (catObj.items ||
          []).forEach(function (lt) {

          var id =
              lt && lt.tutorialId ? String(lt.tutorialId) : '',

            dis =
              lt && lt.disabled,

            lbl =
              escHtml(String(lt && lt.label ||
                '').trim());

          var regPack = id ? catalogLookup[id] : null;
          var implicitDis = !!(regPack && !tutorialRolesAllowPack(regPack));
          var effDis = !!(dis || implicitDis);
          var hintBase = lt.hint ? String(lt.hint) : '';
          var hintExtra = '';
          if (implicitDis && id)
            hintExtra = 'Zpřístupníte jen v rozhraní, pro které je návod určen.';
          var hintMerged =
            hintBase && hintExtra
              ? hintBase + '\n\n' + hintExtra
              : hintBase || hintExtra;

          var suffix = '';
          if (effDis) {
            if (implicitDis && id) suffix = ' · jiný režim rozhraní';
            else if (dis) suffix = ' · připravujeme';
          }

          html +=
            '<li style=\"margin:6px 0\"><button type=\"button\" ' +
            (effDis ? 'disabled' : '') +
            ' style=\"width:100%;text-align:left;padding:10px 12px;border-radius:10px;border:1px solid rgba(148,163,184,.38);cursor:pointer;' +
            (effDis ? 'opacity:.55' : '') +
            '\" data-how-launch=\"' +
            escHtml(id) +
            '\">' +
            lbl +
            suffix +
            '</button>';

          if (hintMerged)

            html +=
              '<div style=\"font-size:.82rem;color:#94a3b8;margin:.25rem .25rem 0\">' +
              escHtml(hintMerged) +
              '</div>';

          html +=
            '</li>';

        });

        html +=
          '</ul></section>';

      });

      host.innerHTML =
        html;

      host.querySelectorAll(
        '[data-how-launch]',

      ).forEach(function (bt) {

        bt.addEventListener(
          'click',

          function () {

            var lid =
              bt.getAttribute(
                'data-how-launch',

              ) ||

              '';

            if (
              bt.disabled ||

              !lid)
              return;

            if (
              typeof window.closeHowToHubModal === 'function')

              window.closeHowToHubModal();

            window.TutorialEngine.startTutorial(lid);

          },

        );

      });

    }

    if (
      typeof window.openStaticOverlayModal === 'function')

       {

      window.openStaticOverlayModal(modal, {

        scrollTargetSelector:

          '#howToHubScroll',

      });

      modal.setAttribute('aria-hidden',

        'false');

    }

  };

  window.closeHowToHubModal = function () {

    var modal =
      document.getElementById(
        'howToHubModal',

      );

    if (!(modal instanceof Element))

      return;

    if (
      typeof window.closeStaticOverlayModal === 'function')

      window.closeStaticOverlayModal(
        modal,

      );

    modal.setAttribute('aria-hidden',

      'true');

  };

})();