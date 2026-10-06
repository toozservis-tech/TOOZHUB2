/* Customer web extensions. Authorization and tier limits remain server-owned. */
(function (global) {
    'use strict';
    const documentNumber = value => /^[A-Z]{2,3}[0-9]{6}$/.test(String(value).trim().toUpperCase()) ? String(value).trim().toUpperCase() : null;
    const registryPayload = value => {
        const clean = String(value).trim().toUpperCase();
        if (/^[A-HJ-NPR-Z0-9]{17}$/.test(clean)) return {vin: clean};
        const orv = documentNumber(clean);
        if (orv) return {orv};
        throw new Error('Zadejte platný VIN (17 znaků) nebo číslo ORV (2–3 písmena a 6 číslic).');
    };
    const registryFields = v => ({vehicleVin: v.vin, vehiclePlate: v.plate, vehicleBrand: v.brand,
        vehicleModel: v.model, vehicleYear: v.production_year ?? v.year, vehicleEngine: v.engine ?? v.fuel,
        vehicleEngineCode: v.engine_code, vehicleMaxPower: v.engine_power_kw, vehicleType: v.type_label,
        vehicleStkDate: v.stk_valid_until, vehicleTyres: v.tyres_info});
    if (typeof module !== 'undefined') module.exports = {documentNumber, registryPayload, registryFields};
    if (!global.document || !global.CustomerWeb) return;
    const $ = id => document.getElementById(id);
    const session = () => global.AdminBrowserSession;
    const h = value => global.escapeHtml(String(value ?? ''));
    const money = value => value == null ? 'Nezadáno' : new Intl.NumberFormat('cs-CZ', {style:'currency',currency:'CZK'}).format(value);
    const date = value => value ? new Date(value).toLocaleDateString('cs-CZ') : 'Nezadáno';
    let draft = null, loadVersion = 0;
    async function request(path, method = 'GET', body) {
        const captured=session().snapshot();
        let r;
        try { r = await session().request(path, {method, timeoutMs:path.endsWith('/parse-orv')?90000:30000, ...(body === undefined ? {} : {headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})}); }
        catch(e) { session().assertCurrent(captured); if(e.name==='AbortError')throw new Error('Server neodpověděl včas. Zkuste akci znovu.'); throw e; }
        const data = r.status === 204 ? null : await r.json();
        if (!r.ok) { const e = new Error(typeof data?.detail === 'string' ? data.detail : data?.detail?.message || data?.error?.message || 'Požadavek se nepodařilo dokončit.'); e.status=r.status; throw e; }
        return data;
    }
    function showError(message) {
        const body=document.querySelector('#customerFeatureDialog .customer-feature-body');
        if(!body){global.showAlert(message,'error');return;}
        let error=body.querySelector('[data-feature-error]');
        if(!error){error=document.createElement('p');error.dataset.featureError='1';error.setAttribute('role','alert');body.prepend(error);}
        error.textContent=message;error.scrollIntoView({block:'nearest'});
    }
    function action(label, fn, secondary = true) {
        const b = document.createElement('button'); b.type='button'; b.className=secondary?'btn-secondary':'btn'; b.textContent=label;
        b.addEventListener('click', async () => {if(b.disabled)return; b.disabled=true; try {await fn();} catch(e) {if(e.name!=='AbortError') showError(e.message);} finally {b.disabled=false;}}); return b;
    }
    function confirmAction(message) {
        const captured=session().snapshot();
        return new Promise(resolve=>{
            const dialog=document.createElement('dialog');dialog.className='customer-feature-dialog';
            const body=document.createElement('div');body.className='customer-feature-body';
            const text=document.createElement('p');text.textContent=message;body.append(text);
            dialog.setAttribute('aria-label','Potvrzení');
            let result=false;
            body.append(action('Zrušit',()=>dialog.close()),action('Potvrdit',()=>{result=true;dialog.close();},false));
            dialog.append(body);document.body.append(dialog);
            dialog.addEventListener('close',()=>{dialog.remove();try{session().assertCurrent(captured);resolve(result);}catch{resolve(false);}},{once:true});dialog.showModal();
        });
    }
    function input(label, id, type='text', value='') {
        const wrap=document.createElement('label'); wrap.className='customer-field'; wrap.textContent=label;
        const el=document.createElement('input'); el.type=type; el.id=id; el.value=value ?? ''; wrap.append(el); return wrap;
    }
    function panel(title) {
        $('customerFeatureDialog')?.remove();
        const dialog=document.createElement('dialog'); dialog.id='customerFeatureDialog';dialog.setAttribute('aria-label',title); dialog.className='customer-feature-dialog';
        const head=document.createElement('header'), heading=document.createElement('h2');heading.textContent=title;
        head.append(heading,action('Zavřít',()=>dialog.close()));
        const body=document.createElement('div');body.className='customer-feature-body';dialog.append(head,body);document.body.append(dialog);
        dialog.addEventListener('close',()=>dialog.remove());dialog.showModal();return body;
    }
    function card(title, content) {return `<article class="customer-feature-card"><h3>${h(title)}</h3>${content}</article>`;}
    function tierError(container, e) {
        container.textContent=e.message;
        if(e.status===403 && /premium|basic|tarif|feature|plan|licen/i.test(e.message)) container.append(action('Zobrazit tarify',()=>global.openLicensePlans()));
    }
    async function download(path, name) {
        const r=await session().request(path); if(!r.ok) throw new Error('Soubor není dostupný pro tento účet nebo tarif.');
        const blob=await r.blob(), url=URL.createObjectURL(blob), a=document.createElement('a'); a.href=url;a.download=name;a.hidden=true;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);
    }
    async function overview() {
        const target=$('customerOverviewTab'), version=++loadVersion, captured=session().snapshot();target.innerHTML='<p role="status">Načítám přehled…</p>';
        try {
            const [vehicles, reminders, reservations]=await Promise.all([request('/api/v1/vehicles'),request('/api/v1/reminders'),request('/api/v1/reservations')]);
            session().assertCurrent(captured);if(version!==loadVersion)return;
            const reminderRows=Array.isArray(reminders)?reminders:reminders.items||[], reservationRows=Array.isArray(reservations)?reservations:reservations.items||[];
            target.innerHTML='<h2>Přehled</h2><div class="customer-feature-grid">'+card('Vozidla',`<strong>${vehicles.length}</strong>`)+card('Připomínky',`<strong>${reminderRows.filter(x=>!x.is_completed).length}</strong>`)+card('Rezervace',`<strong>${reservationRows.length}</strong>`)+ '</div><div id="customerOverviewActions" class="customer-feature-actions"></div><section id="customerAnalytics"><h3>Náklady a statistiky</h3><div id="customerAnalyticsData" role="status">Načítám…</div></section>';
            $('customerOverviewActions').append(action('Přidat vozidlo',()=>global.switchTab('addVehicle')),action('Připomínky',()=>global.switchTab('reminders')),action('Rezervace',()=>global.switchTab('reservations')),action('Obnovit přehled',overview));
            await analytics($('customerAnalyticsData'));
        } catch(e) {if(e.name!=='AbortError' && version===loadVersion) tierError(target,e);}
    }
    async function analytics(container, vehicleId) {
        const captured=session().snapshot(), q=vehicleId?`?vehicle_id=${Number(vehicleId)}`:'';
        try {
            const [summary,monthly,categories]=await Promise.all([request('/api/v1/analytics/summary'+q),request('/api/v1/analytics/monthly-costs'+(q?q+'&':'?')+'months=12'),request('/api/v1/analytics/categories'+q)]);
            session().assertCurrent(captured);if(!container.isConnected)return;
            container.innerHTML='<div class="customer-feature-grid">'+card('Celkové náklady',`<strong>${h(money(summary.total_cost_czk))}</strong><p>${summary.priced_records} oceněných záznamů z ${summary.total_records}</p>`)+card('Průměr za záznam',`<strong>${h(money(summary.average_cost_czk))}</strong>`)+ '</div><h4>Posledních 12 měsíců</h4><div class="customer-table"><table><thead><tr><th>Měsíc</th><th>Záznamy</th><th>Náklady</th></tr></thead><tbody>'+monthly.entries.map(x=>`<tr><td>${h(x.label)}</td><td>${x.records_count}</td><td>${h(money(x.total_cost_czk))}</td></tr>`).join('')+'</tbody></table></div><h4>Podle kategorie</h4>'+categories.categories.map(x=>card(x.category,`${x.records_count} záznamů · ${h(money(x.total_cost_czk))}`)).join('');
        } catch(e){if(e.name!=='AbortError'&&container.isConnected)tierError(container,e);}
    }
    async function archives() {
        const target=$('customerArchivesTab');target.innerHTML='<h2>Archiv vlastnictví</h2><p>Původní záznamy a soukromé přílohy z období, kdy vozidlo patřilo vám.</p>';
        const captured=session().snapshot(), rows=await request('/api/v1/vehicle-archives');session().assertCurrent(captured);
        if(!rows.length)target.append(document.createTextNode('Zatím nemáte žádné archivované vlastnictví.'));
        for(const item of rows){const el=document.createElement('article');el.className='customer-feature-card';el.innerHTML=`<h3>${h(item.nickname)}</h3><p>${h(item.plate)} · ${h(item.vin)} · ${h(date(item.created_at))}</p>`;el.append(action('Otevřít archiv',()=>archiveDetail(item.id)));target.append(el);}
    }
    async function archiveDetail(id) {
        const body=panel('Archiv vlastnictví'), item=await request(`/api/v1/vehicle-archives/${id}`);if(!body.isConnected)return;
        body.innerHTML=`<h3>${h(item.nickname)}</h3><p>${h(item.plate)} · ${h(item.vin)}</p>`;
        for(const record of item.records){const el=document.createElement('article');el.className='customer-feature-card';el.innerHTML=`<h4>${h(record.description)}</h4><p>${h(date(record.performed_at))} · ${h(record.mileage??'—')} km · ${h(money(record.price))}</p><p>${h(record.note)}</p>`;
            let attachments=[];try{attachments=typeof record.attachments==='string'?JSON.parse(record.attachments):record.attachments||[];}catch{}
            for(const att of Array.isArray(attachments)?attachments:[]){const key=att.storage_key||att.key; if(key)el.append(action(att.file_name||'Stáhnout přílohu',()=>download(`/api/v1/vehicle-archives/${id}/attachment?key=${encodeURIComponent(key)}`,att.file_name||'priloha')));}
            body.append(el);
        }
        if(!item.records.length)body.append(document.createTextNode('V archivu nejsou servisní záznamy.'));
        for(const [field,kind,label] of [['photo_path','cover','Fotografie vozidla'],['orv_front_image_path','registration-front','Přední strana ORV'],['orv_back_image_path','registration-back','Zadní strana ORV']])if(item.profile?.[field])body.append(action(label,()=>download(`/api/v1/vehicle-archives/${id}/image/${kind}`,kind+'.jpg')));
        for(const repair of item.repairs||[])body.append(action('Fotodokumentace: '+repair.title,()=>repairPhotos(repair)));
    }
    async function invitations() {
        const target=$('customerInvitationsTab');target.innerHTML='<h2>Pozvánky servisů</h2><p>Přijetím servis získá vaše kontaktní údaje a může připravovat nová vozidla. Historii stávajících vozidel sdílíte samostatně v sekci Servisy.</p>';
        const captured=session().snapshot(), data=await request('/api/v1/services/workspace/invitations/incoming');session().assertCurrent(captured);
        void global.ServiceFeatures?.customerRequests(target);
        if(!data.items.length)target.append(document.createTextNode('Žádné čekající pozvánky.'));
        for(const item of data.items){const el=document.createElement('article');el.className='customer-feature-card';el.innerHTML=`<h3>${h(item.service_name)}</h3><p>${h(item.service_email)}</p><p>${h(item.message)}</p><p>Platí do ${h(date(item.expires_at))}</p>`;
            const decide=async accept=>{if(!await confirmAction(accept?`Propojit účet se servisem ${item.service_name}? Servis získá vaše kontaktní údaje. Historii vozidel tím nesdílíte.`:'Odmítnout tuto pozvánku?'))return;const result=await request('/api/v1/services/workspace/invitations/accept','POST',{invitation_id:item.id,decision:accept?'accept':'decline'});if(result.accepted!==accept)throw new Error('Rozhodnutí nebylo potvrzeno serverem.');await invitations();};
            el.append(action('Přijmout pozvánku',()=>decide(true)),action('Odmítnout',()=>decide(false)));target.append(el);
        }
    }
    function vehicleLoaded(vehicle) {
        if(!$('vehicleModalBody'))return;
        if(vehicle.permissions?.can_edit_vehicle===false){
            for(const control of $('vehicleModalBody').querySelectorAll('.vehicle-photo-actions,.vehicle-info-edit,.vehicle-info-display > button'))control.remove();
            for(const row of $('vehicleModalBody').querySelectorAll('.vehicle-info-row.editable'))row.classList.remove('editable');
        }
        const el=document.createElement('section');el.className='customer-feature-card';el.innerHTML=`<h3>Další funkce vozidla</h3><p>Aktuální stav: ${h(vehicle.current_mileage_km??'Nezadáno')} km</p>`;
        if(vehicle.permissions?.can_record_mileage!==false)el.append(action('Zapsat aktuální km',()=>mileage(vehicle)));
        if(vehicle.permissions?.can_edit_vehicle!==false)el.append(action('Upravit údaje vozidla',()=>editVehicle(vehicle)));
        if(vehicle.permissions?.can_import_tachometer!==false)el.append(action('Načíst km a platnost STK',()=>tachometer(vehicle)));
        el.append(action('Fotodokumentace oprav',()=>global.isServiceWorkspaceRole?.()&&global.ServiceFeatures?global.ServiceFeatures.repairs(vehicle):repairSessions(vehicle.id)));
        if(!global.isServiceWorkspaceRole?.())el.append(action('Náklady a statistiky',()=>analytics(panel('Náklady vozidla'),vehicle.id)));
        el.append(action('PDF report',()=>download(`/api/v1/vehicles/${vehicle.id}/pdf`,'historie-vozidla.pdf')));
        $('vehicleModalBody').prepend(el);
    }
    function mileage(vehicle) {
        const body=panel('Zapsat aktuální km'), field=input('Stav tachometru (km)','customerMileage','number',vehicle.current_mileage_km), note=input('Poznámka (volitelné)','customerMileageNote');field.lastChild.min='0';field.lastChild.step='1';
        body.append(field,note,action('Uložit stav kilometrů',async()=>{const raw=$('customerMileage').value, value=Number(raw);if(!raw||!Number.isSafeInteger(value)||value<0)throw new Error('Zadejte celé nezáporné číslo kilometrů.');
            const lower=vehicle.current_mileage_km!=null&&value<vehicle.current_mileage_km;if(lower&&!await confirmAction('Nový stav je nižší než poslední evidovaný. Potvrzujete opravu údaje?'))return;
            await request(`/api/v1/vehicles/${vehicle.id}/mileage`,'POST',{mileage_km:value,note:$('customerMileageNote').value,confirm_lower_than_current:lower});$('customerFeatureDialog')?.close();await global.showVehicleDetail(vehicle.id);
        },false));
    }
    async function tachometer(vehicle) {
        const body=panel('Načíst km a platnost STK');body.textContent='Připravuji ověření…';
        const challenge=await request(`/api/v1/vehicles/${vehicle.id}/tachometer/init`,'POST');if(!body.isConnected)return;
        body.textContent='Opište ověřovací kód z obrázku. Výsledek se uloží do historie vozidla.';
        const image=document.createElement('img');image.alt='Ověřovací kód registru';
        const mime=['image/jpeg','image/png'].includes(challenge.captcha_mime_type)?challenge.captcha_mime_type:'image/png';
        image.src=`data:${mime};base64,${challenge.captcha_image_base64}`;body.append(image,input('Ověřovací kód','customerCaptcha'));
        body.append(action('Načíst a uložit údaje',async()=>{const code=$('customerCaptcha').value.trim();if(code.length<2)throw new Error('Opište ověřovací kód.');await request(`/api/v1/vehicles/${vehicle.id}/tachometer/submit`,'POST',{session_id:challenge.session_id,captcha_code:code});$('customerFeatureDialog')?.close();await global.showVehicleDetail(vehicle.id);},false));
    }
    function editVehicle(vehicle) {
        const body=panel('Upravit údaje vozidla');
        const fields=[['Název','nickname'],['SPZ','plate'],['VIN','vin'],['Značka','brand'],['Model','model'],['Rok výroby','year','number'],['Motor','engine'],['Poznámka','notes'],['Pojišťovna','insurance_provider'],['Platnost pojištění','insurance_valid_until','date'],['Platnost STK','stk_valid_until','date']];
        for(const [label,key,type] of fields)body.append(input(label,'editCustomer-'+key,type||'text',vehicle[key]));
        body.append(action('Uložit údaje',async()=>{const data={};for(const [,key] of fields){const value=$('editCustomer-'+key).value.trim();data[key]=value||null;}if(!data.nickname||data.nickname.length<2)throw new Error('Název musí mít alespoň 2 znaky.');if(data.vin&&!/^[A-HJ-NPR-Z0-9]{17}$/.test(data.vin.toUpperCase()))throw new Error('Zkontrolujte platný VIN.');if(data.vin)data.vin=data.vin.toUpperCase();if(data.year){data.year=Number(data.year);if(!Number.isInteger(data.year)||data.year<1900||data.year>2100)throw new Error('Zkontrolujte rok výroby.');}await request(`/api/v1/vehicles/${vehicle.id}`,'PUT',data);$('customerFeatureDialog')?.close();await global.showVehicleDetail(vehicle.id);await global.loadVehicles();},false));
    }
    async function repairSessions(vehicleId) {
        const body=panel('Fotodokumentace oprav'), rows=await request(`/api/v1/repair-documentation/vehicles/${vehicleId}`);if(!body.isConnected)return;
        if(!rows.length)body.textContent='Zatím není dostupná fotodokumentace opravy.';
        for(const row of rows){const el=document.createElement('article');el.className='customer-feature-card';el.innerHTML=`<h3>${h(row.title)}</h3><p>${h(date(row.created_at))}</p>`;el.append(action('Fotografie',()=>repairPhotos(row)),action('PDF opravy',()=>download(`/api/v1/repair-documentation/sessions/${row.id}/report.pdf`,'fotodokumentace-opravy.pdf')));body.append(el);}
    }
    async function repairPhotos(repair) {
        const body=panel(repair.title||'Fotografie opravy'), rows=await request(`/api/v1/repair-documentation/sessions/${repair.id}/photos`);if(!body.isConnected)return;
        if(!rows.length)body.textContent='K opravě nejsou přiloženy fotografie.';
        for(const row of rows){const el=document.createElement('article');el.className='customer-feature-card';const phase={before:'Před opravou',during:'Průběh opravy',after:'Po opravě'}[row.phase]||'Fotografie';el.innerHTML=`<h3>${h(phase)}</h3><p>${h(row.note)}</p><p>${h(row.author_name)} · ${h(date(row.captured_at||row.uploaded_at))}</p>`;el.append(action('Stáhnout fotografii',()=>download(`/api/v1/repair-documentation/photos/${row.id}/file`,'oprava-'+row.id+'.jpg')));body.append(el);}
    }
    async function readImage(file) {
        if(!file||file.size>20*1024*1024)throw new Error('Vyberte fotografii do 20 MB.');
        const bitmap=await createImageBitmap(file);try{if(bitmap.width*bitmap.height>60000000)throw new Error('Fotografie je příliš velká. Vyberte menší obrázek.');const scale=Math.min(1,2400/Math.max(bitmap.width,bitmap.height)), canvas=document.createElement('canvas');canvas.width=Math.round(bitmap.width*scale);canvas.height=Math.round(bitmap.height*scale);const ctx=canvas.getContext('2d',{willReadFrequently:true});ctx.drawImage(bitmap,0,0,canvas.width,canvas.height);return {canvas,ctx};}finally{bitmap.close();}
    }
    function photoButton(label, camera, handler) {
        const wrap=document.createElement('span'), picker=document.createElement('input');picker.type='file';picker.accept='image/*';picker.hidden=true;if(camera)picker.setAttribute('capture','environment');
        picker.addEventListener('change',async()=>{const file=picker.files[0];if(!file)return;const captured=session().snapshot();try{await handler(file,captured);}catch(e){if(e.name!=='AbortError')showError(e.message);}finally{picker.value='';}});wrap.append(action(label,()=>picker.click()),picker);return wrap;
    }
    function registryPanel() {
        const body=panel('Přidat vozidlo z ORV / registru');body.innerHTML='<p>Načtěte QR kód z fotografie nebo zadejte VIN či číslo ORV. QR se čte v prohlížeči. Do registru odešleme pouze identifikátor. Údaje před uložením zkontrolujete.</p>';
        body.append(input('VIN nebo číslo ORV','customerRegistryId'),action('Načíst z registru',async()=>{const result=await request('/api/v1/vehicles/registry-lookup','POST',registryPayload($('customerRegistryId').value));if(body.isConnected)showRegistryDraft(result);},false));
        const qr=async(file,captured)=>{const {canvas,ctx}=await readImage(file);session().assertCurrent(captured);const pixels=ctx.getImageData(0,0,canvas.width,canvas.height), code=global.jsQR(pixels.data,pixels.width,pixels.height);const number=documentNumber(code?.data||'');if(!number)throw new Error('QR s číslem ORV nebyl nalezen. Vyberte ostřejší fotografii jediného dokladu nebo zadejte číslo ručně.');const value=await request('/api/v1/vehicles/registry-lookup','POST',{orv:number});session().assertCurrent(captured);if(body.isConnected)showRegistryDraft(value);};
        const buttons=document.createElement('div');buttons.className='customer-feature-actions';buttons.append(photoButton('QR z galerie',false,qr),photoButton('Vyfotit QR',true,qr));body.append(buttons);
        const old=document.createElement('details');old.innerHTML='<summary>Doklad bez QR kódu</summary><p>Pro rozpoznání se obě fotografie odešlou na server Evidence Vozidel. Vyberte přední a zadní stranu; výsledek vždy zkontrolujte.</p>';
        const images={},selections={};for(const [key,title] of [['front','Přední strana'],['back','Zadní strana']]){const row=document.createElement('div'), state=document.createElement('span');state.textContent=title+': nevybráno';const select=async(file,captured)=>{const version=(selections[key]||0)+1;selections[key]=version;const {canvas}=await readImage(file);session().assertCurrent(captured);if(!body.isConnected||selections[key]!==version)return;images[key]=canvas.toDataURL('image/jpeg',0.9).split(',')[1];state.textContent=title+': připraveno';};row.append(state,photoButton(title+' z galerie',false,select),photoButton('Vyfotit — '+title.toLowerCase(),true,select));old.append(row);}
        old.append(action('Rozpoznat obě strany',async()=>{if(!images.front||!images.back)throw new Error('Vyberte obě strany dokladu.');const value=await request('/api/v1/vehicles/parse-orv','POST',{front_image_base64:images.front,back_image_base64:images.back,front_image_mime_type:'image/jpeg',back_image_mime_type:'image/jpeg',source:'web_orv_scan'});if(body.isConnected)showRegistryDraft(value.vehicle_fields,value.scan_id,value.warnings);},false));body.append(old);
    }
    function showRegistryDraft(value, scanId, warnings=[]) {
        const body=panel('Zkontrolujte rozpoznané údaje');body.innerHTML='<p>Načtení ještě nevytvořilo vozidlo. Zkontrolujte VIN, SPZ a technické údaje. Nevyplněnou SPZ opište z dokladu.</p>';
        for(const [label,key] of [['VIN','vin'],['SPZ','plate'],['Značka','brand'],['Model','model'],['Číslo ORV','orv_number']]) body.append(input(label,'registryReview-'+key,'text',value[key]));
        if(warnings.length){const p=document.createElement('p');p.textContent=warnings.join(' ');body.append(p);}
        body.append(action('Použít údaje ve formuláři',()=>{const edited={...value};for(const key of ['vin','plate','brand','model','orv_number'])edited[key]=$('registryReview-'+key).value.trim();if(!/^[A-HJ-NPR-Z0-9]{17}$/.test(edited.vin.toUpperCase()))throw new Error('Zkontrolujte platný VIN.');edited.vin=edited.vin.toUpperCase();
            global.switchTab('addVehicle');for(const [id,val] of Object.entries(registryFields(edited))){if($(id))$(id).value=val??'';}
            if(!$('vehicleName').value)$('vehicleName').value=[edited.brand,edited.model].filter(Boolean).join(' ');
            draft={vin:edited.vin,orv_number:edited.orv_number||null,...(scanId?{orv_scan_id:scanId}:{})};$('customerFeatureDialog').close();global.showAlert('Údaje jsou připravené. Zkontrolujte formulář a uložte vozidlo.','success');
        },false));
    }
    function extraVehicleData(vin) {return draft&&draft.vin===vin.trim().toUpperCase()?{orv_number:draft.orv_number,...(draft.orv_scan_id?{orv_scan_id:draft.orv_scan_id}:{})}:{};}
    function profileLoaded() {
        const target=$('profileContainer');if(!target||global.isServiceWorkspaceRole?.())return;const el=document.createElement('div');el.className='customer-feature-actions';el.append(action('Tarify a předplatné',()=>global.openLicensePlans()),action('Pozvánky servisů',()=>global.switchTab('customerInvitations')),action('Archiv vlastnictví',()=>global.switchTab('customerArchives')));target.prepend(el);
    }
    function install() {
        const tabs=document.querySelector('#dashboard .tabs');if(!tabs||$('customerOverviewTab'))return;
        for(const [key,label] of [['customerOverview','Přehled'],['customerArchives','Archiv vlastnictví'],['customerInvitations','Pozvánky servisů']]){const b=action(label,()=>global.switchTab(key));b.className='tab';b.dataset.tabKey=key;tabs.append(b);const el=document.createElement('div');el.className='tab-content';el.id=key+'Tab';$('dashboard').append(el);}
        tabs.prepend(tabs.querySelector('[data-tab-key="customerOverview"]'));
        const add=$('addVehicleTab');const row=document.createElement('div');row.className='customer-feature-actions';row.append(action('Načíst ORV / QR kód',registryPanel));add.prepend(row);
    }
    function load(tab) {const fn={customerOverview:overview,customerArchives:archives,customerInvitations:invitations}[tab];if(fn)void fn().catch(e=>{if(e.name!=='AbortError')showError(e.message);});}
    global.addEventListener('admin-session-ended',()=>global.CustomerFeatures?.reset());
    global.CustomerFeatures={ui:{request,action,panel,input,h,showError,confirmAction,readImage,photoButton,download,repairPhotos,tierError},downloadPDF:id=>download(`/api/v1/vehicles/${Number(id)}/pdf`,'historie-vozidla.pdf'),install,load,vehicleLoaded,profileLoaded,extraVehicleData,clearDraft:()=>{draft=null;},reset:()=>{draft=null;loadVersion++;for(const dialog of document.querySelectorAll('dialog.customer-feature-dialog')){dialog.close();dialog.remove();}for(const id of ['customerOverviewTab','customerArchivesTab','customerInvitationsTab'])if($(id))$(id).replaceChildren();}};
    if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install);else install();
})(typeof window==='undefined'?globalThis:window);
