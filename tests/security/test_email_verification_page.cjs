// Simulated document and transport only; never sends mail or verifies a real token.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const script = fs.readFileSync('web/verify-email.html','utf8').match(/<script>([\s\S]*?)<\/script>/)[1];
function page(hash='#token='+'fixture_'.repeat(6), response={ok:true,data:{message:'ok'}}) {
  const nodes = Object.fromEntries(['confirm','message','open-app','open-hint'].map(id=>[id,{hidden:id.startsWith('open-'),disabled:false,textContent:''}]));
  const calls=[];const history=[];
  const context={URLSearchParams,document:{getElementById:id=>nodes[id]},location:{hash,pathname:'/web/verify-email.html'},history:{replaceState:(...args)=>history.push(args)},fetch:async(url,options)=>{calls.push({url,options});if(response.error)throw response.error;return{ok:response.ok,json:async()=>response.data};}};
  vm.runInNewContext(script,context);
  return {nodes,calls,history,context};
}
test('token stays out of page URL and confirmation requires a click',()=>{const p=page();assert.equal(p.history[0][2],'/web/verify-email.html');assert.equal(p.calls.length,0);assert.equal(p.nodes['open-app'].hidden,true);});
test('missing or malformed link cannot call the endpoint',async()=>{for(const hash of ['', '#token=short', '#token=%3Cscript%3E']){const p=page(hash);await p.nodes.confirm.onclick();assert.equal(p.nodes.confirm.disabled,true);assert.equal(p.calls.length,0);}});
test('verified email reveals app link, consumes token and prevents double submission',async()=>{const p=page();await p.nodes.confirm.onclick();await p.nodes.confirm.onclick();assert.equal(p.calls.length,1);assert.equal(p.calls[0].url,'/user/email-verification/confirm');assert.equal(p.calls[0].options.credentials,'omit');assert.equal(p.nodes.confirm.hidden,true);assert.equal(p.nodes['open-app'].hidden,false);assert.equal(p.nodes['open-hint'].hidden,false);});
test('server refusal is text, not HTML, and does not claim verification',async()=>{const p=page(undefined,{ok:false,data:{detail:'<img src=x onerror=alert(1)>'}});await p.nodes.confirm.onclick();assert.match(p.nodes.message.textContent,/<img/);assert.equal(p.nodes['open-app'].hidden,true);assert.equal(p.nodes.confirm.disabled,false);});
test('connection loss leaves a retry with the same token',async()=>{const p=page(undefined,{error:new Error('fixture outage')});await p.nodes.confirm.onclick();assert.equal(p.nodes.confirm.disabled,false);assert.equal(p.nodes['open-app'].hidden,true);await p.nodes.confirm.onclick();assert.equal(p.calls.length,2);assert.equal(p.calls[0].options.body,p.calls[1].options.body);});
