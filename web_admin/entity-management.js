/* Administrator operations, explicit review, authenticated API, no inline code from records. */
(() => {
  'use strict';
  const labels = {vehicle:'Vozidlo', service_records:'Servisní záznamy', reservations:'Rezervace', reminders:'Připomínky', service_intakes:'Příjem do servisu',
    vehicle_ownerships:'Vlastníci', vehicle_service_links:'Oprávnění servisů', service_vehicle_access:'Dřívější oprávnění', service_access_requests:'Žádosti o přístup',
    vehicle_tachometer_history_entries:'Historie STK a kilometrů', vehicle_orv_scans:'Doklady ORV', vehicle_ownership_archives:'Archiv vlastnictví',
    merged_profiles:'Sjednocené původní profily', service_record_audit_logs:'Historie úprav záznamů', vehicle_attachment_privacy:'Soukromé přílohy',
    id:'Číslo záznamu', nickname:'Název', brand:'Značka', model:'Model', plate:'SPZ', vin:'VIN', engine:'Motor', year:'Rok výroby',
    notes:'Poznámka', current_mileage_km:'Stav tachometru', stk_valid_until:'Platnost STK', insurance_provider:'Pojišťovna', insurance_valid_until:'Platnost pojištění',
    tyres_info:'Pneumatiky', performed_at:'Datum úkonu', description:'Popis práce', mileage:'Nájezd', price:'Cena', note:'Poznámka', category:'Kategorie',
    text:'Text', due_date:'Termín', type:'Typ', is_completed:'Dokončena', service_type:'Požadované práce', start_datetime:'Začátek', end_datetime:'Konec', status:'Stav',
    odometer_km:'Stav tachometru', work_description:'Práce', damage_description:'Poškození', fluids_ok:'Kapaliny v pořádku',
    street:'Ulice', street_number:'Číslo popisné / orientační', city:'Město', zip:'PSČ'};
  const fields = {
    vehicle: ['nickname','brand','model','year','plate','vin','engine','notes','current_mileage_km','stk_valid_until','insurance_provider','insurance_valid_until','tyres_info'],
    service_records: ['performed_at','description','mileage','price','note','category'],
    reservations: ['service_type','note','start_datetime','end_datetime','status'],
    reminders: ['type','text','due_date','is_completed'],
    service_intakes: ['odometer_km','work_description','damage_description','fluids_ok']
  };
  const routes = {vehicle:'vehicles',service_records:'records',reservations:'reservations',reminders:'reminders',service_intakes:'service-intakes'};
  const bools = new Set(['is_completed','fluids_ok']);
  const numbers = new Set(['year','mileage','current_mileage_km','odometer_km','price']);
  let generation = 0;
  function node(tag, text, className) { const n=document.createElement(tag); if(text!==undefined)n.textContent=text; if(className)n.className=className; return n; }
  function action(title, callback) { const b=node('button',title,'btn-secondary'); b.type='button'; b.addEventListener('click',callback); return b; }
  function modal(title) {
    document.getElementById('management-modal')?.remove(); const version=++generation; const session=AdminBrowserSession.snapshot();
    const overlay=node('div',undefined,'modal'); overlay.id='management-modal'; overlay.setAttribute('role','dialog'); overlay.setAttribute('aria-modal','true');
    const panel=node('div',undefined,'modal-content'); panel.style.maxWidth='1000px'; panel.style.maxHeight='90vh'; panel.style.overflowY='auto';
    const heading=node('div',undefined,'modal-header'); heading.append(node('h2',title),action('Zavřít',()=>{++generation;overlay.remove();}));
    const body=node('div',undefined,'modal-body'); panel.append(heading,body); overlay.append(panel); document.body.append(overlay);
    heading.querySelector('button').focus();
    return {body, session, alive:()=>{try{AdminBrowserSession.assertCurrent(session);}catch{return false;}return generation===version && overlay.isConnected;}};
  }
  function display(value) { if(value===null || value===undefined)return '—'; if(typeof value==='boolean')return value?'Ano':'Ne'; if(typeof value==='object')return JSON.stringify(value,null,2); return String(value); }
  function values(parent, object) {
    const dl=node('dl'); for(const [key,value] of Object.entries(object)) { dl.append(node('dt',labels[key]||key.replaceAll('_',' ')),node('dd',display(value))); }
    parent.append(dl);
  }
  function editor(parent, kind, row, refresh, session) {
    const form=node('form'); const inputs=new Map();
    for(const key of fields[kind]) {
      const label=node('label',labels[key]||key); const input=bools.has(key)?node('select'):node('input');
      if(bools.has(key)) { for(const [v,t] of [...(key==='fluids_ok'?[['','Nehodnotit']]:[]),['true','Ano'],['false','Ne']]) {const o=node('option',t);o.value=v;input.append(o);} }
      else { input.type=numbers.has(key)?'number':key.endsWith('_datetime')||key==='performed_at'?'datetime-local':key.endsWith('_until')||key==='due_date'?'date':'text'; if(numbers.has(key)){input.min='0';input.step=key==='price'?'0.01':'1';} }
      if(key==='status') { input.setAttribute('list','reservation-states'); const list=node('datalist');list.id='reservation-states';for(const state of ['PENDING','CONFIRMED','CANCELLED','COMPLETED']){const o=node('option');o.value=state;list.append(o);}form.append(list); }
      if(key==='fluids_ok'){let assessment={};try{assessment=JSON.parse(row[key]||'{}');}catch{}input.value=typeof assessment?.overall_ok==='boolean'?String(assessment.overall_ok):'';}
      else if(input.type==='datetime-local' && row[key]) {
        // Server stores naive UTC. Browser controls show local time, then convert back.
        const d=new Date(String(row[key]).endsWith('Z')?row[key]:String(row[key])+'Z');
        input.value=new Date(d.getTime()-d.getTimezoneOffset()*60000).toISOString().slice(0,16);
      } else input.value=row[key]===null||row[key]===undefined?'':String(row[key]).slice(0,input.type==='date'?10:100000);
      inputs.set(key,input);label.append(input);form.append(label);
    }
    const submit=node('button','Uložit změny','btn-primary');submit.type='submit';const status=node('p');form.append(submit,status);
    form.addEventListener('submit',async e=>{
      e.preventDefault(); if(submit.disabled)return; const payload={};
      for(const [key,input] of inputs) {
        const raw=input.value.trim();
        if(bools.has(key)){if(raw)payload[key]=raw==='true';}
        else if(numbers.has(key)){if(raw)payload[key]=Number(raw);}
        else if(input.type==='datetime-local'){if(raw)payload[key]=new Date(raw).toISOString();}
        else if(input.type==='date')payload[key]=raw||null;
        else payload[key]=raw;
      }
      if(!confirm('Uložit zobrazené změny? Původní údaje zůstávají v historii změn.'))return;
      try{AdminBrowserSession.assertCurrent(session);}catch(error){status.textContent=error.message;return;}
      submit.disabled=true;
      try { await apiRequest('PATCH',`/admin-api/${routes[kind]}/${row.id}`,payload);status.textContent='Změny uloženy.';await refresh(); }
      catch(error){status.textContent=error.message;}finally{submit.disabled=false;}
    }); parent.append(form);
  }
  async function vehicleDetail(identity) {
    const m=modal('Kompletní vozidlo a související události');m.body.append(node('p','Načítám…'));
    async function refresh(){
      const data=await apiRequest('GET',`/admin-api/vehicles/${identity}/detail`); if(!m.alive())return;
      m.body.replaceChildren();
      for(const [kind,entries] of Object.entries(data)) {
        const section=node('details');const rows=Array.isArray(entries)?entries:[entries];
        section.append(node('summary',`${labels[kind]||kind.replaceAll('_',' ')} (${rows.length})`));if(kind==='vehicle')section.open=true;
        for(const row of rows){const card=node('article',undefined,'card');values(card,row);
          if(fields[kind] && row.merged_into_id==null){const edit=node('details');edit.append(node('summary','Upravit údaje'));editor(edit,kind,row,refresh,m.session);card.append(edit);}
          if(kind==='service_records') {
            let files=[];try{files=JSON.parse(row.attachments||'[]');}catch{}
            for(const file of files){const key=file.storage_key||file.path;if(typeof key!=='string')continue;
              card.append(action('Otevřít přílohu: '+(file.filename||file.name||'doklad'),async()=>{
                try{const response=await AdminBrowserSession.request(`/api/v1/vehicles/${identity}/records/attachments/download?key=${encodeURIComponent(key)}`,{},m.session);
                  if(!response.ok)throw new Error('Přílohu se nepodařilo načíst.');const url=URL.createObjectURL(await response.blob());window.open(url,'_blank','noopener');setTimeout(()=>URL.revokeObjectURL(url),60000);
                }catch(e){showGlobalError(e.message);}
              }));}
          }
          if(kind==='merged_profiles')card.append(action('Otevřít původní archiv',()=>vehicleDetail(row.id)));
          section.append(card);
        }m.body.append(section);
      }
    }
    try{await refresh();}catch(e){if(m.alive())m.body.replaceChildren(node('p',e.message));}
  }
  async function duplicates() {
    const m=modal('Kontrola duplicitních vozidel');m.body.append(node('p','Procházím všechna vozidla…'));
    try{
      const report=await apiRequest('GET','/admin-api/vehicles/duplicates');if(!m.alive())return;m.body.replaceChildren();
      m.body.append(node('p',`Prověřeno ${report.checked_vehicles} vozidel. Nalezeno ${report.total} skupin. Kontrola žádná data nemění.`));
      for(const group of report.groups){const section=node('section',undefined,'card');section.append(node('h3',`${group.kind.toUpperCase()}: ${group.key}`),node('p',group.explanation));
        for(const target of group.vehicles){const card=node('article');card.append(node('h4',`Hlavní profil #${target.id}: ${target.plate||'Bez SPZ'} — ${target.owner_email}`),node('p',`${target.record_count} servisních záznamů`),action('Otevřít vozidlo',()=>vehicleDetail(target.id)));
          if(group.merge_allowed)for(const source of group.vehicles.filter(v=>v.id!==target.id))card.append(action(`Připravit sjednocení #${source.id} do #${target.id}`,()=>prepareMerge(source.id,target.id)));
          section.append(card);
        }m.body.append(section);
      }
    }catch(e){if(m.alive())m.body.replaceChildren(node('p',e.message));}
  }
  async function prepareMerge(source,target) {
    const m=modal('Náhled sjednocení vozidel');
    try {
      const preview=await apiRequest('GET',withQueryParams('/admin-api/vehicles/merge-preview',{source_id:source,target_id:target}));if(!m.alive())return;
      m.body.append(node('p',`Původní profil #${source} → hlavní #${target}. Vlastník hlavního profilu: ${preview.target.owner_email}.`));
      for(const warning of preview.warnings)m.body.append(node('p',warning));values(m.body,preview.counts);
      const reason=node('textarea');reason.placeholder='Důvod sjednocení (alespoň 3 znaky)';reason.maxLength=1000;
      const label=node('label','Zkontroloval/a jsem oba profily a potvrzuji, že jde o stejné vozidlo.');const ack=node('input');ack.type='checkbox';label.prepend(ack);
      const status=node('p');const submit=action('Sjednotit vozidla',async()=>{
        if(submit.disabled)return;submit.disabled=true;
        try{AdminBrowserSession.assertCurrent(m.session);await apiRequest('POST','/admin-api/vehicles/merge',{source_id:source,target_id:target,preview_token:preview.preview_token,confirmed_identity:ack.checked,reason:reason.value.trim()});
          if(m.alive()){m.body.replaceChildren(node('p','Sjednocení bylo dokončeno. Původní profil zůstává archivovaný.'),action('Zkontrolovat znovu',duplicates));}await loadVehicles();
        }catch(e){status.textContent=e.message;submit.disabled=false;}
      });submit.disabled=true;const ready=()=>{submit.disabled=!ack.checked || reason.value.trim().length<3;};ack.addEventListener('change',ready);reason.addEventListener('input',ready);m.body.append(reason,label,submit,status);
    }catch(e){if(m.alive())m.body.append(node('p',e.message));}
  }
  async function workshop(identity) {
    const m=modal('Sídlo firmy a skutečná provozovna');
    try{
      const data=await apiRequest('GET',`/api/v1/services/${identity}/workshop`);if(!m.alive())return;
      m.body.append(node('h3','Sídlo firmy'),node('p',Object.values(data.registered).filter(Boolean).join(', ')),node('p','Provozovnu používáme uvnitř přihlášené aplikace, aby zákazníci našli skutečné místo oprav. Adresu nezveřejňujeme ve veřejném webovém seznamu. Sídlo zůstává zvlášť pro firemní a fakturační údaje.'));
      const label=node('label','Provozovna je totožná se sídlem firmy');const same=node('input');same.type='checkbox';same.checked=data.workshop.workshop_same_as_registered===true;label.prepend(same);
      const form=node('form');const custom=node('div');const inputs={};
      for(const key of ['street','street_number','city','zip']){const l=node('label',labels[key]);const input=node('input');input.value=data.workshop['workshop_'+key]||'';inputs[key]=input;l.append(input);custom.append(l);}
      const update=()=>{custom.hidden=same.checked;};same.addEventListener('change',update);update();const submit=node('button','Uložit provozovnu','btn-primary');submit.type='submit';const status=node('p');form.append(label,custom,submit,status);m.body.append(form);
      form.addEventListener('submit',async e=>{e.preventDefault();if(submit.disabled)return;submit.disabled=true;
        try{AdminBrowserSession.assertCurrent(m.session);const payload={workshop_same_as_registered:same.checked};for(const [k,i] of Object.entries(inputs))payload['workshop_'+k]=i.value.trim();
          await apiRequest('PUT',`/api/v1/services/${identity}/workshop`,payload);status.textContent='Provozovna uložena. Vyhledávání používá tuto adresu.';
        }catch(e){status.textContent=e.message;}finally{submit.disabled=false;}
      });
    }catch(e){if(m.alive())m.body.append(node('p',e.message));}
  }
  document.addEventListener('click',event=>{
    const button=event.target.closest('[data-management-action]');if(!button)return;const id=Number(button.dataset.id);
    if(button.dataset.managementAction==='duplicates')duplicates();
    else if(Number.isSafeInteger(id)&&id>0){if(button.dataset.managementAction==='vehicle-detail')vehicleDetail(id);if(button.dataset.managementAction==='workshop')workshop(id);}
  });
})();
