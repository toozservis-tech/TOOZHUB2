# Odstranění účtu — 1. října 2026

Uživatel vyvolá odstranění ve svém účtu, potvrdí heslo a text SMAZAT UCET. Export je nabídnutý, ale není povinný. Ověření hesla je omezené počtem pokusů. Žádný test tohoto postupu nepoužívá skutečný účet, e-mail ani úložiště.

## Rozsah

- Odstraní se přihlašovací účet, kontaktní a bezpečnostní údaje, registrace, oprávnění, připomínky, rezervace a vlastní vytvořený obsah včetně fotografií a příloh. Servisní záznamy vytvořené daným účtem se odstraňují také; nezávislé záznamy jiných autorů u zachovaných vozidel zůstávají.
- Vozidlo se odstraní pouze při aktivním vlastnictví bez dalšího aktivního vlastníka. Delegovaný přístup nestačí. Spoluvlastník zůstane vlastníkem; starý e-mail není oprávnění k odstranění vozidla. Příslušnost ke stejné organizaci sama o sobě neznamená vlastnictví.
- Celá organizace se nikdy nemaže odhadem podle počtu účtů. Poslední odstraněný účet zastaví obnovování Comgate a uloží anonymní značku, která brání opětovnému zapnutí plateb opožděným potvrzením. Obnovování u Applu uživatel spravuje u Applu, odkaz je ve formuláři.
- Apple identifikátor nákupu zůstane bez zákazníka a organizace, aby cizí účet nemohl převzít původní nákup. Platební kniha zůstává pro účetnictví a ochranu nákupů; veřejné retenční lhůty vyžadují dokončení samostatné právní a provozní kontroly.

## Soubory a potvrzení

`private_file_erasure_queue` se zapisuje ve stejné transakci jako odstranění vlastníka. Do potvrzení transakce se neprovádí nevratná práce se soubory. Fronta přijímá jen konkrétní cesty v pěti známých soukromých složkách. Neprochází ani nevyprazdňuje celý bucket. Cizí přeživší odkaz na stejný soubor se zachová. Neplatná cesta nebo poškozený inventář zastaví odstranění účtu a transakce se vrátí zpět.

Pracovník každou minutu zpracovává nejvýše deset souborů. Odstraňuje soukromý objekt přes Storage API a místní cache. Selhání zůstává ve frontě s odstupňovaným opakováním; neukládá tajné odpovědi poskytovatele. Řádkové zámky a idempotentní odstranění umožňují bezpečné opakování po restartu. Po dokončení nezůstává souborová cesta ve frontě.

`account_erasure_receipts` neobsahuje jméno ani e-mail. Obsahuje hash náhodného potvrzení a dočasný seznam čekajících cest. Po dokončení se cesty vyprázdní; potvrzení se odstraní po 30 dnech. Aplikace po odhlášení kontroluje dokončení pomocí tohoto potvrzení, nikoli původního přihlášení. Potvrzení se neposílá v URL. iOS si vytvoří náhodné potvrzení ještě před požadavkem a umí ověřit potvrzené odstranění při ztracené síťové odpovědi. Výpadek sám není potvrzením úspěchu.

Administrátor vidí počty čekajících a opakovaných souborů v Provoz / Systém a kontrola. Jednorázové tlačítko zpracuje nejvýše jeden již potvrzený soubor. Dokončování potvrzených žádostí se z této administrace nedá pozastavit.

## Ověření a limity

Testy používají oddělenou SQLite databázi se zapnutými cizími klíči, dočasné soubory a napodobené odpovědi úložiště. Pokrývají celý propojený účet, servisní účet, delegaci, spoluvlastníka, cizí záznam ve stejné organizaci, sdílenou přílohu, vrácení transakce, chybu úložiště, idempotentní opakování, neplatné cesty a symbolické odkazy, utajení a dokončení potvrzení, oddělení Apple nákupu a opožděné potvrzení Comgate. Nativní testy kontrolují kladné potvrzení serveru, ztrátu odpovědi a izolaci přehledů mezi přihlášeními.

Stále je potřeba dokončit retenční plán poskytovatelů, kontrolu záloh a veřejné dokumenty. Tato implementace neoznačuje celou aplikaci za právně schválenou ani připravenou k vydání. Data ve fyzicky oddělených zálohách se tímto pracovníkem nemění.

Podklady: [požadavky Applu](https://developer.apple.com/support/offering-account-deletion-in-your-app/), [Supabase odstranění objektů](https://supabase.com/docs/guides/storage/management/delete-objects), [Storage API](https://supabase.com/docs/reference/self-hosting-storage).
