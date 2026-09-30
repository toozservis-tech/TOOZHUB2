# SprávaVozidel — vydání v App Storu

Poslední ověření: 1. 10. 2026. Směr potvrzený uživatelem: iOS předplatné přes Apple In-App Purchase; Comgate pro web. Režim externích EU plateb v iOS není vybraný.

## Skutečný stav

- Členství Apple Developer je od večerní kontroly 30. 9. **aktivní**, tým `5DATUX4X32`, Individual, obnova 1. 10. 2027. Neopakovat platbu. Vstup do App Store Connect nyní vyžaduje první přijetí Terms of Service; modal zůstal připravený pro vlastníka. Vlastník spí a výslovně odložil potřebná osobní potvrzení na další den, podmínky proto nebyly přijaty. Aplikace a produkty dosud nebyly založeny.
- Produkční server běží na placeném Renderu (7 USD/měsíc). Comgate test Basic 98,99 Kč byl potvrzen a nezměnil původní licenci. Ostré Comgate účtování dosud není zapnuté.
- Nový klient používá StoreKit 2, zobrazuje ceny dodané App Storem, obsahuje obnovení nákupů a nativní správu předplatného. Původní Comgate objednávka z iOS byla odstraněna; webové propojení a data jsou zachována.
- Server má samostatný ověřovač Apple, vazbu nákupu na náhodný `appAccountToken`, aktuální ověření přes App Store Server API a zpracování oznámení V2. Nevěří samotnému potvrzení z telefonu. Apple integrace zůstává vypnutá, dokud nejsou dokončené skutečné údaje a ověření.
- Testy s izolovanou databází ověřují bezpečnost a stavové přechody. Nejsou důkazem skutečného sandbox nákupu přes Apple. Ten a TestFlight/App Review zůstávají nutné.

## Nastavení, které ještě vyžaduje účet Apple

1. Vlastník dokončí připravené přijetí App Store Connect Terms of Service. Vývojářské členství už je aktivní a zaplacené. Registrace Individual znamená osobní jméno prodejce; nezakládat ani neplatit druhé členství.
2. Založit aplikaci **SprávaVozidel**, iOS, bundle ID `cz.toozservis.spravavozidel.ios`. Uložit její skutečné číselné Apple ID. Zajistit podepisování pro App Store.
3. Dokončit Paid Apps Agreement, bankovní a daňové údaje a ověření obchodníka pro EU. Žádné z těchto potvrzení nebylo dosud provedeno.
4. Založit JEDNU skupinu automaticky obnovovaných předplatných. Premium má vyšší úroveň než Basic. Měsíční a roční varianta stejného plánu má stejnou úroveň. Family Sharing není implementován; nezapínat.
5. Založit následující produkty (identifikátory jsou smlouvou mezi klientem a serverem):

| Produkt | Úroveň | Období |
| --- | --- | --- |
| `cz.toozservis.spravavozidel.basic.monthly` | Basic | 1 měsíc |
| `cz.toozservis.spravavozidel.basic.yearly` | Basic | 1 rok |
| `cz.toozservis.spravavozidel.premium.monthly` | Premium | 1 měsíc |
| `cz.toozservis.spravavozidel.premium.yearly` | Premium | 1 rok |

Ceny musí vlastník schválit a nastavit v App Store Connect. Klient nepřebírá cenu webového Comgate ceníku. Neaktivovat neimplementované nabídky ani sdílení v rodině. Popisy plánů musí odpovídat skutečně vynuceným funkcím a limitům.

