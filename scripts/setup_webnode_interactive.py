#!/usr/bin/env python3
"""
Interaktivní Python skript pro nastavení Webnode přihlašovacích údajů
Lepší než bash skript, protože funguje i v různých terminálech
"""

import json
import getpass
from pathlib import Path

CONFIG_FILE = Path.home() / ".toozhub_webnode_config.json"

def main():
    print("🔐 Nastavení Webnode přihlašovacích údajů")
    print("=" * 50)
    print()
    print("Tyto údaje budou uloženy lokálně a použity pro automatické aktualizace.")
    print()
    
    # Zkontrolovat, zda soubor už existuje
    if CONFIG_FILE.exists():
        print(f"⚠️  Konfigurační soubor už existuje: {CONFIG_FILE}")
        response = input("Chcete ho přepsat? (y/n): ").strip().lower()
        if response != 'y':
            print("Zrušeno.")
            return
        print()
    
    # Načíst údaje
    print("Zadejte přihlašovací údaje pro Webnode:")
    print()
    
    email = input("📧 Email: ").strip()
    if not email:
        print("❌ Email je povinný!")
        return
    
    password = getpass.getpass("🔑 Heslo: ")
    if not password:
        print("❌ Heslo je povinné!")
        return
    
    print()
    page_url = input("🌐 URL stránky (např. https://www.toozservis.cz/toozhub-aplikace/): ").strip()
    if not page_url:
        print("❌ URL stránky je povinná!")
        return
    
    print()
    api_key = input("🔑 API klíč (pokud máte, jinak nechte prázdné): ").strip()
    
    # Vytvořit konfiguraci
    config = {
        "email": email,
        "password": password,
        "page_url": page_url,
        "api_key": api_key if api_key else None
    }
    
    # Uložit
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        
        # Nastavit oprávnění (pouze pro vlastníka)
        import os
        os.chmod(CONFIG_FILE, 0o600)
        
        print()
        print("✅ Konfigurace uložena do:", CONFIG_FILE)
        print("🔒 Soubor má oprávnění pouze pro vás (600)")
        print()
        print("📝 Co dál:")
        print("1. Spusťte: python3 scripts/webnode_auto_upload.py")
        print("2. Nebo použijte API endpoint: curl -X POST http://localhost:8000/webnode/update")
        print()
        print("⚠️  DŮLEŽITÉ: Tento soubor obsahuje citlivé údaje a NENÍ v Gitu!")
        
    except (IOError, OSError, ValueError) as e:
        print(f"❌ Chyba při ukládání konfigurace: {e}")

if __name__ == "__main__":
    main()

