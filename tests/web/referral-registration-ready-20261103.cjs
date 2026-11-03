'use strict';
// Shipped registration helpers and handlers, with an intercepted transport only.
// No browser, production request, email delivery or account mutation.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.resolve(__dirname, '../..');
const {createRegistration, codeValue, userContact, errorMessage, safePageURL, STORAGE_KEY} = require('../../web/referral-registration.js');
const helperSource = fs.readFileSync(path.join(root, 'web/referral-registration.js'), 'utf8');
const legacy = fs.readFileSync(path.join(root, 'web/legacy-app.js'), 'utf8');
const index = fs.readFileSync(path.join(root, 'web/index.html'), 'utf8');
const code = 'Fixture_Referral-20261103';
function environment(hash='', options={}) {
    const entries = options.entries || new Map(), sessionEntries = new Map();
    const location = new URL('https://fixture.invalid' + (options.pathname || '/web/customer.html') + '?unrelated=keep' + hash);
    const writes = [], events = new Map();
    const storage = {getItem:key=>entries.get(key) ?? null, setItem:(key,value)=>{entries.set(key,value);writes.push(key);}, removeItem:key=>entries.delete(key)};
    const env = {URL, URLSearchParams, location, document:{},
        history:{state:{fixture:true}, replaceState(_state,_title,next){location.href=new URL(next, location).href;}},
        addEventListener:(name,callback)=>events.set(name, callback), localStorage:storage,
        sessionStorage:{getItem:key=>sessionEntries.get(key)??null,setItem:(key,value)=>sessionEntries.set(key,value),removeItem:key=>sessionEntries.delete(key)}};
    if (options.blockStorage) Object.defineProperty(env, 'localStorage', {get(){throw Error('storage denied');}});
    if (options.blockHistory) env.history.replaceState=()=>{throw Error('history denied');};
    return {env, entries, sessionEntries, writes, events};
}
function handler(name) {
    const marker = new RegExp('(?:async )?function ' + name + '\\(').exec(legacy);
    assert.ok(marker, name);
    const end = legacy.indexOf('\n        }', marker.index);
    return legacy.slice(marker.index, end + 10);
}
const contacts = {name:'  Jan   Novák ', phone:'+420 (777) 123-456', street:' Testovací ', street_number:'12', city:' Praha ', zip:'110 00'};

test('early shipped script captures and redacts only referral fragment, before any session or network', () => {
    const page = environment('#unrelated=a%20b&referral=' + code + '&kind=service&anchor=vehicle-4');
    page.sessionEntries.set('customerWebAccessToken', 'existing-session-fixture');
    vm.runInNewContext(helperSource, {...page.env, window:page.env});
    assert.equal(page.env.location.hash, '#unrelated=a%20b&anchor=vehicle-4');
    assert.equal(page.env.ReferralRegistration.pending().code, code);
    assert.equal(page.env.ReferralRegistration.pending().source, 'link');
    assert.equal(page.sessionEntries.get('customerWebAccessToken'), 'existing-session-fixture');
    const registrationAt = index.indexOf('src="referral-registration.js"');
    assert.ok(registrationAt > 0 && registrationAt < index.indexOf('src="/admin-session.js"'));
    assert.ok(index.indexOf('src="referral-features.js"') < index.indexOf('src="/admin-session.js"'));
    assert.ok(index.indexOf('src="vendor/referral-qr.js"') < index.indexOf('src="referral-features.js"'));
});

test('reload and cold reopen preserve a public draft in its own key; only the server decides code expiration', () => {
    const page = environment('#referral=' + code + '&kind=user');
    const first = createRegistration(page.env);first.capture();
    const reloaded = createRegistration(page.env);
    assert.equal(reloaded.registrationDraft().code, code);
    assert.equal(reloaded.begin(false).open, true);
    assert.deepEqual(page.writes, [STORAGE_KEY]);
    const cold=environment('',{entries:page.entries}), reopened=createRegistration(cold.env);
    assert.equal(reopened.begin(false).open,true);
    assert.equal(reopened.registrationDraft().code,code);
    reloaded.clear();
    assert.equal(createRegistration(page.env).pending(), null);
});

