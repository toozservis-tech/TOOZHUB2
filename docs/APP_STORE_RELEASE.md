# SprávaVozidel — vydání v App Storu

Poslední ověření: 30. 9. 2026. Směr potvrzený uživatelem: iOS předplatné přes Apple In-App Purchase; Comgate pro web. Režim externích EU plateb v iOS není vybraný.

## Skutečný stav

- Vlastník potvrdil dokončení registrace a zaplacení členství Apple Developer. Následná kontrola účtu `toozservis@gmail.com` ukazuje **Tomáš Zachurčok (Pending)** a informaci, že zpracování nákupu může trvat až 48 hodin. Neopakovat platbu. Aktivace zatím nebyla potvrzena; aplikace a App Store Connect produkty nebyly založeny.
- Produkční server běží na placeném Renderu (7 USD/měsíc). Comgate test Basic 98,99 Kč byl potvrzen a nezměnil původní licenci. Ostré Comgate účtování dosud není zapnuté.
- Nový klient používá StoreKit 2, zobrazuje ceny dodané App Storem, obsahuje obnovení nákupů a nativní správu předplatného. Původní Comgate objednávka z iOS byla odstraněna; webové propojení a data jsou zachována.
- Server má samostatný ověřovač Apple, vazbu nákupu na náhodný `appAccountToken`, aktuální ověření přes App Store Server API a zpracování oznámení V2. Nevěří samotnému potvrzení z telefonu. Apple integrace zůstává vypnutá, dokud nejsou dokončené skutečné údaje a ověření.
- Testy s izolovanou databází ověřují bezpečnost a stavové přechody. Nejsou důkazem skutečného sandbox nákupu přes Apple. Ten a TestFlight/App Review zůstávají nutné.

## Nastavení, které ještě vyžaduje účet Apple

1. Vyčkat na potvrzení aktivace Apple Developer Program po již oznámené platbě. Apple uvádí 99 USD za rok; skutečná místní cena je uvedena v objednávce. OSVČ se registruje jako jednotlivec a osobní jméno bude uvedené jako prodejce. Smlouvu, osobní údaje a platbu musí potvrdit vlastník.
2. Založit aplikaci **SprávaVozidel**, iOS, bundle ID `cz.toozservis.spravavozidel.ios`. Uložit její skutečné číselné Apple ID. Zajistit podepisování pro App Store.
3. Dokončit Paid Apps Agreement, bankovní a daňové údaje a ověření obchodníka pro EU. Žádné z těchto potvrzení nebylo dosud provedeno.
4. Založit JEDNU skupinu automaticky obnovovaných předplatných. Premium má vyšší úroveň než Basic. Měsíční a roční varianta stejného plánu má stejnou úroveň. Family Sharing není implementován; nezapínat.
5. Založit následující produkty (identifikátory jsou smlouvou mezi klientem a serverem):

| Produkt | Úroveň | Období |
| --- | --- | --- |
| `cz.toozservis.spravavozidel.basic.monthly` | Basic | 1 měsíc |
| `cz.toozservis.spravavozidel.basic.yearly` | Basic | 1 rok |
| `cz.toozservis.spravavozidel.premium.monthly` | Premium | 1 měsíc |
| `cz.toozservis.spravavozidel.premium.yearly` | Premium | 1 rok |

Ceny musí vlastník schválit a nastavit v App Store Connect. Klient nepřebírá cenu webového Comgate ceníku. Neaktivovat neimplementované nabídky ani sdílení v rodině. Popisy plánů musí odpovídat skutečně vynuceným funkcím a limitům.

