# SprávaVozidel – Comgate a předplatné

Přeneseny původní tarify: Basic 99 Kč měsíčně / 990 Kč ročně (5 vozidel), Premium 299 Kč / 2 990 Kč (bez limitu). Free: 1 vozidlo. Funkce se čtou ze stejného licencování jako zbytek aplikace. Provozovatel, kontakty a odkazy na původní dokumenty jsou v katalogu; nebyly vytvořeny nové právní podmínky.

## Obsluha

iOS: Profil → Tarify a předplatné. Správce: Provoz → Platby a licence → Stav připojení Comgate. Web: Nastavení → Comgate → Ověřit spojení s Comgate. Ověření připojení nic neúčtuje. Heslo brány je zapisovatelné, jeho původní hodnota se do klienta nevrací.

Vyberte období a tarif, zkontrolujte konečnou cenu, samostatně potvrďte souhlasy. Brána se otevírá přes SFSafariViewController. Návrat `spravavozidel://payment` jen aktualizuje stav. U neuzavřené platby lze pokračovat v historii. Vypnutí automatického prodlužování zachová zaplacené období. Změna pravidelného tarifu se projeví při příští platbě.

## Dokončení připojení původního obchodu

Původní schválený obchod `toozservis.cz`, propojení `507933`. Dne 29. 9. 2026 byly po schválení vlastníkem uloženy původní údaje pouze do serverového nastavení, v portálu byly změněny návratové adresy a potvrzování plateb na `app.toozservis.cz`. Povolené IP jsou aktuální rozsahy Renderu `74.220.51.0/24` a `74.220.59.0/24`; původní IP byla nahrazena. Skutečné spojení přes seznam platebních metod bylo potvrzeno ve webové administraci i v iOS. Testovací režim zůstává zapnutý.

Před ostrým provozem je nutné dokončit:

- ověření oprávnění pro opakované karetní platby;
- povolené odchozí IP adresy nasazeného serveru (nepovolovat plošně všechny IP);
- potvrzování výsledku: `https://app.toozservis.cz/api/v1/license/comgate/result`;
- všechny návratové adresy: `https://app.toozservis.cz/web/payment-return.html`;
- testovací platbu a doručení výsledku, poté teprve skutečný režim;
- běh kontroly předplatného a dostupnost serveru i bez otevřené aplikace. Uspávaný bezplatný server sám nezaručuje včasnou automatickou obnovu. Je třeba zajistit pravidelné spouštění; pouhé zapnutí přepínače Comgate tento problém neřeší.

Klíč ani platné odkazy na platbu nepatří do Gitu. Aktivní propojení v portálu samo o sobě neprokazuje připravenost celého průchodu. Ostrá platba nebyla při implementaci provedena. Schválení distribuce digitálního předplatného přes externí bránu v App Store je samostatný krok před vydáním do obchodu.

## Ochrany

Server kontroluje cenu, měnu, obchod, identifikátor, referenci a testovací režim oproti uložené objednávce. Aktivuje pouze PAID, nikoli AUTHORIZED. Testovací úhrada je pouze auditní záznam. Aktivace licence a potvrzení platby se zapisují v jedné transakci. Souhlasy zůstávají dohledatelné. Stejné ID objednávky nevolá založení platby podruhé. Nejasný výsledek při výpadku zůstává rezervován pro kontrolu správcem – automatické opakování by mohlo zákazníka zpoplatnit dvakrát. Pravidelné platby mají samostatnou rezervaci pro každé období a čekající transakce se ověřuje, nezakládá znovu.

## Ověření

30. 9. 2026: přihlášená iOS aplikace ověřila spojení s Comgate a načetla skutečný katalog. Při přípravě testovací objednávky původního účtu byl opraven nesoulad jednorázové nabídky a požadavku `initRecurring`. Jednorázová objednávka nyní žádné oprávnění k opakovaným platbám nevyžaduje. Klient posílá `expected_recurring`; změna způsobu prodlužování mezi nabídkou a odesláním se odmítne ještě před bránou. Starší klient dostane požadavek na aktualizaci. Telefon plátce se zbytečně nepředává, kontaktem je e-mail. Přesný připravený serverový stav prošel 105 testy; platba přes skutečnou testovací bránu zatím není dokončena.

Přesný serverový commit bez jiných rozpracovaných změn: 100 úspěšných testů. Offline iOS: 5 úspěšných kontrol navigace a souhlasů. Sestavení pro simulátor a nepodepsané zařízení uspělo.

Izolované testy: `tests/api/test_mobile_billing.py`, původní `test_license_comgate_utils.py`, viditelnost plateb, role administrátorů a veřejné výjimky webu. Žádné skutečné platby ani e-maily. Nativní formulář se ověřuje v oddělené offline instalaci s `--preview-billing`; tato ukázka nesmí nic odeslat. Testy navigace zůstávají zachované.
