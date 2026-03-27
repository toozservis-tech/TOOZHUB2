# MIGRATION RUNBOOK

## 1. Instalace závislostí

```bash
pip install -r requirements.txt
```

## 2. Spuštění migrací

```bash
python scripts/migrate_database.py
```

Alternativně přímo:

```bash
python -m alembic upgrade head
```

## 3. Založení čisté DB

- Nastavte `DATABASE_URL` nebo `VEHICLE_DB_URL`.
- Pokud není nastaveno nic, aplikace použije `data/vehicles.db`.
- Pro čistou DB vytvořte prázdný soubor / nový PostgreSQL schema a spusťte migrace.

## 4. Ověření schématu

```bash
pytest tests/api/test_schema_migration_smoke.py
```

Nebo runtime kontrola:

```bash
curl -H "Authorization: Bearer <token>" http://127.0.0.1:8000/api/v1/system/capabilities
```

Všechny aktivní moduly musí vracet `available: true`.

## 5. Migrace existujících dat

- Baseline migrace automaticky doplní chybějící tabulky a sloupce.
- Legacy ownership z `vehicles.user_email` se backfilluje do `vehicle_ownerships`.
- Existující servisní záznamy zůstávají zachované; nové soft-delete/audit sloupce se doplní aditivně.

## 6. Provozní pravidla

- Nespouštět runtime `create_all` v request flow.
- Nepřidávat další jednorázové `ALTER TABLE` skripty mimo Alembic.
- Po každé změně modelu vytvořit novou migraci a ověřit `system/capabilities`.
