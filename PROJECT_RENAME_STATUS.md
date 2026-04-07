# Stav přejmenování na „Správa vozidel“

Oficiální název produktu je **Správa vozidel**. Tento dokument shrnuje, co už bylo sjednoceno a co zůstává záměrně legacy z kompatibility.

## Přejmenováno okamžitě (uživatelsky / provozně viditelné)

- **Centrální branding:** `src/core/branding.py` – `APP_DISPLAY_NAME`, `APP_API_DISPLAY_NAME`, tokeny pro HTTP `Server` a User-Agent (`APP_SERVER_PRODUCT_TOKEN`), web push typ zprávy, název file-share miniaplikace.
- **Backend:** OpenAPI titulek (přes bootstrap), `/health` pole `project`, middleware hlavička `Server`, push titulky připomínek, poznámky u autopilot záznamů, docstringy modulů, file-share HTML/API titulky, geolokační User-Agent řetězce.
- **Web:** `sw.js` – nový typ `postMessage` `SPRAVA_VOZIDEL_NOTIFICATION_CLICK` (stránka akceptuje i starý typ pro přechodnou kompatibilitu se starým service workerem).
- **Desktop (legacy Qt):** `src/app/main.py` – titulek okna a záhlaví.
- **Tray:** `tray/tray_app.py`, `tray/tray_manager.py`, `tray/README.md`, `start_tray.bat`, `start_tray_hidden.vbs` – zobrazené názvy a názvy zástupců (`SpravaVozidel_tray.lnk`).
- **Skripty / E2E metadata:** výpisy v `webnode_auto_upload.py`, `webnode_learn_steps.py`, `license_clickthrough.py`, `e2e_browser_agent.py`, `kontrolatachometru_cli.py`, `tests/e2e/package.json`.
- **Dokumentace:** hromadná úprava `.md` souborů (kromě řádků s živými URL na `github.com/.../TOOZHUB2`, které odpovídají skutečnému repozitáři).
- **Verze:** `VERSION.py` – `__version_name__` ve tvaru `Správa vozidel <semver>`.

## Zůstává technicky beze změny (záměr)

- **GitHub URL a slug repozitáře** `toozservis-tech/TOOZHUB2` v dokumentaci a výchozí hodnotě `GITHUB_REPOSITORY` – dokud se repozitář na GitHubu fyzicky nepřejmenuje.
- **Proměnné prostředí** `TOOZHUB_API_URL`, `TOOZHUB_ADMIN_TENANT_ID`, `TOOZHUB_ADMIN_FORCE_PREMIUM` – nasazení a skripty je mohou mít nastavené; přejmenování je samostatná migrační akce.
- **iOS / Xcode:** cílový název `TooZHubiOS`, složka `Sources/TooZHub/`, bundle identifier – vyžaduje změnu v Apple Developer / projektu.
- **Interní Python cesty** `src.modules.vehicle_hub` atd. – nejsou uživatelsky viditelné; refaktor až v samostatné větvi.
- **Service worker cache:** uživatelé se starým SW mohou dočasně posílat `TOOZHUB_NOTIFICATION_CLICK` – frontend typ stále přijímá.

## Proč to zatím zůstává

- Zabránit rozbití produkční konfigurace (.env), CI a existujících záložních příkazů s přesným názvem repozitáře.
- Přejmenování iOS bundle ID a složek vyžaduje koordinaci s App Store a vývojářským účtem.
- Krátká překryvná kompatibilita web push zpráv snižuje riziko „mrtvých“ kliků po nasazení.

## Další krok

Podrobný seznam technických identifikátorů, priorit a rizik: **`TECHNICAL_RENAME_BACKLOG.md`**.
