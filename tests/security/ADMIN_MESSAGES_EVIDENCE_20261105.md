# Backend soukromých zpráv — 5. 11. 2026

Izolovaný worktree `evidence-admin-messages-20261105/server`, baseline e84bdac. Žádná změna produkce, skutečných účtů, odeslání e-mailů ani push oznámení.

## Ověřeno

**64 testů prošlo, 26,00 s.** Log: `evidence/admin-messages-20261105-pytest.txt`.

```sh
PYTHONPATH=.:tests/security /Users/toozservis/Developer/toozhub-parity-runtime-20261027/venv/bin/python -m pytest \
 tests/security/test_admin_messages.py \
 tests/security/test_admin_messages_concurrency.py \
 tests/security/test_admin_incidents.py \
 tests/security/test_account_flows.py \
 tests/security/test_account_erasure_graph.py \
 tests/api/test_admin_incident_race.py \
 tests/api/test_mobile_release_migration.py -q --disable-warnings --maxfail=1
```

- 14 cílených autentizovaných testů zpráv: role, cizí účet, veřejný demo JWT, neověřený e-mail, aktuální administrátorské ověření, deaktivace, CSRF, spoofovaná pole, nepřečtené versus potvrzení, atomická dávka skutečných ID, idempotentní opakování, konfliktní UUID, nové zprávy během čtení, stabilní stránkování, staré čekající potvrzení, výslovný výmaz účtu s FK, limity textu/ID, neukládání soukromého obsahu do auditu a limit odesílání.
- 4 souběžné testy s nezávislými spojeními do SQLite: stejný send UUID vytvoří jedinou zprávu/příkaz; konfliktní UUID pro různé příjemce vrátí 409 bez osiřelé zprávy; read souběžný s novou zprávou neoznačí novou zprávu; opakované souběžné ack ponechá první čas.
- Regrese incidentů, autentizace a grafu výmazu účtů.
- 3 migrační testy: skutečný přednasazovací runner, opakování zachovává soukromou zprávu/read/ack, spuštění zabaleného Docker souborového stromu v nezávislých procesech, žádné runtime DDL pro chybějící tabulky.

## Sdílená živá fixture

`tests/web/admin_messages_fixture_20261105.py` běží pouze na loopback18918. Vlastní syntetická SQLite v `admin-messages-qa-20261105`, 12 účtů ve skupinách ios/web/android, 12 původních diagnostických událostí. Používá skutečné routy zpráv, syntetický ovladač identity a skutečné webové soubory. Produkční přihlášení ověřují výše uvedené bezpečnostní testy, nikoli syntetický fixture token.

`GET /qa/setup` poskytuje pouze syntetická fixture data. `POST /qa/seed-messages` vytvoří běžnou a povinnou zprávu přes skutečnou funkci příkazu. `POST /qa/seed-message-history?group=web&recipient=user&count=55&sender=recipient` přidává čistě syntetickou historii pro stránkování, neoslabuje produkční omezování odesílání. Při restartu `MESSAGE_QA_RESUME=1` zachovává DB, zprávy i fixture JWT.

Ověření skutečně vykreslených iOS/web/Android klientů a jejich důkazy vedou příslušní agenti a nadřazený integrační report. Tento backend report sám nedokládá nasazení ani veřejné vydání.

## Hranice ověření

Souběh byl prověřen na SQLite, ne na živém PostgreSQL/Render. PostgreSQL používá řádkový `FOR UPDATE` a jedinečnost příkazů; produkční migrace ani provozní kouřový test nebyly provedeny. Procesní rate limiter není globální distribuovaná kvóta. Body zpráv se ukládají jako soukromý prostý text; nejsou koncově šifrované mezi klienty.