test('storage/history denial never blocks registration and support URLs still redact attribution', () => {
    const page = environment('#referral=' + code + '&kind=service&view=kept', {blockStorage:true, blockHistory:true});
    const helper = createRegistration(page.env);
    assert.doesNotThrow(()=>helper.capture());
    assert.equal(helper.registrationDraft().code, code);
    assert.equal(new URL(helper.safePageURL(page.env.location.href)).hash, '#view=kept');
    assert.doesNotThrow(()=>helper.clear());
    assert.equal(helper.pending(), null);
});

test('malformed/duplicated link fields are removed, never stored, and leave a correctable registration', () => {
    for (const hash of ['#referral=short&kind=user', '#referral='+code+'&kind=admin', '#referral='+code+'&kind=user&kind=service',
        '#referral='+code+'&referral='+code, '#referral=%3Cscript%3E&kind=user', '#referral='+code+'%0A&kind=user']) {
        const page=environment(hash+'&keep=x%2By');const helper=createRegistration(page.env);helper.capture();
        assert.equal(helper.pending(), null, hash);
        assert.equal(page.env.location.hash, '#keep=x%2By');
        assert.equal(helper.begin(false).open, true);
        assert.match(helper.begin(false).error, /Můžete zadat jiný/);
        assert.equal(page.entries.size, 0);
    }
    const unrelated=environment('#kind=service&vehicle=8');createRegistration(unrelated.env).capture();
    assert.equal(unrelated.env.location.hash, '#kind=service&vehicle=8');
    const admin=environment('#referral='+code+'&kind=service', {pathname:'/web/index.html'});createRegistration(admin.env).capture();
    assert.equal(admin.entries.size, 0, 'the protected admin route is not a registration landing');
});

test('an existing login never auto-registers or changes role; suspended attribution does not leak to the next account', () => {
    const page=environment('#referral='+code+'&kind=service');
    page.sessionEntries.set('customerWebAccessToken','fixture-token');page.sessionEntries.set('customerWebRole','user');
    const helper=createRegistration(page.env);helper.capture();
    assert.deepEqual(helper.begin(true), {open:false});
    assert.equal(helper.pending().source, 'link');
    assert.equal(helper.registrationDraft(), null);
    assert.equal(createRegistration(page.env).begin(false).open, false, 'a prior signed-in referral needs a deliberate new registration, not auto-application');
    assert.equal(page.sessionEntries.get('customerWebRole'),'user');
    assert.equal(page.sessionEntries.get('customerWebAccessToken'),'fixture-token');
    vm.runInNewContext(helperSource,{...page.env,window:page.env});
    page.events.get('admin-session-ended')();
    assert.equal(page.env.ReferralRegistration.pending(),null);
});

test('optional code is strict ASCII, editable/removable, and never contains auth or identity data', () => {
    assert.equal(codeValue('  '+code+'  '),code);
    assert.deepEqual(createRegistration(environment().env).payload(''),{});
    for(const value of ['short','a'.repeat(41),'ž'.repeat(20),code+'\nextra','a'.repeat(15)]) assert.throws(()=>codeValue(value));
    const page=environment('#referral='+code+'&kind=user'), helper=createRegistration(page.env);helper.capture();
    helper.update('Second_Fixture_Referral','service');
    assert.equal(helper.pending().source,'manual');
    assert.equal(helper.pending().kind,'service');
    helper.update('','service');assert.equal(helper.pending(),null);
    assert.deepEqual(Object.keys(helper.payload(code)),['referral_code']);
});

test('required user contacts mirror the API and normalize names/phone without changing service rules', () => {
    assert.deepEqual(userContact(contacts),{name:'Jan Novák',phone:'+420777123456',street:'Testovací',street_number:'12',city:'Praha',zip:'110 00'});
    for(const key of Object.keys(contacts)) assert.throws(()=>userContact({...contacts,[key]:'  '}),key);
    for(const extra of [{name:'Jan'},{name:'Jan 123'},{phone:'abcd1234567'},{phone:'+420'},{phone:'+420777123456123456'},{zip:'1'}]) assert.throws(()=>userContact({...contacts,...extra}));
});

