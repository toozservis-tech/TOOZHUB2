"""
Modul pro e-mail notifikace ve Správě vozidel

Obsahuje funkce pro odesílání e-mail notifikací:
- Připomínky (reminders)
- Rezervace (reservations)
"""

from typing import Optional, Tuple
from datetime import date, datetime
from sqlalchemy.orm import Session

from src.core.branding import APP_DISPLAY_NAME
from src.modules.email_client.templates import build_app_url, render_email_layout, render_panel

# Import přímo z service.py, aby se zabránilo importu GUI komponenty
from src.modules.email_client.service import EmailService, EmailMessage
from src.modules.vehicle_hub.models import (
    Reminder,
    Reservation,
    Customer,
    Vehicle,
    EmailNotificationLog
)


def _resolve_tenant_id(*candidates: Optional[int]) -> int:
    """Vrátí první dostupný tenant_id, fallback je 1."""
    for value in candidates:
        if value is not None:
            return value
    return 1


def _add_email_log(
    db: Session,
    *,
    tenant_id: int,
    customer_id: Optional[int],
    email: str,
    subject: str,
    notification_type: str,
    entity_id: Optional[int] = None,
    status: str = "sent",
    error_message: Optional[str] = None,
) -> None:
    """Přidá záznam do email_notification_logs (commit dělá volající)."""
    entry = EmailNotificationLog(
        tenant_id=tenant_id,
        customer_id=customer_id,
        email=email,
        subject=subject,
        notification_type=notification_type,
        entity_id=entity_id,
        status=(status or "sent").lower(),
        error_message=error_message,
    )
    db.add(entry)


def _app_index_url() -> str:
    return build_app_url("/web/index.html")


def send_reminder_email(
    db: Session,
    reminder: Reminder,
    email_service: Optional[EmailService] = None,
    notification_type: str = "REMINDER",
    entity_id: Optional[int] = None,
) -> bool:
    """
    Odešle e-mail notifikaci pro připomínku
    
    Args:
        db: Database session
        reminder: Reminder objekt
        email_service: EmailService instance (vytvoří se, pokud není zadán)
    
    Returns:
        True pokud byl e-mail úspěšně odeslán, False jinak
    """
    if email_service is None:
        email_service = EmailService()
    
    if not email_service.is_configured():
        return False
    
    # Načíst zákazníka
    customer = db.query(Customer).filter(Customer.id == reminder.customer_id).first()
    if not customer or not customer.notify_email:
        return False

    tenant_id = _resolve_tenant_id(getattr(reminder, "tenant_id", None), getattr(customer, "tenant_id", None))
    log_entity_id = entity_id if entity_id is not None else getattr(reminder, "id", None)
    
    # Načíst vozidlo
    vehicle_name = "Obecná připomínka"
    if reminder.vehicle_id:
        vehicle = db.query(Vehicle).filter(Vehicle.id == reminder.vehicle_id).first()
        if vehicle:
            vehicle_name = vehicle.nickname or f"{vehicle.brand} {vehicle.model}" or vehicle.plate or "Neznámé vozidlo"
    
    # Formátovat obsah
    due_date_str = reminder.due_date.strftime("%d.%m.%Y") if reminder.due_date else "Neuvedeno"
    
    reminder_type_map = {
        "STK": "STK - Technická kontrola",
        "OLEJ": "Výměna oleje",
        "SERVIS": "Servis",
        "VLASTNI": "Vlastní připomínka"
    }
    reminder_type_display = reminder_type_map.get(reminder.type, reminder.type)
    
    today = date.today()
    days_until = (reminder.due_date - today).days if reminder.due_date else None
    
    if days_until == 0:
        subject = f"🚨 Dnes: {reminder_type_display} - {vehicle_name}"
        urgency = "dnes"
    elif days_until == 1:
        subject = f"⚠️  Zítra: {reminder_type_display} - {vehicle_name}"
        urgency = "zítra"
    elif days_until is not None:
        subject = f"📅 Připomínka: {reminder_type_display} - {vehicle_name}"
        urgency = f"za {days_until} dní"
    else:
        subject = f"📅 Připomínka: {reminder_type_display} - {vehicle_name}"
        urgency = "brzy"
    
    html_body = render_email_layout(
        title="Připomínka k vozidlu",
        subtitle=f"Naplánovaný termín {urgency}.",
        intro="Dobrý den,",
        paragraphs=[
            f"připomínáme Vám, že {urgency} máte naplánovanou připomínku.",
            "Nezapomeňte si včas zajistit potřebné úkony, aby vozidlo zůstalo bez omezení v provozu.",
        ],
        panels=[
            render_panel(
                title="Přehled připomínky",
                rows=[
                    ("Vozidlo", vehicle_name),
                    ("Typ", reminder_type_display),
                    ("Datum", due_date_str),
                    ("Popis", reminder.text),
                ],
            )
        ],
        cta_label="Otevřít aplikaci",
        cta_url=_app_index_url(),
        accent="#f59e0b",
    )
    
    text_body = f"""Dobrý den,

připomínáme Vám, že {urgency} máte naplánovanou připomínku:

Vozidlo: {vehicle_name}
Typ: {reminder_type_display}
Datum: {due_date_str}
Popis: {reminder.text}

Nezapomeňte včas zajistit potřebné úkony.

S pozdravem,
{APP_DISPLAY_NAME}

Otevřít aplikaci: {_app_index_url()}
"""
    
    try:
        message = EmailMessage(
            to=[customer.email],
            subject=subject,
            body=text_body,
            html_body=html_body
        )
        
        email_service.send_email(message)
        
        # Zalogovat
        _add_email_log(
            db,
            tenant_id=tenant_id,
            customer_id=customer.id,
            email=customer.email,
            subject=subject,
            notification_type=notification_type or "REMINDER",
            entity_id=log_entity_id,
            status="sent",
        )
        db.commit()
        
        return True
        
    except Exception as e:
        # Zalogovat chybu
        _add_email_log(
            db,
            tenant_id=tenant_id,
            customer_id=customer.id,
            email=customer.email,
            subject=subject,
            notification_type=notification_type or "REMINDER",
            entity_id=log_entity_id,
            status="failed",
            error_message=str(e),
        )
        db.commit()
        
        return False


