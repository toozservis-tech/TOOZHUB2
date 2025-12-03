@echo off
REM Spuštění tray aplikace pro TooZ Hub 2 na pozadí (Windows)
REM Používá pythonw.exe - bez otevření konzole

REM Najít pythonw.exe automaticky
set PYTHONW=
if exist "C:\Python312\pythonw.exe" (
    set PYTHONW=C:\Python312\pythonw.exe
) else if exist "%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe" (
    set PYTHONW=%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe
) else if exist "%USERPROFILE%\AppData\Local\Programs\Python\Python312\pythonw.exe" (
    set PYTHONW=%USERPROFILE%\AppData\Local\Programs\Python\Python312\pythonw.exe
) else (
    REM Zkusit najít pythonw v PATH
    where pythonw.exe >nul 2>&1
    if %errorlevel% == 0 (
        set PYTHONW=pythonw.exe
    ) else (
        echo Chyba: pythonw.exe nebylo nalezeno!
        echo Instalujte Python nebo upravte cestu v tomto souboru.
        pause
        exit /b 1
    )
)

REM Získat cestu ke skriptu
set SCRIPT_DIR=%~dp0
set TRAY_SCRIPT=%SCRIPT_DIR%toozhub_tray_final.py

REM Spustit tray aplikaci na pozadí
start "" "%PYTHONW%" "%TRAY_SCRIPT%"

REM Ukončit bez čekání
exit

