'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const timeline = require('../../web/job-timeline.js');
const vectors = require('../fixtures/service-job-timeline-v1.json');
const precisionVectors = require('../fixtures/service-job-timeline-precision-extra.json');
const root = path.resolve(__dirname, '../..');
const event = (id, extra = {}) => ({id, actor_id: 1, status: 'completed', created_at: '2026-11-03T09:00:00', message: 'Fotografie: Práce', ...extra});
const freeze = value => { if (value && typeof value === 'object') { Object.freeze(value); Object.values(value).forEach(freeze); } return value; };

function verifyVector(fixture) {
    const input = freeze(structuredClone(fixture.events)), before = JSON.stringify(input), actual = timeline.rows(input);
    assert.deepEqual(actual.map(row => ({kind: row.kind, title: timeline.rowTitle(row), ids: row.events.map(value => value.id)})), fixture.expected);
    assert.equal(JSON.stringify(input), before);
    assert.deepEqual(actual.flatMap(row => row.events), input);
    actual.flatMap(row => row.events).forEach((value, index) => assert.equal(value, input[index], 'retain original events, including duplicates'));
    assert.doesNotThrow(() => JSON.stringify(actual), 'No precision representation may leak into audit/JSON values');
}
for (const fixture of vectors.cases) test('shared vector: ' + fixture.name, () => verifyVector(fixture));
for (const fixture of precisionVectors.cases) test('shared precision vector: ' + fixture.name, () => verifyVector(fixture));

test('a positive integer actor and a nonempty status are required; malformed actors never merge', () => {
    for (const actor_id of [null, undefined, 0, -1, 1.5, '1', Number.MAX_SAFE_INTEGER + 1]) assert.equal(timeline.rows([event('a', {actor_id}), event('b', {actor_id})]).length, 2);
    for (const status of ['', null, undefined, 3]) assert.equal(timeline.rows([event('a', {status}), event('b', {status})]).length, 2);
});
test('timestamps validate leap days, fractions and offsets; naive values are UTC', () => {
    assert.equal(timeline.timestamp('2026-11-03T09:00:00'), Date.UTC(2026, 10, 3, 9) / 1000);
    assert.equal(timeline.timestamp('2026-11-03T10:00:00+01:00'), timeline.timestamp('2026-11-03T04:00:00-05:00'));
    assert.equal(timeline.timestamp('2024-02-29T23:59:59.123456789Z') !== null, true);
    assert.equal(timeline.timestamp('0001-01-01T00:00:00Z') !== null, true);
    for (const value of ['0000-01-01T00:00:00', '2026-02-29T00:00:00', '2026-04-31T00:00:00', '2026-13-01T00:00:00', '2026-01-00T00:00:00', '2026-01-01T00:60:00', '2026-01-01T00:00:60', '2026-01-01T00:00:00+24:00', '2026-01-01T00:00:00+01:60', '2026-01-01T00:00:00.1234567890', '2026-01-01T00:00:00Z\n', '2026-01-01', '', null]) assert.equal(timeline.timestamp(value), null, String(value));
});
test('the 300-second window is measured from the first event, including fractional boundaries', () => {
    const result = timeline.rows([event('a', {created_at: '2026-11-03T09:00:00.500Z'}), event('b', {created_at: '2026-11-03T09:05:00.500Z'}), event('c', {created_at: '2026-11-03T09:05:00.501Z'})]);
    assert.deepEqual(result.map(row => row.events.map(value => value.id)), [['a', 'b'], ['c']]);
});
test('the exact window retains a nonzero fractional origin, second carries and equivalent offset fractions', () => {
    for (const [first, last, count] of [
        ['2026-11-03T09:00:00.500000001Z', '2026-11-03T09:05:00.500000001Z', 1],
        ['2026-11-03T09:00:00.500000001Z', '2026-11-03T09:05:00.500000002Z', 2],
        ['2026-11-03T09:00:00.999999999Z', '2026-11-03T09:05:01.000000000Z', 2],
        ['2026-11-03T09:00:00.1Z', '2026-11-03T10:00:00.100000000+01:00', 1],
        ['2026-11-03T23:59:59.999999999Z', '2026-11-04T00:00:00.000000000Z', 2],
    ]) assert.equal(timeline.rows([event('first', {created_at: first}), event('last', {created_at: last})]).length, count, first + ' → ' + last);
});
test('duplicate IDs and equal original messages are preserved without sorting or deduplication', () => {
    const input = [event('same'), event('same'), event('0', {created_at: '2026-11-03T08:00:00'})];
    assert.deepEqual(timeline.rows(input).map(row => row.events.map(value => value.id)), [['same', 'same'], ['0']]);
    assert.deepEqual(timeline.rows(input).map(row => row.firstIndex), [0, 2]);
});
test('unknown/empty status uses a neutral label; an empty status is not a lifecycle transition', () => {
    assert.equal(timeline.statusTitle('unknown'), 'Záznam zakázky');
    assert.equal(timeline.statusTitle('cancelled'), 'Zakázka zrušena');
    assert.deepEqual(timeline.rows([event('a', {status: '', message: 'Poznámka'}), event('b', {status: '', message: 'Další'})]).map(timeline.rowTitle), ['Záznam zakázky', 'Záznam zakázky']);
});

