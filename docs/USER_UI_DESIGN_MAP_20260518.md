# User UI Design Map - 2026-05-18

Baseline SHA: `f8218f5d1df66b3f575338ddc254b6ca684e3e20`

This document defines the target visual system for the next user UI. It is intentionally separate from implementation so the first build can be reviewed for function parity before activation.

## Global Principles

- Light SaaS application, not dark automotive/ERP styling.
- Fixed left sidebar on desktop with the `Správa vozidel` brand and icon-based navigation.
- Topbar with search, primary add action, notifications, and profile menu.
- Main content on soft background `#F5F7FA` / `#F7F9FC`.
- White cards with subtle borders and shadows.
- Primary blue accent `#0B46D8` / `#2563EB`; green for verified/OK; orange/red for warning/overdue.
- Rounded cards and panels: 16-24 px, with larger 28 px surfaces only for hero/landing-style cards.
- Clean system typography, strong hierarchy, no negative letter spacing.
- New UI must not show old horizontal tabs as the primary navigation.
- No mock/demo vehicles on real app routes.

## Design Tokens

| Token | Value | Usage |
| --- | --- | --- |
| `--next-bg` | `#F5F7FA` | app background |
| `--next-surface` | `#FFFFFF` | cards, topbar, sidebar |
| `--next-surface-soft` | `#F8FAFC` | subtle card internals |
| `--next-text` | `#0F172A` | primary text |
| `--next-muted` | `#64748B` | secondary text |
| `--next-border` | `#DDE6F2` | card/input borders |
| `--next-blue` | `#0B46D8` | primary buttons, active nav |
| `--next-blue-soft` | `#EAF1FF` | active nav background |
| `--next-green` | `#16A34A` | OK/verified |
| `--next-orange` | `#F97316` | due soon |
| `--next-red` | `#EF4444` | overdue/service warning |
| `--next-radius-sm` | `10px` | buttons/controls |
| `--next-radius-md` | `14px` | vehicle cards |
| `--next-radius-lg` | `18px` | dashboard cards |
| `--next-radius-xl` | `24px` | hero/large panels |
| `--next-shadow-card` | `0 16px 40px rgba(15,23,42,.06)` | standard cards |
| `--next-shadow-float` | `0 24px 60px rgba(15,23,42,.12)` | dropdowns/modals |
| `--next-sidebar-w` | `224px` desktop / `76px` compact | shell grid |
| `--next-gap` | `18px` desktop | content gaps |
| `--next-z-sidebar` | `30` | shell sidebar |
| `--next-z-topbar` | `40` | sticky topbar |
| `--next-z-dropdown` | `80` | notification/profile menus |
| `--next-z-modal` | existing modal z-index | must not fight original modals |

Breakpoints:

- Desktop wide: `>= 1440px`, sidebar expanded, dashboard 3-column content plus right rail.
- Desktop narrow/tablet: `1024-1439px`, sidebar compact, right rails stack below.
- Tablet: `768-1023px`, 2-column vehicle cards, topbar compressed.
- Mobile: `< 768px`, bottom navigation or compact sidebar, one-column cards, minimum touch target 44 px.

## Components

### App Shell

Target:

- CSS grid with sidebar and main content, no `margin-left + 100vw` overflow patterns.
- Content wrapper uses `min-width: 0`, `max-width: 1520px`, and natural grid widths.
- Existing `#app-shell`, `#dashboard`, and route visibility remain source of truth.

Functional source:

- `#app-shell`, `#mainNavbar`, `#appShellNav`, `switchTab()`.

### Sidebar

Items from GPT designs:

- Přehled
- Moje vozidla
- Servisní historie
- Připomínky
- Dokumenty
- Servisy
- Faktury
- Nastavení

Bridge:

- Direct mappings exist for Přehled, Moje vozidla, Připomínky, Dokumenty, Servisy, Nastavení.
- Servisní historie and Faktury need adapters because baseline has no direct tab for them.

