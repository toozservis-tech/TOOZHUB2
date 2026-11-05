# Web: převzetí vozidla a detaily pozvaných účtů — 5. 11. 2026

Stav: **OVĚŘENO v rozsahu níže**, lokální zdroje; bez nasazení/push/produkčních e-mailů. Pravidla iOS → Android/web přečtena. API a iOS upravuje hlavní agent, tento report se týká webu.

## Provedené změny

- Nový `web/vehicle-transfers.js`: vlastní inbox, prodej s e-mailem nebo explicitním důvodem mimo aplikaci, osobní potvrzení kupujícího kódem, odmítnutí, resend/cancel. Bez automatického převodu podle VIN.
- Vstupy v produktovém zákaznickém HTML: Vozidla/Přidat vozidlo → Převzetí; detail vozidla → Správa; Archiv → pozvánka pouze pokud API vrátí `can_invite_new_owner`. Po převzetí/prodeji zavře zastaralý detail a obnoví garáž.
- Konflikt při zadávání existujícího VIN nabídne konkrétní postup a otevření Převzetí.
- Admin: Vozidla → Kompletní vozidlo a události → Ověřit převod. Aktuální vlastník, důvod min10 znaků, acknowledgement a finální potvrzení; review_token + stabilní request UUID. Ani admin potvrzení nepřiřadí vozidlo bez souhlasu kupujícího.
- Referral vlastní detail: ověřený přímý účet zobrazí jméno/e-mail, otevření detailu ukáže registraci, ověření a splnění podmínek. Neověřenému/neaktivnímu kontakt nevynucuje. Veřejná registrace transparentně vysvětluje rozsah sdílení (text patří `web/index.html`, JS helper jej nevykresluje).
- Zachovány pravidla session generation, modal cancellation, same-origin session provider a textContent pro údaje. Nejasný výsledek zápisu používá stejný idempotency UUID.

## Živé browser ověření

Skutečný Google Chrome přes Playwright1.58.2, cs-CZ, mobilní390×844 i desktop1400×1000. Skutečné produktové JS/HTML, FastAPI routery a SQLite. E-maily se pouze zachycují do lokálního souboru, adresy `*@example.com`. Žádné produkční účty.

1. Sdílená fixture18915 / `shared.sqlite`: společná API/schema/SQLite pro iOS, Android a web, oddělené syntetické skupiny aby se klienti nepřepisovali. První webový průchod sedmi scénáři PASS (web-pass1/result.json).
2. Finální sedm scénářů opakováno na čisté fixture18916 ze stejného fixture zdroje po úpravě checkboxu/admin odpovědi: **PASS7**, `web-final-live/result.json`. Seller → pending → nesprávný kód zamítnut → buyer potvrzení → reload, ochrana archivu, referral detail, legacy-sold, admin výjimka, stranger izolace.
3. Skutečné `src.server.web_access.customer_web()` a `web_admin/index.html`, nezměněné skutečné session providery: **PASS5**, `web-final-integrated/result.json`. Kliknutí z produktových Vozidel, detailu, Nastavení, Archivu a admin karty. Ověřen fyzický render desktop a fotografie náhledu.
4. Replacement na sdílené18915: **PASS3**, `web-reinvite/result.json`. Nově vytvořené syntetické vozidlo10/archiv9: pozvánka10 cancelled, 11 rejected, 12 accepted. Všechny tři rozhodnutí zůstaly v historii; starý kód vrací409, další pozvání po přijetí není dostupné. První cancel a nové pozvání provedeny browser UI, následné rejection/accept přes skutečné API.
5. **PASS20** automatických browser/contract testů: stávající referral16 + nové transfer4 (`web-contract-tests.log`). Nové testy pokrývají chybějící e-mail/důvod, finální souhlas, retry po503 se stejným UUID, změnu účtu během potvrzení, starý server bezsalev2 a zákaznický zákaz admin UI. Tyto čtyři používají mock API a nejsou samy E2E důkaz.
6. `git diff --check`, JS syntax check, Python compile PASS.

## Omezení a přesné rozlišení

