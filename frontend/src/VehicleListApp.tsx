import { useCallback, useEffect, useState } from 'react';

import { fetchVehicles } from './api/vehicles';
import { openLegacyVehicleDetail } from './legacy/vehicleDetailBridge';
import { VehicleImage } from './components/VehicleImage';
import type { VehicleListItem } from './types/vehicle';
import styles from './styles/vehicleList.module.css';

function formatDateCz(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = String(iso).slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(d)) return String(iso);
  try {
    return new Date(d + 'T12:00:00').toLocaleDateString('cs-CZ');
  } catch {
    return d;
  }
}

function vehicleTitle(v: VehicleListItem): string {
  const parts = [v.brand, v.model].filter(Boolean);
  if (parts.length) return parts.join(' ');
  if (v.nickname?.trim()) return v.nickname.trim();
  return `Vozidlo #${v.id}`;
}

export type VehicleListAppProps = {
  /** Volitelné; výchozí chování volá openLegacyVehicleDetail. */
  onVehicleDetailRequest?: (vehicleId: number) => void;
};

type VehicleSection = 'all' | 'attention' | 'garage';
type VehicleViewMode = 'grid' | 'list' | 'compact';
type InstallState = 'idle' | 'installed';

const VEHICLE_VIEW_STORAGE_KEY = 'sprava_vozidel_vehicle_view_mode';
const LEGACY_VEHICLE_VIEW_STORAGE_KEY = 'toozhub_vehicle_view_mode';

function daysUntil(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const day = String(iso).slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) return null;

  const target = new Date(`${day}T12:00:00Z`);
  const now = new Date();
  const today = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(), 12, 0, 0));
  return Math.round((target.getTime() - today.getTime()) / 86400000);
}

function formatMileage(km: number | null | undefined): string {
  if (km == null) return 'Neuvedeno';
  return `${new Intl.NumberFormat('cs-CZ').format(km)} km`;
}

function vehicleStatus(v: VehicleListItem): { label: string; tone: 'critical' | 'warning' | 'good' | 'neutral' } {
  const days = daysUntil(v.stk_valid_until);
  if (days == null) return { label: 'Chybí STK', tone: 'neutral' };
  if (days < 0) return { label: `STK propadla ${Math.abs(days)} d`, tone: 'critical' };
  if (days <= 30) return { label: `STK do ${days} d`, tone: 'critical' };
  if (days <= 90) return { label: `STK do ${days} d`, tone: 'warning' };
  return { label: 'STK v pořádku', tone: 'good' };
}

function vehicleAttentionScore(v: VehicleListItem): number {
  const days = daysUntil(v.stk_valid_until);
  if (days == null) return 0;
  if (days < 0) return 1;
  if (days <= 30) return 2;
  if (days <= 90) return 3;
  if (v.current_mileage_km == null) return 4;
  return 5;
}

function getDefaultVehicleViewMode(): VehicleViewMode {
  if (typeof window !== 'undefined' && window.matchMedia?.('(max-width: 768px)').matches) {
    return 'list';
  }
  return 'grid';
}

function readVehicleViewMode(): VehicleViewMode {
  if (typeof window === 'undefined') return getDefaultVehicleViewMode();
  const stored =
    window.localStorage.getItem(VEHICLE_VIEW_STORAGE_KEY) ??
    window.localStorage.getItem(LEGACY_VEHICLE_VIEW_STORAGE_KEY) ??
    getDefaultVehicleViewMode();

  return stored === 'grid' || stored === 'list' || stored === 'compact'
    ? stored
    : getDefaultVehicleViewMode();
}

function persistVehicleViewMode(mode: VehicleViewMode): void {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(VEHICLE_VIEW_STORAGE_KEY, mode);
  window.localStorage.removeItem(LEGACY_VEHICLE_VIEW_STORAGE_KEY);
}

function formatShortNote(vehicle: VehicleListItem): string {
  const note = vehicle.notes?.trim();
  if (!note) {
    return [vehicle.brand, vehicle.model].filter(Boolean).join(' ') || 'Bez doplňujících údajů';
  }
  const firstLine = note.split(/\r?\n/)[0]?.trim() ?? '';
  return firstLine.length > 72 ? `${firstLine.slice(0, 72)}…` : firstLine;
}

