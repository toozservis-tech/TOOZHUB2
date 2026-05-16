import { apiGet } from './client';
import { isVehicleListItem, type VehicleListItem } from '../types/vehicle';

export async function fetchVehicles(): Promise<VehicleListItem[]> {
  const raw = await apiGet<unknown>('/api/v1/vehicles');
  if (!Array.isArray(raw)) {
    throw new Error('Neočekávaná odpověď API: očekáváno pole vozidel.');
  }
  const items: VehicleListItem[] = [];
  for (const el of raw) {
    if (!isVehicleListItem(el)) {
      throw new Error('Neočekávaná odpověď API: neplatná položka vozidla.');
    }
    items.push(el);
  }
  return items;
}
