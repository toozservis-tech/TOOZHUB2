// Synthetic isolated DOM/security harness only: no real API, accounts or product evidence.
const {test,before,after}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || '../e2e/node_modules/playwright');
const decode=require('../../web/vendor/jsQR-1.4.0.js');
const root=path.resolve(__dirname,'../..'),origin='https://referral.example.test',code='Abcdef_0123456789-xyz7890';
const invitationTitle='Pozvánka do Evidence Vozidel';
const invitationMessages={
 user:'Vyzkoušejte Evidence Vozidel a mějte svá auta, servisní historii a důležité termíny na jednom místě. Zaregistrujte se přes mou pozvánku. Vaše vozidla zůstávají soukromá; za splnění podmínek pozvání mohu získat bonus Premium.',
 service:'Zveme váš servis do aplikace Evidence Vozidel. Spravujte klienty, zakázky, fotografie a servisní historii na jednom místě. Zaregistrujte servis přes tuto pozvánku; přístup k vozidlům schvalují jejich majitelé. Za splnění podmínek pozvání mohu získat bonus Premium.'
};
const invitationSteps=[
 'Vyberte, koho zvete, a pošlete svůj odkaz nebo ukažte QR kód.',
 'Pozvaný se přes odkaz nově zaregistruje a ověří e-mail. Uživatel přidá první vozidlo; schválený servis dokončí první zakázku.',
 'Za každé 3 takové uživatele nebo 1 takový servis získáte měsíc Premium. Splnění podmínek uvidíte níže.'
];
const invitationPrivacy='Samotné odeslání pozvánky odměnu nepřidá. Pozvánka nikomu nezpřístupní vaše vozidla ani soukromé údaje.';
let browser;
before(async()=>{browser=await chromium.launch({channel:process.env.TEST_BROWSER_CHANNEL || 'chrome',headless:true});});
after(async()=>{await browser?.close();});
function summary(id=7){return {customer_id:id,name:'Testovací účet',email:'account@example.invalid',code,user_url:`${origin}/api/v1/referrals/join/${code}?kind=user`,service_url:`${origin}/api/v1/referrals/join/${code}?kind=service`,registrations:201,qualified_users:2,qualified_services:0,users_to_next_reward:1,rules:'Měsíc Premium za 3 nové ověřené uživatele nebo 1 nový ověřený servis.',billing_note:'Odměna neruší předplatné.',referrals:[{id:1,kind:'user',status:'waiting_vehicle',name:'SECRET PERSON',email:'private@example.invalid',created_at:'2026-11-03T12:00:00'}],rewards:[{id:8,source:'user',starts_at:'2026-11-03T12:00:00',ends_at:'2026-12-03T12:00:00',reason:'Čekající odměna',waiting_for_paid:true,lifetime:false}]};}
async function fixture({role='user',respond,viewport={width:390,height:844}}={}){
 const context=await browser.newContext({viewport}),requests=[];
 await context.route('**/*',async route=>{
  const url=new URL(route.request().url());
  if(url.origin!==origin)return route.abort();
  if(['/web/referral-features.js','/web/referral-features.css','/web/vendor/referral-qr.js'].includes(url.pathname))return route.fulfill({contentType:url.pathname.endsWith('.css')?'text/css; charset=utf-8':'text/javascript; charset=utf-8',body:fs.readFileSync(path.join(root,url.pathname))});
  if(url.pathname==='/fixture')return route.fulfill({contentType:'text/html; charset=utf-8',body:`<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/web/referral-features.css"></head><body><button id="outside">Fixture</button><script src="/web/vendor/referral-qr.js"></script><script src="/web/referral-features.js"></script><script>
   let generation=0;window.testRole=${JSON.stringify(role)};window.testID=7;
   window.AdminBrowserSession={token:()=> 'SYNTHETIC',snapshot:()=>({generation}),assertCurrent:s=>{if(s.generation!==generation)throw new DOMException('changed','AbortError');},request:(url,init,s)=>{AdminBrowserSession.assertCurrent(s);return fetch(url,init);},changeAccount:()=>{generation++;window.testID=70;}};
   Object.defineProperty(navigator,'clipboard',{value:{writeText:async()=>{throw Error('denied');}},configurable:true});
  </script></body></html>`});
  const request={path:url.pathname,search:url.search,method:route.request().method(),body:route.request().postDataJSON()};requests.push(request);
  if(respond && await respond(route,request,url))return;
  if(url.pathname==='/user/me')return route.fulfill({json:{id:7,role,name:'Fixture',email:'fixture@example.invalid'}});
  if(url.pathname==='/api/v1/referrals/me')return route.fulfill({json:summary()});
  if(url.pathname==='/api/v1/referrals/admin')return route.fulfill({json:{total:31,offset:Number(url.searchParams.get('offset')),limit:30,items:[{id:40,name:'Admin target',email:'target@example.invalid',registrations:3,qualified:3}]}});
  if(url.pathname==='/api/v1/referrals/admin/40')return route.fulfill({json:{...summary(40),name:'Admin target',email:'target@example.invalid'}});
  return route.fulfill({status:404,json:{detail:'Synthetic route not found'}});
 });
 const page=await context.newPage();await page.goto(origin+'/fixture');return {page,context,requests};
}
async function qrText(page){const rgba=await page.locator('canvas.referral-qr').evaluate(c=>({width:c.width,height:c.height,data:Array.from(c.getContext('2d').getImageData(0,0,c.width,c.height).data)}));return decode(new Uint8ClampedArray(rgba.data),rgba.width,rgba.height)?.data;}
async function shareProbe(page,mode='success'){
 await page.evaluate(mode=>{
  window.sharedInvitations=[];window.copiedInvitations=[];window.clipboardAttempts=[];
  Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async text=>{
   window.clipboardAttempts.push(text);
   if(mode==='clipboard-denied')throw new DOMException('Clipboard permission denied','NotAllowedError');
   window.copiedInvitations.push(text);
  }}});
  Object.defineProperty(navigator,'share',{configurable:true,value:['unavailable','clipboard-denied'].includes(mode)?undefined:async payload=>{
   window.sharedInvitations.push({payload,activeUserGesture:navigator.userActivation.isActive});
   if(mode==='cancel')throw new DOMException('User cancelled sharing','AbortError');
   if(mode==='error')throw new TypeError('Synthetic sharing unavailable');
  }});
 },mode);
}

