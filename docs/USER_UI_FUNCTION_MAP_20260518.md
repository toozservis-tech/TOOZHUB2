# User UI Function Map - 2026-05-18

Baseline SHA: `f8218f5d1df66b3f575338ddc254b6ca684e3e20`

Purpose: inventory the production user application before any next UI implementation. New UI may change layout and styling, but must preserve these DOM anchors, handlers, API calls, state objects, and workflows.

## Scope And Rules

- Source audited: `web/index.html` on the baseline SHA.
- Service shell is out of scope and must remain untouched: `web/service-shell.js`.
- Public landing, login/register, admin and backend are out of scope for the next user UI shell.
- Any new visual element must either keep the original DOM/handler or proxy to it.
- If an original handler/API cannot be found, mark the new element as `BLOCKER` rather than implementing a fake action.

## Shell Visibility And Auth

| Area | DOM / ID / Classes | Handler / Flow | API / State | Must Preserve |
| --- | --- | --- | --- | --- |
| App shell after login | `#app-shell.app-shell-root`, `#dashboard`, `#mainNavbar.navbar.app-shell-header` | Auth routes call app navigation and reveal shell after session is established | `/api/me`, `/user/me`, `currentUser`, `accessToken`, workspace state | Public/auth views must not leak into `/web/app/u/*`; service/admin routing must keep existing visibility rules |
| Main navbar | `#mainNavbar`, `.navbar-brand`, `#mainNavbarMenu`, `.navbar-actions` | Shown/hidden by auth/session flow and `handleLogout()` | `currentUser`, workspace context, license state | New shell must not orphan original notification/profile/license/logout controls |
| Workspace switch | `#workspaceModeSwitch`, `.workspace-mode-switch-btn[data-workspace-mode]`, profile copy in `#mobileProfileWorkspaceSwitchWrap` | `switchWorkspaceUIMode('user'|'service')` | `/api/me`, role/workspace payload | Keep tenant/workspace isolation and service account mode |
| Logout | `#logout-btn`, profile menu logout action | `handleLogout()` | clears token/session/local auth state, stops timers and polling | Never replace with manual local redirect only |

## Topbar Functions

| Area | DOM / ID / Classes | Handler / Flow | API / State | Must Preserve |
| --- | --- | --- | --- | --- |
| Desktop notification button | `#desktopNotificationsButton.app-notifications-button`, `#desktopNotificationsBadge` | `toggleAppNotificationsPanel(event)` | `window.__systemNotificationsLastItems`, local seen/ack/archive keys | Badge count, aria state, panel positioning, outside-click close |
| Mobile notification button | `#mobileNotificationsButton.app-notifications-button`, `#mobileNotificationsBadge` | `toggleAppNotificationsPanel(event)` | same notification state | Same panel and badge behavior as desktop |
| Notification panel | `#appNotificationsPanel`, `#appNotificationsList`, `#appNotificationsArchiveDetails`, `#appNotificationsArchiveList` | `renderAppNotificationsPanelList()`, `renderAppNotificationsArchivePanel()`, document click close | `loadSystemNotifications()`, local archive/ack keys | Do not create a second notification panel; style or move the original |
| Notification polling | no visual root only | `startSystemNotificationsPolling()`, `stopSystemNotificationsPolling()`, `loadSystemNotifications()` | system notification payloads, local storage keys | Polling must start/stop with auth lifecycle |
| Desktop profile button | `#desktopProfileButton.mobile-profile-button.app-desktop-profile-navbar-btn` | `toggleMobileProfileMenu()` | profile/license/workspace state | Must open menu, not directly route to settings |
| Mobile profile button | `#mobileProfileButton.mobile-profile-button` | `toggleMobileProfileMenu()` | profile/license/workspace state | Same menu behavior |
| Profile menu | `#mobileProfileMenu.mobile-profile-menu`, `.mobile-profile-sheet`, `.mobile-profile-action` | `setMobileProfileMenuOpen()`, `syncMobileProfileMenu()`, `closeMobileProfileMenu()` | `currentUser`, license label, workspace mode | Keep all original rows and close/backdrop behavior |
| Profile item: Jak na to | `#mobileProfileTutorialRow`, `data-testid="menu-how-to-tutorial"` | `openHowToHubModal()` with fallback to `window.openHowToHubModal()` | onboarding/tutorial state | Must remain available from new user menu |
| Profile item: Nastavení účtu | profile menu action | `closeMobileProfileMenu(); switchTab('account')` | `loadProfile(false)` | Profile click itself must not skip menu |
| Profile item: Licence a plán | profile menu action | `openLicenseModal()` | license status/subscription flows | Must open existing license modal |
| Profile item: Theme | profile menu action | `window.toggleAppUiTheme()` | theme preference | Optional in new design, but if shown must call original |
| Profile item: Odhlásit se | danger profile menu action | `handleLogout()` | auth/session cleanup | Must not be removed |
| License quick dropdown | `#licenseQuickToggle`, `#licenseQuickDropdown`, `#licenseQuickLabel` | `initLicenseQuickBadge()`, `openLicensePlans()`, `openLicenseModal()` | `/api/v1/license/status`, subscription APIs | New UI can visually integrate it, but must use original license flow |

