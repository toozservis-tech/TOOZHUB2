#!/usr/bin/env python3
"""
TooZ Hub 2 - Webnode Learning Script
Tento skript se přihlásí do Webnode, otevře projekt a pak čeká,
až uživatel provede kroky. Všechny akce se zaznamenají do logu.
"""

import json
import time
import sys
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# Konfigurace - stejná cesta jako hlavní skript
CONFIG_FILE = Path.home() / ".toozhub_webnode_config.json"

def load_config():
    """Načte konfiguraci z JSON souboru"""
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
        return config
    except Exception as e:
        print(f"❌ Chyba při načítání konfigurace: {e}")
        sys.exit(1)

def setup_driver():
    """Nastaví Chrome driver"""
    chrome_options = Options()
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    driver = webdriver.Chrome(options=chrome_options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver

def login_to_webnode(driver, config):
    """Přihlásí se do Webnode"""
    print("🔐 Přihlašuji se do Webnode...")
    
    try:
        driver.get("https://www.webnode.com/cs/login/")
        time.sleep(2)
        
        # Zpracovat cookies
        try:
            cookie_button = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button#onetrust-accept-btn-handler, button[id*='accept'], .cookie-accept"))
            )
            cookie_button.click()
            print("✓ Cookies přijaty")
            time.sleep(1)
        except:
            pass
        
        # Vyplnit email
        email_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='email'], input[name='email'], input[id*='email']"))
        )
        email_input.clear()
        email_input.send_keys(config['email'])
        print(f"✓ Email vyplněn: {config['email']}")
        
        # Vyplnit heslo
        password_input = driver.find_element(By.CSS_SELECTOR, "input[type='password'], input[name='password'], input[id*='password']")
        password_input.clear()
        password_input.send_keys(config['password'])
        print("✓ Heslo vyplněno")
        
        # Kliknout na přihlášení
        login_button = driver.find_element(By.CSS_SELECTOR, "button[type='submit'], button.btn-primary, .btn-login")
        driver.execute_script("arguments[0].click();", login_button)
        print("✓ Kliknuto na přihlášení")
        
        # Počkat na přihlášení
        time.sleep(5)
        
        current_url = driver.current_url
        if "login" not in current_url.lower():
            print("✓ Přihlášení úspěšné!")
            print(f"📄 Aktuální URL: {current_url}")
            return True
        else:
            print("❌ Přihlášení selhalo")
            return False
            
    except Exception as e:
        print(f"❌ Chyba při přihlašování: {e}")
        import traceback
        traceback.print_exc()
        return False

def open_project(driver, page_url):
    """Otevře projekt v editoru"""
    print(f"📄 Otevírám projekt: {page_url}")
    
    try:
        # Odstranit koncové lomítko
        page_url = page_url.rstrip('/')
        
        # Otevřít stránku v editoru
        if not page_url.startswith("http"):
            page_url = "https://" + page_url
        
        driver.get(page_url)
        time.sleep(5)
        
        current_url = driver.current_url
        print(f"✓ Stránka načtena: {current_url}")
        
        if "login" in current_url.lower():
            print("⚠️  Je potřeba se přihlásit")
            return False
        
        return True
    except Exception as e:
        print(f"❌ Chyba při otevírání projektu: {e}")
        return False

def log_action(action_type, description, element_info=None, screenshot_path=None):
    """Zapíše akci do logu"""
    log_entry = {
        "timestamp": time.time(),
        "type": action_type,
        "description": description,
        "element": element_info,
        "screenshot": screenshot_path
    }
    
    log_file = Path(__file__).parent / "webnode_learned_steps.json"
    
    # Načíst existující log nebo vytvořit nový
    if log_file.exists():
        with open(log_file, 'r', encoding='utf-8') as f:
            logs = json.load(f)
    else:
        logs = []
    
    logs.append(log_entry)
    
    # Uložit log
    with open(log_file, 'w', encoding='utf-8') as f:
        json.dump(logs, f, indent=2, ensure_ascii=False)
    
    print(f"📝 Zaznamenáno: {action_type} - {description}")

