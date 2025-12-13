# Testy pro TooZ Hub 2

## Instalace závislostí

### Python závislosti (pro API testy)

```powershell
# V root projektu
pip install -r requirements.txt
```

Nebo pouze testovací závislosti:

```powershell
pip install pytest pytest-asyncio
```

### Node.js závislosti (pro E2E testy)

```powershell
cd tests/e2e
npm install
npx playwright install chromium
```

## Spuštění testů

### Automatické spuštění (doporučeno)

```powershell
# V root projektu
.\scripts\qa_run.ps1
```

### Manuální spuštění

**API testy:**

```powershell
# V root projektu
python -m pytest tests/api -v
```

**E2E testy:**

```powershell
cd tests/e2e
npx playwright test
```

**E2E testy (headed mode - viditelné okno):**

```powershell
cd tests/e2e
npx playwright test --headed
```

**E2E testy (UI mode - interaktivní):**

```powershell
cd tests/e2e
npx playwright test --ui
```

## Struktura testů

```text
tests/
├── api/              # API testy (pytest)
│   ├── conftest.py   # Pytest konfigurace a fixtures
│   ├── test_health.py
│   ├── test_auth.py
│   └── test_vehicles.py
└── e2e/              # E2E testy (Playwright)
    ├── package.json
    ├── playwright.config.ts
    ├── auth.spec.ts
    ├── vehicles.spec.ts
    ├── navigation.spec.ts
    └── ...
```

## Požadavky

- Python 3.10+
- Node.js 16+
- Backend server běžící na `http://127.0.0.1:8000` (nebo použijte `qa_run.ps1`)

## Výstupy

Výstupy testů jsou uloženy v `artifacts/qa/`:

- `pytest-report.txt` - Textový výstup API testů
- `pytest-report.xml` - JUnit XML pro CI/CD
- `playwright-report/` - HTML report E2E testů
- `playwright-output.txt` - Textový výstup E2E testů
