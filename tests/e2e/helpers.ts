/**
 * Helper funkce pro E2E testy
 */

/**
 * Získat base URL z environment proměnných nebo použít default
 */
export function getBaseUrl(): string {
  return process.env.BASE_URL || 'http://127.0.0.1:8000';
}

/**
 * Zkontrolovat, zda jsou testy v read-only režimu
 */
export function isReadOnly(): boolean {
  return process.env.E2E_READONLY === '1' || process.env.E2E_READONLY === 'true';
}

/**
 * Získat testovací credentials z environment proměnných nebo použít default
 */
export function getTestCredentials(): { email: string; password: string } {
  return {
    email: process.env.E2E_EMAIL || 'e2e.toozhub@example.com',
    password: process.env.E2E_PASSWORD || 'E2eTest123!',
  };
}

/**
 * Zajistí existenci testovacího uživatele.
 * Registrace je idempotentní: pokud uživatel existuje, pokračujeme dál.
 */
export async function ensureTestUser(page: any, email?: string, password?: string): Promise<void> {
  const credentials = getTestCredentials();
  const targetEmail = email || credentials.email;
  const targetPassword = password || credentials.password;

  const response = await page.request.post('/user/register', {
    data: {
      email: targetEmail,
      password: targetPassword,
      name: 'E2E Test User',
    },
  });

  if (response.status() === 200 || response.status() === 400) {
    return;
  }

  throw new Error(`Unable to ensure test user. HTTP ${response.status()}`);
}

/**
 * Přihlásit uživatele v testu
 */
export async function loginUser(page: any, email?: string, password?: string): Promise<void> {
  const credentials = getTestCredentials();
  const targetEmail = email || credentials.email;
  const targetPassword = password || credentials.password;

  await ensureTestUser(page, targetEmail, targetPassword);
  await page.fill('[data-testid="input-email"]', targetEmail);
  await page.fill('[data-testid="input-password"]', targetPassword);
  await page.click('[data-testid="btn-login"]');
}

/**
 * Ověřit, že nejsou zobrazeny globální chybové hlášky
 */
export async function assertNoGlobalErrorBanner(page: any): Promise<void> {
  const errorAlerts = page.locator('[data-testid="alert-error"]');
  const count = await errorAlerts.count();
  if (count > 0) {
    const messages = await errorAlerts.allTextContents();
    throw new Error(`Found ${count} error alert(s): ${messages.join(', ')}`);
  }
}

/**
 * Přejít na konkrétní tab
 */
export async function gotoTab(page: any, tabTestId: string): Promise<void> {
  await page.click(`[data-testid="${tabTestId}"]`);
  // Počkat na aktivaci tabu
  await page.waitForTimeout(500);
}
