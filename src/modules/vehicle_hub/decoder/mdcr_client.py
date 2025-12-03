"""
MDČR API klient pro získání dat o vozidlech
Používá dataovozidlech.cz API (oficiální databáze vozidel MDČR)
"""
import logging
from typing import Optional
from datetime import datetime
import httpx
import urllib.parse
import re

from .models import VehicleDecodedData

logger = logging.getLogger(__name__)


def parse_date_like(date_value) -> Optional[str]:
    """
    Parsuje datum z různých formátů (ISO, český formát, timestamp, atd.)
    a vrátí ho jako ISO formát string (YYYY-MM-DD).
    
    Args:
        date_value: Datum v různých formátech (str, int, datetime, atd.)
        
    Returns:
        ISO formát string (YYYY-MM-DD) nebo None
    """
    if date_value is None:
        return None
    
    try:
        # Pokud je to už datetime objekt
        if isinstance(date_value, datetime):
            return date_value.strftime("%Y-%m-%d")
        
        # Převést na string
        date_str = str(date_value).strip()
        
        if not date_str:
            return None
        
        # ISO formát YYYY-MM-DD
        if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
            return date_str
        
        # ISO formát s časem YYYY-MM-DDTHH:MM:SS
        iso_match = re.match(r'^(\d{4}-\d{2}-\d{2})', date_str)
        if iso_match:
            return iso_match.group(1)
        
        # Český formát DD.MM.YYYY
        czech_match = re.match(r'^(\d{1,2})\.(\d{1,2})\.(\d{4})$', date_str)
        if czech_match:
            day, month, year = czech_match.groups()
            return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        
        # Formát DD/MM/YYYY
        slash_match = re.match(r'^(\d{1,2})/(\d{1,2})/(\d{4})$', date_str)
        if slash_match:
            day, month, year = slash_match.groups()
            return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        
        # Pouze rok (YYYY) - vrátit jako YYYY-01-01
        if re.match(r'^\d{4}$', date_str):
            return f"{date_str}-01-01"
        
        # Zkusit parsovat jako ISO datetime
        try:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return dt.strftime("%Y-%m-%d")
        except (ValueError, AttributeError):
            pass
        
        # Zkusit parsovat pomocí strptime s různými formáty
        formats = [
            "%Y-%m-%d",
            "%Y-%m-%d %H:%M:%S",
            "%d.%m.%Y",
            "%d/%m/%Y",
            "%Y/%m/%d",
        ]
        
        for fmt in formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                return dt.strftime("%Y-%m-%d")
            except (ValueError, AttributeError):
                continue
        
        logger.warning(f"[MDČR] Nepodařilo se parsovat datum: {date_value}")
        # Vrátit jako string, pokud se nepodařilo parsovat
        return date_str
        
    except Exception as e:
        logger.warning(f"[MDČR] Chyba při parsování data {date_value}: {e}")
        return str(date_value) if date_value else None

# Načíst config proměnné - podporujeme více variant názvů
import os
try:
    from src.core.config import DATAOVO_API_KEY, DATAOVO_API_BASE_URL, MDCR_API_TOKEN, MDCR_API_BASE_URL
    # Použít nové názvy s fallbackem na staré
    DATAOVOZIDLECH_API_KEY = DATAOVO_API_KEY or MDCR_API_TOKEN or os.getenv("DATAOVO_API_KEY") or os.getenv("DATAOVOZIDLECH_API_KEY", "")
    DATAOVOZIDLECH_API_URL = DATAOVO_API_BASE_URL or MDCR_API_BASE_URL or os.getenv("DATAOVO_API_BASE_URL") or os.getenv("DATAOVOZIDLECH_API_URL", "https://api.dataovozidlech.cz/api/vehicletechnicaldata/v2")
except ImportError:
    DATAOVOZIDLECH_API_KEY = os.getenv("DATAOVO_API_KEY") or os.getenv("DATAOVOZIDLECH_API_KEY") or os.getenv("MDCR_API_TOKEN", "")
    DATAOVOZIDLECH_API_URL = os.getenv("DATAOVO_API_BASE_URL") or os.getenv("DATAOVOZIDLECH_API_URL") or os.getenv("MDCR_API_BASE_URL", "https://api.dataovozidlech.cz/api/vehicletechnicaldata/v2")


