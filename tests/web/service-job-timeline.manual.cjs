/* Actual UI only: ordinary password login and readonly navigation. No token/API/clock injection. */
'use strict';
const fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto'), assert = require('node:assert/strict');
const {spawnSync} = require('node:child_process');
const args = {}; for (let i = 2; i < process.argv.length; i += 2) args[process.argv[i].slice(2)] = process.argv[i + 1];
const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const read = file => JSON.parse(fs.readFileSync(file));
assert.equal(sha(fs.readFileSync(args['go-file'])), args['go-sha256']);
assert(args['run-root'] && path.isAbsolute(args['run-root']), 'An explicit external synthetic-fixture run root is required');
const go = read(args['go-file']), R = path.resolve(args['run-root']), QA = path.join(R, 'qa'), origin = 'http://127.0.0.1:18879';
assert.equal(go.allowed, true); assert.equal(go.browser_allowed, true); assert.equal(go.production, false); assert.equal(go.origin, origin);
assert.equal(go.harness_sha256, sha(fs.readFileSync(__filename)));
const output = path.resolve(args.output || ''); assert.equal(path.dirname(output), path.join(R, 'web-ui')); assert(/^run\d+$/.test(path.basename(output))); assert(!fs.existsSync(output));
const oracleFile = path.join(QA, 'timeline-oracle.json'); assert.equal(sha(fs.readFileSync(oracleFile)), go.oracle_sha256); const oracle = read(oracleFile);
assert.equal(oracle.origin, origin); assert.equal(oracle.production, false); assert(oracle.other_owner && oracle.other_service && oracle.service && oracle.owner);
assert.equal(oracle.expected_row_count, oracle.expected.length); assert.equal(oracle.raw_event_count, oracle.events.length);
assert.equal(oracle.expected.find(row => row.ids.includes(String(oracle.events.find(event => event.message.startsWith('Dokument: ')).id))).title, 'Přidán dokument');
const passwordFile = path.resolve(oracle.password_file); assert.equal(path.dirname(passwordFile), path.join(QA, 'server')); assert.equal(fs.statSync(passwordFile).mode & 0o077, 0);
const password = fs.readFileSync(0, 'utf8').trim(); assert(password && password === fs.readFileSync(passwordFile, 'utf8').trim());
const pinsFile = path.join(QA, 'api-source-pins.json'); assert.equal(sha(fs.readFileSync(pinsFile)), go.source_pins_sha256); const pins = read(pinsFile);
const source = () => Object.fromEntries(Object.keys(pins.sha256).map(name => [name, sha(fs.readFileSync(path.join(pins.root, name)))])); assert.deepEqual(source(), pins.sha256);
const helper = go.snapshot_helper, baselineFile = go.business_baseline; assert.equal(sha(fs.readFileSync(helper)), go.snapshot_helper_sha256); assert.equal(sha(fs.readFileSync(baselineFile)), go.business_baseline_sha256); const baseline = read(baselineFile);
assert.equal(path.dirname(path.resolve(helper)), QA); assert.equal(path.dirname(path.resolve(baselineFile)), QA);
const traceFile = go.trace_path; assert.equal(path.dirname(path.resolve(traceFile)), QA);
const trace = () => fs.existsSync(traceFile) ? fs.readFileSync(traceFile, 'utf8').split('\n').filter(Boolean).map(line => JSON.parse(line)) : [];
const startSeq = trace().at(-1)?.seq || 0;
fs.mkdirSync(output); const proof = {status: 'RUNNING', started_at: new Date().toISOString(), origin, go_sha256: args['go-sha256'], source_before: source(), checks: [], requests: [], blocked: [], artifacts: [], errors: [], observations: [], ambient_posts_blocked_unverified: 0, unknown_business_write_attempts: 0, accepted_business_writes: 0, headless: false, token_injected: false, test_called_internal_API: false, clock_changed: false, positive_response_mock: false, production: false};
const report = path.join(output, 'real-journey.json'), save = () => fs.writeFileSync(report, JSON.stringify(proof, null, 2) + '\n');
let browser, page, role = 'none', epoch = 0; const requestScopes = new WeakMap(), pending = new Set();
const settle = () => Promise.all([...pending]), pause = ms => new Promise(resolve => setTimeout(resolve, ms));
async function until(check, message) { const end = Date.now() + 45000; while (Date.now() < end) { if (await check()) return; await pause(100); } throw Error(message || 'Actual UI observation timed out'); }
function pass(name, data = {}) { proof.checks.push({name, ...data, status: 'PASS'}); save(); }
function snapshot(label) { const file = path.join(output, 'business-' + label + '.json'), result = spawnSync(go.python_binary, [helper, '--output', file], {encoding: 'utf8', timeout: 30000}); assert.equal(result.status, 0, 'readonly business snapshot failed'); return {file, sha256: sha(fs.readFileSync(file)), data: read(file)}; }
async function screenshot(label) { const file = path.join(output, label + '.png'); await page.screenshot({path: file, fullPage: true}); proof.artifacts.push({path: file, sha256: sha(fs.readFileSync(file))}); save(); }
const currentRequests = () => proof.requests.filter(row => row.role === role && row.epoch === epoch);
async function principal(actor) { await until(() => currentRequests().some(row => row.identity?.id === actor.id && row.identity.email === actor.email && row.identity.role === (role.includes('service') ? 'service' : 'user')), 'fresh actual principal missing'); }
async function login(actor, name) {
    role = name; await page.goto(origin + '/web/customer.html', {waitUntil: 'domcontentloaded'});
    await page.locator(name.includes('service') ? '#loginModeServiceBtn' : '#loginModeUserBtn').click();
    await page.locator('#loginEmail').fill(actor.email); await page.locator('#loginPassword').fill(password);
    const [response] = await Promise.all([page.waitForResponse(value => new URL(value.url()).pathname === '/user/login' && value.request().method() === 'POST'), page.locator('#loginSubmitBtn').click()]);
    assert.equal(response.status(), 200);
    await page.locator('#dashboard').waitFor({state: 'visible', timeout: 45000}); await principal(actor);
    pass(name + ' normal password login and actual identity', {actor_id: actor.id, epoch});
}
async function logout() {
    for (const selector of ['#customerFeatureDialog', '#vehicleDetailModal']) {
        const modal = page.locator(selector); if (await modal.isVisible()) {
            const close = selector === '#customerFeatureDialog' ? modal.getByRole('button', {name: 'Zavřít', exact: true}) : page.locator('[data-testid="btn-close-vehicle-modal"]');
            await close.click();
        }
    }
    const logoutButton = page.locator('[data-testid="btn-logout"]');
    if (!await logoutButton.isVisible()) await page.locator('#mobileMenuToggle').click();
    await logoutButton.waitFor({state: 'visible'});
    const [result] = await Promise.all([page.waitForResponse(value => { const pathname = new URL(value.url()).pathname; return pathname === '/admin-web-session' && value.request().method() === 'DELETE' && value.status() === 200 || pathname === '/user/logout' && value.request().method() === 'POST' && value.status() === 204; }), logoutButton.click()]);
    await page.locator('#loginSubmitBtn').waitFor({state: 'visible'}); assert.equal(await page.locator('[data-job-timeline]').count(), 0);
    assert.equal((await page.locator('body').textContent()).includes(oracle.job_title), false);
    pass(role + ' normal logout clears private job UI with actual server confirmation', {path: new URL(result.url()).pathname, status: result.status()});
}
async function jobsList() {
    if (role === 'creator-service') {
        const container = page.locator('#serviceWorkspaceContainer');
        const card = container.locator('article.customer-feature-card').filter({hasText: oracle.vehicle_plate}).filter({has: page.getByRole('button', {name: 'Příjem a zakázky krok za krokem', exact: true})});
        await until(async () => await card.count() === 1 && await card.isVisible(), 'real approved vehicle card missing');
        await card.getByRole('button', {name: 'Příjem a zakázky krok za krokem', exact: true}).click();
    } else {
        await page.locator('[data-testid="tab-vehicles"]').click(); const card = page.locator('[data-testid="vehicle-card"][data-vehicle-id="' + oracle.vehicle_id + '"]');
        await card.waitFor({state: 'visible'}); await card.click();
        await page.locator('#vehicleModalBody').getByRole('button', {name: 'Průběh servisu a aktualizace', exact: true}).click();
    }
    const card = page.locator('#customerFeatureDialog article.customer-feature-card').filter({has: page.getByRole('heading', {name: oracle.job_title, exact: true})});
    await card.waitFor({state: 'visible'}); return card;
}
async function openEvidence() { const card = await jobsList(); await card.getByRole('button', {name: 'Fotografie, faktury a průběh', exact: true}).click(); await page.locator('#customerFeatureDialog [data-job-timeline]').waitFor({state: 'visible'}); }
const rawByID = new Map(oracle.events.map(event => [String(event.id), event]));
const expectedISO = raw => new Date(/[zZ]|[+-]\d\d:\d\d$/.test(raw) ? raw : raw + 'Z').toISOString();
async function verifyTimeline(label, withAllOriginals = false) {
    const component = page.locator('#customerFeatureDialog [data-job-timeline]'), rows = component.locator('.job-timeline-list > li');
    await component.waitFor({state: 'visible', timeout: 45000});
    await until(async () => await rows.count() === oracle.expected_row_count, label + ' exact completed timeline row count missing');
    assert.equal(await rows.count(), oracle.expected_row_count);
    const titles = await rows.locator(':scope > .job-timeline-header > strong').allTextContents(); assert.deepEqual(titles, oracle.expected.map(value => value.title));
    const observed = [];
    for (let index = 0; index < oracle.expected.length; index++) {
        const expected = oracle.expected[index], row = rows.nth(index), originals = expected.ids.map(id => rawByID.get(id));
        assert.equal(await row.getAttribute('data-timeline-kind'), expected.kind); assert.equal(await row.getAttribute('data-timeline-count'), String(expected.ids.length));
        assert.equal(await row.locator(':scope > .job-timeline-header > time').getAttribute('datetime'), expectedISO(originals.at(-1).created_at));
        if (expected.kind === 'photo') {
            const button = row.locator(':scope > button'), entries = row.locator(':scope > .job-timeline-originals');
            assert.equal(await button.getAttribute('aria-expanded'), 'false'); assert.equal(await entries.isVisible(), false);
            assert.equal(await entries.locator(':scope > li').count(), expected.ids.length);
            if (withAllOriginals) {
                await button.click(); assert.equal(await entries.isVisible(), true); assert.equal(await button.getAttribute('aria-expanded'), 'true');
                assert.deepEqual(await entries.locator(':scope > li > p').allTextContents(), originals.map(value => value.message));
                assert.deepEqual(await entries.locator(':scope > li > time').evaluateAll(nodes => nodes.map(node => node.getAttribute('datetime'))), originals.map(value => expectedISO(value.created_at)));
                await button.click(); assert.equal(await entries.isVisible(), false);
            }
        } else assert.equal(await row.locator(':scope > .job-timeline-message').textContent(), originals[0].message);
        observed.push({title: titles[index], kind: expected.kind, ids: expected.ids, latest: originals.at(-1).created_at});
    }
    assert.equal(titles.filter(value => value === 'Servis dokončen').length, 1);
    const dimension = await component.evaluate(node => ({clientWidth: node.clientWidth, scrollWidth: node.scrollWidth})); assert(dimension.scrollWidth <= dimension.clientWidth + 1, 'timeline must fit narrow viewport without horizontal clipping');
    proof.observations.push({label, role, epoch, rows: observed, all_originals_expanded_and_verified: withAllOriginals, dimension});
    await settle(); assert(currentRequests().some(row => row.job?.id === oracle.job_id && JSON.stringify(row.job.events) === JSON.stringify(oracle.events)), 'actual job response must exactly preserve raw audit data');
    pass(label + ' actual compact timeline, groups, latest times and lifecycle', {visible_rows: titles.length, raw_events: oracle.raw_event_count, all_originals: withAllOriginals});
}
async function sixPhotoDisclosure(label) {
    const row = page.locator('#customerFeatureDialog [data-job-timeline] .job-timeline-row').filter({has: page.getByText('Přidány fotografie · 6', {exact: true})});
    assert.equal(await row.count(), 1); const button = row.locator(':scope > button'), originals = row.locator('.job-timeline-originals');
    await row.scrollIntoViewIfNeeded(); await screenshot(label + '-collapsed'); await button.click(); assert.equal(await originals.isVisible(), true);
    const expected = oracle.six_photo_event_ids.map(id => rawByID.get(id).message); assert.deepEqual(await originals.locator(':scope > li > p').allTextContents(), expected);
    await button.scrollIntoViewIfNeeded(); await screenshot(label + '-expanded'); await button.click(); assert.equal(await originals.isVisible(), false);
    pass(label + ' visible six-photo disclosure and all six original entries', {count: expected.length});
}
async function deniedUI(actor, name) {
    await login(actor, name);
    if (name === 'foreign-service') {
        const workspace = page.locator('#serviceWorkspaceContainer'); await workspace.getByText('Zatím nemáte schválená vozidla.', {exact: false}).waitFor({state: 'visible'});
        await until(() => currentRequests().some(row => row.workspace?.count === 0), 'fresh empty denied service workspace missing');
    } else {
        await page.locator('[data-testid="tab-vehicles"]').click();
        await until(() => currentRequests().some(row => Array.isArray(row.vehicle_ids)), 'fresh owner vehicle list missing');
        const response = currentRequests().findLast(row => Array.isArray(row.vehicle_ids)); assert(!response.vehicle_ids.includes(oracle.vehicle_id));
        assert.equal(await page.locator('[data-testid="vehicle-card"][data-vehicle-id="' + oracle.vehicle_id + '"]').count(), 0);
    }
    assert.equal(await page.locator('[data-job-timeline]').count(), 0); const text = await page.locator('body').textContent();
    for (const value of [oracle.job_title, ...oracle.events.map(event => event.message)]) assert(!text.includes(value), 'unauthorized UI contains private job event');
    assert(!currentRequests().some(row => row.job?.id === oracle.job_id));
    await screenshot(name + '-private-job-absent'); pass(name + ' ordinary completed workspace has no foreign vehicle/job/event data'); await logout();
}
(async () => {
    proof.business_before = snapshot('before'); assert.deepEqual(proof.business_before.data, baseline);
    const {chromium} = require(go.playwright_module); browser = await chromium.launch({headless: false, executablePath: go.chrome_binary});
    const context = await browser.newContext({viewport: {width: 1280, height: 1000}, serviceWorkers: 'block', userAgent: 'TooZHubTimelineWebQA/20261103 Chrome'});
    await context.route('**/*', async route => {
        const request = route.request(), url = new URL(request.url()), method = request.method(); if (!['http:', 'https:'].includes(url.protocol)) return route.continue();
        let reason = '';
        if (url.origin !== origin) reason = 'external_network_blocked';
        else if (!['GET', 'HEAD', 'OPTIONS'].includes(method) && !(method === 'POST' && ['/user/login', '/user/login/2fa', '/user/logout', '/user/session/renew', '/user/activity'].includes(url.pathname)) && !(method === 'DELETE' && url.pathname === '/admin-web-session')) {
            if (method === 'POST' && ['/api/v1/reminders/check-and-send-notifications', '/api/v1/license/apple/session'].includes(url.pathname)) { proof.ambient_posts_blocked_unverified++; reason = 'ambient_blocked_unverified'; }
            else { proof.unknown_business_write_attempts++; reason = 'business_write_FAIL'; }
        }
        if (reason) { proof.blocked.push({role, epoch, method, path: url.pathname, reason}); save(); return route.abort(); } return route.continue();
    });
    page = await context.newPage(); page.on('framenavigated', frame => { if (frame === page.mainFrame()) epoch++; });
    page.on('request', request => requestScopes.set(request, {role, epoch})); page.on('pageerror', error => { proof.errors.push({role, epoch, error: error.name, message: String(error.message).split(password).join('[redacted]')}); save(); });
    page.on('response', response => {
        const url = new URL(response.url()); if (url.origin !== origin) return;
        const row = {...(requestScopes.get(response.request()) || {role, epoch}), path: url.pathname, method: response.request().method(), status: response.status()}; proof.requests.push(row);
        const task = (async () => {
            if (response.ok() && row.path === '/user/me') { const data = await response.json(); row.identity = {id: data.id, email: data.email, role: data.role}; }
            if (response.ok() && row.path === '/api/v1/services/workspace/approved-vehicles') { const data = await response.json(); assert(Array.isArray(data.items)); row.workspace = {count: data.items.length, vehicle_ids: data.items.map(value => value.id)}; }
            if (response.ok() && row.path === '/api/v1/vehicles') { const data = await response.json(); assert(Array.isArray(data)); row.vehicle_ids = data.map(value => value.id); }
            if (response.ok() && row.path === '/api/v1/service-jobs/' + oracle.job_id) { const data = await response.json(); row.job = {id: data.id, events: data.events}; }
            const asset = row.path.slice(1); if (response.ok() && ['web/job-timeline.js', 'web/service-features.js', 'web/customer-features.js', 'web/customer-session.js', 'web/legacy-app.js'].includes(asset)) assert.equal(sha(await response.body()), pins.sha256[asset], 'actual loaded source mismatch ' + asset);
            save();
        })().catch(error => { proof.errors.push({role: row.role, epoch: row.epoch, path: row.path, error: 'response_observation_failed', message: error.message}); save(); }).finally(() => pending.delete(task)); pending.add(task);
    });
    await login(oracle.service, 'creator-service'); await openEvidence(); await verifyTimeline('creator desktop evidence', true); await sixPhotoDisclosure('01-creator-desktop');
    // Existing photo/document UI remains reachable; the timeline is presentation only.
    assert(await page.locator('#customerFeatureDialog').getByRole('button', {name: oracle.documents[0].file_name, exact: true}).isVisible());
    const more = page.locator('#customerFeatureDialog').getByRole('button', {name: /^Zobrazit další fotografie/}); if (await more.isVisible()) await more.click();
    const images = page.locator('#customerFeatureDialog .job-photo-grid img'); await until(async () => await images.count() === oracle.photo_count && await images.evaluateAll(nodes => nodes.every(node => node.complete && node.naturalWidth > 0)), 'actual gallery thumbnails failed');
    pass('existing readonly gallery still decodes all fixture photos and document action remains', {images: await images.count()});
    await page.locator('#customerFeatureDialog').getByRole('button', {name: 'Zavřít', exact: true}).click();
    const card = await jobsList(); await card.getByRole('button', {name: 'Pokračovat krok za krokem', exact: true}).click(); await verifyTimeline('creator guided', true);
    await page.locator('#customerFeatureDialog').getByRole('button', {name: 'Zavřít', exact: true}).click();
    await page.setViewportSize({width: 390, height: 844}); await openEvidence(); await verifyTimeline('creator narrow 390px', true); await sixPhotoDisclosure('02-creator-390');
    await page.reload({waitUntil: 'domcontentloaded'}); await page.locator('#dashboard').waitFor({state: 'visible', timeout: 45000}); await principal(oracle.service); await openEvidence(); await verifyTimeline('creator real reload and reopen', true); await screenshot('03-creator-reopened'); await logout();
    await login(oracle.owner, 'owner'); await openEvidence(); await verifyTimeline('approved owner narrow', true); await sixPhotoDisclosure('04-owner-390'); await logout();
    await page.setViewportSize({width: 1280, height: 1000}); await deniedUI(oracle.other_service, 'foreign-service'); await deniedUI(oracle.other_owner, 'foreign-owner');
    await settle(); assert.deepEqual(proof.errors, []); assert.equal(proof.unknown_business_write_attempts, 0);
    proof.accepted_business_writes = proof.requests.filter(row => row.path.startsWith('/api/v1/') && !['GET', 'HEAD', 'OPTIONS'].includes(row.method)).length; assert.equal(proof.accepted_business_writes, 0);
    proof.status = 'PASS';
})().catch(async error => { proof.status = 'FAILED'; proof.error = String(error.message).split(password).join('[redacted]'); process.exitCode = 1; if (page) try { await screenshot('failure'); } catch {} }).finally(async () => {
    await settle(); if (browser) await browser.close(); proof.owned_browser_closed = true;
    proof.source_after = source(); if (JSON.stringify(proof.source_after) !== JSON.stringify(proof.source_before)) { proof.status = 'FAILED_SOURCE_CHANGED'; process.exitCode = 1; }
    proof.business_after = snapshot('after'); proof.business_unchanged = JSON.stringify(proof.business_after.data) === JSON.stringify(proof.business_before?.data); if (!proof.business_unchanged) { proof.status = 'FAILED_BUSINESS_CHANGED'; process.exitCode = 1; }
    const scoped = trace().filter(row => row.seq > startSeq), unsafe = scoped.filter(row => row.event === 'request_safety_aborted' && String(row.classification).endsWith('_FAIL'));
    if (unsafe.length) { proof.status = 'FAILED_SERVER_WRITE_ATTEMPT'; process.exitCode = 1; }
    proof.server_safety = {unknown_or_archive_write_attempts: unsafe.length, ambient_blocked_unverified: scoped.filter(row => row.event === 'request_safety_aborted' && String(row.classification).startsWith('ambient_')).length};
    proof.trace_interval = {start_exclusive: startSeq, end_inclusive: scoped.at(-1)?.seq}; proof.finished_at = new Date().toISOString(); save(); console.log(JSON.stringify({status: proof.status, checks: proof.checks.length, business_unchanged: proof.business_unchanged, report}));
});
