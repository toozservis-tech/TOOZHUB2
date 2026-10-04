# Oddělené prostředí pro TestFlight a App Review

Stav 4. 10. 2026: připravené a ověřené lokálními integračními testy; cloudová služba ještě není vytvořená. Nový opakovaný náklad vyžaduje souhlas vlastníka.

## Připravené nasazení

- Zdrojová větev: `codex/appstore-sandbox-20261004`, Dockerfile `Dockerfile.sandbox`.
- Render: nový samostatný web service `spravavozidel-sandbox`, Frankfurt, 0.5 CPU / 512 MB, 7 USD měsíčně.
- Samostatný disk 1 GB na `/var/data`, 0.25 USD měsíčně; celkem 7.25 USD měsíčně před případnými daněmi. Žádný produkční environment group ani databázové přihlašovací údaje.
- Start: `uvicorn src.server.sandbox_review:app`; health `/health` vrací Sandbox a synthetic_data_only.
- Skutečný přidělený HTTPS origin se musí ověřit po vytvoření služby. Návrh předpokládá `https://spravavozidel-sandbox.onrender.com`; tento origin zatím není potvrzený.

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

`APPLE_IAP_KEY_ID`, `APPLE_IAP_ISSUER_ID`, `APPLE_IAP_PRIVATE_KEY`: již existující In-App Purchase klíč. Přenos do nové služby a vytvoření nového přístupu předat ke konkrétnímu souhlasu vlastníka. Klíč se neukládá do iOS aplikace.

## Ochrany a ověření

Konfigurace odmítá Production Apple prostředí, produkční origin, zděděné alternativní databáze, `.env` v checkoutu, SMTP, Supabase, Comgate, push klíče a administrátorské obcházení licence. Validace probíhá před importem aplikace a vytvořením databázového engine. Databáze má vlastní marker, zapnuté cizí klíče, WAL a timeout; start odmítne neznámou existující databázi.

Používají se skutečné přihlašovací, zákaznické a Apple ověřovací controllery. Počáteční tarif je pouze Free, jedno smyšlené vozidlo a jeden ruční záznam na účet. Placený tarif se nepřiděluje bez podpisu a současného stavu ověřeného u Applu. Restart neopravuje ani nepřepisuje nákupy a neobnovuje odstraněný účet. Obnova předplatného z místního starého harnessu do nových identit není automatická.

Veřejná registrace, obnova hesla přes e-mail, admin rozhraní a push registrace nejsou vystavené. Průběžně běží ověření Apple a dokončování fronty odstranění souborů. Chyby mají pouze anonymní diagnostický identifikátor; nikoli text s SQL parametry, JWS nebo klíči.

110 cílených testů prošlo, včetně 17 nových kontrol bezpečné konfigurace, skutečného přihlášení obou účtů, odmítnutí cizího podpisu/JWT a skutečného odstranění účtu s restartem. Tato kontrola nepoužila skutečný Apple klíč ani produkční zákaznická data. Pozitivní nákup v cloudové službě, běh kontejneru na Renderu a distribuční klientské směrování zatím nejsou ověřené. Lokální Docker daemon nebyl dostupný.

## Zbývá po souhlasu

1. Vytvořit službu a uložit pouze její vlastní tajné nastavení; ověřit health, oprávnění disku, přihlášení a přetrvání po restartu.
2. Směrovat distribuční aplikaci podle ověřeného `AppTransaction.environment`, před vytvořením přihlášení a APIClientu. Produkční a sandboxové tokeny musí zůstat oddělené. Žádný přechod do Sandbox při chybě Production.
3. Připravit build 5 a ověřit skutečný TestFlight nákup, obnovu, obnovování a zákaz přenosu mezi účty. Nastavit a ověřit Server Notifications V2 pro jednotlivá prostředí.
4. Dokončit účet recenzenta, snímky aplikace a předplatného. Účty zákazníků nepoužívat pro snímky ani pro App Review.
