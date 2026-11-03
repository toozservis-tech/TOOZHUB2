'use strict';
// Public registration transport and shipped ARES handlers. No provider/network/browser calls.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const root=path.resolve(__dirname,'../..');
const legacy=fs.readFileSync(path.join(root,'web/legacy-app.js'),'utf8');
function functionSource(name) {
    const match=new RegExp('(?:async )?function '+name+'\\(').exec(legacy);assert.ok(match,name);
    const end=legacy.indexOf('\n        }',match.index);return legacy.slice(match.index,end+10);
}
const storage=()=>{const data=new Map();return {getItem:key=>data.get(key)??null,setItem:(key,value)=>data.set(key,String(value)),removeItem:key=>data.delete(key)};};
function sessionFixture() {
    const calls=[],window={addEventListener(){},dispatchEvent(){}};
    const context={window,localStorage:storage(),sessionStorage:storage(),document:{addEventListener(){}},
        location:{origin:'https://fixture.invalid',pathname:'/web/customer.html',replace(){}},URL,Headers,Response,AbortController,DOMException,
        atob,crypto:require('node:crypto').webcrypto,setTimeout,clearTimeout,Event,CustomEvent,
        fetch:async(url,options)=>{calls.push({url,options});return new Response('{"ico":"12345678"}');}};
    vm.runInNewContext(fs.readFileSync(path.join(root,'web/customer-session.js'),'utf8'),context);
    return {session:window.AdminBrowserSession,calls};
}
test('anonymous exact GET company projection has no bearer; every legacy/private ARES route and other method stays protected',async()=>{
    const f=sessionFixture();
    const result=await f.session.request('/user/registration-company?ico=12345678',{method:'GET'});await result.json();
    assert.equal(f.calls.length,1);assert.equal(f.calls[0].options.headers.has('Authorization'),false);
    for(const url of ['/user/ares?ico=12345678','/api/v1/ares/12345678','/user/registration-company/','/user/registration-company-extra','/api/v1/vehicles','/admin-api/users'])await assert.rejects(f.session.request(url));
    for(const method of ['POST','PUT','DELETE','PATCH','HEAD'])await assert.rejects(f.session.request('/user/registration-company?ico=12345678',{method}));
    for(const url of ['https://foreign.invalid/user/registration-company?ico=12345678','https://user:secret@fixture.invalid/user/registration-company?ico=12345678'])await assert.rejects(f.session.request(url));
    assert.equal(f.calls.length,1);
});

function deferred(){let resolve;const promise=new Promise(done=>{resolve=done;});return {promise,resolve};}
const company=(ico='12345678',name='Fixture Autoservis')=>({ico,company_name:name,dic:'CZ'+ico,street:'Testovací',house_number:'12',city:'Praha',zip:'11000',source:'ares',private_field:'must-not-be-copied'});
const response=(data,status=200)=>({ok:status===200,status,json:async()=>data,text:async()=>JSON.stringify(data)});
function lookupFixture(options={}) {
    const nodes={},timers=new Map(),calls=[];let generation=0,token=null,id=0;
    const make=(value='')=>({value,dataset:{},style:{},textContent:'',disabled:false,hidden:false,maxLength:200,
        listeners:new Map(),classList:{contains:name=>false,remove(){},toggle(){}},addEventListener(name,fn){this.listeners.set(name,fn);},emit(name){this.listeners.get(name)?.();}});
    for(const name of ['regIco','regName','regDic','regStreet','regStreetNumber','regCity','regZip','regCompanyLookupBtn','regCompanyStatus','registerForm'])nodes[name]=make();
    nodes.regIco.value='12345678';nodes.regName.value=options.kind==='user'?'Jan Novák':'';
    Object.assign(nodes.regStreet,{value:options.street||''});
    const session={token:()=>token,snapshot:()=>({generation}),assertCurrent:captured=>{if(captured.generation!==generation)throw new DOMException('stale','AbortError');},
        request:async(url,init,captured)=>{calls.push({url,init,captured});return options.fetcher?options.fetcher(url,init):response(company());}};
    const window={CustomerWeb:true,AdminBrowserSession:session};
    const context={window,AdminBrowserSession:session,document:{getElementById:name=>nodes[name]||null},AbortController,Map,
        setTimeout:fn=>{timers.set(++id,fn);return id;},clearTimeout:key=>timers.delete(key),syncReferralRegistrationDraft(){}};
    vm.createContext(context);
    vm.runInContext("let aresAbortController=null, aresDebounceTimeout=null, registrationCompanyVersion=0; const registrationCompanyAutofill=new Map(), registrationCompanyEdits=new Map(); var registrationMode="+JSON.stringify(options.kind||'service')+';\n'+
        ['getSelectedRegistrationMode','getRegistrationModeHintText','setRegistrationMode','clearRegistrationCompanyLookup','initRegistrationCompanyLookup','loadAresData'].map(functionSource).join('\n'),context);
    context.initRegistrationCompanyLookup();
    return {context,nodes,calls,session,timers,lookup:()=>context.loadAresData(nodes.regIco.value),changeSession:()=>{generation++;},login:()=>{token='new-account-fixture';generation++;}};
}

