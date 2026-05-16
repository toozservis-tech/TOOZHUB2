/**
 * Interactive „Jak na to“ tutorials — hub, engine surface, API progress, add-vehicle flow.
 */
import { test, expect } from '@playwright/test';
import type { Page } from '@playwright/test';
import { getBaseUrl } from './helpers';

async function openProfileMenu(page: Page): Promise<void> {
  const desk = page.locator('[data-testid="app-profile-button-desktop"]');
  const mobile = page.locator('#mobileProfileButton');
  if (await desk.isVisible().catch(() => false)) {
    await desk.click();
  } else {
    await mobile.click();
  }
}

async function openHowToHub(page: Page): Promise<void> {
  await page.waitForFunction(
    () =>
      typeof (window as unknown as { TutorialEngine?: unknown }).TutorialEngine !== 'undefined' &&
      typeof (window as unknown as { openStaticOverlayModal?: unknown }).openStaticOverlayModal === 'function' &&
      typeof (window as unknown as { openHowToHubModal?: unknown }).openHowToHubModal === 'function',
    undefined,
    { timeout: 30_000 },
  );
  await openProfileMenu(page);
  await page.locator('[data-testid="menu-how-to-tutorial"]').waitFor({ state: 'visible' });
  await page.locator('[data-testid="menu-how-to-tutorial"]').click();

  await page.waitForFunction(
    () => {
      const modal = document.getElementById('howToHubModal');
      if (!(modal instanceof HTMLElement)) return false;
      if (modal.getAttribute('aria-hidden') === 'true') return false;
      const cs = window.getComputedStyle(modal);
      return cs.display !== 'none' && cs.visibility !== 'hidden';
    },
    undefined,
    { timeout: 20_000 },
  );
}

