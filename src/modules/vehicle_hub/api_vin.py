from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/vin", tags=["vin"])

class TyreResponse(BaseModel):
    tyres: list[str]

@router.get("/tyres", response_model=TyreResponse)
def get_tyres_from_vin(vin: str):
    vin = vin.strip().upper()
    if len(vin) != 17:
        raise HTTPException(status_code=400, detail="Neplatné VIN")

    # TODO: sem přijde reálné API – zatím placeholder
    raw_tyres = [
        "205/55 R16 91V",
        "225/45 R17 94W",
        "225/40 R18 92Y (alternativní)"
    ]

    # Odebrání duplicit a seřazení
    unique = sorted(set([t.strip() for t in raw_tyres if t.strip()]))

    if not unique:
        raise HTTPException(status_code=404, detail="Pro toto VIN nebyly nalezeny rozměry pneu")

    return TyreResponse(tyres=unique)
