# SprávaVozidel 1.0.0 — kontrola před prvním vydáním

Stav 1. 10. 2026: příprava vydání, nikoliv souhlas s veřejným spuštěním. Historické interní verze a Git historie zůstávají zachované; první veřejná verze aplikace má číslo **1.0.0**, sestavení 1.

## Opravy z aktuální kontroly

- Aktivní dvoufázové ověření nelze přepsat novým nastavením. Příprava autentikátoru vyžaduje současné heslo a vyprší po 10 minutách.
- Chybějící nebo poškozený klíč u aktivního ověření zastaví přihlášení; nesmí změnit přihlášení na pouhé heslo.
- Použitý TOTP kód nelze přijmout znovu. Výzvy jsou v databázi uložené pouze jako otisk; pokusy a časová omezení přežijí restart aplikace/serveru.
- Databáze ukládá klíče autentikátoru šifrovaně. Platná starší nastavení se při startu převedou bez změny kódů v telefonu. Podmínky rotace klíče viz `ADMIN_MFA.md`.
- Administrátor potřebuje heslo + autentikátor. Přístup ke spravovaným datům je podmíněn ověřením z posledních 15 minut. Kontrola platí na serveru pro běžné API, volitelné přihlášení i webovou cookie.
- iOS i web vedou administrátora nastavením/obnovou ověření; přihlašovací obrazovky obsahují jen uživatelský popis. Změna faktoru zneplatňuje předchozí relace a klient uloží náhradní relaci.
- Webová administrace nepřijímá token v URL a neukládá jej do trvalého úložiště prohlížeče. Nadále používá token v úložišti aktuální karty; to samo o sobě neřeší případný XSS útok. Nová administrace nyní používá kontextové kódování textů a atributů a oddělené události tlačítek; starší rozhraní `web/index.html` zůstává otevřenou částí auditu.
- **Opraven únik do exportu vlastních dat:** dříve se automaticky exportovaly i sloupce `password_hash`, `totp_secret`, tokeny pozvánek a klíče push notifikací. Nyní je seznam exportovaných polí výslovný; nová databázová pole se bez kontroly do exportu nepřidají. Soukromé interní chybové zprávy se neexportují.
- Neošetřené chyby a HTTP 500 nevracejí obsah výjimky/SQL poskytovatele klientovi. Bezpečná hranice zapisuje identifikátor chyby, typ a šablonu cesty. Parametry SQL jsou skryté i v místní databázi. Další jednotlivá starší místa vlastního logování je nutné dál prověřovat.

## Navazující kontrola webu a chyb (1. 10. 2026)

- Opravené uložené XSS v nové administraci: kompaktní seznam uživatelů, vozidla, servisy, servisní záznamy, audit a chybové zprávy. Dříve se některé hodnoty vkládaly přímo jako HTML.
- Společné kódování nyní chrání také obě uvozovky v atributech nastavení. Mapové odkazy přijímají pouze HTTP/HTTPS bez vloženého jména/hesla.
- Uživatelský text není součástí JavaScriptu tlačítek: argumenty jsou JSON data a obsluha je ve výslovném seznamu povolených akcí. Všechny statické `onclick`/`onsubmit` nové administrace byly převedeny na události ve skriptu.
- Přihlášení, `/web_admin/` i jeho alternativní cesta `/admin-static/` mají přísnější CSP: žádné inline skripty/události, eval, objekty, cizí formuláře, rámce ani změna základní adresy stránky. Přihlašovací skript je samostatný soubor. Toto opatření **zatím neplatí pro rozsáhlé starší `web/index.html`**; jeho úplná kontrola je stále podmínkou vydání.
- Administrátorské API už nevypisuje celé výjimky ani SQL dotazy. Bezpečná diagnostika zachovává náhodné číslo chyby, její typ a umístění ve zdrojovém kódu; neformátuje zprávu výjimky, její parametry, lokální proměnné ani zdrojový řádek. Stejné číslo se předává přes navázané výjimky až ke klientovi. Náhled zdraví a audit selhaných akcí neukládají syrovou databázovou chybu.
- Selhání načtení počtů, záznamů a auditu se hlásí jako chyba, nikoliv úspěšná prázdná databáze. Selhání uložení připomínek je serverová chyba s obecnou zprávou.
- **Důkazy:** 7 izolovaných testů ve skutečném Chromu (bez přístupu k reálným účtům) testuje škodlivé texty i bez CSP, předání přesného názvu při kliknutí, připomínky a mapy, tabulky, chyby, přihlášení, přepojení všech statických akcí a skutečnou navigaci → úpravu → zrušení mazání. K tomu 12 dřívějších JS regresí a 246 serverových testů. Nové testy vstřikují výjimky s fiktivním heslem/SQL/osobními údaji a ověřují odpověď i výstup serveru.
- Běh prohlížečových testů: `npm ci --prefix tests/e2e --ignore-scripts`, potom `node --test tests/security/test_admin_browser.cjs`. Používají nový izolovaný profil Chrome a zachytí všechny požadavky; nepotřebují běžící server. Python lze zadat proměnnou `TEST_PYTHON`, kanál prohlížeče `TEST_BROWSER_CHANNEL`.

Postup vychází z [OWASP – prevence XSS](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html) a [MDN – CSP](https://developer.mozilla.org/en-US/docs/Web/Security/Practical_implementation_guides/CSP). CSP je doplněk opravy vykreslování, nikoliv náhrada auditu dalších cest.

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
5. Dokončení XSS auditu staršího `web/index.html` a ostatních veřejných stránek/skriptů, starších samostatných záznamů chyb mimo opravené administrátorské API, závislostí, obnovy klíčů, provozních upozornění a limitů. Žádné tvrzení o stoprocentní nezneužitelnosti.
6. GDPR provozní část: potvrzené retenční lhůty a jejich provádění, zpracovatelé a smlouvy, úplnost exportovaných souborů/fotografií, přístup k zálohám, postup incidentu a finální informace o ochraně údajů. Technické testy neznamenají právní schválení.

Dokud nejsou otevřené body doložené, verze není označená jako připravená k veřejnému vydání.

## Aktuální výsledky

Po výše uvedených opravách prošlo **246 serverových regresí** (účty, oprávnění, MFA, export, odstranění, ORV, soukromé soubory, Apple/Comgate), **13 iOS jednotkových testů**, **1 iOS test obrazovky a restartu** a kompilace konfigurace Release pro iPhone. **19 JavaScriptových/prohlížečových testů** také prošlo (7 nových prohlížečových kontrol + panel operátora a stránka ověření e-mailu). Testy plateb používají ověřovací testovací objekty, nikoliv skutečný nákup v App Storu. Výsledky samy nepotvrzují splnění otevřených bodů výše.
