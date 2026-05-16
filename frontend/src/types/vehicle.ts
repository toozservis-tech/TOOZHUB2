/**
 * Ořezaný tvar odpovědi GET /api/v1/vehicles (VehicleOutV1) pro zobrazení v seznamu.
 * API vrací JSON; datumy přicházejí jako ISO řetězce.
 */
export interface VehicleListItem {
  id: number;
  nickname: string | null;
  brand: string | null;
  model: string | null;
  year: number | null;
  plate: string | null;
  vin: string | null;
  stk_valid_until: string | null;
  current_mileage_km: number | null;
  notes?: string | null;
  body_type?: string | null;
  engine?: string | null;
  photo_path?: string | null;
  catalog_image_id?: string | null;
  catalog_image_url?: string | null;
  created_at?: string | null;
  primary_photo?: {
    available?: boolean;
    broken?: boolean;
  } | null;
}

export function isVehicleListItem(x: unknown): x is VehicleListItem {
  if (x === null || typeof x !== 'object') return false;
  const o = x as Record<string, unknown>;
  return typeof o.id === 'number';
}