function registrationForm(kind='user', failure=null, withCode=true) {
    const page=environment('#referral='+code+'&kind='+kind), helper=createRegistration(page.env);helper.capture();
    const values={regEmail:'fixture@example.com',regPassword:'Fixture-password-482!',regPasswordConfirm:'Fixture-password-482!',
        regIco:kind==='service'?'12345678':'',regName:contacts.name,regDic:'',regStreet:contacts.street,regStreetNumber:kind==='service'?'':contacts.street_number,
        regCity:contacts.city,regZip:contacts.zip,regPhone:contacts.phone,regResponsiblePerson:'Test Servis',regRegistrationPurpose:'Fiktivní servisní registrace',regReferralCode:withCode?code:''};
    const nodes=Object.fromEntries(Object.entries(values).map(([key,value])=>[key,{value,removeAttribute(){}}]));
    nodes.registerErrorContainer={innerHTML:''};nodes.regReferralStatus={textContent:''};nodes.regReferralRemove={hidden:false};nodes.loginEmail={value:''};
    const calls=[],errors=[],alerts=[];
    const context={window:{ReferralRegistration:helper,CustomerWeb:true},document:{getElementById:id=>nodes[id]},
        getSelectedRegistrationMode:()=>kind,showFormError:(_id,message)=>errors.push(message),showAlert:(...value)=>alerts.push(value),
        setLoginMode(){},showLogin(){},console:{error(){}},apiCall:async(endpoint,method,payload)=>{calls.push({endpoint,method,payload});if(failure)throw failure;return {email_sent:true,message:'Přijato'};}};
    vm.createContext(context);vm.runInContext(handler('clearReferralRegistrationDraft')+'\n'+handler('handleRegister'),context);
    return {...page,helper,nodes,calls,errors,alerts,submit:()=>context.handleRegister()};
}

test('actual user and service submit handlers include the code and consume it only after success', async () => {
    for(const kind of ['user','service']) {
        const page=registrationForm(kind);await page.submit();
        assert.equal(page.errors.length,0);
        assert.equal(page.calls[0].endpoint,kind==='service'?'/user/register/service-request':'/user/register');
        assert.equal(page.calls[0].payload.referral_code,code);
        if(kind==='user')assert.equal(page.calls[0].payload.phone,'+420777123456');
        else assert.equal(page.calls[0].payload.street_number,null);
        assert.equal(page.helper.pending(),null);
        assert.equal(page.nodes.regReferralCode.value,'');
    }
});

test('registration without a code omits referral_code; missing required contact cannot submit', async () => {
    for(const kind of ['user','service']) {
        const page=registrationForm(kind,null,false);await page.submit();
        assert.equal(Object.hasOwn(page.calls[0].payload,'referral_code'),false);
    }
    const page=registrationForm();page.nodes.regStreetNumber.value='';await page.submit();
    assert.equal(page.calls.length,0);assert.match(page.errors[0],/číslo domu/);
});

test('correctable 422 and temporary 503 retain the code and show safe field feedback', async () => {
    for(const kind of ['user','service']) {
        const failure=Object.assign(new Error('raw internal validation'),{status:422,detail:[{loc:['body','referral_code'],msg:'raw-code-detail'}]});
        const page=registrationForm(kind,failure);await page.submit();
        assert.equal(page.helper.pending().code,code);assert.equal(page.nodes.regReferralCode.value,code);
        assert.match(page.errors[0],/Opravte jej/);assert.doesNotMatch(page.errors[0],/raw-code-detail|body\./);
    }
    const page=registrationForm('user',Object.assign(new Error('unavailable'),{status:503}));await page.submit();
    assert.equal(page.helper.pending().code,code);assert.match(page.errors[0],/Zkuste to později/);
});

