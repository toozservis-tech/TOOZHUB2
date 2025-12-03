"""
Dočasný file browser pro sdílení souborů projektu
Pouze pro kontrolu - dočasný přístup
"""
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from typing import Optional
import mimetypes
from datetime import datetime

router = APIRouter(prefix="/files", tags=["files"])

# Kořenový adresář projektu
PROJECT_ROOT = Path(__file__).parent.parent.parent

# Složky, které se mají skrýt
HIDDEN_PATHS = {
    ".git",
    "__pycache__",
    "venv",
    ".venv",
    "node_modules",
    ".env",
    "*.pyc",
    "*.db",
    "*.db.backup",
    ".pytest_cache",
    ".mypy_cache",
}

def is_hidden(path: Path) -> bool:
    """Zkontroluje, zda je cesta skrytá"""
    parts = path.parts
    for hidden in HIDDEN_PATHS:
        if hidden in parts or path.name.startswith('.') and path.name != '.env':
            # Ale .env soubory skrýt vždy
            if path.name == '.env' or '.env' in path.parts:
                return True
    return False

def get_file_size(path: Path) -> str:
    """Vrací velikost souboru v čitelném formátu"""
    try:
        size = path.stat().st_size
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"
    except:
        return "N/A"

@router.get("/", response_class=HTMLResponse)
async def file_browser_index(path: Optional[str] = None):
    """HTML rozhraní pro prohlížení souborů"""
    target_path = PROJECT_ROOT
    if path:
        # Bezpečnostní kontrola - zabránit directory traversal
        try:
            resolved = (PROJECT_ROOT / path).resolve()
            if not str(resolved).startswith(str(PROJECT_ROOT)):
                raise HTTPException(status_code=403, detail="Neplatná cesta")
            target_path = resolved
        except:
            raise HTTPException(status_code=404, detail="Cesta nenalezena")
    
    if not target_path.exists():
        raise HTTPException(status_code=404, detail="Cesta neexistuje")
    
    if target_path.is_file():
        # Pokud je to soubor, zobrazit obsah
        return await view_file(str(target_path.relative_to(PROJECT_ROOT)))
    
    # Zobrazit seznam souborů a složek
    items = []
    try:
        for item in sorted(target_path.iterdir()):
            if is_hidden(item):
                continue
            
            rel_path = item.relative_to(PROJECT_ROOT)
            items.append({
                "name": item.name,
                "path": str(rel_path).replace("\\", "/"),
                "is_dir": item.is_dir(),
                "size": get_file_size(item) if item.is_file() else "-",
                "modified": datetime.fromtimestamp(item.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S") if item.exists() else "N/A"
            })
    except PermissionError:
        raise HTTPException(status_code=403, detail="Přístup zamítnut")
    
    # Generovat HTML
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>File Browser - TOOZHUB2</title>
        <style>
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                margin: 0;
                padding: 20px;
                background: #f5f5f5;
            }}
            .container {{
                max-width: 1200px;
                margin: 0 auto;
                background: white;
                padding: 20px;
                border-radius: 8px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }}
            h1 {{
                color: #333;
                border-bottom: 3px solid #4CAF50;
                padding-bottom: 10px;
            }}
            .breadcrumb {{
                background: #f0f0f0;
                padding: 10px;
                border-radius: 4px;
                margin-bottom: 20px;
                font-size: 14px;
            }}
            .breadcrumb a {{
                color: #4CAF50;
                text-decoration: none;
            }}
            .breadcrumb a:hover {{
                text-decoration: underline;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                margin-top: 10px;
            }}
            th {{
                background: #4CAF50;
                color: white;
                padding: 12px;
                text-align: left;
                font-weight: 600;
            }}
            td {{
                padding: 10px;
                border-bottom: 1px solid #ddd;
            }}
            tr:hover {{
                background: #f9f9f9;
            }}
            .folder {{
                color: #FF9800;
                font-weight: bold;
            }}
            .file {{
                color: #2196F3;
            }}
            a {{
                color: inherit;
                text-decoration: none;
            }}
            a:hover {{
                text-decoration: underline;
            }}
            .actions {{
                display: inline-block;
                margin-left: 10px;
            }}
            .actions a {{
                color: #4CAF50;
                margin-right: 10px;
            }}
            .file-content {{
                background: #f9f9f9;
                padding: 20px;
                border-radius: 4px;
                overflow-x: auto;
                white-space: pre-wrap;
                font-family: 'Courier New', monospace;
                font-size: 13px;
                line-height: 1.5;
            }}
            .back-btn {{
                display: inline-block;
                background: #4CAF50;
                color: white;
                padding: 10px 20px;
                border-radius: 4px;
                text-decoration: none;
                margin-bottom: 20px;
            }}
            .back-btn:hover {{
                background: #45a049;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>📁 File Browser - TOOZHUB2 Project</h1>
            <div class="breadcrumb">
                <a href="/files/">🏠 Root</a>
                {generate_breadcrumb(path) if path else ""}
            </div>
            <table>
                <thead>
                    <tr>
                        <th>Název</th>
                        <th>Typ</th>
                        <th>Velikost</th>
                        <th>Upraveno</th>
                        <th>Akce</th>
                    </tr>
                </thead>
                <tbody>
    """
    
    for item in items:
        icon = "📁" if item["is_dir"] else "📄"
        item_class = "folder" if item["is_dir"] else "file"
        view_link = f'/files/?path={item["path"]}' if item["is_dir"] else f'/files/view?path={item["path"]}'
        download_link = f'/files/download?path={item["path"]}'
        
        html += f"""
                    <tr>
                        <td class="{item_class}">{icon} <a href="{view_link}">{item["name"]}</a></td>
                        <td>{'Složka' if item["is_dir"] else 'Soubor'}</td>
                        <td>{item["size"]}</td>
                        <td>{item["modified"]}</td>
                        <td>
                            <a href="{view_link}">👁️ Zobrazit</a>
                            {'<a href="' + download_link + '">⬇️ Stáhnout</a>' if not item["is_dir"] else ''}
                        </td>
                    </tr>
        """
    
    html += """
                </tbody>
            </table>
            <p style="margin-top: 20px; color: #666; font-size: 12px;">
                ⏰ Dočasný přístup - pouze pro kontrolu
            </p>
        </div>
    </body>
    </html>
    """
    
    return html

def generate_breadcrumb(path: str) -> str:
    """Generuje breadcrumb navigaci"""
    parts = path.split("/")
    breadcrumb = ""
    current_path = ""
    
    for part in parts:
        if not part:
            continue
        current_path += "/" + part if current_path else part
        breadcrumb += f' / <a href="/files/?path={current_path}">{part}</a>'
    
    return breadcrumb

@router.get("/view")
async def view_file(path: str):
    """Zobrazí obsah souboru"""
    try:
        file_path = (PROJECT_ROOT / path).resolve()
        
        # Bezpečnostní kontrola
        if not str(file_path).startswith(str(PROJECT_ROOT)):
            raise HTTPException(status_code=403, detail="Neplatná cesta")
        
        if not file_path.exists() or not file_path.is_file():
            raise HTTPException(status_code=404, detail="Soubor nenalezen")
        
        if is_hidden(file_path):
            raise HTTPException(status_code=403, detail="Přístup zamítnut")
        
        # Zkusit přečíst jako text
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            # Binární soubor
            return FileResponse(file_path, media_type='application/octet-stream')
        
        # HTML pro zobrazení obsahu
        parent_dir = str(file_path.parent.relative_to(PROJECT_ROOT)).replace("\\", "/")
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>{file_path.name} - File Browser</title>
            <style>
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    margin: 0;
                    padding: 20px;
                    background: #f5f5f5;
                }}
                .container {{
                    max-width: 1400px;
                    margin: 0 auto;
                    background: white;
                    padding: 20px;
                    border-radius: 8px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                }}
                h1 {{
                    color: #333;
                    border-bottom: 3px solid #4CAF50;
                    padding-bottom: 10px;
                }}
                .file-info {{
                    background: #f0f0f0;
                    padding: 10px;
                    border-radius: 4px;
                    margin-bottom: 20px;
                    font-size: 14px;
                }}
                .file-content {{
                    background: #1e1e1e;
                    color: #d4d4d4;
                    padding: 20px;
                    border-radius: 4px;
                    overflow-x: auto;
                    font-family: 'Courier New', monospace;
                    font-size: 13px;
                    line-height: 1.6;
                    white-space: pre;
                }}
                .back-btn {{
                    display: inline-block;
                    background: #4CAF50;
                    color: white;
                    padding: 10px 20px;
                    border-radius: 4px;
                    text-decoration: none;
                    margin-bottom: 20px;
                }}
                .back-btn:hover {{
                    background: #45a049;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <a href="/files/?path={parent_dir}" class="back-btn">← Zpět</a>
                <h1>📄 {file_path.name}</h1>
                <div class="file-info">
                    <strong>Cesta:</strong> {path}<br>
                    <strong>Velikost:</strong> {get_file_size(file_path)}
                </div>
                <div class="file-content">{escape_html(content[:100000])}</div>
                <p style="margin-top: 20px;">
                    <a href="/files/download?path={path}">⬇️ Stáhnout soubor</a>
                </p>
            </div>
        </body>
        </html>
        """
        
        return HTMLResponse(content=html)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chyba: {str(e)}")

def escape_html(text: str) -> str:
    """Escape HTML znaky"""
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#x27;"))

@router.get("/download")
async def download_file(path: str):
    """Stáhne soubor"""
    try:
        file_path = (PROJECT_ROOT / path).resolve()
        
        # Bezpečnostní kontrola
        if not str(file_path).startswith(str(PROJECT_ROOT)):
            raise HTTPException(status_code=403, detail="Neplatná cesta")
        
        if not file_path.exists() or not file_path.is_file():
            raise HTTPException(status_code=404, detail="Soubor nenalezen")
        
        if is_hidden(file_path):
            raise HTTPException(status_code=403, detail="Přístup zamítnut")
        
        media_type, _ = mimetypes.guess_type(str(file_path))
        return FileResponse(
            file_path,
            media_type=media_type or "application/octet-stream",
            filename=file_path.name
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chyba: {str(e)}")

@router.get("/api/list")
async def list_files_api(path: Optional[str] = None):
    """API endpoint pro seznam souborů (JSON)"""
    target_path = PROJECT_ROOT
    if path:
        try:
            resolved = (PROJECT_ROOT / path).resolve()
            if not str(resolved).startswith(str(PROJECT_ROOT)):
                raise HTTPException(status_code=403, detail="Neplatná cesta")
            target_path = resolved
        except:
            raise HTTPException(status_code=404, detail="Cesta nenalezena")
    
    if not target_path.exists():
        raise HTTPException(status_code=404, detail="Cesta neexistuje")
    
    if target_path.is_file():
        return {
            "type": "file",
            "path": str(target_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
            "name": target_path.name,
            "size": get_file_size(target_path),
            "modified": datetime.fromtimestamp(target_path.stat().st_mtime).isoformat()
        }
    
    items = []
    try:
        for item in sorted(target_path.iterdir()):
            if is_hidden(item):
                continue
            
            rel_path = item.relative_to(PROJECT_ROOT)
            items.append({
                "name": item.name,
                "path": str(rel_path).replace("\\", "/"),
                "is_dir": item.is_dir(),
                "size": get_file_size(item) if item.is_file() else None,
                "modified": datetime.fromtimestamp(item.stat().st_mtime).isoformat() if item.exists() else None
            })
    except PermissionError:
        raise HTTPException(status_code=403, detail="Přístup zamítnut")
    
    return {
        "type": "directory",
        "path": str(target_path.relative_to(PROJECT_ROOT)).replace("\\", "/") if path else "",
        "items": items
    }

