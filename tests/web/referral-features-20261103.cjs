// Offline presentation/QR checks. This is not product, API, or platform parity evidence.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {parseUTC,rewardState,invitationURL,reasonText,accountCountLabel}=require('../../web/referral-features.js');
const encode=require('../../web/vendor/referral-qr.js');
const decode=require('../../web/vendor/jsQR-1.4.0.js');
const code='Abcdef_0123456789-xyz7890', origin='https://app.example.test';
function url(kind){return `${origin}/api/v1/referrals/join/${code}?kind=${kind}`;}

test('naive API dates are UTC including fractional seconds, explicit offsets retained',()=>{
 assert.equal(parseUTC('2026-11-03T12:30:00.123456').toISOString(),'2026-11-03T12:30:00.123Z');
 assert.equal(parseUTC('2026-11-03T13:30:00+01:00').toISOString(),'2026-11-03T12:30:00.000Z');
 assert.equal(parseUTC(null),null);assert.equal(parseUTC('invalid'),null);
});
test('waiting bonus is not active, revoked wins; queued and expired periods are explicit',()=>{
 const r={starts_at:'2026-11-03T12:30:00',ends_at:'2026-12-03T12:30:00',lifetime:false};
 const now=new Date('2026-11-04T00:00:00Z');
 assert.equal(rewardState({...r,waiting_for_paid:true},now),'waiting');
 assert.equal(rewardState({...r,waiting_for_paid:true,revoked_at:'2026-11-03T15:00:00'},now),'revoked');
 assert.equal(rewardState(r,now),'active');
 assert.equal(rewardState(r,new Date('2026-11-02T00:00:00Z')),'queued');
 assert.equal(rewardState(r,new Date('2026-12-03T12:30:00Z')),'expired');
 assert.equal(rewardState({...r,ends_at:null,lifetime:true},now),'active');
 assert.equal(rewardState({...r,ends_at:null},now),'unknown');
});
test('sharing accepts exact server-owned HTTPS URLs and rejects cross-origin/ambiguous links',()=>{
 for(const kind of ['user','service'])assert.equal(invitationURL(url(kind),origin,code,kind),url(kind));
 for(const bad of [url('service'),url('user')+'&kind=user',url('user')+'&return_to=https://evil.test',url('user')+'#secret',url('user').replace(origin,'https://evil.test'),url('user').replace('https://','javascript:'),url('user').replace('https://','http://'),url('user').replace('https://','https://name:pass@')])assert.throws(()=>invitationURL(bad,origin,code,'user'));
 assert.throws(()=>invitationURL(url('user'),origin,'../other','user'));
 const local=`http://127.0.0.1:18919/api/v1/referrals/join/${code}?kind=user`;
 assert.equal(invitationURL(local,'http://127.0.0.1:18919',code,'user'),local);
});
test('admin reasons require 5–500 Unicode characters after trimming',()=>{
 assert.equal(reasonText('  Platná odměna  '),'Platná odměna');
 for(const bad of ['', '    ', 'čtyř', 'x'.repeat(501)])assert.throws(()=>reasonText(bad));
 assert.equal(reasonText('🚗'.repeat(500)).length,1000);
});
test('Czech account count labels agree for zero, one, two through four and larger counts',()=>{
 assert.equal(accountCountLabel(0),'0 účtů s osobním odkazem');
 assert.equal(accountCountLabel(1),'1 účet s osobním odkazem');
 for(const n of [2,3,4])assert.equal(accountCountLabel(n),`${n} účty s osobním odkazem`);
 for(const n of [5,11,21,31])assert.equal(accountCountLabel(n),`${n} účtů s osobním odkazem`);
});
test('both referral choices round-trip through a real offline QR decoder',()=>{
 for(const kind of ['user','service']){
  const qr=encode(0,'M');qr.addData(url(kind),'Byte');qr.make();
  const border=4,scale=5,size=(qr.getModuleCount()+border*2)*scale;
  const rgba=new Uint8ClampedArray(size*size*4).fill(255);
  for(let y=0;y<qr.getModuleCount();y++)for(let x=0;x<qr.getModuleCount();x++)if(qr.isDark(y,x))for(let yy=0;yy<scale;yy++)for(let xx=0;xx<scale;xx++){
   const at=(((y+border)*scale+yy)*size+(x+border)*scale+xx)*4;rgba[at]=rgba[at+1]=rgba[at+2]=0;
  }
  assert.equal(decode(rgba,size,size)?.data,url(kind));
 }
});
test('bundled encoder is pinned, offline, and keeps its license',()=>{
 const vendor=fs.readFileSync(path.resolve(__dirname,'../../web/vendor/referral-qr.js'),'utf8');
 assert.match(vendor,/qrcode-generator 2\.0\.4/);assert.match(vendor,/Permission is hereby granted/);
 assert.doesNotMatch(vendor,/\b(fetch|XMLHttpRequest|WebSocket)\s*\(/);
});
