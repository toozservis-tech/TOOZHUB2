# PROJECT NAMING STATUS

## Oficiální brand

- Uživatelský a admin brand je `Správa vozidel`.
- Tento název se má zobrazovat v UI, e-mailech, notifikacích, exportech, PDF a display metadatech.

## Kde technicky zůstává legacy `TOOZHUB2` / `TooZHub2`

- Názvy modulů a složek, například `TooZHubiOS`.
- Repo/reference cesty v dokumentaci a clone příkladech.
- Bundle identifier iOS: `cz.toozservis.spravavozidel.ios` zůstává beze změny.
- Interní technické identifikátory v health/debug payloads, například `project: TOOZHUB2`.
- User-Agent identifikátory a některé interní komentáře/docstringy.
- Historické a infrastrukturní skripty pro Windows autostart, tray, GitHub a deploy.

## Proč to zatím zůstává

- Přímý rename technických identifikátorů by mohl rozbít build, importy, CI, iOS distribuci, externí integrace nebo historickou dohledatelnost.
- Současný rename je záměrně omezený na display vrstvu a bezpečná metadata.

## Co je budoucí velký rename refaktor

- Přesun/rename modulů a složek nesoucích `TooZHub*`.
- Přenastavení GitHub/repo infrastruktury a historických deploy skriptů.
- Samostatně řízený rename interních technických identifikátorů v health/debug/telemetrii.
- Případný rename iOS targetu a dalších build artefaktů, pokud to bude koordinováno s release/distribucí.