6. V App Store Connect → Users and Access → Integrations → In-App Purchase vytvořit serverový klíč. Privátní klíč patří pouze do tajných proměnných serveru, nikdy do aplikace, Git historie, chatu nebo webového formuláře mimo schválený server.
7. Konfigurace serveru: `APPLE_IAP_ENABLED=1`, `APPLE_IAP_BUNDLE_ID`, `APPLE_IAP_APP_ID`, `APPLE_IAP_SUBSCRIPTION_GROUP_ID`, `APPLE_IAP_KEY_ID`, `APPLE_IAP_ISSUER_ID`, `APPLE_IAP_PRIVATE_KEY`, `APPLE_IAP_ENVIRONMENT` (`Production` nebo `Sandbox`). Každé nasazení používá jediný ověřovaný režim; žádný automatický přechod z produkce na sandbox. Sandbox testovat na oddělené databázi/testovacích účtech a samostatném backendu, ne na původních účtech. Připravit samostatné sestavení/schéma pro sandbox se správným bundle ID.
8. Před zapnutím provést aditivní migraci `python -m scripts.migrate_apple_billing`. Nemění staré licence, uživatele ani platby. Konfiguraci zapnout až po kontrole migration a testovacího prostředí.
9. Nastavit App Store Server Notifications **V2** na `/api/v1/license/apple/notifications` příslušného HTTPS serveru. Ověřit Apple test notification, skutečný sandbox nákup, obnovení po nové instalaci, renewal, downgrade/upgrade, grace, refund, refund reversal, výpadek sítě, jiný účet aplikace a zrušení obnovování. Pravidelná kontrola vedle oznámení je implementovaná níže; skutečné Apple testy zůstávají nutné. Zajistit variantu backendu pro App Review sandbox; do té doby nelze poslat aplikaci ke schválení.
10. iOS transakci dokončuje až po potvrzeném uložení na serveru. Při chybě zůstane obnovitelná. Staré webhooky vždy znovu načtou aktuální stav od Applu. Potvrzené období vyprší i při opožděném webhooku; uživatelská data se při vypršení nemažou.

## Zbývající závěrečné kontroly celého produktu

- Odstranění účtu je implementované v `ACCOUNT_ERASURE.md`: dobrovolný export, povinné heslo a ruční potvrzení, vlastnictví místo plošného smazání organizace, trvalé odstranění souborů s potvrzením stavu. Izolované testy a nativní formulář prošly bez mazání skutečných účtů. Zbývá právní/produkční ověření uchování účetních podkladů, kopií a záloh.
- Inventura zdrojového kódu je v `docs/APP_PRIVACY_INVENTORY.md`. Nativní manifest nyní zahrnuje 14 používaných kategorií údajů, důvod UserDefaults CA92.1 a deklaraci bez reklamního sledování. Před zveřejněním ještě ověřit konkrétní serverové proměnné, smlouvy, retence a vyplnit odpovědi v App Store Connect. Neslibovat nulový sběr osobních údajů. Ověření nových účtů je popsáno v doplnění níže; rozpracované úpravy fotografií do této etapy nepatří.
- Ověřit aktuální obchodní/platební podmínky, odstoupení u průběžné digitální služby, reklamace, vrácení peněz, DPA a uchování dokladů. Přechod na Apple musí být zohledněn; staré Comgate souhlasy nelze používat pro Apple nákup.
- EET2: dle ověřeného webu MF dne 30. 9. 2026 je účinnost uvedena od 1. 1. 2027. Prověřit přesné znění účinného zákona, kontaktní tržby servisů a technickou specifikaci. Samotné online SaaS předplatné není důkazem povinnosti/absence povinnosti pro všechny platby servisů. Integrace EET dosud neexistuje; nevydávat fiktivní potvrzení o evidenci.
- Fyzický iPhone: fotoaparát a skutečně uložený snímek, přílohy, export, obnova hesla/deep links. Simulátor nenahrazuje ověření fotoaparátu.
- Role uživatel/servis/admin, sdílení a izolace dat, přístupnost, čitelnost, iPad, výpadky, obnovení záloh a monitorování.
- Verze a build, distribuční archiv, metadata, lokalizované snímky, věková klasifikace, veřejná podpora/privacy URL, bezpečný účet pro App Review a popis všech rolí. Neodesílat nehotové nebo skryté funkce.

## Podklady

- https://developer.apple.com/app-store/review/guidelines/
- https://developer.apple.com/programs/enroll/
- https://developer.apple.com/support/offering-account-deletion-in-your-app/
- https://developer.apple.com/app-store/subscriptions/
- https://github.com/apple/app-store-server-library-python
- https://www.apple.com/certificateauthority/
- https://eet.gov.cz/
- https://coi.gov.cz/faq/5-odstoupeni-od-smlouvy-do-14-dnu-u-sluzeb/

