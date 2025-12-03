#!/usr/bin/env python3
"""
Automatické vložení HTML do Webnode editoru pomocí Selenium
Používá lokální konfigurační soubor pro přihlašovací údaje
"""

import sys
import json
import time
import os
import fcntl
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# Zkusit načíst webdriver-manager
try:
    from webdriver_manager.chrome import ChromeDriverManager
    USE_WEBDRIVER_MANAGER = True
except ImportError:
    USE_WEBDRIVER_MANAGER = False
    ChromeDriverManager = None

# Cesta k konfiguračnímu souboru (NENÍ v Gitu!)
CONFIG_FILE = Path.home() / ".toozhub_webnode_config.json"

# Lock file pro zajištění, že běží jen jedna instance
LOCK_FILE = Path("/tmp/toozhub_webnode_upload.lock")

def load_config():
    """Načte konfiguraci z lokálního souboru"""
    if not CONFIG_FILE.exists():
        print("❌ Konfigurační soubor neexistuje!")
        print(f"\nVytvořte soubor: {CONFIG_FILE}")
        print("\nObsah souboru:")
        print("""
{
    "email": "vas@email.cz",
    "password": "vase-heslo",
    "page_url": "https://finalni-verze.cms.webnode.cz/toozhub-aplikace"
}
        """)
        sys.exit(1)
    
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
        return config
    except Exception as e:
        print(f"❌ Chyba při načítání konfigurace: {e}")
        sys.exit(1)

def read_html():
    """Načte HTML z projektu - celý obsah souboru"""
    project_root = Path(__file__).parent.parent
    # Použít iframe verzi pro Webnode (nejmenší - jen 1KB!)
    # Tato verze načte aplikaci z API serveru přes iframe
    html_file = project_root / "web" / "index_iframe.html"
    # Pokud iframe verze neexistuje, použít minimální verzi
    if not html_file.exists():
        html_file = project_root / "web" / "index_minimal.html"
    # Pokud ani minimální neexistuje, použít původní
    if not html_file.exists():
        html_file = project_root / "web" / "index.html"
    
    if not html_file.exists():
        print(f"❌ HTML soubor neexistuje: {html_file}")
        sys.exit(1)
    
    print(f"📄 Načítám HTML z: {html_file}")
    with open(html_file, 'r', encoding='utf-8') as f:
        content = f.read()
    print(f"✓ HTML načteno ({len(content)} znaků)")
    return content

def acquire_lock():
    """Získá lock pro zajištění, že běží jen jedna instance"""
    try:
        lock_fd = os.open(LOCK_FILE, os.O_CREAT | os.O_WRONLY | os.O_TRUNC)
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Zapsat PID do lock file
        os.write(lock_fd, str(os.getpid()).encode())
        os.fsync(lock_fd)
        return lock_fd
    except (IOError, OSError):
        print("⚠️  Jiná instance skriptu už běží. Čekám na dokončení...")
        return None

def release_lock(lock_fd):
    """Uvolní lock"""
    if lock_fd:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
            if LOCK_FILE.exists():
                LOCK_FILE.unlink()
        except:
            pass

def setup_driver():
    """Nastaví Selenium WebDriver"""
    chrome_options = Options()
    
    # Zkontrolovat, zda máme DISPLAY (pokud ne, použít headless)
    if not os.getenv('DISPLAY'):
        chrome_options.add_argument('--headless=new')
        print("💡 Spouštím v headless režimu (žádný display)")
    
    # Zajistit, aby se otevřelo jen jedno okno
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    # Zajistit, aby se nespouštěly další instance Chrome
    chrome_options.add_argument('--disable-extensions')
    chrome_options.add_argument('--disable-plugins')
    
    try:
        if USE_WEBDRIVER_MANAGER:
            from selenium.webdriver.chrome.service import Service
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
        else:
            driver = webdriver.Chrome(options=chrome_options)
        return driver
    except Exception as e:
        print(f"❌ Chyba při spuštění Chrome: {e}")
        print("\nZkuste nainstalovat webdriver-manager:")
        print("  pip install webdriver-manager")
        print("\nNebo nainstalujte ChromeDriver ručně:")
        print("  sudo apt-get install chromium-chromedriver")
        print("  nebo stáhněte z: https://chromedriver.chromium.org/")
        sys.exit(1)