6. V App Store Connect → Users and Access → Integrations → In-App Purchase vytvořit serverový klíč. Privátní klíč patří pouze do tajných proměnných serveru, nikdy do aplikace, Git historie, chatu nebo webového formuláře mimo schválený server.
7. Konfigurace serveru: `APPLE_IAP_ENABLED=1`, `APPLE_IAP_BUNDLE_ID`, `APPLE_IAP_APP_ID`, `APPLE_IAP_SUBSCRIPTION_GROUP_ID`, `APPLE_IAP_KEY_ID`, `APPLE_IAP_ISSUER_ID`, `APPLE_IAP_PRIVATE_KEY`, `APPLE_IAP_ENVIRONMENT` (`Production` nebo `Sandbox`). Každé nasazení používá jediný ověřovaný režim; žádný automatický přechod z produkce na sandbox. Sandbox testovat na oddělené databázi/testovacích účtech a samostatném backendu, ne na původních účtech. Připravit samostatné sestavení/schéma pro sandbox se správným bundle ID.
8. Před zapnutím provést aditivní migraci `python -m scripts.migrate_apple_billing`. Nemění staré licence, uživatele ani platby. Konfiguraci zapnout až po kontrole migration a testovacího prostředí.
9. Nastavit App Store Server Notifications **V2** na `/api/v1/license/apple/notifications` příslušného HTTPS serveru. Ověřit Apple test notification, skutečný sandbox nákup, obnovení po nové instalaci, renewal, downgrade/upgrade, grace, refund, refund reversal, výpadek sítě, jiný účet aplikace a zrušení obnovování. Pravidelná kontrola vedle oznámení je implementovaná níže; skutečné Apple testy zůstávají nutné. Zajistit variantu backendu pro App Review sandbox; do té doby nelze poslat aplikaci ke schválení.
10. iOS transakci dokončuje až po potvrzeném uložení na serveru. Při chybě zůstane obnovitelná. Staré webhooky vždy znovu načtou aktuální stav od Applu. Potvrzené období vyprší i při opožděném webhooku; uživatelská data se při vypršení nemažou.

## Zbývající závěrečné kontroly celého produktu

- Nativní potvrzení smazání účtu nyní vyžaduje současné heslo, ručně zadaný text a výslovné `deleted: true` od serveru. Neodhlašuje po chybě ani nepředstírá dokončený export. Serverové smazání ale stále vyžaduje prověření všech vazeb, médií a zákonné archivace účetních podkladů; následně změnit povinný export na dobrovolný. Neprovádět mazání skutečných účtů pro test.
- Dopracovat inventuru zpracování dat a App Store privacy labels, účely fotoaparátu/polohy a skutečné zpracovatele. PrivacyInfo.xcprivacy je přiložený s důvodem UserDefaults CA92.1 a bez sledování; část inventury sběru dat ještě není dokončená. Neslibovat nulový sběr osobních údajů. Rozpracované změny e-mailového ověření a fotografií zatím nejsou zahrnuté do této platební změny.
- Ověřit aktuální obchodní/platební podmínky, odstoupení u průběžné digitální služby, reklamace, vrácení peněz, DPA a uchování dokladů. Přechod na Apple musí být zohledněn; staré Comgate souhlasy nelze používat pro Apple nákup.
- EET2: dle ověřeného webu MF dne 30. 9. 2026 je účinnost uvedena od 1. 1. 2027. Prověřit přesné znění účinného zákona, kontaktní tržby servisů a technickou specifikaci. Samotné online SaaS předplatné není důkazem povinnosti/absence povinnosti pro všechny platby servisů. Integrace EET dosud neexistuje; nevydávat fiktivní potvrzení o evidenci.
- Fyzický iPhone: fotoaparát a skutečně uložený snímek, přílohy, export, obnova hesla/deep links. Simulátor nenahrazuje ověření fotoaparátu.
- Role uživatel/servis/admin, sdílení a izolace dat, přístupnost, čitelnost, iPad, výpadky, obnovení záloh a monitorování.
- Verze a build, distribuční archiv, metadata, lokalizované snímky, věková klasifikace, veřejná podpora/privacy URL, bezpečný účet pro App Review a popis všech rolí. Neodesílat nehotové nebo skryté funkce.

## Podklady

