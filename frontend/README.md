# React modul: Seznam vozidel

Samostatná Vite + React + TypeScript sada v `app/frontend/`. Build výstup: **`app/web/react/vehicle-list/`**.

Produkční zapojení je v **`app/web/index.html`** (Fáze 2): feature flag `window.__ENABLE_REACT_VEHICLE_LIST` (výchozí **`false`**). Dokud zůstane `false`, chování seznamu vozidel je stejné jako dřív (legacy `loadVehicles`).

## Vývoj (dev)

```bash
cd app/frontend
npm install
npm run dev
```

Otevřete URL s cestou `/web/react/vehicle-list/` (viz `base` v `vite.config.ts`), např. `http://127.0.0.1:5173/web/react/vehicle-list/`.

> V čistém Vite režimu chybí `window.apiCall` z monolitu – test dat probíhá až v hlavní aplikaci (viz níže).

## Produkční build

```bash
cd app/frontend
npm run build
```

- Typecheck: `tsc --noEmit`
- Vite: výstup do `app/web/react/vehicle-list/` (hashované názvy)
- **postbuild:** `node scripts/update-react-assets.js` — doplní `REACT_VEHICLE_LIST_BUILD_JS` / `REACT_VEHICLE_LIST_BUILD_CSS` a řádek „Aktuální build:“ v `app/web/index.html` podle skutečných souborů v `assets/` (viz **Fáze 5**)

## Fáze 5 – build synchronizace (hashe v index.html)

### Jak to funguje

1. `vite build` přepíše složku `app/web/react/vehicle-list/` (včetně `emptyOutDir`).
2. Skript `scripts/update-react-assets.js` přečte `app/web/react/vehicle-list/assets/`, očekává **přesně jeden** `index-*.js` a **jeden** `index-*.css`.
3. V `app/web/index.html` nahradí **jen**:
   - `var REACT_VEHICLE_LIST_BUILD_CSS = '...';`
   - `var REACT_VEHICLE_LIST_BUILD_JS = '...';`
   - volitelně řádek komentáře `Aktuální build: index-....js, index-....css` (pokud existuje).
4. Výchozí `window.__ENABLE_REACT_VEHICLE_LIST = false` a zbytek stránky se **nemění**. React se nespouští jinak než dřív.

### Co dělat při chybě

- Skript skončí s **exit 1** a `index.html` se **nepřepíše** (předchozí stav zůstane).
- Výpis začíná `[update-react-assets] Chyba:` — typicky: chybí složka `assets/`, 0 nebo 2+ kandidáti pro JS/CSS, chybí očekávané řádky `REACT_*` v šabloně.
- Opravte build / strukturu výstupu, případně doplňte v `index.html` dva `var REACT_*` řádky v podobě z existující šablony, a spusťte `npm run build` znovu.

### Jak ověřit

```bash
cd app/frontend
npm run build
```

- V konzoli: `[update-react-assets] OK: index-<hash>.js, index-<hash>.css` nebo zpráva, že `index.html` již odpovídá.
- `grep REACT_VEHICLE_LIST_BUILD app/web/index.html` — názvy = soubory v `app/web/react/vehicle-list/assets/`.
- Rychlá kontrola souborů: `ls app/web/react/vehicle-list/assets/index-*.{js,css}`.
- Playwright: `app/tests/e2e/react-vehicle-list-gated.spec.ts` načte názvy z `app/web/index.html` přes `readReactVehicleListAssetNames()` v `helpers.ts` (nemusíte ručně měnit hashe v specu).
- React se dál zapíná **jen** při `__ENABLE_REACT_VEHICLE_LIST === true` (konzole / test) — build tento flag nijak nenastavuje.

## Fáze 2 – feature flag a ruční test

**Výchozí stav:** `window.__ENABLE_REACT_VEHICLE_LIST === false` – žádný React bundle se nenačítá, `loadVehicles()` běží jako dřív.

**Zapnutí pro manuální test (konzole prohlížeče na načtené aplikaci):**

```js
window.__ENABLE_REACT_VEHICLE_LIST = true;
// pak znovu načtěte seznam vozidel, např. přepnutím záložky nebo:
if (typeof loadVehicles === 'function') loadVehicles();
```

**Ověření, že flag čte kód:**

```js
// pokud existuje (interní helper v index.html; jinak přes přímé čtení)
window.__ENABLE_REACT_VEHICLE_LIST;
```

Očekávané logy s prefixem `[ReactVehicleList]`: `enabled`, `root created` (při prvním vytvoření), `assets requested`; při chybě souboru `asset load failed`.

**Service účet:** experimentální větev se **nespouští**, pokud `isServiceWorkspaceRole()` je pravda (service shell zůstává nedotčený).

**Vypnutí (rollback testu):**

```js
window.__ENABLE_REACT_VEHICLE_LIST = false;
location.reload();
```

Případně obnovit stránku bez nastavení flagu (dokud není v kódu změněn default).

**Úplný rollback kódu:** v `index.html` odstranit/nekomentovat přidané bloky (flag, helpery, větev v `loadVehicles`) a volitelně smazat `app/web/react/vehicle-list/`.

## Manuální test checklist (Fáze 2)

| Krok | Očekávání |
|------|-----------|
| `__ENABLE_REACT_VEHICLE_LIST` je `false` (default) | Seznam vozidel = legacy, stejné chování jako dřív |
| Nastavit `true`, znovu `loadVehicles` / tab Vozidla | Vytvoří se obsah v `#react-vehicles-root` v `#vehiclesContainer`, načte se CSS+JS z `/web/react/vehicle-list/assets/` |
| Chybná cesta k bundlu (např. špatný `REACT_*` název) | Varovné logy, legacy se po resetu kontejneru načte |
| F5 na `/app/u/.../vehicles` s `true` | Stejné chování po přihlášení (shell router beze změny) |
| Uživatel (user) | React seznam lze otestovat |
| Servisní účet (service) | Větev React se nespouští, chování beze změny |

