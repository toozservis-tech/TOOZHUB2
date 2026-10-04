# SprávaVozidel — vydání v App Storu

Poslední přímé ověření: **4. 10. 2026**. iOS předplatné používá Apple In-App Purchase; Comgate zůstává pro web. Níže je současný stav. Datovaná doplnění za touto částí jsou historické záznamy jednotlivých etap, nikoli potvrzení dnešní připravenosti.

## Současný ověřený stav

- Placené členství Apple Developer je aktivní, tým `5DATUX4X32`, Individual. Existuje aplikace **SpravaVozidel**, Apple ID **6818048361**, bundle ID `cz.toozservis.spravavozidel.ios`, SKU `spravavozidel-ios`, primární jazyk čeština. Nativní název je SprávaVozidel; spor o původní název obchodu není tímto vyřešen.
- **Verze 1.0.0, build 3 je skutečně nahraná a zpracovaná Applem.** App Store Connect → TestFlight ukazuje upload **Complete** a build **Ready to Submit** (3. 10. 2026, 20:44 místního času). Build UUID `6dd4532c-0c5f-4d61-be93-7d259e810937`. Toto není schválení App Review, veřejné vydání ani rozeslané pozvánky: build má 0 skupin a 0 jednotlivých testerů.
- Záznam App Store verze je stále **Prepare for Submission**, s ručním zveřejněním. České popisy, klíčová slova, odkazy podpory a privacy jsou uložené. Věkový dotazník je uložený s výsledkem **4+**; aplikace není označená jako aplikace pro děti. Snímky pro obchod a omezený účet pro recenzenta zůstávají nedokončené.
- App Privacy má uložený, plně vyplněný **návrh 14 kategorií**: App Functionality, linked to user, tracking=false. Návrh není zveřejněný. Veřejné zásady a podmínky vracejí HTTP 200, ale konkrétní retence, zálohy a smlouvy se zpracovateli ještě vyžadují ověření; neprohlašovat hotový právní soulad.
- Po výslovném souhlasu vlastníka byl vytvořen místní **Apple Distribution** certifikát `7VH3H4SCRT`, tým `5DATUX4X32`, platnost do 3. 10. 2027. Klíč zůstává na Macu mimo Git a aplikaci. Stávající certifikáty nebyly odstraněné. Exportovaný build 3 prošel `codesign --verify --deep --strict`, včetně vlastní podpisové podmínky, a má App Store profil bez vývojových zařízení a s `get-task-allow=false`.
- Build 2 Apple odmítl kvůli průhledné ikoně a chybě cloudového podpisu. Build 3 používá všech 15 ikon v neprůhledném RGB a schválený místní podpis; nový upload oba problémy uzavřel. Produkční Release neobsahuje místní HTTP výjimky. Vývojové sestavy je zachovávají. Deklarace šifrování používá standardní platformní HTTPS/Keychain/CryptoKit.
- Přesný archiv je `/tmp/sv-appstore-1.0.0-build3.xcarchive`, export `/tmp/sv-appstore-1.0.0-build3-export/TooZHubiOS.ipa`. SHA-256 IPA: `b902e8a7cb69ecd5530585a883f6f79dc486df5ec2138a9452079959d0fcea38`. Protokoly a obrázek přijetí: pracovní kořen `work/v1-appstore-*`, `outputs/appstore-1.0.0/testflight-accepted.jpg`.
- Produkční server je ověřený jako Render **Live**, commit `29b1207a81fb2b254bfdfe7ce8b78a05f7a829f9`, health HTTP 200 / status ok / verze 1.0.0. Oficiální Apple SDK nyní dostává PEM jako bytes; 50 cílených regresí prošlo. Opravené dvojité WHERE v administrátorském přehledu vozidel nyní vylučuje sloučené profily bez chyby SQL. Audit zůstává povinný; opravena byla chybějící skutečná admin identita pouze v testovací fixture.
- Automatické ověření: první serverová sada měla 467 úspěšných a 2 neúspěšné případy; po opravě obou příčin prošlo všech **47 cílených regresí**. Dále prošlo **70 testů skutečného izolovaného PostgreSQL**. Nativní sada má **168 úspěšných, 3 výslovně přeskočené, 0 neúspěšných** případů; po přesunu beze změny finančních datových struktur prošlo dalších **24 cílených** testů. Síťová izolace, přesměrování, soukromé koncepty fotografií a skutečná Keychain po restartu rovněž prošly. To nenahrazuje aktuální ruční test telefonu ani skutečný nákup Apple.