def monitor_user_actions(driver):
    """Sleduje uživatelovy akce"""
    print("\n" + "="*60)
    print("🎓 REŽIM UČENÍ - Sleduji vaše akce...")
    print("="*60)
    print("\n📋 Postup:")
    print("1. Klikněte na HTML blok")
    print("2. Klikněte na 'Upravit'")
    print("3. Označte všechen text v textarea (Ctrl+A)")
    print("4. Já vložím HTML kód")
    print("5. Klikněte na 'OK'")
    print("6. Klikněte na 'Publikovat'")
    print("\n⏳ Čekám na vaše akce...")
    print("💡 Pro ukončení stiskněte Ctrl+C\n")
    
    previous_url = driver.current_url
    previous_title = driver.title
    
    try:
        while True:
            time.sleep(0.5)  # Kontrola každých 0.5 sekundy
            
            # Zkontrolovat změnu URL
            current_url = driver.current_url
            if current_url != previous_url:
                log_action("url_change", f"URL změněna na: {current_url}", {"url": current_url})
                previous_url = current_url
                print(f"🔍 URL změněna: {current_url}")
            
            # Zkontrolovat změnu titulku
            current_title = driver.title
            if current_title != previous_title:
                log_action("title_change", f"Titulek změněn na: {current_title}", {"title": current_title})
                previous_title = current_title
                print(f"🔍 Titulek změněn: {current_title}")
            
            # Zkontrolovat, zda se otevřel dialog/modal
            try:
                modals = driver.find_elements(By.CSS_SELECTOR, "[class*='modal'], [class*='dialog'], [role='dialog']")
                visible_modals = [m for m in modals if m.is_displayed()]
                if visible_modals:
                    for modal in visible_modals:
                        modal_text = modal.text[:100] if modal.text else ""
                        modal_class = modal.get_attribute('class') or ""
                        log_action("modal_opened", f"Dialog otevřen: {modal_text[:50]}", {
                            "class": modal_class,
                            "text": modal_text
                        })
                        print(f"🔍 Dialog otevřen: {modal_text[:50]}")
            except:
                pass
            
            # Zkontrolovat, zda se změnil obsah textarea
            try:
                textareas = driver.find_elements(By.TAG_NAME, "textarea")
                for textarea in textareas:
                    if textarea.is_displayed():
                        current_value = textarea.get_attribute('value') or ""
                        # Pokud textarea obsahuje náš HTML (více než 1000 znaků), znamená to, že jsme vložili kód
                        if len(current_value) > 1000:
                            log_action("textarea_content", "HTML kód vložen do textarea", {
                                "length": len(current_value),
                                "preview": current_value[:100]
                            })
                            print(f"✓ HTML kód vložen do textarea ({len(current_value)} znaků)")
            except:
                pass
                
    except KeyboardInterrupt:
        print("\n\n⏹️  Ukončuji sledování...")
        log_action("monitoring_stopped", "Sledování ukončeno uživatelem")

