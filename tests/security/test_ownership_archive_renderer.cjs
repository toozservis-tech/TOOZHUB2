'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const {archiveProfileSection,archiveAttachments}=require('../../web/customer-features.js');

// The real renderer must put private values in text nodes. Any innerHTML write
// fails this DOM contract, including when a value looks like executable markup.
class TextOnlyNode {
 constructor(tag){this.tag=tag;this.children=[];this.attributes={};this.style={};this._text='';}
 set innerHTML(_){throw Error('Private archive values must not be parsed as HTML');}
 set textContent(value){this._text=String(value);this.children=[];}
 get textContent(){return this._text+this.children.map(x=>x.textContent).join('');}
 append(...nodes){this.children.push(...nodes);}
 setAttribute(key,value){this.attributes[key]=String(value);}
}
const document={createElement:tag=>new TextOnlyNode(tag)};
const rows=node=>Object.fromEntries(node.children.filter(x=>x.attributes['data-archive-profile-field']).map(x=>[x.attributes['data-archive-profile-field'],x]));

test('archive renderer preserves four original private values as literal text, including HTML and newlines',()=>{
 const profile={notes:'PRIVATE NOTE\n<img src=x onerror=alert(1)> & <script>blocked()</script>',insurance_provider:'TEST "Pojistitel" <soukromý>',tyres_info:'205/55 R16 & 91V',orv_number:'QA123456'};
 const rendered=archiveProfileSection(document,profile),fields=rows(rendered);
 assert.equal(rendered.attributes['data-ownership-archive-profile'],'');
 assert.equal(rendered.children[0].textContent,'Původní údaje · pouze ke čtení');
 assert.equal(fields.notes.textContent,profile.notes);assert.equal(fields.notes.style.whiteSpace,'pre-wrap');
 for(const [key,label] of [['insurance_provider','Pojišťovna'],['tyres_info','Pneumatiky'],['orv_number','Číslo ORV']]){
  assert.equal(fields[key].children[0].textContent,label);assert.equal(fields[key].children[1].textContent,profile[key]);
 }
 assert.deepEqual(rendered.children.map(x=>x.tag),['h4','p','dl','dl','dl']);
});
test('archive renderer limits its projection to approved fields and omits absent or malformed values',()=>{
 const rendered=archiveProfileSection(document,{notes:null,insurance_provider:undefined,tyres_info:{private:'bad'},orv_number:7,owner_email:'not-approved@example.test',photo_path:'private-storage-key',insurance_valid_until:'not-part-of-ios-section'});
 assert.deepEqual(Object.keys(rows(rendered)),[]);
 for(const secret of ['not-approved','private-storage','not-part-of-ios','[object Object]'])assert.equal(rendered.textContent.includes(secret),false);
 assert.equal(archiveProfileSection(document,null).children.length,1);
});
test('empty optional strings are represented without manufacturing replacement account data',()=>{
 const fields=rows(archiveProfileSection(document,{notes:'',insurance_provider:'',tyres_info:'',orv_number:''}));
 assert.deepEqual(Object.keys(fields),['notes','insurance_provider','tyres_info','orv_number']);
 assert.equal(fields.notes.textContent,'');assert.equal(fields.orv_number.children[1].textContent,'');
});
test('archive attachments accept legacy path, deduplicate the exact key, and keep original filename',()=>{
 const key='tenant_demo/vehicle_9/Původní doklad % ?&.pdf';
 const result=archiveAttachments(JSON.stringify([{path:key,file_name:'Původní faktura.pdf'},{storage_key:key,file_name:'duplicate.pdf'},{key:'tenant_demo/vehicle_9/compat.pdf'},{storage_key:'tenant_demo/vehicle_9/a.pdf'}]));
 assert.equal(result.length,3);assert.deepEqual(result.map(x=>x.key),[key,'tenant_demo/vehicle_9/a.pdf','tenant_demo/vehicle_9/compat.pdf'].sort());
 assert.deepEqual(result.find(x=>x.key===key),{key,name:'Původní faktura.pdf'});
 assert.equal(decodeURIComponent(encodeURIComponent(result.find(x=>x.key===key).key)),key);
});
test('storage_key takes precedence over legacy aliases without normalizing private file identity',()=>{
 const key='tenant_demo/vehicle_9/ exact key.pdf ';
 assert.deepEqual(archiveAttachments([{storage_key:key,path:'wrong.pdf',key:'also-wrong.pdf'}]),[{key,name:' exact key.pdf '}]);
 assert.deepEqual(archiveAttachments([{storage_key:null,path:'legacy.pdf',key:'wrong.pdf'}]),[{key:'legacy.pdf',name:'legacy.pdf'}]);
});
test('malformed attachment payloads never produce guessed or coerced file routes',()=>{
 for(const value of ['{broken',{},null,'null','{}','123'])assert.deepEqual(archiveAttachments(value),[]);
 assert.deepEqual(archiveAttachments([null,3,'path.pdf',{storage_key:123},{path:''},{storage_key:{path:'bad'}}]),[]);
});