def send_reminder_created_email(
    db: Session,
    reminder: Reminder,
    email_service: Optional[EmailService] = None
) -> bool:
    """
    Odešle e-mail notifikaci při vytvoření připomínky
    
    Args:
        db: Database session
        reminder: Reminder objekt
        email_service: EmailService instance (vytvoří se, pokud není zadán)
    
    Returns:
        True pokud byl e-mail úspěšně odeslán, False jinak
    """
    if email_service is None:
        email_service = EmailService()
    
    if not email_service.is_configured():
        return False
    
    # Načíst zákazníka
    customer = db.query(Customer).filter(Customer.id == reminder.customer_id).first()
    if not customer or not customer.notify_email:
        return False
    
    # Načíst vozidlo
    vehicle_name = "Obecná připomínka"
    if reminder.vehicle_id:
        vehicle = db.query(Vehicle).filter(Vehicle.id == reminder.vehicle_id).first()
        if vehicle:
            vehicle_name = vehicle.nickname or f"{vehicle.brand} {vehicle.model}" or vehicle.plate or "Neznámé vozidlo"
    
    # Formátovat obsah
    due_date_str = reminder.due_date.strftime("%d.%m.%Y") if reminder.due_date else "Neuvedeno"
    
    reminder_type_map = {
        "STK": "STK - Technická kontrola",
        "OLEJ": "Výměna oleje",
        "SERVIS": "Servis",
        "VLASTNI": "Vlastní připomínka",
        "GENERAL": "Obecná připomínka"
    }
    reminder_type_display = reminder_type_map.get(reminder.type, reminder.type)
    
    # Vypočítat dny do termínu
    today = date.today()
    if reminder.due_date:
        days_until = (reminder.due_date - today).days
        if days_until < 0:
            urgency_text = f"termín byl před {abs(days_until)} dny"
        elif days_until == 0:
            urgency_text = "termín je dnes"
        elif days_until == 1:
            urgency_text = "termín je zítra"
        else:
            urgency_text = f"termín je za {days_until} dní"
    else:
        urgency_text = "bez konkrétního termínu"
    
    subject = f"✅ Připomínka vytvořena: {reminder_type_display} - {vehicle_name}"
    
    html_body = render_email_layout(
        title="Připomínka byla vytvořena",
        subtitle="Nová položka je uložená a aktivní.",
        intro="Dobrý den,",
        paragraphs=[
            "potvrzujeme Vám, že byla vytvořena nová připomínka.",
            "Budete upozorněni předem podle svého nastavení v aplikaci.",
        ],
        panels=[
            render_panel(
                title="Přehled připomínky",
                rows=[
                    ("Vozidlo", vehicle_name),
                    ("Typ", reminder_type_display),
                    ("Datum", due_date_str),
                    ("Popis", reminder.text),
                    ("Termín", urgency_text),
                ],
                accent="#10b981",
                tone="#f0fdf4",
            )
        ],
        cta_label="Otevřít aplikaci",
        cta_url=_app_index_url(),
        accent="#f59e0b",
    )
    
    text_body = f"""Dobrý den,

potvrzujeme Vám, že byla vytvořena nová připomínka:

Vozidlo: {vehicle_name}
Typ: {reminder_type_display}
Datum: {due_date_str}
Popis: {reminder.text}
Termín: {urgency_text}

Upozornění:
Budete automaticky upozorněni předem podle Vašeho nastavení. Můžete si nastavit, kolik dní předem chcete být upozorněni v nastavení připomínek.

S pozdravem,
{APP_DISPLAY_NAME}

Otevřít aplikaci: {_app_index_url()}
"""
    
    try:
        message = EmailMessage(
            to=[customer.email],
            subject=subject,
            body=text_body,
            html_body=html_body
        )
        
        email_service.send_email(message)
        
        # Zalogovat
        _add_email_log(
            db,
            tenant_id=_resolve_tenant_id(getattr(reminder, "tenant_id", None), getattr(customer, "tenant_id", None)),
            customer_id=customer.id,
            email=customer.email,
            subject=subject,
            notification_type="REMINDER_CREATED",
            entity_id=getattr(reminder, "id", None),
            status="sent",
        )
        db.commit()
        
        return True
        
    except Exception as e:
        # Zalogovat chybu
        _add_email_log(
            db,
            tenant_id=_resolve_tenant_id(getattr(reminder, "tenant_id", None), getattr(customer, "tenant_id", None)),
            customer_id=customer.id,
            email=customer.email,
            subject=subject,
            notification_type="REMINDER_CREATED",
            entity_id=getattr(reminder, "id", None),
            status="failed",
            error_message=str(e),
        )
        db.commit()
        
        return False


