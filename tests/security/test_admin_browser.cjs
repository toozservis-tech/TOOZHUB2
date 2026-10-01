// Isolated real-browser regression: all requests are intercepted; no live accounts,
// no emails, no transactions, and no access to the user's browser profile.
// npm ci --prefix tests/e2e --ignore-scripts
// node --test tests/security/test_admin_browser.cjs
const {test, before, after}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {execFileSync}=require('node:child_process');
const {chromium}=require('../e2e/node_modules/playwright');
const root=path.resolve(__dirname,'../..');
const csp=execFileSync(process.env.TEST_PYTHON || path.resolve(root,'../cloud-venv/bin/python'),['-c','from src.core.browser_policy import ADMIN_CONTENT_SECURITY_POLICY; print(ADMIN_CONTENT_SECURITY_POLICY)'],{cwd:root,encoding:'utf8'}).trim();
const origin='http://127.0.0.1:19876';
let browser;
before(async()=>{browser=await chromium.launch({channel:process.env.TEST_BROWSER_CHANNEL || 'chrome',headless:true});});
after(async()=>{await browser?.close();});
async function fixture({policy=true,login=false}={}) {
 const context=await browser.newContext();
 const page=await context.newPage();page.setDefaultTimeout(5000);
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 const requests=[];
 await context.route('**/*',async route=>{
  const req=route.request(),url=new URL(req.url()); requests.push({path:url.pathname,method:req.method()});
  if(url.origin!==origin) throw Error('Unexpected external request: '+url.origin);
  const files={'/web_admin/':'web_admin/index.html','/admin-login':'src/server/admin_login.html','/admin-login.js':'src/server/admin_login.js','/admin-session.js':'src/server/admin_session.js'};
  let file=files[url.pathname];
  if(['/admin.js','/workspace.js','/operator-panel.js','/admin.css','/workspace.css'].some(x=>url.pathname==='/web_admin'+x))file=url.pathname.slice(1);
  if(file) return route.fulfill({status:200,body:fs.readFileSync(path.join(root,file)),contentType:file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'text/html',headers:policy?{'Content-Security-Policy':csp}:{}});
  const defaults={
   '/user/security/admin-status':{required:true,enrolled:true,verified:true,valid_until:Math.floor(Date.now()/1000)+900},
   '/user/login':{access_token:'synthetic-test-session'},
   '/user/me':{id:1,email:'synthetic-admin@example.invalid',role:'admin'},
   '/admin-api/users':[], '/admin-api/overview':{}, '/admin-api/audit':{logs:[]},
  };
  return route.fulfill({status:200,json:defaults[url.pathname] || {}});
 });
 if(!login) await page.addInitScript(()=>sessionStorage.setItem('adminAccessToken','synthetic-test-session'));
 await page.goto(origin+(login?'/admin-login':'/web_admin/'));
 if(!login) await page.waitForFunction(()=>!document.getElementById('dashboard-screen').classList.contains('hidden') && document.getElementById('recent-activity').textContent.includes('Žádná nedávná aktivita'));
 return {page,context,errors,requests};
}
const poison=`Zkušební \"'><img src=x onerror="window.__xss=1"><svg onload="window.__xss=2"></svg> & &#39; \\`;
async function assertInert(page) {
 assert.equal(await page.evaluate(()=>window.__xss),undefined);
 assert.equal(await page.locator('img[onerror],svg[onload],[onmouseover],[onfocus],[autofocus]').count(),0);
}

