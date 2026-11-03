'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(process.env.LEGACY_THUMBNAIL_SOURCE||path.resolve(__dirname,'../../web/legacy-app.js'),'utf8');
const start=source.indexOf('        async function loadRecordThumbnails(root) {'),end=source.indexOf('        async function showServiceRecordDetail(',start);
assert(start>=0&&end>start);const actualFunction=source.slice(start,end);
function fixture({connected=true,path='/api/v1/vehicles/5/records/attachments/download?key=private.jpg'}={}){
 let generation=1,token='unit-bearer-a',release,fetches=0;
 const gate=new Promise(r=>release=r),image={isConnected:connected,getAttribute(){return path;}};
 const session={token:()=>token,snapshot:()=>({generation}),assertCurrent(captured){if(captured.generation!==generation)throw new DOMException('Changed account','AbortError');}};
 const ctx={AdminBrowserSession:session,URL:{createObjectURL:()=> 'blob:unit-private-photo',revokeObjectURL(){}},fetchServiceRecordAttachmentBlob:async()=>{fetches++;await gate;return {size:1};},Promise};
 vm.runInNewContext(actualFunction+'\nglobalThis.load=loadRecordThumbnails;',ctx);
 return {image,run:()=>ctx.load({querySelectorAll:()=>[image]}),release,rotate(){token='unit-bearer-b';},switchAccount(){generation++;token='unit-other-actor';},fetches:()=>fetches};
}
test('actual history thumbnail callback survives a legitimate bearer rotation in the same account generation',async()=>{
 const f=fixture(),pending=f.run();f.rotate();f.release();await pending;assert.equal(f.fetches(),1);assert.equal(f.image.src,'blob:unit-private-photo');
});
test('actual history thumbnail callback does not publish the previous account image after an account switch',async()=>{
 const f=fixture(),pending=f.run();f.switchAccount();f.release();await pending;assert.equal(f.image.src,undefined);
});
test('actual history thumbnail loader skips detached images without requesting private bytes',async()=>{
 const f=fixture({connected:false});f.release();await f.run();assert.equal(f.fetches(),0);assert.equal(f.image.src,undefined);
});
test('actual history thumbnail loader retains the vehicle-bound route restriction',async()=>{
 const f=fixture({path:'https://external.invalid/private.jpg'});f.release();await f.run();assert.equal(f.fetches(),0);assert.equal(f.image.src,undefined);
});
