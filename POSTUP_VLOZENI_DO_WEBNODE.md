# 📝 Postup - Napojení TooZ Hub 2 aplikace na Webnode

## 🎯 Cíl

Zpřístupnit TooZ Hub 2 aplikaci na stránce **https://www.toozservis.cz/toozhub-aplikace/** pomocí přesměrování na:

**https://hub.toozservis.cz/web/index.html**

---

## ✅ Předpoklady

- ✅ Backend běží na **https://hub.toozservis.cz**
- ✅ Aplikace je dostupná na **https://hub.toozservis.cz/web/index.html**
- ✅ Máte přístup do Webnode editoru
- ✅ Stránka `toozhub-aplikace` existuje nebo ji můžete vytvořit

---

## 🚀 Hlavní postup (PŘESMĚROVÁNÍ - PRODUKČNÍ VARIANTA)

### Krok 1: Otevření Webnode editoru

1. Přihlaste se do **Webnode** administrace
2. Otevřete projekt **toozservis.cz**
3. V horním menu klikněte na **Stránky**

### Krok 2: Vytvoření / otevření stránky

1. Přidejte novou stránku nebo upravte existující stránku:
   - **Název stránky:** `TooZ Hub aplikace` (doporučeno)
   - **URL / adresa:** `/toozhub-aplikace/`
   - **Typ:** běžná stránka

### Krok 3: Nastavení přesměrování

1. V nastavení této stránky najděte sekci:
   - **„Přesměrovat na jinou webovou stránku"**  
     (nebo podobný text podle UI Webnode - může být v "Nastavení stránky" → "Přesměrování")

2. Do pole „URL adresa" nebo „Adresa pro přesměrování" vložte:

   ```
   https://hub.toozservis.cz/web/index.html
   ```

3. Uložte změny v nastavení stránky

### Krok 4: Publikace

1. Uložte změny v editoru Webnode
2. Klikněte na **Publikovat**
3. Počkejte na dokončení publikace

### Krok 5: Testování

1. Otevřete stránku v prohlížeči:
   ```
   https://www.toozservis.cz/toozhub-aplikace/
   ```

2. ✅ Stránka se musí automaticky přesměrovat na:
   ```
   https://hub.toozservis.cz/web/index.html
   ```

3. ✅ Aplikace TooZ Hub 2 se načte přes celou stránku

4. ✅ Měla by být dostupná přihlašovací obrazovka

5. ✅ API volání by měla fungovat automaticky (API URL se detekuje automaticky)

---

## 🔧 Řešení problémů

### Aplikace se nenačítá

1. **Zkontrolujte, že backend běží:**
   ```bash
   # V prohlížeči otevřít:
   https://hub.toozservis.cz/health
   ```
   Mělo by vrátit: `{"status":"online","version":"2.1.0",...}`

2. **Zkontrolujte, že přesměrování funguje:**
   - Otevřete Developer Tools (F12) → Network tab
   - Obnovte stránku `https://www.toozservis.cz/toozhub-aplikace/`
   - Mělo by dojít k přesměrování (HTTP 301/302) na `https://hub.toozservis.cz/web/index.html`

3. **Zkontrolujte konzoli prohlížeče:**
   - Otevřít Developer Tools (F12)
   - Karta "Console"
   - Hledat chyby (červené texty)

### Aplikace se načítá, ale API nefunguje

1. **Zkontrolujte konzoli:**
   - Otevřít Developer Tools (F12) → Console
   - Hledat zprávy typu `[APP] API URL: ...`
   - Mělo by být: `https://hub.toozservis.cz`

2. **Zkontrolujte Network tab:**
   - Developer Tools → Network
   - Zkuste přihlásit se
   - Zkontrolujte, kam jdou API požadavky (měly by jít na `https://hub.toozservis.cz`)

### Přesměrování nefunguje

1. **Zkontrolujte nastavení stránky v Webnode:**
   - Otevřete stránku `/toozhub-aplikace/` v editoru
   - Zkontrolujte, že je zapnuté přesměrování
   - Zkontrolujte, že URL je správná: `https://hub.toozservis.cz/web/index.html`

2. **Zkuste alternativní způsob:**
   - Pokud Webnode nepodporuje přesměrování v nastavení stránky, použijte alternativní postup (viz níže)

---

## 🔄 Alternativní postup (iframe – nedoporučeno pro produkci)

> **⚠️ POZNÁMKA:** Tato varianta se v produkci nepoužívá. Slouží pouze jako alternativní / vývojářská možnost.

Pokud z nějakého důvodu nemůžete použít přesměrování, můžete použít iframe variantu:

1. Otevřete stránku `/toozhub-aplikace/` v Webnode editoru
2. Klikněte na **"Přidat prvek"** → **"HTML / Code"**
3. Vložte tento kód:

```html
<div style="width: 100%; height: 90vh; min-height: 800px; margin: 0; padding: 0;">
    <iframe 
        src="https://hub.toozservis.cz/web/index.html" 
        style="width: 100%; height: 100%; min-height: 800px; border: none; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);"
        allow="camera; microphone; geolocation"
        title="TooZ Hub 2 - Vozový park">
    </iframe>
</div>
```

**Nebo použijte podrobný návod v souboru:** `WEBNODE_IFRAME_VARIANTA_DEV.md`

> **Důležité:** Tato varianta má omezení a není doporučena pro produkci. Preferujte přesměrování.

---

## 📋 Kontrolní seznam

- [ ] ✅ Backend běží na `https://hub.toozservis.cz`
- [ ] ✅ Aplikace je dostupná na `https://hub.toozservis.cz/web/index.html`
- [ ] ✅ Health check vrací: `{"status":"online"}`
- [ ] ✅ Stránka `toozhub-aplikace` existuje v Webnode
- [ ] ✅ Přesměrování je nastaveno v nastavení stránky
- [ ] ✅ URL přesměrování: `https://hub.toozservis.cz/web/index.html`
- [ ] ✅ Stránka byla publikována
- [ ] ✅ Přesměrování funguje na `https://www.toozservis.cz/toozhub-aplikace/`
- [ ] ✅ Aplikace se načítá správně
- [ ] ✅ Přihlášení funguje
- [ ] ✅ API volání fungují

---

## 🎯 Výsledek

Po dokončení všech kroků bude aplikace dostupná na:

**https://www.toozservis.cz/toozhub-aplikace/**

Stránka automaticky přesměruje na:

**https://hub.toozservis.cz/web/index.html**

Aplikace bude:
- ✅ Automaticky používat produkční API (`https://hub.toozservis.cz`)
- ✅ Fungovat bez jakýchkoliv manuálních nastavení
- ✅ Být responzivní pro mobilní zařízení
- ✅ Podporovat přihlášení, registraci a správu vozidel
- ✅ Zobrazena přes celou stránku (ne v iframe)

---

## 💡 Tipy

1. **Testování před publikováním:**
   - Nejdřív uložte změny jako draft
   - Otestujte na preview URL
   - Teprve potom publikujte

2. **Zabezpečení stránky:**
   - Můžete stránku nastavit jako "Pouze pro přihlášené" v Webnode nastavení
   - Nebo použít Webnode ochranu stránky heslem

---

## 📞 Podpora

Pokud narazíte na problémy:

1. Zkontrolujte sekci "Řešení problémů" výše
2. Otevřete Developer Tools (F12) a zkontrolujte chyby v Console
3. Otestujte, že backend běží: `https://hub.toozservis.cz/health`
4. Zkuste otevřít aplikaci přímo: `https://hub.toozservis.cz/web/index.html`

---

**Hotovo! Aplikace je nyní dostupná na vašem webu!** 🎉
