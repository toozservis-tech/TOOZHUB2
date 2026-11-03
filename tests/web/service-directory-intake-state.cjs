const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
class Element {
 constructor(tag){this.tagName=tag;this.children=[];this.parentElement=null;this.dataset={};this.style={};this.listeners={};this._text='';this.value='';this.hidden=false;}
 get isConnected(){return this.root===true||Boolean(this.parentElement?.isConnected);}
 get lastChild(){return this.children.at(-1);}
 append(...els){for(let el of els){if(typeof el==='string'){const t=new Element('#text');t._text=el;el=t;}el.remove();el.parentElement=this;this.children.push(el);}}
 prepend(...els){const old=this.children.splice(0);this.append(...els,...old);}
 before(el){const p=this.parentElement;if(!p)return;el.remove();el.parentElement=p;p.children.splice(p.children.indexOf(this),0,el);}
 remove(){if(this.parentElement){const p=this.parentElement;p.children=p.children.filter(c=>c!==this);this.parentElement=null;}}
 replaceChildren(...els){for(const child of this.children)child.parentElement=null;this.children=[];this._text='';this.append(...els);}
 set textContent(value){this.replaceChildren();this._text=String(value);}
 get textContent(){return this._text+this.children.map(c=>c.textContent).join('');}
 setAttribute(key,value){this[key]=String(value);}
 addEventListener(type,fn){this.listeners[type]=fn;}
 reportValidity(){return !this.required||Boolean(this.value);}
 querySelector(selector){return this.querySelectorAll(selector)[0]||null;}
 querySelectorAll(selector){const match=el=>selector[0]==='#'?el.id===selector.slice(1):selector==='[data-service-search]'?el.dataset.serviceSearch!==undefined:el.tagName===selector;return this.children.flatMap(c=>[...(match(c)?[c]:[]),...c.querySelectorAll(selector)]);}
 closest(selector){return this.tagName===selector?this:this.parentElement?.closest(selector)||null;}
}
const document={body:new Element('body'),createElement:tag=>new Element(tag),createTextNode:text=>{const el=new Element('#text');el.textContent=text;return el;},querySelectorAll:selector=>document.body.querySelectorAll(selector)};document.body.root=true;
let generation=1,homeResolve,requests=[],mode='user';const events={};
const snapshot=()=>({generation}),assertCurrent=value=>{if(value.generation!==generation)throw Object.assign(new Error('stale'),{name:'AbortError'});};
let pendingHome=true;
async function request(path,method='GET',payload){requests.push({path,method,payload});
 if(path==='/api/v1/services/home-garage'&&method==='GET')return pendingHome?new Promise(resolve=>homeResolve=resolve):{apple_place_id:null};
 if(path.startsWith('/api/v1/services/map-search?'))return {notice:'Testovací katalog',items:[{id:'new-place',name:'Nový servis',address:'Testovací 1',navigation_url:'https://maps.apple.com/?daddr=49,16'}]};
 if(path==='/api/v1/services/home-garage'&&method==='PUT')return {apple_place_id:payload.apple_place_id};
 if(path==='/api/v1/services/workspace/customers')return [];
 if(path==='/api/v1/services/workspace/pending-vehicles')return {vehicle_id:requests.filter(r=>r.path===path&&r.method==='POST').length+100,message:'Vozidlo připraveno'};
 throw new Error('Unexpected request '+path);
}
function action(label,fn){const el=new Element('button');el.textContent=label;el.click=fn;return el;}
function input(label,id,type='text',value=''){const wrap=new Element('label');wrap._text=label;const el=new Element('input');el.id=id;el.type=type;el.value=value;wrap.append(el);return wrap;}
function panel(){document.body.querySelector('#panel')?.remove();const dialog=new Element('dialog');dialog.id='panel';dialog.close=()=>dialog.remove();const body=new Element('main');dialog.append(body);document.body.append(dialog);return body;}
const context={document,CustomerWeb:true,CustomerFeatures:{ui:{request,action,input,panel,h:String,showError:()=>{},confirmAction:async()=>true}},AdminBrowserSession:{snapshot,assertCurrent},isServiceWorkspaceRole:()=>mode==='service',addEventListener:(name,fn)=>events[name]=fn,URL,WeakMap,Map,console};context.window=context;
vm.runInNewContext(fs.readFileSync('web/service-features.js','utf8'),context);
const flush=()=>new Promise(resolve=>setImmediate(resolve));
const button=(scope,text)=>scope.querySelectorAll('button').find(el=>el.textContent===text);
(async()=>{
 const container=new Element('div');document.body.append(container);const card=new Element('article');card.id='service-directory-card-7';container.append(card);
 context.ServiceFeatures.directoryLoaded(container,{services:[{id:7,name:'Registrovaný servis',city:'Praha'}]});
 const tools=document.body.querySelector('[data-service-search]');assert.ok(tools);assert.match(card.textContent,/Registrován/);
 const filter=tools.querySelector('#serviceDirectorySearch');filter.value='cizí';filter.listeners.input();assert.equal(card.style.display,'none');filter.value='praha';filter.listeners.input();assert.equal(card.style.display,'');
 tools.querySelector('#serviceMapCity').value='Praha';await button(tools,'Vyhledat v mapách').click();
 await button(tools,'Nastavit jako domovský servis').click();assert.match(tools.textContent,/Nový servis/);
 homeResolve({apple_place_id:'old-place',place:{name:'Stará odpověď'}});await flush();assert.equal(tools.textContent.includes('Stará odpověď'),false,'late initial home read must not overwrite save');
 container.replaceChildren();const newCard=new Element('article');newCard.id='service-directory-card-7';container.append(newCard);context.ServiceFeatures.directoryLoaded(container,{services:[{id:7,name:'Registrovaný servis',city:'Praha'}]});
 assert.equal(document.body.querySelectorAll('[data-service-search]').length,1);assert.equal(tools.querySelector('#serviceDirectorySearch').value,'praha','directory redraw retains in-flight search UI');
 const oldSave=button(tools,'Nastavit jako domovský servis');generation++;events['admin-session-ended']();const before=requests.length;await oldSave.click();assert.equal(requests.length,before,'detached stale-account action cannot write another account');
 mode='service';pendingHome=false;await context.ServiceFeatures.intake();let form=document.body.querySelector('#panel');
 assert.equal(form.querySelector('#serviceIntakeMode').value,'invite');form.querySelector('#serviceIntakeEmail').value='unregistered@example.test';form.querySelector('#serviceIntakeOwnerName').value='Testovací Majitel';form.querySelector('#serviceIntake-nickname').value='První auto';form.querySelector('#serviceIntake-vin').value='TMB12345678901234';await button(form,'Uložit vozidlo').click();
 assert.match(form.textContent,/udělení souhlasu/);assert.ok(button(form,'Zahájit zakázku'));await button(form,'Přidat další vozidlo stejnému zákazníkovi').click();
 assert.equal(form.querySelector('#serviceIntakeEmail').value,'unregistered@example.test');assert.equal(form.querySelector('#serviceIntakeOwnerName').value,'Testovací Majitel');assert.equal(form.querySelector('#serviceIntake-nickname').value,'');assert.equal(form.querySelector('#serviceIntake-vin').value,'');
 form.querySelector('#serviceIntake-nickname').value='Druhé auto';form.querySelector('#serviceIntake-vin').value='TMB12345678901235';await button(form,'Uložit vozidlo').click();
 const posted=requests.filter(r=>r.path==='/api/v1/services/workspace/pending-vehicles');assert.equal(posted.length,2);assert.equal(posted[0].payload.invite_email,posted[1].payload.invite_email);assert.notEqual(posted[0].payload.vehicle.vin,posted[1].payload.vehicle.vin);assert.equal(requests.some(r=>/vehicle-access|invitations\/accept/.test(r.path)),false,'bookmark and intake do not submit ownership consent');
 console.log('Service directory/intake state: 20 DOM/account/persistence checks passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
