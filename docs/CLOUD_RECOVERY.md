# SprávaVozidel — šifrovaná kopie a zkouška obnovy

Tato část obsahuje nástroje pro správce provozu. Není to automatické denní zálohování ani tlačítko pro obnovení živého serveru. Stávající panel záloh se tím nepřepíná do stavu „hotovo“.

## Ověřený stav 1. 10. 2026

Patnáct izolovaných testů ověřilo skutečné šifrování age, export a obnovu PostgreSQL v odděleném serveru, shodu tabulek a souborů, souběžný zápis po snapshotu, odlišné časové pásmo, nesprávný klíč i poškozenou kopii. Testovací záznamy a dokumenty jsou syntetické. Původní textové poznámky v poli příloh zůstanou v dumpu; nepovažují se za souborové cesty.

Pokus o úplné zachycení obnovené produkční databáze **neprošel** kontrolou souborů. Některé starší reference mají odpověď úložiště „objekt nenalezen“, včetně současných záznamů. Historické auditní reference jsou datované již v březnu 2026. Dostupný původní archiv ani místní kopie nedoplnily chybějící objekty. Jejich příčinu ani dobu ztráty nelze z této kontroly určit. Nástroj správně nevytvořil neúplnou kopii označenou jako úspěšná; žádné původní reference se nemažou a náhradní soubory se nevymýšlejí.

Úplná produkční obnova proto není prokázaná. Chybějící originály vyžadují dohledání u vlastníka nebo v původní záloze. Nové servisní záznamy nyní před připojením souboru ověřují trvalé úložiště, aby neexistující odkazy dál nepřibývaly. Úpravy poznámek starších záznamů jejich původní evidence zachovávají.

## Co se kopíruje

`scripts/capture_cloud_recovery.py` otevírá PostgreSQL transakci pouze pro čtení. Exportovaný snapshot spojuje databázový dump, kontrolní otisky všech tabulek aplikačního schématu a seznam potřebných souborů. Souběžný pozdější zápis se do dumpu ani seznamu nepřimíchá. Zdrojem souborů je privátní cloudové úložiště, nikoli místní cache.

Inventura zahrnuje úvodní fotografie, ORV, dokumentaci oprav, doklady servisu, přílohy současných i historických servisních záznamů, historii vlastníků a dosud nepřipojené evidované přílohy. Neukládá se celý obsah bucketu ani neznámé staré soubory. Zařazené požadavky na odstranění mají přednost před historickým odkazem. Rozpracované nepřiřazené ORV snímky nejsou vydávané za dokončený dokument. Nové neobsloužené sloupce `path` / `*_path` zastaví export; nové typy souborů v JSON vyžadují aktualizaci inventury a testů.

Chybějící požadovaný soubor, síťová chyba, neplatná reference, neúspěšný dump nebo šifrování zastaví vytvoření. Částečná kopie se nezveřejní. Jednotlivý soubor má limit 100 MiB a souhrnný obsah 2 GiB; větší provoz vyžaduje předem změnu a ověření limitů. `admin_settings.json` se ukládá také, ale jde o samostatný proměnlivý objekt: jeho čas zachycení je v manifestu a není tvrzena společná databázová transakce s nastavením.

## Šifrování a oddělení přístupů