test('no startup request; personal service/user QR is real, details anonymous and narrow layout fits',async()=>{
 const f=await fixture();try{
  assert.equal(f.requests.length,0);
  await f.page.evaluate(()=>ReferralFeatures.openPersonal('service'));
  assert.equal(await f.page.locator('select').inputValue(),'service');
  assert.equal(await qrText(f.page),`${origin}/api/v1/referrals/join/${code}?kind=service`);
  assert.doesNotMatch(await f.page.locator('dialog').innerText(),/SECRET PERSON|private@example.invalid/);
  assert.match(await f.page.locator('dialog').innerText(),/posledních 200/);
  assert.match(await f.page.locator('dialog').innerText(),/zbývá 1 uživatel nebo 1 nový servis/);
  assert.match(await f.page.locator('dialog').innerText(),/Bonus se zatím nespotřebovává/);
  await f.page.locator('select').selectOption('user');
  assert.equal(await qrText(f.page),`${origin}/api/v1/referrals/join/${code}?kind=user`);
  await f.page.getByRole('button',{name:'Kopírovat odkaz'}).click();
  assert.match(await f.page.locator('.referral-notice').innerText(),/zkopírujte jej ručně/);
  assert.equal(await f.page.locator('input[readonly]').evaluate(el=>el.selectionEnd-el.selectionStart),f.page ? `${origin}/api/v1/referrals/join/${code}?kind=user`.length:0);
  assert.equal(await f.page.locator('dialog').evaluate(el=>el.scrollWidth<=el.clientWidth),true);
  assert.equal(await f.page.locator('dialog').evaluate(el=>Math.abs(el.getBoundingClientRect().left-(innerWidth-el.getBoundingClientRect().width)/2)<=1),true);
  assert.equal(f.requests.some(r=>r.method!=='GET'),false);
 }finally{await f.context.close();}
});
test('personal user and service views show the approved three-step guide and share kind-specific copy only after a click',async()=>{
 for(const role of ['user','service']){
  const f=await fixture({role});try{
   await shareProbe(f.page);
   assert.equal(f.requests.length,0);
   assert.deepEqual(await f.page.evaluate(()=>window.sharedInvitations),[]);
   await f.page.evaluate(()=>ReferralFeatures.openPersonal('user'));
   const guide=f.page.locator('section').filter({has:f.page.getByRole('heading',{name:'Tři kroky k bonusu Premium',exact:true})});
   assert.equal(await guide.count(),1);
   assert.deepEqual(await guide.getByRole('listitem').allTextContents(),invitationSteps);
   assert.match(await guide.innerText(),/Samotné odeslání pozvánky odměnu nepřidá/);
   assert.equal(await guide.getByText(invitationPrivacy,{exact:true}).count(),1);
   assert.deepEqual(await f.page.evaluate(()=>window.sharedInvitations),[]);
   assert.deepEqual(await f.page.evaluate(()=>window.copiedInvitations),[]);
   for(const kind of ['user','service']){
    if(kind==='service')await f.page.locator('select').selectOption('service');
    assert.equal(await f.page.evaluate(()=>window.sharedInvitations.length),kind==='user'?0:1);
    await f.page.getByRole('button',{name:'Sdílet pozvánku',exact:true}).click();
    const calls=await f.page.evaluate(()=>window.sharedInvitations);
    assert.equal(calls.length,kind==='user'?1:2);
    assert.deepEqual(calls.at(-1),{payload:{title:invitationTitle,text:invitationMessages[kind],url:`${origin}/api/v1/referrals/join/${code}?kind=${kind}`},activeUserGesture:true});
   }
   assert.deepEqual(await f.page.evaluate(()=>window.copiedInvitations),[]);
   assert.equal(f.requests.some(r=>r.method!=='GET'),false);
  }finally{await f.context.close();}
 }
});
test('cancelled sharing does not copy or submit anything; unavailable or failed sharing copies the invitation text and link',async()=>{
 for(const mode of ['cancel','unavailable','error']){
  const f=await fixture();try{
   await shareProbe(f.page,mode);
   await f.page.evaluate(()=>ReferralFeatures.openPersonal('service'));
   const before=f.requests.length;
   await f.page.getByRole('button',{name:'Sdílet pozvánku',exact:true}).click();
   const calls=await f.page.evaluate(()=>({shared:window.sharedInvitations,copied:window.copiedInvitations,clipboardAttempts:window.clipboardAttempts}));
   if(mode==='cancel'){
    assert.equal(calls.shared.length,1);assert.deepEqual(calls.copied,[]);assert.deepEqual(calls.clipboardAttempts,[]);
    assert.equal(calls.shared[0].payload.text,invitationMessages.service);
   }else{
    assert.equal(calls.shared.length,mode==='error'?1:0);
    assert.deepEqual(calls.copied,[invitationMessages.service+'\n\n'+`${origin}/api/v1/referrals/join/${code}?kind=service`]);
   }
   assert.equal(f.requests.length,before);
   assert.equal(f.requests.some(r=>r.method!=='GET'),false);
  }finally{await f.context.close();}
 }
});
test('plain-link copying stays separate and denied invitation clipboard reveals a selected readonly text fallback',async()=>{
 for(const denied of [false,true]){
  const f=await fixture();try{
   await shareProbe(f.page,denied?'clipboard-denied':'unavailable');
   await f.page.evaluate(()=>ReferralFeatures.openPersonal('service'));
   const url=`${origin}/api/v1/referrals/join/${code}?kind=service`;
   const invitationText=invitationMessages.service+'\n\n'+url;
   const urlField=f.page.getByRole('textbox',{name:'Odkaz pozvánky',exact:true});
   const textField=f.page.getByLabel('Text pozvánky s odkazem',{exact:true});
   assert.equal(await urlField.inputValue(),url);
   assert.equal(await textField.count(),1);assert.equal(await textField.isVisible(),false);
   if(!denied){
    await f.page.getByRole('button',{name:'Kopírovat odkaz',exact:true}).click();
    assert.deepEqual(await f.page.evaluate(()=>window.copiedInvitations),[url]);
    assert.equal(await textField.isVisible(),false);
    assert.deepEqual(await f.page.evaluate(()=>window.sharedInvitations),[]);
   }else{
    await f.page.getByRole('button',{name:'Sdílet pozvánku',exact:true}).click();
    assert.deepEqual(await f.page.evaluate(()=>window.copiedInvitations),[]);
    assert.deepEqual(await f.page.evaluate(()=>window.clipboardAttempts),[invitationText]);
    assert.equal(await textField.isVisible(),true);assert.equal(await textField.inputValue(),invitationText);
    assert.equal(await textField.evaluate(el=>el.readOnly),true);
    assert.equal(await textField.evaluate(el=>el.selectionEnd-el.selectionStart),invitationText.length);
    assert.match(await f.page.locator('.referral-notice').innerText(),/ručně/);
   }
   assert.equal(await urlField.inputValue(),url);
   assert.equal(f.requests.some(r=>r.method!=='GET'),false);
  }finally{await f.context.close();}
 }
});
test('a late clipboard result after changing invite kind never claims the new invitation was copied or selected',async()=>{
 for(const outcome of ['resolve','reject']){
  const f=await fixture();try{
   await f.page.evaluate(()=>{
    window.clipboardAttempts=[];
    Object.defineProperty(navigator,'share',{configurable:true,value:undefined});
    Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:text=>{
     window.clipboardAttempts.push(text);
     return new Promise((resolve,reject)=>{window.pendingClipboard={resolve,reject};});
    }}});
   });
   await f.page.evaluate(()=>ReferralFeatures.openPersonal('user'));
   const oldField=await f.page.getByLabel('Text pozvánky s odkazem',{exact:true}).elementHandle();
   assert.equal(await oldField.evaluate(el=>el.hidden),true);
   await f.page.getByRole('button',{name:'Sdílet pozvánku',exact:true}).click();
   await f.page.waitForFunction(()=>Boolean(window.pendingClipboard));
   const before=f.requests.length;
   await f.page.locator('select').selectOption('service');
   assert.equal(await oldField.evaluate(el=>el.isConnected),false);
   await f.page.evaluate(async outcome=>{
    if(outcome==='resolve')window.pendingClipboard.resolve();
    else window.pendingClipboard.reject(new DOMException('Clipboard permission denied','NotAllowedError'));
    await new Promise(resolve=>setTimeout(resolve,0));
   },outcome);
   const currentField=f.page.getByLabel('Text pozvánky s odkazem',{exact:true});
   assert.equal(await currentField.isVisible(),false);
   assert.equal(await oldField.evaluate(el=>el.hidden),true);
   assert.equal(await f.page.locator('.referral-notice').isVisible(),false);
   assert.equal(await f.page.locator('.referral-notice').textContent(),'');
   assert.equal(await f.page.getByRole('textbox',{name:'Odkaz pozvánky',exact:true}).inputValue(),`${origin}/api/v1/referrals/join/${code}?kind=service`);
   assert.equal(await currentField.inputValue(),invitationMessages.service+'\n\n'+`${origin}/api/v1/referrals/join/${code}?kind=service`);
   assert.deepEqual(await f.page.evaluate(()=>window.clipboardAttempts),[invitationMessages.user+'\n\n'+`${origin}/api/v1/referrals/join/${code}?kind=user`]);
   assert.equal(f.requests.length,before);
   assert.equal(f.requests.some(r=>r.method!=='GET'),false);
  }finally{await f.context.close();}
 }
});
test('server-confirmed user role cannot open admin controls or fetch the admin list',async()=>{
 const f=await fixture();try{
  await f.page.evaluate(()=>ReferralFeatures.openAdmin());
  assert.match(await f.page.locator('.referral-notice').innerText(),/pouze administrátorovi/);
  assert.equal(f.requests.length,1);assert.equal(f.requests[0].path,'/user/me');
  assert.equal(await f.page.getByRole('button',{name:'Přidělit odměnu',exact:true}).count(),0);
 }finally{await f.context.close();}
});
test('wrong customer reply is rejected and attacker strings render as text, not markup',async()=>{
 let wrong=true;
 const f=await fixture({respond:async(route,req)=>{
  if(req.path!=='/api/v1/referrals/me')return false;
  const data=summary(wrong?80:7);data.name='<img src=x onerror="window.injected=1">';data.rules='<script>window.injected=2</script>';
  await route.fulfill({json:data});return true;
 }});try{
  await f.page.evaluate(()=>ReferralFeatures.openPersonal());
  assert.match(await f.page.locator('.referral-notice').innerText(),/požadovaného účtu/);
  wrong=false;await f.page.getByRole('button',{name:'Načíst znovu',exact:true}).click();
  await f.page.waitForSelector('canvas');
  assert.match(await f.page.locator('dialog').innerText(),/<img src=x/);
  assert.equal(await f.page.locator('dialog img, dialog script').count(),0);assert.equal(await f.page.evaluate(()=>window.injected),undefined);
 }finally{await f.context.close();}
});
test('late success after account switch or closing the dialog never renders',async()=>{
 for(const close of [false,true]){
  let release;const waiting=new Promise(resolve=>release=resolve);let started;const requested=new Promise(resolve=>started=resolve);
  const f=await fixture({respond:async(route,req)=>{if(req.path!=='/api/v1/referrals/me')return false;started();await waiting;await route.fulfill({json:summary()}).catch(()=>{});return true;}});
  try{
   await f.page.evaluate(()=>{void ReferralFeatures.openPersonal();});await requested;
   if(close)await f.page.getByRole('button',{name:'Zavřít',exact:true}).click();else await f.page.evaluate(()=>AdminBrowserSession.changeAccount());
   release();await f.page.waitForTimeout(650);
   assert.equal(await f.page.locator('dialog').count(),0);assert.doesNotMatch(await f.page.locator('body').innerText(),/Testovací účet|Čekající odměna/);
  }finally{release();await f.context.close();}
 }
});
test('admin search pagination, explicit confirmation, stable retry UUID, and revocation history',async()=>{
 let attempts=0,granted=null,revoked=false;
 const f=await fixture({role:'admin',viewport:{width:1280,height:900},respond:async(route,req)=>{
  if(req.path==='/api/v1/referrals/admin/40' && req.method==='GET'){
   const data={...summary(40),name:'Admin target',email:'target@example.invalid'};
   if(granted)data.rewards.unshift({...granted,...(revoked?{revoked_at:'2026-11-03T15:00:00'}:{})});
   await route.fulfill({json:data});return true;
  }
  if(req.path==='/api/v1/referrals/admin/40/rewards' && req.method==='POST'){
   attempts++;if(attempts===1){await route.fulfill({status:503,json:{detail:'Syntetická nejistá odpověď'}});return true;}
   granted={id:80,source:'admin',starts_at:'2026-11-03T12:00:00',ends_at:null,lifetime:true,waiting_for_paid:false,reason:req.body.reason};await route.fulfill({json:granted});return true;
  }
  if(req.path==='/api/v1/referrals/admin/40/rewards/80/revoke'){
   revoked=true;await route.fulfill({json:{...granted,revoked_at:'2026-11-03T15:00:00'}});return true;
  }
  return false;
 }});try{
  await f.page.evaluate(()=>ReferralFeatures.openAdmin());
  await f.page.getByRole('button',{name:'Další',exact:true}).click();
  await f.page.waitForFunction(()=>document.querySelector('nav')?.textContent.includes('Strana 2'));
  assert.equal(f.requests.some(r=>r.search.includes('offset=30')),true);
  await f.page.getByRole('searchbox').fill('Test + email');await f.page.getByRole('searchbox').press('Enter');
  await f.page.waitForFunction(()=>document.querySelector('nav')?.textContent.includes('Strana 1'));
  assert.equal(f.requests.some(r=>new URLSearchParams(r.search).get('search')==='Test + email'),true);
  await f.page.getByRole('button',{name:'Otevřít přehled účtu'}).click();
  await f.page.waitForSelector('[data-referral-reason="grant"]');
  assert.match(await f.page.locator('dialog').innerText(),/SECRET PERSON|private@example.invalid/);
  assert.equal(await f.page.getByRole('heading',{name:'Tři kroky k bonusu Premium',exact:true}).count(),0);
  assert.equal(await f.page.getByRole('button',{name:'Sdílet pozvánku',exact:true}).count(),0);
  await f.page.getByRole('button',{name:'Přidělit odměnu',exact:true}).click();
  assert.match(await f.page.locator('.referral-notice').innerText(),/5 až 500/);assert.equal(attempts,0);
  await f.page.locator('[data-referral-reason="grant"]').fill('Schválená testovací odměna');
  await f.page.locator('select').selectOption('lifetime');await f.page.getByRole('button',{name:'Přidělit odměnu',exact:true}).click();
  assert.equal(attempts,0);await f.page.locator('.referral-confirm').getByRole('button',{name:'Zrušit',exact:true}).click();assert.equal(attempts,0);
  await f.page.getByRole('button',{name:'Přidělit odměnu',exact:true}).click();await f.page.getByRole('button',{name:'Potvrdit přidělení',exact:true}).click();
  await f.page.waitForFunction(()=>document.querySelector('.referral-notice').textContent.includes('stejné potvrzení'));
  await f.page.getByRole('button',{name:'Znovu ověřit stejné přidělení',exact:true}).click();
  await f.page.waitForSelector('[data-reward-id="80"]');
  const posts=f.requests.filter(r=>r.path.endsWith('/40/rewards')&&r.method==='POST');
  assert.equal(posts.length,2);assert.equal(posts[0].body.request_id,posts[1].body.request_id);assert.match(posts[0].body.request_id,/^[a-f0-9-]{36}$/);assert.equal(posts[1].body.kind,'lifetime');
  await f.page.locator('[data-reward-id="80"]').getByRole('button',{name:'Odebrat odměnu',exact:true}).click();
  await f.page.locator('[data-referral-reason="revoke"]').fill('Oprava testovacího přidělení');await f.page.getByRole('button',{name:'Potvrdit odebrání',exact:true}).click();
  await f.page.locator('.referral-confirm').getByRole('button',{name:'Odebrat odměnu',exact:true}).click();
  await f.page.waitForFunction(()=>document.querySelector('[data-reward-id="80"]')?.textContent.includes('Odměna odebrána'));
  assert.equal(await f.page.locator('[data-reward-id="80"]').count(),1);
  assert.equal(f.requests.some(r=>r.path.includes('/upgrade')||r.path.includes('/billing')),false);
 }finally{await f.context.close();}
});
