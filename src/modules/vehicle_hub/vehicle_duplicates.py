"""Reviewed, atomic vehicle consolidation. Originals and privacy boundaries survive."""
import hashlib
import json
import re
from collections import defaultdict
from datetime import date, datetime

from fastapi import HTTPException
from sqlalchemy import inspect, select
from . import models as m
from .vehicle_identity import normalize_vin
from .ownership import get_primary_vehicle_owner, lock_vehicle_access
from .vehicle_privacy import prepare_owner_change


def plate_key(value):
    return re.sub(r'[^A-Z0-9]', '', str(value or '').upper())


def snapshot(row):
    return {column.key: (value.isoformat() if isinstance(value, (date, datetime)) else value)
            for column in inspect(row).mapper.column_attrs for value in [getattr(row, column.key)]}


def references():
    # Include mapped extension modules too, but never guess foreign keys by column name.
    result = []
    for mapper in m.Base.registry.mappers:
        if mapper.class_ in (m.Vehicle, m.VehicleVINClaim):
            continue
        for column in mapper.columns:
            if any(fk.target_fullname == 'vehicles.id' for fk in column.foreign_keys):
                result.append((mapper.class_, column.key))
    return sorted(result, key=lambda item: (item[0].__tablename__, item[1]))


def vehicle_summary(db, row):
    owner = get_primary_vehicle_owner(db, row)
    return {'id': row.id, 'nickname': row.nickname, 'brand': row.brand, 'model': row.model,
            'vin': row.vin, 'plate': row.plate, 'owner_id': owner.id if owner else None,
            'owner_email': owner.email if owner else row.user_email,
            'record_count': db.query(m.ServiceRecord).filter_by(vehicle_id=row.id).count()}


def duplicate_report(db):
    groups = {'vin': defaultdict(list), 'plate': defaultdict(list)}
    rows = db.query(m.Vehicle).filter(m.Vehicle.merged_into_id.is_(None)).order_by(m.Vehicle.id).all()
    for row in rows:
        if key := normalize_vin(row.vin): groups['vin'][key].append(row)
        if key := plate_key(row.plate): groups['plate'][key].append(row)
    results = []
    for kind, values in groups.items():
        for key, vehicles in values.items():
            if len(vehicles) < 2: continue
            vins = {normalize_vin(row.vin) for row in vehicles if normalize_vin(row.vin)}
            results.append({'kind': kind, 'key': key, 'vehicles': [vehicle_summary(db, row) for row in vehicles],
                'merge_allowed': kind == 'vin' or not vins,
                'explanation': 'Stejný VIN — zkontrolujte vlastníka a zvolte hlavní profil.' if kind == 'vin'
                    else 'Shodná SPZ je pouze podnět ke kontrole. Rozdílné VIN nelze sloučit.'})
    return {'checked_vehicles': len(rows), 'groups': results, 'total': len(results)}