export function VehicleListApp({ onVehicleDetailRequest }: VehicleListAppProps) {
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [errorText, setErrorText] = useState<string>('');
  const [vehicles, setVehicles] = useState<VehicleListItem[]>([]);
  const [query, setQuery] = useState('');
  const [section, setSection] = useState<VehicleSection>('all');
  const [viewMode, setViewMode] = useState<VehicleViewMode>(() => readVehicleViewMode());
  const [isOnline, setIsOnline] = useState(
    typeof navigator === 'undefined' ? true : navigator.onLine
  );
  const [installPrompt, setInstallPrompt] = useState<BeforeInstallPromptEvent | null>(null);
  const [installState, setInstallState] = useState<InstallState>('idle');

  const load = useCallback(async () => {
    setStatus('loading');
    setErrorText('');
    try {
      const data = await fetchVehicles();
      setVehicles(data);
      setStatus('ready');
    } catch (e) {
      const msg =
        e instanceof Error
          ? e.message
          : 'Nepodařilo se načíst vozidla.';
      setErrorText(msg);
      setStatus('error');
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const handleOnline = () => setIsOnline(true);
    const handleOffline = () => setIsOnline(false);
    const handleInstallable = (event: Event) => {
      event.preventDefault();
      setInstallPrompt(event as BeforeInstallPromptEvent);
    };
    const handleInstalled = () => {
      setInstallState('installed');
      setInstallPrompt(null);
    };

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);
    window.addEventListener('beforeinstallprompt', handleInstallable);
    window.addEventListener('appinstalled', handleInstalled);

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
      window.removeEventListener('beforeinstallprompt', handleInstallable);
      window.removeEventListener('appinstalled', handleInstalled);
    };
  }, []);

  useEffect(() => {
    persistVehicleViewMode(viewMode);
  }, [viewMode]);

  if (status === 'loading' && !errorText) {
    return (
      <div className={styles['vl-root']}>
        <div className={styles['vl-shell']}>
          <p className={styles['vl-loading']} role="status">
            Načítám vozidla…
          </p>
        </div>
      </div>
    );
  }

  if (status === 'error') {
    const hint =
      errorText === 'Failed to fetch' || /load failed/i.test(errorText)
        ? ' (v dev: zkontrolujte, že běží backend a Vite proxy / stejný origin.)'
        : '';
    return (
      <div className={styles['vl-root']}>
        <div className={styles['vl-shell']}>
          <p className={styles['vl-error']} role="alert">
            {errorText}
            {hint}
          </p>
          <button type="button" className={styles['vl-secondaryButton']} onClick={() => void load()}>
            Zkusit znovu
          </button>
        </div>
      </div>
    );
  }

  const handleDetail = (id: number) => {
    if (onVehicleDetailRequest) {
      onVehicleDetailRequest(id);
      return;
    }
    void openLegacyVehicleDetail(id);
  };

  const handleInstall = async () => {
    if (!installPrompt) return;
    await installPrompt.prompt();
    const choice = await installPrompt.userChoice;
    if (choice.outcome === 'accepted') {
      setInstallState('installed');
    }
    setInstallPrompt(null);
  };

  const normalizedQuery = query.trim().toLocaleLowerCase('cs-CZ');
  const sortedVehicles = [...vehicles].sort((a, b) => {
    const score = vehicleAttentionScore(a) - vehicleAttentionScore(b);
    if (score !== 0) return score;
    return vehicleTitle(a).localeCompare(vehicleTitle(b), 'cs');
  });

  const filteredVehicles = sortedVehicles.filter((vehicle) => {
    const days = daysUntil(vehicle.stk_valid_until);
    const matchesSection =
      section === 'all'
        ? true
        : section === 'attention'
          ? days == null || days <= 90
          : vehicle.current_mileage_km != null || !!vehicle.plate?.trim();

    if (!matchesSection) return false;
    if (!normalizedQuery) return true;

    const haystack = [
      vehicleTitle(vehicle),
      vehicle.plate ?? '',
      vehicle.vin ?? '',
      vehicle.nickname ?? '',
    ]
      .join(' ')
      .toLocaleLowerCase('cs-CZ');

    return haystack.includes(normalizedQuery);
  });

  const attentionCount = vehicles.filter((vehicle) => {
    const days = daysUntil(vehicle.stk_valid_until);
    return days == null || days <= 90;
  }).length;
  const healthyCount = vehicles.filter((vehicle) => {
    const days = daysUntil(vehicle.stk_valid_until);
    return days != null && days > 90;
  }).length;
  const mileageKnownCount = vehicles.filter((vehicle) => vehicle.current_mileage_km != null).length;

  return (
    <div className={styles['vl-root']}>
      <div className={styles['vl-shell']}>
        <header className={styles['vl-hero']}>
          <div className={styles['vl-heroTopline']}>
            <span className={styles['vl-badge']}>PWA Mobile</span>
            <span className={styles['vl-connection']} data-online={String(isOnline)}>
              {isOnline ? 'Online' : 'Offline'}
            </span>
          </div>
          <h1 className={styles['vl-heading']}>Moje vozidla</h1>
          <p className={styles['vl-subheading']}>
            Rychlý mobilní přehled s velkými ovládacími prvky, prioritami a připraveností pro
            instalaci na plochu.
          </p>
          <div className={styles['vl-heroActions']}>
            <button
              type="button"
              className={styles['vl-primaryButton']}
              onClick={() => void load()}
            >
              Obnovit data
            </button>
            {installPrompt && installState !== 'installed' && (
              <button type="button" className={styles['vl-secondaryButton']} onClick={() => void handleInstall()}>
                Instalovat aplikaci
              </button>
            )}
          </div>
          {!isOnline && (
            <p className={styles['vl-offlineBanner']} role="status">
              Jste offline. Aplikace zůstává čitelná, ale nové údaje se načtou až po obnovení připojení.
            </p>
          )}
        </header>

        <section className={styles['vl-summaryGrid']} aria-label="Souhrn vozového parku">
          <article className={styles['vl-summaryCard']}>
            <span className={styles['vl-summaryLabel']}>Celkem vozidel</span>
            <strong className={styles['vl-summaryValue']}>{vehicles.length}</strong>
            <span className={styles['vl-summaryHint']}>Vaše osobní garáž v mobilu</span>
          </article>
          <article className={styles['vl-summaryCard']}>
            <span className={styles['vl-summaryLabel']}>Potřebuje pozornost</span>
            <strong className={styles['vl-summaryValue']}>{attentionCount}</strong>
            <span className={styles['vl-summaryHint']}>STK do 90 dnů nebo chybí údaj</span>
          </article>
          <article className={styles['vl-summaryCard']}>
            <span className={styles['vl-summaryLabel']}>V pořádku</span>
            <strong className={styles['vl-summaryValue']}>{healthyCount}</strong>
            <span className={styles['vl-summaryHint']}>Delší platnost STK</span>
          </article>
          <article className={styles['vl-summaryCard']}>
            <span className={styles['vl-summaryLabel']}>S tachometrem</span>
            <strong className={styles['vl-summaryValue']}>{mileageKnownCount}</strong>
            <span className={styles['vl-summaryHint']}>Připravené pro servisní přehled</span>
          </article>
        </section>

        <section className={styles['vl-toolbar']} aria-label="Filtrace vozidel">
          <label className={styles['vl-searchWrap']}>
            <span className={styles['vl-searchLabel']}>Najít vozidlo</span>
            <input
              type="search"
              inputMode="search"
              autoComplete="off"
              placeholder="Hledat podle značky, SPZ nebo VIN"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              className={styles['vl-searchInput']}
            />
          </label>
          <div className={styles['vl-toolbarGroup']}>
            <div className={styles['vl-inlineLabel']}>Režim zobrazení</div>
            <div className={styles['vl-pillRow']} role="tablist" aria-label="Režim zobrazení vozidel">
              {[
                ['grid', 'Studio'],
                ['list', 'Řádky'],
                ['compact', 'Radar'],
              ].map(([value, label]) => (
                <button
                  type="button"
                  key={value}
                  role="tab"
                  aria-selected={viewMode === value}
                  className={styles['vl-pillButton']}
                  data-active={String(viewMode === value)}
                  onClick={() => setViewMode(value as VehicleViewMode)}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
          <div className={styles['vl-toolbarGroup']}>
            <div className={styles['vl-inlineLabel']}>Filtr</div>
            <div className={styles['vl-pillRow']} role="tablist" aria-label="Zobrazení">
            {[
              ['all', 'Všechna'],
              ['attention', 'Pozornost'],
              ['garage', 'Garáž'],
            ].map(([value, label]) => (
              <button
                type="button"
                key={value}
                role="tab"
                aria-selected={section === value}
                className={styles['vl-pillButton']}
                data-active={String(section === value)}
                onClick={() => setSection(value as VehicleSection)}
              >
                {label}
              </button>
            ))}
            </div>
          </div>
        </section>

        {vehicles.length === 0 ? (
          <p className={styles['vl-empty']} data-testid="react-vehicle-list-empty">
            Zatím nemáte žádná vozidla.
          </p>
        ) : filteredVehicles.length === 0 ? (
          <p className={styles['vl-empty']}>Tomuto filtru teď neodpovídá žádné vozidlo.</p>
        ) : (
          <ul
            className={styles['vl-list']}
            data-view-mode={viewMode}
            data-testid="react-vehicle-list"
          >
            {filteredVehicles.map((v) => {
              const statusMeta = vehicleStatus(v);
              const listKmText = formatMileage(v.current_mileage_km);
              const shortNote = formatShortNote(v);
              return (
                <li
                  key={v.id}
                  className={styles['vl-item']}
                  data-testid="react-vehicle-list-item"
                  data-view-mode={viewMode}
                >
                  {viewMode === 'list' ? (
                    <div className={styles['vl-listRow']} onClick={() => handleDetail(v.id)} role="button" tabIndex={0}>
                      <div className={styles['vl-listRowMain']}>
                        <p className={styles['vl-listRowTitle']}>{vehicleTitle(v)}</p>
                        <p className={styles['vl-listRowPlate']}>{v.plate?.trim() || 'Bez SPZ'}</p>
                        <p className={styles['vl-listRowNote']}>{shortNote}</p>
                      </div>
                      <div className={styles['vl-listRowKm']}>{listKmText}</div>
                      <div className={styles['vl-listRowStatus']}>
                        <span className={styles['vl-statusBadgeInline']} data-tone={statusMeta.tone}>
                          {statusMeta.label}
                        </span>
                      </div>
                    </div>
                  ) : (
                    <>
                      <div className={styles['vl-itemVisual']}>
                        <VehicleImage
                          vehicle={v}
                          className={styles['vl-thumb']}
                          make={v.brand}
                          model={v.model}
                          year={v.year}
                          nickname={v.nickname}
                          alt={vehicleTitle(v)}
                        />
                        <span className={styles['vl-statusBadge']} data-tone={statusMeta.tone}>
                          {statusMeta.label}
                        </span>
                      </div>
                      <div className={styles['vl-itemBody']}>
                        <div className={styles['vl-itemHeader']}>
                          <div>
                            <p className={styles['vl-itemTitle']}>{vehicleTitle(v)}</p>
                            <p className={styles['vl-itemLead']}>
                              {viewMode === 'compact'
                                ? [v.brand, v.model].filter(Boolean).join(' ') || 'Bez doplňujících údajů'
                                : `${v.plate?.trim() || 'Bez SPZ'}${v.year ? ` · ${v.year}` : ''}`}
                            </p>
                          </div>
                        </div>
                        {viewMode === 'compact' ? (
                          <div className={styles['vl-radarStrip']}>
                            <span className={styles['vl-chip']}><strong>SPZ</strong> {v.plate?.trim() || '—'}</span>
                            <span className={styles['vl-chip']}><strong>STK</strong> {formatDateCz(v.stk_valid_until)}</span>
                            <span className={styles['vl-chip']}><strong>Tacho</strong> {listKmText}</span>
                          </div>
                        ) : (
                          <dl className={styles['vl-metaGrid']}>
                            <div className={styles['vl-metaCard']}>
                              <dt className={styles['vl-metaLabel']}>STK</dt>
                              <dd className={styles['vl-metaValue']}>{formatDateCz(v.stk_valid_until)}</dd>
                            </div>
                            <div className={styles['vl-metaCard']}>
                              <dt className={styles['vl-metaLabel']}>Tachometr</dt>
                              <dd className={styles['vl-metaValue']}>{listKmText}</dd>
                            </div>
                            <div className={styles['vl-metaCard']}>
                              <dt className={styles['vl-metaLabel']}>VIN</dt>
                              <dd className={styles['vl-metaValue']} title={v.vin ?? ''}>
                                {v.vin?.trim() || 'Neuvedeno'}
                              </dd>
                            </div>
                          </dl>
                        )}
                        <div className={styles['vl-itemActions']}>
                          <button
                            type="button"
                            className={styles['vl-detail']}
                            data-testid="react-vehicle-list-detail-btn"
                            onClick={() => handleDetail(v.id)}
                          >
                            Otevřít detail
                          </button>
                        </div>
                      </div>
                    </>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
