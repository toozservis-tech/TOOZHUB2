#!/usr/bin/env python3
"""
Systémová tray ikona pro TooZ Hub 2 - FINÁLNÍ TOP verze
Kombinace všech tří návrhů:
- Automatický start serveru + tunelu (ChatGPT pystray)
- Status monitoring s barevnou indikací (můj návrh)
- Konfigurace z JSON (ChatGPT PySide6)
- pystray (lehká knihovna)
"""

import os
import subprocess
import sys
import webbrowser
import time
import threading
import json
from pathlib import Path
from typing import Optional

import pystray
from pystray import MenuItem as Item
from PIL import Image, ImageDraw, ImageFont
import requests

# --------------------------------------------------
# Konfigurace
# --------------------------------------------------

# Automatická detekce cesty k projektu (Windows i Linux kompatibilní)
PROJECT_ROOT = Path(__file__).parent.resolve()
CONFIG_FILE = PROJECT_ROOT / "tray_hub2_config.json"

# Najít správný Python executable (multi-platformní detekce)
# Zkusit Windows venv (priorita na Windows)
VENV_PYTHON_WIN = PROJECT_ROOT / "venv" / "Scripts" / "python.exe"
VENV_PYTHONW = PROJECT_ROOT / "venv" / "Scripts" / "pythonw.exe"
# Zkusit Linux venv (fallback, pokud Windows neexistuje)
VENV_PYTHON_LINUX = PROJECT_ROOT / "venv" / "bin" / "python"

# Detekce podle OS - WINDOWS NEPOUŽÍVÁ LINUX VENV!
if sys.platform == "win32":
    # Windows - POUZE Windows venv nebo globální Python
    # NIKDY nepoužít Linux venv na Windows - nefunguje!
    if VENV_PYTHON_WIN.exists():
        PYTHON_EXECUTABLE = str(VENV_PYTHON_WIN)
    else:
        # Fallback na globální Python (Windows)
        # Linux venv se NEPOUŽÍVÁ na Windows!
        PYTHON_EXECUTABLE = sys.executable
else:
    # Linux/Mac - zkontrolovat Linux venv, pak globální
    if VENV_PYTHON_LINUX.exists():
        PYTHON_EXECUTABLE = str(VENV_PYTHON_LINUX)
    else:
        # Fallback na globální Python
        PYTHON_EXECUTABLE = sys.executable

# Výchozí hodnoty
DEFAULT_API_URL = "http://127.0.0.1:8000"
DEFAULT_TUNNEL_NAME = "tooz-hub2"
DEFAULT_SERVER_PORT = 8000

# Globální proměnné (načtené z konfigurace)
API_URL = DEFAULT_API_URL
CLOUDFLARE_TUNNEL_NAME = DEFAULT_TUNNEL_NAME
SERVER_PORT = DEFAULT_SERVER_PORT

# Stav procesů a aplikace
uvicorn_process: Optional[subprocess.Popen] = None
cloudflared_process: Optional[subprocess.Popen] = None
tray_icon: Optional[pystray.Icon] = None
status_running = True

# Status indikace
server_status = False
tunnel_status = False

# Interval kontroly stavu (sekundy)
STATUS_CHECK_INTERVAL = 10


def load_config():
    """Načte konfiguraci z JSON souboru (pokud existuje)"""
    global API_URL, SERVER_PORT, CLOUDFLARE_TUNNEL_NAME
    
    try:
        if CONFIG_FILE.exists():
            with CONFIG_FILE.open("r", encoding="utf-8") as f:
                data = json.load(f)
            
            api_url = data.get("api_url") or data.get("API_URL")
            if isinstance(api_url, str) and api_url.strip():
                API_URL = api_url.strip()
            
            tunnel_name = data.get("tunnel_name") or data.get("CLOUDFLARE_TUNNEL_NAME")
            if isinstance(tunnel_name, str) and tunnel_name.strip():
                CLOUDFLARE_TUNNEL_NAME = tunnel_name.strip()
            
            port = data.get("server_port") or data.get("SERVER_PORT")
            if isinstance(port, int):
                SERVER_PORT = port
            elif isinstance(port, str) and port.isdigit():
                SERVER_PORT = int(port)
    except Exception:
        # Při chybě použít defaultní hodnoty
        pass


