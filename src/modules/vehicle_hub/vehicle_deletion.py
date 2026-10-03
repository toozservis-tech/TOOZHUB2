"""Explicit, reviewed vehicle deletion; caller owns the database transaction.

Preview is read-only. Confirmation binds to the complete current dependency graph.
Only incoming foreign keys are followed: owners, services and other vehicles stay.
Files are queued atomically, never removed before the database commit succeeds.
"""
import hashlib
import json
from collections import defaultdict

from fastapi import HTTPException
from sqlalchemy import and_, inspect, or_, select

from . import models as m
from src.core.file_erasure import enqueue_file_erasure, private_path


LABELS = {
    'service_records': 'Servisní záznamy', 'service_record_audit_logs': 'Historie úprav záznamů',
    'reservations': 'Rezervace', 'reminders': 'Připomínky', 'service_intakes': 'Příjmy do servisu',
    'vehicle_orv_scans': 'Doklady ORV', 'vehicle_tachometer_history_entries': 'Historie STK a kilometrů',
    'repair_photo_sessions': 'Fotodokumentace oprav', 'repair_evidence_photos': 'Fotografie oprav',
    'vehicle_ownership_archives': 'Archiv vlastnictví', 'vehicle_ownerships': 'Vlastnické vazby',
    'vehicle_service_links': 'Oprávnění servisů', 'service_vehicle_access': 'Dřívější oprávnění servisů',
    'service_access_requests': 'Žádosti servisů', 'service_vehicle_lookup_audit': 'Historie vyhledání vozidla',
    'service_document_ingestions': 'Nahrané servisní dokumenty', 'customer_commands': 'Úlohy vozidla',
    'vehicle_record_privacy': 'Ochrana záznamů', 'vehicle_repair_privacy': 'Ochrana fotodokumentace',
    'vehicle_attachment_privacy': 'Soukromé přílohy', 'vehicle_vin_claims': 'Identita VIN',
}
TECHNICAL = {'vehicle_ownerships', 'vehicle_vin_claims'}
ALLOWED = set(LABELS) | {'vehicles'}


def _condition(table, rows):
    return or_(*(and_(*(column == row[column.name] for column in table.primary_key)) for row in rows))


def _graph(db, vehicle_id, *, lock=False):
    connection = db.connection()
    inspector = inspect(connection)
    existing = set(inspector.get_table_names())
    tables = {name: table for name, table in m.Base.metadata.tables.items() if name in existing}
    edges = [(child, fk) for (_, child), fks in inspector.get_multi_foreign_keys().items()
             for fk in fks if fk.get('referred_table') in existing]
    root = tables['vehicles']
    query = select(root).where(root.c.id == vehicle_id, root.c.merged_into_id.is_(None))
    if lock: query = query.with_for_update()
    row = connection.execute(query).mappings().first()
    if row is None: raise HTTPException(404, 'Vozidlo nenalezeno nebo již bylo sjednoceno.')
    collected = defaultdict(dict)
    collected['vehicles'][(vehicle_id,)] = dict(row)
    changed = True
    while changed:
        changed = False
        for child, fk in edges:
            parents = collected.get(fk['referred_table'])
            if not parents: continue
            # Unmapped relationships are never silently skipped or cascaded.
            if child not in tables or child not in ALLOWED:
                from sqlalchemy import MetaData, Table
                table = tables[child] if child in tables else Table(child, MetaData(), autoload_with=connection)
            else: table = tables[child]
            pairs = list(zip(fk['constrained_columns'], fk['referred_columns']))
            condition = or_(*(and_(*(table.c[a] == parent[b] for a, b in pairs)) for parent in parents.values()))
            query = select(table).where(condition)
            if lock: query = query.with_for_update()
            rows = connection.execute(query).mappings().all()
            if rows and (child not in ALLOWED or not table.primary_key.columns):
                raise HTTPException(409, 'Odstranění vyžaduje podporu dalších vazeb databáze. Žádná data se nezměnila.')
            for row in rows:
                identity = tuple(row[column.name] for column in table.primary_key)
                if identity not in collected[child]:
                    collected[child][identity] = dict(row); changed = True
    values = {name: sorted(rows.values(), key=lambda row: tuple(str(row[column.name]) for column in tables[name].primary_key))
              for name, rows in collected.items() if rows}
    vehicle_ids = {row['id'] for row in values['vehicles']}
    record_ids = {row['id'] for row in values.get('service_records', [])}
    session_ids = {row['id'] for row in values.get('repair_photo_sessions', [])}
    rebindings = []
    # Legacy record history can have an inconsistent secondary vehicle_id.
    # Its service_record_id determines which record the history actually belongs
    # to. Keep another vehicle's history and correct only this secondary link.
    histories = []
    for history in values.get('service_record_audit_logs', []):
        if history['service_record_id'] in record_ids:
            histories.append(history); continue
        query = select(tables['service_records']).where(tables['service_records'].c.id == history['service_record_id'])
        if lock: query = query.with_for_update()
        record = connection.execute(query).mappings().first()
        if record is None and history['vehicle_id'] in vehicle_ids:
            # Imported history may outlive its deleted record. Its remaining
            # vehicle link is explicit; include it in the reviewed removal.
            histories.append(history); continue
        if record is None or record['vehicle_id'] in vehicle_ids:
            raise HTTPException(409, 'Původní záznam historie nelze ověřit. Data zůstala zachována.')
        rebindings.append({'history': history, 'record': dict(record), 'vehicle_id': record['vehicle_id']})
    if histories: values['service_record_audit_logs'] = histories
    else: values.pop('service_record_audit_logs', None)
    for name, rows in values.items():
        for row in rows:
            if name != 'service_record_audit_logs' and row.get('vehicle_id') is not None and row['vehicle_id'] not in vehicle_ids:
                raise HTTPException(409, 'Navázaný údaj patří jinému vozidlu. Nejprve opravte jeho přiřazení; data zůstala zachována.')
            if name == 'vehicle_record_privacy' and row['record_id'] not in record_ids:
                raise HTTPException(409, 'Archiv chrání záznam jiného vozidla. Data zůstala zachována.')
            if name == 'vehicle_repair_privacy' and row['session_id'] not in session_ids:
                raise HTTPException(409, 'Archiv chrání fotografie jiného vozidla. Data zůstala zachována.')
    # Delete children before their FK parents; all merged aliases are removed in
    # the same vehicle statement, so their self-reference remains consistent.
    remaining = set(values); order = []
    while remaining:
        parents = {fk['referred_table'] for child, fk in edges
                   if child in remaining and fk['referred_table'] in remaining and child != fk['referred_table']}
        ready = sorted(remaining - parents)
        if not ready: raise HTTPException(409, 'Navázaná data obsahují kruhovou vazbu. Data zůstala zachována.')
        order.extend(ready); remaining -= set(ready)
    return tables, values, order, rebindings


