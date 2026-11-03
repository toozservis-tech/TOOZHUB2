'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const {repairPhotoMoment,repairPhotoMetadataSection,createRepairPhotoPreview,downloadRepairReport}=require('../../web/customer-features.js');
class Node {
 constructor(tag){this.tag=tag;this.children=[];this.attributes={};this.style={};this.listeners=new Map();this.parent=null;this.connected=true;this._text='';}
 set innerHTML(_){throw Error('Private repair metadata must remain literal text');}
 set textContent(value){this._text=String(value);this.children=[];}
 get textContent(){return this._text+this.children.map(x=>x.textContent).join('');}
 get isConnected(){return this.connected&&(!this.parent||this.parent.isConnected);}
 append(...nodes){for(const n of nodes){n.parent=this;this.children.push(n);}}
 setAttribute(k,v){this.attributes[k]=String(v);}
 removeAttribute(k){delete this.attributes[k];}
 getAttribute(k){return this.attributes[k]??null;}
 set src(v){this.setAttribute('src',v);}
 get src(){return this.getAttribute('src');}
 addEventListener(type,fn){const a=this.listeners.get(type)||new Set();a.add(fn);this.listeners.set(type,a);}
 removeEventListener(type,fn){this.listeners.get(type)?.delete(fn);}
 emit(type){for(const fn of [...(this.listeners.get(type)||[])])fn();}
 closest(tag){for(let n=this;n;n=n.parent)if(n.tag===tag)return n;return null;}
 remove(){if(this.parent)this.parent.children=this.parent.children.filter(n=>n!==this);this.parent=null;this.connected=false;}
 click(){this.emit('click');}
}
const doc=()=>({body:new Node('body'),createElement:tag=>new Node(tag)});
const descendants=n=>[n,...n.children.flatMap(descendants)];
const find=(n,key,value)=>descendants(n).find(x=>x.getAttribute(key)===value);
function deferred(){let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};}
const tick=()=>new Promise(r=>setImmediate(r));

test('repair metadata retains distinct UTC captured/uploaded instants and actual literal source/author/hash',()=>{
 const photo={id:1,source:'library',author_name:'PARITY <img src=x onerror=blocked()>',captured_at:'2026-11-03T06:00:00',uploaded_at:'2026-11-03T06:40:21.673808',sha256:'a'.repeat(64)};
 const view=repairPhotoMetadataSection(doc(),photo);
 assert.equal(find(view,'data-repair-photo-field','source').children[1].textContent,'Fotogalerie');
 assert.equal(find(view,'data-repair-photo-field','author_name').children[1].textContent,photo.author_name);
 assert.equal(find(view,'data-repair-photo-field','captured_at').children[1].children[0].getAttribute('datetime'),'2026-11-03T06:00:00.000Z');
 assert.equal(find(view,'data-repair-photo-field','uploaded_at').children[1].children[0].getAttribute('datetime'),'2026-11-03T06:40:21.673Z');
 assert.equal(find(view,'data-repair-photo-field','sha256').textContent,photo.sha256);
 assert.equal(descendants(view).filter(n=>['img','script','input'].includes(n.tag)).length,0);
});
test('repair metadata uses supplied camera/author-id data and never fabricates absent optional timestamps',()=>{
 const view=repairPhotoMetadataSection(doc(),{id:2,source:'camera',author_id:31,captured_at:null,uploaded_at:'invalid'});
 assert.equal(find(view,'data-repair-photo-field','source').children[1].textContent,'Fotoaparát');
 assert.equal(find(view,'data-repair-photo-field','author_name').children[1].textContent,'Účet 31');
 assert.equal(find(view,'data-repair-photo-field','captured_at'),undefined);assert.equal(find(view,'data-repair-photo-field','uploaded_at'),undefined);assert.equal(find(view,'data-repair-photo-field','sha256'),undefined);
});
test('repair timestamp parsing preserves explicit offsets and rejects invalid values',()=>{
 assert.equal(repairPhotoMoment('2026-11-03T07:00:00+01:00').iso,'2026-11-03T06:00:00.000Z');
 for(const value of [null,undefined,'','bad',14])assert.equal(repairPhotoMoment(value),null);
});