test('stored text stays inert without CSP in every CRUD view, audit and settings', async()=>{
 const f=await fixture({policy:false});const {page}=f;
 try {
 await page.evaluate(async p=>{
  window.attack=p;
  const user={id:11,name:p,email:p,role:'user',city:p,phone:p,last_location:p,tenant_id:11,license_plan:'free'};
  const vehicle={id:21,nickname:p,brand:p,model:p,owner_name:p,plate:p,vin:p};
  const service={id:31,name:p,email:p,city:p,phone:p,ico:p};
  const record={id:41,description:p,user_name:p,vehicle_nickname:p,category:p,mileage:123,price:99};
  apiRequest=async(method,url)=>{
   if(url.startsWith('/admin-api/audit'))return {logs:[{actor_email:p,action:p,entity_type:p,entity_id:p,source_project:p,details:p}]};
   if(url.startsWith('/admin-api/records'))return [record];
   if(url.startsWith('/admin-api/users'))return [user];
   if(url.startsWith('/admin-api/vehicles'))return [vehicle];
   if(url.startsWith('/admin-api/services'))return [service];
   if(url.startsWith('/admin-api/service-registration-requests'))return [{id:51,service_name:p,email:p,registration_purpose:p}];
   return {};
  };
  await loadUsers(); await loadVehicles(); await loadServices();await loadRecords(); await loadAuditLog();await loadRecentActivity();
  await loadRecordFormData(21);
 },poison);
 for(const view of ['grid','list','compact']) {
  await page.evaluate(v=>{adminViewState.users=v;renderUsersList();},view);
  assert.ok((await page.locator('#users-cards-container').textContent()).includes(poison));await assertInert(page);
 }
 for(const id of ['vehicles-cards-container','services-cards-container','records-cards-container','audit-log-list','recent-activity']) {
  assert.ok((await page.locator('#'+id).textContent()).includes(poison),id);
 }
 // A saved setting containing quotes cannot create a new element/attribute.
 await page.evaluate(p=>{allSettings={general:{app_name:{value:p,description:p}}};renderSettingsCategory('general');},poison);
 assert.equal(await page.locator('#setting-general-app_name').inputValue(),poison);
 await assertInert(page);
 assert.deepEqual(f.errors,[]);
 } finally {await f.context.close();}
});

test('malicious quotes remain original arguments when edit/delete buttons are clicked',async()=>{
 const f=await fixture();const {page}=f;
 try {
 await page.evaluate(async p=>{
  fetchAllList=async path=>path.includes('vehicles')?[{id:21,nickname:p}]:path.includes('services')?[{id:31,name:p}]:[{id:11,email:p,name:p}];
  loadServiceRegistrationRequests=()=>{};await loadUsers();await loadVehicles();await loadServices();
  window.calls=[];
  deleteUser=(event,...a)=>window.calls.push(['user',...a]);
  deleteVehicle=(...a)=>window.calls.push(['vehicle',...a]);
  deleteService=(...a)=>window.calls.push(['service',...a]);
  openUserDetailModal=(...a)=>window.calls.push(['unexpected-card-click',...a]);
 },poison);
 // Hidden sections are intentionally dispatched to test each delegated handler.
 for(const name of ['deleteUser','deleteVehicle','deleteService'])await page.locator(`[data-admin-click="${name}"]`).first().dispatchEvent('click');
 assert.deepEqual(await page.evaluate(()=>window.calls),[['user',11,poison],['vehicle',21,poison],['service',31,poison]]);
 await assertInert(page);assert.deepEqual(f.errors,[]);
 }finally{await f.context.close();}
});

test('user detail, quoted reminder and map links cannot escape their data context',async()=>{
 const f=await fixture({policy:false});const {page}=f;
 try {
 await page.evaluate(p=>{
  userDetailData={user:{id:11,name:p,email:p,role:'user'},stats:{},meta:{ip_history:[{ip_address:p,maps_url:'javascript:window.__xss=3'},{ip_address:p,maps_url:'data:text/html,x',latitude:1,longitude:2}]},panels:{vehicles:[{id:21,nickname:p,plate:p}],reminders:[{id:51,text:p,vehicle_label:p}],reservations:[{id:61,notes:p,vehicle_label:p}],records:[{id:71,description:p}]}};
  window.calls=[];quickEditReminderFromUserDetail=(id,label)=>window.calls.push([id,decodeURIComponent(label)]);
 },poison);
 for(const section of ['vehicles','reminders','reservations','records']) {
  await page.evaluate(s=>{userDetailActivePanel=s;renderUserDetailModal();},section);
  if(section==='reminders') await page.locator('[data-admin-click="quickEditReminderFromUserDetail"]').dispatchEvent('click');
  await assertInert(page);
 }
 assert.equal(await page.locator('a[href^="javascript:"],a[href^="data:"]').count(),0);
 assert.deepEqual(await page.evaluate(()=>window.calls),[[51,poison]]);
 assert.deepEqual(f.errors,[]);
 }finally{await f.context.close();}
});

