# 🌐 DNS Kontrola pro hub.toozservis.cz

## ✅ Potřebný DNS záznam

V Cloudflare Dashboard pro doménu `toozservis.cz` musí existovat CNAME záznam:

```
Type: CNAME
Name: hub
Target: a8451dbb-2ca2-4006-862b-09959b274eb4.cfargotunnel.com
Proxy status: Proxied (oranžový mrak) ✅
TTL: Auto
```

## 🔍 Jak zkontrolovat DNS záznam

1. Přihlaste se do Cloudflare Dashboard: https://dash.cloudflare.com
2. Vyberte doménu `toozservis.cz`
3. Přejděte na **DNS** → **Records**
4. Hledejte záznam s **Name: hub**

### Pokud záznam existuje:
- Ověřte, že **Target** je: `a8451dbb-2ca2-4006-862b-09959b274eb4.cfargotunnel.com`
- Ověřte, že **Proxy status** je **Proxied** (oranžový mrak)
- Pokud není Proxied → klikněte na oranžový mrak pro aktivaci

### Pokud záznam neexistuje:
1. Klikněte na **Add record**
2. Vyplňte:
   - **Type**: CNAME
   - **Name**: hub
   - **Target**: `a8451dbb-2ca2-4006-862b-09959b274eb4.cfargotunnel.com`
   - **Proxy status**: ✅ **Proxied** (klikněte na šedý mrak, aby se změnil na oranžový)
   - **TTL**: Auto
3. Klikněte na **Save**

## ⚠️ Důležité

- **Proxy status MUSÍ být Proxied** (oranžový mrak)
- Pokud je "DNS only" (šedý mrak), tunnel nebude fungovat!
- Po vytvoření/změně záznamu počkejte 5-10 minut na propagaci DNS

## ✅ Ověření

Po nastavení DNS můžete ověřit:

```bash
# Zkontrolovat DNS rozlišení
nslookup hub.toozservis.cz

# Test HTTP
curl https://hub.toozservis.cz/health
```

---

**Tunnel UUID:** a8451dbb-2ca2-4006-862b-09959b274eb4  
**Doména:** hub.toozservis.cz

