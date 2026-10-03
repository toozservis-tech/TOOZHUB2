# SprávaVozidel — vydání v App Storu

Poslední přímé ověření: **3. 10. 2026**. iOS předplatné používá Apple In-App Purchase; Comgate zůstává pro web. Níže je současný stav. Datovaná doplnění za touto částí jsou historické záznamy jednotlivých etap, nikoli potvrzení dnešní připravenosti.

## Současný ověřený stav

- Placené členství Apple Developer je aktivní, tým `5DATUX4X32`, Individual. Existuje aplikace **SpravaVozidel**, Apple ID **6818048361**, bundle ID `cz.toozservis.spravavozidel.ios`, SKU `spravavozidel-ios`, primární jazyk čeština. Nativní název je SprávaVozidel; spor o původní název obchodu není tímto vyřešen.
- **Verze 1.0.0, build 3 je skutečně nahraná a zpracovaná Applem.** App Store Connect → TestFlight ukazuje upload **Complete** a build **Ready to Submit** (3. 10. 2026, 20:44 místního času). Build UUID `6dd4532c-0c5f-4d61-be93-7d259e810937`. Toto není schválení App Review, veřejné vydání ani rozeslané pozvánky: build má 0 skupin a 0 jednotlivých testerů.
- Záznam App Store verze je stále **Prepare for Submission**, s ručním zveřejněním. České popisy, klíčová slova, odkazy podpory a privacy jsou uložené. Věkový dotazník je uložený s výsledkem **4+**; aplikace není označená jako aplikace pro děti. Snímky pro obchod a omezený účet pro recenzenta zůstávají nedokončené.
- App Privacy má uložený, plně vyplněný **návrh 14 kategorií**: App Functionality, linked to user, tracking=false. Návrh není zveřejněný. Veřejné zásady a podmínky vracejí HTTP 200, ale konkrétní retence, zálohy a smlouvy se zpracovateli ještě vyžadují ověření; neprohlašovat hotový právní soulad.
- Po výslovném souhlasu vlastníka byl vytvořen místní **Apple Distribution** certifikát `7VH3H4SCRT`, tým `5DATUX4X32`, platnost do 3. 10. 2027. Klíč zůstává na Macu mimo Git a aplikaci. Stávající certifikáty nebyly odstraněné. Exportovaný build 3 prošel `codesign --verify --deep --strict`, včetně vlastní podpisové podmínky, a má App Store profil bez vývojových zařízení a s `get-task-allow=false`.
- Build 2 Apple odmítl kvůli průhledné ikoně a chybě cloudového podpisu. Build 3 používá všech 15 ikon v neprůhledném RGB a schválený místní podpis; nový upload oba problémy uzavřel. Produkční Release neobsahuje místní HTTP výjimky. Vývojové sestavy je zachovávají. Deklarace šifrování používá standardní platformní HTTPS/Keychain/CryptoKit.
- Přesný archiv je `/tmp/sv-appstore-1.0.0-build3.xcarchive`, export `/tmp/sv-appstore-1.0.0-build3-export/TooZHubiOS.ipa`. SHA-256 IPA: `b902e8a7cb69ecd5530585a883f6f79dc486df5ec2138a9452079959d0fcea38`. Protokoly a obrázek přijetí: pracovní kořen `work/v1-appstore-*`, `outputs/appstore-1.0.0/testflight-accepted.jpg`.
- Produkční server je ověřený jako Render **Live**, commit `144fbdb4b6172a763adbd25b8f8d7b4f6f1f72f1`, health HTTP 200 / status ok / verze 1.0.0. Opravené dvojité WHERE v administrátorském přehledu vozidel nyní vylučuje sloučené profily bez chyby SQL. Audit zůstává povinný; opravena byla chybějící skutečná admin identita pouze v testovací fixture.
- Automatické ověření: první serverová sada měla 467 úspěšných a 2 neúspěšné případy; po opravě obou příčin prošlo všech **47 cílených regresí**. Dále prošlo **70 testů skutečného izolovaného PostgreSQL**. Nativní sada má **168 úspěšných, 3 výslovně přeskočené, 0 neúspěšných** případů; po přesunu beze změny finančních datových struktur prošlo dalších **24 cílených** testů. Síťová izolace, přesměrování, soukromé koncepty fotografií a skutečná Keychain po restartu rovněž prošly. To nenahrazuje aktuální ruční test telefonu ani skutečný nákup Apple.

## Předplatné — vytvořené produkty a zbývající nastavení

Existuje **jedna skupina 22431514** SprávaVozidel. Premium je úroveň 1, Basic úroveň 2; měsíční a roční varianta stejného plánu mají shodnou úroveň. Family Sharing je vypnuté a není implementované.