## Ověření této etapy

- 144 testů přesné serverové verze prošlo: 101 Apple/Comgate a 43 kontrol viditelnosti plateb, webového přístupu a oprávnění administrátorů v izolované databázi. Apple pozitivní stavy jsou simulované odpovědi, podvržený JWS ověřuje skutečný oficiální verifier.
- iOS DevelopmentServer pro simulátor i Release pro skutečný iPhone: BUILD SUCCEEDED, kontrola bez podpisu. Nejde o distribuční archiv ani úspěšný App Review.

## Doplnění večer 30. 9. — spolehlivost relace a kontrola App Storu

- iOS commit `09674a1` opravuje tiché selhání ukládání tokenu v nepodepsaném simulátoru. Nový skript sestavuje s podpisem mimo synchronizované Dokumenty. Samostatný test skutečné Keychain třídy prošel pro zápis, aktualizaci, načtení po restartu i oznámení chyby při nepovoleném zápisu.
- Čtyři izolované testy potvrzení smazání a tři nativní UI testy prošly. Admin zůstává přihlášený po třech ukončeních/spuštěních, původní ručně spravovaná licence se nemění a profil má bezpečný potvrzovací formulář. Primární i zrcadlový Xcode projekt se sestavil podepsaný pro simulátor; Release kompilace prošla bez distribučního podpisu.
- Samostatný serverový job `apple.subscription.reconcile` porovnává uložené nákupy se současným ověřeným stavem u Applu. Nevyvolává platby, neposílá zprávy a nevolá Comgate. Výjimka vrátí změny licence zpět; další pokus má odstup 5 minut až 6 hodin. Jednotlivé nákupy mají trvalý záznam kontroly a desetiminutový zámek proti souběhu, který se po havárii uvolní časem.
- Po zapnutí `APPLE_IAP_ENABLED=1` se kontrola spouští po dávkách každých 300 sekund. `APPLE_RECONCILIATION_INTERVAL_SEC` má rozsah 60–3600 s; `ENABLE_APPLE_RECONCILIATION_WORKER=0` vypne pravidelný běh. Aktivní/obnovované nákupy se ověřují nejčastěji po 15 minutách, ostatní jednou denně. Nové i dříve zrušené nákupy získají další kontrolu bez zablokování jednou chybnou položkou. Oddělení Production/Sandbox platí i zde.
- Webová i iOS administrace mají samostatnou srozumitelně popsanou kontrolu, údaj o opakovaných chybách a posledním ověření. Bez konfigurace a všech tří Apple tabulek se zobrazuje čekání na nastavení a akce nejsou dostupné. Job lze po dokončení nastavení pozastavit/obnovit nebo jednorázově ověřit aktuálně naplánované položky.
- Podepsaná Apple oznámení mají přesnou výjimku z režimu údržby; nevztahuje se na nákupní API ani libovolné podadresáře. Ověřování podpisu zůstává povinné.
- Migraci `scripts.migrate_apple_billing` spustit znovu i na prostředí, kde už existují první dvě Apple tabulky. Přidává pouze `apple_reconciliation_state`; nemění původní licence, účty ani Comgate. Bez dokončených Apple údajů integraci zatím nezapínat.
- Přesná připravená serverová verze: 120 Apple/Comgate testů a 50 testů oprávnění, řízení kontrol a viditelnosti plateb prošlo v izolované databázi. Navíc prošlo 6 kontrol webových ovládacích prvků a nativní testy iOS administrátorských akcí. Pozitivní Apple odpovědi jsou stále simulované; tyto výsledky nenahrazují sandbox nákup.

## Doplnění 30. 9. — soukromí a hranice účtů

