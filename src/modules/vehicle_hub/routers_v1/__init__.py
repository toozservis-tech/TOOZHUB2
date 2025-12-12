"""
API Routery pro TooZ Hub v1.0
Všechny endpointy pod prefixem /api/v1/
"""
from fastapi import APIRouter

from . import vehicles, service_records, service_intake, reservations, reminders, reminder_settings, ai, services, bot

# Hlavní router pro v1 API
api_router = APIRouter(prefix="/api/v1", tags=["api-v1"])

# Zahrnout všechny sub-routery
api_router.include_router(vehicles.router)
api_router.include_router(service_records.router)
api_router.include_router(service_intake.router)
api_router.include_router(reservations.router)
api_router.include_router(reminders.router)
api_router.include_router(reminder_settings.router)  # Nastavení připomínek
api_router.include_router(services.router)
api_router.include_router(ai.router)
api_router.include_router(bot.router)  # AI Asistent Bot

__all__ = ["api_router"]