def merge_preview(db, source_id, target_id):
    if source_id == target_id: raise HTTPException(422, 'Vyberte dvě různá vozidla.')
    rows = {row.id: row for row in db.query(m.Vehicle).filter(m.Vehicle.id.in_([source_id, target_id])).all()}
    if set(rows) != {source_id, target_id}: raise HTTPException(404, 'Vozidlo nenalezeno nebo již bylo sjednoceno.')
    source, target = rows[source_id], rows[target_id]
    source_vin, target_vin = normalize_vin(source.vin), normalize_vin(target.vin)
    exact_vin = bool(source_vin and source_vin == target_vin)
    plate_only = not source_vin and not target_vin and plate_key(source.plate) and plate_key(source.plate) == plate_key(target.plate)
    if not (exact_vin or plate_only):
        raise HTTPException(409, 'Sloučit lze shodný VIN, nebo ručně potvrzenou shodnou SPZ u obou profilů bez VIN. Nejprve opravte identitu vozidla.')
    aliases = db.query(m.Vehicle).execution_options(include_merged_vehicles=True).filter(
        m.Vehicle.merged_into_id.in_([source_id, target_id])).order_by(m.Vehicle.id).all()
    counts, evidence = {}, {'source': snapshot(source), 'target': snapshot(target),
        'aliases': [snapshot(row) for row in aliases], 'references': {}}
    for model, key in references():
        entries = db.query(model).filter(getattr(model, key).in_([source_id, target_id])).order_by(*inspect(model).primary_key).all()
        name = model.__tablename__ + '.' + key
        evidence['references'][name] = [snapshot(row) for row in entries]
        counts[model.__tablename__] = sum(getattr(row, key) == source_id for row in entries)
    token = hashlib.sha256(json.dumps(evidence, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
    different_owner = vehicle_summary(db, source)['owner_id'] != vehicle_summary(db, target)['owner_id']
    return {'source': vehicle_summary(db, source), 'target': vehicle_summary(db, target), 'counts': counts,
            'preview_token': token, 'requires_identity_confirmation': not exact_vin,
            'different_owner': different_owner,
            'warnings': [
                'Hlavní profil i jeho vlastník zůstanou zachováni. Žádné e-maily se neodesílají.',
                'Původní profil a historie změn zůstanou v archivu administrátora.',
                'Soukromé doklady jiného vlastníka zůstanou chráněné; oprávnění servisů se automaticky nerozšiřují.'
            ]}


def merge_vehicles(db, *, source_id, target_id, preview_token, confirmed_identity, actor_id, reason):
    for identity in sorted([source_id, target_id]): lock_vehicle_access(db, identity)
    preview = merge_preview(db, source_id, target_id)
    if preview['preview_token'] != preview_token:
        raise HTTPException(409, 'Data se od náhledu změnila. Připravte nový náhled sjednocení.')
    if preview['requires_identity_confirmation'] and not confirmed_identity:
        raise HTTPException(422, 'Potvrďte, že jde o stejné vozidlo.')
    source, target = db.get(m.Vehicle, source_id), db.get(m.Vehicle, target_id)
    target_owner = get_primary_vehicle_owner(db, target)
    source_owner = get_primary_vehicle_owner(db, source)
    if not target_owner or not source_owner:
        raise HTTPException(409, 'Nejprve přiřaďte oběma vozidlům ověřeného vlastníka.')
    different_owner = source_owner.id != target_owner.id
    from .vehicle_privacy import attachment_keys
    for record in db.query(m.ServiceRecord).filter_by(vehicle_id=source_id):
        for key in attachment_keys(record.attachments):
            if db.get(m.VehicleAttachmentPrivacy, key) is None:
                db.add(m.VehicleAttachmentPrivacy(storage_key=key, vehicle_id=source_id,
                    owner_customer_id=source_owner.id, author_customer_id=record.created_by_service_customer_id or record.user_id))
    db.flush()
    original = snapshot(source)
    original_values = {key: getattr(source, key) for key in original}
    if different_owner:
        prepare_owner_change(db, source, target_owner.id)
        # The source profile itself is retained for the administrator, not copied to the buyer.
        for key, value in original_values.items():
            if key not in ('id', 'vin'): setattr(source, key, value)
    # Keep unique ownership/link/history rows in the archived profile when moving
    # would collide; original author identities, timestamps and evidence stay intact.
    retained = {m.VehicleOwnership, m.VehicleOwnershipArchive, m.VehicleORVScan, m.VehicleVINClaim,
                m.ServiceRecordAuditLog, m.ServiceVehicleLookupAudit}
    known = {(model.__tablename__, key) for model, key in references()}
    inspector = inspect(db.bind)
    for table in inspector.get_table_names():
        if table in ("vehicles", "vehicle_vin_claims"): continue
        for fk in inspector.get_foreign_keys(table):
            if fk.get("referred_table") == "vehicles" and any((table, key) not in known for key in fk["constrained_columns"]):
                raise HTTPException(409, "Sjednocení vyžaduje podporu dalších vazeb databáze. Žádná data nebyla změněna.")
    for model, key in references():
        entries = db.query(model).filter(getattr(model, key) == source_id).all()
        if model in retained: continue
        for row in entries:
            if model in (m.VehicleServiceLink, m.ServiceVehicleAccess, m.ServiceAccessRequest):
                # A duplicate profile never confers additional permissions on the main profile.
                if hasattr(row, 'status'): row.status = 'revoked'
                if hasattr(row, 'revoked_at'): row.revoked_at = datetime.utcnow()
                continue
            if model is m.VehicleTachometerHistoryEntry:
                match = db.query(model).filter_by(vehicle_id=target_id, check_date=row.check_date,
                    mileage_km=row.mileage_km, protocol_number=row.protocol_number).first()
                if match: continue  # Preserve the original evidence in the merge archive.
            if model is m.Reminder and different_owner: row.is_completed = True
            setattr(row, key, target_id)
            # User IDs and tenant IDs remain provenance; do not change the author to admin.
    for ownership in db.query(m.VehicleOwnership).filter_by(vehicle_id=source_id, is_active=True):
        ownership.is_active = False; ownership.is_primary = False
        ownership.revoked_at = ownership.owned_until = datetime.utcnow()
    for key in ('brand', 'model', 'year', 'engine', 'stk_valid_until', 'last_stk_mileage_km'):
        if getattr(target, key) is None and getattr(source, key) is not None: setattr(target, key, getattr(source, key))
    if source.current_mileage_km is not None:
        target.current_mileage_km = max(target.current_mileage_km or 0, source.current_mileage_km)
    source.merged_vin = source.vin; source.vin = None; source.merged_into_id = target_id
    # Flatten earlier merges. Their files still live at the original storage key,
    # which must resolve to the current main vehicle even after another merge.
    aliases = db.query(m.Vehicle).execution_options(include_merged_vehicles=True).filter_by(merged_into_id=source_id).all()
    for alias in aliases:
        alias.merged_into_id = target_id
    db.flush()
    # Recreate the claim if the migration had reserved this legacy VIN on the source row.
    if target.vin and db.bind.dialect.name == 'postgresql' and db.get(m.VehicleVINClaim, normalize_vin(target.vin)) is None:
        db.execute(m.Vehicle.__table__.update().where(m.Vehicle.id == target_id).values(vin=target.vin))
    audit = m.DeveloperActionAuditLog(developer_id=actor_id, developer_email=db.get(m.Customer, actor_id).email,
        action_type='vehicle.merge', target_resource=f'vehicle:{target_id}', result='success', status_code=200,
        parameters_json=json.dumps({'source_id': source_id, 'target_id': target_id, 'reason': reason,
            'counts': preview['counts'], 'preview_token': preview_token, 'affected_customer_ids': [source_owner.id, target_owner.id]}, ensure_ascii=False, default=str))
    db.add(audit); db.flush()
    return {'message': 'Vozidla byla sjednocena. Původní profil zůstává archivovaný.',
            'target_id': target_id, 'source_id': source_id, 'audit_id': audit.id}