def save_config():
    """Uloží konfiguraci do JSON souboru"""
    global API_URL, SERVER_PORT, CLOUDFLARE_TUNNEL_NAME
    try:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with CONFIG_FILE.open("w", encoding="utf-8") as f:
            json.dump(
                {
                    "api_url": API_URL,
                    "tunnel_name": CLOUDFLARE_TUNNEL_NAME,
                    "server_port": SERVER_PORT,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )
    except Exception:
        pass


# Načíst konfiguraci při startu
load_config()

# URL adresy
LOCAL_URL = API_URL
LOCAL_WEB_URL = f"{LOCAL_URL}/web/index.html"
LOCAL_DOCS_URL = f"{LOCAL_URL}/docs"
LOCAL_HEALTH_URL = f"{LOCAL_URL}/health"

PRODUCTION_URL = "https://hub.toozservis.cz"
PRODUCTION_WEB_URL = f"{PRODUCTION_URL}/web/index.html"
PRODUCTION_DOCS_URL = f"{PRODUCTION_URL}/docs"
PRODUCTION_HEALTH_URL = f"{PRODUCTION_URL}/health"

UVICORN_CMD = [
    PYTHON_EXECUTABLE,
    "-m",
    "uvicorn",
    "src.server.main:app",
    "--host",
    "127.0.0.1",
    "--port",
    str(SERVER_PORT),
]

# Cloudflare config soubor pro TooZ Hub 2
CLOUDFLARE_CONFIG_FILE = Path.home() / ".cloudflared" / "config-hub.yml"

# Příkaz pro spuštění cloudflared tunelu s explicitním config souborem
# POZOR: --config musí být PŘED "run", ne po něm!
CLOUDFLARED_CMD = [
    "cloudflared",
    "tunnel",
    "--config", str(CLOUDFLARE_CONFIG_FILE),
    "run",
    CLOUDFLARE_TUNNEL_NAME,
]


def create_icon_image(is_online: bool = False, is_warning: bool = False) -> Image.Image:
    """
    Vytvoří ikonu s barevným gradientem a písmenem "H"
    - Zelená = online (server běží)
    - Žlutá = částečně online (varování)
    - Červená = offline
    """
    # Velikost ikony pro systémovou lištu (16x16 až 256x256, optimální je 64x64)
    size = 64
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    
    # Barvy podle stavu
    if is_online:
        if is_warning:
            # Žlutá/oranžová - částečně online (varování)
            base_color = (255, 217, 61)  # Žlutá
        else:
            # Zelená - plně online
            base_color = (81, 207, 102)  # Zelená
    else:
        # Červená - offline
        base_color = (255, 107, 107)  # Červená
    
    center = size // 2
    max_radius = size // 2 - 2
    
    # Vytvoření gradientového kruhu
    for r in range(max_radius, 0, -1):
        factor = r / max_radius
        # Gradient efekt - tmavší na okrajích, světlejší uprostřed
        color = (
            int(base_color[0] * (0.7 + 0.3 * factor)),
            int(base_color[1] * (0.7 + 0.3 * factor)),
            int(base_color[2] * (0.7 + 0.3 * factor)),
            255,
        )
        draw.ellipse(
            (center - r, center - r, center + r, center + r),
            fill=color,
        )
    
    # Přidat bílý rámeček pro lepší viditelnost
    draw.ellipse(
        (center - max_radius, center - max_radius, center + max_radius, center + max_radius),
        outline=(255, 255, 255, 200),
        width=2,
    )
    
    # Písmeno "H" uprostřed (Hub) - tučné a bílé
    font_size = 36
    try:
        # Zkusit najít vhodný font
        if sys.platform == "win32":
            font = ImageFont.truetype("arialbd.ttf", font_size)
        else:
            font = ImageFont.truetype("DejaVuSans-Bold.ttf", font_size)
    except:
        try:
            if sys.platform == "win32":
                font = ImageFont.truetype("arial.ttf", font_size)
            else:
                font = ImageFont.truetype("DejaVuSans.ttf", font_size)
        except:
            font = ImageFont.load_default()
    
    text = "H"
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    
    text_x = center - text_width // 2
    text_y = center - text_height // 2 - 2  # Mírně posunout nahoru pro lepší zarovnání
    
    # Kreslení písmene "H" - bílé, tučné
    draw.text(
        (text_x, text_y),
        text,
        fill=(255, 255, 255, 255),
        font=font,
    )
    
    # Vytvořit menší ikonu pro systémovou lištu (32x32 je optimální)
    # Windows systémová lišta podporuje různé velikosti, ale 32x32 je standardní
    icon_small = image.resize((32, 32), Image.Resampling.LANCZOS)
    
    return icon_small


def check_server_status() -> bool:
    """Zkontroluje, jestli server běží"""
    try:
        response = requests.get(LOCAL_HEALTH_URL, timeout=2)
        return response.status_code == 200
    except:
        return False


def check_tunnel_status() -> bool:
    """Zkontroluje, jestli tunnel běží"""
    try:
        # Zkusit připojit k produkční URL
        response = requests.get(PRODUCTION_HEALTH_URL, timeout=3)
        return response.status_code == 200
    except:
        # Alternativně zkontrolovat cloudflared proces
        try:
            result = subprocess.run(
                ["cloudflared", "tunnel", "list"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return CLOUDFLARE_TUNNEL_NAME in result.stdout and "x" in result.stdout
        except:
            pass
        return False


def update_icon_status():
    """Aktualizuje ikonu podle stavu serveru a tunelu"""
    global tray_icon, server_status, tunnel_status
    
    if not tray_icon:
        return
    
    server_status = check_server_status()
    tunnel_status = check_tunnel_status()
    
    # Určit stav a barvu ikony
    if server_status and tunnel_status:
        # Vše běží - zelená
        is_online = True
        is_warning = False
        tooltip = "TooZ Hub 2 - Online ✓\nServer: ✓ | Tunnel: ✓"
    elif server_status:
        # Server běží, tunnel ne - žlutá (varování)
        is_online = True
        is_warning = True
        tooltip = "TooZ Hub 2 - Částečně online ⚠\nServer: ✓ | Tunnel: ✗"
    else:
        # Vše offline - červená
        is_online = False
        is_warning = False
        tooltip = "TooZ Hub 2 - Offline ✗\nServer: ✗ | Tunnel: ✗"
    
    # Vytvořit novou ikonu s aktuálním stavem
    new_icon = create_icon_image(is_online=is_online, is_warning=is_warning)
    tray_icon.icon = new_icon
    tray_icon.title = tooltip


def status_monitor_loop():
    """Smyčka pro monitoring stavu - běží na pozadí"""
    global status_running
    
    while status_running:
        update_icon_status()
        time.sleep(STATUS_CHECK_INTERVAL)


# --------------------------------------------------
# Ovládací funkce
# --------------------------------------------------


def start_uvicorn():
    """Spustí uvicorn server"""
    global uvicorn_process
    
    if uvicorn_process is not None and uvicorn_process.poll() is None:
        return  # už běží
    
    # Zkontrolovat, jestli Python executable existuje a je platný
    if not Path(PYTHON_EXECUTABLE).exists():
        print(f"Chyba: Python executable neexistuje: {PYTHON_EXECUTABLE}")
        return
    
    uvicorn_process = subprocess.Popen(
        UVICORN_CMD,
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def stop_uvicorn():
    """Zastaví uvicorn server"""
    global uvicorn_process
    
    if uvicorn_process is None:
        return
    
    try:
        uvicorn_process.terminate()
        uvicorn_process.wait(timeout=10)
    except Exception:
        try:
            uvicorn_process.kill()
        except Exception:
            pass
    
    uvicorn_process = None


def start_cloudflared():
    """Spustí cloudflared tunnel"""
    global cloudflared_process
    
    if cloudflared_process is not None and cloudflared_process.poll() is None:
        return  # už běží
    
    # Zkontrolovat, že config soubor existuje
    if not CLOUDFLARE_CONFIG_FILE.exists():
        print(f"Chyba: Config soubor neexistuje: {CLOUDFLARE_CONFIG_FILE}")
        return
    
    # Nastavit environment variable pro config (alternativa k --config)
    env = os.environ.copy()
    env["CLOUDFLARED_CONFIG"] = str(CLOUDFLARE_CONFIG_FILE)
    
    cloudflared_process = subprocess.Popen(
        CLOUDFLARED_CMD,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
        env=env,
    )


def stop_cloudflared():
    """Zastaví cloudflared tunnel"""
    global cloudflared_process
    
    if cloudflared_process is None:
        return
    
    try:
        cloudflared_process.terminate()
        cloudflared_process.wait(timeout=10)
    except Exception:
        try:
            cloudflared_process.kill()
        except Exception:
            pass
    
    cloudflared_process = None


def start_hub(icon: pystray.Icon, item: Item):
    """Spustí server i tunnel"""
    start_uvicorn()
    time.sleep(1)
    start_cloudflared()
    threading.Timer(3.0, update_icon_status).start()


def stop_hub(icon: pystray.Icon, item: Item):
    """Zastaví server i tunnel"""
    stop_cloudflared()
    stop_uvicorn()
    threading.Timer(1.0, update_icon_status).start()


def restart_hub(icon: pystray.Icon, item: Item):
    """Restartuje server i tunnel"""
    stop_hub(icon, item)
    time.sleep(2)
    start_hub(icon, item)


def restart_server(icon: pystray.Icon, item: Item):
    """Restartuje pouze server"""
    stop_uvicorn()
    time.sleep(1)
    start_uvicorn()
    threading.Timer(2.0, update_icon_status).start()


def restart_tunnel(icon: pystray.Icon, item: Item):
    """Restartuje pouze tunnel"""
    stop_cloudflared()
    time.sleep(1)
    start_cloudflared()
    threading.Timer(2.0, update_icon_status).start()


def open_local_web(icon: pystray.Icon, item: Item):
    """Otevře lokální webové rozhraní"""
    webbrowser.open(LOCAL_WEB_URL)


def open_production_web(icon: pystray.Icon, item: Item):
    """Otevře produkční webové rozhraní"""
    webbrowser.open(PRODUCTION_WEB_URL)


def open_local_docs(icon: pystray.Icon, item: Item):
    """Otevře lokální FastAPI dokumentaci"""
    webbrowser.open(LOCAL_DOCS_URL)


def open_production_docs(icon: pystray.Icon, item: Item):
    """Otevře produkční FastAPI dokumentaci"""
    webbrowser.open(PRODUCTION_DOCS_URL)


def open_health(icon: pystray.Icon, item: Item):
    """Otevře health endpoint"""
    webbrowser.open(LOCAL_HEALTH_URL)


def show_status(icon: pystray.Icon, item: Item):
    """Obnoví status"""
    update_icon_status()


def quit_app(icon: pystray.Icon, item: Item):
    """Ukončí aplikaci a zastaví procesy"""
    global status_running
    
    status_running = False
    stop_cloudflared()
    stop_uvicorn()
    icon.stop()


# --------------------------------------------------
# Menu
# --------------------------------------------------


def create_menu() -> tuple:
    """Vytvoří kontextové menu"""
    global server_status, tunnel_status
    
    # Aktualizovat status před vytvořením menu
    server_status = check_server_status()
    tunnel_status = check_tunnel_status()
    
    # Status text
    if server_status and tunnel_status:
        status_text = "🟢 Status: Online (Server + Tunnel)"
    elif server_status:
        status_text = "🟡 Status: Server běží, Tunnel offline"
    else:
        status_text = "🔴 Status: Offline"
    
    return (
        Item(
            status_text,
            lambda icon, item: None,
            enabled=False,
        ),
        pystray.Menu.SEPARATOR,
        Item("▶ Spustit TooZ Hub 2", start_hub),
        Item("🔄 Restartovat TooZ Hub 2", restart_hub),
        Item("⏹ Zastavit TooZ Hub 2", stop_hub),
        pystray.Menu.SEPARATOR,
        Item("🔄 Restart", pystray.Menu(
            Item("🔄 Restartovat Server", restart_server),
            Item("🔄 Restartovat Tunnel", restart_tunnel),
            Item("🔄 Restartovat Vše", restart_hub),
        )),
        pystray.Menu.SEPARATOR,
        Item("🌐 Web", pystray.Menu(
            Item("Lokální web", open_local_web),
            Item("Produkční web", open_production_web),
        )),
        Item("📚 Dokumentace", pystray.Menu(
            Item("Lokální /docs", open_local_docs),
            Item("Produkční /docs", open_production_docs),
        )),
        Item("❤️ Health Check", open_health),
        pystray.Menu.SEPARATOR,
        Item("🔄 Obnovit status", show_status),
        pystray.Menu.SEPARATOR,
        Item("❌ Ukončit ikonu", quit_app),
    )


# --------------------------------------------------
# Tray ikona
# --------------------------------------------------


def main():
    """Hlavní funkce"""
    global tray_icon, status_running
    
    # Vytvořit počáteční ikonu (offline)
    image = create_icon_image(is_online=False, is_warning=False)
    
    # Vytvořit menu
    menu = create_menu()
    
    # Vytvořit tray ikonu s názvem a popisem
    tray_icon = pystray.Icon(
        "TooZ Hub 2",
        image,
        "TooZ Hub 2 - Kontroluji stav...",
        menu
    )
    
    # Spustit status monitoring na pozadí
    status_thread = threading.Thread(target=status_monitor_loop, daemon=True)
    status_thread.start()
    
    # Aktualizovat ikonu hned po startu (po 2 sekundách)
    threading.Timer(2.0, update_icon_status).start()
    
    # Automatický start serveru a tunelu při spuštění tray aplikace
    print("Spouštím server a tunnel automaticky...")
    start_uvicorn()
    time.sleep(2)  # Počkat, až se server spustí
    start_cloudflared()
    threading.Timer(5.0, update_icon_status).start()  # Aktualizovat status po 5 sekundách
    
    # Spustit tray ikonu
    print("=" * 60)
    print("TooZ Hub 2 Tray aplikace spuštěna!")
    print("Ikona by se měla zobrazit v systémové liště (u hodin).")
    print("Pokud ikonu nevidíte, zkontrolujte skryté ikony (šipka ^ u hodin).")
    print("=" * 60)
    
    try:
        tray_icon.run()
    except KeyboardInterrupt:
        print("\nUkončuji aplikaci...")
        quit_app(tray_icon, None)
    except Exception as e:
        print(f"Chyba při spuštění tray ikony: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
