"""
Generování servisních intervalů na základě parametrů vozidla
"""
import logging
from typing import List, Dict, Optional

from .models import VehicleDecodedData

logger = logging.getLogger(__name__)


def generate_service_intervals(vehicle: VehicleDecodedData) -> List[Dict]:
    """
    Vrátí seznam doporučených servisních intervalů.
    
    Args:
        vehicle: Dekódovaná data o vozidle
        
    Returns:
        Seznam intervalů s typem, km a měsíci
    """
    intervals = []
    
    fuel_type = (vehicle.fuel_type or "").lower()
    engine_displacement = vehicle.engine_displacement_cc or 0
    emission_standard = vehicle.emission_standard or ""
    
    # Výměna oleje - základní interval
    oil_interval_km = 15000
    oil_interval_months = 12
    
    # Upravit podle typu paliva a velikosti motoru
    if fuel_type == "diesel":
        # Diesel vozidla obvykle potřebují častější výměnu oleje
        oil_interval_km = 15000
        oil_interval_months = 12
    elif fuel_type == "petrol":
        # Benzín může mít delší intervaly (pokud není turbo)
        if engine_displacement > 0:
            # Větší motory nebo novější vozidla mohou mít delší intervaly
            if engine_displacement >= 2000:
                oil_interval_km = 20000
                oil_interval_months = 12
            else:
                oil_interval_km = 15000
                oil_interval_months = 12
        else:
            oil_interval_km = 15000
            oil_interval_months = 12
    
    # Emisní norma může ovlivnit intervaly
    if "Euro 6" in emission_standard or "6" in emission_standard:
        # Novější vozidla s Euro 6 mohou mít delší intervaly
        oil_interval_km = max(oil_interval_km, 20000)
    
    intervals.append({
        "type": "oil_change",
        "name": "Výměna oleje a olejového filtru",
        "km": oil_interval_km,
        "months": oil_interval_months,
        "priority": "high"
    })
    
    # Výměna vzduchového filtru
    intervals.append({
        "type": "air_filter",
        "name": "Výměna vzduchového filtru",
        "km": 30000,
        "months": 24,
        "priority": "medium"
    })
    
    # Výměna palivového filtru (hlavně diesel)
    if fuel_type == "diesel":
        intervals.append({
            "type": "fuel_filter",
            "name": "Výměna palivového filtru",
            "km": 60000,
            "months": 36,
            "priority": "medium"
        })
    
    # Výměna brzdové kapaliny
    intervals.append({
        "type": "brake_fluid",
        "name": "Výměna brzdové kapaliny",
        "km": 60000,
        "months": 24,
        "priority": "high"
    })
    
    # Výměna chladicí kapaliny
    intervals.append({
        "type": "coolant",
        "name": "Výměna chladicí kapaliny",
        "km": 120000,
        "months": 60,
        "priority": "medium"
    })
    
    # Výměna rozvodů (řemen/řetěz)
    # Obvykle kolem 120-150k km nebo podle doporučení výrobce
    intervals.append({
        "type": "timing_belt",
        "name": "Kontrola/výměna rozvodového řemene",
        "km": 120000,
        "months": 72,
        "priority": "high"
    })
    
    # Výměna svíček (benzín) / žhavicích svíček (diesel)
    if fuel_type == "petrol":
        spark_plug_interval = 60000 if engine_displacement >= 2000 else 40000
        intervals.append({
            "type": "spark_plugs",
            "name": "Výměna zapalovacích svíček",
            "km": spark_plug_interval,
            "months": 48,
            "priority": "medium"
        })
    elif fuel_type == "diesel":
        intervals.append({
            "type": "glow_plugs",
            "name": "Kontrola/výměna žhavicích svíček",
            "km": 100000,
            "months": 60,
            "priority": "low"
        })
    
    # Kontrola brzd
    intervals.append({
        "type": "brake_inspection",
        "name": "Kontrola brzd (destičky, kotouče)",
        "km": 30000,
        "months": 24,
        "priority": "high"
    })
    
    logger.debug(f"[INTERVALS] Vygenerováno {len(intervals)} servisních intervalů")
    return intervals



