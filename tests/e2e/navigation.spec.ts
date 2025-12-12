import { test, expect } from '@playwright/test';
import { loginUser } from './helpers';

test.describe('Navigation', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/web/index.html');
    
    // Přihlásit se
    await loginUser(page);
    await expect(page.locator('[data-testid="dashboard"]')).toBeVisible({ timeout: 10000 });
  });

  test('should navigate to vehicles tab', async ({ page }) => {
    await page.click('[data-testid="tab-vehicles"]');
    await expect(page.locator('[data-testid="vehicles-tab"]')).toBeVisible();
    await expect(page.locator('[data-testid="tab-vehicles"]')).toHaveClass(/active/);
  });

  test('should navigate to add vehicle tab', async ({ page }) => {
    await page.click('[data-testid="tab-add-vehicle"]');
    await expect(page.locator('[data-testid="add-vehicle-tab"]')).toBeVisible();
    await expect(page.locator('[data-testid="tab-add-vehicle"]')).toHaveClass(/active/);
  });

  test('should navigate to reminders tab', async ({ page }) => {
    await page.click('[data-testid="tab-reminders"]');
    await expect(page.locator('[data-testid="reminders-tab"]')).toBeVisible();
    await expect(page.locator('[data-testid="tab-reminders"]')).toHaveClass(/active/);
  });

  test('should navigate to reservations tab', async ({ page }) => {
    await page.click('[data-testid="tab-reservations"]');
    await expect(page.locator('[data-testid="reservations-tab"]')).toBeVisible();
    await expect(page.locator('[data-testid="tab-reservations"]')).toHaveClass(/active/);
  });

  test('should navigate to profile tab', async ({ page }) => {
    await page.click('[data-testid="tab-profile"]');
    await expect(page.locator('[data-testid="profile-tab"]')).toBeVisible();
    await expect(page.locator('[data-testid="tab-profile"]')).toHaveClass(/active/);
  });
});