test('generic table raw fields and server errors display as text',async()=>{
 const f=await fixture({policy:false});const {page}=f;
 try {
 await page.evaluate(async p=>{
  renderControlCenterTable('cc-security-table',[{key:'raw',label:p}],[{raw:p}]);
  apiRequest=async()=>{throw new Error(p);};fetchAllList=apiRequest;
  await loadUsers();await loadVehicles();await loadRecords();await loadAuditLog();await loadDbInfo();
 },poison);
 await assertInert(page);assert.deepEqual(f.errors,[]);
 }finally{await f.context.close();}
});

test('every static dashboard action dispatches without inline code under strict CSP',async()=>{
 const f=await fixture();const {page}=f;
 try {
 const result=await page.evaluate(()=>{
  const nodes=[...document.querySelectorAll('[data-admin-click], [data-admin-submit]')];
  const original={},called=[],missing=[];
  for(const node of nodes){const name=node.dataset.adminClick||node.dataset.adminSubmit;if(!(name in original)){original[name]=window[name];if(typeof window[name]!=='function')missing.push(name);window[name]=(...args)=>called.push({name,args:args.map(v=>v instanceof Event?'event':v)});}}
  for(const node of nodes){node.disabled=false;node.dispatchEvent(new Event(node.dataset.adminSubmit?'submit':'click',{bubbles:true,cancelable:true}));}
  Object.assign(window,original);
  return {expected:nodes.map(n=>n.dataset.adminClick||n.dataset.adminSubmit),actual:called.map(c=>c.name),missing};
 });
 assert.deepEqual(result.missing,[]);
 assert.deepEqual(result.actual,result.expected);
 assert.ok(result.actual.length>90);
 assert.deepEqual(f.errors,[]);
 }finally{await f.context.close();}
});

test('strict CSP rejects injected inline script and event handlers while sign-in works',async()=>{
 const f=await fixture({login:true});const {page}=f;
 try {
 await page.evaluate(()=>{let s=document.createElement('script');s.textContent='window.__xss=5';document.body.append(s);let b=document.createElement('button');b.setAttribute('onclick','window.__xss=6');b.click();});
 assert.equal(await page.evaluate(()=>window.__xss),undefined);
 await page.locator('#email').fill('synthetic-admin@example.invalid');await page.locator('#password').fill('fixture-password');
 await page.locator('#submit').click();
 await page.waitForURL(origin+'/web_admin/');
 await page.waitForFunction(()=>!document.getElementById('dashboard-screen').classList.contains('hidden'));
 assert.ok(f.requests.some(x=>x.path==='/user/login'&&x.method==='POST'));
 assert.deepEqual(f.errors,[]);
 }finally{await f.context.close();}
});