## Navigation And Sections

| Section | DOM / ID / Classes | Handler / Flow | API / State | Must Preserve |
| --- | --- | --- | --- | --- |
| Sidebar / tabs root | `#appShellNav`, `.tabs`, `.tab[data-tab-key]` | `switchTab(tab, options)` | active tab, URL sync, license locks, capability checks | New sidebar must call `switchTab`, not private fake routing |
| Přehled | `#homeTab`, `#homeDashboardGreeting`, `#homeDashboardHeroStatus`, `#homeDashboardStats`, `#homeDashboardPrimaryActions`, `#homeDashboardRecentFeed` | `loadHomeDashboard()`, `renderHomeDashboardState()` | `/api/v1/vehicles`, `/api/v1/reminders`, `/api/v1/license/status`, records preview calls | Counts, reminders, status bubbles and recommended actions must use real data |
| Moje vozidla | `#vehiclesTab`, `#vehiclesContainer`, `#btnOpenAddVehicleModal`, `.vehicle-view-btn` | `loadVehicles(force)`, `setVehicleView(mode)`, `openAddVehicleModal()` | `/api/v1/vehicles`, photo helpers, service preview records | Real vehicles only; keep vehicle IDs and current view state |
| Připomínky | `#remindersTab`, `#remindersContainer` | `loadReminders(force)`, reminder modal handlers | `/api/v1/reminders`, `/api/v1/reminders/settings` | Complete CRUD and settings toggles |
| Objednat servis / reservations | `#reservationsTab`, `#reservationsContainer` | `loadReservations(force)` | reservation endpoints | Preserve if visible in user shell |
| Servisy / přístupy | `#servicesDirectoryTab`, `#servicesDirectoryTabButton` | `loadServicesDirectory(force)`, service access handlers | `/api/v1/services/discovery`, `/api/v1/services/vehicle-access`, `/api/v1/services/my-contacts` | Share/access workflow must stay intact |
| Service workspace | `#serviceWorkspaceTab`, `#serviceWorkspaceTabButton` | `loadServiceWorkspace()` | service workspace endpoints | Do not restyle as user UI; service account remains separate |
| Dokumenty | `#documentsTab`, `#documentsHubContainer` | `loadDocumentsHub(force)` | `/api/v1/vehicles/documents/hub` and document endpoints | Central documents must remain reachable |
| Nastavení | `#accountTab`, `#profileContainer` | `loadProfile(force)`, `setSettingsPanel(panel)` | `/user/me`, `/user/security/*` | Account, notifications, security, data export/delete flows |
| Podpora | `#supportTab` | `loadSupportPanel(force)` | support/contact flows | Optional in main sidebar, but must stay accessible if present |

## Vehicles And Detail

