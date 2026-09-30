# Administrátorské ověření

Administrátorské role `admin` a `developer_admin` podléhají serverové kontrole druhého faktoru. Vlastní profil, ověření e-mailu a přesně vyjmenované kroky nastavení jsou dostupné před vstupem; ostatní požadavky musí mít platný stav účtu, shodnou verzi relace a ověření heslem + OTP mladší 15 minut. Klientské skrytí tlačítek není autorizační pravidlo.

## Nasazení

Nasazovat server, webové soubory a odpovídající iOS sestavení společně. Starší iOS sestavení bez obrazovky ověření bude administrátorské požadavky dostávat zamítnuté. Běžné účty bez administrátorské role povinnému administrátorskému ověření nepodléhají.

Při startu se přidají tabulky `mfa_security_state`, `mfa_login_challenges`, `mfa_attempt_budgets`; platné starší TOTP klíče se zašifrují. Migrace nemaže účty, vozidla ani platby. Nesprávný uložený klíč nepovolí přihlášení jen heslem. Vlastník nastavuje autentikátor osobně, nikoliv v chatu. Testovací účty do ostré databáze nevkládat.

## Klíče a obnova

Fernet používá klíč odvozený HMAC-SHA256 z existujícího serverového JWT kořene s odděleným účelem `SpravaVozidel/TOTP/storage/v1`. Databázová záloha bez serverového kořene neobsahuje čitelné TOTP klíče. Přístup ke kořeni a databázi současně však znamená přístup k těmto klíčům; oddělené uložení a omezení provozního přístupu jsou nutné.

**JWT kořen nelze prostě vyměnit bez převodu TOTP ciphertextů.** Pro rotaci je nutné v odděleném prostředí ověřit dešifrování starým kořenem, šifrování novým kořenem, atomickou migraci a obnovu ze zálohy. Kořeny ani plaintexty nepatří do logů, exportů ani repozitáře. Automatizovaná rotace a její nácvik zůstávají podmínkou provozní připravenosti.

Po migraci se nevracet na starý kód, který očekává nešifrované klíče. Případná oprava musí zachovat kompatibilitu šifrovaných faktorů a databázové tabulky. Obnova hesla neruší druhý faktor; vypnutí druhého faktoru není administrátorovi povolené.

## Testované hrozby

Přepsání aktivního faktoru, chybějící/poškozený klíč, opakovaný OTP, opakovaná výzva, vypršení, restart limitů, stará relace, deaktivace účtu, změna hesla, neověřená administrátorská cookie a volitelná autentizace. Export osobních dat nezahrnuje ani hash hesla, ani zašifrovaný klíč autentikátoru.

Východiska: [OWASP MFA](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html) a [NIST SP 800-63B](https://pages.nist.gov/800-63-4/sp800-63b.html). Není deklarována úplná shoda s NIST; aktuální uživatelské minimum hesla zůstává dle zadání šest znaků. Doporučené přísnější zásady hesel a obnova druhého faktoru vyžadují další dokončení před vydáním.