Dump a soubory proudí přímo do nástroje [age](https://github.com/FiloSottile/age); při zachycení se nezapisuje nešifrovaný dump na disk. Veřejný příjemce stačí pro vytvoření kopie. Soukromý klíč není potřeba na aplikačním serveru a nesmí být v Gitu, konfiguračním panelu, protokolu, e-mailu ani společném úložišti s kopií. Vlastník musí mít bezpečně uloženou samostatnou kopii klíče; bez ní nelze data obnovit.

Soubor kopie má oprávnění 0600. Vedle něj vzniká souhrnný report bez osobních údajů, s SHA-256 celé zašifrované kopie. Report je nutné zkopírovat do odděleného chráněného umístění. Samotné age šifrování neověřuje totožnost odesílatele — kdokoli s veřejným příjemcem umí vytvořit jinou kopii. Ověření proto vyžaduje otisk z důvěryhodného reportu, nikoliv z obsahu přijatého archivu.

Kopie obsahuje osobní a autentizační údaje databáze a privátní nastavení. Není to uživatelský export. Obnovení musí provádět oprávněný správce v odděleném prostředí. Nástroje přijímají cesty k souborům s údaji; heslo databáze není v argumentech procesu ani ve výstupu.

## Spuštění provozním správcem

Potřebné jsou závislosti serveru, age a PostgreSQL 17 klient i server. Pro cloud je nezbytná podpora TLS v libpq/pg_dump. Obyčejný `pg_dump --version` tuto podporu nedokazuje. Zdrojový soubor spojení musí vyžadovat TLS. PostgreSQL klient nesmí být starší hlavní verze než zdrojový server.

Příklad cest níže je záměrně obecný; neobsahuje žádný skutečný klíč:

```sh
python scripts/capture_cloud_recovery.py \
  --database-url-file /private-config/database-url.txt \
  --storage-env-file /private-config/storage.env \
  --recipient-file /private-config/recovery-recipient.txt \
  --schema application_schema \
  --output /private-backups/capture.zip.age \
  --pg-dump /postgres/bin/pg_dump \
  --age /tools/age
```

Konfigurace úložiště používá `SUPABASE_URL`, `SUPABASE_SECRET_KEY` a `SUPABASE_STORAGE_BUCKET`. Nevypisovat jejich obsah. Soukromé soubory s přihlašovacími údaji musí být přístupné pouze vlastníkovi.

Po bezpečném uložení reportu na samostatné místo:

```sh
python scripts/verify_cloud_recovery.py \
  --bundle /private-backups/capture.zip.age \
  --identity-file /offline-recovery/recovery-identity.key \
  --trusted-report-file /trusted-reports/capture.report.json \
  --postgres-bin /postgres/bin \
  --age /tools/age
```

Ověřovací nástroj nepřijímá adresu cílové databáze. Vytvoří nový PostgreSQL server s náhodným heslem, pouze privátním Unix socketem a bez TCP naslouchání. Aplikace, plánovače, e-mail ani platby se nespouštějí. Kontroluje šifrování, přesný seznam členů archivu, velikosti, SHA-256 každého souboru, skutečný import dumpu, obsah všech tabulek a návaznost všech souborových odkazů. Otisky tabulek mají pevné nastavení časové zóny a formátu hodnot. Výstup obsahuje pouze počty, časy a otisk kopie.

Po ověření se dočasný server zastaví a jeho privátní pracovní adresář i rozšifrované soubory se odstraní. Při selhání zastavení se pracovní adresář zachová soukromý a kontrola selže; správce musí proces bezpečně zastavit a adresář uklidit. Nástroj nikdy nenahrazuje živou databázi.

## Co ještě musí předcházet skutečné obnově provozu

Úspěšná kontrola nastaví pouze `isolated_restore_verified: true`. Hodnota `restore_ready` zůstává `false`, dokud není vyřešeno:

1. Aktuální evidence výmazů mimo obnovovanou databázi. Starší kopie nesmí znovu aktivovat později smazané účty či vrátit jejich odstraněné dokumenty. Samotná fronta výmazů uvnitř starého dumpu nestačí.
2. Zrušení obnovených relací, obnovovacích odkazů, výzev a oprávnění, která od pořízení kopie zanikla. Obnovovat v údržbě bez přístupu klientů.
3. Samostatná obnova serverových tajemství, zvláště klíče chránícího autentikátory. Export databáze nenahrazuje bezpečnou správu klíčů a nesmí vést k vypnutí MFA.
4. Porovnání plateb a předplatného se stavem poskytovatelů. Starý dump nesmí opakovat platby nebo obnovovat zrušená oprávnění.
5. Plánované denní kopie, omezení retence, dohled selhání a kopie mimo jediného poskytovatele. Jednorázový soubor na Macu není služba nepřetržitého zálohování.

Dokumentace poskytovatelů: [PostgreSQL — pg_dump](https://www.postgresql.org/docs/current/app-pgdump.html), [Supabase — zálohy](https://supabase.com/docs/guides/platform/backups). Záloha databáze Supabase sama neobsahuje binární objekty Storage.
