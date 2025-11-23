from dataclasses import dataclass
from typing import Dict, List


@dataclass
class Vehicle:
    vin: str
    plate: str
    name: str
    brand: str | None = None
    model: str | None = None
    year: int | None = None
    engine: str | None = None
    notes: str | None = None


@dataclass
class ServiceRecord:
    vehicle_vin: str
    date: str  # ISO string "YYYY-MM-DD" for now
    odometer_km: int
    price: float
    description: str
    category: str


class VehicleHubService:
    def __init__(self):
        self.vehicles: Dict[str, Vehicle] = {}
        self.records: List[ServiceRecord] = []

    def add_vehicle(self, vehicle: Vehicle) -> None:
        """Přidat vozidlo do seznamu vozidel."""
        self.vehicles[vehicle.vin] = vehicle

    def get_all_vehicles(self) -> list[Vehicle]:
        """Vrátit všechny vozidla."""
        return list(self.vehicles.values())

    def get_vehicle(self, vin: str) -> Vehicle | None:
        """Vrátit vozidlo podle VIN."""
        return self.vehicles.get(vin)

    def add_service_record(self, record: ServiceRecord) -> None:
        """Přidat záznam o službě."""
        self.records.append(record)

    def get_records_for_vehicle(self, vin: str) -> list[ServiceRecord]:
        """Vrátit záznamy o službách pro vozidlo podle VIN."""
        return [record for record in self.records if record.vehicle_vin == vin]

    def decode_vin(self, vin: str) -> dict[str, str]:  # TODO: connect real VIN API later
        """Decodovat VIN (prozatimni implementace)."""
        return {}