def _file_inventory(values, *, strict=True):
    files = set()
    def file(directory, raw):
        if not raw: return
        try:
            path = private_path(directory, raw)
            if path: files.add((directory, str(raw)))
        except ValueError:
            if strict: raise HTTPException(409, 'Soubor má neplatnou cestu. Žádná data se neodstranila.')
    def attachments(raw):
        try:
            items = json.loads(raw) if isinstance(raw, str) else (raw or [])
            if not isinstance(items, list): raise ValueError()
            for item in items:
                if isinstance(item, dict): file('service_record_attachments', item.get('storage_key') or item.get('path'))
        except (ValueError, TypeError):
            if strict: raise HTTPException(409, 'Seznam příloh nelze bezpečně ověřit. Žádná data se neodstranila.')
    def profile(row):
        file('vehicle_photos', row.get('photo_path'))
        for side in ('front', 'back'): file('vehicle_orv_scans', row.get('orv_'+side+'_image_path'))
    for row in values.get('vehicles', []): profile(row)
    for row in values.get('vehicle_ownership_archives', []):
        try: profile(json.loads(row['profile_json']))
        except (ValueError, TypeError, AttributeError):
            if strict: raise HTTPException(409, 'Archiv souborů nelze bezpečně ověřit. Data zůstala zachována.')
    for row in values.get('vehicle_orv_scans', []):
        for side in ('front', 'back'): file('vehicle_orv_scans', row.get(side+'_image_path'))
    for row in values.get('service_records', []): attachments(row.get('attachments'))
    for row in values.get('vehicle_attachment_privacy', []): file('service_record_attachments', row['storage_key'])
    for row in values.get('repair_evidence_photos', []): file('private_repair_photos', row['file_path'])
    for row in values.get('service_document_ingestions', []): file('service_workspace_docs', row['stored_file_path'])
    for row in values.get('service_record_audit_logs', []):
        for key in ('previous_snapshot_json', 'new_snapshot_json'):
            try:
                snapshot = json.loads(row.get(key) or '{}')
                if isinstance(snapshot, dict): attachments(snapshot.get('attachments'))
            except (ValueError, TypeError):
                if strict: raise HTTPException(409, 'Historii příloh nelze bezpečně ověřit. Data zůstala zachována.')
    return files


