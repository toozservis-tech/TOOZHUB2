/**
 * Jak na to — návodové centrum na servisní SPA (reálné přihlášení + přepnutí do servisu).
 */
import { expect, test, type Page } from '@playwright/test';

import { clickServiceWorkspaceSwitchWhenVisible } from './helpers';

async function openRealServiceShellOrSkip(page: Page) {
  /** Session ze `tutorial-auth.setup.ts` (login jednou před suite). */
  await page.goto('/web/app/u');
  await page.locator('[data-testid="dashboard"]').waitFor({ state: 'visible', timeout: 35_000 });
  try {
    await clickServiceWorkspaceSwitchWhenVisible(page);
  } catch {
    test.skip(
      true,
      'Účet z E2E_TUTORIAL_USER_* nemá v /api/me dual workspace (user+service) — chybí viditelný přepínač Servis.',
    );
  }
}

test.describe('Servis — tutorial hub z Nápovědy (produkční login)', () => {
  test('help-center odkazuje do hubu a lze rozjet svc-overview-map', async ({ page }) => {
    await openRealServiceShellOrSkip(page);

    await expect(page.locator('[data-service-shell="root"]')).toBeVisible({ timeout: 40_000 });

    await page.locator('.service-nav-slot[data-nav-group="napoveda"] button.service-nav-item').click();

    await expect(page.getByRole('heading', { name: 'Centrum návodů ToozHub Servis', exact: true })).toBeVisible({
      timeout: 15_000,
    });

    await page.getByTestId('service-open-tutorial-hub-btn').click();

    await expect(page.locator('#howToHubModal')).toBeVisible();
    const launch = page.locator('[data-how-launch="svc-overview-map"]');
    await expect(launch).toBeVisible();
    await expect(launch).toBeEnabled();

    await launch.click();

    await expect(page.locator('#app-tutorial-overlay-root')).toBeAttached({ timeout: 18_000 });

    await expect(page.locator('[data-testid="tutorial-bubble"]')).toContainText(/servis|Servisní/i);

    await page.keyboard.press('Escape');

    await expect(page.locator('#app-tutorial-overlay-root')).toHaveCount(0);
  });

  test('servisní hub neobsahuje uživatelský launcher add-vehicle', async ({ page }) => {
    await openRealServiceShellOrSkip(page);

    await page.locator('.service-nav-slot[data-nav-group="napoveda"] button.service-nav-item').click();
    await page.getByTestId('service-open-tutorial-hub-btn').click();
    await expect(page.locator('#howToHubModal')).toBeVisible();

    await expect(page.locator('[data-how-launch="add-vehicle"]')).toHaveCount(0);

    await expect(page.locator('[data-how-launch="svc-overview-map"]')).toHaveCount(1);
  });
});
