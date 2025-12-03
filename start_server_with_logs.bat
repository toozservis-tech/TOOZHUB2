@echo off
REM Spustí server TooZ Hub 2 s viditelnými logy v terminálu

echo ========================================
echo SPUSTENI SERVERU TOOZ HUB 2 S LOGY
echo ========================================
echo.
echo Server bude spusten na: http://127.0.0.1:8000
echo Pro zastaveni stisknete Ctrl+C
echo.
echo ========================================
echo.

cd /d "%~dp0"
python -m uvicorn src.server.main:app --host 127.0.0.1 --port 8000

pause



