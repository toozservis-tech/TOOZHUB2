'use strict';
// Execute the real module and public actions with a small DOM and intercepted transport.
// This verifies notice transitions, not browser layout, real API behavior or platform parity.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {randomUUID} = require('node:crypto');

class Element {
    constructor(tag) { this.tagName=tag; this.children=[]; this.parentElement=null; this.listeners=new Map(); this.attributes={}; this.dataset={}; this.value=''; this.hidden=false; this.disabled=false; this.checked=false; this.open=false; this._text=''; }
    get isConnected() { return this.root === true || Boolean(this.parentElement?.isConnected); }
    set textContent(value) { this.replaceChildren(); this._text=String(value); }
    get textContent() { return this._text + this.children.map(child => child.textContent).join(''); }
    append(...children) { for (const child of children) { child.remove(); child.parentElement=this; this.children.push(child); if (this.tagName === 'select' && this.children.length === 1) this.value=child.value; } }
    prepend(child) { child.remove(); child.parentElement=this; this.children.unshift(child); }
    replaceChildren(...children) { for (const child of this.children) child.parentElement=null; this.children=[]; this._text=''; this.append(...children); }
    remove() { if (this.parentElement) this.parentElement.children=this.parentElement.children.filter(child => child !== this); this.parentElement=null; }
    setAttribute(name, value) { this.attributes[name]=String(value); }
    addEventListener(name, callback, options={}) { const listeners=this.listeners.get(name) || []; listeners.push({callback, once:options.once}); this.listeners.set(name, listeners); }
    emit(name) { const listeners=this.listeners.get(name) || []; this.listeners.set(name,listeners.filter(listener => !listener.once)); return listeners.map(listener => listener.callback({preventDefault(){}})); }
    async click() { if (this.disabled) return; const direct=this.onclick?.(), listeners=this.emit('click'); await direct; await Promise.all(listeners); }
    showModal() { this.open=true; }
    close() { if (!this.open) return; this.open=false; this.emit('close'); }
}
const walk = node => [node, ...node.children.flatMap(walk)];
function fixture(kind, outcomes=[]) {
    const body=new Element('body'); body.root=true;
    const document={body,createElement:tag => new Element(tag)}, posts=[];
    const result=kind === 'sale'
        ? {vehicle_id:1,action:'sold',state:'archived',message:'Stav byl uložen.'}
        : {id:11,status:'pending',buyer_email:'buyer@example.invalid',delivery_status:'sent'};
    const env={document,crypto:{randomUUID},setInterval:()=>1,clearInterval(){},addEventListener(){},dispatchEvent(){}};
    env.AdminBrowserSession={token:()=> 'synthetic',snapshot:()=>({generation:1}),assertCurrent(){},async request(url,init) {
        if (init.method === 'POST') {
            posts.push({url,body:JSON.parse(init.body)});
            const outcome=outcomes.shift() || {status:200,data:result};
            return {ok:outcome.status === 200,status:outcome.status,json:async()=>outcome.data};
        }
        const data=url === '/user/me' ? {id:1,role:kind === 'sale' ? 'user' : 'admin',email:'seller@example.invalid'}
            : kind === 'sale' ? {vehicle_id:1,state:'active',actions:['sold'],ownership_id:2,ownership_token:'a'.repeat(64),version:1,sale_details_version:2}
            : {vehicle_id:1,title:'Testovací vozidlo',owner_email:'seller@example.invalid',can_invite:true,review_token:'b'.repeat(64)};
        return {ok:true,status:200,json:async()=>data};
    }};
    vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../../web/vehicle-transfers.js'),'utf8'),{window:env,DOMException,AbortController,CustomEvent});
    const all=()=>walk(body), find=predicate=>{const found=all().find(predicate); assert.ok(found,'Required product control was rendered'); return found;};
    const button=text=>find(node => node.tagName === 'button' && node.textContent === text);
    const field=label=>find(node => node.tagName === 'label' && node._text === label).children[0];
    const next=kind === 'sale' ? 'Pokračovat k potvrzení prodeje' : 'Připravit ověřený převod';
    const confirm=kind === 'sale' ? 'Potvrdit prodej' : 'Potvrdit ověřený převod';
    return {posts,button,field,notice:()=>find(node => node.className === 'referral-notice'),hasSuccess:()=>all().some(node => node.tagName === 'h3' && node.textContent === (kind === 'sale' ? 'Změna potvrzena' : 'Pozvánka je připravená')),
        async open() { if (kind === 'sale') { await env.VehicleTransfers.openManagement(1); await button('Prodat vozidlo').click(); } else await env.VehicleTransfers.openAdminReview(1); },
        invalid:()=>button(next).click(),
        async submit() {
            field(kind === 'sale' ? 'E-mail nového majitele · povinné' : 'E-mail nového majitele').value='buyer@example.invalid';
            if (kind !== 'sale') { field('Jak jste vlastnictví ověřili · povinné').value='Testovací doložené ověření převodu.'; find(node => node.type === 'checkbox').checked=true; }
            const pending=button(next).click(); await button(confirm).click(); await pending;
        },
        retry:()=>button(kind === 'sale' ? 'Znovu odeslat stejný požadavek' : 'Znovu ověřit stejný převod').click()
    };
}
for (const kind of ['sale','admin']) {
    test(kind+': corrected required email does not leave a validation alert above the confirmed result',async()=>{
        const f=fixture(kind); await f.open(); await f.invalid();
        assert.match(f.notice().textContent,/Vyplňte platný e-mail/); assert.equal(f.notice().hidden,false); assert.equal(f.posts.length,0);
        await f.submit(); assert.equal(f.posts.length,1); assert.equal(f.hasSuccess(),true);
        assert.equal(f.notice().textContent,''); assert.equal(f.notice().hidden,true); assert.equal(f.notice().attributes.role,'status');
    });
    test(kind+': a genuine API rejection remains visible after corrected validation',async()=>{
        const f=fixture(kind,[{status:422,data:{detail:'Server odmítl aktuální převod.'}}]); await f.open(); await f.invalid(); await f.submit();
        assert.equal(f.hasSuccess(),false); assert.equal(f.notice().textContent,'Server odmítl aktuální převod.'); assert.equal(f.notice().hidden,false); assert.equal(f.notice().attributes.role,'alert');
    });
    test(kind+': ambiguous-write failure stays visible, then exact retry clears it only on confirmed success',async()=>{
        const f=fixture(kind,[{status:503,data:{detail:'Server je dočasně nedostupný.'}}]); await f.open(); await f.submit();
        assert.equal(f.hasSuccess(),false); assert.equal(f.notice().textContent,'Server je dočasně nedostupný.'); assert.equal(f.notice().hidden,false);
        await f.retry(); assert.equal(f.hasSuccess(),true); assert.equal(f.posts.length,2); assert.deepEqual(f.posts[0],f.posts[1]);
        assert.equal(f.notice().textContent,''); assert.equal(f.notice().hidden,true);
    });
}