async def fetch_vehicle_by_vin_from_mdcr(vin: str) -> Optional[VehicleDecodedData]:
    """
    Zavolá MDČR API dle VIN a převede JSON odpověď na VehicleDecodedData.
    
    Args:
        vin: VIN kód vozidla (17 znaků, normalizovaný)
        
    Returns:
        VehicleDecodedData nebo None při chybě/nenalezení
    """
    # Normalizace VIN
    normalized_vin = vin.strip().upper().replace(" ", "").replace("-", "")
    
    # Kontrola konfigurace
    if not DATAOVOZIDLECH_API_KEY or not DATAOVOZIDLECH_API_URL:
        logger.warning(f"[MDČR] API není nakonfigurováno (BASE_URL nebo TOKEN chybí), vracím None pro VIN {normalized_vin}")
        return None
    
    # Detailní logování konfigurace
    logger.info(f"[MDČR] ========================================")
    logger.info(f"[MDČR] Dekóduji VIN: {normalized_vin}")
    logger.info(f"[MDČR] API URL: {DATAOVOZIDLECH_API_URL}")
    logger.info(f"[MDČR] Token nastaven: {bool(DATAOVOZIDLECH_API_KEY)}")
    logger.info(f"[MDČR] Token délka: {len(DATAOVOZIDLECH_API_KEY) if DATAOVOZIDLECH_API_KEY else 0} znaků")
    
    try:
        url = f"{DATAOVOZIDLECH_API_URL}?vin={urllib.parse.quote(normalized_vin)}"
        headers = {
            "api_key": DATAOVOZIDLECH_API_KEY
        }
        
        logger.info(f"[MDČR] Request URL: {url}")
        logger.debug(f"[MDČR] Request headers: api_key={'***' + DATAOVOZIDLECH_API_KEY[-4:] if DATAOVOZIDLECH_API_KEY else 'N/A'}")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers)
        
        logger.info(f"[MDČR] Response status: {response.status_code}")
        logger.info(f"[MDČR] Response headers: {dict(response.headers)}")
        
        if response.status_code != 200:
            logger.warning(f"[MDČR] ❌ API vrátilo status {response.status_code}")
            logger.warning(f"[MDČR] Response text (prvních 500 znaků): {response.text[:500]}")
            return None
        
        api_response = response.json()
        
        # Detailní logování odpovědi
        response_str = str(api_response)
        logger.info(f"[MDČR] ✅ API odpověď přijata")
        logger.info(f"[MDČR] Response body délka: {len(response_str)} znaků")
        logger.info(f"[MDČR] Response body (prvních 500 znaků): {response_str[:500]}")
        logger.debug(f"[MDČR] Celá response: {response_str}")
        
        # API vrací strukturu: {"Status": 1, "Data": {...}} nebo {"Success": true/false, "Data": {...}}
        # Kontrola obou variant pro kompatibilitu
        status = api_response.get("Status")
        success = api_response.get("Success")
        
        # Pokud Success: false, vrátit None
        if success is False:
            logger.warning(f"[MDČR] ❌ API vrátilo Success: false")
            logger.warning(f"[MDČR] Response (prvních 500 znaků): {response_str[:500]}")
            return None
        
        # Pokud Status není 1 nebo Success není True, a není Data
        if (status != 1 and success is not True) or "Data" not in api_response:
            logger.warning(f"[MDČR] ❌ API vrátilo chybu")
            logger.warning(f"[MDČR] Status: {status}, Success: {success}")
            logger.warning(f"[MDČR] Má 'Data' klíč: {'Data' in api_response}")
            logger.warning(f"[MDČR] Response (prvních 500 znaků): {response_str[:500]}")
            return None
        
        data = api_response["Data"]
        logger.info(f"[MDČR] ✅ Data extrahována z API")
        logger.info(f"[MDČR] Data typ: {type(data)}")
        if isinstance(data, dict):
            logger.info(f"[MDČR] Data klíče ({len(data.keys())}): {list(data.keys())[:30]}")
        else:
            logger.warning(f"[MDČR] Data není dict, ale {type(data)}")
        
        # Mapování API dat na VehicleDecodedData
        result = VehicleDecodedData(
            vin=normalized_vin,
            source_priority=["mdcr"]
        )
        
        # Helper funkce pro bezpečné získání hodnoty s fallbacky
        def get_value(*keys, default=None):
            """Zkusí najít hodnotu v data pomocí více variant klíčů"""
            for key in keys:
                if data.get(key) is not None:
                    return data[key]
            return default
        
        # Tovární značka (make/brand)
        make_val = (
            get_value("TovarniZnacka", "tovarniZnacka", "Tovarni_Znacka", "brand", "Brand", "make", "Make")
            or result.make
        )
        if make_val:
            result.make = str(make_val)
            result.manufacturer = str(make_val)
        
        # Obchodní označení / model
        model_val = (
            get_value("ObchodniOznaceni", "obchodniOznaceni", "Obchodni_Oznaceni", "model", "Model")
            or result.model
        )
        if model_val:
            result.model = str(model_val)
        
        # Typ vozidla (body type)
        body_type_val = (
            get_value("Typ", "typ", "BodyType", "bodyType", "vehicle_type", "VehicleType")
            or result.body_type
        )
        if body_type_val:
            result.body_type = str(body_type_val)
        
        # Rok výroby - zkusit více zdrojů
        year_val = None
        # 1) Zkusit přímo RokVyroby
        year_val = get_value("RokVyroby", "rokVyroby", "Rok_Vyroby", "year", "Year", "production_year", "ProductionYear")
        
        # 2) Pokud není, zkusit extrahovat z DatumPrvniRegistrace
        if not year_val and data.get("DatumPrvniRegistrace"):
            try:
                date_str = str(data["DatumPrvniRegistrace"])
                if len(date_str) >= 4:
                    year_val = date_str[:4]
            except (ValueError, TypeError):
                pass
        
        # 3) Převést na int a validovat
        if year_val is not None:
            try:
                year_int = int(str(year_val))
                if 1900 <= year_int <= 2100:
                    result.production_year = year_int
                    if not result.model_year:
                        result.model_year = year_int
                else:
                    logger.warning(f"[MDČR] Nepodařilo se převést rok {year_val} na validní rok (1900-2100)")
            except (ValueError, TypeError) as e:
                logger.warning(f"[MDČR] Nepodařilo se převést rok {year_val} na int: {e}")
        
        # Datum první registrace
        reg_date = get_value("DatumPrvniRegistrace", "datumPrvniRegistrace", "Datum_Prvni_Registrace", 
                            "first_registration_date", "FirstRegistrationDate")
        if reg_date:
            result.first_registration_date = str(reg_date)
        
        # SPZ / registrační značka
        plate_val = (
            get_value("RegistracniZnacka", "registracniZnacka", "Registracni_Znacka", 
                     "plate", "Plate", "registration_plate", "RegistrationPlate")
            or result.plate
        )
        if plate_val:
            result.plate = str(plate_val).strip().upper()
        
        # Typ motoru / kód motoru
        engine_code_val = (
            get_value("MotorTyp", "motorTyp", "Motor_Typ", "KodMotoru", "kodMotoru", "Kod_Motoru",
                     "engine_code", "EngineCode", "motorCode", "MotorCode")
            or result.engine_code
        )
        if engine_code_val:
            result.engine_code = str(engine_code_val)
        
        # Max. výkon [kW]
        power_val = get_value("MotorMaxVykon", "motorMaxVykon", "Motor_Max_Vykon", 
                             "MaxVykonKw", "maxVykonKw", "Max_Vykon_Kw",
                             "VykonKw", "vykonKw", "Vykon_Kw",
                             "engine_power_kw", "EnginePowerKw", "powerKw", "PowerKw")
        if power_val is not None:
            try:
                if isinstance(power_val, (int, float)):
                    result.engine_power_kw = int(power_val)
                elif isinstance(power_val, str):
                    import re
                    numbers = re.findall(r'\d+', power_val)
                    if numbers:
                        result.engine_power_kw = int(numbers[0])
                    else:
                        logger.warning(f"[MDČR] Nepodařilo se extrahovat výkon z '{power_val}'")
            except (ValueError, TypeError) as e:
                logger.warning(f"[MDČR] Nepodařilo se převést výkon {power_val} na int: {e}")
        
        # Objem motoru [cm³]
        displacement_val = get_value("MotorZdvihObjem", "motorZdvihObjem", "Motor_Zdvih_Objem",
                                    "DisplacementCc", "displacementCc", "Displacement_Cc",
                                    "engine_displacement_cc", "EngineDisplacementCc")
        if displacement_val is not None:
            try:
                if isinstance(displacement_val, (int, float)):
                    result.engine_displacement_cc = int(displacement_val)
                elif isinstance(displacement_val, str):
                    import re
                    numbers = re.findall(r'\d+', displacement_val)
                    if numbers:
                        result.engine_displacement_cc = int(numbers[0])
                    else:
                        logger.warning(f"[MDČR] Nepodařilo se extrahovat objem z '{displacement_val}'")
            except (ValueError, TypeError) as e:
                logger.warning(f"[MDČR] Nepodařilo se převést objem {displacement_val} na int: {e}")
        
        # Palivo / druh paliva
        fuel_val = get_value("Palivo", "palivo", "DruhPaliva", "druhPaliva", "Druh_Paliva",
                            "fuel_type", "FuelType", "fuel", "Fuel")
        if fuel_val:
            fuel = str(fuel_val).lower()
            # Normalizace názvu paliva
            fuel_mapping = {
                "benzín": "petrol",
                "benzin": "petrol",
                "petrol": "petrol",
                "nafta": "diesel",
                "diesel": "diesel",
                "lpg": "lpg",
                "cng": "cng",
                "elektřina": "electric",
                "electric": "electric",
                "hybrid": "hybrid",
            }
            result.fuel_type = fuel_mapping.get(fuel, fuel)
        
        # Emisní norma / třída
        emission_val = (
            get_value("EmisniUroven", "emisniUroven", "Emisni_Uroven",
                     "EmisniTrida", "emisniTrida", "Emisni_Trida",
                     "EmissionStandard", "emissionStandard", "emission_standard", "Emission_Standard")
            or result.emission_standard
        )
        if emission_val:
            result.emission_standard = str(emission_val)
        
        # Hmotnosti
        # Provozní hmotnost / pohotovostní
        curb_weight_val = get_value("HmotnostProvozni", "hmotnostProvozni", "Hmotnost_Provozni",
                                   "PohotovostniHmotnost", "pohotovostniHmotnost", "Pohotovostni_Hmotnost",
                                   "curb_weight_kg", "CurbWeightKg", "curbWeight")
        if curb_weight_val is not None:
            try:
                if isinstance(curb_weight_val, (int, float)):
                    result.curb_weight_kg = int(curb_weight_val)
                elif isinstance(curb_weight_val, str):
                    import re
                    numbers = re.findall(r'\d+', curb_weight_val)
                    if numbers:
                        result.curb_weight_kg = int(numbers[0])
            except (ValueError, TypeError) as e:
                logger.warning(f"[MDČR] Nepodařilo se převést pohotovostní hmotnost {curb_weight_val} na int: {e}")
        
        # Celková hmotnost / max. přípustná
        gross_weight_val = get_value("HmotnostCelkova", "hmotnostCelkova", "Hmotnost_Celkova",
                                    "MaxPripustnaHmotnost", "maxPripustnaHmotnost", "Max_Pripustna_Hmotnost",
                                    "gross_weight_kg", "GrossWeightKg", "grossWeight")
        if gross_weight_val is not None:
            try:
                if isinstance(gross_weight_val, (int, float)):
                    result.gross_weight_kg = int(gross_weight_val)
                elif isinstance(gross_weight_val, str):
                    import re
                    numbers = re.findall(r'\d+', gross_weight_val)
                    if numbers:
                        result.gross_weight_kg = int(numbers[0])
            except (ValueError, TypeError) as e:
                logger.warning(f"[MDČR] Nepodařilo se převést celkovou hmotnost {gross_weight_val} na int: {e}")
        
        # Počet míst k sezení
        seats_val = get_value("PocetMistKSezeni", "pocetMistKSezeni", "Pocet_Mist_K_Sezeni",
                             "seats", "Seats", "numSeats", "NumSeats")
        if seats_val is not None:
            try:
                if isinstance(seats_val, (int, str)):
                    result.seats = int(seats_val)
            except (ValueError, TypeError) as e:
                logger.warning(f"[MDČR] Nepodařilo se převést počet míst {seats_val} na int: {e}")
        
        # STK platnost do / technická prohlídka
        stk_date = (
            get_value("PlatnostSTKDo", "platnostSTKDo", "Platnost_STK_Do",
                     "STKPlatnostDo", "stkPlatnostDo", "STK_Platnost_Do",
                     "TechnickaProhlidkaDo", "technickaProhlidkaDo", "Technicka_Prohlidka_Do",
                     "PravidelnaTechnickaProhlidkaDo", "pravidelnaTechnickaProhlidkaDo",
                     "stk_valid_until", "StkValidUntil", "inspection_date", "InspectionDate")
            or result.stk_valid_until
        )
        if stk_date:
            # Parsovat datum do ISO formátu
            parsed_date = parse_date_like(stk_date)
            if parsed_date:
                result.stk_valid_until = parsed_date
                result.tech_inspection_valid_to = parsed_date  # Alias pro nové pole
                logger.info(f"[MDČR] STK platnost do: {result.stk_valid_until}")
            else:
                # Fallback na string pokud se nepodařilo parsovat
                result.stk_valid_until = str(stk_date)
                result.tech_inspection_valid_to = str(stk_date)
                logger.debug(f"[MDČR] STK platnost do (neparsováno): {result.stk_valid_until}")
        
        # Typ vozidla - sestavit type_label z Typ, Varianta, Verze
        type_parts = []
        typ_val = get_value("Typ", "typ", "BodyType", "bodyType", "vehicle_type", "VehicleType")
        varianta_val = get_value("Varianta", "varianta", "Variant", "variant")
        verze_val = get_value("Verze", "verze", "Version", "version")
        
        if typ_val:
            type_parts.append(str(typ_val))
        if varianta_val:
            type_parts.append(str(varianta_val))
        if verze_val:
            type_parts.append(str(verze_val))
        
        if type_parts:
            result.type_label = " / ".join(type_parts)
            # Pokud nemáme body_type, použijeme type_label
            if not result.body_type:
                result.body_type = type_parts[0]
        
        # Typ motoru jako text - sestavit z objem, palivo, výkon
        engine_parts = []
        if result.engine_displacement_cc:
            # Převést na litry (např. 2000 cm³ → 2.0)
            liters = result.engine_displacement_cc / 1000.0
            engine_parts.append(f"{liters:.1f}".rstrip('0').rstrip('.'))
        
        # Přidat palivo
        if result.fuel_type:
            fuel_text = result.fuel_type.lower()
            fuel_mapping = {
                "diesel": "TDI",
                "petrol": "TSI",
                "benzín": "TSI",
                "benzin": "TSI",
                "nafta": "TDI",
            }
            engine_parts.append(fuel_mapping.get(fuel_text, fuel_text.upper()))
        
        # Přidat výkon
        if result.engine_power_kw:
            engine_parts.append(f"{result.engine_power_kw} kW")
        
        if engine_parts:
            result.engine_type_label = " ".join(engine_parts)
        
        # Pneumatiky (NapravyPneuRafky) - extrahovat rozměry
        tyres_raw_val = get_value("NapravyPneuRafky", "napravyPneuRafky", "Napravy_Pneu_Rafky",
                                  "tyres_raw", "TyresRaw", "pneumatiky", "Pneumatiky")
        if tyres_raw_val:
            result.tyres_raw = str(tyres_raw_val)
            logger.debug(f"[MDČR] Pneumatiky (surový text): {result.tyres_raw[:200]}")
            
            # Extrahovat rozměry pneumatik z textu
            import re
            tyres = []
            tyre_patterns = [
                r'(\d{3}/\d{2}\s*R\s*\d{2,3}\s*\d{2,3}[A-Z]?)',  # 205/55 R 16 90V
                r'(\d{3}/\d{2}\s*R\s*\d{2,3}[A-Z]?)',            # 205/55 R16 90V
                r'(\d{3}/\d{2}\s*R\d{2,3})',                     # 205/55R16
                r'(\d{3}x\d{2}x\d{2,3})',                        # 205x55x16
                r'(T\s*\d{3}/\d{2}\s*R\s*\d{2,3})',             # T 125/85 R 16
            ]
            
            for pattern in tyre_patterns:
                matches = re.finditer(pattern, result.tyres_raw, re.IGNORECASE)
                for match in matches:
                    tyre = match.group(1).strip()
                    tyre = re.sub(r'\s+', ' ', tyre)
                    tyre = re.sub(r'(\d{2})\s*([rR])\s*(\d)', r'\1 \2\3', tyre)
                    tyre = re.sub(r'([rR])', 'R', tyre, count=1)
                    if tyre and len(tyre) >= 7 and re.search(r'\d{3}/\d{2}', tyre):
                        if tyre not in tyres:
                            tyres.append(tyre)
                            logger.debug(f"[MDČR] Nalezena pneumatika: {tyre}")
            
            if tyres:
                result.tyres = sorted(list(set(tyres)))
                logger.info(f"[MDČR] Extrahováno {len(result.tyres)} rozměrů pneumatik: {', '.join(result.tyres[:3])}...")
        
        # Kola a pneumatiky - naformátovat z tyres nebo tyres_raw (PO extrakci)
        if result.tyres and len(result.tyres) > 0:
            result.wheels_and_tyres = "\n".join(result.tyres)
        elif result.tyres_raw:
            result.wheels_and_tyres = result.tyres_raw
        
        # Vytvořit extra_records s dalšími záznamy
        extra_records_parts = []
        if result.emission_standard:
            extra_records_parts.append(f"Emisní norma: {result.emission_standard}")
        if result.curb_weight_kg:
            extra_records_parts.append(f"Pohotovostní hmotnost: {result.curb_weight_kg} kg")
        if result.gross_weight_kg:
            extra_records_parts.append(f"Celková hmotnost: {result.gross_weight_kg} kg")
        if result.seats:
            extra_records_parts.append(f"Počet míst: {result.seats}")
        if result.body_type:
            extra_records_parts.append(f"Druh vozidla: {result.body_type}")
        if result.first_registration_date:
            extra_records_parts.append(f"Datum první registrace: {result.first_registration_date}")
        
        if extra_records_parts:
            result.extra_records = "\n".join(extra_records_parts)
            logger.debug(f"[MDČR] Vytvořeny extra_records: {len(extra_records_parts)} položek")
        
        # Detailní logování všech extrahovaných hodnot
        extracted_fields = []
        if result.make: extracted_fields.append(f"značka={result.make}")
        if result.model: extracted_fields.append(f"model={result.model}")
        if result.production_year: extracted_fields.append(f"rok={result.production_year}")
        if result.engine_code: extracted_fields.append(f"motor_kód={result.engine_code}")
        if result.engine_displacement_cc: extracted_fields.append(f"objem={result.engine_displacement_cc}cm³")
        if result.engine_power_kw: extracted_fields.append(f"výkon={result.engine_power_kw}kW")
        if result.stk_valid_until: extracted_fields.append(f"STK={result.stk_valid_until}")
        if result.type_label: extracted_fields.append(f"type_label={result.type_label}")
        if result.engine_type_label: extracted_fields.append(f"engine_type_label={result.engine_type_label}")
        if result.tyres: extracted_fields.append(f"pneumatiky={len(result.tyres)}")
        if result.wheels_and_tyres: extracted_fields.append(f"wheels_and_tyres=yes")
        if result.plate: extracted_fields.append(f"SPZ={result.plate}")
        
        logger.info(f"[MDČR] ✅ Úspěšně dekódováno: {result.make} {result.model} ({result.production_year}) | {', '.join(extracted_fields)}")
        logger.info(f"[MDČR] Kompletní data: make={result.make}, model={result.model}, year={result.production_year}, engine_code={result.engine_code}, power={result.engine_power_kw}kW, type_label={result.type_label}, engine_type_label={result.engine_type_label}")
        return result
        
    except httpx.RequestError as e:
        logger.error(f"[MDČR] Chyba při volání API: {e}")
        return None
    except Exception as e:
        logger.error(f"[MDČR] Neočekávaná chyba: {e}", exc_info=True)
        return None


