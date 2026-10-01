// Real Chrome, fresh profile, intercepted network only. No real users or payments.
const {test,before,after}=require('node:test');
const assert=require('node:assert/strict');const fs=require('node:fs');const path=require('node:path');
const {execFileSync}=require('node:child_process');const {chromium}=require('../e2e/node_modules/playwright');
const root=path.resolve(__dirname,'../..');const origin='http://127.0.0.1:19877';
const csp=execFileSync(process.env.TEST_PYTHON||path.resolve(root,'../cloud-venv/bin/python'),['-c','from src.core.browser_policy import LEGACY_ADMIN_CONTENT_SECURITY_POLICY; print(LEGACY_ADMIN_CONTENT_SECURITY_POLICY)'],{cwd:root,encoding:'utf8'}).trim();
const poison=`Zkušební \"'><img src=x onerror="window.__xss=1"><svg onload="window.__xss=2"></svg> & &#39; \\`;
let browser;
before(async()=>{browser=await chromium.launch({channel:process.env.TEST_BROWSER_CHANNEL||'chrome',headless:true});});
after(async()=>{await browser?.close();});
async function fixture({policy=true}={}){
 const context=await browser.newContext(),page=await context.newPage();page.setDefaultTimeout(5000);
 const errors=[],requests=[],consoleMessages=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>consoleMessages.push(m.text()));
 await context.route('**/*',async route=>{
  const req=route.request(),url=new URL(req.url());requests.push({url:req.url(),method:req.method()});
  if(url.origin!==origin)return route.abort('blockedbyclient');
  if(url.pathname.startsWith('/web/')){
   const file=path.resolve(root,'.'+url.pathname);
   if(file.startsWith(root+'/web/')&&fs.existsSync(file)&&fs.statSync(file).isFile())return route.fulfill({status:200,body:fs.readFileSync(file),contentType:file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':file.endsWith('.html')?'text/html':'image/png',headers:policy?{'Content-Security-Policy':csp}:{}});
  }
  const defaults={'/health':{status:'ok'},'/user/security/admin-status':{required:true,enrolled:true,verified:true},'/user/me':{id:1,email:'admin@example.invalid',role:'admin'},'/api/v1/system/capabilities':{modules:{}},'/api/v1/vehicles':[]};
  return route.fulfill({status:200,json:defaults[url.pathname]||{}});
 });
 await page.goto(origin+'/web/index.html');await page.waitForFunction(()=>typeof API_URL==='string');
 await page.evaluate(()=>{accessToken='synthetic-session';currentUser={id:1,email:'admin@example.invalid',role:'admin'};});
 return {page,context,errors,requests,consoleMessages};
}
async function inert(page){
 assert.equal(await page.evaluate(()=>window.__xss),undefined);
 assert.equal(await page.locator('img[onerror],svg[onload],[onmouseover],[onfocus],[autofocus]').count(),0);
}

test('legacy page and extracted scripts initialize under strict CSP',async()=>{
 const f=await fixture();try{
 assert.deepEqual(f.errors,[]);
 assert.equal(await f.page.locator('[onclick],[oninput],[onsubmit],[onchange],script:not([src])').count(),0);
 await f.page.evaluate(()=>{const s=document.createElement('script');s.textContent='window.__xss=1';document.body.append(s);const b=document.createElement('button');b.setAttribute('onclick','window.__xss=1');b.click();});
 assert.equal(await f.page.evaluate(()=>window.__xss),undefined);
 await f.page.locator('#loginModeServiceBtn').click();assert.equal(await f.page.locator('#loginTitle').textContent(),'Přihlášení servisu');
 await f.page.locator('#loginModeUserBtn').click();assert.equal(await f.page.locator('#loginTitle').textContent(),'Přihlášení');
 assert.deepEqual(f.errors,[]);
 }finally{await f.context.close();}
});

test('vehicle cards, detail and edit form preserve hostile text without creating markup',async()=>{
 const f=await fixture({policy:false});try{const {page}=f;
 await page.evaluate(async p=>{
  const v={id:21,nickname:p,plate:p,vin:p,brand:p,model:p,notes:p,engine:p,created_at:'2026-01-01',year:2020};
  window.fixtureVehicle=v;
  apiCall=async url=>url==='/api/v1/vehicles'?[v]:url==='/api/v1/vehicles/21'?v:url.includes('records')?[]:url.includes('tachometer')?{records:[]}:{};
  await loadVehicles();
 },poison);
 assert.ok((await page.locator('#vehiclesContainer').textContent()).includes(poison));await inert(page);
 await page.evaluate(async()=>{await showVehicleDetail(21);});
 assert.ok((await page.locator('#vehicleDetailModal').textContent()).includes(poison));await inert(page);
 await page.locator('[data-legacy-click="startEditModal_c9c8fba8"]').dispatchEvent('click');
 assert.equal(await page.locator('#edit-nickname-modal-21').inputValue(),poison);
 assert.deepEqual(f.errors,[]);
 }finally{await f.context.close();}
});

test('service workspace, documents, reminders and reservation views keep data inert and markup functional',async()=>{
 const f=await fixture({policy:false});try{const {page}=f;
 const rendered=await page.evaluate(p=>{
  loginMode='service';
  serviceWorkspaceState.customers=[{customer_id:11,name:p,email:p,phone:p,vehicles_count:1,created_at:'2026-01-01'}];
  serviceWorkspaceState.selectedCustomerId=11;
  serviceWorkspaceState.customerVehicles={11:[{id:21,nickname:p,plate:p,vin:p,year:2020,is_shared:true}]};
  serviceWorkspaceState.invitations=[{id:31,email:p,status:'pending',status_label:p}];
  serviceWorkspaceState.documents=[{id:41,file_name:p,processing_status:'processed',parsed_data:{supplier_name:p,customer_name:p,document_number:p,service_summary:p}}];
  renderServiceWorkspace();
  serviceWorkspaceRemindersState.items=[{id:51,customer_id:11,customer_name:p,customer_email:p,vehicle_label:p,type:p,text:p,is_completed:false,due_date:'2027-01-01'}];
  renderServiceWorkspaceReminders();
  const reservation={id:61,customer_id:11,customer_name:p,customer_email:p,vehicle_id:21,vehicle_name:p,service_name:p,service_type:p,note:p,status:'PENDING',start_datetime:'2026-10-01T12:00:00',end_datetime:'2026-10-01T13:00:00'};
  reservationsUiState.all=[reservation];reservationsUiState.isServiceView=true;
  reservationsUiState.calendarAnchorDateKey='2026-10-01';reservationsUiState.selectedDateKey='2026-10-01';reservationsUiState.calendarMonthKey='2026-10';
  const host=document.createElement('div');host.id='fixture-reservations';document.body.append(host);
  const status={PENDING:{label:p,className:'pending'}};
  host.innerHTML=buildReservationServiceDashboard([reservation])+buildReservationCardsHtml([reservation],true,status)+buildReservationMonthView([reservation],status)+buildReservationWeekView([reservation],status)+buildReservationDayView([reservation],status);
  return {customers:document.querySelectorAll('#serviceWorkspaceContainer .service-workspace-customer-card').length,options:document.querySelectorAll('#serviceDocCustomerSelect option').length,buttons:document.querySelectorAll('#fixture-reservations [data-legacy-click]').length};
 },poison);
 assert.ok(rendered.customers>0);assert.ok(rendered.options>1);assert.ok(rendered.buttons>10);
 for(const id of ['serviceWorkspaceContainer','remindersContainer','fixture-reservations'])assert.ok((await page.locator('#'+id).textContent()).includes(poison),id);
 assert.equal(await page.locator('#serviceWorkspaceContainer').getByText('<div', {exact:false}).count(),0);
 await inert(page);assert.deepEqual(f.errors,[]);
 }finally{await f.context.close();}
});

test('delegated actions preserve quoted arguments, this.value, keyboard and stopPropagation',async()=>{
 const f=await fixture();try{const {page}=f;
 const result=await page.evaluate(p=>{
  const box=document.createElement('div');document.body.append(box);window.calls=[];
  showVehicleDetail=(...a)=>calls.push(['detail',...a]);deleteVehicle=(...a)=>calls.push(['delete',...a]);selectVehicleForCommand=(...a)=>calls.push(['command',...a]);
  updateServiceReportItemField=(...a)=>calls.push(['field',...a]);openReminderDetailModalByIndex=(...a)=>calls.push(['reminder',...a]);
  box.innerHTML=`<article ${legacyActionAttributes('click','showVehicleDetail_8ee4a012',21)}><button ${legacyActionAttributes('click','stopPropagation_00b7832c',21)}>delete</button></article><button id="command" ${legacyActionAttributes('click','selectVehicleForCommand_27b22fb1',31,21,p,p)}>command</button><input id="editor" ${legacyActionAttributes('input','updateServiceReportItemField_9e0f4764',p,1)}>`+buildReminderCardMinimalHtml({id:51,type:'STK',text:p,vehicle_name:p},2);
  box.querySelector('article button').click();box.querySelector('#command').click();const input=box.querySelector('#editor');input.value=p;input.dispatchEvent(new Event('input',{bubbles:true}));
  box.querySelector('.reminder-card').dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true}));
  return {calls,icons:box.querySelectorAll('.reminder-type-icon svg').length};
 },poison);
 assert.deepEqual(result.calls,[['delete',21],['command',31,21,poison,poison],['field',poison,1,'name',poison],['reminder',2]]);
 assert.equal(result.icons,1);await inert(page);assert.deepEqual(f.errors,[]);
 }finally{await f.context.close();}
});