function fixture({phase,ok=true,mime='image/jpeg',hash,connected=true,large=false}={}){
 const document=doc(),dialog=new Node('dialog'),host=new Node('article');document.body.append(dialog);dialog.append(host);host.connected=connected;if(!connected)dialog.connected=false;
 const bytes=Buffer.from('unit raster bytes (decode event is simulated only in units)'),digest=crypto.createHash('sha256').update(bytes).digest('hex'),blob=new Blob([bytes],{type:mime});
 let generation=1,observer,requests=0,signal;const gate=deferred(),created=[],revoked=[],events=new Node('window');
 const env={document,AbortController,crypto:crypto.webcrypto,URL:{createObjectURL(value){created.push(value);return 'blob:unit-private-'+created.length;},revokeObjectURL(value){revoked.push(value);}},MutationObserver:class {constructor(fn){this.callback=fn;observer=this;this.disconnected=false;}observe(){}disconnect(){this.disconnected=true;}},addEventListener:(...a)=>events.addEventListener(...a),removeEventListener:(...a)=>events.removeEventListener(...a)};
 const photo={id:1,sha256:hash||digest,size_bytes:large?13*1024*1024:blob.size};
 const response={ok,headers:new Headers({'content-type':mime}),blob:async()=>phase==='body'?gate.promise:large?{size:13*1024*1024,type:mime}:blob};
 const session={snapshot:()=>({generation}),assertCurrent(scope){if(scope.generation!==generation)throw new DOMException('Changed account','AbortError');},async request(path,init){assert.equal(path,'/api/v1/repair-documentation/photos/1/file');requests++;signal=init.signal;return phase==='headers'?gate.promise:response;}};
 const preview=createRepairPhotoPreview(env,session,photo,host);
 return {preview,photo,host,dialog,events,created,revoked,observer:()=>observer,requests:()=>requests,signal:()=>signal,resolve(){gate.resolve(phase==='headers'?response:blob);},switchAccount(){generation++;},decode(width=640,height=480){preview.image.naturalWidth=width;preview.image.naturalHeight=height;preview.image.onload?.();},state:()=>preview.element.getAttribute('data-preview-state')};
}
test('private preview verifies protected bytes before exposing one blob image and decoded dimensions',async()=>{
 const f=fixture();await f.preview.ready;assert.equal(f.requests(),1);assert.equal(f.created.length,1);assert.equal(f.preview.image.src,'blob:unit-private-1');assert.equal(f.state(),'loading');
 f.decode();assert.equal(f.state(),'loaded');assert.equal(f.preview.element.getAttribute('data-natural-width'),'640');assert.equal(f.preview.element.getAttribute('data-verified-sha256'),f.photo.sha256);f.preview.cleanup();
});
test('account switch after private bytes arrive but before image decode revokes the URL without publishing dimensions',async()=>{
 const f=fixture();await f.preview.ready;f.switchAccount();f.decode();assert.equal(f.state(),'disposed');assert.equal(f.preview.image.src,null);assert.deepEqual(f.revoked,['blob:unit-private-1']);assert.equal(f.preview.element.getAttribute('data-natural-width'),null);
});
for(const phase of ['headers','body'])for(const event of ['logout','account-change'])test('delayed '+phase+' after '+event+' cannot create or reveal a private image URL',async()=>{
 const f=fixture({phase});await tick();f.switchAccount();if(event==='logout')f.events.emit('admin-session-ended');f.resolve();await f.preview.ready;
 assert.equal(f.created.length,0);assert.equal(f.preview.image.src,null);assert.equal(f.state(),'disposed');assert.equal(f.signal().aborted,true);assert.equal(f.observer().disconnected,true);
});
for(const event of ['close','remove','logout','decode-error'])test('loaded private URL is revoked exactly once on '+event,async()=>{
 const f=fixture();await f.preview.ready;f.decode();
 if(event==='close')f.dialog.emit('close');else if(event==='remove'){f.host.remove();f.observer().callback();}else if(event==='logout')f.events.emit('admin-session-ended');else f.preview.image.onerror();
 assert.deepEqual(f.revoked,['blob:unit-private-1']);assert.equal(f.preview.image.src,null);f.preview.cleanup();assert.deepEqual(f.revoked,['blob:unit-private-1']);assert.equal(f.observer().disconnected,true);
});
for(const [label,options]of [['SVG',{mime:'image/svg+xml'}],['hash mismatch',{hash:'0'.repeat(64)}],['oversized raster',{large:true}],['denied response',{ok:false}]])test('private preview rejects '+label+' before creating a URL',async()=>{
 const f=fixture(options);await f.preview.ready;assert.equal(f.created.length,0);assert.equal(f.state(),'error');assert.equal(f.requests(),1);f.preview.cleanup();
});
test('detached screen performs no private request',async()=>{
 const f=fixture({connected:false});await f.preview.ready;assert.equal(f.requests(),0);assert.equal(f.created.length,0);assert.equal(f.state(),'disposed');
});
test('decode failure does not cause an automatic image request loop',async()=>{
 const f=fixture();await f.preview.ready;f.decode(0,0);await tick();assert.equal(f.state(),'error');assert.equal(f.requests(),1);assert.equal(f.created.length,1);assert.equal(f.revoked.length,1);
 const retry=f.preview.element.children[2];retry.emit('click');await f.preview.ready;assert.equal(f.requests(),2);f.preview.cleanup();
});

