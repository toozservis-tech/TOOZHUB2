"""Allowlisted UI diagnostics. Never accept arbitrary labels, form values or actors."""
import json
from datetime import datetime, timezone, timedelta

from pydantic import BaseModel, ConfigDict, Field, AwareDatetime, field_validator

from src.modules.vehicle_hub.database import AuditSessionLocal
from src.modules.vehicle_hub.models import SecurityAccessLog
from src.server.security_tracking import access_diagnostics, extract_client_ip

UI_ACTIONS = {
    'screen.dashboard': 'Otevřel přehled',
    'screen.vehicles': 'Otevřel vozidla',
    'screen.services': 'Otevřel servisy',
    'screen.reservations': 'Otevřel rezervace',
    'screen.profile': 'Otevřel profil',
    'screen.service_clients': 'Otevřel klienty servisu',
    'screen.service_reminders': 'Otevřel připomínky servisu',
    'screen.vehicle_detail': 'Otevřel detail vozidla',
    'screen.billing': 'Otevřel tarify a předplatné',
    'screen.admin_activity': 'Otevřel aktivitu uživatelů',
    'action.vehicles.add': 'Klepl na Přidat vozidlo',
    'action.vehicles.edit': 'Klepl na Upravit vozidlo',
    'action.vehicles.remove': 'Klepl na Odebrat z profilu',
    'action.vehicles.refresh': 'Obnovil přehled vozidel tahem dolů',
    'action.vehicle.save': 'Klepl na Uložit vozidlo',
    'action.vehicle.record_add': 'Klepl na Přidat servisní záznam',
    'action.vehicle.report': 'Klepl na PDF report',
    'action.orv.open': 'Otevřel načítání dokladu ORV',
    'action.orv.qr_camera': 'Zvolil načtení QR fotoaparátem',
    'action.orv.qr_gallery': 'Zvolil QR kód z galerie',
    'action.orv.front_camera': 'Zvolil vyfocení přední strany dokladu',
    'action.orv.back_camera': 'Zvolil vyfocení zadní strany dokladu',
    'action.orv.front_gallery': 'Zvolil přední stranu dokladu z galerie',
    'action.orv.back_gallery': 'Zvolil zadní stranu dokladu z galerie',
    'action.billing.show_plans': 'Klepl na Zobrazit tarify',
    'action.billing.purchase': 'Klepl na výběr předplatného u Applu',
    'action.billing.restore': 'Klepl na Obnovit nákupy',
    'action.billing.manage': 'Otevřel správu předplatného u Applu',
}


class UIEvent(BaseModel):
    model_config = ConfigDict(extra='forbid')
    code: str = Field(max_length=64)
    occurred_at: AwareDatetime

    @field_validator('code')
    @classmethod
    def known_code(cls, value):
        if value not in UI_ACTIONS:
            raise ValueError('Unknown activity code')
        return value

    @field_validator('occurred_at')
    @classmethod
    def recent_time(cls, value):
        now = datetime.now(timezone.utc)
        if not now - timedelta(days=1) <= value <= now + timedelta(minutes=5):
            raise ValueError('Activity timestamp outside supported range')
        return value


class UIEventBatch(BaseModel):
    model_config = ConfigDict(extra='forbid')
    events: list[UIEvent] = Field(min_length=1, max_length=20)


def save_ui_events(request, events):
    actor = request.state.activity_actor  # authenticated server identity only
    diagnostics = access_diagnostics(request)
    with AuditSessionLocal() as db:
        for event in events:
            db.add(SecurityAccessLog(**actor,
                event_type='client_screen' if event.code.startswith('screen.') else 'client_action',
                endpoint='/user/activity', ip_address=extract_client_ip(request),
                created_at=event.occurred_at.astimezone(timezone.utc).replace(tzinfo=None),
                user_agent=request.headers.get('user-agent', '')[:256],
                details=json.dumps({**diagnostics, 'ui_code': event.code,
                                    'occurred_at': event.occurred_at.astimezone(timezone.utc).isoformat(),
                                    'received_at': datetime.now(timezone.utc).isoformat()}, ensure_ascii=False)))
        db.commit()
