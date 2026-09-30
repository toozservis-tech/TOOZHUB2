/* Plain-language administration built on the existing authorized API. */
const operatorPending = new Set();
const operatorJobs = {
  'privacy.files.erase': {
    title: 'Odstranění soukromých souborů',
    description: 'Dokončuje již potvrzené žádosti o odstranění souborů a při výpadku úložiště je opakuje.',
    impact: 'Zpracuje jeden soubor, jehož odstranění už bylo potvrzeno. Nevytváří novou žádost o smazání účtu.',
    pause: 'Dokončování potvrzených žádostí nelze pozastavit.'
  },
  'apple.subscription.reconcile': {
    title: 'Předplatné v App Storu',
    description: 'Ověřuje aktuální předplatné přímo u Applu a doplňuje změny při opožděném oznámení.',
    impact: 'Zkontroluje naplánovaná předplatná a podle ověřeného výsledku upraví dostupnost tarifu. Nevyvolává platbu ani neposílá e-maily.',
    pause: 'Zastaví pravidelnou kontrolu App Storu. Podepsaná oznámení od Applu se nadále zpracovávají.'
  },
  'license.subscription.cycle': {
    title: 'Předplatné a licence',
    description: 'Kontroluje končící předplatné, obnovuje licence a zpracovává související platby.',
    impact: 'Může obnovit předplatné, vyvolat opakovanou platbu, změnit tarif a odeslat upozornění zákazníkům.',
    pause: 'Automatické obnovy a upozornění předplatného se nebudou zpracovávat.'
  },
  'reminders.notification.check': {
    title: 'Připomínky termínů',
    description: 'Prověřuje blížící se termíny u vozidel a odesílá připomínky podle nastavení uživatelů.',
    impact: 'Může odeslat skutečné e-maily zákazníkům s blížícím se termínem.',
    pause: 'Automatické odesílání připomínek termínů se do obnovení přeruší.'
  }
};
function opElement(tag, text, className) {
  const el = document.createElement(tag);
  if (text != null) el.textContent = text;
  if (className) el.className = className;
  return el;
}
function opResult(id, message, error=false) {
  const el=document.getElementById(id); if(!el)return;
  el.classList.add('operator-result');el.replaceChildren(opElement('p',message));
  el.classList.toggle('operator-error',error);
  el.setAttribute('role',error?'alert':'status');
}
function opButton(title, description, action, disabled=false) {
  const b=opElement('button',null,'btn-secondary operator-action'); b.type='button';b.disabled=disabled;
  b.append(opElement('strong',title),opElement('small',description)); b.onclick=action;return b;
}
function operatorConfirm({title,description,confirmLabel='Potvrdit změnu',reason=false,password=false,danger=false}) {
  if(document.getElementById('operator-confirm'))return Promise.resolve(null);
  return new Promise(resolve=>{
    const previous=document.activeElement,dialog=opElement('dialog',null,'operator-dialog');dialog.id='operator-confirm';
    const form=document.createElement('form');form.method='dialog';
    const heading=opElement('h2',title);heading.id='operator-dialog-title';dialog.setAttribute('aria-labelledby',heading.id);
    const descriptionEl=opElement('p',description);descriptionEl.id='operator-dialog-description';dialog.setAttribute('aria-describedby',descriptionEl.id);
    form.append(heading,descriptionEl);let reasonInput,passInput;
    if(password){const label=opElement('label','Nové heslo (nepovinné)');passInput=document.createElement('input');passInput.type='password';passInput.autocomplete='new-password';passInput.minLength=6;passInput.maxLength=72;label.append(passInput);form.append(label,opElement('p','Nechte prázdné pro vygenerování dočasného hesla. Vyplněné heslo musí mít alespoň 6 znaků.','operator-hint'));}
    if(reason){const label=opElement('label','Důvod změny');reasonInput=document.createElement('textarea');reasonInput.required=true;reasonInput.minLength=3;reasonInput.maxLength=1000;reasonInput.rows=3;label.append(reasonInput);form.append(label);}
    if(danger){const label=opElement('label',null,'operator-check');const box=document.createElement('input');box.type='checkbox';box.required=true;label.append(box,opElement('span','Rozumím popsanému dopadu a chci akci provést.'));form.append(label);}
    const actions=opElement('div',null,'operator-dialog-actions');const cancel=opElement('button','Zrušit','btn-secondary');cancel.type='button';cancel.onclick=()=>dialog.close();const submit=opElement('button',confirmLabel,danger?'btn-danger':'btn-primary');submit.type='submit';actions.append(cancel,submit);form.append(actions);dialog.append(form);document.body.append(dialog);
    let answer=null;
    form.onsubmit=e=>{e.preventDefault();if(reasonInput&&reasonInput.value.trim().length<3){reasonInput.setCustomValidity('Napište alespoň 3 znaky důvodu.');reasonInput.reportValidity();return;}answer={reason:reasonInput?.value.trim()||null,password:passInput?.value||''};dialog.close();};
    if(reasonInput)reasonInput.oninput=()=>reasonInput.setCustomValidity('');
    dialog.addEventListener('close',()=>{dialog.remove();previous?.focus();resolve(answer);},{once:true});dialog.showModal();(danger?cancel:(reasonInput||submit)).focus();
  });
}
async function opAction(key,resultId,fn) {
  if(operatorPending.has(key))return;
  operatorPending.add(key);const buttons=[...document.querySelectorAll(`[data-operation="${key}"]`)];const previous=buttons.map(b=>b.disabled);buttons.forEach(b=>b.disabled=true);
  try{return await fn();}catch(error){opResult(resultId,`Akci se nepodařilo dokončit: ${error.message}`,true);}
  finally{operatorPending.delete(key);buttons.forEach((b,i)=>b.disabled=previous[i]);}
}
function operatorJobView(job) {
  if(job.available===false)return {label:'Čeká na dokončení nastavení',resume:false,pause:false,run:false,note:job.unavailable_reason||'Propojení služby zatím není připravené.'};
  if(!job.env_enabled)return {label:'Automatika vypnutá na serveru',resume:false,pause:false,run:!job.is_paused, note:'Tlačítko jednorázové kontroly automatiku nezapíná. Pravidelný běh musí nejprve povolit správce nasazení serveru.'};
  if(job.pause_supported===false)return {label:'Automatika zapnutá',resume:false,pause:false,run:true,note:'Dokončování již potvrzených žádostí běží automaticky a nelze je pozastavit.'};
  if(job.is_paused)return {label:'Pozastavená',resume:true,pause:false,run:false,note:'Nejdříve obnovte automatiku. Potom můžete spustit jednorázovou kontrolu.'};
  return {label:'Automatika zapnutá',resume:false,pause:true,run:true,note:'Jde o nastavení pravidelného běhu; tento údaj nepotvrzuje dokončení poslední kontroly.'};
}
function renderOperatorJobs(data) {
  const container=document.getElementById('operator-jobs');if(!container)return;container.replaceChildren();
  const jobs=Array.isArray(data?.jobs)?data.jobs:[];
  for(const job of jobs){const meta=operatorJobs[job.name];if(!meta)continue;const view=operatorJobView(job),card=opElement('section',null,'operator-job');
    card.append(opElement('h4',meta.title),opElement('p',meta.description),opElement('strong',view.label,'operator-job-status'),opElement('p',`Interval: přibližně každých ${Math.ceil(job.interval_seconds/60)} minut. ${view.note}`,'operator-hint'));
    if(Number.isInteger(job.pending_count))card.append(opElement('p',`Soubory čekající na odstranění: ${job.pending_count}`));
    if(job.pause_reason)card.append(opElement('p',`Důvod pozastavení: ${job.pause_reason}`));
    if(job.last_success_at)card.append(opElement('p',`Poslední ověřené předplatné: ${new Date(job.last_success_at).toLocaleString('cs-CZ')}`));
    if(Number(job.retry_count)>0)card.append(opElement('p',`Kontroly čekající na opakování: ${job.retry_count}`,'operator-error'));
    const actions=opElement('div',null,'operator-job-actions');
    for(const [action,label,hint,allowed] of [['run','Provést kontrolu nyní',meta.impact,view.run],['pause','Pozastavit automatiku',meta.pause,view.pause],['resume','Obnovit automatiku','Povolí další naplánované kontroly. Jednorázovou kontrolu nespouští.',view.resume]]){
      const button=opButton(label,hint,()=>operatorJobAction(job.name,action),!allowed||operatorPending.has('job:'+job.name));button.dataset.operation='job:'+job.name;actions.append(button);
    }card.append(actions);container.append(card);
  }
  if(!container.children.length)container.append(opElement('p','Seznam automatických kontrol není dostupný. Zkuste jej aktualizovat.'));
}
async function operatorJobAction(name,action) {
  const meta=operatorJobs[name];if(!meta||!['run','pause','resume'].includes(action))return;
  if(!controlCenterDataState.jobs)await loadControlCenterJobs();
  const job=controlCenterDataState.jobs?.jobs?.find(j=>j.name===name);if(!job){opResult('cc-job-action-result','Nejprve načtěte stav automatických kontrol.',true);return;}
  if(!operatorJobView(job)[action]){opResult('cc-job-action-result','Tato akce není v aktuálním stavu dostupná. Aktualizujte přehled.',true);return;}
  await opAction('job:'+name,'cc-job-action-result',async()=>{
    const label={run:'Provést kontrolu nyní',pause:'Pozastavit automatiku',resume:'Obnovit automatiku'}[action];
    const answer=await operatorConfirm({title:`${label}: ${meta.title}`,description:action==='run'?meta.impact:action==='pause'?meta.pause:'Automatické kontroly budou opět povolené podle nastavení serveru.',confirmLabel:label,reason:action!=='run',danger:true});if(!answer)return;
    opResult('cc-job-action-result',`${meta.title}: požadavek se zpracovává. Vyčkejte na výsledek.`);
    const data=await apiRequest('POST',`/admin-api/control-center/jobs/${action}`,{job_name:name,...(answer.reason?{reason:answer.reason}:{})});
    const summary=data.result||{};let message=action==='run'?'Jednorázová kontrola dokončena.':action==='pause'?'Automatické kontroly byly pozastaveny.':'Automatické kontroly byly znovu povoleny.';
    const labels={removed:'Odstraněné soubory',retrying:'Soubory čekající na opakování',checked_reminders:'Prověřené připomínky',checked_auto_stk:'Prověřené termíny STK',notifications_sent:'Odeslaná oznámení',email_notifications_sent:'Z toho e-mailem',push_notifications_sent:'Z toho do telefonu',renewal_success:'Obnovená předplatná',renewal_failed:'Neúspěšné obnovy',downgraded_free:'Převedeno na bezplatný tarif',notified:'Odeslaná upozornění',cancel_finalized:'Ukončená předplatná',errors:'Chyby',sent:'Odesláno',failed:'Neodesláno',checked:'Zkontrolováno'};
    const counts=Object.entries(labels).filter(([k])=>typeof summary[k]==='number').map(([k,label])=>`${label}: ${summary[k]}`);
    const partial=Number(summary.retrying||0)>0||Number(summary.errors||0)>0||Number(summary.failed||0)>0||Number(summary.renewal_failed||0)>0;
    if(partial)message='Kontrola skončila s problémy. Prověřte níže uvedený výsledek.';
    opResult('cc-job-action-result',`${meta.title}: ${message} ${counts.join('. ')}`,partial);await loadControlCenterJobs();
  });
  renderOperatorJobs(controlCenterDataState.jobs);
}
loadControlCenterJobs = async function(){
  try {const data=await apiRequest('GET','/admin-api/control-center/jobs');setControlCenterState('jobs',data);renderOperatorJobs(data);renderControlCenterTable('cc-jobs-table',[{key:'title',label:'Automatická kontrola'},{key:'state',label:'Nastavení'},{key:'interval',label:'Interval'}],data.jobs.filter(j=>operatorJobs[j.name]).map(j=>({title:operatorJobs[j.name].title,state:operatorJobView(j).label,interval:`${Math.ceil(j.interval_seconds/60)} minut`})));}
  catch(e){document.getElementById('operator-jobs')?.replaceChildren(opElement('p','Stav kontrol se nepodařilo načíst. Použijte „Aktualizovat běh úloh“.'));opResult('cc-job-action-result',e.message,true);}
};
function opFillSelect(id,rows,label,empty='Vyberte…') {
  const el=document.getElementById(id);if(!el)return;const previous=el.value;
  el.replaceChildren(new Option(empty,''));for(const row of rows)el.append(new Option(label(row),String(row.id)));
  if([...el.options].some(o=>o.value===previous))el.value=previous;
}
function operatorUserChoices(){
  const users=Array.isArray(controlCenterDataState.users)?controlCenterDataState.users:[];
  const query=(document.getElementById('operator-user-search')?.value||'').toLocaleLowerCase('cs');
  opFillSelect('cc-insight-user-id',users.filter(u=>`${u.name||''} ${u.email||''}`.toLocaleLowerCase('cs').includes(query)),u=>`${u.name||'Bez jména'} — ${u.email}`,'Vyberte účet…');
  opFillSelect('cc-restore-user-id',users,u=>`${u.name||'Bez jména'} — ${u.email}`,'Vyberte účet…');
  operatorSelectedUser();operatorRecipientChoices();
}
function operatorRecipientChoices(){
  const type=document.getElementById('cc-broadcast-target-type')?.value,users=controlCenterDataState.users||[],select=document.getElementById('cc-broadcast-target-value');if(!select)return;
  select.disabled=type==='all';
  if(type==='all')opFillSelect(select.id,[],x=>x,'Všichni uživatelé');
  else if(type==='plan')opFillSelect(select.id,[{id:'free',name:'Zdarma'},{id:'basic',name:'Základní'},{id:'premium',name:'Premium'}],r=>r.name,'Vyberte tarif…');
  else if(type==='user')opFillSelect(select.id,users,u=>`${u.name||'Bez jména'} — ${u.email}`,'Vyberte účet…');
  else {const tenants=[...new Map(users.filter(u=>u.tenant_id).map(u=>[u.tenant_id,{id:u.tenant_id,name:`${u.name||u.email} — organizace č. ${u.tenant_id}`}])).values()];opFillSelect(select.id,tenants,r=>r.name,'Vyberte organizaci…');}
}
const operatorOriginalSetState=setControlCenterState;
setControlCenterState=function(key,value){operatorOriginalSetState(key,value);if(key==='users')operatorUserChoices();if(key==='backups'){opFillSelect('cc-restore-backup-id',(value.items||[]).map(r=>({...r,id:r.backup_id})),r=>`${formatDateTime(r.created_at)} — ${r.backup_id}`,'Vyberte zálohu…');}};
function operatorSelectedUser(){
  const s=document.getElementById('cc-insight-user-id');if(!s)return;
  document.getElementById('operator-selected-user').textContent=s.value?`Akce se týkají účtu: ${s.selectedOptions[0].textContent}`:'Nejprve vyberte účet, kterého se má akce týkat.';
}
function operatorUser(){const id=getControlCenterSelectedUserId();const user=(controlCenterDataState.users||[]).find(u=>String(u.id)===String(id));if(!user){showGlobalError('Vyberte účet podle jména nebo e-mailu.');return null;}return user;}
async function operatorAccountAction(action){const user=operatorUser();if(!user)return;
  const definitions={disable:['Pozastavit účet','Uživatel se nebude moci přihlásit. Jeho data zůstanou zachovaná.'],enable:['Znovu povolit účet','Uživatel opět získá přístup ke svému účtu.'],'force-logout':['Odhlásit všechna zařízení','Všechna současná přihlášení uživatele přestanou platit.'],'reset-password':['Nastavit dočasné heslo','Dosavadní heslo přestane platit a aktivní přihlášení budou ukončena. Nové heslo se zobrazí pouze zde.']};const [title,description]=definitions[action];
  await opAction('account','operator-account-result',async()=>{const answer=await operatorConfirm({title,description:`Účet: ${user.name||''} (${user.email}). ${description}`,confirmLabel:title,reason:true,password:action==='reset-password',danger:true});if(!answer)return;
    const payload={reason:answer.reason};if(action==='reset-password')Object.assign(payload,{new_password:answer.password||null,generate_random:!answer.password});
    opResult('operator-account-result','Ukládám změnu účtu…');const data=await apiRequest('POST',`/admin-api/control-center/users/${user.id}/${action}`,payload);
    opResult('operator-account-result',`${title}: dokončeno pro ${user.email}.`);
    if(data.temporary_password){const el=document.getElementById('operator-account-result');el.append(opElement('p','Dočasné heslo předejte bezpečným způsobem:'),opElement('code',data.temporary_password));el.append(opButton('Skrýt heslo','Odstraní heslo z této obrazovky.',()=>opResult(el.id,'Heslo bylo skryto.')));}
    await loadControlCenterUsersSnapshot();
  });
}
disableUserFromControlCenter=()=>operatorAccountAction('disable');enableUserFromControlCenter=()=>operatorAccountAction('enable');forceLogoutFromControlCenter=()=>operatorAccountAction('force-logout');resetUserPasswordFromControlCenter=()=>operatorAccountAction('reset-password');
runControlCenterPaymentResync=()=>operatorJobAction('license.subscription.cycle','run');
updateUserLicenseFromControlCenter=async()=>{const user=operatorUser();if(!user)return;const plan=document.getElementById('cc-license-plan'),status=document.getElementById('cc-license-status');if(!plan.value&&!status.value){showGlobalError('Vyberte tarif nebo stav licence, který chcete změnit.');return;}await opAction('license','operator-account-result',async()=>{const answer=await operatorConfirm({title:'Změnit licenci',description:`Účet ${user.email}. Tarif: ${plan.selectedOptions[0].textContent}. Stav: ${status.selectedOptions[0].textContent}. Změna ovlivní dostupné funkce aplikace.`,reason:true,danger:true,confirmLabel:'Uložit licenci'});if(!answer)return;await apiRequest('POST',`/admin-api/control-center/users/${user.id}/license`,{plan:plan.value||null,status:status.value||null,source:'developer_override',reason:answer.reason});opResult('operator-account-result',`Licence účtu ${user.email} byla změněna.`);await loadControlCenterUsersSnapshot();});};
broadcastControlCenterNotification=async()=>{const message=document.getElementById('cc-broadcast-message').value.trim(),title=document.getElementById('cc-broadcast-title').value.trim(),type=document.getElementById('cc-broadcast-target-type').value,select=document.getElementById('cc-broadcast-target-value');if(message.length<3){showGlobalError('Napište zprávu alespoň se 3 znaky.');return;}if(type!=='all'&&!select.value){showGlobalError('Vyberte příjemce oznámení.');return;}await opAction('broadcast','cc-notifications-result',async()=>{if(!await operatorConfirm({title:'Zveřejnit oznámení',description:`Příjemci: ${select.selectedOptions[0].textContent}.\n${title}\n${message}`,danger:true,confirmLabel:'Zveřejnit v aplikaci'}))return;await apiRequest('POST','/admin-api/control-center/notifications/broadcast',{message,title:title||null,target_type:type,target_value:type==='all'?null:select.value,severity:'info'});await loadControlCenterNotifications();opResult('cc-notifications-result','Oznámení bylo zveřejněno vybraným příjemcům.');});};
runControlCenterStorageCleanup=async()=>opAction('cleanup','cc-infra-result',async()=>{const preview=await apiRequest('GET','/admin-api/control-center/storage/cleanup-preview?logs_days=30&backups_days=30');if(!preview.old_logs_count&&!preview.old_backups_count){opResult('cc-infra-result','Nebyly nalezeny žádné staré místní soubory k odstranění.');return;}if(!await operatorConfirm({title:'Odstranit staré místní soubory',description:`Nenávratně se odstraní ${preview.old_logs_count} provozních souborů (${preview.old_logs_human}) a ${preview.old_backups_count} místních záloh (${preview.old_backups_human}) starších 30 dnů. Účty, vozidla a jejich fotografie tato akce nemaže.`,danger:true,confirmLabel:'Odstranit uvedené soubory'}))return;const data=await apiRequest('POST','/admin-api/control-center/storage/cleanup',{confirm_text:preview.confirm_text_required,delete_old_logs_days:30,delete_old_backups_days:30});await loadControlCenterStorage();setControlCenterResult('cc-infra-result',data);opResult('cc-infra-result',data.errors?.length?'Úklid skončil s chybami. Otevřete podklady pro podporu.':'Úklid byl dokončen.',Boolean(data.errors?.length));});
restoreControlCenterBackup=async()=>{if(controlCenterDataState.backups?.local_snapshot_supported===false)return;const backup=document.getElementById('cc-restore-backup-id'),scope=document.getElementById('cc-restore-scope'),userId=getNumberValue('cc-restore-user-id'),vehicleId=getNumberValue('cc-restore-vehicle-id');if(!backup.value||(scope.value==='user'&&!userId)||(scope.value==='vehicle'&&!vehicleId)){showGlobalError('Vyberte zálohu a účet nebo vozidlo podle rozsahu obnovy.');return;}await opAction('restore','cc-backup-result',async()=>{if(!await operatorConfirm({title:'Obnovit data ze zálohy',description:`Záloha: ${backup.selectedOptions[0].textContent}. Rozsah: ${scope.selectedOptions[0].textContent}. ${scope.value==='user'?document.getElementById('cc-restore-user-id').selectedOptions[0].textContent:scope.value==='vehicle'?document.getElementById('cc-restore-vehicle-id').selectedOptions[0].textContent:''} Současná vybraná data se přepíší.`,danger:true,confirmLabel:'Obnovit a přepsat vybraná data'}))return;await apiRequest('POST','/admin-api/control-center/backups/restore',{backup_id:backup.value,scope:scope.value,user_id:userId,vehicle_id:vehicleId,confirm_text:'PROCEED_RESTORE'});opResult('cc-backup-result','Obnova vybraných dat byla dokončena.');await loadOverview();});};
for(const [name,action] of [['blockIpFromControlCenter','block-ip'],['unblockIpFromControlCenter','unblock-ip']])window[name]=async()=>{const ip=document.getElementById('cc-block-ip').value.trim(),reason=document.getElementById('cc-block-reason').value.trim();if(!ip||reason.length<3){showGlobalError('Vyberte nebo vyplňte adresu a napište důvod alespoň se 3 znaky.');return;}await opAction('ip','cc-security-result',async()=>{if(!await operatorConfirm({title:action==='block-ip'?'Zablokovat přístup z adresy':'Povolit přístup z adresy',description:`Adresa: ${ip}. Důvod: ${reason}. Změna se týká všech osob připojených přes tuto adresu.`,danger:true}))return;await apiRequest('POST',`/admin-api/control-center/security/${action}`,{ip_address:ip,reason});await loadControlCenterSecurityMonitor();opResult('cc-security-result','Změna přístupu byla uložena.');});};
const originalSaveSettings=saveAllSettings;
saveAllSettings=async()=>{if(await operatorConfirm({title:'Uložit nastavení',description:'Upravené hodnoty v aktuální kategorii se zapíší do nastavení aplikace. Konfigurace nasazení serveru se tím nemění.',confirmLabel:'Uložit změny'}))await originalSaveSettings();};
resetSettingsCategory=()=>{renderSettingsCategory(currentSettingsCategory);showSuccess('Neuložené změny v této kategorii byly zahozeny.');};
const originalRenderSettings=renderSettingsCategory;
renderSettingsCategory=function(category){originalRenderSettings(category);const area=document.getElementById('settings-categories');area?.querySelectorAll('input[data-key],select[data-key],textarea[data-key]').forEach(el=>{if(el.type==='number'){el.min='0';}const item=el.closest('.setting-item');const key=el.dataset.key;const help={jwt_expiration_hours:'Jak dlouho může zůstat přihlášení platné. Běžná obsluha tuto hodnotu nemusí měnit.',cors_origins:'Seznam povolených webových adres je spravován v nasazení serveru.',backup_enabled:'Tato historická volba sama nezapne cloudové zálohování. Použijte sekci Zálohy a obnova.',autostart_enabled:'Týká se původní aplikace pro počítač; cloudový server tímto tlačítkem nespustíte.'};if(help[key])item?.append(opElement('p',help[key],'operator-hint'));});};
function initOperatorPanel(){
  const users=document.getElementById('cc-module-users');if(users&&!document.getElementById('operator-account-result')){const el=opElement('div',null,'operator-result');el.id='operator-account-result';el.setAttribute('role','status');users.append(el);}
  document.getElementById('operator-user-search')?.addEventListener('input',operatorUserChoices);document.getElementById('cc-insight-user-id')?.addEventListener('change',operatorSelectedUser);document.getElementById('cc-broadcast-target-type')?.addEventListener('change',operatorRecipientChoices);
  document.getElementById('cc-restore-scope')?.addEventListener('change',async()=>{const scope=document.getElementById('cc-restore-scope').value;document.getElementById('cc-restore-user-id').disabled=scope!=='user';document.getElementById('cc-restore-vehicle-id').disabled=scope!=='vehicle';if(scope==='vehicle'){try{const rows=await fetchAllList('/admin-api/vehicles');opFillSelect('cc-restore-vehicle-id',rows,r=>`${r.plate||'Bez SPZ'} — ${r.brand||''} ${r.model||''} ${r.nickname||''}`);}catch(e){showGlobalError('Seznam vozidel se nepodařilo načíst.');}}});
  document.getElementById('cc-restore-user-id').disabled=true;document.getElementById('cc-restore-vehicle-id').disabled=true;
  for(const [key,names] of Object.entries({account:['disableUserFromControlCenter','enableUserFromControlCenter','forceLogoutFromControlCenter','resetUserPasswordFromControlCenter'],license:['updateUserLicenseFromControlCenter'],broadcast:['broadcastControlCenterNotification'],cleanup:['runControlCenterStorageCleanup'],restore:['restoreControlCenterBackup'],ip:['blockIpFromControlCenter','unblockIpFromControlCenter']}))for(const name of names)document.querySelectorAll(`[onclick="${name}()"]`).forEach(b=>b.dataset.operation=key);
  operatorUserChoices();if(controlCenterDataState.jobs)renderOperatorJobs(controlCenterDataState.jobs);
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',initOperatorPanel);else initOperatorPanel();

initDefaultSettings=async()=>{if(!await operatorConfirm({title:'Doplnit chybějící nastavení',description:'Doplní nové položky doporučenými hodnotami. Uložené hodnoty včetně nastavení e-mailů a plateb zůstanou zachované.',confirmLabel:'Doplnit položky'}))return;try{await apiRequest('POST','/admin-api/settings/init-defaults');await loadSettings();showSuccess('Chybějící položky byly doplněny.');}catch(e){showGlobalError(e.message);}};
