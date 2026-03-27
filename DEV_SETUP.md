# DEV_SETUP

## Požadovaná verze Pythonu
- Oficiální lokální interpreter je Python `3.12`.
- Důvod: CI workflow v `.github/workflows/*.yml` běží na `3.12` a lokální starý `.venv` byl rozbitý na cizí cestě s Pythonem 3.10.

## Bootstrap prostředí
```bash
cd source-mirror/app
brew install python@3.12
scripts/bootstrap_dev.sh
source .venv/bin/activate
```

## Instalace dependencies
```bash
.venv/bin/python -m pip install -r requirements-dev.txt
```

## Start backendu
```bash
scripts/run_backend.sh
```

Alternativa:
```bash
.venv/bin/python -m uvicorn src.server.main:app --host 127.0.0.1 --port 8000
```

## Migrace DB
```bash
scripts/migrate_database.py
```

Další Alembic příkazy:
```bash
scripts/migrate_database.py current
scripts/migrate_database.py history
scripts/migrate_database.py upgrade head
```

## Testy
Lokální izolovaný smoke:
```bash
scripts/run_tests.sh local
```

Integration testy proti běžícímu API:
```bash
scripts/run_backend.sh
scripts/run_tests.sh integration
```

## Schema smoke
```bash
scripts/schema_smoke.sh
```

## Nejběžnější chyby
- `Python 3.12 nebyl nalezen`
  - Na macOS nainstalujte `brew install python@3.12`.
- `ModuleNotFoundError`
  - Zkontrolujte, že používáte `.venv/bin/python` a ne systémový `/usr/bin/python3`.
- `FileExistsError` při bootstrapu `data`
  - Bylo opraveno v `src/core/config.py`; pokud zůstane rozbitý symlink `data`, ověřte jeho target.
- `Integration` testy padají na `127.0.0.1:8000`
  - Tyto testy vyžadují běžící backend a lokální `.env`.
- `alembic current` neukazuje revizi
  - Nad starou DB ještě nemusí být zapsaná `alembic_version`; spusťte `scripts/migrate_database.py upgrade head`.