def send_reservation_created_email(
    db: Session,
    reservation: Reservation,
    email_service: Optional[EmailService] = None,
    service_link_claim_url: Optional[str] = None,
    requires_service_link_confirmation: bool = False,
) -> Tuple[bool, bool]:
    """
    Odešle e-mail notifikace při vytvoření rezervace (zákazníkovi i servisu)
    
    Args:
        db: Database session
        reservation: Reservation objekt
        email_service: EmailService instance (vytvoří se, pokud není zadán)
        service_link_claim_url: URL pro 1-klik potvrzení propojení klienta se servisem
        requires_service_link_confirmation: Pokud True, servis musí nejprve potvrdit propojení klienta
    
    Returns:
        Tuple (customer_sent, service_sent) - True pokud byl e-mail odeslán
    """
    if email_service is None:
        email_service = EmailService()
    
    if not email_service.is_configured():
        return False, False
    
    customer_sent = False
    service_sent = False
    logs_written = False
    
    # Načíst zákazníka a servis
    customer = db.query(Customer).filter(Customer.id == reservation.customer_id).first()
    service = db.query(Customer).filter(Customer.id == reservation.service_id).first()
    vehicle = db.query(Vehicle).filter(Vehicle.id == reservation.vehicle_id).first()
    
    if not customer or not service or not vehicle:
        return False, False
    
    vehicle_name = vehicle.nickname or f"{vehicle.brand} {vehicle.model}" or vehicle.plate or "Neznámé vozidlo"
    start_datetime_str = reservation.start_datetime.strftime("%d.%m.%Y %H:%M")
    tenant_id = _resolve_tenant_id(
        getattr(reservation, "tenant_id", None),
        getattr(customer, "tenant_id", None),
        getattr(service, "tenant_id", None),
    )
    customer_waiting_text = (
        "Rezervace čeká na potvrzení servisem. Servisu jsme poslali žádost o přiřazení klienta k rezervaci."
        if requires_service_link_confirmation
        else "Rezervace čeká na potvrzení servisem. Obdržíte další e-mail po potvrzení."
    )
    
    # E-mail pro zákazníka
    if customer.notify_email:
        subject = f"✅ Rezervace vytvořena - {vehicle_name}"
        
        html_body = render_email_layout(
            title="Rezervace vytvořena",
            subtitle="Žádost byla uložena a čeká na další krok.",
            intro="Dobrý den,",
            paragraphs=[customer_waiting_text],
            panels=[
                render_panel(
                    title="Detaily rezervace",
                    rows=[
                        ("Vozidlo", vehicle_name),
                        ("Servis", service.name or service.email),
                        ("Typ servisu", reservation.service_type or "Neuvedeno"),
                        ("Datum a čas", start_datetime_str),
                        ("Stav", "Čeká na potvrzení"),
                        ("Poznámka", reservation.note or "Bez poznámky"),
                    ],
                    accent="#10b981",
                    tone="#f0fdf4",
                )
            ],
            cta_label="Zobrazit rezervaci",
            cta_url=_app_index_url(),
            accent="#f59e0b",
        )
        
        text_body = f"""Dobrý den,

Vaše rezervace byla úspěšně vytvořena:

Vozidlo: {vehicle_name}
Servis: {service.name or service.email}
Typ servisu: {reservation.service_type or 'Neuvedeno'}
Datum a čas: {start_datetime_str}
Status: Čeká na potvrzení
{f'Poznámka: {reservation.note}' if reservation.note else ''}

{customer_waiting_text}

S pozdravem,
{APP_DISPLAY_NAME}

Zobrazit rezervaci: {_app_index_url()}
"""
        
        try:
            message = EmailMessage(
                to=[customer.email],
                subject=subject,
                body=text_body,
                html_body=html_body
            )
            email_service.send_email(message)
            
            # Zalogovat
            _add_email_log(
                db,
                tenant_id=tenant_id,
                customer_id=customer.id,
                email=customer.email,
                subject=subject,
                notification_type="RESERVATION_CREATED",
                entity_id=reservation.id,
                status="sent",
            )
            logs_written = True
            customer_sent = True
        except Exception as e:
            _add_email_log(
                db,
                tenant_id=tenant_id,
                customer_id=customer.id,
                email=customer.email,
                subject=subject,
                notification_type="RESERVATION_CREATED",
                entity_id=reservation.id,
                status="failed",
                error_message=str(e),
            )
            logs_written = True
    
    # E-mail pro servis
    if service.email:
        if requires_service_link_confirmation and service_link_claim_url:
            subject = f"🔔 Nová rezervace – potvrďte propojení klienta ({vehicle_name})"
        else:
            subject = f"🔔 Nová rezervace - {vehicle_name}"

        service_intro = (
            "byla vytvořena nová rezervace. Klient ještě není propojen se servisním účtem, proto prosím nejprve potvrďte přiřazení jedním klikem."
            if requires_service_link_confirmation
            else "byla vytvořena nová rezervace:"
        )
        service_action_html = (
            f"""
        <div style="text-align: center;">
            <a href="{service_link_claim_url}" class="button">Přiřadit klienta k rezervaci</a>
        </div>
        <p style="font-size:13px; color:#64748b;">Pokud tlačítko nefunguje, otevřete odkaz ručně:<br><a href="{service_link_claim_url}">{service_link_claim_url}</a></p>
"""
            if requires_service_link_confirmation and service_link_claim_url
            else ""
        )
        service_action_text = (
            f"Potvrzení propojení: {service_link_claim_url}"
            if requires_service_link_confirmation and service_link_claim_url
            else "Prosím potvrďte nebo zrušte rezervaci v administračním panelu."
        )
        
        html_body = render_email_layout(
            title="Nová rezervace",
            subtitle="Oznámení pro servisní účet.",
            intro="Dobrý den,",
            paragraphs=[
                service_intro,
                (
                    "Po potvrzení propojení bude rezervace viditelná v servisním přehledu."
                    if requires_service_link_confirmation and service_link_claim_url
                    else "Prosím potvrďte nebo zrušte rezervaci v administračním panelu."
                ),
            ],
            panels=[
                render_panel(
                    title="Detaily rezervace",
                    rows=[
                        ("Zákazník", customer.name or customer.email),
                        ("Vozidlo", vehicle_name),
                        ("Typ servisu", reservation.service_type or "Neuvedeno"),
                        ("Datum a čas", start_datetime_str),
                        ("Poznámka", reservation.note or "Bez poznámky"),
                    ],
                    accent="#3b82f6",
                    tone="#eff6ff",
                ),
                *(
                    [
                        render_panel(
                            title="Potvrzení propojení",
                            message=f"Odkaz pro rychlé přiřazení klienta:\n{service_link_claim_url}",
                            accent="#f59e0b",
                            tone="#fff7ed",
                        )
                    ]
                    if requires_service_link_confirmation and service_link_claim_url
                    else []
                ),
            ],
            cta_label="Otevřít admin panel",
            cta_url=build_app_url("/web_admin/"),
            accent="#f59e0b",
        )
        
        text_body = f"""Dobrý den,

byla vytvořena nová rezervace:

Zákazník: {customer.name or customer.email}
Vozidlo: {vehicle_name}
Typ servisu: {reservation.service_type or 'Neuvedeno'}
Datum a čas: {start_datetime_str}
{f'Poznámka: {reservation.note}' if reservation.note else ''}

{service_action_text}

S pozdravem,
{APP_DISPLAY_NAME}
"""
        
        try:
            message = EmailMessage(
                to=[service.email],
                subject=subject,
                body=text_body,
                html_body=html_body
            )
            email_service.send_email(message)
            
            # Zalogovat
            _add_email_log(
                db,
                tenant_id=tenant_id,
                customer_id=service.id,
                email=service.email,
                subject=subject,
                notification_type="RESERVATION_CREATED_SERVICE",
                entity_id=reservation.id,
                status="sent",
            )
            logs_written = True
            service_sent = True
        except Exception as e:
            _add_email_log(
                db,
                tenant_id=tenant_id,
                customer_id=service.id,
                email=service.email,
                subject=subject,
                notification_type="RESERVATION_CREATED_SERVICE",
                entity_id=reservation.id,
                status="failed",
                error_message=str(e),
            )
            logs_written = True
    
    if logs_written:
        db.commit()
    
    return customer_sent, service_sent