def _plan(db, vehicle_id, *, lock=False):
    if lock:
        tables, values, _, rebindings = _graph(db, vehicle_id)
        ids = {row['id'] for row in values['vehicles']} | {row['vehicle_id'] for row in rebindings}
        # Common parent locks precede child locks, in a stable order. This also
        # protects retained history from concurrent edits on its actual vehicle.
        db.connection().execute(select(tables['vehicles'].c.id).where(tables['vehicles'].c.id.in_(ids))
            .order_by(tables['vehicles'].c.id).with_for_update()).all()
    tables, values, order, rebindings = _graph(db, vehicle_id, lock=lock)
    files = _file_inventory(values)
    # Exact paths can have surviving references on another vehicle. Never erase
    # that vehicle's document merely because one of its copies is being deleted.
    outside = {}
    for name in ('vehicles', 'vehicle_ownership_archives', 'vehicle_orv_scans', 'service_records',
                 'vehicle_attachment_privacy', 'repair_evidence_photos', 'service_document_ingestions', 'service_record_audit_logs'):
        if name not in tables: continue
        query = select(tables[name])
        if name in values: query = query.where(~_condition(tables[name], values[name]))
        outside[name] = [dict(row) for row in db.connection().execute(query).mappings()]
    normalize = lambda pair: str(private_path(*pair))
    shared = {normalize(pair) for pair in _file_inventory(outside, strict=False)}
    deletable_files = sorted({normalize(pair): pair for pair in files if normalize(pair) not in shared}.values())
    material = {'rows': values, 'files': deletable_files, 'retained_history': rebindings}
    token = hashlib.sha256(json.dumps(material, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()
    root = next(row for row in values['vehicles'] if row['id'] == vehicle_id)
    items = [{'key': name, 'label': LABELS[name], 'count': len(rows)} for name, rows in sorted(values.items())
             if name not in TECHNICAL and name != 'vehicles']
    if len(values['vehicles']) > 1:
        items.append({'key': 'merged_profiles', 'label': 'Sjednocené původní profily', 'count': len(values['vehicles']) - 1})
    count = sum(item['count'] for item in items)
    preview = {'vehicle_id': vehicle_id, 'title': root.get('nickname') or 'Vozidlo', 'plate': root.get('plate'),
               'items': items, 'related_count': count, 'files_count': len(deletable_files),
               'preserved_shared_files': len({normalize(pair) for pair in files} & shared),
               'preserved_history_count': len(rebindings),
               'requires_related_confirmation': bool(count or files), 'preview_token': token}
    return preview, tables, values, order, deletable_files, rebindings


def deletion_preview(db, vehicle_id):
    return _plan(db, vehicle_id)[0]


def delete_reviewed_vehicle(db, vehicle_id, *, preview_token, delete_related, actor, reason, request_ip=None):
    if not preview_token:
        raise HTTPException(422, 'Nejprve otevřete přehled údajů k odstranění.')
    preview, tables, values, order, files, rebindings = _plan(db, vehicle_id, lock=True)
    if preview['preview_token'] != preview_token:
        raise HTTPException(409, 'Údaje se od potvrzení změnily. Obnovte přehled odstranění a znovu jej potvrďte.')
    if preview['requires_related_confirmation'] and not delete_related:
        raise HTTPException(409, 'Potvrďte, zda chcete s vozidlem odstranit i všechny navázané záznamy.')
    affected = set()
    for name, rows in values.items():
        for column in tables[name].columns:
            if any(fk.target_fullname == 'customers.id' for fk in column.foreign_keys):
                affected.update(row[column.name] for row in rows if row[column.name] is not None)
    emails = {row['user_email'] for row in values['vehicles'] if row.get('user_email')}
    affected.update(db.connection().execute(select(m.Customer.id).where(m.Customer.email.in_(emails))).scalars())
    for binding in rebindings:
        affected.update(value for value in [binding['history'].get('changed_by_user_id'), binding['record'].get('user_id'),
            binding['record'].get('created_by_service_customer_id')] if value is not None)
    archive = {name: [{key: value for key, value in row.items()
                       if not any(word in key.lower() for word in ('password', 'secret', 'token'))} for row in rows]
               for name, rows in values.items() if name not in TECHNICAL}
    for directory, path in files: enqueue_file_erasure(db, directory, path)
    for binding in rebindings:
        db.execute(tables['service_record_audit_logs'].update().where(tables['service_record_audit_logs'].c.id == binding['history']['id'])
            .values(vehicle_id=binding['vehicle_id']))
    for name in order:
        db.execute(tables[name].delete().where(_condition(tables[name], values[name])))
    db.add(m.DeveloperActionAuditLog(developer_id=actor.id, developer_email=actor.email,
        action_type='vehicle.delete', target_resource=f'vehicles:{vehicle_id}', result='success', status_code=200,
        request_ip=request_ip, parameters_json=json.dumps({'reason': reason, 'delete_related': bool(delete_related),
            'preview': preview, 'deleted_rows': archive, 'retained_history': rebindings, 'affected_customer_ids': sorted(affected)}, default=str, ensure_ascii=False)))
    return {'message': 'Vozidlo a potvrzené navázané záznamy byly odstraněny.', 'deleted_related': preview['related_count'],
            'files_pending': len(files), 'preserved_shared_files': preview['preserved_shared_files'], 'soft_deleted': False}