def login_to_webnode(driver, email, password):
    """Přihlásí se do Webnode"""
    print("🔐 Přihlašuji se do Webnode...")
    
    driver.get("https://www.webnode.com/login/")
    time.sleep(3)
    
    # Nejdřív přijmout/odškrtnout cookies
    print("🍪 Zpracovávám cookies...")
    try:
        # Zkusit najít a odškrtnout/akceptovat cookies
        cookie_selectors = [
            (By.CSS_SELECTOR, ".w-cookie-modal-accept-cookies"),
            (By.CSS_SELECTOR, ".cookie-accept, .accept-cookies, button[data-cookie='accept']"),
            (By.XPATH, "//button[contains(text(), 'Přijmout') or contains(text(), 'Accept') or contains(text(), 'Souhlasím')]"),
            (By.XPATH, "//span[contains(@class, 'cookie') and (contains(text(), 'Přijmout') or contains(text(), 'Accept'))]"),
            (By.CSS_SELECTOR, "[data-cookie-accept], [id*='cookie-accept']")
        ]
        for by, value in cookie_selectors:
            try:
                cookie_button = driver.find_element(by, value)
                if cookie_button and cookie_button.is_displayed():
                    cookie_button.click()
                    print("✓ Cookies přijaty/odškrtnuty")
                    time.sleep(1)
                    break
            except:
                continue
    except Exception as e:
        print(f"⚠️  Cookies: {e}")
        pass
    
    try:
        # Zkusit různé selektory pro email
        email_input = None
        selectors = [
            (By.NAME, "email"),
            (By.ID, "email"),
            (By.CSS_SELECTOR, "input[type='email']"),
            (By.XPATH, "//input[@type='email']"),
            (By.XPATH, "//input[contains(@placeholder, 'email') or contains(@placeholder, 'Email')]")
        ]
        
        for by, value in selectors:
            try:
                email_input = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((by, value))
                )
                if email_input and email_input.is_displayed():
                    break
            except:
                continue
        
        if not email_input:
            print("❌ Nepodařilo se najít pole pro email")
            print(f"📄 Aktuální URL: {driver.current_url}")
            print(f"📄 Titulek stránky: {driver.title}")
            # Uložit screenshot pro debug
            try:
                driver.save_screenshot("/tmp/webnode_login_debug.png")
                print("📸 Screenshot uložen do: /tmp/webnode_login_debug.png")
            except:
                pass
            return False
        
        email_input.clear()
        email_input.send_keys(email)
        print(f"✓ Email vyplněn: {email}")
        
        # Zkusit různé selektory pro heslo
        password_input = None
        selectors = [
            (By.NAME, "password"),
            (By.ID, "password"),
            (By.CSS_SELECTOR, "input[type='password']"),
            (By.XPATH, "//input[@type='password']")
        ]
        
        for by, value in selectors:
            try:
                password_input = driver.find_element(by, value)
                if password_input and password_input.is_displayed():
                    break
            except:
                continue
        
        if not password_input:
            print("❌ Nepodařilo se najít pole pro heslo")
            return False
        
        password_input.clear()
        password_input.send_keys(password)
        print("✓ Heslo vyplněno")
        
        # Cookies už byly zpracovány výše při načtení stránky
        
        # Najít tlačítko pro přihlášení
        login_button = None
        selectors = [
            (By.CSS_SELECTOR, "button[type='submit']"),
            (By.XPATH, "//button[contains(text(), 'Přihlásit') or contains(text(), 'Login')]"),
            (By.CSS_SELECTOR, "input[type='submit']"),
            (By.CSS_SELECTOR, "button.btn-primary"),
            (By.CSS_SELECTOR, ".btn-login")
        ]
        
        for by, value in selectors:
            try:
                login_button = driver.find_element(by, value)
                if login_button and login_button.is_displayed():
                    break
            except:
                continue
        
        if not login_button:
            print("❌ Nepodařilo se najít tlačítko pro přihlášení")
            return False
        
        # Scrollovat k tlačítku a zkusit kliknout
        try:
            driver.execute_script("arguments[0].scrollIntoView(true);", login_button)
            time.sleep(0.5)
            # Zkusit kliknout přes JavaScript, pokud normální klik nefunguje
            driver.execute_script("arguments[0].click();", login_button)
            print("✓ Kliknuto na přihlášení (přes JavaScript)")
        except:
            # Fallback na normální klik
            login_button.click()
            print("✓ Kliknuto na přihlášení")
        
        # Počkat na přihlášení (zkontrolovat změnu URL nebo přítomnost elementu)
        time.sleep(3)
        
        # Zkontrolovat, zda jsme přihlášeni
        current_url = driver.current_url
        if "login" not in current_url.lower() or "dashboard" in current_url.lower() or "admin" in current_url.lower():
            print("✓ Přihlášení úspěšné!")
            print(f"📄 Aktuální URL: {current_url}")
            return True
        else:
            # Zkontrolovat, zda není chybová zpráva
            try:
                error_elements = driver.find_elements(By.CSS_SELECTOR, ".error, .alert-danger, .message-error")
                if error_elements:
                    error_text = error_elements[0].text
                    print(f"❌ Chyba při přihlašování: {error_text}")
                else:
                    print("❌ Přihlášení selhalo - zůstali jsme na přihlašovací stránce")
            except:
                print("❌ Přihlášení selhalo")
            return False
        
    except TimeoutException as e:
        print(f"❌ Timeout při přihlašování: {e}")
        return False
    except Exception as e:
        print(f"❌ Chyba při přihlašování: {e}")
        import traceback
        traceback.print_exc()
        return False