| Produkt | Apple ID | Období | Úroveň |
| --- | --- | --- | --- |
| `cz.toozservis.spravavozidel.basic.monthly` | 6818211306 | 1 měsíc | 2 |
| `cz.toozservis.spravavozidel.basic.yearly` | 6818211688 | 1 rok | 2 |
| `cz.toozservis.spravavozidel.premium.monthly` | 6818209814 | 1 měsíc | 1 |
| `cz.toozservis.spravavozidel.premium.yearly` | 6818210963 | 1 rok | 1 |

**Vlastník schválil a App Store Connect má uložené všechny čtyři české ceny.** Basic 149 Kč měsíčně / 1 490 Kč ročně; Premium 449 Kč měsíčně / 4 490 Kč ročně. Každá skutečná Starting Price byla po uložení otevřená a ověřená, nikoli pouze vypočtená v cenové kalkulačce. Všechny produkty mají uloženou českou lokalizaci. Basic uvádí až 5 vozidel, servisní historii a dokumenty; Premium neomezený počet vozidel, náklady, statistiky a sdílení. Popisy odpovídají `PLAN_LIMITS` a `PLAN_FEATURES` produkčního serveru. Country availability a snímky pro schválení nejsou dokončené. Přepočtený ceník pro 175 zemí sám nezpřístupňuje nákup ani aplikaci. Klient zobrazuje cenu z App Storu; webové ceny se touto změnou nemění.

1. **Business:** Free Apps Agreement je Active; Paid Apps Agreement vlastník 3. 10. 2026 osobně potvrdil a Apple nyní uvádí Pending User Info. Apple vyžaduje nejdříve aktualizovat právní údaje v Edit Legal Entity. Vlastník osobně zkontroloval a uložil právní údaje; zmizela blokující výzva a Apple zpřístupnil Paid Apps Agreement. Smlouva je potvrzená přímo vlastníkem; údaj o typu subjektu, jméně a adrese se nevymýšlí. Agent za vlastníka smlouvu nepřijímal. Vlastník osobně uložil bankovní účet; Apple nyní uvádí Processing a očekává zpracování do 24 hodin. Úvodní U.S. Tax Questionnaire je dokončený. U.S. Certificate of Foreign Status of Beneficial Owner vlastník osobně odeslal a jeho stav je ověřený jako Active. Následně Apple zpřístupnil U.S. Form W-8BEN, který má stále Missing Tax Info a zůstává předaný vlastníkovi. Agent nezadává daňová čísla, neurčuje neověřený smluvní nárok a nepotvrzuje daňové prohlášení. DSA dokončení čeká. Bankovní a daňové identifikátory se neukládají do tohoto přehledu.
2. **Serverový klíč:** Distribuční certifikát nenahrazuje In-App Purchase API klíč. Ten ještě není vytvořený/nastavený. Produkční Render prostředí má 22 viditelných názvů proměnných, žádné `APPLE_IAP_*` a žádnou připojenou skupinu tajných proměnných. Integraci zatím nezapínat. Po konkrétním oprávnění vytvořit klíč přes Users and Access → Integrations → In-App Purchase a uložit pouze na schválený server, nikdy do aplikace, Git nebo chatu.
3. Nastavit `APPLE_IAP_ENABLED`, `APPLE_IAP_BUNDLE_ID=cz.toozservis.spravavozidel.ios`, `APPLE_IAP_APP_ID=6818048361`, `APPLE_IAP_SUBSCRIPTION_GROUP_ID=22431514`, `APPLE_IAP_KEY_ID`, `APPLE_IAP_ISSUER_ID`, `APPLE_IAP_PRIVATE_KEY`, `APPLE_IAP_ENVIRONMENT` (`Production` nebo `Sandbox`). Každé nasazení ověřuje jediný režim; žádný automatický přechod z produkce na sandbox. TestFlight a App Review musí dostat funkční podporu sandbox nákupů bez oslabení produkčního verifieru. Oddělený backend, databáze, účty a odpovídající klientské směrování dosud nejsou ověřené.
4. Před zapnutím provést aditivní migraci `python -m scripts.migrate_apple_billing`. Přidává potřebné Apple tabulky včetně `apple_reconciliation_state`; nemění staré licence, účty ani Comgate. Konfiguraci aktivovat až po ověření migrace a izolovaného testovacího prostředí.
5. Nastavit App Store Server Notifications **V2** na `/api/v1/license/apple/notifications` příslušného HTTPS serveru. Produkční a sandbox adresy zatím v App Store Connect nastavené nejsou. Ověřit Apple test notification, skutečný sandbox nákup, obnovu po instalaci, renewal, downgrade/upgrade, grace, refund, refund reversal, výpadek sítě, změnu účtu aplikace a zrušení obnovování.
6. iOS transakci dokončuje až po potvrzeném uložení na serveru. Náhodný `appAccountToken` svazuje nákup s účtem; server ověřuje současný stav přes App Store Server API a oznámení V2. Opožděný webhook neobnoví zaniklý účet. Vypršení období nemaže uživatelská data. Pozitivní izolované platební testy jsou simulované a nejsou skutečným nákupem Apple.
7. Po zapnutí Apple běží samostatná průběžná kontrola ověřených nákupů, ve výchozím stavu po dávkách každých 300 s. `APPLE_RECONCILIATION_INTERVAL_SEC` má rozsah 60–3600 s, `ENABLE_APPLE_RECONCILIATION_WORKER=0` ji vypne. Jednotlivé položky mají trvalý stav, obnovitelný zámek a odstup opakování. Dokud integrace není nastavená, administrace správně hlásí čekání.