test('AI extension cannot override attribute escaping or grant UI admin by query string',async()=>{
 const f=await fixture({policy:false});try{const {page}=f;
 await page.evaluate(p=>{
  const aiHost=document.createElement('div');aiHost.id='aiFeaturesContainer';document.body.append(aiHost);
  aiFeaturesSuggestions=[{id:31,title:p,description:p,reasoning:p,category:p,status:p,priority:p,implementation_complexity:p}];renderAIFeaturesSuggestions();
  const host=document.createElement('div');host.innerHTML=`<input id="quote-fixture" value="${escapeHtml(p)}">`;document.body.append(host);
 },poison);
 assert.equal(await page.locator('#quote-fixture').inputValue(),poison);await inert(page);
 assert.ok((await page.locator('#aiFeaturesContainer').textContent()).includes(poison));
 assert.equal(await page.locator('#aiFeaturesContainer .badge').count(),2);
 const roles=await page.evaluate(async()=>{history.replaceState({},'', '?admin=1');currentUser.role='user';const user=await checkIfAdmin();currentUser.role='admin';const admin=await checkIfAdmin();return {user,admin};});
 assert.deepEqual(roles,{user:false,admin:true});assert.deepEqual(f.errors,[]);
 }finally{await f.context.close();}
});

test('untrusted protocols are rejected and attachment preview is sandboxed',async()=>{
 const f=await fixture();try{const {page}=f;
 const result=await page.evaluate(()=>{
  const invalid=['javascript:alert(1)','data:text/html,x','https://user:pass@example.invalid/a','\u0000javascript:alert(1)'].map(v=>safeLegacyURL(v));
  openAttachmentPreviewModal(URL.createObjectURL(new Blob(['test'],{type:'text/plain'})),'Document');
  return {invalid,https:safeLegacyURL('https://example.invalid/a'),relative:safeLegacyURL('/api/v1/documents/1'),mailto:safeLegacyURL('mailto:info@example.invalid',true),sandbox:document.getElementById('attachmentPreviewFrame').getAttribute('sandbox')};
 });
 assert.deepEqual(result.invalid,['','','','']);assert.equal(result.https,'https://example.invalid/a');assert.equal(result.relative,origin+'/api/v1/documents/1');assert.equal(result.mailto,'mailto:info@example.invalid');assert.equal(result.sandbox,'');assert.deepEqual(f.errors,[]);
 }finally{await f.context.close();}
});