test('navigation, record edit and cancellation of deletion remain functional with CSP',async()=>{
 const f=await fixture();const {page}=f;
 try {
 await page.route(origin+'/admin-api/vehicles?*',route=>route.fulfill({json:[{id:21,nickname:"Rodinné auto O'Neill",brand:'Škoda',model:'Octavia'}]}));
 await page.route(origin+'/admin-api/vehicles/21',route=>route.fulfill({json:{id:21,nickname:"Rodinné auto O'Neill",brand:'Škoda',model:'Octavia'}}));
 await page.locator('.nav-item[data-section="vehicles"]').click();
 await page.locator('[data-admin-click="editVehicle"]').click();
 await page.locator('#vehicle-nickname').waitFor({state:'visible'});
 assert.equal(await page.locator('#vehicle-nickname').inputValue(),"Rodinné auto O'Neill");
 await page.locator('#vehicle-modal [data-admin-click="closeVehicleModal"]').last().click();
 page.once('dialog',dialog=>dialog.accept());
 await page.locator('[data-admin-click="deleteVehicle"]').click();
 await page.locator('#delete-reason').waitFor({state:'visible'});
 await page.locator('#delete-cancel').click();
 assert.equal(f.requests.filter(r=>r.method==='DELETE').length,0);
 await page.locator('.nav-item[data-section="users"]').click();
 assert.equal(await page.locator('#section-users').isVisible(),true);
 assert.deepEqual(f.errors,[]);
 }finally{await f.context.close();}
});

test('deletion confirmed after session change is cancelled before any mutation',async()=>{
 const f=await fixture();try{
 const result=await f.page.evaluate(async()=>{
  let confirm;
  requestDeletionConfirmation=()=>new Promise(resolve=>{confirm=resolve;});
  const operation=apiRequest('DELETE','/admin-api/users/11').then(()=> 'DELETED',e=>e.name);
  AdminBrowserSession.set('new-synthetic-session','admin');
  confirm({reason:'Synthetic confirmation'});
  return await operation;
 });
 assert.equal(result,'AbortError');assert.equal(f.requests.filter(r=>r.method==='DELETE').length,0);
 }finally{await f.context.close();}
});

test('admin sign-in rejects a forged ordinary-user verification response',async()=>{
 const f=await fixture({login:true});try{
 await f.page.route('**/user/security/admin-status',r=>r.fulfill({json:{required:false,verified:true,valid_until:Math.floor(Date.now()/1000)+900}}));
 await f.page.locator('#email').fill('admin@example.invalid');await f.page.locator('#password').fill('synthetic-password');await f.page.locator('#submit').click();
 await f.page.waitForFunction(()=>document.getElementById('error').textContent.includes('nepodařilo potvrdit'));
 assert.equal(await f.page.evaluate(()=>sessionStorage.getItem('adminAccessToken')),null);
 assert.equal(f.requests.filter(r=>r.path==='/admin-web-session').length,0);
 }finally{await f.context.close();}
});

test('restarting MFA sign-in rejects a late challenge response',async()=>{
 const f=await fixture({login:true});try{
 await f.page.route('**/user/login',r=>r.fulfill({json:{two_factor_required:true,challenge_token:'synthetic-challenge'}}));
 await f.page.locator('#email').fill('admin@example.invalid');await f.page.locator('#password').fill('synthetic-password');await f.page.locator('#submit').click();
 await f.page.locator('#code').waitFor({state:'visible'});
 await f.page.evaluate(()=>{
  const native=fetch;
  window.fetch=(url,options)=>String(url).endsWith('/user/login/2fa')?new Promise(resolve=>window.deliverChallenge=()=>resolve(new Response(JSON.stringify({access_token:'LATE-TOKEN'})))):native(url,options);
 });
 await f.page.locator('#code').fill('123456');await f.page.locator('#submit').click();
 await f.page.waitForFunction(()=>typeof deliverChallenge==='function');await f.page.locator('#restart').click();
 await f.page.evaluate(async()=>{deliverChallenge();await new Promise(resolve=>setTimeout(resolve,0));});
 assert.equal(await f.page.locator('#password').isVisible(),true);
 assert.equal(await f.page.evaluate(()=>sessionStorage.getItem('adminAccessToken')),null);
 assert.equal(f.requests.filter(r=>r.path==='/admin-web-session').length,0);
 assert.deepEqual(f.errors,[]);
 }finally{await f.context.close();}
});
