import { execFileSync } from 'node:child_process';
import path from 'node:path';

/**
 * Označí zákazníky s danými e-maily jako uvolněné v DB (stejně jako recycle_integration_emails.py),
 * aby šel stejný e-mail znovu zaregistrovat přes POST /user/register.
 * Bez venv/skriptu tichě nedělá nic (test může spadnout jen na kolizi unikátu emailu).
 */
export function recycleCiEmailsQuiet(emails: string[]): void {
  const norm = [...new Set(emails.map((e) => String(e || '').trim().toLowerCase()).filter(Boolean))];
  if (!norm.length) return;
  const appRoot = path.resolve(__dirname, '..', '..');
  const py = path.join(appRoot, '..', '.venv', 'bin', 'python');
  const script = path.join(appRoot, 'scripts', 'recycle_integration_emails.py');
  try {
    execFileSync(py, [script, ...norm], { cwd: appRoot, stdio: 'ignore' });
  } catch {
    /* ignore — např. chybějící venv na lokálu */
  }
}