function reportFixture({phase,mime='application/pdf',payload='%PDF-1.4\nunit report\n%%EOF',ok=true}={}){
 const document=doc(),dialog=new Node('dialog'),host=new Node('section'),events=new Node('window');document.body.append(dialog);dialog.append(host);
 const gate=deferred(),blob=new Blob([payload],{type:mime}),created=[],revoked=[],clicked=[];let generation=1,observer,signal,timer;
 const originalCreate=document.createElement;document.createElement=tag=>{const node=originalCreate(tag);if(tag==='a')node.addEventListener('click',()=>clicked.push({href:node.href,name:node.download}));return node;};
 const env={document,AbortController,URL:{createObjectURL(value){created.push(value);return 'blob:unit-report';},revokeObjectURL(value){revoked.push(value);}},setTimeout(fn){timer=fn;return 1;},clearTimeout(){timer=null;},MutationObserver:class{constructor(fn){this.callback=fn;observer=this;}observe(){}disconnect(){this.disconnected=true;}},addEventListener:(...a)=>events.addEventListener(...a),removeEventListener:(...a)=>events.removeEventListener(...a)};
 const response={ok,headers:new Headers({'content-type':mime}),blob:async()=>phase==='body'?gate.promise:blob};
 const session={snapshot:()=>({generation}),assertCurrent(scope){if(scope.generation!==generation)throw new DOMException('Changed account','AbortError');},async request(path,init){assert.equal(path,'/api/v1/repair-documentation/sessions/17/report.pdf');signal=init.signal;return phase==='headers'?gate.promise:response;}};
 return {env,session,host,dialog,events,created,revoked,clicked,run:()=>downloadRepairReport(env,session,17,host),resolve:()=>gate.resolve(phase==='headers'?response:blob),switchAccount(){generation++;},remove(){host.remove();observer.callback();},finish:()=>timer?.(),signal:()=>signal,observer:()=>observer};
}
test('repair report uses its private session route and downloads validated PDF bytes with bounded URL cleanup',async()=>{
 const f=reportFixture();await f.run();assert.equal(f.clicked.length,1);assert.deepEqual(f.clicked[0],{href:'blob:unit-report',name:'fotodokumentace-opravy.pdf'});assert.equal(f.created.length,1);assert.equal(f.revoked.length,0);f.finish();assert.deepEqual(f.revoked,['blob:unit-report']);assert.equal(f.observer().disconnected,true);
});
for(const phase of ['headers','body'])for(const event of ['logout','account-change'])test('delayed PDF '+phase+' after '+event+' cannot download another account private report',async()=>{
 const f=reportFixture({phase}),pending=f.run();await tick();f.switchAccount();if(event==='logout')f.events.emit('admin-session-ended');f.resolve();await assert.rejects(pending,{name:'AbortError'});assert.equal(f.clicked.length,0);assert.equal(f.created.length,0);assert.equal(f.signal().aborted,true);assert.equal(f.observer().disconnected,true);
});
for(const event of ['close','remove','logout'])test('repair PDF URL is revoked once on '+event,async()=>{
 const f=reportFixture();await f.run();if(event==='close')f.dialog.emit('close');else if(event==='remove')f.remove();else f.events.emit('admin-session-ended');f.finish();assert.deepEqual(f.revoked,['blob:unit-report']);assert.equal(f.observer().disconnected,true);
});
for(const [label,options]of [['denied response',{ok:false}],['HTML response',{mime:'text/html'}],['invalid PDF bytes',{payload:'private error page'}]])test('repair report rejects '+label+' before creating a download',async()=>{
 const f=reportFixture(options);await assert.rejects(f.run());assert.equal(f.clicked.length,0);assert.equal(f.created.length,0);assert.equal(f.observer().disconnected,true);
});
