import { expect, test } from '@playwright/test';

import { installServiceShellMocks } from './service-shell-fallback.helpers';

test.describe('Service shell work order flow', () => {
  test('covers create, duplicate reject and update refresh flow', async ({ page }) => {
    test.setTimeout(90_000);
    await installServiceShellMocks(page);
    await page.goto('/web/app/s/toozservis/dashboard');
    const forceServiceShell = async () => page.evaluate((user) => {
      localStorage.setItem('accessToken', 'test-token');
      localStorage.setItem('currentUser', JSON.stringify(user));
      (window as any).accessToken = 'test-token';
      (window as any).currentUser = user;
      (window as any).isServiceWorkspaceRole = () => true;
    }, {
      id: 9901,
      email: 'service.workspace@example.com',
      role: 'service',
      name: 'ToozServis',
    });
    await forceServiceShell();
    await page.waitForFunction(() => Boolean((window as any).serviceShell?.mount), null, { timeout: 15000 });
    await page.evaluate(() => (window as any).serviceShell.mount({ section: 'work-orders' }));
    await expect(page.locator('[data-service-shell="root"]')).toBeVisible({ timeout: 15000 });

    const closeModal = async () => {
      await page.evaluate(() => (window as any).serviceShell.closeModal());
      await expect(page.locator('.service-shell-modal')).toHaveCount(0);
    };

    await page.getByRole('button', { name: '+ Nová zakázka' }).click();
    await expect(page.locator('.service-shell-modal-title')).toContainText('Nová zakázka');
    await closeModal();

    await page.getByRole('button', { name: /Výchozí zakázka/ }).first().click();
    await expect(page.locator('.service-shell-modal-title')).toContainText('Detail zakázky');
    await expect(page.locator('.service-shell-modal')).toContainText('Linked Customer');
    await closeModal();

    await page.getByRole('button', { name: '+ Nová zakázka' }).click();
    await page.fill('#serviceShellWorkOrderTitle', 'E2E Zakazka');
    await page.fill('#serviceShellWorkOrderDueDate', '2026-04-13');
    await page.fill('#serviceShellWorkOrderDescription', 'Zakázka vytvořená testem');
    await page.evaluate(() => (window as any).serviceShell.submitCreateWorkOrderModal());
    await expect(page.locator('.service-shell-modal')).toHaveCount(0);
    await forceServiceShell();
    await page.evaluate(() => (window as any).serviceShell.mount({ section: 'work-orders' }));
    await expect(page.locator('[data-service-shell="root"]')).toContainText('E2E Zakazka');

    await page.getByRole('button', { name: /E2E Zakazka/ }).first().click();
    await expect(page.locator('.service-shell-modal-title')).toContainText('Detail zakázky');
    await expect(page.locator('.service-shell-modal')).toContainText('Linked Customer');
    await expect(page.locator('.service-shell-modal')).toContainText('Položky zakázky');
    await expect(page.locator('.service-shell-modal')).toContainText('Zatím nejsou přidané žádné položky zakázky');

    await page.getByRole('button', { name: 'Přidat práci' }).click();
    await expect(page.locator('.service-shell-modal-title')).toContainText('Přidat práci');
    await page.fill('#serviceShellWorkOrderItemName', 'Kontrola brzd');
    await page.fill('#serviceShellWorkOrderItemCode', 'BRZDY');
    await page.fill('#serviceShellWorkOrderItemQuantity', '2');
    await page.fill('#serviceShellWorkOrderItemUnit', 'h');
    await page.fill('#serviceShellWorkOrderItemVat', '21');
    await page.fill('#serviceShellWorkOrderItemSale', '500');
    await page.evaluate(() => (window as any).serviceShell.submitWorkOrderItemModal());
    await expect(page.locator('.service-shell-modal-title')).toContainText('Detail zakázky');
    await expect(page.locator('.service-shell-modal')).toContainText('Kontrola brzd');
    await expect(page.locator('.service-shell-modal')).toContainText('1 210 Kč');

    page.once('dialog', async (dialog) => {
      await dialog.accept();
    });
    await page.locator('.service-shell-work-order-items-card').getByRole('button', { name: 'Odebrat' }).click();
    await expect(page.locator('.service-shell-modal')).toContainText('Zatím nejsou přidané žádné položky zakázky');

    await page.getByRole('button', { name: 'Přidat materiál' }).click();
    await page.fill('#serviceShellWorkOrderItemName', 'FORBIDDEN');
    await page.fill('#serviceShellWorkOrderItemSale', '100');
    await page.evaluate(() => (window as any).serviceShell.submitWorkOrderItemModal());
    await expect(page.locator('.service-shell-modal')).toContainText('Servis nemá oprávnění k této zakázce/vozidlu.');
    await page.getByRole('button', { name: 'Zpět na zakázku' }).click();
    await expect(page.locator('.service-shell-modal-title')).toContainText('Detail zakázky');

    await page.getByRole('button', { name: 'Import CSV dílů' }).click();
    await expect(page.locator('.service-shell-modal-title')).toContainText('Import CSV dílů');
    await page.setInputFiles('#serviceShellCsvFile', {
      name: 'parts.csv',
      mimeType: 'text/csv',
      buffer: Buffer.from('name;code;quantity;unit;vat_rate;sale_price_without_vat\nKabínový filtr;KF1;2;ks;21;250\n', 'utf-8'),
    });
    await expect(page.locator('.service-shell-modal')).toContainText('Kabínový filtr');
    await page.selectOption('#serviceShellCsvMap_name', 'name');
    await page.selectOption('#serviceShellCsvMap_quantity', 'quantity');
    await page.selectOption('#serviceShellCsvMap_sale_price_without_vat', 'sale_price_without_vat');
    const importResponse = page.waitForResponse((response) => (
      response.url().includes('/api/v1/services/workspace/work-orders/777/csv/import')
      && response.request().method() === 'POST'
    ));
    await page.getByRole('button', { name: 'Potvrdit import' }).click();
    await importResponse;
    await expect(page.locator('.service-shell-modal-title')).toContainText('Detail zakázky');
    await expect(page.locator('.service-shell-modal')).toContainText('Kabínový filtr');
    await expect(page.locator('.service-shell-modal')).toContainText('605 Kč');

    await page.selectOption('#serviceShellDetailStatus', 'approved');
    await page.fill('#serviceShellDetailDescription', 'Aktualizovaná zakázka');
    await page.evaluate(() => (window as any).serviceShell.submitWorkOrderDetailUpdate(777));
    await expect(page.locator('.service-shell-modal')).toHaveCount(0);
    await forceServiceShell();
    await page.evaluate(() => (window as any).serviceShell.mount({ section: 'work-orders' }));

    await expect(page.getByRole('button', { name: /E2E Zakazka/ }).first()).toContainText('Schváleno');
    await page.getByRole('button', { name: 'Přehled' }).click();
    await expect(page.getByRole('button', { name: /Aktivní zakázky\s+2/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /Nestíháme\s+0/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /Nové zakázky\s+2/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /Čeká na schválení\s+0/ })).toBeVisible();

    await page.getByRole('button', { name: '+ Nová zakázka' }).click();
    await page.fill('#serviceShellWorkOrderTitle', 'Duplicitní pokus');
    await page.fill('#serviceShellWorkOrderDueDate', '2026-04-14');
    await page.fill('#serviceShellWorkOrderDescription', 'Nemá projít');
    await page.evaluate(() => (window as any).serviceShell.submitCreateWorkOrderModal());
    await expect(page.locator('.service-shell-modal')).toContainText('Na stejné vozidlo už existuje rozpracovaná zakázka');
    await expect(page.getByRole('button', { name: 'Otevřít existující zakázku' })).toBeVisible();
    await closeModal();

    await page.evaluate(() => (window as any).serviceShell.navigate('reservations'));
    await expect(page.locator('[data-service-shell="root"]')).toContainText('Příjmy vozidel');
    await expect(page.locator('.service-shell-intake-card').filter({ hasText: 'Klepe přední náprava' })).toContainText('Vytvořit zakázku');
    await expect(page.locator('.service-shell-intake-card').filter({ hasText: 'Už má navázanou zakázku' })).toContainText('Otevřít zakázku');

    const intakeResponse = page.waitForResponse((response) => (
      response.url().includes('/api/v1/services/workspace/vehicle-intakes/321/create-work-order')
      && response.request().method() === 'POST'
    ));
    const createFromIntakeButton = page.locator('.service-shell-intake-card').filter({ hasText: 'Klepe přední náprava' }).getByRole('button', { name: 'Vytvořit zakázku' });
    await createFromIntakeButton.click();
    await createFromIntakeButton.click({ timeout: 500 }).catch(() => undefined);
    await intakeResponse;
    const stats = await page.evaluate(() => (window as any).__serviceShellMockStats());
    expect(stats.createFromIntakeCalls['321']).toBe(1);
    await expect(page.locator('.service-shell-modal-title')).toContainText('Detail zakázky');
    await expect(page.locator('.service-shell-modal')).toContainText('Zakázka vytvořená z příjmu');
    await closeModal();

    await page.evaluate(() => (window as any).serviceShell.navigate('reservations'));
    await page.locator('.service-shell-intake-card').filter({ hasText: 'Už má navázanou zakázku' }).getByRole('button', { name: 'Otevřít zakázku' }).click();
    await expect(page.locator('.service-shell-modal-title')).toContainText('Detail zakázky');
    await expect(page.locator('.service-shell-modal')).toContainText('Zakázka #501');
    await closeModal();

    await page.evaluate(() => (window as any).serviceShell.navigate('reservations'));
    await page.locator('.service-shell-intake-card').filter({ hasText: 'Příjem bez oprávnění' }).getByRole('button', { name: 'Vytvořit zakázku' }).click();
    await expect(page.locator('.service-shell-toast--error')).toContainText('Servis nemá oprávnění vytvořit zakázku z tohoto příjmu.');
  });
});
