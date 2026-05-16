/**
 * Most do legacy monolitu: otevření detailu vozidla přes stávající showVehicleDetail (index.html).
 * Neukládá data; autorizaci a načtení full detailu řeší legacy (GET /api/v1/vehicles/:id přes window.apiCall).
 */

export type OpenLegacyDetailResult = 'opened' | 'unavailable' | 'error';

/**
 * Otevře modální detail vozidla, pokud je v legacy shellu dostupná globální showVehicleDetail(vehicleId).
 * Při chybějící funkci nebo výjimce: console.warn, žádný throw ven (React zůstane stabilní).
 */
export async function openLegacyVehicleDetail(vehicleId: number): Promise<OpenLegacyDetailResult> {
  if (!Number.isFinite(vehicleId) || vehicleId <= 0) {
    console.warn('[react-vehicles] openLegacyVehicleDetail: neplatné vehicleId', vehicleId);
    return 'unavailable';
  }
  const w = window as unknown as { showVehicleDetail?: (id: number) => Promise<unknown> };
  if (typeof w.showVehicleDetail !== 'function') {
    console.warn(
      '[react-vehicles] openLegacyVehicleDetail: window.showVehicleDetail není k dispozici (načtěte app v kontextu Správa vozidel).',
    );
    return 'unavailable';
  }
  try {
    await w.showVehicleDetail(vehicleId);
    return 'opened';
  } catch (e) {
    console.warn('[react-vehicles] openLegacyVehicleDetail: showVehicleDetail selhalo', e);
    return 'error';
  }
}
