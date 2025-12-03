# 📝 Instrukce - Úprava DNS záznamu v Cloudflare

## 🎯 Cíl

Upravit DNS záznam `hub.toozservis.cz`, aby ukazoval na nový tunel `tooz-hub2`.

---

## 📋 Krok za krokem

### Krok 1: Otevřít Cloudflare Dashboard
1. Otevřít prohlížeč
2. Přejít na: **https://dash.cloudflare.com**
3. Přihlásit se

### Krok 2: Vybrat doménu
1. V seznamu domén najít a kliknout na: **toozservis.cz**

### Krok 3: Otevřít DNS nastavení
1. V levém menu kliknout na: **DNS**
2. Otevře se sekce **Records** (DNS záznamy)

### Krok 4: Najít záznam `hub`
1. V seznamu DNS záznamů najít záznam s **Name:** `hub`
2. Měl by mít **Type:** `CNAME`
3. Kliknout na ikonu **Edit** (tužka) vedle záznamu

### Krok 5: Upravit Target
1. V poli **Target** smazat starou hodnotu
2. Vložit novou hodnotu: `a8451dbb-2ca2-4006-862b-09959b274eb4.cfargotunnel.com`
3. Zkontrolovat, že **Proxy status** je nastaven na **🟡 Proxied** (oranžový mrak)
   - Pokud je **DNS only** (šedý mrak), kliknout na něj a změnit na **Proxied**
4. Kliknout na tlačítko **Save**

---

## ✅ Kontrola

Po uložení by měl záznam vypadat takto:

```
Type:     CNAME
Name:     hub
Target:   a8451dbb-2ca2-4006-862b-09959b274eb4.cfargotunnel.com
Proxy:    🟡 Proxied (oranžový mrak)
TTL:      Auto
```

---

## ⏱️ Propagace DNS

Po úpravě DNS záznamu:
- **Počkejte 5-10 minut** na propagaci DNS změn
- Během této doby se změny rozšíří na DNS servery po celém světě

---

## 🧪 Test po propagaci

Po 5-10 minutách zkuste otestovat:

### Test 1: Health check
```powershell
"Invoke-WebRequest -Uri "https://hub.toozservis.cz/health
```

**Očekávaný výstup:**
```
Status Code: 200
Response: {"status":"online","service":"TooZ Hub 2 API","version":"2.0.0"}
```

### Test 2: Otevřít v prohlížeči
- Otevřít: **https://hub.toozservis.cz/docs**
- Měla by se otevřít FastAPI dokumentace

### Test 3: Web interface
- Otevřít: **https://hub.toozservis.cz/web/index.html**
- Mělo by se otevřít webové rozhraní TooZ Hub 2

---

## ❌ Řešení problémů

### Pokud stále dostáváte chybu 530

1. **Zkontrolovat, že tunel běží:**
   ```powershell
   Get-Process cloudflared
   ```
   - Měl by běžet proces s `tooz-hub2`

2. **Zkontrolovat, že server běží:**
   ```powershell
   Invoke-WebRequest -Uri "http://127.0.0.1:8000/health"
   ```
   - Mělo by vrátit Status 200

3. **Zkontrolovat config soubor:**
   - Cesta: `C:\Users\djtoo\.cloudflared\config-hub.yml`
   - Měl obsahovat:
     ```yaml
     ingress:
       - hostname: hub.toozservis.cz
         service: http://127.0.0.1:8000
     ```

4. **Zkontrolovat DNS záznam znovu:**
   - Ujistit se, že Target je správně nastavený
   - Ujistit se, že Proxy je zapnutý (oranžový mrak)

---

## 📋 Kontrolní seznam

- [ ] Otevřít Cloudflare Dashboard
- [ ] Vybrat doménu `toozservis.cz`
- [ ] Otevřít DNS → Records
- [ ] Najít záznam `hub` (CNAME)
- [ ] Kliknout na Edit
- [ ] Změnit Target na: `a8451dbb-2ca2-4006-862b-09959b274eb4.cfargotunnel.com`
- [ ] Zapnout Proxy (oranžový mrak)
- [ ] Uložit změny
- [ ] Počkat 5-10 minut
- [ ] Otestovat připojení

---

**Po úpravě DNS záznamu bude `hub.toozservis.cz` fungovat!** ✅


