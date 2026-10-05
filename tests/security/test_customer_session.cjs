const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm'),fs=require('node:fs');
function fixture(fetcher=async()=>new Response('{}')) {
 const storage=()=>{const d={};return {getItem:k=>d[k]??null,setItem:(k,v)=>d[k]=v,removeItem:k=>delete d[k]};};
 const window={addEventListener(){},dispatchEvent(){}};
 const ctx={window,localStorage:storage(),sessionStorage:storage(),document:{addEventListener(){}},location:{origin:'https://example.com',pathname:'/web/customer.html',replace(){}},URL,Headers,Response,AbortController,DOMException,Proxy,Reflect,Set,Map,JSON,Date,Number,Math,Object,String,atob,crypto:require('node:crypto').webcrypto,setTimeout,clearTimeout,Event,CustomEvent,fetch:fetcher};
 vm.runInNewContext(fs.readFileSync('web/customer-session.js','utf8'),ctx);
 return {s:window.AdminBrowserSession,ctx};
}
test('anonymous login allowed but protected requests and cross-origin credentials blocked',async()=>{
 const calls=[];const {s}=fixture(async(u,o)=>{calls.push([u,o]);return new Response('{}');});
 await (await s.request('/user/login',{method:'POST'})).json();
 assert.equal(calls[0][1].headers.has('Authorization'),false);
 await assert.rejects(s.request('/api/v1/vehicles'));
 s.set('account-a','user');
 await assert.rejects(s.request('https://attacker.invalid/'));
 assert.equal(calls.length,1);
});
test('administrator token cannot enter customer session',()=>{
 const {s}=fixture();assert.throws(()=>s.set('admin-token','admin'));assert.equal(s.token(),null);
});
test('late response after account switch cannot reveal previous account data',async()=>{
 let finish;const {s}=fixture(()=>new Promise(r=>finish=r));s.set('a','user');
 const pending=s.request('/user/me');s.set('b','user');finish(new Response('{"private":"a"}'));
 await assert.rejects(pending,{name:'AbortError'});assert.equal(s.token(),'b');
});
test('customer tokens stay session-only and unauthorized response clears session',async()=>{
 const {s,ctx}=fixture(async()=>new Response('{}',{status:401}));s.set('a','user');
 assert.equal(ctx.localStorage.getItem('customerWebAccessToken'),null);
 await assert.rejects(s.request('/user/me'));assert.equal(s.token(),null);
});
