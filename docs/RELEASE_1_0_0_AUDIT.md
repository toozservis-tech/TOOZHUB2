# SprávaVozidel 1.0.0 — kontrola před prvním vydáním

Stav 1. 10. 2026: příprava vydání, nikoliv souhlas s veřejným spuštěním. Historické interní verze a Git historie zůstávají zachované; první veřejná verze aplikace má číslo **1.0.0**, sestavení 1.

## Opravy z aktuální kontroly

- Aktivní dvoufázové ověření nelze přepsat novým nastavením. Příprava autentikátoru vyžaduje současné heslo a vyprší po 10 minutách.
- Chybějící nebo poškozený klíč u aktivního ověření zastaví přihlášení; nesmí změnit přihlášení na pouhé heslo.
- Použitý TOTP kód nelze přijmout znovu. Výzvy jsou v databázi uložené pouze jako otisk; pokusy a časová omezení přežijí restart aplikace/serveru.
- Databáze ukládá klíče autentikátoru šifrovaně. Platná starší nastavení se při startu převedou bez změny kódů v telefonu. Podmínky rotace klíče viz `ADMIN_MFA.md`.
- Administrátor potřebuje heslo + autentikátor. Přístup ke spravovaným datům je podmíněn ověřením z posledních 15 minut. Kontrola platí na serveru pro běžné API, volitelné přihlášení i webovou cookie.
- iOS i web vedou administrátora nastavením/obnovou ověření; přihlašovací obrazovky obsahují jen uživatelský popis. Změna faktoru zneplatňuje předchozí relace a klient uloží náhradní relaci.
- Webová administrace nepřijímá token v URL a neukládá jej do trvalého úložiště prohlížeče. Nadále používá token v úložišti aktuální karty; to samo o sobě neřeší případný XSS útok. Nová administrace nyní používá kontextové kódování textů a atributů a oddělené události tlačítek; hlavní starší rozhraní `web/index.html` bylo následně převedeno stejným směrem. Ukládání relací obou hlavních rozhraní je sjednocené (viz navazující kontrola níže); další alternativní/veřejné stránky ještě vyžadují samostatnou kontrolu.
- **Opraven únik do exportu vlastních dat:** dříve se automaticky exportovaly i sloupce `password_hash`, `totp_secret`, tokeny pozvánek a klíče push notifikací. Nyní je seznam exportovaných polí výslovný; nová databázová pole se bez kontroly do exportu nepřidají. Soukromé interní chybové zprávy se neexportují.
- Neošetřené chyby a HTTP 500 nevracejí obsah výjimky/SQL poskytovatele klientovi. Bezpečná hranice zapisuje identifikátor chyby, typ a šablonu cesty. Parametry SQL jsou skryté i v místní databázi. Další jednotlivá starší místa vlastního logování je nutné dál prověřovat.

## Navazující kontrola webu a chyb (1. 10. 2026)

- Opravené uložené XSS v nové administraci: kompaktní seznam uživatelů, vozidla, servisy, servisní záznamy, audit a chybové zprávy. Dříve se některé hodnoty vkládaly přímo jako HTML.
- Společné kódování nyní chrání také obě uvozovky v atributech nastavení. Mapové odkazy přijímají pouze HTTP/HTTPS bez vloženého jména/hesla.
- Uživatelský text není součástí JavaScriptu tlačítek: argumenty jsou JSON data a obsluha je ve výslovném seznamu povolených akcí. Všechny statické `onclick`/`onsubmit` nové administrace byly převedeny na události ve skriptu.
- Přihlášení, `/web_admin/` i jeho alternativní cesta `/admin-static/` mají přísnější CSP: žádné inline skripty/události, eval, objekty, cizí formuláře, rámce ani změna základní adresy stránky. Přihlašovací skript je samostatný soubor. Hlavní starší `web/index.html` dostal následně vlastní přísnou variantu CSP s náhledem příloh v omezeném rámu (viz níže). Alternativní a veřejné stránky nejsou tímto tvrzením zahrnuté.
- Administrátorské API už nevypisuje celé výjimky ani SQL dotazy. Bezpečná diagnostika zachovává náhodné číslo chyby, její typ a umístění ve zdrojovém kódu; neformátuje zprávu výjimky, její parametry, lokální proměnné ani zdrojový řádek. Stejné číslo se předává přes navázané výjimky až ke klientovi. Náhled zdraví a audit selhaných akcí neukládají syrovou databázovou chybu.
- Selhání načtení počtů, záznamů a auditu se hlásí jako chyba, nikoliv úspěšná prázdná databáze. Selhání uložení připomínek je serverová chyba s obecnou zprávou.
- **Důkazy:** 7 izolovaných testů ve skutečném Chromu (bez přístupu k reálným účtům) testuje škodlivé texty i bez CSP, předání přesného názvu při kliknutí, připomínky a mapy, tabulky, chyby, přihlášení, přepojení všech statických akcí a skutečnou navigaci → úpravu → zrušení mazání. K tomu 12 dřívějších JS regresí a 246 serverových testů. Nové testy vstřikují výjimky s fiktivním heslem/SQL/osobními údaji a ověřují odpověď i výstup serveru.
- Běh prohlížečových testů: `npm ci --prefix tests/e2e --ignore-scripts`, potom `node --test tests/security/test_admin_browser.cjs`. Používají nový izolovaný profil Chrome a zachytí všechny požadavky; nepotřebují běžící server. Python lze zadat proměnnou `TEST_PYTHON`, kanál prohlížeče `TEST_BROWSER_CHANNEL`.

