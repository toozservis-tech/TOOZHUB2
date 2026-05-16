import fs from 'node:fs';
import path from 'node:path';
import { test as setup } from '@playwright/test';

import { getTutorialE2ECredentials, loginExistingUser } from './helpers';

const tutorialAuthPath = path.join(__dirname, 'playwright', '.auth', 'tutorial-user.json');

/**
 * Jedna přihlašovací session pro všechny tutorial E2E (žádné opakované /login → méně 429 „Příliš mnoho pokusů“).
 */
setup('authenticate tutorial user (existing account)', async ({ page }) => {
  setup.setTimeout(180_000);
  fs.mkdirSync(path.dirname(tutorialAuthPath), { recursive: true });

  await loginExistingUser(page, getTutorialE2ECredentials());

  await page
    .locator('[data-testid="dashboard"]')
    .waitFor({ state: 'visible', timeout: 35_000 })
    .catch(async () => {
      await page.locator('[data-service-shell="root"]').waitFor({ state: 'visible', timeout: 35_000 });
    });

  await page.context().storageState({ path: tutorialAuthPath });
});
