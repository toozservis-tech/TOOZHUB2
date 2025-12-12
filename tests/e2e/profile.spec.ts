import { test, expect } from '@playwright/test';
import { loginUser } from './helpers';

test.describe('Profile', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/web/index.html');
    
    // Přihlásit se
    await loginUser(page);
    await expect(page.locator('[data-testid="dashboard"]')).toBeVisible({ timeout: 10000 });
  });

  test('should display profile tab', async ({ page }) => {
    await page.click('[data-testid="tab-profile"]');
    await expect(page.locator('[data-testid="profile-tab"]')).toBeVisible();
    await expect(page.locator('[data-testid="profile-container"]')).toBeVisible();
  });

  test('should load profile data', async ({ page }) => {
    await page.click('[data-testid="tab-profile"]');
    // Počkat na načtení
    await page.waitForTimeout(2000);
    await expect(page.locator('[data-testid="profile-container"]')).toBeVisible();
  });
});

