# Web oznámení – 5. 11. 2026

## Rozsah a zdroj

Izolovaný worktree `/Users/toozservis/Developer/evidence-push-admin-delivery-20261105/web`, branch `codex/web-notice-delivery-20261105`, baseline `b55a5fe2822fdf9dd1e955748d55f0eac275f8da`.

Používá společný kontrakt iOS → web. API a fixture vlastní samostatný API agent. Tento balíček nemění API, databázi produkce ani iOS. Žádný deploy, App Store upload nebo odeslání skutečnému příjemci není součástí tohoto výsledku.

## Chování

- Adresné zprávy administrace i systémová oznámení jsou nahoře při otevření a návratu do zákaznického nebo servisního účtu. Banner má dynamickou rezervu podle skutečné výšky, nepřekrývá navigaci a při opakovaném načtení stejného stavu neodebírá focus.
- Hlavní navigace i profil mají Oznámení s počtem položek; historie obsahuje také upozornění k vozidlům. Soukromá konverzace Zprávy administrace zůstává oddělená od servisních zpráv.
- Skutečně viditelný detail zapisuje přečtení. Běžná výzva se vyřídí až Rozumím, povinná až Potvrdit přečtení. Zavření detailu ani nové otevření účtu je samo nepotvrdí.
- Odpověď se ukládá do existující soukromé konverzace. Teprve úspěšné uložení může vyřídit běžnou výzvu; povinné potvrzení zůstává samostatné.
- Ztracená odpověď potvrzovací operace používá při opakování stejný UUID. Session storage obsahuje jen metadata této operace, nikoli soukromý text.
- Expirovaná/ukončená oznámení se zobrazují jako archiv bez potvrzovacího tlačítka. Server zachovává jejich snapshot a historii.
- Session guards chrání načítání, zobrazení i změny při odhlášení nebo změně účtu; tělo se vykresluje jako text, nikoli HTML.
- Web Push používá nový session-bound endpoint zařízení. Instalační tajemství je náhodný údaj uložený v originově odděleném IndexedDB. Povolení je uživatelský krok. Systémový náhled neobsahuje soukromý text; worker nic nepřečte ani nepotvrdí kliknutím. Přesný detail se načte až pod přihlášením.

## Ověření

**PASS: 18 živých kontrol (14 hlavních + 4 rozšířené)**, skutečný Chrome a celý `/web/customer.html` proti reálným API routerům na `http://127.0.0.1:18920`, jen syntetická skupina `web`.

Přihlášení bylo připraveno syntetickým QA JWT; zadání skutečného hesla/MFA nebylo testováno. Jde o lokální HTML a skutečné API zápisy, nikoli o nahrazení notification odpovědí mocky. Jedna cílená chyba transportu simuluje ztracenou odpověď až poté, co skutečný server příkaz přijal.

Hlavní běh:

```
NOTIFICATION_QA_OUTPUT=/Users/toozservis/Developer/evidence-push-admin-delivery-20261105/web-evidence/run8 node tests/web/notification-center-live-20261105.cjs
NOTIFICATION_QA_OUTPUT=/Users/toozservis/Developer/evidence-push-admin-delivery-20261105/web-evidence/history node tests/web/notification-history-live-20261105.cjs
node tests/web/notification-worker-20261105.cjs
```

Výsledky a snímky:

- `/Users/toozservis/Developer/evidence-push-admin-delivery-20261105/web-evidence/run8/result.json`
- `run8/01-floating-start.png` – banner a navigace bez překrytí.
- `run8/02-foreground-announcement.png` – nové oznámení po návratu.
- `run8/03-explicit-ack.png` – skutečně potvrzený stav.
- `run8/04-service-large-text-last-buttons.png` – servis, šířka 390 px, zvětšený text, dostupná spodní tlačítka.
- `run8/05-archived-snapshot.png` – archivované systémové oznámení.
- `run8/05-push-unavailable-honest.png` – pravdivý stav chybějícího poskytovatele.
- `/Users/toozservis/Developer/evidence-push-admin-delivery-20261105/web-evidence/worker-result.txt`

Vizuálně zkontrolovány startup banner, servisní detail, archiv a přesný detail upozornění. Rozšířený běh `/Users/toozservis/Developer/evidence-push-admin-delivery-20261105/web-evidence/history/result.json` ověřil skutečné stránkování `before_id` bez duplicit, upozornění k autorizovanému vozidlu včetně read a přesného navigačního requestu, otevření přesného notification ID z deep-linku a nepřihlášený deep-link bez načítání soukromého obsahu. Snímky jsou v podadresáři `history`. Worker VM test zvlášť ověřil generický systémový obsah, badge, bezpečný původ, přesné ID, zachování rozepsané práce a absenci read/ack při kliknutí.

## Limity

- Skutečná cesta poskytovatel → operační systém → zařízení se netestovala. Fixture má dispatch vypnutý a Web Push poskytovatele nenakonfigurovaného. Žádné povolení ani klíče produkce se neměnily.
- Pro živé Web Push je potřeba povolení uživatele, bezpečný původ, VAPID a konfigurované nové úložiště zařízení/dispatch. Safari na iPhonu/iPadu vyžaduje web přidaný na plochu; podporu a doručení je nutno ověřit na skutečném zařízení.
- Zvětšení písma bylo provedeno CSS v Chromu; nejde o fyzický iPhone ani OS Dynamic Type test.
- Navigační cíl vozidla neznamená automaticky ověřený celý detail vozidla; fixture tento legacy detail neposkytuje.
- QA fixture neposkytuje celý provozní health dashboard, takže screenshot může zobrazovat Server offline i při fungujících notification API. Tento štítek není výsledkem testu produkční dostupnosti.
- Cross-platform dokončení vyhodnocuje root až s výsledky iOS a Androidu.

Dokumentace poskytovatele: https://webkit.org/blog/13878/web-push-for-web-apps-on-ios-and-ipados/ ; https://developer.apple.com/documentation/usernotifications/sending-web-push-notifications-in-web-apps-and-browsers
