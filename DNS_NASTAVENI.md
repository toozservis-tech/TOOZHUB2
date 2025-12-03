# 🌐 DNS Nastavení pro Cloudflare Tunnel

## 📋 Postup nastavení DNS záznamu

### Krok 1: Získat UUID tunelu

Před nastavením DNS potřebujete UUID vašeho tunelu. Získáte ho jedním z těchto způsobů:

#### Metoda A: Z credentials souboru
```powershell
# Otevřete soubor
notepad C:\Users\djtoo\.cloudflared\tooz-hub2.json

# Najděte řádek s "AccountTag" nebo "TunnelID"
# UUID je dlouhý řetězec (např. a1b2c3d4-e5f6-7890-abcd-ef1234567890)
```

#### Metoda B: Z výstupu příkazu
```bash
cloudflared tunnel create tooz-hub2
```

Výstup bude obsahovat UUID tunelu.

#### Metoda C: Z listu tunelů
```bash
cloudflared tunnel list
```

### Krok 2: Nastavit DNS záznam v Cloudflare

1. **Přihlaste se do Cloudflare Dashboard**
   - Otevřete: https://dash.cloudflare.com
   - Přihlaste se do svého účtu

2. **Vyberte doménu**
   - Klikněte na doménu `toozservis.cz`

3. **Přejděte na DNS**
   - V levém menu klikněte na **DNS** → **Records**

4. **Vytvořte nový CNAME záznam**
   - Klikněte na tlačítko **Add record**
   - Vyplňte:
     - **Type**: `CNAME`
     - **Name**: `hub`
     - **Target**: `<UUID>.cfargotunnel.com`
       - Nahraďte `<UUID>` skutečným UUID z Kroku 1
       - Příklad: `a1b2c3d4-e5f6-7890-abcd-ef1234567890.cfargotunnel.com`
     - **Proxy status**: ✅ **Proxied** (oranžový mrak) - **DŮLEŽITÉ!**
     - **TTL**: `Auto`

5. **Uložte záznam**
   - Klikněte na **Save**

### Krok 3: Ověřit DNS záznam

Po vytvoření záznamu byste měli vidět:

```
Type    Name    Content                                    Proxy
CNAME   hub     a1b2c3d4-...cfargotunnel.com              Proxied
```

**Důležité:**
- ✅ **Proxy status musí být "Proxied"** (oranžový mrak)
- ✅ Pokud je "DNS only" (šedý mrak), tunnel nebude fungovat!

### Krok 4: Počkat na propagaci DNS

- DNS změny se obvykle propagují během **5-10 minut**
- V některých případech to může trvat až 30 minut

### Krok 5: Otestovat

Po propagaci DNS otestujte:

```bash
# V PowerShell
curl https://hub.toozservis.cz/health

# Nebo otevřete v prohlížeči
https://hub.toozservis.cz/health
```

Měli byste vidět JSON odpověď:
```json
{
  "status": "online",
  "service": "TooZ Hub 2 API",
  "version": "2.0.0"
}
```

## 🔍 Řešení problémů

### Problém: DNS záznam nefunguje

**Kontrola:**
1. Ověřte, že záznam má **Proxied** status (oranžový mrak)
2. Zkontrolujte, zda UUID v Target je správný
3. Počkejte na propagaci DNS (5-30 minut)

### Problém: "502 Bad Gateway"

**Možné příčiny:**
1. Tunnel neběží - spusťte `start_cloudflare_tunnel.bat`
2. Server neběží na portu 8000 - spusťte `start_server_production.bat`
3. Špatný UUID v DNS záznamu

### Problém: "DNS resolution failed"

**Řešení:**
- Zkontrolujte, zda DNS záznam existuje v Cloudflare
- Ověřte, že doména `toozservis.cz` je správně nakonfigurována v Cloudflare
- Počkejte na propagaci DNS

## 📝 Příklad DNS záznamu

```
┌─────────────────────────────────────────────────────────┐
│ Type: CNAME                                             │
│ Name: hub                                               │
│ Target: a1b2c3d4-e5f6-7890-abcd-ef1234567890.cfargotunnel.com │
│ Proxy: ✅ Proxied (oranžový mrak)                      │
│ TTL: Auto                                               │
└─────────────────────────────────────────────────────────┘
```

## ✅ Checklist

- [ ] UUID tunelu získán
- [ ] DNS CNAME záznam vytvořen v Cloudflare
- [ ] Target obsahuje správný UUID
- [ ] Proxy status je **Proxied** (oranžový mrak)
- [ ] Počkali jste na propagaci DNS (5-30 minut)
- [ ] `https://hub.toozservis.cz/health` vrací 200 OK

---

**Vytvořeno:** 2025-01-27  
**Doména:** hub.toozservis.cz  
**Tunnel:** tooz-hub2

