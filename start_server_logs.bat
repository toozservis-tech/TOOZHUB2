@echo off
title TooZ Hub 2 - Server Logy
color 0A
cls
echo ========================================
echo   TOOZ HUB 2 - SERVER S LOGY
echo ========================================
echo.
echo Server bude spusten na: http://0.0.0.0:8000
echo (Pro Cloudflare Tunnel - produkce)
echo.
echo V tomto okne uvidite vsechny logy v realnem case:
echo   - [SERVER] - obecne logy serveru
echo   - [MDCR] - komunikace s MDCR API
echo   - [DECODER] - VIN dekodovani
echo   - [MERGE] - slucovani dat
echo.
echo Pro zastaveni serveru stisknete: Ctrl+C
echo.
echo ========================================
echo.
echo Startuji server...
echo.

cd /d "%~dp0"
python -m uvicorn src.server.main:app --host 0.0.0.0 --port 8000

echo.
echo.
echo Server byl zastaven.
pause


