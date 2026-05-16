import { expect, test, type Page } from '@playwright/test';

const TEST_VIN = 'VF3TESTVN12345678';

async function ensureLoggedDashboard(page: Page): Promise<void> {
  await page.goto('/web/index.html');
  await expect(page.locator('[data-testid="dashboard"]')).toBeVisible({ timeout: 20_000 });
}

test('VIN preview card shows illustrative photo and vehicle can be saved without real photo', async ({ page }) => {
  await page.route('**/api/v1/license/status', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true,
        data: {
          plan: 'premium',
          status: 'active',
          vehicles_limit: 0,
          current_vehicles_count: 0,
          vin_decode_enabled: true,
          ares_enabled: true,
          reminders_enabled: true,
          vehicle_history_enabled: true,
          documents_enabled: true,
          costs_tracking_enabled: true,
          statistics_enabled: true,
          sharing_with_service_enabled: true,
        },
      }),
    });
  });

  await ensureLoggedDashboard(page);

  let previewCallCount = 0;
  let createCallCount = 0;

  await page.route('**/api/vehicles/decode-vin', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: {
          vin: TEST_VIN,
          make: 'Peugeot',
          model: 'Boxer',
          production_year: 2019,
          body_type: 'van',
          source_priority: ['existing-vin-decoder'],
        },
        errors: [],
      }),
    });
  });

  await page.route('**/api/v1/vehicles/preview-from-vin', async (route) => {
    previewCallCount += 1;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true,
        vin: TEST_VIN,
        decoded: {
          make: 'Peugeot',
          model: 'Boxer',
          year: 2019,
          body_type: 'van',
          source: 'existing-vin-decoder',
        },
        catalog_image: {
          id: 'catalog-1',
          url: '/web/assets/vehicle-placeholder.svg',
          thumbnail_url: '/web/assets/vehicle-placeholder.svg',
          source_domain: 'mock.local',
          provider: 'mock',
          score: 82,
          representative: true,
          verified_real_vehicle: false,
          license_note: 'Ilustrační katalogová fotka – nejde o skutečnou fotku vozidla.',
        },
        alternatives: [
          {
            url: '/web/assets/vehicle-placeholder.svg',
            thumbnail_url: '/web/assets/vehicle-placeholder.svg',
            score: 71,
            source_domain: 'mock.local',
          },
        ],
        warnings: [],
      }),
    });
  });

  await page.route('**/api/v1/vehicles', async (route) => {
    const request = route.request();
    if (request.method() === 'POST') {
      createCallCount += 1;
      const payload = JSON.parse(request.postData() || '{}');
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 9991,
          user_email: 'preview@example.com',
          nickname: payload.nickname,
          brand: payload.brand,
          model: payload.model,
          year: payload.year,
          engine: payload.engine,
          vin: payload.vin,
          plate: payload.plate,
          notes: payload.notes,
          primary_photo: { available: false, broken: false, asset_id: null },
          photo_path: null,
          catalog_image_id: payload.catalog_image_id,
          catalog_image_url: payload.catalog_image_url,
          stk_valid_until: payload.stk_valid_until,
          tenant_id: 1,
          created_at: new Date().toISOString(),
        }),
      });
      return;
    }
    await route.continue();
  });

  await page.click('[data-testid="tab-vehicles"]');
  await page.click('[data-testid="btn-toggle-add-vehicle"]');
  await expect(page.locator('[data-testid="add-vehicle-form"]')).toBeVisible({ timeout: 10_000 });

  await page.fill('[data-testid="input-vehicle-vin"]', TEST_VIN);
  await page.click('#vinFetchBtn');

  const previewCard = page.locator('[data-testid="vehicle-catalog-preview"]');
  await expect(previewCard).toBeVisible({ timeout: 10_000 });
  await expect(previewCard).toContainText('Ilustrační');
  await expect(previewCard).toContainText('nejde o skutečnou fotku vozidla');
  await expect(page.locator('#vehicleCatalogPreviewImage.is-active')).toBeVisible({ timeout: 10_000 });
  await expect(page.locator('#vehicleCatalogPreviewPlaceholder')).toBeHidden({ timeout: 10_000 });

  await page.fill('[data-testid="input-vehicle-plate"]', 'SMK1234');
  await page.fill('[data-testid="input-vehicle-stk-date"]', '2027-05-01');
  await page.click('[data-testid="btn-add-vehicle"]');

  await expect(page.locator('#vehicleCatalogPreviewGroup')).toBeHidden({ timeout: 10_000 });
  expect(previewCallCount).toBeGreaterThan(0);
  expect(createCallCount).toBe(1);
});
