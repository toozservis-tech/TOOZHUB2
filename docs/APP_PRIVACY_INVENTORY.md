# SprávaVozidel — inventura údajů pro vydání iOS

Pracovní inventura podle zdrojového kódu, 30. 9. 2026. Není to potvrzení právního souladu ani zveřejněné prohlášení v App Store Connect. Před odesláním musí odpovídat finálnímu sestavení, serverové konfiguraci a skutečným smlouvám se zpracovateli.

## Připravené kategorie pro Apple

Všechny níže uvedené údaje mohou být propojené s přihlášeným účtem. Účel v manifestu je **App Functionality**: provoz funkce, přihlášení, podpora a zabezpečení. Reklamní sledování, sdílení s datovými brokery a reklamní SDK nebyly v aktivním nativním projektu nalezeny. Manifest uvádí tracking=false. Interní přehled nákladů nazvaný „analytics“ není sám o sobě reklamní analytika.

| Kategorie Apple | Skutečný údaj / tok | Zdroj v projektu |
| --- | --- | --- |
| Name | Jméno zákazníka, název servisu, jméno autora záznamu | `Customer`, `ServiceRegistrationRequest`, `RepairEvidencePhoto` |
| Email Address | Přihlášení, ověření, obnova hesla, servisní vazby, adresát oznámení | `Customer`, `ServiceCustomerInvite`, `EmailNotificationLog` |
| Phone Number | Kontaktní telefon z profilu nebo žádosti servisu | `Customer.phone`, registrace a profil |
| Physical Address | Kontaktní/fakturační adresa a město | `Customer`, `ServiceRegistrationRequest`, doklady |
| Other Financial Info | Náklady na opravy, částky dokladů, kredit a případné nedoplatky | `ServiceRecord`, `ServiceDocumentIngestion`, `LicenseSubscription` |
| Coarse Location | Město zvolené ručně nebo získané pro vyhledání servisu; profilové město a případná poloha odvozená z IP | iOS `RootView.AreaLocation`, `/api/v1/services/area-directory`, bezpečnostní konfigurace |
| Photos or Videos | Fotografie vozidla, dokladů a průběhu opravy; aplikace aktuálně používá fotografie | `Vehicle.photo_path`, ORV skeny, `RepairEvidencePhoto`, přílohy |
| Customer Support | Předmět a text požadavku na podporu, e-mail účtu | iOS `AccountView`, `/user/support` |
| Other User Content | VIN, SPZ, poznámky, servisní historie, rezervace, připomínky, dokumenty a jejich OCR výstup | modely Vehicle Hub a soukromé úložiště |
| Search History | Evidované vyhledání vozidla servisem podle VIN/SPZ včetně výsledku | `ServiceVehicleLookupAudit` |
| User ID | ID zákazníka a organizace, přístupové relace, náhodný identifikátor propojení nákupu Apple | `Customer`, `Tenant`, `AppleBillingIdentity` |
| Purchase History | Tarif, období, transakce a ověřený stav předplatného | `LicenseSubscription`, `LicensePaymentTransaction`, `AppleSubscription` |
| Product Interaction | Přístupy na funkce, poslední přihlášení a administrátorské akce v bezpečnostním auditu | `SecurityAccessLog`, `DeveloperActionAuditLog`, `last_seen_at` |
| Other Data Types | IP adresa a údaj o klientovi pro zabezpečení; IČO/DIČ podnikatele | `SecurityAccessLog`, `Customer` |

Výběr „Data Not Collected“ by byl nesprávný. Kategorie jsou vložené do `Sources/TooZHub/Resources/PrivacyInfo.xcprivacy` v autoritativním iOS projektu. Hodnoty kategorií a účelu byly porovnány s oficiálními klíči Apple. Zveřejnění odpovědí v App Store Connect ještě neproběhlo.

## Poloha a oprávnění

