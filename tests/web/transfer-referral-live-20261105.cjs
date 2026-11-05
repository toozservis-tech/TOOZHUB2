// Real product JavaScript -> loopback FastAPI -> synthetic SQLite; no production credentials/mail.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE);
const origin=process.env.TRANSFER_QA_ORIGIN||'http://127.0.0.1:18915';
if(new URL(origin).hostname!=='127.0.0.1')throw Error('Only local synthetic fixture is allowed.');
const output=path.resolve(process.env.TRANSFER_QA_OUTPUT||'/tmp/transfer-referral-web-qa');fs.mkdirSync(output,{recursive:true});
const checks=[];
async function get(path,token){const r=await fetch(origin+path,{headers:token?{Authorization:'Bearer '+token}:{}});assert.equal(r.status,200,await r.clone().text());return r.json();}
async function main(){
 const browser=await chromium.launch({channel:'chrome',headless:true});
 const context=await browser.newContext({viewport:{width:390,height:844},locale:'cs-CZ'});
 await context.route('**/*',route=>new URL(route.request().url()).origin===origin?route.continue():route.abort());
 const page=await context.newPage();const exceptions=[];page.on('pageerror',e=>exceptions.push(e.message));
 const setup=(await get('/qa/setup')).web;const vehicle=setup.vehicles.active;
 async function role(value){await page.goto(origin+'/qa/client');await page.waitForSelector('body[data-ready="true"]');await page.locator('#account').selectOption(value);}
 async function close(){const d=page.locator('dialog.referral-dialog:not(.referral-confirm)');if(await d.count())await d.getByRole('button',{name:'Zavřít',exact:true}).click();}
 async function confirm(name){await page.locator('.referral-confirm').getByRole('button',{name,exact:true}).click();}
 async function accept(id){
  const code=await (await fetch(origin+'/qa/mail-code?buyer_email=web-buyer@example.com')).text();
  const card=page.locator(`[data-transfer-id="${id}"]`);await card.getByLabel('Kód z poslední pozvánky').fill(code);
  await card.getByRole('button',{name:'Převzít vozidlo',exact:true}).click();await confirm('Potvrdit převzetí');
  await page.waitForFunction(id=>document.querySelector(`[data-transfer-id="${id}"]`)?.textContent.includes('Převzato novým majitelem'),id);
 }
 try{
  await role('seller');await page.locator('#manage').click();await page.getByRole('button',{name:'Prodat vozidlo',exact:true}).click();
  await page.getByLabel('E-mail nového majitele · povinné').fill('web-buyer@example.com');
  await page.getByRole('button',{name:'Pokračovat k potvrzení prodeje',exact:true}).click();
  assert.equal((await get('/qa/assertions?group=web')).owners[String(vehicle)],'web-seller@example.com');
  await confirm('Potvrdit prodej');await page.getByRole('heading',{name:'Změna potvrzena'}).waitFor();
  let state=await get('/qa/assertions?group=web');assert.equal(state.owners[String(vehicle)],undefined);assert.equal(state.invitations.find(x=>x.vehicle_id===vehicle).status,'pending');
  const first=state.invitations.find(x=>x.vehicle_id===vehicle).id;
  checks.push('Seller email form and explicit confirmation; pending invitation grants no ownership');
  await page.getByRole('button',{name:'Zobrazit pozvánku'}).click();await page.locator(`[data-transfer-id="${first}"]`).waitFor();
  assert.match(await page.locator(`[data-transfer-id="${first}"]`).innerText(),/E-mail předán/);await close();
  await role('buyer');await page.locator('#inbox').click();const card=page.locator(`[data-transfer-id="${first}"]`);await card.waitFor();
  await card.getByLabel('Kód z poslední pozvánky').fill('a'.repeat(32));await card.getByRole('button',{name:'Převzít vozidlo',exact:true}).click();await confirm('Potvrdit převzetí');
  await page.getByRole('alert').filter({hasText:'Kód z pozvánky není platný'}).waitFor();assert.equal((await get('/qa/assertions?group=web')).owners[String(vehicle)],undefined);
  checks.push('Wrong email code rejected by actual API; pending invitation unchanged');
  await accept(first);state=await get('/qa/assertions?group=web');assert.equal(state.owners[String(vehicle)],'web-buyer@example.com');
  await page.screenshot({path:path.join(output,'buyer-accepted.png'),fullPage:true});await close();
  await role('buyer');await page.locator('#inbox').click();await page.locator(`[data-transfer-id="${first}"]`).waitFor();assert.match(await page.locator(`[data-transfer-id="${first}"]`).innerText(),/Převzato novým/);await close();
  assert.equal((await get('/api/v1/vehicle-archives','qa-web-buyer')).length,0);
  checks.push('Buyer confirms, sees result after page reload; private seller archive absent');
  await role('seller');await page.locator('#referrals').click();const detail=page.locator('details[data-referral-id]').first();await detail.waitFor();
  assert.match(await page.locator('dialog').innerText(),/web-buyer@example.com/);await detail.locator('summary').click();assert.match(await detail.innerText(),/Ověření e-mailu: Dokončeno/);assert.match(await detail.innerText(),/Podmínky splněny/);
  await page.screenshot({path:path.join(output,'referral-detail.png'),fullPage:true});assert.equal(await page.locator('dialog').evaluate(el=>el.scrollWidth<=el.clientWidth),true);await close();
  checks.push('Direct verified referral identity and qualification detail are visible and fit narrow viewport');
  await page.locator('#legacy').click();await page.getByLabel('E-mail nového majitele',{exact:true}).fill('web-buyer@example.com');await page.getByRole('button',{name:'Připravit pozvánku',exact:true}).click();await confirm('Poslat pozvánku');
  await page.getByRole('heading',{name:'Vámi odeslané pozvánky'}).waitFor();state=await get('/qa/assertions?group=web');const legacy=state.invitations.find(x=>x.vehicle_id===setup.vehicles.legacy);assert.equal(legacy.status,'pending');await close();
  await role('buyer');await page.locator('#inbox').click();await page.locator(`[data-transfer-id="${legacy.id}"]`).waitFor();await accept(legacy.id);await close();
  checks.push('Previously sold archived car can be invited by seller and accepted without admin');
  await role('admin');await page.locator('#review').click();await page.getByLabel('E-mail nového majitele',{exact:true}).fill('web-buyer@example.com');await page.getByLabel('Jak jste vlastnictví ověřili · povinné').fill('Syntetický test: převod doložen účastníky.');await page.getByRole('checkbox').check();await page.getByRole('button',{name:'Připravit ověřený převod',exact:true}).click();
  assert.equal((await get('/qa/assertions?group=web')).owners[String(setup.vehicles.admin)],'web-seller@example.com');await confirm('Potvrdit ověřený převod');await page.getByRole('heading',{name:'Pozvánka je připravená'}).waitFor();
  state=await get('/qa/assertions?group=web');const adminInvite=state.invitations.find(x=>x.vehicle_id===setup.vehicles.admin);assert.equal(adminInvite.status,'pending');assert.equal(state.owners[String(setup.vehicles.admin)],undefined);await close();
  await role('buyer');await page.locator('#inbox').click();await page.locator(`[data-transfer-id="${adminInvite.id}"]`).waitFor();await accept(adminInvite.id);await close();
  checks.push('Admin verified exception requires reason, acknowledgment, final confirmation and still buyer consent');
  await role('stranger');await page.locator('#inbox').click();await page.getByRole('heading',{name:'Vámi odeslané pozvánky'}).waitFor();assert.equal(await page.locator('[data-transfer-id]').count(),0);await close();await page.locator('#referrals').click();await page.getByRole('heading',{name:'Pozvané účty'}).waitFor();assert.doesNotMatch(await page.locator('dialog').innerText(),/web-buyer@example.com/);await close();
  checks.push('Unrelated account sees neither transfer nor referral identity');
  assert.deepEqual(exceptions,[]);const result={status:'PASS',date:new Date().toISOString(),origin,database:'synthetic shared fixture',checks,assertions:await get('/qa/assertions?group=web')};fs.writeFileSync(path.join(output,'result.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result,null,2));
 }catch(error){await page.screenshot({path:path.join(output,'failure.png'),fullPage:true});fs.writeFileSync(path.join(output,'failure.txt'),error.stack+'\n'+await page.locator('body').innerText());throw error;}
 finally{await context.close();await browser.close();}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