- https://developer.apple.com/app-store/review/guidelines/
- https://developer.apple.com/programs/enroll/
- https://developer.apple.com/support/offering-account-deletion-in-your-app/
- https://developer.apple.com/app-store/subscriptions/
- https://github.com/apple/app-store-server-library-python
- https://www.apple.com/certificateauthority/
- https://eet.gov.cz/
- https://coi.gov.cz/faq/5-odstoupeni-od-smlouvy-do-14-dnu-u-sluzeb/

## Ověření této etapy

- 144 testů přesné serverové verze prošlo: 101 Apple/Comgate a 43 kontrol viditelnosti plateb, webového přístupu a oprávnění administrátorů v izolované databázi. Apple pozitivní stavy jsou simulované odpovědi, podvržený JWS ověřuje skutečný oficiální verifier.
- iOS DevelopmentServer pro simulátor i Release pro skutečný iPhone: BUILD SUCCEEDED, kontrola bez podpisu. Nejde o distribuční archiv ani úspěšný App Review.

## Doplnění večer 30. 9. — spolehlivost relace a kontrola App Storu

- iOS commit `09674a1` opravuje tiché selhání ukládání tokenu v nepodepsaném simulátoru. Nový skript sestavuje s podpisem mimo synchronizované Dokumenty. Samostatný test skutečné Keychain třídy prošel pro zápis, aktualizaci, načtení po restartu i oznámení chyby při nepovoleném zápisu.
- Čtyři izolované testy potvrzení smazání a tři nativní UI testy prošly. Admin zůstává přihlášený po třech ukončeních/spuštěních, původní ručně spravovaná licence se nemění a profil má bezpečný potvrzovací formulář. Primární i zrcadlový Xcode projekt se sestavil podepsaný pro simulátor; Release kompilace prošla bez distribučního podpisu.
- Samostatný serverový job `apple.subscription.reconcile` porovnává uložené nákupy se současným ověřeným stavem u Applu. Nevyvolává platby, neposílá zprávy a nevolá Comgate. Výjimka vrátí změny licence zpět; další pokus má odstup 5 minut až 6 hodin. Jednotlivé nákupy mají trvalý záznam kontroly a desetiminutový zámek proti souběhu, který se po havárii uvolní časem.
- Po zapnutí `APPLE_IAP_ENABLED=1` se kontrola spouští po dávkách každých 300 sekund. `APPLE_RECONCILIATION_INTERVAL_SEC` má rozsah 60–3600 s; `ENABLE_APPLE_RECONCILIATION_WORKER=0` vypne pravidelný běh. Aktivní/obnovované nákupy se ověřují nejčastěji po 15 minutách, ostatní jednou denně. Nové i dříve zrušené nákupy získají další kontrolu bez zablokování jednou chybnou položkou. Oddělení Production/Sandbox platí i zde.
- Webová i iOS administrace mají samostatnou srozumitelně popsanou kontrolu, údaj o opakovaných chybách a posledním ověření. Bez konfigurace a všech tří Apple tabulek se zobrazuje čekání na nastavení a akce nejsou dostupné. Job lze po dokončení nastavení pozastavit/obnovit nebo jednorázově ověřit aktuálně naplánované položky.
- Podepsaná Apple oznámení mají přesnou výjimku z režimu údržby; nevztahuje se na nákupní API ani libovolné podadresáře. Ověřování podpisu zůstává povinné.
- Migraci `scripts.migrate_apple_billing` spustit znovu i na prostředí, kde už existují první dvě Apple tabulky. Přidává pouze `apple_reconciliation_state`; nemění původní licence, účty ani Comgate. Bez dokončených Apple údajů integraci zatím nezapínat.
- Přesná připravená serverová verze: 120 Apple/Comgate testů a 50 testů oprávnění, řízení kontrol a viditelnosti plateb prošlo v izolované databázi. Navíc prošlo 6 kontrol webových ovládacích prvků a nativní testy iOS administrátorských akcí. Pozitivní Apple odpovědi jsou stále simulované; tyto výsledky nenahrazují sandbox nákup.
