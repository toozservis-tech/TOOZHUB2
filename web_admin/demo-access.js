let demoGeneration = 0;
const demoLabels = {verified:'E-mail ověřen · vstup povolen', sent:'Kód odeslán · čeká na ověření', sending:'Odesílání probíhá', delivery_failed:'Kód se nepodařilo odeslat', expired:'Platnost kódu skončila', superseded:'Nahrazen novým kódem', locked:'Vyčerpány pokusy o ověření'};
async function loadDemoAccess(offset=0) {
  const generation=++demoGeneration;
  const get=id=>document.getElementById(id);
  get('demo-status').textContent='Načítám vstupy do dema…';
  get('demo-items').replaceChildren(); get('demo-pages').replaceChildren();
  try {
    const data=await apiRequest('GET','/admin-api/control-center/demo-access?'+new URLSearchParams({search:get('demo-search').value,status:get('demo-status-filter').value,limit:'50',offset:String(offset)}));
    if(generation!==demoGeneration)return;
    get('demo-status').textContent=`Počet žádostí: ${data.total} · posledních ${data.retention_days} dní`;
    for(const row of data.items){
      const card=activityNode('article','','activity-event');
      const severity=row.status==='verified'?'success':['delivery_failed','locked'].includes(row.status)?'error':'warning';
      card.append(activityNode('h2',row.email),activityNode('strong',demoLabels[row.status]||'Stav není známý','activity-severity '+severity));
      for(const [label,key] of [['Žádost o kód','requested_at'],['Kód odeslán','sent_at'],['E-mail ověřen','verified_at']]) {
        if(row[key])card.append(activityNode('p',label+': '+activityStamp(row[key])));
      }
      card.append(activityNode('p','Pokusů o ověření: '+row.attempts));get('demo-items').append(card);
    }
    if(!data.items.length)get('demo-items').append(activityNode('p','Žádné odpovídající vstupy do dema.'));
    activityPager('demo-pages',offset,data.total,loadDemoAccess);
  }catch(error){if(generation===demoGeneration)get('demo-status').textContent='Přehled se nepodařilo načíst. '+error.message;}
}
document.getElementById('demo-filters').addEventListener('submit',event=>{event.preventDefault();loadDemoAccess();});
document.getElementById('demo-status-filter').addEventListener('change',()=>loadDemoAccess());