test.describe('Jak na to — tutorials', () => {
  /** beforeEach (goto + nástřik shellu) + tělo testu někdy přesáhne výchozích 60 s. */
  test.describe.configure({ timeout: 90_000 });

  test.beforeEach(async ({ page }) => {
    await page.goto('/web/app/u');
    await expect(page.locator('[data-testid="dashboard"]')).toBeVisible({ timeout: 30_000 });
    await page.waitForFunction(
      () =>
        typeof (window as unknown as { TutorialEngine?: unknown }).TutorialEngine !== 'undefined' &&
        typeof (window as unknown as { openHowToHubModal?: unknown }).openHowToHubModal === 'function',
      undefined,
      { timeout: 25_000 },
    );
  });

  test('profile menu exposes Jak na to entry', async ({ page }) => {
    await openProfileMenu(page);
    await expect(page.locator('[data-testid="menu-how-to-tutorial"]')).toBeVisible();
  });

  test('how-to hub modal opens with vehicle category', async ({ page }) => {
    await openHowToHub(page);
    await expect(page.locator('#howToHubModal')).toBeVisible();
    await expect(page.locator('[data-testid="how-to-hub-scroll"]')).toBeVisible();
    await expect(page.locator('[data-testid="how-to-hub-categories"]')).toContainText('Vozidla');
  });

  test('hub lists enabled tutorial launchers for user onboarding', async ({ page }) => {
    await openHowToHub(page);
    const addVehicleLaunch = page.locator('[data-how-launch="add-vehicle"]');
    await expect(addVehicleLaunch).toBeVisible();
    await expect(addVehicleLaunch).toBeEnabled();

    const overviewLaunch = page.locator('[data-how-launch="user-overview-map"]');
    await expect(overviewLaunch).toBeVisible();
    await expect(overviewLaunch).toBeEnabled();
  });

  test('hub disables placeholder tutorial rows', async ({ page }) => {
    await openHowToHub(page);
    const disabled = await page.locator('#howToHubCategories button:disabled').count();
    expect(disabled).toBeGreaterThanOrEqual(16);
    await expect(page.locator('#howToHubCategories button:not(:disabled)')).toHaveCount(2);
  });

  test('TutorialEngine exposes failure code constants', async ({ page }) => {
    const codes = await page.evaluate(() => {
      const te = (window as unknown as { TutorialEngine?: { FAILURE_CODES?: Record<string, string> } })
        .TutorialEngine;
      return te?.FAILURE_CODES ?? null;
    });
    expect(codes).toBeTruthy();
    expect(codes!.SEL).toBe('TUTORIAL_SELECTOR_MISSING');
    expect(codes!.VAL).toBe('VALIDATION_BLOCKED');
    expect(codes!.DESYNC).toBe('STATE_DESYNC');
  });

  test('TutorialEngine AUTO_NEXT_ON_INPUT is disabled', async ({ page }) => {
    const v = await page.evaluate(() => {
      const te = (window as unknown as { TutorialEngine?: { AUTO_NEXT_ON_INPUT?: boolean } }).TutorialEngine;
      return te?.AUTO_NEXT_ON_INPUT;
    });
    expect(v).toBe(false);
  });

  test('categorizeFailure maps STATE_DESYNC to tutorial_flow_ui', async ({ page }) => {
    const bucket = await page.evaluate(() => {
      const te = (window as unknown as { TutorialEngine?: { categorizeFailure?: (c: string) => string } })
        .TutorialEngine;
      return te?.categorizeFailure?.('STATE_DESYNC') ?? '';
    });
    expect(bucket).toBe('tutorial_flow_ui');
  });

  test('categorizeFailure maps selector errors to tutorial_config_selector', async ({ page }) => {
    const bucket = await page.evaluate(() => {
      const te = (window as unknown as { TutorialEngine?: { categorizeFailure?: (c: string) => string } })
        .TutorialEngine;
      return te?.categorizeFailure?.('TUTORIAL_SELECTOR_MISSING') ?? '';
    });
    expect(bucket).toBe('tutorial_config_selector');
  });

  test('__e2e reportSelectorMissing records failure on body', async ({ page }) => {
    const code = await page.evaluate(() => {
      document.body.removeAttribute('data-tutorial-last-failure');
      const te = (window as unknown as { TutorialEngine?: { __e2e?: { reportSelectorMissing: () => void } } })
        .TutorialEngine;
      te?.__e2e?.reportSelectorMissing();
      return document.body.getAttribute('data-tutorial-last-failure');
    });
    expect(code).toBe('TUTORIAL_SELECTOR_MISSING');
  });

  test('__e2e reportDisabled records UI_TARGET_DISABLED', async ({ page }) => {
    const code = await page.evaluate(() => {
      document.body.removeAttribute('data-tutorial-last-failure');
      const te = (window as unknown as { TutorialEngine?: { __e2e?: { reportDisabled: () => void } } })
        .TutorialEngine;
      te?.__e2e?.reportDisabled();
      return document.body.getAttribute('data-tutorial-last-failure');
    });
    expect(code).toBe('UI_TARGET_DISABLED');
  });

  test('__e2e reportRoute records ROUTE_MISMATCH', async ({ page }) => {
    const code = await page.evaluate(() => {
      document.body.removeAttribute('data-tutorial-last-failure');
      const te = (window as unknown as { TutorialEngine?: { __e2e?: { reportRoute: () => void } } })
        .TutorialEngine;
      te?.__e2e?.reportRoute();
      return document.body.getAttribute('data-tutorial-last-failure');
    });
    expect(code).toBe('ROUTE_MISMATCH');
  });

  test('GET tutorial progress succeeds when authenticated', async ({ page }) => {
    /** Stejné lokální chování jako `playwright.config` pro žádanky z aplikace. */
    const token = await page.evaluate(() => localStorage.getItem('accessToken'));
    expect(token && token.length > 20).toBeTruthy();
    const res = await page.request.get(`${getBaseUrl()}/api/v1/tutorials/progress`, {
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: 'application/json',
        'x-forwarded-proto': 'https',
      },
    });
    expect(res.ok()).toBeTruthy();
    const data = (await res.json()) as { items?: unknown };
    expect(Array.isArray(data.items)).toBe(true);
  });

  test('launching add-vehicle from hub mounts tutorial overlay', async ({ page }) => {
    await openHowToHub(page);
    await page.locator('[data-how-launch="add-vehicle"]').click();
    await expect(page.locator('#app-tutorial-overlay-root')).toBeAttached();
    await expect(page.locator('[data-testid="tutorial-bubble"]')).toBeVisible();
  });

  test('first bubble step mentions vehicles tab', async ({ page }) => {
    await openHowToHub(page);
    await page.locator('[data-how-launch="add-vehicle"]').click();
    const bubble = page.locator('[data-testid="tutorial-bubble"]');
    await expect(bubble).toContainText(/Vozidl/i);
  });

  test('Další advances from route step to add-vehicle click step', async ({ page }) => {
    await openHowToHub(page);
    await page.locator('[data-how-launch="add-vehicle"]').click();
    await page.locator('[data-testid="tutorial-bubble"] button:has-text("Další")').click();
    await expect(page.locator('[data-testid="tutorial-bubble"]')).toContainText(/Přidat vozidlo/i);
  });

  test('tutorial click step completes when user opens add-vehicle form', async ({ page }) => {
    await page.locator('[data-testid="tab-vehicles"]').click();
    await openHowToHub(page);
    await page.locator('[data-how-launch="add-vehicle"]').click();
    await page.locator('[data-testid="tutorial-bubble"] button:has-text("Další")').click();
    await page.locator('[data-tutorial="add-vehicle-button"]').click();
    await expect(page.locator('[data-testid="add-vehicle-form"]')).toBeVisible();
    await expect(page.locator('[data-testid="tutorial-bubble"]')).toContainText(/VIN/i, { timeout: 30_000 });
  });

  test('Přeskočit tears down tutorial overlay', async ({ page }) => {
    await openHowToHub(page);
    await page.locator('[data-how-launch="add-vehicle"]').click();
    await expect(page.locator('#app-tutorial-overlay-root')).toBeAttached();
    await page.locator('[data-testid="tutorial-bubble"] button:has-text("Přeskočit")').click();
    await expect(page.locator('#app-tutorial-overlay-root')).toHaveCount(0);
  });

  test('Escape skips tutorial and removes overlay', async ({ page }) => {
    await openHowToHub(page);
    await page.locator('[data-how-launch="add-vehicle"]').click();
    await expect(page.locator('[data-testid="tutorial-bubble"]')).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.locator('#app-tutorial-overlay-root')).toHaveCount(0);
  });

  test('mobile viewport can open how-to hub', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await openHowToHub(page);
    await expect(page.locator('#howToHubModal')).toBeVisible();
    await expect(page.locator('[data-how-launch="add-vehicle"]')).toBeVisible();
  });

  test('VIN step does not advance on one character — requires 17 chars', async ({ page }) => {
    await page.locator('[data-testid="tab-vehicles"]').click();
    await openHowToHub(page);
    await page.locator('[data-how-launch="add-vehicle"]').click();
    await page.locator('[data-testid="tutorial-bubble"] button:has-text("Další")').click();
    await page.locator('[data-tutorial="add-vehicle-button"]').click();
    await expect(page.locator('[data-testid="input-vehicle-vin"]')).toBeVisible({ timeout: 25_000 });

    const bubble = page.locator('[data-testid="tutorial-bubble"]');
    await page.locator('[data-testid="input-vehicle-vin"]').clear();
    await page.locator('[data-testid="input-vehicle-vin"]').type('X', { delay: 50 });
    await page.waitForTimeout(650);
    await expect(bubble).toContainText(/VIN/i);
    await expect(bubble).not.toContainText('Název vozidla');

    await page.locator('[data-testid="input-vehicle-vin"]').fill('VF3TESTVN12345678');
    await expect(bubble).toContainText(/název vozidla|Název vozidla/i, { timeout: 35_000 });
  });

  test('add vehicle modal stays open during partial VIN typing in tutorial', async ({ page }) => {
    await page.locator('[data-testid="tab-vehicles"]').click();
    await openHowToHub(page);
    await page.locator('[data-how-launch="add-vehicle"]').click();
    await page.locator('[data-testid="tutorial-bubble"] button:has-text("Další")').click();
    await page.locator('[data-tutorial="add-vehicle-button"]').click();
    await expect(page.locator('[data-testid="input-vehicle-vin"]')).toBeVisible({ timeout: 25_000 });

    const modal = page.locator('#addVehicleModal');
    await page.locator('[data-testid="input-vehicle-vin"]').clear();
    await page.locator('[data-testid="input-vehicle-vin"]').type('ABCDE', { delay: 30 });
    await expect(modal).toHaveClass(/active/);
  });

  test('tutorial stops when current step target loses data-tutorial binding', async ({ page }) => {
    await page.locator('[data-testid="tab-vehicles"]').click();
    await openHowToHub(page);
    await page.locator('[data-how-launch="add-vehicle"]').click();
    await page.locator('[data-testid="tutorial-bubble"] button:has-text("Další")').click();
    await page.locator('[data-tutorial="add-vehicle-button"]').click();
    await expect(page.locator('[data-testid="input-vehicle-vin"]')).toBeVisible({ timeout: 25_000 });

    await page.evaluate(() => {
      document.body.removeAttribute('data-tutorial-last-failure');
      const el = document.querySelector('[data-testid="input-vehicle-vin"]') as HTMLElement | null;
      if (el) el.removeAttribute('data-tutorial');
    });
    await expect(page.locator('#app-tutorial-overlay-root')).toHaveCount(0, { timeout: 9000 });
    const code = await page.evaluate(() => document.body.getAttribute('data-tutorial-last-failure'));
    expect(code).toBe('UI_TARGET_NOT_VISIBLE');
    await expect(page.locator('#app-tutorial-overlay-root')).toHaveCount(0);
  });

  test('tutorial stops when add-vehicle modal closes during guided step', async ({ page }) => {
    await page.locator('[data-testid="tab-vehicles"]').click();
    await openHowToHub(page);
    await page.locator('[data-how-launch="add-vehicle"]').click();
    await page.locator('[data-testid="tutorial-bubble"] button:has-text("Další")').click();
    await page.locator('[data-tutorial="add-vehicle-button"]').click();
    await expect(page.locator('[data-testid="input-vehicle-vin"]')).toBeVisible({ timeout: 25_000 });

    await page.evaluate(() => document.body.removeAttribute('data-tutorial-last-failure'));
    /** Bez `skipConfirm` může být blokující dialog — E2E nečeká na potvrzení uživatelem. */
    await page.evaluate(() => {
      const w = window as unknown as { closeAddVehicleModal?: (o?: { skipConfirm?: boolean }) => void };
      if (typeof w.closeAddVehicleModal === 'function') w.closeAddVehicleModal({ skipConfirm: true });
    });
    await expect(page.locator('#app-tutorial-overlay-root')).toHaveCount(0, { timeout: 15_000 });
    const code = await page.evaluate(() => document.body.getAttribute('data-tutorial-last-failure'));
    expect(code).toBe('MODAL_NOT_OPENED');
  });

  test('tutorial remains consistent after opening another tab and returning', async ({ page, context }) => {
    await page.locator('[data-testid="tab-vehicles"]').click();
    await openHowToHub(page);
    await page.locator('[data-how-launch="add-vehicle"]').click();
    await page.locator('[data-testid="tutorial-bubble"] button:has-text("Další")').click();
    await page.locator('[data-tutorial="add-vehicle-button"]').click();
    await expect(page.locator('[data-testid="input-vehicle-vin"]')).toBeVisible({ timeout: 25_000 });

    const second = await context.newPage();
    await second.goto(`${getBaseUrl()}/web/index.html`);
    await page.bringToFront();
    await expect(page.locator('#app-tutorial-overlay-root')).toBeAttached();
    await page.locator('[data-testid="input-vehicle-vin"]').fill('VF3TESTVN12345678');
    await expect(page.locator('[data-testid="tutorial-bubble"]')).toContainText(/název vozidla|Název vozidla/i, {
      timeout: 35_000,
    });
    await second.close();
  });

  test('full add-vehicle tutorial completes after successful API save', async ({ page }) => {
    await page.route('**/api/v1/vehicles', async (route) => {
      if (route.request().method() !== 'POST') {
        await route.continue();
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: Number(`9000${Date.now().toString().slice(-8)}`),
          vin: 'VF3TESTVN12345678',
          plate: 'E2EP',
          nickname: `Tutorial Stub ${Date.now()}`,
          stk_valid_until: new Date(Date.now() + 86400000).toISOString().slice(0, 10),
        }),
      });
    });

    page.once('dialog', (d) => {
      void d.dismiss();
    });
    await page.locator('[data-testid="tab-vehicles"]').click();
    await openHowToHub(page);
    await page.locator('[data-how-launch="add-vehicle"]').click();

    await page.locator('[data-testid="tutorial-bubble"] button:has-text("Další")').click();
    await page.locator('[data-tutorial="add-vehicle-button"]').click();
    await expect(page.locator('[data-testid="input-vehicle-vin"]')).toBeVisible({ timeout: 25_000 });

    await page.locator('[data-testid="input-vehicle-vin"]').fill('VF3TESTVN12345678');
    await expect(page.locator('[data-testid="tutorial-bubble"]')).toContainText(/název vozidla|Název vozidla/i, {
      timeout: 25_000,
    });

    const stamp = Date.now();
    await page.locator('[data-testid="input-vehicle-name"]').fill(`Tutorial E2E ${stamp}`);
    await page.locator('[data-testid="tutorial-bubble"] button:has-text("Další")').click();
    await expect(page.locator('[data-testid="tutorial-bubble"]')).toContainText(/SPZ/i, { timeout: 25_000 });

    await page.locator('[data-testid="input-vehicle-plate"]').fill(`TU${String(stamp).slice(-5)}`);
    await page.locator('[data-testid="tutorial-bubble"] button:has-text("Další")').click();
    await expect(page.locator('[data-testid="tutorial-bubble"]')).toContainText(/technick|Technick/i, {
      timeout: 35_000,
    });

    await page.locator('[data-testid="tutorial-bubble"] button:has-text("Další")').click();

    const stkDate = new Date(Date.now() + 365 * 86400000).toISOString().slice(0, 10);
    await page.locator('[data-testid="input-vehicle-stk-date"]').fill(stkDate);
    await expect(page.locator('[data-testid="tutorial-bubble"]')).toContainText(/tachomet|Tachometr/i, {
      timeout: 35_000,
    });

    await page.locator('[data-testid="tutorial-bubble"] button:has-text("Další")').click();

    await expect(page.locator('[data-testid="tutorial-bubble"]')).toContainText(/Kontrola|povinn/i, {
      timeout: 25_000,
    });
    await page.locator('[data-testid="tutorial-bubble"] button:has-text("Další")').click();

    await expect(page.locator('[data-testid="tutorial-bubble"]')).toContainText(/ulož|Přidat vozidlo/i);

    await page.locator('[data-tutorial="vehicle-save-button"]').click();

    await expect(page.locator('[data-testid="tutorial-bubble"]')).toContainText(/Hotovo|založen/i, { timeout: 45_000 });
    await page.locator('[data-testid="tutorial-bubble"] button:has-text("Další")').click();
    await expect(page.locator('#app-tutorial-overlay-root')).toHaveCount(0);
  });
});
