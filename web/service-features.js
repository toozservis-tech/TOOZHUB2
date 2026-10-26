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
        section.prepend(action('Práce a souhlas majitele',()=>workBeforeConsent()));
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
    const photoBatches=new Map();
    const consentTitle=value=>({pending:'Čeká na souhlas · pouze u servisu',rejected:'Souhlas odmítnut · historie u servisu',revoked:'Souhlas byl odvolán',ownership_changed:'Změnil se majitel',approved:'Sdíleno s majitelem'}[value]||'Sdíleno s majitelem');
    const statusTitle=value=>({received:'Přijato do servisu',in_progress:'Probíhá oprava',completed:'Dokončeno',handed_over:'Předáno',cancelled:'Zrušeno'}[value]||value);
    const evidenceWritable=(job,actor)=>actor.role==='service' && Number(actor.id)===Number(job.service_id) && !['handed_over','cancelled'].includes(job.status) && !['revoked','ownership_changed'].includes(job.consent_status);
    async function workBeforeConsent(offset=0) {
        const body=panel('Práce a souhlas majitele');
        body.textContent='Načítám zakázky…';
        const reply=await request(`/api/v1/services/workspace/work-before-consent?offset=${offset}`);
        if(!body.isConnected)return;
        body.textContent='Vlastní práce servisu zůstává uložená i při odmítnutí. Majitel ji uvidí až po schválení.';
        for(const row of reply.items||[]) {
            const card=document.createElement('article');card.className='customer-feature-card';
            card.innerHTML=`<h3>${h(row.vehicle_title||'Vozidlo')}</h3><p>${h(row.plate)} · ${h(consentTitle(row.status))}</p>`;
            card.append(action('Zakázky a přílohy',()=>jobs(row.vehicle_id,row.id)));body.append(card);
        }
        if(!reply.items?.length)body.append(document.createTextNode('Žádné další žádosti a práce.'));
        if(reply.next_offset!=null)body.append(action('Další žádosti',()=>workBeforeConsent(reply.next_offset)));
    }
    async function jobs(vehicleId,requestId) {
        const body=panel('Průběh servisu a aktualizace');body.textContent='Načítám…';
        const reply=await request(`/api/v1/vehicles/${Number(vehicleId)}/service-jobs${requestId?`?access_request_id=${Number(requestId)}`:''}`);
        if(!body.isConnected)return;body.replaceChildren();
        for(const job of reply.items||[]) {
            const card=document.createElement('article');card.className='customer-feature-card';
            card.innerHTML=`<h3>${h(job.title)}</h3><p>${h(statusTitle(job.status))} · ${h(consentTitle(job.consent_status))}</p><p>${h(job.description)}</p>`;
            card.append(action('Fotografie, faktury a průběh',()=>jobEvidence(job.id)));body.append(card);
        }
        if(!reply.items?.length)body.textContent='Vozidlo zatím nemá dostupnou servisní zakázku.';
    }
    async function jobEvidence(jobId) {
        jobId=Number(jobId);if(!Number.isSafeInteger(jobId)||jobId<=0)throw new Error('Neplatná zakázka.');
        const captured=session().snapshot(),body=panel('Přílohy zakázky');body.textContent='Načítám…';
        const [job,actor]=await Promise.all([request(`/api/v1/service-jobs/${jobId}`),request('/user/me')]);
        session().assertCurrent(captured);if(!body.isConnected)return;
        body.innerHTML=`<h3>${h(job.title)}</h3><p>${h(statusTitle(job.status))} · ${h(consentTitle(job.consent_status))}</p><p>Snímky a PDF se ukládají k této zakázce. Před souhlasem je vidí pouze servis; po souhlasu také majitel.</p>`;
        const list=document.createElement('section');body.append(list);
        const urls=[];const dialog=body.closest('dialog');dialog.addEventListener('close',()=>urls.forEach(URL.revokeObjectURL),{once:true});
        const style=document.createElement('style');style.textContent=`
            .job-photo-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(135px,1fr));gap:12px;margin:12px 0}
            .job-photo-tile{display:flex!important;flex-direction:column;text-align:left!important;gap:6px;padding:8px!important;border-radius:14px!important;overflow:hidden;min-width:0}
            .job-photo-tile img{width:100%;height:110px;object-fit:cover;border-radius:10px;background:#303d55}
            .job-photo-caption{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;min-height:2.6em;line-height:1.3}
            .job-photo-tile small{opacity:.7}.job-photo-lightbox{max-width:90vw;max-height:94vh;border:0;border-radius:18px;padding:18px;background:#263148;color:white}
            .job-photo-lightbox img{display:block;max-width:85vw;max-height:72vh;object-fit:contain}.job-photo-lightbox::backdrop{background:#000b}
        `;body.append(style);
        let galleryVersion=0;
        async function preview(photo) {
            session().assertCurrent(captured);
            const r=await session().request(`/api/v1/service-jobs/${jobId}/photos/${photo.id}`);
            if(!r.ok)throw new Error('Fotografie není pro tento účet dostupná.');
            const blob=await r.blob();session().assertCurrent(captured);if(!body.isConnected)return;
            const url=URL.createObjectURL(blob),viewer=document.createElement('dialog');viewer.className='job-photo-lightbox';
            const title=document.createElement('h3');title.textContent=photo.caption||'Fotografie práce';
            const image=document.createElement('img');image.src=url;image.alt=title.textContent;
            const close=action('Zavřít fotografii',()=>viewer.close());viewer.append(title,close,image);document.body.append(viewer);
            viewer.addEventListener('close',()=>{URL.revokeObjectURL(url);viewer.remove();},{once:true});
            dialog.addEventListener('close',()=>{if(viewer.open)viewer.close();},{once:true});viewer.showModal();
        }
        function files(value) {
            const version=++galleryVersion;urls.splice(0).forEach(URL.revokeObjectURL);
            list.innerHTML=`<h3>Fotografie (${value.photos.length})</h3><p>Klepnutím na náhled otevřete celou fotografii.</p>`;
            const grid=document.createElement('div');grid.className='job-photo-grid';list.append(grid);
            let shown=0;
            const more=action('Zobrazit další fotografie',()=>next());
            function next() {
                const batch=value.photos.slice(shown,shown+12),offset=shown;shown+=batch.length;
                const pending=batch.map((photo,index)=>{
                    const tile=action('',()=>preview(photo));tile.className+=' job-photo-tile';tile.setAttribute('aria-label',`Fotografie ${offset+index+1}: ${photo.caption||'Fotografie práce'}`);
                    const image=document.createElement('img');image.alt='Načítám náhled…';
                    const caption=document.createElement('span');caption.className='job-photo-caption';caption.textContent=photo.caption||'Fotografie práce';
                    const info=document.createElement('small');info.textContent=`${offset+index+1} · ${Math.ceil(photo.file_size/1000)} kB`;
                    tile.append(image,caption,info);grid.append(tile);return {photo,image};
                });
                more.hidden=shown>=value.photos.length;more.style.setProperty('display',more.hidden?'none':'inline-flex','important');more.textContent=`Zobrazit další fotografie (${value.photos.length-shown})`;
                async function worker() {while(pending.length) {
                    const {photo,image}=pending.shift();
                    try {
                        session().assertCurrent(captured);if(!body.isConnected||version!==galleryVersion)return;
                        const r=await session().request(`/api/v1/service-jobs/${jobId}/photos/${photo.id}?thumbnail=true`);
                        if(!r.ok)throw new Error('Náhled nedostupný');
                        const blob=await r.blob();session().assertCurrent(captured);if(!body.isConnected||version!==galleryVersion)return;
                        const url=URL.createObjectURL(blob);urls.push(url);image.src=url;image.alt=photo.caption||'Fotografie práce';
                    }catch(e){if(e.name==='AbortError')return;image.alt='Náhled nelze načíst. Klepněte pro otevření.';}
                }}
                for(let i=0;i<3;i++)void worker();
            }
            next();list.append(more);
            if(!value.photos.length)list.append(document.createTextNode('Zatím nejsou přiložené fotografie.'));
            const title=document.createElement('h3');title.textContent='Faktury a dokumenty PDF';list.append(title);
            for(const doc of value.documents)list.append(action(doc.file_name,()=>download(`/api/v1/service-jobs/${jobId}/documents/${doc.id}`,doc.file_name)));
        }
        files(job);
        if(evidenceWritable(job,actor)) {
            const caption=input('Popis fotografií','jobPhotoCaption','text','Fotografie práce');caption.lastChild.maxLength=200;
            const picker=input('Vybrat více fotografií','jobPhotos','file');picker.lastChild.multiple=true;picker.lastChild.accept='image/*';
            const selections=document.createElement('div'),result=document.createElement('p');result.setAttribute('role','status');
            const key=String(actor.id)+':'+jobId;
            let batch=photoBatches.get(key),busy=false;
            const button=action('Přidat vybrané fotografie',async()=>{
                session().assertCurrent(captured);if(busy||!batch?.items.length)return;
                busy=true;batch.started=true;picker.lastChild.disabled=true;caption.lastChild.disabled=true;
                selections.querySelectorAll('input').forEach(x=>x.disabled=true);
                const close=dialog.querySelector('header button');close.disabled=true;
                try {
                    while(batch.done<batch.items.length) {
                        session().assertCurrent(captured);
                        const item=batch.items[batch.done];
                        if(!item.payload) {
                            const {canvas}=await readImage(item.file);session().assertCurrent(captured);
                            item.payload={client_id:item.id,caption:batch.caption,content_base64:canvas.toDataURL('image/jpeg',0.82).split(',')[1]};
                        }
                        await request(`/api/v1/service-jobs/${jobId}/photos`,'POST',item.payload);
                        session().assertCurrent(captured);batch.done++;item.payload=null;item.file=null;
                        result.textContent=`Fotografie uloženy: ${batch.done} z ${batch.items.length}.`;
                    }
                    const updated=await request(`/api/v1/service-jobs/${jobId}`);session().assertCurrent(captured);
                    if(body.isConnected)files(updated);
                    photoBatches.delete(key);batch=null;picker.lastChild.value='';selections.replaceChildren();
                    button.textContent='Přidat vybrané fotografie';
                } catch(e) {
                    if(e.name==='AbortError')throw e;
                    result.textContent=`Fotografie uloženy: ${batch.done} z ${batch.items.length}. ${e.message} Uložené snímky zůstávají. Pokračujte stejnou dávkou.`;
                    button.textContent='Pokračovat v nahrávání fotografií';
                } finally {busy=false;close.disabled=false;picker.lastChild.disabled=Boolean(batch);caption.lastChild.disabled=Boolean(batch);}
            },false);
            dialog.addEventListener('cancel',e=>{if(busy)e.preventDefault();});
            function chosen() {
                selections.replaceChildren();
                if(!batch)return;
                if(batch.started) {picker.lastChild.disabled=true;caption.lastChild.disabled=true;button.textContent='Pokračovat v nahrávání fotografií';result.textContent=`Fotografie uloženy: ${batch.done} z ${batch.items.length}.`;return;}
                for(const item of batch.items) {const label=document.createElement('label'),check=document.createElement('input');check.type='checkbox';check.checked=true;check.addEventListener('change',()=>{item.selected=check.checked;});label.append(check,document.createTextNode(item.file.name));selections.append(label,document.createElement('br'));}
                result.textContent=`Vybráno ${batch.items.length} fotografií. Před potvrzením se nic neodesílá.`;
            }
            // The same UUID and bytes are retained until the server acknowledges each file.
            button.addEventListener('click',()=>{
                if(batch&&!batch.started) {batch.items=batch.items.filter(x=>x.selected!==false);batch.caption=caption.lastChild.value.trim()||'Fotografie práce';}
            },true);
            picker.lastChild.addEventListener('change',()=>{
                if(busy||batch?.started)return;
                const selected=Array.from(picker.lastChild.files);
                if(!selected.length)return;
                batch={done:0,caption:'',started:false,items:selected.map(file=>({file,id:crypto.randomUUID(),selected:true}))};photoBatches.set(key,batch);chosen();
            });
            const info=document.createElement('p');info.textContent='Fotografie můžete doplnit i po dokončení. Automaticky je zmenšíme; originály ve vašem zařízení zůstanou beze změny.';
            const upload=document.createElement('section');upload.className='customer-feature-card';upload.append(info,caption,picker,selections,button,result);body.insertBefore(upload,list);chosen();
        }
        const timeline=document.createElement('details');timeline.innerHTML='<summary>Historie zakázky</summary>';
        for(const event of job.events||[]) {const p=document.createElement('p');p.textContent=`${new Date(event.created_at).toLocaleString('cs-CZ')} · ${statusTitle(event.status)} · ${event.message||''}`;timeline.append(p);}
        body.append(timeline);
    }
    global.addEventListener('admin-session-ended',()=>photoBatches.clear());

    global.ServiceFeatures={workspaceLoaded:container=>{void workspaceLoaded(container).catch(e=>{if(e.name!=='AbortError')showError(e.message);});},repairs,customerRequests,jobs,jobEvidence};
})(window);
