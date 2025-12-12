# scripts/windows/run_server.ps1
# Spuštění FastAPI serveru pro TOOZHUB2

param(
    [int]$Port = 8000
)

# Nastavit working directory na root projektu
$projectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $projectRoot

# Zkontrolovat, zda existuje venv
$pythonExe = "python"
if (Test-Path "venv\Scripts\python.exe") {
    $pythonExe = "venv\Scripts\python.exe"
}

# Spusť uvicorn v novém okně (minimalizovaně)
Start-Process $pythonExe -ArgumentList @(
    "-m", "uvicorn",
    "src.server.main:app",
    "--host", "127.0.0.1",
    "--port", "$Port"
) -WindowStyle Minimized

Write-Host "Server spuštěn na portu $Port"
Write-Host "Pro zastavení použijte Task Manager nebo: Get-Process python | Where-Object {$_.CommandLine -like '*uvicorn*'} | Stop-Process"

