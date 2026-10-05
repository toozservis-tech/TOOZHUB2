# Zákaznický web — 5. 10. 2026

Vstup: `/web/customer.html`, kořen serveru na něj přesměrovává. Stránka `/web/open-app.html` nabízí web i iOS. Stávající účty používají stejné API, databázi a serverové limity jako mobilní aplikace. Administrace zůstává na `/admin-login` s původním MFA a cookie gate.

Web znovu používá udržované rozhraní `web/index.html` přes samostatnou odpověď se zákaznickým session skriptem. Zveřejněny jsou pouze konkrétní statické závislosti, nikoli staré alternativní HTML nebo zálohy. Token zůstává v sessionStorage, nikdy v localStorage, žádné credentials nejsou v souborech. Odchozí autorizované požadavky jsou omezené na stejný origin. Při změně účtu jsou rozpracované odpovědi zahozeny. Nový neověřený účet má samostatnou obrazovku pro ověření e-mailu.

Oprava ručních servisních úkonů Free: neposílat implicitní dokumentová metadata, která server správně odmítal jako placenou funkci. Formulář skryje placené dokumentové vstupy. Server nadále vynucuje limit 2 úkonů. VIN hlášky odpovídají dostupnosti od Basic.

Ověření na lokální izolované SQLite databázi a smyšlených účtech v Chromu: přihlášení, obnovení stránky, přidání vozidla, detail, dva ruční úkony Free, odmítnutí třetího, připomínky, rezervace, nastavení, odhlášení, druhý účet nevidí vozidlo prvního. Kontrola šířky 390 px. Automatické testy: veřejné soubory versus chráněná administrace, revokace relací, CSP, zákaz úniku tokenu na cizí origin, zákaz admin tokenu v zákaznické relaci a opožděná odpověď po přepnutí účtu.

Webové platby používají stávající serverové nastavení Comgate. Tato změna neaktivuje bránu ani neprovádí žádný skutečný nákup. Úspěšný placený checkout, skutečný Android a úplná shoda všech pokročilých iOS obrazovek nejsou touto kontrolou potvrzeny.
