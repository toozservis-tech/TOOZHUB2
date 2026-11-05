# Soukromé zprávy administrace

Jedna konverzace patří jednomu zákazníkovi nebo servisu (`Customer.id`). Administrace ji spravuje společně: přečtení kterýmkoli oprávněným administrátorem znamená „Přečteno administrací“. Přístup ke konverzaci ostatních účtů zákaznické ani servisní API nenabízí.

Zprávy nemají e-mailový ani push rozesílač. „Odesláno“ je uložení na serveru; „Přečteno“ je potvrzení konkrétních zobrazených příchozích zpráv klientem; „Potvrzeno“ vzniká jen výslovným potvrzením požadované zprávy příjemcem. Žádný z těchto údajů nepotvrzuje doručení na konkrétní zařízení. Zobrazení historie samo o sobě nic nemění.

## API

Administrace vyžaduje aktuální ověření administrátora:

- `GET /admin-api/control-center/messages?search=&unread_only=false&limit=50&offset=0`
- `GET /admin-api/control-center/messages/accounts/{customer_id}?limit=50&before_id=...`
- `POST /admin-api/control-center/messages/accounts/{customer_id}`: `{body, requires_ack, client_id}`
- `POST /admin-api/control-center/messages/accounts/{customer_id}/read`: `{message_ids, client_id}`

Aktivní ověřený zákazník nebo servis:

- `GET /api/v1/admin-messages?limit=50&before_id=...&pending_only=false`
- `GET /api/v1/admin-messages/summary`
- `POST /api/v1/admin-messages`: `{body, client_id}`
- `POST /api/v1/admin-messages/read`: `{message_ids, client_id}`
- `POST /api/v1/admin-messages/{message_id}/ack`: `{client_id}`

`pending_only=true` vrací příchozí zprávy administrace, které jsou nepřečtené **nebo** vyžadují dosud nepotvrzené převzetí. Banner otevírá tento filtr „Nové a k potvrzení“; Profil otevírá celou historii. Starší nepotvrzený vzkaz se tak neztratí za novějšími odpověďmi.

Text je prostý text, 1–4 000 znaků po odstranění krajních mezer. Prázdný text, nepovolené řídicí znaky a cizí pole jsou odmítnuty. `client_id` je UUID; klient zachovává stejné UUID i obsah při opakování přerušeného požadavku. UUID použité stejným aktérem pro jinou operaci vrátí 409. Odpovědi se čtou kolektivně administrací; příjemce nemůže označovat své odchozí zprávy jako přečtené ani potvrzovat jinou konverzaci.

`message_ids` obsahuje 1–100 kladných číselných ID příchozích zpráv skutečně zobrazených v aktivním rozhraní. Žádné `through_id`: nově doručené ani nezobrazené starší zprávy se neoznačí. Neplatný člen odmítá celou dávku. `read` neprovádí `ack`. Explicitní `ack` nastaví první `read_at`, pokud dosud chybí. První časy čtení i potvrzení zůstávají zachovány při opakování.

## DTO

Message: `id, sender_kind(admin|recipient), sender_label, body, body_erased, requires_ack, sent_at, read_at, acknowledged_at`. Administrace navíc dostává `sender_name`; příjemce nevidí osobní identitu pracovníka administrace.

History: `recipient, pending_only, items, has_more, next_before_id, summary`. Stránka obsahuje nejnovějších nejvýše `limit` zpráv, seřazených vzestupně; `next_before_id` je nejstarší ID této stránky. Dotaz `< before_id` nepřeskakuje historii při současném příchodu nové zprávy.

Summary: `unread_count, unread_admin_count, unread_recipient_count, pending_ack_count, banner_count, last_message_id`. U příjemce `banner_count` počítá sjednocení nepřečtených a nepotvrzených zpráv; jednu zprávu nezapočítá dvakrát. U administrace `unread_count/banner_count` počítá nepřečtené příchozí odpovědi.

Send/reply/ack response: `{message, summary}`. Read response: `{updated_count, summary, items}`; položky jsou autoritativní DTO všech vyžádaných ID včetně serverových časů. Klient si čas čtení nevymýšlí.

Inbox: `{total, items:[{recipient, last_message, unread_admin_count, unread_recipient_count, pending_ack_count, updated_at}]}`. Recipient: `{id,name,email,role,active}`.

## Ochrany a provoz

- Autentizace využívá existující kontrolu relace, aktivního účtu a ověření e-mailu; veřejný demo token je odmítnut. Admin navíc vyžaduje existující aktuální administrátorské ověření.
- Zápisy serializují konverzaci přes řádek příjemce; jedinečný příkaz `(actor_id, client_id)` brání zdvojení. Prohlížečové zápisy kontrolují Origin/Sec-Fetch-Site. Odpovědi mají `Cache-Control: no-store`.
- Odeslání je omezené stávajícím procesním rate limiterem: administrace 120/minutu, příjemce 20/minutu. Opakování již dokončeného příkazu není nové odeslání. Limit je na proces, nikoli distribuovaná globální kvóta.
- Audit příkazů ukládá pouze ID, typ, časy a počty; ne text zpráv, tokeny ani kopie těla požadavku. Zprávy nemají API pro úpravy ani běžné mazání. GET neoznačuje čtení.
- Výmaz účtu odstraní jeho soukromou konverzaci a související příkazy. Při výmazu autora administrace zůstane v cizí konverzaci fakt/čas zprávy, ale text se anonymizuje a požadavek potvrzení zruší. Běžné čtení/ack historii nemaže.
- Migrace `0028` je aditivní a opakovatelná; je zapojená do `python -m scripts.migrate_mobile_release` i Docker balíčku. Bez tabulek API odpoví 503. Runtime nové tabulky sám nevytváří. Downgrade automaticky historii neodstraňuje.

## Ověření

Podrobnosti a přesný příkaz: `tests/security/ADMIN_MESSAGES_EVIDENCE_20261105.md`. Změna sama o sobě není potvrzením nasazení ani vydání mobilních klientů.
