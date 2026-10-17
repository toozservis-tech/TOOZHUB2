# Owner lifecycle — shared mobile contract

These changes are prepared in source. They do not imply a production migration or deployment.

`GET /api/v1/vehicles/{vehicle_id}/lifecycle` is available only to the current primary owner, including when a service or administrator otherwise has vehicle editing rights. It returns `vehicle_id`, `ownership_id`, opaque `ownership_token`, `version` (initially 0 in an ownership period), `state` (`active` or `deposited`) and supported action strings.

`POST` to the same path accepts:

```json
{"client_id":"a client-generated UUID","ownership_id":123,"ownership_token":"64 lowercase hexadecimal characters from GET","expected_version":0,"action":"deposited","note":"Optional, at most 1000 characters","effective_date":"2026-10-17"}
```

Keep the entire operation, including its UUID, across a retry. A changed body with the same UUID returns 409. A successful response can be retrieved by an identical retry by its original authenticated actor after ownership ends. A request that was never executed cannot cross an ownership boundary: the token also changes when the database reuses an earlier owner's assignment row. The token is a concurrency fence, never proof of ownership by itself.

Actions:

| Action | Outcome |
|---|---|
| `deposited` | Active → deposited. Ownership, history, sharing, bookings and reminders remain. This is the owner's app designation, not a registry operation. |
| `reactivated` | Deposited → active; no ownership change. |
| `sold` | Private archive followed by ownership release; no buyer is assigned automatically. |
| `removed` | Private archive followed by ownership release; the existing verified last-owner recovery policy remains available. |
| `scrapped` | Private archive and ownership release, recording an owner's report only; no official registry or global VIN deletion. |

End actions return 409 while the current ownership period has an open job, or the owner has a future PENDING/CONFIRMED reservation for that vehicle. They do not cancel another actor's work. Deposit preserves those items. Future effective dates return 422. Ending an ownership period archives the private profile and original records/documents before sanitizing the active vehicle and revoking both permission models. Old-owner archives are not supplied to buyers or unrelated services.

Responses contain `vehicle_id`, `action`, `state` (`active`, `deposited`, `archived`), incremented `version`, optional `archive_id` and a Czech explanation. Archive list/detail adds a `lifecycle` metadata object with action, effective date, note, reporting time/actor, and explicit `owner_reported`/`official_registry_change` flags.

Sold and scrapped periods cannot be restored merely by entering the VIN. A reviewed ownership transfer remains separate. Removed profiles can be restored under the existing policy; private original documents stay protected by the archive and their existing privacy boundaries. Grants are not restored.

Legacy `DELETE /api/v1/vehicles/{id}` retains its existing owner/admin authorization but now performs the same immediate archival and open-work checks, recording `removed`. It still never deletes the VIN or technical history.

Recommended explicit pre-deploy command: `python -m scripts.migrate_mobile_release`. This single module applies additive `20261017_0014` and then `20261017_0015` before starting the changed API; a failure exits unsuccessfully and stops deployment. It needs no shell condition or argument quoting. The standalone `scripts/migrate_vehicle_lifecycle.py` applies only 0015. No endpoint performs schema DDL. An absent lifecycle schema fails closed with 503. Account erasure removes lifecycle events before their referenced archives/ownership/accounts.

Validation uses isolated temporary SQLite databases: lifecycle, privacy, sharing, VIN recovery, jobs, notices and migration regression tests. No real account mutations are required.

## Mobile entry and verification

Both mobile projects expose `Správa vozidla` from the vehicle detail and use the same action names: `Prodal jsem vozidlo`, `Odebrat z mé garáže`, `Evidovat likvidaci`, `Depozit` and `Vrátit do provozu`. A successful owner-only GET gates action availability. A 403 hides the entry; a missing route or schema shows an update explanation without enabling a write. A deposited vehicle receives a detail badge. These controls do not perform any official vehicle-registry operation.

Clients preserve the UUID and complete body for an uncertain response and require manual retry. Android persists pending requests encrypted in app-private no-backup storage with an account/server/vehicle scope and exposes recovery from the garage. iOS retains the pending operation in memory and prevents closing its sheet until resolved; it does not automatically resend after application termination. Both reject stale callbacks after an account/session change.

On 2026-10-17, the combined isolated backend suite passed 92 tests. A subsequent legacy-admin reporting-metadata adjustment passed its focused regression. The iOS transport/model checks passed seven groups, including malformed ownership tokens, identical retry bodies, account changes and error mapping. Android compilation and the full offline APK build passed. None of these checks imply the production API has been deployed or that a real owner's vehicle has been sold, archived or put into deposit.

The simulator iOS binary compiled and linked; the normal Xcode signing step was blocked by Finder metadata on the build output. A metadata-free staged copy passed ad-hoc signing and strict signature verification, then installed and launched successfully on the existing user simulator. Android installation with `-r` and cold launch succeeded on emulators 5554 and 5556 without clearing application storage. DeviceHub visually confirmed the iOS vehicle detail remained accessible. Visual verification of the new lifecycle panel is incomplete; DeviceHub scrolling returned `noWindowsAvailable`, and production does not yet expose the lifecycle contract. No end-to-end production lifecycle operation was performed.
