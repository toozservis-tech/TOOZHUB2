/**
 * E2E: React modul Seznam vozidel (Fáze 3–4) – flag, assety, reload, legacy detail, servis.
 *
 * ENV (volitelné):
 * - E2E_SERVICE_EMAIL, E2E_SERVICE_PASSWORD – describe „servis“ se přeskočí, pokud chybí.
 * - Dohody s `auth.setup` / helpers: E2E_EMAIL, E2E_PASSWORD (uživatelský běh).
 * Názvy build assetů: `readReactVehicleListAssetNames()` z `app/web/index.html` (Fáze 5 / postbuild).
 */

import { expect, test, type Page, type Request, type TestInfo } from '@playwright/test';
import {
  attachReactVehicleListFailureDiagnostics,
  getServiceTestCredentials,
  loginServiceUser,
  readReactVehicleListAssetNames,
} from './helpers';
import type { ReactVehicleListAssetNames } from './helpers';

const REACT_LIST_ASSET_RE = /\/web\/react\/vehicle-list\/assets\/[^/]+\.(?:js|mjs|css)(?:$|[?#])/i;

function createReactListAssetMonitor(page: Page) {
  const urls: string[] = [];
  const handler = (req: Request) => {
    const u = req.url();
    if (REACT_LIST_ASSET_RE.test(u)) {
      urls.push(u);
    }
  };
  page.on('request', handler);
  return {
    snapshot: () => [...urls],
    clear: () => {
      urls.length = 0;
    },
    dispose: () => {
      page.off('request', handler);
    },
  };
}

function createRelevantRequestRing(page: Page, maxLen = 40) {
  const urls: string[] = [];
  const pat = (u: string) =>
    u.includes('react/vehicle-list') || u.includes('/api/v1/vehicles') || u.includes('/api/me') || u.includes('/login');
  const handler = (req: Request) => {
    const u = req.url();
    if (pat(u)) {
      urls.push(u);
      while (urls.length > maxLen) {
        urls.shift();
      }
    }
  };
  page.on('request', handler);
  return {
    last: (n: number) => urls.slice(-n),
    dispose: () => {
      page.off('request', handler);
    },
  };
}

function collectPageErrorsForDiagnostics(page: Page) {
  const consoleErrors: string[] = [];
  const handler = (msg: { type: () => string; text: () => string }) => {
    if (msg.type() === 'error') {
      consoleErrors.push(msg.text());
    }
  };
  const pageerr = (err: Error) => {
    consoleErrors.push(`[pageerror] ${err.message}`);
  };
  page.on('console', handler);
  page.on('pageerror', pageerr);
  return {
    snapshot: () => [...consoleErrors],
    dispose: () => {
      page.off('console', handler);
      page.off('pageerror', pageerr);
    },
  };
}

async function withDiagnosticsOnFailure(
  testInfo: TestInfo,
  page: Page,
  relevantRing: { last: (n: number) => string[]; dispose: () => void },
  fn: () => Promise<void>,
): Promise<void> {
  const consoleBuffer = collectPageErrorsForDiagnostics(page);
  try {
    await fn();
  } catch (e) {
    await attachReactVehicleListFailureDiagnostics(page, testInfo, {
      lastRelevantRequestUrls: relevantRing.last(10),
      consoleErrorSamples: consoleBuffer.snapshot().slice(-10),
    });
    throw e;
  } finally {
    consoleBuffer.dispose();
  }
}

async function getMeForRouting(
  page: Page,
): Promise<{ account_slug: string; workspace_route_kind: string } | null> {
  return page.evaluate(async () => {
    const w = window as unknown as { apiCall?: (e: string, m?: string) => Promise<unknown> };
    if (typeof w.apiCall !== 'function') {
      return null;
    }
    const me = (await w.apiCall('/api/me', 'GET')) as {
      authenticated?: boolean;
      account_slug?: string;
      workspace_route_kind?: string;
    };
    if (!me || me.authenticated !== true) {
      return null;
    }
    return {
      account_slug: String(me.account_slug || ''),
      workspace_route_kind: String(me.workspace_route_kind || 'user'),
    };
  });
}

async function gotoUserVehiclesList(page: Page, baseURL: string | undefined) {
  test.skip(!baseURL, 'baseURL is required');
  await page.goto('/web/index.html', { waitUntil: 'load' });
  await expect(page.locator('[data-testid="dashboard"]')).toBeVisible({ timeout: 20_000 });

  const me = await getMeForRouting(page);
  expect(me, '/api/me musí být autentizovaný').toBeTruthy();
  if (!me) {
    return null;
  }
  if (me.workspace_route_kind === 'service') {
    test.skip();
    return null;
  }
  const appVehiclesPath = `/app/u/${encodeURIComponent(me.account_slug)}/vehicles`;
  await page.goto(appVehiclesPath, { waitUntil: 'domcontentloaded', timeout: 90_000 });
  expect(page.url()).toMatch(/\/app\/u\/[^/]+\/vehicles/);

  await page.locator('[data-testid="tab-vehicles"]').click();
  await expect(page.locator('[data-testid="vehicles-container"]')).toBeVisible({ timeout: 20_000 });
  return me;
}

test.describe('React vehicle list (gated) — user', () => {
  let reactAssets: ReactVehicleListAssetNames;

  test.beforeAll(() => {
    reactAssets = readReactVehicleListAssetNames();
  });

  test('default false: po tabu Vozidla a loadVehicles se nenačtou React assety', async ({ page, baseURL }, testInfo) => {
    const rel = createRelevantRequestRing(page);
    try {
      await withDiagnosticsOnFailure(testInfo, page, rel, async () => {
        const me = await gotoUserVehiclesList(page, baseURL);
        if (!me) {
          return;
        }

        const flag = await page.evaluate(
          () => (window as unknown as { __ENABLE_REACT_VEHICLE_LIST?: boolean }).__ENABLE_REACT_VEHICLE_LIST,
        );
        expect(flag, 'výchozí flag v šabloně musí být false').toBe(false);

        const monitor = createReactListAssetMonitor(page);
        try {
          await page.evaluate(async () => {
            const w = window as unknown as { loadVehicles?: (f?: boolean) => Promise<unknown> };
            if (typeof w.loadVehicles === 'function') {
              await w.loadVehicles(true);
            }
          });
          await expect
            .poll(
              () => {
                return page
                  .locator('[data-testid="vehicles-container"]')
                  .locator('.loading, .cards-grid, p, [data-testid="vehicle-card"]')
                  .count();
              },
              { message: 'legacy obsah vozidel nebo stav načítání', timeout: 25_000 },
            )
            .toBeGreaterThan(0);
          const assetUrls = monitor.snapshot();
          expect(assetUrls, 'při false se nesmí requestovat /web/react/vehicle-list/assets/*').toEqual([]);
        } finally {
          monitor.dispose();
        }
      });
    } finally {
      rel.dispose();
    }
  });

  test('true + loadVehicles: #react-vehicles-root, očekávané assety, GET /api/v1/vehicles (ne dřív než listener)', async ({
    page,
    baseURL,
  }, testInfo) => {
    const rel = createRelevantRequestRing(page);
    const monitor = createReactListAssetMonitor(page);
    try {
      await withDiagnosticsOnFailure(testInfo, page, rel, async () => {
        const me = await gotoUserVehiclesList(page, baseURL);
        if (!me) {
          return;
        }

        const defaultFlag = await page.evaluate(
          () => (window as unknown as { __ENABLE_REACT_VEHICLE_LIST?: boolean }).__ENABLE_REACT_VEHICLE_LIST,
        );
        expect(defaultFlag).toBe(false);

        /** Request na API musí být chycen: listener dřív než asynchronní spuštění Reactu po načtení modulu. */
        const apiWait = page.waitForResponse(
          (res) => {
            try {
              const u = new URL(res.url());
              return u.pathname === '/api/v1/vehicles' && res.request().method() === 'GET' && res.status() < 500;
            } catch {
              return false;
            }
          },
          { timeout: 45_000 },
        );

        await page.evaluate(async () => {
          const w = window as unknown as { __ENABLE_REACT_VEHICLE_LIST?: boolean; loadVehicles?: (f?: boolean) => void };
          w.__ENABLE_REACT_VEHICLE_LIST = true;
          if (typeof w.loadVehicles === 'function') {
            await w.loadVehicles(true);
          }
        });

        const [, apiRes] = await Promise.all([
          expect(page.locator('#react-vehicles-root')).toBeVisible({ timeout: 30_000 }),
          apiWait,
        ]);

        const after = monitor.snapshot();
        expect(
          after.some((u) => u.includes(reactAssets.buildJs)),
          `očekáván request na .js: ${reactAssets.buildJs} (z index.html)`,
        ).toBe(true);
        expect(
          after.some((u) => u.includes(reactAssets.buildCss)),
          `očekáván request na .css: ${reactAssets.buildCss} (z index.html)`,
        ).toBe(true);

        expect(apiRes.ok(), `GET /api/v1/vehicles očekáván 2xx, dost ${apiRes.status()}`).toBe(true);

        const hasApiCall = await page.evaluate(() => typeof (window as unknown as { apiCall?: unknown }).apiCall === 'function');
        expect(hasApiCall, 'React list používá window.apiCall z legacy shell').toBe(true);
      });
    } finally {
      monitor.dispose();
      rel.dispose();
    }
  });

  test('Fáze 4: tlačítko Detail → legacy vehicleDetailModal (prázdný stav = bez kliku)', async ({
    page,
    baseURL,
  }, testInfo) => {
    const rel = createRelevantRequestRing(page);
    try {
      await withDiagnosticsOnFailure(testInfo, page, rel, async () => {
        const me = await gotoUserVehiclesList(page, baseURL);
        if (!me) {
          return;
        }

        await page.evaluate(async () => {
          const w = window as unknown as { __ENABLE_REACT_VEHICLE_LIST?: boolean; loadVehicles?: (f?: boolean) => void };
          w.__ENABLE_REACT_VEHICLE_LIST = true;
          if (typeof w.loadVehicles === 'function') {
            await w.loadVehicles(true);
          }
        });
        await expect(page.locator('#react-vehicles-root')).toBeVisible({ timeout: 30_000 });

        const hasItems = (await page.locator('[data-testid="react-vehicle-list-item"]').count()) > 0;
        if (!hasItems) {
          await expect(page.locator('[data-testid="react-vehicle-list-empty"]')).toBeVisible({ timeout: 15_000 });
          await expect(page.locator('[data-testid="react-vehicle-list-detail-btn"]')).toHaveCount(0);
          return;
        }

        const detail = page.locator('[data-testid="react-vehicle-list-detail-btn"]').first();
        await expect(detail, 'karta s vozidlem má Detail').toBeVisible({ timeout: 15_000 });
        await detail.click();
        await expect(page.locator('[data-testid="vehicle-detail-modal"]')).toBeVisible({ timeout: 20_000 });
      });
    } finally {
      rel.dispose();
    }
  });

  test('reload: flag se vrátí na false, legacy kontejner, bez opětovného načtení React assetů', async ({ page, baseURL }, testInfo) => {
    const rel = createRelevantRequestRing(page);
    const monitor = createReactListAssetMonitor(page);
    try {
      await withDiagnosticsOnFailure(testInfo, page, rel, async () => {
        const me = await gotoUserVehiclesList(page, baseURL);
        if (!me) {
          return;
        }

        await page.evaluate(async () => {
          const w = window as unknown as { __ENABLE_REACT_VEHICLE_LIST?: boolean; loadVehicles?: (f?: boolean) => void };
          w.__ENABLE_REACT_VEHICLE_LIST = true;
          if (typeof w.loadVehicles === 'function') {
            await w.loadVehicles(true);
          }
        });
        await expect(page.locator('#react-vehicles-root')).toBeVisible({ timeout: 30_000 });

        monitor.clear();
        await page.reload({ waitUntil: 'load' });

        const afterReload = await page.evaluate(
          () => (window as unknown as { __ENABLE_REACT_VEHICLE_LIST?: boolean }).__ENABLE_REACT_VEHICLE_LIST,
        );
        expect(afterReload, 'po reloadu musí být flag znovu false').toBe(false);

        await expect(page.locator('[data-testid="dashboard"]')).toBeVisible({ timeout: 20_000 });
        await expect(page.locator('#vehiclesContainer')).toBeAttached();

        const postReloadAssetHits = monitor.snapshot();
        expect(
          postReloadAssetHits,
          'po cold reloadu s default false se nesmí hned stahovat vehicle-list assety (flag false)',
        ).toEqual([]);

        await page.locator('[data-testid="tab-vehicles"]').click();
        await expect(page.locator('[data-testid="vehicles-container"]')).toBeVisible({ timeout: 15_000 });
        const stillNoReact = monitor.snapshot();
        expect(stillNoReact, 'i po tabu Vozidla bez true flagu — žádné React assety').toEqual([]);
      });
    } finally {
      monitor.dispose();
      rel.dispose();
    }
  });

  test('po reloadu: legacy obsah v vehicles-container (bez vynuceného flagu)', async ({ page, baseURL }, testInfo) => {
    const rel = createRelevantRequestRing(page);
    try {
      await withDiagnosticsOnFailure(testInfo, page, rel, async () => {
        test.skip(!baseURL, 'baseURL is required');
        await page.goto('/web/index.html', { waitUntil: 'load' });
        await expect(page.locator('[data-testid="dashboard"]')).toBeVisible({ timeout: 20_000 });
        const me = await getMeForRouting(page);
        if (!me || me.workspace_route_kind === 'service') {
          test.skip();
          return;
        }
        await page.goto(`/app/u/${encodeURIComponent(me.account_slug)}/vehicles`, { waitUntil: 'load' });
        await expect(page.locator('[data-testid="vehicles-container"]')).toBeVisible({ timeout: 15_000 });
        if ((await page.locator('#react-vehicles-root').count()) > 0) {
          await page.evaluate(() => {
            (window as unknown as { __ENABLE_REACT_VEHICLE_LIST?: boolean }).__ENABLE_REACT_VEHICLE_LIST = false;
          });
          await page.reload({ waitUntil: 'load' });
        }
        await expect(page.locator('[data-testid="dashboard"]')).toBeVisible({ timeout: 20_000 });
        await page.locator('[data-testid="tab-vehicles"]').click();
        const flag = await page.evaluate(
          () => (window as unknown as { __ENABLE_REACT_VEHICLE_LIST?: boolean }).__ENABLE_REACT_VEHICLE_LIST,
        );
        expect(flag).toBe(false);
        const container = page.locator('[data-testid="vehicles-container"]');
        await expect(container).toBeVisible();
        const legacy = container.locator(
          '[data-testid="vehicle-card"], .cards-grid, .loading, p',
        );
        await expect(legacy.first()).toBeVisible({ timeout: 20_000 });
      });
    } finally {
      rel.dispose();
    }
  });
});

test.describe('React vehicle list — servis (nesmí aktivovat vehicle-list assety)', () => {
  test.beforeEach(({}, testInfo) => {
    testInfo.skip(
      !getServiceTestCredentials(),
      'Missing E2E_SERVICE_EMAIL or E2E_SERVICE_PASSWORD',
    );
  });

  test('flag true + loadVehicles: žádné assety, žádný #react-vehicles-root, service shell viditelné', async ({
    browser,
    baseURL,
  }, testInfo) => {
    const creds = getServiceTestCredentials()!;
    test.skip(!baseURL, 'baseURL is required');

    const context = await browser.newContext({
      baseURL,
      extraHTTPHeaders: { 'x-forwarded-proto': 'https' },
      ignoreHTTPSErrors: true,
      storageState: { cookies: [], origins: [] },
    });
    const page = await context.newPage();
    const rel = createRelevantRequestRing(page);
    const monitor = createReactListAssetMonitor(page);
    try {
      await withDiagnosticsOnFailure(testInfo, page, rel, async () => {
        await loginServiceUser(page, creds.email, creds.password);
        await expect(page.locator('[data-service-shell="root"]')).toBeVisible({ timeout: 30_000 });
        const defaultFlag = await page.evaluate(
          () => (window as unknown as { __ENABLE_REACT_VEHICLE_LIST?: boolean }).__ENABLE_REACT_VEHICLE_LIST,
        );
        expect(defaultFlag).toBe(false);

        await page.evaluate(async () => {
          const w = window as unknown as { __ENABLE_REACT_VEHICLE_LIST?: boolean; loadVehicles?: (f?: boolean) => void };
          w.__ENABLE_REACT_VEHICLE_LIST = true;
          if (typeof w.loadVehicles === 'function') {
            await w.loadVehicles(true);
          }
        });
        await page.waitForTimeout(1_000);

        expect(
          monitor.snapshot(),
          'servisní režim nesmí stáhnout assety /web/react/vehicle-list/',
        ).toEqual([]);
        await expect(page.locator('#react-vehicles-root')).toHaveCount(0);
        await expect(page.locator('[data-service-shell="root"]')).toBeVisible();
      });
    } finally {
      monitor.dispose();
      rel.dispose();
      await context.close();
    }
  });
});
