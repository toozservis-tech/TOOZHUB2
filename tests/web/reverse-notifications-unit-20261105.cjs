// Isolated VM tests of actual client functions. No browser, HTTP or fixture mutation.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {webcrypto}=require('node:crypto');
class Element {
 constructor(tag='div'){this.tagName=tag.toUpperCase();this.children=[];this.dataset={};this.style={removeProperty(){},setProperty(){}};this.isConnected=true;this.classList={contains:()=>false,add(){},remove(){},toggle(){}};this.textContent='';}
 insertBefore(child){this.children.push(child);} append(...children){this.children.push(...children);} replaceChildren(...children){this.children=children;} prepend(...children){this.children.unshift(...children);}
 setAttribute(){} addEventListener(){} scrollIntoView(){} focus(){} remove(){this.isConnected=false;} close(){this.open=false;} showModal(){this.open=true;} querySelector(){return new Element();} querySelectorAll(){return [];}
}
const plain=v=>JSON.parse(JSON.stringify(v));
function host(file,exportNames){
 let revision=1;const slots={},values=new Map(),requests=[];
 const doc={hidden:false,readyState:'loading',body:new Element(),createElement:tag=>new Element(tag),getElementById:id=>slots[id]||null,querySelectorAll:()=>[],addEventListener(){},hasFocus:()=>true};
 slots.dashboard=new Element();slots.dashboard.classList.contains=c=>c==='active';
 const session={token:()=> 'synthetic-unit-not-a-JWT',snapshot:()=>({revision}),assertCurrent:s=>{if(s.revision!==revision)throw new DOMException('changed','AbortError');},request:async(url,init={},snapshot)=>{session.assertCurrent(snapshot);requests.push({url,method:init.method||'GET',body:init.body?JSON.parse(init.body):null});return {ok:true,json:async()=>({})};}};
 const window={document:doc,CustomerWeb:true,AdminBrowserSession:session,addEventListener(){}};
 const sandbox={window,document:doc,crypto:webcrypto,TextEncoder,DOMException,URL,URLSearchParams,Date,console,location:{origin:'http://127.0.0.1:1',hash:''},navigator:{},sessionStorage:{getItem:key=>values.get(key)||null,setItem:(key,value)=>values.set(key,value),removeItem:key=>values.delete(key)},IntersectionObserver:class{observe(){}disconnect(){}},ResizeObserver:class{observe(){}disconnect(){}},setTimeout:()=>1,clearTimeout(){},setInterval:()=>1,clearInterval(){},requestAnimationFrame:fn=>fn()};
 let source=fs.readFileSync(path.join(__dirname,'../../web',file),'utf8');source=source.replace('})(window);',`global.__checks={${exportNames.join(',')}};\n})(window);`);vm.runInNewContext(source,sandbox,{filename:file});
 return {api:window.__checks,window,doc,slots,session,values,requests,changed:()=>revision++,context:()=>({session,snapshot:session.snapshot(),actor:{id:7,role:'service'},closed:false}),Element};
}
(async()=>{
 const h=host('notification-center.js',['validItem','isPending','relatedRoute','replyReferenceFor','status','complete','openRelated','authorize']);
 const base={id:101,source_id:17,title:'Synthetic',body:'<script>not HTML</script>',kind:'service_event',requires_ack:false,read_at:null,acknowledged_at:null,dismissed_at:null};
 assert.equal(h.api.validItem(base),base);assert.equal(h.api.isPending(base),false);
 assert.equal(h.api.isPending({...base,kind:'admin_reply'}),false);
 assert.equal(h.api.isPending({...base,kind:'announcement'}),true);
 assert.equal(h.api.isPending({...base,kind:'announcement',archived:true}),false);
 assert.deepEqual(plain(h.api.replyReferenceFor({...base,kind:'admin_message'})),{reply_to_message_id:17});
 assert.deepEqual(plain(h.api.replyReferenceFor({...base,kind:'announcement'})),{reply_to_notification_id:17});
 assert.throws(()=>h.api.replyReferenceFor(base));assert.throws(()=>h.api.replyReferenceFor({...base,kind:'announcement',source_id:0}));
 const ctx=h.context();
 for(const [type,id,pathValue] of [['reservation',41,'/api/v1/reservations/41/workspace'],['booking_request',52,'/api/v1/service-booking-requests/52'],['service_access',63,'/api/v1/service-notification-events/63']]){
  const item={...base,action:{type,id,vehicle_id:999}},route=h.api.relatedRoute(ctx,item);assert.equal(route.path,pathValue);assert.equal(route.id,id);
  assert.equal(h.api.relatedRoute({...ctx,actor:{id:8,role:'user'}},item),null);
 }
 assert.equal(h.api.relatedRoute(ctx,{...base,action:null}),null);
 assert.equal(h.api.relatedRoute(ctx,{...base,action:{type:'https://evil.test',id:1}}),null);
 assert.equal(h.api.relatedRoute(ctx,{...base,action:{type:'reservation',id:'41'}}),null);
 const reply={...base,kind:'admin_reply',action:{type:'admin_conversation',id:23}};
 assert.equal(h.api.relatedRoute(ctx,reply),null);
 h.window.CustomerWeb=false;h.slots['admin-notification-entry']=new Element();h.slots['dashboard-screen']=new Element();
 const admin={...ctx,actor:{id:9,role:'admin'}};
 assert.deepEqual(plain(h.api.relatedRoute(admin,reply)),{type:'admin_conversation',id:23,label:'Otevřít konverzaci'});
 let target;h.window.AdminMessages={openAdmin:async id=>target=id};await h.api.openRelated(admin,reply,h.api.relatedRoute(admin,reply));assert.equal(target,23);
 h.window.CustomerWeb=true;delete h.slots['admin-notification-entry'];
 const denied={...h.context(),detailVersion:1,body:new Element(),heading:new Element(),notice:new Element(),dialog:new Element()};
 h.session.request=async()=>({ok:false,status:403,json:async()=>({detail:'denied'})});
 await assert.rejects(h.api.openRelated(denied,{...base,action:{type:'reservation',id:41}},h.api.relatedRoute(denied,{...base,action:{type:'reservation',id:41}})),/denied/);
 assert.equal(denied.body.children.length,0,'Denied service target must not render stale data');
 const flatten=el=>[el.textContent||'',...el.children.map(child=>typeof child==='string'?child:flatten(child))].join(' ');
 const minimal={...h.context(),detailVersion:1,body:new Element(),heading:new Element(),notice:new Element(),dialog:new Element()};
 let minimalURL;h.session.request=async url=>{minimalURL=url;return {ok:true,json:async()=>({event_id:63,title:'Souhlas odvolán',occurred_at:'2026-11-05T20:00:00Z',current_status:'revoked',message:'Historická informace',vehicle_id:999,private_jobs:'PRIVATE_JOB_DO_NOT_RENDER'})};};
 const event={...base,action:{type:'service_access',id:63,vehicle_id:999}};
 await h.api.openRelated(minimal,event,h.api.relatedRoute(minimal,event));assert.equal(minimalURL,'/api/v1/service-notification-events/63');assert(flatten(minimal.body).includes('Odvoláno'));assert(!flatten(minimal.body).includes('PRIVATE_JOB_DO_NOT_RENDER'));assert(!flatten(minimal.body).includes('999'));
 const wrong={...h.context(),detailVersion:1,body:new Element(),heading:new Element(),notice:new Element(),dialog:new Element()};h.session.request=async()=>({ok:true,json:async()=>({reservation_id:999})});
 await assert.rejects(h.api.openRelated(wrong,{...base,action:{type:'reservation',id:41}},h.api.relatedRoute(wrong,{...base,action:{type:'reservation',id:41}})),/vybraný podklad/);assert.equal(wrong.body.children.length,0);
 h.session.request=async(url,init)=>({ok:true,json:async()=>{h.requests.push({url,body:JSON.parse(init.body)});return {item:{...base,dismissed_at:'2026-11-05T20:00:00Z'},summary:{unread_count:0,pending_admin_count:0,pending_ack_count:0,badge_count:0}};}});
 h.doc.hidden=true;await h.api.complete(h.context(),base);assert.equal(h.requests.at(-1).url,'/api/v1/notifications/101/dismiss');
 h.session.request=async()=>({ok:true,json:async()=>({item:base,summary:{}})});
 await assert.rejects(h.api.complete(h.context(),base),/nepotvrdil/,'A reverse kind requires a real dismissed_at receipt, not absence from forced-pending');
 const stale=h.context();h.changed();await assert.rejects(h.api.openRelated(stale,{...base,action:{type:'reservation',id:41}},{type:'reservation',id:41}),e=>e.name==='AbortError');
 console.log('PASS notification contract: source namespaces, exact routes, admin recipient guard, no consent mutation, no forced modal, denied/stale responses, explicit dismiss receipt.');
 const m=host('admin-messages.js',['replyReference','referenceFromBody','commandFor','send','showPending']);
 assert.throws(()=>m.api.replyReference({reply_to_message_id:1,reply_to_notification_id:2}));assert.throws(()=>m.api.replyReference({addressed_admin_id:9}));assert.throws(()=>m.api.replyReference({reply_to_message_id:-1}));
 const mc={...m.context(),accountID:7};const a={body:'Synthetic exact text',reply_to_message_id:2},b={body:'Synthetic exact text',reply_to_message_id:3},c={body:'Synthetic exact text',reply_to_notification_id:2};
 const aID=await m.api.commandFor(mc,a);assert.equal(await m.api.commandFor(mc,a),aID);assert.notEqual(await m.api.commandFor(mc,b),aID);assert.notEqual(await m.api.commandFor(mc,c),aID);assert.notEqual(await m.api.commandFor(mc,{body:a.body}),aID);
 const persisted=JSON.parse([...m.values.values()][0]);assert(!JSON.stringify(persisted).includes(a.body));assert.deepEqual(persisted[0].reference,{reply_to_message_id:2});
 // A reload preserves command metadata only, never the private body, and reuses exact UUID + reference.
 const reload=host('admin-messages.js',['commandFor']);for(const [key,value]of m.values)reload.values.set(key,value);assert.equal(await reload.api.commandFor({...reload.context(),accountID:7},a),aID);
 const sendctx={...m.context(),admin:false,accountID:7,path:'/api/v1/admin-messages',key:'unit-account',replyReference:{reply_to_notification_id:17},compose:Object.assign(new Element('textarea'),{value:'Synthetic reply'}),exit:new Element(),sendButton:new Element(),retry:new Element(),notice:new Element(),busy:false};
 let sent;m.session.request=async(url,init)=>{sent=JSON.parse(init.body);throw Error('uncertain network');};
 await assert.rejects(m.api.send(sendctx),/uncertain network/);assert.deepEqual(Object.keys(sent).sort(),['body','client_id','reply_to_notification_id']);assert.equal(sent.reply_to_notification_id,17);const first=JSON.stringify(sent);
 sendctx.replyReference={reply_to_message_id:999};await assert.rejects(m.api.send(sendctx),/uncertain network/);assert.equal(JSON.stringify(sent),first,'Uncertain retry cannot switch original reply namespace or ID');
 console.log('PASS message contract: mutually exclusive refs, same-ID namespace separation, exact UUID retry/reload, no plaintext body storage, no target-admin input.');
})().catch(error=>{console.error(error);process.exitCode=1;});
