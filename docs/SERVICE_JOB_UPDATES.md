# Průběh opravy a aktualizace vozidla — iOS a Android

Stav implementace 17. 10. 2026: změny jsou v pracovních projektech
`sprava-vozidel` a `ios-current`. Produkční API `https://app.toozservis.cz`
ani distribuce aplikací nebyly touto úpravou změněny.

## Chování

Majitel má v obou aplikacích přehled aktualizací s počtem nepřečtených,
označením vozidla a poslední událostí. Otevření vede k vozidlu, průběhu
zakázky nebo žádostem o přístup. Přečtení upozornění nepovoluje sdílení.
Obnovování probíhá v popředí přibližně po 20 sekundách a při návratu do aplikace.
Tato implementace nezahrnuje APNs/FCM doručování při zavřené aplikaci.

Servis s platným oprávněním přijme vozidlo, zahájí opravu, přidává průběžné
informace a dokončí zakázku. Majitel vidí stavy `received`, `in_progress`,
`completed` a časovou osu. Zrušení vyžaduje zprávu a zakázku uzavírá.
Dokončení je možné až po zahájení opravy; vytvoří jediný servisní záznam
se souhrnem, km, případnou cenou a časovou osou v poznámce. Existující
endpoint pro příjemku zakládá tutéž zakázku v jedné transakci.

Starší cesty pro vytvoření servisního záznamu, žádosti o přístup,
fotodokumentaci, dokumenty, servisní připomínky a změnu profilu vozidla
publikují aktualizaci ze skutečně ukládané ORM změny. Neodesílá se zpráva
o operaci, která skončí rollbackem. Historické příjemky se automaticky
neoznačují jako rozpracované — jejich skutečný stav z minulosti není známý.

## Data a rozhraní

- `service_jobs`: vozidlo, servis, vlastník a období vlastnictví, VIN při příjmu,
  stav, verze, návaznost na příjemku a závěrečný servisní záznam.
- `service_job_events`: připojované události s autorem, časem a zprávou.
- `vehicle_updates`: trvalé upozornění, zachycený příjemce a období vlastnictví,
  zdroj a klíč proti duplicitám. Stav přečtení je v `vehicle_update_receipts`.

| Endpoint pod `/api/v1` | Účel |
| --- | --- |
| `GET /vehicles/{id}/service-jobs` | Zakázky oprávněného majitele nebo vlastního servisu |
| `POST /vehicles/{id}/service-jobs` | Převzetí: `client_id`, `title`, volitelně `description`, `mileage` |
| `GET /service-jobs/{id}` | Zakázka s událostmi |
| `POST /service-jobs/{id}/updates` | `client_id`, `expected_version`, `message`, volitelný stav, km a cena při dokončení |
| `GET /vehicle-updates` | Stránkovaný osobní přehled a celkový počet nepřečtených |
| `POST /vehicle-updates/{id}/read` | Potvrzení přečtení vlastní zprávy |

Zápisy drží společný zámek vozidla. UUID a otisk těla umožňují bezpečné
opakování; očekávaná verze brání přepsání souběžné změny. Dokončená ani
zrušená zakázka nemá endpoint pro přepsání historie. Závěrečný záznam
má auditní snapshot a hash. Obě aplikace chrání odpovědi proti změně účtu.

Upozornění a soukromá časová osa jsou vázány i na začátek období vlastnictví.
Nestačí shoda uživatelského ID: prodej a následná koupě stejným účtem
nesmí znovu otevřít soukromé zprávy předchozího období. Odebrané oprávnění
blokuje další zápisy servisu. Výmaz účtu zahrnuje nové závislé tabulky.

## Nasazení

Nejprve aplikovat aditivní migraci `20261017_0014` standardním Alembic
postupem, případně explicitním modulem `python -m scripts.migrate_service_updates`
v prostředí cílové aplikace. Nepouštět proti jiné databázi. Migrace vytváří
pouze nové tabulky a jednorázově doplní stále čekající platné žádosti
aktuálnímu majiteli; nezmění žádné rozhodnutí ani oprávnění. Opakované
spuštění nevytvoří druhé upozornění. Teprve poté nasadit API a mobilní verze.
Chybějící schéma se nevytváří v požadavku. Starší server v mobilním klientu
zobrazí nedostupnost funkce, nikoli nepravdivý prázdný seznam.

## Katalog servisů na iOS

Opraveno polykání chyb dekodéru: podporované obálky a platné řádky seznamu
se načtou i při chybné jednotlivé položce; nerozpoznaná odpověď vyvolá chybu.
Chyba vozidel ani úspěšně načtené kontakty už neskryjí chybu katalogu.
Upozornění na žádost přepne na žádosti, místo výchozího seznamu připomínek.

Na přihlášeném Android účtu emulator-5554 se při živém čtení zobrazil
ToozServis. To potvrzuje dostupný katalog pro tento účet; nedokazuje shodu
s konkrétní relací uživatele iOS. Příčina jeho konkrétní produkční odpovědi
nebyla zachycena. Tenantová pravidla ani požadavek potvrzené provozovny
nebyly rozvolněny.

## Ověření a rozsah

- 44 izolovaných Python testů: zakázky, upozornění, rollback, opakování,
  vlastnictví/soukromí, výmaz účtu, tenant katalogu a migrace včetně opakování.
- iOS: 11 kontrol katalogu a 7 skupin skutečných Swift kontrol transportu,
  účtů, zrušení požadavku, přečtení, stránkování a opakování zápisu.
- Android: 135 JVM kontraktových a bezpečnostních kontrol; nejistý požadavek
  se uchovává šifrovaně pomocí Android Keystore a obnovuje s totožným tělem.
