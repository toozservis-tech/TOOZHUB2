/* Service browser flows share the mobile APIs and their consent boundaries. */
(function (global) {
    'use strict';
    if (!global.CustomerWeb || !global.CustomerFeatures) return;
    const ui = global.CustomerFeatures.ui;
    const {request, action, panel, input, h, showError, confirmAction, readImage, photoButton, download} = ui;
    const session = () => global.AdminBrowserSession;
    const serviceRole = () => Boolean(global.isServiceWorkspaceRole?.());

    async function workspaceLoaded(container) {
        if (!serviceRole()) return;
        const section = document.createElement('section');
        section.className = 'customer-feature-card';
        section.innerHTML = '<h3>Vozidla klientů / Připojit vozidlo</h3><p>Vyhledejte vozidlo podle SPZ nebo VIN. Historie je dostupná až po souhlasu jeho majitele.</p>';
        const query = input('SPZ nebo VIN', 'serviceAccessQuery');
        query.lastChild.maxLength = 128;
        const results = document.createElement('div');
        results.setAttribute('aria-live', 'polite');
        const approved = document.createElement('div');
        section.append(query, action('Vyhledat vozidlo', async () => {
            const value = query.lastChild.value.trim();
            if (value.length < 2) throw new Error('Zadejte SPZ nebo VIN vozidla.');
            results.textContent = 'Vyhledávám…';
            try {
                const data = await request('/api/v1/services/workspace/vehicle-lookup', 'POST', {query:value});
                if (!section.isConnected) return;
                results.replaceChildren();
                if (!data.candidates.length) results.textContent = 'Vozidlo nebylo nalezeno. Nové vozidlo můžete připravit v sekci Přidat vozidlo.';
                for (const candidate of data.candidates) {
                    const card = document.createElement('article');
                    card.className = 'customer-feature-card';
                    card.innerHTML = `<h4>${h(candidate.nickname || [candidate.brand,candidate.model].filter(Boolean).join(' ') || 'Vozidlo')}</h4><p>${h(candidate.plate_masked)} · ${h(candidate.vin_masked)}</p>`;
                    if (candidate.status === 'already_approved') card.append(document.createTextNode('Přístup již byl schválen. Vozidlo najdete v seznamu níže.'));
                    else if (candidate.status === 'pending_request') card.append(document.createTextNode('Žádost čeká na rozhodnutí majitele.'));
                    else if (candidate.can_request_access) card.append(action('Požádat majitele o přístup', () => accessRequest(candidate, value)));
                    results.append(card);
                }
            } catch (e) { if (e.name !== 'AbortError' && section.isConnected) results.textContent=e.message; }
        }), results, approved);
        container.prepend(section);
        async function loadApproved() {
            approved.innerHTML='<h4>Schválená vozidla</h4><p>Načítám…</p>';
            try {
                const data=await request('/api/v1/services/workspace/approved-vehicles');
                if (!section.isConnected) return;
                approved.innerHTML='<h4>Schválená vozidla</h4>';
                approved.append(action('Obnovit seznam',loadApproved));
                if(!data.items.length) approved.append(document.createTextNode('Zatím nemáte schválená vozidla.'));
                for(const vehicle of data.items){
                    const card=document.createElement('article');card.className='customer-feature-card';
                    card.innerHTML=`<h4>${h(vehicle.vehicle_name)}</h4><p>${h(vehicle.vehicle_plate)} · ${h(vehicle.customer_name)}</p>`;
                    card.append(action('Detail a servisní historie',()=>global.showVehicleDetail(vehicle.id)));
                    approved.append(card);
                }
            } catch(e){if(e.name!=='AbortError'&&section.isConnected)approved.textContent=e.message;}
        }
        await loadApproved();
    }
    function accessRequest(candidate, lookupQuery) {
        const body=panel('Žádost o přístup k vozidlu');
        const note=input('Zpráva majiteli (volitelné)','serviceAccessNote');note.lastChild.maxLength=500;
        body.append(document.createTextNode('Žádost se zobrazí majiteli vozidla. Teprve jeho schválení umožní číst historii a přidávat nové servisní záznamy.'),note,
            action('Odeslat žádost',async()=>{
                const result=await request('/api/v1/services/workspace/access-requests','POST',{vehicle_id:candidate.vehicle_id,lookup_query:lookupQuery,note:note.lastChild.value.trim()||null});
                if(body.isConnected){body.replaceChildren();body.textContent=result.message||'Žádost čeká na schválení majitelem.';}
            },false));
    }
    async function repairs(vehicle) {
        const body=panel('Fotodokumentace oprav');
        const actor=await request('/user/me');
        const rows=await request(`/api/v1/repair-documentation/vehicles/${vehicle.id}`);
        if(!body.isConnected)return;
        if(vehicle.permissions?.can_create_repair_photos===true)body.append(action('Založit fotodokumentaci opravy',()=>createRepair(vehicle)));
        if(!rows.length)body.append(document.createTextNode('Vozidlo zatím nemá fotodokumentaci opravy.'));
        for(const row of rows){
            const card=document.createElement('article');card.className='customer-feature-card';
            card.innerHTML=`<h3>${h(row.title)}</h3>`;
            card.append(action('Fotografie',()=>ui.repairPhotos(row)),action('PDF opravy',()=>download(`/api/v1/repair-documentation/sessions/${row.id}/report.pdf`,'fotodokumentace-opravy.pdf')));
            if(vehicle.permissions?.can_create_repair_photos===true && Number(row.service_id)===Number(actor.id))card.append(action('Přidat fotografii',()=>uploadPhoto(row)));
            body.append(card);
        }
    }
    function createRepair(vehicle) {
        const body=panel('Nová fotodokumentace opravy'), title=input('Název opravy','serviceRepairTitle');title.lastChild.maxLength=200;
        let lastTitle='',clientId;
        body.append(title,action('Vytvořit opravu',async()=>{
            const value=title.lastChild.value.trim();if(!value)throw new Error('Vyplňte název opravy.');
            if(value!==lastTitle){clientId=crypto.randomUUID();lastTitle=value;}
            const row=await request(`/api/v1/repair-documentation/vehicles/${vehicle.id}`,'POST',{title:value,client_id:clientId});
            if(body.isConnected)uploadPhoto(row);
        },false));
    }
    function uploadPhoto(repair) {
        const body=panel('Přidat fotografii opravy');
        body.append(document.createTextNode('Fotografie se uloží k opravě a bude dostupná oprávněnému majiteli vozidla. Před uložením zkontrolujte její obsah.'));
        const phaseLabel=document.createElement('label');phaseLabel.className='customer-field';phaseLabel.textContent='Fáze opravy';
        const phase=document.createElement('select');
        for(const [value,label] of [['before','Před opravou'],['during','Průběh opravy'],['after','Po opravě']]){const option=document.createElement('option');option.value=value;option.textContent=label;phase.append(option);}
        phaseLabel.append(phase);
        const note=input('Popis fotografie','servicePhotoNote');note.lastChild.maxLength=2000;
        const preview=document.createElement('img');preview.alt='Náhled vybrané fotografie';preview.hidden=true;preview.className='service-photo-preview';
        let selected=null, selection=0, previousPayload='',clientId;
        const choose=source=>async(file,captured)=>{
            const version=++selection;selected=null;preview.hidden=true;preview.removeAttribute('src');const {canvas}=await readImage(file);session().assertCurrent(captured);
            if(!body.isConnected||version!==selection)return;
            const url=canvas.toDataURL('image/jpeg',0.9);selected={file_content_base64:url.split(',')[1],source};preview.src=url;preview.hidden=false;
        };
        body.append(phaseLabel,note,photoButton('Vybrat z galerie',false,choose('library')),photoButton('Vyfotit',true,choose('camera')),preview,
            action('Uložit fotografii',async()=>{
                if(!selected)throw new Error('Nejprve vyberte nebo vyfoťte fotografii.');
                const payload={...selected,phase:phase.value,note:note.lastChild.value.trim()};
                const key=JSON.stringify(payload);if(previousPayload!==key){clientId=crypto.randomUUID();previousPayload=key;}
                await request(`/api/v1/repair-documentation/sessions/${repair.id}/photos`,'POST',{...payload,client_id:clientId});
                if(body.isConnected){selected=null;preview.removeAttribute('src');await ui.repairPhotos(repair);}
            },false));
    }
    async function customerRequests(target) {
        const block=document.createElement('section');block.className='customer-feature-card';block.innerHTML='<h3>Žádosti o přístup k vozidlu</h3>';target.prepend(block);
        try {
            const data=await request('/api/v1/services/access-requests');if(!block.isConnected)return;
            if(!data.requests.length)block.append(document.createTextNode('Žádné čekající žádosti.'));
            for(const row of data.requests){
                const item=document.createElement('article');item.className='customer-feature-card';
                item.innerHTML=`<h4>${h(row.service_name)}</h4><p>${h(row.vehicle_name)} · ${h(row.vehicle_plate)}</p><p>${h(row.note)}</p><p>${h(row.scope_summary||'Čtení historie a vytváření nových servisních záznamů.')}</p>`;
                const decide=async approved=>{
                    if(!await confirmAction(approved?`Povolit servisu ${row.service_name} čtení historie a přidávání nových záznamů u vozidla ${row.vehicle_plate||row.vehicle_name}?`:'Zamítnout žádost servisu?'))return;
                    await request(`/api/v1/services/access-requests/${row.id}`,'PUT',{decision:approved?'approved':'rejected'});
                    if(item.isConnected){item.textContent=approved?'Přístup byl schválen.':'Žádost byla zamítnuta.';}
                };
                item.append(action('Schválit přístup',()=>decide(true)),action('Zamítnout',()=>decide(false)));block.append(item);
            }
        }catch(e){if(e.name!=='AbortError'&&block.isConnected)ui.tierError(block,e);}
    }
    global.ServiceFeatures={workspaceLoaded:container=>{void workspaceLoaded(container).catch(e=>{if(e.name!=='AbortError')showError(e.message);});},repairs,customerRequests};
})(window);