Postup vychází z [OWASP – prevence XSS](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html) a [MDN – CSP](https://developer.mozilla.org/en-US/docs/Web/Security/Practical_implementation_guides/CSP). CSP je doplněk opravy vykreslování, nikoliv náhrada auditu dalších cest.

## Hlavní starší web: vykreslování a události (1. 10. 2026)

- Původní skripty z `web/index.html` jsou v `legacy-app.js` a `legacy-lookups.js`. `legacy-actions.js` obsahuje výslovnou mapu 230 obsluh; argumenty zůstávají JSON daty, nikoliv spustitelným zdrojovým kódem. Přesunuté obsluhy zachovávají hodnotu pole, klávesové události i zastavení kliknutí na nadřazenou kartu.
- Doplněné kódování databázových textů a hodnot v HTML: vozidla a jejich úpravy, servisní záznamy, dokumenty, profily, kontakty, přehledy, připomínky, rezervace, chybové zprávy a podpůrné funkce. Statické části rozhraní a ikony zůstávají HTML; obsah uživatele je text.
- Odstraněno přepisování společné funkce `escapeHtml` slabší variantou v `ai-features.js`. Doplněk už nepovažuje `?admin=1` za roli administrátora a testuje skutečný výsledek funkce pro roli. Serverová autorizace zůstává rozhodující.
- Hlavní `/web/index.html` a jeho kořenové adresy nepovolují inline skripty ani události, cizí připojení, vložení celé administrace do rámu ani změnu základní adresy. Náhled přílohy má `sandbox` bez oprávnění skriptů; povolen je pouze jeho lokální blob. Odkazy odmítají spustitelné protokoly a HTTP adresy s vloženým jménem/heslem. Kontaktní odkazy zachovávají `mailto`.
- Diagnostika hlavního klienta již neloguje celé odpovědi API, tokeny, jména a vstupy ani je neschovává do ladicího přehledu. Přehled požadavků zachovává jen metodu, cestu bez query, stav a čas. Chybová konzole obsahuje pevné popisy bez dodatečných dat.
- Push notifikace používají pouze obrázky a cíle stejného původu. Kliknutí znovu kontroluje i dříve uložený obsah notifikace, aby nemohlo navigovat na cizí nebo spustitelnou adresu.
- Opravena funkční chyba: dostupnost modulů volala neexistujícího klienta API. Nyní se načítá přes existující autorizované volání.
- **Důkazy:** 10 nových izolovaných prohlížečových testů a 3 testy push. Ověřují škodlivé texty i bez CSP, skutečný přechod detail → editace vozidla/záznamu, formuláře servisního centra, přehledy rezervací a připomínek, původní SVG ikony, přesné předání uvozovek, všechny odkazy obsluh na existující funkce, omezený náhled přílohy, role, diagnostiku a načítání dostupnosti modulů. Běh: `node --test tests/security/*.cjs`.
- **Zbývající rozsah:** alternativní `index_minimal.html`, stránky s iframe, veřejné obnovovací/platební stránky a další skripty vyžadují vlastní inventuru; CSP výše se vztahuje pouze na hlavní starší rozhraní. Jeho historické trvalé úložiště tokenů, přechod mezi novou a starší správou, vypršení MFA a oddělení rozpracovaných dat při změně relace dosud nejsou uzavřené. Výše popsané testy vykreslení nenahrazují úplný produkční scénář více uživatelů.

## Matice návazností a důkazy

| Oblast | Kontrolovaná návaznost | Důkaz / zbývající ověření |
|---|---|---|
| Účty | Registrace → e-mailové ověření → přihlášení; servis → schválení administrátorem | Izolované testy account_flows a email_verification_flow; e-mailový transport je v těchto testech nahrazen testovací funkcí |
| Role | Uživatel / servis / admin → skutečná serverová oprávnění | Testy admin_roles, MFA a volitelného přihlášení; administrátorská role se nevytváří volbou na přihlášení |
| Obnova hesla | Jednorázový odkaz, expirace, neodhalování existence e-mailu, zrušení staré relace | Automatické testy account_flows + test stránky pro návrat do aplikace; aktuální skutečné doručení není součástí této noční dávky |
| Administrátor | Heslo → autentikátor → správa → vypršení → nové ověření | Serverové testy + 13 iOS jednotkových testů; samostatný iOS UI test ověřil, že restart neobejde povinné nastavení |
| Vozidla a servis | Vlastnictví → sdílení → záznamy → dokumenty | Regrese vlastnictví a ORV, opravy fotografií/PDF; úplné klikání všech servisních scénářů ještě zbývá |
| Soukromé soubory | Příjem obrázku → interní evidence → úložiště → oprávnění → fronta odstranění | Testy orv_durable_storage, repair_photo_report, account_erasure_graph |
| Export / odstranění | Vlastní data → bezpečný export → potvrzené smazání → odstranění souborů a MFA | Testy pro úplný export bez autentizačních údajů, mazání MFA záznamů, cizí vozidla, selhání úložiště a opakování |
| Platby | Ověřená transakce → účet → tarif; opakovaná/pozdní zpráva, refundace, souběh poskytovatelů | Automatické testy Apple/Comgate; skutečný App Store sandbox a TestFlight ještě nejsou hotové |
| Web | Přihlášení → druhý faktor → zabezpečená cookie → administrace | Serverové testy web_access a MFA; v prohlížeči ověřena výzva na odděleném syntetickém účtu |
| Vzhled | Ověření administrátora na telefonu | Zkontrolován skutečný snímek simulátoru; pole mají světlý podklad a tmavý text |

Testy nevytvářejí ani nemažou skutečné účty, nestrhávají platby a neposílají skutečné e-maily. Místní UI fixture je mimo repozitář serveru a nesmí být nasazena.

## Co stále brání vydání do světa

1. Dokončení osobních kroků vlastníka v App Store Connect, založení produktů/podepisovacích údajů a skutečný sandboxový nákup, obnova, refundace, serverové notifikace a TestFlight. Zaplacené členství samo tyto kroky nenahrazuje.
2. Nastavení autentikátoru vlastníkem hlavního administrátorského účtu. Klíč musí zůstat v jeho správě. Dokončit ověřený postup obnovy při ztrátě autentikátoru; nesmí vzniknout obejití druhého faktoru pouhou znalostí e-mailu.
3. Fotoaparát ověřený přímo na fyzickém iPhonu. Úspěch simulátoru nedokazuje funkčnost snímání; dřívější černý náhled a zelené fotografie nejsou uzavřená závada.
4. Úplná scénářová kontrola rezervací, připomínek, servisních vazeb, všech tlačítek a navigace s více oddělenými účty, včetně přerušení spojení a souběžných požadavků. Kontrola běhu na PostgreSQL a obnova zálohy do odděleného prostředí.
5. Dokončení bezpečnostní kontroly relací a ostatních alternativních/veřejných stránek/skriptů, starších samostatných záznamů chyb mimo opravené administrátorské API, závislostí, obnovy klíčů, provozních upozornění a limitů. Žádné tvrzení o stoprocentní nezneužitelnosti.
6. GDPR provozní část: potvrzené retenční lhůty a jejich provádění, zpracovatelé a smlouvy, úplnost exportovaných souborů/fotografií, přístup k zálohám, postup incidentu a finální informace o ochraně údajů. Technické testy neznamenají právní schválení.

Dokud nejsou otevřené body doložené, verze není označená jako připravená k veřejnému vydání.

## Aktuální výsledky

Po výše uvedených opravách prošlo **247 serverových regresí** (účty, oprávnění, MFA, export, odstranění, ORV, soukromé soubory, Apple/Comgate), **13 iOS jednotkových testů**, **1 iOS test obrazovky a restartu** a kompilace konfigurace Release pro iPhone. **32 JavaScriptových/prohlížečových testů** také prošlo (17 kontrol v Chromu + push, panel operátora a stránka ověření e-mailu). Testy plateb používají ověřovací testovací objekty, nikoliv skutečný nákup v App Storu. Výsledky samy nepotvrzují splnění otevřených bodů výše.

## Sjednocení relací obou administrací (1. 10. 2026)

- Hlavní starší i nová administrace používají společné přihlášení pouze v aktuální kartě. Staré trvale uložené tokeny/profily, uložená poloha a pozvánky se nepřebírají. Profil a oprávnění se vždy načítají ze serveru. Ověření vyžaduje výslovně administrátorskou roli a dosud platné silné ověření.
- Ověřený token se neposílá na jiný origin ani při přesměrování. Odstraněna stará identifikace přes e-mail a přesměrování API podle místního nastavení. Platí pro seznamy, úpravy, fotografie, přílohy, exporty, PDF i uploady.
- Změna/ukončení relace ruší čekající požadavky. Odpověď ze staré relace se nepřijme ani při opožděném těle JSON/fotografie; opožděná 401 nesmí ukončit nové přihlášení. Potvrzení odstranění připravené v předchozí relaci nespustí novou mutaci.
- Odhlášení skryje data a ruší lokální náhledy ihned i při výpadku serveru. Ostatní karty dostanou pouze náhodný signál bez identity/tokenů. Návrat ke stránce z paměti historie vyžaduje nové ověření; absolutní čas MFA platí i při návratu do skryté karty.
- Přihlášení/autentikátor po stisku „Začít znovu“ nepřijme starý rozpracovaný požadavek. Návrat z přihlášení má výslovný seznam místních cílů.
- Pozdní geolokace nesmí uložit data do nové relace. Dodatečně odstraněno uchovávání těla odpovědi v diagnostice VIN/ARES. Úspěšné prázdné odpovědi 204 starší klient nehlásí jako chybu.
- Ověřeno: **247 serverových kontrol** a **49 kontrol JavaScriptu / skutečného Chromu** na syntetických datech. Zahrnuje předchozí ochranu XSS/CSP a funkční návaznosti vozidel, záznamů, formulářů i administrátorských akcí. Žádná skutečná platba, e-mail, změna MFA vlastníka ani mazání skutečných záznamů.
- Praktické meze: přerušení požadavku v prohlížeči nevrací již dokončenou změnu na serveru. Stažený dokument nelze odvolat z cizího úložiště. Samostatné odvolání serverového JWT doplňuje navazující část tohoto auditu. Alternativní webové stránky a dosud otevřené oblasti auditu musí být dořešeny před vydáním.

## Trvalé odhlášení a bezpečné opakování (1. 10. 2026)

Předchozí otevřený bod o platnosti tokenu po odhlášení řeší tato změna:

- Každé vydání přístupu má vlastní náhodný identifikátor. Server ukládá pouze jednosměrný otisk odvolaného přístupu a expiraci; původní token ani osobní údaje se do seznamu neukládají. Kontrola platí i pro volitelné přihlášení a webovou cookie. Výpadek úložiště ověření nepovolí přístup.
- Odhlášení je opakovatelné, funguje i před ověřením e-mailu či při prošlém MFA, přežije restart serveru a neukončuje jiná zařízení. Tabulka vzniká přidáním při startu; zákaznické záznamy se nemění. Propadlé otisky se uklízejí při dalších odhlášeních.
- Nový přístup obsahuje zvlášť podepsané potvrzení použitelné pouze k jeho zrušení. Nemá identitu účtu a nelze s ním otevřít API ani administraci. Díky němu může klient zopakovat odhlášení po výpadku bez uchování použitelného přihlašovacího klíče. Web ukládá pouze toto omezené potvrzení, iOS používá chráněný Keychain a svázání s původním serverem.
- Pozdní webové odhlášení pracuje se zachyceným přístupem, ne s novou sdílenou cookie. Odpověď neposílá odstranění nové cookie. Lokální obsah je skrytý ihned. Dokud server nepotvrdí odhlášení, klient to uvádí jako čekající stav.
- iOS zachová odhlášený stav i při neúspěšném odstranění staré položky Keychain. Opětovné odeslání nesmí změnit mezitím přihlášeného uživatele. Přesměrování API zachová autorizaci pouze na stejném originu; cizí host, port nebo změna protokolu jsou odmítnuté. Chybová hlášení neukazují syrové odpovědi serveru.

Doloženo: 273 serverových regresí, 53 JavaScriptových/Chrome testů a 19 iOS jednotkových testů. Samostatná podepsaná aplikace ověřila skutečný Keychain, opětovné spuštění a zablokování zbylého starého tokenu. Transportní test se skutečnými místními HTTP servery ověřil přesměrování JSON, binárního i prázdného požadavku, nepředání údajů jinému cíli a požadavek na výslovné potvrzení odhlášení. Vše se smyšlenými údaji.

Meze: server nelze vzdáleně informovat bez spojení; token zůstává platný do doručení odhlášení nebo expirace. Staré přístupy vydané před touto změnou nemají samostatné potvrzení pro opakování; klient je neuchovává a po neúspěšném online pokusu hlásí omezení. Změna hesla ruší všechna přihlášení. Kontrola fyzického fotoaparátu, App Store a ostatní otevřené body nejsou tímto uzavřené.

## Hranice iOS serveru a import údajů vozidla (1. 10. 2026)

- iOS Release přijímá pouze oficiální HTTPS server. Staré vývojové nastavení ani změna UserDefaults nepřesměrují existující přihlášený klient. Keychain odděluje přihlašování podle serveru; migrace starého klíče je povolená jen k oficiální adrese. Výchozí síťová relace nesdílí cookies, přihlašovací údaje ani mezipaměť. Kontrola dostupnosti ověřuje obsah odpovědi a nebere přihlašovací HTML za zdravý server.
- Odkazy tachometru používají přesný protokol, doménu a port, nikoli porovnání začátku textu. Platí pro odkazy dokumentů v iOS i stažení captcha, detailu a odeslání formuláře na serveru. Každé přesměrování se ověřuje před dalším odesláním; tělo VIN/captcha/token se neposílá jinam. Není zapnuté načítání náhodných `.netrc` přístupů.
- Odpovědi poskytovatele mají limit dekomprimované velikosti, včetně těla přesměrování. Obrázek se ověřuje jako podporovaný rastr; HTML/SVG či vadný soubor se uživateli nepředá. Celkový počet rozpracovaných ověření i počet na účet je omezený. Chybné odpovědi neobsahují technické chyby poskytovatele.
- Ověření captcha je svázané s konkrétním přihlášeným účtem a podle typu také vozidlem/VIN. Současný druhý pokus je odmítnutý; po úspěchu není opakovaně použitelný. Chybně přepsaný kód lze opravit. Před uložením se po odpovědi poskytovatele znovu kontroluje oprávnění a aktuální VIN.
- Import získá databázový zámek řádku vozidla před hledáním existujících záznamů. Opakovaný import znovu použije servisní záznam a historii; funguje i při neznámém datu prohlídky. Skutečný souběh různých PostgreSQL procesů dosud tímto testem doložený není.
- Výpis vozidel při chybě serializace neskrývá vadný záznam jako prázdný účet. Chyba je výslovná a obsahuje jen náhodný kód pro podporu. Při vytváření/výpisu vozidla se do logů nevypisují e-maily, VIN, SPZ, SQL parametry ani text výjimky.

Ověření: 330 společných serverových regresí prošlo; následné rozšířené cílené testy tachometru ověřují také skutečnou přesměrovací vrstvu knihovny requests pomocí izolovaného transportu. Testy používají výhradně syntetické odpovědi, nevytvářejí zákaznické záznamy a neřeší skutečnou captcha. iOS: 20 nativních testů a nový test bezpečných odkazů, samostatná podepsaná kontrola Keychain po restartu, kontroly Release/Development adres i skutečných lokálních HTTP požadavků. Podepsaná sestava v hlavním simulátoru i zrcadlový projekt a Release kompilace prošly. Přihlášení vlastníka zůstalo zachováno a brána nastavení MFA zůstala zamčená.

Meze importu: rozpracované captcha jsou dosud pouze v paměti jednoho serverového procesu, po restartu je nutný nový obrázek. Před víceprocesovým provozem je nutné společné úložiště nebo směrování relace. Skutečné chování externího portálu po ručním přepsání kódu zůstává k ověření vlastníkem. PostgreSQL souběh, obnova záloh, ostatní otevřené funkční a právní body nadále zůstávají v seznamu před vydáním.

## Oddělení čtení vozidla od úprav a návaznosti iOS (1. 10. 2026)

- Schválený servisní přístup nyní respektuje i samostatný příznak čtení historie. Pouhá existence schválené vazby nestačí. Vypnutí čtení nebo odvolání vazby zavře běžný detail, historii i nové zápisy.
- Úprava profilu vozidla, úvodní fotografie a import STK vyžadují vlastníka nebo administrátora. Servis používá povolené nové servisní záznamy a fotodokumentaci oprav. Servisní zápis kilometrů vyžaduje oprávnění přidávat záznamy, zachová identitu servisu a konkrétního souhlasu; servis nesmí snížit aktuální nájezd cizího vozidla ani zasláním potvrzovacího příznaku.
- Kontrola zápisu příloh a vytěžení dokladů proběhne před dekódováním, uložením či zpracováním souboru. Dříve část cest ověřovala jen právo číst, případně ověřovala zápis až po uložení souboru.
- Sdílený detail vozidla neposílá servisům skeny/číslo registračního dokladu, soukromou poznámku vlastníka, pojišťovnu ani e-mail/tenant vlastníka. Technické údaje a povolená historie zůstávají dostupné. Vlastník se ověřuje podle aktuální vlastnické vazby, nikoli jen shody e-mailu.
- Smíšený účet se staršími i novějšími vlastnickými vazbami nyní zobrazí všechna oprávněná vozidla. Opakované načtení nevytvoří duplicitu a neobnoví dříve odvolané vlastnictví; jiný tenant zůstává vyloučený.
- Server vrací výslovné možnosti konkrétního vozidla. iOS podle nich nabízí fotografii, zápis km, import STK, přidání/úpravu historie i založení fotodokumentace. Chybějící oprávnění nezpřístupní zápis. Lokální režim vrací pouze funkce, které skutečně implementuje.
- Změna přihlášené relace invaliduje dočasně uložený detail; opožděná odpověď staré relace nepřepíše nový účet. Odmítnutí přístupu při obnovení odstraní detail, historii a oprávnění z mezipaměti. Odstraněna náhradní iOS cesta, která při chybě endpointu kilometrů upravila pouze vozidlo bez auditního záznamu.
- Starší vlastní chybové handlery servisních záznamů a PDF už nevypisují obsah výjimky do logů/odpovědi. Zůstává náhodný diagnostický identifikátor, typ a místo chyby.

Důkazy: `tests/api/test_vehicle_permission_boundaries.py` — 37 izolovaných testů HTTP rozhraní nad dočasnou SQLite databází. Pokrývají vlastníka, stejného i cizího tenanta, povolený a cizí servis, admina/developer_admin, read-only souhlas, odvolání, přiřazení auditního zápisu, zachování vlastní fotodokumentace servisu, soukromé chyby a smíšenou historii vlastnictví. Zakázané požadavky jsou opatřené pastí na přístup k souborům, parseru a síti. Přihlášení/MFA testují samostatné bezpečnostní testy; tyto scénáře je nenahrazují. iOS jednotkové testy pokrývají chybějící oprávnění, změnu relace, opožděnou odpověď a výpadek auditního endpointu; lokální úložiště ověřuje zachování dostupných funkcí.

Meze: SQLite nedokládá souběh PostgreSQL. Na skutečných zákaznících nebyly měněny záznamy, oprávnění, MFA ani soubory. Dříve stažené kopie nelze odvolat z cizího zařízení. Přístup servisu k jeho vlastním fotografiím oprav po odvolání sdílení zůstává zachován podle dosavadní funkce; definitivní retenční pravidla, exporty a právní podklady jsou samostatným otevřeným bodem. Vydání do App Storu, fyzický fotoaparát a ostatní otevřené body nejsou tímto dokončené.

## Přílohy: překročení hranice vozidla (1. 10. 2026)

Izolovaný reprodukční test potvrdil chybu: držitel přístupu k vozidlu A mohl sestavit cestu obsahující jeho adresář a následné `../`, která po normalizaci mířila k existující příloze vozidla B. Původní endpoint kontroloval pouze přítomnost textového segmentu; v testu vrátil 200 a cizí syntetický soubor. To dokládá zranitelnost, nikoli skutečný historický únik zákaznických dat.

- Správce souborů nyní vyžaduje výslovné ID již autorizovaného vozidla. Klíč musí přesně odpovídat `tenant_N/vehicle_ID/nazev_souboru`; absolutní cesty, rodičovské segmenty, backslash, řídicí znaky, další podadresáře i symlinky jinam jsou odmítnuté před lokálním/externím čtením.
- Stejná hranice platí při automatickém obnovování vytěžených údajů ze starších příloh. Podvržené metadata vlastního servisního záznamu nesmějí nechat parser číst soubor jiného vozidla. Nový nebo upravovaný záznam odmítne cizí `storage_key` i alternativní `path`.
- Historická příloha vozidla zůstává čitelná po převodu do jiného tenanta. Autoritu tvoří stabilní ID vozidla, nikoli jeho dnešní vlastník/adresář tenanta. Žádné soubory se kvůli této opravě nepřesouvají ani nemažou.
- Stažení výslovně vrací `private, no-store` a `nosniff`.

Důkazy: 21 nových testů `test_service_attachment_boundaries.py` a 37 předchozích multi-role testů prošlo. Reproduktor původně selhal očekávaným 200 místo 403; po opravě odmítne požadavek ještě před voláním úložiště. Funkční testy současně ověřují stažení správné přílohy, vložení do záznamu, obnovení jejího obsahu pro parser a historický adresář po převodu. Starší test obnovení vytěženého přehledu byl přesunut výhradně do dočasného adresáře a doplněn o ID vozidla; nečte cloudové soubory. Všechny soubory a osoby jsou testovací. Další typy úložišť, retenční politika a posouzení historie přístupů zůstávají samostatnou součástí auditu.


## Odvolání souhlasů, převody a PostgreSQL souběh (1. 10. 2026)

Nalezené chyby byly reprodukované výhradně na syntetických účtech: odpojení servisního kontaktu a nahrazení servisu měnilo jen starší `service_vehicle_access`, zatímco současná autorita `vehicle_service_links` zůstávala schválená. Interní převod navíc přepisoval vlastníka schváleného souhlasu místo jeho odvolání. Osm z devíti počátečních regresních scénářů před opravou selhalo.

- Odpojení/nahrazení, odebrání vozidla, převod i administrátorské přeřazení používají společné odvolání. Uzavřou aktuální i historické oprávnění a příslušné čekající žádosti. Historie oprav a servisní fotodokumentace se nemaže.
- Starý souhlas nepřejde na nového vlastníka; ten musí udělit vlastní. I chybně obnovená stará schválená vazba se při čtení porovnává s aktuálním vlastníkem. Servisní seznamy používají stejnou kontrolu a respektují rozsah čtení.
- Požadavky na schválení, odebrání/převod a servisní zápisy se řadí přes společný zámek vozidla. Po získání zámku se znovu načte aktuální vlastnictví/souhlas. Duplicitní rozhodnutí vrací 409. Opakované přidělení vlastnictví nevytváří další aktivní řádek.
- Při převzetí stejného již existujícího VIN současně dvěma účty uspěje pouze jeden. Před změnou se znovu ověřuje VIN. Nově vytvořená vazba při migraci starého vlastníka se zohlední hned v témže požadavku, takže ji cizí účet nemůže přeskočit.
- Administrátor může odebrat vazbu skutečného vlastníka (dříve akce nesprávně hledala vlastnictví samotného administrátora). Chyby upravených operací vracejí obecný popis, nikoli SQL či interní výjimku. Vnější autentizace/MFA zůstává povinná.
- Převod staršího oprávnění už nikdy neobnovuje výslovně odvolaný souhlas.

Ověření: 407 společných serverových testů prošlo, následný test ochrany legacy VIN a související scénáře 19/19 (celkem 408 unikátních kontrol v sadě). Nových 16 SQLite scénářů je v `tests/api/test_vehicle_sharing_lifecycle.py`. Skutečný PostgreSQL 17.11: 10 integračních scénářů, paralelní oddělená spojení (až 6 současně), import s datem i bez data, jeden vítěz převodu, opakovaná vlastnická vazba, ztráta souhlasu během zápisu, duplicitní oprava, souběžné žádosti/rozhodnutí a trvalé odhlášení. Testovací cluster přijímá pouze lokální Unix socket, nikoli síťová spojení; po testu se zastaví. Žádné zákaznické řádky ani dokumenty se neměnily.

## Ověření obnovy a dosud chybějící provozní zálohy (1. 10. 2026)

`tests/postgresql/test_backup_restore.py` provedl skutečný `pg_dump` a `pg_restore --single-transaction --exit-on-error` do nově vytvořené prázdné databáze. Porovnává kontrolní otisky a počty všech 43 registrovaných tabulek, 11 syntetických řádků a 2 souborů. Po obnově ověřil i vazby servisní evidence, odvolané oprávnění, neplatnost odhlášené relace a pokračování sekvence nových ID. Výstupní manifest je v místních podkladech `work/v1-postgresql-restore-manifest.json`.

Jde o ověření mechanismu obnovy syntetických dat. Není to důkaz úplné obnovitelnosti produkce ani všech modulů/importů, cloudových objektů, šifrovacích klíčů nebo opětovného uplatnění pozdějších výmazů. [PostgreSQL uvádí konzistentní snapshot pg_dump](https://www.postgresql.org/docs/17/backup-dump.html); soubory mimo databázi, aplikační konfigurace a klíče musí mít vlastní koordinovaný postup.

Přímá kontrola Supabase Dashboard → Database → Backups potvrdila **Free Plan does not include project backups**. Žádný nový tarif ani placená služba nebyly aktivované. Stávající administrátorský panel správně označuje svou lokální zálohu jako SQLite-only; nepokrývá aktuální PostgreSQL + Supabase Storage. Starý `scripts/backup_volume_data.sh` míří na původní Hetzner/SQLite a nebyl spuštěn. Před vydáním je potřeba doplnit automatické šifrované zálohy databáze i souborů, oddělené uložení a obnovu klíčů, retenci, kontrolu poslední úspěšné zálohy a zkoušku úplné obnovy bez oživení odstraněných dat.

Další návazné auditní body: přidání zcela nového stejného VIN různými cestami (současná oprava pokrývá převzetí existujícího řádku), důkaz oprávněnosti převodu uvolněného VIN a oddělení osobních údajů původního vlastníka od technické historie, ruční záznamy/km při opakování offline požadavku, další typy souborů a rezervace/připomínky. Veřejné vydání stále není schválené.


## VIN není doklad vlastnictví, souběžné založení a obnova profilu (1. 10. 2026)

Předchozí kontrola souběhu převzetí existujícího VIN neověřovala oprávněnost samotného převzetí. To bylo bezpečnostní riziko: po odebrání vozidla ze starého profilu jej mohl jiný přihlášený účet převzít podle veřejně známého VIN, včetně původních soukromých údajů. Nové chování nahrazuje původní volné `vin_claim`:

- Přidání existujícího VIN jiným účtem vrací obecné odmítnutí bez údajů vlastníka, záznamů nebo příloh. Automatické převzetí cizího uvolněného profilu není povolené. Přeřazení na jiný účet nyní vyžaduje ověřeného administrátora; jeho existující cesta nadále podléhá serverovému MFA. Úplný samoobslužný převod se souhlasem obou stran a oddělením starých osobních údajů zůstává samostatným bodem před vydáním.
- Obnovit odebraný profil může poslední vlastník. Dřívější vlastník po následném prodeji/přeřazení tuto možnost nemá. Pouhá shoda starého e-mailového aliasu nepostačuje. Nejednoznačné historické vlastnické období nebo několik starších záznamů téhož VIN se automaticky nepřiřazuje.
- Předregistrace servisem bez historie vlastnictví vyžaduje účet příjemce, ověření jeho e-mailu podle stávajících pravidel registrace, odpovídající původní servisní vazbu a platnou pozvánku (nebo dříve přijatou pozvánku vázanou na tento účet). Převzetí zruší původní servisní přístup; další sdílení musí zákazník schválit.
- Nový VIN i jeho změna procházejí společnou kontrolou všech ORM zápisů: uživatelské přidání, servisní předregistrace/přidání klientovi, administrace a starší aplikační modely. Normalizují se velikost písmen a oddělovače. PostgreSQL drží transakční zámek i pro dosud neexistující VIN; po čekání znovu čte skutečnou databázi. SQLite získá před kontrolou zámek pro zápis. Bez VIN může existovat více vozidel. Již existující staré duplicity se nemažou ani neslučují. Přímé SQL importy obcházející modely nejsou tímto chráněné a vyžadují vlastní kontrolu.
- Obnova vlastníka znovu nepřičte tentýž profil do limitu tarifu, ale stále ověřuje aktivní licenci. Kontrola limitu při uživatelském přidání je ve stejné transakci jako uložení; nevytvoří samostatný commit licence ani neuvolní zámek vozidla. Dvě různá VIN přidávaná současně stejným uživatelem nepřekročí jeho limit. Zámek tenanta používá `FOR NO KEY UPDATE`, aby neblokoval kontrolu cizího klíče jiného zapisujícího a nevzniklo vzájemné čekání s VIN.
- iOS před odebráním žádá potvrzení. V serverovém režimu vysvětluje uchování historie a zrušení přístupů; lokální režim uvádí odstranění testovacích dat v zařízení.

Ověření: společná serverová sada 419/419; následné rozšíření a cílené kontroly licence a vlastnictví 35/35, včetně nového odmítnutí neaktivní licence (420 unikátních scénářů ve společné sadě). Finálních 12 kontrol VIN/autority prošlo po doplnění návaznosti pozvánek. Izolovaný PostgreSQL: 15/15, včetně souběhu uživatel/servis/admin, dvou změn VIN, dvou neoprávněných převzetí, čtyř obnov vlastníka, dvou různých VIN proti limitu a rollbacku kontroly licence. Souběžný test nejprve odhalil databázové vzájemné blokování; po změně typu zámku prošel. Nikdy se netestovalo na zákaznických záznamech.

Otevřeno před vydáním: oddělení původních osobních polí, faktur a fotografií od technické historie při administrátorském i budoucím samoobslužném převodu; kontrola limitů v ostatních servisních cestách; produkční zálohy a obnova; ostatní dříve zapsané funkční, provozní, právní a App Store kroky. Tato etapa není schválením veřejného vydání ani zárukou, že nemůže dojít k bezpečnostnímu incidentu.
