/* Referral presentation only. Entitlements, attribution and awards remain server-authoritative. */
(function (global) {
    'use strict';
    const BASE = '/api/v1/referrals';
    const statuses = Object.freeze({waiting_verification:'Čeká na ověření e-mailu', waiting_vehicle:'Čeká na první vlastní vozidlo', waiting_job:'Čeká na první dokončenou zakázku', waiting_service_approval:'Čeká na schválení servisu', qualified:'Podmínky splněny', ineligible:'Nesplňuje podmínky', unavailable:'Účet není dostupný'});
    function parseUTC(raw) {
        if (typeof raw !== 'string' || !raw) return null;
        const value = new Date(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(raw) ? raw : raw + 'Z');
        return Number.isNaN(value.getTime()) ? null : value;
    }
    function rewardState(reward, now = new Date()) {
        if (reward.revoked_at) return 'revoked';
        if (reward.waiting_for_paid) return 'waiting';
        const start = parseUTC(reward.starts_at), end = parseUTC(reward.ends_at);
        if (!start || (!reward.lifetime && !end)) return 'unknown';
        if (start > now) return 'queued';
        if (end && end <= now) return 'expired';
        return 'active';
    }
    function invitationURL(raw, origin, code, kind) {
        if (typeof raw !== 'string' || !/^[A-Za-z0-9_-]{16,40}$/.test(code || '')) throw Error('Server nevrátil platnou pozvánku.');
        const url = new URL(raw), base = new URL(origin);
        if (url.origin !== base.origin || url.username || url.password || url.hash ||
            !['https:', 'http:'].includes(url.protocol) ||
            (url.protocol !== 'https:' && !['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)) ||
            url.pathname !== BASE + '/join/' + code ||
            [...url.searchParams].length !== 1 || url.searchParams.get('kind') !== kind) {
            throw Error('Odkaz pozvánky nepatří k této aplikaci.');
        }
        return url.href;
    }
    function reasonText(raw) {
        const value = String(raw || '').trim(), size = [...value].length;
        if (size < 5 || size > 500) throw Error('Uveďte důvod v délce 5 až 500 znaků.');
        return value;
    }
    function accountCountLabel(value) {
        const n=Number.isSafeInteger(value)&&value>=0?value:0;
        return `${n} ${n===1?'účet':n>=2&&n<=4?'účty':'účtů'} s osobním odkazem`;
    }
    function createFeatures(env) {
        let active = null, sequence = 0, pendingScope = null;
        const doc = env.document;
        const text = (tag, value, cls) => { const el = doc.createElement(tag); el.textContent = String(value ?? ''); if (cls) el.className = cls; return el; };
        const date = raw => parseUTC(raw)?.toLocaleString('cs-CZ', {dateStyle:'medium', timeStyle:'short'}) || 'Datum není dostupné';
        const count = n => Number.isSafeInteger(n) && n >= 0 ? n : 0;
        const stale = () => new DOMException('Přihlášení nebo otevřený přehled se změnily.', 'AbortError');
        function ensure(ctx, view) {
            if (ctx.closed || active !== ctx || !ctx.dialog.isConnected || env.AdminBrowserSession !== ctx.session || (view !== undefined && view !== ctx.view)) throw stale();
            ctx.session.assertCurrent(ctx.snapshot);
        }
        function close() {
            const ctx = active;
            if (!ctx) return;
            ctx.closed = true; active = null; ctx.controller.abort(); env.clearInterval(ctx.timer);
            for (const confirm of ctx.confirmations) confirm.close();
            if (ctx.dialog.open) ctx.dialog.close();
            ctx.dialog.remove();
        }
        function reset() { close(); pendingScope = null; }
        function error(ctx, value) {
            try { ensure(ctx); } catch { return; }
            ctx.notice.setAttribute('role', 'alert'); ctx.notice.textContent = value; ctx.notice.hidden = false;
        }
        function notice(ctx, value) { ctx.notice.setAttribute('role','status'); ctx.notice.textContent = value; ctx.notice.hidden = !value; }
        function button(ctx, label, handler, cls = '') {
            const b = text('button', label, 'referral-button ' + cls); b.type = 'button';
            b.addEventListener('click', async () => {
                if (b.disabled || !b.isConnected) return;
                b.disabled = true;
                try { ensure(ctx); await handler(); }
                catch (e) { if (e.name !== 'AbortError') error(ctx, e.message || 'Akci nelze dokončit.'); }
                finally { if (b.isConnected) b.disabled = false; }
            });
            return b;
        }
        function section(title) { const el = text('section','', 'referral-section'); el.append(text('h3',title)); return el; }
        function field(label, input) { const el = text('label', label, 'referral-field'); el.append(input); return el; }
        function start(title, admin) {
            close();
            const session = env.AdminBrowserSession;
            if (!session?.token?.() || !session.snapshot || !session.assertCurrent || !session.request) throw Error('Nejprve se přihlaste.');
            const snapshot = session.snapshot(); session.assertCurrent(snapshot);
            const dialog = doc.createElement('dialog'); dialog.className = 'referral-dialog';
            const headingID = 'referral-heading-' + (++sequence); dialog.setAttribute('aria-labelledby',headingID);
            const heading = text('h2', title); heading.id = headingID;
            const header = text('header','', 'referral-header'), body = text('div','', 'referral-body'), status = text('p','', 'referral-notice');
            status.hidden = true; status.setAttribute('aria-live','polite');
            const ctx = {session,snapshot,dialog,body,notice:status,admin,closed:false,view:0,controller:new AbortController(),confirmations:new Set(),query:'',offset:0};
            active = ctx; header.append(heading,button(ctx,'Zavřít',close,'referral-secondary'));
            dialog.append(header,status,body); doc.body.append(dialog);
            dialog.addEventListener('close', () => { if (active === ctx) close(); }, {once:true});
            dialog.showModal();
            ctx.timer = env.setInterval(() => { try { ensure(ctx); } catch { if (active === ctx) reset(); } }, 500);
            return ctx;
        }
        async function request(ctx, path, method = 'GET', body, view) {
            const expectedView = view === undefined ? ctx.view : view;
            ensure(ctx,expectedView);
            let response;
            try {
                response = await ctx.session.request(path, {method,signal:ctx.controller.signal,timeoutMs:30000,
                    ...(body === undefined ? {} : {headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})},ctx.snapshot);
            } catch(e) {
                ensure(ctx,expectedView);
                if(e.name === 'AbortError') throw Error('Server neodpověděl včas. Zkuste akci znovu.');
                throw e;
            }
            ensure(ctx,expectedView);
            let data;
            try { data = response.status === 204 ? null : await response.json(); }
            catch (e) { ensure(ctx,expectedView); throw Error('Server nevrátil čitelný výsledek. Obnovte přehled.'); }
            ensure(ctx,expectedView);
            if (!response.ok) {
                const messages = {401:'Přihlášení již není platné. Přihlaste se znovu.',403:'Tato akce není pro váš účet dostupná. Zkontrolujte přihlášení a ověření administrátora.',404:'Účet nebo odměna nejsou dostupné.',409:'Toto potvrzení už patří jiné odměně. Obnovte přehled.',422:'Zkontrolujte vyplněné údaje.',429:'Příliš mnoho pokusů. Zkuste akci později.',503:'Pozvánky a odměny zatím nejsou na serveru dostupné.'};
                const e = Error(typeof data?.detail === 'string' ? data.detail : messages[response.status] || 'Požadavek se nepodařilo dokončit.');
                e.status = response.status; throw e;
            }
            return data;
        }
        async function authorize(ctx) {
            const profile = await request(ctx,'/user/me');
            const roles = ctx.admin ? ['admin','developer_admin'] : ['user','customer','service'];
            if (!Number.isSafeInteger(profile?.id) || profile.id <= 0 || !roles.includes(profile.role)) {
                throw Error(ctx.admin ? 'Správa odměn je dostupná pouze administrátorovi.' : 'Přehled je dostupný přihlášenému uživateli nebo servisu.');
            }
            ctx.profile = profile;
            let same = pendingScope?.session === ctx.session && pendingScope?.profileID === profile.id;
            if (same) { try { ctx.session.assertCurrent(pendingScope.snapshot); } catch { same = false; } }
            if (!same) pendingScope = {session:ctx.session,snapshot:ctx.snapshot,profileID:profile.id,grants:new Map()};
            ctx.grants = pendingScope.grants;
        }
        function validateSummary(ctx, data, targetID) {
            if (!data || data.customer_id !== targetID || !Array.isArray(data.referrals) || !Array.isArray(data.rewards)) throw Error('Server nevrátil přehled požadovaného účtu.');
            ensure(ctx); return data;
        }
        function qr(ctx, url, kind) {
            if (typeof env.qrcode !== 'function') return text('p','QR kód nyní nelze vytvořit. Použijte odkaz nebo osobní kód.');
            const matrix = env.qrcode(0,'M'); matrix.addData(url,'Byte'); matrix.make();
            const size = matrix.getModuleCount(), canvas = doc.createElement('canvas'), scale = 5, margin = 4;
            canvas.width = canvas.height = (size + margin * 2) * scale;
            const paint = canvas.getContext('2d');
            if (!paint) return text('p','QR kód nyní nelze zobrazit. Použijte odkaz.');
            paint.fillStyle = '#fff'; paint.fillRect(0,0,canvas.width,canvas.height); paint.fillStyle = '#000';
            for (let y=0;y<size;y++) for (let x=0;x<size;x++) if (matrix.isDark(y,x)) paint.fillRect((x+margin)*scale,(y+margin)*scale,scale,scale);
            canvas.className = 'referral-qr'; canvas.setAttribute('role','img'); canvas.setAttribute('aria-label','QR pozvánky pro ' + (kind === 'service' ? 'servis' : 'uživatele'));
            return canvas;
        }
        async function copy(ctx, value, fallback) {
            ensure(ctx);
            try { if (!env.navigator.clipboard?.writeText) throw Error('unavailable'); await env.navigator.clipboard.writeText(value); ensure(ctx); notice(ctx,'Odkaz byl zkopírován.'); }
            catch (e) {
                ensure(ctx); fallback.focus(); fallback.select();
                notice(ctx,'Automatické kopírování není dostupné. Odkaz je vybraný; zkopírujte jej ručně.');
            }
        }
        function invitation(ctx, summary, initialKind) {
            const area = section('Vaše pozvánka'), select = doc.createElement('select'), shareArea = text('div','', 'referral-share');
            for (const [value,label] of [['user','Uživatele'],['service','Servis']]) { const opt = text('option',label); opt.value=value; select.append(opt); }
            select.value = initialKind; area.append(field('Koho chcete pozvat',select),shareArea);
            const code = text('code',summary.code || 'Kód není dostupný','referral-code'); area.append(text('p','Váš osobní kód'),code);
            function render() {
                ensure(ctx); shareArea.replaceChildren();
                try {
                    const url = invitationURL(select.value === 'service' ? summary.service_url : summary.user_url,env.location.origin,summary.code,select.value);
                    const input = doc.createElement('input'); input.type='text'; input.readOnly=true; input.value=url; input.setAttribute('aria-label','Odkaz pozvánky');
                    const actions = text('div','', 'referral-actions');
                    actions.append(button(ctx,'Kopírovat odkaz',()=>copy(ctx,url,input),'referral-secondary'));
                    actions.append(button(ctx,'Sdílet pozvánku',async()=>{
                        if (typeof env.navigator.share !== 'function') return copy(ctx,url,input);
                        try { await env.navigator.share({title:'Pozvánka do Evidence Vozidel',url}); ensure(ctx); }
                        catch(e) { if(e.name !== 'AbortError') await copy(ctx,url,input); }
                    }));
                    shareArea.append(qr(ctx,url,select.value),input,actions);
                } catch(e) { shareArea.append(text('p',e.message,'referral-error')); }
            }
            select.addEventListener('change',render); render(); return area;
        }
        function rewards(ctx, summary, admin) {
            const area = section('Odměny'), labels = {active:'Aktivní bonus',waiting:'Čeká na placené Premium',queued:'Navazující bonus',expired:'Bonus skončil',revoked:'Odměna odebrána',unknown:'Platnost nelze určit'};
            if (!summary.rewards.length) area.append(text('p','Zatím bez odměny. Postup najdete výše.'));
            for (const reward of summary.rewards) {
                const state=rewardState(reward), card=text('article','', 'referral-card'); card.dataset.rewardId=String(reward.id);
                card.append(text('h4',reward.lifetime ? 'Premium doživotně' : 'Premium na měsíc'),text('p',labels[state],'referral-state referral-state-'+state),text('p',reward.reason));
                card.append(text('p',({user:'Automaticky: 3 ověření uživatelé s vozidlem',service:'Automaticky: ověřený servis s dokončenou zakázkou',admin:'Přidělil administrátor'})[reward.source] || 'Odměna','referral-muted'));
                if (reward.waiting_for_paid && !reward.revoked_at) card.append(text('p','Bonus se zatím nespotřebovává. Začne po dočerpání placeného Premium.'));
                else { card.append(text('p','Od ' + date(reward.starts_at))); if (reward.ends_at) card.append(text('p','Do ' + date(reward.ends_at))); }
                if (reward.revoked_at) card.append(text('p','Odebrána ' + date(reward.revoked_at),'referral-muted'));
                if (admin && !reward.revoked_at) card.append(button(ctx,'Odebrat odměnu',()=>revokeForm(ctx,summary,reward),'referral-danger'));
                area.append(card);
            }
            area.append(text('p',summary.billing_note,'referral-muted'),text('p','Dostupné funkce určuje aktuální tarif ověřený serverem. Historie odměn sama tarif nemění.','referral-muted')); return area;
        }
        function entries(summary, admin) {
            const area=section('Pozvané účty');
            if (!summary.referrals.length) area.append(text('p','Přes tento kód se zatím nikdo nezaregistroval.'));
            for (const entry of summary.referrals.slice(0,200)) {
                const card=text('article','', 'referral-card');
                card.append(text('h4',admin && entry.name ? entry.name : (entry.kind === 'service' ? 'Pozvaný servis' : 'Pozvaný uživatel') + ' #' + entry.id));
                if (admin && entry.email) card.append(text('p',entry.email));
                card.append(text('p',statuses[entry.status] || 'Čeká na kontrolu','referral-state'),text('p','Registrace ' + date(entry.created_at),'referral-muted'));
                if (entry.qualified_at) card.append(text('p','Podmínky splněny ' + date(entry.qualified_at),'referral-muted'));
                area.append(card);
            }
            if (summary.registrations > 200) area.append(text('p','Zobrazeno posledních 200 registrací; souhrny zahrnují celou historii.','referral-muted'));
            return area;
        }
        function renderSummary(ctx, summary, initialKind) {
            const body=ctx.body; body.replaceChildren();
            if (ctx.admin) body.append(button(ctx,'← Zpět na přehled účtů',()=>loadAdmin(ctx),'referral-secondary'));
            const identity=section(ctx.admin ? 'Přehled účtu' : 'Váš účet'); identity.append(text('p',summary.name));
            if (ctx.admin && summary.email) identity.append(text('p',summary.email));
            body.append(identity);
            if (!ctx.admin) body.append(invitation(ctx,summary,initialKind));
            const progress=section('Cesta k další odměně'), counts=text('dl','', 'referral-counts');
            for (const [label,value] of [['Registrací',summary.registrations],['Uživatelů splňujících podmínky',summary.qualified_users],['Servisů splňujících podmínky',summary.qualified_services]]) counts.append(text('dt',label),text('dd',count(value)));
            const remaining=count(summary.users_to_next_reward), people=remaining===1?'zbývá 1 uživatel':remaining>=2&&remaining<=4?`zbývají ${remaining} uživatelé`:`zbývá ${remaining} uživatelů`;
            progress.append(counts,text('p',`K dalšímu měsíci Premium ${people} nebo 1 nový servis.`),text('p',summary.rules),text('p','Samotné sdílení odkazu nic nepřiděluje. Pozvánka nepředává přístup k vozidlům.','referral-muted'));
            body.append(progress,rewards(ctx,summary,ctx.admin),entries(summary,ctx.admin));
            if (ctx.admin) body.append(grantForm(ctx,summary));
            body.append(button(ctx,'Obnovit přehled',()=>loadSummary(ctx,summary.customer_id,initialKind),'referral-secondary'));
        }
        async function loadSummary(ctx, targetID, kind='user') {
            const view=++ctx.view; notice(ctx,''); ctx.body.replaceChildren(text('p','Načítám přehled…'));
            try {
                const data=await request(ctx,ctx.admin ? BASE+'/admin/'+targetID : BASE+'/me','GET',undefined,view);
                ensure(ctx,view); renderSummary(ctx,validateSummary(ctx,data,targetID),kind);
            } catch(e) {
                if (e.name==='AbortError') return;
                try { ensure(ctx,view); } catch { return; }
                ctx.body.replaceChildren(button(ctx,'Načíst znovu',()=>loadSummary(ctx,targetID,kind))); error(ctx,e.message);
            }
        }
        function confirm(ctx, message, label='Potvrdit') {
            ensure(ctx);
            return new Promise(resolve=>{
                const dialog=doc.createElement('dialog'); dialog.className='referral-dialog referral-confirm'; dialog.setAttribute('aria-label','Potvrzení změny odměny');
                const body=text('div','', 'referral-body'); let confirmed=false;
                body.append(text('h3','Potvrdit změnu'),text('p',message));
                body.append(button(ctx,'Zrušit',()=>dialog.close(),'referral-secondary'),button(ctx,label,()=>{confirmed=true;dialog.close();}));
                dialog.append(body); doc.body.append(dialog); ctx.confirmations.add(dialog);
                dialog.addEventListener('close',()=>{ctx.confirmations.delete(dialog);dialog.remove();try{ensure(ctx);resolve(confirmed);}catch{resolve(false);}},{once:true});
                dialog.showModal();
            });
        }
        function uuid() {
            if (env.crypto.randomUUID) return env.crypto.randomUUID();
            const bytes=env.crypto.getRandomValues(new Uint8Array(16)); bytes[6]=(bytes[6]&15)|64;bytes[8]=(bytes[8]&63)|128;
            return Array.from(bytes,(b,i)=>([4,6,8,10].includes(i)?'-':'')+b.toString(16).padStart(2,'0')).join('');
        }
        function grantForm(ctx, summary) {
            const area=section('Přidělit odměnu tomuto účtu'), kind=doc.createElement('select'), reason=doc.createElement('textarea');
            for (const [value,label] of [['month','Měsíc Premium'],['lifetime','Doživotní Premium']]) {const option=text('option',label);option.value=value;kind.append(option);}
            reason.rows=3; reason.maxLength=1000; reason.dataset.referralReason='grant';
            let draft=ctx.grants.get(summary.customer_id);
            if (draft) {kind.value=draft.kind;reason.value=draft.reason;kind.disabled=reason.disabled=true;}
            const submit=button(ctx,draft?'Znovu ověřit stejné přidělení':'Přidělit odměnu',async()=>{
                if (!draft) {
                    const value=reasonText(reason.value), selected=kind.value;
                    if (!await confirm(ctx,`Přidělit ${selected==='lifetime'?'doživotní Premium':'měsíc Premium'} účtu ${summary.name} (${summary.email || '#'+summary.customer_id})? Důvod: ${value}`,'Potvrdit přidělení')) return;
                    draft={request_id:uuid(),kind:selected,reason:value}; ctx.grants.set(summary.customer_id,draft); kind.disabled=reason.disabled=true;
                }
                try {
                    const result=await request(ctx,BASE+'/admin/'+summary.customer_id+'/rewards','POST',draft);
                    if (!Number.isSafeInteger(result?.id)) throw Error('Výsledek odměny se nepodařilo ověřit.');
                    ctx.grants.delete(summary.customer_id); await loadSummary(ctx,summary.customer_id); notice(ctx,'Server potvrdil přidělení odměny.');
                } catch(e) {
                    submit.textContent='Znovu ověřit stejné přidělení';
                    if (e.name !== 'AbortError') throw Error(e.message+' Opakování použije stejné potvrzení a nevytvoří druhou odměnu.');
                    throw e;
                }
            });
            area.append(field('Odměna',kind),field('Důvod přidělení (5–500 znaků)',reason),text('p','Změna se zapíše do historie. Nezruší placené předplatné. Při nejistém výsledku použijte opakování stejného potvrzení.','referral-muted'),submit);
            return area;
        }
        function revokeForm(ctx, summary, reward) {
            ensure(ctx); const area=section('Odebrat odměnu #'+reward.id), reason=doc.createElement('textarea'); reason.rows=3; reason.maxLength=1000; reason.dataset.referralReason='revoke';
            area.append(field('Důvod odebrání (5–500 znaků)',reason));
            area.append(button(ctx,'Zrušit',()=>area.remove(),'referral-secondary'),button(ctx,'Potvrdit odebrání',async()=>{
                const value=reasonText(reason.value);
                if (!await confirm(ctx,`Odebrat odměnu #${reward.id} účtu ${summary.name} (${summary.email || '#'+summary.customer_id})? Důvod: ${value}`,'Odebrat odměnu')) return;
                const result=await request(ctx,BASE+'/admin/'+summary.customer_id+'/rewards/'+reward.id+'/revoke','POST',{reason:value});
                if (result?.id !== reward.id || !result.revoked_at) throw Error('Odebrání se nepodařilo potvrdit. Obnovte přehled.');
                await loadSummary(ctx,summary.customer_id); notice(ctx,'Server potvrdil odebrání. Záznam zůstává v historii.');
            },'referral-danger'));
            ctx.body.querySelector('[data-referral-revoke]')?.remove(); area.dataset.referralRevoke='1'; ctx.body.prepend(area); reason.focus();
        }
        async function loadAdmin(ctx) {
            const view=++ctx.view; notice(ctx,''); ctx.body.replaceChildren(text('p','Načítám účty…'));
            try {
                const params=new URLSearchParams({search:ctx.query,offset:String(ctx.offset)}), page=await request(ctx,BASE+'/admin?'+params,'GET',undefined,view);
                ensure(ctx,view);
                if (!Array.isArray(page?.items) || page.limit !== 30 || page.offset !== ctx.offset || !Number.isSafeInteger(page.total)) throw Error('Server nevrátil platnou stránku přehledu.');
                const form=doc.createElement('form'), search=doc.createElement('input'); search.type='search';search.maxLength=120;search.value=ctx.query;
                const find=button(ctx,'Hledat',()=>{ctx.query=search.value.trim();ctx.offset=0;return loadAdmin(ctx);});
                form.append(field('Jméno nebo e-mail',search),find);form.addEventListener('submit',e=>{e.preventDefault();find.click();});
                ctx.body.replaceChildren(form,text('p',accountCountLabel(page.total)));
                if (!page.items.length) ctx.body.append(text('p','Žádné odpovídající účty.'));
                for (const item of page.items) {
                    if (!Number.isSafeInteger(item.id) || item.id<=0) continue;
                    const card=text('article','', 'referral-card');card.append(text('h3',item.name),text('p',item.email),text('p',`${count(item.registrations)} registrací · ${count(item.qualified)} splnilo podmínky`),button(ctx,'Otevřít přehled účtu',()=>loadSummary(ctx,item.id),'referral-secondary'));ctx.body.append(card);
                }
                const pages=text('nav','', 'referral-actions');pages.setAttribute('aria-label','Stránky účtů');
                const prev=button(ctx,'Předchozí',()=>{ctx.offset=Math.max(0,ctx.offset-30);return loadAdmin(ctx);},'referral-secondary'), next=button(ctx,'Další',()=>{ctx.offset+=30;return loadAdmin(ctx);},'referral-secondary');
                prev.disabled=ctx.offset===0;next.disabled=ctx.offset+30>=page.total;pages.append(prev,text('span','Strana '+(Math.floor(ctx.offset/30)+1)),next);ctx.body.append(pages);
            } catch(e) {
                if (e.name==='AbortError') return;
                try { ensure(ctx,view); } catch { return; }
                ctx.body.replaceChildren(button(ctx,'Načíst znovu',()=>loadAdmin(ctx)));error(ctx,e.message);
            }
        }
        async function open(admin, kind='user') {
            let ctx;
            try { ctx=start(admin?'Pozvánky a odměny':'Pozvat a získat odměny',admin); await authorize(ctx); if(admin) await loadAdmin(ctx);else await loadSummary(ctx,ctx.profile.id,kind==='service'?'service':'user'); }
            catch(e) { if(e.name==='AbortError')return;if(ctx){ctx.body.replaceChildren();error(ctx,e.message);}else if(env.showAlert)env.showAlert(e.message,'error'); }
        }
        env.addEventListener('admin-session-ended',reset);env.addEventListener('pagehide',reset);
        return Object.freeze({openPersonal:kind=>open(false,kind),openAdmin:()=>open(true),reset});
    }
    if (typeof module !== 'undefined') module.exports = {parseUTC,rewardState,invitationURL,reasonText,accountCountLabel,createFeatures};
    if (global.document) global.ReferralFeatures=createFeatures(global);
})(typeof window !== 'undefined' ? window : globalThis);
