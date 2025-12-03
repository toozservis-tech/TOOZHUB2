@echo off
title TooZ Hub 2 - Public Server (0.0.0.0:8000)
color 0A
cls
echo ========================================
echo   TOOZ HUB 2 - PUBLIC SERVER
echo ========================================
echo.
echo Server bude spusten na: http://0.0.0.0:8000
echo.
echo Tento server je pripraven pro Cloudflare Tunnel.
echo URL: https://hub.toozservis.cz
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

