/* Registration attribution only. A referral never authenticates or shares a vehicle. */
(function (global) {
    'use strict';
    const STORAGE_KEY = 'sprava_vozidel_referral_registration_v1';
    const CODE_PATTERN = /^[A-Za-z0-9_-]{16,40}$/;
    const CODE_ERROR = 'Kód pozvánky musí mít 16 až 40 písmen bez diakritiky, číslic, pomlček nebo podtržítek. Opravte jej nebo pokračujte bez kódu.';

    function codeValue(value) {
        const code = typeof value === 'string' ? value.trim() : '';
        if (code && !CODE_PATTERN.test(code)) throw new Error(CODE_ERROR);
        return code;
    }

    function fragmentParts(hash) {
        return String(hash || '').replace(/^#/, '').split('&');
    }

    function partName(part) {
        try { return decodeURIComponent(part.split('=')[0].replace(/\+/g, ' ')); }
        catch { return ''; }
    }

    function stripAttribution(hash) {
        const parts = fragmentParts(hash);
        if (!parts.some(part => partName(part) === 'referral')) return hash || '';
        const remaining = parts.filter(part => !['referral', 'kind'].includes(partName(part)));
        return remaining.length ? '#' + remaining.join('&') : '';
    }

    function safePageURL(value) {
        try {
            const url = new URL(value);
            const hasQueryReferral = url.searchParams.has('referral');
            if (hasQueryReferral) { url.searchParams.delete('referral'); url.searchParams.delete('kind'); }
            url.hash = stripAttribution(url.hash);
            return url.href;
        } catch { return ''; }
    }

    function userContact(values) {
        const fields = {};
        const labels = {name:'jméno a příjmení', street:'ulici', street_number:'číslo domu', city:'město', zip:'PSČ', phone:'telefon'};
        const limits = {name:[3,200], street:[1,200], street_number:[1,64], city:[1,120], zip:[3,16], phone:[7,32]};
        for (const [field, [min, max]] of Object.entries(limits)) {
            const value = typeof values[field] === 'string' ? values[field].trim().replace(/\s+/g, ' ') : '';
            if (value.length < min || value.length > max) throw new Error('Vyplňte platně ' + labels[field] + '.');
            fields[field] = value;
        }
        if (fields.name.split(' ').length < 2 || !fields.name.split(' ').every(part => /\p{L}/u.test(part))) {
            throw new Error('Vyplňte jméno i příjmení.');
        }
        fields.phone = fields.phone.replace(/[\s()\-]/g, '');
        if (!/^\+?[0-9]{7,15}$/.test(fields.phone)) throw new Error('Zadejte platný telefon, například +420 777 123 456.');
        return fields;
    }

    function errorMessage(error) {
        const labels = {name:'Jméno a příjmení', street:'Ulice', street_number:'Číslo domu', city:'Město', zip:'PSČ', phone:'Telefon',
            email:'E-mail', password:'Heslo', ico:'IČO', service_name:'Název servisu', responsible_person:'Zodpovědná osoba', registration_purpose:'Účel registrace'};
        if (Array.isArray(error?.detail)) {
            const messages = error.detail.map(item => {
                const field = Array.isArray(item.loc) ? item.loc[item.loc.length - 1] : '';
                return field === 'referral_code' ? CODE_ERROR : (labels[field] ? labels[field] + ': zkontrolujte vyplněný údaj.' : 'Zkontrolujte povinné údaje formuláře.');
            });
            return [...new Set(messages)].join(' ');
        }
        if (error?.status === 503) return 'Registrace s pozvánkou nyní není dostupná. Zkuste to později; kód zůstává vyplněný.';
        return typeof error?.message === 'string' ? error.message : 'Registraci se nepodařilo dokončit. Zkuste to znovu.';
    }

    function createRegistration(env) {
        let memory = null, linkError = '';
        // Only a public invitation draft persists here. Session credentials stay in the session module.
        // Validity/expiration belongs to the server, including after a cold browser restart.
        function store() { try { return env.localStorage; } catch { return null; } }
        function removeStored() { try { store()?.removeItem(STORAGE_KEY); } catch { /* memory fallback */ } }
        function save(value) {
            memory = value;
            try { if (value) store()?.setItem(STORAGE_KEY, JSON.stringify(value)); else removeStored(); }
            catch { /* Private browsing or a full store must not block registration. */ }
        }
        function pending() {
            if (!memory) {
                try { memory = JSON.parse(store()?.getItem(STORAGE_KEY) || 'null'); } catch { memory = null; }
            }
            if (!memory) return null;
            if (typeof memory.code !== 'string' || !CODE_PATTERN.test(memory.code) || !['user','service'].includes(memory.kind) ||
                !['link','manual'].includes(memory.source)) {
                save(null); return null;
            }
            return {...memory};
        }
        function clear() { linkError = ''; save(null); }
        function capture() {
            // This script runs before either browser session script can redirect.
            if (env.location?.pathname !== '/web/customer.html') return null;
            const params = new URLSearchParams(String(env.location.hash || '').replace(/^#/, ''));
            if (!params.has('referral')) return pending();
            const hash = stripAttribution(env.location.hash);
            try { env.history.replaceState(env.history.state, '', env.location.pathname + (env.location.search || '') + hash); }
            catch { /* safePageURL also redacts support/debug output if history is unavailable. */ }
            clear();
            const rawCode = params.get('referral') || '', kind = params.get('kind') || 'user';
            if (params.getAll('referral').length !== 1 || params.getAll('kind').length > 1 ||
                !CODE_PATTERN.test(rawCode) || !['user','service'].includes(kind)) {
                linkError = 'Pozvánka v odkazu nemá platný kód nebo typ účtu. Můžete zadat jiný kód nebo pokračovat bez něj.';
                return null;
            }
            save({code:rawCode, kind, source:'link', blocked:false});
            return pending();
        }
        function begin(authenticated) {
            const draft = pending();
            if (authenticated) {
                if (draft) save({...draft, blocked:true});
                return {open:false};
            }
            return {open:!!(draft && !draft.blocked) || !!linkError, kind:draft && !draft.blocked ? draft.kind : 'user', error:linkError};
        }
        function registrationDraft() {
            const draft = pending();
            return draft && !draft.blocked ? draft : null;
        }
        function update(value, kind) {
            const previous = pending();
            const code = codeValue(value);
            if (!code) { clear(); return ''; }
            if (!['user','service'].includes(kind)) throw new Error('Vyberte registraci uživatele nebo servisu.');
            linkError = '';
            save({code, kind, source:previous?.code === code ? previous.source : 'manual', blocked:false});
            return code;
        }
        function payload(value) {
            const code = codeValue(value);
            return code ? {referral_code:code} : {};
        }
        return {capture, begin, pending, registrationDraft, update, clear, payload, codeValue, userContact, errorMessage, safePageURL};
    }

    if (typeof module !== 'undefined' && module.exports) module.exports = {createRegistration, codeValue, userContact, errorMessage, safePageURL, STORAGE_KEY};
    if (global?.document) {
        global.ReferralRegistration = createRegistration(global);
        global.ReferralRegistration.capture();
        global.addEventListener('admin-session-ended', () => global.ReferralRegistration.clear());
    }
})(typeof window !== 'undefined' ? window : globalThis);