| Area | DOM / ID / Classes | Handler / Flow | API / State | Must Preserve |
| --- | --- | --- | --- | --- |
| Vehicle list container | `#vehiclesContainer` | `loadVehicles(force)` renders vehicles and view modes | `/api/v1/vehicles` | Use real production/staging data only |
| Add vehicle entry | `#btnOpenAddVehicleModal`, `#addVehicleModal`, `#vehiclesAddPanel` | `openAddVehicleModal()`, `closeAddVehicleModal()`, `handleAddVehicle()` | `/api/v1/vehicles`, `/api/v1/vehicles/preview-from-vin`, ORV scan APIs | Preserve VIN/ORV/photo form and validation |
| Add vehicle photo | `#vehiclePhotoInput`, `#vehiclePhotoPreviewWrap` | `previewAddVehiclePhoto()`, crop/reopen helpers | upload through vehicle creation payload | Do not invent image URLs |
| Detail modal | `#vehicleDetailModal`, `#vehicleModalBody`, `#vehicleModalTitle`, `#vehicleModalRemoveBtn` | `showVehicleDetail(vehicleId)`, `closeVehicleModal()` | `/api/v1/vehicles/{id}` | New detail must carry the same `vehicleId` into all actions |
| Detail floating sections | dock buttons with `data-vehicle-detail-tab` for `basic`, `service`, `ops`, `documents`, `gallery`, `access` | `openVehicleDetailFloatingSection(section, vehicleId)`, `closeVehicleDetailFloatingSection()` | current vehicle/detail section state | New detail tabs must call these section keys |
| Gallery/photos | `vehicle-photo-upload-{id}`, `vehicle-photo-preview-modal-{id}`, hero/gallery actions | `handleVehiclePhotoUpload()`, `hydrateVehiclePhotoPreview()`, gallery helpers | `/api/v1/vehicles/{id}/photos`, `/api/v1/vehicles/{id}/photo`, catalog image endpoints | Use existing authorized photo endpoints and fallback states |
| Service records in detail | `loadServiceRecordsModal(vehicleId)` | record list/detail/edit/delete flows | `/api/v1/vehicles/{id}/records`, `/records/{recordId}` | Detail, edit, delete, PDF export must remain connected |
| Add service record | `#addServiceRecordModal`, `#addServiceRecordModalBody`, `#addServiceRecordForm` | `openAddServiceRecordModal(vehicleId)`, `handleAddServiceRecordSubmit(event)` | `/api/v1/vehicles/{id}/records`, attachment upload/prefill endpoints | Keep category dropdown, document prefill, attachment upload |
| Vehicle documents | detail section `documents`, central hub | `openVehicleDetailFloatingSection('documents', id)`, `loadDocumentsHub()` | document hub, TP/PDF/download endpoints | Upload/download/preview behavior must remain original |
| Share with service | detail/access section and services directory | `openVehicleDetailFloatingSection('access', id)`, service access handlers | `/api/v1/services/vehicle-access`, `/api/v1/services/connect-by-email` | Never reduce to a toast; must grant/revoke access |
| Remove/archive vehicle | `#vehicleModalRemoveBtn`, sidebar remove buttons | `deleteVehicle(vehicleId)` | `/api/v1/vehicles/{id}/remove/init`, `/remove/confirm` | Preserve confirmation/archive workflow |

## Reminders, Documents, Invoices, Services

| Area | DOM / ID / Classes | Handler / Flow | API / State | Must Preserve |
| --- | --- | --- | --- | --- |
| Reminder board | `#remindersTab`, `#remindersContainer` | `loadReminders()`, create/edit/complete/delete functions | `/api/v1/reminders`, `/api/v1/reminders/settings` | New kanban/cards must call original CRUD |
| Reminder settings | reminder settings summary/toggles | settings load/save functions | `/api/v1/reminders/settings` | Automatic reminder toggles must remain real |
| Documents hub | `#documentsTab`, `#documentsHubContainer` | `loadDocumentsHub()` | `/api/v1/vehicles/documents/hub`, related download endpoints | Keep central hub and per-vehicle document actions |
| Upload document to service record | `#serviceAttachmentFile-add`, source type select | `handleAddServiceAttachmentSelection()`, `uploadServiceRecordAttachment()` | `/api/v1/vehicles/{id}/records/attachments/upload`, document prefill endpoint | Upload/prefill must remain connected |
| Invoices | implemented through document/service record/license flows; no standalone `invoicesTab` found in baseline user tab map | document/license/subscription handlers | document and license APIs | `BLOCKER`: target sidebar has Faktury; bridge must decide whether it maps to documents/license invoices or needs a real existing tab |
| Service access directory | `#servicesDirectoryTab` | `loadServicesDirectory()`, access grant/revoke/connect handlers | `/api/v1/services/*` | Must preserve contacts, access requests and sharing |
| License/subscription | `#licenseModal`, `#licenseQuickToggle` | `openLicenseModal()`, `openLicensePlans()`, subscription change/cancel/resume handlers | `/api/v1/license/status`, `/api/v1/license/subscription/*`, Comgate checkout | Must preserve sandbox/production env safety |
| Onboarding / Jak na to | profile menu tutorial row and `openHowToHubModal()` | modal/tutorial helpers | tutorial state and DOM | Must remain callable from profile menu and help affordances |
| Settings | `#profileContainer`, `data-settings-panel`, `data-settings-panel-btn` | `loadProfile()`, `setSettingsPanel()`, `handleSaveProfile()` | `/user/me`, `/user/security/*`, export/delete APIs | New settings restyle must not break security/data export |

## Existing Blockers / Ambiguities

- `Faktury` as a standalone user sidebar item: baseline tab map has no `invoices`/`invoicesTab`. It likely maps to documents, service-record attachments, or license billing. Needs product decision before implementing as a real section.
- `Servisní historie` as a top-level sidebar item: baseline exposes service history primarily through vehicle detail records and quick service record modal, not as a first-class `serviceHistoryTab`. A new top-level screen needs adapter over records from `/api/v1/vehicles/{id}/records`.
- `Topbar global search`: no single production global search handler found in the audited shell. New search should be `NEEDS_ADAPTER`, initially scoped to vehicles/documents after mapping.
- `Invoice detail`: no dedicated user invoice detail handler found in baseline; document/license flows exist.
- Exact mobile bottom-nav target set differs from baseline tabs and must be mapped before activation.