### Schválené uložené ceny a výnos z App Store Connect

Vlastník výslovně schválil Basic **149 Kč měsíčně / 1 490 Kč ročně** a Premium **449 Kč měsíčně / 4 490 Kč ročně**. Všechny čtyři úrovně Apple skutečně nabízí; byly uložené a následně ověřené v jednotlivých Starting Subscription Price tabulkách.

| Tarif | Cena v ČR | Year 1 Proceeds | Year 2 Proceeds |
| --- | --- | --- | --- |
| Basic měsíční | 149,00 Kč | 104,67 Kč | 104,67 Kč |
| Basic roční | 1 490,00 Kč | 1 046,69 Kč | 1 046,69 Kč |
| Premium měsíční | 449,00 Kč | 315,41 Kč | 315,41 Kč |
| Premium roční | 4 490,00 Kč | 3 154,13 Kč | 3 154,13 Kč |

Tyto výnosy jsou přesně údaje z aktuálního ceníku Applu, nikoli slíbená čistá částka po všech povinnostech vlastníka. Samotná tabulka nedokládá schválení Small Business Program ani nerozhoduje o jeho daňovém statusu. Důkazy jsou `outputs/appstore-1.0.0/{basic,premium}-{monthly,yearly}-price.jpg`.

Přímá kontrola oficiálních zdrojů 3. 10. 2026 zjistila změnu: jednotné EU podmínky jsou účinné od **1. 10. 2026** a Apple pro Apple In-App Purchase uvádí **26 %**, případně **15 %** pro Small Business Program a předplatné po prvním roce. Mimo EU standardní předplatné začíná 30 % a po roce 15 %. Výnos ovlivňují příslušné transakční daně. Small Business Program není automatický: je nutná registrace, schválení a splnění společného limitu příjmů včetně propojených vývojářských účtů. Účast tohoto konkrétního účtu nebyla ověřená; slevu neslibovat jako již aktivní.

- [Apple: jednotné EU podmínky a sazby](https://developer.apple.com/support/apps-in-the-eu/)
- [Apple: Small Business Program](https://developer.apple.com/app-store/small-business-program/)
- [Apple: výnosy a daně předplatného](https://developer.apple.com/app-store/subscriptions/)

## Co ještě brání veřejnému vydání

- Dokončení W-8BEN, zpracování bankovního účtu, aktivace Paid Apps Agreement a DSA. Ceny a české lokalizace jsou uložené; dostupnost produktů, konfigurace a skutečné ověření Apple nákupů čekají.
- Pravdivé veřejné zásady a podmínky pro současné zpracování a Apple nákupy; doložení dob uchování, zpracovatelů a obnovy záloh včetně záznamů o výmazu. Starších 47 nedostupných cloudových objektů a nezávislá obnova zálohy nejsou touto etapou vyřešené.
- Reprezentativní snímky iPhone/iPad bez skutečných zákaznických údajů, kontakty a bezpečný omezený účet pro App Review, potvrzení práv k obsahu a závěrečný ruční test současného sestavení. Recenzent nedostává skutečný admin účet ani heslo vlastníka.
- Nehotová pokladna/EET zůstává skrytá podle skutečných schopností serveru; nelze ji nabízet jako hotovou funkci v popisu vydané verze. Vývojový backend s rozpracovanými POS změnami se nenasazuje místo ověřené produkční větve.
- **Add for Review ani veřejné zveřejnění nebylo provedeno.** Po uzavření těchto bodů vyžádat závěrečné konkrétní potvrzení vydání.

## Zbývající závěrečné kontroly celého produktu

- Odstranění účtu je implementované v `ACCOUNT_ERASURE.md`: dobrovolný export, povinné heslo a ruční potvrzení, vlastnictví místo plošného smazání organizace, trvalé odstranění souborů s potvrzením stavu. Izolované testy a nativní formulář prošly bez mazání skutečných účtů. Zbývá právní/produkční ověření uchování účetních podkladů, kopií a záloh.
- Inventura zdrojového kódu a zkontrolované konfigurace je v `docs/APP_PRIVACY_INVENTORY.md`. Nativní manifest zahrnuje 14 používaných kategorií údajů, UserDefaults CA92.1, FileTimestamp C617.1 a deklaraci bez reklamního sledování. Odpovědi v App Store Connect jsou vyplněné jako návrh; smlouvy, retence a konkrétní zálohy před zveřejněním ještě ověřit. Neslibovat nulový sběr osobních údajů. Ověření nových účtů je popsáno v doplnění níže; rozpracované úpravy fotografií do této etapy nepatří.
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
