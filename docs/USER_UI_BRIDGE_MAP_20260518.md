# User UI Bridge Map - 2026-05-18

Baseline SHA: `f8218f5d1df66b3f575338ddc254b6ca684e3e20`

Status values:

- `READY`: original handler/API is identified and can be used directly or proxied.
- `NEEDS_ADAPTER`: original function exists but the new screen/component needs a small adapter to aggregate data, select a vehicle, or open a modal section.
- `BLOCKER`: no reliable original handler/API was identified; do not build fake behavior.

| New UI prvek | Původní funkce/handler | Původní DOM/API | Stav | Poznámka |
| --- | --- | --- | --- | --- |
| Nový zvoneček | `toggleAppNotificationsPanel(event)` | `#desktopNotificationsButton`, `#mobileNotificationsButton`, `#appNotificationsPanel`, `#appNotificationsList` | READY | Prefer physically reuse original button/panel or proxy `.click()` |
| Nový notifikační panel | `renderAppNotificationsPanelList()`, `renderAppNotificationsArchivePanel()` | `#appNotificationsPanel`, local notification state | READY | Do not create a second panel |
| Notifikační badge | `loadSystemNotifications()` updates badge state | `#desktopNotificationsBadge`, `#mobileNotificationsBadge` | READY | Must keep unread count |
| Nový profil button | `toggleMobileProfileMenu()` | `#desktopProfileButton`, `#mobileProfileButton` | READY | Profile click opens menu, not settings |
| Nové profilové menu | `setMobileProfileMenuOpen()`, `syncMobileProfileMenu()` | `#mobileProfileMenu.mobile-profile-menu` | READY | Reuse original menu DOM or mount it into new topbar layer |
| Jak na to | `openHowToHubModal()` | `#mobileProfileTutorialRow`, `data-testid="menu-how-to-tutorial"` | READY | Close menu first, then open original modal |
| Licence | `openLicenseModal()`, `openLicensePlans()` | `#licenseModal`, `#licenseQuickToggle` | READY | License quick dropdown can remain original |
| Nastavení | `switchTab('account')`, `loadProfile(false)` | `#accountTab`, `#profileContainer` | READY | From menu and sidebar |
| Odhlášení | `handleLogout()` | `#logout-btn`, profile danger action | READY | Must clear tokens/timers/session through original |
| Sidebar Přehled | `switchTab('home')` | `#homeTab`, `.tab[data-tab-key="home"]` | READY | Keep URL sync through `switchTab` |
| Sidebar Moje vozidla | `switchTab('vehicles')` | `#vehiclesTab`, `.tab[data-tab-key="vehicles"]` | READY | Calls `loadVehicles(false)` |
| Sidebar Servisní historie | aggregate records, then `showServiceRecordDetail(recordId, vehicleId)` for detail | `/api/v1/vehicles`, `/api/v1/vehicles/{id}/records` | NEEDS_ADAPTER | No direct baseline tab exists |
| Sidebar Připomínky | `switchTab('reminders')`, `loadReminders()` | `#remindersTab`, `/api/v1/reminders` | READY | New board can be adapter over loaded reminders |
| Sidebar Dokumenty | `switchTab('documents')`, `loadDocumentsHub()` | `#documentsTab`, `/api/v1/vehicles/documents/hub` | READY | Use original hub |
| Sidebar Servisy | `switchTab('servicesDirectory')`, `loadServicesDirectory()` | `#servicesDirectoryTab`, `/api/v1/services/*` | READY | Button currently hidden in baseline; must respect visibility rules |
| Sidebar Faktury | none confirmed | possible document/license APIs | BLOCKER | Decide product mapping before UI |
| Sidebar Nastavení | `switchTab('account')` | `#accountTab` | READY | Existing settings panels remain |
| Topbar search | none confirmed as global user search | vehicle/document datasets | NEEDS_ADAPTER | Start with client-side vehicle search after data load; do not fake server search |
| `+ Přidat vozidlo` | `openAddVehicleModal()` or `switchTab('vehicles', { expandVehiclesAdd: true })` | `#addVehicleModal`, `#btnOpenAddVehicleModal` | READY | Keep original modal/form |
| Vozidlo Detail | `showVehicleDetail(vehicleId)` | `#vehicleDetailModal`, `/api/v1/vehicles/{id}` | READY | Vehicle card must pass real `vehicle.id` |
| Detail: Technické údaje | `openVehicleDetailFloatingSection('basic', vehicleId)` | detail floating section state | READY | Proxy from new tab |
| Detail: Servisní historie | `openVehicleDetailFloatingSection('service', vehicleId)`, `loadServiceRecordsModal(vehicleId)` | `/api/v1/vehicles/{id}/records` | READY | Service record detail via `showServiceRecordDetail()` |
| Detail: Dokumenty | `openVehicleDetailFloatingSection('documents', vehicleId)` | document section/download handlers | READY | Preserve upload/preview/download |
| Detail: Fotogalerie | `openVehicleDetailFloatingSection('gallery', vehicleId)` | photo/gallery endpoints | READY | Existing authorized photo logic |
| Detail: Připomínky/provoz | `openVehicleDetailFloatingSection('ops', vehicleId)` | mileage/STK/reminder ops | READY | Use existing section |
| Detail: Přístupy a sdílení | `openVehicleDetailFloatingSection('access', vehicleId)` | service access APIs | READY | Preserve grant/revoke |
| Přidat záznam | `openAddServiceRecordModal(vehicleId)` | `#addServiceRecordModal`, `/api/v1/vehicles/{id}/records` | READY | Original modal includes attachment/prefill |
| Dokumenty vozidla | `openVehicleDetailFloatingSection('documents', vehicleId)` | detail documents section | READY | If detail is closed, adapter opens detail then section |
| Sdílet servisem | `openVehicleDetailFloatingSection('access', vehicleId)` | `/api/v1/services/vehicle-access` | READY | Do not replace with toast |
| Upload fotky | `handleVehiclePhotoUpload(vehicleId, input)` and photo helpers | `vehicle-photo-upload-{id}`, `/api/v1/vehicles/{id}/photo`, `/photos` | READY | Use existing file inputs/endpoints |
| Upload dokumentu | record attachment/document handlers | `#serviceAttachmentFile-add`, `/records/attachments/upload`, document hub endpoints | READY | Context determines service record vs central document |
| Připomínka detail | reminder modal/edit functions from `loadReminders()` | `#remindersContainer`, `/api/v1/reminders/{id}` | READY | Exact modal names should be re-confirmed during implementation |
| Faktura detail | none confirmed | documents/license billing | BLOCKER | No standalone invoice detail handler found |
| Servisní přístup detail | service directory/access handlers | `#servicesDirectoryTab`, access APIs | NEEDS_ADAPTER | Existing directory has multiple flows; map exact card action during implementation |
| Zobrazit archivovaná vozidla | unknown archived endpoint/flag in baseline list | `/api/v1/vehicles` maybe includes archived state | BLOCKER | Must verify API payload before enabling |
| Grid/list toggle | `setVehicleView('grid'|'list'|'compact')` | `.vehicle-view-btn[data-view]` | READY | New icons can call original function |
| Add vehicle ORV/QR | ORV wizard functions | `#orvOnboardingModal`, `#addVehicleTransferQrBtn`, ORV APIs | READY | Keep original wizard |
| Account save | `handleSaveProfile()` | `#settingsSaveButton`, `/user/me` PUT | READY | Only visible in settings account panel |
| 2FA / security | security setup/enable/disable handlers | `/user/security/*` | READY | High-risk; preserve original forms |
| Data export/delete | `handleAccountDataExport()`, `handleDeleteAccount()` | `/user/me/export`, `/user/me` DELETE | READY | Do not restyle until reviewed |

## Required Implementation Pattern

1. New component renders visual shell.
2. For each interactive element, bridge to a row in this table.
3. If status is `READY`, call original handler or click original DOM element.
4. If status is `NEEDS_ADAPTER`, implement minimal adapter using existing API/handler and test it before visual polish.
5. If status is `BLOCKER`, show no active fake UI. Either hide the control or mark it disabled in staging review.

## Blocker List

- Standalone `Faktury` screen and invoice detail.
- Global topbar search.
- Top-level aggregate `Servisní historie` screen.
- Archived vehicles filter/card count.
- Exact service access detail card action beyond known access directory operations.

## Recommended Next Implementation Step

Build a disabled scaffold for **next user shell/topbar/sidebar**:

- `web/user-app-next.css`
- `web/user-app-next.js`
- Not loaded by `web/index.html` yet.
- Include adapters for:
  - `nextOpenNotifications()` -> original notifications button/panel.
  - `nextOpenProfileMenu()` -> original profile menu.
  - `nextSwitchTab(tab)` -> `switchTab(tab)`.
  - `nextOpenAddVehicle()` -> `openAddVehicleModal()`.

Only after review should the scaffold be loaded behind a staging-only guard for `/web/app/u/*`.