- Přihlášení je syntetická předpodmínka; test vložil fixture JWT do sessionStorage, poté skutečný session provider ověřoval `/user/me`. Tento průchod NEOVĚŘUJE heslo, e-mailovou doručitelnost ani MFA. Admin-assurance endpoint je výslovně QA stub.
- Fixture zahrnuje cílové skutečné routery, nikoli celý server. Integrovaný test eviduje404 pro nesouvisející `/health`, reminders, system-notifications, capabilities, Comgate config, service contacts, records, security settings, admin overview a session renewal. Přesné role/cesty jsou v JSON. Tyto další funkce nebyly označeny PASS.
- V čerstvé QA DB byl chybějící lazy model `service_booking_requests`; opraveno jen pořadí importu fixture a doplněny chybějící tabulky. Produkční kód či oprávnění nebyly kvůli QA měněny.
- Nejprve chybně připojené admin routes ignorovaly fixture auth override a odmítaly JWT401. Fixture opraven přes APIRouter/include_router, produktová autorizace zachována.
- Kompletní paritu nativních klientů a releasu hodnotí hlavní agent. Tento web nebyl nasazen, žádná veřejná aktualizace nebyla nahraná.

## Fixture a migrace

Server18915 zůstává spuštěný pro další QA.18916 byl po testech zastaven, DB/evidence zachována. Testovací server není registrován v produkční aplikaci a kód je pouze v tests/web. Vyžaduje explicitní `TRANSFER_QA_DB` v samostatném lokálním adresáři `transfer-referral-qa-*`, zakazuje symlink, omezuje peer na loopback, role/tokeny jen přes přesné syntetické účty, capture přijímá pouze example.com.

Guardy ověřeny TestClientem: cizí peer403, loopback setup a autorizovaný inbox200, cizí e-mail capture odmítnut (`web-fixture-guards.json`).

Migrace0026 aplikována na zachovanou shared.sqlite, před/po všech sedm tehdejších pozvánek shodných, unikátní archive_id odstraněno. Záloha `shared-before-0026.sqlite`, důkaz `migration-0026.json`. Následné klientské testy přidaly další řádky bez mazání původních.

## Evidence

Lokální adresář: `/Users/toozservis/Developer/evidence-mac-lifecycle-fix-20261104/transfer-referral-qa-20261105`

- web-final-live/result.json, buyer-accepted.png, referral-detail.png
- web-final-integrated/result.json, customer-management.png, customer-referral-detail.png, admin-transfer-review.png
- web-reinvite/result.json, cancelled-and-replacement.png
- web-contract-tests.log; web-fixture-guards.json; migration-0026.json

## Otisky SHA-256

Datum záznamu UTC: 2026-11-05T07:36:47.183672+00:00

| Soubor | SHA-256 |
|---|---|
| `web/vehicle-transfers.js` | `bf5653eabc6eef3b3afa90740d8922993da52722316f25c57a864cbd377a38f4` |
| `web/customer-features.js` | `8670269a2a07510a2f114268eea280363f22cbd577e3a95dac746d631ba66e48` |
| `web/index.html` | `87e3c51bb8f4e58840132fbac5fab5b449d70a73cb959061389b3d901c5a0e14` |
| `web/legacy-app.js` | `548d3b537c51ba228ef60934cd84f03b786bdf04b186eb6407fb0681bc7d0750` |
| `web/referral-features.js` | `96fcc36e5bff9f47555c72cea83207fd96ae16d97fac1a22bfca58402b6d635f` |
| `web/referral-features.css` | `08b3681ad42fcec1c09f9768d4e3a224d8b374aea3c6897b714aff2509c8752b` |
| `web/vehicle-transfer.html` | `4443634569b66a7142f3619cecf5947d1fb96a63546667e810a604ecea8f61dd` |
| `web_admin/index.html` | `0e743512fad01b633ee1a33ebc8f543b31acde987c342be2ab0a2d8b5cabad6d` |
| `web_admin/entity-management.js` | `d62479d9cc50803cb912700288ce6eb8750a83c0964d6a3e0476091efc7684d5` |
| `tests/web/transfer_referral_fixture_20261105.py` | `a1a58de989603bb28412ea822a30c11b8227dc3a4b2bb04e8d9f464b70bb4b4a` |
| `tests/web/transfer-referral-live-20261105.cjs` | `b260910a20dbeca3d3bba20654edfb3f73236c271186c59a51d6b38628b7a72d` |
| `tests/web/transfer-referral-integrated-20261105.cjs` | `4f4459775b6ac6ca2f8dc40d48152f609c8f53afbda5fc98b74a87c0851b0183` |
| `tests/web/transfer-reinvite-live-20261105.cjs` | `ce0ba72afce38d16d41ffbe1b4f55988a824f7d62609df9d2559cae27559b459` |
| `tests/web/vehicle-transfers-browser-20261105.cjs` | `79843cdd5fcaf50b5557dc92627e181c39d7405c788678538ad427490a12d05c` |
