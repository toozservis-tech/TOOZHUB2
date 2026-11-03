/* Prepared only. Runtime requires fresh root iOS authority and an explicit GO.
 * Real headed Chrome, normal form login, readonly fictional loopback API.
 * No evaluate, injected token, positive response mock, clock/visibility override.
 */
'use strict';
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),assert=require('node:assert/strict');
const {spawnSync}=require('node:child_process');
const ORIGIN='http://127.0.0.1:18879',options={};
for(let i=2;i<process.argv.length;i+=2){assert(process.argv[i].startsWith('--')&&process.argv[i+1]);options[process.argv[i].slice(2)]=process.argv[i+1];}
const goFile=path.resolve(options['go-file']||''),out=path.resolve(options.output||'');
assert(fs.existsSync(goFile),'Fresh explicit runtime GO is required');const go=JSON.parse(fs.readFileSync(goFile));
assert.equal(go.allowed,true);assert.equal(go.origin,ORIGIN);assert.equal(go.readonly_product,true);assert.equal(go.allow_safety_network_abort,true);
assert.deepEqual(go.allowed_ambient_safety_abort_paths,['/api/v1/reminders/check-and-send-notifications']);
const sha=data=>crypto.createHash('sha256').update(data).digest('hex');
assert.equal(sha(fs.readFileSync(__filename)),go.harness_sha256,'Reviewed harness must match GO');
assert(go.ios_authority_path&&go.ios_authority_sha256,'Source-only iOS authority is insufficient');
assert.equal(sha(fs.readFileSync(go.ios_authority_path)),go.ios_authority_sha256);
const root=path.resolve(options['project-root']||go.project_root||''),oracleFile=path.resolve(options.oracle||go.oracle_file||'');
assert.equal(root,path.resolve(go.project_root));assert.equal(fs.existsSync(path.join(root,'.env')),false);
assert.equal(sha(fs.readFileSync(oracleFile)),go.oracle_sha256);
const oracle=JSON.parse(fs.readFileSync(oracleFile));assert.equal(oracle.origin,ORIGIN);
const repairMetadataFile=path.resolve(go.repair_metadata_file||'');assert.equal(sha(fs.readFileSync(repairMetadataFile)),go.repair_metadata_sha256);const repairMetadata=JSON.parse(fs.readFileSync(repairMetadataFile)).photo;assert.equal(repairMetadata.id,oracle.repair.photo_id);
const metadataInstant=value=>new Date(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?$/.test(value)?value+'Z':value).toISOString();
const fixture=path.resolve(oracle.fixture_dir),run=path.dirname(fixture),work=path.join(run,'web-ownership-ui');
const snapshotHelper=path.resolve(go.business_snapshot_helper||'');assert.equal(sha(fs.readFileSync(snapshotHelper)),go.business_snapshot_helper_sha256);
const frozenBaselineFile=path.resolve(go.frozen_business_baseline||'');assert.equal(sha(fs.readFileSync(frozenBaselineFile)),go.frozen_business_baseline_sha256);const frozenBaseline=JSON.parse(fs.readFileSync(frozenBaselineFile));
assert.equal(path.basename(fixture),'server');assert.equal(path.dirname(goFile),work);assert.equal(path.dirname(out),work);assert(path.basename(out).startsWith('run'));
assert.equal(fs.existsSync(out),false,'Use a new output directory; preserve failed evidence');
const secretFile=path.resolve(oracle.password_file);assert.equal(path.dirname(secretFile),fixture);assert.equal(fs.statSync(secretFile).mode&0o077,0);
const password=fs.readFileSync(0,'utf8').trim();assert(password&&password===fs.readFileSync(secretFile,'utf8').trim());
const sourceFiles=Object.keys(go.source_sha256||{});
for(const name of ['web/customer-features.js','web/customer-session.js','web/legacy-app.js','web/legacy-actions.js','web/index.html','src/modules/vehicle_hub/routers_v1/vehicle_archives.py'])assert(sourceFiles.includes(name),'Pin source '+name);
for(const name of sourceFiles)assert(!path.isAbsolute(name)&&!name.split('/').includes('..'));
const fingerprints=()=>Object.fromEntries(sourceFiles.map(name=>[name,sha(fs.readFileSync(path.join(root,name)))]));
const sourceBefore=fingerprints();assert.deepEqual(sourceBefore,go.source_sha256);
fs.mkdirSync(out,{recursive:false});fs.mkdirSync(path.join(out,'downloads'));
const scrub=v=>String(v).split(password).join('[fixture secret redacted]').replace(/eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+/g,'[bearer redacted]');
const proof={status:'RUNNING',scope:'Former-owner ownership archive private profile and original files; readonly real Chrome against same fictional native fixture',origin:ORIGIN,started_at:new Date().toISOString(),source_before:sourceBefore,source_after:null,harness_sha256:sha(fs.readFileSync(__filename)),oracle_sha256:sha(fs.readFileSync(oracleFile)),ios_authority:{path:go.ios_authority_path,sha256:go.ios_authority_sha256},checks:[],mutation_counters:{attempted_archive_mutations:0,ambient_notification_posts_blocked:0,unknown_business_writes:0,accepted_business_writes:0},notifications_status:'BLOKOVÁNO / NEOVĚŘENO: ambient notification POST is safety-aborted',requests:[],blocked_requests:[],page_errors:[],console_errors:[],observer_errors:[],asset_proof:[],downloads:[],artifacts:[],token_injected:false,positive_response_mock:false,internal_action_called_by_test:false,clock_changed:false,visibility_changed_by_test:false,headless:false,limits:['Fictional loopback only; no production, deployed, released or physical-device claim.','Foreign role UI absence is not a direct-endpoint authorization proof; root actual JWT API tests cover denied archive/file reads.','Service archive tab remains hidden as in current product; this test does not add service access.','Private preview late logout/account change/close/remove/error URL cleanup has isolated actual-helper unit contracts; this journey proves normal decoded preview and screen removal, not timed browser races.','Background reminder-send POST remains blocked and unverified; zero attempted business writes globally is not claimed.','Exact file bytes come from the native UI download artifact; a missing/empty CDP body observation is diagnostic, not the file bytes.']};
const report=path.join(out,'real-journey.json'),save=()=>fs.writeFileSync(report,JSON.stringify(proof,null,2)+'\n');
function businessSnapshot(label){const file=path.join(out,'business-'+label+'.json');const result=spawnSync(process.env.PARITY_PYTHON||go.python_binary||'python3',[snapshotHelper,'--output',file],{encoding:'utf8',timeout:30000});assert.equal(result.status,0,'Read-only business snapshot failed: '+scrub(result.stderr||''));return {file,sha256:sha(fs.readFileSync(file)),data:JSON.parse(fs.readFileSync(file))};}
const pause=ms=>new Promise(r=>setTimeout(r,ms));async function until(fn,timeout=30000){const end=Date.now()+timeout;while(Date.now()<end){const value=await fn();if(value)return value;await pause(100);}throw Error('Observed browser condition timed out');}
function pass(name,details={}){proof.checks.push({name,status:'PASS',...details});save();console.log(JSON.stringify({phase:name,report}));}
async function screenshot(page,name){const file=path.join(out,name+'.png');await page.screenshot({path:file,fullPage:true});proof.artifacts.push({path:file,sha256:sha(fs.readFileSync(file))});save();}
const tasks=new Set(),pages=[],pageRoles=new WeakMap();let browser;
const settle=()=>Promise.all([...tasks]);
async function contextFor(role){
 const state={role};
 const context=await browser.newContext({viewport:{width:1280,height:1000},acceptDownloads:true,serviceWorkers:'block'});
 await context.route('**/*',async route=>{
  const request=route.request(),url=new URL(request.url()),method=request.method();if(!['http:','https:'].includes(url.protocol))return route.continue();
  let reason='';if(url.origin!==ORIGIN)reason='external_network';
  else if(!['GET','HEAD','OPTIONS'].includes(method)){
   const auth=method==='POST'&&['/user/login','/user/login/2fa','/user/session/renew','/user/logout','/user/activity'].includes(url.pathname);
   const close=method==='DELETE'&&url.pathname==='/admin-web-session';
   if(!auth&&!close){
    if(method==='POST'&&url.pathname==='/api/v1/reminders/check-and-send-notifications'){reason='ambient_notification_post_blocked';proof.mutation_counters.ambient_notification_posts_blocked++;}
    else{reason='product_write_not_allowed';if(url.pathname.startsWith('/api/v1/vehicle-archives')||url.pathname.startsWith('/api/v1/repair-documentation')||url.pathname.startsWith('/api/v1/vehicles/'+oracle.vehicle_id))proof.mutation_counters.attempted_archive_mutations++;else proof.mutation_counters.unknown_business_writes++;}
   }
  }
  if(reason){proof.blocked_requests.push({role:state.role,method,path:url.pathname,reason});save();return route.abort();}return route.continue();
 });
 const page=await context.newPage();pageRoles.set(page,state);pages.push({page,role});page.on('pageerror',e=>{proof.page_errors.push({role:state.role,error:scrub(e.message)});save();});
 page.on('console',m=>{if(m.type()==='error')proof.console_errors.push({role:state.role,error:scrub(m.text()).slice(0,400)});});
 page.on('response',response=>{
  const url=new URL(response.url());if(url.origin!==ORIGIN)return;
  const row={role:state.role,path:url.pathname,method:response.request().method(),status:response.status()};proof.requests.push(row);
  const task=(async()=>{
   const asset=url.pathname.startsWith('/web/')?url.pathname.slice(1):null;
   if(asset&&['web/customer-features.js','web/customer-session.js','web/legacy-app.js'].includes(asset)&&response.ok()){
    const digest=sha(await response.body());proof.asset_proof.push({role:row.role,path:asset,sha256:digest,expected:sourceBefore[asset],resource_type:response.request().resourceType(),service_worker:response.fromServiceWorker()});assert.equal(digest,sourceBefore[asset]);assert.equal(response.fromServiceWorker(),false);
   }
   if(response.ok()&&row.method==='GET'){
    if(url.pathname==='/user/me'){const data=await response.json();row.account={id:data.id,email:data.email,role:data.role};}
    if(url.pathname==='/api/v1/vehicle-archives')row.archive_ids=(await response.json()).map(x=>x.id);
    if(url.pathname===`/api/v1/repair-documentation/sessions/${oracle.repair.session_id}/photos`)row.repair_photos=(await response.json()).map(p=>({id:p.id,author_name:p.author_name,source:p.source,captured_at:p.captured_at,uploaded_at:p.uploaded_at,sha256:p.sha256}));
    if(url.pathname===`/api/v1/vehicle-archives/${oracle.archive_id}`){const data=await response.json();row.archive={id:data.id,profile:data.profile,record_ids:data.records.map(x=>x.id)};}
    if(url.pathname===`/api/v1/vehicle-archives/${oracle.archive_id}/attachment`||url.pathname.startsWith(`/api/v1/vehicle-archives/${oracle.archive_id}/image/`)||url.pathname===`/api/v1/repair-documentation/photos/${oracle.repair.photo_id}/file`||url.pathname===`/api/v1/repair-documentation/sessions/${oracle.repair.session_id}/report.pdf`){
     row.file={key:url.searchParams.get('key'),content_type:response.headers()['content-type'],cache_control:response.headers()['cache-control'],nosniff:response.headers()['x-content-type-options']};
     try{const bytes=await response.body();row.file.body_observer={bytes:bytes.length,sha256:sha(bytes),status:bytes.length?'AVAILABLE_CDP_OBSERVATION':'EMPTY_CDP_OBSERVATION_NOT_DOWNLOAD_BYTES'};}catch(e){row.file.body_observer={status:'UNAVAILABLE_CDP_OBSERVATION',error:scrub(e.message)};}
    }
   }save();
  })().catch(e=>{proof.observer_errors.push({role:row.role,path:url.pathname,error:scrub(e.message)});save();}).finally(()=>tasks.delete(task));tasks.add(task);
 });return {context,page};
}
async function login(page,role,actor,mode='user'){
 await settle();pageRoles.get(page).role=role;
 await page.bringToFront();const document=await page.goto(ORIGIN+'/web/customer.html',{waitUntil:'domcontentloaded'});assert.equal(document.status(),200);
 await page.locator(mode==='service'?'#loginModeServiceBtn':'#loginModeUserBtn').click();await page.locator('#loginEmail').fill(actor.email);await page.locator('#loginPassword').fill(password);
 const loginResponse=page.waitForResponse(r=>new URL(r.url()).pathname==='/user/login'&&r.request().method()==='POST');await page.locator('#loginSubmitBtn').click();assert.equal((await loginResponse).status(),200);
 await page.locator('#dashboard').waitFor({state:'visible',timeout:45000});
 await until(()=>proof.requests.findLast(x=>x.role===role&&x.account?.id===actor.id&&x.account.email===actor.email));await settle();
 for(const name of ['web/customer-features.js','web/customer-session.js','web/legacy-app.js'])assert(proof.asset_proof.some(x=>x.role===role&&x.path===name&&x.sha256===sourceBefore[name]));
 pass(role+' normal UI login and actual source bytes',{account_id:actor.id});
}
const archiveDialog=page=>page.locator('#customerFeatureDialog');
async function openArchives(page){
 const response=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/vehicle-archives'&&r.request().method()==='GET');await page.locator('[data-tab-key="customerArchives"]').click();const result=await response;assert.equal(result.status(),200);return result.json();
}
async function openDetail(page){
 const card=page.locator('#customerArchivesTab article.customer-feature-card').filter({has:page.getByRole('heading',{name:oracle.vehicle_nickname,exact:true})});assert.equal(await card.count(),1);
 const response=page.waitForResponse(r=>new URL(r.url()).pathname===`/api/v1/vehicle-archives/${oracle.archive_id}`&&r.request().method()==='GET');await card.getByRole('button',{name:'Otevřít archiv',exact:true}).click();assert.equal((await response).status(),200);await archiveDialog(page).waitFor({state:'visible'});await archiveDialog(page).locator('[data-ownership-archive-profile]').waitFor();
}
async function verifyFields(page,label){
 const section=archiveDialog(page).locator('[data-ownership-archive-profile]');
 for(const [field,value]of Object.entries(oracle.profile)){
  const row=section.locator(`[data-archive-profile-field="${field}"]`);assert.equal(await row.count(),1);const actual=field==='notes'?await row.textContent():await row.locator('dd').textContent();assert.equal(actual,value);
 }
 assert.equal(await section.locator('script,img,iframe,input,textarea,select').count(),0);
 const record=archiveDialog(page).locator('article.customer-feature-card').filter({has:page.getByRole('heading',{name:oracle.record.title,exact:true})});assert.equal(await record.count(),1);
 const text=await record.textContent();assert(text.includes(oracle.record.note));assert(text.includes(String(oracle.record.mileage)));assert(text.includes(new Intl.NumberFormat('cs-CZ',{style:'currency',currency:'CZK'}).format(oracle.record.price)));
 assert.equal(await record.getByRole('button').count(),oracle.unique_attachment_count);
 for(const doc of oracle.documents)assert.equal(await record.getByRole('button',{name:doc.name,exact:true}).count(),1);
 assert.equal(await archiveDialog(page).getByRole('button',{name:/^(Uložit|Smazat|Upravit|Archivovat)/}).count(),0);
 pass(label+' exact readonly profile/record values and deduplicated documents');return record;
}
async function download(page,button,expected,file,requestPath,key=null){
 const event=page.waitForEvent('download');await button.scrollIntoViewIfNeeded();await button.click();const d=await event;const destination=path.join(out,'downloads',file);await d.saveAs(destination);
 const bytes=fs.readFileSync(destination);if(expected.generated_pdf===true){assert.equal(bytes.subarray(0,5).toString(),'%PDF-');assert(bytes.length>500);assert(bytes.subarray(-1024).includes(Buffer.from('%%EOF')));}else{assert.equal(bytes.length,expected.bytes);assert.equal(sha(bytes),expected.sha256);}
 await until(()=>proof.requests.some(x=>x.path===requestPath&&x.status===200&&x.file&&(key===null||x.file.key===key)));await settle();
 const observed=proof.requests.findLast(x=>x.path===requestPath&&x.status===200&&x.file&&(key===null||x.file.key===key));assert.equal(observed.status,200);assert(/(?:^|,)\s*no-store(?:\s*(?:,|$))/i.test(observed.file.cache_control||''));assert(!/(?:^|,)\s*public(?:\s*(?:,|$))/i.test(observed.file.cache_control||''));assert.equal(observed.file.nosniff,'nosniff');assert(observed.file.content_type.startsWith(expected.mime_type));
 if(expected.name)assert.equal(d.suggestedFilename(),expected.name);
 if(expected.generated_pdf===true&&observed.file.body_observer?.status==='AVAILABLE_CDP_OBSERVATION')assert.equal(observed.file.body_observer.sha256,sha(bytes));
 proof.downloads.push({file:destination,suggested_filename:d.suggestedFilename(),bytes:bytes.length,sha256:sha(bytes),bytes_authority:'actual native UI download artifact',api_path:requestPath,key,response_status:observed.status,response_metadata:observed.file});save();
}
async function verifyRepair(page,label,requestsBefore){
 const body=archiveDialog(page),section=body.locator('[data-repair-photo-metadata="'+oracle.repair.photo_id+'"]');await section.waitFor();
 assert.equal(await section.locator('[data-repair-photo-field="author_name"] dd').textContent(),repairMetadata.author_name);
 assert.equal(await section.locator('[data-repair-photo-field="source"] dd').textContent(),repairMetadata.source==='camera'?'Fotoaparát':'Fotogalerie');
 for(const field of ['captured_at','uploaded_at']){const time=section.locator('[data-repair-photo-field="'+field+'"] time');assert.equal(await time.getAttribute('datetime'),metadataInstant(repairMetadata[field]));assert(await time.isVisible());}
 await section.getByText('Kontrolní otisk uloženého souboru',{exact:true}).click();const hash=section.locator('[data-repair-photo-field="sha256"]');assert.equal(await hash.textContent(),oracle.repair.sha256);assert(await hash.isVisible());
 const preview=body.locator('[data-repair-photo-preview="'+oracle.repair.photo_id+'"]');await until(async()=>{const state=await preview.getAttribute('data-preview-state');if(state==='error')throw Error('Actual repair image preview failed');return state==='loaded';});
 const width=Number(await preview.getAttribute('data-natural-width')),height=Number(await preview.getAttribute('data-natural-height'));assert(width>0&&height>0);assert.equal(await preview.getAttribute('data-verified-sha256'),oracle.repair.sha256);const img=preview.getByRole('img',{name:'Fotografie opravy',exact:true});assert(await img.isVisible());assert((await img.getAttribute('src')).startsWith('blob:'));const box=await img.boundingBox();assert(box&&box.width>0&&box.height>0);
 await settle();const fileReads=proof.requests.filter(x=>x.path===`/api/v1/repair-documentation/photos/${oracle.repair.photo_id}/file`);assert.equal(fileReads.length-requestsBefore,1,'Preview should issue one private GET, not a render/request loop');assert(fileReads.slice(requestsBefore).every(x=>x.status===200));
 const metadataReads=proof.requests.flatMap(x=>x.repair_photos||[]).filter(p=>p.id===oracle.repair.photo_id);assert(metadataReads.length);const actual=metadataReads.at(-1);assert.equal(actual.source,repairMetadata.source);assert.equal(actual.author_name,repairMetadata.author_name);assert.equal(actual.sha256,repairMetadata.sha256);for(const field of ['captured_at','uploaded_at'])assert.equal(metadataInstant(actual[field]),metadataInstant(repairMetadata[field]));
 proof.repair_preview_observations=proof.repair_preview_observations||[];proof.repair_preview_observations.push({label,natural_width:width,natural_height:height,sha256:await preview.getAttribute('data-verified-sha256'),evidence_kind:'Actual application image.onload reads natural dimensions; no test evaluation/injected image',private_GET_count:fileReads.length-requestsBefore});pass(label+' actual decoded private image and source/captured/uploaded/author/SHA metadata');
 return {image:await img.elementHandle(),element:await preview.elementHandle()};
}
async function closeRepair(page,handles,label){await closeDetail(page);await until(async()=>await handles.image.getAttribute('src')===null&&await handles.element.getAttribute('data-preview-state')==='disposed');await handles.image.dispose();await handles.element.dispose();pass(label+' removed preview clears private image source and reaches disposed state');}
async function closeDetail(page){await archiveDialog(page).getByRole('button',{name:'Zavřít',exact:true}).click();await archiveDialog(page).waitFor({state:'detached'});}
async function assertNoPrivateUI(page){
 assert.equal(await archiveDialog(page).count(),0);
 for(const value of [...Object.values(oracle.profile),oracle.record.title,oracle.record.note])assert.equal(await page.getByText(value,{exact:true}).count(),0);
}
async function logout(page,label){
 if(await archiveDialog(page).count())await closeDetail(page);const response=page.waitForResponse(r=>new URL(r.url()).pathname==='/admin-web-session'&&r.request().method()==='DELETE');
 await page.locator('[data-testid="btn-logout"]').click();const r=await response;assert.equal(r.status(),200);await page.locator('#loginSubmitBtn').waitFor({state:'visible',timeout:30000});await assertNoPrivateUI(page);pass(label+' normal logout clears private archive UI');
}
(async()=>{
 proof.business_before=businessSnapshot('before');assert.deepEqual(proof.business_before.data,frozenBaseline,'Current fixture differs from the approved frozen business baseline');save();
 const {chromium}=require(go.playwright_module||process.env.PLAYWRIGHT_MODULE||'playwright');browser=await chromium.launch({headless:false,...(go.chrome_binary?{executablePath:go.chrome_binary}:{})});
 const owner=await contextFor('former-owner');await login(owner.page,'former-owner',oracle.former_owner);
 const list=await openArchives(owner.page);assert(list.some(x=>x.id===oracle.archive_id));await openDetail(owner.page);let record=await verifyFields(owner.page,'desktop');await screenshot(owner.page,'01-desktop-private-profile');
 for(const [index,doc]of oracle.documents.entries())await download(owner.page,record.getByRole('button',{name:doc.name,exact:true}),doc,`document-${index+1}.pdf`,`/api/v1/vehicle-archives/${oracle.archive_id}/attachment`,doc.key);
 pass('two unique native downloads include legacy path-only PDF with exact bytes');
 const labels={cover:'Fotografie vozidla','registration-front':'Přední strana ORV','registration-back':'Zadní strana ORV'};
 for(const image of oracle.images)await download(owner.page,archiveDialog(owner.page).getByRole('button',{name:labels[image.kind],exact:true}),image,image.kind+'.jpg',`/api/v1/vehicle-archives/${oracle.archive_id}/image/${image.kind}`);
 pass('three private archive image downloads preserve exact bytes');
 const initialPhotoReads=proof.requests.filter(x=>x.path===`/api/v1/repair-documentation/photos/${oracle.repair.photo_id}/file`).length;
 await archiveDialog(owner.page).getByRole('button',{name:'Fotodokumentace: '+oracle.repair.title,exact:true}).click();await archiveDialog(owner.page).getByRole('heading',{name:oracle.repair.title,exact:true}).waitFor();await archiveDialog(owner.page).getByText(oracle.repair.note,{exact:true}).waitFor();
 const desktopRepair=await verifyRepair(owner.page,'desktop',initialPhotoReads);await screenshot(owner.page,'02-desktop-private-repair-preview-metadata');
 await download(owner.page,archiveDialog(owner.page).getByRole('button',{name:'PDF opravy',exact:true}),{generated_pdf:true,mime_type:'application/pdf',name:'fotodokumentace-opravy.pdf'},'repair-report.pdf',`/api/v1/repair-documentation/sessions/${oracle.repair.session_id}/report.pdf`);assert.equal(await desktopRepair.element.getAttribute('data-preview-state'),'loaded');assert(Number(await desktopRepair.element.getAttribute('data-natural-width'))>0);assert.equal(await desktopRepair.element.getAttribute('data-verified-sha256'),oracle.repair.sha256);pass('former-owner archive repair PDF native UI download is valid and private; decoded photo remains loaded');
 await download(owner.page,archiveDialog(owner.page).getByRole('button',{name:'Stáhnout fotografii',exact:true}),oracle.repair,'repair.jpg',`/api/v1/repair-documentation/photos/${oracle.repair.photo_id}/file`);pass('original repair photo native download preserves exact bytes');
 await closeRepair(owner.page,desktopRepair,'desktop');await openDetail(owner.page);await verifyFields(owner.page,'close/reopen');
 await owner.page.reload({waitUntil:'domcontentloaded'});await owner.page.locator('#dashboard').waitFor({state:'visible',timeout:45000});await openArchives(owner.page);await openDetail(owner.page);await verifyFields(owner.page,'reload');
 await owner.page.setViewportSize({width:390,height:844});await verifyFields(owner.page,'narrow390');
 for(const field of Object.keys(oracle.profile)){const row=archiveDialog(owner.page).locator(`[data-archive-profile-field="${field}"]`);await row.scrollIntoViewIfNeeded();const box=await row.boundingBox();assert(box&&box.x>=-1&&box.x+box.width<=391,'Profile field exceeds narrow viewport: '+field);}
 await archiveDialog(owner.page).locator('[data-ownership-archive-profile]').scrollIntoViewIfNeeded();await screenshot(owner.page,'03-narrow390-literal-private-profile');pass('390px profile fields remain reachable within viewport');
 const narrowPhotoReads=proof.requests.filter(x=>x.path===`/api/v1/repair-documentation/photos/${oracle.repair.photo_id}/file`).length;await archiveDialog(owner.page).getByRole('button',{name:'Fotodokumentace: '+oracle.repair.title,exact:true}).click();const narrowRepair=await verifyRepair(owner.page,'narrow390',narrowPhotoReads);await screenshot(owner.page,'04-narrow390-private-repair-preview-metadata');await closeRepair(owner.page,narrowRepair,'narrow390');
 await owner.page.setViewportSize({width:1280,height:1000});await logout(owner.page,'former-owner');await login(owner.page,'new-owner',oracle.new_owner);assert.deepEqual(await openArchives(owner.page),[]);await assertNoPrivateUI(owner.page);await screenshot(owner.page,'05-new-owner-empty-private-archive');pass('new owner normal login has empty personal archive and no former private UI');await logout(owner.page,'new-owner');
 for(const [index,actor]of oracle.services.entries()){
  const role='service-'+(index+1),service=await contextFor(role);await login(service.page,role,actor,'service');assert.equal(await service.page.locator('[data-tab-key="customerArchives"]').isVisible(),false);await assertNoPrivateUI(service.page);await screenshot(service.page,'06-'+role+'-no-private-archive');pass(role+' current hidden archive UI reveals no former-owner data');await logout(service.page,role);
 }
 await settle();assert.deepEqual(proof.observer_errors,[]);assert.deepEqual(proof.page_errors,[]);proof.mutation_counters.accepted_business_writes=proof.requests.filter(x=>x.path.startsWith('/api/v1/')&&!['GET','HEAD','OPTIONS'].includes(x.method)).length;assert.equal(proof.mutation_counters.accepted_business_writes,0);assert.equal(proof.mutation_counters.attempted_archive_mutations,0);assert.equal(proof.mutation_counters.unknown_business_writes,0);assert.equal(proof.blocked_requests.filter(x=>x.reason==='product_write_not_allowed').length,0);
 proof.status='PASS';pass('no accepted business writes; archive/unknown mutation attempts0; ambient notification posts remain blocked',{counters:proof.mutation_counters,notifications_status:proof.notifications_status});
})().catch(async error=>{proof.status='FAILED';proof.error=scrub(error.message);proof.error_stack=scrub(error.stack||'');process.exitCode=1;for(const {page,role}of pages)try{await screenshot(page,'failure-'+role);}catch{}}).finally(async()=>{
 await settle();proof.source_after=fingerprints();if(JSON.stringify(proof.source_after)!==JSON.stringify(sourceBefore)){proof.status='FAILED_SOURCE_CHANGED';process.exitCode=1;}
 if(browser)await browser.close();try{proof.business_after=businessSnapshot('after');proof.business_unchanged=JSON.stringify(proof.business_before?.data)===JSON.stringify(proof.business_after.data);if(!proof.business_unchanged){proof.status='FAILED_BUSINESS_CHANGED';process.exitCode=1;}}catch(e){proof.status='FAILED_BUSINESS_SNAPSHOT';proof.snapshot_error=scrub(e.message);process.exitCode=1;}
 proof.finished_at=new Date().toISOString();save();console.log(JSON.stringify({status:proof.status,checks:proof.checks.length,report,error:proof.error||null,business_unchanged:proof.business_unchanged}));
});