### Topbar

Target:

- Left search input.
- Primary `+ Přidat vozidlo` button.
- Original notification button/panel visually styled as bell.
- Original profile button/menu visually styled as avatar/name/dropdown.

Bridge:

- Search: `NEEDS_ADAPTER`.
- Add vehicle: `openAddVehicleModal()` or `switchTab('vehicles', { expandVehiclesAdd: true })`.
- Notifications: original `#desktopNotificationsButton`/`#appNotificationsPanel`.
- Profile menu: original `#desktopProfileButton`/`#mobileProfileMenu`.

### Cards And Controls

- Button: 44 px min height, primary blue for main action, white outlined for secondary.
- Badge: rounded pill, semantic colors.
- Card: white, border `#DDE6F2`, shadow, radius 14-18 px.
- Dropdown: use original DOM where existing; new dropdowns only as adapters.
- Modal bridge: original modals remain functional; next UI may open them from new buttons.

### Vehicle Card

Target from design:

- Photo at top, real uploaded photo if available.
- Status badge top-left.
- Vehicle name large and bold.
- Plate chip with CZ strip.
- VIN line.
- Mileage row.
- STK, insurance, last service rows.
- Actions: Detail, Přidat záznam, Dokumenty, Sdílet servisem, chevron/open.

Bridge:

- Detail: `showVehicleDetail(vehicleId)`.
- Přidat záznam: `openAddServiceRecordModal(vehicleId)`.
- Dokumenty: `openVehicleDetailFloatingSection('documents', vehicleId)` or open detail then section.
- Sdílet: `openVehicleDetailFloatingSection('access', vehicleId)`.

### Vehicle Detail

Target:

- Breadcrumb `Moje vozidla / Detail vozidla`.
- Large hero card: photo left, vehicle title/meta/actions right.
- Six metric cards: STK/SME, Pojištění, Nájezd, Poslední servis, Dokumenty, Přístupy servisů.
- Tab row: Technické údaje, Servisní historie, Dokumenty, Fotogalerie, Připomínky, Přístupy a sdílení.
- Main details panel plus right rail with timeline, nearest terms, quick actions.

Bridge:

- Shell opens through `showVehicleDetail(vehicleId)`.
- Tabs proxy to `openVehicleDetailFloatingSection(section, vehicleId)`.
- Service history is `loadServiceRecordsModal(vehicleId)`.
- Quick actions call original add/upload/export/access functions.

### Timeline Item

- Date column, dot/line, title, service name/metadata, optional image/document affordance.
- Click opens original service record detail: `showServiceRecordDetail(recordId, vehicleId)`.

### Documents

- Document cards grouped by vehicle/type.
- Upload must use original document/attachment handlers.
- Central documents screen maps to `loadDocumentsHub()`.

### Reminders

- Kanban-style board: Po termínu, Blíží se, Naplánováno, Dokončeno.
- Cards call original reminder detail/edit/complete/postpone flows.
- Settings toggles use `/api/v1/reminders/settings`.

### Invoice Card

- Target exists in sidebar, but baseline standalone invoice section is not confirmed.
- Until product mapping is confirmed, mark as `BLOCKER` or map to document/license invoices only.

### Service Access Card

- Service logos/names, status badges, access level, actions.
- Must use original service access grant/revoke/connect workflow.

### Empty State And Loading

- Empty state should be visual only; action button must call real workflow.
- Loading should preserve existing async states and error retry controls.

## Screen Map

### Přehled

Sections:

- Topbar.
- Hero: greeting, real vehicle count, STK/reminder counts, real hero vehicle photo if available.
- Overall status card.
- Four quick cards: STK/SME, Pojištění, Servis, Dokumenty.
- Vehicle preview cards.
- Right rail: Blížící se termíny, Poslední aktivita, Servisy a přístupy.

Functions:

- `loadHomeDashboard()`.
- Vehicles from `/api/v1/vehicles`.
- Reminders from `/api/v1/reminders`.
- Records from `/api/v1/vehicles/{id}/records`.

Blockers:

- None for core overview; design must avoid MDCR/VIN decode text in service quick card.

### Moje vozidla

Sections:

- Header with count and archive link.
- Filter pills.
- Sort and grid/list toggle.
- Vehicle grid.
- Add vehicle card.
- Summary strip.

Functions:

- `loadVehicles()`, `setVehicleView()`, `showVehicleDetail()`, `openAddVehicleModal()`, `openAddServiceRecordModal()`.

Blockers:

- Archive filter depends on whether baseline exposes archived vehicle data in `/api/v1/vehicles`; verify before activation.

### Detail Vozidla

Sections:

- Hero detail card.
- Six metric cards.
- Tab row.
- Basic info, identification, note.
- Right rail: timeline, nearest terms, quick actions.

Functions:

- `showVehicleDetail(vehicleId)`, `openVehicleDetailFloatingSection()`, `loadServiceRecordsModal()`, photo/upload/document/service access functions.

Blockers:

- If final design requires detail as full page instead of modal, need router adapter that still opens/closes original modal or mounts data through the same loaders.

### Servisní Historie

Target:

- Timeline list with filters, cost summary, frequent tasks, services summary.

Functions:

- Records currently exist per vehicle via `/api/v1/vehicles/{id}/records`.

Blocker:

- No direct top-level `serviceHistoryTab` in baseline. Needs adapter that aggregates records across vehicles.

### Připomínky

Target:

- Stats row, kanban board, calendar, automatic reminders, recommended actions.

Functions:

- `loadReminders()`, reminder create/edit/complete/delete, settings API.

Blockers:

- Calendar month view can be generated from existing reminders; no blocker if read-only calendar is acceptable.

### Dokumenty

Target:

- Hub with document cards, filters, uploads and per-vehicle grouping.

Functions:

- `loadDocumentsHub()`, document/download/preview/upload handlers.

Blockers:

- None for hub; exact upload entry points must be tied to original handlers.

### Servisy

Target:

- Service directory, contacts, access statuses, request/connect flows.

Functions:

- `loadServicesDirectory()`, service access and contact APIs.

Blockers:

- None for existing directory; new visual must not skip access confirmation.

### Faktury

Target:

- Invoice list/cards and details.

Functions:

- Current evidence appears in service record attachments/documents/license billing, not standalone tab.

Blocker:

- Product decision required: map to documents filtered by invoice, license billing, or implement only after existing API/handler is confirmed.

### Nastavení

Target:

- Restyled account settings, notifications, security, data export/delete.

Functions:

- `loadProfile()`, `setSettingsPanel()`, `/user/me`, `/user/security/*`.

Blockers:

- None, but high risk because it includes account deletion and security.

### Mobile Přehled / Moje Vozidla

Target:

- One-column cards, topbar compact, bottom nav, floating add button.

Functions:

- Same handlers as desktop.

Blockers:

- Need exact mapping for bottom nav labels: Přehled, Vozidla, Připomínky, Dokumenty, Menu.

## Architecture Recommendation

Recommended: **Variant A - new clean user shell with a bridge layer**.

Why:

- `web/index.html` is a large monolith with many existing workflows and inline handlers. Re-skinning it directly caused hybrid UI and detached controls.
- A new shell can own visual layout in `web/user-app-next.js` and `web/user-app-next.css`, but must use a bridge map to call original handlers and APIs.
- It can be staged behind a strict guard for `/web/app/u/*` and staging hostname only.
- It can leave original DOM/handlers mounted for notifications, profile menu, license modal, and complex modals.

Implementation guard:

- Do not activate in this phase.
- Later activation should be feature-flagged and reversible.
- New shell should preserve original hidden controls where needed and proxy clicks rather than re-implementing critical flows.