- Oprava `backfill_vehicle_owner_assignment` zabrání přepsání aktuálního vlastníka zastaralým e-mailem při pouhém ověřování přístupu. Automatické doplnění se použije jen bez předchozí historie a ve stejné organizaci; zrušená vazba se sama neobnoví. Smíšený účet se starými i migrovanými vozidly nyní zahrne obě skupiny bez přidání cizích vozidel.
- Potvrzení odstranění účtu má samostatný limit ověřování hesla (5 pokusů / 15 minut na účet, navíc limit IP). Chyba vrátí transakci zpět a klient nedostane databázové podrobnosti. Nejde zatím o dokončení celého serverového odstranění.
- Bezpečnostní IP/GPS obohacování je nyní výslovně volitelné a ve výchozím nastavení vypnuté. Audit přihlášení zůstává; nativní vyhledávání podle města není touto změnou odstraněné. Podrobnosti a kategorie manifestu jsou v `APP_PRIVACY_INVENTORY.md`.
- **90 testů přesné připravené serverové verze prošlo** v oddělené databázi: účty, webová oprávnění, administrace, geolokace a vlastnictví vozidel. Starší integrační scénář `test_service_access_requests.py` očekával externí testovací server na 127.0.0.1:8000 a bez něj neproběhl; není započítaný mezi úspěchy. Není důvod ho spouštět proti skutečným účtům.
- Poslední předchozí nasazení `8ff8fc7` bylo potvrzeno jako Live; veřejný health ukazuje SprávaVozidel 2.2.0 a datum sestavení 2026-09-30. Integrace Apple stále není aktivovaná.

## Doplnění 30. 9. — ověření registrací

- Nový zákazník i nově schválený servis získají povinné ověření e-mailu. Záznam omezení vzniká ve stejné transakci jako účet; chyba doručování jej neodstraní. Původní účty bez tohoto záznamu zůstávají přístupné a opakované odeslání jim nezaloží nové omezení.
- Před ověřením funguje vlastní profil, stav ověření, opakované odeslání odkazu, změna hesla a export/odstranění vlastního účtu. Běžné chráněné funkce, volitelné přihlášení a webová administrace toto omezení respektují. Přidělení administrátorské role není náhradou ověření.
- Odkaz platí 24 hodin, používá náhodný token a v databázi se uchovává pouze jeho SHA-256 otisk. Nový odkaz nahradí starý, úspěšný se spotřebuje. Opakované odeslání má minutový odstup a samostatný limit požadavků.
- Ověřovací stránka odstraní token z adresy, neposílá jej v referreru a provede potvrzení až po stisku tlačítka. Automatické otevření bezpečnostním skenerem e-mailu tím účet neověří. Po úspěchu nabídne návrat do SprávaVozidel; běžná webová aplikace zůstává pouze pro administrátory.
- Automatické kontroly nepoužívají skutečné zákazníky ani e-mailové adresy. Zahrnují nedoručení, výpadek, vypršení, opakované použití, zablokovaný účet, schválení servisu, staré účty, rollback registrace a cizí klíče zapnuté v izolované databázi. Stránka byla vizuálně ověřena při šířce 390 a 320 px.
- Tabulka `email_verifications` se při startu přidává pomocí `checkfirst`; změna neoznačuje existující účty za neověřené. Pokud vytvoření tabulky selže, chráněné API nesmí ochranu obejít. Před nasazením spustit izolované testy přesného indexu a po něm ověřit načtení původního administrátora.

- Ověření připraveného zdrojového indexu: **188 serverových testů prošlo**, dále 5 kontrol skriptu ověřovací stránky a nativní Swift kontrola povinného ověření, kompatibility se starým serverem a odmítnutých relací. E-mailový transport a pozitivní platební odpovědi jsou simulované; žádný skutečný účet ani nákup nebyl vytvořen.

## Doplnění 30. 9. — fotografie a předání vozidla

