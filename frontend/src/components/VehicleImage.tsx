import { useEffect, useState } from 'react';

import { VehicleImageService } from '@/services/vehicleImageService';
import type { VehicleListItem } from '@/types/vehicle';
import styles from '@/styles/vehicleImage.module.css';

export type VehicleImageProps = {
  vehicle?: VehicleListItem;
  make: string | null | undefined;
  model: string | null | undefined;
  year?: number | null;
  nickname?: string | null;
  alt?: string;
  className?: string;
};

/**
 * Jednotný náhled vozidla: pevný poměr stran, ořez na střed, skeleton při načítání.
 */
export function VehicleImage({ vehicle, make, model, year, nickname, alt, className }: VehicleImageProps) {
  const [metaError, setMetaError] = useState(false);
  const [src, setSrc] = useState<string | null>(null);
  const [imgReady, setImgReady] = useState(false);

  const m = make ?? '';
  const mo = model ?? '';

  useEffect(() => {
    const ac = new AbortController();
    setMetaError(false);
    setSrc(null);
    setImgReady(false);
    let objectUrl: string | null = null;

    void (async () => {
      try {
        let resolvedUrl: string;

        if (vehicle && VehicleImageService.hasPrimaryPhoto(vehicle)) {
          resolvedUrl = await VehicleImageService.fetchPrimaryPhotoObjectUrl(vehicle.id, ac.signal);
          objectUrl = resolvedUrl;
        } else if (vehicle && VehicleImageService.hasCatalogPhoto(vehicle)) {
          resolvedUrl = await VehicleImageService.resolveCatalogImageUrl(vehicle, ac.signal);
          if (VehicleImageService.isProtectedCatalogImageUrl(resolvedUrl)) {
            resolvedUrl = await VehicleImageService.fetchCatalogImageObjectUrl(resolvedUrl, ac.signal);
            objectUrl = resolvedUrl;
          }
        } else {
          const meta = await VehicleImageService.resolve(m, mo, year, ac.signal, nickname);
          resolvedUrl = meta.url;
        }

        if (ac.signal.aborted) return;
        setSrc(resolvedUrl);
      } catch {
        if (ac.signal.aborted) return;
        setMetaError(true);
      }
    })();

    return () => {
      ac.abort();
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [
    vehicle?.id,
    vehicle?.photo_path,
    vehicle?.catalog_image_id,
    vehicle?.catalog_image_url,
    vehicle?.primary_photo?.available,
    m,
    mo,
    year,
    nickname ?? '',
  ]);

  const title = alt ?? ([m, mo].filter(Boolean).join(' ') || 'Vozidlo');
  const showSkeleton = !metaError && !!src && !imgReady;

  return (
    <div
      className={[styles['vi-frame'], className].filter(Boolean).join(' ')}
      role="img"
      aria-label={title}
    >
      {metaError && <div className={styles['vi-fallback']} aria-hidden />}
      {!metaError && !src && <div className={styles['vi-skeleton']} aria-hidden />}
      {!metaError && src && (
        <>
          {showSkeleton && <div className={styles['vi-skeleton']} aria-hidden />}
          <img
            src={src}
            alt=""
            className={styles['vi-img']}
            loading="lazy"
            decoding="async"
            onLoad={() => setImgReady(true)}
            onError={() => setMetaError(true)}
          />
        </>
      )}
    </div>
  );
}