test('telemetry URL redaction preserves unrelated fragment and does not swallow a standalone kind', () => {
    assert.equal(safePageURL('https://fixture.invalid/web/customer.html?x=1#referral='+code+'&kind=user&view=a%20b'), 'https://fixture.invalid/web/customer.html?x=1#view=a%20b');
    assert.equal(safePageURL('https://fixture.invalid/web/customer.html#kind=user&view=1'),'https://fixture.invalid/web/customer.html#kind=user&view=1');
    assert.match(legacy,/page_url: window\.ReferralRegistration\?\.safePageURL/);
    assert.match(legacy,/debug-location-href'\)\.textContent = window\.ReferralRegistration\?\.safePageURL/);
    assert.equal(errorMessage({detail:[{loc:['body','phone'],msg:'raw'}]}),'Telefon: zkontrolujte vyplněný údaj.');
});

test('actual anonymous bootstrap opens the captured registration but authenticated bootstrap never does', async () => {
    const start=legacy.indexOf("window.addEventListener('DOMContentLoaded', async () => {");
    const end=legacy.indexOf("\n            document.addEventListener('click'",start);
    for(const authenticated of [false,true]) {
        const page=environment('#referral='+code+'&kind=service'), helper=createRegistration(page.env);helper.capture();
        const registrations=[], logins=[], modes=[], calls=[];let callback;
        const context={window:{CustomerWeb:true,ReferralRegistration:helper,showCustomerEmailVerification:async()=>false,addEventListener:(_name,cb)=>{callback=cb;}},
            AdminBrowserSession:{protect(){},token:()=>authenticated?'fixture-token':null,verify:async()=>{},end:()=>assert.fail('must not end session')},
            clearLegacySessionData(){},showCustomerEmailVerification:async()=>false,initRegistrationCompanyLookup(){},
            document:{getElementById:()=>({classList:{add(){}}})},getApiBaseUrl:()=>page.env.location.origin,
            initReferralRegistrationForm(){},showLogin:()=>logins.push(true),initLoginModeFromState:()=>modes.push('login'),initRememberedLoginPreferences(){},
            showRegister:kind=>registrations.push(kind),showFormError(){},apiCall:async url=>{calls.push(url);return {role:'user'};},
            markAuthSessionEstablished(){},capturePendingPaymentReturnFromUrl(){},setupActivityTracking(){},setInterval(){},checkServerStatus(){},showDashboard(){}};
        vm.createContext(context);vm.runInContext(legacy.slice(start,end)+'\n        });',context);await callback();
        assert.deepEqual(registrations,authenticated?[]:['service']);
        assert.deepEqual(logins,authenticated?[]:[true]);
        assert.deepEqual(calls,authenticated?['/user/me']:[]);
    }
});

test('shipped edit/remove controls let a visitor replace a rejected code or continue without it', () => {
    const page=environment('#referral='+code+'&kind=user'), helper=createRegistration(page.env);helper.capture();
    const listeners=new Map(), attributes=new Map();
    const input={value:code,dataset:{referralReady:'true'},addEventListener:(name,fn)=>listeners.set(name,fn),
        setAttribute:(key,value)=>attributes.set(key,value),removeAttribute:key=>attributes.delete(key),focus(){}};
    let remove;const nodes={regReferralCode:input,regReferralStatus:{textContent:''},regReferralRemove:{hidden:false,addEventListener:(_name,fn)=>{remove=fn;}}};
    const context={window:{ReferralRegistration:helper},document:{getElementById:id=>nodes[id]},getSelectedRegistrationMode:()=> 'user'};
    vm.createContext(context);vm.runInContext(['syncReferralRegistrationDraft','clearReferralRegistrationDraft','initReferralRegistrationForm'].map(handler).join('\n'),context);
    context.initReferralRegistrationForm();
    input.value='short';listeners.get('input')();assert.equal(helper.pending(),null);assert.equal(attributes.get('aria-invalid'),'true');
    input.value='Replacement_Referral_2026';listeners.get('input')();assert.equal(helper.pending().code,input.value);assert.equal(attributes.has('aria-invalid'),false);
    remove();assert.equal(input.value,'');assert.equal(helper.pending(),null);assert.equal(nodes.regReferralRemove.hidden,true);assert.match(nodes.regReferralStatus.textContent,/bez pozvánky/);
});

test('profile invitation shortcuts enforce the current role and never turn a user into an administrator', async () => {
    const calls=[];let prevented=0;
    const context={window:{ReferralFeatures:{openPersonal:async()=>calls.push('personal'),openAdmin:async()=>calls.push('admin')}},
        currentUser:{role:'user'},isAuthenticated:()=>true,showAlert:()=>assert.fail('available module must open')};
    vm.createContext(context);vm.runInContext(handler('openReferralFeature'),context);
    const click=kind=>context.openReferralFeature({target:{closest:()=>({dataset:{referralOpen:kind}})},preventDefault(){prevented++;}});
    await click('admin');assert.equal(calls.length,0);
    await click('personal');context.currentUser.role='service';await click('personal');
    context.currentUser.role='admin';await click('admin');await click('personal');
    assert.deepEqual(calls,['personal','personal','admin']);assert.equal(prevented,3);
    context.isAuthenticated=()=>false;await click('admin');assert.equal(calls.length,3);
});

test('service Add vehicle uses guided intake only on a deliberate click and preserves selected client', async () => {
    const hidden=new Set(), classes={add:value=>hidden.add(value),remove:value=>hidden.delete(value)};
    let onClick;const section={id:'serviceAddVehicleSection',classList:{add(){},remove(){}},querySelector:()=>({addEventListener:(_name,fn)=>{onClick=fn;}})};
    const tab={children:[section,{id:'defaultVehicleForm',classList:classes}]}, calls=[];
    const context={document:{getElementById:id=>id==='addVehicleTab'?tab:id==='serviceAddVehicleSection'?section:null},
        isServiceWorkspaceRole:()=>true,serviceAddVehicleState:{initialized:false},serviceWorkspaceState:{},
        window:{ServiceFeatures:{intake:async id=>calls.push(id)}},showAlert:()=>assert.fail('intake available'),
        buildServiceAddVehicleSectionHtml:()=>assert.fail('legacy linked-only form must not be used'),loadServiceAddVehicleCustomers:()=>assert.fail('no legacy catalog prerequisite')};
    vm.createContext(context);vm.runInContext(handler('ensureServiceAddVehicleSection')+'\n'+handler('openServiceAddVehicleForCustomer'),context);
    await context.ensureServiceAddVehicleSection();assert.equal(calls.length,0);assert.equal(hidden.has('hidden'),true);
    await onClick();assert.deepEqual(calls,[undefined]);
    await context.openServiceAddVehicleForCustomer(42);assert.deepEqual(calls,[undefined,42]);assert.equal(context.serviceWorkspaceState.selectedCustomerId,42);
    context.isServiceWorkspaceRole=()=>false;await context.openServiceAddVehicleForCustomer(43);assert.equal(calls.length,2);
    assert.match(handler('renderServicesDirectory'),/window\.ServiceFeatures\?\.directoryLoaded\(container, payload\)/);
    assert.match(handler('loadServicesDirectory'),/if \(window\.CustomerWeb\) window\.ServiceFeatures\?\.directoryLoading\(container\)/);
});

// Parse the shipped markup rather than hand-building a flat list of input nodes.
// This checks ancestor visibility and the real historical CSS rule that hid ARES contacts.
function registrationDOM() {
    const nodes=new Map(), stack=[], voidTags=new Set(['area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr']);
    const markup=index.replace(/<!--[\s\S]*?-->/g,'').replace(/<(style|script)\b[^>]*>[\s\S]*?<\/\1>/gi,'');
    for(const token of markup.matchAll(/<(\/?)([a-z][\w-]*)\b([^>]*)>/gi)) {
        const tag=token[2].toLowerCase();
        if(token[1]) {const found=stack.findLastIndex(node=>node.tag===tag);if(found>=0)stack.length=found;continue;}
        const attributes=Object.fromEntries([...token[3].matchAll(/([\w:-]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?/g)].map(match=>[match[1],match[2]??match[3]??match[4]??'']));
        const classes=new Set((attributes.class||'').split(/\s+/).filter(Boolean));
        const node={tag,parent:stack.at(-1)||null,attributes,style:{},dataset:{},value:attributes.value||'',required:Object.hasOwn(attributes,'required'),hidden:Object.hasOwn(attributes,'hidden'),
            classList:{add:name=>classes.add(name),remove:name=>classes.delete(name),contains:name=>classes.has(name),toggle(name,enabled){if(enabled)classes.add(name);else classes.delete(name);}},
            setAttribute:(name,value)=>{attributes[name]=value;},removeAttribute:name=>{delete attributes[name];},addEventListener(){},focus(){},remove(){}};
        for(const declaration of (attributes.style||'').split(';')) {const [name,value]=declaration.split(':');if(name?.trim()&&value)node.style[name.trim()]=value.trim();}
        if(attributes.id)nodes.set(attributes.id,node);
        if(!voidTags.has(tag)&&!token[3].endsWith('/'))stack.push(node);
    }
    const css=['theme.css','app.css','inline-styles.css'].map(file=>fs.readFileSync(path.join(root,'web',file),'utf8')).join('\n')+'\n'+[...index.matchAll(/<style>([\s\S]*?)<\/style>/g)].map(match=>match[1]).join('\n');
    const hiddenRules=[...css.replace(/\/\*[\s\S]*?\*\//g,'').matchAll(/([^{}]+)\{([^{}]*)\}/g)].filter(match=>/display\s*:\s*none\b/.test(match[2])).flatMap(match=>match[1].trim().split(',').map(selector=>({selector:selector.trim(),important:/display\s*:\s*none\s*!important/.test(match[2])})));
    const matches=(node,selector)=>/^#[\w-]+$/.test(selector)?node.attributes.id===selector.slice(1):/^\.[\w-]+$/.test(selector)?node.classList.contains(selector.slice(1)):false;
    const visible=node=>{for(let current=node;current;current=current.parent){if(current.hidden||hiddenRules.some(rule=>rule.important&&matches(current,rule.selector)))return false;if(current.style.display==='none')return false;if(!current.style.display&&hiddenRules.some(rule=>matches(current,rule.selector)))return false;}return true;};
    return {nodes,visible,hiddenRules};
}

test('real anonymous join bootstrap exposes mandatory contact inputs through their actual HTML/CSS ancestors without IČO', async () => {
    for(const kind of ['user','service']) {
        const page=environment('#referral='+code+'&kind='+kind), helper=createRegistration(page.env);helper.capture();
        const dom=registrationDOM();
        assert.ok(dom.hiddenRules.some(rule=>rule.selector==='#aresDataFields'),'fixture must include the CSS which caused the real browser failure');
        const contacts=['regName','regStreet','regStreetNumber','regCity','regZip'];
        for(const id of contacts)assert.equal(dom.visible(dom.nodes.get(id)),false,'registration starts hidden before opening');
        let bootstrap;const errors=[];
        const context={window:{CustomerWeb:true,ReferralRegistration:helper,addEventListener:(name,fn)=>{if(name==='DOMContentLoaded')bootstrap=fn;}},
            AdminBrowserSession:{protect(){},token:()=>null},document:{getElementById:id=>dom.nodes.get(id)||null},registrationMode:'user',
            clearLegacySessionData(){},getApiBaseUrl:()=>page.env.location.origin,initLoginModeFromState(){},initRememberedLoginPreferences(){},
            clearRegistrationCompanyLookup(){},initRegistrationCompanyLookup(){},
            getSelectedLoginMode:()=> 'user',showFormError:(_id,message)=>errors.push(message)};
        vm.createContext(context);
        vm.runInContext(['getSelectedRegistrationMode','getRegistrationModeHintText','setRegistrationMode','syncReferralRegistrationDraft',
            'clearReferralRegistrationDraft','initReferralRegistrationForm','clearFormError','showLogin','showRegister'].map(handler).join('\n'),context);
        const start=legacy.indexOf("window.addEventListener('DOMContentLoaded', async () => {"), end=legacy.indexOf("\n            document.addEventListener('click'",start);
        vm.runInContext(legacy.slice(start,end)+'\n        });',context);await bootstrap();
        assert.equal(dom.nodes.get('regIco').value,'');assert.equal(errors.length,0);
        for(const id of contacts){assert.equal(dom.visible(dom.nodes.get(id)),true,kind+': '+id+' must be reachable without an ARES lookup');assert.equal(dom.nodes.get(id).required,id==='regStreetNumber'?kind==='user':true);}
        assert.equal(dom.nodes.get('registrationContactFields').style.display,'block');
        assert.equal(dom.nodes.get('regReferralCode').value,code);
        assert.equal(dom.nodes.get('serviceRegistrationExtraFields').classList.contains('hidden'),kind!=='service');
        assert.equal(dom.nodes.get('regIco').required,kind==='service');
    }
});