## Předplatné — vytvořené produkty a zbývající nastavení

Existuje **jedna skupina 22431514** SprávaVozidel. Premium je úroveň 1, Basic úroveň 2; měsíční a roční varianta stejného plánu mají shodnou úroveň. Family Sharing je vypnuté a není implementované. Vícemístné nákupy jsou vypnuté. Roční produkt znamená zaplacení celého roku předem; měsíční splátky s ročním závazkem nejsou nastavené. **Streamlined Purchasing je stále Turned On.** Přímý Edit v současném stavu změnu nezpřístupnil. Apple pro vypnutí požaduje poslední schválenou sestavu s příslušnými StoreKit API (`PurchaseIntent`); zatím není schválená žádná sestava. Zdroj build 4 již obsahuje bezpečný příjem `PurchaseIntent` s přihlášením, vazbou na účet a výslovným potvrzením; 15 cílených testů a Release kompilace prošly. Build 4 zatím není nahraný ani schválený. Základní skutečný Sandbox nákup Basic měsíčně, obnova, změna účtu a restart jsou ověřené v odděleném místním testu popsaném níže; další životní cyklus a distribuční směrování ještě ne. Před aktivací vyřešit bezpečný vstup přes přihlášený účet a dostupné vypnutí nákupů mimo aplikaci. Propagace a externí nabídky se zatím nenastavují. [Pravidla Applu](https://developer.apple.com/help/app-store-connect/manage-subscriptions/manage-streamlined-purchasing).

| Produkt | Apple ID | Období | Úroveň |
| --- | --- | --- | --- |
| `cz.toozservis.spravavozidel.basic.monthly` | 6818211306 | 1 měsíc | 2 |
| `cz.toozservis.spravavozidel.basic.yearly` | 6818211688 | 1 rok | 2 |
| `cz.toozservis.spravavozidel.premium.monthly` | 6818209814 | 1 měsíc | 1 |
| `cz.toozservis.spravavozidel.premium.yearly` | 6818210963 | 1 rok | 1 |

**Vlastník schválil a App Store Connect má uložené všechny čtyři české ceny.** Basic 149 Kč měsíčně / 1 490 Kč ročně; Premium 449 Kč měsíčně / 4 490 Kč ročně. Každá skutečná Starting Price byla po uložení otevřená a ověřená, nikoli pouze vypočtená v cenové kalkulačce. Všechny produkty mají uloženou českou lokalizaci. Basic uvádí až 5 vozidel, servisní historii a dokumenty; Premium neomezený počet vozidel, náklady, statistiky a sdílení. Popisy odpovídají `PLAN_LIMITS` a `PLAN_FEATURES` produkčního serveru. Dostupnost všech čtyř produktů je uložená a ověřená pro Českou republiku (1 ze 175 regionů); roční produkty pouze s úhradou celého roku předem. Snímky pro schválení ještě nejsou dodané. Přepočtený ceník pro 175 zemí sám nezpřístupňuje nákup ani aplikaci. Klient zobrazuje cenu z App Storu; webové ceny se touto změnou nemění.

1. **Business:** Free Apps Agreement i Paid Apps Agreement jsou **Active**, bankovní účet rovněž **Active** (živě 4. 10. 2026). Vlastník osobně zkontroloval právní údaje, potvrdil smlouvu a odeslal bankovní a daňové formuláře. Foreign Status Certificate a W-8BEN jsou **Active**. DSA je **In Review**; výsledek ověření ještě není známý. DAC7 ukazuje **Missing Info**; požadavky a dopad na vydání ještě nebyly zkontrolované. Agent smlouvy ani daňová prohlášení nepotvrzoval; bankovní a daňové identifikátory do tohoto přehledu nepatří.
2. **Serverový klíč:** Distribuční certifikát nenahrazuje In-App Purchase API klíč. Vlastník jej mezitím vytvořil jako „SpravaVozidel server“; živě ověřeno Active (1). Po výslovném souhlasu vlastníka byl jednou stažený a přesunutý mimo Downloads a repozitáře do soukromé složky na Macu (složka 0700, soubor 0600); platný P-256 klíč. Render `srv-dasnd9e0tbcc7386n5t0` má uložených osm `APPLE_IAP_*` proměnných, celkem 30, s **`APPLE_IAP_ENABLED=0`**. Volba Save and deploy nasadila stávající sestavení, bez změny kódu; Následná oprava SDK je nasazená jako Live `29b1207` a health 200/ok je ověřený. Přímý read-only požadavek z Macu přes oficiální knihovnu s tímto klíčem byl přijat v **Sandbox**, Production opakovaně vrátila **401** (4. 10. 2026). Technik App Store Commerce v oficiálním fóru Applu uvádí, že produkční API je dostupné až po prvním vydání aplikace. Současný předvydáním zjištěný stav tomu odpovídá, skutečné produkční ověření však zůstává podmínkou po vydání. [Vyjádření Apple Staff](https://developer.apple.com/forums/thread/806452). Žádný fallback na Sandbox se nezavádí. Samotný test klíče neověřuje nákupy ani webhooky; výsledky následného skutečného místního Sandbox nákupu jsou uvedené níže. Klíč nikdy není v aplikaci, Gitu ani chatu. Další klíč nevytvářet.
3. Nastavit `APPLE_IAP_ENABLED`, `APPLE_IAP_BUNDLE_ID=cz.toozservis.spravavozidel.ios`, `APPLE_IAP_APP_ID=6818048361`, `APPLE_IAP_SUBSCRIPTION_GROUP_ID=22431514`, `APPLE_IAP_KEY_ID`, `APPLE_IAP_ISSUER_ID`, `APPLE_IAP_PRIVATE_KEY`, `APPLE_IAP_ENVIRONMENT` (`Production` nebo `Sandbox`). Každé nasazení ověřuje jediný režim; žádný automatický přechod z produkce na sandbox. TestFlight a App Review musí dostat funkční podporu sandbox nákupů bez oslabení produkčního verifieru. Oddělený backend, databáze, účty a odpovídající klientské směrování dosud nejsou ověřené.
4. Před zapnutím provést aditivní migraci `python -m scripts.migrate_apple_billing`. Přidává potřebné Apple tabulky včetně `apple_reconciliation_state`; nemění staré licence, účty ani Comgate. Konfiguraci aktivovat až po ověření migrace a izolovaného testovacího prostředí.
5. Nastavit App Store Server Notifications **V2** na `/api/v1/license/apple/notifications` příslušného HTTPS serveru. Produkční a sandbox adresy zatím v App Store Connect nastavené nejsou. Ověřit Apple test notification, skutečný sandbox nákup, obnovu po instalaci, renewal, downgrade/upgrade, grace, refund, refund reversal, výpadek sítě, změnu účtu aplikace a zrušení obnovování.
6. iOS transakci dokončuje až po potvrzeném uložení na serveru. Náhodný `appAccountToken` svazuje nákup s účtem; server ověřuje současný stav přes App Store Server API a oznámení V2. Opožděný webhook neobnoví zaniklý účet. Vypršení období nemaže uživatelská data. Pozitivní izolované platební testy jsou simulované a nejsou skutečným nákupem Apple.
7. Po zapnutí Apple běží samostatná průběžná kontrola ověřených nákupů, ve výchozím stavu po dávkách každých 300 s. `APPLE_RECONCILIATION_INTERVAL_SEC` má rozsah 60–3600 s, `ENABLE_APPLE_RECONCILIATION_WORKER=0` ji vypne. Jednotlivé položky mají trvalý stav, obnovitelný zámek a odstup opakování. Dokud integrace není nastavená, administrace správně hlásí čekání.


### Ověření kroku 1 — 4. 10. 2026

- Vlastník vytvořil první Sandbox Apple Account; App Store Connect po obnovení potvrzuje jeden účet pro Českou republiku, bez předchozího nákupu. Heslo není v projektu ani v důkazech. Přihlášení na telefonu provádí vlastník pouze přes Nastavení → Vývojář → Sandbox Apple Account.
- Nativní commit `a719dc9` vyžaduje ověřenou AppTransaction a přesnou shodu prostředí instalace, katalogu, nákupní relace i transakce. Deset cílených nativních testů a nepodepsaná Release kompilace prošly. Zdrojový kód a testy jsou bezpečně přenesené také do původního source-mirror; jeho ostatní změny se nepřepisovaly.
- Tři nové skutečné PostgreSQL testy prošly na čerstvém izolovaném Unix-only clusteru. Ověřují souběžné vytvoření identity, zákaz přisvojení stejné organizace dvěma zákazníky a neobnovení refundované licence starší odpovědí. Apple odpovědi v těchto případech jsou syntetické, nikoli platby.
- Místní testovací harness používá skutečný nativní BillingView/AppStoreSubscriptions a skutečný serverový apple_billing/verifier. Má samostatnou databázi se dvěma smyšlenými účty a pouze Sandbox; žádné produkční účty, SMTP/Comgate worker nebo veřejný tunel. Preflight odmítl anonymní i neplatné přihlášení a neplatný podpis transakce. Podpisový Apple klíč je pouze v paměti serveru na Macu a není v testovací aplikaci.
- Fyzické vývojové testovací sestavení používá produkční bundle ID, aby mohlo načíst existující Apple produkty; je samostatně označené „SprávaVozidel test“. Není to distribuční archiv build 4 ani konfigurace pro TestFlight/App Review. Po opravě úzké výjimky pouze pro místní testovací spojení se sestavení nainstalovalo a spustilo na iPhonu „1234“. Vlastník přímo ověřil ceny, potvrdil Basic měsíčně v Sandboxu, obnovu, přepnutí na účet 2 a návrat i restart. Server skutečně ověřil podepsanou Apple transakci a současný stav přes Apple API: Basic patří zákazníkovi/organizaci 1, druhý účet zůstává zdarma. Nejde o simulovanou pozitivní Apple odpověď. Device Hub obraz telefonu nevracel; vizuální výsledky potvrzuje vlastník, serverové výsledky jsou přímo zkontrolované. Důkaz: `outputs/appstore-1.0.0/sandbox-purchase-proof.json`.
- Skutečné automatické Sandbox prodloužení rovněž prošlo: nová podepsaná Apple transakce, stejná původní objednávka i vlastník, pozdější platnost; druhý účet zůstává zdarma. Výpadky sítě, zrušení obnovování, změny plánu, grace/refund a oznámení HTTPS V2 ještě nejsou tímto testem prokázané.
- Protokoly: `work/v1-appstore-environment-tests.log`, `work/v1-appstore-environment-release.log`, `work/v1-apple-postgresql-tests.log`, `work/v1-apple-sandbox-device-build.log`. Současná produkce stále používá `APPLE_IAP_ENABLED=0`.


### Ověření funkcí jednotlivých tarifů — 4. 10. 2026

Tato změna je připravená ve zdrojovém kódu a ve fyzické **SprávaVozidel test**. Není součástí již nahraného buildu 3 ani dosud potvrzeného produkčního nasazení. Apple nákupy se tím na produkci nezapínají.

| Zákaznický tarif | Vozidla | Ruční servisní úkony | VIN / ORV / STK | Úplná historie a dokumenty | Náklady, statistiky, sdílení |
| --- | --- | --- | --- | --- | --- |
| Zdarma | 1 | 2 aktivní úkony u každého vozidla | Ne | Ne | Ne |
| Basic | 5 | Bez tohoto limitu | Ano | Ano | Ne |
| Premium | Neomezeně | Bez tohoto limitu | Ano | Ano | Ano |

- Vlastník výslovně doplnil 2 ručně zadané úkony ve Free a potvrdil, že jde o limit u vozidla. Free má jednoduchý formulář, čtení a úpravu vlastních takto vytvořených úkonů. Jejich původ dokládá serverový audit `free_manual_create`; importy, přílohy a starší placená historie se touto výjimkou neodemknou. Neprovádí se migrace ani přepis historických záznamů. Odebraný úkon uvolní místo v limitu aktivních úkonů.
- Server kontroluje skutečnou roli, vlastnictví, dostupné funkce i limit v transakci. Free odmítne druhé vozidlo, Basic šesté. Souběžné ruční zápisy ve Free se zastaví na dvou. Basic smí načítat údaje i při naplněném limitu pěti vozidel; načtení údajů není založení dalšího auta.
- iOS používá serverové příznaky vázané na aktuální účet a přihlášení. Obnovuje je po nákupu, obnově, přihlášení a návratu do aplikace; opožděná odpověď předchozího účtu nemůže odemknout nový účet. Chybějící nebo neplatný stav nezpřístupní placené funkce. Zamčení historie/nákladů neshodí základní garáž ani detail vozidla.
- Zprávy o limitu jsou oddělené: Free nabídne Basic nebo Premium, Basic po pěti vozidlech doporučí Premium. Tlačítko `+` zobrazí vysvětlení a tarify i při dosaženém limitu. Ruční třetí úkon ve Free hlásí vlastní limit dvou úkonů.
- Oprávnění servisu a administrátora se řídí rolí a přístupem k vozidlu, zákaznické předplatné tyto role neuděluje. Členství ve stejné organizaci jako administrátor neumožňuje měnit vlastní tarif přes `/license/upgrade`.
- Prošlo **276 API regresí**, **13 nativních testů**, samostatná kontrola dekódování příznaků a chyb a kontrola místního ukládání. Prošlo **6 skutečných PostgreSQL kontrol** souběhu vozidel/Apple identity a další kontrola **tří současných ručních zápisů → 2 úspěchy + 1 odmítnutí**. Externí registry a pozitivní Apple odpovědi v těchto regresích jsou izolované testovací vstupy. Nepodepsané Release sestavení i fyzické vývojové sestavení prošly.
- Fyzický test původně narazil na `Relace vypršela` v detailu vozidla: některé obrazovky vytvářejí vlastní APIClient a soukromý harness jim nezadal místní server. Vývojové nastavení nyní směruje všechny klienty na totožný soukromý server; produkční omezení HTTPS zůstává. Vlastník potvrdil, že detail se po opravě načetl. Přepnutí testovacího účtu navíc obnoví celý strom obrazovek stejně jako skutečný RootView.
- Soukromý HTTP preflight přímo ověřil vytvoření a čtení dvou ručních záznamů na smyšleném účtu 2, odmítnutí třetího a vrácení testovacího vozidla do prázdného stavu. Důkaz: `outputs/appstore-1.0.0/subscription-entitlement-device-preflight.json`. Dřívější skutečné Sandbox Basic mezitím vypršelo; po restartu server ověřil současný stav u Applu a účet 1 přešel na Free, přičemž všech pět vozidel zůstalo uložených. Placená licence se v harnessu uměle nenastavuje.
- Vlastník ve fyzické testovací aplikaci uložil dva smyšlené ruční úkony na účtu 2; soukromá databáze přímo potvrzuje právě dva aktivní záznamy. Třetí vstup neukázal limit: tlačítko `+` v historii a tlačítko prázdného seznamu obcházely kontrolu provedenou pouze v hlavičce detailu. Všechny tři vstupy nyní používají jeden handler s načtením aktuální licence i počtu úkonů; vyčerpaný limit nabídne Basic/Premium. Případná chyba zápisu je viditelná i při neprázdném seznamu. Nový nativní test ověřil obnovení původně prázdné cache po zaplnění kvóty.
- **Oprava všech vstupů je sestavená, nainstalovaná a spuštěná na iPhonu 1234.** Původní vývojový profil hlavního bundle vypršel 4. 10. v 08:13:49 UTC a automatické podepisování Xcode nefungovalo ani po obnovení přihlášení vlastníkem. Profil byl obnovený na portálu Apple Developer se stejným existujícím vývojovým certifikátem, stejným bundle a jediným již registrovaným iPhonem 1234; žádný nový certifikát ani privátní klíč nevznikl. Aktivní profil do 4. 10. 2027 se stáhl přes Xcode a soukromé sestavení použilo ruční podpis. Podpisové nastavení distribučního projektu se neměnilo. Důkaz je `outputs/appstore-1.0.0/development-profile-renewed.png`. Dva uložené úkony zůstávají zachované. **Zbývá ruční potvrzení hlášky třetího úkonu u tlačítek v hlavičce i historii a otevření tarifů.** Úplné vizuální ověření všech tarifů, skutečný upgrade na Premium a ostatní dříve uvedené distribuční/platební kontroly nejsou tímto prohlášeny za hotové.
- Další hlášení vlastníka ukázalo zprávu Free na účtu 1, považovaném za Basic. Přímý živý dotaz ověřil shodu obou API: licence Free, limit 1, zachovaných 5 vozidel; Apple katalog Free/canceled a ukončení Basic **4. 10. v 09:43:41 místního času**. Nejde o záměnu rolí ani zprávu Basic vrácenou jako Free. Soukromá testovací hlavička nyní ukazuje aktuální serverový tarif a počty i v režimu celé aplikace. Upravený harness se sestavil, nainstaloval a spustil na stejném telefonu. **Vlastník po novém skutečném Sandbox nákupu potvrdil aktivní Basic a správnou hlášku limitu pěti vozidel s doporučením Premium.** Následný soukromý HTTP dotaz v 10:47:22 místního času potvrdil Basic/active, 5 uložených vozidel a limit 5; účet 2 zůstal Free s limitem 1 vozidla a 2 ručních úkonů. Tento časový bod neznamená trvalou platnost zrychleného Sandbox předplatného. Důkaz je aktualizovaný `subscription-entitlement-device-preflight.json`; ruční kontrola třetího úkonu ve Free ještě čeká.
- Změny 18 zdrojových a testovacích souborů jsou přenesené do původního `source-mirror/app/ios/TooZHubiOS`; podpisové nastavení a ostatní rozpracované změny se nepřepisovaly. Protokoly této etapy mají prefix `work/v1-entitlements-`.
- Vlastník následně hlásil chybu rezervací, profilu a připomínek v celé testovací aplikaci. Soukromému harnessu chyběly skutečné routy rezervací, servisních kontaktů, zabezpečení profilu a nastavení připomínek. Nyní je používá přímo z aplikace; **22 přihlášených HTTP kontrol prošlo pro oba účty, anonymní čtení byla odmítnuta**. Skutečný Swift klient přečetl jejich odpovědi včetně vozidel dostupných pro rezervaci, s kontrolou správného vlastníka. Dvě původní identity, vazba nákupu Apple a dva uložené Free úkony zůstaly zachované; e-mailový transport je vypnutý. Sestavení, instalace a spuštění na iPhonu 1234 prošly a **vlastník potvrdil načtení všech tří obrazovek bez chyby**. Současně opraveno pořadí statické routy `/reminders/settings` před dynamickou `/reminders/{reminder_id}`, aby PUT nastavení nekončil chybnou validací ID; **6 cílených testů prošlo**, včetně uložení nastavení, oddělení účtů a zachované úpravy jednotlivé připomínky. Produkční nasazení tato kontrola neprovádí. Protokoly mají prefix `work/v1-entitlements-tabs-`.

### Sjednocený vzhled nativních obrazovek — 4. 10. 2026

- Tarify a předplatné nyní používají stejné tmavé pozadí, karty, oranžové hlavní akce a světlé texty jako zákaznická aplikace. Sdílená karta tarifu zobrazuje skutečnou lokalizovanou cenu StoreKit a přizpůsobuje nadpis/cenu většímu písmu. Nákup, obnova, správa předplatného, ověření prostředí a podmínky dostupnosti zůstávají stejné.
- Společné `HubForm`, `HubList` a `hubSystemPage()` sjednocují vlastní formuláře, ORV, pozvánky, přehledy dokladů, ověřování účtu a potvrzení odstranění. Odstraněna vynucená světlá prezentace těchto obrazovek; tmavé texty na bývalých světlých plochách jsou upravené pro čitelnost. Tiskové PDF a bílá podložka bezpečnostního QR zůstávají čitelné ve svém původním formátu. Systémové obrazovky Apple ovládá iOS.
- Prošlo fyzické vývojové, simulátorové i nepodepsané Release sestavení a **13 cílených testů tarifů a hranice Apple prostředí**. Jeden původní test přepnutí účtů potřeboval čekat na dokončení asynchronní aktualizace licence; zachovává kontrolu, že opožděná Premium odpověď nikdy neodemkne nový Free účet. Vizuálně zkontrolovány skutečné společné karty a formulář v simulátoru při běžném i větším písmu. Náhledy mají výhradně smyšlená data a neprovádějí nákup. Důkazy: `outputs/appstore-1.0.0/theme-review/`, protokoly `work/v1-theme-*`.
- Upravený testovací build je nainstalovaný na iPhonu **1234**. Ruční potvrzení vzhledu vlastníkem zatím čeká. Změny jsou přenesené také do původního iOS zdroje; zachované odlišné jméno aplikace v tomto zdroji a podpisová nastavení. Neproběhlo nové nahrání do App Store Connect ani změna produkčních předplatných.

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

- Výsledek přezkumu DSA a zjištění požadavků DAC7 Missing Info. Banka, Paid Apps Agreement a daňové formuláře jsou Active; ceny, české lokalizace a dostupnost pro ČR jsou uložené. Oddělené testovací nasazení pro TestFlight/App Review a skutečné ověření Apple nákupů ještě čekají.
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

## 3. 10. 2026 — reálný klíč a konstruktor Apple SDK

- Při použití skutečné oficiální Python knihovny se zjistilo, že konstruktor klienta vyžaduje PEM jako `bytes`, ale konfigurace předávala text z prostředí. Oprava převádí UTF-8 pouze na rozhraní klienta; žádná změna ověřování podpisu, prostředí nebo oprávnění.
- Nová regrese vytváří pouze dočasný P-256 klíč v paměti a skutečný klient/verifier bez přístupu na síť. Všech **50 cílených Apple testů prošlo**. Skutečná platba nebyla zahájená.