test('API diagnostics never retain response content or credentials',async()=>{
 const f=await fixture();try{const {page}=f;const secret='SYNTHETIC-PRIVATE-PAYLOAD';
 await page.route('**/api/v1/fixture**',r=>r.fulfill({status:200,json:{password_hash:secret,name:secret,token:secret}}));
 const result=await page.evaluate(async s=>{await apiCall('/api/v1/fixture?token='+s,'GET');return debugRequests;},secret);
 assert.ok(!JSON.stringify(result).includes(secret));assert.ok(!f.consoleMessages.join('\n').includes(secret));assert.deepEqual(f.errors,[]);
 }finally{await f.context.close();}
});

test('every migrated action refers to a real function and every rendered binding is registered',async()=>{
 const {babelParse,traverse}=require('../e2e/node_modules/playwright/lib/transform/babelBundle.js');
 const source=fs.readFileSync(path.join(root,'web/legacy-actions.js'),'utf8');const functions=new Set();
 traverse(babelParse(source,'actions.js',true),{VariableDeclarator(p){if(p.node.id.name!=='legacyActions')return;p.traverse({CallExpression(c){if(c.node.callee.type==='Identifier'&&!['Number','String','parseInt'].includes(c.node.callee.name))functions.add(c.node.callee.name);}});}});
 // Object.freeze itself is not an Identifier callee.
 const f=await fixture();try{
 const result=await f.page.evaluate(names=>({missingFunctions:names.filter(n=>typeof window[n]!=='function'),missingActions:[...document.querySelectorAll('*')].flatMap(e=>[...e.attributes].filter(a=>/^data-legacy-(click|submit|input|change|keydown|keypress)$/.test(a.name)).filter(a=>!Object.hasOwn(legacyActions,a.value)).map(a=>a.value)),count:Object.keys(legacyActions).length}),[...functions]);
 assert.deepEqual(result.missingFunctions,[]);assert.deepEqual(result.missingActions,[]);assert.ok(result.count>220);assert.deepEqual(f.errors,[]);
 }finally{await f.context.close();}
});