## Náhled buildu (volitelné)

```bash
npm run preview
```

## Struktura modulu

- `src/main.tsx` – mount pouze na `#react-vehicles-root`, error boundary
- `src/api/client.ts` – bridge na `window.apiCall`
- `src/VehicleListApp.tsx` – stavy loading / error / empty / seznam (bez editace)

## Fáze 3 – ověření React Vehicle List

**Datum auditu:** 2026-04-24

### Provedené příkazy a artefakty

- **Build (úspěch):**  
  `cd /opt/toozhub2/app/frontend` → `npm run build`  
  Výstup: `tsc --noEmit` + Vite, bez chyby; ~1 s.

- **Shoda názvů s `app/web/index.html`:**  
  Konstanty `REACT_VEHICLE_LIST_BUILD_CSS` a `REACT_VEHICLE_LIST_BUILD_JS` **odpovídají** souborům v `app/web/react/vehicle-list/assets/` po posledním buildu. **Změna konstant v této fázi nebyla potřeba.**

- **Aktuální assety (po posledním `npm run build`):**
  - CSS: `app/web/react/vehicle-list/assets/index-DJfPmz_O.css`
  - JS: `app/web/react/vehicle-list/assets/index-DHx26g2r.js` (+ `.map`)

- **Dostupnost statik přes FastAPI (HTTP):**  
  Na běžícím `uvicorn` vrací stezky pod `/web/react/vehicle-list/assets/…` stav **200** a očekávanou velikost, pokud je požadavek s hlavičkou **`x-forwarded-proto: https`** (v produkci za proxy; bez ní middleware může vracet **308** na `https://…`). Otestováno: `css` 869 B, `js` 146347 B (odpovídá buildu).

### Interaktivní prohlížeč (user / service / konzole)

Tento běh **neprovedl** plné přihlášení a manuální klikací scénáře v prohlížeči (nejsou zde k dispozici produkční přihlašovací údaje / Playwright s uloženou session pro tento run). Doplňte ve vašem prostředí:

| Scénář | Stav v tomto auditu | Poznámka |
|--------|----------------------|----------|
| User: legacy při `false` | Nespouštěno v prohlížeči | Očekávání: beze změny; default je `false` v `index.html` |
| User: `true` + `loadVehicles()` | Nespouštěno v prohlížeči | Očekávání: `#react-vehicles-root`, link+script, React UI, `apiCall` dle Fáze 1 |
| Service účet | Nespouštěno v prohlížeči | Kód: větev React se **nevolí**, když `isServiceWorkspaceRole()` — `service-shell.js` nebyl měněn (ověřeno mimo tento běh git diff) |
| Rollback `false` + `location.reload()` | Logicky z kódu | Při každém načtení stránky se znovu provede `window.__ENABLE_REACT_VEHICLE_LIST = false` → manuální `true` z konzole se **po F5 ztratí** |
| F5 + `/app/u/.../vehicles` + flag v konzoli | Logicky z kódu | Po reloadu opět `false` → běží legacy, pokud se flag znovu nenastaví |

**Chyby v konzoli v tomto auditu:** žádné (nebyl spuštěn prohlížeč s aplikací v tomto kroku).

### Statická / kódová kontrola (bez refaktoru)

- **F5 a flag:** V šabloně zůstává výchozí při každém full load: `false` v JS — konzolová úprava `window.__ENABLE_REACT_VEHICLE_LIST = true` se po **reloadu stránky** nezachová.
- **Service režim:** V `loadVehicles` je větev React podmíněna `!isServiceWorkspaceRole()`.

### Finální verdikt (Fáze 3)

- **Build a soubory:** OK; hashe odpovídají; statiky servovatelné při správných hlavičkách.
- **Prohlížeč a účty:** **Neuzavřeno** v tomto prostředí – doporučena krátká ruční místní QA dle tabulky výše.
- **Bezpečnost vydání:** Při default `false` beze zapnutí flagu v konzoli se produkční chování nemění; dokončení Fáze 3 vyžaduje alespoň jedno ověření v prohlížeči s reálným user účtem.

## E2E (Playwright) – `react-vehicle-list-gated.spec.ts`

Automatizované ověření (Fáze 3) je v `app/tests/e2e/react-vehicle-list-gated.spec.ts`, project `react-vehicle-list-gated` (závisí na `setup-auth`).

```bash
cd /opt/toozhub2/app/tests/e2e
npx playwright test react-vehicle-list-gated.spec.ts --project=react-vehicle-list-gated
```

**Předpoklady:** běžící backend (např. `BASE_URL=http://127.0.0.1:8000`, nebo výchozí z `playwright.config.ts` + `webServer`), stejné jako ostatní E2E.

**ENV (volitelné):** `E2E_SERVICE_EMAIL` + `E2E_SERVICE_PASSWORD` pro test servisního režimu (bez nich se servisní test přeskočí). User scénář používá sdílený auth z `auth.setup` (`E2E_EMAIL` / `E2E_PASSWORD` v `helpers`). Dokumentované aliasy `E2E_USER_EMAIL` / `E2E_USER_PASSWORD` jsou v hlavičce specu pro budoucí napojení — zatím je nečte `helpers.ts`.