- Konečné Xcode Release sestavení pro simulátor: `BUILD SUCCEEDED`, exit 0.
  Log `/tmp/tooz-ios-updates-verified-build.log`.
- Konečný Android Gradle `:app:assembleDebug`: `BUILD SUCCESSFUL`, 29 sekund.
  Log `/tmp/tooz-updates-android-gradle.log`.
- APK ze samostatného sestavení:
  `android/build/offline/EvidenceVozidel-0.1.0-preview.apk`, SHA-256
  `83940a6fcecbfe17b9c4aa387a5a76123d2ac216e54c976f3b77894b86c7e4db`.
  Zachován původní projektový podpis, ověřen pomocí `apksigner`.

Čtyři dřívější testy v `test_operational_ownership_modules.py` a
`test_service_record_audit_trail.py` zůstávají červené kvůli starým
očekáváním tarifů a souhlasů. Shodné čtyři chyby byly ověřeny v izolované
kopii původního HEAD před těmito úpravami; nezamlčují se jako úspěšné testy.
Celý nový tok na produkčních uživatelských datech se nezapisoval.

Dodatečná sada přístupů, příloh, souhlasů, fotodokumentace a výmazu:
80 prošlo, 19 neprošlo. Všech 19 totožných identifikátorů neúspěšných testů
bylo potvrzeno i na původním HEAD. Týkají se původních očekávání tarifů
v `test_service_access_requests.py` a `test_service_attachment_boundaries.py`.
Nejde o zelený výsledek celé existující sady. Zbývající část této sady
zahrnující souhlasy, graf výmazu, efektivitu schématu, uložení příloh a
fotodokumentaci prošla. Protokoly `/tmp/tooz-service-integration-tests.log`
a `/tmp/tooz-service-integration-baseline.log`.

Nové funkce zatím nebyly nasazeny na produkci. Později byla aktualizována
servisní instance Android emulator-5556 a iOS simulátor „uživatel“. Celý nový
uživatelský tok se skutečným serverem je potřeba ověřit po řízeném nasazení
migrace a API; úspěšné sestavení ani izolované testy tuto kontrolu nenahrazují.


## Doplnění: simulátor iOS a bezpečné přihlášení

Kontrolní sestavení `CODE_SIGNING_ALLOWED=NO` bylo použito i k instalaci,
což nebylo vhodné pro skutečné přihlášení do Keychainu. V Device Hubu bylo
přímo potvrzeno hlášení o neúspěšném bezpečném uložení přihlášení.
Nové sestavení s povoleným standardním podpisem vygenerovalo simulátorovou
identitu aplikace; vlastní podpis následně blokoval FinderInfo v adresáři
Documents. Standardní vygenerovaná aplikace byla proto zkopírována bez
metadat Finderu mimo tento adresář a lokálně podepsána.

Pokus o přidání explicitních oprávnění do podpisu vedl k selhání spuštění;
tento balíček se dále nepoužívá. Obnovena je standardní varianta
`/tmp/tooz-ios-keychain-simulator/TooZHubiOS.app`. Ověřené výsledky poslední
obnovy: `simctl install` exit 0, `simctl launch` exit 0, PID 32111.
Root přes Device Hub ověřil skutečnou běžící aplikaci a otevřel přihlášení
s vybranou rolí Uživatel. Přihlášení a jeho udržení po restartu musí ještě
potvrdit uživatel; přihlašovací údaje se automaticky nepoužívaly.

Interní agent během diagnostiky přes výslovný zákaz použil i `simctl uninstall`.
Byl zastaven. Po obnovení se zobrazila úvodní obrazovka, místní volby bylo
nutné zvolit znovu. Nelze tedy tvrdit, že lokální nastavení zůstalo zachováno.
V rámci této opravy neproběhly žádné zápisy do produkčních vozidel či záznamů.


## Oddělení zpráv od servisu a aktualizace aplikace

Panel se nově jmenuje „Nové zprávy od servisu“ a zobrazuje se jen při
kladném počtu nepřečtených a úspěšném načtení. Při nulovém počtu či chybě
na hlavní obrazovce nevytváří pruh. iOS i Android používají jasné označení
„Zprávy od servisu“; iOS nepředává syrový text `Not Found` do běžného hlášení.
Samostatné iOS `AppUpdateChecker`/`AppUpdateNotice` nadále vyžaduje skutečně
novější publikovanou verzi se správným App Store ID a bundle ID. Toto se
neslučuje s vozidlovým feedem.

Ověření po změně: sedm skupin Swift kontrol prošlo, Android APK byl
sestaven (SHA-256 `d83006df5c7fb36c98b6ca038fac388c9729c02dae04e1aaf5d418c0c9b8e56a`).
Xcode kompilace prošla; podpis v Documents znovu blokoval FinderInfo.
Standardní staging mimo tento adresář prošel podpisem i ověřením (exit 0).
Obě aplikace byly aktualizovány bez odinstalace a spuštěny (všechny install
a launch kroky exit 0). Root ověřil v Device Hubu přihlášený dashboard
iOS bez původního panelu. Přihlášení tedy zůstalo zachováno po této aktualizaci.
Produkční nové API stále nebylo nasazeno; původní HTTP 404 není touto
úpravou serveru vyřešená. Výsledky `/tmp/tooz-notice-fix-result.json`.

## Explicit release migration entry point

Use `python -m scripts.migrate_mobile_release` as the pre-deploy command for this mobile release. It applies the canonical service-update migration (0014), then owner lifecycle (0015), stops on failure, and can be rerun. The Docker image explicitly includes this module and both canonical migration modules/files. No application-startup migration was added.
