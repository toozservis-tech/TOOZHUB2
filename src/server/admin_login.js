let challenge=null, pendingToken=null, mode='login';
const el=id=>document.getElementById(id), form=el('form'), button=el('submit');
// Unverified sessions and authenticator seeds remain only in this page's memory.
localStorage.removeItem('adminAccessToken');localStorage.removeItem('accessToken');
sessionStorage.removeItem('adminAccessToken');
async function api(url,body,token){
 const r=await fetch(url,{method:body===null?'GET':'POST',cache:'no-store',headers:{'Content-Type':'application/json',...(token?{'Authorization':'Bearer '+token}:{})},...(body===null?{}:{body:JSON.stringify(body)})});
 const data=await r.json();if(!r.ok)throw new Error(typeof data.detail==='string'?data.detail:'Ověření se nezdařilo.');return data;
}
function showMode(next){
 mode=next;const otp=next==='otp'||next==='setupCode';
 el('passwordLabel').hidden=otp;el('password').required=!otp;el('password').value='';
 el('email').readOnly=next!=='login';el('codeLabel').hidden=!otp;el('code').required=otp;el('code').value='';
 el('setup').hidden=next!=='setupCode';el('restart').hidden=next==='login';
 button.textContent=next==='setupPassword'?'Připravit autentikátor':next==='setupCode'?'Potvrdit nastavení a otevřít správu':otp?'Ověřit a otevřít správu':'Přihlásit administrátora';
 (otp?el('code'):el('password')).focus();
}
async function accept(token){
 const profile=await api('/user/me',null,token);
 if(!['admin','developer_admin'].includes(profile.role))throw new Error('Webová správa je určena pouze administrátorům.');
 const status=await api('/user/security/admin-status',null,token);
 if(!status.verified){
   pendingToken=token;
   if(status.enrolled)throw new Error('Ověření vypršelo. Začněte přihlášení znovu.');
   showMode('setupPassword');el('error').textContent='Před prvním vstupem nastavte autentikátor. Znovu potvrďte své heslo.';return;
 }
 await api('/admin-web-session',{},token);
 sessionStorage.setItem('adminAccessToken',token);sessionStorage.setItem('adminRole',profile.role);
 pendingToken=null;challenge=null;el('secret').textContent='';form.reset();location.replace('/web_admin/');
}
el('restart').addEventListener('click',()=>{pendingToken=null;challenge=null;el('secret').textContent='';el('error').textContent='';showMode('login');});
form.addEventListener('submit',async event=>{event.preventDefault();button.disabled=true;el('error').textContent='';try{
 if(mode==='setupPassword'){
   const data=await api('/user/security/totp/setup',{current_password:el('password').value},pendingToken);
   el('secret').textContent=data.secret;showMode('setupCode');return;
 }
 if(mode==='setupCode'){
   const data=await api('/user/security/totp/enable',{code:el('code').value},pendingToken);
   el('secret').textContent='';await accept(data.access_token);return;
 }
 const data=mode==='otp'?await api('/user/login/2fa',{challenge_token:challenge,code:el('code').value}):await api('/user/login',{email:el('email').value.trim(),password:el('password').value});
 el('password').value='';
 if(data.two_factor_required){challenge=data.challenge_token;showMode('otp');return;}
 await accept(data.access_token);
}catch(e){el('error').textContent=e.message;}finally{button.disabled=false;el('code').value='';}});
