@echo off
title Cloudflare Tunnel - TooZ Hub 2
color 0B
cls
echo ========================================
echo   CLOUDFLARE TUNNEL - TOOZ HUB 2
echo ========================================
echo.
echo Tunnel: tooz-hub2
echo Doména: hub.toozservis.cz
echo Backend: http://localhost:8000
echo.
echo Ujistete se, ze server bezi na portu 8000!
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

