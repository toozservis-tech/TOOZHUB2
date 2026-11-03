'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.resolve(__dirname,'../../web/legacy-app.js'),'utf8');
const start=source.indexOf('        function captureClientGeolocation(force = false) {'),end=source.indexOf('        function startClientGeoRefresh()',start);
assert(start>=0&&end>start);const actualFunction=source.slice(start,end);
function fixture({anonymous=false}={}){
 let bearer=anonymous?null:'unit-session-a',generation=1,calls=0,callback;const saved=[];
 const ctx={AdminBrowserSession:{token:()=>bearer,snapshot:()=>({generation}),assertCurrent(value){if(!bearer||value.generation!==generation)throw new DOMException('Changed account','AbortError');}},navigator:{geolocation:{getCurrentPosition(success){calls++;callback=success;}}},Date,Number,clientGeoLastAttemptAt:0,CLIENT_GEO_MIN_RETRY_MS:300000,saveClientGeoTelemetry:value=>saved.push(value)};
 vm.runInNewContext(actualFunction+'\nglobalThis.capture=captureClientGeolocation;',ctx);
 return {run:()=>ctx.capture(true),calls:()=>calls,saved,finish:()=>callback?.({coords:{latitude:49.1234567,longitude:16.7654321,accuracy:12.4}}),rotate(){bearer='unit-session-b';},switchAccount(){generation++;bearer='unit-other-account';}};
}
test('actual geolocation function never asks an anonymous browser for location',()=>{
 const f=fixture({anonymous:true});f.run();assert.equal(f.calls(),0);assert.deepEqual(f.saved,[]);
});
test('actual geolocation function requests once for an ordinary authenticated account',()=>{
 const f=fixture();f.run();assert.equal(f.calls(),1);f.finish();assert.equal(f.saved.length,1);assert.equal(f.saved[0].lat,49.123457);assert.equal(f.saved[0].lon,16.765432);assert.equal(f.saved[0].accuracy,12);
});
test('actual geolocation callback survives credential rotation within the same account generation',()=>{
 const f=fixture();f.run();f.rotate();f.finish();assert.equal(f.calls(),1);assert.equal(f.saved.length,1);
});
test('actual geolocation callback cannot publish the previous account location after an account switch',()=>{
 const f=fixture();f.run();f.switchAccount();f.finish();assert.equal(f.calls(),1);assert.deepEqual(f.saved,[]);
});
