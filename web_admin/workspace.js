'use strict';
function requestDeletionConfirmation(path) {
  return new Promise(resolve => {
    const dialog = document.createElement('dialog');
    dialog.className = 'admin-delete-dialog';
    dialog.setAttribute('aria-labelledby','delete-heading');
    dialog.innerHTML = `<form><h2 id="delete-heading">Odstranění záznamu</h2><p>Odstranění může ovlivnit související data. Důvod se uloží do historie administrátorských akcí.</p><small id="delete-target"></small><label for="delete-reason">Důvod odstranění</label><textarea id="delete-reason" minlength="3" maxlength="1000" rows="3" required placeholder="Popište důvod tohoto zásahu"></textarea><label for="delete-confirm">Pro potvrzení napište ODSTRANIT</label><input id="delete-confirm" pattern="ODSTRANIT" required autocomplete="off"><footer><button type="button" class="btn-secondary" id="delete-cancel">Zrušit</button><button type="submit" class="btn-danger">Odstranit</button></footer></form>`;
    dialog.querySelector('#delete-target').textContent = 'Záznam: ' + path.split('/').slice(-2).join(' / ');
    let finished = false;
    function finish(value) { if(finished)return; finished=true;dialog.close();dialog.remove();resolve(value); }
    dialog.querySelector('#delete-cancel').addEventListener('click',()=>finish(null));
    dialog.addEventListener('cancel',event=>{event.preventDefault();finish(null);});
    dialog.querySelector('form').addEventListener('submit',event=>{event.preventDefault(); const reason=dialog.querySelector('#delete-reason').value.trim();if(reason.length<3){dialog.querySelector('#delete-reason').focus();return;}finish({reason,confirmation:'ODSTRANIT'});});
    document.body.appendChild(dialog);dialog.showModal();dialog.querySelector('#delete-reason').focus();
  });
}
window.addEventListener('DOMContentLoaded',()=>{
  const stats=document.getElementById('overview-stats');
  const destinations=['users','vehicles','services','records','users'];
  const decorate=()=>stats?.querySelectorAll('.stat-card').forEach((card,index)=>{card.dataset.destination=destinations[index];card.tabIndex=0;card.setAttribute('role','button');card.setAttribute('aria-label','Otevřít: '+card.textContent.trim());card.onclick=()=>switchSection(destinations[index]);card.onkeydown=event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();card.click();}};});
  if(stats){new MutationObserver(decorate).observe(stats,{childList:true});decorate();}
});
