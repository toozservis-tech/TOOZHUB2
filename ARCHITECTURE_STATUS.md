# ARCHITECTURE STATUS

## Aktivní moduly

- Auth a account management: `src/server/main.py`
- Vozidla a servisní historie: `src/modules/vehicle_hub/routers_v1/vehicles.py`, `src/modules/vehicle_hub/routers_v1/service_records.py`
- Připomínky a rezervace: `src/modules/vehicle_hub/routers_v1/reminders.py`, `src/modules/vehicle_hub/routers_v1/reservations.py`
- Service workspace: `src/modules/vehicle_hub/routers_v1/service_workspace.py`
- Licence a billing: `src/modules/licensing/service.py`, `src/modules/vehicle_hub/routers_v1/license_status.py`
- Admin/developer: `src/server/admin_api.py`

## Source-of-truth pro ownership

- Primární ownership je `vehicle_ownerships`.
- `vehicles.user_email` je kompatibilní legacy alias pro starší klienty a exporty.

## Source-of-truth pro licence

- Jediná rozhodovací vrstva je `src/modules/licensing/service.py`.
- `src/modules/licensing/licensing_service.py` je deprecated compatibility wrapper.

## Append-only princip servisní historie

- `service_records` se fyzicky nemažou.
- Delete přepíná `is_deleted=1` a zapisuje audit log do `service_record_audit_logs`.
- Update vždy zapisuje `previous_snapshot_json`, `new_snapshot_json` a `snapshot_hash`.

## RBAC přehled

- `user`: vlastní vozidla a jejich historii
- `service`: pouze explicitně sdílená vozidla / linky
- `admin`: admin přístup napříč tenantem
- `developer_admin`: admin + developer control center, ale není implicitně servis

## Deprecated části

- `vehicles.user_email` jako ownership source-of-truth
- `src/modules/licensing/licensing_service.py` jako samostatná licenční implementace
- `/user/ares` jako primární ARES endpoint
- Runtime `create_all` / `ALTER TABLE` patching v request flow
