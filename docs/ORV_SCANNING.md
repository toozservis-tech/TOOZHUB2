# Přidání vozidla z ORV

Fotografie obou stran čte iOS Vision v telefonu, bez jazykových oprav identifikátorů. Pixelové rozměry jsou nezávislé na hustotě displeje. VisionKit zajišťuje automatické ostření, ořez a perspektivu; skutečné ostření vyžaduje test na fyzickém telefonu. Po snímcích následuje kontrola náhledů a výslovné odeslání soukromého podkladu na server. Server ukládá obrázky pod původní ochranou vlastnictví a mazání; klientský OCR text je pouze neověřený návrh. Starší klient může využít dvě omezená serverová OCR čtení na stranu; neúspěch dalšího čtení nesmaže již získaný text.

QR nového českého ORV obsahuje číslo dokladu (ověřeno na veřejném vzoru MD, strana 6: UBK000000). Aplikace přijímá pouze tento formát, nikdy neotevírá adresu z QR. Nové vyhledání na `/api/v1/vehicles/registry-lookup` přijímá právě jeden platný VIN nebo číslo ORV. Používá stávající schválený serverový klíč STK_REGISTRY_API_KEY a pouze oficiální API; zakazuje přesměrování, omezuje velikost odpovědi a vrací jen vyjmenované technické údaje. Osobní údaje, klíč a celé odpovědi se nezpřístupňují ani nezapisují do logu. Platnost STK je výhradně explicitní údaj registru. Rok výroby se neodhaduje z první registrace. Načtení nepřiděluje přístup k vozidlu.

Po kontrole a potvrzení VIN se doplní údaje z registru a zobrazí finální kontrola. Přenos do formuláře nic neukládá; běžný uživatel i servis následně potvrdí založení vozidla. Výpadek zachová návrh a nabídne opakování nebo ruční kontrolu. Odhlášení/zavření zneplatní pozdní odpovědi. QR cesta nepotřebuje fotografie; nepotvrzuje existenci naskenovaného podkladu.

Ověření: test_document_registry.py (validace, chybné vozidlo, minimalizace, autentizace, limity, pevný cíl), test_vehicle_orv_flow.py (místní OCR a evropská označení polí, částečný timeout), test_orv_durable_storage.py (soukromé ukládání a mazání). Nativní ORVScanningTests zahrnuje skutečné Vision OCR syntetického dokladu, pixelový resize a orientaci, serverový kontrakt, QR validaci a čitelnost úvodní obrazovky. Reálné ORV a automatické ostření na iPhonu se ověřují samostatně; test v simulátoru je neprokazuje.

Zdroje: https://dataovozidlech.cz/wwwroot/data/RSV_Verejna_API_DK_v1_0.pdf a https://md.gov.cz/getattachment/Dokumenty/Silnicni-doprava/Schvalovani-vozidel/Metodiky/Souhrnne_informace_z_Ministerstva_dopravy_kveten_2023.pdf.aspx?lang=cs-CZ

## Scan lifecycle and document identity

- Both camera entry points request access only after a user action and before checking QR availability. Denied access offers the application Settings button; restricted/unsupported/temporarily unavailable cameras have distinct messages and manual VIN entry remains available. Closing the sheet or signing out invalidates delayed permission responses.
- Replacing the front photo also discards the previous back photo and previous review data. Both sides must be captured again for a new document. Successful QR lookup discards earlier photograph drafts.
- Conflicting exact or labelled VIN candidates on either image leave VIN blank and display a specific warning. Identical repeated VINs and equivalent OCR corrections remain supported. The user still reviews the VIN before registry enrichment; this is not proof of ownership.
- Editing VIN after applying the reviewed document to either vehicle form blocks saving that document until it is reviewed again. Reappearing after a scanner sheet does not reinitialize the user form.
- On the server, a scan's vehicle association is locked and may be saved again for the same vehicle, but cannot be moved/copied to a second vehicle. A real isolated PostgreSQL two-transaction test exercises preloaded stale ORM instances and verifies exactly one association.
- Physical autofocus, real document OCR and live registry lookup on the connected iPhone remain a separate acceptance check; simulator/synthetic fixtures do not prove those hardware results.
