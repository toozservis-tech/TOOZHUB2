// Account-first support timeline. Use textContent for every server-supplied value.
let activityActor = null, activitySnapshot = null, activityGeneration = 0;
let activitySelection = {hours:'24', failures:'false', role:'all', search:''};
const activityElement = id => document.getElementById(id);
function activityNode(tag, text, className = '') {
  const node = document.createElement(tag); node.textContent = text; node.className = className; return node;
}
function activityCount(count, one, few, many) {
  return `${count} ${count===1?one:count>=2&&count<=4?few:many}`;
}
function activityStamp(raw) {
  const date = new Date(raw);
  return Number.isNaN(date.getTime()) ? 'Neznámý čas' : date.toLocaleString('cs-CZ', {timeZone:'Europe/Prague'});
}
function activitySummary(row) {
  if (row.ui_label) return row.ui_label;
  const events = {login_success:'Úspěšné přihlášení',login_failed:'Neúspěšné přihlášení',
    login_2fa_success:'Potvrzené dvoufázové ověření',login_2fa_failed:'Neúspěšné ověření',
    request_completed:'Dokončený požadavek',request_failed:'Chyba požadavku',
    api_activity:'Aktivita aplikace',login_blocked_ip:'Blokovaný přístup',login_rate_limited:'Příliš mnoho pokusů'};
  const paths = [['/vehicles','Vozidla'],['/reservations','Rezervace'],['/reminders','Připomínky'],
    ['/license','Tarify a předplatné'],['/user/me','Profil'],['/user/login','Přihlášení'],['/service-record','Servisní záznamy']];
  const operation = paths.find(([path]) => (row.endpoint || '').includes(path));
  return (events[row.event_type] || row.event_type || 'Událost') + (operation ? ' · '+operation[1] : '');
}
function activityStatus(row) {
  const severity = ['success','warning','error'].includes(row.severity) ? row.severity : 'success';
  return activityNode('strong', {success:'✓ Bez zaznamenaného problému',warning:'⚠ Upozornění',error:'✕ Zaznamenaná chyba'}[severity], 'activity-severity '+severity);
}
function activityPager(id, offset, total, load) {
  const container = activityElement(id); container.replaceChildren();
  for (const [label, next, disabled] of [['Předchozí',offset-50,offset===0],['Další',offset+50,offset+50>=total]]) {
    const button = activityNode('button', label, 'btn-secondary'); button.type='button'; button.disabled=disabled;
    button.addEventListener('click',()=>load(next)); container.append(button);
  }
  container.append(activityNode('span', `Strana ${Math.floor(offset/50)+1} · celkem ${total}`));
}
async function loadActivityAccounts(offset = 0) {
  const generation = ++activityGeneration; activityActor=null; activitySnapshot=null;
  activityElement('activity-detail').hidden=true;
  activityElement('activity-accounts').hidden=false; activityElement('activity-pages').hidden=false;
  activityElement('activity-filters').hidden=false;
  activityElement('activity-status').textContent='Načítám aktivitu…';
  activityElement('activity-accounts').replaceChildren(); activityElement('activity-pages').replaceChildren();
  activitySelection = {search:activityElement('activity-search').value,role:activityElement('activity-role').value,
    hours:activityElement('activity-hours').value,failures:String(activityElement('activity-problems').checked)};
  try {
    const data=await apiRequest('GET','/admin-api/control-center/access-accounts?'+new URLSearchParams({...activitySelection,limit:'50',offset:String(offset)}));
    if (generation!==activityGeneration) return;
    activityElement('activity-status').textContent=`${activityCount(data.total,'účet','účty','účtů')} · ${activitySelection.failures==='true'?'pouze problémy':'všechny aktivity'}`;
    for (const row of data.items) {
      const card=activityNode('button','', 'activity-account'); card.type='button';
      card.append(activityNode('h2',row.name||row.actor),activityNode('p',row.actor),activityStatus(row),
        activityNode('p','Poslední aktivita: '+activityStamp(row.created_at)),activityNode('p',activitySummary(row)),
        activityNode('p',`${activityCount(row.event_count,'událost','události','událostí')} · ${activityCount(row.problem_count,'problém','problémy','problémů')}`),activityNode('strong','Zobrazit aktivitu →'));
      card.addEventListener('click',()=>{activityActor=row.actor;activitySnapshot=null;activityElement('activity-kind').value='all';loadActivityDetail(0);});
      activityElement('activity-accounts').append(card);
    }
    if (!data.items.length) activityElement('activity-accounts').append(activityNode('p','Pro tento výběr nejsou zaznamenané události.'));
    activityPager('activity-pages',offset,data.total,loadActivityAccounts);
  } catch(error) { if(generation===activityGeneration) activityElement('activity-status').textContent=error.message||'Aktivitu se nepodařilo načíst.'; }
}
async function loadActivityDetail(offset=0) {
  const generation=++activityGeneration;
  activityElement('activity-detail').hidden=false; activityElement('activity-accounts').hidden=true;
  activityElement('activity-pages').hidden=true; activityElement('activity-filters').hidden=true;
  activityElement('activity-actor').textContent=activityActor;
  activityElement('activity-detail-problems').checked=activitySelection.failures==='true';
  activityElement('activity-status').textContent='Načítám historii účtu…';
  activityElement('activity-timeline').replaceChildren(); activityElement('activity-detail-pages').replaceChildren();
  const query=new URLSearchParams({actor:activityActor,hours:activitySelection.hours,failures:activitySelection.failures,
    kind:activityElement('activity-kind').value,limit:'50',offset:String(offset)});
  if (activitySnapshot) query.set('before_id',String(activitySnapshot));
  try {
    const data=await apiRequest('GET','/admin-api/control-center/access-history?'+query);
    if(generation!==activityGeneration) return;
    activitySnapshot=data.snapshot_id;
    activityElement('activity-status').textContent=`${activityCount(data.total,'událost','události','událostí')} · nejnovější nahoře`;
    for(const row of data.items) {
      const card=activityNode('article','', 'activity-event');
      card.append(activityStatus(row),activityNode('p',activityStamp(row.created_at)),activityNode('h3',activitySummary(row)));
      if(row.ui_label) card.append(activityNode('p','Nahlášeno aplikací · čas ze zařízení. Přijato serverem '+activityStamp(row.received_at)));
      if(row.status) card.append(activityNode('p','Výsledek serveru: HTTP '+row.status));
      if(row.reason) card.append(activityNode('p','Důvod: '+row.reason));
      const details=activityNode('details',''); details.append(activityNode('summary','Technické podrobnosti'));
      for(const [title,key] of [['Operace','endpoint'],['Záznam','resource'],['IP adresa','ip_address'],['Verze aplikace','app_version'],['Sestavení','app_build'],['ID požadavku','request_id']]) {
        if(row[key]) details.append(activityNode('p',title+': '+row[key]));
      }
      card.append(details); activityElement('activity-timeline').append(card);
    }
    if(!data.items.length) activityElement('activity-timeline').append(activityNode('p','Pro tento výběr nejsou zaznamenané události. Pro širší kontext zvolte všechny události.'));
    activityPager('activity-detail-pages',offset,data.total,loadActivityDetail);
  } catch(error) { if(generation===activityGeneration) activityElement('activity-status').textContent=error.message||'Historii se nepodařilo načíst.'; }
}
document.addEventListener('DOMContentLoaded',()=>{
  activityElement('activity-filters').addEventListener('submit',event=>{event.preventDefault();loadActivityAccounts();});
  for(const id of ['activity-role','activity-hours','activity-problems']) activityElement(id).addEventListener('change',()=>loadActivityAccounts());
  activityElement('activity-back').addEventListener('click',()=>loadActivityAccounts());
  activityElement('activity-kind').addEventListener('change',()=>{activitySnapshot=null;loadActivityDetail();});
  activityElement('activity-detail-problems').addEventListener('change',()=>{activitySelection.failures=String(activityElement('activity-detail-problems').checked);activitySnapshot=null;loadActivityDetail();});
});