def send_reservation_status_email(
    db: Session,
    reservation: Reservation,
    old_status: str,
    email_service: Optional[EmailService] = None
) -> bool:
    """
    Odešle e-mail notifikaci při změně stavu rezervace (CONFIRMED nebo CANCELLED)
    
    Args:
        db: Database session
        reservation: Reservation objekt
        old_status: Původní status (pro logování)
        email_service: EmailService instance (vytvoří se, pokud není zadán)
    
    Returns:
        True pokud byl e-mail úspěšně odeslán, False jinak
    """
    if email_service is None:
        email_service = EmailService()
    
    if not email_service.is_configured():
        return False
    
    # Posílat e-mail pouze pro CONFIRMED a CANCELLED
    if reservation.status not in ["CONFIRMED", "CANCELLED"]:
        return False
    
    # Načíst zákazníka a vozidlo
    customer = db.query(Customer).filter(Customer.id == reservation.customer_id).first()
    service = db.query(Customer).filter(Customer.id == reservation.service_id).first()
    vehicle = db.query(Vehicle).filter(Vehicle.id == reservation.vehicle_id).first()
    
    if not customer or not customer.notify_email or not vehicle or not service:
        return False
    
    vehicle_name = vehicle.nickname or f"{vehicle.brand} {vehicle.model}" or vehicle.plate or "Neznámé vozidlo"
    start_datetime_str = reservation.start_datetime.strftime("%d.%m.%Y %H:%M")
    
    if reservation.status == "CONFIRMED":
        subject = f"✅ Rezervace potvrzena - {vehicle_name}"
        status_text = "potvrzena"
        status_color = "#10b981"
        status_emoji = "✅"
    else:  # CANCELLED
        subject = f"❌ Rezervace zrušena - {vehicle_name}"
        status_text = "zrušena"
        status_color = "#ef4444"
        status_emoji = "❌"
    
    html_body = render_email_layout(
        title=f"Rezervace {status_text}",
        subtitle=f"Aktuální stav: {status_emoji} {status_text.upper()}",
        intro="Dobrý den,",
        paragraphs=[
            f"Vaše rezervace byla {status_text}.",
            (
                f"Rezervace byla {status_text} servisem. Těšíme se na Vás!"
                if reservation.status == "CONFIRMED"
                else "Rezervace byla zrušena. Pokud potřebujete, můžete vytvořit novou rezervaci."
            ),
        ],
        panels=[
            render_panel(
                title="Detaily rezervace",
                rows=[
                    ("Vozidlo", vehicle_name),
                    ("Servis", service.name or service.email),
                    ("Typ servisu", reservation.service_type or "Neuvedeno"),
                    ("Datum a čas", start_datetime_str),
                    ("Stav", f"{status_emoji} {status_text.upper()}"),
                    ("Poznámka", reservation.note or "Bez poznámky"),
                ],
                accent=status_color,
                tone="#f8fafc",
            )
        ],
        cta_label="Zobrazit rezervaci",
        cta_url=_app_index_url(),
        accent="#f59e0b",
    )
    
    text_body = f"""Dobrý den,

Vaše rezervace byla {status_text}:

Vozidlo: {vehicle_name}
Servis: {service.name or service.email}
Typ servisu: {reservation.service_type or 'Neuvedeno'}
Datum a čas: {start_datetime_str}
Status: {status_text.upper()}
{f'Poznámka: {reservation.note}' if reservation.note else ''}

{f'Rezervace byla {status_text} servisem. Těšíme se na Vás!' if reservation.status == 'CONFIRMED' else 'Rezervace byla zrušena. Pokud potřebujete, můžete vytvořit novou rezervaci.'}

S pozdravem,
{APP_DISPLAY_NAME}

Zobrazit rezervaci: {_app_index_url()}
"""
    
    try:
        message = EmailMessage(
            to=[customer.email],
            subject=subject,
            body=text_body,
            html_body=html_body
        )
        email_service.send_email(message)
        
        # Zalogovat
        _add_email_log(
            db,
            tenant_id=_resolve_tenant_id(
                getattr(reservation, "tenant_id", None),
                getattr(customer, "tenant_id", None),
                getattr(service, "tenant_id", None),
            ),
            customer_id=customer.id,
            email=customer.email,
            subject=subject,
            notification_type=f"RESERVATION_{reservation.status}",
            entity_id=reservation.id,
            status="sent",
        )
        db.commit()
        
        return True
        
    except Exception as e:
        _add_email_log(
            db,
            tenant_id=_resolve_tenant_id(
                getattr(reservation, "tenant_id", None),
                getattr(customer, "tenant_id", None),
                getattr(service, "tenant_id", None),
            ),
            customer_id=customer.id,
            email=customer.email,
            subject=subject,
            notification_type=f"RESERVATION_{reservation.status}",
            entity_id=reservation.id,
            status="failed",
            error_message=str(e),
        )
        db.commit()
        
        return False


