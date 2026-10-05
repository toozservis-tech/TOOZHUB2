# Evidence Vozidel — webová aplikace

Zákaznický a servisní vstup: `/web/customer.html` nebo kořen serveru.
Administrace: `/admin-login` (stále vyžaduje administrátorskou roli a MFA).

Rozhraní používá stejný server, účty, vozidla a tarify jako iOS. Přístupový token je omezen na relaci prohlížeče a požadavky na stejný origin. Podrobnosti a rozsah ověření: `docs/CUSTOMER_WEB_RELEASE.md`.

`index.html` zůstává sdíleným zdrojem šablony a chráněným administrátorským kompatibilním vstupem. Zákaznická cesta načítá `customer-session.js`. Staré `index_minimal.html`, iframe varianty a záložní soubory se nezpřístupňují.
