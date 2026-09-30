# SprávaVozidel – Comgate a předplatné

Přeneseny původní tarify: Basic 99 Kč měsíčně / 990 Kč ročně (5 vozidel), Premium 299 Kč / 2 990 Kč (bez limitu). Free: 1 vozidlo. Funkce se čtou ze stejného licencování jako zbytek aplikace. Provozovatel, kontakty a odkazy na původní dokumenty jsou v katalogu; nebyly vytvořeny nové právní podmínky.

## Obsluha

iOS: Profil → Tarify a předplatné. Správce: Provoz → Platby a licence → Stav připojení Comgate. Web: Nastavení → Comgate → Ověřit spojení s Comgate. Ověření připojení nic neúčtuje. Heslo brány je zapisovatelné, jeho původní hodnota se do klienta nevrací.

Vyberte období a tarif, zkontrolujte konečnou cenu, samostatně potvrďte souhlasy. Brána se otevírá přes SFSafariViewController. Návrat `spravavozidel://payment` jen aktualizuje stav. U neuzavřené platby lze pokračovat v historii. Vypnutí automatického prodlužování zachová zaplacené období. Změna pravidelného tarifu se projeví při příští platbě.

## Dokončení připojení původního obchodu

Původní schválený obchod `toozservis.cz`, propojení `507933`. Dne 29. 9. 2026 byly po schválení vlastníkem uloženy původní údaje pouze do serverového nastavení, v portálu byly změněny návratové adresy a potvrzování plateb na `app.toozservis.cz`. Povolené IP jsou aktuální rozsahy Renderu `74.220.51.0/24` a `74.220.59.0/24`; původní IP byla nahrazena. Skutečné spojení přes seznam platebních metod bylo potvrzeno ve webové administraci i v iOS. Testovací režim zůstává zapnutý.

30. 9. 2026 byl po výslovném schválení aktivován Render 0,5 CPU / 512 MB za 7 USD měsíčně. `ENABLE_LICENSE_SUBSCRIPTION_WORKER=1`; skutečný server zaznamenal spuštění s intervalem 3 600 sekund a první cyklus s nulou chyb. Před zapnutím nebyly žádné splatné obnovy, rušení ani oznámení. Připomínkový worker se tímto nezapínal.

Testovací objednávka Basic za 98,99 Kč vznikla v přihlášené iOS aplikaci (původní účet má kredit 0,01 Kč). Stejná platba byla potvrzena na testovací stránce Comgate v Chromu, protože ovládání okna simulátoru přes Computer Use nebylo dostupné. Skutečné potvrzení od brány dorazilo na server: `test_paid_confirmed`, `PAID`. Původní licence a předplatné se před testem a po testu shodují ve všech uložených polích. Návratový odkaz a zobrazení „Test potvrzen · bez změny tarifu“ byly ověřeny v iOS. Neproběhlo skutečné stržení peněz.

Lokální ukázka nyní registruje pouze `spravavozidel-local`, aby při souběžné instalaci nepřebírala návraty plateb a obnovy hesla určené serverové aplikaci. Serverová a distribuovaná verze používá `spravavozidel`.

Před ostrým účtováním ještě zbývá potvrdit oprávnění tohoto obchodu pro automatické opakované platby a ověřit jejich celý průchod. Portál potvrzuje schválený obchod a aktivní propojení, ale tyto údaje samy oprávnění k opakování neprokazují. [Dokumentace Comgate](https://help.comgate.eu/docs/opakovane-platby) vyžaduje aktivaci této funkce podporou. Jednorázový test nenahrazuje ověření automatické obnovy. Testovací režim proto zůstává zapnutý.

Klíč ani platné odkazy na platbu nepatří do Gitu. Aktivní propojení v portálu samo o sobě neprokazuje připravenost celého průchodu. Ostrá platba nebyla při implementaci provedena. Schválení distribuce digitálního předplatného přes externí bránu v App Store je samostatný krok před vydáním do obchodu.

## Ochrany

Server kontroluje cenu, měnu, obchod, identifikátor, referenci a testovací režim oproti uložené objednávce. Aktivuje pouze PAID, nikoli AUTHORIZED. Testovací úhrada je pouze auditní záznam. Aktivace licence a potvrzení platby se zapisují v jedné transakci. Souhlasy zůstávají dohledatelné. Stejné ID objednávky nevolá založení platby podruhé. Nejasný výsledek při výpadku zůstává rezervován pro kontrolu správcem – automatické opakování by mohlo zákazníka zpoplatnit dvakrát. Pravidelné platby mají samostatnou rezervaci pro každé období a čekající transakce se ověřuje, nezakládá znovu.

## Ověření

30. 9. 2026: přihlášená iOS aplikace ověřila spojení s Comgate a načetla skutečný katalog. Při přípravě testovací objednávky původního účtu byl opraven nesoulad jednorázové nabídky a požadavku `initRecurring`. Jednorázová objednávka nyní žádné oprávnění k opakovaným platbám nevyžaduje. Klient posílá `expected_recurring`; změna způsobu prodlužování mezi nabídkou a odesláním se odmítne ještě před bránou. Starší klient dostane požadavek na aktualizaci. Telefon plátce se zbytečně nepředává, kontaktem je e-mail. Po doplnění bezpečného ověření historických zrušených objednávek prošel přesný serverový stav 114 testy. Stará nevyřízená objednávka přestává blokovat nákup pouze po ověření stavu CANCELLED, obchodu, reference, identifikátoru, měny a částky přímo u brány. Původní záznam se zachovává; neznámá historická platba PAID nesmí bez původních podmínek měnit oprávnění.

Přesný serverový commit bez jiných rozpracovaných změn: 100 úspěšných testů. Offline iOS: 5 úspěšných kontrol navigace a souhlasů. Sestavení pro simulátor a nepodepsané zařízení uspělo.

Izolované testy: `tests/api/test_mobile_billing.py`, původní `test_license_comgate_utils.py`, viditelnost plateb, role administrátorů a veřejné výjimky webu. Žádné skutečné platby ani e-maily. Nativní formulář se ověřuje v oddělené offline instalaci s `--preview-billing`; tato ukázka nesmí nic odeslat. Testy navigace zůstávají zachované.