def send_reservation_rescheduled_email(
    db: Session,
    reservation: Reservation,
    old_start_datetime: datetime,
    old_end_datetime: Optional[datetime] = None,
    changed_by_role: Optional[str] = None,
    email_service: Optional[EmailService] = None,
) -> bool:
    """
    Odešle e-mail notifikaci při změně termínu rezervace.

    Args:
        db: Database session
        reservation: Reservation objekt po změně
        old_start_datetime: Původní datum/čas začátku
        old_end_datetime: Původní datum/čas konce (volitelně)
        changed_by_role: Role, která změnu provedla (service/admin)
        email_service: EmailService instance (vytvoří se, pokud není zadán)

    Returns:
        True pokud byl e-mail úspěšně odeslán, False jinak
    """
    if email_service is None:
        email_service = EmailService()

    if not email_service.is_configured():
        return False

    customer = db.query(Customer).filter(Customer.id == reservation.customer_id).first()
    service = db.query(Customer).filter(Customer.id == reservation.service_id).first()
    vehicle = db.query(Vehicle).filter(Vehicle.id == reservation.vehicle_id).first()

    if not customer or not customer.notify_email or not service or not vehicle:
        return False

    def _format_range(start_dt: Optional[datetime], end_dt: Optional[datetime]) -> str:
        if not start_dt:
            return "Neuvedeno"
        start_str = start_dt.strftime("%d.%m.%Y %H:%M")
        if end_dt:
            return f"{start_str} - {end_dt.strftime('%H:%M')}"
        return start_str

    vehicle_name = vehicle.nickname or f"{vehicle.brand} {vehicle.model}" or vehicle.plate or "Neznámé vozidlo"
    old_range = _format_range(old_start_datetime, old_end_datetime)
    new_range = _format_range(reservation.start_datetime, reservation.end_datetime)
    role_key = str(changed_by_role or "").strip().lower()
    actor_label = "servis"
    if role_key in {"admin", "developer_admin"}:
        actor_label = "provozovatel"

    status_map = {
        "PENDING": "Čeká na potvrzení",
        "CONFIRMED": "Potvrzena",
        "COMPLETED": "Dokončena",
        "CANCELLED": "Zrušena",
    }
    status_label = status_map.get(str(reservation.status or "").upper(), str(reservation.status or "Neznámý"))

    subject = f"🔄 Změna termínu rezervace - {vehicle_name}"

    html_body = render_email_layout(
        title="Změna termínu rezervace",
        subtitle=f"{actor_label.capitalize()} upravil termín rezervace.",
        intro="Dobrý den,",
        paragraphs=[
            f"{actor_label.capitalize()} upravil termín Vaší rezervace.",
            "Pokud Vám nový termín nevyhovuje, můžete rezervaci v aplikaci zrušit a vytvořit novou.",
        ],
        panels=[
            render_panel(
                title="Přehled změny",
                rows=[
                    ("Vozidlo", vehicle_name),
                    ("Servis", service.name or service.email),
                    ("Typ servisu", reservation.service_type or "Neuvedeno"),
                    ("Původní termín", old_range),
                    ("Nový termín", new_range),
                    ("Stav rezervace", status_label),
                    ("Poznámka", reservation.note or "Bez poznámky"),
                ],
                accent="#4f46e5",
                tone="#eef2ff",
            )
        ],
        cta_label="Otevřít rezervace",
        cta_url=_app_index_url(),
        accent="#f59e0b",
    )

    text_body = f"""Dobrý den,

{actor_label.capitalize()} upravil termín Vaší rezervace.

Vozidlo: {vehicle_name}
Servis: {service.name or service.email}
Typ servisu: {reservation.service_type or 'Neuvedeno'}
Původní termín: {old_range}
Nový termín: {new_range}
Stav rezervace: {status_label}
{f'Poznámka: {reservation.note}' if reservation.note else ''}

Pokud Vám nový termín nevyhovuje, můžete rezervaci v aplikaci zrušit a vytvořit novou.

S pozdravem,
{APP_DISPLAY_NAME}

Otevřít rezervace: {_app_index_url()}
"""

    try:
        message = EmailMessage(
            to=[customer.email],
            subject=subject,
            body=text_body,
            html_body=html_body
        )
        email_service.send_email(message)

        _add_email_log(
            db,
            tenant_id=_resolve_tenant_id(
                getattr(reservation, "tenant_id", None),
                getattr(customer, "tenant_id", None),
                getattr(service, "tenant_id", None),
            ),
            customer_id=customer.id,
            email=customer.email,
            subject=subject,
            notification_type="RESERVATION_RESCHEDULED",
            entity_id=reservation.id,
            status="sent",
        )
        db.commit()
        return True
    except Exception as e:
        _add_email_log(
            db,
            tenant_id=_resolve_tenant_id(
                getattr(reservation, "tenant_id", None),
                getattr(customer, "tenant_id", None),
                getattr(service, "tenant_id", None),
            ),
            customer_id=customer.id,
            email=customer.email,
            subject=subject,
            notification_type="RESERVATION_RESCHEDULED",
            entity_id=reservation.id,
            status="failed",
            error_message=str(e),
        )
        db.commit()
        return False