def edit_page(driver, page_url):
    """Otevře stránku v editoru a najde HTML blok"""
    print(f"📄 Naviguji k stránce: {page_url}")
    
    try:
        # Odstranit koncové lomítko, pokud existuje
        page_url = page_url.rstrip('/')
        
        # Nejdřív jít na "Moje projekty" nebo přímo na stránku v editoru
        # Zkusit otevřít přímo URL stránky v editoru
        if "cms.webnode.cz" in page_url or "webnode.cz" in page_url:
            # Pokud je to CMS URL, použít přímo
            editor_url = page_url
        else:
            # Pokud je to publikovaná URL, převést na editor URL
            # finalni-verze.cms.webnode.cz/toozhub-aplikace -> editor URL
            editor_url = page_url.replace("www.toozservis.cz", "finalni-verze.cms.webnode.cz")
            if not editor_url.startswith("http"):
                editor_url = "https://" + editor_url
        
        print(f"📄 Otevírám stránku v editoru: {editor_url}")
        driver.get(editor_url)
        
        # Počkat na načtení stránky
        time.sleep(5)
        
        # Počkat, až se stránka načte (ne přesměrování na login)
        try:
            WebDriverWait(driver, 10).until(
                lambda d: "login" not in d.current_url.lower() and "signin" not in d.current_url.lower()
            )
        except:
            pass
        
        # Zkontrolovat, zda jsme na správné stránce
        current_url = driver.current_url
        print(f"✓ Stránka načtena: {current_url}")
        
        # Pokud jsme na přihlašovací stránce, musíme se přihlásit
        if "login" in current_url.lower() or "signin" in current_url.lower():
            print("⚠️  Je potřeba se přihlásit do Webnode")
            return False
        
        # Najít HTML blok na stránce (ten s tlačítky "Upravit", smazat atd.)
        print("🔍 Hledám HTML blok na stránce...")
        html_block = None
        
        # Zkusit různé selektory pro HTML blok (ten s textem "HTML kód" a tlačítky Upravit/Smazat)
        selectors = [
            # Hledat podle textu "HTML kód"
            (By.XPATH, "//*[contains(text(), 'HTML kód') or contains(text(), 'HTML code')]"),
            # Hledat blok, který obsahuje text o bezpečnostních důvodech
            (By.XPATH, "//*[contains(text(), 'bezpečnostních důvodů') or contains(text(), 'security reasons')]"),
            # Hledat podle třídy
            (By.CSS_SELECTOR, ".html-block, .html-content, .code-block, [class*='html'], [class*='code']"),
            (By.XPATH, "//div[contains(@class, 'html') or contains(@id, 'html')]"),
            (By.XPATH, "//div[contains(@class, 'code') or contains(@id, 'code')]"),
            # Hledat blok s tlačítky Upravit/Smazat
            (By.XPATH, "//div[.//button[contains(text(), 'Upravit')] and .//*[contains(text(), 'HTML')]]"),
        ]
        
        for by, selector in selectors:
            try:
                elements = driver.find_elements(by, selector)
                for elem in elements:
                    if elem.is_displayed():
                        # Pokud je to textový element, najít jeho rodičovský blok
                        if elem.tag_name in ['span', 'p', 'div'] and 'HTML' in (elem.text or ''):
                            # Najít rodičovský blok, který obsahuje tlačítka
                            parent = elem.find_element(By.XPATH, "./ancestor::div[.//button]")
                            if parent:
                                html_block = parent
                            else:
                                html_block = elem
                        else:
                            html_block = elem
                        print(f"✓ HTML blok nalezen pomocí selektoru: {selector}")
                        break
                if html_block:
                    break
            except:
                continue
        
        if not html_block:
            print("⚠️  HTML blok nenalezen, zkouším kliknout na první iframe nebo textarea...")
            # Fallback - zkusit najít iframe nebo textarea
            try:
                iframes = driver.find_elements(By.TAG_NAME, "iframe")
                if iframes:
                    html_block = iframes[0]
                    print("✓ Používám první iframe jako HTML blok")
            except:
                pass
        
        if html_block:
            # Scrollovat k bloku
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", html_block)
            time.sleep(1)
            
            # KROK 1: Kliknout na HTML blok (vyjede malé okénko s "Upravit" nebo "Smazat")
            print("🖱️  Klikám na HTML blok (vyjede okénko s Upravit/Smazat)...")
            
            # Zkusit několik způsobů kliknutí
            clicked = False
            for attempt in range(3):
                try:
                    if attempt == 0:
                        # Normální klik
                        html_block.click()
                        print(f"  Pokus {attempt+1}: Normální klik")
                    elif attempt == 1:
                        # Klik přes JavaScript
                        driver.execute_script("arguments[0].click();", html_block)
                        print(f"  Pokus {attempt+1}: Klik přes JavaScript")
                    else:
                        # Klik na střed bloku
                        driver.execute_script("""
                            var elem = arguments[0];
                            var rect = elem.getBoundingClientRect();
                            var x = rect.left + rect.width / 2;
                            var y = rect.top + rect.height / 2;
                            var clickEvent = new MouseEvent('click', {
                                view: window,
                                bubbles: true,
                                cancelable: true,
                                clientX: x,
                                clientY: y
                            });
                            elem.dispatchEvent(clickEvent);
                        """, html_block)
                        print(f"  Pokus {attempt+1}: Klik na střed bloku")
                    clicked = True
                    break
                except Exception as e:
                    print(f"  Pokus {attempt+1} selhal: {e}")
                    continue
            
            if not clicked:
                print("⚠️  Nepodařilo se kliknout na HTML blok")
            
            print("⏳ Čekám na zobrazení malého okénka...")
            time.sleep(5)  # Počkat déle, až se otevře malé okénko
            
            # Zkusit najít malé okénko (tooltip, popup, menu)
            print("🔍 Hledám malé okénko (tooltip/popup/menu)...")
            try:
                popup_selectors = [
                    (By.CSS_SELECTOR, "[class*='tooltip'], [class*='popup'], [class*='menu'], [class*='dropdown']"),
                    (By.XPATH, "//div[contains(@class, 'tooltip') or contains(@class, 'popup') or contains(@class, 'menu')]"),
                    (By.CSS_SELECTOR, "[role='menu'], [role='tooltip'], [role='dialog']"),
                ]
                for by, selector in popup_selectors:
                    try:
                        popups = driver.find_elements(by, selector)
                        for popup in popups:
                            if popup.is_displayed():
                                print(f"✓ Nalezeno malé okénko: {selector}")
                                # Hledat tlačítko "Upravit" v tomto okénku
                                edit_btn = popup.find_element(By.XPATH, ".//button[contains(., 'Upravit') or contains(., 'Edit')] | .//a[contains(., 'Upravit') or contains(., 'Edit')]")
                                if edit_btn and edit_btn.is_displayed():
                                    edit_button = edit_btn
                                    print("✓ Tlačítko 'Upravit' nalezeno v malém okénku!")
                                    break
                        if edit_button:
                            break
                    except:
                        continue
            except:
                pass
            
            # KROK 2: Najít tlačítko "Upravit" v malém okénku (má ikonu tužky)
            print("🔍 Hledám tlačítko 'Upravit' v malém okénku...")
            edit_button = None
            
            # Zkusit najít všechna viditelná tlačítka a zkontrolovat text/title
            try:
                # Počkat, až se malé okénko zobrazí
                WebDriverWait(driver, 5).until(
                    lambda d: len([b for b in d.find_elements(By.TAG_NAME, "button") if b.is_displayed()]) > 0
                )
                
                all_buttons = driver.find_elements(By.TAG_NAME, "button")
                print(f"🔍 Nalezeno {len(all_buttons)} tlačítek, kontroluji...")
                
                # Debug: Vypiš všechny viditelné tlačítka
                visible_buttons = [b for b in all_buttons if b.is_displayed()]
                print(f"🔍 Viditelná tlačítka ({len(visible_buttons)}):")
                for i, btn in enumerate(visible_buttons[:8]):  # Prvních 8
                    try:
                        btn_text = (btn.text or '').strip()
                        btn_title = (btn.get_attribute('title') or '').strip()
                        btn_class = (btn.get_attribute('class') or '').strip()
                        print(f"  {i+1}. Text: '{btn_text}', Title: '{btn_title}', Class: '{btn_class[:50]}'")
                    except:
                        pass
                
                for btn in all_buttons:
                    try:
                        if btn.is_displayed():
                            btn_text = (btn.text or '').strip().lower()
                            btn_title = (btn.get_attribute('title') or '').strip().lower()
                            btn_aria = (btn.get_attribute('aria-label') or '').strip().lower()
                            
                            # Zkontrolovat, zda obsahuje "upravit" nebo "edit"
                            if any(keyword in text for keyword in ['upravit', 'edit'] for text in [btn_text, btn_title, btn_aria]):
                                edit_button = btn
                                print(f"✓ Tlačítko 'Upravit' nalezeno: '{btn.text or btn.get_attribute('title') or btn.get_attribute('aria-label')}'")
                                break
                            # Zkontrolovat, zda má ikonu tužky (edit icon)
                            try:
                                icon = btn.find_element(By.XPATH, ".//*[contains(@class, 'pencil') or contains(@class, 'edit') or contains(@class, 'icon-edit')]")
                                if icon:
                                    edit_button = btn
                                    print(f"✓ Tlačítko 'Upravit' nalezeno podle ikony tužky")
                                    break
                            except:
                                pass
                    except:
                        continue
            except:
                pass
            
            # Pokud se nenašlo, zkusit najít podle selektorů (tlačítka i odkazy)
            if not edit_button:
                edit_selectors = [
                    # Hledat tlačítko nebo odkaz s textem "Upravit"
                    (By.XPATH, "//button[contains(., 'Upravit') or contains(., 'Edit')]"),
                    (By.XPATH, "//a[contains(., 'Upravit') or contains(., 'Edit')]"),
                    (By.XPATH, "//button[contains(@title, 'Upravit') or contains(@title, 'Edit')]"),
                    (By.XPATH, "//a[contains(@title, 'Upravit') or contains(@title, 'Edit')]"),
                    (By.XPATH, "//button[contains(@aria-label, 'Upravit') or contains(@aria-label, 'Edit')]"),
                    (By.XPATH, "//a[contains(@aria-label, 'Upravit') or contains(@aria-label, 'Edit')]"),
                    # Hledat tlačítko s ikonou tužky
                    (By.XPATH, "//button[.//*[contains(@class, 'pencil') or contains(@class, 'edit') or contains(@class, 'icon-edit')]]"),
                    (By.XPATH, "//a[.//*[contains(@class, 'pencil') or contains(@class, 'edit') or contains(@class, 'icon-edit')]]"),
                    (By.CSS_SELECTOR, "button[title*='Upravit'], button[title*='Edit'], a[title*='Upravit'], a[title*='Edit']"),
                    (By.CSS_SELECTOR, ".edit-button, .btn-edit, [data-action='edit']"),
                    (By.XPATH, "//button[contains(@class, 'edit') or contains(@id, 'edit')]"),
                    (By.XPATH, "//a[contains(@class, 'edit') or contains(@id, 'edit')]"),
                    # Hledat v tooltip nebo popup
                    (By.CSS_SELECTOR, "[role='tooltip'] button, .tooltip button, [role='tooltip'] a, .tooltip a"),
                ]
                
                for by, selector in edit_selectors:
                    try:
                        elements = driver.find_elements(by, selector)
                        for elem in elements:
                            try:
                                if elem.is_displayed():
                                    elem_text = (elem.text or '').strip().lower()
                                    elem_title = (elem.get_attribute('title') or '').strip().lower()
                                    
                                    if 'upravit' in elem_text or 'edit' in elem_text or 'upravit' in elem_title or 'edit' in elem_title:
                                        edit_button = elem
                                        print(f"✓ Tlačítko 'Upravit' nalezeno: '{elem.text or elem.get_attribute('title') or 'bez textu'}'")
                                        break
                            except:
                                continue
                        if edit_button:
                            break
                    except:
                        continue
            
            if edit_button:
                try:
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", edit_button)
                    time.sleep(0.5)
                    driver.execute_script("arguments[0].click();", edit_button)
                    print("✓ Kliknuto na 'Upravit' - otevírá se dialog s kódem...")
                    time.sleep(2)  # Počkat, až se otevře dialog s kódem
                except:
                    edit_button.click()
                    time.sleep(2)
            else:
                print("⚠️  Tlačítko 'Upravit' nenalezeno - zkusím pokračovat")
                # Uložit screenshot pro debug
                try:
                    driver.save_screenshot("/tmp/webnode_edit_button_debug.png")
                    print("📸 Screenshot uložen do: /tmp/webnode_edit_button_debug.png")
                except:
                    pass
        else:
            print("⚠️  HTML blok nenalezen - zkusím pokračovat bez kliknutí")
        
        return True
        
    except Exception as e:
        print(f"❌ Chyba při otevírání stránky: {e}")
        import traceback
        traceback.print_exc()
        return False

