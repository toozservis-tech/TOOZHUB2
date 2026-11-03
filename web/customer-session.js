// Shared by both administrator dashboards. Never store access credentials in localStorage,
// forward them to another origin, or accept a response from a previous session.
(function (global) {
    'use strict';
    const TOKEN_KEY = 'customerWebAccessToken';
    const SESSION_ORIGIN = location.origin;
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
    // Forms belong to the account generation; a transport uses one credential revision.
    let credentialRevision = 0, renewal = null, retryRenewalAt = 0, renewalTimer = null;
    let serverPrincipal = null, verificationContext = null, licenceContext = null;
    let acceptedToken = sessionStorage.getItem(TOKEN_KEY), acceptedRole = sessionStorage.getItem(ROLE_KEY);
    const RENEW_WINDOW = 7 * 86400, RENEW_AGE = 86400, RENEW_RETRY_MS = 30000;
    const allowedRoles = ['user', 'customer', 'service'];
    const publicPaths = ['/user/login', '/user/login/2fa', '/user/register', '/user/register/service-request', '/user/forgot-password'];

    function removeLegacyCredentials() {
        for (const key of [TOKEN_KEY, ROLE_KEY, ...legacyKeys]) localStorage.removeItem(key);
        for (const key of legacyKeys) sessionStorage.removeItem(key);
    }
    removeLegacyCredentials();

    function token() { return sessionStorage.getItem(TOKEN_KEY); }
    function snapshot() { return {generation}; }
    function transportSnapshot() { return {generation, credentialRevision, token: token()}; }
    function stale() { return new DOMException('Přihlášení se změnilo. Zopakujte akci po ověření.', 'AbortError'); }
    function assertCurrent(value) {
        if (location.origin !== SESSION_ORIGIN) { end('environment', false); throw stale(); }
        if (!value || value.generation !== generation || ended || suspended) throw stale();
        if (token() !== acceptedToken || sessionStorage.getItem(ROLE_KEY) !== acceptedRole) {
            end('account-changed'); throw stale();
        }
    }
    function assertTransport(value) {
        assertCurrent(value);
        if (value.credentialRevision !== credentialRevision || value.token !== token()) throw stale();
    }
    function cancelPending() {
        clearTimeout(expiryTimer); expiryTimer = null; deadline = 0;
        clearTimeout(renewalTimer); renewalTimer = null;
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
        ended = true; generation++; credentialRevision++; serverPrincipal = null; verificationContext = null; licenceContext = null;
        acceptedToken = null; acceptedRole = null; cancelPending();
        removeLegacyCredentials(); sessionStorage.removeItem(TOKEN_KEY); sessionStorage.removeItem(ROLE_KEY);
        if (broadcast && !wasEnded) notifyOtherTabs();
        global.dispatchEvent(new CustomEvent('admin-session-ended', {detail: {reason}}));
        if (!wasEnded) lockPage();
    }
    function set(nextToken, role) {
        if (!nextToken || !allowedRoles.includes(role)) throw new Error('Administrátoři používají samostatné přihlášení administrace.');
        // A duplicate login callback is not an account change or a cross-tab logout.
        if (!ended && !suspended && nextToken === acceptedToken && role === acceptedRole && nextToken === token() && role === sessionStorage.getItem(ROLE_KEY)) return;
        generation++; credentialRevision++; serverPrincipal = null; verificationContext = null; licenceContext = null; retryRenewalAt = 0;
        cancelPending(); removeLegacyCredentials(); ended = false; suspended = false;
        sessionStorage.setItem(TOKEN_KEY, nextToken); sessionStorage.setItem(ROLE_KEY, role);
        acceptedToken = nextToken; acceptedRole = role;
        notifyOtherTabs(); scheduleRenewal();
    }
    function sameOriginURL(value) {
        const url = new URL(value, location.origin);
        if (url.origin !== location.origin || !['http:', 'https:'].includes(url.protocol) || url.username || url.password) {
            throw new Error('Požadavek smí směřovat pouze na server této aplikace.');
        }
        return url.href;
    }
    function profileIdentity(profile) {
        if (!profile || !Number.isSafeInteger(profile.id) || profile.id <= 0 ||
            typeof profile.email !== 'string' || !profile.email ||
            !allowedRoles.includes(profile.role)) throw new Error('Server nevrátil platný zákaznický účet.');
        return JSON.stringify([profile.id, profile.email.toLowerCase(), profile.role]);
    }
    function observeProfile(profile) {
        if (!allowedRoles.includes(profile?.role)) { end('role'); throw stale(); }
        const identity = profileIdentity(profile);
        if (profile.role !== sessionStorage.getItem(ROLE_KEY) ||
            (serverPrincipal !== null && serverPrincipal !== identity)) {
            end('account-changed'); throw stale();
        }
        serverPrincipal = identity;
        return identity;
    }
    function verificationIdentity(value) {
        if (!value || typeof value.required !== 'boolean') throw new Error('Server nevrátil platné ověření účtu.');
        return value.required;
    }
    function licenceIdentity(value) {
        const data = value?.data || value;
        const flags = ['is_unlimited','vin_decode_enabled','ares_enabled','reminders_enabled','vehicle_history_enabled',
            'documents_enabled','costs_tracking_enabled','statistics_enabled','sharing_with_service_enabled','manual_service_records_enabled'];
        if (!data || typeof data.tenant_id !== 'string' || !data.tenant_id ||
            typeof data.plan !== 'string' || !data.plan || typeof data.status !== 'string' || !data.status ||
            !Number.isSafeInteger(data.vehicles_limit) || flags.some(key => typeof data[key] !== 'boolean') ||
            (data.manual_service_records_limit !== null && !Number.isSafeInteger(data.manual_service_records_limit))) {
            throw new Error('Server nevrátil platná oprávnění účtu.');
        }
        // Usage counters, contact fields, subscription dates and last-seen data are not account boundaries.
        return JSON.stringify([data.tenant_id, data.plan, data.status, data.vehicles_limit,
            data.manual_service_records_limit, ...flags.map(key => data[key])]);
    }
    function refreshPrivateContext() {
        // Keep the server-issued credential; normal bootstrap reapplies current verification and access gates.
        generation++; credentialRevision++; suspended = true;
        serverPrincipal = null; verificationContext = null; licenceContext = null; cancelPending();
        global.dispatchEvent(new CustomEvent('admin-session-ended', {detail: {reason:'access-changed'}}));
        try { cleanup(); } catch {}
        if (document.body) {
            const main = document.createElement('main'), message = document.createElement('p');
            message.textContent = 'Oprávnění účtu se změnila. Načítám aktuální přístup…';
            main.append(message); document.body.replaceChildren(main);
        }
        location.replace(loginTarget());
        throw stale();
    }
    function observeVerification(value) {
        const next = verificationIdentity(value);
        if (verificationContext !== null && verificationContext !== next) refreshPrivateContext();
        verificationContext = next;
        return next;
    }
    function observeLicence(value) {
        const next = licenceIdentity(value);
        if (licenceContext !== null && licenceContext !== next) refreshPrivateContext();
        licenceContext = next;
        return next;
    }
    async function request(input, init = {}, expected = snapshot()) {
        assertCurrent(expected);
        // Reject foreign origins before renewal can initiate any authenticated request.
        const url = sameOriginURL(input), path = new URL(url).pathname;
        // Only the bounded company lookup is a new public operation; legacy ARES stays protected.
        const publicCompanyLookup = path === '/user/registration-company' && String(init.method || 'GET').toUpperCase() === 'GET';
        const publicRequest = publicPaths.includes(path) || publicCompanyLookup;
        if (!token() && !publicRequest) throw new Error('Nejprve se přihlaste.');
        if (token() && renewalDue(token()) && Date.now() >= retryRenewalAt &&
            !publicRequest && !['/user/session/renew', '/user/logout'].includes(path)) {
            await renewIfNeeded();
        }
        assertCurrent(expected);
        // Never reuse a bearer captured by a long-lived form.
        return transportRequest(url, init, transportSnapshot());
    }
    async function transportRequest(input, init = {}, expected = transportSnapshot(), bearer = expected.token, inspectProfile = true) {
        assertTransport(expected);
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
        headers.delete('X-User-Email'); if (bearer) headers.set('Authorization', 'Bearer ' + bearer); else headers.delete('Authorization');
        try {
            const response = await fetch(url, {...options, headers, signal:controller.signal, credentials:'same-origin', cache:'no-store', redirect:'error'});
            assertCurrent(expected); controller.signal.throwIfAborted();
            if ((bearer && response.status === 401) || response.headers.get('X-Admin-Verification') === 'required') {
                // A late401 for a replaced bearer must not end the renewed session.
                if (expected.credentialRevision !== credentialRevision || expected.token !== token()) { release(); throw stale(); }
                release(); end('expired'); throw stale();
            }
            function guardBody(body) {
                return new Proxy(body, {get(target, key) {
                    if (key === 'clone') return () => { assertCurrent(expected); return guardBody(target.clone()); };
                    if (['json','text','blob','arrayBuffer','formData','bytes'].includes(key)) return async () => {
                        assertCurrent(expected);
                        try {
                            const result = await target[key](); assertCurrent(expected); controller.signal.throwIfAborted();
                            if (key === 'json' && target.ok && inspectProfile && (options.method || 'GET').toUpperCase() === 'GET') {
                                const path = new URL(url).pathname;
                                if (path === '/user/me') observeProfile(result);
                                if (path === '/user/email-verification') observeVerification(result);
                                if (path === '/api/v1/license/status') observeLicence(result);
                            }
                            return result;
                        } finally { release(); }
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
    function renewalDue(value) {
        // Unsigned claims only schedule an attempt; all authority comes from the server.
        const claims = jwtClaims(value || ''), now = Date.now() / 1000;
        return claims && Number.isFinite(claims.exp) && Number.isFinite(claims.iat) &&
            (claims.exp - now < RENEW_WINDOW || now - claims.iat > RENEW_AGE);
    }
    function sessionIdentity(value) {
        const claims = jwtClaims(value || '');
        if (!claims || typeof claims.sub !== 'string' || !claims.sub ||
            typeof claims.jti !== 'string' || !claims.jti ||
            !['number', 'string'].includes(typeof claims.sv)) throw new Error('Obnovu přihlášení nelze bezpečně ověřit.');
        return JSON.stringify([claims.sub, claims.jti, claims.sv, claims.amr ?? null, claims.mfa_at ?? null]);
    }
    function scheduleRenewal() {
        clearTimeout(renewalTimer); renewalTimer = null;
        if (!token() || ended || suspended) return;
        renewalTimer = setTimeout(() => {
            renewalTimer = null;
            if (!document.hidden) void renewIfNeeded().catch(() => {}).finally(scheduleRenewal);
            else scheduleRenewal();
        }, 3600000);
        // Only relevant to host-side contract tests; browsers return a number.
        renewalTimer?.unref?.();
    }
    async function securitySnapshot(expected, bearer, inspect) {
        async function read(path) {
            const response = await transportRequest(path, {}, expected, bearer, inspect);
            if (!response.ok) { await response.text(); throw new Error('Oprávnění účtu se nepodařilo ověřit.'); }
            return response.json();
        }
        const profile = await read('/user/me');
        if (!allowedRoles.includes(profile?.role)) { end('role'); throw stale(); }
        const principal = profileIdentity(profile);
        const required = verificationIdentity(await read('/user/email-verification'));
        // Pending e-mail verification intentionally denies the licence endpoint on the server.
        const licence = required ? null : licenceIdentity(await read('/api/v1/license/status'));
        return {profile, principal, required, licence};
    }
    async function renewIfNeeded() {
        if (ended || suspended || !token()) return false;
        if (renewal && renewal.generation === generation && renewal.token === token()) return renewal.promise;
        // Background polls must not keep an otherwise inactive account alive.
        if (document.hidden || !renewalDue(token()) || Date.now() < retryRenewalAt) return false;
        const expected = transportSnapshot();
        const operation = {generation: expected.generation, token: expected.token, promise: null};
        operation.promise = (async () => {
            try {
                // All authority comes from real server checks, never from decoded JWT roles.
                const before = await securitySnapshot(expected, expected.token, true);
                const response = await transportRequest('/user/session/renew', {method:'POST'}, expected);
                if (!response.ok) { await response.text(); throw new Error('Obnovení přihlášení není dostupné.'); }
                const result = await response.json(), nextToken = result?.access_token;
                if (typeof nextToken !== 'string' || !nextToken || nextToken === expected.token || renewalDue(nextToken)) throw new Error('Server nevrátil obnovené přihlášení.');
                const after = await securitySnapshot(expected, nextToken, false);
                assertTransport(expected);
                if (after.principal !== before.principal || after.profile.role !== sessionStorage.getItem(ROLE_KEY) ||
                    sessionIdentity(nextToken) !== sessionIdentity(expected.token)) {
                    end('account-changed'); throw stale();
                }
                sessionStorage.setItem(TOKEN_KEY, nextToken); acceptedToken = nextToken;
                credentialRevision++; retryRenewalAt = 0;
                verificationContext = after.required; licenceContext = after.licence;
                if (before.required !== after.required || before.licence !== after.licence) refreshPrivateContext();
                // Same-account in-flight responses, including committed writes, remain usable.
                // Real logout/account/security changes still cancel every pending operation.
                return true;
            } catch (error) {
                assertCurrent(expected);
                // A service/network failure retains the current valid account and draft.
                retryRenewalAt = Date.now() + RENEW_RETRY_MS;
                return false;
            } finally {
                if (renewal === operation) renewal = null;
                scheduleRenewal();
            }
        })();
        renewal = operation;
        return operation.promise;
    }
    async function verify() {
        const response = await request('/user/me');
        if (!response.ok) throw new Error('Přihlášení se nepodařilo ověřit.');
        const profile = await response.json();
        observeProfile(profile);
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
        else if (!document.hidden) void renewIfNeeded().catch(() => {});
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
        else if (!document.hidden) void renewIfNeeded().catch(() => {});
    });
    global.CustomerWeb = true;
    global.AdminBrowserSession = Object.freeze({token, snapshot, assertCurrent, set, end, request, verify, logout, protect, sameOriginURL, retryLogouts, logoutNotice, hasPendingLogouts});
    void retryLogouts();
    scheduleRenewal();
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
