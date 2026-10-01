// Browser session isolation on a fresh Chrome profile; synthetic network only.
const {test,before,after}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');const path=require('node:path');
const {chromium}=require('../e2e/node_modules/playwright');
const root=path.resolve(__dirname,'../..'),origin='http://127.0.0.1:19878';
let browser;
before(async()=>{browser=await chromium.launch({channel:process.env.TEST_BROWSER_CHANNEL||'chrome',headless:true});});
after(async()=>{await browser?.close();});
async function fixture(){
 const context=await browser.newContext();const requests=[];
 await context.route('**/*',async route=>{
  const req=route.request(),url=new URL(req.url());requests.push({path:url.pathname,method:req.method(),headers:req.headers()});
  if(url.origin!==origin)return route.abort();
  if(url.pathname==='/admin-session.js')return route.fulfill({contentType:'text/javascript',body:fs.readFileSync(path.join(root,'src/server/admin_session.js'))});
  if(url.pathname==='/fixture'||url.pathname==='/admin-login')return route.fulfill({contentType:'text/html',body:'<!doctype html><body><main id="private-data">'+(url.pathname==='/fixture'?'SYNTHETIC PRIVATE DATA':'Sign in')+'</main><script src="/admin-session.js"></script></body>'});
  return route.fulfill({json:{required:true,enrolled:true,verified:true,valid_until:Math.floor(Date.now()/1000)+900}});
 });
 await context.addInitScript(()=>{
  if(location.pathname!=='/fixture')return;
  sessionStorage.setItem('adminAccessToken','SESSION-A');
  for(const key of ['accessToken','currentUser','wasLoggedIn','adminAccessToken','adminRole'])localStorage.setItem(key,'OLD-PERSISTENT-CREDENTIAL');
  for(const key of ['accessToken','currentUser','wasLoggedIn'])sessionStorage.setItem(key,'OLD-PROFILE');
 });
 const page=await context.newPage();await page.goto(origin+'/fixture');
 return {context,page,requests};
}

test('legacy persisted credentials and profiles are removed without reusing them',async()=>{
 const f=await fixture();try{
 const state=await f.page.evaluate(()=>({local:Object.values(localStorage),session:{...sessionStorage},token:AdminBrowserSession.token()}));
 assert.deepEqual(state.local,[]);assert.deepEqual(state.session,{adminAccessToken:'SESSION-A'});assert.equal(state.token,'SESSION-A');
 }finally{await f.context.close();}
});

test('a delayed successful response from another session never reaches the caller',async()=>{
 const f=await fixture();try{
 const result=await f.page.evaluate(async()=>{
  let deliver;window.fetch=()=>new Promise(resolve=>{deliver=resolve;});
  const request=AdminBrowserSession.request('/private-data').then(r=>r.json()).then(data=>({data}),e=>({error:e.name}));
  AdminBrowserSession.set('SESSION-B','admin');
  deliver(new Response(JSON.stringify({email:'OLD-USER@example.invalid'}),{headers:{'Content-Type':'application/json'}}));
  return {result:await request,token:AdminBrowserSession.token()};
 });
 assert.deepEqual(result,{result:{error:'AbortError'},token:'SESSION-B'});
 }finally{await f.context.close();}
});

test('late 401 cannot sign out a newer verified session',async()=>{
 const f=await fixture();try{
 const result=await f.page.evaluate(async()=>{
  let deliver;window.fetch=()=>new Promise(resolve=>{deliver=resolve;});
  const request=AdminBrowserSession.request('/private-data').catch(e=>e.name);
  AdminBrowserSession.set('SESSION-B','admin');deliver(new Response('',{status:401}));
  return {result:await request,token:AdminBrowserSession.token()};
 });
 assert.deepEqual(result,{result:'AbortError',token:'SESSION-B'});
 }finally{await f.context.close();}
});

test('slow JSON and binary bodies are rejected even after headers have arrived',async()=>{
 const f=await fixture();try{
 for(const reader of ['json','text','blob','arrayBuffer','formData']){
  const result=await f.page.evaluate(async reader=>{
   AdminBrowserSession.set('SESSION-A','admin');let deliver;
   window.fetch=async()=>new Response(new ReadableStream({start(c){deliver=c;}}),{headers:{'Content-Type':reader==='formData'?'application/x-www-form-urlencoded':'application/json'}});
   const response=await AdminBrowserSession.request('/private-photo');
   const body=response[reader]().then(()=> 'LEAK',e=>e.name);
   AdminBrowserSession.set('SESSION-B','admin');
   deliver.enqueue(new TextEncoder().encode(reader==='formData'?'private=photo':'{"private":"photo"}'));deliver.close();
   return await body;
  },reader);
  assert.equal(result,'AbortError',reader);
 }
 }finally{await f.context.close();}
});

