# TooZ Hub 2 - Webová verze

## Použití

1. **Nastavte API URL:**
   - Otevřete `index.html` v textovém editoru
   - Najděte řádek: `const API_URL = ...`
   - Nastavte URL vašeho API serveru (např. `http://127.0.0.1:8001` nebo `https://hub.toozservis.cz`)

2. **Vložení do Webnode:**
   - Zkopírujte obsah `index.html`
   - V Webnode editoru přidejte HTML blok
   - Vložte zkopírovaný kód

3. **Nebo použijte iframe:**
   ```html
   <iframe 
       src="https://hub.toozservis.cz/web/index.html" 
       width="100%" 
       height="800px" 
       frameborder="0">
   </iframe>
   ```

## Funkce

- ✅ Přihlášení a registrace
- ✅ Zobrazení vozidel
- ✅ Přidání nového vozidla
- ✅ Responzivní design

## Poznámky

- Webová verze komunikuje s backend API
- Všechna data se ukládají do backend databáze
- Pro plnou funkcionalitu je potřeba spuštěný backend server


