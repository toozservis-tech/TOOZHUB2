# Soukromé fotografie osvědčení o registraci

Od 1. 10. 2026 se nové normalizované JPEG snímky obou stran ukládají přes stejné
soukromé trvalé úložiště jako ostatní fotografie. Lokální DATA_DIR je pouze cache.
Objekty nejsou veřejné; nejde o přílohy e-mailu ani analytická data.

Před prvním zápisem do úložiště se v databázi uloží stav `processing` a přesné
unikátní cesty obou stran. Nový pokus nepoužívá cestu po dříve smazaném snímku,
ani při opakovaném použití číselného ID databáze. Vytváření snímku drží zámek účtu,
a odstranění účtu tedy nemůže předběhnout ještě běžící upload.

Úspěch (`review`) se vrací až po uložení obou stran a zpracování OCR. Při běžné
chybě se obě zamýšlené cesty zařadí do trvalé fronty odstranění, i když server
neví, zda opožděný upload do úložiště dorazil. Chybějící objekt lze bezpečně
odstranit opakovaně. Přerušený proces ponechá inventář souborů; nezpracované,
k vozidlu nepřiřazené pokusy starší 24 hodin uklízí pracovník mazání. Zamčené
probíhající operace přeskočí. Kontrolované a potvrzené dokumenty se tím nemažou. Automatický úklid pozná pouze
nové unikátní cesty; staré pokusy s původním formátem cest nechává beze změny.
Neúplný pokus nelze použít jako potvrzený doklad při uložení vozidla.

Tato oprava nemůže sama obnovit soubory ztracené před zavedením trvalého ukládání.
Staré soubory, pokud jsou v původní záloze, je potřeba přenést zvlášť po kontrole
vazeb a účelu uchování. Plošně se žádné existující složky nemažou.

Testy používají falešného poskytovatele, syntetické obrázky a oddělenou databázi:
obnova po ztrátě cache, ztracená odpověď při nahrávání první/druhé strany, chyba
OCR, ukončení procesu, nepoužitelnost neúplného dokladu a úklid pouze opuštěných
pokusů. Skutečné doklady uživatelů nebyly při ověření čtené ani měněné.