def insert_html(driver, html_content):
    """Vloží HTML do otevřeného dialogu/tabulky s kódem"""
    print("📝 Hledám otevřený dialog/tabulku s HTML kódem...")
    
    try:
        # Počkat, až se dialog/tabulka otevře
        time.sleep(2)
        
        # Zkusit najít otevřený dialog "UPRAVIT HTML" s textarea
        html_element = None
        
        # 1. Zkusit najít dialog s názvem "UPRAVIT HTML" nebo "EDIT HTML"
        try:
            # Hledat dialog podle názvu
            dialog_selectors = [
                (By.XPATH, "//*[contains(text(), 'UPRAVIT HTML') or contains(text(), 'EDIT HTML')]"),
                (By.XPATH, "//*[contains(text(), 'Upravit HTML') or contains(text(), 'Edit HTML')]"),
            ]
            
            dialog = None
            for by, selector in dialog_selectors:
                try:
                    dialogs = driver.find_elements(by, selector)
                    for d in dialogs:
                        if d.is_displayed():
                            # Najít rodičovský dialog/modal
                            dialog = d.find_element(By.XPATH, "./ancestor::div[contains(@class, 'modal') or contains(@class, 'dialog')]")
                            if dialog:
                                print(f"✓ Nalezen dialog 'UPRAVIT HTML'")
                                break
                    if dialog:
                        break
                except:
                    continue
            
            # Hledat textarea podle ID pattern (z learned steps: wnd_HtmlBlock_*_popup_html_popup_content_item_*)
            try:
                textarea_by_id = driver.find_elements(By.CSS_SELECTOR, "textarea[id^='wnd_HtmlBlock_'][id*='popup_html']")
                for textarea in textarea_by_id:
                    if textarea.is_displayed():
                        html_element = textarea
                        element_type = 'textarea'
                        print(f"✓ Nalezen textarea podle ID pattern: {textarea.get_attribute('id')}")
                        break
            except:
                pass
            
            # Hledat textarea v dialogu s label "Vložte HTML kód:"
            if not html_element:
                textarea_selectors = [
                    (By.XPATH, "//label[contains(text(), 'Vložte HTML kód') or contains(text(), 'Insert HTML code')]/following::textarea"),
                    (By.XPATH, "//label[contains(text(), 'Vložte HTML kód') or contains(text(), 'Insert HTML code')]/..//textarea"),
                    (By.XPATH, "//textarea[preceding::label[contains(text(), 'Vložte HTML kód') or contains(text(), 'HTML')]]"),
                ]
                
                for by, selector in textarea_selectors:
                    try:
                        textareas = driver.find_elements(by, selector)
                        for textarea in textareas:
                            if textarea.is_displayed():
                                html_element = textarea
                                element_type = 'textarea'
                                print("✓ Nalezen textarea v dialogu 'UPRAVIT HTML'")
                                break
                        if html_element:
                            break
                    except:
                        continue
            
            # Pokud se nenašlo podle labelu, zkusit najít textarea v dialogu
            if not html_element:
                textareas = driver.find_elements(By.TAG_NAME, "textarea")
                for textarea in textareas:
                    if textarea.is_displayed():
                        # Zkontrolovat, zda je textarea v dialogu (wnd-p-dialog nebo modal/dialog)
                        try:
                            parent = textarea.find_element(By.XPATH, "./ancestor::div[contains(@class, 'wnd-p-dialog') or contains(@class, 'modal') or contains(@class, 'dialog') or contains(@class, 'popup')]")
                            if parent and parent.is_displayed():
                                html_element = textarea
                                element_type = 'textarea'
                                print("✓ Nalezen textarea v dialogu")
                                break
                        except:
                            continue
        except:
            pass
        
        # 2. Zkusit najít iframe s HTML obsahem
        if not html_element:
            try:
                iframes = driver.find_elements(By.TAG_NAME, "iframe")
                for iframe in iframes:
                    if iframe.is_displayed():
                        # Zkusit přepnout do iframe a zkontrolovat obsah
                        try:
                            driver.switch_to.frame(iframe)
                            body = driver.find_element(By.TAG_NAME, "body")
                            html_element = body
                            element_type = 'iframe'
                            print("✓ Nalezen iframe pro HTML")
                            break
                        except:
                            driver.switch_to.default_content()
                            continue
            except:
                pass
        
        # 3. Zkusit najít contenteditable div
        if not html_element:
            try:
                editables = driver.find_elements(By.CSS_SELECTOR, "[contenteditable='true']")
                for editable in editables:
                    if editable.is_displayed():
                        # Zkontrolovat, zda obsahuje HTML strukturu
                        inner_html = editable.get_attribute('innerHTML') or ''
                        if len(inner_html) > 100 or '<' in inner_html or len(inner_html) == 0:
                            html_element = editable
                            element_type = 'contenteditable'
                            print("✓ Nalezen contenteditable element pro HTML")
                            break
            except:
                pass
        
        # 4. Fallback - zkusit najít podle selektorů
        if not html_element:
            try:
                textareas = driver.find_elements(By.CSS_SELECTOR, "textarea[id*='html'], textarea[id*='code'], textarea[class*='html']")
                for textarea in textareas:
                    if textarea.is_displayed():
                        html_element = textarea
                        element_type = 'textarea'
                        print("✓ Nalezen HTML element pomocí selektoru: [id*='html'], [id*='code'], [class*='html']")
                        break
            except:
                pass
        
        # 2. Zkusit najít iframe s HTML obsahem
        if not html_element:
            try:
                iframes = driver.find_elements(By.TAG_NAME, "iframe")
                for iframe in iframes:
                    if iframe.is_displayed():
                        # Zkusit přepnout do iframe a zkontrolovat obsah
                        try:
                            driver.switch_to.frame(iframe)
                            body = driver.find_element(By.TAG_NAME, "body")
                            html_element = body
                            element_type = 'iframe'
                            print("✓ Nalezen iframe pro HTML")
                            break
                        except:
                            driver.switch_to.default_content()
                            continue
            except:
                pass
        
        # 3. Zkusit najít contenteditable div
        if not html_element:
            try:
                editables = driver.find_elements(By.CSS_SELECTOR, "[contenteditable='true']")
                for editable in editables:
                    if editable.is_displayed():
                        # Zkontrolovat, zda obsahuje HTML strukturu
                        inner_html = editable.get_attribute('innerHTML') or ''
                        if len(inner_html) > 100 or '<' in inner_html or len(inner_html) == 0:
                            html_element = editable
                            element_type = 'contenteditable'
                            print("✓ Nalezen contenteditable element pro HTML")
                            break
            except:
                pass
        
        # 4. Zkusit najít podle třídy nebo ID (Webnode specifické)
        if not html_element:
            try:
                selectors = [
                    (By.CSS_SELECTOR, ".html-block, .html-content, .code-block"),
                    (By.CSS_SELECTOR, "[id*='html'], [id*='code'], [class*='html']"),
                    (By.XPATH, "//textarea[contains(@class, 'html') or contains(@id, 'html')]"),
                    (By.XPATH, "//div[contains(@class, 'html') or contains(@id, 'html')]"),
                ]
                for by, selector in selectors:
                    try:
                        elements = driver.find_elements(by, selector)
                        for elem in elements:
                            if elem.is_displayed():
                                html_element = elem
                                element_type = 'specific'
                                print(f"✓ Nalezen HTML element pomocí selektoru: {selector}")
                                break
                        if html_element:
                            break
                    except:
                        continue
            except:
                pass
        
        if not html_element:
            print("❌ Nepodařilo se najít HTML blok na stránce")
            print("💡 Zkuste:")
            print("   1. Otevřít stránku v prohlížeči")
            print("   2. Najít HTML blok/políčko")
            print("   3. Zkopírovat HTML ručně")
            
            # Uložit screenshot pro debug
            try:
                driver.save_screenshot("/tmp/webnode_html_block_debug.png")
                print("📸 Screenshot uložen do: /tmp/webnode_html_block_debug.png")
            except:
                pass
            return False
        
        # Vložit HTML do nalezeného elementu
        print("📝 Vkládám HTML do dialogu...")
        
        if element_type == 'textarea':
            # Kliknout na textarea, aby získal focus
            print("🖱️  Klikám na textarea...")
            driver.execute_script("arguments[0].focus();", html_element)
            driver.execute_script("arguments[0].click();", html_element)
            time.sleep(0.5)
            
            # Označit všechen text pomocí JavaScript (Ctrl+A)
            print("📋 Označuji všechen text (Ctrl+A)...")
            driver.execute_script("""
                var elem = arguments[0];
                elem.focus();
                elem.select();
                if (elem.setSelectionRange) {
                    elem.setSelectionRange(0, elem.value.length);
                }
                // Také zkusit pomocí Ctrl+A
                var event = new KeyboardEvent('keydown', {
                    key: 'a',
                    code: 'KeyA',
                    ctrlKey: true,
                    bubbles: true
                });
                elem.dispatchEvent(event);
            """, html_element)
            time.sleep(0.5)
            
            # Vymazat starý obsah a vložit nový pomocí JavaScript
            print("📝 Vkládám nový HTML kód...")
            driver.execute_script("""
                var elem = arguments[0];
                var content = arguments[1];
                // Vymazat starý obsah
                elem.value = '';
                // Vložit nový obsah
                elem.value = content;
                // Spustit události pro uložení
                elem.dispatchEvent(new Event('input', { bubbles: true }));
                elem.dispatchEvent(new Event('change', { bubbles: true }));
                elem.dispatchEvent(new Event('keyup', { bubbles: true }));
                elem.dispatchEvent(new Event('paste', { bubbles: true }));
            """, html_element, html_content)
            
            print("✓ HTML vloženo do textarea (celý obsah z index.html)!")
            
        elif element_type == 'iframe':
            # Vymazat starý obsah
            driver.execute_script("arguments[0].innerHTML = '';", html_element)
            time.sleep(0.5)
            # Vložit nový obsah
            driver.execute_script("arguments[0].innerHTML = arguments[1];", html_element, html_content)
            driver.switch_to.default_content()
            print("✓ HTML vloženo do iframe!")
            
        else:  # contenteditable nebo specific
            # Vymazat starý obsah
            driver.execute_script("arguments[0].innerHTML = '';", html_element)
            time.sleep(0.5)
            # Vložit nový obsah
            driver.execute_script("arguments[0].innerHTML = arguments[1];", html_element, html_content)
            # Spustit události
            driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", html_element)
            driver.execute_script("arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", html_element)
            print("✓ HTML vloženo do elementu!")
        
        # Najít a kliknout na tlačítko OK v dialogu "UPRAVIT HTML"
        print("🔍 Hledám tlačítko OK v dialogu 'UPRAVIT HTML'...")
        ok_button = None
        
        # Počkat déle na načtení dialogu
        time.sleep(2)
        
        # Nejdřív zkusit najít dialog "UPRAVIT HTML"
        dialog = None
        try:
            # Zkusit najít podle textu v nadpisu
            dialog_elements = driver.find_elements(By.XPATH, "//*[contains(text(), 'UPRAVIT HTML') or contains(text(), 'EDIT HTML') or contains(text(), 'Upravit HTML')]")
            for d in dialog_elements:
                if d.is_displayed():
                    try:
                        dialog = d.find_element(By.XPATH, "./ancestor::div[contains(@class, 'modal') or contains(@class, 'dialog') or contains(@class, 'popup')]")
                        if dialog:
                            print("✓ Dialog 'UPRAVIT HTML' nalezen podle nadpisu")
                            break
                    except:
                        continue
        except:
            pass
        
        # Pokud se dialog nenašel, zkusit najít podle textarea (které už máme)
        if not dialog and html_element:
            try:
                # Zkusit různé selektory pro dialog
                dialog_selectors = [
                    "./ancestor::div[contains(@class, 'modal')]",
                    "./ancestor::div[contains(@class, 'dialog')]",
                    "./ancestor::div[contains(@class, 'popup')]",
                    "./ancestor::div[contains(@class, 'window')]",
                    "./ancestor::div[@role='dialog']",
                    "./ancestor::div[contains(@id, 'modal')]",
                    "./ancestor::div[contains(@id, 'dialog')]",
                ]
                for selector in dialog_selectors:
                    try:
                        dialog = html_element.find_element(By.XPATH, selector)
                        if dialog and dialog.is_displayed():
                            print(f"✓ Dialog nalezen podle textarea: {selector}")
                            break
                    except:
                        continue
            except:
                pass
        
        # Pokud se dialog stále nenašel, zkusit najít všechny modaly/dialogy na stránce
        if not dialog:
            try:
                all_modals = driver.find_elements(By.CSS_SELECTOR, "[class*='modal'], [class*='dialog'], [class*='popup'], [role='dialog']")
                for modal in all_modals:
                    if modal.is_displayed():
                        # Zkontrolovat, zda obsahuje textarea
                        try:
                            modal.find_element(By.TAG_NAME, "textarea")
                            dialog = modal
                            print("✓ Dialog nalezen podle textarea v modalu")
                            break
                        except:
                            continue
            except:
                pass
        
        ok_selectors = [
            # Hledat tlačítko OK v dialogu s HTML (podle learned steps - dialog má třídu wnd-p-dialog)
            (By.XPATH, "//div[contains(@class, 'wnd-p-dialog')]//button[normalize-space(text())='OK']"),
            (By.XPATH, "//div[contains(@class, 'wnd-p-dialog')]//button[contains(., 'OK')]"),
            (By.XPATH, "//div[contains(@class, 'wnd-t-popup-content')]//button[normalize-space(text())='OK']"),
            (By.XPATH, "//div[contains(@class, 'wnd-t-popup-content')]//button[contains(., 'OK')]"),
            # Hledat tlačítko OK v dialogu (modré tlačítko vpravo)
            (By.XPATH, "//div[contains(@class, 'modal') or contains(@class, 'dialog')]//button[normalize-space(text())='OK']"),
            (By.XPATH, "//div[contains(@class, 'modal') or contains(@class, 'dialog')]//button[contains(., 'OK')]"),
            (By.XPATH, "//button[normalize-space(text())='OK' or normalize-space(text())='Ok']"),
            (By.XPATH, "//button[contains(., 'OK') or contains(., 'Ok')]"),
            # Hledat modré tlačítko v dialogu (OK je obvykle modré/primary)
            (By.XPATH, "//div[contains(@class, 'wnd-p-dialog')]//button[contains(@class, 'primary') or contains(@class, 'btn-primary')]"),
            (By.XPATH, "//div[contains(@class, 'modal') or contains(@class, 'dialog')]//button[contains(@class, 'primary') or contains(@class, 'btn-primary')]"),
            (By.XPATH, "//div[contains(@class, 'modal') or contains(@class, 'dialog')]//button[contains(@class, 'btn') and not(contains(@class, 'secondary'))]"),
            # Hledat tlačítko podle pozice (vpravo dole v dialogu)
            (By.XPATH, "//div[contains(@class, 'modal') or contains(@class, 'dialog')]//button[contains(@class, 'btn')][last()]"),
            (By.XPATH, "//button[contains(text(), 'Uložit') or contains(text(), 'Save')]"),
            (By.XPATH, "//button[@type='submit']"),
            (By.CSS_SELECTOR, ".modal button.btn-primary, .dialog button.btn-primary, .wnd-p-dialog button.btn-primary"),
            # Hledat všechna tlačítka v dialogu a vybrat to modré/primary
            (By.CSS_SELECTOR, "[class*='modal'] button, [class*='dialog'] button, [class*='wnd-p-dialog'] button"),
        ]
        
        # Nejdřív zkusit najít všechna viditelná tlačítka v dialogu
        if dialog:
            try:
                # Zkusit najít tlačítka v dialogu (včetně footeru)
                dialog_buttons = dialog.find_elements(By.TAG_NAME, "button")
                print(f"🔍 Nalezeno {len(dialog_buttons)} tlačítek v dialogu, kontroluji...")
                
                # Zkusit najít také odkazy (a tagy) v dialogu
                dialog_links = dialog.find_elements(By.TAG_NAME, "a")
                print(f"🔍 Nalezeno {len(dialog_links)} odkazů v dialogu, kontroluji...")
                
                # Zkusit najít footer dialogu
                try:
                    footer = dialog.find_element(By.CSS_SELECTOR, ".modal-footer, .dialog-footer, .popup-footer, [class*='footer']")
                    footer_buttons = footer.find_elements(By.TAG_NAME, "button")
                    footer_links = footer.find_elements(By.TAG_NAME, "a")
                    print(f"🔍 Nalezen footer s {len(footer_buttons)} tlačítky a {len(footer_links)} odkazy")
                    dialog_buttons.extend(footer_buttons)
                    dialog_links.extend(footer_links)
                except:
                    pass
                
                # Zkontrolovat tlačítka
                for btn in dialog_buttons:
                    try:
                        if btn.is_displayed():
                            btn_text = (btn.text or '').strip()
                            btn_class = (btn.get_attribute('class') or '').lower()
                            print(f"  Tlačítko: Text='{btn_text}', Class='{btn_class[:50]}'")
                            
                            # Zkontrolovat, zda text tlačítka obsahuje OK
                            if btn_text.upper() == 'OK' or btn_text == 'Ok':
                                ok_button = btn
                                print(f"✓ Tlačítko OK nalezeno: '{btn_text}'")
                                break
                    except:
                        continue
                
                # Zkontrolovat odkazy
                if not ok_button:
                    for link in dialog_links:
                        try:
                            if link.is_displayed():
                                link_text = (link.text or '').strip()
                                if link_text.upper() == 'OK' or link_text == 'Ok':
                                    ok_button = link
                                    print(f"✓ Odkaz OK nalezen: '{link_text}'")
                                    break
                        except:
                            continue
            except Exception as e:
                print(f"⚠️  Chyba při hledání tlačítek v dialogu: {e}")
        
        # Pokud se dialog nenašel, zkusit najít všechna viditelná tlačítka na stránce
        if not ok_button:
            try:
                # Zkusit najít tlačítko OK pomocí XPath (hledat všude)
                ok_xpath_selectors = [
                    "//button[normalize-space(text())='OK']",
                    "//button[normalize-space(text())='Ok']",
                    "//a[normalize-space(text())='OK']",
                    "//a[normalize-space(text())='Ok']",
                    "//*[normalize-space(text())='OK' and (self::button or self::a)]",
                ]
                
                for xpath in ok_xpath_selectors:
                    try:
                        elements = driver.find_elements(By.XPATH, xpath)
                        for elem in elements:
                            try:
                                if elem.is_displayed():
                                    # Zkontrolovat, zda je element v dialogu (ne v hlavní navigaci)
                                    try:
                                        parent = elem.find_element(By.XPATH, "./ancestor::div[contains(@class, 'modal') or contains(@class, 'dialog') or contains(@class, 'popup')]")
                                        if parent and parent.is_displayed():
                                            ok_button = elem
                                            print(f"✓ Tlačítko OK nalezeno pomocí XPath: '{xpath}'")
                                            break
                                    except:
                                        # Pokud se nenašel parent dialog, zkusit zkontrolovat, zda není v hlavní navigaci
                                        try:
                                            nav_parent = elem.find_element(By.XPATH, "./ancestor::*[contains(@class, 'wnd-a-button')]")
                                            # Pokud je v navigaci, přeskočit
                                            continue
                                        except:
                                            # Pokud není v navigaci, může to být OK tlačítko
                                            ok_button = elem
                                            print(f"✓ Tlačítko OK nalezeno (není v navigaci): '{xpath}'")
                                            break
                            except:
                                continue
                        if ok_button:
                            break
                    except:
                        continue
                
                # Pokud se stále nenašlo, zkusit najít všechna viditelná tlačítka
                if not ok_button:
                    all_buttons = driver.find_elements(By.TAG_NAME, "button")
                    visible_buttons = [b for b in all_buttons if b.is_displayed()]
                    print(f"🔍 Hledám tlačítko OK mezi všemi viditelnými tlačítky ({len(visible_buttons)})...")
                    for btn in visible_buttons:
                        try:
                            btn_text = (btn.text or '').strip()
                            if btn_text.upper() == 'OK' or btn_text == 'Ok':
                                # Zkontrolovat, zda není v hlavní navigaci
                                try:
                                    nav_parent = btn.find_element(By.XPATH, "./ancestor::*[contains(@class, 'wnd-a-button')]")
                                    continue
                                except:
                                    ok_button = btn
                                    print(f"✓ Tlačítko OK nalezeno: '{btn_text}'")
                                    break
                        except:
                            continue
            except Exception as e:
                print(f"⚠️  Chyba při hledání tlačítka OK: {e}")
        
        # Pokud se nenašlo v dialogu, zkusit najít podle selektorů
        if not ok_button:
            for by, selector in ok_selectors:
                try:
                    buttons = driver.find_elements(by, selector)
                    for btn in buttons:
                        try:
                            if btn.is_displayed():
                                btn_text = (btn.text or '').strip()
                                btn_class = (btn.get_attribute('class') or '').lower()
                                
                                # Zkontrolovat, zda text tlačítka obsahuje OK
                                if btn_text.upper() == 'OK' or btn_text == 'Ok':
                                    ok_button = btn
                                    print(f"✓ Tlačítko OK nalezeno: '{btn_text}' (selektor: {selector})")
                                    break
                        except:
                            continue
                    if ok_button:
                        break
                except Exception as e:
                    continue
        
        if ok_button:
            try:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", ok_button)
                time.sleep(0.5)
                driver.execute_script("arguments[0].click();", ok_button)
                print("✓ Kliknuto na tlačítko OK")
                time.sleep(2)  # Počkat, až se dialog zavře
            except Exception as e:
                try:
                    ok_button.click()
                    print("✓ Kliknuto na tlačítko OK (normální klik)")
                    time.sleep(2)
                except Exception as e2:
                    print(f"⚠️  Chyba při kliknutí na OK: {e2}")
        else:
            print("⚠️  Tlačítko OK nenalezeno - zkusím pokračovat bez kliknutí")
            # Uložit screenshot pro debug
            try:
                driver.save_screenshot("/tmp/webnode_ok_button_debug.png")
                print("📸 Screenshot uložen do: /tmp/webnode_ok_button_debug.png")
            except:
                pass
        
        # Počkat déle, aby se změny uložily
        print("⏳ Čekám na uložení změn...")
        time.sleep(3)
        return True
        
    except Exception as e:
        print(f"❌ Chyba při vkládání HTML: {e}")
        import traceback
        traceback.print_exc()
        return False

