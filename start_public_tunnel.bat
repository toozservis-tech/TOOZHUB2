@echo off
title Cloudflare Tunnel - TooZ Hub 2 (Public)
color 0B
cls
echo ========================================
echo   CLOUDFLARE TUNNEL - TOOZ HUB 2
echo ========================================
echo.
echo Tunnel: tooz-hub2
echo UUID: a8451dbb-2ca2-4006-862b-09959b274eb4
echo Doména: hub.toozservis.cz
echo Backend: http://localhost:8000
echo.
echo Ujistete se, ze server bezi na portu 8000!
echo Spustte: start_public_server.bat
echo.
echo Pro zastaveni tunelu stisknete: Ctrl+C
echo.
echo ========================================
echo.
echo Startuji Cloudflare Tunnel...
echo.

cd /d "%~dp0"
cloudflared tunnel run tooz-hub2

echo.
echo.
echo Tunnel byl zastaven.
pause

