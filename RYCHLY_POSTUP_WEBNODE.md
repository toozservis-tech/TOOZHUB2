# ⚡ Rychlý postup - Vložení TooZ Hub 2 do Webnode

## 🎯 Cíl stránky

**https://www.toozservis.cz/toozhub-aplikace/**

---

## ✅ Předpoklady

- ✅ Backend běží na `https://hub.toozservis.cz`
- ✅ Stránka `toozhub-aplikace` existuje v Webnode (nebo ji vytvoříte)

---

## 🚀 3 jednoduché kroky

### 1️⃣ Otevřít Webnode editor

- Přihlásit se do Webnode
- Přejít na stránku `/toozhub-aplikace/`
- Kliknout na **"Přidat prvek"** → **"HTML / Code"**

### 2️⃣ Zkopírovat a vložit tento kód

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

**Nebo otevřít soubor:** `WEBNODE_IFRAME_KOD.html` a zkopírovat jeho obsah

### 3️⃣ Uložit a publikovat

- Kliknout **"Uložit"** v HTML editoru
- Uložit stránku
- Publikovat změny

---

## ✅ Hotovo!

Otevřít: **https://www.toozservis.cz/toozhub-aplikace/**

Aplikace by se měla načíst a fungovat! 🎉

---

## 🔧 Pokud něco nefunguje

1. **Zkontrolovat backend:**
   - Otevřít: `https://hub.toozservis.cz/health`
   - Mělo by vrátit: `{"status":"online"}`

2. **Zkontrolovat konzoli:**
   - Stisknout `F12` → Karta "Console"
   - Hledat chyby (červené texty)

3. **Podrobnější postup:**
   - Viz `POSTUP_VLOZENI_DO_WEBNODE.md`

---

**Jednoduché a rychlé!** ⚡



