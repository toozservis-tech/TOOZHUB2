# 📝 Postup - Vložení TooZ Hub 2 aplikace do Webnode

## 🎯 Cíl

Zpřístupnit TooZ Hub 2 aplikaci na stránce **https://www.toozservis.cz/toozhub-aplikace/**

---

## ✅ Předpoklady

- ✅ Backend běží na **https://hub.toozservis.cz**
- ✅ Aplikace je dostupná na **https://hub.toozservis.cz/web/index.html**
- ✅ Máte přístup do Webnode editoru
- ✅ Stránka `toozhub-aplikace` existuje nebo ji můžete vytvořit

---

## 🚀 Krok za krokem

### Krok 1: Otevření Webnode editoru

1. Přihlaste se do **Webnode** administrace
2. Přejděte na stránku **"toozhub-aplikace"**
   - Pokud stránka neexistuje, vytvořte ji:
     - **Název stránky:** `toozhub-aplikace`
     - **URL:** `/toozhub-aplikace/`
     - **Typ:** běžná stránka

### Krok 2: Přidání HTML bloku

1. V editoru klikněte na **"Přidat prvek"** nebo **"+"** (plus)
2. Vyberte **"HTML / Code"** nebo **"Vlastní HTML"**
3. Klikněte na prvek pro úpravu

### Krok 3: Vložení iframe kódu

**Zkopírujte a vložte tento HTML kód:**

```html
<div style="width: 100%; height: 90vh; min-height: 800px; margin: 0; padding: 0;">
    <iframe 
        id="toozhub-app-frame"
        src="https://hub.toozservis.cz/web/index.html" 
        style="width: 100%; height: 100%; min-height: 800px; border: none; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); display: block;"
        allow="camera; microphone; geolocation"
        scrolling="auto"
        title="TooZ Hub 2 - Vozový park">
    </iframe>
</div>
```

### Krok 4: Uložení a publikování

1. Klikněte na **"Uložit"** nebo **"OK"** v HTML editoru
2. Uložte stránku v Webnode editoru
3. Publikujte změny (pokud je potřeba)

### Krok 5: Testování

1. Otevřete stránku v prohlížeči:
   ```
   https://www.toozservis.cz/toozhub-aplikace/
   ```
2. ✅ Aplikace by se měla načíst a zobrazit
3. ✅ Měla by být dostupná přihlašovací obrazovka
4. ✅ API volání by měla fungovat automaticky (API URL se detekuje automaticky)

---

## 🎨 Upravená verze s lepším vzhledem (volitelné)

Pokud chcete lepší vzhled s loading indikátorem, použijte tuto verzi:

```html
<div id="toozhub-container" style="width: 100%; height: 90vh; min-height: 800px; margin: 20px auto; padding: 0; position: relative;">
    <div id="loading-indicator" style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #667eea; font-size: 18px; z-index: 1;">
        Načítání aplikace TooZ Hub 2...
    </div>
    <iframe 
        id="toozhub-app-frame"
        src="https://hub.toozservis.cz/web/index.html" 
        style="width: 100%; height: 100%; min-height: 800px; border: none; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.15); display: block; opacity: 0; transition: opacity 0.3s ease-in-out;"
        allow="camera; microphone; geolocation"
        scrolling="auto"
        title="TooZ Hub 2 - Vozový park"
        onload="document.getElementById('loading-indicator').style.display='none'; document.getElementById('toozhub-app-frame').style.opacity='1';">
    </iframe>
</div>

<script>
    // Timeout pro skrytí loading indikátoru (pokud se iframe nenačte do 10 sekund)
    setTimeout(function() {
        var loading = document.getElementById('loading-indicator');
        var iframe = document.getElementById('toozhub-app-frame');
        if (loading && loading.style.display !== 'none') {
            loading.innerHTML = 'Chyba při načítání aplikace. Zkuste obnovit stránku.';
            loading.style.color = '#e53e3e';
        }
        if (iframe && iframe.style.opacity === '0') {
            iframe.style.opacity = '1';
        }
    }, 10000);
</script>
```

---

## 📱 Responzivní verze (pro mobilní zařízení)

Pokud chcete lepší zobrazení na mobilních zařízeních:

