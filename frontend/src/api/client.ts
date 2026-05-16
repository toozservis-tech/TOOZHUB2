/**
 * Tenký bridge na window.apiCall z monolitického index.html.
 * Neduplikuje auth: token, cookies a logout logika zůstávají v legacy apiCall.
 */

export const API_CALL_MISSING_MESSAGE =
  'Modul seznamu vozidel: funkce window.apiCall není dostupná. ' +
  'Otevřete stránku v kontextu hlavní webové aplikace Správa vozidel, kde je načtený legacy skrypt.';

export function getApiCall(): NonNullable<Window['apiCall']> {
  if (typeof window === 'undefined') {
    throw new Error(API_CALL_MISSING_MESSAGE);
  }
  const fn = window.apiCall;
  if (typeof fn !== 'function') {
    throw new Error(API_CALL_MISSING_MESSAGE);
  }
  return fn;
}

export async function apiGet<T>(endpoint: string): Promise<T> {
  const result = await getApiCall()(endpoint, 'GET');
  return result as T;
}

export function getApiBaseUrl(): string {
  if (typeof window === 'undefined') {
    return '';
  }
  return window.location.origin;
}

export function getAuthorizedImageHeaders(): HeadersInit {
  const headers: Record<string, string> = {
    Accept: 'image/*',
  };

  if (window.accessToken) {
    headers.Authorization = `Bearer ${window.accessToken}`;
  } else if (window.currentUser?.email) {
    headers['X-User-Email'] = window.currentUser.email;
  }

  return headers;
}
