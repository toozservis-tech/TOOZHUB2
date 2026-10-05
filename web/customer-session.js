// Shared by both administrator dashboards. Never store access credentials in localStorage,
// forward them to another origin, or accept a response from a previous session.
(function (global) {
    'use strict';
    const TOKEN_KEY = 'customerWebAccessToken';
    const ROLE_KEY = 'customerWebRole';
    const SIGNOUT_KEY = 'evidence_customer_session_changed';
    const LOGOUT_PREFIX = 'sprava_vozidel_logout_receipt:';
    const LOGOUT_WARNING = 'customerLogoutWarning';
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
        return '/web/customer.html';
    }
    function lockPage() {
        if (!protectedPage) return;
        try { cleanup(); } catch { /* navigation also destroys the old document */ }
        if (document.body) {
            const main = document.createElement('main');
            main.style.cssText = 'padding:32px;font:18px system-ui;color:#102d31;background:#e1f5ef;min-height:100vh';
            const message = document.createElement('p');
            message.textContent = 'Relace skončila. Přihlaste se znovu.';
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
        if (!nextToken || !['user', 'customer', 'service'].includes(role)) throw new Error('Administrátoři používají samostatné přihlášení administrace.');
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
        if (!expected.token) {
            const path = new URL(input, location.origin).pathname;
            const publicPaths = ['/user/login', '/user/login/2fa', '/user/register', '/user/register/service-request', '/user/forgot-password'];
            if (!publicPaths.includes(path)) throw new Error('Nejprve se přihlaste.');
        }
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
        headers.delete('X-User-Email'); if (expected.token) headers.set('Authorization', 'Bearer ' + expected.token); else headers.delete('Authorization');
        try {
            const response = await fetch(url, {...options, headers, signal:controller.signal, credentials:'same-origin', cache:'no-store', redirect:'error'});
            assertCurrent(expected); controller.signal.throwIfAborted();
            if ((expected.token && response.status === 401) || response.headers.get('X-Admin-Verification') === 'required') {
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
        const response = await request('/user/me');
        if (!response.ok) throw new Error('Přihlášení se nepodařilo ověřit.');
        const profile = await response.json();
        if (!['user', 'customer', 'service'].includes(profile.role)) {
            end('role'); throw new Error('Použijte přihlášení administrace.');
        }
        return profile;
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
    function hasPendingLogouts() { return receipts().size > 0; }
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
        sessionStorage.setItem(LOGOUT_WARNING, receipt ? 'Server zatím odhlášení nepotvrdil.' : 'V prohlížeči jste odhlášeni. Server odhlášení staršího přístupu nepotvrdil; zůstává platný do vypršení. Změna hesla ukončí všechna přihlášení.');
        // Use the captured bearer, never a possibly newer shared browser cookie.
        const headers = oldToken ? {Authorization:'Bearer ' + oldToken} : {};
        const closing = fetch('/admin-web-session', {method:'DELETE', headers, credentials:oldToken ? 'omit' : 'same-origin',
            cache:'no-store', redirect:'error', keepalive:true}).then(async response => {
                if (!response.ok || (await response.json()).ok !== true) throw new Error('Logout unconfirmed');
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
        // An anonymous customer can use the login and registration forms.
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
    global.CustomerWeb = true;
    global.AdminBrowserSession = Object.freeze({token, snapshot, assertCurrent, set, end, request, verify, logout, protect, sameOriginURL, retryLogouts, logoutNotice, hasPendingLogouts});
    void retryLogouts();
})(window);

// Verification screen avoids showing failed private-data loads to new accounts.
window.showCustomerEmailVerification = async function () {
    const response = await AdminBrowserSession.request('/user/email-verification');
    if (!response.ok) throw new Error('Nepodařilo se ověřit stav účtu.');
    const status = await response.json();
    if (!status.required) return false;
    const main = document.createElement('main');
    main.className = 'customer-verification';
    const title = document.createElement('h1'); title.textContent = 'Potvrďte e-mail';
    const message = document.createElement('p'); message.textContent = 'Otevřete ověřovací odkaz ve svém e-mailu. Potom zde zkontrolujte ověření.';
    const result = document.createElement('p'); result.setAttribute('role','status');
    const check = document.createElement('button'); check.className='btn'; check.textContent='Zkontrolovat ověření'; check.onclick=()=>location.reload();
    const resend = document.createElement('button'); resend.className='btn btn-secondary'; resend.textContent='Poslat ověřovací e-mail znovu';
    resend.onclick = async () => {
        resend.disabled=true;
        try { const r=await AdminBrowserSession.request('/user/email-verification/resend',{method:'POST'}); const data=await r.json(); result.textContent=r.ok ? 'Žádost byla zpracována. Zkontrolujte e-mail včetně spamu.' : (typeof data.detail==='string'?data.detail:'E-mail se nepodařilo odeslat.'); }
        catch { result.textContent='Nepodařilo se spojit se serverem. Zkuste to znovu.'; }
        finally { resend.disabled=false; }
    };
    const logout = document.createElement('button'); logout.className='btn btn-secondary'; logout.textContent='Odhlásit se'; logout.onclick=()=>AdminBrowserSession.logout();
    main.append(title,message,check,resend,logout,result); document.body.replaceChildren(main);
    return true;
};