- Ověření e-mailů `ab9afa2` je nasazené jako Live. Produkční health a ověřovací stránka vracejí 200, anonymní stav ověření 401. Původní admin v simulátoru přežil tři restarty. Test odhalil přesouvání odkazu na tarify během načítání karet; odkazy jsou nyní v iOS nahoře. Opakovaný test vstupu do tarifů i návratu z provozní kontroly prošel.
- Soukromý PDF protokol opravy shrnuje všechny tři fáze, autora, čas nahrání, čas/zdroj podle telefonu a SHA-256 původního souboru. Obsahuje správné logo a místo pro ruční předání/podpisy. Není elektronicky podepsaný a neprokazuje nezávisle čas pořízení ani pravdivost scény.
- Protokol mohou stáhnout vlastník vozidla, servis, který dokumentaci vytvořil, a administrátor. Cizí uživatel ani jiný servis přístup nemají. Po odvolání sdílení zůstává původnímu servisu čtení jeho historie; další snímky už přidávat nemůže.
- Chybějící, poškozený či nečitelný snímek vede k chybě, nikdy k neoznačenému vynechání. Export má limity 100 fotografií / 120 MB zdrojových souborů, zmenšené náhledy pro tisk a nejvýše jeden souběžný výpočet na proces. Při zaneprázdnění lze pokus opakovat. Neexistují veřejné odkazy na soubory.
- iOS koncept drží jednou připravené bajty JPEG a identifikátor opakovaného požadavku. Rozlišuje server, účet a opravu, je chráněný na zařízení a vynechaný ze záloh. Obnovení formuláře snímek znovu nekomprimuje a nemění identifikátor. Po zahájení odesílání zůstává obsah neměnný až do potvrzení nebo výslovného zahození místního konceptu. Starý formát konceptu se přenese bez změny bajtů.
- Fyzický fotoaparát není tímto ověřený: výchozí je samostatný širokoúhlý objektiv, odstraněn souběžný diagnostický výstup. Dříve hlášený černý/zelený obraz musí znovu ověřit vlastník na iPhonu.

- Přesný připravený serverový index prošel 21 izolovanými testy protokolu, oprávnění, nezměnitelnosti opakovaného odeslání a vlastnictví. Náhled PDF má čtyři vykreslené a zkontrolované stránky se smyšlenými snímky. iOS `ddac1de` prošlo podepsaným sestavením simulátoru, Release kompilací pro iPhone a testem místních konceptů; kopie pro Xcode je synchronizovaná se zachovaným nastavením podpisu.


## Doplnění 1. 10. — odstranění účtu, doklady a oddělení místních dat

- Server `e08125f` je ověřený jako Live. Změny účtu a fronta odstranění souborů
  jsou atomické; opožděná Comgate platba nemůže obnovit předplatné zaniklé
  organizace. Platební evidence a ochrana Apple nákupů zůstávají uchované.
  Stav dokončení se ověřuje náhodným potvrzením bez e-mailu či jiných detailů.
- iOS `9a68604` je synchronizovaný do pracovního Xcode projektu. Potvrzení
  odstranění je čitelné, přístupné i po restartu; export není podmínkou.
  Při změně přihlášení se oddělí přehledy i opožděné odpovědi.
- Dvě kontroly skutečného admin rozhraní prošly: bezpečný nevyplněný formulář
  odstranění a Provoz → Automatické kontroly → čekající soukromé soubory.
  Původní automatizace mířila na neklikací nadpis; po opravě prošla.
- Nové ORV fotografie mají trvalé soukromé ukládání obou stran, inventář uložený
  před uploadem, chybové stavy a úklid pouze nových opuštěných pokusů. Starší
  dokumenty se automaticky nemažou. Podrobnosti: `ORV_STORAGE.md`.
- Přesný připravený kód ORV spolu s účetním výmazem, přístupy a Apple/Comgate
  prošel **226 testy** v oddělené databázi. Skutečné soubory, účty, nákupy ani
  e-maily se testem neměnily.
- Současná kompilace Release pro iPhone prošla bez distribučního podpisu.
  Apple ToS, produkty, sandbox nákupy, TestFlight a fyzický fotoaparát stále
  vyžadují dokončení; nejde o prohlášení, že je aplikace již vydaná.

## Kontrola před prvním veřejným vydáním 1.0.0 — 1. 10. 2026

První veřejná verze je **1.0.0**, build 1. Přehled nalezených bezpečnostních chyb, provedených kontrol a zbývajících překážek vydání je v [RELEASE_1_0_0_AUDIT.md](RELEASE_1_0_0_AUDIT.md). Povinné ověření administrátora a provozní důsledky popisuje [ADMIN_MFA.md](ADMIN_MFA.md). Starší úspěšné sestavení nebo počet testů není schválením veřejného vydání.
