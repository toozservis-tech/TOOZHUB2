# ⚡ Rychlý postup – napojení TooZ Hub 2 na Webnode

## 🎯 Cíl

Zajistit, aby stránka na Webnode:

**https://www.toozservis.cz/toozhub-aplikace/**

automaticky přesměrovala uživatele do aplikace TooZ Hub 2 běžící na:

**https://hub.toozservis.cz/web/index.html**

---

## ✅ Předpoklady

- Backend TooZ Hub 2 běží na:
  - `https://hub.toozservis.cz`
  - frontend aplikace: `https://hub.toozservis.cz/web/index.html`
- Stránka `toozhub-aplikace` je vytvořená v Webnode (nebo ji vytvoříte).

---

## 🚀 Postup ve Webnode (PŘESMĚROVÁNÍ – DOPORUČENÁ PRODUKČNÍ VARIANTA)

### 1️⃣ Přihlášení do Webnode

- Přihlaste se do administrace Webnode.
- Otevřete projekt **toozservis.cz**.

### 2️⃣ Vytvoření / otevření stránky „TooZ Hub aplikace"

- V horním menu klikněte na **Stránky**.
- Přidejte novou stránku nebo upravte existující:
  - Název: `TooZ Hub aplikace` (doporučeno)
  - URL / adresa: `/toozhub-aplikace/`.

### 3️⃣ Nastavení přesměrování na aplikaci

- V nastavení této stránky najděte volbu:
  - **„Přesměrovat na jinou webovou stránku"**  
    (nebo podobný text podle UI Webnode).
- Do pole „URL adresa" vložte:

  `https://hub.toozservis.cz/web/index.html`

- Uložte změny.

### 4️⃣ Publikace

- Uložte změny v editoru Webnode.
- Klikněte na **Publikovat**.

---

## ✅ Ověření funkčnosti

1. Otevřete v prohlížeči:
   - `https://www.toozservis.cz/toozhub-aplikace/`

2. Stránka se musí automaticky přesměrovat na:
   - `https://hub.toozservis.cz/web/index.html`

3. Aplikace TooZ Hub 2 se načte přes celou stránku.

---

## 🔧 Kontrola backendu

Pokud se aplikace nenačte:

1. Zkontrolujte, zda backend běží:
   - `https://hub.toozservis.cz/health`
   - očekává se odpověď: `{"status": "online"}` (nebo ekvivalent).

2. Zkontrolujte **Cloudflare tunnel / DNS**:
   - CNAME záznam pro subdoménu `hub`
   - tunel namířený na lokální backend (např. `localhost:8000`).

3. Zkuste otevřít frontend přímo:
   - `https://hub.toozservis.cz/web/index.html`

---

## ℹ️ Poznámka k iframe variantě

Varianta s vložením aplikace přes `<iframe>` do HTML bloku na Webnode **se aktuálně v produkci nepoužívá**  

(ponechat je ji možné jen jako alternativní / vývojářskou možnost v samostatném dokumentu, ale ne jako hlavní doporučené řešení).

---

## 📋 Podrobnější postup

Pro podrobnější návod včetně řešení problémů viz:
- `POSTUP_VLOZENI_DO_WEBNODE.md`

Pro alternativní iframe variantu (experimentální):
- `WEBNODE_IFRAME_VARIANTA_DEV.md`

---

**Jednoduché a rychlé!** ⚡



## 🎯 Cíl

Zajistit, aby stránka na Webnode:

**https://www.toozservis.cz/toozhub-aplikace/**

automaticky přesměrovala uživatele do aplikace TooZ Hub 2 běžící na:

**https://hub.toozservis.cz/web/index.html**

---

## ✅ Předpoklady

- Backend TooZ Hub 2 běží na:
  - `https://hub.toozservis.cz`
  - frontend aplikace: `https://hub.toozservis.cz/web/index.html`
- Stránka `toozhub-aplikace` je vytvořená v Webnode (nebo ji vytvoříte).

---

## 🚀 Postup ve Webnode (PŘESMĚROVÁNÍ – DOPORUČENÁ PRODUKČNÍ VARIANTA)

### 1️⃣ Přihlášení do Webnode

- Přihlaste se do administrace Webnode.
- Otevřete projekt **toozservis.cz**.

### 2️⃣ Vytvoření / otevření stránky „TooZ Hub aplikace"

- V horním menu klikněte na **Stránky**.
- Přidejte novou stránku nebo upravte existující:
  - Název: `TooZ Hub aplikace` (doporučeno)
  - URL / adresa: `/toozhub-aplikace/`.

### 3️⃣ Nastavení přesměrování na aplikaci

- V nastavení této stránky najděte volbu:
  - **„Přesměrovat na jinou webovou stránku"**  
    (nebo podobný text podle UI Webnode).
- Do pole „URL adresa" vložte:

  `https://hub.toozservis.cz/web/index.html`

- Uložte změny.

### 4️⃣ Publikace

- Uložte změny v editoru Webnode.
- Klikněte na **Publikovat**.

---

## ✅ Ověření funkčnosti

1. Otevřete v prohlížeči:
   - `https://www.toozservis.cz/toozhub-aplikace/`

2. Stránka se musí automaticky přesměrovat na:
   - `https://hub.toozservis.cz/web/index.html`

3. Aplikace TooZ Hub 2 se načte přes celou stránku.

---

## 🔧 Kontrola backendu

Pokud se aplikace nenačte:

1. Zkontrolujte, zda backend běží:
   - `https://hub.toozservis.cz/health`
   - očekává se odpověď: `{"status": "online"}` (nebo ekvivalent).

2. Zkontrolujte **Cloudflare tunnel / DNS**:
   - CNAME záznam pro subdoménu `hub`
   - tunel namířený na lokální backend (např. `localhost:8000`).

3. Zkuste otevřít frontend přímo:
   - `https://hub.toozservis.cz/web/index.html`

---

## ℹ️ Poznámka k iframe variantě

Varianta s vložením aplikace přes `<iframe>` do HTML bloku na Webnode **se aktuálně v produkci nepoužívá**  

(ponechat je ji možné jen jako alternativní / vývojářskou možnost v samostatném dokumentu, ale ne jako hlavní doporučené řešení).

---

## 📋 Podrobnější postup

Pro podrobnější návod včetně řešení problémů viz:
- `POSTUP_VLOZENI_DO_WEBNODE.md`

Pro alternativní iframe variantu (experimentální):
- `WEBNODE_IFRAME_VARIANTA_DEV.md`

---

**Jednoduché a rychlé!** ⚡