```html
<div style="width: 100%; height: 90vh; min-height: 600px; margin: 0; padding: 10px; box-sizing: border-box;">
    <iframe 
        id="toozhub-app-frame"
        src="https://hub.toozservis.cz/web/index.html" 
        style="width: 100%; height: 100%; min-height: 600px; border: none; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); display: block;"
        allow="camera; microphone; geolocation"
        scrolling="auto"
        title="TooZ Hub 2 - Vozový park">
    </iframe>
</div>

<style>
    @media (max-width: 768px) {
        #toozhub-app-frame {
            min-height: 500px !important;
            border-radius: 0 !important;
        }
    }
</style>
```

---

## 🔧 Řešení problémů

### Aplikace se nenačítá

1. **Zkontrolujte, že backend běží:**
   ```bash
   # V prohlížeči otevřít:
   https://hub.toozservis.cz/health
   ```
   Mělo by vrátit: `{"status":"online",...}`

2. **Zkontrolujte konzoli prohlížeče:**
   - Otevřít Developer Tools (F12)
   - Karta "Console"
   - Hledat chyby (červené texty)

3. **Zkontrolujte CORS:**
   - V konzoli hledat chyby typu "CORS policy"
   - Zkontrolujte, že `.env` obsahuje:
     ```
     ALLOWED_ORIGINS=https://www.toozservis.cz,https://toozservis.cz
     ```

### Černý prázdný prostor místo aplikace

1. **Zkontrolujte výšku iframe:**
   - Zkuste změnit `height: 90vh` na `height: 1200px`
   - Nebo použít `min-height: 1200px`

2. **Zkontrolujte, že URL je správná:**
   - Měla by být: `https://hub.toozservis.cz/web/index.html`
   - Otevřete URL přímo v prohlížeči a zkontrolujte, že funguje

### Aplikace se načítá, ale API nefunguje

1. **Zkontrolujte konzoli:**
   - Otevřít Developer Tools (F12) → Console
   - Hledat zprávy typu `[APP] API URL: ...`
   - Mělo by být: `https://hub.toozservis.cz`

2. **Zkontrolujte Network tab:**
   - Developer Tools → Network
   - Zkuste přihlásit se
   - Zkontrolujte, kam jdou API požadavky (měly by jít na `https://hub.toozservis.cz`)

---

## 📋 Kontrolní seznam

- [ ] ✅ Backend běží na `https://hub.toozservis.cz`
- [ ] ✅ Aplikace je dostupná na `https://hub.toozservis.cz/web/index.html`
- [ ] ✅ Stránka `toozhub-aplikace` existuje v Webnode
- [ ] ✅ HTML kód byl vložen do Webnode editoru
- [ ] ✅ Stránka byla uložena a publikována
- [ ] ✅ Aplikace se načítá na `https://www.toozservis.cz/toozhub-aplikace/`
- [ ] ✅ Přihlášení funguje
- [ ] ✅ API volání fungují

---

## 🎯 Výsledek

Po dokončení všech kroků bude aplikace dostupná na:

**https://www.toozservis.cz/toozhub-aplikace/**

Aplikace bude:
- ✅ Automaticky používat produkční API (`https://hub.toozservis.cz`)
- ✅ Fungovat bez jakýchkoliv manuálních nastavení
- ✅ Být responzivní pro mobilní zařízení
- ✅ Podporovat přihlášení, registraci a správu vozidel

---

## 💡 Tipy

1. **Testování před publikováním:**
   - Nejdřív uložte změny jako draft
   - Otestujte na preview URL
   - Teprve potom publikujte

2. **Zabezpečení stránky:**
   - Můžete stránku nastavit jako "Pouze pro přihlášené" v Webnode nastavení
   - Nebo použít Webnode ochranu stránky heslem

3. **Optimalizace výkonu:**
   - Iframe se načítá až při zobrazení stránky
   - Pokud je stránka dlouhá, iframe můžete umístit až dolů (lazy loading)

---

## 📞 Podpora

Pokud narazíte na problémy:

1. Zkontrolujte sekci "Řešení problémů" výše
2. Otevřete Developer Tools (F12) a zkontrolujte chyby v Console
3. Otestujte, že backend běží: `https://hub.toozservis.cz/health`

---

**Hotovo! Aplikace je nyní dostupná na vašem webu!** 🎉