// Execute the actual DOM renderer. Deliberately reject HTML parsing so literal
// private captions cannot become elements, attributes, scripts or event handlers.
class Node {
    constructor(tag) { this.tag = tag; this.children = []; this.attributes = {}; this.style = {setProperty(key, value) { this[key] = value; }}; this.handlers = {}; this._text = ''; this.isConnected = true; this.hidden = false; }
    set innerHTML(value) { if (!this.allowHTML) throw new Error('Timeline must render literal text'); this._text = String(value); this.children = []; }
    set textContent(value) { this._text = String(value); this.children = []; }
    get textContent() { return this._text + this.children.map(child => child.textContent).join(''); }
    append(...nodes) { this.children.push(...nodes); }
    replaceChildren(...nodes) { this._text = ''; this.children = nodes; }
    setAttribute(key, value) { this.attributes[key] = String(value); }
    getAttribute(key) { return this.attributes[key] ?? null; }
    addEventListener(type, handler) { (this.handlers[type] ||= []).push(handler); }
    click() { return Promise.all((this.handlers.click || []).map(handler => handler())); }
    closest() { return new Node('dialog'); }
    insertBefore(node, target) { this.children.splice(this.children.indexOf(target), 0, node); }
}
const document = {createElement: tag => new Node(tag), createTextNode: value => { const node = new Node('#text'); node.textContent = value; return node; }};
const descendants = node => [node, ...node.children.flatMap(descendants)];
const find = (node, fn) => descendants(node).find(fn);
const visible = node => node.hidden || node.style.display === 'none' || node.tag === 'style' ? '' : node._text + node.children.map(visible).join('');

