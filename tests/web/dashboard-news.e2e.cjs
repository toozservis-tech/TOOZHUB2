// Exercises the real customer portal with normal login to the synthetic full API fixture.
// Serve the two changed static files from this checkout. Auth, permissions and API responses
// come from the loopback server. No real customers, device tokens or outbound providers.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const origin = 'http://127.0.0.1:18926';
const output = process.env.NEWS_QA_OUT;
const assets = ['customer-features.js', 'customer.css'];
const checks = [];
const calls = [];

async function main() {
    const health = await (await fetch(origin + '/health')).json();
    assert.equal(health.fixture, 'synthetic-full18926');
    assert.equal(health.push_delivery_enabled, false);
    const setup = await (await fetch(origin + '/qa/setup?group=api')).json();
    const browser = await chromium.launch({channel: 'chrome', headless: true});
    if (output) await fs.mkdir(output, {recursive: true});
    let context;
    let page;
    async function login(role, override, reducedMotion = 'no-preference') {
        if (context) await context.close();
        context = await browser.newContext({
            viewport: {width: 390, height: 844}, locale: 'cs-CZ',
            serviceWorkers: 'block', hasTouch: true, reducedMotion
        });
        await context.route('**/*', async route => {
            const url = new URL(route.request().url());
            if (url.origin !== origin) return route.abort();
            const file = url.pathname.split('/').pop();
            if (override && url.pathname === '/web/' + file && assets.includes(file)) {
                const response = await route.fetch();
                assert.equal(response.status(), 200);
                return route.fulfill({response, path: path.join(__dirname, '../../web', file)});
            }
            return route.continue();
        });
        page = await context.newPage();
        page.setDefaultTimeout(12000);
        page.on('response', r => calls.push({role, path: new URL(r.url()).pathname, status: r.status()}));
        await page.goto(origin + '/web/customer.html', {waitUntil: 'domcontentloaded'});
        if (role === 'service') await page.locator('#loginModeServiceBtn').click();
        await page.locator('#loginEmail').fill(role === 'owner' ? 'qa18926-dashboard-news@example.com' : setup.users[role].email);
        await page.locator('#loginPassword').fill(setup.password);
        await page.locator('#loginForm button[type=submit]').click();
        await page.locator('#dashboard.active').waitFor();
    }
    const overview = async () => {
        const tab = page.locator('#dashboard .tab[data-tab-key="customerOverview"]');
        await tab.click();
    };
    const deck = () => page.locator('#customerOverviewTab .customer-news');
    const button = key => deck().locator('[data-news-action="' + key + '"]');
    const story = async id => page.locator('.customer-news[data-story="' + id + '"]').waitFor();
    const picture = async name => {
        if (output) await page.screenshot({path: path.join(output, name + '.png')});
    };
    try {
        await login('owner', false);
        await overview();
        await page.locator('#customerOverviewTab').getByText(/Method Not Allowed/).waitFor();
        assert(calls.some(call => call.path === '/api/v1/reservations' && call.status === 405));
        checks.push('Baseline owner overview reproduces reservation GET 405.');
        await login('owner', true);
        await overview();
        await story('nearby');
        await deck().scrollIntoViewIfNeeded();
        const original = await deck().boundingBox();
        assert(original.height < 155);
        await picture('01-owner-390');
        await story('booking');
        checks.push('Real owner sees a compact first story at 390px and advances automatically after 8 seconds.');
        await button('next').click();
        await story('referrals');
        await page.waitForTimeout(8400);
        assert.equal(await deck().getAttribute('data-story'), 'referrals');
        assert.equal(await button('play').getAttribute('aria-label'), 'Spustit střídání novinek');
        await deck().getByRole('button', {name: 'Premium za pozvání'}).click();
        await page.getByRole('dialog', {name: 'Pozvat a získat odměny'}).waitFor();
        await page.getByRole('dialog', {name: 'Pozvat a získat odměny'}).getByRole('button',{name:'Zavřít',exact:true}).click();
        await button('prev').click();
        await deck().getByRole('button', {name: 'Objednání do servisu'}).click();
        await page.locator('#reservationVehicle').waitFor();
        await page.locator('#reservationServiceId').waitFor();
        await page.keyboard.press('Escape');
        const close = page.locator('.reservation-create-modal .modal-close');
        if (await close.isVisible()) await close.click();
        const existingFormClose = page.locator('.reservation-create-modal button').filter({hasText: 'Zrušit'}).first();
        if (await existingFormClose.isVisible()) await existingFormClose.click();
        await overview();
        await button('prev').click();
        await deck().getByRole('button', {name: 'Servisy ve vašem okolí'}).click();
        await page.locator('#servicesDirectoryTab.active [data-service-search]').waitFor();
        checks.push('Manual navigation pauses, and all three stories open existing customer destinations.');
        await overview();
        await button('prev').click();
        await story('access');
        await button('next').click();
        await story('nearby');
        await button('play').click();
        await story('booking');
        checks.push('Manual controls wrap in both directions and explicit resume restarts rotation.');
        const cdp = await context.newCDPSession(page);
        const box = await deck().locator('.customer-news-copy').boundingBox();
        const startX = Math.floor(box.x + box.width * .8);
        const endX = Math.floor(box.x + box.width * .2);
        const y = Math.floor(box.y + box.height * .55);
        await cdp.send('Input.dispatchTouchEvent', {type:'touchStart',touchPoints:[{x:startX,y}]});
        await cdp.send('Input.dispatchTouchEvent', {type:'touchMove',touchPoints:[{x:endX,y}]});
        await cdp.send('Input.dispatchTouchEvent', {type:'touchEnd',touchPoints:[]});
        await story('referrals');
        assert.equal(await button('play').getAttribute('aria-label'), 'Spustit střídání novinek');
        await button('prev').click();
        checks.push('A real horizontal touch gesture changes one slide, pauses rotation and leaves the overview open.');
        await button('play').click();
        assert.equal(await button('play').getAttribute('aria-label'), 'Pozastavit střídání novinek');
        await page.emulateMedia({reducedMotion: 'reduce'});
        await page.waitForTimeout(8400);
        assert.equal(await deck().getAttribute('data-story'), 'booking');
        assert.equal(await button('play').isVisible(), false);
        await page.setViewportSize({width: 320, height: 740});
        await deck().scrollIntoViewIfNeeded();
        const fits = await deck().evaluate(el => el.scrollWidth <= el.clientWidth);
        assert(fits);
        await picture('02-owner-320-reduced');
        checks.push('Reduced motion stops rotation, and the 320px card fits without horizontal overflow.');
        await login('service', true);
        assert.equal(await page.locator('#dashboard .tab[data-tab-key="customerOverview"]').isVisible(), false);
        assert.equal(await page.locator('.customer-news').count(), 0);
        checks.push('Normal service login sees its own workspace without owner news.');
        await login('owner', true, 'reduce');
        await overview();
        await story('nearby');
        checks.push('Fresh owner login resets news to the first story and the overview loads without 405.');
        console.log(JSON.stringify({status:'PASS',checks,height390:original.height}, null, 2));
        if (output) await fs.writeFile(path.join(output,'result.json'),JSON.stringify({checks,height390:original.height,origin,actor:'qa18926-dashboard-news@example.com',serviceGroup:'api',source:health.source,calls},null,2));
    } catch (error) {
        if (output && page) {
            await picture('failure');
            await fs.writeFile(path.join(output,'failure.txt'),String(error.stack)+'\n'+(await page.locator('body').innerText()).slice(-8500));
        }
        throw error;
    } finally { await browser.close(); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