def publish_page(driver):
    """Klikne na tlačítko publikace vpravo nahoře"""
    print("📤 Publikuji změny...")
    
    try:
        # Počkat chvíli, aby se stránka načetla
        time.sleep(2)
        
        # Zkusit najít tlačítko publikace - obvykle je vpravo nahoře
        publish_button = None
        selectors = [
            # Různé možné selektory pro tlačítko publikace
            (By.XPATH, "//button[contains(text(), 'Publikovat') or contains(text(), 'Publish')]"),
            (By.XPATH, "//a[contains(text(), 'Publikovat') or contains(text(), 'Publish')]"),
            (By.CSS_SELECTOR, "button[title*='Publikovat'], button[title*='Publish']"),
            (By.CSS_SELECTOR, "a[title*='Publikovat'], a[title*='Publish']"),
            (By.CSS_SELECTOR, ".publish-button, .btn-publish, [data-action='publish']"),
            (By.XPATH, "//button[contains(@class, 'publish') or contains(@id, 'publish')]"),
            (By.XPATH, "//a[contains(@class, 'publish') or contains(@id, 'publish')]"),
            # Zkusit najít tlačítko vpravo nahoře (obvykle má ikonu nebo text "Publikovat")
            (By.CSS_SELECTOR, ".header button, .toolbar button, .top-bar button"),
        ]
        
        for by, value in selectors:
            try:
                elements = driver.find_elements(by, value)
                for elem in elements:
                    # Zkontrolovat, zda je element viditelný a obsahuje text související s publikací
                    if elem.is_displayed():
                        text = elem.text.lower()
                        if any(word in text for word in ['publikovat', 'publish', 'zveřejnit', 'zverejnit']):
                            publish_button = elem
                            break
                        # Nebo zkontrolovat title/aria-label
                        title = elem.get_attribute('title') or elem.get_attribute('aria-label') or ''
                        if any(word in title.lower() for word in ['publikovat', 'publish', 'zveřejnit', 'zverejnit']):
                            publish_button = elem
                            break
                if publish_button:
                    break
            except:
                continue
        
        if publish_button:
            try:
                # Scrollovat k tlačítku
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", publish_button)
                time.sleep(0.5)
                
                # Zkusit kliknout přes JavaScript (obvykle spolehlivější)
                driver.execute_script("arguments[0].click();", publish_button)
                print("✓ Kliknuto na tlačítko publikace (přes JavaScript)")
                time.sleep(2)
                
                # Zkontrolovat, zda se objevilo potvrzovací dialog nebo zda se stránka změnila
                # Někdy je potřeba potvrdit publikaci v dialogu
                try:
                    # Zkusit najít potvrzovací tlačítko v dialogu
                    confirm_selectors = [
                        (By.XPATH, "//button[contains(text(), 'Ano') or contains(text(), 'Yes') or contains(text(), 'Potvrdit') or contains(text(), 'Confirm')]"),
                        (By.XPATH, "//button[contains(text(), 'OK')]"),
                        (By.CSS_SELECTOR, ".modal button.btn-primary, .dialog button.btn-primary"),
                    ]
                    
                    for by, value in confirm_selectors:
                        try:
                            confirm_btn = WebDriverWait(driver, 3).until(
                                EC.element_to_be_clickable((by, value))
                            )
                            if confirm_btn and confirm_btn.is_displayed():
                                driver.execute_script("arguments[0].click();", confirm_btn)
                                print("✓ Publikace potvrzena")
                                time.sleep(2)
                                break
                        except:
                            continue
                except:
                    pass
                
                print("✅ Publikace dokončena!")
                return True
            except Exception as e:
                print(f"⚠️  Chyba při kliknutí na publikaci: {e}")
                # Zkusit normální klik jako fallback
                try:
                    publish_button.click()
                    print("✓ Kliknuto na tlačítko publikace (normální klik)")
                    time.sleep(2)
                    return True
                except:
                    pass
        else:
            print("⚠️  Tlačítko publikace nenalezeno")
            print("💡 Zkuste publikovat ručně v editoru")
            # Uložit screenshot pro debug
            try:
                driver.save_screenshot("/tmp/webnode_publish_debug.png")
                print("📸 Screenshot uložen do: /tmp/webnode_publish_debug.png")
            except:
                pass
            return False
        
    except Exception as e:
        print(f"⚠️  Chyba při publikaci: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("🚗 TooZ Hub 2 - Automatické vložení do Webnode")
    print("=" * 50)
    
    # Získat lock - zajištění, že běží jen jedna instance
    lock_fd = acquire_lock()
    if lock_fd is None:
        # Počkat chvíli a zkusit znovu
        time.sleep(2)
        lock_fd = acquire_lock()
        if lock_fd is None:
            print("❌ Nelze získat lock - jiná instance stále běží")
            sys.exit(1)
    
    try:
        # Načíst konfiguraci
        config = load_config()
        email = config.get("email")
        password = config.get("password")
        page_url = config.get("page_url")
        
        if not all([email, password, page_url]):
            print("❌ Konfigurační soubor neobsahuje všechny potřebné údaje!")
            sys.exit(1)
        
        # Načíst HTML
        html_content = read_html()
        print(f"✓ HTML načteno ({len(html_content)} znaků)")
        
        # Nastavit driver
        driver = setup_driver()
        
        try:
            # Přihlásit se
            if not login_to_webnode(driver, email, password):
                print("❌ Přihlášení selhalo")
                return
            
            # Otevřít stránku s HTML blokem
            if not edit_page(driver, page_url):
                print("❌ Otevření stránky selhalo")
                print(f"💡 Zkontrolujte URL v konfiguraci: {page_url}")
                print("💡 URL by měla být: https://finalni-verze.cms.webnode.cz/toozhub-aplikace")
                return
            
            # KROK 1: Vložit HTML do HTML bloku
            print("\n" + "="*50)
            print("KROK 1/2: Vkládání HTML do HTML bloku")
            print("="*50)
            if not insert_html(driver, html_content):
                print("❌ Vložení HTML selhalo - zkuste ručně")
                print("💡 Prohlížeč zůstane otevřený pro ruční úpravy.")
                return
            
            # KROK 2: Počkat na dokončení uložení a pak publikovat
            print("\n" + "="*50)
            print("KROK 2/2: Publikace změn")
            print("="*50)
            # Počkat ještě chvíli, aby se změny definitivně uložily
            print("⏳ Čekám na dokončení uložení...")
            time.sleep(2)
            
            # Publikovat jako poslední krok
            if publish_page(driver):
                print("\n" + "="*50)
                print("✅ HOTOVO! HTML bylo vloženo, uloženo a publikováno.")
                print("="*50)
            else:
                print("\n⚠️  HTML bylo vloženo, ale publikace selhala.")
                print("💡 Zkuste publikovat ručně v editoru.")
            
            print("💡 Prohlížeč zůstane otevřený - můžete ručně zkontrolovat změny.")
            
            # Počkat před zavřením (pokud není headless režim)
            try:
                import sys
                if sys.stdin.isatty():  # Pouze pokud je interaktivní terminál
                    input("\nStiskněte Enter pro zavření prohlížeče...")
                else:
                    print("\n💡 Prohlížeč zůstane otevřený. Zavřete ho ručně po kontrole.")
                    time.sleep(5)  # Počkat 5 sekund
            except:
                print("\n💡 Prohlížeč zůstane otevřený. Zavřete ho ručně po kontrole.")
                time.sleep(5)
        finally:
            if 'driver' in locals():
                driver.quit()
    finally:
        # Uvolnit lock
        release_lock(lock_fd)

if __name__ == "__main__":
    main()

