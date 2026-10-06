# Zákaznický web — 5. 10. 2026

Vstup: `/web/customer.html`, kořen serveru na něj přesměrovává. Stránka `/web/open-app.html` nabízí web i iOS. Stávající účty používají stejné API, databázi a serverové limity jako mobilní aplikace. Administrace zůstává na `/admin-login` s původním MFA a cookie gate.

Web znovu používá udržované rozhraní `web/index.html` přes samostatnou odpověď se zákaznickým session skriptem. Zveřejněny jsou pouze konkrétní statické závislosti, nikoli staré alternativní HTML nebo zálohy. Token zůstává v sessionStorage, nikdy v localStorage, žádné credentials nejsou v souborech. Odchozí autorizované požadavky jsou omezené na stejný origin. Při změně účtu jsou rozpracované odpovědi zahozeny. Nový neověřený účet má samostatnou obrazovku pro ověření e-mailu.

Oprava ručních servisních úkonů Free: neposílat implicitní dokumentová metadata, která server správně odmítal jako placenou funkci. Formulář skryje placené dokumentové vstupy. Server nadále vynucuje limit 2 úkonů. VIN hlášky odpovídají dostupnosti od Basic.

Ověření na lokální izolované SQLite databázi a smyšlených účtech v Chromu: přihlášení, obnovení stránky, přidání vozidla, detail, dva ruční úkony Free, odmítnutí třetího, připomínky, rezervace, nastavení, odhlášení, druhý účet nevidí vozidlo prvního. Kontrola šířky 390 px. Automatické testy: veřejné soubory versus chráněná administrace, revokace relací, CSP, zákaz úniku tokenu na cizí origin, zákaz admin tokenu v zákaznické relaci a opožděná odpověď po přepnutí účtu.

Webové platby používají stávající serverové nastavení Comgate. Tato změna neaktivuje bránu ani neprovádí žádný skutečný nákup. Úspěšný placený checkout, skutečný Android a úplná shoda všech pokročilých iOS obrazovek nejsou touto kontrolou potvrzeny.


## Rozšíření zákaznického webu — 6. 10. 2026

Doplněn přehled s náklady a statistikami, archiv vlastnictví, příchozí pozvánky servisů, ruční zápis kilometrů, úprava technických údajů, načtení km/STK s uživatelem vyplněnou CAPTCHA, čtení fotodokumentace oprav a serverový PDF report. Přidání vozidla nyní nabízí VIN/číslo ORV, lokální dekódování QR pomocí přibaleného jsQR 1.4.0 (licence v `web/vendor`) a fotografie obou stran pro serverové rozpoznání dokladu bez QR. Výsledek se vždy kontroluje před uložením; samotné načtení nic nevytváří.

Nové obrazovky používají stávající autorizované API; tato změna nepovoluje další práva a neupravuje databázové schéma. Rozpracované dialogy a importní údaje se zahodí při ukončení relace. Odpovědi patřící starému účtu se nepoužijí. Statické soubory jsou povolené jednotlivě a CSP zůstává zachované.

Ověřeno: 83 Python testů (veřejný web, administrativní hranice, kilometry, souhlas s pozvánkou, soukromí vlastnictví a ORV) a 7 Node testů (identifikátory, přenos SPZ, izolace relací). V lokálním Chromu se smyšlenými daty ověřeno: přehled/statistiky, prázdný i naplněný archiv s historií, odmítnutí pozvánky s vlastním potvrzovacím dialogem, zápis kilometrů, změna motoru, ruční ORV i QR z galerie, kontrola SPZ a vytvoření vozidla, stažený PDF a rozložení na 390 px. Volání registru a pozvánky používají místní testovací odpovědi; ukládání vozidel, kilometry, statistiky a archiv používají skutečné API nad oddělenou SQLite.

Omezení této kontroly: nebylo ověřeno focení na skutečném Androidu, OCR skutečného dokladu ani živé zadání CAPTCHA registru. Úplná shoda všech iOS funkcí není tvrzena; lokální iOS šablony ani systémové funkce telefonu nejsou tímto automaticky přeneseny na web.
