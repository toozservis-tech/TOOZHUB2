# Oddělené prostředí pro TestFlight a App Review

Stav 4. 10. 2026: Evidence Vozidel používá samostatnou službu Render **Live** (`srv-db141qu0tbcc739dlh7g`, deployment `dep-db1508lckfvc73dbk3cg`, zdroj `7aa7982`). Vlastník schválil 7.25 USD měsíčně plus případné daně i uložení existujícího Apple klíče. Databáze, soubory a přihlašovací klíč jsou oddělené od produkce. Build **1.0.0 (8)** je zpracovaný Applem a dostupný stávající interní skupině Ověření vydání. Omezené testovací přístupy jsou po výslovném souhlasu vlastníka uložené v neveřejných polích App Review a TestFlight Review.

## Připravené nasazení

- Zdrojová větev: `codex/appstore-sandbox-20261004`, Dockerfile `Dockerfile.sandbox`.
- Render: nový samostatný web service `spravavozidel-sandbox`, Frankfurt, 0.5 CPU / 512 MB, 7 USD měsíčně.
- Samostatný disk 1 GB na `/var/data`, 0.25 USD měsíčně; celkem 7.25 USD měsíčně před případnými daněmi. Žádný produkční environment group ani databázové přihlašovací údaje.
- Start: `uvicorn src.server.sandbox_review:app`; health `/health` vrací Sandbox a synthetic_data_only.
- Skutečný přidělený a ověřený HTTPS origin je `https://spravavozidel-sandbox.onrender.com`.

## Veřejné nastavení

```dotenv
SV_ISOLATED_APPLE_SANDBOX=1
APPLE_IAP_ENABLED=1
APPLE_IAP_ENVIRONMENT=Sandbox
APPLE_IAP_BUNDLE_ID=cz.toozservis.spravavozidel.ios
APPLE_IAP_APP_ID=6818048361
APPLE_IAP_SUBSCRIPTION_GROUP_ID=22431514
SANDBOX_DATA_ROOT=/var/data
DATABASE_URL=sqlite:////var/data/sv-sandbox.sqlite3
DATA_DIR_PATH=/var/data/files
PUBLIC_API_BASE_URL=https://spravavozidel-sandbox.onrender.com
ENABLE_IP_GEOLOOKUP=0
ENVIRONMENT=production
```

## Tajné nastavení — bez hodnot v repozitáři

`JWT_SECRET_KEY`: nový náhodný trvalý klíč pouze pro tuto službu, nejméně 40 znaků. Nikdy nepoužít produkční JWT klíč.

`SANDBOX_CUSTOMER_1_PASSWORD_HASH` a `SANDBOX_CUSTOMER_2_PASSWORD_HASH`: bcrypt s cost 12–16. Přihlašovací hesla pro dva smyšlené zákazníky mají vlastní bezpečné uložení; nevkládat do zdrojů, protokolů ani veřejných podkladů. Účty `sandbox-1@example.com` / `sandbox-2@example.com` nejsou skutečné e-mailové schránky.

`APPLE_IAP_KEY_ID`, `APPLE_IAP_ISSUER_ID`, `APPLE_IAP_PRIVATE_KEY`: již existující In-App Purchase klíč. Přenos do této konkrétní služby vlastník výslovně schválil a byl dokončen. Klíč se neukládá do iOS aplikace.

## Ochrany a ověření

Konfigurace odmítá Production Apple prostředí, produkční origin, zděděné alternativní databáze, `.env` v checkoutu, SMTP, Supabase, Comgate, push klíče a administrátorské obcházení licence. Validace probíhá před importem aplikace a vytvořením databázového engine. Databáze má vlastní marker, zapnuté cizí klíče, WAL a timeout; start odmítne neznámou existující databázi.

Používají se skutečné přihlašovací, zákaznické a Apple ověřovací controllery. Počáteční tarif je pouze Free, jedno smyšlené vozidlo a jeden ruční záznam na účet. Placený tarif se nepřiděluje bez podpisu a současného stavu ověřeného u Applu. Restart neopravuje ani nepřepisuje nákupy a neobnovuje odstraněný účet. Obnova předplatného z místního starého harnessu do nových identit není automatická.