async def fetch_vehicle_by_plate_from_mdcr(plate: str) -> Optional[VehicleDecodedData]:
    """
    Zavolá MDČR API dle SPZ a převede JSON odpověď na VehicleDecodedData.
    
    Args:
        plate: SPZ (normalizovaná - uppercase, bez mezer)
        
    Returns:
        VehicleDecodedData nebo None při chybě/nenalezení
    """
    # Normalizace SPZ
    normalized_plate = plate.strip().upper().replace(" ", "").replace("-", "")
    
    # Kontrola konfigurace
    if not DATAOVOZIDLECH_API_KEY or not DATAOVOZIDLECH_API_URL:
        logger.warning(f"[MDČR] API není nakonfigurováno (BASE_URL nebo TOKEN chybí), vracím None pro SPZ {normalized_plate}")
        return None
    
    logger.info(f"[MDČR] Volám API pro SPZ {normalized_plate} na {DATAOVOZIDLECH_API_URL}, token nastaven: {bool(DATAOVOZIDLECH_API_KEY)}")
    
    try:
        url = f"{DATAOVOZIDLECH_API_URL}?plate={urllib.parse.quote(normalized_plate)}"
        headers = {
            "api_key": DATAOVOZIDLECH_API_KEY
        }
        
        logger.debug(f"[MDČR] Request URL: {url}")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers)
        
        logger.info(f"[MDČR] Response status {response.status_code} pro SPZ {normalized_plate}")
        
        if response.status_code != 200:
            logger.warning(f"[MDČR] API vrátilo status {response.status_code}: {response.text[:500]}")
            return None
        
        api_response = response.json()
        logger.debug(f"[MDČR] ✅ API odpověď přijata, response body (první 1000 znaků): {str(api_response)[:1000]}")
        
        # API vrací strukturu: {"Status": 1, "Data": {...}}
        if api_response.get("Status") != 1 or "Data" not in api_response:
            logger.warning(f"[MDČR] API vrátilo chybu: Status={api_response.get('Status', 'Unknown')}, response: {str(api_response)[:500]}")
            return None
        
        data = api_response["Data"]
        logger.debug(f"[MDČR] Data extrahována z API, klíče: {list(data.keys())[:20] if isinstance(data, dict) else 'N/A'}")
        
        # Použít stejné mapování jako u VIN - vytvořit base result s plate
        result = VehicleDecodedData(
            plate=normalized_plate,
            source_priority=["mdcr"]
        )
        
        # Helper funkce pro bezpečné získání hodnoty s fallbacky
        def get_value(*keys, default=None):
            """Zkusí najít hodnotu v data pomocí více variant klíčů"""
            for key in keys:
                if data.get(key) is not None:
                    return data[key]
            return default
        
        # VIN z API
        vin_val = get_value("VIN", "vin")
        if vin_val:
            result.vin = str(vin_val).strip().upper()
        
        # Použít stejné mapování jako u VIN (zkopírováno z fetch_vehicle_by_vin_from_mdcr)
        # Tovární značka
        make_val = (
            get_value("TovarniZnacka", "tovarniZnacka", "Tovarni_Znacka", "brand", "Brand", "make", "Make")
            or result.make
        )
        if make_val:
            result.make = str(make_val)
            result.manufacturer = str(make_val)
        
        # Model
        model_val = (
            get_value("ObchodniOznaceni", "obchodniOznaceni", "Obchodni_Oznaceni", "model", "Model")
            or result.model
        )
        if model_val:
            result.model = str(model_val)
        
        # Typ vozidla
        body_type_val = (
            get_value("Typ", "typ", "BodyType", "bodyType", "vehicle_type", "VehicleType")
            or result.body_type
        )
        if body_type_val:
            result.body_type = str(body_type_val)
        
        # Rok výroby
        year_val = get_value("RokVyroby", "rokVyroby", "Rok_Vyroby", "year", "Year", "production_year", "ProductionYear")
        if not year_val and data.get("DatumPrvniRegistrace"):
            try:
                date_str = str(data["DatumPrvniRegistrace"])
                if len(date_str) >= 4:
                    year_val = date_str[:4]
            except (ValueError, TypeError):
                pass
        
        if year_val is not None:
            try:
                year_int = int(str(year_val))
                if 1900 <= year_int <= 2100:
                    result.production_year = year_int
                    if not result.model_year:
                        result.model_year = year_int
            except (ValueError, TypeError) as e:
                logger.warning(f"[MDČR] Nepodařilo se převést rok {year_val} na int: {e}")
        
        # Datum první registrace
        reg_date = get_value("DatumPrvniRegistrace", "datumPrvniRegistrace", "Datum_Prvni_Registrace", 
                            "first_registration_date", "FirstRegistrationDate")
        if reg_date:
            result.first_registration_date = str(reg_date)
        
        # SPZ
        plate_val = (
            get_value("RegistracniZnacka", "registracniZnacka", "Registracni_Znacka", 
                     "plate", "Plate", "registration_plate", "RegistrationPlate")
            or result.plate
        )
        if plate_val:
            result.plate = str(plate_val).strip().upper()
        
        # Zbytek mapování (stejné jako u VIN)
        # Typ motoru
        engine_code_val = (
            get_value("MotorTyp", "motorTyp", "Motor_Typ", "KodMotoru", "kodMotoru", "Kod_Motoru",
                     "engine_code", "EngineCode", "motorCode", "MotorCode")
            or result.engine_code
        )
        if engine_code_val:
            result.engine_code = str(engine_code_val)
        
        # Max. výkon [kW]
        power_val = get_value("MotorMaxVykon", "motorMaxVykon", "Motor_Max_Vykon", 
                             "MaxVykonKw", "maxVykonKw", "Max_Vykon_Kw",
                             "VykonKw", "vykonKw", "Vykon_Kw",
                             "engine_power_kw", "EnginePowerKw", "powerKw", "PowerKw")
        if power_val is not None:
            try:
                if isinstance(power_val, (int, float)):
                    result.engine_power_kw = int(power_val)
                elif isinstance(power_val, str):
                    import re
                    numbers = re.findall(r'\d+', power_val)
                    if numbers:
                        result.engine_power_kw = int(numbers[0])
            except (ValueError, TypeError) as e:
                logger.warning(f"[MDČR] Nepodařilo se převést výkon {power_val} na int: {e}")
        
        # Objem motoru
        displacement_val = get_value("MotorZdvihObjem", "motorZdvihObjem", "Motor_Zdvih_Objem",
                                    "DisplacementCc", "displacementCc", "Displacement_Cc",
                                    "engine_displacement_cc", "EngineDisplacementCc")
        if displacement_val is not None:
            try:
                if isinstance(displacement_val, (int, float)):
                    result.engine_displacement_cc = int(displacement_val)
                elif isinstance(displacement_val, str):
                    import re
                    numbers = re.findall(r'\d+', displacement_val)
                    if numbers:
                        result.engine_displacement_cc = int(numbers[0])
            except (ValueError, TypeError) as e:
                logger.warning(f"[MDČR] Nepodařilo se převést objem {displacement_val} na int: {e}")
        
        # Palivo
        fuel_val = get_value("Palivo", "palivo", "DruhPaliva", "druhPaliva", "Druh_Paliva",
                            "fuel_type", "FuelType", "fuel", "Fuel")
        if fuel_val:
            fuel = str(fuel_val).lower()
            fuel_mapping = {
                "benzín": "petrol", "benzin": "petrol", "petrol": "petrol",
                "nafta": "diesel", "diesel": "diesel",
                "lpg": "lpg", "cng": "cng",
                "elektřina": "electric", "electric": "electric",
                "hybrid": "hybrid",
            }
            result.fuel_type = fuel_mapping.get(fuel, fuel)
        
        # Emisní norma
        emission_val = (
            get_value("EmisniUroven", "emisniUroven", "Emisni_Uroven",
                     "EmisniTrida", "emisniTrida", "Emisni_Trida",
                     "EmissionStandard", "emissionStandard", "emission_standard", "Emission_Standard")
            or result.emission_standard
        )
        if emission_val:
            result.emission_standard = str(emission_val)
        
        # Hmotnosti
        curb_weight_val = get_value("HmotnostProvozni", "hmotnostProvozni", "Hmotnost_Provozni",
                                   "PohotovostniHmotnost", "pohotovostniHmotnost", "Pohotovostni_Hmotnost",
                                   "curb_weight_kg", "CurbWeightKg", "curbWeight")
        if curb_weight_val is not None:
            try:
                if isinstance(curb_weight_val, (int, float)):
                    result.curb_weight_kg = int(curb_weight_val)
                elif isinstance(curb_weight_val, str):
                    import re
                    numbers = re.findall(r'\d+', curb_weight_val)
                    if numbers:
                        result.curb_weight_kg = int(numbers[0])
            except (ValueError, TypeError) as e:
                logger.warning(f"[MDČR] Nepodařilo se převést pohotovostní hmotnost {curb_weight_val} na int: {e}")
        
        gross_weight_val = get_value("HmotnostCelkova", "hmotnostCelkova", "Hmotnost_Celkova",
                                    "MaxPripustnaHmotnost", "maxPripustnaHmotnost", "Max_Pripustna_Hmotnost",
                                    "gross_weight_kg", "GrossWeightKg", "grossWeight")
        if gross_weight_val is not None:
            try:
                if isinstance(gross_weight_val, (int, float)):
                    result.gross_weight_kg = int(gross_weight_val)
                elif isinstance(gross_weight_val, str):
                    import re
                    numbers = re.findall(r'\d+', gross_weight_val)
                    if numbers:
                        result.gross_weight_kg = int(numbers[0])
            except (ValueError, TypeError) as e:
                logger.warning(f"[MDČR] Nepodařilo se převést celkovou hmotnost {gross_weight_val} na int: {e}")
        
        # Počet míst
        seats_val = get_value("PocetMistKSezeni", "pocetMistKSezeni", "Pocet_Mist_K_Sezeni",
                             "seats", "Seats", "numSeats", "NumSeats")
        if seats_val is not None:
            try:
                if isinstance(seats_val, (int, str)):
                    result.seats = int(seats_val)
            except (ValueError, TypeError) as e:
                logger.warning(f"[MDČR] Nepodařilo se převést počet míst {seats_val} na int: {e}")
        
        # STK platnost
        stk_date = (
            get_value("PlatnostSTKDo", "platnostSTKDo", "Platnost_STK_Do",
                     "STKPlatnostDo", "stkPlatnostDo", "STK_Platnost_Do",
                     "TechnickaProhlidkaDo", "technickaProhlidkaDo", "Technicka_Prohlidka_Do",
                     "PravidelnaTechnickaProhlidkaDo", "pravidelnaTechnickaProhlidkaDo",
                     "stk_valid_until", "StkValidUntil", "inspection_date", "InspectionDate")
            or result.stk_valid_until
        )
        if stk_date:
            result.stk_valid_until = str(stk_date)
            logger.debug(f"[MDČR] STK platnost do: {result.stk_valid_until}")
        
        # Pneumatiky (NapravyPneuRafky) - extrahovat rozměry (stejné jako u VIN)
        tyres_raw_val = get_value("NapravyPneuRafky", "napravyPneuRafky", "Napravy_Pneu_Rafky",
                                  "tyres_raw", "TyresRaw", "pneumatiky", "Pneumatiky")
        if tyres_raw_val:
            result.tyres_raw = str(tyres_raw_val)
            logger.debug(f"[MDČR] Pneumatiky (surový text): {result.tyres_raw[:200]}")
            
            import re
            tyres = []
            tyre_patterns = [
                r'(\d{3}/\d{2}\s*R\s*\d{2,3}\s*\d{2,3}[A-Z]?)',  # 205/55 R 16 90V
                r'(\d{3}/\d{2}\s*R\s*\d{2,3}[A-Z]?)',            # 205/55 R16 90V
                r'(\d{3}/\d{2}\s*R\d{2,3})',                     # 205/55R16
                r'(\d{3}x\d{2}x\d{2,3})',                        # 205x55x16
                r'(T\s*\d{3}/\d{2}\s*R\s*\d{2,3})',             # T 125/85 R 16
            ]
            
            for pattern in tyre_patterns:
                matches = re.finditer(pattern, result.tyres_raw, re.IGNORECASE)
                for match in matches:
                    tyre = match.group(1).strip()
                    tyre = re.sub(r'\s+', ' ', tyre)
                    tyre = re.sub(r'(\d{2})\s*([rR])\s*(\d)', r'\1 \2\3', tyre)
                    tyre = re.sub(r'([rR])', 'R', tyre, count=1)
                    if tyre and len(tyre) >= 7 and re.search(r'\d{3}/\d{2}', tyre):
                        if tyre not in tyres:
                            tyres.append(tyre)
            
            if tyres:
                result.tyres = sorted(list(set(tyres)))
                logger.info(f"[MDČR] Extrahováno {len(result.tyres)} rozměrů pneumatik")
        
        # Detailní logování všech extrahovaných hodnot
        extracted_fields = []
        if result.make: extracted_fields.append(f"značka={result.make}")
        if result.model: extracted_fields.append(f"model={result.model}")
        if result.production_year: extracted_fields.append(f"rok={result.production_year}")
        if result.engine_code: extracted_fields.append(f"motor_kód={result.engine_code}")
        if result.engine_displacement_cc: extracted_fields.append(f"objem={result.engine_displacement_cc}cm³")
        if result.engine_power_kw: extracted_fields.append(f"výkon={result.engine_power_kw}kW")
        if result.stk_valid_until: extracted_fields.append(f"STK={result.stk_valid_until}")
        if result.tyres: extracted_fields.append(f"pneumatiky={len(result.tyres)}")
        if result.plate: extracted_fields.append(f"SPZ={result.plate}")
        
        logger.info(f"[MDČR] ✅ Úspěšně dekódováno podle SPZ: {result.make} {result.model} ({result.production_year}) | {', '.join(extracted_fields)}")
        return result
        
    except httpx.RequestError as e:
        logger.error(f"[MDČR] Chyba při volání API podle SPZ: {e}")
        return None
    except Exception as e:
        logger.error(f"[MDČR] Neočekávaná chyba při volání API podle SPZ: {e}", exc_info=True)
        return None

