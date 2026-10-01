let challenge = null, pendingToken = null, mode = 'login', attempt = 0;
const pendingRequests = new Set();
const el = id => document.getElementById(id), form = el('form'), button = el('submit');
// Unverified sessions and authenticator seeds remain only in this page's memory.
AdminBrowserSession.end('login', false);
function assertAttempt(expected) {
    if (expected !== attempt) throw new DOMException('Přihlášení bylo přerušeno.', 'AbortError');
}
async function api(url, body, token, expected) {
    assertAttempt(expected);
    const controller = new AbortController(); pendingRequests.add(controller);
    const timer = setTimeout(() => controller.abort(), 30000);
    try {
        const r = await fetch(AdminBrowserSession.sameOriginURL(url), {
            method: body === null ? 'GET' : 'POST', cache: 'no-store', redirect: 'error',
            credentials: 'same-origin', signal: controller.signal,
            headers: {'Content-Type': 'application/json', ...(token ? {'Authorization': 'Bearer ' + token} : {})},
            ...(body === null ? {} : {body: JSON.stringify(body)})
        });
        assertAttempt(expected);
        const data = await r.json(); assertAttempt(expected);
        if (!r.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Ověření se nezdařilo.');
        return data;
    } finally { clearTimeout(timer); pendingRequests.delete(controller); }
}
function showMode(next) {
    mode = next; const otp = next === 'otp' || next === 'setupCode';
    el('passwordLabel').hidden = otp; el('password').required = !otp; el('password').value = '';
    el('email').readOnly = next !== 'login'; el('codeLabel').hidden = !otp; el('code').required = otp; el('code').value = '';
    el('setup').hidden = next !== 'setupCode'; el('restart').hidden = next === 'login';
    button.textContent = next === 'setupPassword' ? 'Připravit autentikátor' : next === 'setupCode' ? 'Potvrdit nastavení a otevřít správu' : otp ? 'Ověřit a otevřít správu' : 'Přihlásit administrátora';
    (otp ? el('code') : el('password')).focus();
}
function restart() {
    attempt++;
    for (const request of pendingRequests) request.abort();
    pendingRequests.clear(); pendingToken = null; challenge = null;
    el('secret').textContent = ''; el('error').textContent = ''; button.disabled = false;
    showMode('login');
}
async function accept(token, expected) {
    const profile = await api('/user/me', null, token, expected);
    if (!['admin', 'developer_admin'].includes(profile.role)) throw new Error('Webová správa je určena pouze administrátorům.');
    const status = await api('/user/security/admin-status', null, token, expected);
    if (status.required !== true) throw new Error('Ověření administrátora se nepodařilo potvrdit.');
    if (!status.verified) {
        if (status.enrolled) throw new Error('Ověření vypršelo. Začněte přihlášení znovu.');
        pendingToken = token;
        showMode('setupPassword'); el('error').textContent = 'Před prvním vstupem nastavte autentikátor. Znovu potvrďte své heslo.'; return;
    }
    if (!Number.isFinite(status.valid_until) || status.valid_until * 1000 <= Date.now()) throw new Error('Ověření vypršelo. Začněte přihlášení znovu.');
    await api('/admin-web-session', {}, token, expected);
    assertAttempt(expected);
    AdminBrowserSession.set(token, profile.role);
    pendingToken = null; challenge = null; el('secret').textContent = ''; form.reset();
    const next = new URLSearchParams(location.search).get('next');
    location.replace(next === '/web/index.html' ? next : '/web_admin/');
}
el('restart').addEventListener('click', restart);
window.addEventListener('admin-session-ended', restart);
window.addEventListener('pagehide', restart);
form.addEventListener('submit', async event => {
    event.preventDefault(); if (button.disabled) return;
    const expected = ++attempt;
    button.disabled = true; el('error').textContent = '';
    try {
        if (mode === 'setupPassword') {
            const data = await api('/user/security/totp/setup', {current_password: el('password').value}, pendingToken, expected);
            el('secret').textContent = data.secret; showMode('setupCode'); return;
        }
        if (mode === 'setupCode') {
            const data = await api('/user/security/totp/enable', {code: el('code').value}, pendingToken, expected);
            el('secret').textContent = ''; await accept(data.access_token, expected); return;
        }
        const data = mode === 'otp'
            ? await api('/user/login/2fa', {challenge_token: challenge, code: el('code').value}, null, expected)
            : await api('/user/login', {email: el('email').value.trim(), password: el('password').value}, null, expected);
        el('password').value = '';
        if (data.two_factor_required) { challenge = data.challenge_token; showMode('otp'); return; }
        await accept(data.access_token, expected);
    } catch (error) {
        if (expected === attempt) el('error').textContent = error.name === 'AbortError' ? 'Připojení se přerušilo. Zkuste přihlášení znovu.' : error.message;
    } finally {
        if (expected === attempt) { button.disabled = false; el('password').value = ''; el('code').value = ''; }
    }
});

function renderLogoutNotice() {
    const message = AdminBrowserSession.logoutNotice();
    el('logoutNotice').hidden = !message;
    el('logoutMessage').textContent = message || '';
}
window.addEventListener('admin-logout-updated', renderLogoutNotice);
el('retryLogout').addEventListener('click', async () => {
    el('retryLogout').disabled = true;
    try { await AdminBrowserSession.retryLogouts(); }
    finally { el('retryLogout').disabled = false; renderLogoutNotice(); }
});
renderLogoutNotice();
