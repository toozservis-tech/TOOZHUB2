"""
Solo file server pro sdílení souborů z public_share
Nezávislý modul pouze pro file sharing - bez celého TooZ Hub 2 projektu
"""

import sys
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse

# Přidání kořenového adresáře projektu do Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Vytvoření FastAPI aplikace
app = FastAPI(title="TooZ FileShare", version="1.0.0")

# CORS middleware - veřejný přístup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Veřejný přístup
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Cesta k public_share složce v rootu projektu
public_path = project_root / "public_share"
public_path.mkdir(parents=True, exist_ok=True)


@app.get("/", response_class=HTMLResponse)
@app.get("/{path:path}", response_class=HTMLResponse)
def file_list(path: str = ""):
    """Zobrazí seznam souborů a složek v public_share nebo servíruje soubor"""
    # Normalizace cesty - odstranit koncové lomítko
    path_clean = path.strip("/") if path else ""

    # Rozdělení na části
    path_parts = [p for p in path_clean.split("/") if p and p != "." and p != ".."]
    target_path = public_path
    if path_parts:
        target_path = public_path / "/".join(path_parts)

    # Bezpečnostní kontrola - zabránit directory traversal
    try:
        target_path = target_path.resolve()
        if not str(target_path).startswith(str(public_path.resolve())):
            raise HTTPException(status_code=403, detail="Neplatná cesta")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=404, detail="Cesta nenalezena")

    if not target_path.exists():
        raise HTTPException(status_code=404, detail="Cesta neexistuje")

    # Pokud je to soubor, servíruj ho
    if target_path.is_file():
        return FileResponse(target_path)

    # Generování HTML seznamu pro složku
    items = []
    try:
        for item in sorted(target_path.iterdir()):
            if item.name.startswith("."):
                continue  # Skrýt skryté soubory

            rel_path = str(item.relative_to(public_path)).replace("\\", "/")
            size = ""
            if item.is_file():
                size_bytes = item.stat().st_size
                if size_bytes < 1024:
                    size = f"{size_bytes} B"
                elif size_bytes < 1024 * 1024:
                    size = f"{size_bytes / 1024:.1f} KB"
                else:
                    size = f"{size_bytes / (1024 * 1024):.1f} MB"

            items.append(
                {
                    "name": item.name,
                    "path": rel_path,
                    "is_dir": item.is_dir(),
                    "size": size,
                    "modified": datetime.fromtimestamp(item.stat().st_mtime).strftime(
                        "%Y-%m-%d %H:%M"
                    ),
                }
            )
    except PermissionError:
        raise HTTPException(status_code=403, detail="Přístup zamítnut")

    # Breadcrumb navigace
    breadcrumb = '<a href="/">🏠 Kořen</a>'
    current_breadcrumb_path = ""
    for part in path_parts:
        current_breadcrumb_path += "/" + part
        breadcrumb += f' / <a href="{current_breadcrumb_path}/">{part}</a>'

    # HTML šablona - CSS barvy v proměnných kvůli f-stringu
    color_primary = "#667eea"
    color_secondary = "#764ba2"

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Veřejné soubory - TooZ FileShare</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                background: linear-gradient(135deg, {color_primary} 0%, {color_secondary} 100%);
                min-height: 100vh;
                padding: 20px;
            }}
            .container {{
                max-width: 1200px;
                margin: 0 auto;
                background: white;
                border-radius: 12px;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                overflow: hidden;
            }}
            .header {{
                background: linear-gradient(135deg, {color_primary} 0%, {color_secondary} 100%);
                color: white;
                padding: 30px;
                text-align: center;
            }}
            .header h1 {{
                font-size: 2em;
                margin-bottom: 10px;
            }}
            .breadcrumb {{
                padding: 20px 30px;
                background: #f5f5f5;
                border-bottom: 1px solid #ddd;
                font-size: 14px;
            }}
            .breadcrumb a {{
                color: {color_primary};
                text-decoration: none;
            }}
            .breadcrumb a:hover {{
                text-decoration: underline;
            }}
            .file-list {{
                padding: 30px;
            }}
            .file-item {{
                display: flex;
                align-items: center;
                padding: 15px;
                border-bottom: 1px solid #eee;
                transition: background 0.2s;
            }}
            .file-item:hover {{
                background: #f9f9f9;
            }}
            .file-icon {{
                font-size: 24px;
                margin-right: 15px;
                width: 30px;
            }}
            .file-info {{
                flex: 1;
            }}
            .file-name {{
                font-weight: 500;
                color: #333;
                text-decoration: none;
                font-size: 16px;
            }}
            .file-name:hover {{
                color: {color_primary};
            }}
            .file-meta {{
                font-size: 12px;
                color: #666;
                margin-top: 5px;
            }}
            .file-size {{
                color: #999;
                font-size: 14px;
                margin-left: 15px;
            }}
            .empty {{
                text-align: center;
                padding: 60px 20px;
                color: #999;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>📁 Veřejné soubory</h1>
                <p>TooZ FileShare - Solo File Server</p>
            </div>
            <div class="breadcrumb">
                {breadcrumb}
            </div>
            <div class="file-list">
"""

    if not items:
        html += """
                <div class="empty">
                    <p>📭 Tato složka je prázdná</p>
                </div>
"""
    else:
        for item in items:
            icon = "📁" if item["is_dir"] else "📄"
            url = f'/{item["path"]}' if not item["is_dir"] else f'/{item["path"]}/'
            html += f"""
                <div class="file-item">
                    <div class="file-icon">{icon}</div>
                    <div class="file-info">
                        <a href="{url}" class="file-name">{item["name"]}</a>
                        <div class="file-meta">Upraveno: {item["modified"]}</div>
                    </div>
                    <div class="file-size">{item["size"]}</div>
                </div>
"""

    html += """
            </div>
        </div>
    </body>
    </html>
    """

    return HTMLResponse(content=html)


@app.get("/health")
def health():
    """Health check endpoint"""
    return {"status": "ok", "service": "TooZ FileShare"}
