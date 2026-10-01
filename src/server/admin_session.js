// Shared by both administrator dashboards. Never store credentials in localStorage,
// forward them to another origin, or accept a response from a previous session.
(function (global) {
    'use strict';
    const TOKEN_KEY = 'adminAccessToken';
    const ROLE_KEY = 'adminRole';
    const SIGNOUT_KEY = 'sprava_vozidel_admin_session_changed';
    const LOGOUT_PREFIX = 'sprava_vozidel_logout_receipt:';
    const LOGOUT_WARNING = 'adminLogoutWarning';
    const volatileReceipts = new Map();
    let flushingLogouts = false;
    const legacyKeys = ['accessToken', 'token', 'currentUser', 'wasLoggedIn', 'clientGeoTelemetry', 'rememberedLoginEmail', 'pendingServiceInviteToken', 'pendingReservationClaimToken', 'pendingReservationClaimReservationId'];
    const pending = new Set();
    let generation = 0, deadline = 0, expiryTimer = null, ended = false, suspended = false;
    let protectedPage = false, cleanup = () => {};

    function removeLegacyCredentials() {
        for (const key of [TOKEN_KEY, ROLE_KEY, ...legacyKeys]) localStorage.removeItem(key);
        for (const key of legacyKeys) sessionStorage.removeItem(key);
    }
    removeLegacyCredentials();

    function token() { return sessionStorage.getItem(TOKEN_KEY); }
    function snapshot() { return {generation, token: token()}; }
    function stale() { return new DOMException('Přihlášení se změnilo. Zopakujte akci po ověření.', 'AbortError'); }
    function assertCurrent(value) {
        if (value.generation !== generation || value.token !== token() || ended || suspended) throw stale();
    }
    function cancelPending() {
        clearTimeout(expiryTimer); expiryTimer = null; deadline = 0;
        for (const controller of pending) controller.abort();
        pending.clear();
    }
    function notifyOtherTabs() {
        // Only an opaque signal, never a credential, account or personal information.
        localStorage.setItem(SIGNOUT_KEY, crypto.randomUUID());
    }
    function loginTarget() {
        const next = ['/web', '/web/', '/web/index.html'].includes(location.pathname) ? '/web/index.html' : '/web_admin/';
        return '/admin-login?next=' + encodeURIComponent(next);
    }
    function lockPage() {
        if (!protectedPage) return;
        try { cleanup(); } catch { /* navigation also destroys the old document */ }
        if (document.body) {
            const main = document.createElement('main');
            main.style.cssText = 'padding:32px;font:18px system-ui;color:#102d31;background:#e1f5ef;min-height:100vh';
            const message = document.createElement('p');
            message.textContent = 'Pro pokračování znovu ověřte přihlášení administrátora.';
            const link = document.createElement('a'); link.href = loginTarget(); link.textContent = 'Ověřit přihlášení';
            main.append(message, link); document.body.replaceChildren(main); document.body.style.visibility = 'visible';
        }
        location.replace(loginTarget());
    }
    function end(reason = 'expired', broadcast = true) {
        const wasEnded = ended;
        ended = true; generation++; cancelPending();
        removeLegacyCredentials(); sessionStorage.removeItem(TOKEN_KEY); sessionStorage.removeItem(ROLE_KEY);
        if (broadcast && !wasEnded) notifyOtherTabs();
        global.dispatchEvent(new CustomEvent('admin-session-ended', {detail: {reason}}));
        if (!wasEnded) lockPage();
    }
    function set(nextToken, role) {
        if (!nextToken || !['admin', 'developer_admin'].includes(role)) throw new Error('Webová správa je určena administrátorům.');
        generation++; cancelPending(); removeLegacyCredentials(); ended = false; suspended = false;
        sessionStorage.setItem(TOKEN_KEY, nextToken); sessionStorage.setItem(ROLE_KEY, role);
        notifyOtherTabs();
    }
    function sameOriginURL(value) {
        const url = new URL(value, location.origin);
        if (url.origin !== location.origin || !['http:', 'https:'].includes(url.protocol) || url.username || url.password) {
            throw new Error('Požadavek smí směřovat pouze na server této aplikace.');
        }
        return url.href;
    }
    async function request(input, init = {}, expected = snapshot()) {
        assertCurrent(expected);
        if (!expected.token) { end('missing'); throw stale(); }
        const url = sameOriginURL(input);
        const {timeoutMs = 30000, signal: externalSignal, ...options} = init;
        const controller = new AbortController(); pending.add(controller);
        const abort = () => controller.abort();
        if (externalSignal?.aborted) abort();
        else externalSignal?.addEventListener('abort', abort, {once:true});
        const timeout = setTimeout(abort, timeoutMs);
        let released = false;
        function release() {
            if (released) return;
            released = true; clearTimeout(timeout); pending.delete(controller);
            externalSignal?.removeEventListener('abort', abort);
        }
        controller.signal.addEventListener('abort', release, {once:true});
        if (controller.signal.aborted) release();
        const headers = new Headers(options.headers);
        headers.delete('X-User-Email'); headers.set('Authorization', 'Bearer ' + expected.token);
        try {
            const response = await fetch(url, {...options, headers, signal:controller.signal, credentials:'same-origin', cache:'no-store', redirect:'error'});
            assertCurrent(expected); controller.signal.throwIfAborted();
            if (response.status === 401 || response.headers.get('X-Admin-Verification') === 'required') {
                release(); end('expired'); throw stale();
            }
            function guardBody(body) {
                return new Proxy(body, {get(target, key) {
                    if (key === 'clone') return () => { assertCurrent(expected); return guardBody(target.clone()); };
                    if (['json','text','blob','arrayBuffer','formData','bytes'].includes(key)) return async () => {
                        assertCurrent(expected);
                        try { const result = await target[key](); assertCurrent(expected); controller.signal.throwIfAborted(); return result; }
                        finally { release(); }
                    };
                    if (key === 'body') throw new Error('Použijte ověřené načtení obsahu odpovědi.');
                    const value = Reflect.get(target, key, target);
                    return typeof value === 'function' ? value.bind(target) : value;
                }});
            }
            if (response.status === 204 || response.headers.get('content-length') === '0') release();
            return guardBody(response);
        } catch (error) { release(); throw error; }
    }
    async function verify() {
        const expected = snapshot();
        const response = await request('/user/security/admin-status', {}, expected);
        if (!response.ok) throw new Error('Ověření administrátora se nepodařilo načíst.');
        const status = await response.json(); assertCurrent(expected);
        if (status.required !== true || status.verified !== true || !Number.isFinite(status.valid_until) || status.valid_until * 1000 <= Date.now()) {
            end('verification'); throw stale();
        }
        deadline = status.valid_until * 1000;
        clearTimeout(expiryTimer);
        expiryTimer = setTimeout(() => end('expired'), Math.min(900000, Math.max(0, deadline - Date.now())));
        return status;
    }
    function jwtClaims(value) {
        try {
            const parts = value.split('.'); if (parts.length !== 3) return null;
            return JSON.parse(atob(parts[1].replace(/-/g, '+').replace(/_/g, '/')));
        } catch { return null; }
    }
    function queueLogout(accessToken) {
        const ticket = jwtClaims(accessToken || '')?.logout_ticket;
        if (typeof ticket !== 'string' || ticket.length > 2048) return null;
        const claims = jwtClaims(ticket);
        if (claims?.aud !== 'session-logout' || !/^[0-9a-f]{64}$/.test(claims?.sid || '')) return null;
        const key = LOGOUT_PREFIX + claims.sid;
        // This separate signed capability can ONLY revoke its session. It has
        // no account data and cannot authenticate. Never persist the bearer.
        volatileReceipts.set(key, ticket);
        try { localStorage.setItem(key, ticket); } catch { /* retry in memory */ }
        return key;
    }
    function receipts() {
        const result = new Map(volatileReceipts);
        for (const key of Object.keys(localStorage)) {
            if (key.startsWith(LOGOUT_PREFIX)) result.set(key, localStorage.getItem(key));
        }
        return result;
    }
    function logoutNotice() {
        return receipts().size ? 'V tomto prohlížeči jste odhlášeni. Potvrzení odhlášení serverem čeká na spojení.' : sessionStorage.getItem(LOGOUT_WARNING);
    }
    function notifyLogout() { global.dispatchEvent(new Event('admin-logout-updated')); }
    async function retryLogouts() {
        if (flushingLogouts) return;
        flushingLogouts = true;
        try {
            for (const [key, ticket] of receipts()) {
                const controller = new AbortController();
                const timer = setTimeout(() => controller.abort(), 8000);
                try {
                    const response = await fetch('/user/logout', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({logout_ticket:ticket}),
                        credentials:'omit', cache:'no-store', redirect:'error', signal:controller.signal});
                    if (response.status !== 204) throw new Error('Logout unconfirmed');
                    localStorage.removeItem(key); volatileReceipts.delete(key);
                    if (!receipts().size) sessionStorage.removeItem(LOGOUT_WARNING);
                } catch { break; } finally { clearTimeout(timer); }
            }
        } finally { flushingLogouts = false; notifyLogout(); }
    }
    async function logout() {
        const oldToken = token(), receipt = queueLogout(oldToken);
        sessionStorage.setItem(LOGOUT_WARNING, 'V prohlížeči jste odhlášeni. Server zatím odhlášení nepotvrdil.');
        // Use the captured bearer, never a possibly newer shared browser cookie.
        const headers = oldToken ? {Authorization:'Bearer ' + oldToken} : {};
        const closing = fetch('/admin-web-session', {method:'DELETE', headers, credentials:oldToken ? 'omit' : 'same-origin',
            cache:'no-store', redirect:'error', keepalive:true}).then(response => {
                if (!response.ok) throw new Error('Logout unconfirmed');
                if (receipt) { localStorage.removeItem(receipt); volatileReceipts.delete(receipt); }
                sessionStorage.removeItem(LOGOUT_WARNING); notifyLogout();
            }).catch(() => { notifyLogout(); });
        end('logout');
        await closing;
    }
    function protect(onCleanup) {
        protectedPage = true;
        if (typeof onCleanup === 'function') cleanup = onCleanup;
        if (ended) lockPage();
        else if (!token()) end('missing', false);
    }
    global.addEventListener('storage', event => {
        if (event.key === SIGNOUT_KEY && event.newValue) end('other-tab', false);
        if (event.key?.startsWith(LOGOUT_PREFIX)) notifyLogout();
    });
    global.addEventListener('online', () => { void retryLogouts(); });
    global.addEventListener('pageshow', event => {
        if (protectedPage && event.persisted) { end('restore', false); }
    });
    global.addEventListener('pagehide', () => {
        if (protectedPage) {
            generation++; suspended = true; cancelPending();
            if (document.body) document.body.style.visibility = 'hidden';
            try { cleanup(); } catch {}
        }
    });
    document.addEventListener('visibilitychange', () => {
        if (protectedPage && !document.hidden && deadline && Date.now() >= deadline) end('expired');
    });
    global.AdminBrowserSession = Object.freeze({token, snapshot, assertCurrent, set, end, request, verify, logout, protect, sameOriginURL, retryLogouts, logoutNotice});
    void retryLogouts();
})(window);
