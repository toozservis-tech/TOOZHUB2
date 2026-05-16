import { getApiBaseUrl, getApiCall, getAuthorizedImageHeaders } from '@/api/client';
import type { VehicleListItem } from '@/types/vehicle';

/** Odpověď GET /api/v1/vehicle-image — server drží API klíče a volí poskytovatele. */
export type VehicleImageMeta = {
  url: string;
  provider: string;
  photographer_name?: string | null;
  photographer_url?: string | null;
};

function buildQuery(
  make: string,
  model: string,
  year: number | null | undefined,
  nickname?: string | null,
): string {
  const p = new URLSearchParams();
  if (make.trim()) p.set('make', make.trim());
  if (model.trim()) p.set('model', model.trim());
  if (year != null && Number.isFinite(year)) p.set('year', String(Math.trunc(year)));
  if (nickname?.trim()) p.set('nickname', nickname.trim());
  return p.toString();
}

/**
 * Klient pro dynamické náhledy vozidel. Primární logika je na backendu (Unsplash / šablona / placeholder).
 * Výměna poskytovatele: pouze .env na serveru (URL šablona + klíč).
 */
export class VehicleImageService {
  static hasPrimaryPhoto(vehicle: VehicleListItem): boolean {
    if (vehicle.primary_photo && typeof vehicle.primary_photo.available === 'boolean') {
      return Boolean(vehicle.primary_photo.available);
    }
    return Boolean(vehicle.photo_path && String(vehicle.photo_path).trim());
  }

  static hasCatalogPhoto(vehicle: VehicleListItem): boolean {
    const raw = vehicle.catalog_image_url != null ? String(vehicle.catalog_image_url).trim() : '';
    return !!raw && raw !== '/web/assets/vehicle-placeholder.svg';
  }

  static async fetchPrimaryPhotoObjectUrl(
    vehicleId: number,
    signal?: AbortSignal,
  ): Promise<string> {
    const response = await fetch(`${getApiBaseUrl()}/api/v1/vehicles/${vehicleId}/photo?v=${Date.now()}`, {
      method: 'GET',
      headers: getAuthorizedImageHeaders(),
      credentials: 'include',
      mode: 'cors',
      cache: 'no-store',
      signal,
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const blob = await response.blob();
    return URL.createObjectURL(blob);
  }

  static isProtectedCatalogImageUrl(url: string): boolean {
    const raw = String(url || '').trim();
    return /(^\/api\/v1\/vehicles\/catalog-images\/[A-Za-z0-9]+\/file\b)|(^https?:\/\/[^/]+\/api\/v1\/vehicles\/catalog-images\/[A-Za-z0-9]+\/file\b)/.test(raw);
  }

  static async fetchCatalogImageObjectUrl(
    url: string,
    signal?: AbortSignal,
  ): Promise<string> {
    const raw = String(url || '').trim();
    if (!raw) {
      throw new Error('Chybí URL katalogové fotky.');
    }
    const absoluteUrl = raw.startsWith('http') ? raw : `${getApiBaseUrl()}${raw}`;
    const response = await fetch(absoluteUrl, {
      method: 'GET',
      headers: getAuthorizedImageHeaders(),
      credentials: 'include',
      mode: 'cors',
      cache: 'no-store',
      signal,
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const blob = await response.blob();
    const contentType = String(blob.type || response.headers.get('content-type') || '').toLowerCase();
    if (contentType.includes('svg')) {
      throw new Error('Katalogový endpoint vrátil placeholder místo reálné fotky.');
    }
    return URL.createObjectURL(blob);
  }

  static async resolveCatalogImageUrl(
    vehicle: VehicleListItem,
    signal?: AbortSignal,
  ): Promise<string> {
    if (vehicle.catalog_image_id && String(vehicle.catalog_image_id).trim()) {
      return `/api/v1/vehicles/catalog-images/${encodeURIComponent(String(vehicle.catalog_image_id).trim())}/file`;
    }
    if (vehicle.catalog_image_url && String(vehicle.catalog_image_url).trim()) {
      return String(vehicle.catalog_image_url).trim();
    }

    return this.resolve(vehicle.brand ?? '', vehicle.model ?? '', vehicle.year, signal, vehicle.nickname).then(
      (meta) => meta.url,
    );
  }

  static async resolve(
    make: string,
    model: string,
    year?: number | null,
    signal?: AbortSignal,
    nickname?: string | null,
  ): Promise<VehicleImageMeta> {
    const qs = buildQuery(make ?? '', model ?? '', year, nickname);
    const path = qs ? `/api/v1/vehicle-image?${qs}` : '/api/v1/vehicle-image';
    const result = await getApiCall()(path, 'GET', undefined, signal);
    return result as VehicleImageMeta;
  }
}