test('public lookup prefill copies safe company fields for service, but user full name stays separate',async()=>{
    for(const kind of ['user','service']){
        const f=lookupFixture({kind});await f.lookup();
        assert.equal(f.calls[0].url,'/user/registration-company?ico=12345678');assert.equal(f.calls[0].init.method,'GET');
        assert.equal(f.nodes.regIco.dataset.aresListenerAttached,'true','the old protected lookup must not bind');
        assert.equal(f.nodes.regIco.dataset.companyVerifiedIco,'12345678');
        assert.equal(f.nodes.regName.value,kind==='user'?'Jan Novák':'Fixture Autoservis');
        for(const [id,value] of [['regDic','CZ12345678'],['regStreet','Testovací'],['regStreetNumber','12'],['regCity','Praha'],['regZip','11000']])assert.equal(f.nodes[id].value,value);
        assert.equal(Object.hasOwn(f.nodes,'private_field'),false);
        assert.equal(f.nodes.regCompanyLookupBtn.disabled,false);
    }
});

test('blank/malformed optional ICO never fetches; authenticated or hidden registration cannot start public lookup',async()=>{
    const f=lookupFixture({kind:'user'});
    for(const value of ['','123','１２３４５６７８','1234567x']){f.nodes.regIco.value=value;await f.lookup();}
    assert.equal(f.calls.length,0);
    f.nodes.regIco.value='12345678';f.login();await f.lookup();assert.equal(f.calls.length,0);
    const hidden=lookupFixture();hidden.nodes.registerForm.classList.contains=()=>true;await hidden.lookup();assert.equal(hidden.calls.length,0);
});

test('new ICO clears only unchanged prior autofill and invalidates old company confirmation',async()=>{
    const f=lookupFixture();await f.lookup();
    f.nodes.regStreet.value='Ručně zvolená ulice';f.nodes.regStreet.emit('input');
    f.nodes.regIco.value='87654321';f.nodes.regIco.emit('input');
    assert.equal(f.nodes.regIco.dataset.companyVerifiedIco,undefined);
    assert.equal(f.nodes.regName.value,'');assert.equal(f.nodes.regCity.value,'');
    assert.equal(f.nodes.regStreet.value,'Ručně zvolená ulice');
    assert.equal(f.nodes.regCompanyLookupBtn.disabled,false);
});

test('late response cannot prefill after ICO change, mode change, session change, login, or closing the form',async()=>{
    for(const scenario of ['ico','mode','session','login','hidden']){
        const gate=deferred(),f=lookupFixture({fetcher:()=>gate.promise});const pending=f.lookup();
        if(scenario==='ico'){f.nodes.regIco.value='87654321';f.nodes.regIco.emit('input');}
        if(scenario==='mode')f.context.setRegistrationMode('user');
        if(scenario==='session')f.changeSession();
        if(scenario==='login')f.login();
        if(scenario==='hidden')f.nodes.registerForm.classList.contains=()=>true;
        gate.resolve(response(company()));await pending;
        assert.equal(f.nodes.regStreet.value,'',scenario);assert.equal(f.nodes.regName.value,'',scenario);assert.equal(f.nodes.regIco.dataset.companyVerifiedIco,undefined,scenario);
    }
});

test('manual edits made while a request is pending are never overwritten, even if restored to the same value',async()=>{
    const gate=deferred(),f=lookupFixture({street:'Ručně zadaná',fetcher:()=>gate.promise});const pending=f.lookup();
    f.nodes.regCity.value='Ručně měněné město';f.nodes.regCity.emit('input');
    f.nodes.regZip.value='touched';f.nodes.regZip.emit('input');f.nodes.regZip.value='';f.nodes.regZip.emit('input');
    gate.resolve(response(company()));await pending;
    assert.equal(f.nodes.regStreet.value,'Ručně zadaná');assert.equal(f.nodes.regCity.value,'Ručně měněné město');assert.equal(f.nodes.regZip.value,'');
    assert.equal(f.nodes.regStreetNumber.value,'12');
});

test('provider errors or mismatched ICO preserve manual contacts and show only public, recoverable feedback',async()=>{
    for(const status of [404,422,429,503]){
        const f=lookupFixture({street:'Ručně zadaná',fetcher:async()=>response({detail:'SECRET provider diagnostic'},status)});await f.lookup();
        assert.equal(f.nodes.regStreet.value,'Ručně zadaná');assert.equal(f.nodes.regIco.dataset.companyVerifiedIco,undefined);
        assert.match(f.nodes.regCompanyStatus.textContent,/ručně/);assert.doesNotMatch(f.nodes.regCompanyStatus.textContent,/SECRET/);assert.equal(f.nodes.regCompanyLookupBtn.disabled,false);
    }
    const f=lookupFixture({street:'Ručně zadaná',fetcher:async()=>response(company('87654321'))});await f.lookup();
    assert.equal(f.nodes.regStreet.value,'Ručně zadaná');assert.equal(f.nodes.regName.value,'');assert.equal(f.nodes.regIco.dataset.companyVerifiedIco,undefined);
});

test('latest retry wins even if an older response finishes JSON parsing later',async()=>{
    const json=deferred();let count=0;
    const f=lookupFixture({fetcher:async()=>++count===1?{ok:true,status:200,json:()=>json.promise}:response(company('12345678','Latest Fixture Company'))});
    const first=f.lookup();await new Promise(resolve=>setImmediate(resolve));
    await f.lookup();json.resolve(company('12345678','OLD COMPANY'));await first;
    assert.equal(f.nodes.regName.value,'Latest Fixture Company');
});