test('compact DOM has one row for six photos with latest time; expansion preserves all six original messages/times', async () => {
    const input = structuredClone(vectors.cases[0].events);
    input.slice(2).forEach((value, index) => { value.message += ' ' + index; value.created_at = '2026-11-03T09:0' + (index < 3 ? 1 : 2) + ':00'; });
    const section = timeline.render(document, input), list = find(section, node => node.className === 'job-timeline-list');
    assert.equal(list.children.length, 3);
    const group = list.children[2], button = find(group, node => node.tag === 'button'), originals = find(group, node => node.className === 'job-timeline-originals');
    assert.equal(group.attributes['data-timeline-count'], '6');
    assert.equal(group.children[0].children[0].textContent, 'Přidány fotografie · 6');
    assert.equal(group.children[0].children[1].attributes.datetime, '2026-11-03T09:02:00.000Z');
    assert.equal(originals.children.length, 6); assert.equal(originals.hidden, true); assert.equal(originals.style.display, 'none');
    assert.equal(button.attributes['aria-controls'], originals.id); assert.equal(button.attributes['aria-expanded'], 'false');
    assert.equal(visible(section).includes(input[2].message), false);
    await button.click();
    assert.equal(button.attributes['aria-expanded'], 'true'); assert.equal(originals.hidden, false); assert.equal(originals.style.display, 'block');
    input.slice(2).forEach((value, index) => { assert.equal(originals.children[index].children[1].textContent, value.message); assert.equal(visible(section).includes(value.message), true); });
    await button.click(); assert.equal(originals.hidden, true); assert.equal(visible(section).includes(input[2].message), false);
});
test('singleton caption is literal and complete; its exact original message remains locally reachable', async () => {
    const caption = '<img src=x onerror=steal()> & "foto"\n' + 'Dlouhý popisek '.repeat(40);
    const original = event('x', {message: 'Fotografie doplněná po dokončení: ' + caption});
    const section = timeline.render(document, [original]), button = find(section, node => node.tag === 'button');
    assert.equal(find(section, node => node.className === 'job-timeline-message').textContent, caption);
    assert.equal(visible(section).includes(caption), true); assert.equal(visible(section).includes(original.message), false);
    await button.click(); assert.equal(visible(section).includes(original.message), true);
    assert.equal(descendants(section).some(node => ['img', 'script', 'a'].includes(node.tag)), false);
});
test('ordinary events retain exact messages, unknown timestamp text and independent lifecycle transitions', () => {
    const input = [event('1', {status: 'received', message: 'Příjem'}), event('2', {status: 'completed', message: '<b>Hotovo</b>'}), event('3', {message: 'Poznámka', created_at: 'invalid'}), event('4', {message: 'Dokument: Faktura.pdf'}), event('5', {status: 'handed_over', message: 'Předáno'})];
    const section = timeline.render(document, input), list = find(section, node => node.className === 'job-timeline-list');
    assert.deepEqual(list.children.map(node => node.children[0].children[0].textContent), ['Přijato do servisu', 'Servis dokončen', 'Doplněna informace', 'Přidán dokument', 'Vozidlo předáno zákazníkovi']);
    input.forEach((value, index) => assert.equal(list.children[index].children[1].textContent, value.message));
    const invalid = list.children[2].children[0].children[1]; assert.equal(invalid.textContent, 'invalid'); assert.equal(invalid.attributes.datetime, undefined);
    assert.equal(find(section, node => node.tag === 'button'), undefined);
});
test('two rendered timelines have independent accessible disclosures and scoped styles', async () => {
    const a = timeline.render(document, [event('1'), event('2')]), b = timeline.render(document, [event('1'), event('2')]);
    const buttonA = find(a, node => node.tag === 'button'), buttonB = find(b, node => node.tag === 'button');
    assert.notEqual(buttonA.attributes['aria-controls'], buttonB.attributes['aria-controls']);
    await buttonA.click(); assert.equal(buttonB.attributes['aria-expanded'], 'false');
    const style = find(a, node => node.tag === 'style').textContent;
    for (const selector of style.match(/[^{}]+(?=\{)/g)) assert.ok(selector.trim().startsWith('.job-timeline'), selector);
    assert.match(style, /\.job-timeline \[hidden\] \{display:none !important;\}/);
    assert.doesNotMatch(style, /line-clamp|max-height|overflow:hidden/);
});
test('empty timelines have an explicit accessible empty state', () => {
    const section = timeline.render(document, []); assert.equal(section.attributes['aria-label'], 'Průběh zakázky');
    assert.match(visible(section), /Historie zatím neobsahuje žádné události/);
    assert.equal(find(section, node => node.tag === 'button'), undefined);
});

test('actual normal evidence and guided terminal routes use the same renderer after their real session guards', async () => {
    const source = fs.readFileSync(path.join(root, 'web/service-features.js'), 'utf8'), panels = [], calls = [], renders = [];
    const job = {id: 11, title: 'Testovací zakázka', service_id: 1, status: 'handed_over', consent_status: 'approved', workflow_version: 1, workflow: {}, photos: [], documents: [], events: vectors.cases[0].events};
    const actor = {id: 2, role: 'user'};
    const ui = {
        request: async url => { calls.push(url); if (url === '/user/me') return actor; if (url === '/api/v1/service-jobs/11') return job; if (url === '/api/v1/vehicles/9/service-jobs') return {items: [job]}; throw Error('Unexpected data request ' + url); },
        panel: title => { const node = new Node('div'); node.allowHTML = true; node.panelTitle = title; panels.push(node); return node; },
        action: (title, handler) => { const node = new Node('button'); node.textContent = title; node.addEventListener('click', handler); return node; }, h: value => String(value),
    };
    let assertions = 0;
    const legacyDocument = {...document, createElement: tag => { const node = new Node(tag); node.allowHTML = true; return node; }};
    const window = {CustomerWeb: {}, CustomerFeatures: {ui}, ServiceJobTimeline: {render(doc, values) { renders.push({assertions, values}); return timeline.render(doc, values); }}, AdminBrowserSession: {snapshot: () => ({generation: 1}), assertCurrent: () => { assertions++; }}, addEventListener() {}};
    // IndexedDB is only the existing guarded command reader; it performs no write.
    const indexedDB = {open() { const request = {}; setImmediate(() => { request.result = {close() {}, transaction() { const tx = {objectStore() { return {get() { const get = {}; setImmediate(() => { get.result = undefined; get.onsuccess(); tx.oncomplete(); }); return get; }}; }}; return tx; }}; request.onsuccess(); }); return request; }};
    vm.runInNewContext(source, {window, document: legacyDocument, URL, location: {origin: 'https://fixture.invalid'}, indexedDB});
    await window.ServiceFeatures.jobEvidence(11);
    assert.equal(renders.length, 1); assert.equal(renders[0].values, job.events); assert.ok(renders[0].assertions >= 2);
    assert.equal(find(panels.at(-1), node => node.attributes['data-job-timeline'] === '') !== undefined, true);
    // Enter the actual guided route through the service-author job-card action.
    actor.id = 1; actor.role = 'service'; await window.ServiceFeatures.jobs(9);
    const guidedButton = find(panels.at(-1), node => node.tag === 'button' && node.textContent === 'Pokračovat krok za krokem');
    assert.ok(guidedButton, 'actual guided navigation remains reachable'); await guidedButton.click();
    assert.equal(renders.length, 2); assert.equal(renders[1].values, job.events); assert.ok(renders[1].assertions > renders[0].assertions);
    assert.equal(find(panels.at(-1), node => node.attributes['data-job-timeline'] === '') !== undefined, true);
    assert.ok(calls.every(value => !/photos\/|updates|documents\//.test(value)), 'display projection does not request or mutate evidence');
});
test('customer HTML loads the public helper before service features without changing API gates', () => {
    const webAccess = fs.readFileSync(path.join(root, 'src/server/web_access.py'), 'utf8');
    assert.match(webAccess, /PUBLIC_WEB_PAGES\s*=\s*\{[\s\S]*?"job-timeline\.js"/);
    assert.match(webAccess, /<script src="job-timeline\.js"><\/script><script src="service-features\.js"><\/script>/);
    assert.equal((webAccess.match(/job-timeline\.js/g) || []).length, 2);
});
