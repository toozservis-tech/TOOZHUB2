#!/usr/bin/env python3
"""Operator-only read-only capture. Credentials are paths, never command arguments.

No restore command is provided: a verified archive is not permission to revive
old accounts or replace a production database. See docs/CLOUD_RECOVERY.md.
"""
import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import dotenv_values
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from src.core.recovery_bundle import create_bundle, PrivateObjectReader, RecoveryError


def private_file(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
        raise RecoveryError('Credential file must be private to its owner')
    return path


def main():
    parser = argparse.ArgumentParser(description='Capture encrypted database and private objects without changing the server.')
    parser.add_argument('--database-url-file', required=True)
    parser.add_argument('--storage-env-file', required=True)
    parser.add_argument('--recipient-file', required=True, help='Public age recipient only; private recovery identity stays offline.')
    parser.add_argument('--schema', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--pg-dump', default='pg_dump')
    parser.add_argument('--age', default='age')
    args = parser.parse_args()
    os.umask(0o077)
    engine = reader = None
    try:
        destination = Path(args.output).absolute()
        report_path = destination.with_suffix(destination.suffix+'.report.json')
        if report_path.exists() or destination.exists(): raise RecoveryError('Recovery destination already exists')
        config = dotenv_values(private_file(args.storage_env_file), interpolate=False)
        url = make_url(private_file(args.database_url_file).read_text().strip()).set(drivername='postgresql+psycopg')
        recipient = Path(args.recipient_file).read_text().strip()
        engine = create_engine(url, hide_parameters=True, pool_pre_ping=True, connect_args={'connect_timeout': 15})
        reader = PrivateObjectReader(config.get('SUPABASE_URL', ''), config.get('SUPABASE_SECRET_KEY', ''),
                                     config.get('SUPABASE_STORAGE_BUCKET', 'toozhub-private'))
        report = create_bundle(destination, engine=engine, schema=args.schema, reader=reader,
                               recipient=recipient, pg_dump=args.pg_dump, age=args.age)
        # Keep a separately protected copy of this report away from the archive.
        with report_path.open('x') as target:
            json.dump(report, target, indent=2)
        print(json.dumps(report))  # Aggregate counts/digest only, never paths or identities.
    except Exception as error:
        print(json.dumps({'ok': False, 'error': str(error) if isinstance(error, RecoveryError) else
                          'Capture failed; inspect configuration privately. No complete backup was confirmed.'}))
        return 1
    finally:
        if reader: reader.close()
        if engine: engine.dispose()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
