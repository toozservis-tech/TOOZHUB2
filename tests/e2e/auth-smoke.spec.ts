import { test, expect } from '@playwright/test';
import { getTestCredentials, loginUser } from './helpers';

test.describe('Auth Smoke', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/web/index.html');
  });

  test('[SEC-CRIT-001] file browser routes are blocked when unauthenticated', async ({ page }) => {
    const protectedRoutes = [
      '/files/',
      '/files/api/list',
      '/files/view?path=README.md',
      '/files/download?path=README.md',
    ];

    for (const route of protectedRoutes) {
      const response = await page.request.get(route);
      expect([401, 403, 404], `Unexpected status for ${route}`).toContain(response.status());
    }
  });

  test('login with valid user', async ({ page }) => {
    await loginUser(page);
    await expect(page.locator('[data-testid="dashboard"]')).toBeVisible({ timeout: 15_000 });
    await expect(page.locator('[data-testid="tab-vehicles"]')).toBeVisible();
  });

  test('invalid login shows proper error', async ({ page }) => {
    const credentials = getTestCredentials();
    await page.fill('[data-testid="input-email"]', credentials.email);
    await page.fill('[data-testid="input-password"]', 'incorrect-password');
    await page.click('[data-testid="btn-login"]');
    await expect(page.locator('[data-testid="alert-error"]')).toBeVisible({ timeout: 10_000 });
  });

  test('logout path works', async ({ page }) => {
    await loginUser(page);
    await expect(page.locator('[data-testid="dashboard"]')).toBeVisible({ timeout: 15_000 });
    const logoutBtn = page.locator('[data-testid="btn-logout"]');
    if (!(await logoutBtn.isVisible().catch(() => false))) {
      const mobileMenuToggle = page.locator('#mobileMenuToggle');
      if (await mobileMenuToggle.isVisible().catch(() => false)) {
        await mobileMenuToggle.click();
      }
    }
    await expect(logoutBtn).toBeVisible({ timeout: 15_000 });
    await logoutBtn.click();
    await expect(page.locator('[data-testid="login-form"]')).toBeVisible({ timeout: 10_000 });
  });
});
