/* TooZ Servis: free, local FAQ assistant. No visitor data leaves this widget. */
(() => {
  'use strict';
  if (document.getElementById('tooz-service-advisor')) return;
  const base = new URL('.', document.currentScript.src);
  const host = document.createElement('div'); host.id = 'tooz-service-advisor';
  const root = host.attachShadow({mode:'open'});
  root.innerHTML = `<style>
  :host{all:initial;position:fixed;right:20px;bottom:20px;z-index:2147483000;font:15px/1.5 system-ui,sans-serif;color:#183437}*{box-sizing:border-box}button,input,a{font:inherit}button,a{cursor:pointer}button:focus-visible,a:focus-visible,input:focus-visible{outline:3px solid #eaae30;outline-offset:3px}button{border:0}button.launch{background:#164c49;color:white;border-radius:30px;padding:10px 18px;display:flex;align-items:center;gap:10px;box-shadow:0 6px 25px #0003}.launch img{width:42px;height:42px;object-fit:contain}.panel{width:370px;height:min(600px,80dvh);background:#f2f7f5;border:1px solid #c9dbd7;border-radius:20px;box-shadow:0 15px 60px #0004;display:flex;flex-direction:column;overflow:hidden;margin-bottom:12px}.panel[hidden]{display:none}header{background:#164c49;color:white;padding:18px;display:flex;gap:12px;align-items:center}header strong{display:block;font-size:18px}header small{font-size:12px;color:#d0e6e1}header button{margin-left:auto;background:transparent;color:white;font-size:25px;padding:5px 10px}.messages{overflow:auto;flex:1;padding:16px}.message{background:white;border:1px solid #d7e5df;border-radius:14px;padding:12px;margin-bottom:10px;white-space:pre-wrap;overflow-wrap:anywhere}.message.user{background:#dceee8;margin-left:30px}.topics{display:flex;gap:7px;flex-wrap:wrap;margin:12px 0}.topics button{background:white;color:#18534b;border:1px solid #b4d3c7;border-radius:18px;padding:7px 12px}.links{display:flex;flex-wrap:wrap;gap:12px;padding:0 16px 12px}.links a{color:#16534c;font-weight:650;text-decoration:underline}form{display:flex;gap:7px;padding:12px;border-top:1px solid #d6e1dc;background:white}input{min-width:0;flex:1;border:1px solid #a7bfb7;border-radius:10px;padding:10px;color:#183437;background:white}form button{background:#164c49;color:white;border-radius:10px;padding:9px 12px}.note{font-size:11px;padding:0 14px 10px;background:white;color:#536961}@media(max-width:440px){:host{right:10px;bottom:10px}.panel{width:calc(100vw - 20px);height:min(580px,76dvh)}.launch{margin-left:auto}}
  </style><section class="panel" hidden aria-label="Servisní poradce"><header><div><strong>TooZ Servis</strong><small>Rychlý servisní poradce</small></div><button class="close" aria-label="Zavřít poradce">×</button></header><div class="messages" role="log" aria-live="polite" aria-relevant="additions"></div><nav class="links" aria-label="Kontakt a objednání"><a href="https://www.toozservis.cz/objednavka/" target="_blank" rel="noopener">Objednat servis ↗</a><a href="tel:+420731552299">Zavolat</a><a href="mailto:info@toozservis.cz">E-mail</a></nav><form><input aria-label="Váš dotaz" placeholder="Např. kde vás najdu?" maxlength="500" autocomplete="off"><button>Odeslat</button></form><div class="note">Automatické odpovědi bez AI. Dotazy se neukládají ani neodesílají servisu.</div></section><button class="launch" aria-expanded="false"><img alt=""/><span>Poradíme vám</span></button>`;
  root.querySelector('img').src = new URL('robot-logo.png',base).href;
  document.body.append(host);
  const panel=root.querySelector('.panel'),launch=root.querySelector('.launch'),input=root.querySelector('input'),messages=root.querySelector('.messages');
  const answers={
    'Objednání':'Termín si můžete vyžádat přes „Objednat servis“ nebo na +420 731 552 299. Dostupnost termínu potvrdí servis; tento chat rezervaci nevytváří.',
    'Kontakt a adresa':'Najdete nás na adrese Opatovec 122, 568 02 Svitavy. Telefon: +420 731 552 299. E-mail: info@toozservis.cz.',
    'Otevírací doba':'Na webu je uvedeno Po–Pá 8:00–17:00 a So 9:00–15:00. Před návštěvou doporučujeme domluvit termín telefonicky.',
    'Ceny':'Aktuální ceník najdete na www.toozservis.cz/cenik/. Přesnou cenu opravy servis potvrdí podle vozidla, rozsahu práce a dílů.',
    'Služby':'Servis nabízí diagnostiku, pneuservis, výměnu oleje, servis brzd a podvozku, přípravu na STK a další opravy. Podrobnosti najdete na www.toozservis.cz/sluzby/.',
    'SprávaVozidel':'Vozidla a servisní historii spravujete v mobilní aplikaci SprávaVozidel. Potřebujete-li pomoc s účtem nebo přístupem, kontaktujte info@toozservis.cz. Heslo ani jiné přihlašovací údaje sem nevkládejte.'
  };
  function add(text,user=false){const el=document.createElement('div');el.className='message'+(user?' user':'');el.textContent=text;messages.append(el);while(messages.children.length>60)messages.firstChild.remove();messages.scrollTop=messages.scrollHeight;}
  function normalize(t){return t.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'');}
  function reply(t){const n=normalize(t);let key;
    if(/objedn|termin|rezerv/.test(n))key='Objednání';
    else if(/otevir|otevren|pracovni doba|sobot|kdy mate/.test(n))key='Otevírací doba';
    else if(/cena|ceny|cenik|kolik|stoji/.test(n))key='Ceny';
    else if(/aplik|heslo|ucet|prihlas|spravavozidel/.test(n))key='SprávaVozidel';
    else if(/kde|adres|kontakt|telefon|mail|najdu/.test(n))key='Kontakt a adresa';
    else if(/sluzb|olej|brzd|pneu|stk|diagnost|oprav/.test(n))key='Služby';
    add(key?answers[key]:'Na tento dotaz nemám spolehlivou automatickou odpověď. Zavolejte nám na +420 731 552 299 nebo napište na info@toozservis.cz. Technickou závadu musí posoudit servis.');
  }
  add('Dobrý den! Vyberte téma nebo napište krátký dotaz. Pomohu s informacemi o servisu a objednáním.');
  const topics=document.createElement('div');topics.className='topics';Object.keys(answers).forEach(k=>{const b=document.createElement('button');b.type='button';b.textContent=k;b.onclick=()=>{add(k,true);add(answers[k]);};topics.append(b);});messages.append(topics);
  function toggle(open){panel.hidden=!open;launch.setAttribute('aria-expanded',String(open));if(open)input.focus();else launch.focus();}
  launch.onclick=()=>toggle(panel.hidden);root.querySelector('.close').onclick=()=>toggle(false);root.addEventListener('keydown',e=>{if(e.key==='Escape')toggle(false);});
  root.querySelector('form').onsubmit=e=>{e.preventDefault();const t=input.value.trim();if(!t)return;input.value='';add(t,true);reply(t);};
})();