Veřejná registrace, obnova hesla přes e-mail, admin rozhraní a push registrace nejsou vystavené. Průběžně běží ověření Apple a dokončování fronty odstranění souborů. Chyby mají pouze anonymní diagnostický identifikátor; nikoli text s SQL parametry, JWS nebo klíči.

110 cílených testů prošlo, včetně 17 nových kontrol bezpečné konfigurace, skutečného přihlášení obou účtů, odmítnutí cizího podpisu/JWT a skutečného odstranění účtu s restartem. Tato kontrola nepoužila skutečný Apple klíč ani produkční zákaznická data. Dalších 17 regresí odstranění účtů a 150 cílených regresí přejmenování, fakturace a zabezpečení prošlo. Render skutečně sestavil kontejner a spustil jej; health a přihlášení obou účtů přes HTTPS fungují. Ověřeno 20 chráněných odpovědí, nákupní relace, odmítnutí neplatného podpisu a odmítnutí Sandbox tokenu produkčním serverem.

Build 7 již umožnil ověřit instalaci, ale kontrola účtu posílala Sandbox JWT na produkční origin. Build 8 (`88dfff3`) uzamkne ověřený `AppTransaction.environment` před vytvořením relace a předá stejný origin všem klientům funkcí aplikace; Release bez ověření nesmí zahájit síťový požadavek. Kontrola e-mailu navíc přímo používá klienta prostředí. Prošlo 25 nativních testů, Release archiv, App Store export a přísné ověření podpisu. Vlastník potvrdil úspěšné přihlášení build 8.

Vlastník provedl skutečný TestFlight nákup Basic měsíčně na smyšleném účtu 2. Přímé HTTPS ověření v 14:01:25 UTC potvrdilo Apple Sandbox `active`, Basic, limit 5 a dostupnou historii, dokumenty a VIN/ORV. Náklady a statistiky jsou zamčené. Účet 1 zůstává Free s limitem 1 vozidla a 2 ručních úkonů; nákup se na něj nepřenesl. Vlastník následně potvrdil obnovu nákupů a restart aplikace: účet 2 zůstává Basic, detail vozidla funguje a účet 1 po obnově zůstává Free. Vlastník následně provedl skutečný upgrade na Premium a potvrdil dostupné funkce. Přímé HTTPS ověření ve 14:12:45 UTC potvrzuje účet 2: Apple Premium active, neomezená vozidla a odemčené náklady, statistiky i sdílení; účet 1 zůstává Free. Důkaz: `outputs/appstore-1.0.0/cloud-sandbox-entitlements-premium.json`. Vlastník potvrdil také obnovu nákupů a restart po upgradu: Premium, neomezená vozidla, náklady a statistiky zůstaly dostupné. Ostatní životní cyklus dosud není ověřený. Důkazy v pracovním kořeni: `outputs/appstore-1.0.0/cloud-sandbox-auth-preflight.json`, `cloud-sandbox-entitlements.json`, `build8-signature-check.json` a `build8-testflight-ready.jpg`. Nákupy v TestFlight standardně používají zrychlené obnovování po 24 hodinách; datum 5. 10. v tomto testu není měsíční produkční perioda.

## Zbývající ověření

1. Ověřit přetrvání skutečné cloudové databáze po nasazení/restartu; integrační test restartu a odstranění již prošel lokálně.
2. Dokončit širší ruční kontrolu všech sekcí build 8 přes TestFlight; přihlášení, detail a restart již vlastník potvrdil. Směrování a oddělení tokenů je již implementované. Žádný přechod do Sandbox při chybě Production.
3. Ověřit další cloudové obnovování a ostatní životní cyklus; skutečný Premium upgrade, obnova i restart jsou potvrzené. Skutečný cloudový nákup, obnova, restart i zákaz přenosu na druhý účet jsou potvrzené. Obě serverové URL jsou uložené a ověřené v App Store Connect. Bezprostřední Sandbox žádost o test oznámení vracela Apple 4040007 (URL ještě nenalezena); úspěšné doručení není potvrzené. Produkční předplatné je stále vypnuté.
4. Dokončit snímky aplikace a předplatného. Účet recenzenta je již uložený. Účty zákazníků nepoužívat pro snímky ani pro App Review.
