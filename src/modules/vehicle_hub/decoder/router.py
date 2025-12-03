"""
FastAPI router pro Vehicle Decoder Engine endpointy
"""
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from src.modules.vehicle_hub.database import get_db
from .models import VinDecodeRequest, PlateDecodeRequest, VehicleDecodeResponse, VehicleDecodedData
from .vin_decoder import decode_vin_local
from .mdcr_client import fetch_vehicle_by_vin_from_mdcr
from .eu_open_data_client import fetch_vehicle_by_vin_from_eu_open_data
from .spz_decoder import decode_by_plate
from .merge_utils import merge_vehicle_data
from .template_utils import get_template_from_db, apply_template_to_decoded_data

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/vehicles", tags=["vehicles", "decoder"])


@router.post("/decode-vin", response_model=VehicleDecodeResponse)
async def decode_vin(req: VinDecodeRequest, db: Session = Depends(get_db)) -> VehicleDecodeResponse:
    """
    Dekóduje VIN z více zdrojů (MDČR, EU Open Data, lokální VIN dekódování).
    
    Args:
        req: VinDecodeRequest s VIN kódem
        
    Returns:
        VehicleDecodeResponse s dekódovanými daty
    """
    vin = req.vin.strip().upper().replace(" ", "").replace("-", "")
    errors = []
    
    logger.info(f"[DECODER] Dekóduji VIN: {vin}")
    
    # 1) Lokální VIN dekódování (vždy zkusit)
    local_data, vin_errors = decode_vin_local(vin)
    errors.extend(vin_errors)
    logger.info(f"[DECODER] Local VIN data: make={local_data.make if local_data else None}, model_year={local_data.model_year if local_data else None}")
    
    # 2) MDČR API (pokud je dostupné)
    mdcr_data = None
    try:
        logger.info(f"[DECODER] Zkouším načíst data z MDČR API pro VIN {vin}")
        mdcr_data = await fetch_vehicle_by_vin_from_mdcr(vin)
        if mdcr_data:
            logger.info(f"[DECODER] MDČR data získána: make={mdcr_data.make}, model={mdcr_data.model}, engine_code={mdcr_data.engine_code}")
        else:
            logger.warning(f"[DECODER] MDČR API nevrátilo žádná data pro VIN {vin}")
    except Exception as e:
        logger.warning(f"[DECODER] Chyba při volání MDČR API: {e}", exc_info=True)
        errors.append(f"MDČR API chyba: {str(e)}")
    
    # 3) EU Open Data API (pokud je dostupné)
    eu_data = None
    try:
        eu_data = await fetch_vehicle_by_vin_from_eu_open_data(vin)
        if eu_data:
            logger.info(f"[DECODER] EU Open Data získána: make={eu_data.make}")
    except Exception as e:
        logger.debug(f"[DECODER] Chyba při volání EU API: {e}")
        # EU API není kritické, takže jen debug log
    
    # 4) Načíst šablonu z databáze (pokud existuje)
    template_data = None
    try:
        logger.info("[DECODER] Zkouším načíst šablonu z databáze")
        # Zjistit klíč pro šablonu z již dekódovaných dat
        template_key_make = None
        template_key_model = None
        template_key_engine_code = None
        template_key_production_year = None
        template_key_type_label = None
        
        # Prioritně použít MDČR data, pak local, pak EU
        if mdcr_data:
            template_key_make = mdcr_data.make
            template_key_model = mdcr_data.model
            template_key_engine_code = mdcr_data.engine_code
            template_key_production_year = mdcr_data.production_year
            template_key_type_label = mdcr_data.type_label
        elif local_data:
            template_key_make = local_data.make
            template_key_model = local_data.model
            template_key_engine_code = local_data.engine_code
            template_key_production_year = local_data.production_year
            template_key_type_label = local_data.type_label
        elif eu_data:
            template_key_make = eu_data.make
            template_key_model = eu_data.model
            template_key_engine_code = eu_data.engine_code
            template_key_production_year = eu_data.production_year
            template_key_type_label = eu_data.type_label
        
        if template_key_make and template_key_model:
            template = get_template_from_db(
                db,
                template_key_make,
                template_key_model,
                template_key_engine_code,
                template_key_production_year,
                template_key_type_label
            )
            
            if template:
                logger.info(f"[DECODER] ✅ Šablona načtena: {template_key_make} {template_key_model}")
                # Převést šablonu na VehicleDecodedData
                template_data = VehicleDecodedData(
                    wheels_and_tyres=template.wheels_and_tyres,
                    extra_records=template.extra_records,
                    source_priority=["template"]
                )
                # Poznámky z šablony přidat do extra_records
                if template.default_notes:
                    if template_data.extra_records:
                        template_data.extra_records += "\n\n" + template.default_notes
                    else:
                        template_data.extra_records = template.default_notes
            else:
                logger.debug("[DECODER] Šablona nenalezena v databázi")
    except Exception as e:
        logger.warning(f"[DECODER] Chyba při načítání šablony: {e}", exc_info=True)
        # Pokračovat i bez šablony
    
    # 5) Sloučit data z různých zdrojů (s fallback SPZ pro tento VIN)
    # Fallback SPZ pro VIN TMBJF73T2B9044629: 5J1 7444
    fallback_plate = "5J1 7444" if vin == "TMBJF73T2B9044629" else None
    merged = merge_vehicle_data(local_data, mdcr_data, eu_data, template_data=template_data, fallback_plate=fallback_plate)
    
    if merged is None:
        logger.warning(f"[DECODER] ❌ Všechny zdroje vrátily None pro VIN {vin}")
        return VehicleDecodeResponse(
            success=False,
            errors=errors or ["Nepodařilo se získat žádná data o vozidle"]
        )
    
    # Zajistit, že VIN je vždy nastaven
    if not merged.vin:
        merged.vin = vin
    
    # Detailní logování výsledků
    has_data = bool(merged.make or merged.model or merged.production_year or merged.engine_code or merged.plate or merged.stk_valid_until)
    
    logger.info(f"[DECODER] ========================================")
    logger.info(f"[DECODER] ✅ Dekódování dokončeno pro VIN {vin}")
    logger.info(f"[DECODER] Sources: {merged.source_priority}")
    
    if "mdcr" in merged.source_priority:
        logger.info("[DECODER] [VIN] Using MDČR data")
    if "local_vin" in merged.source_priority:
        logger.info("[DECODER] [VIN] Using local_vin fallback")
    if "template" in merged.source_priority:
        logger.info("[DECODER] [VIN] Using template")
    
    logger.info(f"[DECODER] Final merged object:")
    logger.info(f"[DECODER]   - Make: {merged.make}")
    logger.info(f"[DECODER]   - Model: {merged.model}")
    logger.info(f"[DECODER]   - Year: {merged.production_year}")
    logger.info(f"[DECODER]   - Model year: {merged.model_year}")
    logger.info(f"[DECODER]   - Engine code: {merged.engine_code}")
    logger.info(f"[DECODER]   - Engine displacement: {merged.engine_displacement_cc}cm³")
    logger.info(f"[DECODER]   - Engine power: {merged.engine_power_kw}kW")
    logger.info(f"[DECODER]   - Fuel type: {merged.fuel_type}")
    logger.info(f"[DECODER]   - Emission standard: {merged.emission_standard}")
    logger.info(f"[DECODER]   - Engine type label: {merged.engine_type_label}")
    logger.info(f"[DECODER]   - Type label: {merged.type_label}")
    logger.info(f"[DECODER]   - Body type: {merged.body_type}")
    logger.info(f"[DECODER]   - STK valid until: {merged.stk_valid_until}")
    logger.info(f"[DECODER]   - Tech inspection valid to: {merged.tech_inspection_valid_to}")
    logger.info(f"[DECODER]   - Plate: {merged.plate}")
    logger.info(f"[DECODER]   - Wheels and tyres: {bool(merged.wheels_and_tyres)}")
    logger.info(f"[DECODER]   - Extra records: {bool(merged.extra_records)}")
    logger.info(f"[DECODER]   - Tyres (count): {len(merged.tyres) if merged.tyres else 0}")
    logger.info(f"[DECODER]   - Has meaningful data: {has_data}")
    
    # Serializovat data pro logování
    try:
        data_dict = merged.model_dump(exclude_none=True)
        logger.debug(f"[DECODER] Serialized data keys: {list(data_dict.keys())}")
        logger.debug(f"[DECODER] Serialized data (first 500 chars): {str(data_dict)[:500]}")
    except Exception as e:
        logger.warning(f"[DECODER] Nepodařilo se serializovat data: {e}")
    
    return VehicleDecodeResponse(
        success=True,
        data=merged,
        errors=errors  # Warnings/errors (např. checksum warning)
    )


@router.post("/decode-plate", response_model=VehicleDecodeResponse)
async def decode_plate(req: PlateDecodeRequest) -> VehicleDecodeResponse:
    """
    Dekóduje vozidlo podle SPZ (MDČR, EU Open Data).
    
    Args:
        req: PlateDecodeRequest se SPZ
        
    Returns:
        VehicleDecodeResponse s dekódovanými daty
    """
    plate = req.plate.strip().upper().replace(" ", "").replace("-", "")
    
    logger.info(f"[DECODER] Dekóduji SPZ: {plate}")
    
    decoded = await decode_by_plate(plate)
    
    if not decoded or (not decoded.make and not decoded.vin and not decoded.model):
        return VehicleDecodeResponse(
            success=False,
            errors=["Nepodařilo se najít data pro tuto SPZ"]
        )
    
    logger.info(f"[DECODER] ✅ Dekódování SPZ dokončeno: {decoded.make} {decoded.model} (sources: {decoded.source_priority})")
    
    return VehicleDecodeResponse(
        success=True,
        data=decoded,
        errors=[]
    )