def insert_html_when_ready(driver, html_content):
    """Vloží HTML kód, když uživatel označí text v textarea"""
    print("\n⏳ Čekám, až označíte text v textarea (Ctrl+A)...")
    print("💡 Po označení textu automaticky vložím HTML kód\n")
    
    # Nastavit event listenery pro detekci označení textu
    driver.execute_script("""
        window.htmlInserted = false;
        window.selectionDetected = false;
        
        // Funkce pro detekci označení textu
        function checkSelection() {
            var textareas = document.querySelectorAll('textarea');
            for (var i = 0; i < textareas.length; i++) {
                var textarea = textareas[i];
                if (textarea.offsetParent !== null) { // Je viditelný
                    var start = textarea.selectionStart;
                    var end = textarea.selectionEnd;
                    var valueLength = textarea.value.length;
                    
                    // Pokud je označen celý text (nebo většina)
                    if (start !== end && (end - start) >= valueLength * 0.9) {
                        window.selectionDetected = true;
                        return true;
                    }
                }
            }
            return false;
        }
        
        // Přidat event listenery na všechny textarea
        document.addEventListener('mouseup', function() {
            setTimeout(checkSelection, 100);
        });
        
        document.addEventListener('keyup', function(e) {
            if (e.ctrlKey && e.key === 'a') {
                setTimeout(checkSelection, 100);
            }
        });
    """)
    
    previous_selection = False
    
    while True:
        try:
            # Zkontrolovat, zda JavaScript detekoval označení
            selection_detected = driver.execute_script("return window.selectionDetected;")
            
            if selection_detected and not previous_selection:
                # Text je označen, najít textarea a vložit HTML
                print("✓ Text označen, vkládám HTML kód...")
                
                textareas = driver.find_elements(By.TAG_NAME, "textarea")
                for textarea in textareas:
                    if textarea.is_displayed():
                        # Vložit HTML
                        driver.execute_script("""
                            var textarea = arguments[0];
                            var content = arguments[1];
                            textarea.value = content;
                            textarea.dispatchEvent(new Event('input', { bubbles: true }));
                            textarea.dispatchEvent(new Event('change', { bubbles: true }));
                        """, textarea, html_content)
                        
                        log_action("html_inserted", "HTML kód vložen do textarea", {
                            "length": len(html_content),
                            "textarea_id": textarea.get_attribute('id'),
                            "textarea_class": textarea.get_attribute('class')
                        })
                        
                        print(f"✓ HTML kód vložen ({len(html_content)} znaků)")
                        print("💡 Nyní klikněte na 'OK' a poté na 'Publikovat'")
                        
                        # Resetovat flag
                        driver.execute_script("window.selectionDetected = false; window.htmlInserted = true;")
                        previous_selection = True
                        return True
            
            # Alternativně zkontrolovat přímo
            textareas = driver.find_elements(By.TAG_NAME, "textarea")
            for textarea in textareas:
                if textarea.is_displayed():
                    try:
                        selection_info = driver.execute_script("""
                            var textarea = arguments[0];
                            var start = textarea.selectionStart || 0;
                            var end = textarea.selectionEnd || 0;
                            var valueLength = textarea.value.length;
                            return {
                                start: start,
                                end: end,
                                length: valueLength,
                                selected: (end - start) >= valueLength * 0.9
                            };
                        """, textarea)
                        
                        if selection_info['selected'] and not previous_selection:
                            print("✓ Text označen (přímá kontrola), vkládám HTML kód...")
                            
                            driver.execute_script("""
                                var textarea = arguments[0];
                                var content = arguments[1];
                                textarea.value = content;
                                textarea.dispatchEvent(new Event('input', { bubbles: true }));
                                textarea.dispatchEvent(new Event('change', { bubbles: true }));
                            """, textarea, html_content)
                            
                            log_action("html_inserted", "HTML kód vložen do textarea (přímá kontrola)", {
                                "length": len(html_content)
                            })
                            
                            print(f"✓ HTML kód vložen ({len(html_content)} znaků)")
                            print("💡 Nyní klikněte na 'OK' a poté na 'Publikovat'")
                            previous_selection = True
                            return True
                    except:
                        pass
        except:
            pass
        
        time.sleep(0.2)

def main():
    """Hlavní funkce"""
    print("🎓 TooZ Hub 2 - Webnode Learning Script")
    print("="*60)
    
    # Načíst konfiguraci
    config = load_config()
    
    # Načíst HTML
    project_root = Path(__file__).parent.parent
    html_file = project_root / "web" / "index.html"
    if not html_file.exists():
        print(f"❌ HTML soubor neexistuje: {html_file}")
        sys.exit(1)
    
    with open(html_file, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    print(f"✓ HTML načteno ({len(html_content)} znaků)\n")
    
    # Nastavit driver
    driver = setup_driver()
    
    try:
        # Přihlásit se
        if not login_to_webnode(driver, config):
            print("❌ Přihlášení selhalo")
            return
        
        # Otevřít projekt
        page_url = config.get('page_url', 'https://finalni-verze.cms.webnode.cz/toozhub-aplikace/')
        if not open_project(driver, page_url):
            print("❌ Otevření projektu selhalo")
            return
        
        print("\n✅ Přihlášení a otevření projektu dokončeno!")
        print("⏳ Nyní čekám na vaše akce...\n")
        
        # Spustit sledování v samostatném vlákně
        import threading
        monitor_thread = threading.Thread(target=monitor_user_actions, args=(driver,), daemon=True)
        monitor_thread.start()
        
        # Čekat, až uživatel označí text a vložit HTML
        insert_html_when_ready(driver, html_content)
        
        # Pokračovat ve sledování
        print("\n⏳ Pokračuji ve sledování... (stiskněte Ctrl+C pro ukončení)")
        monitor_thread.join()
        
    except KeyboardInterrupt:
        print("\n\n⏹️  Ukončuji...")
    except Exception as e:
        print(f"\n❌ Chyba: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\n💡 Prohlížeč zůstane otevřený pro kontrolu.")
        print("💡 Všechny zaznamenané kroky jsou v: scripts/webnode_learned_steps.json")
        print("\n⏳ Prohlížeč se zavře za 60 sekund...")
        time.sleep(60)
        driver.quit()

if __name__ == "__main__":
    main()