- Nativní lokátor žádá polohu jen po volbě uživatele, používá Core Location s kilometrovou požadovanou přesností a Apple geocoder. Na vlastní adresářové API posílá název města, ne GPS souřadnice. Město jde zadat ručně. Poslední města se ukládají do UserDefaults v telefonu.
- Bezpečnostní modul od této změny ve výchozím nastavení neposílá návštěvnickou IP na ipwho.is, neposílá GPS na Nominatim a neukládá GPS z hlaviček prohlížeče. IP, čas, účet a výsledek přihlášení zůstávají v bezpečnostním záznamu.
- Volby `ENABLE_IP_GEOLOOKUP`, `ENABLE_BROWSER_GEOLOCATION_OVERRIDE`, `ENABLE_REVERSE_GEOCODE` mají výchozí hodnotu 0. Existující explicitní hodnota 1 má přednost; před zveřejněním je nutné zkontrolovat prostředí. Opětovné zapnutí vyžaduje aktualizaci inventury, transparentního informování a posouzení zpracovatele. Při ukládání přesné polohy doplnit také Precise Location.
- Samostatné starší API `/services/discovery` může geokódovat adresu servisu přes Nominatim. Nativní záhlaví používá `/services/area-directory`; jde o různé toky. Odstranění IP geolokace proto samo neodstraňuje všechny kontakty s Nominatim.
- Face ID ověřuje odemknutí lokálně. Aplikace nepřebírá biometrickou šablonu. Samotné použití Face ID není důvod vykazovat sběr biometrických dat.
- Fotoaparát a fotoknihovna slouží k uživatelem vybraným snímkům. iOS připravuje JPEG pro odeslání; obecné souborové přílohy ale mohou obsahovat vlastní metadata a osobní údaje. Slib „žádné další údaje v dokumentech“ by nebyl správný.
- V aktivním iOS zdrojovém kódu nebyl nalezen sběr kontaktů, reklamního ID, systémové historie prohlížení, zvuku ani dat HealthKit. Identifikátory pro staré PC instalace a web push nejsou důkazem jejich sběru nativní iOS aplikací.
- `NSPrivacyAccessedAPICategoryUserDefaults` má důvod CA92.1: vlastní předvolby aplikace. Při přidání dalších knihoven nebo rozhraní s povinným důvodem je nutná nová kontrola.

## Příjemci a infrastruktura k doložení

| Příjemce / služba | Účel | Co ještě ověřit |
| --- | --- | --- |
| Render | Běh API a technické protokoly | Region, délka logů, DPA a nastavení záloh |
| Supabase PostgreSQL / soukromý Storage | Databáze a přílohy | Region, přístupové politiky, DPA, obnova zálohy a odstranění objektů |
| Cloudflare | DNS a případně proxy podle DNS nastavení | Skutečné proxy režimy, logy a smluvní podmínky |
| Resend / nakonfigurovaný SMTP | Doručování provozních e-mailů | Aktivní poskytovatel, retenční doba obsahu a adresátů, DPA |
| Apple | App Store předplatné, geokódování a uživatelem otevřené Mapy | Dokončit IAP konfiguraci a sandbox ověření. Vlastní server ukládá stav nákupu, nikoli údaje k Apple platební kartě. |
| Servis vybraný zákazníkem | Záznamy a dokumentace vozidla v povoleném rozsahu | Pravdivé vysvětlení vazeb a testy odvolání přístupu |
| OSM Nominatim / ipwho.is | Volitelné výše popsané geolokační toky | Nezaměňovat nový výchozí stav s ověřením explicitních produkčních proměnných |
| Comgate | Webové předplatné a jeho historie | Nativní iOS nákup přes Apple; stávající webové platby vyžadují samostatné informace |

Manifest nemění žádné smlouvy se zpracovateli ani retenční lhůty. Před publikací doplnit konkrétní platné údaje do veřejných zásad, včetně účelů, právních základů, příjemců, dob uchování a práv uživatele. Nepoužívat nepodložené obecné sliby „všechna data jen v EU“ nebo „vše se ihned vymaže“.

## Odstranění účtu — zjištěná otevřená práce

Nativní formulář je dostupný v účtu a ověřuje heslo, ručně zadané potvrzení a kladnou odpověď serveru. Nové serverové testy ověřují omezení pokusů a vrácení neúspěšné transakce zpět bez úniku interní chyby.

Původní `delete_customer_account` není ještě dostatečný pro vydání: nepokrývá všechny nové vazby, neumí bezpečně odstranit soukromé soubory a obsahuje široké mazání celé organizace. Export je zatím povinný a po dokončení bezpečného serverového postupu musí být dobrovolný. Potřebná je zvláštní ochrana sdílených/převedených vozidel, zákonně uchovávaných dokladů, zastavení obnovování Comgate a anonymizované oddělení Apple transakcí. Testy této etapy nenahrazují tyto práce. Žádný skutečný účet nebyl kvůli testům odstraněn.

## Ověřené primární podklady

- Apple: https://developer.apple.com/app-store/app-privacy-details/
- Apple: https://developer.apple.com/documentation/bundleresources/describing-data-use-in-privacy-manifests
- Apple: https://developer.apple.com/documentation/bundleresources/app-privacy-configuration/nsprivacycollecteddatatypes/nsprivacycollecteddatatype
- Apple: https://developer.apple.com/support/offering-account-deletion-in-your-app/
