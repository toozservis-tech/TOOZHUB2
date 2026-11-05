const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../../web/sw.js'),'utf8');
(async()=>{
 const listeners={},shown=[],sent=[],opened=[],badges=[];
 const client={url:'https://example.test/web/customer.html',focus:async()=>sent.push({focus:true}),postMessage:value=>sent.push(value),navigate:async url=>opened.push(url)};
 const self={navigator:{setAppBadge:async n=>badges.push(n),clearAppBadge:async()=>badges.push(0)},location:{origin:'https://example.test'},addEventListener:(key,fn)=>listeners[key]=fn,skipWaiting(){},registration:{showNotification:async(title,options)=>shown.push({title,options})},clients:{claim:async()=>{},matchAll:async()=>[client],openWindow:async url=>opened.push(url)}};
 vm.runInNewContext(source,{self,URL,Date,Promise,Number});
 async function trigger(kind,data){let promise;listeners[kind]({...data,waitUntil:p=>promise=p});await promise;}
 await trigger('push',{data:{json:()=>({notification_id:41,body:'PRIVATE BODY',title:'PRIVATE TITLE',url:'https://evil.test/',badge_count:3})}});
 assert.equal(shown[0].title,'Evidence Vozidel');assert(!JSON.stringify(shown).includes('PRIVATE'));assert.equal(shown[0].options.data.url,'https://example.test/web/customer.html#notifications/41');assert(sent.some(x=>x.type==='EVIDENCE_NOTIFICATION_REFRESH'));assert.deepEqual(badges,[3]);
 await trigger('notificationclick',{notification:{data:shown[0].options.data,close(){}}});
 assert(sent.some(x=>x.type==='EVIDENCE_NOTIFICATION_OPEN'&&x.notification_id===41));assert.equal(opened.length,0,'Opening notice must not destroy an existing draft by navigating');
 client.url='https://example.test/web/index.html';
 await trigger('notificationclick',{notification:{data:shown[0].options.data,close(){}}});
 assert.equal(opened.at(-1),'https://example.test/web/customer.html#notifications/41','Do not route customer message to admin document');
 await trigger('push',{data:{json:()=>({url:'https://evil.test/',icon:'https://evil.test/x',title:'Legacy reminder'})}});
 assert.equal(shown[1].options.data.url,'https://example.test/web/index.html');assert.equal(shown[1].options.icon,'https://example.test/web/assets/toozservis-logo-icon.png');
 assert(!/fetch\(/.test(source),'Worker never reads, confirms or dismisses a message on click');
 console.log('PASS: generic private push, same-origin URL, foreground refetch, exact item route, retained draft, admin separation, no receipts.');
})().catch(error=>{console.error(error);process.exitCode=1;});