test('uploads use the current bearer only and no request may forward it to another origin',async()=>{
 const f=await fixture();try{
 const result=await f.page.evaluate(async()=>{
  const sent=[];window.fetch=async(url,options)=>{sent.push({url,authorization:options.headers.get('Authorization'),email:options.headers.get('X-User-Email'),file:options.body.get('photo'),credentials:options.credentials,redirect:options.redirect});return new Response('{}');};
  const form=new FormData();form.append('photo','SYNTHETIC PHOTO');
  await (await AdminBrowserSession.request('/photo',{method:'POST',body:form,headers:{Authorization:'Bearer OLD','X-User-Email':'old@example.invalid'}})).json();
  const rejected=[];for(const url of ['https://other.example.invalid/private','//other.example.invalid/private','javascript:alert(1)','https://user:pass@127.0.0.1/private']){
   try{await AdminBrowserSession.request(url);}catch{rejected.push(url);}
  }
  return {sent,rejected};
 });
 assert.equal(result.sent.length,1);assert.equal(result.sent[0].authorization,'Bearer SESSION-A');assert.equal(result.sent[0].email,null);assert.equal(result.sent[0].file,'SYNTHETIC PHOTO');assert.equal(result.sent[0].redirect,'error');assert.equal(result.rejected.length,4);
 }finally{await f.context.close();}
});

test('MFA status must explicitly require admin assurance with an unexpired deadline',async()=>{
 const f=await fixture();try{
 const result=await f.page.evaluate(async()=>{
  const results=[];
  for(const status of [{required:false,verified:true},{required:true,verified:false},{required:true,verified:true},{required:true,verified:true,valid_until:1}]){
   AdminBrowserSession.set('SESSION-A','admin');window.fetch=async()=>new Response(JSON.stringify(status));
   try{await AdminBrowserSession.verify();results.push('ACCEPTED');}catch(e){results.push([e.name,AdminBrowserSession.token()]);}
  }
  return results;
 });
 assert.deepEqual(result,Array(4).fill(['AbortError',null]));
 }finally{await f.context.close();}
});

test('logout clears credentials, previews and visible data immediately while offline',async()=>{
 const f=await fixture();try{
 await f.page.evaluate(()=>{
  window.fetch=()=>new Promise(()=>{});
  AdminBrowserSession.protect(()=>sessionStorage.setItem('cleanup-completed','yes'));
  void AdminBrowserSession.logout();
 });
 await f.page.waitForURL('**/admin-login?next=**');
 // Cleanup must precede navigation even when server logout never responds.
 assert.equal(await f.page.evaluate(()=>sessionStorage.getItem('cleanup-completed')),'yes');
 assert.equal(await f.page.evaluate(()=>AdminBrowserSession.token()),null);
 assert.ok(!(await f.page.locator('body').textContent()).includes('SYNTHETIC PRIVATE DATA'));
 assert.ok(f.requests.every(r=>r.path!=='/private-data'));
 }finally{await f.context.close();}
});

test('sign-out in one tab clears another tab without copying identity or credentials',async()=>{
 const f=await fixture();try{
 const other=await f.context.newPage();await other.goto(origin+'/fixture');
 await f.page.evaluate(()=>AdminBrowserSession.end('logout'));
 await other.waitForFunction(()=>AdminBrowserSession.token()===null);
 const storage=await other.evaluate(()=>({session:{...sessionStorage},signal:localStorage.getItem('sprava_vozidel_admin_session_changed')}));
 assert.deepEqual(storage.session,{});assert.match(storage.signal,/^[0-9a-f-]{36}$/);
 }finally{await f.context.close();}
});

test('expiration removes a protected view and cancels its outstanding work',async()=>{
 const f=await fixture();try{
 await f.page.evaluate(async()=>{
  AdminBrowserSession.protect(()=>sessionStorage.setItem('expiry-cleanup','yes'));
  window.fetch=async()=>new Response(JSON.stringify({required:true,verified:true,valid_until:(Date.now()+80)/1000}));
  await AdminBrowserSession.verify();
 });
 await f.page.waitForURL('**/admin-login?next=**');
 assert.equal(await f.page.evaluate(()=>sessionStorage.getItem('expiry-cleanup')),'yes');
 }finally{await f.context.close();}
});

test('history restoration requires verification instead of exposing the cached view',async()=>{
 const f=await fixture();try{
 await f.page.evaluate(()=>{
  AdminBrowserSession.protect(()=>sessionStorage.setItem('history-cleanup','yes'));
  dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}));
 });
 await f.page.waitForURL('**/admin-login?next=**');
 assert.equal(await f.page.evaluate(()=>sessionStorage.getItem('history-cleanup')),'yes');
 }finally{await f.context.close();}
});

test('a timeout interrupts body consumption while leaving a valid session usable',async()=>{
 const f=await fixture();try{
 const result=await f.page.evaluate(async()=>{
  let deliver;
  window.fetch=async()=>new Response(new ReadableStream({start(c){deliver=c;}}));
  const response=await AdminBrowserSession.request('/slow',{timeoutMs:15});
  const body=response.text().then(()=> 'LEAK',e=>e.name);
  await new Promise(resolve=>setTimeout(resolve,35));
  deliver.enqueue(new TextEncoder().encode('SENSITIVE'));deliver.close();
  return {result:await body,token:AdminBrowserSession.token()};
 });
 assert.deepEqual(result,{result:'AbortError',token:'SESSION-A'});
 }finally{await f.context.close();}
});
