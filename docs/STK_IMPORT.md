# Import kilometrů a platnosti STK

Po úspěšném ručním opsání CAPTCHA a načtení historie z kontrolatachometru.cz se pro stejné VIN zavolá oficiální API registru vozidel. Do `Vehicle.stk_valid_until` se přenáší pouze výslovné `Data.PravidelnaTechnickaProhlidkaDo`, pokud `Status == 1` a `Data.VIN` odpovídá dotazu. Kilometry a datum se uloží v jedné transakci se stávající kontrolou oprávnění a deduplikací historie. Současná platnost podle registru je v technickém importním podkladu označena jako údaj o vozidle v okamžiku importu, nikoli platnost každé historické prohlídky.

Není přípustné vypočítávat platnost přičtením dvou let k nejnovějším kilometrům. Přehled zahrnuje také evidenční kontroly a emise. Import přijme i již prošlou výslovnou platnost; nemá ji prodlužovat ani vybírat větší ze dvou dat. Chybějící či neplatné datum, jiné VIN, limit, výpadek nebo chybějící klíč zachová dosavadní STK a neblokuje úspěšný import kilometrů.

## Konfigurace

Serverový `STK_REGISTRY_API_KEY` obsahuje existující klíč dataovozidlech.cz. Je oddělený od obecného staršího dekodéru VIN, jehož konfiguraci tato oprava nezapíná. Pro kompatibilitu lze použít již nastavený `DATAOVO_API_KEY`. Klíč nesmí být v iOS, Gitu, chatu nebo logu.

Povolen je pouze přesný `https://api.dataovozidlech.cz/api/vehicletechnicaldata/v2` (výchozí `DATAOVO_API_BASE_URL`). Bez přesměrování, bez síťového proxy z prostředí, s ověřením TLS, omezením času a velikosti odpovědi. API se dotazuje až po úspěšném načtení tachometru, jednou na import; při limitu se neopakuje automaticky.

## Odpověď a aplikace

Obě odpovědi `tachometer/lookup` a `/{id}/tachometer/submit` přidávají volitelné `stk_valid_until`, `stk_validity_status` a `stk_validity_source`. Při úspěchu status `verified`. Klient převezme datum pouze s tímto stavem. Existující detail i jeho cache se aktualizují z vráceného vozidla; formuláře nového/editovaného vozidla a servisní formulář přebírají ověřené datum. Zpětná kompatibilita se starším serverem zachová datum a zobrazí, že platnost nebyla ověřena.

Není nutná migrace databáze ani změna rolí. Obnovení oprávnění nebo VIN během dotazu stále znemožní uložení výsledku. Tato změna neaktivuje rozpracovanou pokladnu/EET.

## Zdroje a ověření

Oficiální dokumentace RSV API, 21. 1. 2025: https://dataovozidlech.cz/wwwroot/data/RSV_Verejna_API_DK_v1_0.pdf — rozhraní v2, identifikace VIN, výslovná platnost, limit 27 požadavků za minutu na klíč. Ověřeno 1. 10. 2026. Živý dotaz existujícím klíčem na veřejný vzor VIN z dokumentace vrátil ověřenou platnost; nešlo o změnu skutečného vozidla.

Regrese: `tests/api/test_inspection_validity.py`, `test_vehicle_tachometer_flow.py`, `test_vehicle_mileage_entry.py`, `test_vehicle_permission_boundaries.py`; iOS `TachometerValidityTests`. Testy pokrývají přímo trvalé uložení a opakovaný import bez duplicit, neúplná data, shodu VIN, neplatná data, výpadky, transport a aktualizaci nativního detailu/cache.
