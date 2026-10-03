'use strict';
function requestDeletionConfirmation(path, preview = null) {
  return new Promise(resolve => {
    const dialog = document.createElement('dialog');
    dialog.className = 'admin-delete-dialog';
    dialog.setAttribute('aria-labelledby','delete-heading');
    dialog.innerHTML = `<form><h2 id="delete-heading">Odstranění záznamu</h2><p>Odstranění může ovlivnit související data. Důvod se uloží do historie administrátorských akcí.</p><small id="delete-target"></small><label for="delete-reason">Důvod odstranění</label><textarea id="delete-reason" minlength="3" maxlength="1000" rows="3" required placeholder="Popište důvod tohoto zásahu"></textarea><label for="delete-confirm">Pro potvrzení napište ODSTRANIT</label><input id="delete-confirm" pattern="ODSTRANIT" required autocomplete="off"><footer><button type="button" class="btn-secondary" id="delete-cancel">Zrušit</button><button type="submit" class="btn-danger">Odstranit</button></footer></form>`;
    dialog.querySelector('#delete-target').textContent = 'Záznam: ' + path.split('/').slice(-2).join(' / ');
    let related = null;
    if (preview) {
      dialog.querySelector('h2').textContent = 'Odstranění vozidla';
      dialog.querySelector('#delete-target').textContent = `${preview.title} • ${preview.plate || 'Bez SPZ'} • #${preview.vehicle_id}`;
      const summary = document.createElement('section');
      const heading = document.createElement('h3'); heading.textContent = 'Smazat i navázané záznamy?'; summary.append(heading);
      const list = document.createElement('ul');
      for (const item of preview.items || []) {
        const line = document.createElement('li'); line.textContent = `${item.label}: ${item.count}`; list.append(line);
      }
      if (preview.files_count) { const line=document.createElement('li');line.textContent=`Soubory k odstranění: ${preview.files_count}`;list.append(line); }
      summary.append(list);
      const note = document.createElement('p');
      note.textContent = preview.requires_related_confirmation ? 'S vozidlem se odstraní všechny uvedené záznamy a jeho soubory. Účty zákazníků a servisů zůstanou zachované. Zásah se uloží do historie administrace.' : 'Vozidlo nemá další záznamy k odstranění. Účty zákazníků a servisů zůstanou zachované.';
      summary.append(note);
      if (preview.preserved_history_count) {
        const kept=document.createElement('p');kept.textContent=`Historie jiných vozidel zůstane zachovaná: ${preview.preserved_history_count}.`;summary.append(kept);
      }
      if (preview.requires_related_confirmation) {
        const label=document.createElement('label');label.className='delete-related-choice';related=document.createElement('input');
        related.type='checkbox';related.id='delete-related';related.required=true;
        label.append(related,document.createTextNode(' Chci smazat vozidlo i všechny uvedené navázané záznamy.'));summary.append(label);
        dialog.querySelector('[type="submit"]').textContent='Odstranit vozidlo i záznamy';
      } else dialog.querySelector('[type="submit"]').textContent='Odstranit vozidlo';
      dialog.querySelector('#delete-target').after(summary);
    }
    let finished = false;
    function finish(value) { if(finished)return; finished=true;dialog.close();dialog.remove();resolve(value); }
    dialog.querySelector('#delete-cancel').addEventListener('click',()=>finish(null));
    dialog.addEventListener('cancel',event=>{event.preventDefault();finish(null);});
    dialog.querySelector('form').addEventListener('submit',event=>{event.preventDefault(); const reason=dialog.querySelector('#delete-reason').value.trim();if(reason.length<3){dialog.querySelector('#delete-reason').focus();return;}if(related&&!related.checked)return;finish({reason,confirmation:'ODSTRANIT',...(preview ? {delete_related: related?.checked===true,preview_token:preview.preview_token} : {})});});
    document.body.appendChild(dialog);dialog.showModal();dialog.querySelector('#delete-reason').focus();
  });
}
window.addEventListener('DOMContentLoaded',()=>{
  const stats=document.getElementById('overview-stats');
  const destinations=['users','vehicles','services','records','users'];
  const decorate=()=>stats?.querySelectorAll('.stat-card').forEach((card,index)=>{card.dataset.destination=destinations[index];card.tabIndex=0;card.setAttribute('role','button');card.setAttribute('aria-label','Otevřít: '+card.textContent.trim());card.onclick=()=>switchSection(destinations[index]);card.onkeydown=event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();card.click();}};});
  if(stats){new MutationObserver(decorate).observe(stats,{childList:true});decorate();}
});