test('capabilities are obtained through the existing authenticated API client',async()=>{
 const f=await fixture();try{const actual=await f.page.evaluate(async()=>{const calls=[];apiCall=async(...args)=>{calls.push(args);return {modules:{vehicles:{available:false,reason:'synthetic'}}};};await loadSystemCapabilities();return {calls,modules:moduleCapabilities};});
 assert.deepEqual(actual.calls,[['/api/v1/system/capabilities','GET']]);assert.equal(actual.modules.vehicles.available,false);assert.deepEqual(f.errors,[]);
 }finally{await f.context.close();}
});

test('record detail to editor keeps text, attachment names and values intact',async()=>{
 const f=await fixture({policy:false});try{const {page}=f;
 await page.evaluate(async p=>{
  const record={id:41,category:'JINE',description:p,note:p,mileage:125000,price:1234,performed_at:'2026-10-01T12:00:00',attachments:[]};
  apiCall=async url=>url==='/api/v1/vehicles/21/records/41'?record:[];
  await showServiceRecordDetail(41,21);
 },poison);
 assert.ok((await page.locator('#serviceRecordDetailModalBody').textContent()).includes(poison));await inert(page);
 await page.locator('#serviceRecordDetailModalBody [data-legacy-click^="openEditServiceRecordModal_"]').dispatchEvent('click');
 await page.waitForFunction(()=>document.getElementById('serviceDescription-edit-41'));
 assert.equal(await page.locator('#serviceDescription-edit-41').inputValue(),poison);
 assert.equal(await page.locator('#serviceNote-edit-41').inputValue(),poison);
 await inert(page);assert.deepEqual(f.errors,[]);
 }finally{await f.context.close();}
});
